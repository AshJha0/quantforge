"""K-8 phase 2: generator of the out-of-sample case set (specifications/06-risk/bermudan-ladder-k8.md,
"Phase 2 acceptance"; ruling KR-113).

The cases are drawn from the stated envelope by the rule below with a fixed seed, so that nobody picks
them by hand. This script computes inputs only: the curve, the schedule and the strike. It never calls
the pricing method or QuantLib, and the lane that wrote it ran neither on these cases.

Only `random.Random(SEED).random()` is used (the Mersenne Twister double, stable across Python
versions); every other draw is arithmetic on that number, in the order written.

Usage: python oracle/python/k8_phase2_cases.py          writes oracle/K8_PHASE2_CASES.json
       python oracle/python/k8_phase2_cases.py --check  fails if the file differs from a fresh build
"""

import hashlib
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "oracle/K8_PHASE2_CASES.json"
SEED = 20261119
N_RANDOM = 8  # random cases per cell
A_RANGE = (0.005, 0.20)  # mean reversion, log-uniform
SIGMA_RANGE = (0.002, 0.02)  # short-rate volatility, log-uniform
T0_DAYS = (30, 1095)  # first exercise date, whole days
K_MIN = 0.001
# Curve node sets, whole days from the valuation date (times are days / 365).
NODES = {
    "A_acceptance": [182, 365, 730, 1095, 1826, 2557, 3652, 5479, 7305, 10957],
    "B_standard": [91, 182, 365, 730, 1095, 1825, 2555, 3650, 5475, 7300, 10950],
    "C_off_dates": [
        120,
        300,
        500,
        900,
        1300,
        1700,
        2100,
        2600,
        3700,
        5500,
        7300,
        10950,
    ],
}
# Cells: (name, swaption_type, sign of d = (K - S) / (sigma sqrt(t_m)), |d| band). For a payer the
# strike below the forward (d < 0) is in the money; for a receiver the strike above it (d > 0).
CELLS = [
    ("near_payer", "PAYER", 0, (0.0, 0.5)),
    ("near_receiver", "RECEIVER", 0, (0.0, 0.5)),
    ("mid_itm_payer", "PAYER", -1, (0.5, 1.5)),
    ("mid_otm_payer", "PAYER", 1, (0.5, 1.5)),
    ("mid_itm_receiver", "RECEIVER", 1, (0.5, 1.5)),
    ("mid_otm_receiver", "RECEIVER", -1, (0.5, 1.5)),
    ("far_itm_payer", "PAYER", -1, (1.5, 3.0)),
    ("far_otm_payer", "PAYER", 1, (1.5, 3.0)),
    ("far_itm_receiver", "RECEIVER", 1, (1.5, 3.0)),
    ("far_otm_receiver", "RECEIVER", -1, (1.5, 3.0)),
]
PATTERNS = (
    "all_reset_dates",
    "every_second_reset_date",
    "first_and_last_reset_date",
    "first_reset_date_only",
)


def log_uniform(u: float, lo: float, hi: float) -> float:
    return lo * math.exp(u * math.log(hi / lo))


def zero_rate(t: float, b0: float, b1: float, b2: float, tau: float) -> float:
    """Nelson-Siegel zero rate, continuous compounding."""
    x = t / tau
    f = -math.expm1(-x) / x
    return b0 + b1 * f + b2 * (f - math.exp(-x))


def ln_p(times: list[float], dfs: list[float], s: float) -> float:
    """ln P(0, s) by the rule of spec step 2: linear in time between nodes, the last segment continued."""
    ts, ls = [0.0, *times], [0.0, *[math.log(d) for d in dfs]]
    k = len(ts) - 2
    for j in range(len(ts) - 1):
        if ts[j] <= s < ts[j + 1]:
            k = j
            break
    w = (s - ts[k]) / (ts[k + 1] - ts[k])
    return ls[k] + (ls[k + 1] - ls[k]) * w


def draw_curve(rng: random.Random) -> dict[str, Any]:
    name = list(NODES)[int(3 * rng.random())]
    times = [d / 365.0 for d in NODES[name]]
    for _ in range(1000):
        b0 = 0.01 + 0.05 * rng.random()
        b1 = -0.02 + 0.04 * rng.random()
        b2 = -0.02 + 0.04 * rng.random()
        tau = 1.0 + 4.0 * rng.random()
        zs = [zero_rate(t, b0, b1, b2, tau) for t in times]
        dfs = [round(math.exp(-z * t), 10) for z, t in zip(zs, times, strict=True)]
        # Accepted only if every zero rate is at least 20 bp and every forward between nodes is at least 10 bp.
        fwd = [
            -(math.log(b) - math.log(a)) / (tb - ta)
            for a, b, ta, tb in zip(
                [1.0, *dfs], dfs, [0.0, *times], times, strict=False
            )
        ]
        if min(zs) >= 0.002 and min(fwd) >= 0.001:
            return {
                "node_set": name,
                "ns": [b0, b1, b2, tau],
                "times": times,
                "discount_factors": dfs,
            }
    raise SystemExit("no admissible curve in 1000 draws")


def build(
    rng: random.Random,
    cell: tuple[str, str, int, tuple[float, float]],
    corner: int | None,
) -> dict[str, Any]:
    """One case. `corner` None is a random case; 0..3 is an edge case at a corner of (a, sigma) with |d| at the
    outer edge of the cell's band, the first exercise date at an end of its range and every reset date exercisable.
    A strike below K_MIN: a random case is redrawn; an edge case is set to K_MIN and filed by its realised d."""
    name, kind, sign, band = cell
    for _ in range(1000):
        curve = draw_curve(rng)
        u_period, u_t0, u_n, u_pat, u_a, u_s, u_d, u_sign = (
            rng.random() for _ in range(8)
        )
        if corner is None:
            period = 365 if u_period < 0.5 else 182
            t0 = T0_DAYS[0] + int(u_t0 * (T0_DAYS[1] - T0_DAYS[0] + 1))
            pattern = PATTERNS[int(4 * u_pat)]
            a, sigma = log_uniform(u_a, *A_RANGE), log_uniform(u_s, *SIGMA_RANGE)
            absd = band[0] + u_d * (band[1] - band[0])
        else:
            period = 182 if corner < 2 else 365
            t0 = T0_DAYS[corner % 2]
            pattern = PATTERNS[0]
            a, sigma = A_RANGE[corner // 2], SIGMA_RANGE[corner % 2]
            absd = band[1]
        n = (
            (2 + int(9 * u_n)) if period == 365 else (4 + int(17 * u_n))
        )  # swap length 2 to 10 years
        resets = [t0 + k * period for k in range(n)]
        pays = [t0 + (k + 1) * period for k in range(n)]
        ex = {
            "all_reset_dates": resets,
            "every_second_reset_date": resets[::2],
            "first_and_last_reset_date": [resets[0], resets[-1]],
            "first_reset_date_only": resets[:1],
        }[pattern]
        ts, ds = curve["times"], curve["discount_factors"]
        p = [math.exp(ln_p(ts, ds, d / 365.0)) for d in [t0, *pays]]
        annuity = sum((period / 365.0) * x for x in p[1:])
        fwd = (p[0] - p[-1]) / annuity
        s = sign if sign else (1 if u_sign < 0.5 else -1)
        d_std = s * absd
        scale = sigma * math.sqrt(ex[-1] / 365.0)
        strike = fwd + d_std * scale
        if strike < K_MIN and corner is None:
            continue  # a random case is redrawn whole
        if strike < K_MIN:
            # An edge case is moved to the strike floor, which is itself an edge of the envelope, and
            # is filed in the cell its realised d falls in (bands: near <= 0.5 < mid <= 1.5 < far).
            strike = K_MIN
            d_std = (strike - fwd) / scale
            band_name = (
                "near" if abs(d_std) <= 0.5 else ("mid" if abs(d_std) <= 1.5 else "far")
            )
            money = (
                ""
                if band_name == "near"
                else ("itm_" if (d_std < 0) == (kind == "PAYER") else "otm_")
            )
            name = f"{band_name}_{money}{kind.lower()}"
        return {
            "cell": name,
            "nominal_cell": cell[0],
            "kind": "random" if corner is None else f"edge corner {corner}",
            "node_set": curve["node_set"],
            "nelson_siegel": curve["ns"],
            "period_days": period,
            "first_exercise_days": t0,
            "exercise_pattern": pattern,
            "forward_swap_rate": fwd,
            "d": d_std,
            "inputs": {
                "curve": {"times": ts, "discount_factors": ds},
                "mean_reversion": a,
                "sigma": sigma,
                "start_years": t0 / 365.0,
                "payment_times": [x / 365.0 for x in pays],
                "fixed_rate": strike,
                "swaption_type": kind,
                "notional": 1000000.0,
                "exercise_times": [x / 365.0 for x in ex],
                "method": "CN_RANNACHER_SMOOTHED",
            },
        }
    raise SystemExit(f"no admissible case for {name}")


def document() -> dict[str, Any]:
    rng = random.Random(SEED)
    cases = []
    for cell in CELLS:
        for _ in range(N_RANDOM):
            cases.append(build(rng, cell, None))
        for corner in range(4):
            cases.append(build(rng, cell, corner))
    for k, c in enumerate(cases):
        c["case_id"] = f"k8p2-{k + 1:04d}"
    body = json.dumps(cases, sort_keys=True)
    return {
        "what": "K-8 phase 2 out-of-sample case set: inputs only, generated by oracle/python/k8_phase2_cases.py from "
        "the envelope of specifications/06-risk/bermudan-ladder-k8.md (Phase 2 acceptance). No reference value and "
        "no method value exists for these cases at the time of this commit. The grid is not part of a case: the "
        "acceptance names the grids.",
        "status": "generated 2026-11-19; NOT RUN",
        "seed": SEED,
        "cells": [c[0] for c in CELLS],
        "cases_per_cell": {"random": N_RANDOM, "edge": 4},
        "sha256_of_cases": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "cases": cases,
    }


def main() -> None:
    text = json.dumps(document(), indent=1) + "\n"
    if "--check" in sys.argv:
        if OUT.read_text("utf-8") != text:
            raise SystemExit("oracle/K8_PHASE2_CASES.json differs from a fresh build")
        print("K8_PHASE2_CASES.json: matches a fresh build")
        return
    OUT.write_text(text, "utf-8", newline="\n")
    print(f"wrote {OUT.name}: {len(json.loads(text)['cases'])} cases")


if __name__ == "__main__":
    main()
