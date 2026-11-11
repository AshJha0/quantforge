"""Stage I wave 3: cross-asset hedge, equity and rates (specifications/08-hedging/cross-asset-hedge.md, rulings I-20 on).

Every golden, error codes included, is the output of `xa_ref`. Risk factors are an equity move (`EQ01`, half the value
change between spot x 1.01 and spot x 0.99) and key-rate zero bumps (`KR01_k`, half the change between +1bp and -1bp
on pillar k of a linear-in-zero curve). The hedge is `hedge.qp.solve` (wave 1) on that risk matrix.

Outside: QuantLib 1.44 `ZeroCurve` (linear in continuous zero rates, ACT/365F) and `AnalyticEuropeanEngine` on a
`BlackScholesMertonProcess` that discounts on that curve; forwards and bonds from the curve's discount factors. The same
half-differences of QuantLib values, then the wave 1 objective solved by numpy `linalg.lstsq` on the weighted system.

    cd oracle/python && uv run python -W ignore gen_stage_i_w3.py
"""
import json
import math
from pathlib import Path

import mpmath as mp
import numpy as np
import QuantLib as ql

import gen_stage_i_w1 as W
from gen_stage_i_w1 import fail, finite_rule, run_error, RF
from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_i_w3.py"
SPEC = "specifications/08-hedging/cross-asset-hedge.md"
HERE = Path(__file__).resolve().parent
XA = "hedge.crossasset.solve"
KINDS = {"CALL": {"strike", "expiry_years"}, "PUT": {"strike", "expiry_years"}, "FORWARD": {"strike", "expiry_years"},
         "ZCB": {"expiry_years", "notional"}, "UNDERLYING": set()}
MUT = []


def zero(times, rates, t):
    """Linear in zero rate between pillars, flat before the first; t beyond the last is refused by validation."""
    if t <= times[0]:
        return rates[0]
    for i in range(len(times) - 1):
        if t <= times[i + 1]:
            u = (t - times[i]) / (times[i + 1] - times[i])
            return rates[i] + u * (rates[i + 1] - rates[i])
    raise AssertionError("beyond the last pillar")


def value(mk, ins, S, rates):
    kind = ins["instrument"]
    if kind == "UNDERLYING":
        return S
    T = mp.mpf(ins["expiry_years"])
    z = zero([mp.mpf(x) for x in mk["curve"]["times"]], rates, T)
    P = mp.exp(-z * T)
    q = mp.mpf(mk["dividend_yield"])
    if kind == "ZCB":
        return mp.mpf(ins["notional"]) * P
    K = mp.mpf(ins["strike"])
    if kind == "FORWARD":
        return S * mp.exp(-q * T) - K * P
    v = mp.mpf(mk["volatility"])
    d1 = (mp.log(S / K) + (z - q + v * v / 2) * T) / (v * mp.sqrt(T))
    d2 = d1 - v * mp.sqrt(T)
    if kind == "CALL":
        return S * mp.exp(-q * T) * mp.ncdf(d1) - K * P * mp.ncdf(d2)
    return K * P * mp.ncdf(-d2) - S * mp.exp(-q * T) * mp.ncdf(-d1)


def risk_row(mk, ins, valf):
    S = mp.mpf(mk["spot"])
    r0 = [mp.mpf(x) for x in mk["curve"]["zero_rates"]]
    out = [(valf(mk, ins, S * mp.mpf("1.01"), r0) - valf(mk, ins, S * mp.mpf("0.99"), r0)) / 2]
    bp = mp.mpf("1e-4")
    for k in range(len(r0)):
        up = [r + bp * (j == k) for j, r in enumerate(r0)]
        dn = [r - bp * (j == k) for j, r in enumerate(r0)]
        out.append((valf(mk, ins, S, up) - valf(mk, ins, S, dn)) / 2)
    return out


def xa_ref(inp):
    book, hed = inp["book"], inp["hedges"]
    cv = inp["curve"]
    if len(book) > 1000 or len(hed) > 200 or len(cv["times"]) > 100:
        fail("E_LIMIT")
    finite_rule(inp)
    tm, zr = cv["times"], cv["zero_rates"]
    P = len(tm)
    if P == 0 or len(zr) != P or any(b <= a for a, b in zip(tm, tm[1:])) or tm[0] <= 0:
        fail("E_INPUT", "curve")
    for x in book + hed:
        if x["instrument"] not in KINDS or set(x) - {"instrument", "quantity"} != KINDS[x["instrument"]]:
            fail("E_INPUT", "instrument keys")
    if not book or not hed or len(inp["weights"]) != P + 1:
        fail("E_INPUT", "book, hedges, weights")
    for x in book + hed:
        if "expiry_years" in x and x["expiry_years"] > tm[-1]:
            fail("E_INPUT", "maturity beyond the last curve pillar")
    if inp["spot"] <= 0 or inp["volatility"] <= 0 or any(w <= 0 for w in inp["weights"]) or inp.get("ridge", 0.0) < 0:
        fail("E_DOMAIN", "market or weights")
    for x in book + hed:
        if x.get("strike", 1.0) <= 0 or x.get("expiry_years", 1.0) <= 0 or x.get("notional", 1.0) <= 0:
            fail("E_DOMAIN", "strike or expiry")
    rows = [risk_row(inp, h, value) for h in hed]
    bvec = [sum(mp.mpf(p["quantity"]) * r for p, r in zip(book, col)) for col in zip(*[risk_row(inp, p, value) for p in book])]
    a = [[float(rows[j][f]) for j in range(len(hed))] for f in range(P + 1)]
    q = {"a": a, "b": [float(v) for v in bvec], "weights": inp["weights"]}
    if "ridge" in inp:
        q["ridge"] = inp["ridge"]
    x, r, obj, rank = W.qp_core(q)  # raises E_SINGULAR under the wave 1 rule (I-3)
    # residual from the 50-digit risks, not the rounded matrix
    res = [bvec[f] + sum(mp.mpf(x[j]) * rows[j][f] for j in range(len(hed))) for f in range(P + 1)]
    return {"positions": [float(v) for v in x], "book_risk": [float(v) for v in bvec], "residual_risk": [float(v) for v in res],
            "objective": float(sum(mp.mpf(w) * v * v for w, v in zip(inp["weights"], res)) + mp.mpf(inp.get("ridge", 0.0)) * sum(mp.mpf(v) ** 2 for v in x))}


def ql_value(mk, ins, S, rates):
    kind = ins["instrument"]
    if kind == "UNDERLYING":
        return float(S)
    dc, today = ql.Actual365Fixed(), ql.Date(11, 11, 2026)
    ql.Settings.instance().evaluationDate = today
    days = [round(t * 365) for t in mk["curve"]["times"]]
    assert all(abs(d - t * 365) < 1e-9 for d, t in zip(days, mk["curve"]["times"]))
    rates = [float(r) for r in rates]
    zc = ql.ZeroCurve([today] + [today + d for d in days], [rates[0]] + rates, dc)
    yh = ql.YieldTermStructureHandle(zc)
    T = ins["expiry_years"]
    nd = round(T * 365)
    assert abs(nd - T * 365) < 1e-9
    P = zc.discount(today + nd)
    if kind == "ZCB":
        return ins["notional"] * P
    if kind == "FORWARD":
        return float(S) * math.exp(-mk["dividend_yield"] * T) - ins["strike"] * P
    proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(float(S))), ql.YieldTermStructureHandle(ql.FlatForward(today, mk["dividend_yield"], dc, ql.Continuous)),
                                        yh, ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.NullCalendar(), mk["volatility"], dc)))
    o = ql.EuropeanOption(ql.PlainVanillaPayoff(ql.Option.Call if kind == "CALL" else ql.Option.Put, ins["strike"]), ql.EuropeanExercise(today + nd))
    o.setPricingEngine(ql.AnalyticEuropeanEngine(proc))
    return o.NPV()


def xa_outside(inp, out):
    rows = np.array([[float(v) for v in risk_row(inp, h, ql_value)] for h in inp["hedges"]]).T
    bq = np.zeros(rows.shape[0])
    for p in inp["book"]:
        bq += p["quantity"] * np.array([float(v) for v in risk_row(inp, p, ql_value)])
    sw = np.sqrt(np.array(inp["weights"]))
    A, b = rows * sw[:, None], bq * sw
    if inp.get("ridge"):
        A = np.vstack([A, math.sqrt(inp["ridge"]) * np.eye(A.shape[1])])
        b = np.concatenate([b, np.zeros(A.shape[1])])
    x = np.linalg.lstsq(A, -b, rcond=None)[0]
    tol = lambda e: 1e-8 + 1e-9 * abs(e)  # noqa: E731
    ok = all(abs(p - e) <= tol(e) for p, e in zip(x, out["positions"]))
    ok &= all(abs(p - e) <= tol(e) for p, e in zip(bq, out["book_risk"]))
    return bool(ok)


def suite():
    s = Suite("hedgexa_i", SPEC, G)
    cv = {"times": [365 / 365, 730 / 365, 1825 / 365, 3650 / 365], "zero_rates": [0.030, 0.032, 0.035, 0.038]}
    mk = dict(spot=4000.0, dividend_yield=0.015, volatility=0.18, curve=cv)
    C = lambda K, d: {"instrument": "CALL", "strike": K, "expiry_years": d / 365}  # noqa: E731
    Pt = lambda K, d: {"instrument": "PUT", "strike": K, "expiry_years": d / 365}  # noqa: E731
    F = lambda K, d: {"instrument": "FORWARD", "strike": K, "expiry_years": d / 365}  # noqa: E731
    Z = lambda d, n=1e6: {"instrument": "ZCB", "expiry_years": d / 365, "notional": n}  # noqa: E731
    U = {"instrument": "UNDERLYING"}
    book = [dict(C(4200.0, 547), quantity=-50.0), dict(Pt(3600.0, 1095), quantity=30.0), dict(Z(2555, 2e6), quantity=1.0)]
    w5 = [1.0] * 5
    cases = [
        ("equity and four key rates with a future and four bonds (exact)", dict(mk, book=book, hedges=[F(4000.0, 365), Z(365), Z(730), Z(1825), Z(3650)], weights=w5)),
        ("equity with the underlying, rates with two bonds (least squares)", dict(mk, book=book, hedges=[U, Z(730), Z(3650)], weights=w5)),
        ("forward carries rate risk: futures only", dict(mk, book=book, hedges=[F(4000.0, 365), F(4000.0, 1825)], weights=w5)),
        ("equity weighted 100 times the rates", dict(mk, book=book, hedges=[F(4000.0, 365), Z(1825)], weights=[100.0, 1.0, 1.0, 1.0, 1.0])),
        ("rates-only book hedged with bonds; equity row is zero", dict(mk, book=[dict(Z(1460), quantity=1.0), dict(Z(2920), quantity=-0.5)], hedges=[Z(730), Z(1825), Z(3650)], weights=w5)),
        ("ridge 10 shrinks a near-duplicate bond pair", dict(mk, book=book, hedges=[Z(1825), Z(1826), U], weights=w5, ridge=10.0)),
        ("maturity between pillars splits its key-rate risk", dict(mk, book=[dict(C(4000.0, 1277), quantity=-100.0)], hedges=[U, Z(730), Z(1825)], weights=w5)),
        ("maturity before the first pillar loads on pillar 1 only", dict(mk, book=[dict(F(3900.0, 182), quantity=10.0)], hedges=[U, Z(365)], weights=w5)),
        ("inverted curve", dict(mk, curve={"times": cv["times"], "zero_rates": [0.05, 0.045, 0.04, 0.037]}, book=book, hedges=[F(4000.0, 365), Z(730), Z(3650)], weights=w5)),
    ]
    n_out = 0
    for desc, inp in cases:
        out = xa_ref(inp)
        ok = xa_outside(inp, out)
        n_out += ok
        if not ok:
            note(f"  hedgexa not counted: {desc}")
        lim = {"absolute": 1e-8, "relative": 1e-9, "reason": "risks are half-differences of prices of size up to 1e6; least-squares solve"}
        s.add(XA, inp, out, cls=RF, limit=lim, verified=["mpmath-50", "wave-1-qp"] + (["quantlib-1.44-zerocurve-analytic-european", "numpy-2.5-lstsq"] if ok else []),
              tags=["hedge", "cross-asset"], description=desc)
    # self-checks: exact square hedge leaves no residual; rates-only book has no equity risk; short maturity only on pillar 1
    assert max(abs(v) for v in s.cases[0]["expected"]["outputs"]["residual_risk"]) < 1e-6
    assert s.cases[4]["expected"]["outputs"]["book_risk"][0] == 0.0
    assert all(v == 0.0 for v in s.cases[7]["expected"]["outputs"]["book_risk"][2:])
    # mutants
    def flat_ext(mk_, ins, S, rates):  # forward priced without the dividend yield
        return value(dict(mk_, dividend_yield=0.0), ins, S, rates)
    a = risk_row(mk, F(4000.0, 1825), value)[0]
    b = risk_row(mk, F(4000.0, 1825), flat_ext)[0]
    MUT.append(("forward without the dividend yield", float(abs(a - b))))
    assert abs(a - b) > 1e-6
    e = dict(mk, book=book, hedges=[U, Z(730)], weights=w5)
    errs = [
        (dict(e, weights=[1.0] * 4), "E_INPUT", "weights shorter than 1 + pillars"),
        (dict(e, curve={"times": [1.0, 1.0, 5.0, 10.0], "zero_rates": cv["zero_rates"]}), "E_INPUT", "curve times not increasing"),
        (dict(e, hedges=[U, Z(4000)]), "E_INPUT", "bond beyond the last pillar"),
        (dict(e, hedges=[U, {"instrument": "ZCB", "expiry_years": 2.0, "notional": 1e6, "strike": 1.0}]), "E_INPUT", "bond with a strike"),
        (dict(e, volatility=0.0), "E_DOMAIN", "zero volatility"),
        (dict(e, weights=[1.0, 1.0, 0.0, 1.0, 1.0]), "E_DOMAIN", "zero weight"),
        (dict(e, hedges=[U, dict(U)]), "E_SINGULAR", "the underlying twice"),
        (dict(e, hedges=[Z(730), Z(730)]), "E_SINGULAR", "the same bond twice"),
    ]
    for inp, code, desc in errs:
        run_error(s, XA, xa_ref, inp, code, desc, ["hedge", "cross-asset"])
    return s, n_out


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / W.FOLDER
    s, n_out = suite()
    for c in s.cases:
        c["tags"].append("synthetic")
    s.write()
    common.GOLDEN = keep
    reg_p = HERE.parent / "outside_register_i.json"
    reg = json.loads(reg_p.read_text(encoding="utf-8"))
    reg[s.name] = {"counted": n_out, "total": len(s.cases), "rule": "QuantLib 1.44 ZeroCurve (linear zero, continuous, ACT/365F) and AnalyticEuropeanEngine values, the spec's half-differences of them, numpy lstsq on the weighted system; positions and book risk within the case limit"}
    suites = {k: v for k, v in reg.items() if not k.startswith("_")}
    cnt, tot = sum(v["counted"] for v in suites.values()), sum(v["total"] for v in suites.values())
    reg["_stage"] = {"counted": cnt, "total": tot, "share": round(cnt / tot, 4), "floor": 0.60,
                     "note": "Stage I so far, error cases in the denominator (ruling I-2); the floor applies at release"}
    reg_p.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8", newline="\n")
    note(f"{s.name}: {len(s.cases)} cases, outside {n_out}; stage I outside so far: {cnt} of {tot} = {100 * cnt / tot:.1f}%")
    for m_, g in MUT:
        note(f"  mutant caught: {m_} (gap {g:.3e})")


if __name__ == "__main__":
    main()
