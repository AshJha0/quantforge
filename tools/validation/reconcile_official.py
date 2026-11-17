#!/usr/bin/env python3
"""Validation evidence pack, option B: rebuild an OIS curve from a published fitted curve and compare at the pillars.

Free data has no SOFR or SONIA swap quotes (stage D data survey, LEARN.md), so the published curve itself supplies
the quotes. The round trip is:

  1. published fitted zero curve D_pub(date)  (Fed staff GSW Treasury curve; Bank of England fitted OIS curve)
  2. par OIS rates for standard tenors, priced by QuantLib MakeOIS on D_pub (an outside library, not QuantForge)
  3. QuantForge `rates.ois.bootstrap` on those par rates (the library under review)
  4. compare QuantForge's discount factors at its own pillar dates with D_pub on the same dates

What it tests: that the bootstrap, its schedules and its conventions invert an outside pricer's par rates back to the
curve they came from. What it does not test: market quotes (none are free), or the curve between pillars, where
QuantForge interpolates log-linearly in the discount factor and the published curves are smooth parametric (GSW,
Svensson) or spline (BoE) fits; the gap there is a method difference, reported for information only.

Tolerance, stated before the run: |z_QF - z_pub| <= 0.5 bp at every pillar, z = -ln D / t, t = days / 365. Reason:
coupon dates sit on earlier pillars apart from payment lag (2 days for SOFR), so the only error source is the
log-linear interpolation over those few days and the published curve's own interpolation on its grid.

Time on the published curve: years = days / 365.25 (GSW and BoE publish yields by maturity in years). The BoE grid
is interpolated linearly in the zero rate between published maturities; GSW is evaluated from its Svensson parameters,
checked against its published SVENYnn zero yields.

Terms: GSW (federalreserve.gov, staff research product, not an official statistical release) and the BoE curves
(Bank copyright, internal non-commercial use; tools/workflows/boe_curves.py) are used locally. No published value
is written to the repository: the report gives pass or fail at the stated tolerance and two tighter tiers.

Two steps, because QuantLib runs in the oracle venv (WSL; its Windows DLL may be blocked) and the CLI on the host:
    <oracle python> tools/validation/reconcile_official.py quotes --gsw feds200628.csv --boe latest-yield-curve-data.zip --work DIR
    python tools/validation/reconcile_official.py compare --work DIR [--impl python] [--out docs/validation/data/real-data.json]
"""
import argparse
import bisect
import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOL_BP = 0.5
TIERS_BP = (0.5, 0.1, 0.01)
TENORS = {"SOFR": ["1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y", "15Y", "20Y", "25Y", "30Y"],
          "ESTR": ["1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y", "15Y", "20Y", "25Y", "30Y"],
          "SONIA": ["1Y", "2Y", "3Y", "4Y", "5Y", "7Y", "10Y", "15Y", "20Y", "25Y", "30Y"]}
# Second set: a pillar every year, so every annual coupon date lies on a pillar (apart from payment lag). This
# separates the conventions (should agree to rounding) from the interpolation gap in the standard set.
EVERY_YEAR = ["1W", "1M", "3M", "6M"] + [f"{n}Y" for n in range(1, 31)]  # short tenors pin the front stub


def gsw(path):
    """Latest row of feds200628.csv: (iso date, years -> zero decimal, check of the parameters against SVENYnn)."""
    rows = list(csv.reader(open(path, encoding="utf-8")))
    hi = next(i for i, r in enumerate(rows) if r and r[0] == "Date")
    head = rows[hi]
    last = [r for r in rows[hi + 1:] if r and r[0][:2] in ("19", "20")][-1]
    v = dict(zip(head, last))
    b0, b1, b2, b3, t1, t2 = (float(v[k]) for k in ("BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2"))

    def y(tau):
        a, b = tau / t1, tau / t2
        f1 = (1 - math.exp(-a)) / a
        f2 = (1 - math.exp(-b)) / b
        return (b0 + b1 * f1 + b2 * (f1 - math.exp(-a)) + b3 * (f2 - math.exp(-b))) / 100
    worst = max(abs(y(n) * 100 - float(v[f"SVENY{n:02d}"])) for n in range(1, 31) if v.get(f"SVENY{n:02d}", "NA") != "NA")
    return v["Date"], y, worst


def ecb(folder):
    """ECB euro area AAA government curve, Svensson parameters (ecb_BETA0.csv ... ecb_TAU2.csv, ECB Data Portal series
    YC/B.U2.EUR.4F.G_N_A.SV_C_YM.<param>, csvdata): (iso date, years -> zero decimal, check against SR_1Y and SR_10Y)."""
    def last(k):
        rows = list(csv.DictReader(open(Path(folder) / f"ecb_{k}.csv", encoding="utf-8")))
        return rows[-1]["TIME_PERIOD"], float(rows[-1]["OBS_VALUE"])
    vals = {k: last(k) for k in ("BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2")}
    days = {d for d, _ in vals.values()}
    assert len(days) == 1, days
    b0, b1, b2, b3, t1, t2 = (vals[k][1] for k in ("BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2"))

    def y(tau):
        a, b = tau / t1, tau / t2
        f1, f2 = (1 - math.exp(-a)) / a, (1 - math.exp(-b)) / b
        return (b0 + b1 * f1 + b2 * (f1 - math.exp(-a)) + b3 * (f2 - math.exp(-b))) / 100
    worst = max(abs(y(n) * 100 - last(f"SR_{n}Y")[1]) for n in (1, 10))
    return days.pop(), y, worst


def boe(path):
    sys.path.insert(0, str(ROOT / "tools" / "workflows"))
    import boe_curves
    day, pts = boe_curves.spot_curves(Path(path).read_bytes(), "ois")[-1]
    ts, zs = [p[0] for p in pts], [p[1] for p in pts]

    def y(tau):
        if tau <= ts[0]:
            return zs[0]
        if tau >= ts[-1]:
            return zs[-1]
        i = bisect.bisect_right(ts, tau)
        w = (tau - ts[i - 1]) / (ts[i] - ts[i - 1])
        return zs[i - 1] + w * (zs[i] - zs[i - 1])
    return day, y, ts[-1]


def quotes(a):
    import QuantLib as ql
    sys.path.insert(0, str(ROOT / "oracle" / "python"))
    import gen_stage_b as B
    import gen_stage_d as D
    from qf_oracle import rates as RT
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    out = {}
    srcs = {}
    if a.gsw:
        d, y, worst = gsw(a.gsw)
        srcs["SOFR"] = (d, y, 30.0, {"source": "GSW (Fed staff fitted Treasury zero curve, feds200628.csv)", "param_check_max_pct": worst})
    if a.ecb:
        D.estr()  # adds ESTR conventions (spot lag 2, payment lag 2, ACT_360) to the shared table
        d, y, worst = ecb(a.ecb)
        srcs["ESTR"] = (d, y, 30.0, {"source": "ECB euro area AAA government curve (Svensson parameters, ECB Data Portal)", "param_check_max_pct": worst})
    if a.boe:
        d, y, top = boe(a.boe)
        srcs["SONIA"] = (d, y, top, {"source": "Bank of England fitted OIS spot curve (latest-yield-curve-data.zip)", "max_maturity_years": top})
    for conv, (d, y, top, meta) in srcs.items():
        as_of = dt.date.fromisoformat(d)
        qd = ql.Date(as_of.day, as_of.month, as_of.year)
        ql.Settings.instance().evaluationDate = qd
        days = list(range(0, int(round(top * 365.25)) + 400))
        dates = [qd + n for n in days]
        dfs = [1.0] + [math.exp(-y(n / 365.25) * n / 365.25) for n in days[1:]]
        h = ql.YieldTermStructureHandle(ql.DiscountCurve(dates, dfs, ql.Actual365Fixed()))
        c = RT.CONV[conv]
        ref = {(as_of + dt.timedelta(n)).isoformat(): v for n, v in zip(days, dfs)}
        for key, ten in ((conv, TENORS[conv]), (conv + "-EVERY-YEAR", EVERY_YEAR)):
            qs = []
            for t in ten:
                if t.endswith("Y") and int(t[:-1]) > top + 1e-9:
                    continue
                sw = ql.MakeOIS(B.qper(t), D.qindex(conv, h), 0.0, settlementDays=c["spot_lag"], paymentLag=c["payment_lag"],
                                pricingEngine=ql.DiscountingSwapEngine(h), telescopicValueDates=True)
                qs.append({"tenor": t, "rate": sw.fairRate()})
            out[key] = {"convention": conv, "as_of": d, "quotes": qs, "meta": meta, "par_pricer": f"QuantLib {ql.__version__} MakeOIS"}
        # The published discount factor on each calendar date out to the last tenor, kept in the work dir only.
        (work / f"ref-{conv}.json").write_text(json.dumps(ref), encoding="utf-8")
    (work / "quotes.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: {"as_of": v["as_of"], "tenors": len(v["quotes"]), **v["meta"]} for k, v in out.items()}, indent=1))


def compare(a):
    sys.path.insert(0, str(ROOT / "tools" / "workflows"))
    import common as c
    work = Path(a.work)
    q = json.loads((work / "quotes.json").read_text(encoding="utf-8"))
    cases = [c.case(conv, "rates.ois.bootstrap", {"convention": v["convention"], "as_of": v["as_of"], "quotes": v["quotes"],
                                                  "interpolation": "LOG_LINEAR_DF", "method": "SEQUENTIAL"}) for conv, v in q.items()]
    res = c.batch(cases, a.impl)
    report = {"generator": "tools/validation/reconcile_official.py", "tolerance_bp": TOL_BP, "tiers_bp": list(TIERS_BP),
              "implementation": a.impl, "curves": {}}
    ok_all = True
    for conv, v in q.items():
        ref = json.loads((work / f"ref-{v['convention']}.json").read_text(encoding="utf-8"))
        r = res[conv]
        ent = {"as_of": v["as_of"], "source": v["meta"]["source"], "par_pricer": v["par_pricer"], "tenors": [x["tenor"] for x in v["quotes"]]}
        if r["status"] != "ok":
            ent["result"] = "bootstrap failed: " + r.get("error", {}).get("message", "")
            ok_all = False
        else:
            diffs, mids = [], []
            pil = r["outputs"]["pillars"]
            prev = (v["as_of"], 1.0)
            for p in pil:
                t = c.years(p["date"], v["as_of"])
                diffs.append(abs(-math.log(p["discount_factor"]) / t + math.log(ref[p["date"]]) / t) * 1e4)
                # Midpoint between pillars: QuantForge log-linear against the published curve. Information only.
                d0, d1 = dt.date.fromisoformat(prev[0]), dt.date.fromisoformat(p["date"])
                m = d0 + (d1 - d0) / 2
                w = (m - d0).days / (d1 - d0).days
                qf = math.exp((1 - w) * math.log(prev[1]) + w * math.log(p["discount_factor"]))
                tm = c.years(m.isoformat(), v["as_of"])
                if tm > 0:
                    mids.append(abs(-math.log(qf) / tm + math.log(ref[m.isoformat()]) / tm) * 1e4)
                prev = (p["date"], p["discount_factor"])
            worst = max(diffs)
            ent["pillars"] = len(pil)
            ent["pass"] = worst <= TOL_BP
            ent["tiers"] = {f"{t} bp": worst <= t for t in TIERS_BP}
            ent["between_pillars_within_1bp"] = max(mids) <= 1.0
            ent["between_pillars_within_5bp"] = max(mids) <= 5.0
            ok_all &= ent["pass"]
            if a.show:
                print(conv, "max pillar diff bp", worst, "max midpoint diff bp", max(mids), "argmax", pil[diffs.index(worst)]["date"])
        report["curves"][conv] = ent
    text = json.dumps(report, indent=1) + "\n"
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0 if ok_all else 1


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p1 = sp.add_parser("quotes")
    p1.add_argument("--gsw")
    p1.add_argument("--boe")
    p1.add_argument("--ecb", help="folder with ecb_BETA0.csv ... ecb_TAU2.csv, ecb_SR_1Y.csv, ecb_SR_10Y.csv")
    p1.add_argument("--work", required=True)
    p2 = sp.add_parser("compare")
    p2.add_argument("--work", required=True)
    p2.add_argument("--impl", default="python")
    p2.add_argument("--out")
    p2.add_argument("--show", action="store_true", help="print the worst differences locally (not written to --out)")
    a = ap.parse_args()
    return quotes(a) if a.cmd == "quotes" else compare(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
