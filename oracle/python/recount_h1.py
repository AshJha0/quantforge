"""R5 finding H1: recount swaption_g, swaption_affine_g and exposure_g against QuantLib 1.44's own
JamshidianSwaptionEngine (no platform root solve or decomposition), at a relative tolerance of 3e-7 (the engine's own
critical-rate stopping, ruling G-13). Updates oracle/outside_register_g.json and writes oracle/H1_RECOUNT_G.json.

    cd oracle/python && uv run python -W ignore recount_h1.py
"""
import json
from pathlib import Path

import QuantLib as ql

from gen_stage_g_w1 import TODAY, DC, ql_curve

HERE = Path(__file__).resolve().parent
GOLD = HERE.parent.parent / "datasets" / "golden" / "stage_g"
REL = 3e-7
ql.IborCoupon.createAtParCoupons()


def on_day(t):
    d = round(t * 365)
    return abs(d / 365 - t) < 1e-13, TODAY + d


def model(inp):
    m = inp.get("model", "HULL_WHITE")
    if m == "HULL_WHITE":
        h = ql_curve(inp["curve"])
        return ql.HullWhite(h, inp["mean_reversion"], inp["sigma"]), h
    if m == "VASICEK":
        mm = ql.Vasicek(inp["short_rate"], inp["mean_reversion"], inp["long_term_mean"], inp["sigma"])
    else:
        mm = ql.CoxIngersollRoss(inp["short_rate"], inp["long_term_mean"], inp["mean_reversion"], inp["sigma"])
    zc = ql.ZeroCurve  # model-implied discounting for the index: a discount curve sampled from the model's own bonds
    dates = [TODAY + d for d in range(0, 365 * 31 + 1, 30)]
    dfs = [1.0] + [mm.discount(DC.yearFraction(TODAY, d)) for d in dates[1:]]
    h = ql.YieldTermStructureHandle(ql.DiscountCurve(dates, dfs, DC))
    return mm, h


def ql_swaption(inp, T0, Ts, payer, notional):
    ok, d0 = on_day(T0)
    ds = []
    for t in Ts:
        o, d = on_day(t)
        ok &= o
        ds.append(d)
    if not ok:
        return None
    m, h = model(inp)
    sched = ql.Schedule(ql.DateVector([d0] + ds), ql.NullCalendar(), ql.Unadjusted)
    idx = ql.IborIndex("QF", ql.Period(1, ql.Years), 0, ql.EURCurrency(), ql.NullCalendar(), ql.Unadjusted, False, DC, h)
    sw = ql.VanillaSwap(ql.VanillaSwap.Payer if payer else ql.VanillaSwap.Receiver, notional, sched, inp["fixed_rate"], DC,
                        sched, idx, 0.0, DC)
    sw.setPricingEngine(ql.DiscountingSwapEngine(h))
    so = ql.Swaption(sw, ql.EuropeanExercise(d0))
    eng = ql.JamshidianSwaptionEngine(m, h)
    so.setPricingEngine(eng)
    return so.NPV()


def close(a, b):
    return abs(a - b) <= 1e-8 + REL * abs(a)


def main():
    res, reg = {}, json.loads((HERE.parent / "outside_register_g.json").read_text(encoding="utf-8"))
    for suite in ("swaption_g", "swaption_affine_g"):
        cases = json.loads((GOLD / f"{suite}.json").read_text(encoding="utf-8"))["cases"]
        n, rows = 0, []
        for c in cases:
            if c["expected"]["status"] != "ok":
                continue
            i = c["inputs"]
            q = ql_swaption(i, i["expiry_years"], i["payment_times"], i["swaption_type"] == "PAYER", i["notional"])
            g = c["expected"]["outputs"]["price"]
            ok = q is not None and close(g, q)
            n += ok
            rows.append({"case": c["case_id"], "golden": g, "quantlib_engine": q, "counted": bool(ok)})
        res[suite] = {"counted": n, "total": len(cases), "rows": rows}
    cases = json.loads((GOLD / "exposure_g.json").read_text(encoding="utf-8"))["cases"]
    n, rows = 0, []
    for c in cases:
        if c["expected"]["status"] != "ok":
            continue
        i = c["inputs"]
        ok, qs = "cva" not in c["expected"]["outputs"], []
        for t, g in zip(i["exposure_times"], c["expected"]["outputs"]["discounted_ee"]):
            rest = [T for T in i["payment_times"] if T > t]
            q = ql_swaption(i, t, rest, i["side"] == "PAY", i["notional"])
            qs.append(q)
        ok = all(q is not None and close(g, q) for q, g in zip(qs, c["expected"]["outputs"]["discounted_ee"]))
        if ok and "cva" in c["expected"]["outputs"]:
            cv = c["expected"]["outputs"]["cva"]  # CVA is arithmetic on the EE (G-16 buckets): recomputed from the engine EEs
            import math
            h, R, ts = i["hazard_rate"], i["recovery"], i["exposure_times"]
            prev, tot = 0.0, 0.0
            for t, e in zip(ts, qs):
                tot += (1 - R) * e * (math.exp(-h * prev) - math.exp(-h * t))
                prev = t
            ok = close(cv, tot)
        n += ok
        rows.append({"case": c["case_id"], "quantlib_engine_ee": qs, "counted": bool(ok)})
    res["exposure_g"] = {"counted": n, "total": len(cases), "rows": rows}
    for k in res:
        reg[k] = {"counted": res[k]["counted"], "total": res[k]["total"],
                  "rule": "QuantLib 1.44 JamshidianSwaptionEngine on a VanillaSwap (par floater on the same curve, NullCalendar, ACT/365F), "
                          "relative 3e-7 (R5 H1); CVA as G-16 bucket arithmetic on the engine EEs"}
        print(k, res[k]["counted"], "of", res[k]["total"])
    (HERE.parent / "H1_RECOUNT_G.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    (HERE.parent / "outside_register_g.json").write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
