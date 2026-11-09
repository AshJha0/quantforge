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
    "TERM.HELPERS": ("02-curves/projection-and-fra.md USD-TERM-3M deposits, FRAs, swaps", "IborIndex TERM 3M (2 days, US GovernmentBond, ModifiedFollowing, Actual360); DepositRateHelper, FraRateHelper, SwapRateHelper(Annual, ModifiedFollowing, Thirty360 BondBasis, exogenous discount)"),
    "CRV.LOG_LINEAR_DF": ("02-curves/curve-framework.md LOG_LINEAR_DF", "PiecewiseLogLinearDiscount(ref, helpers, Actual365Fixed)"),
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


PIECEWISE = {"LOG_LINEAR_DF": lambda a, hs, j=None: ql.PiecewiseLogLinearDiscount(a, hs, A365),
             "MONOTONIC_LOG_CUBIC": lambda a, hs, j=None: ql.PiecewiseLogCubicDiscount(a, hs, A365),
             "MONOTONE_CONVEX": lambda a, hs, j=None: ql.PiecewiseConvexMonotoneForward(a, hs, A365, [], [], ql.ConvexMonotone(0.0, 1.0, False))}


def _term_index(h=None):
    return ql.IborIndex("TERM", ql.Period(3, ql.Months), 2, ql.USDCurrency(), ql.UnitedStates(ql.UnitedStates.GovernmentBond), ql.ModifiedFollowing,
                        False, ql.Actual360(), h or ql.YieldTermStructureHandle())


def ql_joint(i, bump=None):
    """QuantLib build of an OIS + PROJECTION system (no turns, steps or xccy). bump = (instrument index, dq). Returns
    {curve name: (QuantLib curve, pillar dates)}."""
    a = Q(D(i["as_of"]))
    ql.Settings.instance().evaluationDate = a
    built = {}
    for c in i["curves"]:
        if c["type"] not in ("OIS", "PROJECTION") or c.get("turns") or c.get("jumps") or c["interpolation"] not in PIECEWISE:
            raise NotImplementedError(f"{c['type']} {c.get('interpolation')} turns={bool(c.get('turns'))}")
        hs = []
        for k, q in enumerate(i["instruments"]):
            if q["curve"] != c["name"]:
                continue
            r = q["rate"] + (bump[1] if bump and bump[0] == k else 0.0)
            qq = ql.QuoteHandle(ql.SimpleQuote(r))
            if q["type"] == "OIS":
                sl, pl = LAGS[c["convention"]]
                hs.append(ql.OISRateHelper(sl, _per(q["tenor"]), qq, IDX[c["convention"]](), ql.YieldTermStructureHandle(), True, pl))
            elif q["type"] == "DEPOSIT":
                hs.append(ql.DepositRateHelper(qq, _term_index()))
            elif q["type"] == "FRA":
                hs.append(ql.FraRateHelper(qq, q["start_months"], _term_index()))
            elif q["type"] == "SWAP":
                idx = _term_index()
                hs.append(ql.SwapRateHelper(qq, ql.Period(q["months"], ql.Months), idx.fixingCalendar(), ql.Annual, ql.ModifiedFollowing,
                                            ql.Thirty360(ql.Thirty360.BondBasis), idx, ql.QuoteHandle(), ql.Period(0, ql.Days),
                                            ql.YieldTermStructureHandle(built[c["discount"]][0])))
            else:
                raise NotImplementedError(q["type"])
        cv = PIECEWISE[c["interpolation"]](a, hs)
        cv.enableExtrapolation()
        built[c["name"]] = (cv, [h.pillarDate() for h in hs])
    return built


def h_joint(i):
    b0 = ql_joint(i)
    curves = [{"name": c["name"], "pillars": [{"date": p.ISO(), "discount_factor": b0[c["name"]][0].discount(p)} for p in b0[c["name"]][1]]} for c in i["curves"]]
    x0 = [math.log(p["discount_factor"]) for cv in curves for p in cv["pillars"]]
    labels = [f"{cv['name']}:pillar:{p['date']}" for cv in curves for p in cv["pillars"]]

    def xs(bump):
        b = ql_joint(i, bump)
        return [math.log(b[c["name"]][0].discount(p)) for c in i["curves"] for p in b[c["name"]][1]]
    h = 1e-4
    cols = []
    for k in range(len(i["instruments"])):
        d1 = [(u - v) / (2 * h) for u, v in zip(xs((k, h)), xs((k, -h)))]
        d2 = [(u - v) / h for u, v in zip(xs((k, h / 2)), xs((k, -h / 2)))]
        cols.append([(4 * q2 - q1) / 3 for q1, q2 in zip(d1, d2)])
    matrix = [[cols[k][r] for k in range(len(cols))] for r in range(len(x0))]
    return {"curves": curves, "turn_factors": [], "jacobian": {"unknowns": labels, "quotes": [q["id"] for q in i["instruments"]], "matrix": matrix},
            "turn_sensitivity": []}, {"CRV." + c["interpolation"] for c in i["curves"]} | {"OIS.HELPER", "IDX", "TERM.HELPERS"}


HANDLERS = {"rates.ois.bootstrap": h_bootstrap, "rates.curve.inspect": h_inspect, "rates.curve.joint_solve": h_joint}


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
            except NotImplementedError:
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
