"""Stage I wave 2: credit and correlation hedges (specifications/08-hedging/credit-and-correlation-hedges.md, rulings I-15 on).

As in wave 1, every golden (error codes included) is the output of the reference functions here (`*_ref`), and an error
case is kept only if the reference stops at the rule it was written for.

- `hedge.credit.cds`: CDS legs from the stage D ISDA replay (`gen_stage_d_credit.py`, checked there against QuantLib's
  IsdaCdsEngine). CS01 and bucket CS01 are central differences of the hazard rates, fixed by the spec (I-15), so the
  outside check reproduces them exactly from QuantLib NPVs on bumped `HazardRateCurve`s; JTD is arithmetic on the NPV.
- `hedge.correlation.neutralise`: Margrabe exchange options, analytic Greeks at 50 digits (mpmath). Outside: QuantLib 1.44
  `AnalyticEuropeanMargrabeEngine` (`delta1`, `delta2`); vegas and correlation from QuantLib's analytic
  `BlackCalculator.vega`, since the Margrabe price is a Black price in the spread volatility (asserted against the
  engine NPV). A finite-difference stencil on the engine NPV was tried first and is too noisy for 1e-10.

    cd oracle/python && uv run python -W ignore gen_stage_i_w2.py
"""
import json
import math
from datetime import date, timedelta
from pathlib import Path

import mpmath as mp
import numpy as np
import QuantLib as ql

import gen_stage_d as D
import gen_stage_d_credit as C
import gen_stage_i_w1 as W
from gen_stage_i_w1 import QfErr, fail, finite_rule, decide, run_error, RF, EX
from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_i_w2.py"
SPEC = "specifications/08-hedging/credit-and-correlation-hedges.md"
HERE = Path(__file__).resolve().parent
CR, CO = "hedge.credit.cds", "hedge.correlation.neutralise"
MUT = []


def caught(name, gap, tol=1e-9):
    assert gap > tol, f"mutant '{name}' is not caught: gap {gap:.3e}"
    MUT.append((name, float(gap)))


def pdate(s):
    return date.fromisoformat(s)


# ================================================================================================ hedge.credit.cds
def hz_from_json(T, hj):
    dates = [pdate(p["date"]) for p in hj["pillars"]]
    surv = [p["survival"] for p in hj["pillars"]]
    ts = [(d - T).days / 365 for d in dates]
    hz, q0, t0 = [], 1.0, 0.0
    for t, q in zip(ts, surv):
        hz.append(math.log(q0 / q) / (t - t0))
        q0, t0 = q, t
    return dates, hz


def disc_from_json(dj):
    T = pdate(dj["as_of"])
    return D.Curve(T, [pdate(p["date"]) for p in dj["pillars"]], [p["discount_factor"] for p in dj["pillars"]], dj["interpolation"])


def trade_pv(T, disc, H, R, tr, sign):
    p = C.price(T, disc, H, pdate(tr["maturity"]), R, tr["coupon"])
    return sign * p["pv_unit"], p["upfront"]


def risks(T, disc, dates, hz, R, tr, sign, P):
    """Per unit notional, buyer sign given: (pv, cs01, jtd, buckets) for one trade."""
    eps = 1e-4 / (1 - R)
    pv, up = trade_pv(T, disc, C.Hz(T, dates, hz), R, tr, sign)

    def bumped(mask):
        hp = [h + eps * m for h, m in zip(hz, mask)]
        hm = [h - eps * m for h, m in zip(hz, mask)]
        return (trade_pv(T, disc, C.Hz(T, dates, hp), R, tr, sign)[0] - trade_pv(T, disc, C.Hz(T, dates, hm), R, tr, sign)[0]) / 2
    cs01 = bumped([1] * P)
    bks = [bumped([1 if j == k else 0 for j in range(P)]) for k in range(P)]
    jtd = sign * (1 - R) - pv
    return pv, cs01, jtd, bks, up


def credit_ref(inp):
    book, hed, tg = inp["book"], inp["hedges"], inp["targets"]
    if len(book) > 1000 or len(hed) > 50:
        fail("E_LIMIT")
    finite_rule(inp)
    if inp["discount"]["interpolation"] != "LOG_LINEAR_DF":
        fail("E_INPUT", "discount interpolation (R1-4)")
    T = pdate(inp["trade_date"])
    P = len(inp["hazard"]["pillars"])
    names = {"CS01", "JTD"} | {f"BUCKET_{k}" for k in range(1, P + 1)}
    if not book or not hed or len(tg) != len(hed) or len(set(tg)) != len(tg) or any(t not in names for t in tg):
        fail("E_INPUT", "book, hedges, targets")
    for tr in book + hed:
        if pdate(tr["maturity"]) <= T:
            fail("E_INPUT", "maturity not after the trade date")
    R = inp["recovery"]
    if not 0 <= R < 1:
        fail("E_DOMAIN", "recovery")
    if any(tr["notional"] < 0 for tr in book) or any(tr["coupon"] < 0 for tr in book + hed):
        fail("E_DOMAIN", "notional or coupon")
    disc = disc_from_json(inp["discount"])
    dates, hz = hz_from_json(T, inp["hazard"])
    tot = {"pv": 0.0, "cs01": 0.0, "jtd": 0.0, "buckets": [0.0] * P}
    for tr in book:
        sg = (1 if tr["side"] == "BUY_PROTECTION" else -1) * tr["notional"]
        pv, cs, jt, bk, _ = risks(T, disc, dates, hz, R, tr, 1, P)
        tot["pv"] += sg * pv
        tot["cs01"] += sg * cs
        tot["jtd"] += sg * jt
        tot["buckets"] = [a + sg * b for a, b in zip(tot["buckets"], bk)]
    hr = [risks(T, disc, dates, hz, R, h, 1, P) for h in hed]

    def pick(r, t):
        return r[1] if t == "CS01" else r[2] if t == "JTD" else r[3][int(t.split("_")[1]) - 1]
    bookv = {"CS01": tot["cs01"], "JTD": tot["jtd"], **{f"BUCKET_{k + 1}": tot["buckets"][k] for k in range(P)}}
    Gm = mp.matrix([[mp.mpf(pick(r, t)) for r in hr] for t in tg])
    U, Sv, V = mp.svd_r(Gm)
    sv = [Sv[i] for i in range(len(tg))]
    if decide(min(sv), max(sv), "credit hedge matrix"):
        fail("E_SINGULAR", "hedge risks dependent")
    n = mp.lu_solve(Gm, mp.matrix([-mp.mpf(bookv[t]) for t in tg]))
    n = [float(x) for x in n]
    after = {"cs01": tot["cs01"] + sum(x * r[1] for x, r in zip(n, hr)), "jtd": tot["jtd"] + sum(x * r[2] for x, r in zip(n, hr)),
             "buckets": [b + sum(x * r[3][k] for x, r in zip(n, hr)) for k, b in enumerate(tot["buckets"])]}
    return {"notionals": n, "book": {"pv": tot["pv"], "cs01": tot["cs01"], "jtd": tot["jtd"], "buckets": tot["buckets"]},
            "after": after, "hedge_upfront": sum(x * r[4] for x, r in zip(n, hr))}


def ql_risks(T, disc, dates, hz, R, tr, P):
    eps = 1e-4 / (1 - R)

    def npv(h):
        dh, ph = C.ql_setup(T, disc, C.Hz(T, dates, h), R)
        return C.ql_cds(T, pdate(tr["maturity"]), tr["coupon"], R, dh, ph).NPV()

    def fair_up(h):
        dh, ph = C.ql_setup(T, disc, C.Hz(T, dates, h), R)
        return C.ql_cds(T, pdate(tr["maturity"]), tr["coupon"], R, dh, ph).fairUpfront()
    pv = npv(hz)
    cs = (npv([h + eps for h in hz]) - npv([h - eps for h in hz])) / 2
    bk = [(npv([h + eps * (j == k) for j, h in enumerate(hz)]) - npv([h - eps * (j == k) for j, h in enumerate(hz)])) / 2 for k in range(P)]
    return pv, cs, (1 - R) - pv, bk, fair_up(hz)


def credit_outside(inp, out):
    T = pdate(inp["trade_date"])
    disc = disc_from_json(inp["discount"])
    dates, hz = hz_from_json(T, inp["hazard"])
    R, P = inp["recovery"], len(dates)
    tot = np.zeros(3 + P)
    for tr in inp["book"]:
        sg = (1 if tr["side"] == "BUY_PROTECTION" else -1) * tr["notional"]
        pv, cs, jt, bk, _ = ql_risks(T, disc, dates, hz, R, tr, P)
        tot += sg * np.array([pv, cs, jt] + bk)
    hr = [ql_risks(T, disc, dates, hz, R, h, P) for h in inp["hedges"]]
    idx = {"CS01": 1, "JTD": 2, **{f"BUCKET_{k + 1}": 3 + k for k in range(P)}}
    vec = lambda r: np.array([r[0], r[1], r[2]] + r[3])  # noqa: E731
    Gm = np.array([[vec(r)[idx[t]] for r in hr] for t in inp["targets"]])
    n = np.linalg.solve(Gm, -np.array([tot[idx[t]] for t in inp["targets"]]))
    lim = 1e-6 + 1e-8 * max(abs(v) for v in n)
    ok = all(abs(a - b) <= lim for a, b in zip(n, out["notionals"]))
    ok &= all(abs(a - b) <= 1e-6 + 1e-9 * abs(b) for a, b in zip(tot[:3], (out["book"]["pv"], out["book"]["cs01"], out["book"]["jtd"])))
    ok &= abs(sum(x * r[4] for x, r in zip(n, hr)) - out["hedge_upfront"]) <= 1e-6 + 1e-8 * abs(out["hedge_upfront"])
    return bool(ok)


def credit_suite():
    s = Suite("hedgecredit_i", SPEC, G)
    T = D.AS_OF
    disc = D.Curve(T, [T + timedelta(7305)], [math.exp(-.039 * 7305 / 365)])
    jd = D.jcurve(disc, C.disc_dates(disc), [disc.df(d) for d in C.disc_dates(disc)])
    qs = [("1Y", .0060), ("3Y", .0090), ("5Y", .0120), ("7Y", .0135), ("10Y", .0150)]
    R = 0.40
    H, mats, surv = C.bootstrap(T, disc, R, qs)
    jh = C.jhz(T, mats, surv)
    hy, mh, sh = C.bootstrap(T, disc, 0.25, [(t, 4 * q) for t, q in qs])
    jhy = C.jhz(T, mh, sh)
    m = {t: str(C.maturity(T, t)) for t in ("1Y", "2Y", "3Y", "5Y", "7Y", "10Y")}
    base = dict(trade_date=str(T), discount=jd, hazard=jh, recovery=R)
    b7 = [{"maturity": m["7Y"], "coupon": 0.01, "notional": 1e7, "side": "SELL_PROTECTION"}]
    mixed = [{"maturity": m["7Y"], "coupon": 0.01, "notional": 1e7, "side": "SELL_PROTECTION"},
             {"maturity": m["2Y"], "coupon": 0.01, "notional": 2.5e7, "side": "BUY_PROTECTION"},
             {"maturity": m["10Y"], "coupon": 0.05, "notional": 5e6, "side": "SELL_PROTECTION"}]
    h5 = {"maturity": m["5Y"], "coupon": 0.01}
    h3 = {"maturity": m["3Y"], "coupon": 0.01}
    h10 = {"maturity": m["10Y"], "coupon": 0.01}
    h1 = {"maturity": m["1Y"], "coupon": 0.01}
    h7 = {"maturity": m["7Y"], "coupon": 0.01}
    cases = [
        ("CS01 hedge of a sold 7Y with a 5Y", dict(base, book=b7, hedges=[h5], targets=["CS01"])),
        ("CS01 hedge with the same 7Y contract: notional matches", dict(base, book=b7, hedges=[h7], targets=["CS01"])),
        ("JTD hedge of a sold 7Y with a 3Y", dict(base, book=b7, hedges=[h3], targets=["JTD"])),
        ("CS01 and JTD together with a 3Y and a 10Y", dict(base, book=b7, hedges=[h3, h10], targets=["CS01", "JTD"])),
        ("bucket hedge: five buckets, five tenors", dict(base, book=mixed, hedges=[h1, h3, h5, h7, h10], targets=[f"BUCKET_{k}" for k in range(1, 6)])),
        ("mixed book, CS01 with a 5Y at a 500 bp coupon", dict(base, book=mixed, hedges=[dict(h5, coupon=0.05)], targets=["CS01"])),
        ("mixed book, buckets 3 and 4 only", dict(base, book=mixed, hedges=[h5, h7], targets=["BUCKET_3", "BUCKET_4"])),
        ("high-yield curve, recovery 25%: CS01 and JTD", dict(base, hazard=jhy, recovery=0.25, book=[dict(b7[0], coupon=0.05)], hedges=[dict(h3, coupon=0.05), dict(h10, coupon=0.05)], targets=["CS01", "JTD"])),
        ("bought protection hedged by selling (negative notional out)", dict(base, book=[dict(b7[0], side="BUY_PROTECTION")], hedges=[h5], targets=["CS01"])),
        ("zero coupon hedge contract", dict(base, book=b7, hedges=[dict(h5, coupon=0.0)], targets=["CS01"])),
    ]
    n_out = 0
    for desc, inp in cases:
        out = credit_ref(inp)
        # self-checks: targeted risks after the hedge vanish; replay against QuantLib per trade
        for t in inp["targets"]:
            v = out["after"]["cs01"] if t == "CS01" else out["after"]["jtd"] if t == "JTD" else out["after"]["buckets"][int(t[7:]) - 1]
            assert abs(v) < 1e-6, (desc, t, v)
        ok = credit_outside(inp, out)
        n_out += ok
        if not ok:
            note(f"  hedgecredit not counted: {desc}")
        lim = {"absolute": 1e-6, "relative": 1e-8, "reason": "ISDA replay agrees with QuantLib to 1e-15 per unit; notionals up to 1e8, a solve of condition up to 1e3"}
        s.add(CR, inp, out, cls=RF, limit=lim, verified=["isda-replay"] + (["quantlib-1.44-isda-cds-engine", "numpy-2.5-solve"] if ok else []),
              tags=["hedge", "credit", "isda-cds"], description=desc)
    # the same-contract case: CS01 neutral means the hedge buys back exactly the sold notional
    assert abs(s.cases[1]["expected"]["outputs"]["notionals"][0] - 1e7) < 1e-6
    # mutants
    o = credit_ref(cases[0][1])["notionals"][0]
    T_ = pdate(base["trade_date"])
    dates, hz = hz_from_json(T_, jh)

    def cs_one_sided(tr):
        eps = 1e-4 / (1 - R)
        return trade_pv(T_, disc, C.Hz(T_, dates, [h + eps for h in hz]), R, tr, 1)[0] - trade_pv(T_, disc, C.Hz(T_, dates, hz), R, tr, 1)[0]
    mut = -(-1e7 * cs_one_sided(b7[0])) / cs_one_sided(h5)
    caught("one-sided CS01 bump", abs(mut - o), 1e-3)
    jt_clean = credit_ref(cases[3][1])["book"]["jtd"]
    caught("JTD without subtracting the position's value", abs((-1e7 * (1 - R)) - jt_clean), 1.0)
    errs = [
        (dict(base, discount=dict(jd, interpolation="LINEAR_ZERO"), book=b7, hedges=[h5], targets=["CS01"]), "E_INPUT", "discount not LOG_LINEAR_DF (R1-4)"),
        (dict(base, book=b7, hedges=[h5, h3], targets=["CS01"]), "E_INPUT", "two hedges, one target"),
        (dict(base, book=b7, hedges=[h5, h3], targets=["CS01", "CS01"]), "E_INPUT", "repeated target"),
        (dict(base, book=b7, hedges=[h5], targets=["BUCKET_6"]), "E_INPUT", "bucket beyond the last hazard pillar"),
        (dict(base, book=b7, hedges=[{"maturity": str(T), "coupon": 0.01}], targets=["CS01"]), "E_INPUT", "hedge maturing on the trade date"),
        (dict(base, recovery=1.0, book=b7, hedges=[h5], targets=["CS01"]), "E_DOMAIN", "recovery 1"),
        (dict(base, book=[dict(b7[0], notional=-1.0)], hedges=[h5], targets=["CS01"]), "E_DOMAIN", "negative book notional"),
        (dict(base, book=b7, hedges=[h5, dict(h5)], targets=["CS01", "JTD"]), "E_SINGULAR", "the same contract twice"),
        (dict(base, book=b7, hedges=[h1, h3], targets=["BUCKET_4", "BUCKET_5"]), "E_SINGULAR", "short hedges have no risk in late buckets"),
    ]
    for inp, code, desc in errs:
        run_error(s, CR, credit_ref, inp, code, desc, ["hedge", "credit"])
    return s, n_out, "QuantLib 1.44 IsdaCdsEngine NPVs on bumped HazardRateCurves (CS01, buckets, JTD by the spec's own central difference), then numpy solve; notionals, book pv, CS01, JTD and hedge upfront within the case limit"


# ================================================================================================ hedge.correlation.neutralise
CG = ("DELTA_1", "DELTA_2", "VEGA_1", "VEGA_2", "CORRELATION")
OUTK = {"DELTA_1": "delta_1", "DELTA_2": "delta_2", "VEGA_1": "vega_1", "VEGA_2": "vega_2", "CORRELATION": "correlation01"}


def margrabe(mk, ins):
    if ins["instrument"] == "UNDERLYING_1":
        return {"DELTA_1": mp.mpf(1), "DELTA_2": mp.mpf(0), "VEGA_1": mp.mpf(0), "VEGA_2": mp.mpf(0), "CORRELATION": mp.mpf(0), "price": mp.mpf(mk["spot1"])}
    if ins["instrument"] == "UNDERLYING_2":
        return {"DELTA_1": mp.mpf(0), "DELTA_2": mp.mpf(1), "VEGA_1": mp.mpf(0), "VEGA_2": mp.mpf(0), "CORRELATION": mp.mpf(0), "price": mp.mpf(mk["spot2"])}
    if ins["instrument"] in VAN:
        k = ins["instrument"][-1]
        g = W.bs_greeks(mk[f"spot{k}"], mk["rate"], mk[f"yield{k}"], mk[f"vol{k}"], {"instrument": ins["instrument"][:-2], "strike": ins["strike"], "expiry_years": ins["expiry_years"]})
        z = mp.mpf(0)
        return {"DELTA_1": g["DELTA"] if k == "1" else z, "DELTA_2": g["DELTA"] if k == "2" else z, "VEGA_1": g["VEGA"] if k == "1" else z,
                "VEGA_2": g["VEGA"] if k == "2" else z, "CORRELATION": z, "price": z}
    S1, S2, q1, q2, v1, v2, rho = (mp.mpf(mk[k]) for k in ("spot1", "spot2", "yield1", "yield2", "vol1", "vol2", "correlation"))
    Q1, Q2, T = mp.mpf(ins["quantity1"]), mp.mpf(ins["quantity2"]), mp.mpf(ins["expiry_years"])
    s = mp.sqrt(v1 * v1 + v2 * v2 - 2 * rho * v1 * v2)
    F1, F2 = Q1 * S1 * mp.exp(-q1 * T), Q2 * S2 * mp.exp(-q2 * T)
    d1 = (mp.log(F1 / F2) + s * s * T / 2) / (s * mp.sqrt(T))
    d2 = d1 - s * mp.sqrt(T)
    dVds = F1 * mp.npdf(d1) * mp.sqrt(T)
    return {"DELTA_1": Q1 * mp.exp(-q1 * T) * mp.ncdf(d1), "DELTA_2": -Q2 * mp.exp(-q2 * T) * mp.ncdf(d2),
            "VEGA_1": dVds * (v1 - rho * v2) / s, "VEGA_2": dVds * (v2 - rho * v1) / s,
            "CORRELATION": dVds * (-v1 * v2 / s) * mp.mpf("0.01"), "price": F1 * mp.ncdf(d1) - F2 * mp.ncdf(d2)}


VAN = ("CALL_1", "PUT_1", "CALL_2", "PUT_2")


def corr_check(ins):
    k = set(ins)
    need = {"EXCHANGE": {"quantity1", "quantity2", "expiry_years"}}.get(ins["instrument"], {"strike", "expiry_years"} if ins["instrument"] in VAN else set())
    if (k & {"quantity1", "quantity2", "strike", "expiry_years"}) != need:
        fail("E_INPUT", "instrument fields")


def corr_ref(inp):
    book, hed, tg = inp["book"], inp["hedges"], inp["targets"]
    if len(book) > 1000 or len(hed) > 5:
        fail("E_LIMIT")
    finite_rule(inp)
    for x in book + hed:
        corr_check(x)
    if not hed or len(tg) != len(hed) or len(set(tg)) != len(tg):
        fail("E_INPUT", "targets and hedges")
    if inp["spot1"] <= 0 or inp["spot2"] <= 0 or inp["vol1"] <= 0 or inp["vol2"] <= 0 or not -1 <= inp["correlation"] <= 1:
        fail("E_DOMAIN", "market")
    for x in book + hed:
        if x["instrument"] == "EXCHANGE" and (x["quantity1"] <= 0 or x["quantity2"] <= 0 or x["expiry_years"] <= 0):
            fail("E_DOMAIN", "option fields")
        if x["instrument"] in VAN and (x["strike"] <= 0 or x["expiry_years"] <= 0):
            fail("E_DOMAIN", "option fields")
    v1, v2, r = inp["vol1"], inp["vol2"], inp["correlation"]
    if any(x["instrument"] == "EXCHANGE" for x in book + hed) and v1 * v1 + v2 * v2 - 2 * r * v1 * v2 <= 0:
        fail("E_DOMAIN", "zero spread volatility")
    before = {g: sum(mp.mpf(p["quantity"]) * margrabe(inp, p)[g] for p in book) for g in CG}
    hg = [margrabe(inp, h) for h in hed]
    Gm = mp.matrix([[h[t] for h in hg] for t in tg])
    U, Sv, V = mp.svd_r(Gm)
    sv = [Sv[i] for i in range(len(tg))]
    if decide(min(sv), max(sv), "correlation hedge matrix"):
        fail("E_SINGULAR", "hedge Greeks dependent")
    qv = mp.lu_solve(Gm, mp.matrix([-before[t] for t in tg]))
    after = {g: before[g] + sum(qv[j] * hg[j][g] for j in range(len(hed))) for g in CG}
    return {"quantities": [float(x) for x in qv], "greeks_before": {OUTK[g]: float(before[g]) for g in CG},
            "greeks_after": {OUTK[g]: float(after[g]) for g in CG}}


def ql_margrabe(mk, ins, bump=None):
    """QuantLib Greeks per unit: delta1, delta2 from the Margrabe engine; vegas and correlation from BlackCalculator.vega."""
    if ins["instrument"] in VAN:
        k = ins["instrument"][-1]
        g = W.ql_greeks({"spot": mk[f"spot{k}"], "rate": mk["rate"], "dividend_yield": mk[f"yield{k}"], "volatility": mk[f"vol{k}"]},
                        {"instrument": ins["instrument"][:-2], "strike": ins["strike"], "expiry_years": ins["expiry_years"]})
        return {"DELTA_1": g["DELTA"] * (k == "1"), "DELTA_2": g["DELTA"] * (k == "2"), "VEGA_1": g["VEGA"] * (k == "1"), "VEGA_2": g["VEGA"] * (k == "2"), "CORRELATION": 0.0}
    if ins["instrument"] != "EXCHANGE":
        return {k: float(v) for k, v in margrabe(mk, ins).items()}
    dc, today = ql.Actual365Fixed(), ql.Date(11, 11, 2026)
    ql.Settings.instance().evaluationDate = today
    days = round(ins["expiry_years"] * 365)
    assert abs(days - ins["expiry_years"] * 365) < 1e-9

    def npv(v1, v2, rho, greeks=False):
        def proc(S, q, v):
            return ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(S)), ql.YieldTermStructureHandle(ql.FlatForward(today, q, dc, ql.Continuous)),
                                                ql.YieldTermStructureHandle(ql.FlatForward(today, 0.03, dc, ql.Continuous)),
                                                ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.NullCalendar(), v, dc)))
        o = ql.MargrabeOption(int(ins["quantity1"]), int(ins["quantity2"]), ql.EuropeanExercise(today + days))
        o.setPricingEngine(ql.AnalyticEuropeanMargrabeEngine(proc(mk["spot1"], mk["yield1"], v1), proc(mk["spot2"], mk["yield2"], v2), rho))
        return (o.NPV(), o.delta1(), o.delta2()) if greeks else o.NPV()

    v1, v2, r = mk["vol1"], mk["vol2"], mk["correlation"]
    price, d1, d2 = npv(v1, v2, r, True)
    # V = F2 * Black(call, strike 1, forward F1/F2, stdDev s sqrt T): dV/ds from QuantLib's analytic stdDev derivative
    T = days / 365
    sv = math.sqrt(v1 * v1 + v2 * v2 - 2 * r * v1 * v2)
    F1 = ins["quantity1"] * mk["spot1"] * math.exp(-mk["yield1"] * T)
    F2 = ins["quantity2"] * mk["spot2"] * math.exp(-mk["yield2"] * T)
    assert abs(F2 * ql.blackFormula(ql.Option.Call, 1.0, F1 / F2, sv * math.sqrt(T)) - price) < 1e-12 * price
    bc = ql.BlackCalculator(ql.PlainVanillaPayoff(ql.Option.Call, 1.0), F1 / F2, sv * math.sqrt(T), 1.0)
    dVds = F2 * bc.vega(T)  # BlackCalculator.vega(T): d price / d sigma with stdDev = sigma sqrt(T)
    out = {"price": price, "DELTA_1": d1, "DELTA_2": d2, "VEGA_1": dVds * (v1 - r * v2) / sv, "VEGA_2": dVds * (v2 - r * v1) / sv,
           "CORRELATION": dVds * (-v1 * v2 / sv) * 0.01}
    return out


def corr_suite():
    s = Suite("hedgecorr_i", SPEC, G)
    mk = dict(spot1=100.0, spot2=95.0, rate=0.03, yield1=0.01, yield2=0.02, vol1=0.25, vol2=0.20, correlation=0.6)
    X = lambda q1, q2, d: {"instrument": "EXCHANGE", "quantity1": float(q1), "quantity2": float(q2), "expiry_years": d / 365}  # noqa: E731
    book = [dict(X(1, 1, 365), quantity=-1000.0), dict(X(1, 1, 730), quantity=400.0)]
    U1, U2 = {"instrument": "UNDERLYING_1"}, {"instrument": "UNDERLYING_2"}
    e1, e2 = X(1, 1, 182), X(2, 1, 547)
    c1 = {"instrument": "CALL_1", "strike": 100.0, "expiry_years": 365 / 365}
    p2 = {"instrument": "PUT_2", "strike": 90.0, "expiry_years": 547 / 365}
    cases = [
        ("correlation hedge with one exchange option", dict(mk, book=book, hedges=[e1], targets=["CORRELATION"])),
        ("correlation and both deltas", dict(mk, book=book, hedges=[e1, U1, U2], targets=["CORRELATION", "DELTA_1", "DELTA_2"])),
        ("all five Greeks", dict(mk, book=book, hedges=[e1, c1, p2, U1, U2], targets=["CORRELATION", "VEGA_1", "VEGA_2", "DELTA_1", "DELTA_2"])),
        ("correlation and vega of asset 1: exchange option and a call on asset 1", dict(mk, book=book, hedges=[e1, c1], targets=["CORRELATION", "VEGA_1"])),
        ("delta hedge only with the two underlyings", dict(mk, book=book, hedges=[U1, U2], targets=["DELTA_1", "DELTA_2"])),
        ("negative correlation", dict(mk, correlation=-0.4, book=book, hedges=[e1, U1, U2], targets=["CORRELATION", "DELTA_1", "DELTA_2"])),
        ("zero correlation", dict(mk, correlation=0.0, book=book, hedges=[e2], targets=["CORRELATION"])),
        ("correlation 1 with unequal vols (spread vol 0.05)", dict(mk, correlation=1.0, book=book, hedges=[e1], targets=["CORRELATION"])),
        ("book holding an underlying", dict(mk, book=book + [dict(U1, quantity=250.0)], hedges=[e1, U1, U2], targets=["CORRELATION", "DELTA_1", "DELTA_2"])),
    ]
    n_out = 0
    for desc, inp in cases:
        out = corr_ref(inp)
        scale = max(abs(v) for v in out["greeks_before"].values())
        lim = {"absolute": 1e-10 * max(1.0, scale), "relative": 1e-10, "reason": "targeted Greeks after hedging are zero up to rounding of the before value"}
        qg = [ql_margrabe(inp, h) for h in inp["hedges"]]
        Gq = np.array([[g[t] for g in qg] for t in inp["targets"]])
        bq = {t: sum(p["quantity"] * ql_margrabe(inp, p)[t] for p in inp["book"]) for t in CG}
        qq = np.linalg.solve(Gq, -np.array([bq[t] for t in inp["targets"]]))
        ok = all(abs(a - b) <= 1e-10 * max(1, abs(b)) for a, b in zip(qq, out["quantities"])) and \
            all(abs(bq[t] - out["greeks_before"][OUTK[t]]) <= lim["absolute"] + 1e-10 * abs(bq[t]) for t in CG)
        n_out += ok
        if not ok:
            note(f"  hedgecorr not counted: {desc}")
        s.add(CO, inp, out, cls=RF, limit=lim, verified=["mpmath-50"] + (["quantlib-1.44-margrabe", "numpy-2.5-solve"] if ok else []),
              tags=["hedge", "correlation"], description=desc)
    # correlation01 sign: higher correlation narrows the spread, so a long exchange option loses (risk.sens.correlation)
    assert margrabe(mk, X(1, 1, 365))["CORRELATION"] < 0
    v1, v2, r = mk["vol1"], mk["vol2"], mk["correlation"]
    caught("correlation sensitivity per unit, not per 0.01", abs(float(margrabe(mk, e1)["CORRELATION"]) * 99), 1e-3)
    caught("vega_1 without the -rho v2 term", abs(float(margrabe(mk, e1)["VEGA_1"] * r * v2 / (v1 - r * v2))), 1e-3)
    e = dict(mk, book=book, hedges=[e1, U1], targets=["CORRELATION", "DELTA_1"])
    errs = [
        (dict(e, targets=["CORRELATION"]), "E_INPUT", "two hedges, one target"),
        (dict(e, hedges=[{"instrument": "EXCHANGE", "quantity1": 1.0, "quantity2": 1.0}, U1]), "E_INPUT", "exchange option without expiry"),
        (dict(e, hedges=[e1, dict(U1, expiry_years=1.0)]), "E_INPUT", "underlying with an expiry"),
        (dict(e, correlation=1.2), "E_DOMAIN", "correlation above 1"),
        (dict(e, vol2=0.0), "E_DOMAIN", "zero volatility"),
        (dict(e, vol1=0.2, vol2=0.2, correlation=1.0), "E_DOMAIN", "zero spread volatility"),
        (dict(e, hedges=[e1, dict(e1)]), "E_SINGULAR", "the same option twice"),
        (dict(e, hedges=[e1, e2], targets=["CORRELATION", "VEGA_1"]), "E_SINGULAR", "exchange options alone: vega and correlation rows proportional (I-17)"),
        (dict(e, hedges=[e1, {"instrument": "CALL_1", "strike": 100.0}]), "E_INPUT", "vanilla without expiry"),
        (dict(e, hedges=[U1, U2], targets=["CORRELATION", "DELTA_1"]), "E_SINGULAR", "underlyings carry no correlation risk"),
        (dict(e, hedges=[U1] * 6, targets=list(CG) + ["DELTA_1"]), "E_LIMIT", "six hedges (limit 5)"),
    ]
    for inp, code, desc in errs:
        run_error(s, CO, corr_ref, inp, code, desc, ["hedge", "correlation"])
    return s, n_out, "QuantLib 1.44 AnalyticEuropeanMargrabeEngine delta1 and delta2, and BlackCalculator.vega (the Margrabe price as a Black price in the spread volatility, asserted equal to the engine NPV) for the vegas and correlation, then numpy solve; quantities and before-Greeks within root_finding"


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / W.FOLDER
    reg_p = HERE.parent / "outside_register_i.json"
    reg = json.loads(reg_p.read_text(encoding="utf-8"))
    for fn in (credit_suite, corr_suite):
        s, n_out, rule = fn()
        for c in s.cases:
            c["tags"].append("synthetic")
        s.write()
        reg[s.name] = {"counted": n_out, "total": len(s.cases), "rule": rule}
        note(f"{s.name}: {len(s.cases)} cases, outside {n_out}")
    common.GOLDEN = keep
    suites = {k: v for k, v in reg.items() if not k.startswith("_")}
    cnt, tot = sum(v["counted"] for v in suites.values()), sum(v["total"] for v in suites.values())
    reg["_stage"] = {"counted": cnt, "total": tot, "share": round(cnt / tot, 4), "floor": 0.60,
                     "note": "Stage I so far, error cases in the denominator (ruling I-2); the floor applies at release"}
    reg_p.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8", newline="\n")
    note(f"stage I outside so far: {cnt} of {tot} = {100 * cnt / tot:.1f}%")
    for m_, g in MUT:
        note(f"  mutant caught: {m_} (gap {g:.3e})")


if __name__ == "__main__":
    main()
