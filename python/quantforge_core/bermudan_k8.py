"""K-8 (stage K; rulings KR-8 and KR-15): the `CN_RANNACHER_SMOOTHED` Bermudan scheme.

Same state, grid, knots and exercise value as the pinned G-18 scheme (shortrate.py), with three
changes (specifications/06-risk/bermudan-ladder-k8.md, version 0.2.0):

1. The scheme solves for `U(t, x) = V(t, x) exp(-int_0^t alpha)`. The operator then has no curve
   term and does not change with time; the curve enters only through `P(0, t)` at exercise and
   payment times (KR-15 a). A curve node inside a time step can no longer leak into the ladder.
2. Time stepping is Crank-Nicolson (theta = 1/2). The first two steps after the maturity payoff
   and after each exercise date are each replaced by two fully implicit steps of half size
   (Rannacher start-up, four half steps; KR-15 c).
3. At each exercise date (maturity included) the `max` is applied as a hat-weighted average of
   `max(U - E, 0)` over `[x_(i-1), x_(i+1)]`, with `U - E` linear between nodes, a third-order
   correction in the cell that holds the crossing, and the stencil `1 - delta^2/6` (KR-15 b).

The ladder is the exact derivative of this discrete scheme, carried forward in tangent mode: every
quantity is an array whose last axis holds the value and its derivatives with respect to the log
discount factors of the curve nodes, the mean reversion and the volatility. KR-8 step 4 names
reverse-mode AAD; the tangent sweep gives the same derivative of the same discrete scheme (up to
rounding), at a cost of `P + 1` columns per solve.
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


class _Model:
    def __init__(self, curve: _Curve, a: Arr, sigma: Arr):
        self.curve, self.a, self.sigma = curve, a, sigma
        self.s2 = _mul(sigma, sigma)

    def big_b(self, tau: float) -> Arr:
        return -_div(_expm1(-self.a * tau), self.a)


# --- the scheme ------------------------------------------------------------------------------------


def _plus(u: Arr, c: float) -> Arr:
    """`u + c` for a dual `u` and a constant `c` (the tangents are untouched)."""
    out = u.copy()
    out[..., 0] += c
    return out


def _exercise(m: _Model, t: float, xs: Arr, times: Floats, k: float, phi: float) -> Arr:
    """Exercise value at `t` times `D(t) = exp(-int_0^t alpha)` (spec step 3). No forward rate
    appears: it cancels between the bond formula and `alpha`."""
    after = [s for s in times if s > t]
    taus = [after[0] - t, *(b - a for a, b in itertools.pairwise(after))]
    e1 = _expm1(-m.a * t)
    e2 = _expm1(-2 * m.a * t)
    big_i = _plus(2 * _div(e1, m.a) - _div(e2, 2 * m.a), t)
    c2 = _div(m.s2, 2 * _mul(m.a, m.a))
    c4 = _div(m.s2, 4 * m.a)
    lead = _exp(m.curve.log_discount(t) - _mul(c2, big_i))
    fixed = np.zeros_like(xs)
    last = fixed
    for tau, s in zip(taus, after, strict=True):
        b = m.big_b(s - t)
        drift = _mul(c2, big_i + _mul(b, _mul(e1, e1))) - _mul(c4, _mul(e2, _mul(b, b)))
        q = _exp(m.curve.log_discount(s) - drift - _mul(b, xs))
        fixed = fixed + tau * q
        last = q
    out: Arr = phi * (lead - last - k * fixed)
    return out


def _hat_part(p: Arr, q: Arr) -> Arr:
    """`int_0^1 (1 - u) max(p + (q - p) u, 0) du` row by row: half of the hat-weighted average of
    the positive part, on the segment from a node (value `p`) to its neighbour (value `q`)."""
    a, b = p[:, 0], q[:, 0]
    out = np.zeros_like(p)
    both = (a >= 0) & (b >= 0)
    out[both] = p[both] / 3 + q[both] / 6
    down = (a > 0) & (b < 0)
    if down.any():
        d = p[down] - q[down]
        t = _div(_mul(p[down], p[down]), 2 * d)
        out[down] = t - _mul(t, _div(p[down], d)) / 3
    up = (a < 0) & (b > 0)
    if up.any():
        r = _div(q[up], q[up] - p[up])
        out[up] = _mul(q[up], _mul(r, r)) / 6
    return out


def _smoothed_max(v: Arr, e: Arr) -> Arr:
    """`max(V, E)` at an exercise date as a second-order smoothing (KR-15 b, spec step 5)."""
    f = v - e
    before = np.empty_like(f)
    after = np.empty_like(f)
    before[1:] = f[:-1]
    before[0] = 2 * f[0] - f[1]
    after[:-1] = f[1:]
    after[-1] = 2 * f[-1] - f[-2]
    h = _hat_part(f, before) + _hat_part(f, after)
    d2 = np.zeros_like(f)
    d2[1:-1] = f[:-2] - 2 * f[1:-1] + f[2:]
    a = f[:, 0]
    crossing = ((a[:-1] > 0) & (a[1:] < 0)) | ((a[:-1] < 0) & (a[1:] > 0))
    for j in np.nonzero(crossing)[0]:
        pos, neg = (j, j + 1) if a[j] > 0 else (j + 1, j)
        rho = _div(f[pos], f[pos] - f[neg])  # the part of the cell where V > E
        rest = _plus(-rho, 1.0)
        g = _mul(_mul(rho, rest), _plus(2 * rho, -1.0)) / 12
        corr = _mul(g, 0.5 * (d2[j] + d2[j + 1]))
        h[pos] -= _mul(rest, corr)
        h[neg] -= _mul(rho, corr)
    out = h.copy()
    out[1:-1] -= (h[:-2] - 2 * h[1:-1] + h[2:]) / 6
    return e + out


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
    """Rows of `A = -L` at the interior nodes, before the boundary substitution. `A` has no curve
    term (KR-15 a), so it is the same at every time."""

    def __init__(self, m: _Model, xs: Arr, dx: Arr):
        inner = xs[1:-1]
        diff = _div(m.s2, 2 * _mul(dx, dx))
        conv = _div(_mul(m.a, inner), 2 * dx)
        self.lower = -(diff + conv)
        self.upper = -(diff - conv)
        self.diag = 2 * diff + inner


def _implicit(op: _Operator, w: float, rhs: Arr) -> Arr:
    """Solves `(I + w A) y = rhs` on the interior with linear extrapolation at both ends."""
    lower, upper = w * op.lower, w * op.upper
    diag = _plus(w * op.diag, 1.0)
    diag[0] += 2 * lower[0]
    upper[0] -= lower[0]
    lower[-1] -= upper[-1]
    diag[-1] += 2 * upper[-1]
    y = _solve(lower, diag, upper, rhs)
    return np.concatenate([[2 * y[0] - y[1]], y, [2 * y[-1] - y[-2]]])


def _explicit(op: _Operator, w: float, v: Arr) -> Arr:
    """`(I - w A) v` at the interior nodes."""
    lv = _mul(op.lower, v[:-2]) + _mul(op.diag, v[1:-1]) + _mul(op.upper, v[2:])
    return v[1:-1] - w * lv


START_UP_STEPS = 2  # steps replaced by two implicit half steps each (KR-15 c)


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
        half = (t_hi - t_lo) / steps / 2
        for j in range(steps - 1, -1, -1):
            if j >= steps - START_UP_STEPS:  # Rannacher start-up: two implicit half steps
                v = _implicit(op, half, v[1:-1])
                v = _implicit(op, half, v[1:-1])
            else:
                v = _implicit(op, half, _explicit(op, half, v))
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
    # the schedule (structural E_INPUT) before the grid's width (E_DOMAIN): error order HR-66, as Java
    payer = check_bermudan(start, payment_times, swaption_type, exercise_times)
    grid = make_grid(nx, steps_per_year, width)
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
    # the schedule (structural E_INPUT) before the grid's width (E_DOMAIN): error order HR-66, as Java
    payer = check_bermudan(start, payment_times, swaption_type, exercise_times)
    grid = make_grid(nx, steps_per_year, width)
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
