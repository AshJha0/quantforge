#!/usr/bin/env python3
"""R2 daily job: P&L explain (plan 11.2.1) and calibration stability, over real historical daily moves.

  python tools/workflows/pnl_explain.py [--impl rust] [--days 20] [--trades 20] [--out reports/workflows] [--data DIR]

Data: the US Treasury daily par yield curve (public domain), last --days pairs of consecutive business days.
The curve is the same labelled proxy as workflow (a): Treasury par yields bootstrapped with SOFR OIS conventions.

P&L explain, for each pair (t, t+1) and each trade of the seeded sample book:
  full     = PV(curve from quotes of t+1, as of t) - PV(curve from quotes of t, as of t)    [rates.ois.pv]
  explain  = sum over key rates of key_rate_dv01(t) x (quote(t+1) - quote(t)) in bp           [risk.ois.dv01]
  unexplained = full - explain
Both curves use as-of t, so the trade does not age: this is the market-move P&L, and theta is out of scope.
risk.ois.dv01 returns the PV change for +1 bp (checked: a 5Y payer has positive DV01).

Calibration stability, per day: calib.curve_report condition number, and a robust Nelson-Siegel fit
(calib.curve.robust) on the bootstrapped zero rates; the report shows day-to-day parameter moves and outliers.

Thresholds are in tools/workflows/pnl_explain.json and are PROVISIONAL until the R2 spec fixes them.
All finance is CLI calls; this file only adds, subtracts and compares. Exit 1 if a fail-level check fails.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import eod_curves  # noqa: E402
from sample_book import book, digest  # noqa: E402

LIMITS = json.loads(Path(__file__).with_name("pnl_explain.json").read_text(encoding="utf-8"))


def history(a):
    """[(as_of, quotes)] for the last days+1 business days. Pulls last year too if this year is short."""
    import datetime as dt
    year = dt.date.today().year
    rows = eod_curves.treasury(eod_curves.load("us-treasury-par-yields.csv", c.source_url("us-treasury-par-yields", year), a.data))
    if len(rows) < a.days + 1 and not a.data:
        rows = eod_curves.treasury(c.fetch(c.source_url("us-treasury-par-yields", year - 1))) + rows
    rows = rows[-(a.days + 1):]
    # Keep only tenors present on every day, so key rates line up.
    common_tenors = set.intersection(*[{q["tenor"] for q in qs} for _, qs in rows])
    return [(d, [q for q in qs if q["tenor"] in common_tenors]) for d, qs in rows]


def boot(as_of, quotes):
    return {"convention": "SOFR", "as_of": as_of, "quotes": quotes, "interpolation": "LOG_LINEAR_DF", "method": "SEQUENTIAL"}


def run(hist, n_trades, impl):
    trades = book(n_trades)
    days = [(hist[i][0], hist[i][1], hist[i + 1][0], hist[i + 1][1]) for i in range(len(hist) - 1)]
    # Pass 1: curves (t on t, t+1 on t) and calibration diagnostics.
    cases = []
    for t, qt, t1, qt1 in days:
        cases += [c.case(f"b0-{t}", "rates.ois.bootstrap", boot(t, qt)), c.case(f"b1-{t}", "rates.ois.bootstrap", boot(t, qt1)),
                  c.case(f"cr-{t}", "calib.curve_report", {k: v for k, v in boot(t, qt).items() if k != "method"})]
    res = c.batch(cases, impl)
    # Pass 2: par rates on day 0 fix each trade's coupon; then PVs and key rates per day.
    t0, _, _, _ = days[0]
    curve0 = {"as_of": t0, "interpolation": "LOG_LINEAR_DF", "pillars": res[f"b0-{t0}"]["outputs"]["pillars"]}
    tenors = sorted({x["tenor"] for x in trades})
    par = c.batch([c.case(f"par-{tn}", "rates.ois.pv", {"curve": curve0, "trade": {"convention": "SOFR", "tenor": tn, "fixed_rate": 0.0,
                   "notional": 1.0, "side": "PAY"}}) for tn in tenors], impl)
    fixed = {x["id"]: round(par[f"par-{x['tenor']}"]["outputs"]["par_rate"] + x["offset"], 8) for x in trades}
    cases, zero_cases = [], []
    for t, qt, t1, qt1 in days:
        for k in ("b0", "b1"):
            curve = {"as_of": t, "interpolation": "LOG_LINEAR_DF", "pillars": res[f"{k}-{t}"]["outputs"]["pillars"]}
            for x in trades:
                tr = {"convention": "SOFR", "tenor": x["tenor"], "fixed_rate": fixed[x["id"]], "notional": x["notional"], "side": x["side"]}
                cases.append(c.case(f"{k}pv-{t}-{x['id']}", "rates.ois.pv", {"curve": curve, "trade": tr}))
        for x in trades:
            tr = {"convention": "SOFR", "tenor": x["tenor"], "fixed_rate": fixed[x["id"]], "notional": x["notional"], "side": x["side"]}
            cases.append(c.case(f"kr-{t}-{x['id']}", "risk.ois.dv01", {"as_of": t, "quotes": qt, "interpolation": "LOG_LINEAR_DF", "trade": tr}))
        pillars = res[f"b0-{t}"]["outputs"]["pillars"]
        mats = [c.years(p["date"], t) for p in pillars]
        zeros = [c.zero_rate(p["discount_factor"], m) for p, m in zip(pillars, mats)]
        zero_cases.append(c.case(f"ns-{t}", "calib.curve.robust", {"maturities": mats, "zero_rates": zeros, "tau": 2.0, "delta": 0.0005}))
    res.update(c.batch(cases + zero_cases, impl))
    return trades, days, res


CAL_TEXT = ("Condition number of the zero-to-quote Jacobian (`calib.curve_report`), and a robust Nelson-Siegel fit (tau 2, Huber delta 5 bp) to "
            "the bootstrapped zero rates (`calib.curve.robust`). Nelson-Siegel parameters are poorly identified, so a large step with small "
            "residuals means a flat objective, not a broken curve.")


def summarise(trades, days, res):
    """Numbers only, no thresholds: what the report and the gallery page both show."""
    rows, cal = [], []
    for t, qt, t1, qt1 in days:
        move = [(b["rate"] - a_["rate"]) * 1e4 for a_, b in zip(qt, qt1)]
        full_b = expl_b = dv01_b = 0.0
        trade_rows = []
        for x in trades:
            full = res[f"b1pv-{t}-{x['id']}"]["outputs"]["valuation"]["pv"] - res[f"b0pv-{t}-{x['id']}"]["outputs"]["valuation"]["pv"]
            kr = res[f"kr-{t}-{x['id']}"]["outputs"]
            expl = sum(k * m for k, m in zip(kr["key_rate"], move))
            full_b, expl_b, dv01_b = full_b + full, expl_b + expl, dv01_b + abs(kr["dv01"])
            trade_rows.append({"id": x["id"], "notional": x["notional"], "full": full, "explained": expl})
        rows.append({"from": t, "to": t1, "largest_move_bp": max(move, key=abs), "full": full_b, "explained": expl_b,
                     "unexplained": full_b - expl_b, "book_dv01": dv01_b, "trades": trade_rows})
    prev = None
    for t, *_ in days:
        ns = res[f"ns-{t}"]["outputs"]
        step = max(abs(b - p) for b, p in zip(ns["betas"], prev)) if prev else 0.0
        prev = ns["betas"]
        cal.append({"date": t, "condition": res[f"cr-{t}"]["outputs"]["condition_number"], "betas": ns["betas"], "beta_step": step,
                    "outliers": len(ns["outliers"]), "max_residual": max(abs(e) for e in ns["residuals"])})
    return {"explain": rows, "calibration": cal}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", default="python")
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--trades", type=int, default=20)
    ap.add_argument("--out", default=str(c.ROOT / "reports" / "workflows"))
    ap.add_argument("--data")
    a = ap.parse_args()
    hist = history(a)
    trades, days, res = run(hist, a.trades, a.impl)
    r = c.Report("PnL explain", hist[-1][0], a.out)
    notices = [c.SOURCES["us-treasury-par-yields"]["notice"]]
    bad = [k for k, v in res.items() if v["status"] != "ok"]
    r.check("all CLI cases ok", "fail", not bad, f"{len(res) - len(bad)}/{len(res)}; failed {bad[:5] or 'none'}")
    if bad:
        return r.write(notices)
    s = summarise(trades, days, res)
    lim, cal = LIMITS["explain"], LIMITS["calibration"]

    r.h("P&L explain")
    r.p(f"{eod_curves.CURVE_LABEL} {len(days)} daily moves from {days[0][0]} to {days[-1][2]}, {len(trades)} synthetic SOFR swaps "
        f"(book sha256 `{digest(trades)[:16]}`). Market-move P&L only: both curves of a pair are as of the first day. "
        f"Thresholds are provisional until the R2 spec sets them: book |unexplained| ≤ {lim['book_rel']:.0%} of |full P&L| "
        f"plus {lim['book_abs_per_dv01']} × book DV01; trade |unexplained| ≤ {lim['trade_rel']:.0%} of |full| plus {lim['trade_abs_per_mm']} USD per million.")
    breaches = 0
    for d in s["explain"]:
        allowed = lim["book_rel"] * abs(d["full"]) + lim["book_abs_per_dv01"] * d["book_dv01"]
        r.check(f"book explain {d['from']}", "fail", abs(d["unexplained"]) <= allowed, f"unexplained {d['unexplained']:,.0f} vs allowed {allowed:,.0f}")
        breaches += sum(abs(t["full"] - t["explained"]) > lim["trade_rel"] * abs(t["full"]) + lim["trade_abs_per_mm"] * t["notional"] / 1e6
                        for t in d["trades"])
    r.check("trade-level explain", "warn", breaches == 0, f"{breaches} trade-days over the trade threshold")
    r.table(["Move", "Largest quote move (bp)", "Full P&L (USD)", "Explained (USD)", "Unexplained (USD)", "Unexplained / full"],
            [(f"{d['from']} → {d['to']}", f"{d['largest_move_bp']:+.1f}", f"{d['full']:,.0f}", f"{d['explained']:,.0f}",
              f"{d['unexplained']:,.0f}", f"{abs(d['unexplained']) / max(abs(d['full']), 1):.2%}") for d in s["explain"]])

    r.h("Calibration stability")
    conds = [x["condition"] for x in s["calibration"]]
    worst = max(x["beta_step"] for x in s["calibration"])
    r.check("condition number in band", "fail", max(conds) <= cal["condition_max"], f"max {max(conds):.1f} vs {cal['condition_max']}")
    r.check("Nelson-Siegel day-to-day parameter move", "warn", worst <= cal["beta_step_warn"], f"largest {worst * 1e4:.1f} bp vs {cal['beta_step_warn'] * 1e4:.0f} bp")
    r.p(CAL_TEXT)
    r.table(["Date", "Condition number", "β0 / β1 / β2 (%)", "Largest β step (bp)", "Outliers", "Largest residual (bp)"],
            [(x["date"], f"{x['condition']:.1f}", " / ".join(f"{b * 100:.3f}" for b in x["betas"]), f"{x['beta_step'] * 1e4:.1f}",
              x["outliers"], f"{x['max_residual'] * 1e4:.1f}") for x in s["calibration"]])
    r.data.update({"book_sha256": digest(trades), **s})
    return r.write(notices)


if __name__ == "__main__":
    sys.exit(main())
