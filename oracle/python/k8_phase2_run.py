"""K-8 phase 2 runner (specifications/06-risk/bermudan-ladder-k8.md, "Phase 2 acceptance"; ruling KR-260).

Frozen with KR-260: this file, the case file oracle/K8_PHASE2_CASES.json and the rules below are fixed by
the commit that confirms KR-260, before any of the 120 cases is priced. Nothing here is changed after a
result is seen.

Steps (two interpreters, as oracle/python/k8_acceptance.py):

  reference [--workers N]  QuantLib wheel (run with QuantLib 1.44). FdHullWhiteSwaptionEngine at tGrid 8,000,
                           xGrid 3,201 (KR-19), central bump and revalue, relative bumps 1e-4 and 5e-5 on each
                           discount factor, on mean_reversion and on sigma. One raw file per case.
  method                   project Python. CN_RANNACHER_SMOOTHED at the judged grid 201/100, width 6.0. One raw
                           file per case.
  cross [--workers N]      project Python. Cross-check of point 5 (reported, not counted): the method at 801/400
                           and 1601/800 on CROSS_CASES only (see below).
  freeze                   writes program/k8_phase2/RAW_MANIFEST.json: SHA-256 of every raw file of the counted
                           steps (reference and method). Refuses to run twice.
  score                    checks the manifest, then applies KR-260 points 6 and 7 and writes
                           oracle/K8_PHASE2_RESULT.json.

Every step skips a case whose raw file exists, so a restarted run resumes. Each process lowers its own
priority to below normal (shared laptop).

Interpretations fixed here, before any run (each follows the text of KR-260):
  * cell = the case's `nominal_cell` (point 3: 10 cells of 8 random and 4 edge cases each). Four edge cases
    were moved to the strike floor and carry a different realised `cell`; that grouping is reported too,
    not counted.
  * reference value of an entry = the 1e-4 bump; unresolved = |r(5e-5) - r(1e-4)| > 1e-3 |r(1e-4)|, tested on
    judged entries (as acceptance 1 and oracle/K8_ACCEPTANCE_W2.json).
  * the 1e-3 floor is taken against max_j |r(1e-4)| over the discount-factor rows (point 6).
  * the price is compared and reported, not counted.
  * QuantLib swap: Actual/365 Fixed on whole days; fixed and floating schedules equal; Ibor index tenor equal
    to the case's period in days (182 or 365), fixing days 0, null calendar, unadjusted, forecast and
    discounting on the bumped curve, so a floating coupon is worth P(T_{i-1}) - P(T_i) as in the spec's
    exercise value.
  * cross-check (point 5): the method at 801/400 takes about 75 s and at 1601/800 about 10 min per 6-year case
    in Python (measured 2026-11-20 on aadladder_g-0001, not a phase 2 case), so 120 cases would take more than
    a day. It runs on CROSS_CASES, the first case of each nominal cell, after the counted steps.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CASE_FILE = ROOT / "oracle/K8_PHASE2_CASES.json"
RAW = ROOT / "program/k8_phase2/raw"
MANIFEST = ROOT / "program/k8_phase2/RAW_MANIFEST.json"
RESULT = ROOT / "oracle/K8_PHASE2_RESULT.json"
CASES_SHA256 = "0fd9b43bd631202cbc26a5c6e286e1f3ac2c473ba1cdb14709275d977e18f553"
GRID = (201, 100, 6.0)
QL_GRID = (8000, 3201)
BUMPS = (1e-4, 5e-5)
TOL, HARD, FLOOR, UNRESOLVED = 1e-2, 3e-2, 1e-3, 1e-3
PASS_MIN, CELL_MIN = 114, 10
CROSS_GRIDS = ((801, 400), (1601, 800))
CROSS_TOL = 2e-3


def low_priority() -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    else:
        import os

        os.nice(15)


def cases() -> list[dict[str, Any]]:
    data = CASE_FILE.read_bytes()
    if hashlib.sha256(data).hexdigest() != CASES_SHA256:
        raise SystemExit("K8_PHASE2_CASES.json differs from the file frozen by KR-260")
    out: list[dict[str, Any]] = json.loads(data)["cases"]
    return out


def cross_cases(cs: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, str] = {}
    for c in cs:
        seen.setdefault(c["nominal_cell"], c["case_id"])
    return list(seen.values())


def write(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1) + "\n", "utf-8", newline="\n")
    tmp.replace(path)


# --- reference (QuantLib) ---------------------------------------------------------------------------


def ql_price(c: dict[str, Any], dfs: list[float], a: float, sigma: float) -> float:
    import QuantLib as ql

    i = c["inputs"]
    ref = ql.Date(1, 1, 2025)
    dc = ql.Actual365Fixed()

    def day(t: float) -> Any:
        d = t * 365.0
        assert abs(d - round(d)) < 1e-9, t
        return ref + round(d)

    ql.Settings.instance().evaluationDate = ref
    curve = ql.DiscountCurve([ref] + [day(t) for t in i["curve"]["times"]], [1.0, *dfs], dc)
    handle = ql.YieldTermStructureHandle(curve)
    model = ql.HullWhite(handle, a, sigma)
    index = ql.IborIndex(
        "k8p2", ql.Period(int(c["period_days"]), ql.Days), 0, ql.EURCurrency(), ql.NullCalendar(), ql.Unadjusted,
        False, dc, handle,
    )  # fmt: skip
    sched = ql.Schedule([day(i["start_years"])] + [day(t) for t in i["payment_times"]])
    kind = ql.VanillaSwap.Payer if i["swaption_type"] == "PAYER" else ql.VanillaSwap.Receiver
    swap = ql.VanillaSwap(kind, i["notional"], sched, i["fixed_rate"], dc, sched, index, 0.0, dc)
    swaption = ql.Swaption(swap, ql.BermudanExercise([day(t) for t in i["exercise_times"]]))
    swaption.setPricingEngine(ql.FdHullWhiteSwaptionEngine(model, QL_GRID[0], QL_GRID[1], 0, 1e-10))
    return float(swaption.NPV())


def reference_one(c: dict[str, Any]) -> str:
    import time

    import QuantLib as ql

    low_priority()
    path = RAW / "ql" / f"{c['case_id']}.json"
    if path.exists():
        return f"{c['case_id']} exists"
    t0 = time.time()
    i = c["inputs"]
    dfs, a, s = list(i["curve"]["discount_factors"]), i["mean_reversion"], i["sigma"]

    def f(k: int, x: float) -> float:
        d, aa, ss = list(dfs), a, s
        if k < len(dfs):
            d[k] = x
        elif k == len(dfs):
            aa = x
        else:
            ss = x
        return ql_price(c, d, aa, ss)

    rows = []
    for k in range(len(dfs) + 2):
        x0 = dfs[k] if k < len(dfs) else (a if k == len(dfs) else s)
        rows.append([(f(k, x0 * (1 + h)) - f(k, x0 * (1 - h))) / (2 * h * x0) for h in BUMPS])
    doc = {
        "case_id": c["case_id"],
        "quantlib": ql.__version__,
        "engine": "FdHullWhiteSwaptionEngine(model, 8000, 3201, dampingSteps=0, invEps=1e-10)",
        "bumps": list(BUMPS),
        "rows": "d/dDF per node, then d/da, d/dsigma; each [bump 1e-4, bump 5e-5]",
        "price": ql_price(c, dfs, a, s),
        "d": rows,
        "seconds": round(time.time() - t0, 1),
    }
    write(path, doc)
    return f"{c['case_id']} ql {doc['seconds']} s"


# --- method (project Python) ------------------------------------------------------------------------


def method_one(c: dict[str, Any], nx: int, spy: int, sub: str) -> str:
    import time

    low_priority()
    path = RAW / sub / f"{c['case_id']}.json"
    if path.exists():
        return f"{c['case_id']} {sub} exists"
    sys.path.insert(0, str(ROOT / "python"))
    from quantforge_core import bermudan_k8 as k8

    t0 = time.time()
    i = c["inputs"]
    cu = i["curve"]
    r = k8.bermudan_ladder(
        cu["times"], cu["discount_factors"], i["mean_reversion"], i["sigma"], False, i["start_years"],
        i["payment_times"], i["fixed_rate"], i["swaption_type"], i["notional"], i["exercise_times"], nx, spy, GRID[2],
    )  # fmt: skip
    doc = {
        "case_id": c["case_id"],
        "build": "python quantforge_core.bermudan_k8, CN_RANNACHER_SMOOTHED",
        "grid": {"nx": nx, "steps_per_year": spy, "width": GRID[2]},
        "row": [
            r["price"],
            *r["d_price_d_discount_factors"],
            r["d_price_d_mean_reversion"],
            r["d_price_d_sigma"],
        ],
        "seconds": round(time.time() - t0, 1),
    }
    write(path, doc)
    return f"{c['case_id']} {sub} {doc['seconds']} s"


def _method_job(args: tuple[dict[str, Any], int, int, str]) -> str:
    return method_one(*args)


def run_pool(fn: Any, jobs: list[Any], workers: int) -> None:
    import datetime
    import multiprocessing as mp

    prog = ROOT / "program/k8_phase2/progress.txt"
    prog.parent.mkdir(parents=True, exist_ok=True)
    with mp.Pool(workers) as pool, prog.open("a", encoding="utf-8") as fh:
        for n, msg in enumerate(pool.imap_unordered(fn, jobs), 1):
            fh.write(f"{datetime.datetime.now(datetime.UTC):%H:%M:%S} {n}/{len(jobs)} {msg}\n")
            fh.flush()


# --- freeze and score -------------------------------------------------------------------------------


def counted_files(cs: list[dict[str, Any]]) -> list[Path]:
    return [RAW / sub / f"{c['case_id']}.json" for sub in ("ql", "method_201_100") for c in cs]


def freeze(cs: list[dict[str, Any]]) -> None:
    if MANIFEST.exists():
        raise SystemExit("RAW_MANIFEST.json exists: the raw results are already frozen")
    files = counted_files(cs)
    missing = [p.name for p in files if not p.exists()]
    if missing:
        raise SystemExit(f"{len(missing)} raw files missing, first {missing[:3]}")
    per = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    }
    combined = hashlib.sha256("".join(f"{k} {v}\n" for k, v in per.items()).encode()).hexdigest()
    write(MANIFEST, {"what": "SHA-256 of the counted raw results of K-8 phase 2, frozen before scoring",
                     "cases_sha256": CASES_SHA256, "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     "combined_sha256": combined, "files": per})  # fmt: skip
    print("frozen", combined)


def rel(x: float, y: float) -> float:
    return abs(x - y) / abs(y) if y != 0 else math.inf


def score(cs: list[dict[str, Any]]) -> None:
    man = json.loads(MANIFEST.read_text("utf-8"))
    for name, h in man["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != h:
            raise SystemExit(f"{name} changed after the freeze")
    per_case = []
    worst_all = 0.0
    for c in cs:
        q = json.loads((RAW / "ql" / f"{c['case_id']}.json").read_text("utf-8"))
        m = json.loads((RAW / "method_201_100" / f"{c['case_id']}.json").read_text("utf-8"))["row"]
        d = q["d"]
        n = len(d) - 2
        top = max(abs(d[k][0]) for k in range(n))
        entries = []
        for k in range(n + 2):
            judged = k >= n or abs(d[k][0]) >= FLOOR * top
            if not judged:
                continue
            ref, ref2, got = d[k][0], d[k][1], m[k + 1]
            err = rel(got, ref)
            label = f"df{k}" if k < n else ("d_a" if k == n else "d_sigma")
            entries.append({"entry": label, "reference": ref, "reference_5e-5": ref2, "method": got,
                            "error": err, "signed_error": (got - ref) / ref,
                            "unresolved": rel(ref2, ref) > UNRESOLVED})  # fmt: skip
        worst = max(entries, key=lambda e: e["error"])
        worst_all = max(worst_all, worst["error"])
        unres = [e["entry"] for e in entries if e["unresolved"]]
        ok = worst["error"] <= TOL and not unres
        per_case.append({
            "case_id": c["case_id"], "cell": c["nominal_cell"], "realised_cell": c["cell"], "kind": c["kind"],
            "pass": ok, "worst_entry": worst["entry"], "worst_error": worst["error"],
            "worst_signed_error": worst["signed_error"], "unresolved": unres,
            "n_judged": len(entries), "n_over_1pct": sum(e["error"] > TOL for e in entries),
            "price_method": m[0], "price_reference": q["price"], "price_error": rel(m[0], q["price"]),
            "entries": entries,
        })  # fmt: skip
    cells: dict[str, dict[str, Any]] = {}
    for p in per_case:
        cl = cells.setdefault(
            p["cell"], {"cases": 0, "pass": 0, "max_error": 0.0, "unresolved_cases": 0}
        )
        cl["cases"] += 1
        cl["pass"] += p["pass"]
        cl["max_error"] = max(cl["max_error"], p["worst_error"])
        cl["unresolved_cases"] += bool(p["unresolved"])
    realised: dict[str, list[int]] = {}
    for p in per_case:
        r = realised.setdefault(p["realised_cell"], [0, 0])
        r[0] += 1
        r[1] += p["pass"]
    n_pass = sum(p["pass"] for p in per_case)
    a_ok, b_ok = n_pass >= PASS_MIN, worst_all <= HARD
    c_ok = all(v["pass"] >= CELL_MIN for v in cells.values()) and len(cells) == 10
    doc = {
        "what": "K-8 phase 2 result, scored against KR-260 as confirmed (bermudan-ladder-k8.md, Phase 2 acceptance)",
        "manifest_combined_sha256": man["combined_sha256"],
        "rule": {"tolerance": TOL, "hard_bound": HARD, "floor": FLOOR, "unresolved": UNRESOLVED,
                 "pass_min": PASS_MIN, "cell_min": CELL_MIN},
        "verdict": "PASS" if (a_ok and b_ok and c_ok) else "MISS",
        "a_cases_passing": n_pass, "a_ok": a_ok, "b_max_error": worst_all, "b_ok": b_ok, "c_ok": c_ok,
        "cells": cells, "realised_cells_reported_not_counted": realised, "cases": per_case,
    }  # fmt: skip
    write(RESULT, doc)
    print(f"verdict {doc['verdict']}: {n_pass}/120 cases pass (need {PASS_MIN}); max error {worst_all:.4%} "
          f"(hard {HARD:.0%}); cells:")  # fmt: skip
    for k, v in cells.items():
        print(
            f"  {k:18s} {v['pass']:2d}/{v['cases']}  max {v['max_error']:.3%}  unresolved cases {v['unresolved_cases']}"
        )


def cross_report(cs: list[dict[str, Any]]) -> None:
    ids = cross_cases(cs)
    out = {}
    for cid in ids:
        f = [RAW / f"method_{nx}_{spy}" / f"{cid}.json" for nx, spy in CROSS_GRIDS]
        if not all(p.exists() for p in f):
            out[cid] = "not run"
            continue
        a, b = (json.loads(p.read_text("utf-8"))["row"] for p in f)
        gaps = [rel(x, y) for x, y in zip(a[1:], b[1:], strict=True) if y != 0.0]
        out[cid] = {"max_gap_801_vs_1601": max(gaps), "within_0.2pct": max(gaps) <= CROSS_TOL,
                    "sha256": [hashlib.sha256(p.read_bytes()).hexdigest() for p in f]}  # fmt: skip
    write(ROOT / "program/k8_phase2/CROSS_CHECK.json", {"what": "point 5 cross-check, reported not counted",
                                                         "cases": out})  # fmt: skip
    print(json.dumps(out, indent=1))


def main() -> None:
    cs = cases()
    step = sys.argv[1]
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 1
    if step in ("reference", "method", "cross"):
        low_priority()
    if step == "reference":
        run_pool(reference_one, cs, workers)
    elif step == "method":
        run_pool(_method_job, [(c, GRID[0], GRID[1], "method_201_100") for c in cs], workers)
    elif step == "cross":
        ids = set(cross_cases(cs))
        jobs = [
            (c, nx, spy, f"method_{nx}_{spy}")
            for nx, spy in CROSS_GRIDS
            for c in cs
            if c["case_id"] in ids
        ]
        run_pool(_method_job, jobs, workers)
    elif step == "freeze":
        freeze(cs)
    elif step == "score":
        score(cs)
    elif step == "cross-report":
        cross_report(cs)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
