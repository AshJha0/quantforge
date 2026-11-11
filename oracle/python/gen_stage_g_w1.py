"""Stage G wave 1, slice G1: one-factor short-rate models (Vasicek, CIR, Hull-White) - zero-coupon bond prices under
the model and European options on zero-coupon bonds.

Goldens come from this file's own replicas at 50 digits (mpmath). The outside oracle is QuantLib 1.44 with its own model
objects (`ql.Vasicek`, `ql.CoxIngersollRoss`, `ql.HullWhite` on a `ql.DiscountCurve`), rule 11.2.5; a case counts only if
every output is a QuantLib value. Each named wrong convention must be caught by the tolerance (`caught`).

    cd oracle/python && uv run python -W ignore gen_stage_g_w1.py
"""
import json
import math
from datetime import date, timedelta
from pathlib import Path

import mpmath as mp
import QuantLib as ql

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_g_w1.py"
A, R = "simple_analytic", "root_finding"
FOLDER = "stage_g"
HERE = Path(__file__).resolve().parent
MUTANTS, OUTSIDE = [], []
TOL = 1e-12 + 0  # simple_analytic absolute; relative 1e-10 checked below
ZCB, OPT = "rates.shortrate.zcb", "rates.shortrate.zcb_option"


def caught(name, gap, tol=1e-9):
    assert gap > tol, f"mutant '{name}' is not caught: gap {gap:.3e}"
    MUTANTS.append((name, float(gap)))


# ------------------------------------------------------------------------------------------------ model formulas
def vas_AB(a, b, s, tau, drop_conv=False):
    a, b, s, tau = map(mp.mpf, (a, b, s, tau))
    B = (1 - mp.exp(-a * tau)) / a
    lnA = (B - tau) * (a * a * b - s * s / 2) / (a * a)
    if not drop_conv:
        lnA -= s * s * B * B / (4 * a)
    return lnA, B


def cir_AB(a, b, s, tau, gamma_mut=False):
    a, b, s, tau = map(mp.mpf, (a, b, s, tau))
    g = mp.sqrt(a * a + (1 if gamma_mut else 2) * s * s)
    den = (g + a) * (mp.exp(g * tau) - 1) + 2 * g
    B = 2 * (mp.exp(g * tau) - 1) / den
    lnA = (2 * a * b / (s * s)) * mp.log(2 * g * mp.exp((a + g) * tau / 2) / den)
    return lnA, B


class Curve:
    """Log-linear discount factors on pillar times (ACT/365F year fractions), P(0) = 1, flat forward beyond the last."""

    def __init__(self, times, discount_factors):
        dfs = discount_factors
        self.t = [mp.mpf(0)] + [mp.mpf(x) for x in times]
        self.p = [mp.mpf(1)] + [mp.mpf(x) for x in dfs]

    def seg(self, t):
        for i in range(1, len(self.t)):
            if t < self.t[i]:
                return i
        return len(self.t) - 1

    def fwd(self, t):  # right-hand instantaneous forward
        i = self.seg(mp.mpf(t))
        return -(mp.log(self.p[i]) - mp.log(self.p[i - 1])) / (self.t[i] - self.t[i - 1])

    def P(self, t):
        t = mp.mpf(t)
        if t == 0:
            return mp.mpf(1)
        i = self.seg(t)
        return self.p[i - 1] * mp.exp(-self.fwd(self.t[i - 1]) * (t - self.t[i - 1]))


def hw_bond(cv, a, s, t, T, r, drop_var=False):
    a, s, t, T, r = map(mp.mpf, (a, s, t, T, r))
    B = (1 - mp.exp(-a * (T - t))) / a
    lnA = mp.log(cv.P(T) / cv.P(t)) + B * cv.fwd(t)
    if not drop_var:
        lnA -= s * s / (4 * a) * (1 - mp.exp(-2 * a * t)) * B * B
    return mp.exp(lnA - B * r), B


def gauss_opt(typ, PT, PS, K, sp):
    h = mp.log(PS / (PT * K)) / sp + sp / 2
    c = PS * mp.ncdf(h) - K * PT * mp.ncdf(h - sp)
    return c if typ == "CALL" else c - PS + K * PT


def sigma_p(a, s, T, S, ho_lee=False):
    a, s, T, S = map(mp.mpf, (a, s, T, S))
    if ho_lee:
        return s * (S - T) * mp.sqrt(T)
    return s / a * (1 - mp.exp(-a * (S - T))) * mp.sqrt((1 - mp.exp(-2 * a * T)) / (2 * a))


def ncx2_cdf(x, k, lam):
    x, k, lam = mp.mpf(x), mp.mpf(k), mp.mpf(lam)
    tot, j, w = mp.mpf(0), 0, mp.exp(-lam / 2)
    while True:
        term = w * mp.gammainc(k / 2 + j, 0, x / 2, regularized=True)
        tot += term
        if j > lam / 2 + 10 and term < mp.mpf(10) ** -45:
            return tot
        j += 1
        w *= (lam / 2) / j


def cir_opt(typ, a, b, s, r0, K, T, S):
    a, b, s, r0, K, T, S = map(mp.mpf, (a, b, s, r0, K, T, S))
    PT = mp.exp(cir_AB(a, b, s, T)[0] - cir_AB(a, b, s, T)[1] * r0)
    PS = mp.exp(cir_AB(a, b, s, S)[0] - cir_AB(a, b, s, S)[1] * r0)
    lnA, B = cir_AB(a, b, s, S - T)
    g = mp.sqrt(a * a + 2 * s * s)
    rho = 2 * g / (s * s * (mp.exp(g * T) - 1))
    psi = (a + g) / (s * s)
    rbar = (lnA - mp.log(K)) / B
    k = 4 * a * b / (s * s)
    c = (PS * ncx2_cdf(2 * rbar * (rho + psi + B), k, 2 * rho * rho * r0 * mp.exp(g * T) / (rho + psi + B))
         - K * PT * ncx2_cdf(2 * rbar * (rho + psi), k, 2 * rho * rho * r0 * mp.exp(g * T) / (rho + psi)))
    return (c if typ == "CALL" else c - PS + K * PT), PT, PS


# ------------------------------------------------------------------------------------------------ QuantLib (outside)
TODAY = ql.Date(10, 11, 2026)
ql.Settings.instance().evaluationDate = TODAY
DC = ql.Actual365Fixed()


def ql_curve(c):
    dates = [TODAY] + [TODAY + int(round(t * 365)) for t in c["times"]]
    h = ql.YieldTermStructureHandle(ql.DiscountCurve(dates, [1.0] + c["discount_factors"], DC))
    h.enableExtrapolation()
    return h


def ql_model(inp):
    m = inp["model"]
    if m == "VASICEK":
        return ql.Vasicek(inp["short_rate"], inp["mean_reversion"], inp["long_term_mean"], inp["sigma"], 0.0)
    if m == "CIR":
        return ql.CoxIngersollRoss(inp["short_rate"], inp["long_term_mean"], inp["mean_reversion"], inp["sigma"])
    return ql.HullWhite(ql_curve(inp["curve"]), inp["mean_reversion"], inp["sigma"])


def ql_zcb(inp):
    return ql_model(inp).discountBond(inp["t_years"], inp["maturity_years"], inp["short_rate"])


def ql_bonds(inp):
    if inp["model"] == "HULL_WHITE":
        h = ql_curve(inp["curve"])
        return h.discount(inp["expiry_years"]), h.discount(inp["maturity_years"])
    m = ql_model(inp)
    return m.discountBond(0.0, inp["expiry_years"], inp["short_rate"]), m.discountBond(0.0, inp["maturity_years"], inp["short_rate"])


def ql_opt(inp):
    t = ql.Option.Call if inp["option_type"] == "CALL" else ql.Option.Put
    return inp["notional"] * ql_model(inp).discountBondOption(t, inp["strike"], inp["expiry_years"], inp["maturity_years"])


# ------------------------------------------------------------------------------------------------ cases
CURVE = {"times": [d / 365 for d in (182, 365, 730, 1095, 1826, 2557, 3652, 5479, 7305, 10957)],
         "discount_factors": [0.98085, 0.96190, 0.92540, 0.89060, 0.82420, 0.76200, 0.67870, 0.56100, 0.46700, 0.33200]}
NEG = {"times": [d / 365 for d in (365, 1826, 3652)], "discount_factors": [1.0045, 1.0080, 0.9950]}


def zcb_value(inp, mut=None):
    m, t, T = inp["model"], inp["t_years"], inp["maturity_years"]
    if m == "VASICEK":
        lnA, B = vas_AB(inp["mean_reversion"], inp["long_term_mean"], inp["sigma"], T - t, drop_conv=mut == "vas_conv")
        P = mp.exp(lnA - B * inp["short_rate"])
    elif m == "CIR":
        lnA, B = cir_AB(inp["mean_reversion"], inp["long_term_mean"], inp["sigma"], T - t, gamma_mut=mut == "cir_gamma")
        P = mp.exp(lnA - B * inp["short_rate"])
    else:
        P, B = hw_bond(Curve(**inp["curve"]), inp["mean_reversion"], inp["sigma"], t, T, inp["short_rate"],
                       drop_var=mut == "hw_var")
    tau = mp.mpf(T) - mp.mpf(t)
    return {"discount_factor": float(P), "zero_rate": float(-mp.log(P) / tau)}


def opt_value(inp, mut=None):
    m, T, S, K, typ = inp["model"], inp["expiry_years"], inp["maturity_years"], inp["strike"], inp["option_type"]
    if m == "CIR":
        v, PT, PS = cir_opt(typ, inp["mean_reversion"], inp["long_term_mean"], inp["sigma"], inp["short_rate"], K, T, S)
        out = {"price": v}
    else:
        if m == "VASICEK":
            f = lambda x: vas_AB(inp["mean_reversion"], inp["long_term_mean"], inp["sigma"], x)  # noqa: E731
            PT, PS = (mp.exp(f(x)[0] - f(x)[1] * inp["short_rate"]) for x in (T, S))
        else:
            cv = Curve(**inp["curve"])
            PT, PS = cv.P(T), cv.P(S)
        sp = sigma_p(inp["mean_reversion"], inp["sigma"], T, S, ho_lee=mut == "ho_lee")
        out = {"price": gauss_opt(typ, PT, PS, mp.mpf(K), sp)}
    out["price"] *= inp["notional"]
    out.update(bond_price_expiry=PT, bond_price_maturity=PS)
    return {k: float(v) for k, v in out.items()}


def close(a, b):
    return abs(a - b) <= 1e-12 + 1e-10 * abs(b)


def main():
    s = Suite("shortrate_g", "specifications/04-pricing/short-rate-models.md", G)
    vas = dict(model="VASICEK", mean_reversion=0.15, long_term_mean=0.045, sigma=0.012)
    cir = dict(model="CIR", mean_reversion=0.25, long_term_mean=0.04, sigma=0.08)
    hw = dict(model="HULL_WHITE", mean_reversion=0.05, sigma=0.01, curve=CURVE)
    zcb_cases = []
    for base, rs in ((vas, (0.035, -0.01, 0.0)), (cir, (0.03, 0.0005)), (hw, (0.04, -0.005))):
        for r in rs:
            for t, T in ((0.0, 1.0), (0.0, 10.0), (2.1, 7.5), (0.0, 30.0), (0.25, 0.26)):
                zcb_cases.append(dict(base, short_rate=r, t_years=t, maturity_years=T))
    zcb_cases.append(dict(vas, mean_reversion=1e-4, short_rate=0.03, t_years=0.0, maturity_years=5.0))  # small a
    zcb_cases.append(dict(hw, short_rate=0.04, t_years=2.0, maturity_years=7.5))  # t on a pillar: right-hand forward (G-3)
    zcb_cases.append(dict(hw, curve=NEG, short_rate=-0.004, t_years=1.5, maturity_years=6.0))  # negative rates
    for inp in zcb_cases:
        out = zcb_value(inp)
        ver = ["mpmath-50"]
        q = ql_zcb(inp)
        if close(q, out["discount_factor"]):
            ver.append("quantlib-1.44")
            OUTSIDE.append(1)
        else:
            note(f"  QL zcb differs: {inp} {q} {out['discount_factor']}")
            OUTSIDE.append(0)
        s.add(ZCB, inp, out, cls=A, verified=ver, tags=["shortrate", inp["model"].lower()],
              description=f"{inp['model']} P(t={inp['t_years']}, T={inp['maturity_years']} | r={inp['short_rate']})")
    opt_cases = []
    for base, extra in ((vas, dict(short_rate=0.035)), (cir, dict(short_rate=0.03)), (hw, {})):
        for typ in ("CALL", "PUT"):
            for T, S, K in ((1.0, 5.0, 0.86), (2.0, 3.0, 0.97), (5.0, 10.0, 0.80), (0.5, 20.0, 0.50)):
                opt_cases.append(dict(base, **extra, option_type=typ, strike=K, expiry_years=T, maturity_years=S,
                                      notional=1e6))
    opt_cases.append(dict(hw, curve=NEG, option_type="CALL", strike=1.0, expiry_years=1.0, maturity_years=5.0,
                          notional=1e6))  # negative-rate HW: strike at par
    for inp in opt_cases:
        out = opt_value(inp)
        ver = ["mpmath-50", "put-call-parity"]
        q = ql_opt(inp)
        qb = ql_bonds(inp)
        if abs(q - out["price"]) <= 1e-6 + 1e-9 * abs(out["price"]) and close(qb[0], out["bond_price_expiry"]) and close(qb[1], out["bond_price_maturity"]):
            ver.append("quantlib-1.44")
            OUTSIDE.append(1)
        else:
            note(f"  QL opt differs: {inp['model']} {inp['option_type']} {q} {out['price']}")
            OUTSIDE.append(0)
        s.add(OPT, inp, out, cls=R if inp["model"] == "CIR" else A, verified=ver,
              tags=["shortrate", inp["model"].lower(), inp["option_type"].lower()],
              limit={"absolute": 1e-6, "relative": 1e-9, "reason": "1e-12 per unit notional"},
              description=f"{inp['model']} {inp['option_type']} on ZCB, T={inp['expiry_years']}, S={inp['maturity_years']}, K={inp['strike']}")
    # mutants
    b0 = dict(vas, short_rate=0.035, t_years=0.0, maturity_years=10.0)
    caught("vasicek without -sigma^2 B^2/(4a)", abs(zcb_value(b0)["discount_factor"] - zcb_value(b0, "vas_conv")["discount_factor"]))
    b1 = dict(cir, short_rate=0.03, t_years=0.0, maturity_years=10.0)
    caught("cir gamma with sigma^2 not 2 sigma^2", abs(zcb_value(b1)["discount_factor"] - zcb_value(b1, "cir_gamma")["discount_factor"]))
    b2 = dict(hw, short_rate=0.04, t_years=2.0, maturity_years=7.5)
    caught("hull-white without the variance term", abs(zcb_value(b2)["discount_factor"] - zcb_value(b2, "hw_var")["discount_factor"]))
    b3 = dict(hw, option_type="CALL", strike=0.86, expiry_years=1.0, maturity_years=5.0, notional=1e6)
    caught("ho-lee sigma_p", abs(opt_value(b3)["price"] - opt_value(b3, "ho_lee")["price"]), 1e-6)
    # errors (all fixed by the spec's check order)
    e = dict(vas, short_rate=0.03, t_years=0.0, maturity_years=5.0)
    errs = [(ZCB, dict(e, mean_reversion=0.0), "E_DOMAIN", "a = 0"),
            (ZCB, dict(e, sigma=-0.01), "E_DOMAIN", "sigma < 0"),
            (ZCB, dict(e, maturity_years=0.0), "E_DOMAIN", "T = t"),
            (ZCB, dict(e, t_years=-1.0), "E_DOMAIN", "t < 0"),
            (ZCB, dict(e, model="G2PP"), "E_INPUT", "unknown model"),
            (ZCB, dict(cir, short_rate=-0.01, t_years=0.0, maturity_years=5.0), "E_DOMAIN", "CIR r < 0"),
            (ZCB, dict(cir, long_term_mean=0.0, short_rate=0.01, t_years=0.0, maturity_years=5.0), "E_DOMAIN", "CIR b = 0"),
            (ZCB, dict(hw, short_rate=0.01, t_years=0.0, maturity_years=5.0, curve={"times": [1.0, 0.5], "discount_factors": [0.99, 0.98]}), "E_INPUT", "pillar times not increasing"),
            (ZCB, dict(hw, short_rate=0.01, t_years=0.0, maturity_years=5.0, curve={"times": [1.0], "discount_factors": [0.0]}), "E_DOMAIN", "df <= 0"),
            (ZCB, dict(vas, t_years=0.0, maturity_years=5.0), "E_SCHEMA", "short_rate missing"),
            (OPT, dict(vas, short_rate=0.03, option_type="CALL", strike=0.9, expiry_years=5.0, maturity_years=5.0, notional=1.0), "E_DOMAIN", "expiry = maturity"),
            (OPT, dict(vas, short_rate=0.03, option_type="CALL", strike=0.0, expiry_years=1.0, maturity_years=5.0, notional=1.0), "E_DOMAIN", "strike = 0"),
            (OPT, dict(vas, short_rate=0.03, option_type="CALL", strike=0.9, expiry_years=0.0, maturity_years=5.0, notional=1.0), "E_DOMAIN", "expiry = 0"),
            (OPT, dict(hw, short_rate=0.03, option_type="CALL", strike=0.9, expiry_years=1.0, maturity_years=5.0, notional=1.0), "E_INPUT", "short_rate given for HULL_WHITE"),
            (OPT, dict(vas, short_rate=0.03, option_type="STRADDLE", strike=0.9, expiry_years=1.0, maturity_years=5.0, notional=1.0), "E_INPUT", "unknown option_type")]
    for op, inp, code, d in errs:
        s.add(op, inp, error=code, cls="date_and_convention", tags=["invalid", "shortrate"], description=d)
        OUTSIDE.append(0)
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    n_out = sum(OUTSIDE)
    note(f"outside (QuantLib 1.44, own model objects): {n_out} of {len(OUTSIDE)} = {100 * n_out / len(OUTSIDE):.1f}%")
    for m, g in MUTANTS:
        note(f"  mutant caught: {m} (gap {g:.3e})")
    (HERE.parent / "outside_register_g.json").write_text(json.dumps(
        {"suite": "shortrate_g", "library": "QuantLib 1.44", "counted": n_out, "total": len(OUTSIDE),
         "rule": "11.2.5 and G-4: every output is a QuantLib value (discountBond, discountBondOption, the curve discount) or plain arithmetic on one (zero_rate)"},
        indent=1) + "\n", encoding="utf-8")


# ================================================================================================ R9 discrete barrier
BGK = 0.5826  # Broadie-Glasserman-Kou beta, as written in plan 13.3 R9 (ruling G-7); -zeta(1/2)/sqrt(2 pi) = 0.58259715...
BAR = "exotic.barrier.price"
PATHS = 40000


def bgk_barrier(btype, H, v, dt, beta=BGK):
    return H * math.exp((-1 if btype.startswith("DOWN") else 1) * beta * v * math.sqrt(dt))


def r9_dt(inp):
    """R5 M3 (ruling G-30): n = floor(m T + 0.5) observation dates, n >= 1, step dt = T / n."""
    n = math.floor(inp["monitoring_per_year"] * inp["expiry_years"] + 0.5)
    assert n >= 1
    return inp["expiry_years"] / n


def r9_price(inp, mut=None):
    from gen_stage_e_a import barrier
    H = inp["barrier"]
    if inp.get("monitoring", "CONTINUOUS") == "DISCRETE":
        if mut == "sign":
            H = bgk_barrier("UP" if inp["barrier_type"].startswith("DOWN") else "DOWN", H, inp["vol"], r9_dt(inp))
        else:
            H = bgk_barrier(inp["barrier_type"], H, inp["vol"], r9_dt(inp))
    return barrier(inp["barrier_type"], inp["option_type"], inp["spot"], inp["strike"], H, inp["rebate"],
                   inp["expiry_years"], inp["rate"], inp["dividend_yield"], inp["vol"])


def ql_barrier(inp):
    bt = {"DOWN_OUT": ql.Barrier.DownOut, "DOWN_IN": ql.Barrier.DownIn, "UP_OUT": ql.Barrier.UpOut, "UP_IN": ql.Barrier.UpIn}
    ex = TODAY + int(round(inp["expiry_years"] * 365))
    opt = ql.BarrierOption(bt[inp["barrier_type"]], inp["barrier"], inp["rebate"],
                           ql.PlainVanillaPayoff(ql.Option.Call if inp["option_type"] == "CALL" else ql.Option.Put, inp["strike"]),
                           ql.EuropeanExercise(ex))
    ts = lambda r: ql.YieldTermStructureHandle(ql.FlatForward(TODAY, r, DC))  # noqa: E731
    proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(inp["spot"])), ts(inp["dividend_yield"]), ts(inp["rate"]),
                                        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(TODAY, ql.NullCalendar(), inp["vol"], DC)))
    opt.setPricingEngine(ql.AnalyticBarrierEngine(proc))
    return opt.NPV()


def r9_mc(inp, paths, seed=20261109):
    """Exact GBM at each monitoring date (no time-step error), knocked out if S <= H at any date; core.rng draws."""
    import numpy as np
    from scipy.special import ndtri
    from qf_oracle.rng import Xo
    m, T = inp["monitoring_per_year"], inp["expiry_years"]
    n = int(round(m * T))
    dt = T / n
    g = Xo(seed=seed)
    u = np.array([((g.next() >> 12) + 0.5) * 2.0 ** -52 for _ in range(paths * n)]).reshape(paths, n)
    z = ndtri(u)
    v, r, q = inp["vol"], inp["rate"], inp["dividend_yield"]
    lnS = math.log(inp["spot"]) + np.cumsum((r - q - v * v / 2) * dt + v * math.sqrt(dt) * z, axis=1)
    alive = (lnS > math.log(inp["barrier"])).all(axis=1)
    ST = np.exp(lnS[:, -1])
    pay = np.where(alive, np.maximum(ST - inp["strike"], 0) if inp["option_type"] == "CALL" else np.maximum(inp["strike"] - ST, 0), 0.0)
    disc = math.exp(-r * T)
    return disc * pay.mean(), disc * pay.std(ddof=1) / math.sqrt(paths)


def r9():
    s = Suite("barrier_g", "specifications/04-pricing/exotics.md", G)
    base = dict(spot=100.0, strike=100.0, expiry_years=1.0, rate=0.05, dividend_yield=0.02, vol=0.25, rebate=0.0)
    rows = []
    for bt, H in (("DOWN_OUT", 90.0), ("DOWN_IN", 90.0), ("UP_OUT", 120.0), ("UP_IN", 120.0)):
        for ot in ("CALL", "PUT"):
            for m in (252, 52, 12):
                rows.append(dict(base, barrier=H, barrier_type=bt, option_type=ot, monitoring="DISCRETE", monitoring_per_year=m))
    rows.append(dict(base, barrier=95.0, barrier_type="DOWN_OUT", option_type="CALL", rebate=3.0, monitoring="DISCRETE", monitoring_per_year=252))
    rows.append(dict(base, barrier=90.0, barrier_type="DOWN_OUT", option_type="CALL", monitoring="CONTINUOUS"))
    rows.append(dict(base, barrier=90.0, barrier_type="DOWN_OUT", option_type="CALL"))  # monitoring absent = CONTINUOUS
    n_out = 0
    for inp in rows:
        ver = ["closed-form-bgk"]
        if inp.get("monitoring", "CONTINUOUS") == "CONTINUOUS":
            q = ql_barrier(inp)
            assert abs(q - r9_price(inp)) <= 1e-10 * abs(q) + 1e-12, (q, r9_price(inp))
            ver = ["closed-form", "quantlib-1.44"]
            n_out += 1
        s.add(BAR, inp, {"price": r9_price(inp)}, verified=ver,
              tags=["barrier", "r9", inp.get("monitoring", "CONTINUOUS").lower()],
              description=f"{inp['barrier_type']} {inp['option_type']} H={inp['barrier']} m={inp.get('monitoring_per_year', 'cont')}")
    # in-out parity on the shifted barrier (no rebate)
    errs = [(dict(base, barrier=90.0, barrier_type="DOWN_OUT", option_type="CALL", monitoring="DISCRETE"), "E_INPUT", "DISCRETE without monitoring_per_year"),
            (dict(base, barrier=90.0, barrier_type="DOWN_OUT", option_type="CALL", monitoring="CONTINUOUS", monitoring_per_year=252), "E_INPUT", "monitoring_per_year with CONTINUOUS"),
            (dict(base, barrier=90.0, barrier_type="DOWN_OUT", option_type="CALL", monitoring="DISCRETE", monitoring_per_year=0), "E_DOMAIN", "monitoring_per_year = 0"),
            (dict(base, barrier=90.0, barrier_type="DOWN_OUT", option_type="CALL", monitoring="WEEKLY", monitoring_per_year=52), "E_INPUT", "unknown monitoring"),
            (dict(base, barrier=101.0, barrier_type="DOWN_OUT", option_type="CALL", monitoring="DISCRETE", monitoring_per_year=252), "E_DOMAIN", "spot below the unshifted down barrier")]
    for inp, code, d in errs:
        s.add(BAR, inp, error=code, cls="date_and_convention", tags=["invalid", "r9"], description=d)
    # R5 M3 (ruling G-30), appended to keep ids: non-unit T, non-integer and tie m T, UP_* with rebate, n = 0
    m3 = [dict(base, expiry_years=0.3, barrier=90.0, barrier_type="DOWN_OUT", option_type="CALL", monitoring="DISCRETE", monitoring_per_year=252),
          dict(base, expiry_years=0.5, barrier=90.0, barrier_type="DOWN_OUT", option_type="PUT", monitoring="DISCRETE", monitoring_per_year=3),
          dict(base, expiry_years=0.75, barrier=115.0, barrier_type="UP_OUT", option_type="CALL", rebate=2.0, monitoring="DISCRETE", monitoring_per_year=10),
          dict(base, expiry_years=1.5, barrier=120.0, barrier_type="UP_IN", option_type="PUT", rebate=1.5, monitoring="DISCRETE", monitoring_per_year=52)]
    for inp in m3:
        n = math.floor(inp["monitoring_per_year"] * inp["expiry_years"] + 0.5)
        s.add(BAR, inp, {"price": r9_price(inp)}, verified=["closed-form-bgk"], tags=["barrier", "r9", "discrete", "m3"],
              description=f"{inp['barrier_type']} {inp['option_type']} T={inp['expiry_years']} m={inp['monitoring_per_year']}: n={n}, dt=T/n")
    s.add(BAR, dict(base, expiry_years=0.3, barrier=90.0, barrier_type="DOWN_OUT", option_type="CALL", monitoring="DISCRETE", monitoring_per_year=1),
          error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "r9"], description="n = floor(m T + 0.5) = 0")
    a = rows[0]
    caught("BGK shift with the wrong sign", abs(r9_price(a) - r9_price(a, "sign")), 1e-6)
    caught("continuous price for a daily barrier", abs(r9_price(a) - r9_price(dict(a, monitoring="CONTINUOUS"))), 1e-6)
    # acceptance (plan 13.3 R9): daily-monitored down-and-out against exact-date MC within 3 SE
    accept = []
    for ot in ("CALL", "PUT"):
        inp = dict(rows[0], option_type=ot)
        mc, se = r9_mc(inp, PATHS)
        bgk = r9_price(inp)
        z = (bgk - mc) / se
        note(f"R9 acceptance {ot}: BGK {bgk:.6f}, MC {mc:.6f} +- {se:.6f}, z = {z:+.2f}, continuous {r9_price(dict(inp, monitoring='CONTINUOUS')):.6f}")
        assert abs(z) <= 3, "R9 acceptance fails"
        accept.append({"option_type": ot, "bgk": bgk, "mc": mc, "se": se, "z": z, "paths": 40000, "seed": 20261109})
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    note(f"barrier_g outside (QuantLib 1.44 AnalyticBarrierEngine): {n_out} of {len(s.cases)}")
    reg = HERE.parent / "outside_register_g.json"
    d = json.loads(reg.read_text(encoding="utf-8"))
    d["barrier_g"] = {"counted": n_out, "total": len(s.cases), "rule": "continuous-monitoring rows only; the BGK rows have MC evidence, not an outside library value"}
    reg.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")
    (HERE.parent / "R9_ACCEPTANCE.json").write_text(json.dumps(accept, indent=1) + chr(10), encoding="utf-8")

# ================================================================================================ G2a Jamshidian swaption
SWO = "rates.shortrate.swaption"


def jam_price(inp, mut=None):
    cv, a, sg = Curve(**inp["curve"]), inp["mean_reversion"], inp["sigma"]
    T0 = mp.mpf(inp["expiry_years"])
    Ts = [mp.mpf(x) for x in inp["payment_times"]]
    K = mp.mpf(inp["fixed_rate"])
    acc = [Ts[0] - T0] + [Ts[i] - Ts[i - 1] for i in range(1, len(Ts))]
    c = [K * x for x in acc]
    c[-1] += 1
    f = lambda r: sum(ci * hw_bond(cv, a, sg, T0, Ti, r)[0] for ci, Ti in zip(c, Ts)) - 1  # noqa: E731
    rs = mp.findroot(f, 0.0, tol=mp.mpf(10) ** -45)
    typ = "CALL" if inp["swaption_type"] == "RECEIVER" else "PUT"
    v = mp.mpf(0)
    for ci, Ti in zip(c, Ts):
        X = hw_bond(cv, a, sg, T0, Ti, rs)[0]
        sp = sigma_p(a, sg, T0, Ti, ho_lee=mut == "ho_lee")
        v += ci * gauss_opt(typ, cv.P(T0), cv.P(Ti), X if mut != "strike_one" else mp.mpf(1), sp)
    ann = sum(x * cv.P(Ti) for x, Ti in zip(acc, Ts))
    return {"price": float(inp["notional"] * v), "forward_swap_rate": float((cv.P(T0) - cv.P(Ts[-1])) / ann),
            "annuity": float(inp["notional"] * ann)}


def ql_jam(inp):
    """QuantLib's own HullWhite: r* by Brent on HullWhite.discountBond to 1e-15, then the sum of discountBondOption."""
    m = ql.HullWhite(ql_curve(inp["curve"]), inp["mean_reversion"], inp["sigma"])
    T0, Ts, K = inp["expiry_years"], inp["payment_times"], inp["fixed_rate"]
    acc = [Ts[0] - T0] + [Ts[i] - Ts[i - 1] for i in range(1, len(Ts))]
    c = [K * x for x in acc]
    c[-1] += 1
    f = lambda r: sum(ci * m.discountBond(T0, Ti, r) for ci, Ti in zip(c, Ts)) - 1  # noqa: E731
    rs = ql.Brent().solve(f, 1e-15, 0.0, -0.5, 0.5)
    t = ql.Option.Call if inp["swaption_type"] == "RECEIVER" else ql.Option.Put
    v = sum(ci * m.discountBondOption(t, m.discountBond(T0, Ti, rs), T0, Ti) for ci, Ti in zip(c, Ts))
    h = ql_curve(inp["curve"])
    ann = sum(x * h.discount(Ti) for x, Ti in zip(acc, Ts))
    return {"price": inp["notional"] * v, "forward_swap_rate": (h.discount(T0) - h.discount(Ts[-1])) / ann,
            "annuity": inp["notional"] * ann}


def g2a():
    s = Suite("swaption_g", "specifications/04-pricing/short-rate-models.md", G)
    hw = dict(mean_reversion=0.05, sigma=0.01, curve=CURVE, notional=1e6)
    rows = []
    for T0, n in ((1.0, 5), (2.0, 10), (5.0, 5), (10.0, 20), (0.5, 2)):
        Ts = [T0 + k for k in range(1, n + 1)]
        base = dict(hw, expiry_years=T0, payment_times=Ts)
        fwd = jam_price(dict(base, fixed_rate=0.03, swaption_type="PAYER"))["forward_swap_rate"]
        for K in (round(fwd - 0.01, 6), round(fwd, 6), round(fwd + 0.01, 6)):
            for st in ("PAYER", "RECEIVER"):
                rows.append(dict(base, fixed_rate=K, swaption_type=st))
    semi = [1.0 + 0.5 * k for k in range(1, 11)]
    rows.append(dict(hw, expiry_years=1.0, payment_times=semi, fixed_rate=0.04, swaption_type="PAYER"))
    rows.append(dict(hw, mean_reversion=0.5, sigma=0.02, expiry_years=2.0, payment_times=[3.0, 4.0, 5.0], fixed_rate=0.04, swaption_type="RECEIVER"))
    rows.append(dict(hw, curve=NEG, expiry_years=1.0, payment_times=[2.0, 3.0, 4.0, 5.0], fixed_rate=0.0, swaption_type="PAYER"))
    n_out = 0
    for inp in rows:
        out = jam_price(inp)
        q = ql_jam(inp)
        ok = all(abs(q[k] - out[k]) <= 1e-6 + 1e-10 * abs(out[k]) for k in ("price", "annuity")) and close(q["forward_swap_rate"], out["forward_swap_rate"])
        ver = ["mpmath-50", "payer-receiver-parity"] + (["quantlib-1.44"] if ok else [])
        n_out += ok
        if not ok:
            note(f"  QL swaption differs: {q} {out}")
        s.add(SWO, inp, out, cls=R, verified=ver, tags=["shortrate", "jamshidian", inp["swaption_type"].lower()],
              limit={"absolute": 1e-6, "relative": 1e-9, "reason": "1e-12 per unit notional"},
              description=f"HW {inp['swaption_type']} {inp['expiry_years']}y into {len(inp['payment_times'])} periods, K={inp['fixed_rate']}")
    # payer - receiver = annuity (F - K) (asserted on the goldens)
    for i in range(0, 30, 2):
        p, r = s.cases[i]["expected"]["outputs"], s.cases[i + 1]["expected"]["outputs"]
        K = s.cases[i]["inputs"]["fixed_rate"]
        assert abs(p["price"] - r["price"] - p["annuity"] * (p["forward_swap_rate"] - K)) < 1e-8
    b = rows[2]
    caught("ho-lee sigma_p in Jamshidian", abs(jam_price(b)["price"] - jam_price(b, "ho_lee")["price"]), 1e-6)
    caught("strike 1 for every bond option", abs(jam_price(b)["price"] - jam_price(b, "strike_one")["price"]), 1e-6)
    e = dict(hw, expiry_years=1.0, payment_times=[2.0, 3.0], fixed_rate=0.03, swaption_type="PAYER")
    errs = [(dict(e, payment_times=[3.0, 2.0]), "E_INPUT", "payment times not increasing"),
            (dict(e, payment_times=[1.0, 2.0]), "E_INPUT", "first payment on expiry"),
            (dict(e, payment_times=[]), "E_INPUT", "no payments"),
            (dict(e, expiry_years=0.0), "E_DOMAIN", "expiry = 0"),
            (dict(e, swaption_type="STRADDLE"), "E_INPUT", "unknown swaption_type"),
            (dict(e, sigma=0.0), "E_DOMAIN", "sigma = 0"),
            (dict(e, short_rate=0.01), "E_INPUT", "short_rate given")]
    for inp, code, d in errs:
        s.add(SWO, inp, error=code, cls="date_and_convention", tags=["invalid", "jamshidian"], description=d)
    # R5 M2 (ruling G-29): small negative strike (value), and the limit 1 + K tau_n <= 0 (E_DOMAIN); appended to keep ids
    for st in ("PAYER", "RECEIVER"):
        inp = dict(hw, expiry_years=1.0, payment_times=[2.0, 3.0, 4.0, 5.0], fixed_rate=-0.002, swaption_type=st)
        out = jam_price(inp)
        q = ql_jam(inp)
        ok = all(abs(q[k] - out[k]) <= 1e-6 + 1e-10 * abs(out[k]) for k in ("price", "annuity"))
        n_out += ok
        s.add(SWO, inp, out, cls=R, verified=["mpmath-50"] + (["quantlib-1.44"] if ok else []), tags=["shortrate", "jamshidian", "negative-strike", st.lower()],
              limit={"absolute": 1e-6, "relative": 1e-9, "reason": "1e-9 relative"}, description=f"HW {st} K=-0.2%: negative coupons, root still unique")
    s.add(SWO, dict(e, fixed_rate=-1.0), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "jamshidian"], description="1 + K tau_n = 0")
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    note(f"swaption_g outside (QuantLib 1.44 HullWhite objects): {n_out} of {len(s.cases)}")
    reg = HERE.parent / "outside_register_g.json"
    d = json.loads(reg.read_text(encoding="utf-8"))
    d["swaption_g"] = {"counted": n_out, "total": len(s.cases), "rule": "QuantLib HullWhite discountBond and discountBondOption, r* by QuantLib Brent to 1e-15, combined by arithmetic; DiscountCurve discounts for the annuity and forward"}
    reg.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")


# ================================================================================================ G2b G2++
G2Z, G2O = "rates.g2pp.zcb", "rates.g2pp.zcb_option"


def g2_V(a, sg, b, et, rho, tau):
    a, sg, b, et, rho, tau = map(mp.mpf, (a, sg, b, et, rho, tau))
    va = sg ** 2 / a ** 2 * (tau + 2 / a * mp.exp(-a * tau) - 1 / (2 * a) * mp.exp(-2 * a * tau) - 3 / (2 * a))
    vb = et ** 2 / b ** 2 * (tau + 2 / b * mp.exp(-b * tau) - 1 / (2 * b) * mp.exp(-2 * b * tau) - 3 / (2 * b))
    vab = 2 * rho * sg * et / (a * b) * (tau + (mp.exp(-a * tau) - 1) / a + (mp.exp(-b * tau) - 1) / b
                                         - (mp.exp(-(a + b) * tau) - 1) / (a + b))
    return va + vb + vab


def g2_zcb(inp, mut=None):
    cv = Curve(**inp["curve"])
    a, sg, b, et, rho = (inp[k] for k in ("a", "sigma", "b", "eta", "rho"))
    t, T, x, y = (mp.mpf(inp[k]) for k in ("t_years", "maturity_years", "x", "y"))
    half = (g2_V(a, sg, b, et, rho, T - t) - g2_V(a, sg, b, et, rho, T) + g2_V(a, sg, b, et, rho, t)) / 2
    if mut == "no_half":
        half *= 2
    P = cv.P(T) / cv.P(t) * mp.exp(half - (1 - mp.exp(-a * (T - t))) / a * x - (1 - mp.exp(-b * (T - t))) / b * y)
    return {"discount_factor": float(P), "zero_rate": float(-mp.log(P) / (T - t))}


def g2_opt(inp, mut=None):
    cv = Curve(**inp["curve"])
    a, sg, b, et, rho = (mp.mpf(inp[k]) for k in ("a", "sigma", "b", "eta", "rho"))
    T, S, K = (mp.mpf(inp[k]) for k in ("expiry_years", "maturity_years", "strike"))
    if mut == "rho_sign":
        rho = -rho
    S2 = (sg ** 2 / (2 * a ** 3) * (1 - mp.exp(-a * (S - T))) ** 2 * (1 - mp.exp(-2 * a * T))
          + et ** 2 / (2 * b ** 3) * (1 - mp.exp(-b * (S - T))) ** 2 * (1 - mp.exp(-2 * b * T))
          + 2 * rho * sg * et / (a * b * (a + b)) * (1 - mp.exp(-a * (S - T))) * (1 - mp.exp(-b * (S - T))) * (1 - mp.exp(-(a + b) * T)))
    PT, PS = cv.P(T), cv.P(S)
    v = gauss_opt(inp["option_type"], PT, PS, K, mp.sqrt(S2)) * inp["notional"]
    return {"price": float(v), "bond_price_expiry": float(PT), "bond_price_maturity": float(PS)}


def ql_g2(inp):
    return ql.G2(ql_curve(inp["curve"]), inp["a"], inp["sigma"], inp["b"], inp["eta"], inp["rho"])


def g2b():
    s = Suite("g2pp_g", "specifications/04-pricing/short-rate-models.md", G)
    pars = [dict(a=0.5, sigma=0.01, b=0.05, eta=0.008, rho=-0.75), dict(a=0.1, sigma=0.012, b=0.8, eta=0.01, rho=0.3),
            dict(a=0.2, sigma=0.015, b=0.03, eta=0.006, rho=0.0)]
    n_out = 0
    for pr in pars:
        for t, T, x, y in ((0.0, 5.0, 0.0, 0.0), (1.5, 7.5, 0.004, -0.002), (2.5, 30.0, -0.01, 0.006), (0.3, 0.31, 0.002, 0.001)):
            inp = dict(pr, curve=CURVE, t_years=t, maturity_years=T, x=x, y=y)
            out = g2_zcb(inp)
            q = ql_g2(inp).discountBond(t, T, ql.Array([x, y]))
            ok = close(q, out["discount_factor"])
            n_out += ok
            if not ok:
                note(f"  QL g2 zcb differs: {q} {out}")
            s.add(G2Z, inp, out, verified=["mpmath-50"] + (["quantlib-1.44"] if ok else []), tags=["g2pp"],
                  description=f"G2++ P(t={t}, T={T} | x={x}, y={y})")
        for typ in ("CALL", "PUT"):
            for T, S, K in ((1.0, 5.0, 0.86), (5.0, 10.0, 0.80), (0.5, 20.0, 0.50)):
                inp = dict(pr, curve=CURVE, option_type=typ, strike=K, expiry_years=T, maturity_years=S, notional=1e6)
                out = g2_opt(inp)
                q = 1e6 * ql_g2(inp).discountBondOption(ql.Option.Call if typ == "CALL" else ql.Option.Put, K, T, S)
                ok = abs(q - out["price"]) <= 1e-6 + 1e-9 * abs(out["price"])
                n_out += ok
                if not ok:
                    note(f"  QL g2 opt differs: {q} {out}")
                s.add(G2O, inp, out, verified=["mpmath-50", "put-call-parity"] + (["quantlib-1.44"] if ok else []),
                      tags=["g2pp", typ.lower()], limit={"absolute": 1e-6, "relative": 1e-9, "reason": "1e-12 per unit notional"},
                      description=f"G2++ {typ} on ZCB T={T} S={S} K={K}")
    # one-factor limit: eta -> 0 recovers Hull-White (asserted, and a golden)
    lim = dict(a=0.05, sigma=0.01, b=0.3, eta=1e-12, rho=0.0, curve=CURVE, option_type="CALL", strike=0.86, expiry_years=1.0, maturity_years=5.0, notional=1e6)
    hwv = opt_value(dict(model="HULL_WHITE", mean_reversion=0.05, sigma=0.01, curve=CURVE, option_type="CALL", strike=0.86, expiry_years=1.0, maturity_years=5.0, notional=1e6))["price"]
    assert abs(g2_opt(lim)["price"] - hwv) < 1e-6
    s.add(G2O, lim, g2_opt(lim), verified=["mpmath-50", "hull-white-limit"], tags=["g2pp", "limit"],
          limit={"absolute": 1e-6, "relative": 1e-9, "reason": "1e-12 per unit notional"}, description="eta near 0: the Hull-White price")
    b0 = dict(pars[0], curve=CURVE, t_years=1.5, maturity_years=7.5, x=0.004, y=-0.002)
    caught("G2++ without the 1/2 on the variance terms", abs(g2_zcb(b0)["discount_factor"] - g2_zcb(b0, "no_half")["discount_factor"]))
    b1 = dict(pars[0], curve=CURVE, option_type="CALL", strike=0.86, expiry_years=1.0, maturity_years=5.0, notional=1e6)
    caught("G2++ cross term with the wrong sign", abs(g2_opt(b1)["price"] - g2_opt(b1, "rho_sign")["price"]), 1e-6)
    e = dict(pars[0], curve=CURVE, t_years=0.0, maturity_years=5.0, x=0.0, y=0.0)
    eo = dict(pars[0], curve=CURVE, option_type="CALL", strike=0.9, expiry_years=1.0, maturity_years=5.0, notional=1.0)
    errs = [(G2Z, dict(e, rho=1.0), "E_DOMAIN", "rho = 1"), (G2Z, dict(e, rho=-1.2), "E_DOMAIN", "rho < -1"),
            (G2Z, dict(e, a=0.0), "E_DOMAIN", "a = 0"), (G2Z, dict(e, eta=0.0), "E_DOMAIN", "eta = 0"),
            (G2Z, dict(e, maturity_years=0.0), "E_DOMAIN", "T = t"), (G2O, dict(eo, expiry_years=5.0), "E_DOMAIN", "expiry = maturity"),
            (G2O, dict(eo, x=0.0), "E_INPUT", "state given to the option")]
    for op, inp, code, d in errs:
        s.add(op, inp, error=code, cls="date_and_convention", tags=["invalid", "g2pp"], description=d)
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    note(f"g2pp_g outside (QuantLib 1.44 G2): {n_out} of {len(s.cases)}")
    reg = HERE.parent / "outside_register_g.json"
    d = json.loads(reg.read_text(encoding="utf-8"))
    d["g2pp_g"] = {"counted": n_out, "total": len(s.cases), "rule": "QuantLib G2 discountBond and discountBondOption on a DiscountCurve; zero_rate and the curve discounts as arithmetic or curve values"}
    reg.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")


# ================================================================================================ G5a swap EE and CVA under Hull-White
EEOP = "xva.exposure.swap_ee_hw"


def ee_profile(inp, mut=None):
    """Discounted EE of a fixed-for-floating swap at its reset dates: the European swaption on the remaining swap."""
    T0, Ts = inp["start_years"], inp["payment_times"]
    resets = [T0] + Ts[:-1]
    st = "PAYER" if inp["side"] == "PAY" else "RECEIVER"
    if mut == "side":
        st = "RECEIVER" if st == "PAYER" else "PAYER"
    out = []
    for t in inp["exposure_times"]:
        k = resets.index(t)
        rest = Ts[k:]
        out.append(dict(mean_reversion=inp["mean_reversion"], sigma=inp["sigma"], curve=inp["curve"], notional=inp["notional"],
                        expiry_years=t, payment_times=rest, fixed_rate=inp["fixed_rate"], swaption_type=st))
    return out


def cva_from(ee, times, h, R):
    surv = [1.0] + [math.exp(-h * t) for t in times]
    return (1 - R) * math.fsum(e * (surv[i] - surv[i + 1]) for i, e in enumerate(ee))


def g5a():
    s = Suite("exposure_g", "specifications/06-risk/xva-exposure.md", G)
    base = dict(mean_reversion=0.05, sigma=0.01, curve=CURVE, notional=1e7)
    rows = []
    Ts5 = [1.0, 2.0, 3.0, 4.0, 5.0]
    for side in ("PAY", "RECEIVE"):
        for K in (0.03, 0.045):
            rows.append(dict(base, start_years=0.0, payment_times=Ts5, fixed_rate=K, side=side, exposure_times=[1.0, 2.0, 3.0, 4.0],
                             hazard_rate=0.02, recovery=0.4))
    Ts10 = [0.5 * k for k in range(1, 21)]
    rows.append(dict(base, start_years=0.0, payment_times=Ts10, fixed_rate=0.04, side="PAY", exposure_times=Ts10[:-1], hazard_rate=0.015, recovery=0.4))
    rows.append(dict(base, start_years=2.0, payment_times=[3.0, 4.0, 5.0, 6.0, 7.0], fixed_rate=0.04, side="RECEIVE",
                     exposure_times=[2.0, 4.0, 6.0]))
    rows.append(dict(base, mean_reversion=0.3, sigma=0.015, start_years=0.0, payment_times=Ts5, fixed_rate=0.04, side="PAY",
                     exposure_times=[1.0, 2.0, 3.0, 4.0], hazard_rate=0.05, recovery=0.25))
    n_out = 0
    for inp in rows:
        sws = ee_profile(inp)
        ee = [jam_price(w)["price"] for w in sws]
        qee = [ql_jam(w)["price"] for w in sws]
        out = {"discounted_ee": ee}
        if "hazard_rate" in inp:
            out["cva"] = cva_from(ee, inp["exposure_times"], inp["hazard_rate"], inp["recovery"])
        ok = all(abs(a - b) <= 1e-6 + 1e-10 * abs(a) for a, b in zip(ee, qee))
        n_out += ok
        s.add(EEOP, inp, out, cls=R, verified=["mpmath-50", "jamshidian"] + (["quantlib-1.44"] if ok else []),
              tags=["xva", "exposure", inp["side"].lower()], limit={"absolute": 1e-6, "relative": 1e-9, "reason": "1e-12 per unit notional"},
              description=f"{inp['side']} {inp['fixed_rate']} swap {inp['start_years']}-{inp['payment_times'][-1]}y, {len(inp['exposure_times'])} dates")
    # PAY minus RECEIVE EE at each date = the forward swap value at that date (deterministic part), asserted
    for i, j in ((0, 2), (1, 3)):
        a, b = s.cases[i]["expected"]["outputs"]["discounted_ee"], s.cases[j]["expected"]["outputs"]["discounted_ee"]
        inp = rows[i]
        cv = Curve(**inp["curve"])
        for t, x, y in zip(inp["exposure_times"], a, b):
            k = ([inp["start_years"]] + inp["payment_times"][:-1]).index(t)
            rest = inp["payment_times"][k:]
            ann = sum((Ti - Tp) * cv.P(Ti) for Tp, Ti in zip([t] + rest[:-1], rest))
            fwd = inp["notional"] * (cv.P(t) - cv.P(rest[-1]) - inp["fixed_rate"] * ann)
            assert abs(x - y - float(fwd)) < 1e-6
    b = rows[0]
    caught("receiver swaption for a pay-fixed swap", abs(jam_price(ee_profile(b)[1])["price"] - jam_price(ee_profile(b, "side")[1])["price"]), 1e-6)
    e = dict(base, start_years=0.0, payment_times=Ts5, fixed_rate=0.03, side="PAY", exposure_times=[1.0, 2.0])
    errs = [(dict(e, exposure_times=[1.5]), "E_INPUT", "exposure time not a reset date"),
            (dict(e, exposure_times=[5.0]), "E_INPUT", "exposure at the last payment"),
            (dict(e, exposure_times=[2.0, 1.0]), "E_INPUT", "exposure times not increasing"),
            (dict(e, exposure_times=[0.0]), "E_DOMAIN", "exposure at time 0"),
            (dict(e, side="BUY"), "E_INPUT", "unknown side"),
            (dict(e, hazard_rate=0.02), "E_INPUT", "hazard_rate without recovery"),
            (dict(e, hazard_rate=-0.01, recovery=0.4), "E_DOMAIN", "hazard_rate < 0"),
            (dict(e, hazard_rate=0.01, recovery=1.0), "E_DOMAIN", "recovery = 1")]
    for inp, code, d in errs:
        s.add(EEOP, inp, error=code, cls="date_and_convention", tags=["invalid", "xva"], description=d)
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    note(f"exposure_g outside (QuantLib 1.44 HullWhite objects): {n_out} of {len(s.cases)}")
    reg = HERE.parent / "outside_register_g.json"
    d = json.loads(reg.read_text(encoding="utf-8"))
    d["exposure_g"] = {"counted": n_out, "total": len(s.cases), "rule": "each EE point is the swaption_g QuantLib check; cva is arithmetic on those values"}
    reg.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")


# ================================================================================================ G2c Hull-White sigma calibration
CAL = "rates.shortrate.hw_calibrate"


def cal_obj(inp, sg):
    tot = mp.mpf(0)
    for q in inp["swaptions"]:
        w = dict(mean_reversion=inp["mean_reversion"], sigma=sg, curve=inp["curve"], notional=1.0, **q)
        w.pop("target_price")
        m = jam_mp(w)
        tot += (m - mp.mpf(q["target_price"])) ** 2
    return tot


def jam_mp(inp):
    cv, a, sg = Curve(**inp["curve"]), inp["mean_reversion"], inp["sigma"]
    T0 = mp.mpf(inp["expiry_years"])
    Ts = [mp.mpf(x) for x in inp["payment_times"]]
    K = mp.mpf(inp["fixed_rate"])
    acc = [Ts[0] - T0] + [Ts[i] - Ts[i - 1] for i in range(1, len(Ts))]
    c = [K * x for x in acc]
    c[-1] += 1
    a_, = (mp.mpf(a),)
    f = lambda r: sum(ci * hw_bond(cv, a_, sg, T0, Ti, r)[0] for ci, Ti in zip(c, Ts)) - 1  # noqa: E731
    rs = mp.findroot(f, 0.0, tol=mp.mpf(10) ** -45)
    typ = "CALL" if inp["swaption_type"] == "RECEIVER" else "PUT"
    return sum(ci * gauss_opt(typ, cv.P(T0), cv.P(Ti), hw_bond(cv, a_, sg, T0, Ti, rs)[0], sigma_p(a_, sg, T0, Ti))
               for ci, Ti in zip(c, Ts))


def calibrate(inp):
    g = lambda x: mp.diff(lambda y: cal_obj(inp, y), x)  # noqa: E731
    grid = [mp.mpf(k) / 2000 for k in range(2, 81)]
    vals = [cal_obj(inp, x) for x in grid]
    i = min(range(len(vals)), key=lambda k: vals[k])
    assert 0 < i < len(vals) - 1, "optimum at the scan edge"
    sg = mp.findroot(g, (grid[i - 1], grid[i + 1]), solver="anderson")
    return sg


def g2c():
    mp.mp.dps = 30
    s = Suite("hwcal_g", "specifications/04-pricing/short-rate-models.md", G)
    strips = []
    # co-terminal 10y strip, ATM-ish strikes, targets from sigma 0.0115 with stated perturbations (so the fit is not exact)
    for a, true_s, pert, typ in ((0.05, 0.0115, (1.02, 0.99, 1.01, 0.985, 1.0), "PAYER"), (0.2, 0.009, (0.97, 1.03, 1.0, 1.01, 0.99), "RECEIVER"),
                                 (0.01, 0.007, (1.0, 1.0, 1.0, 1.0, 1.0), "PAYER")):
        sw = []
        for T0, p in zip((1.0, 2.0, 3.0, 5.0, 7.0), pert):
            Ts = [T0 + k for k in range(1, int(10 - T0) + 1)]
            base = dict(mean_reversion=a, sigma=true_s, curve=CURVE, notional=1.0, expiry_years=T0, payment_times=Ts, fixed_rate=0.03, swaption_type=typ)
            K = round(jam_price(base)["forward_swap_rate"], 6)
            px = float(jam_mp(dict(base, fixed_rate=K)) * p)
            sw.append(dict(expiry_years=T0, payment_times=Ts, fixed_rate=K, swaption_type=typ, target_price=px))
        strips.append(dict(mean_reversion=a, curve=CURVE, swaptions=sw))
    n_out = 0
    for inp in strips:
        sg = calibrate(inp)
        fitted = [float(jam_mp(dict(mean_reversion=inp["mean_reversion"], sigma=sg, curve=CURVE, notional=1.0, **{k: v for k, v in q.items() if k != "target_price"}))) for q in inp["swaptions"]]
        rmse = float(mp.sqrt(cal_obj(inp, sg) / len(fitted)))
        out = {"sigma": float(sg), "fitted_prices": fitted, "rmse": rmse}
        # outside: fitted prices by QuantLib HullWhite objects at the golden sigma (G-13 method), and QL's own gradient sign change
        q = [ql_jam(dict(mean_reversion=inp["mean_reversion"], sigma=float(sg), curve=CURVE, notional=1.0, **{k: v for k, v in x.items() if k != "target_price"}))["price"] for x in inp["swaptions"]]
        ok = all(abs(a - b) <= 1e-12 + 1e-10 * abs(a) for a, b in zip(fitted, q))
        note(f"  hwcal sigma {float(sg):.12f} rmse {rmse:.3e} QL fitted match {ok}")
        s.add(CAL, inp, out, cls=R, verified=["mpmath-30", "grid-scan-unique"], tags=["shortrate", "calibration"],
              output_classes={"sigma": R, "fitted_prices": R, "rmse": R},
              limit={"absolute": 1e-12, "relative": 1e-9, "reason": "1-D optimum; sigma judged at 1e-9 relative"},
              description=f"HW sigma to a 10y co-terminal strip, a = {inp['mean_reversion']}")
    e = strips[0]
    errs = [(dict(e, swaptions=[]), "E_INPUT", "empty strip"),
            (dict(e, swaptions=[dict(e["swaptions"][0], target_price=-0.01)]), "E_DOMAIN", "negative target"),
            (dict(e, mean_reversion=0.0), "E_DOMAIN", "a = 0")]
    for inp, code, d in errs:
        s.add(CAL, inp, error=code, cls="date_and_convention", tags=["invalid", "calibration"], description=d)
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    mp.mp.dps = 50
    note(f"hwcal_g outside: {n_out} of {len(s.cases)} (sigma is not a library value)")
    reg = HERE.parent / "outside_register_g.json"
    d = json.loads(reg.read_text(encoding="utf-8"))
    d["hwcal_g"] = {"counted": n_out, "total": len(s.cases), "rule": "not counted: the fitted sigma is this platform's least-squares optimum; QuantLib reprices the fitted prices (evidence only)"}
    reg.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")


# ================================================================================================ G2e caps and floors
CAPOP = "rates.shortrate.capfloor"


def cap_value(inp, mut=None):
    Ts, K, n = inp["period_times"], mp.mpf(inp["strike"]), inp["notional"]
    typ = "PUT" if inp["cap_floor"] == "CAP" else "CALL"
    if mut == "type":
        typ = "CALL" if typ == "PUT" else "PUT"
    lets = []
    for t0, t1 in zip(Ts, Ts[1:]):
        tau = mp.mpf(t1) - mp.mpf(t0)
        q = {k: v for k, v in inp.items() if k not in ("period_times", "strike", "cap_floor", "notional")}
        o = opt_value(dict(q, option_type=typ, strike=float(1 / (1 + K * tau)), expiry_years=t0, maturity_years=t1, notional=1.0))
        lets.append((1 + K * tau) * mp.mpf(o["price"]) * n)
    return {"price": float(sum(lets)), "caplet_prices": [float(x) for x in lets]}


def ql_cap(inp):
    m = ql_model(inp)
    Ts, K, n = inp["period_times"], inp["strike"], inp["notional"]
    t = ql.Option.Put if inp["cap_floor"] == "CAP" else ql.Option.Call
    lets = [(1 + K * (t1 - t0)) * m.discountBondOption(t, 1 / (1 + K * (t1 - t0)), t0, t1) * n for t0, t1 in zip(Ts, Ts[1:])]
    return {"price": sum(lets), "caplet_prices": lets}


def g2e():
    s = Suite("capfloor_g", "specifications/04-pricing/short-rate-models.md", G)
    models = [dict(model="VASICEK", mean_reversion=0.15, long_term_mean=0.045, sigma=0.012, short_rate=0.035),
              dict(model="CIR", mean_reversion=0.25, long_term_mean=0.04, sigma=0.08, short_rate=0.03),
              dict(model="HULL_WHITE", mean_reversion=0.05, sigma=0.01, curve=CURVE)]
    n_out = 0
    for m in models:
        for Ts in ([0.5 * k for k in range(1, 11)], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]):
            for cf in ("CAP", "FLOOR"):
                for K in (0.03, 0.04, 0.05):
                    inp = dict(m, period_times=Ts, strike=K, cap_floor=cf, notional=1e6)
                    out = cap_value(inp)
                    q = ql_cap(inp)
                    ok = all(abs(a - b) <= 1e-6 + 1e-9 * abs(a) for a, b in zip(out["caplet_prices"] + [out["price"]], q["caplet_prices"] + [q["price"]]))
                    n_out += ok
                    if not ok:
                        note(f"  QL cap differs {m['model']} {cf} {K}: {q['price']} {out['price']}")
                    s.add(CAPOP, inp, out, cls=R if m["model"] == "CIR" else A,
                          verified=["mpmath-50", "cap-floor-parity"] + (["quantlib-1.44"] if ok else []),
                          tags=["shortrate", "capfloor", m["model"].lower(), cf.lower()],
                          limit={"absolute": 1e-6, "relative": 1e-9, "reason": "1e-12 per unit notional"},
                          description=f"{m['model']} {cf} K={K}, {len(Ts) - 1} periods to {Ts[-1]}y")
    # parity: cap - floor = sum notional (P(t0) - (1 + K tau) P(t1)), asserted on every pair
    for i in range(0, 36, 6):
        for j in range(3):
            cap, flo = s.cases[i + j], s.cases[i + 3 + j]
            inp = cap["inputs"]
            Pm = (lambda t: Curve(**inp["curve"]).P(t)) if inp["model"] == "HULL_WHITE" else                 (lambda t: mp.mpf(zcb_value(dict(inp, t_years=0.0, maturity_years=t))["discount_factor"]))
            Ts, K = inp["period_times"], inp["strike"]
            sw = sum(Pm(t0) - (1 + K * (t1 - t0)) * Pm(t1) for t0, t1 in zip(Ts, Ts[1:])) * inp["notional"]
            assert abs(cap["expected"]["outputs"]["price"] - flo["expected"]["outputs"]["price"] - float(sw)) < 1e-6
    b = dict(models[2], period_times=[1.0, 2.0, 3.0], strike=0.04, cap_floor="CAP", notional=1e6)
    caught("cap priced with bond calls", abs(cap_value(b)["price"] - cap_value(b, "type")["price"]), 1e-6)
    e = dict(models[2], period_times=[1.0, 2.0, 3.0], strike=0.04, cap_floor="CAP", notional=1.0)
    errs = [(dict(e, period_times=[1.0]), "E_INPUT", "one period time"), (dict(e, period_times=[0.0, 1.0]), "E_DOMAIN", "first fixing at 0"),
            (dict(e, period_times=[2.0, 1.0]), "E_INPUT", "period times not increasing"), (dict(e, strike=-0.5), "E_DOMAIN", "1 + K tau <= 0"),
            (dict(e, cap_floor="COLLAR"), "E_INPUT", "unknown cap_floor")]
    for inp, code, d in errs:
        s.add(CAPOP, inp, error=code, cls="date_and_convention", tags=["invalid", "capfloor"], description=d)
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    note(f"capfloor_g outside (QuantLib 1.44 model objects): {n_out} of {len(s.cases)}")
    reg = HERE.parent / "outside_register_g.json"
    d = json.loads(reg.read_text(encoding="utf-8"))
    d["capfloor_g"] = {"counted": n_out, "total": len(s.cases), "rule": "QuantLib Vasicek, CoxIngersollRoss, HullWhite discountBondOption per caplet, scaled by (1 + K tau) and summed"}
    reg.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")


# ================================================================================================ G2f Jamshidian for Vasicek and CIR
def jam_affine(inp):
    T0 = mp.mpf(inp["expiry_years"])
    Ts = [mp.mpf(x) for x in inp["payment_times"]]
    K = mp.mpf(inp["fixed_rate"])
    acc = [Ts[0] - T0] + [Ts[i] - Ts[i - 1] for i in range(1, len(Ts))]
    c = [K * x for x in acc]
    c[-1] += 1
    AB = vas_AB if inp["model"] == "VASICEK" else cir_AB
    pr = (inp["mean_reversion"], inp["long_term_mean"], inp["sigma"])
    bond = lambda tau, r: mp.exp(AB(*pr, tau)[0] - AB(*pr, tau)[1] * r)  # noqa: E731
    f = lambda r: sum(ci * bond(Ti - T0, r) for ci, Ti in zip(c, Ts)) - 1  # noqa: E731
    rs = mp.findroot(f, 0.03, tol=mp.mpf(10) ** -40)
    if inp["model"] == "CIR":
        assert rs > 0.001, "CIR critical rate must be positive with a margin"
    typ = "CALL" if inp["swaption_type"] == "RECEIVER" else "PUT"
    base = {k: inp[k] for k in ("model", "mean_reversion", "long_term_mean", "sigma", "short_rate")}
    v = mp.mpf(0)
    for ci, Ti in zip(c, Ts):
        X = bond(Ti - T0, rs)
        v += ci * mp.mpf(opt_value(dict(base, option_type=typ, strike=float(X), expiry_years=float(T0), maturity_years=float(Ti), notional=1.0))["price"])
    P0 = lambda t: bond(t, inp["short_rate"])  # noqa: E731
    ann = sum(x * P0(Ti) for x, Ti in zip(acc, Ts))
    return {"price": float(inp["notional"] * v), "forward_swap_rate": float((P0(T0) - P0(Ts[-1])) / ann), "annuity": float(inp["notional"] * ann)}


def ql_jam_affine(inp):
    m = ql_model(inp)
    T0, Ts, K = inp["expiry_years"], inp["payment_times"], inp["fixed_rate"]
    acc = [Ts[0] - T0] + [Ts[i] - Ts[i - 1] for i in range(1, len(Ts))]
    c = [K * x for x in acc]
    c[-1] += 1
    f = lambda r: sum(ci * m.discountBond(T0, Ti, r) for ci, Ti in zip(c, Ts)) - 1  # noqa: E731
    rs = ql.Brent().solve(f, 1e-15, 0.03, 0.0001, 0.5)
    t = ql.Option.Call if inp["swaption_type"] == "RECEIVER" else ql.Option.Put
    v = sum(ci * m.discountBondOption(t, m.discountBond(T0, Ti, rs), T0, Ti) for ci, Ti in zip(c, Ts))
    P0 = lambda t: m.discountBond(0.0, t, inp["short_rate"])  # noqa: E731
    ann = sum(x * P0(Ti) for x, Ti in zip(acc, Ts))
    return {"price": inp["notional"] * v, "forward_swap_rate": (P0(T0) - P0(Ts[-1])) / ann, "annuity": inp["notional"] * ann}


def g2f():
    s = Suite("swaption_affine_g", "specifications/04-pricing/short-rate-models.md", G)
    models = [dict(model="VASICEK", mean_reversion=0.15, long_term_mean=0.045, sigma=0.012, short_rate=0.035),
              dict(model="CIR", mean_reversion=0.25, long_term_mean=0.04, sigma=0.08, short_rate=0.03)]
    n_out = 0
    for m in models:
        for T0, n in ((1.0, 5), (2.0, 10), (5.0, 5)):
            Ts = [T0 + k for k in range(1, n + 1)]
            base = dict(m, notional=1e6, expiry_years=T0, payment_times=Ts)
            fwd = jam_affine(dict(base, fixed_rate=0.04, swaption_type="PAYER"))["forward_swap_rate"]
            for K in (round(fwd - 0.01, 6), round(fwd, 6), round(fwd + 0.01, 6)):
                for st in ("PAYER", "RECEIVER"):
                    inp = dict(base, fixed_rate=K, swaption_type=st)
                    out = jam_affine(inp)
                    q = ql_jam_affine(inp)
                    ok = all(abs(q[k] - out[k]) <= 1e-6 + 1e-9 * abs(out[k]) for k in ("price", "annuity")) and close(q["forward_swap_rate"], out["forward_swap_rate"])
                    n_out += ok
                    if not ok:
                        note(f"  QL affine swaption differs {m['model']}: {q} {out}")
                    s.add(SWO, inp, out, cls=R, verified=["mpmath-50", "payer-receiver-parity"] + (["quantlib-1.44"] if ok else []),
                          tags=["shortrate", "jamshidian", m["model"].lower(), st.lower()],
                          limit={"absolute": 1e-6, "relative": 1e-9, "reason": "1e-12 per unit notional"},
                          description=f"{m['model']} {st} {T0}y into {n}y, K={K}")
    for i in range(0, len(s.cases), 2):
        p_, r_ = s.cases[i]["expected"]["outputs"], s.cases[i + 1]["expected"]["outputs"]
        assert abs(p_["price"] - r_["price"] - p_["annuity"] * (p_["forward_swap_rate"] - s.cases[i]["inputs"]["fixed_rate"])) < 1e-6
    e = dict(models[0], notional=1.0, expiry_years=1.0, payment_times=[2.0, 3.0], fixed_rate=0.04, swaption_type="PAYER")
    errs = [(dict(e, model="G2PP"), "E_INPUT", "unknown model"),
            ({k: v for k, v in e.items() if k != "short_rate"}, "E_SCHEMA", "VASICEK without short_rate"),
            (dict(models[1], notional=1.0, expiry_years=1.0, payment_times=[2.0, 3.0], fixed_rate=0.0, swaption_type="PAYER"), "E_DOMAIN", "CIR critical rate below 0 (bond sum at r = 0 below 1)")]
    for inp, code, d in errs:
        s.add(SWO, inp, error=code, cls="date_and_convention", tags=["invalid", "jamshidian"], description=d)
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep
    note(f"swaption_affine_g outside (QuantLib 1.44 model objects): {n_out} of {len(s.cases)}")
    reg = HERE.parent / "outside_register_g.json"
    d = json.loads(reg.read_text(encoding="utf-8"))
    d["swaption_affine_g"] = {"counted": n_out, "total": len(s.cases), "rule": "G-13 method on QuantLib Vasicek and CoxIngersollRoss objects"}
    reg.write_text(json.dumps(d, indent=1) + chr(10), encoding="utf-8")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2 or "G1" in sys.argv:
        main()
    if len(sys.argv) < 2 or "R9" in sys.argv:
        r9()
    if len(sys.argv) < 2 or "G2A" in sys.argv:
        g2a()
    if len(sys.argv) < 2 or "G2B" in sys.argv:
        g2b()
    if len(sys.argv) < 2 or "G5A" in sys.argv:
        g5a()
    if len(sys.argv) < 2 or "G2C" in sys.argv:
        g2c()
    if len(sys.argv) < 2 or "G2E" in sys.argv:
        g2e()
    if len(sys.argv) < 2 or "G2F" in sys.argv:
        g2f()
