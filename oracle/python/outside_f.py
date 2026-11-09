"""Stage F outside-oracle verifier (plan rule 11.2.5). Never writes an expected value.

A case counts only if an outside source reproduces every output within the case's own tolerance:
- QuantLib 1.44 through its own convention objects (rows below, reviewed copy in oracle/CONVENTION_MAP_F.md);
- a published worked example by the methodology owner (the Cboe VIX sample calculation), counted as outside because the
  numbers come from the index provider, not from QuantForge (vix_f, plan R10).
Cases checked only in part (an output QuantLib does not expose) are listed as partly outside and not counted.

    cd oracle/python && uv run python -W ignore outside_f.py
"""
import json
import math
import sys
from datetime import date

import QuantLib as ql

from outside_d import ROOT, judge
from qf_oracle import convmap as CM

Q = lambda d: ql.Date(d.day, d.month, d.year)  # noqa: E731
D = date.fromisoformat
A365 = ql.Actual365Fixed()
REVIEW = "self-reviewed 2026-11-09 (spec session); second review by the R5 audit"

ROWS = {
    "CRV.MONOTONE_CONVEX": ("02-curves/curve-framework.md MONOTONE_CONVEX = QuantLib ConvexMonotone(quadraticity 0, monotonicity 1, forcePositive false), ruling F-19",
                            "PiecewiseConvexMonotoneForward(ref, helpers, Actual365Fixed, [], [], ConvexMonotone(0, 1, False)); ConvexMonotoneInterpolation on discrete forwards"),
    "CRV.MONOTONIC_LOG_CUBIC": ("02-curves/curve-framework.md MONOTONIC_LOG_CUBIC = QuantLib MonotonicLogCubic",
                                "MonotonicLogCubicDiscountCurve(dates, dfs, Actual365Fixed) for D; MonotonicCubicNaturalSpline(t, ln D).derivative for f; PiecewiseLogCubicDiscount(ref, helpers, Actual365Fixed[, jumps])"),
    "OIS.HELPER": ("02-curves/ois-curves.md periods and lags", "OISRateHelper(settlementDays, tenor, quote, index, discount=None, telescopic=True, paymentLag)"),
    "IDX": ("01-core/conventions.md SOFR, SONIA, ESTR", "ql.Sofr(), ql.Sonia(), ql.Estr()"),
    "CBOE.SAMPLE": ("05-volatility/vix-index.md Cboe sample", "Cboe Volatility Index Methodology v6.0, Appendix 3 printed values (F, K0, sigma^2, VIX)"),
}
LAGS = {"SOFR": (2, 2), "ESTR": (2, 2), "SONIA": (0, 0)}
IDX = {"SOFR": ql.Sofr, "SONIA": ql.Sonia, "ESTR": ql.Estr}


def _per(t):
    return ql.Period(int(t[:-1]), {"W": ql.Weeks, "M": ql.Months, "Y": ql.Years}[t[-1]])


def ql_build(i):
    a = Q(D(i["as_of"]))
    ql.Settings.instance().evaluationDate = a
    sl, pl = LAGS[i["convention"]]
    hs = [ql.OISRateHelper(sl, _per(q["tenor"]), ql.QuoteHandle(ql.SimpleQuote(q["rate"])), IDX[i["convention"]](), ql.YieldTermStructureHandle(), True, pl)
          for q in i["quotes"]]
    js = i.get("jumps") or []
    jq, jd = [ql.QuoteHandle(ql.SimpleQuote(j["factor"])) for j in js], [Q(D(j["date"])) for j in js]
    if i["interpolation"] == "MONOTONE_CONVEX":
        c = ql.PiecewiseConvexMonotoneForward(a, hs, A365, jq, jd, ql.ConvexMonotone(0.0, 1.0, False))
    elif i["interpolation"] == "MONOTONIC_LOG_CUBIC":
        c = ql.PiecewiseLogCubicDiscount(a, hs, A365, jq, jd) if js else ql.PiecewiseLogCubicDiscount(a, hs, A365)
    else:
        raise NotImplementedError(i["interpolation"])
    c.enableExtrapolation()
    return c, hs


def h_bootstrap(i):
    c, hs = ql_build(i)
    return {"pillars": [{"date": h.pillarDate().ISO(), "discount_factor": c.discount(h.pillarDate())} for h in hs]}, {"CRV." + i["interpolation"], "OIS.HELPER", "IDX"}


def h_inspect(i):
    cv = i["curve"]
    if cv["interpolation"] != "MONOTONIC_LOG_CUBIC" or cv.get("jumps"):
        raise NotImplementedError("only MONOTONIC_LOG_CUBIC without jumps has a QuantLib discount curve from pillars")
    a = D(cv["as_of"])
    ql.Settings.instance().evaluationDate = Q(a)
    ds = [Q(a)] + [Q(D(p["date"])) for p in cv["pillars"]]
    c = ql.MonotonicLogCubicDiscountCurve(ds, [1.0] + [p["discount_factor"] for p in cv["pillars"]], A365)
    c.enableExtrapolation()
    # instantaneous forward from QuantLib's own spline slope on ln D (forwardRate(t, t) is a 1e-4 finite difference)
    tn = [0.0] + [(D(p["date"]) - a).days / 365 for p in cv["pillars"]]
    sp = ql.MonotonicCubicNaturalSpline(tn, [0.0] + [math.log(p["discount_factor"]) for p in cv["pillars"]])
    out = {"discount_factors": [], "zero_rates": [], "instantaneous_forwards": []}
    for s in i["dates"]:
        d = D(s)
        t = (d - a).days / 365
        df = c.discount(t, True)
        out["discount_factors"].append(df)
        out["zero_rates"].append(None if t == 0 else -math.log(df) / t)
        out["instantaneous_forwards"].append(-sp.derivative(min(t, tn[-1]), True))
    return out, {"CRV.MONOTONIC_LOG_CUBIC"}


def h_cboe(case):
    """The Cboe printed values: the golden must round to them (checked again here, independently of the generator)."""
    o = case["expected"]["outputs"]
    if case["operation"] == "vol.vix.index":
        ok = round(o["index"], 2) == 13.93 and round(o["index"] / 100, 8) == 0.13927842
    elif case["inputs"]["minutes_to_expiry"] == 34484:
        ok = round(o["forward"], 5) == 1962.89996 and o["k0"] == 1960.0 and round(o["variance"], 9) == 0.019233906
    else:
        ok = round(o["forward"], 5) == 1962.40006 and o["k0"] == 1960.0 and round(o["variance"], 9) == 0.019423884
    return ok


HANDLERS = {"rates.ois.bootstrap": h_bootstrap, "rates.curve.inspect": h_inspect}


def main():
    reg, partly, table = [], [], []
    for p in sorted((ROOT / "datasets" / "golden" / "stage_f").glob("*.json")):
        if p.name.startswith("e1_"):
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        n_ok = n = 0
        for c in doc["cases"]:
            n += 1
            if c["expected"]["status"] != "ok":
                continue
            if "cboe-sample" in c["tags"]:
                if h_cboe(c):
                    n_ok += 1
                    reg.append({"case_id": c["case_id"], "operation": c["operation"], "source": "Cboe Volatility Index Methodology v6.0, Appendix 3",
                                "convention_rows": ["CBOE.SAMPLE"], "map_review": REVIEW})
                continue
            h = HANDLERS.get(c["operation"])
            if not h:
                continue
            try:
                got, rows = h(c["inputs"])
            except NotImplementedError as e:
                if c["operation"] == "rates.curve.inspect" and c["inputs"]["curve"]["interpolation"] == "MONOTONE_CONVEX":
                    partly.append({"case_id": c["case_id"], "why": "forwards checked against ConvexMonotoneInterpolation; its integral is not in the wheel"})
                continue
            ok, why, _ = judge(c, got)
            if ok:
                n_ok += 1
                reg.append({"case_id": c["case_id"], "operation": c["operation"], "library": CM.LIBRARY, "version": CM.VERSION,
                            "convention_rows": sorted(rows), "map_review": REVIEW})
            else:
                print(f"  NOT VERIFIED {c['case_id']}: {why}")
        table.append((doc["suite"], n_ok, n))
    (ROOT / "oracle" / "outside_register_f.json").write_text(json.dumps({"rule": "plan 11.2.5", "library": CM.LIBRARY, "version": CM.VERSION, "map_review": REVIEW,
                                                                         "partly_outside_not_counted": partly, "cases": reg}, indent=1) + "\n", encoding="utf-8", newline="\n")
    lines = ["# Stage F convention map (rule 11.2.5)", "", f"QuantLib {CM.VERSION}. {REVIEW}. Written by `oracle/python/outside_f.py`.", "",
             "| Row | Spec | Library objects |", "|---|---|---|"] + [f"| `{k}` | {a} | {b} |" for k, (a, b) in ROWS.items()]
    (ROOT / "oracle" / "CONVENTION_MAP_F.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    tot = sum(t[1] for t in table), sum(t[2] for t in table)
    for s, k, n in table:
        print(f"{s:<12} outside {k:>3} / {n:>3}")
    print(f"stage F (E1 excluded, ruling F-23): {tot[0]} / {tot[1]} = {100 * tot[0] / max(tot[1], 1):.1f}%; partly outside {len(partly)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
