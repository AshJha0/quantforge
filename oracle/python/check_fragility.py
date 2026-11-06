"""Checks that integration and no-convergence goldens do not hang on rounding.

Each adaptive case is re-run in binary64 with the function perturbed by relative noise of a few ulps, which stands in
for a different maths library. The outcome, ok or E_NO_CONVERGENCE, must not change.
"""
import json
import math
import random

from scipy.optimize import brentq

from qf_oracle.common import GOLDEN, note

XK = [0.991455371120812639206854697526329, 0.949107912342758524526189684047851, 0.864864423359769072789712788640926, 0.741531185599394439863864773280788,
      0.586087235467691130294144838258730, 0.405845151377397166906606412076961, 0.207784955007898467600689403773244, 0.0]
WK = [0.022935322010529224963732008058970, 0.063092092629978553290700663189204, 0.104790010322250183839876322541518, 0.140653259715525918998541745705333,
      0.169004726639267902826583426140209, 0.190350578064785409913256402421014, 0.204432940075298892414161999234649, 0.209482141084727828012999174351914]
WG = [0.129484966168869693270611432679082, 0.279705391489276667901467771423780, 0.381830050505118944950369775488975, 0.417959183673469387755102040816327]
F = {"exp": math.exp, "sin": math.sin, "runge": lambda x: 1 / (1 + 25 * x * x), "sqrt": math.sqrt, "inv_sqrt": lambda x: 1 / math.sqrt(x),
     "normal_pdf": lambda x: math.exp(-x * x / 2) / math.sqrt(2 * math.pi), "oscillatory": lambda x: math.cos(50 * x) * math.exp(-x),
     "poly5": lambda x: x ** 5 - 3 * x ** 2 + 1}


class Stop(Exception):
    pass


def noisy(fn, rnd, ulps):
    return lambda x: fn(x) * (1 + rnd.uniform(-ulps, ulps) * 2.0 ** -52)


def simpson(f, a, b, tol, max_depth):
    calls = [0]

    def g(x):
        calls[0] += 1
        if calls[0] > 10000000:
            raise Stop
        return f(x)

    def go(l, r, fl, fm, fr, s, t, d):
        m = (l + r) / 2
        a1, a2 = (l + m) / 2, (m + r) / 2
        f1, f2 = g(a1), g(a2)
        s1, s2 = (m - l) / 6 * (fl + 4 * f1 + fm), (r - m) / 6 * (fm + 4 * f2 + fr)
        if abs(s1 + s2 - s) <= 15 * t:
            return
        if d >= max_depth:
            raise Stop
        go(l, m, fl, f1, fm, s1, t / 2, d + 1)
        go(m, r, fm, f2, fr, s2, t / 2, d + 1)
    fa, fm, fb = g(a), g((a + b) / 2), g(b)
    try:
        go(a, b, fa, fm, fb, (b - a) / 6 * (fa + 4 * fm + fb), tol, 0)
        return "ok"
    except Stop:
        return "E_NO_CONVERGENCE"


def rule(f, a, b):
    c, h = (a + b) / 2, (b - a) / 2
    k = WK[7] * f(c)
    g = WG[3] * f(c)
    for i in range(7):
        s = f(c - h * XK[i]) + f(c + h * XK[i])
        k += WK[i] * s
        if i % 2:
            g += WG[i // 2] * s
    return k * h, abs(k - g) * h


def kronrod(f, a, b, tol, max_intervals):
    v, e = rule(f, a, b)
    ivs = [(e, a, b, v)]
    while sum(i[0] for i in ivs) > max(tol, 1e-14 * abs(sum(i[3] for i in ivs))):
        if len(ivs) >= max_intervals:
            return "E_NO_CONVERGENCE"
        ivs.sort()
        _, l, r, _ = ivs.pop()
        m = (l + r) / 2
        for p, q in ((l, m), (m, r)):
            v, e = rule(f, p, q)
            ivs.append((e, p, q, v))
    return "ok"


def main():
    rnd = random.Random(11)
    n = 0
    for suite in ("integrate", "limits", "rulings"):
        for c in json.loads((GOLDEN / f"{suite}.json").read_text(encoding="utf-8"))["cases"]:
            op, i, e = c["operation"], c["inputs"], c["expected"]
            if op not in ("core.integrate.adaptive_simpson", "core.integrate.gauss_kronrod") or e.get("error_code") in ("E_LIMIT", "E_INPUT", "E_NON_FINITE"):
                continue
            want = e.get("error_code", "ok")
            for ulps in (0, 2, 8):
                for _ in range(1 if ulps == 0 else 6):
                    f = noisy(F[i["function"]], rnd, ulps)
                    if op.endswith("simpson"):
                        got = simpson(f, i["a"], i["b"], i.get("tol", 1e-10), i.get("max_depth", 50))
                    else:
                        got = kronrod(f, i["a"], i["b"], i.get("tol", 1e-10), i.get("max_intervals", 500))
                    assert got == want, (c["case_id"], ulps, got)
            n += 1
    note(f"fragility: {n} adaptive cases keep their outcome under noise of up to 8 ulps")
    f = F["oscillatory"]
    gap = abs(rule(f, 0.0, 2.0)[1])
    assert gap > 1e-6
    full = (2.0 / 6) * (f(0.0) + 4 * f(1.0) + f(2.0))
    note(f"fragility: integrate-0095 error estimate {gap:.2e} against tol 1e-13")
    r = brentq(lambda x: x ** 3 - 2 * x - 5, 2.0, 3.0, xtol=1e-12, rtol=1e-15, maxiter=100, full_output=True)[1]
    assert r.iterations > 3
    note(f"fragility: root-0025 needs {r.iterations} Brent steps against max_iter 2; root-0026 has width 0.125 after 3 bisections against x_tol 1e-12")
    assert full == full


if __name__ == "__main__":
    main()
