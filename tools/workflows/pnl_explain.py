#!/usr/bin/env python3
"""P&L explain over real daily moves (plan 11.2.1, spec specifications/06-risk/pnl-explain.md). Standard library only.

  python tools/workflows/pnl_explain.py [--impl python] [--years 2024 2025] [--out reports/workflows] [--data DIR]

For each pair of consecutive published days of the US Treasury par yield curve (the workflow (a) proxy curve, SOFR OIS
conventions), it sends one `risk.pnl.explain` case per product of a fixed sample book through the CLI's batch mode, and
writes a dated report of the explained share and unexplained-P&L percentiles. The tool holds no financial logic: it pairs
days, keeps the tenors present on both, and counts what the CLI returns. --data reads saved yearly files named
us-treasury-par-yields-YEAR.csv instead of fetching. Raw data is never written to the report.

Exit status: 0 every product explained on at least 95% of days; 1 otherwise or on a CLI failure.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
from eod_curves import CURVE_LABEL, treasury  # noqa: E402

LABEL = "Real moves of a proxy curve; synthetic product terms. " + CURVE_LABEL
ACCEPT = 0.95
BOND = {"maturity": "2035-08-15", "coupon": 0.0425, "frequency": 2}


def book(as_of, quotes):
    """Fixed sample book. Swap fixed rates are the start day's quote at that tenor, so each swap starts near par."""
    q = {x["tenor"]: x["rate"] for x in quotes}
    out = []
    for tenor, side, n in (("2Y", "RECEIVE", 2.5e7), ("10Y", "RECEIVE", 1e7), ("30Y", "PAY", 5e6)):
        if tenor in q:
            out.append((f"OIS {tenor} {side}", {"kind": "OIS", "trade": {"convention": "SOFR", "tenor": tenor, "fixed_rate": q[tenor], "notional": n, "side": side}}))
    out.append(("Bond 4.25% 2035", {"kind": "BOND", "bond": BOND, "settlement": as_of, "notional": 1e7}))
    return out


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * (len(xs) - 1) + 0.5))] if xs else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", default="python")
    ap.add_argument("--years", type=int, nargs="+", default=[dt.date.today().year - 1])
    ap.add_argument("--out", default=str(c.ROOT / "reports" / "workflows"))
    ap.add_argument("--data")
    a = ap.parse_args()
    days = []
    for y in a.years:
        raw = (Path(a.data) / f"us-treasury-par-yields-{y}.csv").read_bytes() if a.data else c.fetch(c.source_url("us-treasury-par-yields", y))
        days += treasury(raw)
    days.sort()
    cases, meta = [], {}
    for (d0, q0), (d1, q1) in zip(days, days[1:]):
        t1 = {x["tenor"] for x in q1}
        s0 = [x for x in q0 if x["tenor"] in t1]
        e = {x["tenor"]: x for x in q1}
        s1 = [e[x["tenor"]] for x in s0]
        big = max(abs(x["rate"] - y["rate"]) for x, y in zip(s0, s1)) / 1e-4
        for name, prod in book(d0, s0):
            cid = f"{d0}|{name}"
            cases.append(c.case(cid, "risk.pnl.explain", {"as_of": d0, "convention": "SOFR", "interpolation": "LOG_LINEAR_DF", "quotes_start": s0,
                                                           "quotes_end": s1, "product": prod, "bump_bp": 1.0}))
            meta[cid] = (name, d0, d1, big)
    res = c.batch(cases, a.impl)
    r = c.Report("P&L explain", days[-1][0], a.out)
    r.data.update({"label": LABEL, "impl": a.impl, "years": a.years, "pairs": len(days) - 1, "threshold": "max(5% |full|, 5% |par_dv01|)"})
    r.p(f"{LABEL} Years {a.years}, {len(days) - 1} day pairs, implementation {a.impl}. Threshold: spec `06-risk/pnl-explain.md`.")
    rows, by = [], {}
    for cid, out in res.items():
        name, d0, d1, big = meta[cid]
        by.setdefault(name, []).append((cid, out, d0, d1, big))
    summary = {}
    for name, xs in by.items():
        ok = [x for x in xs if x[1]["status"] == "ok"]
        errs = len(xs) - len(ok)
        ex = sum(1 for x in ok if x[1]["outputs"]["explained"])
        rel = [abs(x[1]["outputs"]["unexplained"]) / max(abs(x[1]["outputs"]["full_pnl"]), abs(sum(x[1]["outputs"]["par_buckets"])), 1e-12) for x in ok]
        share = ex / len(xs) if xs else 0.0
        summary[name] = {"days": len(xs), "explained": ex, "errors": errs, "share": share, "p50": pct(rel, .5), "p95": pct(rel, .95), "p99": pct(rel, .99)}
        rows.append((name, len(xs), ex, errs, f"{share * 100:.1f}%", f"{pct(rel, .5):.2e}", f"{pct(rel, .95):.2e}", f"{pct(rel, .99):.2e}"))
        r.check(f"{name} explained share >= {ACCEPT:.0%}", "fail", share >= ACCEPT and errs == 0, f"{share * 100:.1f}% of {len(xs)} days, {errs} errors")
        worst = sorted(ok, key=lambda x: -abs(x[1]["outputs"]["unexplained"]))[:5]
        summary[name]["worst"] = [{"start": x[2], "end": x[3], "unexplained": x[1]["outputs"]["unexplained"], "full_pnl": x[1]["outputs"]["full_pnl"],
                                   "largest_move_bp": round(x[4], 2)} for x in worst]
    r.h("Explained share by product")
    r.table(["Product", "Days", "Explained", "Errors", "Share", "p50 rel", "p95 rel", "p99 rel"], rows)
    r.h("Worst days")
    r.table(["Product", "Start", "End", "Unexplained", "Full P&L", "Largest move (bp)"],
            [(n, w["start"], w["end"], f"{w['unexplained']:.2f}", f"{w['full_pnl']:.2f}", w["largest_move_bp"]) for n, s in summary.items() for w in s["worst"]])
    r.data["summary"] = summary
    return r.write([c.SOURCES["us-treasury-par-yields"]["notice"]])


if __name__ == "__main__":
    sys.exit(main())
