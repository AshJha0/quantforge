"""Stage E golden cases, spec B slices (E4, E6, E7, E8). This file: shared helpers and E7.

All market data is synthetic. Goldens come from this file's own replicas (mpmath at 50 digits or exact rationals); QuantLib is
used only by the separate verifier `outside_e_b.py` (plan rule 11.2.5), never to write an expected value. No golden depends
on maths-library last-digit rounding, unseeded Monte Carlo, or a solver's path: fits are judged on the objective at the
optimum (checked by gradient and curvature), and every suite stops if its tolerance would let a named wrong convention through.

    cd oracle/python && uv run python -W ignore gen_stage_e_b.py [E7|E4|E6|E8 ...]
"""
import math
import sys
from datetime import date
from fractions import Fraction as Fr

import mpmath as mp
import numpy as np

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_e_b.py"
E, A, R, I, Q = "date_and_convention", "simple_analytic", "root_finding", "interpolation", "quadrature"
STAT = "statistics"
SYN = "synthetic"
AS_OF = date(2026, 11, 6)
MUTANTS = []
FOLDER = "stage_e_b"


def S(name, spec):
    return Suite(name, f"specifications/{spec}", G)


def write(s):
    keep = common.GOLDEN
    for c in s.cases:
        if SYN not in c["tags"]:
            c["tags"].append(SYN)
    common.GOLDEN = keep.parent / FOLDER
    s.write()
    common.GOLDEN = keep


def caught(suite, name, gap, tol):
    assert gap > tol, f"{suite}: mutant '{name}' is not caught: gap {gap:.3e}, tolerance {tol:.3e}"
    MUTANTS.append((suite, name, gap))


f = float


# ===================================================================================== E7 GARCH(1,1)
def garch_path(r, om, al, be, init):
    """Conditional variances sigma2_1..sigma2_{n+1} and the Gaussian log-likelihood, in mpmath. r are mpf."""
    n = len(r)
    s2 = [mp.fsum(x * x for x in r) / n if init == "SAMPLE" else mp.mpf(init)]
    for t in range(1, n + 1):
        s2.append(om + al * r[t - 1] ** 2 + be * s2[t - 1])
    ll = -mp.mpf(1) / 2 * mp.fsum(mp.log(2 * mp.pi) + mp.log(s2[t]) + r[t] ** 2 / s2[t] for t in range(n))
    return s2, ll


def garch_sim(n, om, al, be, seed):
    """Fixed synthetic return series (the seed only makes the input data; outputs never depend on draws)."""
    g = np.random.default_rng(seed)
    z = g.standard_normal(n + 200)
    s2, out = om / (1 - al - be), []
    for zt in z:
        x = math.sqrt(s2) * zt
        out.append(x)
        s2 = om + al * x * x + be * s2
    return [round(x, 10) for x in out[200:]]


def garch_forecast(om, al, be, nv, H, ppy):
    om, al, be, nv = map(mp.mpf, (om, al, be, nv))
    VL = om / (1 - al - be)
    v = [VL + (al + be) ** (h - 1) * (nv - VL) for h in range(1, H + 1)]
    tot = mp.fsum(v)
    return {"variances": [f(x) for x in v], "total_variance": f(tot), "annualized_vol": f(mp.sqrt(tot * ppy / H)), "long_run_variance": f(VL)}


def garch_fit(r):
    """Maximum likelihood with init SAMPLE. Multi-start scipy, then Newton in mpmath; returns (params, ll) after checking
    the gradient is below 1e-12 relative and the Hessian negative definite (interior optimum)."""
    from scipy.optimize import minimize
    rf = np.array(r)
    s0 = float(np.mean(rf * rf))

    def nll(p):
        om, al, be = p
        if om <= 0 or al < 0 or be < 0 or al + be >= 1:
            return 1e10
        s2, ll = s0, 0.0
        for x in rf:
            ll += math.log(s2) + x * x / s2
            s2 = om + al * x * x + be * s2
        return 0.5 * ll
    best = None
    for st in ((s0 * .05, .05, .90), (s0 * .2, .1, .7), (s0 * .02, .03, .95), (s0 * .5, .2, .3)):
        m = minimize(nll, st, method="Nelder-Mead", options={"xatol": 1e-12, "fatol": 1e-12, "maxiter": 40000, "maxfev": 80000})
        if best is None or m.fun < best.fun:
            best = m
    rm = [mp.mpf(x) for x in r]
    p = mp.matrix([mp.mpf(x) for x in best.x])
    F = lambda a, b, c: garch_path(rm, a, b, c, "SAMPLE")[1]  # noqa: E731
    for _ in range(8):
        gr = mp.matrix([mp.diff(lambda x: F(x, p[1], p[2]), p[0]), mp.diff(lambda x: F(p[0], x, p[2]), p[1]), mp.diff(lambda x: F(p[0], p[1], x), p[2])])
        H = mp.matrix(3, 3)
        for i in range(3):
            for j in range(3):
                o = [0, 0, 0]
                o[i] += 1
                o[j] += 1
                H[i, j] = mp.diff(lambda a, b, c: F(a, b, c), (p[0], p[1], p[2]), tuple(o))
        p = p - mp.lu_solve(H, gr)
    gr = [mp.diff(lambda x: F(x, p[1], p[2]), p[0]), mp.diff(lambda x: F(p[0], x, p[2]), p[1]), mp.diff(lambda x: F(p[0], p[1], x), p[2])]
    assert all(abs(g) * abs(x) < 1e-20 for g, x in zip(gr, p)), "GARCH fit: gradient not zero"
    ev = mp.eigsy(H)[0]
    assert all(e < 0 for e in ev), "GARCH fit: not a maximum"
    assert p[0] > 0 and p[1] > 0 and p[2] > 0 and p[1] + p[2] < 1, "GARCH fit: optimum on a bound"
    ll = F(p[0], p[1], p[2])
    assert ll + best.fun + 0.5 * len(r) * math.log(2 * math.pi) > -1e-6, "Nelder-Mead beat Newton: not the global optimum"
    return [f(x) for x in p], ll


def garch_e():
    s = S("garch_e", "05-volatility/garch.md")
    LIM = {"absolute": 1e-9, "relative": 1e-10, "reason": "sum of n logs; libm last digits move each term by 1e-16 relative"}
    VLIM = {"absolute": 1e-16, "relative": 1e-11, "reason": "variances near 1e-4: 1e-11 relative is 1e-9 in annualised vol"}
    series = {
        "A": garch_sim(500, 2e-6, .08, .90, 20261106),
        "B": garch_sim(250, 5e-6, .12, .82, 7),
        "C": [.01, -.02, .015, 0.0, -.005, .03, -.025, .01],
    }
    lop = "vol.garch.loglik"
    for key, om, al, be, init in (("C", 1e-5, .1, .85, "SAMPLE"), ("C", 1e-5, .1, .85, 2.5e-4), ("A", 2e-6, .08, .90, "SAMPLE"), ("A", 3e-6, .05, .92, "SAMPLE"),
                                  ("A", 2e-6, .08, .90, 1e-4), ("B", 5e-6, .12, .82, "SAMPLE"), ("B", 1e-6, .0, .99, "SAMPLE"), ("B", 5e-6, .3, .7, "SAMPLE")):
        r = series[key]
        rm = [mp.mpf(x) for x in r]
        s2, ll = garch_path(rm, mp.mpf(om), mp.mpf(al), mp.mpf(be), init)
        out = {"loglik": f(ll), "variances": [f(x) for x in s2[:-1]], "next_variance": f(s2[-1])}
        s.add(lop, {"returns": r, "omega": om, "alpha": al, "beta": be, "initial_variance": init}, out, cls=STAT, verified=["independent-replay", "mpmath-50"],
              tags=["garch", f"series-{key}"] + (["integrated"] if al + be >= 1 else []), output_classes={"loglik": "likelihood_sum" if len(r) > 10 else STAT}, limit=VLIM)
        if init == "SAMPLE":
            _, l2 = garch_path(rm, mp.mpf(om), mp.mpf(al), mp.mpf(be), rm[0] ** 2)
            caught("garch_e", f"{key}: init r_1^2 instead of sample variance", abs(f(l2 - ll)), 1e-9 + 1e-10 * abs(f(ll)))
        caught("garch_e", f"{key}: no ln(2 pi) constant", len(r) * math.log(2 * math.pi) / 2, 1e-9 + 1e-10 * abs(f(ll)))
        s2b = [s2[0]] + [mp.mpf(om) + al * rm[min(t, len(r) - 1)] ** 2 + be * s2[t - 1] for t in range(1, len(r))]
        llb = -mp.mpf(1) / 2 * mp.fsum(mp.log(2 * mp.pi) + mp.log(s2b[t]) + rm[t] ** 2 / s2b[t] for t in range(len(r)))
        if al > 0:
            caught("garch_e", f"{key}: same-day return in the recursion", abs(f(llb - ll)), 1e-9 + 1e-10 * abs(f(ll)))
    # Hand case: two returns, worked in garch.md.
    r = [.01, -.02]
    s2, ll = garch_path([mp.mpf(x) for x in r], mp.mpf("1e-5"), mp.mpf(".1"), mp.mpf(".8"), "SAMPLE")
    assert abs(s2[0] - mp.mpf("2.5e-4")) < 1e-18 and abs(s2[1] - mp.mpf("2.2e-4")) < 1e-18 and abs(s2[2] - mp.mpf("2.26e-4")) < 1e-18
    s.add(lop, {"returns": r, "omega": 1e-5, "alpha": .1, "beta": .8, "initial_variance": "SAMPLE"}, {"loglik": f(ll), "variances": [f(x) for x in s2[:-1]], "next_variance": f(s2[-1])},
          cls=STAT, verified=["hand", "mpmath-50"], tags=["garch", "hand"], output_classes={"loglik": STAT}, limit=VLIM)
    b = {"returns": series["C"], "omega": 1e-5, "alpha": .1, "beta": .85, "initial_variance": "SAMPLE"}
    for d, bad, code in (("omega must be positive", {"omega": 0.0}, "E_DOMAIN"), ("alpha negative", {"alpha": -.01}, "E_DOMAIN"), ("beta negative", {"beta": -.01}, "E_DOMAIN"),
                         ("initial variance must be positive", {"initial_variance": 0.0}, "E_DOMAIN"), ("unknown initial variance rule", {"initial_variance": "FIRST"}, "E_INPUT"),
                         ("at least two returns", {"returns": [.01]}, "E_INPUT"), ("all-zero returns with SAMPLE", {"returns": [0.0, 0.0, 0.0]}, "E_DOMAIN")):
        s.add(lop, {**b, **bad}, error=code, cls=E, tags=["invalid"], description=d)
    # Forecast
    fop = "vol.garch.forecast"
    for om, al, be, nv, H, ppy in ((2e-6, .08, .90, 1.5e-4, 1, 252), (2e-6, .08, .90, 1.5e-4, 21, 252), (2e-6, .08, .90, 5e-5, 252, 252), (5e-6, .12, .82, 3e-4, 10, 252),
                                   (1e-5, .1, .85, 2.15e-4, 5, 252), (2e-6, .0, .0, 1e-4, 3, 252)):
        out = garch_forecast(om, al, be, nv, H, ppy)
        s.add(fop, {"omega": om, "alpha": al, "beta": be, "next_variance": nv, "horizon": H, "periods_per_year": ppy}, out, cls=A, verified=["independent-replay", "mpmath-50"],
              tags=["garch", "forecast"], limit=VLIM)
        if H > 1 and al + be > 0:
            VL = om / (1 - al - be)
            wrong = [VL + (al + be) ** h * (nv - VL) for h in range(1, H + 1)]
            caught("garch_e", f"forecast H={H}: exponent h not h-1", abs(sum(wrong) - out["total_variance"]), 1e-16 + 1e-11 * out["total_variance"])
    s.add(fop, {"omega": 1e-5, "alpha": .1, "beta": .9, "next_variance": 1e-4, "horizon": 5, "periods_per_year": 252}, error="E_DOMAIN", cls=E, tags=["invalid", "ruling"],
          description="alpha + beta = 1: no long-run variance")
    s.add(fop, {"omega": 1e-5, "alpha": .1, "beta": .8, "next_variance": 1e-4, "horizon": 0, "periods_per_year": 252}, error="E_INPUT", cls=E, tags=["invalid"], description="horizon at least 1")
    s.add(fop, {"omega": 0.0, "alpha": .1, "beta": .8, "next_variance": 1e-4, "horizon": 5, "periods_per_year": 252}, error="E_DOMAIN", cls=E, tags=["invalid"], description="omega must be positive")
    s.add(fop, {"omega": 1e-5, "alpha": .1, "beta": .8, "next_variance": 0.0, "horizon": 5, "periods_per_year": 252}, error="E_DOMAIN", cls=E, tags=["invalid"], description="next_variance must be positive")
    # Fit: judged on the log-likelihood at the optimum (policy class calibration: objective, not parameters).
    pop = "vol.garch.fit"
    for key in ("A", "B"):
        r = series[key]
        p, ll = garch_fit(r)
        s.add(pop, {"returns": r, "initial_variance": "SAMPLE"}, {"loglik": f(ll)}, cls=R, verified=["independent-replay", "mpmath-50 Newton", "scipy multi-start"],
              tags=["garch", "fit", "calibration"], limit={"absolute": 1e-6, "relative": 0.0, "reason": "objective at the optimum, not parameters (garch.md, ruling E-B16): class root_finding with this limit"},
              description=f"maximum at omega={p[0]:.6e}, alpha={p[1]:.6f}, beta={p[2]:.6f} (informative, not compared)")
        rm = [mp.mpf(x) for x in r]
        llp = garch_path(rm, mp.mpf(p[0]) * 1.05, mp.mpf(p[1]), mp.mpf(p[2]), "SAMPLE")[1]
        caught("garch_e", f"fit {key}: omega 5% off the optimum", f(ll - llp), 1e-6)
    s.add(pop, {"returns": [.01, -.01, .01], "initial_variance": "SAMPLE"}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="fit needs at least 30 returns")
    note("garch_e: log-likelihood and variances in mpmath at 50 digits; fit maximum by Nelder-Mead from four starts, polished by Newton, gradient and Hessian checked")
    write(s)


# ===================================================================================== E7 variance swaps
def act365(a, b):
    return Fr((b - a).days, 365)


def varswap(inp):
    """Demeterfi-Derman-Kamal-Zou discrete replication, reference point S* = spot. Black prices in mpmath."""
    S0, r, q = mp.mpf(inp["spot"]), mp.mpf(inp["rate"]), mp.mpf(inp["dividend_yield"])
    T = mp.mpf(act365(date.fromisoformat(inp["as_of"]), date.fromisoformat(inp["maturity"])))
    vol = {x["strike"]: mp.mpf(x["vol"]) for x in inp["vols"]}
    D, F = mp.exp(-r * T), S0 * mp.exp((r - q) * T)
    pay = lambda K: 2 / T * ((K - S0) / S0 - mp.log(K / S0))  # noqa: E731

    def weights(ks, call):
        ks = sorted(mp.mpf(k) for k in ks)
        dk = mp.mpf(inp["extension_step"])
        ks = ks + [ks[-1] + dk] if call else ([ks[0] - dk] + ks)[::-1]
        out, prev = [], 0
        for i in range(len(ks) - 1):
            sl = abs((pay(ks[i + 1]) - pay(ks[i])) / (ks[i + 1] - ks[i]))
            out.append((ks[i], sl - prev))
            prev = sl
        return out

    def black(call, K):
        v = vol[float(K)] * mp.sqrt(T)
        d1 = (mp.log(F / K) + v * v / 2) / v
        d2 = d1 - v
        N = lambda x: mp.ncdf(x)  # noqa: E731
        return D * (F * N(d1) - K * N(d2)) if call else D * (K * N(-d2) - F * N(-d1))
    wc, wp = weights(inp["call_strikes"], True), weights(inp["put_strikes"], False)
    port = mp.fsum(w * black(True, K) for K, w in wc) + mp.fsum(w * black(False, K) for K, w in wp)
    var = 2 / T * ((r - q) * T - (F / S0 - 1)) + port / D
    pv = mp.mpf(inp["variance_notional"]) * D * (var - mp.mpf(inp["variance_strike"]))
    return {"fair_variance": f(var), "fair_vol": f(mp.sqrt(var)), "pv": f(pv)}, (port, D, T, r, q, F, S0)


def realized(inp):
    p = [mp.mpf(x) for x in inp["prices"]]
    lr = [mp.log(p[i] / p[i - 1]) for i in range(1, len(p))]
    rv = mp.mpf(inp["periods_per_year"]) / len(lr) * mp.fsum(x * x for x in lr)
    pay = mp.mpf(inp["variance_notional"]) * (rv - mp.mpf(inp["variance_strike"]))
    return {"realized_variance": f(rv), "realized_vol": f(mp.sqrt(rv)), "payoff": f(pay)}, lr


def varswap_e():
    s = S("varswap_e", "05-volatility/variance-swaps.md")
    op = "vol.varswap.fair_strike"
    smile = lambda K, S0, a, b: round(a - b * math.log(K / S0), 6)  # noqa: E731
    specs = [
        ("2027-11-06", 100.0, .04, 0.0, [50, 60, 70, 80, 90, 100], [100, 110, 120, 130, 140, 150], 10.0, .2, 0.0, .04),
        ("2027-05-07", 100.0, .04, 0.0, [60, 70, 80, 90, 100], [100, 110, 120, 130, 140], 5.0, .2, .15, .05),
        ("2027-11-06", 4500.0, .035, 0.0, [2700 + 150 * i for i in range(13)], [4500 + 150 * i for i in range(9)], 150.0, .18, .12, .035),
        ("2026-12-18", 4500.0, .035, 0.0, [3600 + 50 * i for i in range(19)], [4500 + 50 * i for i in range(11)], 50.0, .16, .2, .02),
        ("2028-11-06", 50.0, .03, 0.0, [20, 25, 30, 35, 40, 45, 50], [50, 55, 60, 70, 80, 100], 5.0, .3, .1, .09),
        ("2027-11-06", 100.0, -.005, 0.0, [70, 80, 90, 100], [100, 110, 120, 130], 10.0, .25, 0.0, .06),
        ("2027-11-06", 100.0, .04, .015, [50, 60, 70, 80, 90, 100], [100, 110, 120, 130, 140, 150], 10.0, .2, .1, .04),
        ("2027-11-06", 4500.0, .035, .013, [2700 + 150 * i for i in range(13)], [4500 + 150 * i for i in range(9)], 150.0, .18, .12, .035),
    ]
    # Strip-density and maturity grid on one smile (q = 0): finer strips converge towards the continuous log contract.
    for mat in ("2027-02-05", "2027-11-06", "2029-11-06"):
        for step in (20, 10, 5, 2.5):
            n = int(50 / step)
            specs.append((mat, 100.0, .03, 0.0, sorted(100 - step * i for i in range(n + 1)), [100 + step * i for i in range(int(100 / step) + 1)], step, .22, .18, .05))
    for mat, S0, r, q, ps, cs, dk, a, b, Kv in specs:
        ks = sorted(set(ps + cs))
        inp = {"as_of": AS_OF.isoformat(), "maturity": mat, "spot": S0, "rate": r, "dividend_yield": q, "put_strikes": [float(k) for k in ps], "call_strikes": [float(k) for k in cs],
               "vols": [{"strike": float(k), "vol": smile(k, S0, a, b)} for k in ks], "extension_step": dk, "variance_strike": Kv, "variance_notional": 1e6}
        out, (port, D, T, rr, qq, F, S_) = varswap(inp)
        s.add(op, inp, out, cls=A, verified=["independent-replay", "mpmath-50"] + (["quantlib-1.44 ReplicatingVarianceSwapEngine (q=0)"] if q == 0 else []),
              output_classes={"fair_variance": A, "fair_vol": A},
              tags=["varswap"] + (["dividend"] if q else []) + (["negative-rate"] if r < 0 else []),
              limit={"absolute": 1e-12 * 1e6, "relative": 1e-10, "reason": "1e-12 in variance per unit of variance notional: 1e-6 currency on 1e6"})
        tol = 1e-6 + 1e-10 * abs(out["pv"])
        if q:
            qlvar = 2 / T * (rr * T - (1 / D - 1)) + port / D  # QuantLib's drift term uses r only
            caught("varswap_e", f"{mat} q={q}: drift r instead of r - q (QuantLib's form)", abs(f(1e6 * D * (qlvar - out["fair_variance"]))), tol)
        if r != 0:
            caught("varswap_e", f"{mat}: strip not grown at the rate (port, not port/D)", abs(f(1e6 * D * (port - port / D))), tol)
    b = specs[0]
    base = {"as_of": AS_OF.isoformat(), "maturity": b[0], "spot": 100.0, "rate": .04, "dividend_yield": 0.0, "put_strikes": [80.0, 90.0, 100.0], "call_strikes": [100.0, 110.0, 120.0],
            "vols": [{"strike": float(k), "vol": .2} for k in (80, 90, 100, 110, 120)], "extension_step": 10.0, "variance_strike": .04, "variance_notional": 1e6}
    for d, bad, code in (("put strike above spot", {"put_strikes": [80.0, 90.0, 105.0]}, "E_INPUT"), ("call strike below spot", {"call_strikes": [95.0, 110.0, 120.0]}, "E_INPUT"),
                         ("missing vol for a strike", {"vols": base["vols"][:-1]}, "E_INPUT"), ("extension step not positive", {"extension_step": 0.0}, "E_DOMAIN"),
                         ("maturity not after as_of", {"maturity": AS_OF.isoformat()}, "E_INPUT"), ("extension takes the lowest put to zero", {"extension_step": 80.0}, "E_DOMAIN"),
                         ("duplicate strike in a list", {"put_strikes": [80.0, 90.0, 90.0, 100.0]}, "E_INPUT"),
                         ("spot not positive", {"spot": 0.0, "put_strikes": [0.0], "call_strikes": [0.0], "vols": [{"strike": 0.0, "vol": .2}]}, "E_DOMAIN"),
                         ("vol not positive", {"vols": base["vols"][:-1] + [{"strike": 120.0, "vol": 0.0}]}, "E_DOMAIN")):
        s.add(op, {**base, **bad}, error=code, cls=E, tags=["invalid"], description=d)
    rop = "vol.varswap.realized"
    px = [100.0, 101.0, 99.5, 100.25, 102.0, 101.5]
    out, lr = realized({"prices": px, "periods_per_year": 252, "variance_strike": .04, "variance_notional": 1e6})
    s.add(rop, {"prices": px, "periods_per_year": 252, "variance_strike": .04, "variance_notional": 1e6}, out, cls=A, verified=["hand", "mpmath-50"], tags=["varswap", "realized", "hand"],
          output_classes={"realized_variance": A, "realized_vol": A}, limit={"absolute": 1e-6, "relative": 1e-10, "reason": "1e-12 in variance on 1e6 variance notional"})
    m = mp.fsum(lr) / len(lr)
    caught("varswap_e", "realized: demeaned with n-1", abs(f(1e6 * (252 / mp.mpf(len(lr) - 1) * mp.fsum((x - m) ** 2 for x in lr) - out["realized_variance"]))), 1e-6)
    g = np.random.default_rng(11)
    px2 = [4500.0]
    for z in g.standard_normal(63):
        px2.append(round(px2[-1] * math.exp(.18 / math.sqrt(252) * z), 2))
    o2, _ = realized({"prices": px2, "periods_per_year": 252, "variance_strike": .0324, "variance_notional": 2.5e6})
    s.add(rop, {"prices": px2, "periods_per_year": 252, "variance_strike": .0324, "variance_notional": 2.5e6}, o2, cls=A, verified=["independent-replay", "mpmath-50"], tags=["varswap", "realized"],
          output_classes={"realized_variance": A, "realized_vol": A}, limit={"absolute": 2.5e-6, "relative": 1e-10, "reason": "1e-12 in variance on the variance notional"})
    s.add(rop, {"prices": [100.0], "periods_per_year": 252, "variance_strike": .04, "variance_notional": 1e6}, error="E_INPUT", cls=E, tags=["invalid"], description="at least two prices")
    s.add(rop, {"prices": [100.0, 0.0], "periods_per_year": 252, "variance_strike": .04, "variance_notional": 1e6}, error="E_DOMAIN", cls=E, tags=["invalid"], description="prices positive")
    note("varswap_e: DDKZ weights and Black prices in mpmath; q=0 cases re-priced by QuantLib ReplicatingVarianceSwapEngine in outside_e_b.py")
    write(s)


# ===================================================================================== E7 VIX-style index
NY, N30 = 525600, 43200


def vix_term(inp, mutant=None):
    """CBOE VIX white paper method on one expiry. Sums in exact rationals; exp(RT) in mpmath at 50 digits."""
    strip = sorted(inp["strip"], key=lambda x: x["strike"])
    T = Fr(inp["minutes_to_expiry"], NY if mutant != "days" else 1440 * 360)
    R = Fr(inp["rate"])
    eRT = mp.exp(mp.mpf(R.numerator) / R.denominator * mp.mpf(T.numerator) / T.denominator)
    mid = lambda b, a: (Fr(b) + Fr(a)) / 2  # noqa: E731
    K = [Fr(x["strike"]) for x in strip]
    C = [mid(x["call_bid"], x["call_ask"]) for x in strip]
    P = [mid(x["put_bid"], x["put_ask"]) for x in strip]
    diffs = [abs(c - p) for c, p in zip(C, P)]
    j = diffs.index(min(diffs))  # lowest strike on a tie
    Fw = K[j] + eRT * (C[j] - P[j])
    below = [i for i in range(len(K)) if K[i] <= Fw]
    if not below:
        raise ValueError("no strike at or below the forward")
    i0 = below[-1] if mutant != "k0-above" else min(i for i in range(len(K)) if K[i] >= Fw)
    sel = {i0: (C[i0] + P[i0]) / 2}
    for side, rng, bid, q in (("put", range(i0 - 1, -1, -1), "put_bid", P), ("call", range(i0 + 1, len(K)), "call_bid", C)):
        zeros = 0
        for i in rng:
            if Fr(strip[i][bid]) == 0:
                zeros += 1
                if zeros == 2 and mutant != "no-stop":
                    break
                continue
            zeros = 0
            sel[i] = q[i]
    ks = sorted(sel)
    if not any(i < i0 for i in ks) or not any(i > i0 for i in ks):
        raise ValueError("all out-of-the-money puts or calls excluded")
    if mutant == "full-strip-dk":
        allk = list(range(len(K)))
        dK = {i: (K[min(i + 1, len(K) - 1)] - K[max(i - 1, 0)]) / (2 if 0 < i < len(K) - 1 else 1) for i in allk}
    else:
        dK = {}
        for n, i in enumerate(ks):
            lo, hi = ks[max(n - 1, 0)], ks[min(n + 1, len(ks) - 1)]
            dK[i] = (K[hi] - K[lo]) / (2 if 0 < n < len(ks) - 1 else 1)
    contrib = sum(dK[i] / K[i] ** 2 * sel[i] for i in ks)
    Tm = mp.mpf(T.numerator) / T.denominator
    var = 2 / Tm * eRT * mp.mpf(contrib.numerator) / contrib.denominator
    if mutant != "no-correction":
        var -= 1 / Tm * (Fw / mp.mpf(K[i0].numerator / K[i0].denominator) - 1) ** 2
    return {"forward": f(Fw), "k0": f(K[i0]), "variance": f(var), "strikes_used": [f(K[i]) for i in ks]}, var, Tm


def vix_index(inp, mutant=None):
    n = inp["near"]
    x = inp["next"]
    o1, v1, T1 = vix_term(n, mutant)
    o2, v2, T2 = vix_term(x, mutant)
    N1, N2 = n["minutes_to_expiry"], x["minutes_to_expiry"]
    w1, w2 = mp.mpf(N2 - N30) / (N2 - N1), mp.mpf(N30 - N1) / (N2 - N1)
    vix = 100 * mp.sqrt((T1 * v1 * w1 + T2 * v2 * w2) * mp.mpf(NY) / N30)
    return {"index": f(vix), "near_variance": o1["variance"], "next_variance": o2["variance"]}


def make_strip(S0, R, minutes, ks, atm, skew, tick=.05, zero_wings=()):
    """Synthetic quotes from Black prices on a smile, rounded to ticks. Bid zero on listed strikes."""
    T = minutes / NY
    F = S0 * math.exp(R * T)
    D = math.exp(-R * T)
    out = []
    for k in ks:
        v = atm - skew * math.log(k / F)
        sd = v * math.sqrt(T)
        d1 = (math.log(F / k) + sd * sd / 2) / sd
        N = lambda z: .5 * math.erfc(-z / math.sqrt(2))  # noqa: E731
        c = D * (F * N(d1) - k * N(d1 - sd))
        p = D * (k * N(sd - d1) - F * N(-d1))
        q = lambda x: max(round(x / tick) * tick, 0.0)  # noqa: E731
        spc, spp = (max(tick, round(.04 * x / tick) * tick) for x in (c, p))
        cb, pb = q(c - spc / 2), q(p - spp / 2)
        if k in zero_wings:
            cb, pb = (0.0 if k > S0 else cb), (0.0 if k < S0 else pb)
        out.append({"strike": float(k), "call_bid": round(cb, 2), "call_ask": round(q(c + spc / 2) + tick, 2), "put_bid": round(pb, 2), "put_ask": round(q(p + spp / 2) + tick, 2)})
    return out


def vix_e():
    s = S("vix_e", "05-volatility/vix-index.md")
    top, iop = "vol.vix.term_variance", "vol.vix.index"
    LIM = {"absolute": 1e-12, "relative": 1e-10, "reason": "variance near 0.04: 1e-10 relative is under 1e-5 index points"}
    # Hand case, worked in vix-index.md: five strikes, rate 0, 30 days.
    hand = {"minutes_to_expiry": 43200, "rate": 0.0, "strip": [
        {"strike": 90.0, "call_bid": 10.5, "call_ask": 11.5, "put_bid": 0.5, "put_ask": 0.7},
        {"strike": 95.0, "call_bid": 6.0, "call_ask": 6.6, "put_bid": 1.4, "put_ask": 1.6},
        {"strike": 100.0, "call_bid": 2.9, "call_ask": 3.1, "put_bid": 2.9, "put_ask": 3.3},
        {"strike": 105.0, "call_bid": 1.0, "call_ask": 1.2, "put_bid": 5.8, "put_ask": 6.6},
        {"strike": 110.0, "call_bid": 0.3, "call_ask": 0.5, "put_bid": 10.0, "put_ask": 11.0}]}
    o, v, _ = vix_term(hand)
    # By hand: mids C(100)=3.0, P(100)=3.1, min |C-P| at 100, F = 100 - 0.1 = 99.9, K0 = 95.
    assert o["forward"] == 99.9 and o["k0"] == 95.0
    s.add(top, hand, o, cls=A, verified=["hand", "exact-rational"], tags=["vix", "hand"], limit=LIM)
    for m in ("no-correction", "k0-above", "full-strip-dk", "days"):
        try:
            ov = vix_term(hand, m)[0]["variance"]
        except ValueError:
            continue
        if ov != o["variance"]:
            caught("vix_e", f"hand: {m}", abs(ov - o["variance"]), 1e-12 + 1e-10 * o["variance"])
    cases = [
        (4500.0, .045, 34560, [3800 + 25 * i for i in range(57)], .17, .25, (3850, 3875, 3950, 5100, 5125, 5050)),
        (4500.0, .046, 50400, [3700 + 25 * i for i in range(61)], .175, .23, (3800, 3825, 5000)),
        (4500.0, .045, 25920, [4000 + 10 * i for i in range(101)], .15, .3, ()),
        (4500.0, .046, 60480, [3500 + 50 * i for i in range(37)], .18, .2, (3650, 5100, 5150)),
        (100.0, 0.0, 43200, [70 + 2.5 * i for i in range(25)], .25, .1, (77.5, 80.0, 125.0)),
    ]
    terms = []
    for S0, R, mins, ks, atm, skew, zw in cases:
        strip = make_strip(S0, R, mins, ks, atm, skew, zero_wings=zw)
        inp = {"minutes_to_expiry": mins, "rate": R, "strip": strip}
        o, v, _ = vix_term(inp)
        terms.append(inp)
        s.add(top, inp, o, cls=A, verified=["independent-replay", "exact-rational"], tags=["vix"] + (["zero-bids"] if zw else []), limit=LIM)
        for m in ("no-correction", "k0-above", "full-strip-dk", "days", "no-stop"):
            ov = vix_term(inp, m)[0]
            if ov["variance"] != o["variance"]:
                caught("vix_e", f"{mins}: {m}", abs(ov["variance"] - o["variance"]), 1e-12 + 1e-10 * o["variance"])
    t30 = {"minutes_to_expiry": N30, "rate": .045, "strip": make_strip(4500.0, .045, N30, [3800 + 25 * i for i in range(57)], .17, .25, zero_wings=(3850, 3875, 5100))}
    terms += [t30]
    for a, b, tg in ((0, 1, []), (2, 3, []), (5, 1, ["boundary", "near-at-30d"]), (0, 5, ["boundary", "next-at-30d"])):
        inp = {"near": terms[a], "next": terms[b]}
        o = vix_index(inp)
        s.add(iop, inp, o, cls=A, verified=["independent-replay", "exact-rational"], tags=["vix", "index"] + tg,
              output_classes={"near_variance": A, "next_variance": A}, limit={"absolute": 1e-8, "relative": 1e-10, "reason": "index points; 1e-8 is far inside the 0.01 published precision"})
        for m in ("no-correction", "days"):
            caught("vix_e", f"index {a}/{b}: {m}", abs(vix_index(inp, m)["index"] - o["index"]), 1e-8 + 1e-10 * o["index"])
    t0 = terms[0]
    for d, bad, code in (("rate key missing value", {"rate": None}, "E_SCHEMA"), ("minutes not positive", {"minutes_to_expiry": 0}, "E_INPUT"),
                         ("fewer than three strikes", {"strip": t0["strip"][:2]}, "E_INPUT"), ("bid above ask", {"strip": [t0["strip"][0] | {"call_bid": 9e9}] + t0["strip"][1:]}, "E_INPUT"),
                         ("duplicate strike", {"strip": t0["strip"] + [t0["strip"][5]]}, "E_INPUT")):
        s.add(top, {**t0, **bad}, error=code, cls=E, tags=["invalid"], description=d)
    s.add(iop, {"near": terms[1], "next": terms[0]}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="near must expire before next, bracketing 30 days")
    # R5 audit additions (ruling E-B14)
    rev = {**t0, "strip": t0["strip"][::-1]}
    s.add(top, rev, vix_term(t0)[0], cls=A, verified=["independent-replay", "exact-rational"], tags=["vix", "unsorted", "ruling"], limit=LIM, description="strip in descending order: same result")
    z = [dict(x) for x in hand["strip"]]
    z[2]["call_bid"] = 0.0
    oz = vix_term({**hand, "strip": z})[0]
    assert oz["forward"] == 98.45 and oz["k0"] == 95.0
    s.add(top, {**hand, "strip": z}, oz, cls=A, verified=["hand", "exact-rational"], tags=["vix", "hand", "zero-bid-atm", "ruling"], limit=LIM,
          description="zero call bid at the ATM strike: still an ATM candidate (Cboe v5.0 3(a)(ii)), excluded from the call walk")
    np_ = [dict(x) for x in hand["strip"]]
    np_[0]["put_bid"] = 0.0
    for d, inp, code in (("negative quote", {**hand, "strip": [hand["strip"][0] | {"put_bid": -0.05}] + hand["strip"][1:]}, "E_DOMAIN"),
                         ("no strike at or below the forward", {**hand, "strip": hand["strip"][2:]}, "E_INPUT"),
                         ("all out-of-the-money puts excluded", {**hand, "strip": np_}, "E_INPUT")):
        if code == "E_INPUT":
            try:
                vix_term(inp)
                raise AssertionError(d)
            except ValueError:
                pass
        s.add(top, inp, error=code, cls=E, tags=["invalid", "ruling"], description=d)
    neg = {"minutes_to_expiry": 34560, "rate": 0.0, "strip": [
        {"strike": 45.0, "call_bid": 54.0, "call_ask": 56.0, "put_bid": 0.05, "put_ask": 0.1},
        {"strike": 50.0, "call_bid": 49.0, "call_ask": 51.0, "put_bid": 0.1, "put_ask": 0.2},
        {"strike": 100.0, "call_bid": 2.9, "call_ask": 3.1, "put_bid": 2.9, "put_ask": 3.3},
        {"strike": 101.0, "call_bid": 2.5, "call_ask": 2.7, "put_bid": 3.4, "put_ask": 3.8}]}
    assert vix_term(neg)[1] < 0
    s.add(iop, {"near": neg, "next": terms[1]}, error="E_DOMAIN", cls=E, tags=["invalid", "ruling"], description="near-term variance so negative that the bracket under the root is below 0")
    note("vix_e: Cboe methodology v5.0; strike sums in exact rationals, exp and sqrt in mpmath")
    write(s)


def e7():
    MUTANTS.clear()
    garch_e()
    varswap_e()
    vix_e()
    note(f"stage E E7: {len(MUTANTS)} wrong-convention checks, each caught")


SLICES = {"E7": e7}


def main():
    for k in sys.argv[1:] or list(SLICES):
        SLICES[k]()


if __name__ == "__main__":
    main()
