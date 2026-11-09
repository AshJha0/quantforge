"""Stage F wave 1, slice F6: model fixes R7 (CDS index option, Pedersen adjusted forward), R8 (GARCH parameters with
standard errors, Student-t, demeaning) and R10 (VIX null quotes and the Cboe sample strip; local vol at slice expiries).

Goldens come from this file's own replicas at 50 digits (mpmath, exact rationals). Every suite stops if its tolerance
would let a named wrong convention through (`caught`). No golden depends on an optimiser's path: GARCH optima are
Newton-polished in 50-digit arithmetic with exact second derivatives (forward-mode jets) and checked interior.

    cd oracle/python && uv run python -W ignore gen_stage_f_f6.py [R7|R8|R10|COVER ...]
"""
import json
import math
import sys
from datetime import date, timedelta
from fractions import Fraction as Fr
from pathlib import Path

import mpmath as mp
import numpy as np

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_f_f6.py"
E, A, R, I = "date_and_convention", "simple_analytic", "root_finding", "interpolation"
SYN = "synthetic"
FOLDER = "stage_f"
MUTANTS = []
HERE = Path(__file__).resolve().parent
f = float
D_ = date.fromisoformat


def S(name, spec):
    return Suite(name, f"specifications/{spec}", G)


def write(s, synthetic=True):
    keep = common.GOLDEN
    for c in s.cases:
        if synthetic and SYN not in c["tags"] and "cboe-sample" not in c["tags"]:
            c["tags"].append(SYN)
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep


def caught(suite, name, gap, tol):
    assert gap > tol, f"{suite}: mutant '{name}' is not caught: gap {gap:.3e}, tolerance {tol:.3e}"
    MUTANTS.append((suite, name, gap))


# ===================================================================================== R7 CDS index option
def add_m(d, m):
    import calendar
    y, mo = divmod(d.month - 1 + m, 12)
    return date(d.year + y, mo + 1, min(d.day, calendar.monthrange(d.year + y, mo + 1)[1]))


def periods(ex, mat):
    dates, k = [ex], 1
    while dates[-1] < mat:
        dates.append(min(add_m(ex, 3 * k), mat))
        k += 1
    return list(zip(dates, dates[1:]))


def legs(origin, ex, mat, r, h, Rr):
    """Stylised legs (E-B22) from ex to mat, times and discounting measured from `origin`. Returns (prot, annuity)."""
    tt = lambda d: mp.mpf((d - origin).days) / 365  # noqa: E731
    Sv = lambda d: mp.exp(-h * tt(d))  # noqa: E731
    Dv = lambda d: mp.exp(-r * tt(d))  # noqa: E731
    prot, ann = mp.mpf(0), mp.mpf(0)
    for a, b in periods(ex, mat):
        m = a + timedelta((b - a).days // 2)
        prot += (1 - Rr) * Dv(m) * (Sv(a) - Sv(b))
        ann += mp.mpf((b - a).days) / 360 * Dv(b) * Sv(b) + mp.mpf((m - a).days) / 360 * Dv(m) * (Sv(a) - Sv(b))
    return prot, ann


def strike_hazard(ex, mat, r, Rr, K, origin=None):
    """h_K >= 0 with prot'(h)/A'(h) = K, legs measured from expiry (ruling F-8). Bisection at 50 digits."""
    origin = origin or ex
    spread = lambda x: (lambda p, a: p / a)(*legs(origin, ex, mat, r, x, Rr))  # noqa: E731
    lo, hi = mp.mpf(0), 2 * K / (1 - Rr)
    while spread(hi) < K:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        if spread(mid) < K:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def black(call, F, K, sd):
    if sd == 0:
        return max(F - K, 0) if call else max(K - F, 0)
    d1 = (mp.log(F / K) + sd * sd / 2) / sd
    d2 = d1 - sd
    return F * mp.ncdf(d1) - K * mp.ncdf(d2) if call else K * mp.ncdf(-d2) - F * mp.ncdf(-d1)


def cdsidx(i, mutant=None):
    t0, ex, mat = D_(i["as_of"]), D_(i["expiry"]), D_(i["maturity"])
    if ex <= t0 or mat <= ex:
        raise ValueError("E_INPUT")
    r, h, Rr, K, C, N, v = (mp.mpf(i[k]) for k in ("rate", "hazard_rate", "recovery", "strike", "coupon", "notional", "vol"))
    if not (0 <= Rr < 1) or h < 0 or K <= 0 or C < 0 or v < 0 or N <= 0:
        raise ValueError("E_DOMAIN")
    T = mp.mpf((ex - t0).days) / 365
    prot, Aa = legs(t0, ex, mat, r, h, Rr)
    if Aa == 0 or prot == 0:
        raise ValueError("E_DOMAIN")
    F = prot / Aa
    fep = (1 - Rr) * (1 - mp.exp(-h * T)) * mp.exp(-r * T)
    hK = strike_hazard(ex, mat, r, Rr, K) if mutant != "ak-index-hazard" else h
    if mutant == "ak-from-asof":
        AK = legs(t0, ex, mat, r, strike_hazard(ex, mat, r, Rr, K, origin=t0), Rr)[1]
    else:
        AK = legs(ex, ex, mat, r, hK, Rr)[1]
    Gx = (K - C) * AK
    Fadj = F + fep / Aa if mutant != "fep-outright" else F
    Kadj = C + Gx * (mp.exp(-r * T) if mutant != "no-discount" else 1) / Aa
    if mutant == "no-coupon-adj":
        Kadj = K
    if Fadj <= 0 or Kadj <= 0:
        raise ValueError("E_DOMAIN")
    payer = i["type"] == "PAYER"
    price = N * Aa * black(payer, Fadj, Kadj, v * mp.sqrt(T))
    if mutant == "fep-outright" and payer:
        price += N * fep
    return {"price": f(price), "forward_spread": f(F), "adjusted_forward": f(Fadj), "adjusted_strike": f(Kadj), "risky_annuity": f(Aa),
            "strike_annuity": f(AK), "strike_hazard": f(hK), "exercise_upfront": f(N * Gx), "front_end_protection": f(N * fep)}, (price, Aa, Fadj, Kadj, N)


def r7():
    s = S("cdsidx_f", "04-pricing/credit-options-and-copulas.md")
    op = "credit.cdsindex.option_price"
    AS = "2026-11-09"
    # (label, expiry, maturity, rate, hazard, recovery, coupon, strikes, vol)
    mk = [("IG 3m", "2027-02-17", "2031-12-20", .037, .0105, .4, .01, (.0055, .0065, .008), .45),
          ("IG 1m short", "2026-12-17", "2031-12-20", .037, .009, .4, .01, (.005, .0058), .5),
          ("HY 3m", "2027-02-17", "2031-12-20", .037, .055, .3, .05, (.03, .0385, .045), .6),
          ("HY 6m deep", "2027-05-19", "2031-12-20", .035, .08, .3, .05, (.045, .06), .7),
          ("Europe 9m", "2027-08-18", "2032-06-20", .022, .012, .4, .01, (.006, .0075), .4)]
    oc = {k: R for k in ("forward_spread", "adjusted_forward", "adjusted_strike", "risky_annuity", "strike_annuity", "strike_hazard", "exercise_upfront")}
    oc["front_end_protection"] = A
    N = 1e7
    lim = {"absolute": 1e-9 * N, "relative": 1e-9, "reason": "1e-9 per unit notional, as stage D credit"}
    n_par = 0
    for lab, ex, mat, r, h, Rr, C, ks, v in mk:
        for K in ks:
            for vol in (v, 0.0) if K == ks[0] else (v,):
                pair = {}
                for typ in ("PAYER", "RECEIVER"):
                    inp = {"as_of": AS, "expiry": ex, "maturity": mat, "rate": r, "hazard_rate": h, "recovery": Rr, "type": typ, "strike": K,
                           "coupon": C, "notional": N, "vol": vol}
                    out, raw = cdsidx(inp)
                    pair[typ] = raw
                    tags = ["cdsindex", typ.lower(), "pedersen"] + (["intrinsic"] if vol == 0 else []) + (["strike-below-coupon"] if K < C else [])
                    s.add(op, inp, out, cls=R, verified=["mpmath-50", "parity-check"], tags=tags, output_classes=oc, limit=lim,
                          description=f"{lab}, K = {K * 1e4:.0f} bp, C = {C * 1e4:.0f} bp, vol {vol}")
                    for m in ("fep-outright", "no-coupon-adj", "ak-index-hazard", "no-discount", "ak-from-asof"):
                        try:
                            mo = cdsidx(inp, m)[0]["price"]
                        except ValueError:
                            continue
                        if vol > 0 and (m != "fep-outright" or typ == "PAYER"):
                            caught("cdsidx_f", f"{lab} {K} {typ}: {m}", abs(mo - out["price"]), 1e-9 * N + 1e-9 * abs(out["price"]))
                (pp, Aa, Fa, Ka, NN), (pr, _, _, _, _) = pair["PAYER"], pair["RECEIVER"]
                par = NN * Aa * (Fa - Ka)
                assert abs((pp - pr) - par) <= mp.mpf("1e-30") * max(1, abs(par)), "parity"
                n_par += 1
    base = {"as_of": AS, "expiry": "2027-02-17", "maturity": "2031-12-20", "rate": .037, "hazard_rate": .0105, "recovery": .4, "type": "PAYER",
            "strike": .0065, "coupon": .01, "notional": N, "vol": .45}
    bad = [("expiry on as_of", {"expiry": AS}, "E_INPUT"), ("maturity before expiry", {"maturity": "2027-01-20"}, "E_INPUT"),
           ("recovery 1", {"recovery": 1.0}, "E_DOMAIN"), ("negative hazard", {"hazard_rate": -.001}, "E_DOMAIN"),
           ("strike 0", {"strike": 0.0}, "E_DOMAIN"), ("negative coupon", {"coupon": -.01}, "E_DOMAIN"), ("negative vol", {"vol": -.1}, "E_DOMAIN"),
           ("notional 0", {"notional": 0.0}, "E_DOMAIN"), ("zero hazard: F_adj = 0", {"hazard_rate": 0.0}, "E_DOMAIN"),
           ("strike far below a 500 bp coupon: K_adj <= 0", {"strike": .0005, "coupon": .05}, "E_DOMAIN"),
           ("type not listed", {"type": "STRADDLE"}, "E_SCHEMA")]
    for d, chg, code in bad:
        if code != "E_SCHEMA":
            try:
                cdsidx({**base, **chg})
                raise AssertionError(d)
            except ValueError as e:
                assert str(e) == code, (d, e)
        s.add(op, {**base, **chg}, error=code, cls=E, tags=["invalid"], description=d)
    note(f"cdsidx_f: {len(s.cases)} cases; payer - receiver = N A (F_adj - K_adj) on {n_par} pairs to 1e-30; Pedersen (2003) example not available (spec)")
    write(s)


# ===================================================================================== R8 GARCH estimate
class Jet:
    """Second-order forward-mode number over mpf: value, gradient and Hessian in n variables."""
    __slots__ = ("v", "g", "h")

    def __init__(self, v, g, h):
        self.v, self.g, self.h = v, g, h

    @staticmethod
    def const(c, n):
        return Jet(mp.mpf(c), [mp.mpf(0)] * n, [[mp.mpf(0)] * n for _ in range(n)])

    @staticmethod
    def var(c, i, n):
        j = Jet.const(c, n)
        j.g[i] = mp.mpf(1)
        return j

    def _n(self):
        return len(self.g)

    def __add__(self, o):
        if not isinstance(o, Jet):
            return Jet(self.v + o, self.g, self.h)
        return Jet(self.v + o.v, [a + b for a, b in zip(self.g, o.g)], [[a + b for a, b in zip(x, y)] for x, y in zip(self.h, o.h)])
    __radd__ = __add__

    def __neg__(self):
        return Jet(-self.v, [-a for a in self.g], [[-a for a in x] for x in self.h])

    def __sub__(self, o):
        return self + (-o if isinstance(o, Jet) else -o)

    def __rsub__(self, o):
        return (-self) + o

    def __mul__(self, o):
        if not isinstance(o, Jet):
            return Jet(self.v * o, [a * o for a in self.g], [[a * o for a in x] for x in self.h])
        n = self._n()
        return Jet(self.v * o.v, [self.g[i] * o.v + self.v * o.g[i] for i in range(n)],
                   [[self.h[i][j] * o.v + self.g[i] * o.g[j] + self.g[j] * o.g[i] + self.v * o.h[i][j] for j in range(n)] for i in range(n)])
    __rmul__ = __mul__

    def apply(self, f0, f1, f2):
        """phi(self) for a univariate phi with value f0, first derivative f1 and second f2 at self.v."""
        n = self._n()
        return Jet(f0, [f1 * a for a in self.g], [[f1 * self.h[i][j] + f2 * self.g[i] * self.g[j] for j in range(n)] for i in range(n)])

    def log(self):
        return self.apply(mp.log(self.v), 1 / self.v, -1 / self.v ** 2)

    def inv(self):
        return self.apply(1 / self.v, -1 / self.v ** 2, 2 / self.v ** 3)

    def __truediv__(self, o):
        return self * (o.inv() if isinstance(o, Jet) else 1 / mp.mpf(o))


def lgamma_jet(x):
    return x.apply(mp.loggamma(x.v), mp.digamma(x.v), mp.psi(1, x.v))


def garch_ll(e, theta, dist, init, jet=False):
    """Log-likelihood of demeaned returns e (mpf) at theta = (omega, alpha, beta[, nu]). jet=True returns a Jet."""
    n = len(theta)
    if jet:
        th = [Jet.var(theta[i], i, n) for i in range(n)]
    else:
        th = [mp.mpf(x) for x in theta]
    om, al, be = th[:3]
    s2 = Jet.const(init, n) if jet else init
    ll = Jet.const(0, n) if jet else mp.mpf(0)
    if dist == "NORMAL":
        c = -mp.log(2 * mp.pi) / 2
        for x in e:
            ll = ll + (c - (s2.log() if jet else mp.log(s2)) / 2 - (x * x) * (s2.inv() if jet else 1 / s2) / 2)
            s2 = om + al * (x * x) + be * s2
    else:
        nu = th[3]
        if jet:
            c = lgamma_jet((nu + 1) * mp.mpf("0.5")) - lgamma_jet(nu * mp.mpf("0.5")) - ((nu - 2) * mp.pi).log() * mp.mpf("0.5")
        else:
            c = mp.loggamma((nu + 1) / 2) - mp.loggamma(nu / 2) - mp.log(mp.pi * (nu - 2)) / 2
        half = (nu + 1) * mp.mpf("0.5")
        for x in e:
            if jet:
                u = (x * x) * (((nu - 2) * s2).inv())
                ll = ll + c - s2.log() * mp.mpf("0.5") - half * (u + 1).log()
            else:
                ll += c - mp.log(s2) / 2 - half * mp.log(1 + x * x / ((nu - 2) * s2))
            s2 = om + al * (x * x) + be * s2
    return ll


def garch_sim_t(n, om, al, be, nu, seed, drift=0.0):
    """Input data only: GARCH(1,1) with unit-variance t (nu) or normal (nu None) shocks, numpy PCG64, burn-in 500."""
    g = np.random.default_rng(seed)
    z = g.standard_normal(n + 500) if nu is None else g.standard_t(nu, n + 500) * math.sqrt((nu - 2) / nu)
    s2, out = om / (1 - al - be), []
    for zt in z:
        x = math.sqrt(s2) * zt
        out.append(x)
        s2 = om + al * x * x + be * s2
    return [round(x + drift, 10) for x in out[500:]]


def fit_float(r, dist, demean, init="SAMPLE"):
    """Float MLE (multi-start Nelder-Mead on a scaled problem). Returns (theta, mu, s0)."""
    from scipy.optimize import minimize
    rf = np.array(r, dtype=float)
    mu = float(rf.mean()) if demean else 0.0
    e = rf - mu
    s0 = float(np.mean(e * e)) if init == "SAMPLE" else float(init)
    lg = math.lgamma

    def nll(p):
        w, a, b = p[0] * s0, p[1], p[2]
        if w <= 0 or a < 0 or b < 0 or a + b >= 1:
            return 1e100
        s2, ll = s0, 0.0
        if dist == "NORMAL":
            for x in e:
                ll += math.log(s2) + x * x / s2
                s2 = w + a * x * x + b * s2
            return 0.5 * ll
        nu = p[3]
        if not 2.01 < nu <= 500:
            return 1e100
        c = lg((nu + 1) / 2) - lg(nu / 2) - 0.5 * math.log(math.pi * (nu - 2))
        for x in e:
            ll -= c - 0.5 * math.log(s2) - (nu + 1) / 2 * math.log1p(x * x / ((nu - 2) * s2))
            s2 = w + a * x * x + b * s2
        return ll
    starts = [(.05, .05, .9), (.2, .1, .7), (.02, .03, .95), (.5, .2, .3)]
    if dist == "STUDENT_T":
        starts = [st + (nu0,) for st in starts for nu0 in (5.0, 10.0)]
    best = None
    for st in starts:
        m = minimize(nll, st, method="Nelder-Mead", options={"xatol": 1e-11, "fatol": 1e-11, "maxiter": 60000, "maxfev": 120000})
        if best is None or m.fun < best.fun:
            best = m
    th = [best.x[0] * s0] + list(best.x[1:])
    return th, mu, s0, best.fun


def garch_estimate(inp, mutant=None):
    """Golden: float multi-start, then Newton on exact jets at 50 digits. Returns outputs and the high-precision optimum."""
    r, dist, demean = inp["returns"], inp["distribution"], inp["demean"]
    if mutant == "no-demean":
        demean = False
    th0, mu_f, s0, fun = fit_float(r, dist, demean, inp["initial_variance"])
    rm = [mp.mpf(x) for x in r]
    mu = mp.fsum(rm) / len(rm) if demean else mp.mpf(0)
    e = [x - mu for x in rm]
    init = mp.fsum(x * x for x in e) / len(e) if inp["initial_variance"] == "SAMPLE" else mp.mpf(inp["initial_variance"])
    th = [mp.mpf(x) for x in th0]
    n = len(th)
    for it in range(30):
        J = garch_ll(e, th, dist, init, jet=True)
        H = mp.matrix(J.h)
        step = mp.lu_solve(H, mp.matrix(J.g))
        th = [th[i] - step[i] for i in range(n)]
        rel = max(abs(step[i]) / abs(th[i]) for i in range(n))
        if rel < mp.mpf("1e-40"):
            break
    J = garch_ll(e, th, dist, init, jet=True)
    assert all(abs(J.g[i]) * abs(th[i]) < mp.mpf("1e-20") * abs(J.v) for i in range(n)), "gradient not zero"
    H = mp.matrix(J.h)
    ev = mp.eigsy(H)[0]
    assert all(x < 0 for x in ev), "not a maximum"
    sv = f(init)
    assert th[0] > 1e-6 * sv and th[1] > 1e-6 and th[2] > 1e-6 and th[1] + th[2] < 1 - 1e-6, "optimum near a bound"
    if dist == "STUDENT_T":
        assert 2 + 1e-6 < th[3] < 500 - 1e-6
    V = mp.inverse(-H)
    se = [mp.sqrt(V[i, i]) for i in range(n)]
    names = ["omega", "alpha", "beta", "degrees_of_freedom"]
    out = {k: f(th[i]) for i, k in enumerate(names[:n])}
    if dist == "NORMAL":
        out["degrees_of_freedom"] = None
    out["mean"] = f(mu)
    out["loglik"] = f(J.v)
    out["std_errors"] = {k: (f(se[i]) if i < n else None) for i, k in enumerate(names)}
    out["persistence"] = f(th[1] + th[2])
    # float multi-start must not beat the polished optimum
    assert J.v + mp.mpf(10) ** -6 >= -mp.mpf(fun) - (len(r) * mp.log(2 * mp.pi) / 2 if dist == "NORMAL" else 0), "a float start beat the polished optimum"
    return out, th, J.v, se


def garch_ll_case(inp):
    rm = [mp.mpf(x) for x in inp["returns"]]
    mu = mp.mpf(inp.get("mean", 0.0))
    e = [x - mu for x in rm]
    init = mp.fsum(x * x for x in e) / len(e) if inp["initial_variance"] == "SAMPLE" else mp.mpf(inp["initial_variance"])
    dist = inp.get("distribution", "NORMAL")
    th = [inp["omega"], inp["alpha"], inp["beta"]] + ([inp["degrees_of_freedom"]] if dist == "STUDENT_T" else [])
    ll = garch_ll(e, th, dist, init)
    s2 = [init]
    for x in e:
        s2.append(mp.mpf(inp["omega"]) + mp.mpf(inp["alpha"]) * x * x + mp.mpf(inp["beta"]) * s2[-1])
    return {"loglik": f(ll), "variances": [f(x) for x in s2[:-1]], "next_variance": f(s2[-1])}, ll


TRUE_N = (2e-6, .08, .90)
TRUE_T = (2e-6, .08, .90, 6.0)


def r8():
    s = S("garch_f", "05-volatility/garch.md")
    lop, eop = "vol.garch.loglik", "vol.garch.estimate"
    LL = {"absolute": 1e-9, "relative": 1e-10, "reason": "likelihood_sum: n logs and lgamma terms; libm last digits"}
    VL = {"absolute": 1e-16, "relative": 1e-11, "reason": "variances, as garch_e (ruling E-B14)"}
    rn = garch_sim_t(2000, *TRUE_N, None, 20261109)
    rt = garch_sim_t(2000, *TRUE_T[:3], TRUE_T[3], 20261109)
    rnd = garch_sim_t(2000, *TRUE_N, None, 20261110, drift=4e-4)
    rtd = garch_sim_t(2000, *TRUE_T[:3], TRUE_T[3], 20261110, drift=4e-4)
    # loglik with the new inputs
    short = rt[:250]
    for d, extra in (("Student-t nu 6", {"distribution": "STUDENT_T", "degrees_of_freedom": 6.0}),
                     ("Student-t nu 4.5 with mean", {"distribution": "STUDENT_T", "degrees_of_freedom": 4.5, "mean": 3e-4}),
                     ("normal with mean", {"distribution": "NORMAL", "mean": -2e-4}),
                     ("normal; degrees_of_freedom ignored", {"distribution": "NORMAL", "degrees_of_freedom": 1.5}),
                     ("Student-t nu 400 (near normal)", {"distribution": "STUDENT_T", "degrees_of_freedom": 400.0})):
        inp = {"returns": short, "omega": 4e-6, "alpha": .09, "beta": .88, "initial_variance": "SAMPLE", **extra}
        out, ll = garch_ll_case(inp)
        s.add(lop, inp, out, cls="likelihood_sum", verified=["mpmath-50", "lgamma-mpmath"], tags=["garch", "loglik", "stage-f"], limit=LL,
              output_classes={"variances": "statistics", "next_variance": "statistics"}, description=d)
        if extra.get("distribution") == "STUDENT_T":
            th = [inp["omega"], inp["alpha"], inp["beta"]]
            e = [mp.mpf(x) - mp.mpf(inp.get("mean", 0.0)) for x in short]
            init = mp.fsum(x * x for x in e) / len(e)
            nu = mp.mpf(extra["degrees_of_freedom"])
            # wrong convention: unit-scale t density (nu in place of nu - 2), rescaled by sqrt(nu/(nu-2)) is not unit variance
            wrong = mp.fsum(mp.loggamma((nu + 1) / 2) - mp.loggamma(nu / 2) - mp.log(mp.pi * nu) / 2 - mp.log(s2v) / 2
                            - (nu + 1) / 2 * mp.log(1 + x * x / (nu * s2v)) for x, s2v in zip(e, [mp.mpf(v) for v in out["variances"]]))
            caught("garch_f", f"{d}: nu in place of nu - 2", abs(f(wrong - ll)), 1e-9 + 1e-10 * abs(f(ll)))
            gl = garch_ll(e, th, "NORMAL", init)
            caught("garch_f", f"{d}: Gaussian loglik on t", abs(f(gl - ll)), 1e-9 + 1e-10 * abs(f(ll)))
    nu_big = garch_ll([mp.mpf(x) for x in short], [4e-6, .09, .88, 1e6], "STUDENT_T", mp.fsum(mp.mpf(x) ** 2 for x in short) / len(short))
    nrm = garch_ll([mp.mpf(x) for x in short], [4e-6, .09, .88], "NORMAL", mp.fsum(mp.mpf(x) ** 2 for x in short) / len(short))
    assert abs(nu_big - nrm) < 1e-3, "limit nu -> infinity"
    base = {"returns": short, "omega": 4e-6, "alpha": .09, "beta": .88, "initial_variance": "SAMPLE"}
    for d, chg, code in (("distribution not listed", {"distribution": "LAPLACE"}, "E_SCHEMA"),
                         ("Student-t without degrees_of_freedom", {"distribution": "STUDENT_T"}, "E_INPUT"),
                         ("nu = 2: variance not finite", {"distribution": "STUDENT_T", "degrees_of_freedom": 2.0}, "E_DOMAIN")):
        s.add(lop, {**base, **chg}, error=code, cls=E, tags=["invalid", "stage-f"], description=d)
    # estimate
    PL = {"absolute": 1e-14, "relative": 1e-6, "reason": "parameters agree to 1e-6 relative (plan R8); the optimum is Newton-polished"}
    oc = {"loglik": "likelihood_sum", "std_errors": "standard_error", "mean": A}
    report = []
    for key, r, dist, dm, truth in (("normal", rn, "NORMAL", False, TRUE_N), ("t", rt, "STUDENT_T", False, TRUE_T),
                                    ("normal demeaned", rnd, "NORMAL", True, TRUE_N), ("t demeaned", rtd, "STUDENT_T", True, TRUE_T)):
        inp = {"returns": r, "initial_variance": "SAMPLE", "distribution": dist, "demean": dm}
        out, th, ll, se = garch_estimate(inp)
        lim = dict(PL)
        s.add(eop, inp, out, cls=R, verified=["mpmath-50 jet Newton", "scipy multi-start", "Hessian negative definite"], tags=["garch", "estimate", "stage-f", key.replace(" ", "-")],
              limit=lim, output_classes=oc,
              description=f"simulated, true {truth}; seed {20261109 if not dm else 20261110}{', drift 4e-4' if dm else ''}")
        z = [abs(f(th[i]) - truth[i]) / f(se[i]) for i in range(len(th))]
        report.append(f"{key}: |estimate - truth| / SE = " + ", ".join(f"{x:.2f}" for x in z))
        # wrong conventions on the estimate
        if dm:
            o2 = garch_estimate(inp, "no-demean")[0]
            caught("garch_f", f"{key}: demean ignored", abs(o2["omega"] - out["omega"]), 1e-14 + 1e-6 * out["omega"])
        # SE on the parameters times 1.1 stands for a sandwich: the policy is 1e-5 relative on SEs
        caught("garch_f", f"{key}: SEs off by 1% (sandwich or expected information differ by more)", 0.01 * out["std_errors"]["alpha"], 1e-15 + 1e-5 * out["std_errors"]["alpha"])
    note("garch_f: " + "; ".join(report))
    s.add(eop, {"returns": rn[:29], "initial_variance": "SAMPLE", "distribution": "NORMAL", "demean": False}, error="E_INPUT", cls=E, tags=["invalid", "stage-f"],
          description="fewer than 30 returns")
    s.add(eop, {"returns": rt[:99], "initial_variance": "SAMPLE", "distribution": "STUDENT_T", "demean": False}, error="E_INPUT", cls=E, tags=["invalid", "stage-f"],
          description="Student-t needs at least 100 returns")
    s.add(eop, {"returns": rn[:100], "initial_variance": -1e-4, "distribution": "NORMAL", "demean": False}, error="E_DOMAIN", cls=E, tags=["invalid", "stage-f"],
          description="negative initial variance")
    s.add(eop, {"returns": rn[:100], "initial_variance": "SAMPLE", "distribution": "NORMAL", "demean": "yes"}, error="E_SCHEMA", cls=E, tags=["invalid", "stage-f"],
          description="demean must be a boolean")
    write(s)


def coverage():
    """R8 recovery: share of +-2 SE intervals holding the truth over 200 simulated series per distribution (float fits)."""
    out = {}
    for dist, truth in (("NORMAL", TRUE_N), ("STUDENT_T", TRUE_T)):
        hits = np.zeros(len(truth))
        for i in range(200):
            r = garch_sim_t(2000, *truth[:3], truth[3] if dist == "STUDENT_T" else None, 20261109 + i)
            th, mu, s0, _ = fit_float(r, dist, False)
            e = np.array(r)
            n = len(th)

            def ll(p):
                s2, v = s0, 0.0
                if dist == "NORMAL":
                    for x in e:
                        v -= 0.5 * (math.log(2 * math.pi) + math.log(s2) + x * x / s2)
                        s2 = p[0] + p[1] * x * x + p[2] * s2
                    return v
                nu = p[3]
                c = math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2) - 0.5 * math.log(math.pi * (nu - 2))
                for x in e:
                    v += c - 0.5 * math.log(s2) - (nu + 1) / 2 * math.log1p(x * x / ((nu - 2) * s2))
                    s2 = p[0] + p[1] * x * x + p[2] * s2
                return v
            hs = [1e-4 * abs(x) for x in th]
            H = np.zeros((n, n))
            for a in range(n):
                for b in range(a, n):
                    def at(da, db):
                        p = list(th)
                        p[a] += da * hs[a]
                        p[b] += db * hs[b]
                        return ll(p)
                    H[a, b] = H[b, a] = (at(1, 1) - at(1, -1) - at(-1, 1) + at(-1, -1)) / (4 * hs[a] * hs[b])
            se = np.sqrt(np.diag(np.linalg.inv(-H)))
            hits += np.abs(np.array(th) - np.array(truth)) <= 2 * se
        out[dist] = (hits / 200).tolist()
    note(f"garch_f recovery (200 series of 2,000, +-2 SE coverage, band [0.90, 0.99]): {out}")
    for d, v in out.items():
        for x in v:
            assert 0.90 <= x <= 0.99, (d, v)
    (HERE.parents[0] / "R8_COVERAGE.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")


# ===================================================================================== R10 VIX null quotes, Cboe strip; local vol continuity
NY, N30 = 525600, 43200


def vix_term_f(inp, mutant=None):
    """Cboe v5.0 with null quotes (ruling F-15). Exact rationals; exp(RT) at 50 digits."""
    strip = sorted(inp["strip"], key=lambda x: x["strike"])
    T = Fr(inp["minutes_to_expiry"], NY)
    Rr = Fr(inp["rate"])
    eRT = mp.exp(mp.mpf(Rr.numerator) / Rr.denominator * mp.mpf(T.numerator) / T.denominator)
    K = [Fr(x["strike"]) for x in strip]
    cnull = [x["call_bid"] is None or x["call_ask"] is None for x in strip]
    pnull = [x["put_bid"] is None or x["put_ask"] is None for x in strip]
    mid = lambda b, a: None if b is None or a is None else (Fr(b) + Fr(a)) / 2  # noqa: E731
    C = [mid(x["call_bid"], x["call_ask"]) for x in strip]
    P = [mid(x["put_bid"], x["put_ask"]) for x in strip]
    cand = [i for i in range(len(K)) if (not cnull[i] and not pnull[i]) or mutant == "null-candidate"]
    if not cand:
        raise ValueError("E_INPUT")
    diffs = {i: abs((C[i] or 0) - (P[i] or 0)) for i in cand}
    j = min(cand, key=lambda i: (diffs[i], K[i]))
    Fw = K[j] + eRT * ((C[j] or 0) - (P[j] or 0))
    below = [i for i in range(len(K)) if K[i] <= Fw]
    if not below:
        raise ValueError("E_INPUT")
    i0 = below[-1]
    if cnull[i0] or pnull[i0]:
        raise ValueError("E_INPUT")
    sel = {i0: (C[i0] + P[i0]) / 2}
    for rng, bidk, q, nul in ((range(i0 - 1, -1, -1), "put_bid", P, pnull), (range(i0 + 1, len(K)), "call_bid", C, cnull)):
        zeros = 0
        for i in rng:
            other = cnull if nul is pnull else pnull
            if nul[i] or (mutant == "null-both-sides" and other[i]):
                if mutant == "null-as-zero":
                    zeros += 1
                    if zeros == 2:
                        break
                continue
            if Fr(strip[i][bidk]) == 0:
                zeros += 1
                if zeros == 2:
                    break
                continue
            zeros = 0
            sel[i] = q[i]
    ks = sorted(sel)
    if not any(i < i0 for i in ks) or not any(i > i0 for i in ks):
        raise ValueError("E_INPUT")
    dK = {}
    for n, i in enumerate(ks):
        lo, hi = ks[max(n - 1, 0)], ks[min(n + 1, len(ks) - 1)]
        dK[i] = (K[hi] - K[lo]) / (2 if 0 < n < len(ks) - 1 else 1)
    contrib = sum(dK[i] / K[i] ** 2 * sel[i] for i in ks)
    Tm = mp.mpf(T.numerator) / T.denominator
    var = 2 / Tm * eRT * mp.mpf(contrib.numerator) / contrib.denominator - 1 / Tm * (Fw / mp.mpf(K[i0].numerator / K[i0].denominator) - 1) ** 2
    return {"forward": f(Fw), "k0": f(K[i0]), "variance": f(var), "strikes_used": [f(K[i]) for i in ks]}, var, Tm


def vix_index_f(inp):
    n, x = inp["near"], inp["next"]
    o1, v1, T1 = vix_term_f(n)
    o2, v2, T2 = vix_term_f(x)
    N1, N2 = n["minutes_to_expiry"], x["minutes_to_expiry"]
    w1, w2 = mp.mpf(N2 - N30) / (N2 - N1), mp.mpf(N30 - N1) / (N2 - N1)
    return {"index": f(100 * mp.sqrt((T1 * v1 * w1 + T2 * v2 * w2) * mp.mpf(NY) / N30)), "near_variance": o1["variance"], "next_variance": o2["variance"]}


def r10():
    from gen_stage_e_b import vix_term
    s = S("vix_f", "05-volatility/vix-index.md")
    top, iop = "vol.vix.term_variance", "vol.vix.index"
    LIM = {"absolute": 1e-12, "relative": 1e-10, "reason": "as vix_e"}
    data = json.loads((HERE / "data" / "cboe_vix_sample_2022-09-27.json").read_text(encoding="utf-8"))
    near = {"minutes_to_expiry": 34484, "rate": 0.00031664, "strip": data["near"]}
    nxt = {"minutes_to_expiry": 44954, "rate": 0.00028797, "strip": data["next"]}
    o1, v1, _ = vix_term_f(near)
    o2, v2, _ = vix_term_f(nxt)
    assert o1 == vix_term(near)[0] and o2 == vix_term(nxt)[0], "null-free strip must give the stage E result"
    # the printed digits of Cboe Volatility Index Methodology v6.0, Appendix 3
    assert round(o1["forward"], 5) == 1962.89996 and round(o2["forward"], 5) == 1962.40006 and o1["k0"] == o2["k0"] == 1960.0
    assert round(o1["variance"], 9) == 0.019233906 and round(o2["variance"], 9) == 0.019423884
    assert len(o1["strikes_used"]) == 146 and len(o2["strikes_used"]) == 122
    assert o1["strikes_used"][0] == 1370 and o1["strikes_used"][-1] == 2125 and o2["strikes_used"][0] == 1275 and o2["strikes_used"][-1] == 2200
    ix = vix_index_f({"near": near, "next": nxt})
    assert round(ix["index"] / 100, 8) == 0.13927842 and round(ix["index"], 2) == 13.93
    vb = ["cboe-vix-methodology-v6.0-appendix-3", "exact-rational"]
    s.add(top, near, o1, cls=A, verified=vb, tags=["vix", "cboe-sample", "outside"], limit=LIM, description="Cboe sample calculation, near term (SPX 2022-10-21, 34,484 minutes)")
    s.add(top, nxt, o2, cls=A, verified=vb, tags=["vix", "cboe-sample", "outside"], limit=LIM, description="Cboe sample calculation, next term (SPXW 2022-10-28, 44,954 minutes)")
    s.add(iop, {"near": near, "next": nxt}, ix, cls=A, verified=vb, tags=["vix", "index", "cboe-sample", "outside"],
          output_classes={"near_variance": A, "next_variance": A}, limit={"absolute": 1e-8, "relative": 1e-10, "reason": "index points"},
          description="Cboe sample calculation: VIX 13.93 (printed 100 x 0.13927842)")
    # null-quote cases on the stage E hand strip, widened so that walks matter
    hand = [
        {"strike": 75.0, "call_bid": 24.5, "call_ask": 26.0, "put_bid": 0.05, "put_ask": 0.1},
        {"strike": 80.0, "call_bid": 19.5, "call_ask": 21.0, "put_bid": 0.1, "put_ask": 0.2},
        {"strike": 85.0, "call_bid": 15.0, "call_ask": 16.0, "put_bid": 0.0, "put_ask": 0.1},
        {"strike": 90.0, "call_bid": 10.5, "call_ask": 11.5, "put_bid": 0.5, "put_ask": 0.7},
        {"strike": 95.0, "call_bid": 6.0, "call_ask": 6.6, "put_bid": 1.4, "put_ask": 1.6},
        {"strike": 100.0, "call_bid": 2.9, "call_ask": 3.1, "put_bid": 2.9, "put_ask": 3.3},
        {"strike": 105.0, "call_bid": 1.0, "call_ask": 1.2, "put_bid": 5.8, "put_ask": 6.6},
        {"strike": 110.0, "call_bid": 0.3, "call_ask": 0.5, "put_bid": 10.0, "put_ask": 11.0},
        {"strike": 115.0, "call_bid": 0.0, "call_ask": 0.1, "put_bid": 14.5, "put_ask": 15.5},
        {"strike": 120.0, "call_bid": 0.05, "call_ask": 0.15, "put_bid": 19.5, "put_ask": 20.5}]
    base = {"minutes_to_expiry": 43200, "rate": 0.0, "strip": hand}
    ob = vix_term_f(base)[0]
    s.add(top, base, ob, cls=A, verified=["hand", "exact-rational"], tags=["vix", "hand", "stage-f"], limit=LIM, description="ten-strike hand strip, no nulls")

    def with_null(changes):
        st = [dict(x) for x in hand]
        for ch in changes:
            k, field, val = ch if len(ch) == 3 else (*ch, None)
            st[[x["strike"] for x in st].index(k)][field] = val
        return {**base, "strip": st}
    cases = [
        ("null call ask at the smallest |C - P| strike (100): K* moves to 95", [(100.0, "call_ask")], ("null-candidate",)),
        ("null put at 85, zero put bid at 80: the null is removed, so 80 is the first zero and the walk reaches 75",
         [(85.0, "put_bid"), (85.0, "put_ask"), (85.0, "put_bid", None), (80.0, "put_bid", 0.0)], ("null-as-zero",)),
        ("null call at 90 (deep in the money): put at 90 still used", [(90.0, "call_bid")], ("null-both-sides",)),
        ("null put at 115 and null call bid at 120: calls stop as before", [(115.0, "put_bid"), (120.0, "call_bid")], ()),
    ]
    for d, ch, muts in cases:
        inp = with_null(ch)
        o = vix_term_f(inp)[0]
        s.add(top, inp, o, cls=A, verified=["hand", "exact-rational"], tags=["vix", "null-quote", "ruling", "stage-f"], limit=LIM, description=d)
        for m in muts:
            try:
                ov = vix_term_f(inp, m)[0]["variance"]
            except (ValueError, TypeError):
                MUTANTS.append(("vix_f", f"{d}: {m} (fails)", 1.0))
                continue
            caught("vix_f", f"{d}: {m}", abs(ov - o["variance"]), 1e-12 + 1e-10 * abs(o["variance"]))
    for d, ch in (("K0 put is null: cannot be calculated", [(95.0, "put_ask")]),
                  ("every strike has a null side: no ATM candidate", [(k, "put_bid") for k in (75.0, 80.0, 85.0, 90.0, 95.0)] + [(k, "call_bid") for k in (100.0, 105.0, 110.0, 115.0, 120.0)])):
        inp = with_null(ch)
        try:
            vix_term_f(inp)
            raise AssertionError(d)
        except ValueError:
            pass
        s.add(top, inp, error="E_INPUT", cls=E, tags=["invalid", "null-quote", "ruling", "stage-f"], description=d)
    write(s, synthetic=False)
    lvc()


def lvc():
    from gen_stage_e_a import SURF, dupire, mp_dupire
    s = S("lvc_f", "05-volatility/local-and-forward-vol.md")
    op = "vol.local.dupire"
    two = SURF[:2]
    for name, surf in (("three-slice", SURF), ("two-slice", two)):
        Ts = [x["expiry_years"] for x in surf]
        pts = []
        for k in (-0.4, 0.0, 0.3):
            for j, Tj in enumerate(Ts):
                pts += [(Tj * (1 - 1e-9), k), (Tj, k), (Tj * (1 + 1e-9), k)]
            edges = [0.0] + Ts + [Ts[-1] * 1.5]
            for a, b in zip(edges, edges[1:]):
                pts += [(a + (b - a) * u, k) for u in (0.1, 0.3, 0.5, 0.7, 0.9)]
        out = {"total_variance": [], "implied_vol": [], "local_vol": []}
        for T, k in pts:
            w, g, wT = dupire(surf, T, k)
            assert g > 1e-4 and wT > 1e-6, (name, T, k)
            lv = math.sqrt(wT / g)
            out["total_variance"].append(w)
            out["implied_vol"].append(math.sqrt(w / T))
            out["local_vol"].append(lv)
        for idx in range(0, len(pts), 1):
            T, k = pts[idx]
            if idx % 7 == 0:
                alt = mp_dupire(surf, T, k)
                assert abs(alt - out["local_vol"][idx]) < 1e-8 * alt, (name, T, k, alt, out["local_vol"][idx])
        # continuity assertions, and the jump formula at every slice expiry
        for i, (T, k) in enumerate(pts):
            if T in Ts:
                wl, wn = out["total_variance"][i - 1], out["total_variance"][i]
                assert abs(wl - wn) <= 1e-8 * wn
                assert abs(out["implied_vol"][i - 1] - out["implied_vol"][i]) <= 1e-8 * out["implied_vol"][i]
                j = Ts.index(T)
                wj, gj, _ = dupire(surf, T, k)
                from gen_stage_e_a import P5, svi_d
                wjk = svi_d(P5(surf[j]["svi"]), k)[0]
                left = wjk / T if j == 0 else (wjk - svi_d(P5(surf[j - 1]["svi"]), k)[0]) / (T - Ts[j - 1])
                right = (svi_d(P5(surf[j + 1]["svi"]), k)[0] - wjk) / (Ts[j + 1] - T) if j + 1 < len(Ts) else wjk / T
                assert abs(out["local_vol"][i - 1] - math.sqrt(left / gj)) <= 2e-8 * out["local_vol"][i - 1]
                assert abs(out["local_vol"][i] - math.sqrt(right / gj)) <= 1e-12 * out["local_vol"][i]
                if j + 1 < len(Ts):
                    caught("lvc_f", f"{name} T={T} k={k}: node averaged across the jump", abs(out["local_vol"][i] - (math.sqrt(left / gj) + math.sqrt(right / gj)) / 2), 1e-10 + 1e-8 * out["local_vol"][i])
        inp = {"slices": surf, "points": [{"expiry_years": T, "log_moneyness": k} for T, k in pts]}
        s.add(op, inp, out, cls=I, verified=["analytic", "mpmath-price-dupire-40-digits"], tags=["dupire", "continuity", "stage-f", name],
              description=f"{name}: points at T_j(1 -+ 1e-9), at T_j, and inside each interval, k in (-0.4, 0, 0.3)")
    one = SURF[1:2]
    pts = [(1.0 * (1 - 1e-9), 0.0), (1.0, 0.0), (1.0 * (1 + 1e-9), 0.0), (0.3, -0.2), (2.5, 0.2)]
    o1 = {"total_variance": [], "implied_vol": [], "local_vol": []}
    for T, k in pts:
        w, g, wT = dupire(one, T, k)
        o1["total_variance"].append(w)
        o1["implied_vol"].append(math.sqrt(w / T))
        o1["local_vol"].append(math.sqrt(wT / g))
    assert abs(o1["local_vol"][0] - o1["local_vol"][1]) < 1e-8 * o1["local_vol"][1], "one slice: no jump (g moves by 1e-9 with T)"
    s.add(op, {"slices": one, "points": [{"expiry_years": T, "log_moneyness": k} for T, k in pts]}, o1, cls=I, verified=["analytic"],
          tags=["dupire", "continuity", "stage-f", "one-slice"], description="one slice: flat vol, no jump at the slice expiry")
    write(s)


SLICES = {"R7": r7, "R8": r8, "R10": r10, "COVER": coverage}


def main():
    names = sys.argv[1:] or ["R7", "R8", "R10"]
    for n in names:
        MUTANTS.clear()
        SLICES[n]()
        if MUTANTS:
            note(f"F6 {n}: {len(MUTANTS)} wrong conventions caught")


if __name__ == "__main__":
    main()
