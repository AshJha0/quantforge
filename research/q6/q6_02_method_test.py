#!/usr/bin/env python3
"""Q6-02: robust, shape-only penalised calibration on SYNTHETIC noisy quotes (plan J-11). A method test, not real quotes.

Runs the procedure fixed in research/preregs/Q6-02-robust-shape-penalty.md. The quote generator, grid, churn ratio,
arbitrage check, split and selection come unchanged from research/q6/q6_method_test.py (Q6-01). What changes:

- fit term rho(e) = e^2 for |e| <= 1, 2|e| - 1 otherwise, e = (model - mid) / h (twice the Huber function, so equal
  to Q6-01's squared loss inside the spread);
- penalty lambda * mean_g (u_g / sigma_g)^2, u_g the change of the grid vol net of the same-expiry at-the-forward
  move, sigma_g = sqrt(2) times the quote-noise standard error of yesterday's grid vol (Gauss-Newton, noise sd h/2);
- grid lambda in {0, 1, 3}; seed 20261113.

The real run (seed 20261113, 60 days) is refused unless the prereg is signed, its body matches its recorded hash, this
file and the generator match the hashes in its header, and research/q6/q6_02_output.json does not exist yet.

  python research/q6/q6_02_method_test.py            # the one real run (guarded)
  python research/q6/q6_02_method_test.py --dry-run  # checks the guard only, draws nothing
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, TypeAlias

import numpy as np
import numpy.typing as npt
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
g: Any = importlib.import_module("q6_method_test")  # Q6-01 generator and checks, frozen and untyped

Arr: TypeAlias = npt.NDArray[np.float64]
LAMBDAS = (0, 1, 3)
SEED = 20261113
DAYS = 60
PREREG = HERE.parent / "preregs" / "Q6-02-robust-shape-penalty.md"
OUTPUT = HERE / "q6_02_output.json"
MARK = b"<!-- body -->\n"
STEP = 1e-6
SIGMA_FLOOR = 1e-6
LABEL = "Synthetic quotes from a known SSVI surface; a method test, not a calibration to real option quotes (Q6-02)."


def rho(e: Arr) -> Arr:
    """Twice the Huber function with threshold 1: e^2 inside the spread, 2|e| - 1 outside."""
    a = np.abs(e)
    return np.where(a <= 1.0, e * e, 2.0 * a - 1.0)


def quote_vols(x: Arr, q: dict[str, Arr]) -> Arr:
    p = g.unpack(x)
    return np.asarray(g.vols(p[0], p[1], p[2], q["k"], q["T"]), dtype=np.float64)


def grid_vols(x: Arr) -> Arr:
    return np.asarray(g.grid_vols(g.unpack(x)), dtype=np.float64)


def atm_on_grid(x: Arr) -> Arr:
    """At-the-forward vol a(T_g) for each of the 45 grid nodes (k = 0 at the node's expiry), same order as grid_vols."""
    atm = np.asarray(g.atm_vol(g.unpack(x)), dtype=np.float64)
    return np.repeat(atm, g.K_GRID.size)


def jac(f: Any, x: Arr) -> Arr:
    cols = []
    for i in range(x.size):
        d = np.zeros_like(x)
        d[i] = STEP
        cols.append((f(x + d) - f(x - d)) / (2 * STEP))
    return np.stack(cols, axis=1)


def sigma_grid(x_prev: Arr, q_prev: dict[str, Arr]) -> Arr:
    """sqrt(2) x quote-noise standard error of each grid vol of the previous day's fit (prereg, sigma_g)."""
    jq = jac(lambda z: quote_vols(z, q_prev), x_prev)
    jg = jac(grid_vols, x_prev)
    w = 4.0 / q_prev["h"] ** 2
    cov = np.linalg.pinv(jq.T @ (w[:, None] * jq), rcond=1e-10)
    var = np.einsum("ij,jk,ik->i", jg, cov, jg)
    out: Arr = np.maximum(np.sqrt(2.0 * np.maximum(var, 0.0)), SIGMA_FLOOR)
    return out


def day_loss(x: Arr, q: dict[str, Arr], lam: float, prev: tuple[Arr, Arr, Arr] | None) -> float:
    val = float(np.sum(rho((quote_vols(x, q) - q["mid"]) / q["h"])))
    if lam and prev is not None:
        s_prev, a_prev, sig = prev
        u = (grid_vols(x) - s_prev) - (atm_on_grid(x) - a_prev)
        val += lam * float(np.mean((u / sig) ** 2))
    return val


def run_days(qs: list[dict[str, Arr]], lam: float) -> tuple[list[Arr], Arr, float]:
    """One sample, fitted in order from x_start with no penalty on its first day. Returns fits, R_t, inside share."""
    xs: list[Arr] = []
    ratios: list[float] = []
    inside: list[bool] = []
    x = np.asarray(g.x_start(qs[0]), dtype=np.float64)
    for i, q in enumerate(qs):
        prev = None
        if i:
            xp = xs[-1]
            prev = (grid_vols(xp), atm_on_grid(xp), sigma_grid(xp, qs[i - 1]))
        x = np.asarray(minimize(day_loss, x, args=(q, lam, prev), method="L-BFGS-B").x, dtype=np.float64)
        inside.extend(bool(b) for b in np.abs(quote_vols(x, q) - q["mid"]) <= q["h"])
        if i:
            pp, pc = g.unpack(xs[-1]), g.unpack(x)
            c = math.sqrt(float(np.mean((g.grid_vols(pc) - g.grid_vols(pp)) ** 2)))
            a = math.sqrt(float(np.mean((g.atm_vol(pc) - g.atm_vol(pp)) ** 2)))
            ratios.append(c / max(a, 0.001))
        xs.append(x)
    return xs, np.array(ratios), float(np.mean(inside))


def draw(days: int, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Arr]]]:
    """Q6-01's generator in Q6-01's draw order: the truth path first, then each day's quotes."""
    rng = np.random.default_rng(seed)
    truth = g.truth_path(days, rng)
    qs: list[dict[str, Arr]] = []
    prev = None
    for t in truth:
        q = g.quotes(t, rng, prev)
        qs.append(q)
        prev = q["mid"]
    return truth, qs


def main(days: int = DAYS, seed: int = SEED) -> dict[str, Any]:
    truth, qs = draw(days, seed)
    n_sel = max(2, round(0.2 * days))
    sel, test = qs[:n_sel], qs[n_sel:]
    trials = []
    chosen = None
    for lam in LAMBDAS:  # every grid value is evaluated and logged
        _, r, share = run_days(sel, lam)
        trials.append({"lambda": lam, "median_R": float(np.median(r)), "p95_R": float(np.percentile(r, 95)), "inside_share": share})
        if chosen is None and share >= 0.80 and g.churn_ok(r):
            chosen = lam
    out: dict[str, Any] = {"label": LABEL, "prereg": "Q6-02", "seed": seed, "days": days, "selection_days": n_sel,
                           "trials": trials, "chosen_lambda": chosen}
    if chosen is None:
        out["result"] = "FAIL: no lambda in the grid met the churn bound and fit quality on the selection sample"
        return out
    xs, r, share = run_days(test, chosen)
    fits = [g.unpack(x) for x in xs]
    arb = [g.arbitrage_ok(p) for p in fits]
    err = float(np.sqrt(np.mean([(g.grid_vols(p) - g.grid_vols(g.unpack_truth(t))) ** 2 for p, t in zip(fits, truth[n_sel:])])))
    out.update({
        "test_median_R": float(np.median(r)), "test_p95_R": float(np.percentile(r, 95)), "churn_bound_met": g.churn_ok(r),
        "test_inside_share": share, "fit_quality_met": share >= 0.80,
        "calendar_free_days": sum(a[0] for a in arb), "butterfly_free_days": sum(a[1] for a in arb), "test_days": len(fits),
        "rms_error_to_truth_on_grid_vol": err,
    })
    ok = out["churn_bound_met"] and out["fit_quality_met"] and all(a[0] and a[1] for a in arb)
    out["result"] = "PASS" if ok else "FAIL"
    return out


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def guard(prereg: Path = PREREG, output: Path = OUTPUT) -> str:
    """Refuses the real run unless the signed prereg and the frozen files match. Returns the freeze commit."""
    if output.exists():
        raise SystemExit(f"refused: {output.name} exists; Q6-02 is run once")
    if not prereg.exists():
        raise SystemExit("refused: prereg Q6-02 not found")
    b = prereg.read_bytes()
    if MARK not in b:
        raise SystemExit("refused: prereg has no body marker")
    head = b[:b.index(MARK)].decode()
    if "Status: **signed**" not in head:
        raise SystemExit("refused: prereg Q6-02 is not signed")
    if hashlib.sha256(b[b.index(MARK) + len(MARK):]).hexdigest() not in head:
        raise SystemExit("refused: prereg Q6-02 body differs from its recorded hash")
    for f in (HERE / "q6_02_method_test.py", HERE / "q6_method_test.py"):
        m = re.search(rf"`{re.escape(f.name)}` \(whole file\): `([0-9a-f]{{64}})`", head)
        if not m or m.group(1) != sha(f):
            raise SystemExit(f"refused: {f.name} differs from the hash in prereg Q6-02")
    if len(re.findall(r"^Q6-02,Q6-02-T0[123],", (HERE.parent / "trials.csv").read_text(encoding="utf-8"), re.MULTILINE)) != 3:
        raise SystemExit("refused: trials Q6-02-T01..T03 not logged in research/trials.csv before the run")
    m = re.search(r"freeze commit: `([0-9a-f]{7,40})`", head)
    if not m:
        raise SystemExit("refused: prereg Q6-02 names no freeze commit")
    return m.group(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="check the guard, draw nothing")
    a = ap.parse_args()
    commit = guard()
    if a.dry_run:
        print(f"guard ok (freeze commit {commit}); nothing drawn")
        raise SystemExit(0)
    res = main()
    res["freeze_commit"] = commit
    OUTPUT.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))
