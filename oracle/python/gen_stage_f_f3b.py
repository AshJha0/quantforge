"""Stage F carry-over wave 2b, F3 sensitivities (ruling G-47): inflation01 of a zero-coupon inflation swap, dividend and
borrow sensitivity of a European equity option, correlation sensitivity of an exchange (Margrabe) option.

Values: 50-digit mpmath. Outside: QuantLib 1.44 `VanillaOption.dividendRho()` (AnalyticEuropeanEngine) for the dividend
and borrow cases; QuantLib `MargrabeOption` prices with a central correlation bump (arithmetic on library values, G-13)
for the correlation cases. inflation01 has no outside check (own closed form).

    cd oracle/python && uv run python -W ignore gen_stage_f_f3b.py
"""
import json
from pathlib import Path

import mpmath as mp
import QuantLib as ql

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_f_f3b.py"
SPEC = "specifications/06-risk/f3-sensitivities.md"
HERE = Path(__file__).resolve().parent
BP = mp.mpf("1e-4")
MUT = []
TODAY = ql.Date(10, 11, 2026)
ql.Settings.instance().evaluationDate = TODAY
DC = ql.Actual365Fixed()


def caught(name, gap, tol=1e-9):
    assert gap > tol, name
    MUT.append((name, gap))


def infl(inp, mut=None):
    N, n, K, z, P = (mp.mpf(inp[k]) for k in ("notional", "years", "fixed_rate", "market_rate", "discount_factor"))
    pv = lambda zz: N * P * ((1 + zz) ** n - (1 + K) ** n)  # noqa: E731
    d = N * P * n * (1 + z) ** (n - (0 if mut == "power" else 1))
    return {"pv": float(pv(z)), "inflation01": float(d * BP), "inflation01_bump": float(pv(z + BP) - pv(z))}


def N_(x):
    return mp.ncdf(x)


def bs(inp, q_extra=0, mut=None):
    S, K, T, r, v = (mp.mpf(inp[k]) for k in ("spot", "strike", "expiry_years", "rate", "vol"))
    y = mp.mpf(inp["dividend_yield"]) + mp.mpf(inp["borrow_rate"]) + q_extra
    d1 = (mp.log(S / K) + (r - y + v * v / 2) * T) / (v * mp.sqrt(T))
    d2 = d1 - v * mp.sqrt(T)
    if inp["option_type"] == "CALL":
        return S * mp.exp(-y * T) * N_(d1) - K * mp.exp(-r * T) * N_(d2), -T * S * mp.exp(-y * T) * N_(d1)
    return K * mp.exp(-r * T) * N_(-d2) - S * mp.exp(-y * T) * N_(-d1), T * S * mp.exp(-y * T) * N_(-d1)


def divborrow(inp, mut=None):
    price, dv = bs(inp)
    if mut == "borrow_sign":
        return {"price": float(price), "dividend01": float(dv * BP), "borrow01": float(-dv * BP)}
    return {"price": float(price), "dividend01": float(dv * BP), "borrow01": float(dv * BP)}


def ql_div(inp):
    days = round(inp["expiry_years"] * 365)
    ts = lambda r: ql.YieldTermStructureHandle(ql.FlatForward(TODAY, r, DC, ql.Continuous))  # noqa: E731
    proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(inp["spot"])), ts(inp["dividend_yield"] + inp["borrow_rate"]), ts(inp["rate"]),
                                        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(TODAY, ql.NullCalendar(), inp["vol"], DC)))
    o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if inp["option_type"] == "CALL" else ql.Option.Put, inp["strike"]), ql.EuropeanExercise(TODAY + days))
    o.setPricingEngine(ql.AnalyticEuropeanEngine(proc))
    return o.NPV(), o.dividendRho() * 1e-4


def margrabe(inp, mut=None):
    S1, S2, q1, q2, v1, v2, rho, T = (mp.mpf(inp[k]) for k in ("spot1", "spot2", "yield1", "yield2", "vol1", "vol2", "correlation", "expiry_years"))
    Q1, Q2 = (mp.mpf(inp[k]) for k in ("quantity1", "quantity2"))
    s = mp.sqrt(v1 * v1 + v2 * v2 - 2 * rho * v1 * v2)
    F1, F2 = Q1 * S1 * mp.exp(-q1 * T), Q2 * S2 * mp.exp(-q2 * T)
    d1 = (mp.log(F1 / F2) + s * s * T / 2) / (s * mp.sqrt(T))
    price = F1 * N_(d1) - F2 * N_(d1 - s * mp.sqrt(T))
    vega_s = F1 * mp.npdf(d1) * mp.sqrt(T)  # dV/ds
    ds_drho = -v1 * v2 / s * (-1 if mut == "sign" else 1)
    return {"price": float(price), "correlation01": float(vega_s * ds_drho * mp.mpf("0.01")), "spread_vol": float(s)}


def ql_marg(inp, rho):
    days = round(inp["expiry_years"] * 365)
    ts = lambda r: ql.YieldTermStructureHandle(ql.FlatForward(TODAY, r, DC, ql.Continuous))  # noqa: E731
    vol = lambda v: ql.BlackVolTermStructureHandle(ql.BlackConstantVol(TODAY, ql.NullCalendar(), v, DC))  # noqa: E731
    p1 = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(inp["spot1"])), ts(inp["yield1"]), ts(0.03), vol(inp["vol1"]))
    p2 = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(inp["spot2"])), ts(inp["yield2"]), ts(0.03), vol(inp["vol2"]))
    o = ql.MargrabeOption(int(inp["quantity1"]), int(inp["quantity2"]), ql.EuropeanExercise(TODAY + days))
    o.setPricingEngine(ql.AnalyticEuropeanMargrabeEngine(p1, p2, rho))
    return o.NPV()


def main():
    s = Suite("risk_f3b", SPEC, G)
    n_out = 0
    zi = dict(notional=1e7, years=10, fixed_rate=0.025, market_rate=0.027, discount_factor=0.75)
    for inp, d in ((zi, "10y ZCIS, receive inflation"), (dict(zi, years=1, market_rate=0.025), "1y at the money: pv 0"), (dict(zi, years=30, market_rate=0.03, discount_factor=0.4), "30y")):
        s.add("risk.sens.inflation01", inp, infl(inp), verified=["mpmath-50", "bump-1bp"], tags=["f3", "inflation01"],
              limit={"absolute": 1e-6, "relative": 1e-12, "reason": "closed form"}, description=d)
    caught("power n instead of n - 1", abs(infl(zi)["inflation01"] - infl(zi, "power")["inflation01"]))
    s.add("risk.sens.inflation01", dict(zi, discount_factor=0.0), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "f3"], description="discount factor 0")
    s.add("risk.sens.inflation01", dict(zi, market_rate=-1.0), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "f3"], description="1 + z <= 0")
    eq = dict(spot=100.0, strike=100.0, expiry_years=1.0, rate=0.03, dividend_yield=0.02, borrow_rate=0.005, vol=0.25, option_type="CALL")
    for inp, d in ((eq, "ATM call"), (dict(eq, option_type="PUT"), "ATM put"), (dict(eq, strike=120.0, expiry_years=2.0), "OTM 2y call"),
                   (dict(eq, borrow_rate=0.0), "no borrow"), (dict(eq, strike=80.0, expiry_years=0.6, option_type="PUT"), "OTM put 0.6y (219 days)")):
        out = divborrow(inp)
        qp, qd = ql_div(inp)
        ok = abs(qp - out["price"]) <= 1e-9 * max(1, abs(qp)) and abs(qd - out["dividend01"]) <= 1e-12 + 1e-9 * abs(qd)
        n_out += ok
        if not ok:
            note(f"  QL dividendRho differs: {qp} {qd} {out}")
        s.add("risk.sens.dividend_borrow", inp, out, verified=["mpmath-50"] + (["quantlib-1.44"] if ok else []), tags=["f3", "dividend_borrow"],
              limit={"absolute": 1e-12, "relative": 1e-9, "reason": "closed form"}, description=d)
    caught("borrow sign flipped", abs(divborrow(eq)["borrow01"] - divborrow(eq, "borrow_sign")["borrow01"]))
    s.add("risk.sens.dividend_borrow", dict(eq, vol=0.0), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "f3"], description="vol 0")
    s.add("risk.sens.dividend_borrow", dict(eq, option_type="DIGITAL"), error="E_INPUT", cls="date_and_convention", tags=["invalid", "f3"], description="unknown option_type")
    mg = dict(spot1=100.0, spot2=95.0, quantity1=1.0, quantity2=1.0, yield1=0.01, yield2=0.02, vol1=0.3, vol2=0.25, correlation=0.5, expiry_years=1.0)
    for inp, d in ((mg, "rho 0.5"), (dict(mg, correlation=-0.3), "rho -0.3"), (dict(mg, correlation=0.9, expiry_years=2.0), "rho 0.9, 2y"), (dict(mg, quantity2=2.0, spot2=50.0), "quantities 1 and 2")):
        out = margrabe(inp)
        h = 1e-4
        qp = ql_marg(inp, inp["correlation"])
        qd = (ql_marg(inp, inp["correlation"] + h) - ql_marg(inp, inp["correlation"] - h)) / (2 * h) * 0.01
        ok = abs(qp - out["price"]) <= 1e-9 * max(1, abs(qp)) and abs(qd - out["correlation01"]) <= 1e-9 + 1e-6 * abs(qd)
        n_out += ok
        if not ok:
            note(f"  QL Margrabe differs: {qp} {qd} {out}")
        s.add("risk.sens.correlation", inp, out, verified=["mpmath-50"] + (["quantlib-1.44-bump"] if ok else []), tags=["f3", "correlation"],
              limit={"absolute": 1e-12, "relative": 1e-9, "reason": "closed form"}, description=d)
    caught("correlation sign", abs(margrabe(mg)["correlation01"] - margrabe(mg, "sign")["correlation01"]))
    s.add("risk.sens.correlation", dict(mg, correlation=1.0, vol1=0.25), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "f3"], description="rho 1 with equal vols: spread vol 0")
    s.add("risk.sens.correlation", dict(mg, correlation=1.2), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "f3"], description="rho above 1")
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_f"
    s.write()
    common.GOLDEN = keep
    note(f"risk_f3b outside (QuantLib 1.44): {n_out} of {len(s.cases)}")
    (HERE.parent / "OUTSIDE_F3B.json").write_text(json.dumps({"suite": "risk_f3b", "counted": n_out, "total": len(s.cases),
        "rule": "dividendRho of AnalyticEuropeanEngine; Margrabe price and central correlation bump h = 1e-4 at 1e-6 relative"}, indent=1) + "\n", encoding="utf-8", newline="\n")
    for m, g in MUT:
        note(f"  mutant caught: {m} (gap {float(g):.3e})")


if __name__ == "__main__":
    main()
