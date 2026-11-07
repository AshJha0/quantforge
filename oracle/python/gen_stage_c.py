"""Stage C golden cases: equity forward, Black models, smile, surface, SABR, Greeks, use case 3.

All market data is synthetic. Each suite checks results against QuantLib or an analytic route, and stops if a tolerance
would let a named wrong convention through. Nothing here may depend on maths-library rounding or on a solver's path:
guards below stop the run if a boolean sits near its threshold, a vol is ill-conditioned, or a fit is not unique.
"""
import math
from datetime import date, timedelta

import numpy as np
import QuantLib as ql

from qf_oracle import common
from qf_oracle.common import Suite, note
from qf_oracle import vol as V

G = "oracle/python/gen_stage_c.py"
E, A, R, I, NS = "date_and_convention", "simple_analytic", "root_finding", "interpolation", "numerical_scheme"
SYN = "synthetic"
AS_OF = date(2026, 11, 6)
QLV = "quantlib-1.44"
FITLIM = {"absolute": 1e-6, "relative": 0.0, "reason": "stage-c-targets: languages use different solvers; minimum checked unique from several starts"}
BUMPLIM = {"absolute": 1e-4, "relative": 1e-6, "reason": "volga divides rounding of about 1e-15 by a bump squared"}
MUTANTS = []
Q = lambda d: ql.Date(d.day, d.month, d.year)  # noqa: E731


def S(name, spec):
    return Suite(name, f"specifications/{spec}", G)


def write(s):
    keep = common.GOLDEN
    for c in s.cases:
        if SYN not in c["tags"]:
            c["tags"].append(SYN)
    common.GOLDEN = keep.parent / "stage_c"
    s.write()
    common.GOLDEN = keep
    note(f"{s.name}: {len(s.cases)} cases")


def caught(suite, name, gap, tol):
    assert gap > tol, f"{suite}: mutant '{name}' is not caught: gap {gap:.3e}, tolerance {tol:.3e}"
    MUTANTS.append((suite, name, gap))


def atol(x):  # simple_analytic limit at x
    return 1e-12 + 1e-10 * abs(x)


def flat(r, days=7300):
    d = AS_OF + timedelta(days)
    return {"as_of": str(AS_OF), "interpolation": "LOG_LINEAR_DF", "pillars": [{"date": str(d), "discount_factor": math.exp(-r * days / 365)}]}


def curve_df(r, d):
    return math.exp(-r * (d - AS_OF).days / 365)


def jdivs(divs):
    return [{"ex_date": str(d), "amount": a} for d, a in divs]


def tdivs(divs):
    return [((d - AS_OF).days / 365, a) for d, a in divs]


def ql_eq(S0, r_curve, q_rate, K, ex, t, v, divs):
    """QuantLib dividend engine. It discounts dividends on its risk-free curve, so that curve is given the carry rate."""
    ql.Settings.instance().evaluationDate = Q(AS_OF)
    dc = ql.Actual365Fixed()
    rf = ql.YieldTermStructureHandle(ql.FlatForward(Q(AS_OF), r_curve, dc))
    dv = ql.YieldTermStructureHandle(ql.FlatForward(Q(AS_OF), q_rate, dc))
    vt = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(Q(AS_OF), ql.NullCalendar(), v, dc))
    pr = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(S0)), dv, rf, vt)
    o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if t == "CALL" else ql.Option.Put, K), ql.EuropeanExercise(Q(ex)))
    o.setPricingEngine(ql.AnalyticDividendEuropeanEngine(pr, ql.DividendVector([Q(d) for d, _ in divs], [a for _, a in divs])))
    return o


def equity_forward():
    s = S("equity_forward", "02-curves/equity-forward.md")
    op = "eq.forward.flat"
    base = dict(spot=100.0, rate=.04, borrow=.05, expiry_years=1.0, dividends=[{"time_years": .5, "amount": 2.0}])
    tr = V.fwd_flat(100, .04, .05, 1, [(.5, 2)])
    wr = V.fwd_wrong(100, .04, .05, 1, [(.5, 2)])
    assert abs(tr - 97.015) < 6e-4 and abs(wr - 97.064) < 6e-4 and abs(V.fwd_rolled(100, .04, .05, 1, [(.5, 2)]) - tr) < 1e-11
    s.add(op, base, {"forward": tr}, cls=A, verified=["analytic-rolled", "plan-section-8"], tags=["wrong-convention"], description="plan check case: 97.015 true, 97.064 wrong")
    caught("equity_forward", "dividends discounted on r, not r-b (97.064)", abs(tr - wr), atol(tr))
    for S0, r, b, T, dv in ((100., .03, 0., 2., [(.5, 1.), (1.5, 1.)]), (250., .01, .002, .75, [(.25, 3.), (.75, 3.), (.8, 3.)]), (80., -.005, .01, 3., []), (100., .05, -.01, 1., [(0., 5.), (1., 2.)])):
        ins = dict(spot=S0, rate=r, borrow=b, expiry_years=T, dividends=[{"time_years": t, "amount": a} for t, a in dv])
        if dv and dv[0][0] == 0.:
            ins["dividends"][0]["time_years"] = 1e-9
            dv = [(1e-9, 5.), (1., 2.)]
        f = V.fwd_flat(S0, r, b, T, dv)
        assert abs(f - V.fwd_rolled(S0, r, b, T, dv)) < 1e-10
        s.add(op, ins, {"forward": f}, cls=A, verified=["analytic-rolled"])
    for ins, code in ((dict(base, spot=0.0), "E_DOMAIN"), (dict(base, expiry_years=-1.0), "E_DOMAIN"), (dict(base, dividends=[{"time_years": .5, "amount": -1.0}]), "E_DOMAIN"),
                      (dict(base, dividends=[{"time_years": .5, "amount": 1.0}, {"time_years": .5, "amount": 1.0}]), "E_INPUT"), (dict(base, dividends=[{"time_years": .5, "amount": 200.0}]), "E_DOMAIN")):
        s.add(op, ins, error=code, cls=E, tags=["invalid"])
    op = "eq.forward.outright"
    d1, d2, d3 = AS_OF + timedelta(73), AS_OF + timedelta(146), AS_OF + timedelta(365)
    b0 = dict(spot=100.0, as_of=str(AS_OF), expiry=str(d3), funding_curve=flat(.04), borrow_curve=flat(.01), dividends=jdivs([(d1, 1.5), (d2, 1.5), (d3, 1.0)]))
    C = lambda d: curve_df(.04, d) / curve_df(.01, d)  # noqa: E731
    pv = 1.5 * C(d1) + 1.5 * C(d2) + C(d3)
    f = (100 - pv) / C(d3)
    assert abs(f - V.fwd_flat(100, .04, .01, 1, tdivs([(d1, 1.5), (d2, 1.5), (d3, 1.0)]))) < 1e-10
    s.add(op, b0, {"forward": f, "discount_factor": curve_df(.04, d3), "carry_factor": C(d3), "pv_dividends": pv}, cls=A, verified=["analytic-rolled"], tags=["dividend-on-expiry"])
    caught("equity_forward", "dividend on expiry dropped", 1.0, atol(f))
    caught("equity_forward", "borrow ignored", abs(f - (100 - sum(a * curve_df(.04, d) for d, a in [(d1, 1.5), (d2, 1.5), (d3, 1.)])) / curve_df(.04, d3)), atol(f))
    caught("equity_forward", "ACT/360 time", abs(f - V.fwd_flat(100, .04, .01, 365 / 360, [(73 / 360, 1.5), (146 / 360, 1.5), (1.0139, 1.)])), atol(f))
    past = dict(b0, dividends=jdivs([(AS_OF, 9.0), (d3 + timedelta(1), 9.0)]))
    s.add(op, past, {"forward": 100 / C(d3), "discount_factor": curve_df(.04, d3), "carry_factor": C(d3), "pv_dividends": 0.0}, cls=A, verified=["hand"], tags=["boundary"], description="dividends on as_of and after expiry are ignored")
    s.add(op, dict(b0, borrow_curve=None, dividends=[]), {"forward": 100 / curve_df(.04, d3), "discount_factor": curve_df(.04, d3), "carry_factor": curve_df(.04, d3), "pv_dividends": 0.0}, cls=A, verified=["hand"])
    s.add(op, dict(b0, expiry=str(AS_OF), dividends=[]), {"forward": 100.0, "discount_factor": 1.0, "carry_factor": 1.0, "pv_dividends": 0.0}, cls=A, verified=["hand"], tags=["boundary"])
    s.add(op, dict(b0, expiry=str(AS_OF - timedelta(1))), error="E_DATE_ORDER", cls=E, tags=["invalid"])
    s.add(op, dict(b0, borrow_curve=dict(flat(.01), as_of=str(AS_OF + timedelta(1)))), error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, dict(b0, dividends=[{"ex_date": str(d1 + timedelta(i)), "amount": .01} for i in range(101)]), error="E_LIMIT", cls=E, tags=["invalid"])
    s.add(op, dict(b0, dividends=jdivs([(d2, 1.0), (d1, 1.0)])), error="E_INPUT", cls=E, tags=["invalid"])
    op = "eq.forward.parity"
    Fv, D = 102.5, .97
    def quotes(ks, sp=.1, skew=0.0):
        out = []
        for i, k in enumerate(ks):
            c = V.black("CALL", Fv, k, .2, 1, D)
            p = V.black("PUT", Fv, k, .2, 1, D)
            e = skew * (-1) ** i
            out.append({"strike": k, "call_bid": c - sp + e, "call_ask": c + sp + e, "put_bid": p - sp, "put_ask": p + sp})
        return out
    ks = [80., 90., 100., 110., 120.]
    s.add(op, {"quotes": quotes(ks), "discount_factor": D}, {"forward": Fv, "discount_factor": D, "max_residual": 0.0, "outside_spread": []}, cls=I, limit={"absolute": 1e-9, "relative": 1e-10, "reason": "residual is a rounding-sized number"}, verified=["analytic"])
    s.add(op, {"quotes": quotes(ks), "discount_factor": None}, {"forward": Fv, "discount_factor": D, "max_residual": 0.0, "outside_spread": []}, cls=I, limit={"absolute": 1e-9, "relative": 1e-10, "reason": "residual is a rounding-sized number"}, verified=["analytic", "numpy"])
    q = quotes(ks, .1, .4)
    y = np.array([(x["call_bid"] + x["call_ask"]) / 2 - (x["put_bid"] + x["put_ask"]) / 2 for x in q])
    Kx = np.array(ks)
    sl, ic = np.polyfit(Kx, y, 1)
    Dh, Fh = -sl, ic / -sl
    res = y - Dh * (Fh - Kx)
    outs = [k for k, x in zip(ks, q) if not x["call_bid"] - x["put_ask"] <= Dh * (Fh - k) <= x["call_ask"] - x["put_bid"]]
    gapm = min(min(abs(Dh * (Fh - k) - (x["call_bid"] - x["put_ask"])), abs(Dh * (Fh - k) - (x["call_ask"] - x["put_bid"]))) for k, x in zip(ks, q))
    assert gapm > 1e-3 and outs
    s.add(op, {"quotes": q, "discount_factor": None}, {"forward": float(Fh), "discount_factor": float(Dh), "max_residual": float(np.max(np.abs(res))), "outside_spread": outs}, cls=I, verified=["numpy"], tags=["noisy"])
    F2 = float(np.mean(Kx + y / D))
    caught("equity_forward", "parity mean forgets the discount factor", abs(F2 - float(np.mean(Kx + y))), 1e-8)
    s.add(op, {"quotes": [], "discount_factor": D}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"quotes": quotes([100.]), "discount_factor": None}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"quotes": quotes([100., 90.]), "discount_factor": D}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"quotes": quotes([100.]), "discount_factor": 0.0}, error="E_DOMAIN", cls=E, tags=["invalid"])
    bad = quotes([100.])
    bad[0]["call_bid"] = bad[0]["call_ask"] + 1
    s.add(op, {"quotes": bad, "discount_factor": D}, error="E_INPUT", cls=E, tags=["invalid"])
    write(s)


def pinputs(model, t, K, T, **kw):
    return dict(model=model, option_type=t, strike=K, expiry_years=T, **kw)


GRID = [("CALL", 100., 100., .2, 1.), ("PUT", 100., 100., .2, 1.), ("CALL", 100., 130., .25, .5), ("PUT", 100., 70., .35, 2.), ("CALL", 50., 40., .6, 3.), ("PUT", 1500., 1650., .15, .25), ("CALL", 100., 105., .05, 5.)]


def black():
    s = S("black", "05-volatility/black-models.md")
    pr, im = "vol.option.price", "vol.option.implied"
    bq = dict(forward=100.0, discount_factor=1.0)
    for t, F, K, v, T in GRID:
        D = math.exp(-.03 * T)
        p = V.black(t, F, K, v, T, D)
        assert abs(ql.blackFormula(ql.Option.Call if t == "CALL" else ql.Option.Put, K, F, v * math.sqrt(T), D) - p) < 1e-10
        s.add(pr, pinputs("BLACK_76", t, K, T, forward=F, discount_factor=D, vol=v), {"price": p, "forward": F}, cls=A, verified=[QLV])
        vega = V.greeks("BLACK_76", t, K, v, T, F=F, D=D)["vega"]
        assert vega >= 1e-3 * max(p, 1)
        s.add(im, pinputs("BLACK_76", t, K, T, forward=F, discount_factor=D, price=p), {"vol": v}, cls=R, verified=[QLV, "known-truth"])
        Sx, r, q = F, .03, .01
        Fb = Sx * math.exp((r - q) * T)
        pb = V.black(t, Fb, K, v, T, D)
        s.add(pr, pinputs("BLACK_SCHOLES", t, K, T, spot=Sx, rate=r, **{"yield": q}, vol=v), {"price": pb, "forward": Fb}, cls=A, verified=["analytic"])
        s.add(im, pinputs("BLACK_SCHOLES", t, K, T, spot=Sx, rate=r, **{"yield": q}, price=pb), {"vol": v}, cls=R, verified=["known-truth"])
        vn = v * F
        pn = V.bachelier(t, F, K, vn, T, D)
        assert abs(ql.bachelierBlackFormula(ql.Option.Call if t == "CALL" else ql.Option.Put, K, F, vn * math.sqrt(T), D) - pn) < 1e-9
        s.add(pr, pinputs("BACHELIER", t, K, T, forward=F, discount_factor=D, vol=vn), {"price": pn, "forward": F}, cls=A, verified=[QLV])
        s.add(im, pinputs("BACHELIER", t, K, T, forward=F, discount_factor=D, price=pn), {"vol": vn}, cls=R, limit={"absolute": 1e-9, "relative": 1e-10, "reason": "normal vol in price units"}, verified=[QLV, "known-truth"])
    s.add(pr, pinputs("BACHELIER", "CALL", -.01, 2., forward=-.005, discount_factor=.99, vol=.008), {"price": V.bachelier("CALL", -.005, -.01, .008, 2, .99), "forward": -.005}, cls=A, verified=["analytic"], tags=["negative-rates"])
    p = V.black("CALL", .01 + .03, -.01 + .03, .2, 2, .98)
    s.add(pr, pinputs("BLACK_76", "CALL", -.01, 2., forward=.01, discount_factor=.98, shift=.03, vol=.2), {"price": p, "forward": .01}, cls=A, verified=[QLV], tags=["shift"])
    assert abs(ql.blackFormula(ql.Option.Call, -.01, .01, .2 * math.sqrt(2), .98, .03) - p) < 1e-12
    for t, x in (("CALL", 10.0), ("PUT", 0.0)):
        s.add(pr, pinputs("BLACK_76", t, 90., 1., **bq, vol=0.0), {"price": x, "forward": 100.0}, cls=A, verified=["hand"], tags=["boundary", "zero-vol"])
        s.add(pr, pinputs("BLACK_76", t, 90., 0., **bq, vol=.2), {"price": x, "forward": 100.0}, cls=A, verified=["hand"], tags=["boundary", "expiry"])
    s.add(im, pinputs("BLACK_76", "CALL", 90., 1., **bq, price=10.0), {"vol": 0.0}, cls=R, verified=["hand"], tags=["boundary"])
    for ins in (pinputs("BLACK_76", "CALL", 90., 1., **bq, price=9.0), pinputs("BLACK_76", "CALL", 90., 1., **bq, price=100.0), pinputs("BLACK_76", "PUT", 90., 1., **bq, price=90.0), pinputs("BLACK_76", "CALL", 90., 0., **bq, price=11.0),
                pinputs("BACHELIER", "CALL", 90., 1., **bq, price=9.0)):
        s.add(im, ins, error="E_DOMAIN", cls=E, tags=["invalid", "no-arbitrage"])
    for ins in (pinputs("BLACK_76", "CALL", 0.0, 1., **bq, vol=.2), pinputs("BLACK_76", "CALL", 90., -1., **bq, vol=.2), pinputs("BLACK_76", "CALL", 90., 1., **bq, vol=-.2), pinputs("BLACK_76", "CALL", 90., 1., forward=-1.0, discount_factor=1.0, vol=.2), pinputs("BLACK_76", "CALL", 90., 1., forward=100.0, discount_factor=0.0, vol=.2)):
        s.add(pr, ins, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(pr, pinputs("BLACK_76", "CALL", 90., 1., spot=100.0, discount_factor=1.0, vol=.2), error="E_SCHEMA", cls=E, tags=["invalid"])
    s.add(pr, pinputs("BACHELIER", "CALL", 90., 1., **bq, shift=.1, vol=.2), error="E_SCHEMA", cls=E, tags=["invalid"])
    write(s)
    s = S("black_deep", "05-volatility/black-models.md")
    ql.Settings.instance().evaluationDate = Q(AS_OF)
    # parity and QuantLib implied routes on a wider grid, and mutants
    g = {"undiscounted": 0, "swap": 0, "sqrtT": 0, "lognormal-as-normal": 0}
    for F in (60., 100., 160.):
        for m in (.8, 1., 1.25):
            for T in (.1, 1., 4.):
                for v in (.1, .3, .7):
                    K, D = F * m, math.exp(-.02 * T)
                    c, p = V.black("CALL", F, K, v, T, D), V.black("PUT", F, K, v, T, D)
                    assert abs(c - p - D * (F - K)) < 1e-10
                    s.add("vol.option.price", pinputs("BLACK_76", "CALL", K, T, forward=F, discount_factor=D, vol=v), {"price": c, "forward": F}, cls=A, verified=[QLV, "put-call-parity"])
                    vg = V.greeks("BLACK_76", "CALL", K, v, T, F=F, D=D)["vega"]
                    if vg >= 1e-3 * max(c, 1):
                        got = ql.blackFormulaImpliedStdDev(ql.Option.Call, K, F, c, D, 0.0, 0.25, 1e-11, 500) / math.sqrt(T)
                        assert abs(got - v) < 1e-6
                        s.add("vol.option.implied", pinputs("BLACK_76", "CALL", K, T, forward=F, discount_factor=D, price=c), {"vol": v}, cls=R, verified=[QLV, "known-truth"])
                    if m == 1. and F == 100. and T == 1.:
                        g["undiscounted"] = max(g["undiscounted"], abs(c / D - c))
                        g["sqrtT"] = max(g["sqrtT"], abs(V.black("CALL", F, K, v * math.sqrt(T + .5) / math.sqrt(T), T, D) - c))
                        g["lognormal-as-normal"] = max(g["lognormal-as-normal"], abs(V.bachelier("CALL", F, K, v, T, D) - c))
                    if m != 1:
                        g["swap"] = max(g["swap"], abs(p - c))
    caught("black_deep", "price not discounted", g["undiscounted"], atol(10))
    caught("black_deep", "CALL and PUT swapped", g["swap"], atol(10))
    caught("black_deep", "time scaled wrongly", g["sqrtT"], atol(10))
    caught("black_deep", "lognormal vol fed to Bachelier", g["lognormal-as-normal"], atol(10))
    # QuantLib AnalyticDividendEuropeanEngine at zero borrow, and with the carry curve on a borrow
    d3 = AS_OF + timedelta(365)
    divs = [(AS_OF + timedelta(90), 1.0), (AS_OF + timedelta(270), 1.0)]
    write(s)


def eq_inputs(S0, r, b, ex, divs, t, K, v, q, side):
    return dict(spot=S0, as_of=str(AS_OF), expiry=str(ex), funding_curve=flat(r), borrow_curve=flat(b) if b else None, dividends=jdivs(divs), option_type=t, strike=K, vol=v, quantity=q, side=side, currency="USD")


def eq_outputs(S0, r, b, ex, divs, t, K, v, q, side):
    T = (ex - AS_OF).days / 365
    sign = 1 if side == "BUY" else -1
    F = V.fwd_flat(S0, r, b, T, tdivs(divs))
    D, C = math.exp(-r * T), math.exp(-(r - b) * T)
    gk = V.greeks("BLACK_76", t, K, v, T, F=F, D=D)
    return {"valuation": {"pv": sign * q * gk["price"], "currency": "USD", "model": "BLACK_76_EQUITY", "data_version": None, "conventions": "EQUITY_FORWARD", "as_of": str(AS_OF)},
            "forward": F, "delta": sign * q * gk["delta"] / C, "gamma": sign * q * gk["gamma"] / C ** 2, "vega": sign * q * gk["vega"]}


def equity_deep():
    s = S("equity_forward_deep", "06-risk/vol-greeks.md")
    op = "vol.equity.price"
    n_b = n_q = 0
    worst = 0.0
    for S0, r, b, days, divs, t, K, v in ((100., .03, 0., 365, [(90, 1.), (270, 1.)], "CALL", 100., .2), (100., .03, 0., 365, [(90, 1.), (270, 1.)], "PUT", 95., .25), (250., .01, 0., 548, [(100, 4.), (280, 4.), (460, 4.)], "CALL", 260., .3),
                                          (100., .04, .05, 365, [(182, 2.)], "CALL", 100., .2), (100., .04, .05, 365, [(182, 2.)], "PUT", 90., .3), (100., .05, .02, 730, [(180, 1.5), (360, 1.5), (540, 1.5)], "CALL", 105., .22), (50., .02, .01, 200, [], "PUT", 50., .4)):
        ex = AS_OF + timedelta(days)
        dv = [(AS_OF + timedelta(x), a) for x, a in divs]
        o = eq_outputs(S0, r, b, ex, dv, t, K, v, 1.0, "BUY")
        # Second route: carry rate as QuantLib's risk-free curve, PV rescaled from C(T) to D(T).
        T = days / 365
        scale = math.exp(-r * T) / math.exp(-(r - b) * T)
        if dv:
            qo = ql_eq(S0, r - b, 0.0, K, ex, t, v, dv)
            assert abs(qo.NPV() * scale - o["valuation"]["pv"]) < 1e-9, (qo.NPV() * scale, o["valuation"]["pv"])
            assert abs(qo.delta() * scale - o["delta"]) < 1e-9 and abs(qo.gamma() * scale - o["gamma"]) < 1e-9 and abs(qo.vega() * scale - o["vega"]) < 1e-8
            n_q += 1
            ver = [QLV, "analytic"]
        else:
            ver = ["analytic"]
        s.add(op, eq_inputs(S0, r, b, ex, dv, t, K, v, 1.0, "BUY"), o, cls=A, verified=ver, tags=["dividends"] if dv else [])
        if b and dv:
            shipped = ql_eq(S0, r, b, K, ex, t, v, dv)  # QuantLib as shipped carries dividends on r-b too: an outside check of plan section 8
            assert abs(shipped.NPV() - o["valuation"]["pv"]) < 1e-9
            wrongF = V.fwd_wrong(S0, r, b, T, tdivs(dv))
            worst = max(worst, abs(V.black(t, wrongF, K, v, T, math.exp(-r * T)) - o["valuation"]["pv"]))
            n_b += 1
    caught("equity_forward_deep", "dividends discounted on r in the option forward", worst, atol(10))
    note(f"equity_forward_deep: {n_q} QuantLib checks, {n_b} with a borrow on the shipped engine; the wrong forward misses by up to {worst:.3e}")
    ex = AS_OF + timedelta(365)
    dv = [(AS_OF + timedelta(100), 1.0)]
    o = eq_outputs(100., .03, .01, ex, dv, "CALL", 100., .2, 250.0, "SELL")
    s.add(op, dict(eq_inputs(100., .03, .01, ex, dv, "CALL", 100., .2, 250.0, "SELL")), o, cls=A, verified=["analytic"])
    i = eq_inputs(100., .03, .01, ex, dv, "CALL", 100., .2, 1.0, "BUY")
    o1 = eq_outputs(100., .03, .01, ex, dv, "CALL", 100., .2, 1.0, "BUY")
    o2 = eq_outputs(100.01, .03, .01, ex, dv, "CALL", 100., .2, 1.0, "BUY")
    o0 = eq_outputs(99.99, .03, .01, ex, dv, "CALL", 100., .2, 1.0, "BUY")
    assert abs((o2["valuation"]["pv"] - o0["valuation"]["pv"]) / .02 - o1["delta"]) < 1e-6
    caught("equity_forward_deep", "delta against forward, not spot", abs(o1["delta"] * math.exp(-.02) - o1["delta"]), atol(1))
    s.add(op, dict(i, snapshot_id="snap-1"), {**o1, "valuation": {**o1["valuation"], "data_version": "snap-1"}}, cls=A, verified=["analytic"])
    for k, x, c in (("vol", 0.0, "E_DOMAIN"), ("strike", 0.0, "E_DOMAIN"), ("quantity", 0.0, "E_DOMAIN"), ("expiry", str(AS_OF), "E_DOMAIN"), ("expiry", str(AS_OF - timedelta(2)), "E_DATE_ORDER"), ("spot", -1.0, "E_DOMAIN")):
        s.add(op, dict(i, **{k: x}), error=c, cls=E, tags=["invalid"])
    write(s)


def greeks():
    s = S("greeks", "06-risk/vol-greeks.md")
    op, ob = "risk.vol.greeks", "risk.vol.bump_greeks"
    ql.Settings.instance().evaluationDate = Q(AS_OF)
    dc = ql.Actual365Fixed()
    for t, F, K, v, T in GRID:
        days = round(T * 365)
        T = days / 365
        r, q = .03, .01
        kw = dict(S=F, r=r, q=q)
        g = V.greeks("BLACK_SCHOLES", t, K, v, T, **kw)
        pr = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(F)), ql.YieldTermStructureHandle(ql.FlatForward(Q(AS_OF), q, dc)), ql.YieldTermStructureHandle(ql.FlatForward(Q(AS_OF), r, dc)),
                                          ql.BlackVolTermStructureHandle(ql.BlackConstantVol(Q(AS_OF), ql.NullCalendar(), v, dc)))
        o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if t == "CALL" else ql.Option.Put, K), ql.EuropeanExercise(Q(AS_OF + timedelta(days))))
        o.setPricingEngine(ql.AnalyticEuropeanEngine(pr))
        for a, b in ((o.NPV(), g["price"]), (o.delta(), g["delta"]), (o.gamma(), g["gamma"]), (o.vega(), g["vega"]), (o.theta(), g["theta"]), (o.rho(), g["rho"])):
            assert abs(a - b) < 1e-8 * max(1, abs(b)), (a, b)
        ins = pinputs("BLACK_SCHOLES", t, K, T, spot=F, rate=r, **{"yield": q}, vol=v)
        s.add(op, ins, g, cls=A, verified=[QLV, "analytic-bump"])
        models = [("BLACK_SCHOLES", ins, kw), ("BLACK_76", pinputs("BLACK_76", t, K, T, forward=F, discount_factor=.97, vol=v), dict(F=F, D=.97)), ("BACHELIER", pinputs("BACHELIER", t, K, T, forward=F, discount_factor=.97, vol=v * F), dict(F=F, D=.97))]
        for m, i2, k2 in models:
            vv = v * F if m == "BACHELIER" else v
            ga = V.greeks(m, t, K, vv, T, **k2)
            gb = V.bump_greeks(m, t, K, vv, T, **k2)
            for key in gb:
                assert abs(ga[key] - gb[key]) <= 2e-4 + 1e-4 * abs(ga[key]), (m, key, ga[key], gb[key])
            hv = 1e-3 * vv
            assert 4 * 4e-16 * max(ga["price"], 1) / hv ** 2 < BUMPLIM["absolute"] + 1e-6 * abs(ga["volga"])
            if m != "BLACK_SCHOLES":
                s.add(op, i2, ga, cls=A, verified=["analytic-bump"])
            s.add(ob, i2, gb, cls=I, limit=BUMPLIM, verified=["analytic-bump"])
    g = V.greeks("BLACK_76", "CALL", -.01, .2, 2., F=.01, D=.98, shift=.03)
    s.add(op, pinputs("BLACK_76", "CALL", -.01, 2., forward=.01, discount_factor=.98, shift=.03, vol=.2), g, cls=A, verified=["analytic-bump"], tags=["shift"])
    base = V.greeks("BLACK_SCHOLES", "CALL", 100., .2, 1., S=100., r=.03, q=.01)
    caught("greeks", "vega per vol point", base["vega"] * .99, atol(base["vega"]))
    caught("greeks", "theta per day", abs(base["theta"]) * (1 - 1 / 365), atol(base["theta"]))
    caught("greeks", "delta without the yield factor", abs(base["delta"] / math.exp(-.01) - base["delta"]), atol(1))
    caught("greeks", "rho per point", base["rho"] * .99, atol(base["rho"]))
    caught("greeks", "Black-76 delta left undiscounted", .03 * .5, atol(1))
    b76 = pinputs("BLACK_76", "CALL", 100., 1., forward=100.0, discount_factor=1.0, vol=.2)
    s.add(op, dict(b76, vol=0.0), error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, dict(b76, expiry_years=0.0), error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)


def smile():
    s = S("smile", "05-volatility/smile-and-surface.md")
    to, fr = "vol.delta.to_strike", "vol.delta.from_strike"
    for t, d in (("CALL", .25), ("PUT", -.25), ("CALL", .1), ("PUT", -.1), ("CALL", .5)):
        for conv, sc in (("FORWARD", None), ("SPOT", .97)):
            F, v, T = 100., .22, .75
            k = V.to_strike(F, v, T, t, d, sc or 1.)
            assert abs(V.from_strike(F, v, T, t, k, sc or 1.) - d) < 1e-12
            s.add(to, dict(forward=F, vol=v, expiry_years=T, option_type=t, delta=d, convention=conv, scale=sc), {"strike": k}, cls=I, verified=["round-trip", "analytic"])
            s.add(fr, dict(forward=F, vol=v, expiry_years=T, option_type=t, strike=k, convention=conv, scale=sc), {"delta": d}, cls=A, limit={"absolute": 1e-10, "relative": 1e-10, "reason": "strike came through Ninv"}, verified=["round-trip"])
    caught("smile", "spot delta read as forward delta", abs(V.to_strike(100, .22, .75, "CALL", .25, .97) - V.to_strike(100, .22, .75, "CALL", .25)), 1e-8)
    base = dict(forward=100., vol=.22, expiry_years=.75, option_type="CALL", delta=.25, convention="FORWARD", scale=None)
    s.add(to, dict(base, delta=1.0), error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(to, dict(base, option_type="PUT", delta=.25), error="E_DOMAIN", cls=E, tags=["invalid"], description="a put delta is negative")
    s.add(to, dict(base, scale=.9), error="E_INPUT", cls=E, tags=["invalid"])
    s.add(to, dict(base, convention="SPOT", scale=0.0), error="E_DOMAIN", cls=E, tags=["invalid"])
    op = "vol.smile.rr_bf"
    for atmc in ("ATM_FORWARD", "DELTA_NEUTRAL"):
        F, T, a, rr, bf = 100., 1., .2, -.04, .006
        cv, pv = a + bf + rr / 2, a + bf - rr / 2
        o = {"atm_strike": F if atmc == "ATM_FORWARD" else F * math.exp(a * a * T / 2), "call_vol": cv, "put_vol": pv, "call_strike": V.to_strike(F, cv, T, "CALL", .25), "put_strike": V.to_strike(F, pv, T, "PUT", -.25)}
        s.add(op, dict(forward=F, expiry_years=T, atm_vol=a, atm_convention=atmc, rr=rr, bf=bf, delta=.25, convention="FORWARD", scale=None), o, cls=I, verified=["analytic"])
    caught("smile", "ATM forward taken for delta neutral", 100 * (math.exp(.02) - 1), 1e-8)
    caught("smile", "risk reversal sign", .04, 1e-8)
    s.add(op, dict(forward=100., expiry_years=1., atm_vol=.01, atm_convention="ATM_FORWARD", rr=-.1, bf=0.0, delta=.25, convention="FORWARD", scale=None), error="E_DOMAIN", cls=E, tags=["invalid"])
    # SVI
    P = dict(a=.03, b=.12, rho=-.35, m=.02, sigma=.15)
    Pv = [P[x] for x in ("a", "b", "rho", "m", "sigma")]
    ks = [-.6, -.4, -.25, -.1, 0., .1, .25, .4, .6]
    T = 1.5
    ev = "vol.svi.evaluate"
    w = [V.svi_w(Pv, k) for k in ks]
    gs = [V.svi_g(Pv, k) for k in ks]
    sec = ql.SviSmileSection(T, 100.0, [P["a"], P["b"], P["sigma"], P["rho"], P["m"]])
    assert max(abs(sec.volatility(100 * math.exp(k)) - math.sqrt(x / T)) for k, x in zip(ks, w)) < 1e-12
    assert min(gs) > 1e-3
    s.add(ev, dict(svi=P, log_moneyness=ks, expiry_years=T), {"total_variance": w, "implied_vol": [math.sqrt(x / T) for x in w], "g": gs, "min_g": min(gs), "butterfly_free": True}, cls=I, verified=[QLV, "analytic"])
    # Axel Vogt's published butterfly counterexample
    Pa = dict(a=-.0410, b=.1331, rho=.3060, m=.3586, sigma=.4153)
    Pav = [Pa[x] for x in ("a", "b", "rho", "m", "sigma")]
    ka = [-1.5, -1., -.5, 0., .5, 1., 1.5]
    ga = [V.svi_g(Pav, k) for k in ka]
    assert min(ga) < -1e-3
    wa = [V.svi_w(Pav, k) for k in ka]
    s.add(ev, dict(svi=Pa, log_moneyness=ka, expiry_years=1.0), {"total_variance": wa, "implied_vol": [math.sqrt(x) for x in wa], "g": ga, "min_g": min(ga), "butterfly_free": False}, cls=I, verified=["published-counterexample", "analytic"], tags=["arbitrage"], description="Vogt parameters from Gatheral-Jacquier 2014; g is negative")
    caught("smile", "SVI rho sign flipped", abs(V.svi_w(Pv, .4) - V.svi_w([.03, .12, .35, .02, .15], .4)), 1e-8)
    for bad in (dict(P, b=-.1), dict(P, rho=1.0), dict(P, sigma=0.0), dict(P, a=-1.0)):
        s.add(ev, dict(svi=bad, log_moneyness=ks, expiry_years=T), error="E_DOMAIN", cls=E, tags=["invalid"])
    cal = "vol.svi.calibrate"
    x, e, spread = V.svi_fit(ks, w)
    assert spread < 1e-6 and e < 1e-9 and max(abs(a - b) for a, b in zip(x, Pv)) < 1e-6
    s.add(cal, dict(log_moneyness=ks, total_variance=w), {"svi": P, "rmse": 0.0}, cls=I, limit=FITLIM, verified=["known-truth", "scipy"])
    noise = [1, -1, .5, -.5, 1, -1, .3, .7, -.4]
    wn = [a + 1e-4 * b for a, b in zip(w, noise)]
    x, e, spread = V.svi_fit(ks, wn)
    assert spread < 1e-5, spread
    s.add(cal, dict(log_moneyness=ks, total_variance=wn), {"svi": dict(zip(("a", "b", "rho", "m", "sigma"), map(float, x))), "rmse": e}, cls=I, limit={"absolute": 2e-4, "relative": 0.0, "reason": "noisy fit: flat directions in the minimum; rmse itself is held by the extra check"},
          verified=["scipy"], tags=["noisy"], description="parameters loose, rmse tight")
    s.cases[-1]["extra_checks"] = [{"output": "rmse", "expected": e, "method": "absolute", "limit": 1e-8}]
    s.add(cal, dict(log_moneyness=ks[:4], total_variance=w[:4]), error="E_INPUT", cls=E, tags=["invalid"])
    s.add(cal, dict(log_moneyness=ks, total_variance=[-.01] + w[1:]), error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(cal, dict(log_moneyness=ks[::-1], total_variance=w), error="E_INPUT", cls=E, tags=["invalid"])
    # SSVI
    op = "vol.ssvi.evaluate"
    ths = [.01, .04, .09, .16]
    def ss(rho, eta, g, kk=(-.4, -.1, 0., .1, .4)):
        rows = [[V.ssvi_w(k, th, rho, eta, g) for k in kk] for th in ths]
        pf = [V.ssvi_phi(th, eta, g) for th in ths]
        m1 = [4 - th * p * (1 + abs(rho)) for th, p in zip(ths, pf)] + [4 - th * p * p * (1 + abs(rho)) for th, p in zip(ths, pf)]
        m2 = [1 + math.sqrt(1 - rho * rho) - rho * rho * (1 - g) / (1 + th) for th in ths]
        assert min(abs(x) for x in m1 + m2) > 1e-6
        return dict(rho=rho, eta=eta, gamma=g, thetas=ths, log_moneyness=list(kk)), {"total_variance": rows, "butterfly_free": min(m1) > 0, "calendar_free": min(m2) >= 0}
    i1, o1 = ss(-.4, 1.0, .5)
    assert o1["butterfly_free"] and o1["calendar_free"] and all(abs(r[2] - th) < 1e-15 for r, th in zip(o1["total_variance"], ths))
    s.add(op, i1, o1, cls=I, verified=["analytic", "atm-equals-theta"])
    i2, o2 = ss(-.7, 3.0, .5)
    assert not o2["butterfly_free"]
    s.add(op, i2, o2, cls=I, verified=["analytic"], tags=["arbitrage"])
    i3, o3 = ss(0.0, .15, 1.0)
    s.add(op, i3, o3, cls=I, verified=["analytic"])
    caught("smile", "SSVI phi without the (1+theta) term", abs(V.ssvi_w(.4, .16, -.4, 1., .5) - .16 / 2 * (1 - .4 * (1 / .4) * .4 + math.sqrt((1 / .4 * .4 - .4) ** 2 + 1 - .16))), 1e-8)
    s.add(op, dict(i1, rho=1.0), error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, dict(i1, gamma=0.0), error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, dict(i1, thetas=[.04, .01]), error="E_INPUT", cls=E, tags=["invalid"])
    from scipy.optimize import least_squares
    kk = [-.4, -.2, -.1, 0., .1, .2, .4]
    tv = [[V.ssvi_w(k, th, -.4, 1.0, .5) for k in kk] for th in ths]
    flatw = np.array(tv).ravel()
    res = lambda p: np.array([V.ssvi_w(k, th, p[0], p[1], p[2]) for th in ths for k in kk]) - flatw  # noqa: E731
    sols = [least_squares(res, x0, bounds=([-.99, 1e-4, 1e-3], [.99, 10, 1]), xtol=1e-15, ftol=1e-15, gtol=1e-15).x for x0 in ([0, .5, .3], [-.8, 2, .8], [.5, 1, .5])]
    assert all(max(abs(a - b) for a, b in zip(x, (-.4, 1., .5))) < 1e-6 for x in sols), sols
    s.add("vol.ssvi.calibrate", dict(thetas=ths, log_moneyness=kk, total_variance=tv), {"rho": -.4, "eta": 1.0, "gamma": .5, "rmse": 0.0}, cls=I, limit=FITLIM, verified=["known-truth", "scipy"])
    s.add("vol.ssvi.calibrate", dict(thetas=ths, log_moneyness=kk, total_variance=[tv[0]] + [r[:-1] for r in tv[1:]]), error="E_INPUT", cls=E, tags=["invalid"])
    write(s)


SURF = {"expiry_years": [.25, .5, 1., 2.], "log_moneyness": [-.4, -.2, 0., .2, .4],
        "vols": [[.32, .27, .23, .22, .23], [.30, .26, .225, .215, .22], [.285, .25, .22, .21, .215], [.27, .24, .215, .205, .21]]}


def surface():
    s = S("surface", "05-volatility/smile-and-surface.md")
    ql.Settings.instance().evaluationDate = Q(AS_OF)
    dc = ql.Actual365Fixed()
    days = [73, 146, 365, 730]
    sf = dict(SURF, expiry_years=[d / 365 for d in days])
    off = 10.0  # QuantLib's strike axis carries k + 10, so its bilinear variance rule is the spec's rule in k
    m = ql.Matrix(5, 4)
    for j in range(4):
        for i in range(5):
            m[i][j] = sf["vols"][j][i]
    qs = ql.BlackVarianceSurface(Q(AS_OF), ql.NullCalendar(), [Q(AS_OF + timedelta(d)) for d in days], [k + off for k in sf["log_moneyness"]], m, dc, ql.BlackVarianceSurface.ConstantExtrapolation, ql.BlackVarianceSurface.ConstantExtrapolation)
    qs.enableExtrapolation()
    pts = [(d / 365, k) for d in (30, 73, 100, 146, 200, 365, 500, 730, 900) for k in (-.6, -.4, -.3, -.05, 0., .1, .33, .4, .7)]
    w = [V.surf_w(sf, T, k) for T, k in pts]
    for (T, k), x in zip(pts, w):
        assert abs(qs.blackVariance(T, k + off, True) - x) < 1e-12, (T, k, qs.blackVariance(T, k + off, True), x)
    s.add("vol.surface.query", dict(surface=sf, points=[{"expiry_years": T, "log_moneyness": k} for T, k in pts]), {"total_variance": w, "vols": [math.sqrt(x / T) for x, (T, _) in zip(w, pts)]}, cls=I, verified=[QLV])
    lin = (.285 + (500 - 365) / 365 * (.27 - .285))
    caught("surface", "vol, not total variance, linear in time", abs(math.sqrt(V.surf_w(sf, 500 / 365, -.4) / (500 / 365)) - lin), 1e-8)
    wK = V.surf_w(sf, 1., .1)
    caught("surface", "k from spot, not forward (F/S 1.03)", abs(V.surf_w(sf, 1., .1 + math.log(1.03)) - wK), 1e-8)
    s.add("vol.surface.query", dict(surface=sf, points=[{"expiry_years": 0.0, "log_moneyness": 0.0}]), error="E_DOMAIN", cls=E, tags=["invalid"])
    ck = "vol.surface.check"
    def add(x, tags=()):
        c, b, gap = V.surf_check(x)
        assert gap > 1e-9
        s.add(ck, {"surface": x}, {"calendar_violations": c, "butterfly_violations": b, "arbitrage_free": not c and not b}, cls=E, verified=["analytic"], tags=list(tags))
        return c, b
    c, b = add(sf)
    assert not c and not b
    x = {**sf, "vols": [r[:] for r in sf["vols"]]}
    x["vols"][2] = [v * .6 for v in x["vols"][2]]
    c, b = add(x, ["arbitrage"])
    assert c
    x = {**sf, "vols": [r[:] for r in sf["vols"]]}
    x["vols"][1][2] = .75
    c, b = add(x, ["arbitrage"])
    assert any(z["kind"] == "CONVEXITY" for z in b)
    x = {**sf, "vols": [r[:] for r in sf["vols"]]}
    x["vols"][3] = [.05, .05, .9, .05, .05]
    c, b = add(x, ["arbitrage"])
    assert any(z["kind"] == "SLOPE" for z in b)
    s.add(ck, {"surface": {**sf, "expiry_years": sf["expiry_years"][::-1]}}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(ck, {"surface": {**sf, "vols": sf["vols"][:3]}}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(ck, {"surface": {**sf, "vols": [[0.0] + r[1:] for r in sf["vols"]]}}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(ck, {"surface": {**sf, "log_moneyness": [i / 100 for i in range(101)], "vols": [[.2] * 101] * 4}}, error="E_LIMIT", cls=E, tags=["invalid"])
    # bucket vega
    op = "risk.vol.surface_vega"
    pos = [dict(option_type="CALL", forward=100., strike=105., discount_factor=.98, expiry_years=.75, quantity=10.), dict(option_type="PUT", forward=100., strike=85., discount_factor=.99, expiry_years=.3, quantity=-4.), dict(option_type="CALL", forward=100., strike=170., discount_factor=.9, expiry_years=3., quantity=2.)]
    def pv(z):
        return sum(p["quantity"] * V.black(p["option_type"], p["forward"], p["strike"], math.sqrt(V.surf_w(z, p["expiry_years"], math.log(p["strike"] / p["forward"])) / p["expiry_years"]), p["expiry_years"], p["discount_factor"]) for p in pos)
    def bump(fn):
        return {**sf, "vols": [[fn(j, i, v) for i, v in enumerate(r)] for j, r in enumerate(sf["vols"])]}
    bk = [[(pv(bump(lambda a, b, v: v + 1e-4 if (a, b) == (j, i) else v)) - pv(bump(lambda a, b, v: v - 1e-4 if (a, b) == (j, i) else v))) / 2e-4 for i in range(5)] for j in range(4)]
    par = (pv(bump(lambda a, b, v: v + 1e-4)) - pv(bump(lambda a, b, v: v - 1e-4))) / 2e-4
    tot = sum(sum(r) for r in bk)
    assert abs(tot - par) < 5e-2 * abs(par), (tot, par)
    s.add(op, dict(surface=sf, positions=pos), {"pv": pv(sf), "bucket_vega": bk, "parallel_vega": par, "bucket_sum": tot}, cls=I, limit={"absolute": 1e-7, "relative": 1e-8, "reason": "central difference over 2e-4 of prices near 100"}, verified=["analytic-bump"])
    caught("surface", "bucket vega per vol point", abs(par) * .99, 1e-7 + 1e-8 * abs(par))
    s.add(op, dict(surface={**sf, "vols": [[5e-5] + r[1:] for r in sf["vols"]]}, positions=pos), error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)


def sabr():
    s = S("sabr", "05-volatility/sabr.md")
    op = "vol.sabr.hagan"
    sets = [(.03, 2., .04, .5, -.3, .4, 0.), (100., 1., 3.0, .5, -.4, .6, 0.), (100., .5, .25, 1., -.6, .8, 0.), (.01, 5., .02, .3, .2, .35, .03), (1., 10., .25, 0., .1, .3, 0.)]
    g = {"swap": 0, "noshift": 0, "noT": 0}
    for f, T, al, be, rho, nu, sh in sets:
        ks = [(f + sh) * m - sh for m in (.6, .8, .95, 1., 1.05, 1.25, 1.6)]
        vs = [V.hagan(f + sh, k + sh, T, al, be, rho, nu) for k in ks]
        for k, x in zip(ks, vs):
            q = ql.shiftedSabrVolatility(k, f, T, al, be, nu, rho, sh) if sh else ql.sabrVolatility(k, f, T, al, be, nu, rho)
            assert abs(q - x) < 1e-10, (k, q, x)
        ins = dict(forward=f, strikes=ks, expiry_years=T, alpha=al, beta=be, rho=rho, nu=nu)
        if sh:
            ins["shift"] = sh
        s.add(op, ins, {"vols": vs}, cls=I, verified=[QLV], tags=["shift"] if sh else [])
        g["swap"] = max(g["swap"], abs(V.hagan(f + sh, ks[0] + sh, T, al, be, nu, abs(rho)) - vs[0]))
        g["noT"] = max(g["noT"], abs(V.hagan(f + sh, ks[0] + sh, 0, al, be, rho, nu) - vs[0]))
    caught("sabr", "rho and nu swapped (QuantLib argument order)", g["swap"], 1e-7)
    caught("sabr", "expansion term in T dropped", g["noT"], 1e-7)
    caught("sabr", "shift ignored", abs(V.hagan(.01, .01 * 1.25, 5, .02, .3, .2, .35) - V.hagan(.04, .05, 5, .02, .3, .2, .35)), 1e-7)
    base = dict(forward=.03, strikes=[.02, .03], expiry_years=2., alpha=.04, beta=.5, rho=-.3, nu=.4)
    for k, x in (("expiry_years", 0.0), ("alpha", 0.0), ("beta", 1.5), ("rho", -1.0), ("nu", -.1), ("forward", -.01), ("strikes", [-.01, .03])):
        s.add(op, dict(base, **{k: x}), error="E_DOMAIN", cls=E, tags=["invalid"])
    # density: Hagan negative at low strikes, shifted or not; the arbitrage-free recipe is not
    dn = "vol.sabr.density"
    LIM = {"absolute": 1e-5, "relative": 1e-6, "reason": "second difference: rounding of 1e-16 over h squared"}
    bad = dict(f=.02, T=20., al=.03, be=.5, rho=-.3, nu=.5)
    ks = [.0005, .001, .002, .004, .008, .012, .02, .03, .05]
    h = 2e-4
    def dens(f, ks, sh):
        return [V.sabr_density(f + sh, k + sh, bad["T"], bad["al"], bad["be"], bad["rho"], bad["nu"], h) for k in ks]
    d = dens(.02, ks, 0.)
    assert min(d) < -1e-3, min(d)
    ins = dict(forward=.02, strikes=ks, expiry_years=20., alpha=.03, beta=.5, rho=-.3, nu=.5, h_strike=h, on_negative="REPORT")
    s.add(dn, ins, {"density": d, "min_density": min(d), "negative_density": True}, cls=I, limit=LIM, verified=["analytic-replay"], tags=["arbitrage"])
    s.add(dn, dict(ins, on_negative="REJECT"), error="E_ARBITRAGE", cls=E, tags=["arbitrage"])
    sh = .01
    ks2 = [k - sh for k in ks]
    d2 = dens(.01, ks2, sh)
    assert min(d2) < -1e-3 and abs(min(d2) - min(d)) < 1e-6
    s.add(dn, dict(ins, forward=.01, strikes=ks2, shift=sh), {"density": d2, "min_density": min(d2), "negative_density": True}, cls=I, limit=LIM, verified=["analytic-replay"], tags=["arbitrage", "shift"], description="a shift does not cure negative density")
    s.add(dn, dict(ins, forward=.01, strikes=ks2, shift=sh, on_negative="REJECT"), error="E_ARBITRAGE", cls=E, tags=["arbitrage", "shift"])
    good = dict(forward=100., strikes=[60., 80., 100., 120., 150.], expiry_years=1., alpha=3.0, beta=.5, rho=-.4, nu=.6, h_strike=.5, on_negative="REJECT")
    d = [V.sabr_density(100., k, 1., 3., .5, -.4, .6, .5) for k in good["strikes"]]
    assert min(d) > 1e-5
    s.add(dn, good, {"density": d, "min_density": min(d), "negative_density": False}, cls=I, limit=LIM, verified=["analytic-replay"])
    s.add(dn, dict(good, strikes=[.2], h_strike=.5), error="E_DOMAIN", cls=E, tags=["invalid"])
    cal = "vol.sabr.calibrate"
    ks = [60., 75., 90., 100., 110., 125., 150.]
    al, be, rho, nu = 3., .5, -.4, .6
    vs = [V.hagan(100., k, 1., al, be, rho, nu) for k in ks]
    x, e, sp = V.sabr_fit(100., 1., be, ks, vs)
    assert sp < 1e-6 and max(abs(x - np.array([al, rho, nu]))) < 1e-6
    s.add(cal, dict(forward=100., expiry_years=1., beta=be, strikes=ks, vols=vs), {"alpha": al, "rho": rho, "nu": nu, "rmse": 0.0}, cls=I, limit=FITLIM, verified=["known-truth", "scipy"])
    vn = [v + 2e-4 * z for v, z in zip(vs, (1, -1, .5, -.5, 1, -1, .3))]
    x, e, sp = V.sabr_fit(100., 1., be, ks, vn)
    assert sp < 1e-5
    s.add(cal, dict(forward=100., expiry_years=1., beta=be, strikes=ks, vols=vn), {"alpha": float(x[0]), "rho": float(x[1]), "nu": float(x[2]), "rmse": e}, cls=I, limit={"absolute": 1e-4, "relative": 0.0, "reason": "noisy fit; rmse held by the extra check"}, verified=["scipy"], tags=["noisy"])
    s.cases[-1]["extra_checks"] = [{"output": "rmse", "expected": e, "method": "absolute", "limit": 1e-8}]
    caught("sabr", "beta 0.5 fitted as beta 1 misses the quotes", V.sabr_fit(100., 1., 1., ks, vs)[1], 1e-6)
    s.add(cal, dict(forward=100., expiry_years=1., beta=be, strikes=ks[:2], vols=vs[:2]), error="E_INPUT", cls=E, tags=["invalid"])
    s.add(cal, dict(forward=100., expiry_years=1., beta=be, strikes=ks, vols=[0.0] + vs[1:]), error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)
    s = S("sabr_deep", "05-volatility/sabr.md")
    af = "vol.sabr.arbfree"
    def run(f, T, al, be, rho, nu, sh, J, m, Nn, ks, ver, tags=()):
        xs = [k + sh for k in ks]
        r = V.arbfree(f + sh, T, al, be, rho, nu, J, m, Nn, xs)
        r2 = V.arbfree((f + sh), T, al * (1 + 2e-15), be, rho, nu, J, m, Nn, xs)
        assert max(abs(a - b) for a, b in zip(r["calls"], r2["calls"])) < 1e-9 * max(1, f)
        assert abs(r["mass"] - 1) < 1e-11 and abs(r["mean"] - (f + sh)) < 1e-10 * (f + sh) and r["min_density"] >= 0
        vs = []
        for x, c in zip(xs, r["calls"]):
            iv = max(f + sh - x, 0.)
            vs.append(V.implied_black("CALL", f + sh, x, c, T) if c > iv + 1e-10 * (f + sh) else None)
        ins = dict(forward=f, expiry_years=T, alpha=al, beta=be, rho=rho, nu=nu, shift=sh, cells=J, cells_below=m, steps=Nn, strikes=ks)
        s.add(af, ins, {"call_prices": r["calls"], "vols": vs, "mass": r["mass"], "mean": r["mean"], "absorbed": r["absorbed"], "min_density": r["min_density"]}, cls=NS, verified=ver, tags=list(tags))
        return r, vs
    ql.Settings.instance().evaluationDate = Q(AS_OF)
    # CEV truth at nu = 0: QuantLib AnalyticCEVEngine, 365 days
    dc = ql.Actual365Fixed()
    rts = ql.YieldTermStructureHandle(ql.FlatForward(Q(AS_OF), 0.0, dc))
    worst = 0.0
    for be_, al_ in ((.5, .3), (.25, .3)):
        ks = [.7, .85, 1., 1.2, 1.5]
        r, _ = run(1., 1., al_, be_, 0.0, 0.0, 0., 2000, 500, 1000, ks, [QLV + "-cev"], ["cev"])
        for k, c in zip(ks, r["calls"]):
            o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call, k), ql.EuropeanExercise(Q(AS_OF + timedelta(365))))
            o.setPricingEngine(ql.AnalyticCEVEngine(1., al_, be_, rts))
            worst = max(worst, abs(o.NPV() - c))
    assert worst < 5e-4, worst
    note(f"sabr_deep: arbitrage-free recipe against QuantLib CEV at nu=0: worst call error {worst:.2e}")
    ARB_CEV.append(worst)
    # Hagan where it is safe, and the wrong sign of the time-dependent term
    ks = [.6, .8, 1., 1.25, 1.6]
    r, vs = run(1., 2., .3, .5, -.4, .5, 0., 1000, 250, 800, ks, ["hagan-formula-near"], [])
    hv = [V.hagan(1., k, 2., .3, .5, -.4, .5) for k in ks]
    gap = max(abs(a - b) for a, b in zip(vs, hv))
    assert gap < 7e-3, gap
    ARB_HAGAN.append(gap)
    wrong = V.arbfree(1., 2., .3, .5, -.4, .5, 1000, 250, 800, ks, sign=-1.0)
    caught("sabr_deep", "sign of the time term in M flipped", max(abs(a - b) for a, b in zip(r["calls"], wrong["calls"])), 1e-8 + 1e-8)
    nsec = ql.NoArbSabrSmileSection(2.0, 1.0, [.3, .5, .5, -.4])
    d = max(abs(nsec.volatility(k) - v) for k, v in zip(ks, vs))
    ARB_DOUST.append(d)
    note(f"sabr_deep: against QuantLib NoArbSabr (Doust, another method): worst vol gap {d:.2e}")
    assert d < 2e-2, d
    s.cases[-1]["verified_by"].append(QLV + "-noarbsabr-near")
    # the plan's failure case: Hagan density negative, recipe not
    kk = [.002, .004, .008, .012, .02, .03, .05]
    r, _ = run(.02, 20., .03, .5, -.3, .5, 0., 800, 40, 400, kk, ["mass-and-mean"], ["arbitrage"])
    assert r["absorbed"] > .05
    c = r["calls"]
    sl = [(c[i + 1] - c[i]) / (kk[i + 1] - kk[i]) for i in range(len(c) - 1)]
    assert all(sl[i] <= sl[i + 1] + 1e-12 for i in range(len(sl) - 1)) and sl[0] >= -1
    run(.01, 20., .03, .5, -.3, .5, .01, 800, 40, 400, [k - .01 for k in kk], ["mass-and-mean"], ["arbitrage", "shift"])
    caught("sabr_deep", "reflecting, not absorbing, floor (no mass absorbed)", r["absorbed"], 1e-8)
    i = dict(forward=1., expiry_years=1., alpha=.3, beta=.5, rho=-.4, nu=.5, shift=0., cells=100, cells_below=25, steps=50, strikes=[1.])
    s.add(af, dict(i, beta=1.0), error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(af, dict(i, cells_below=100), error="E_INPUT", cls=E, tags=["invalid"])
    s.add(af, dict(i, cells_below=0), error="E_INPUT", cls=E, tags=["invalid"])
    s.add(af, dict(i, steps=0), error="E_INPUT", cls=E, tags=["invalid"])
    s.add(af, dict(i, cells=20001), error="E_LIMIT", cls=E, tags=["invalid"])
    s.add(af, dict(i, strikes=[100.]), error="E_INPUT", cls=E, tags=["invalid"])
    write(s)


ARB_CEV, ARB_HAGAN, ARB_DOUST = [], [], []


def strata_check():
    """Strata results are read from oracle/strata/out/vol-out.tsv, written by StrataVol from vol-in.tsv. Inputs are fixed here."""
    from qf_oracle.common import ROOT
    src = ROOT / "oracle" / "strata" / "out" / "vol-in.tsv"
    lines = [f"BLACK\t{t}\t{F!r}\t{K!r}\t{v!r}\t{T!r}" for t, F, K, v, T in GRID] + [f"NORMAL\t{t}\t{F!r}\t{K!r}\t{v * F!r}\t{T!r}" for t, F, K, v, T in GRID]
    for f, T, al, be, rho, nu in ((.03, 2., .04, .5, -.3, .4), (100., 1., 3.0, .5, -.4, .6), (1., 10., .25, .25, .1, .3)):
        lines += [f"SABR\t{f!r}\t{f * m!r}\t{T!r}\t{al!r}\t{be!r}\t{rho!r}\t{nu!r}" for m in (.6, .8, .95, 1.05, 1.25, 1.6)]
    src.write_text("\n".join(lines) + "\n", newline="\n")
    back = (ROOT / "oracle" / "strata" / "out" / "vol-out.tsv").read_text().splitlines()
    assert len(back) == len(lines) and all(b.startswith(a) for a, b in zip(lines, back)), "rerun StrataVol: vol-out.tsv is stale"
    s = S("strata_vol", "05-volatility/black-models.md")
    SV = "strata-2.12.78"
    worst = 0.0
    for r in back:
        x = r.split("\t")
        if x[0] == "SABR":
            f, k, T, al, be, rho, nu = map(float, x[1:8])
            v = V.hagan(f, k, T, al, be, rho, nu)
            worst = max(worst, abs(v - float(x[8])))
            s.add("vol.sabr.hagan", dict(forward=f, strikes=[k], expiry_years=T, alpha=al, beta=be, rho=rho, nu=nu), {"vols": [v]}, cls=I, verified=[SV, QLV])
            continue
        t, F, K, v, T = x[1], *map(float, x[2:6])
        if x[0] == "NORMAL":
            p = V.bachelier(t, F, K, v, T)
            worst = max(worst, abs(p - float(x[6])))
            s.add("vol.option.price", pinputs("BACHELIER", t, K, T, forward=F, discount_factor=1.0, vol=v), {"price": p, "forward": F}, cls=A, verified=[SV, QLV])
            continue
        g = V.greeks("BLACK_76", t, K, v, T, F=F, D=1.0)
        for key, val in zip(("price", "delta", "gamma", "vega", "vanna", "volga"), map(float, x[6:12])):
            worst = max(worst, abs(g[key] - val) / max(1, abs(val)))
        worst = max(worst, abs(float(x[12]) - v))
        s.add("risk.vol.greeks", pinputs("BLACK_76", t, K, T, forward=F, discount_factor=1.0, vol=v), g, cls=A, verified=[SV, "analytic-bump"])
    assert worst < 1e-8, worst
    note(f"strata_vol: Black, Greeks, Bachelier, Hagan against Strata, worst gap {worst:.2e}")
    write(s)


def usecase():
    s = S("usecases_c", "04-pricing/use-cases.md")
    r = .03
    S0 = 5000.
    fc = flat(r)
    Ps = [(91, [.004, .05, -.5, .0, .08]), (182, [.008, .07, -.45, .01, .1]), (365, [.016, .09, -.4, .02, .13])]
    slices, fw, rm = [], [], []
    ms = [.7, .8, .85, .9, .95, 1., 1.05, 1.1, 1.15, 1.25, 1.4]
    kgrid = [-.3, -.15, 0., .15, .3]
    rows, Ts, Ps_fit = [], [], []
    for days, P in Ps:
        T = days / 365
        ex = AS_OF + timedelta(days)
        D = curve_df(r, ex)
        F = S0 * math.exp(.01 * T)
        qs = []
        ws, kk = [], []
        for m in ms:
            K = round(F * m, 0)
            k = math.log(K / F)
            v = math.sqrt(V.svi_w(P, k) / T)
            c, p = V.black("CALL", F, K, v, T, D), V.black("PUT", F, K, v, T, D)
            sp = min(.5, c / 2, p / 2)  # symmetric, so each mid is the model price
            qs.append({"strike": K, "call_bid": c - sp, "call_ask": c + sp, "put_bid": p - sp, "put_ask": p + sp})
            assert V.greeks("BLACK_76", "CALL", K, v, T, F=F, D=D)["vega"] > 1.0  # inversion well conditioned
            kk.append(k)
            ws.append(v * v * T)
        slices.append({"expiry": str(ex), "quotes": qs})
        x, e, sp = V.svi_fit(kk, ws)
        assert sp < 1e-6 and e < 1e-8, (sp, e)
        fw.append(F)
        rm.append(0.0)
        rows.append([math.sqrt(V.svi_w(P, k) / T) for k in kgrid])
        Ts.append(T)
        Ps_fit.append(P)
    c, b, gap = V.surf_check({"expiry_years": Ts, "log_moneyness": kgrid, "vols": rows})
    assert not c and not b and gap > 1e-9
    ex = AS_OF + timedelta(182)
    T, D, F = 182 / 365, curve_df(r, ex), fw[1]
    K = 5100.
    v = math.sqrt(V.svi_w(Ps_fit[1], math.log(K / F)) / T)
    g = V.greeks("BLACK_76", "CALL", K, v, T, F=F, D=D)
    q = 3.0
    out = {"forwards": fw, "svi_rmse": rm, "arbitrage_free": True, "vol": v, "valuation": {"pv": q * g["price"], "currency": "USD", "model": "BLACK_76_EQUITY", "data_version": None, "conventions": "EQUITY_FORWARD", "as_of": str(AS_OF)}, "delta": q * g["delta"], "vega": q * g["vega"]}
    ins = dict(as_of=str(AS_OF), funding_curve=fc, slices=slices, k_grid=kgrid, target=dict(option_type="CALL", strike=K, expiry=str(ex), quantity=q, side="BUY"), currency="USD")
    s.add("usecase.vol_surface", ins, out, cls=I, limit={"absolute": 2e-3, "relative": 1e-7, "reason": "SVI fit on quotes: 1e-6 in parameters carried through vega near 1400 by quantity 3"}, verified=["known-truth"], tags=["usecase"])
    s.add("usecase.vol_surface", dict(ins, target=dict(ins["target"], expiry=str(ex + timedelta(1)))), error="E_INPUT", cls=E, tags=["invalid"])
    write(s)


def main():
    equity_forward()
    black()
    equity_deep()
    greeks()
    smile()
    surface()
    sabr()
    strata_check()
    usecase()
    from qf_oracle.common import ROOT
    lines = [f"| {a} | {b} | {c:.3e} |" for a, b, c in MUTANTS]
    (ROOT / "oracle" / "MUTANTS_C.md").write_text("# Stage C wrong-convention checks\n\nWritten by `gen_stage_c.py`. The run stops if a suite's tolerance lets one through. Gap is the size of the error at the case that shows it.\n\n| Suite | Wrong convention | Gap |\n|---|---|---|\n" + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    note(f"stage C mutants: {len(MUTANTS)} caught; arbitrage-free against CEV {ARB_CEV}, Hagan {ARB_HAGAN}, Doust {ARB_DOUST}")


if __name__ == "__main__":
    main()
