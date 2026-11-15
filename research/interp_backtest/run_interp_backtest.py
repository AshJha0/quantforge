#!/usr/bin/env python3
"""Interpolation backtests B1 (held-out strikes, SSVI) and B2 (leave-one-out, Treasury par curve).

Pass rules: specifications/11-research/interp-backtest.md, section "Pass rules" (committed in c41f629 before any run).
Run once:  python research/interp_backtest/run_interp_backtest.py   -> research/interp_backtest/RESULTS.md, results.json
Refuses if results.json exists.
"""
import csv
import hashlib
import io
import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from quantforge_core import research_w3

HERE = Path(__file__).resolve().parent
RAW = ROOT / "datasets" / "scenarios" / "raw"
YEARS = (2008, 2013, 2020, 2021, 2022)
LABELS = ("1 Mo", "3 Mo", "6 Mo", "1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr")
TENORS = [1 / 12, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]
RULE_COMMIT = "c41f629"


def ssvi_vol(k: float, t: float) -> float:
    th = 0.04 * t
    phi = 1.0 * th ** -0.5 * (1 + th) ** (0.5 - 1)
    w = th / 2 * (1 - 0.4 * phi * k + math.sqrt((phi * k - 0.4) ** 2 + 1 - 0.16))
    return math.sqrt(w / t)


def b1() -> dict:
    ks = [round(-0.4 + 0.1 * j, 10) for j in range(9)]
    ts = [0.25, 0.5, 1.0, 2.0]
    vols = [[ssvi_vol(k, t) for k in ks] for t in ts]
    out = {}
    for m in ("cubic_natural", "linear", "monotone_pchip"):
        loo = [abs(research_w3.backtest_surface_holdout(m, ts, ks, vols, [h])["errors"][r][0])
               for h in range(1, 8) for r in range(4)]
        alt = research_w3.backtest_surface_holdout(m, ts, ks, vols, [1, 3, 5, 7])
        out[m] = {"a_max_vol_pts": 100 * max(loo), "a_count": len(loo), "b_max_vol_pts": 100 * alt["max_abs_error"],
                  "b_count": 16}
    p = out["cubic_natural"]
    out["pass"] = p["a_max_vol_pts"] <= 0.25 and p["b_max_vol_pts"] <= 0.50
    return out


def b2() -> dict:
    prov = {r["name"]: r["sha256"] for r in csv.DictReader((RAW / "provenance.csv").open(encoding="utf-8"))}
    rows: dict[date, list[float]] = {}
    skipped = 0
    for y in YEARS:
        b = (RAW / f"ust_{y}.csv").read_bytes()
        if hashlib.sha256(b).hexdigest() != prov[f"ust_{y}.csv"]:
            raise SystemExit(f"ust_{y}.csv hash differs from provenance")
        for r in csv.DictReader(io.StringIO(b.decode("utf-8-sig"))):
            m, d, yy = (int(x) for x in r.pop("Date").split("/"))
            vals = {k.strip(): v for k, v in r.items()}
            if any(vals.get(lab, "") in ("", None) for lab in LABELS):
                skipped += 1
                continue
            rows[date(yy, m, d)] = [float(vals[lab]) for lab in LABELS]
    out: dict = {"rows": len(rows), "rows_skipped": skipped}
    for meth in ("monotone_pchip", "linear", "cubic_natural"):
        judged: list[float] = []
        t20: list[float] = []
        by_tenor: dict[str, list[float]] = {lab: [] for lab in LABELS[1:-1]}
        for y in rows.values():
            e = research_w3.backtest_interp_loo(meth, TENORS, y)["errors"]
            for lab, v in zip(LABELS[1:-1], e, strict=True):
                by_tenor[lab].append(abs(100 * v))
            judged += [abs(100 * v) for v in e[:-1]]  # 3M .. 10Y
            t20.append(abs(100 * e[-1]))

        def q(xs: list[float], p: float) -> float:
            s = sorted(xs)
            return s[math.ceil(p * len(s)) - 1]
        out[meth] = {"judged_n": len(judged), "median_bp": statistics.median(judged), "p95_bp": q(judged, 0.95),
                     "t20_median_bp": statistics.median(t20), "t20_p95_bp": q(t20, 0.95),
                     "by_tenor_median_bp": {k: statistics.median(v) for k, v in by_tenor.items()},
                     "by_tenor_p95_bp": {k: q(v, 0.95) for k, v in by_tenor.items()}}
    p = out["monotone_pchip"]
    out["pass"] = p["median_bp"] <= 3.0 and p["p95_bp"] <= 15.0
    return out


def main() -> int:
    res = HERE / "results.json"
    if res.exists():
        raise SystemExit("results.json exists: the backtest is run once")
    r = {"rule_commit": RULE_COMMIT, "B1": b1(), "B2": b2()}
    res.write_text(json.dumps(r, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: (v["pass"] if isinstance(v, dict) else v) for k, v in r.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
