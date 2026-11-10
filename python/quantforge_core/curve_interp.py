"""Stage F pluggable interpolations on ln S (specifications/02-curves/curve-framework.md,
section "Stage F: pluggable interpolation").

Each interpolator is built on the node times t_0 = 0 < t_1 < ... < t_n and the node values
ln S_0 = 0, ln S_1, ..., ln S_n, and gives ln S(t) and the instantaneous forward
f(t) = -d ln S/dt (right-hand at a node) for t >= 0, extrapolating beyond t_n with the flat
forward f(t_n-) (ruling F-20).
"""
import math
from bisect import bisect_right
from collections.abc import Sequence

from .finite import guard

NEW_METHODS = ("MONOTONE_CONVEX", "MONOTONIC_LOG_CUBIC", "TENSION_SPLINE", "HYBRID")
_FLAT = 1e-14


class Interpolator:
    """ln S and f on a list of nodes. Subclasses fill `_log_inside` and `_forward_inside`."""

    def __init__(self, ts: Sequence[float], xs: Sequence[float]):
        self.ts, self.xs = list(ts), list(xs)
        self.n = len(ts) - 1

    def _section(self, t: float) -> int:
        """The node index i with t_i <= t < t_{i+1}."""
        return bisect_right(self.ts, t) - 1

    def log(self, t: float) -> float:
        n = self.n
        if t >= self.ts[n]:
            return self.xs[n] - self.last_forward() * (t - self.ts[n])
        return self._log_inside(self._section(t), t)

    def forward(self, t: float) -> float:
        if t >= self.ts[self.n]:
            return self.last_forward()
        return self._forward_inside(self._section(t), t)

    def last_forward(self) -> float:
        raise NotImplementedError

    def _log_inside(self, i: int, t: float) -> float:
        raise NotImplementedError

    def _forward_inside(self, i: int, t: float) -> float:
        raise NotImplementedError


class LogLinear(Interpolator):
    """LOG_LINEAR_DF on its nodes; the last segment's forward carries on (stage B rule)."""

    def _slope(self, i: int) -> float:
        return -(self.xs[i + 1] - self.xs[i]) / (self.ts[i + 1] - self.ts[i])

    def last_forward(self) -> float:
        return self._slope(self.n - 1)

    def _log_inside(self, i: int, t: float) -> float:
        u = (t - self.ts[i]) / (self.ts[i + 1] - self.ts[i])
        return (1 - u) * self.xs[i] + u * self.xs[i + 1]

    def _forward_inside(self, i: int, t: float) -> float:
        return self._slope(i)


class MonotoneConvex(Interpolator):
    """Hagan-West as QuantLib ConvexMonotone(0, 1, forcePositive = false) (ruling F-19)."""

    def __init__(self, ts: Sequence[float], xs: Sequence[float]):
        super().__init__(ts, xs)
        n = self.n
        dx = [ts[i + 1] - ts[i] for i in range(n)]
        y = [(xs[i] - xs[i + 1]) / dx[i] for i in range(n)]  # y[k] is the spec's y_{k+1}
        self.dx, self.y = dx, y
        if n == 1:
            self.nodes = [y[0], y[0]]
            return
        f = [0.0] * (n + 1)
        for i in range(1, n):
            f[i] = (dx[i] * y[i - 1] + dx[i - 1] * y[i]) / (dx[i - 1] + dx[i])
        f[0] = 1.5 * y[0] - 0.5 * f[1]
        f[n] = 1.5 * y[n - 1] - 0.5 * f[n - 1]
        self.nodes = f

    def last_forward(self) -> float:
        return self.nodes[self.n] if self.n > 1 else self.y[0]

    def _branch(self, i: int, x: float) -> tuple[float, float]:
        """(f, integral of f from 0 to x) on section i + 1 (from t_i to t_{i+1})."""
        y = self.y[i]
        if self.n == 1:
            return y, y * x
        f0, f1 = self.nodes[i], self.nodes[i + 1]
        g0, g1 = f0 - y, f1 - y
        if abs(g0) < _FLAT and abs(g1) < _FLAT:  # (a)
            return f0 + (f1 - f0) * x, f0 * x + (f1 - f0) * x * x / 2
        if (g0 > 0 and -2 * g0 <= g1 <= -0.5 * g0) or (g0 < 0 and -0.5 * g0 <= g1 <= -2 * g0):
            a = 3 * f0 + 3 * f1 - 6 * y  # (b)
            b = -(4 * f0 + 2 * f1 - 6 * y)
            return a * x * x + b * x + f0, a * x ** 3 / 3 + b * x * x / 2 + f0 * x
        if (g0 < 0 and g1 > -2 * g0) or (g0 > 0 and g1 < -2 * g0):  # (c)
            eta = (g1 + 2 * g0) / (g1 - g0)
            if eta < 1:
                base = y + g0
                if x <= eta:
                    return base, base * x
                w = (x - eta) / (1 - eta)
                return base + (g1 - g0) * w * w, base * x + (g1 - g0) * (1 - eta) * w ** 3 / 3
            return _rule_e(y, g0, g1, 1.0, x)
        if (g0 > 0 and 0 > g1 > -0.5 * g0) or (g0 < 0 and 0 < g1 < -0.5 * g0):  # (d)
            eta = 3 * g1 / (g1 - g0)
            if eta > 0:
                base = y + g1
                if x <= eta:
                    w = (eta - x) / eta
                    return base + (g0 - g1) * w * w, base * x + (g0 - g1) * eta * (1 - w ** 3) / 3
                return base, base * x + (g0 - g1) * eta / 3
            return _rule_e(y, g0, g1, 0.0, x)
        s = g0 + g1  # (e)
        eta = min(max(g1 / s, 0.0), 1.0) if s != 0 else 0.5
        return _rule_e(y, g0, g1, eta, x)

    def _x(self, i: int, t: float) -> float:
        return (t - self.ts[i]) / self.dx[i]

    def _log_inside(self, i: int, t: float) -> float:
        return self.xs[i] - self.dx[i] * self._branch(i, self._x(i, t))[1]

    def _forward_inside(self, i: int, t: float) -> float:
        return self._branch(i, self._x(i, t))[0]


def _rule_e(y: float, g0: float, g1: float, eta: float, x: float) -> tuple[float, float]:
    big_a = -(eta * g0 + (1 - eta) * g1) / 2
    base = y + big_a
    if x <= eta:
        if eta == 0:  # only the point x = 0 (ruling F-19)
            return y + g0, 0.0
        w = (eta - x) / eta
        return base + (g0 - big_a) * w * w, base * x + (g0 - big_a) * eta * (1 - w ** 3) / 3
    w = (x - eta) / (1 - eta)
    return (base + (g1 - big_a) * w * w,
            base * x + (g0 - big_a) * eta / 3 + (g1 - big_a) * (1 - eta) * w ** 3 / 3)


def _tridiagonal(lower: Sequence[float], diag: Sequence[float], upper: Sequence[float],
                 rhs: Sequence[float]) -> list[float]:
    """Thomas algorithm; lower[0] and upper[-1] are unused."""
    n = len(diag)
    c, d = [0.0] * n, [0.0] * n
    c[0], d[0] = upper[0] / diag[0] if n > 1 else 0.0, rhs[0] / diag[0]
    for i in range(1, n):
        m = diag[i] - lower[i] * c[i - 1]
        c[i] = upper[i] / m if i < n - 1 else 0.0
        d[i] = (rhs[i] - lower[i] * d[i - 1]) / m
    out = [0.0] * n
    out[-1] = d[-1]
    for i in range(n - 2, -1, -1):
        out[i] = d[i] - c[i] * out[i + 1]
    return out


def _sign(v: float) -> float:
    return 1.0 if v > 0 else -1.0 if v < 0 else 0.0


class MonotonicLogCubic(Interpolator):
    """QuantLib MonotonicLogCubic: natural cubic spline in ln S with the Hyman filter."""

    def __init__(self, ts: Sequence[float], xs: Sequence[float]):
        super().__init__(ts, xs)
        n = self.n
        h = [ts[i + 1] - ts[i] for i in range(n)]
        s = [(xs[i + 1] - xs[i]) / h[i] for i in range(n)]
        lower, diag, upper, rhs = [0.0] * (n + 1), [0.0] * (n + 1), [0.0] * (n + 1), [0.0] * (n + 1)
        diag[0], upper[0], rhs[0] = 2.0, 1.0, 3 * s[0]
        for i in range(1, n):
            lower[i], diag[i], upper[i] = h[i], 2 * (h[i - 1] + h[i]), h[i - 1]
            rhs[i] = 3 * (h[i] * s[i - 1] + h[i - 1] * s[i])
        lower[n], diag[n], rhs[n] = 1.0, 2.0, 3 * s[n - 1]
        m = _tridiagonal(lower, diag, upper, rhs)
        out = list(m)
        for i in range(n + 1):
            if i == 0 or i == n:
                chord = s[0] if i == 0 else s[n - 1]
                out[i] = _sign(m[i]) * min(abs(m[i]), 3 * abs(chord)) if m[i] * chord > 0 else 0.0
                continue
            p = (s[i - 1] * h[i] + s[i] * h[i - 1]) / (h[i - 1] + h[i])
            cap = 3 * min(abs(s[i - 1]), abs(s[i]), abs(p))
            if i > 1 and (s[i - 1] - s[i - 2]) * (s[i] - s[i - 1]) > 0:
                pd = (s[i - 1] * (2 * h[i - 1] + h[i - 2]) - s[i - 2] * h[i - 1]) / (h[i - 2] + h[i - 1])
                if p * pd > 0 and p * (s[i - 1] - s[i - 2]) > 0:
                    cap = max(cap, 1.5 * min(abs(p), abs(pd)))
            if i < n - 1 and (s[i] - s[i - 1]) * (s[i + 1] - s[i]) > 0:
                pu = (s[i] * (2 * h[i] + h[i + 1]) - s[i + 1] * h[i]) / (h[i] + h[i + 1])
                if p * pu > 0 and -p * (s[i] - s[i - 1]) > 0:
                    cap = max(cap, 1.5 * min(abs(p), abs(pu)))
            out[i] = _sign(m[i]) * min(abs(m[i]), cap) if m[i] * p > 0 else 0.0
        self.m = out
        self.b = [(3 * s[i] - out[i + 1] - 2 * out[i]) / h[i] for i in range(n)]
        self.c = [(out[i + 1] + out[i] - 2 * s[i]) / (h[i] * h[i]) for i in range(n)]
        self.h = h

    def last_forward(self) -> float:
        i, d = self.n - 1, self.h[self.n - 1]
        return -(self.m[i] + 2 * self.b[i] * d + 3 * self.c[i] * d * d)

    def _log_inside(self, i: int, t: float) -> float:
        d = t - self.ts[i]
        return self.xs[i] + d * (self.m[i] + d * (self.b[i] + d * self.c[i]))

    def _forward_inside(self, i: int, t: float) -> float:
        d = t - self.ts[i]
        return -(self.m[i] + 2 * self.b[i] * d + 3 * self.c[i] * d * d)


def _one_minus_exp(x: float) -> float:
    """1 - e^{-x}."""
    return -math.expm1(-x)


class TensionSpline(Interpolator):
    """Exponential tension spline in ln S with natural ends."""

    def __init__(self, ts: Sequence[float], xs: Sequence[float], sigma: float):
        super().__init__(ts, xs)
        n = self.n
        self.sigma = sigma
        h = [ts[i + 1] - ts[i] for i in range(n)]
        s = [(xs[i + 1] - xs[i]) / h[i] for i in range(n)]
        self.h, self.s = h, s
        alpha, beta = [], []
        for hi in h:
            z = sigma * hi
            if z < 1e-3:
                alpha.append(hi / 6 * (1 - z * z / 60))
                beta.append(hi / 3 * (1 - z * z / 15))
            else:
                den = _one_minus_exp(2 * z)
                inv_sinh = 2 * math.exp(-z) / den
                coth = (1 + math.exp(-2 * z)) / den
                alpha.append(1 / (sigma * sigma * hi) - inv_sinh / sigma)
                beta.append(coth / sigma - 1 / (sigma * sigma * hi))
        big_m = [0.0] * (n + 1)
        if n > 1:
            k = n - 1
            lower = [alpha[i - 1] for i in range(1, n)]
            diag = [beta[i - 1] + beta[i] for i in range(1, n)]
            upper = [alpha[i] for i in range(1, n)]
            rhs = [s[i] - s[i - 1] for i in range(1, n)]
            inner = _tridiagonal(lower, diag, upper, rhs) if k else []
            big_m[1:n] = inner
        self.big_m = big_m

    def _r(self, u: float, h: float) -> tuple[float, float, float]:
        """R(u), R'(u), R''(u) on an interval of length h."""
        sg = self.sigma
        if sg * h < 1e-3:
            return (u / h) * (u * u - h * h) / 6, (3 * u * u - h * h) / (6 * h), u / h
        den = _one_minus_exp(2 * sg * h)
        e = math.exp(-sg * (h - u))
        sinh_ratio = e * _one_minus_exp(2 * sg * u) / den
        cosh_ratio = e * (1 + math.exp(-2 * sg * u)) / den
        return ((sinh_ratio - u / h) / (sg * sg), (sg * cosh_ratio - 1 / h) / (sg * sg),
                sinh_ratio)

    def _parts(self, i: int, t: float) -> tuple[float, float, float]:
        """(ln S, d ln S/dt, d2 ln S/dt2) inside interval i, t_i <= t <= t_{i+1}."""
        h = self.h[i]
        a, b = t - self.ts[i], self.ts[i + 1] - t
        ra, rb = self._r(a, h), self._r(b, h)
        mi, mj = self.big_m[i], self.big_m[i + 1]
        value = self.xs[i] * b / h + self.xs[i + 1] * a / h + mi * rb[0] + mj * ra[0]
        slope = self.s[i] - mi * rb[1] + mj * ra[1]
        return value, slope, mi * rb[2] + mj * ra[2]

    def last_forward(self) -> float:
        return -self._parts(self.n - 1, self.ts[self.n])[1]

    def _log_inside(self, i: int, t: float) -> float:
        return self._parts(i, t)[0]

    def _forward_inside(self, i: int, t: float) -> float:
        return -self._parts(i, t)[1]

    def forward_slope(self, t: float) -> float:
        """f'(t) = -(ln S)'' inside the nodes, right-hand at a node."""
        return -self._parts(min(self._section(t), self.n - 1), t)[2]


class Hybrid(Interpolator):
    """LOG_LINEAR_DF up to node k (step_end), MONOTONE_CONVEX on nodes k..n after it."""

    def __init__(self, ts: Sequence[float], xs: Sequence[float], k: int):
        super().__init__(ts, xs)
        self.k = k
        self.steps = LogLinear(ts[:k + 1], xs[:k + 1])
        self.smooth = MonotoneConvex(ts[k:], xs[k:]) if k < self.n else None
        self.whole = LogLinear(ts, xs) if self.smooth is None else None

    def log(self, t: float) -> float:
        if self.whole is not None:
            return self.whole.log(t)
        if t < self.ts[self.k]:
            return self.steps.log(t)
        assert self.smooth is not None
        return self.smooth.log(t)

    def forward(self, t: float) -> float:
        if self.whole is not None:
            return self.whole.forward(t)
        if t < self.ts[self.k]:
            return self.steps.forward(t)
        assert self.smooth is not None
        return self.smooth.forward(t)


def make(method: str, ts: Sequence[float], xs: Sequence[float], tension: float | None,
         step_index: int | None) -> Interpolator:
    if method == "LOG_LINEAR_DF":
        return LogLinear(ts, xs)
    if method == "MONOTONE_CONVEX":
        return MonotoneConvex(ts, xs)
    if method == "MONOTONIC_LOG_CUBIC":
        return MonotonicLogCubic(ts, xs)
    if method == "TENSION_SPLINE":
        assert tension is not None
        return TensionSpline(ts, xs, tension)
    assert method == "HYBRID" and step_index is not None
    return Hybrid(ts, xs, step_index)


guard(globals())
