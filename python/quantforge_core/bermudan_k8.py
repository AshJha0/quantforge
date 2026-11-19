"""K-8 (stage K wave 1, PROPOSED; ruling KR-8): the `CN_RANNACHER_SMOOTHED` Bermudan scheme.

Same state, grid and exercise value as the pinned G-18 scheme (shortrate.py), with two changes:

1. Time stepping is Crank-Nicolson (theta = 1/2). The first full step after the maturity payoff and
   after each exercise date is replaced by two fully implicit steps of half size (Rannacher start-up).
   The implicit side uses `alpha` at the step's lower time, the explicit side at its upper time.
2. At each exercise date (maturity included) node `i` takes the average of `max(V, E)` over its cell
   `[x_i - dx/2, x_i + dx/2]`, with `V` and `E` linear between nodes (and the end segment extended at
   the two edge nodes), in closed form: the cell is split at the crossing of `V - E` when it lies
   inside.

The ladder is the exact derivative of this discrete scheme, carried forward in tangent mode: every
quantity is an array whose last axis holds the value and its derivatives with respect to the log
discount factors of the curve nodes, the mean reversion and the volatility. KR-8 step 4 names
reverse-mode AAD; the tangent sweep gives the same derivative of the same discrete scheme (up to
rounding), at a cost of `P + 1` columns per solve. This deviation is recorded in the K-8 status.

Specification: specifications/06-risk/bermudan-ladder-k8.md (PROPOSED).
"""

import bisect
import itertools
import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import numpy.typing as npt

from .finite import guard
from .shortrate import check_bermudan, curve_model, make_grid

Floats = Sequence[float]
Arr = npt.NDArray[np.float64]
METHOD = "CN_RANNACHER_SMOOTHED"


# --- dual arithmetic on the last axis: column 0 is the value, 1.. the tangents -------------------


def _mul(u: Arr, v: Arr) -> Arr:
    out = np.empty(np.broadcast_shapes(u.shape, v.shape))
    out[..., 0] = u[..., 0] * v[..., 0]
    out[..., 1:] = u[..., :1] * v[..., 1:] + v[..., :1] * u[..., 1:]
    return out


def _div(u: Arr, v: Arr) -> Arr:
    out = np.empty(np.broadcast_shapes(u.shape, v.shape))
    q = u[..., 0] / v[..., 0]
    out[..., 0] = q
    out[..., 1:] = (u[..., 1:] - q[..., None] * v[..., 1:]) / v[..., :1]
    return out


def _func(u: Arr, value: Arr, slope: Arr) -> Arr:
    out = np.empty(u.shape)
    out[..., 0] = value
    out[..., 1:] = slope[..., None] * u[..., 1:]
    return out


def _exp(u: Arr) -> Arr:
    e = np.exp(u[..., 0])
    return _func(u, e, e)


def _expm1(u: Arr) -> Arr:
    return _func(u, np.expm1(u[..., 0]), np.exp(u[..., 0]))


def _sqrt(u: Arr) -> Arr:
    s = np.sqrt(u[..., 0])
    return _func(u, s, 0.5 / s)


class _Curve:
    """Log-linear curve on dual logs (shortrate.Curve, G-3)."""

    def __init__(self, nodes: tuple[float, ...], logs: Arr):
        self.nodes, self.logs = nodes, logs

    def log_discount(self, t: float) -> Arr:
        if t <= 0:
            return np.zeros(self.logs.shape[1])
        n = self.nodes
        j = min(bisect.bisect_right(n, t) - 1, len(n) - 2)
        w = (t - n[j]) / (n[j + 1] - n[j])
        out: Arr = self.logs[j] + (self.logs[j + 1] - self.logs[j]) * w
        return out

    def forward(self, t: float) -> Arr:
        n = self.nodes
        j = min(max(bisect.bisect_right(n, t) - 1, 0), len(n) - 2)
        out: Arr = -(self.logs[j + 1] - self.logs[j]) / (n[j + 1] - n[j])
        return out


class _Model:
    def __init__(self, curve: _Curve, a: Arr, sigma: Arr):
        self.curve, self.a, self.sigma = curve, a, sigma
        self.s2 = _mul(sigma, sigma)

    def big_b(self, tau: float) -> Arr:
        return -_div(_expm1(-self.a * tau), self.a)

    def alpha(self, t: float) -> Arr:
        e = _expm1(-self.a * t)
        return self.curve.forward(t) + _div(_mul(self.s2, _mul(e, e)), 2 * _mul(self.a, self.a))

    def ln_a(self, t: float, s: float) -> tuple[Arr, Arr]:
        b = self.big_b(s - t)
        c = self.curve
        e2 = _expm1(-2 * self.a * t)
        ln_a = (
            c.log_discount(s)
            - c.log_discount(t)
            + _mul(b, c.forward(t))
            + _mul(_div(self.s2, 4 * self.a), _mul(e2, _mul(b, b)))
        )
        return ln_a, b


# --- the scheme ------------------------------------------------------------------------------------


def _exercise(m: _Model, t: float, xs: Arr, times: Floats, k: float, phi: float) -> Arr:
    after = [s for s in times if s > t]
    taus = [after[0] - t, *(b - a for a, b in itertools.pairwise(after))]
    r = xs + m.alpha(t)
    fixed = np.zeros_like(xs)
    last = fixed
    for tau, s in zip(taus, after, strict=True):
        ln_a, b = m.ln_a(t, s)
        p = _exp(ln_a - _mul(b, r))
        fixed = fixed + tau * p
        last = p
    out = -(last + k * fixed)
    out[..., 0] += 1.0
    return phi * out


def _positive_mean(lo: Arr, hi: Arr) -> Arr:
    """Mean of `max(f, 0)` over a segment where `f` is linear from `lo` to `hi`."""
    a, b = lo[:, 0], hi[:, 0]
    both = (a >= 0) & (b >= 0)
    cross = ~both & ((a > 0) | (b > 0))
    out = np.zeros_like(lo)
    out[both] = 0.5 * (lo[both] + hi[both])
    if cross.any():
        p = np.where((a >= b)[:, None], lo, hi)[cross]
        q = np.where((a >= b)[:, None], hi, lo)[cross]
        out[cross] = _div(_mul(p, p), 2 * (p - q))
    return out


def _smoothed_max(v: Arr, e: Arr) -> Arr:
    """Cell average of `max(V, E)` at every node (KR-8 step 3)."""
    f = v - e

    def halves(g: Arr) -> tuple[Arr, Arr]:
        left = np.empty_like(g)
        right = np.empty_like(g)
        left[1:] = 0.5 * (g[:-1] + g[1:])
        right[:-1] = left[1:]
        left[0] = 1.5 * g[0] - 0.5 * g[1]
        right[-1] = 1.5 * g[-1] - 0.5 * g[-2]
        return left, right

    fl, fr = halves(f)
    el, er = halves(e)
    e_mean = 0.25 * (el + 2 * e + er)
    return e_mean + 0.5 * (_positive_mean(fl, f) + _positive_mean(f, fr))


def _thomas_value(lower: Arr, diag: Arr, upper: Arr) -> tuple[list[float], list[float]]:
    """Value-only elimination: returns the multipliers and pivots, reused for every column."""
    n = len(diag)
    c = [0.0] * n
    den = [0.0] * n
    den[0] = float(diag[0])
    c[0] = float(upper[0]) / den[0]
    for i in range(1, n):
        den[i] = float(diag[i]) - float(lower[i]) * c[i - 1]
        c[i] = float(upper[i]) / den[i]
    return c, den


def _solve_columns(lower: Arr, c: list[float], den: list[float], rhs: Arr) -> Arr:
    n = rhs.shape[0]
    d = np.empty_like(rhs)
    d[0] = rhs[0] / den[0]
    for i in range(1, n):
        d[i] = (rhs[i] - lower[i] * d[i - 1]) / den[i]
    for i in range(n - 2, -1, -1):
        d[i] -= c[i] * d[i + 1]
    return d


def _solve(lower: Arr, diag: Arr, upper: Arr, rhs: Arr) -> Arr:
    """Solves the dual tridiagonal system: `M0 y0 = r0`, then `M0 dy = dr - dM y0`."""
    c, den = _thomas_value(lower[:, 0], diag[:, 0], upper[:, 0])
    y0 = _solve_columns(lower[:, 0], c, den, rhs[:, :1])[:, 0]
    full = rhs.copy()
    full[:, 1:] -= diag[:, 1:] * y0[:, None]
    full[1:, 1:] -= lower[1:, 1:] * y0[:-1, None]
    full[:-1, 1:] -= upper[:-1, 1:] * y0[1:, None]
    out = _solve_columns(lower[:, 0], c, den, full)
    out[:, 0] = y0
    return out


class _Operator:
    """Rows of `L` at the interior nodes, before the boundary substitution."""

    def __init__(self, m: _Model, xs: Arr, dx: Arr):
        inner = xs[1:-1]
        diff = _div(m.s2, 2 * _mul(dx, dx))
        conv = _div(_mul(m.a, inner), 2 * dx)
        self.m = m
        self.lower = -(diff + conv)
        self.upper = -(diff - conv)
        self.base = 2 * diff + inner

    def diag(self, t: float) -> Arr:
        return self.base + self.m.alpha(t)


def _implicit(op: _Operator, t: float, w: float, rhs: Arr) -> Arr:
    """Solves `(I + w L(t)) y = rhs` on the interior with linear extrapolation at both ends."""
    lower, upper = w * op.lower, w * op.upper
    diag = w * op.diag(t)
    diag[..., 0] += 1.0
    diag[0] += 2 * lower[0]
    upper[0] -= lower[0]
    lower[-1] -= upper[-1]
    diag[-1] += 2 * upper[-1]
    y = _solve(lower, diag, upper, rhs)
    return np.concatenate([[2 * y[0] - y[1]], y, [2 * y[-1] - y[-2]]])


def _explicit(op: _Operator, t: float, w: float, v: Arr) -> Arr:
    """`(I - w L(t)) v` at the interior nodes."""
    lv = _mul(op.lower, v[:-2]) + _mul(op.diag(t), v[1:-1]) + _mul(op.upper, v[2:])
    return v[1:-1] - w * lv


def scheme(
    times: Floats,
    dfs: Floats,
    a: float,
    sigma: float,
    payment_times: Floats,
    k: float,
    payer: bool,
    exercise_times: Floats,
    nx: int,
    steps_per_year: int,
    width: float,
    tangents: bool,
) -> Arr:
    """Price per unit notional (column 0) and, with `tangents`, its derivatives with respect to the
    log discount factors of the curve pillars, `a` and `sigma` (columns 1..)."""
    n = len(times)
    width_p = n + 3 if tangents else 1
    logs = np.zeros((n + 1, width_p))
    logs[1:, 0] = [math.log(d) for d in dfs]
    a_d = np.zeros(width_p)
    s_d = np.zeros(width_p)
    a_d[0], s_d[0] = a, sigma
    if tangents:
        logs[1:, 1 : n + 1] = np.eye(n)
        a_d[n + 1] = 1.0
        s_d[n + 2] = 1.0
    m = _Model(_Curve((0.0, *times), logs), a_d, s_d)
    phi = 1.0 if payer else -1.0
    knots = list(exercise_times)
    t_m = knots[-1]
    g = -_div(_expm1(-2 * t_m * a_d), 2 * a_d)
    sx = _mul(s_d, _sqrt(g))
    h = width * sx
    dx = 2 * h / (nx - 1)
    xs = -h + np.arange(nx, dtype=float)[:, None] * dx
    op = _Operator(m, xs, dx)
    v = _smoothed_max(np.zeros_like(xs), _exercise(m, t_m, xs, payment_times, k, phi))
    grid = [0.0, *knots]
    for kk in range(len(grid) - 1, 0, -1):
        t_hi, t_lo = grid[kk], grid[kk - 1]
        steps = max(1, math.ceil(steps_per_year * (t_hi - t_lo)))
        dt = (t_hi - t_lo) / steps
        for j in range(steps - 1, -1, -1):
            t = t_lo + j * dt
            if j == steps - 1:  # Rannacher start-up: two implicit half steps
                mid = t + dt / 2
                v = _implicit(op, mid, dt / 2, v[1:-1])
                v = _implicit(op, t, dt / 2, v[1:-1])
            else:
                v = _implicit(op, t, dt / 2, _explicit(op, t_lo + (j + 1) * dt, dt / 2, v))
        if kk - 1 > 0:
            v = _smoothed_max(v, _exercise(m, t_lo, xs, payment_times, k, phi))
    out: Arr = v[nx // 2]
    return out


def bermudan_price(
    times: Floats,
    dfs: Floats,
    a: float,
    sigma: float,
    rate_given: bool,
    start: float,
    payment_times: Floats,
    fixed_rate: float,
    swaption_type: str,
    notional: float,
    exercise_times: Floats,
    nx: int,
    steps_per_year: int,
    width: float,
) -> dict[str, float]:
    """`rates.shortrate.bermudan_swaption` with `method` `CN_RANNACHER_SMOOTHED`."""
    curve_model(times, dfs, a, sigma, rate_given)
    grid = make_grid(nx, steps_per_year, width)
    payer = check_bermudan(start, payment_times, swaption_type, exercise_times)
    r = scheme(
        times, dfs, a, sigma, payment_times, fixed_rate, payer, exercise_times,
        grid.nx, grid.steps_per_year, grid.width, False,
    )  # fmt: skip
    return {"price": notional * float(r[0])}


def bermudan_ladder(
    times: Floats,
    dfs: Floats,
    a: float,
    sigma: float,
    rate_given: bool,
    start: float,
    payment_times: Floats,
    fixed_rate: float,
    swaption_type: str,
    notional: float,
    exercise_times: Floats,
    nx: int,
    steps_per_year: int,
    width: float,
) -> dict[str, Any]:
    """`rates.shortrate.bermudan_ladder` with `method` `CN_RANNACHER_SMOOTHED`."""
    curve_model(times, dfs, a, sigma, rate_given)
    grid = make_grid(nx, steps_per_year, width)
    payer = check_bermudan(start, payment_times, swaption_type, exercise_times)
    r = scheme(
        times, dfs, a, sigma, payment_times, fixed_rate, payer, exercise_times,
        grid.nx, grid.steps_per_year, grid.width, True,
    )  # fmt: skip
    n = len(times)
    return {
        "price": notional * float(r[0]),
        "d_price_d_discount_factors": [notional * float(r[1 + j]) / d for j, d in enumerate(dfs)],
        "d_price_d_mean_reversion": notional * float(r[n + 1]),
        "d_price_d_sigma": notional * float(r[n + 2]),
    }


guard(globals())
