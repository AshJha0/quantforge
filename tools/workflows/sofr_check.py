#!/usr/bin/env python3
"""Workflow (c), plan 11.2.7: SOFR compounding and fallback check against NY Fed published averages.

  python tools/workflows/sofr_check.py [--impl python] [--out reports/workflows] [--days 5] [--data DIR]

For each of the last --days publication dates T, the library recomputes the NY Fed 30-, 90- and 180-day SOFR
averages from the published daily SOFR. It compares them with the NY Fed's published figures (5 decimals in
percent), and checks the SOFR Index ratio. Method, per the NY Fed's methodology: compounded in arrears over
the calendar days [T - n, T), each rate weighted by its calendar days, actual/360.
- If T - n is a business day: `rates.ois.compound_dated` (SOFR, no shift).
- Otherwise the first rate applies from T - n to the next business day: `rates.ois.compound`, with day weights
  counted here. That count is calendar arithmetic, not pricing.

Fallback: `rates.fallback.rate` for USD-LIBOR-3M, on the latest period ending at a fixing date. It checks:
- the spread adjustment equals the ISDA fixed spread of 0.26161% (fixed 2021-03-05);
- fallback = compounded + spread.

Exit status: 0 all fail-level checks passed, 1 otherwise.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c  # noqa: E402
import sanity  # noqa: E402

AVG_URL = "https://markets.newyorkfed.org/api/rates/secured/sofrai/search.json?startDate={start}&endDate={end}"
ISDA_3M_SPREAD = 0.0026161
WINDOWS = (30, 90, 180)


def load(name, url, data_dir):
    if data_dir:
        return (Path(data_dir) / name).read_bytes()
    return c.fetch(url)


def window_case(case_id, T, n, fixings):
    """fixings: [(iso, rate)] oldest first, business days only."""
    end = dt.date.fromisoformat(T)
    start = end - dt.timedelta(days=n)
    dates = [dt.date.fromisoformat(d) for d, _ in fixings]
    if start in dates:
        return c.case(case_id, "rates.ois.compound_dated", {"convention": "SOFR", "start": start.isoformat(), "end": T,
                      "method": "NONE", "shift_days": 0, "fixings": [{"date": d, "rate": x} for d, x in fixings]})
    # Weights: each fixing on or before the start covers from max(its date, start) to the next fixing, clipped to [start, end).
    rates, days = [], []
    for i, (d, x) in enumerate(fixings):
        d0 = dates[i]
        d1 = dates[i + 1] if i + 1 < len(dates) else end
        lo, hi = max(d0, start), min(d1, end)
        if hi > lo:
            rates.append(x)
            days.append((hi - lo).days)
    return c.case(case_id, "rates.ois.compound", {"rates": rates, "days": days, "denominator": 360})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", default="python")
    ap.add_argument("--out", default=str(c.ROOT / "reports" / "workflows"))
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--data")
    a = ap.parse_args()
    today = dt.date.today()
    start = (today - dt.timedelta(days=400)).isoformat()
    sofr_url = c.SOURCES["nyfed-sofr"]["url"].split("?")[0] + f"?startDate={start}&endDate={today.isoformat()}"
    fixings = sorted((x["effectiveDate"], x["percentRate"] / 100) for x in json.loads(load("nyfed-sofr-400d.json", sofr_url, a.data))["refRates"])
    avgs = sorted(json.loads(load("nyfed-sofrai.json", AVG_URL.format(start=start, end=today.isoformat()), a.data))["refRates"],
                  key=lambda x: x["effectiveDate"])
    T_last = avgs[-1]["effectiveDate"]
    r = c.Report("SOFR check", T_last, a.out)
    sanity.check_fixings(r, "SOFR", fixings)
    tol = sanity.BANDS["sofr_average"]["abs_diff_fail"]

    pubs = avgs[-a.days:]
    cases, meta = [], []
    for p in pubs:
        T = p["effectiveDate"]
        before = [f for f in fixings if f[0] < T]
        for n in WINDOWS:
            cid = f"avg{n}-{T}"
            cases.append(window_case(cid, T, n, before))
            meta.append((cid, T, n, p[f"average{n}day"] / 100))
    # Index: Index(T) / Index(prev publication) - 1 must equal one compounding step over the days between.
    for prev, cur in zip(pubs, pubs[1:]):
        days = [f for f in fixings if prev["effectiveDate"] <= f[0] < cur["effectiveDate"]]
        if days:
            cases.append(window_case(f"idx-{cur['effectiveDate']}", cur["effectiveDate"],
                                     (dt.date.fromisoformat(cur["effectiveDate"]) - dt.date.fromisoformat(prev["effectiveDate"])).days,
                                     [f for f in fixings if f[0] < cur["effectiveDate"]]))
    # Fallback: 3M period ending at the latest fixing date.
    end = fixings[-1][0]
    fb_start = next(d for d, _ in fixings if d >= (dt.date.fromisoformat(end) - dt.timedelta(days=91)).isoformat())
    cases.append(c.case("fallback", "rates.fallback.rate", {"ibor": "USD-LIBOR-3M", "start": fb_start, "end": end,
                        "fixings": [{"date": d, "rate": x} for d, x in fixings]}))
    res = c.batch(cases, a.impl)

    r.h("Published averages against the library")
    r.p(f"NY Fed 30/90/180-day SOFR averages for the last {len(pubs)} publications. Pass if |library - published| "
        f"≤ {tol} (published to 5 decimals in percent, so half a unit is 5e-8). Implementation: {a.impl}.")
    rows, worst = [], 0.0
    for cid, T, n, pub in meta:
        o = res[cid]
        if o["status"] != "ok":
            r.check(f"{n}-day average {T}", "fail", False, o["error"]["message"])
            continue
        mine = o["outputs"]["compounded_rate"]
        diff = mine - pub
        worst = max(worst, abs(diff))
        r.check(f"{n}-day average {T}", "fail", abs(diff) <= tol, f"diff {diff:.2e}")
        rows.append((T, n, f"{pub * 100:.5f}", f"{mine * 100:.7f}", f"{diff:.2e}", cases[[x['case_id'] for x in cases].index(cid)]["operation"]))
    r.table(["Date", "Window (d)", "Published (%)", "Library (%)", "Diff (decimal)", "Operation"], rows)
    r.data["averages"] = [dict(zip(["date", "window", "published_pct", "library_pct", "diff", "operation"], x)) for x in rows]
    r.data["worst_abs_diff"] = worst

    r.h("SOFR Index")
    irows = []
    for prev, cur in zip(pubs, pubs[1:]):
        o = res.get(f"idx-{cur['effectiveDate']}")
        if not o or o["status"] != "ok":
            continue
        T0, T1 = dt.date.fromisoformat(prev["effectiveDate"]), dt.date.fromisoformat(cur["effectiveDate"])
        implied = (cur["index"] / prev["index"] - 1) * 360 / (T1 - T0).days
        diff = o["outputs"]["compounded_rate"] - implied
        # Index is published to 8 decimals; over one day that rounding is about 1e-8 / index * 360, so allow 5e-6.
        r.check(f"Index step {cur['effectiveDate']}", "warn", abs(diff) <= 5e-6, f"diff {diff:.2e}")
        irows.append((prev["effectiveDate"], cur["effectiveDate"], f"{implied * 100:.5f}", f"{o['outputs']['compounded_rate'] * 100:.5f}", f"{diff:.1e}"))
    r.table(["From", "To", "Index-implied (%)", "Library (%)", "Diff"], irows)

    r.h("USD-LIBOR-3M fallback")
    o = res["fallback"]
    r.check("fallback computed", "fail", o["status"] == "ok", o.get("error", {}).get("message", "ok"))
    if o["status"] == "ok":
        out = o["outputs"]
        r.check("ISDA 3M spread adjustment", "fail", abs(out["spread_adjustment"] - ISDA_3M_SPREAD) < 1e-12, f"{out['spread_adjustment']}")
        r.check("fallback = compounded + spread", "fail",
                abs(out["fallback_rate"] - out["compounded_rate"] - out["spread_adjustment"]) < 1e-12, f"{out['fallback_rate']}")
        r.p(f"Period {fb_start} to {end}: compounded {out['compounded_rate'] * 100:.5f}%, spread "
            f"{out['spread_adjustment'] * 100:.5f}%, fallback {out['fallback_rate'] * 100:.5f}%.")
        r.data["fallback"] = {"start": fb_start, "end": end, **out}
    return r.write([c.SOURCES["nyfed-sofr"]["notice"]])


if __name__ == "__main__":
    sys.exit(main())
