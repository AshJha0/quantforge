"""Statistics, time series, PDE, COS."""
from fractions import Fraction as Fr

import mpmath as mp
import numpy as np
import QuantLib as ql
from scipy import stats as st
from scipy.linalg import solve_banded

from qf_oracle.common import Suite, f, note
from qf_oracle.rng import bs

G = "oracle/python/gen_stats_engines.py"
S = "statistics"
XS = [[1.5, 2.25, 3.0, 2.75, 7.5, -1.25, 4.0, 3.5, 2.0, 0.5, 6.25, 3.25],
      [100.0, 101.5, 99.25, 102.0, 103.5, 102.75, 104.0, 105.25, 103.0, 106.5],
      [1e9 + 1, 1e9 + 2, 1e9 + 4, 1e9 + 3, 1e9 + 7]]


def rat(x):
    return [Fr(v) for v in x]


def summary(x):
    q = rat(x)
    n = len(q)
    m = sum(q) / n
    d = [v - m for v in q]
    m2, m3, m4 = (sum(v ** k for v in d) / n for k in (2, 3, 4))
    var = sum(v * v for v in d) / (n - 1)
    sk = mp.mpf(m3.numerator) / m3.denominator / (mp.mpf(m2.numerator) / m2.denominator) ** 1.5
    return {"count": n, "mean": float(m), "variance": float(var), "stdev": f(mp.sqrt(mp.mpf(var.numerator) / var.denominator)),
            "skewness": f(sk), "excess_kurtosis": float(m4 / m2 ** 2 - 3), "min": min(x), "max": max(x)}


def statistics():
    s = Suite("stats", "specifications/01-core/statistics-and-time-series.md", G)
    xs = [-37.0, -10.0, -5.0, -1.0, -0.1, 0.0, 0.5, 1.96, 6.0]
    N = lambda v: mp.erfc(-mp.mpf(v) / mp.sqrt(2)) / 2  # noqa: E731
    s.add("core.stats.normal", {"x": xs}, {"pdf": [f(mp.exp(-mp.mpf(v) ** 2 / 2) / mp.sqrt(2 * mp.pi)) for v in xs], "cdf": [f(N(v)) for v in xs]}, cls=S, verified=["mpmath-50"],
          limit={"relative": 1e-13, "absolute": 0.0, "reason": "tail values near 1e-300: relative accuracy is the point"})
    for x in XS:
        o = summary(x)
        a = np.array(x)
        assert abs(st.skew(a) - o["skewness"]) < 1e-6 and abs(st.kurtosis(a) - o["excess_kurtosis"]) < 1e-5
        s.add("core.stats.summary", {"x": x}, o, cls=S, verified=["exact-rational", "scipy-1.18.1"], output_classes={"count": "date_and_convention"})
        ps = [0.0, 0.01, 0.25, 0.5, 0.9, 0.99, 1.0]
        s.add("core.stats.quantile", {"x": x, "p": ps}, {"values": [float(v) for v in np.quantile(a, ps, method="linear")]}, cls=S, verified=["numpy-type7"])
    s.add("core.stats.summary", {"x": [2.0, 2.0, 2.0]}, {"count": 3, "mean": 2.0, "variance": 0.0, "stdev": 0.0, "skewness": None, "excess_kurtosis": None, "min": 2.0, "max": 2.0}, cls=S, verified=["hand"], tags=["boundary"], output_classes={"count": "date_and_convention"})
    s.add("core.stats.summary", {"x": [1.0]}, error="E_INPUT", tags=["invalid"])
    s.add("core.stats.quantile", {"x": [1.0, 2.0], "p": [1.5]}, error="E_DOMAIN", tags=["invalid"])
    x = XS[0]
    y = [2 * v + (-1) ** i * 0.5 + 1 for i, v in enumerate(x)]
    q, r = rat(x), rat(y)
    n = len(q)
    mx, my = sum(q) / n, sum(r) / n
    sxx = sum((a - mx) ** 2 for a in q)
    syy = sum((b - my) ** 2 for b in r)
    sxy = sum((a - mx) * (b - my) for a, b in zip(q, r))
    corr = mp.mpf(sxy.numerator) / sxy.denominator / mp.sqrt(mp.mpf((sxx * syy).numerator) / (sxx * syy).denominator)
    s.add("core.stats.covariance", {"x": x, "y": y}, {"covariance": float(sxy / (n - 1)), "correlation": f(corr)}, cls=S, verified=["exact-rational"])
    s.add("core.stats.covariance", {"x": [1.0, 1.0], "y": [1.0, 2.0]}, {"covariance": 0.0, "correlation": None}, cls=S, verified=["hand"], tags=["boundary"])
    lr = st.linregress(x, y)
    beta = sxy / sxx
    alpha = my - beta * mx
    rss = sum((b - alpha - beta * a) ** 2 for a, b in zip(q, r))
    s2 = rss / (n - 2)
    se_b = mp.sqrt(mp.mpf((s2 / sxx).numerator) / (s2 / sxx).denominator)
    se_a2 = s2 * (Fr(1, n) + mx * mx / sxx)
    se_a = mp.sqrt(mp.mpf(se_a2.numerator) / se_a2.denominator)
    assert abs(lr.slope - float(beta)) < 1e-12 and abs(lr.stderr - float(se_b)) < 1e-12
    s.add("core.stats.ols", {"x": x, "y": y}, {"alpha": float(alpha), "beta": float(beta), "r_squared": float(1 - rss / syy), "se_alpha": f(se_a), "se_beta": f(se_b)}, cls=S, verified=["exact-rational", "scipy-1.18.1"])
    s.add("core.stats.ols", {"x": [1.0, 1.0, 1.0], "y": [1.0, 2.0, 3.0]}, error="E_SINGULAR", tags=["invalid"])
    s.add("core.stats.covariance", {"x": [1.0, 2.0], "y": [1.0]}, error="E_INPUT", tags=["invalid"])
    p = XS[1]
    s.add("core.ts.returns", {"prices": p, "kind": "SIMPLE"}, {"returns": [float(Fr(b) / Fr(a) - 1) for a, b in zip(p, p[1:])]}, cls=S, verified=["exact-rational"])
    s.add("core.ts.returns", {"prices": p, "kind": "LOG"}, {"returns": [f(mp.log(mp.mpf(b) / a)) for a, b in zip(p, p[1:])]}, cls=S, verified=["mpmath-50"])
    s.add("core.ts.returns", {"prices": [1.0, 0.0], "kind": "LOG"}, error="E_DOMAIN", tags=["invalid"])
    z = [1e8, 1.0, 2.0, 4.0, 3.0, 5.0]
    for stat in ("MEAN", "STDEV"):
        out = [None] * 2
        for i in range(2, 6):
            w = rat(z[i - 2:i + 1])
            m = sum(w) / 3
            v = sum((a - m) ** 2 for a in w) / 2
            out.append(float(m) if stat == "MEAN" else f(mp.sqrt(mp.mpf(v.numerator) / v.denominator)))
        s.add("core.ts.rolling", {"x": z, "window": 3, "statistic": stat}, {"values": out}, cls=S, verified=["exact-rational"], description="the large first value must leave no residue")
    s.add("core.ts.rolling", {"x": z, "window": 1, "statistic": "MEAN"}, error="E_INPUT", tags=["invalid"])
    rets = [0.01, -0.02, 0.015, 0.0, -0.03]
    v, ew = Fr(rets[0]) ** 2, []
    lam = Fr(0.94)
    ew.append(float(v))
    for a in rets[1:]:
        v = lam * v + (1 - lam) * Fr(a) ** 2
        ew.append(float(v))
    s.add("core.ts.ewma_variance", {"returns": rets, "lambda": 0.94}, {"variance": ew}, cls=S, verified=["exact-rational"])
    s.add("core.ts.ewma_variance", {"returns": rets, "lambda": 1.0}, error="E_DOMAIN", tags=["invalid"])
    w = rat(XS[0])
    n = len(w)
    m = sum(w) / n
    den = sum((v - m) ** 2 for v in w)
    ac = [sum((w[i] - m) * (w[i - k] - m) for i in range(k, n)) / den for k in range(1, 5)]
    a = np.array(XS[0]) - np.mean(XS[0])
    assert abs(float(ac[1]) - float((a[2:] * a[:-2]).sum() / (a * a).sum())) < 1e-13
    s.add("core.ts.autocorrelation", {"x": XS[0], "max_lag": 4}, {"acf": [float(v) for v in ac]}, cls=S, verified=["exact-rational", "numpy"])
    lb = n * (n + 2) * sum(v * v / (n - k - 1) for k, v in enumerate(ac))
    s.add("core.ts.ljung_box", {"x": XS[0], "max_lag": 4}, {"statistic": float(lb)}, cls=S, verified=["exact-rational"])
    s.add("core.ts.autocorrelation", {"x": [1.0, 1.0, 1.0], "max_lag": 1}, error="E_DOMAIN", tags=["invalid"])
    lr = st.linregress(XS[0][:-1], XS[0][1:])
    res = np.array(XS[0][1:]) - lr.intercept - lr.slope * np.array(XS[0][:-1])
    s.add("core.ts.ar1", {"x": XS[0]}, {"constant": float(lr.intercept), "phi": float(lr.slope), "sigma": float(np.sqrt((res ** 2).sum() / (len(XS[0]) - 3)))}, cls=S, verified=["scipy-1.18.1"])
    E = "date_and_convention"
    ds = ["2024-01-29", "2024-01-31", "2024-02-01", "2024-02-02", "2024-02-05", "2024-02-29", "2024-03-01", "2024-03-04"]
    vs = [1.0, 2.0, None, 4.0, None, 6.0, 7.0, None]
    s.add("core.ts.resample_last", {"dates": ds, "values": vs, "frequency": "MONTH"}, {"dates": ["2024-01-31", "2024-02-29", "2024-03-01"], "values": [2.0, 6.0, 7.0]}, cls=E, verified=["hand"])
    s.add("core.ts.resample_last", {"dates": ds, "values": vs, "frequency": "WEEK"}, {"dates": ["2024-02-02", "2024-03-01"], "values": [4.0, 7.0]}, cls=E, verified=["hand"], description="weeks holding only nulls are dropped")
    s.add("core.ts.resample_last", {"dates": ["2024-01-02", "2024-01-01"], "values": [1.0, 2.0], "frequency": "WEEK"}, error="E_INPUT", tags=["invalid"])
    s.add("core.ts.forward_fill", {"values": [None, 1.0, None, None, None, 2.0, None], "limit": 2}, {"values": [None, 1.0, 1.0, 1.0, None, 2.0, 2.0]}, cls=E, verified=["hand"])
    s.write()


def pde_replay(inp):
    opt, S0, K, r, q, sig, t = (inp[k] for k in ("option", "spot", "strike", "r", "q", "sigma", "t"))
    J, M, w, R = inp["space_steps"], inp["time_steps"], inp.get("width", 6.0), inp.get("rannacher_steps", 2)
    a = sig * sig / 2
    b = r - q - a
    h = 2 * w * sig * np.sqrt(t) / J
    x = np.log(S0) + (np.arange(J + 1) - J / 2) * h
    k = np.log(K)
    L, U = x - h / 2, x + h / 2
    if opt == "CALL":
        l = np.maximum(L, k)
        V = np.where(U <= k, 0.0, (np.exp(U) - np.exp(l) - K * (U - l)) / h)
    else:
        u = np.minimum(U, k)
        V = np.where(L >= k, 0.0, (K * (u - L) - np.exp(u) + np.exp(L)) / h)

    def bc(tau):
        if opt == "CALL":
            return 0.0, np.exp(x[-1]) * np.exp(-q * tau) - K * np.exp(-r * tau)
        return K * np.exp(-r * tau) - np.exp(x[0]) * np.exp(-q * tau), 0.0

    lo, ce, up = a / h ** 2 - b / (2 * h), -2 * a / h ** 2 - r, a / h ** 2 + b / (2 * h)
    n = J - 1

    def step(V, tau, s, th):
        rhs = V[1:-1] + (1 - th) * s * (lo * V[:-2] + ce * V[1:-1] + up * V[2:])
        b0, b1 = bc(tau + s)
        rhs[0] += th * s * lo * b0
        rhs[-1] += th * s * up * b1
        ab = np.zeros((3, n))
        ab[0, 1:] = -th * s * up
        ab[1, :] = 1 - th * s * ce
        ab[2, :-1] = -th * s * lo
        out = np.empty_like(V)
        out[1:-1] = solve_banded((1, 1), ab, rhs)
        out[0], out[-1] = b0, b1
        return out

    V = V.copy()
    V[0], V[-1] = bc(0.0)
    dt, tau = t / M, 0.0
    for i in range(M):
        if i < R:
            V = step(V, tau, dt / 2, 1.0)
            V = step(V, tau + dt / 2, dt / 2, 1.0)
        else:
            V = step(V, tau, dt, 0.5)
        tau += dt
    m = J // 2
    vx = (V[m + 1] - V[m - 1]) / (2 * h)
    vxx = (V[m + 1] - 2 * V[m] + V[m - 1]) / h ** 2
    return float(V[m]), float(vx / S0), float((vxx - vx) / S0 ** 2)


def pde():
    s = Suite("pde", "specifications/01-core/pde.md", G)
    op = "core.pde.bs_european"
    base = {"spot": 100.0, "strike": 100.0, "r": 0.05, "q": 0.02, "sigma": 0.2, "t": 1.0}
    errs = []
    for J, M in ((100, 50), (200, 100), (400, 200), (800, 400)):
        inp = {**base, "option": "CALL", "space_steps": J, "time_steps": M}
        p, d, g = pde_replay(inp)
        tp, td, tg = (float(v) for v in bs("CALL", 100, 100, .05, .02, .2, 1))
        errs.append(abs(p - tp))
        note(f"pde J={J} M={M}: price err {abs(p - tp):.3e} delta err {abs(d - td):.3e} gamma err {abs(g - tg):.3e}")
        if J == 400:
            assert abs(p - tp) < 1e-3 and abs(d - td) < 1e-4 and abs(g - tg) < 1e-4
        s.add(op, inp, {"price": p, "delta": d, "gamma": g}, cls="numerical_scheme", verified=["independent-replay", "analytic-mpmath-50"],
              extra_checks=[{"output": "price", "expected": tp, "method": "absolute", "limit": max(2 * errs[-1], 1e-6)}])
    ratios = [errs[i] / errs[i + 1] for i in range(3)]
    note(f"pde convergence ratios on halving h and dt: {[round(x, 3) for x in ratios]}")
    assert all(3 < x < 5 for x in ratios)
    for opt, K, r, q, sig, t in (("PUT", 100.0, 0.05, 0.02, 0.2, 1.0), ("CALL", 80.0, 0.01, 0.0, 0.4, 0.5), ("PUT", 120.0, 0.03, 0.01, 0.15, 2.0), ("CALL", 103.7, -0.005, 0.0, 0.25, 1.0)):
        inp = {"spot": 100.0, "strike": K, "r": r, "q": q, "sigma": sig, "t": t, "option": opt, "space_steps": 400, "time_steps": 200}
        p, d, g = pde_replay(inp)
        tp = float(bs(opt, 100, K, r, q, sig, t)[0])
        assert abs(p - tp) < 5e-3, (opt, K, p, tp)
        s.add(op, inp, {"price": p, "delta": d, "gamma": g}, cls="numerical_scheme", verified=["independent-replay", "analytic-mpmath-50"],
              extra_checks=[{"output": "price", "expected": tp, "method": "absolute", "limit": 5e-3}])
    s.add(op, {**base, "option": "CALL", "space_steps": 101, "time_steps": 50}, error="E_INPUT", tags=["invalid"])
    s.add(op, {**base, "option": "CALL", "space_steps": 100, "time_steps": 2, "rannacher_steps": 2}, error="E_INPUT", tags=["invalid"])
    s.add(op, {**base, "option": "CALL", "sigma": -0.2, "space_steps": 100, "time_steps": 50}, error="E_DOMAIN", tags=["invalid"])
    s.write()


def phi(model, u, r, q, t):
    i = mp.mpc(0, 1)
    if u == 0:
        return mp.mpc(1)
    if model["name"] == "BLACK_SCHOLES":
        sg = mp.mpf(model["sigma"])
        return mp.exp(i * u * (r - q - sg * sg / 2) * t - sg * sg * u * u * t / 2)
    v0, ka, th, sg, rho = (mp.mpf(model[k]) for k in ("v0", "kappa", "theta", "sigma", "rho"))
    be = ka - rho * sg * i * u
    d = mp.sqrt(be * be + sg * sg * (i * u + u * u))
    g = (be - d) / (be + d)
    e = mp.exp(-d * t)
    return mp.exp(i * u * (r - q) * t + ka * th / sg ** 2 * ((be - d) * t - 2 * mp.log((1 - g * e) / (1 - g))) + v0 / sg ** 2 * (be - d) * (1 - e) / (1 - g * e))


def cos_replay(inp):
    S0, K, r, q, t = (mp.mpf(inp[k]) for k in ("spot", "strike", "r", "q", "t"))
    N, L, m = inp["terms"], mp.mpf(inp["truncation"]), inp["model"]
    if m["name"] == "BLACK_SCHOLES":
        w = mp.mpf(m["sigma"]) ** 2 * t
    else:
        v0, ka, th = (mp.mpf(m[k]) for k in ("v0", "kappa", "theta"))
        w = (th + (v0 - th) * (1 - mp.exp(-ka * t)) / (ka * t)) * t
    x = mp.log(S0 / K)
    c1 = x + (r - q) * t - w / 2
    a, b = c1 - L * mp.sqrt(w), c1 + L * mp.sqrt(w)
    tot = mp.mpf(0)
    for k in range(N):
        u = k * mp.pi / (b - a)
        chi = (mp.cos(-u * a) + u * mp.sin(-u * a) - mp.exp(a)) / (1 + u * u)
        psi = mp.sin(-u * a) / u if k else -a
        Vk = 2 / (b - a) * K * (psi - chi)
        term = mp.re(phi(m, u, r, q, t) * mp.exp(mp.mpc(0, 1) * u * (x - a))) * Vk
        tot += term / 2 if k == 0 else term
    put = mp.exp(-r * t) * tot
    return put if inp["option"] == "PUT" else put + S0 * mp.exp(-q * t) - K * mp.exp(-r * t)


def ql_heston(opt, S0, K, r, q, t, m):
    d = ql.Date(6, 11, 2026)
    ql.Settings.instance().evaluationDate = d
    dc = ql.Actual365Fixed()
    mat = d + int(round(t * 365))
    rt = ql.YieldTermStructureHandle(ql.FlatForward(d, r, dc))
    qt = ql.YieldTermStructureHandle(ql.FlatForward(d, q, dc))
    pr = ql.HestonProcess(rt, qt, ql.QuoteHandle(ql.SimpleQuote(S0)), m["v0"], m["kappa"], m["theta"], m["sigma"], m["rho"])
    eng = ql.AnalyticHestonEngine(ql.HestonModel(pr), 1e-13, 200000)
    o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if opt == "CALL" else ql.Option.Put, K), ql.EuropeanExercise(mat))
    o.setPricingEngine(eng)
    return o.NPV()


def cos():
    s = Suite("cos", "specifications/01-core/cos.md", G)
    op = "core.cos.european"
    for opt, K, sig, t in (("CALL", 100.0, 0.2, 1.0), ("PUT", 100.0, 0.2, 1.0), ("CALL", 80.0, 0.3, 0.25), ("PUT", 130.0, 0.15, 2.0), ("CALL", 120.0, 0.5, 5.0)):
        inp = {"option": opt, "spot": 100.0, "strike": K, "r": 0.05, "q": 0.02, "t": t, "model": {"name": "BLACK_SCHOLES", "sigma": sig}, "terms": 256, "truncation": 10.0}
        v = cos_replay(inp)
        tv = bs(opt, 100, K, .05, .02, sig, t)[0]
        e = abs(v - tv)
        note(f"cos BS {opt} K={K} sig={sig} t={t}: err {float(e):.2e}")
        assert e < 1e-10
        s.add(op, inp, {"price": f(v)}, cls="fourier", verified=["mpmath-50-replay", "analytic-mpmath-50"], extra_checks=[{"output": "price", "expected": f(tv), "method": "absolute", "limit": 1e-10}])
    hm = {"name": "HESTON", "v0": 0.04, "kappa": 1.5, "theta": 0.04, "sigma": 0.3, "rho": -0.7}
    for opt, K, t, m in (("CALL", 100.0, 1.0, hm), ("PUT", 90.0, 1.0, hm), ("CALL", 120.0, 2.0, {**hm, "v0": 0.09}), ("PUT", 100.0, 0.5, {**hm, "sigma": 0.6, "rho": -0.3})):
        days = int(round(t * 365))  # QuantLib prices a whole number of days, so the case uses that time
        inp = {"option": opt, "spot": 100.0, "strike": K, "r": 0.03, "q": 0.01, "t": days / 365, "model": m, "terms": 512, "truncation": 16.0}
        v = cos_replay(inp)
        qv = ql_heston(opt, 100.0, K, 0.03, 0.01, days / 365, m)
        e = abs(float(v) - qv)
        note(f"cos Heston {opt} K={K} t={t}: against QuantLib err {e:.2e}")
        assert e < 1e-7
        s.add(op, inp, {"price": f(v)}, cls="fourier", verified=["mpmath-50-replay", "quantlib-1.44"], extra_checks=[{"output": "price", "expected": qv, "method": "absolute", "limit": 1e-7}])
    # Near-zero vol-of-vol tends to Black-Scholes at the average variance (plan section 8).
    v0, th, ka, t = 0.09, 0.04, 2.0, 1.0
    vbar = th + (v0 - th) * (1 - np.exp(-ka * t)) / (ka * t)
    inp = {"option": "CALL", "spot": 100.0, "strike": 100.0, "r": 0.02, "q": 0.0, "t": t, "model": {"name": "HESTON", "v0": v0, "kappa": ka, "theta": th, "sigma": 1e-3, "rho": 0.0}, "terms": 512, "truncation": 16.0}
    v = cos_replay(inp)
    tv = bs("CALL", 100, 100, .02, 0, float(np.sqrt(vbar)), t)[0]
    note(f"cos Heston near zero vol-of-vol against BS at average variance: err {float(abs(v - tv)):.2e}")
    assert abs(v - tv) < 1e-3
    s.add(op, inp, {"price": f(v)}, cls="fourier", verified=["mpmath-50-replay", "limit-case"], tags=["boundary"], extra_checks=[{"output": "price", "expected": f(tv), "method": "absolute", "limit": 1e-3}])
    b = {"option": "CALL", "spot": 100.0, "strike": 100.0, "r": 0.0, "q": 0.0, "t": 1.0, "terms": 64, "truncation": 10.0}
    s.add(op, {**b, "model": {"name": "BLACK_SCHOLES", "sigma": -0.1}}, error="E_DOMAIN", tags=["invalid"])
    s.add(op, {**b, "model": {**hm, "rho": 1.0}}, error="E_DOMAIN", tags=["invalid"])
    s.add(op, {**b, "terms": 1, "model": {"name": "BLACK_SCHOLES", "sigma": 0.2}}, error="E_INPUT", tags=["invalid"])
    s.add(op, {**b, "strike": 1000.0, "truncation": 1.0, "model": {"name": "BLACK_SCHOLES", "sigma": 0.2}}, error="E_INPUT", tags=["invalid"], description="range does not hold the strike")
    s.write()


def main():
    statistics()
    pde()
    cos()


if __name__ == "__main__":
    main()
