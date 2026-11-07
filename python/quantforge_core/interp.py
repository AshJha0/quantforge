"""Interpolation (specifications/01-core/interpolation.md)."""
import itertools
import math
from bisect import bisect_left, bisect_right
from collections.abc import Sequence

from .errors import QfError, required
from .numeric import thomas

Floats = Sequence[float]
MIN_KNOTS = {
    "linear": 2, "log_linear": 2, "cubic_natural": 3, "cubic_clamped": 2,
    "cubic_not_a_knot": 4, "monotone_pchip": 2, "tension": 3,
}


def _check_knots(x: Floats, y: Floats, minimum: int) -> None:
    if len(x) != len(y) or len(x) < minimum:
        raise QfError("E_INPUT", f"need equal lengths and at least {minimum} knots")
    if any(b <= a for a, b in itertools.pairwise(x)):
        raise QfError("E_INPUT", "knots must be strictly increasing", "x")


def _interval(x: Floats, t: float) -> int:
    return min(bisect_right(x, t) - 1, len(x) - 2)


def _steps(x: Floats, y: Floats) -> tuple[list[float], list[float]]:
    h = [b - a for a, b in itertools.pairwise(x)]
    d = [(y[i + 1] - y[i]) / h[i] for i in range(len(h))]
    return h, d


def _spline_slopes(
    method: str, x: Floats, y: Floats, slope_start: float | None, slope_end: float | None
) -> list[float]:
    """Knot slopes of a C2 cubic: a tridiagonal system, one equation per knot."""
    n = len(x) - 1
    h, d = _steps(x, y)
    lower = [0.0] * (n + 1)
    diag = [0.0] * (n + 1)
    upper = [0.0] * (n + 1)
    rhs = [0.0] * (n + 1)
    for i in range(1, n):
        lower[i] = h[i]
        diag[i] = 2 * (h[i - 1] + h[i])
        upper[i] = h[i - 1]
        rhs[i] = 3 * (h[i] * d[i - 1] + h[i - 1] * d[i])
    if method == "cubic_natural":
        diag[0], upper[0], rhs[0] = 2.0, 1.0, 3 * d[0]
        lower[n], diag[n], rhs[n] = 1.0, 2.0, 3 * d[n - 1]
    elif method == "cubic_clamped":
        diag[0], rhs[0] = 1.0, required(slope_start, "slope_start")
        diag[n], rhs[n] = 1.0, required(slope_end, "slope_end")
    else:
        # Equal third derivatives at x_1 and x_{n-1}, with the far unknown eliminated by the
        # neighbouring row, so that the system stays tridiagonal.
        p, q = h[0], h[1]
        third = 2 * (q * q * d[0] - p * p * d[1])
        diag[0], upper[0], rhs[0] = q, p + q, (third + p * rhs[1]) / (p + q)
        p, q = h[n - 2], h[n - 1]
        third = 2 * (q * q * d[n - 2] - p * p * d[n - 1])
        lower[n], diag[n], rhs[n] = p + q, p, (q * rhs[n - 1] - third) / (p + q)
    return thomas(lower, diag, upper, rhs)


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _pchip_end(h0: float, h1: float, d0: float, d1: float) -> float:
    m = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    if _sign(m) != _sign(d0):
        return 0.0
    if _sign(d0) != _sign(d1) and abs(m) > 3 * abs(d0):
        return 3 * d0
    return m


def _pchip_slopes(x: Floats, y: Floats) -> list[float]:
    h, d = _steps(x, y)
    n = len(x) - 1
    if n == 1:
        return [d[0], d[0]]
    m = [0.0] * (n + 1)
    for i in range(1, n):
        if d[i - 1] != 0 and d[i] != 0 and _sign(d[i - 1]) == _sign(d[i]):
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    m[0] = _pchip_end(h[0], h[1], d[0], d[1])
    m[n] = _pchip_end(h[n - 1], h[n - 2], d[n - 1], d[n - 2])
    return m


def _hermite(
    x: Floats, y: Floats, m: Floats, at: Floats
) -> tuple[list[float], list[float]]:
    values, derivatives = [], []
    for t in at:
        i = _interval(x, t)
        h = x[i + 1] - x[i]
        u = (t - x[i]) / h
        u2, u3 = u * u, u * u * u
        values.append(
            (2 * u3 - 3 * u2 + 1) * y[i]
            + (u3 - 2 * u2 + u) * h * m[i]
            + (-2 * u3 + 3 * u2) * y[i + 1]
            + (u3 - u2) * h * m[i + 1]
        )
        derivatives.append(
            (6 * u2 - 6 * u) * (y[i] - y[i + 1]) / h
            + (3 * u2 - 4 * u + 1) * m[i]
            + (3 * u2 - 2 * u) * m[i + 1]
        )
    return values, derivatives


def _tension(x: Floats, y: Floats, p: float, at: Floats) -> tuple[list[float], list[float]]:
    h, d = _steps(x, y)
    n = len(x) - 1
    e = [1 / hi - p / math.sinh(p * hi) for hi in h]
    c = [p * math.cosh(p * hi) / math.sinh(p * hi) - 1 / hi for hi in h]
    lower = [e[i - 1] for i in range(1, n)]
    diag = [c[i - 1] + c[i] for i in range(1, n)]
    upper = [e[i] for i in range(1, n)]
    rhs = [p * p * (d[i] - d[i - 1]) for i in range(1, n)]
    second = [0.0, *thomas(lower, diag, upper, rhs), 0.0]
    p2 = p * p
    values, derivatives = [], []
    for t in at:
        i = _interval(x, t)
        hi = h[i]
        right, left = x[i + 1] - t, t - x[i]
        mi, mj = second[i], second[i + 1]
        den = p2 * math.sinh(p * hi)
        a0 = y[i] - mi / p2
        a1 = y[i + 1] - mj / p2
        values.append(
            (mi * math.sinh(p * right) + mj * math.sinh(p * left)) / den
            + a0 * right / hi
            + a1 * left / hi
        )
        derivatives.append(
            p * (mj * math.cosh(p * left) - mi * math.cosh(p * right)) / den + (a1 - a0) / hi
        )
    return values, derivatives


def evaluate(
    method: str,
    x: Floats,
    y: Floats,
    at: Floats,
    slope_start: float | None = None,
    slope_end: float | None = None,
    tension: float | None = None,
) -> tuple[list[float], list[float] | None]:
    """Returns (values, derivatives). derivatives is None for linear and log_linear."""
    _check_knots(x, y, MIN_KNOTS[method])
    h = [b - a for a, b in itertools.pairwise(x)]
    if method == "log_linear" and any(v <= 0 for v in y):
        raise QfError("E_DOMAIN", "log_linear needs y > 0", "y")
    if method == "tension":
        tension = required(tension, "tension")
        if tension < 0:
            raise QfError("E_DOMAIN", "tension must not be negative", "tension")
        if tension > 0 and any(not 0.01 <= tension * hi <= 500 for hi in h):
            raise QfError("E_DOMAIN", "need 0.01 <= p h <= 500 on every interval", "tension")
    if any(not x[0] <= t <= x[-1] for t in at):
        raise QfError("E_OUT_OF_RANGE", "a query lies outside the knots", "at")

    if method in ("linear", "log_linear"):
        values = []
        for t in at:
            i = _interval(x, t)
            u = (t - x[i]) / h[i]
            if method == "linear":
                values.append(y[i] + u * (y[i + 1] - y[i]))
            else:
                values.append(math.exp((1 - u) * math.log(y[i]) + u * math.log(y[i + 1])))
        return values, None
    if method == "monotone_pchip":
        return _hermite(x, y, _pchip_slopes(x, y), at)
    if method == "tension" and required(tension, "tension") > 0:
        return _tension(x, y, required(tension, "tension"), at)
    spline = "cubic_natural" if method == "tension" else method
    return _hermite(x, y, _spline_slopes(spline, x, y, slope_start, slope_end), at)


def _clamp(v: float, low: float, high: float) -> float:
    return min(max(v, low), high)


def _g_and_integral(g0: float, g1: float, x: float) -> tuple[float, float]:
    """g(x) and G(x), the integral of g from 0 to x, by the Hagan-West regions."""
    if g0 == 0 and g1 == 0:
        return 0.0, 0.0
    if (g0 < 0 and -g0 / 2 <= g1 <= -2 * g0) or (g0 > 0 and -g0 / 2 >= g1 >= -2 * g0):
        g = g0 * (1 - 4 * x + 3 * x * x) + g1 * (-2 * x + 3 * x * x)
        return g, g0 * (x - 2 * x * x + x**3) + g1 * (-x * x + x**3)
    if (g0 < 0 and g1 > -2 * g0) or (g0 > 0 and g1 < -2 * g0):
        eta = (g1 + 2 * g0) / (g1 - g0)
        if x <= eta:
            return g0, g0 * x
        w = (x - eta) / (1 - eta)
        return g0 + (g1 - g0) * w * w, g0 * x + (g1 - g0) * (x - eta) * w * w / 3
    if (g0 > 0 and -g0 / 2 < g1 < 0) or (g0 < 0 and 0 < g1 < -g0 / 2):
        eta = 3 * g1 / (g1 - g0)
        if x < eta:
            w = (eta - x) / eta
            return g1 + (g0 - g1) * w * w, g1 * x + (g0 - g1) * eta * (1 - w**3) / 3
        return g1, g1 * x + (g0 - g1) * eta / 3
    eta = g1 / (g1 + g0)
    a = -g0 * g1 / (g0 + g1)
    if x < eta:
        w = (eta - x) / eta
        return a + (g0 - a) * w * w, a * x + (g0 - a) * eta * (1 - w**3) / 3
    # eta = 1 only when g0 = 0, and then x = 1 here: the ratio below is 0/0 in the spec's formula.
    # g takes its end value g1 there. See SPEC_QUESTIONS.md.
    w = (x - eta) / (1 - eta) if eta < 1 else 1.0
    return a + (g1 - a) * w * w, a * x + (g0 - a) * eta / 3 + (g1 - a) * (x - eta) * w * w / 3


def monotone_convex(
    t: Floats, r: Floats, at: Floats, positive: bool = False
) -> tuple[list[float], list[float]]:
    """Returns (forwards, zero_rates)."""
    if len(t) != len(r) or len(t) < 2:
        raise QfError("E_INPUT", "need equal lengths and at least 2 points")
    if t[0] <= 0 or any(b <= a for a, b in itertools.pairwise(t)):
        raise QfError("E_INPUT", "t must be positive and strictly increasing", "t")
    if any(s <= 0 or s > t[-1] for s in at):
        raise QfError("E_OUT_OF_RANGE", "a query lies outside (0, t_n]", "at")

    n = len(t)
    tt = [0.0, *t]
    rt = [0.0, *(ri * ti for ri, ti in zip(r, t))]
    fd = [0.0] * (n + 1)
    for i in range(1, n + 1):
        fd[i] = (rt[i] - rt[i - 1]) / (tt[i] - tt[i - 1])
    if positive and any(v < 0 for v in fd[1:]):
        raise QfError("E_DOMAIN", "positive needs every discrete forward >= 0", "r")
    f = [0.0] * (n + 1)
    for i in range(1, n):
        span = tt[i + 1] - tt[i - 1]
        f[i] = (tt[i] - tt[i - 1]) / span * fd[i + 1] + (tt[i + 1] - tt[i]) / span * fd[i]
    f[0] = fd[1] - (f[1] - fd[1]) / 2
    f[n] = fd[n] - (f[n - 1] - fd[n]) / 2
    if positive:
        f[0] = _clamp(f[0], 0.0, 2 * fd[1])
        for i in range(1, n):
            f[i] = _clamp(f[i], 0.0, 2 * min(fd[i], fd[i + 1]))
        f[n] = _clamp(f[n], 0.0, 2 * fd[n])

    forwards, zero_rates = [], []
    for s in at:
        i = bisect_left(tt, s)
        width = tt[i] - tt[i - 1]
        x = (s - tt[i - 1]) / width
        g, big_g = _g_and_integral(f[i - 1] - fd[i], f[i] - fd[i], x)
        forwards.append(fd[i] + g)
        zero_rates.append((rt[i - 1] + width * (fd[i] * x + big_g)) / s)
    return forwards, zero_rates
