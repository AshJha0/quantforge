"""Root finders, integration, interpolation, differences, linear algebra."""
import mpmath as mp
import numpy as np
import QuantLib as ql
from scipy.interpolate import CubicSpline, PchipInterpolator

from qf_oracle.common import Suite, f, note
from qf_oracle.rng import bs

G = "oracle/python/gen_numerics.py"
FUNCS = {"exp": mp.exp, "sin": mp.sin, "runge": lambda x: 1 / (1 + 25 * x * x), "sqrt": mp.sqrt, "inv_sqrt": lambda x: 1 / mp.sqrt(x),
         "normal_pdf": lambda x: mp.exp(-x * x / 2) / mp.sqrt(2 * mp.pi), "oscillatory": lambda x: mp.cos(50 * x) * mp.exp(-x),
         "poly5": lambda x: x ** 5 - 3 * x ** 2 + 1}


def roots():
    s = Suite("root", "specifications/01-core/root-finders.md", G)
    C = lambda v: bs("CALL", 100, 100, 0.01, 0, v, 1)[0] - 10  # noqa: E731
    table = {"cubic_wallis": (lambda x: x ** 3 - 2 * x - 5, 2, 3, 2.5), "cos_minus_x": (lambda x: mp.cos(x) - x, 0, 1, 0.5),
             "exp_minus_two": (lambda x: mp.exp(x) - 2, 0, 2, 1.0), "steep_atan": (lambda x: mp.atan(1000 * (x - mp.mpf("0.3"))), 0, 1, 0.3001),
             "bs_vol_atm": (C, 0.01, 1.0, 0.3)}
    for name, (fn, a, b, x0) in table.items():
        root = mp.findroot(fn, (mp.mpf(a), mp.mpf(b)), solver="anderson", tol=1e-40, verify=False) if name != "steep_atan" else mp.mpf("0.3")
        assert abs(fn(root)) < 1e-30
        out = {"root": f(root)}
        s.add("core.root.bisection", {"function": name, "a": a, "b": b}, out, cls="root_finding", verified=["mpmath-50"])
        s.add("core.root.brent", {"function": name, "a": a, "b": b}, out, cls="root_finding", verified=["mpmath-50"])
        s.add("core.root.newton", {"function": name, "x0": x0, "a": a, "b": b}, out, cls="root_finding", verified=["mpmath-50"])
    s.add("core.root.newton", {"function": "cubic_wallis", "x0": 2.0}, {"root": f(mp.findroot(lambda x: x ** 3 - 2 * x - 5, 2))}, cls="root_finding", verified=["mpmath-50"])
    s.add("core.root.bisection", {"function": "exp_minus_two", "a": 0.0, "b": 1.0, "x_tol": 1e-6}, {"root": f(mp.log(2))}, cls="root_finding",
          verified=["mpmath-50"], limit={"absolute": 2e-6, "reason": "x_tol is 1e-6"})
    s.add("core.root.bisection", {"function": "triple_root", "a": 0.0, "b": 3.0}, {"root": 1.0}, cls="root_finding", verified=["hand"],
          limit={"absolute": 1e-4, "reason": "f underflows to rounding noise within about 1e-5 of a triple root"})
    s.add("core.root.brent", {"function": "triple_root", "a": 0.0, "b": 3.5}, {"root": 1.0}, cls="root_finding", verified=["hand"],
          limit={"absolute": 1e-4, "reason": "f underflows to rounding noise within about 1e-5 of a triple root"})
    s.add("core.root.bisection", {"function": "cubic_wallis", "a": 2.0945514815423265, "b": 2.0945514815423265}, error="E_INPUT", tags=["invalid"])
    s.add("core.root.bisection", {"function": "no_real_root", "a": -1.0, "b": 1.0}, error="E_NOT_BRACKETED", tags=["invalid"])
    s.add("core.root.brent", {"function": "no_real_root", "a": -1.0, "b": 1.0}, error="E_NOT_BRACKETED", tags=["invalid"])
    s.add("core.root.newton", {"function": "square", "x0": 0.0 + 0.0}, {"root": 0.0}, cls="root_finding", verified=["hand"], tags=["boundary"],
          description="f(x0) is exactly 0, so EXACT is reported before the derivative is looked at")
    s.add("core.root.newton", {"function": "no_real_root", "x0": 0.0}, error="E_ZERO_DERIVATIVE", tags=["invalid"])
    s.add("core.root.brent", {"function": "cubic_wallis", "a": 2.0, "b": 3.0, "max_iter": 2}, error="E_NO_CONVERGENCE", tags=["invalid"])
    s.add("core.root.bisection", {"function": "cubic_wallis", "a": 2.0, "b": 3.0, "max_iter": 3}, error="E_NO_CONVERGENCE", tags=["invalid"])
    s.add("core.root.bisection", {"function": "cubic_wallis", "a": 2.0, "b": 3.0, "x_tol": 0.0}, error="E_INPUT", tags=["invalid"])
    s.add("core.root.brent", {"function": "not_registered", "a": 2.0, "b": 3.0}, error="E_SCHEMA", tags=["invalid"])
    s.write()


def integrate():
    s = Suite("integrate", "specifications/01-core/integration.md", G)
    Q = "quadrature"
    rng = {"exp": (0, 1), "sin": (0, 3), "runge": (-1, 1), "sqrt": (0, 1), "normal_pdf": (-3, 2), "oscillatory": (0, 2), "poly5": (-1, 2)}
    for name, (a, b) in rng.items():
        fn = FUNCS[name]
        A, B = mp.mpf(a), mp.mpf(b)
        for n in (1, 10, 101):
            h = (B - A) / n
            v = h * (fn(A) / 2 + sum(fn(A + i * h) for i in range(1, n)) + fn(B) / 2)
            s.add("core.integrate.trapezoid", {"function": name, "a": a, "b": b, "n": n}, {"value": f(v)}, cls=Q, verified=["mpmath-50-replay"])
        for n in (2, 10, 100):
            h = (B - A) / n
            v = h / 3 * (fn(A) + fn(B) + sum((4 if i % 2 else 2) * fn(A + i * h) for i in range(1, n)))
            s.add("core.integrate.simpson", {"function": name, "a": a, "b": b, "n": n}, {"value": f(v)}, cls=Q, verified=["mpmath-50-replay"])
        for n in (1, 2, 5, 16, 64):
            t, w = np.polynomial.legendre.leggauss(n)
            pts = []
            for k in range(1, n + 1):
                x = mp.cos(mp.pi * (k - mp.mpf(1) / 4) / (n + mp.mpf(1) / 2))
                for _ in range(12):
                    p0, p1 = mp.mpf(1), x
                    for j in range(2, n + 1):
                        p0, p1 = p1, ((2 * j - 1) * x * p1 - (j - 1) * p0) / j
                    dp = n * (x * p1 - p0) / (x * x - 1)
                    x -= p1 / dp
                if n == 1:
                    x, dp = mp.mpf(0), mp.mpf(1)
                pts.append((x, 2 / ((1 - x * x) * dp * dp)))
            assert np.allclose(sorted(float(p[0]) for p in pts), t, atol=1e-13)
            v = (B - A) / 2 * sum(wi * fn((A + B) / 2 + (B - A) / 2 * x) for x, wi in pts)
            s.add("core.integrate.gauss_legendre", {"function": name, "a": a, "b": b, "n": n}, {"value": f(v)}, cls=Q, verified=["mpmath-50-replay", "numpy-leggauss"])
        true = mp.quad(fn, mp.linspace(A, B, 41))
        lim = {"absolute": 1e-9, "reason": "tol is 1e-10; the error estimate is not a bound"}
        s.add("core.integrate.gauss_kronrod", {"function": name, "a": a, "b": b, "tol": 1e-10}, {"value": f(true)}, cls=Q, verified=["mpmath-50"], limit=lim)
        if name != "sqrt":
            s.add("core.integrate.adaptive_simpson", {"function": name, "a": a, "b": b, "tol": 1e-10}, {"value": f(true)}, cls=Q, verified=["mpmath-50"], limit=lim)
    s.add("core.integrate.gauss_kronrod", {"function": "inv_sqrt", "a": 0.0, "b": 1.0, "tol": 1e-10}, {"value": 2.0}, cls=Q, verified=["hand"],
          limit={"absolute": 1e-9, "reason": "singular end point, tol 1e-10"}, tags=["boundary"])
    s.add("core.integrate.trapezoid", {"function": "exp", "a": 1.0, "b": 1.0, "n": 4}, error="E_INPUT", tags=["invalid"])
    s.add("core.integrate.simpson", {"function": "exp", "a": 0.0, "b": 1.0, "n": 3}, error="E_INPUT", tags=["invalid"])
    s.add("core.integrate.gauss_legendre", {"function": "exp", "a": 0.0, "b": 1.0, "n": 65}, error="E_INPUT", tags=["invalid"])
    s.add("core.integrate.gauss_kronrod", {"function": "oscillatory", "a": 0.0, "b": 2.0, "tol": 1e-13, "max_intervals": 1}, error="E_NO_CONVERGENCE", tags=["invalid"])
    s.write()


def tension(x, y, p, at):
    n = len(x) - 1
    x = [mp.mpf(v) for v in x]
    y = [mp.mpf(v) for v in y]
    p = mp.mpf(p)
    h = [x[i + 1] - x[i] for i in range(n)]
    d = [(y[i + 1] - y[i]) / h[i] for i in range(n)]
    e = [1 / hi - p / mp.sinh(p * hi) for hi in h]
    c = [p * mp.coth(p * hi) - 1 / hi for hi in h]
    A = mp.zeros(n - 1)
    rhs = mp.zeros(n - 1, 1)
    for i in range(1, n):
        A[i - 1, i - 1] = c[i - 1] + c[i]
        if i > 1:
            A[i - 1, i - 2] = e[i - 1]
        if i < n - 1:
            A[i - 1, i] = e[i]
        rhs[i - 1] = p * p * (d[i] - d[i - 1])
    sol = mp.lu_solve(A, rhs)
    M = [mp.mpf(0)] + [sol[i] for i in range(n - 1)] + [mp.mpf(0)]

    def seg(i, t):
        hi = h[i]
        a, b = x[i + 1] - t, t - x[i]
        s = (M[i] * mp.sinh(p * a) + M[i + 1] * mp.sinh(p * b)) / (p * p * mp.sinh(p * hi)) + (y[i] - M[i] / p ** 2) * a / hi + (y[i + 1] - M[i + 1] / p ** 2) * b / hi
        ds = (-M[i] * mp.cosh(p * a) + M[i + 1] * mp.cosh(p * b)) / (p * mp.sinh(p * hi)) - (y[i] - M[i] / p ** 2) / hi + (y[i + 1] - M[i + 1] / p ** 2) / hi
        return s, ds

    for i in range(1, n):  # s' must be continuous: this proves the tridiagonal system in the spec
        assert abs(seg(i - 1, x[i])[1] - seg(i, x[i])[1]) < mp.mpf(10) ** -30
    vs, ds = [], []
    for t in at:
        t = mp.mpf(t)
        i = max(j for j in range(n) if x[j] <= t) if t < x[n] else n - 1
        v, dv = seg(i, t)
        vs.append(f(v))
        ds.append(f(dv))
    return vs, ds


def g_region(g0, g1, x):
    """Returns g(x) and G(x), the integral from 0 to x, by the table in interpolation.md."""
    if g0 == 0 and g1 == 0:
        return mp.mpf(0), mp.mpf(0)
    if (g0 < 0 and -g0 / 2 <= g1 <= -2 * g0) or (g0 > 0 and -g0 / 2 >= g1 >= -2 * g0):
        return (g0 * (1 - 4 * x + 3 * x * x) + g1 * (-2 * x + 3 * x * x),
                g0 * (x - 2 * x ** 2 + x ** 3) + g1 * (-x ** 2 + x ** 3))
    if (g0 < 0 and g1 > -2 * g0) or (g0 > 0 and g1 < -2 * g0):
        eta = (g1 + 2 * g0) / (g1 - g0)
        if x <= eta:
            return g0, g0 * x
        return g0 + (g1 - g0) * ((x - eta) / (1 - eta)) ** 2, g0 * x + (g1 - g0) * (x - eta) ** 3 / (3 * (1 - eta) ** 2)
    if (g0 > 0 and -g0 / 2 < g1 < 0) or (g0 < 0 and 0 < g1 < -g0 / 2):
        eta = 3 * g1 / (g1 - g0)
        if x < eta:
            return g1 + (g0 - g1) * ((eta - x) / eta) ** 2, g1 * x + (g0 - g1) * (eta ** 3 - (eta - x) ** 3) / (3 * eta ** 2)
        return g1, g1 * x + (g0 - g1) * eta / 3
    eta = g1 / (g1 + g0)
    A = -g0 * g1 / (g0 + g1)
    if x < eta:
        return A + (g0 - A) * ((eta - x) / eta) ** 2, A * x + (g0 - A) * (eta ** 3 - (eta - x) ** 3) / (3 * eta ** 2)
    return A + (g1 - A) * ((x - eta) / (1 - eta)) ** 2, A * x + (g0 - A) * eta / 3 + (g1 - A) * (x - eta) ** 3 / (3 * (1 - eta) ** 2)


def monotone_convex(t, r, at, positive):
    t = [mp.mpf(0)] + [mp.mpf(v) for v in t]
    r = [mp.mpf(0)] + [mp.mpf(v) for v in r]
    n = len(t) - 1
    fd = [None] + [(r[i] * t[i] - r[i - 1] * t[i - 1]) / (t[i] - t[i - 1]) for i in range(1, n + 1)]
    fn = [None] * (n + 1)
    for i in range(1, n):
        w = t[i + 1] - t[i - 1]
        fn[i] = (t[i] - t[i - 1]) / w * fd[i + 1] + (t[i + 1] - t[i]) / w * fd[i]
    fn[0] = fd[1] - (fn[1] - fd[1]) / 2
    fn[n] = fd[n] - (fn[n - 1] - fd[n]) / 2
    if positive:
        cl = lambda v, hi: min(max(v, mp.mpf(0)), hi)  # noqa: E731
        fn[0] = cl(fn[0], 2 * fd[1])
        for i in range(1, n):
            fn[i] = cl(fn[i], 2 * min(fd[i], fd[i + 1]))
        fn[n] = cl(fn[n], 2 * fd[n])
    for i in range(1, n + 1):  # each g integrates to zero, and matches the node forwards
        g0, g1 = fn[i - 1] - fd[i], fn[i] - fd[i]
        assert abs(g_region(g0, g1, mp.mpf(1))[1]) < mp.mpf(10) ** -35, (i, g0, g1)
        assert abs(g_region(g0, g1, mp.mpf(0))[0] - g0) < mp.mpf(10) ** -35
        assert abs(g_region(g0, g1, mp.mpf(1))[0] - g1) < mp.mpf(10) ** -35
        xm = mp.mpf("0.37")
        with mp.workdps(20):  # g has a kink, so integrate over many small panels
            num = mp.quad(lambda z: g_region(g0, g1, z)[0], mp.linspace(0, xm, 257), maxdegree=3)
        assert abs(num - g_region(g0, g1, xm)[1]) <= mp.mpf(10) ** -9 * (abs(g0) + abs(g1)), (i, num, g_region(g0, g1, xm)[1])
    fw, zr = [], []
    for s in at:
        s = mp.mpf(s)
        i = min(j for j in range(1, n + 1) if s <= t[j])
        h = t[i] - t[i - 1]
        x = (s - t[i - 1]) / h
        g, Gx = g_region(fn[i - 1] - fd[i], fn[i] - fd[i], x)
        fw.append(f(fd[i] + g))
        zr.append(f((r[i - 1] * t[i - 1] + h * (fd[i] * x + Gx)) / s))
    return fw, zr


def interpolate():
    s = Suite("interp", "specifications/01-core/interpolation.md", G)
    I = "interpolation"
    op = "core.interp.evaluate"
    sets = [([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 2.0, 1.0, 3.0, 2.5]),
            ([0.25, 1.0, 2.0, 5.0, 10.0, 30.0], [0.031, 0.034, 0.036, 0.038, 0.041, 0.04]),
            ([-2.0, -0.5, 0.0, 1.5, 3.0], [1.0, 1.5, 2.0, 2.0, 7.0]),
            ([0.0, 0.1, 5.0, 5.1, 10.0], [1.0, 0.99, 0.8, 0.79, 0.6])]
    for x, y in sets:
        xa = np.array(x)
        at = sorted(set(list(np.linspace(x[0], x[-1], 17)) + x))
        at = [float(v) for v in at]
        s.add(op, {"method": "linear", "x": x, "y": y, "at": at}, {"values": [float(v) for v in np.interp(at, x, y)]}, cls=I, verified=["numpy"])
        if min(y) > 0:
            s.add(op, {"method": "log_linear", "x": x, "y": y, "at": at}, {"values": [float(v) for v in np.exp(np.interp(at, x, np.log(y)))]}, cls=I, verified=["numpy"])
        q = ql.CubicNaturalSpline(x, y)
        for name, bc, extra in (("cubic_natural", "natural", {}), ("cubic_clamped", ((1, 0.5), (1, -0.25)), {"slope_start": 0.5, "slope_end": -0.25}), ("cubic_not_a_knot", "not-a-knot", {})):
            cs = CubicSpline(xa, y, bc_type=bc)
            ver = ["scipy-1.18.1"]
            if name == "cubic_natural":
                assert max(abs(q(v, True) - cs(v)) for v in at) < 1e-10
                ver.append("quantlib-1.44")
            s.add(op, {"method": name, "x": x, "y": y, "at": at, **extra}, {"values": [float(cs(v)) for v in at], "derivatives": [float(cs(v, 1)) for v in at]}, cls=I, verified=ver)
        pc = PchipInterpolator(xa, y)
        s.add(op, {"method": "monotone_pchip", "x": x, "y": y, "at": at}, {"values": [float(pc(v)) for v in at], "derivatives": [float(pc(v, 1)) for v in at]}, cls=I, verified=["scipy-1.18.1"])
        hmin, hmax = min(np.diff(x)), max(np.diff(x))
        for p in (0.2, 1.0, 5.0):
            if p * hmin >= 0.01 and p * hmax <= 500:
                v, d = tension(x, y, p, at)
                s.add(op, {"method": "tension", "tension": p, "x": x, "y": y, "at": at}, {"values": v, "derivatives": d}, cls=I, verified=["mpmath-50", "derivative-continuity"])
        cs = CubicSpline(xa, y, bc_type="natural")
        s.add(op, {"method": "tension", "tension": 0.0, "x": x, "y": y, "at": at}, {"values": [float(cs(v)) for v in at], "derivatives": [float(cs(v, 1)) for v in at]}, cls=I, verified=["scipy-1.18.1"], tags=["boundary"])
    # Limits: small tension approaches the cubic spline, large tension the straight lines.
    x, y = sets[0]
    at = [0.5, 1.5, 2.5, 3.5]
    lo = tension(x, y, 0.011, at)[0]
    hi = tension(x, y, 400.0, at)[0]
    cs = CubicSpline(np.array(x), y, bc_type="natural")
    assert max(abs(a - float(cs(b))) for a, b in zip(lo, at)) < 1e-3
    assert max(abs(a - float(np.interp(b, x, y))) for a, b in zip(hi, at)) < 2e-2
    note("tension: limits to natural cubic (p=0.011) and to linear (p=400) hold; s' continuous at every knot")
    curves = [([0.1, 1.0, 4.0, 9.0, 20.0, 30.0], [0.081, 0.07, 0.044, 0.07, 0.04, 0.03], False),
              ([0.1, 1.0, 4.0, 9.0, 20.0, 30.0], [0.081, 0.07, 0.044, 0.07, 0.04, 0.03], True),
              ([0.25, 0.5, 1.0, 2.0, 5.0, 10.0], [0.01, 0.012, 0.015, 0.02, 0.025, 0.03], False),
              ([1.0, 2.0, 3.0], [0.02, 0.02, 0.02], False),
              ([1.0, 2.0, 5.0, 7.0], [-0.004, -0.002, 0.003, 0.002], False)]
    for t, r, pos in curves:
        if pos:
            fd = [r[0]] + [(r[i] * t[i] - r[i - 1] * t[i - 1]) / (t[i] - t[i - 1]) for i in range(1, len(t))]
            if min(fd) < 0:
                s.add("core.interp.monotone_convex", {"t": t, "r": r, "at": [1.0], "positive": True}, error="E_DOMAIN", tags=["invalid"])
                continue
        at = sorted(set(t + [float(v) for v in np.linspace(t[0] / 2, t[-1], 23)]))
        fw, zr = monotone_convex(t, r, at, pos)
        for ti, ri in zip(t, r):
            assert abs(zr[at.index(ti)] - ri) < 1e-14
        s.add("core.interp.monotone_convex", {"t": t, "r": r, "at": at, "positive": pos}, {"forwards": fw, "zero_rates": zr}, cls=I, verified=["mpmath-50", "repricing", "zero-integral"])
    note("monotone convex: every g integrates to 0, matches node forwards, closed-form G matches quadrature; all inputs reprice")
    x, y = sets[0]
    s.add(op, {"method": "linear", "x": x, "y": y[:-1], "at": [1.0]}, error="E_INPUT", tags=["invalid"])
    s.add(op, {"method": "linear", "x": [0.0, 0.0, 1.0], "y": [1.0, 2.0, 3.0], "at": [0.5]}, error="E_INPUT", tags=["invalid"])
    s.add(op, {"method": "linear", "x": x, "y": y, "at": [4.5]}, error="E_OUT_OF_RANGE", tags=["invalid"])
    s.add(op, {"method": "log_linear", "x": [0.0, 1.0], "y": [1.0, -1.0], "at": [0.5]}, error="E_DOMAIN", tags=["invalid"])
    s.add(op, {"method": "cubic_not_a_knot", "x": [0.0, 1.0, 2.0], "y": [1.0, 2.0, 3.0], "at": [0.5]}, error="E_INPUT", tags=["invalid"])
    s.add(op, {"method": "tension", "tension": 0.001, "x": x, "y": y, "at": [0.5]}, error="E_DOMAIN", tags=["invalid"])
    s.add(op, {"method": "tension", "tension": 1000.0, "x": x, "y": y, "at": [0.5]}, error="E_DOMAIN", tags=["invalid"])
    s.add("core.interp.monotone_convex", {"t": [1.0, 2.0], "r": [0.01, 0.02], "at": [0.0]}, error="E_OUT_OF_RANGE", tags=["invalid"])
    s.write()


def diff_linalg():
    s = Suite("diff_linalg", "specifications/01-core/differentiation-and-linalg.md", G)
    for name, x in (("exp", 1.0), ("sin", 0.7), ("poly5", 1.3), ("normal_pdf", 0.4)):
        fn = FUNCS[name]
        X = mp.mpf(x)
        for order, h in ((1, 1e-5), (2, 1e-4)):
            H = mp.mpf(h)
            v = (fn(X + H) - fn(X - H)) / (2 * H) if order == 1 else (fn(X + H) - 2 * fn(X) + fn(X - H)) / H ** 2
            terms = abs(X) ** 5 + 3 * X ** 2 + 1 if name == "poly5" else abs(fn(X))
            M = terms + abs(X * mp.diff(fn, X))
            eps = mp.mpf(2) ** -52
            lim = 8 * eps * M / H if order == 1 else 32 * eps * M / H ** 2
            s.add("core.diff.central", {"function": name, "x": x, "h": h, "order": order}, {"value": f(v)}, cls="quadrature", verified=["mpmath-50"],
                  limit={"absolute": f(lim), "reason": "rounding bound in differentiation-and-linalg.md; any correct form of f passes"})
    s.add("core.diff.central", {"function": "exp", "x": 1.0, "h": 0.0, "order": 1}, error="E_INPUT", tags=["invalid"])
    A = [[4.0, 1.0, 2.0], [1.0, 3.0, 0.0], [2.0, 0.0, 5.0]]
    b = [1.0, 2.0, 3.0]
    Am = mp.matrix(A)
    x = mp.lu_solve(Am, mp.matrix(b))
    I = "interpolation"
    s.add("core.linalg.solve", {"a": A, "b": b}, {"x": [f(v) for v in x]}, cls=I, verified=["mpmath-50"])
    P = [[0.0, 2.0], [3.0, 1.0]]
    s.add("core.linalg.solve", {"a": P, "b": [2.0, 4.0]}, {"x": [1.0, 1.0]}, cls=I, verified=["hand"], description="needs pivoting")
    L = mp.cholesky(Am)
    s.add("core.linalg.cholesky", {"a": A}, {"l": [[f(L[i, j]) for j in range(3)] for i in range(3)]}, cls=I, verified=["mpmath-50"])
    ev = sorted(mp.eigsy(Am, eigvals_only=True))
    s.add("core.linalg.eigen_symmetric", {"a": A}, {"values": [f(v) for v in ev]}, cls=I, verified=["mpmath-50"])
    s.add("core.linalg.solve", {"a": [[1.0, 2.0], [2.0, 4.0]], "b": [1.0, 2.0]}, error="E_SINGULAR", tags=["invalid"])
    s.add("core.linalg.solve", {"a": [[1.0, 2.0], [2.0]], "b": [1.0, 2.0]}, error="E_INPUT", tags=["invalid"])
    s.add("core.linalg.cholesky", {"a": [[1.0, 2.0], [2.0, 1.0]]}, error="E_NOT_POSITIVE_DEFINITE", tags=["invalid"])
    s.add("core.linalg.cholesky", {"a": [[1.0, 2.0], [0.0, 1.0]]}, error="E_INPUT", tags=["invalid"])
    s.write()


def main():
    roots()
    integrate()
    interpolate()
    diff_linalg()


if __name__ == "__main__":
    main()
