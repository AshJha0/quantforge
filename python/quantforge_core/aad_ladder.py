"""Q3b: the full ladder of the pinned Bermudan scheme by reverse-mode differentiation.

`rates.shortrate.bermudan_ladder` differentiates the discrete G-18 scheme of
`rates.shortrate.bermudan_swaption` with respect to every curve discount factor, the mean
reversion and the volatility. The adjoint is written by hand: one forward sweep stores the
coefficients, Thomas solutions and exercise decisions, and one backward sweep runs the transposed
tridiagonal solves, the `max` through its active branch, and the chain rule into the curve,
`alpha(t)`, the space grid and the bond formula.

Specification: specifications/06-risk/aad-core.md; rulings G-9, G-18, G-35.
"""
import bisect
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .finite import guard
from .shortrate import (
    Curve,
    Model,
    check_bermudan,
    curve_model,
    make_grid,
)

Floats = Sequence[float]


@dataclass
class _Adj:
    """Adjoint accumulators: logs of the curve nodes, `a` and `sigma`."""

    logs: list[float]
    a: float = 0.0
    sigma: float = 0.0
    xs: list[float] = field(default_factory=list)
    dx: float = 0.0


def _segment(curve: Curve, t: float) -> tuple[int, float]:
    n = curve.nodes
    j = bisect.bisect_right(n, t) - 1
    if j >= len(n) - 1:
        j = len(n) - 2
    return j, (t - n[j]) / (n[j + 1] - n[j])


def _forward_segment(curve: Curve, t: float) -> int:
    n = curve.nodes
    return min(max(bisect.bisect_right(n, t) - 1, 0), len(n) - 2)


def _bar_log_discount(curve: Curve, t: float, bar: float, adj: _Adj) -> None:
    """Adjoint of `ln D(t)`."""
    if t <= 0 or bar == 0:
        return
    j, w = _segment(curve, t)
    adj.logs[j] += bar * (1 - w)
    adj.logs[j + 1] += bar * w


def _bar_forward(curve: Curve, t: float, bar: float, adj: _Adj) -> None:
    """Adjoint of the right-hand forward `f(t) = -(L_(j+1) - L_j)/(T_(j+1) - T_j)`."""
    if bar == 0:
        return
    j = _forward_segment(curve, t)
    span = curve.nodes[j + 1] - curve.nodes[j]
    adj.logs[j + 1] -= bar / span
    adj.logs[j] += bar / span


def _alpha(m: Model, t: float) -> float:
    assert m.curve is not None
    return m.curve.forward(t) + m.sigma ** 2 / (2 * m.a ** 2) * math.expm1(-m.a * t) ** 2


def _bar_alpha(m: Model, t: float, bar: float, adj: _Adj) -> None:
    if bar == 0:
        return
    assert m.curve is not None
    a, s = m.a, m.sigma
    e = math.expm1(-a * t)
    _bar_forward(m.curve, t, bar, adj)
    adj.sigma += bar * s * e * e / (a * a)
    adj.a += bar * s * s / 2 * (2 * e * (-t * math.exp(-a * t)) / (a * a) - 2 * e * e / a ** 3)


@dataclass(frozen=True)
class _Exercise:
    """Exercise values at one time with what their adjoint needs."""

    t: float
    after: tuple[float, ...]
    taus: tuple[float, ...]
    ln_a: tuple[float, ...]
    bs: tuple[float, ...]
    values: tuple[float, ...]


def _exercise(m: Model, t: float, xs: Floats, times: Floats, k: float, phi: float) -> _Exercise:
    after = tuple(s for s in times if s > t)
    taus = (after[0] - t, *(b - a for a, b in itertools.pairwise(after)))
    factors = [m.ab(t, s) for s in after]
    alpha = _alpha(m, t)
    values = []
    for x in xs:
        r = x + alpha
        bonds = [math.exp(la - bb * r) for la, bb in factors]
        fixed = 0.0
        for tau, p in zip(taus, bonds, strict=True):
            fixed += tau * p
        values.append(phi * (1 - bonds[-1] - k * fixed))
    return _Exercise(t, after, taus, tuple(f[0] for f in factors), tuple(f[1] for f in factors),
                     tuple(values))


def _bar_exercise(m: Model, ex: _Exercise, xs: Floats, bars: Floats, k: float, phi: float,
                  adj: _Adj) -> None:
    """Adjoint of the exercise values at the nodes with nonzero `bars`."""
    assert m.curve is not None
    a, s, t = m.a, m.sigma, ex.t
    alpha = _alpha(m, t)
    n = len(ex.after)
    bar_ln_a = [0.0] * n
    bar_b = [0.0] * n
    bar_alpha = 0.0
    for i, (x, bar) in enumerate(zip(xs, bars, strict=True)):
        if bar == 0:
            continue
        r = x + alpha
        bar_r = 0.0
        for j in range(n):
            p = math.exp(ex.ln_a[j] - ex.bs[j] * r)
            # value = phi (1 - p_n - k sum tau_j p_j)
            bar_p = -phi * bar * (k * ex.taus[j] + (1.0 if j == n - 1 else 0.0))
            bar_ln_a[j] += bar_p * p
            bar_b[j] -= bar_p * p * r
            bar_r -= bar_p * p * ex.bs[j]
        adj.xs[i] += bar_r
        bar_alpha += bar_r
    _bar_alpha(m, t, bar_alpha, adj)
    # ln A = ln D(T) - ln D(t) + B f(t) + sigma^2/(4a) E2 B^2, B = -expm1(-a tau)/a
    e2 = math.expm1(-2 * a * t)
    f_t = m.curve.forward(t)
    bar_f = 0.0
    for j in range(n):
        big_b = ex.bs[j]
        tau = ex.after[j] - t
        la = bar_ln_a[j]
        _bar_log_discount(m.curve, ex.after[j], la, adj)
        _bar_log_discount(m.curve, t, -la, adj)
        bar_f += la * big_b
        adj.sigma += la * s / (2 * a) * e2 * big_b * big_b
        adj.a += la * s * s * big_b * big_b * (-2 * t * math.exp(-2 * a * t) / (4 * a)
                                               - e2 / (4 * a * a))
        bar_bb = bar_b[j] + la * (f_t + s * s / (2 * a) * e2 * big_b)
        adj.a += bar_bb * (tau * math.exp(-a * tau) - big_b) / a
    _bar_forward(m.curve, t, bar_f, adj)


def _transposed_thomas(sub: Floats, diag: Floats, sup: Floats, rhs: Floats) -> list[float]:
    """Solves `M^T y = rhs` for a tridiagonal `M` given as the transpose's own diagonals:
    `sub[i] = M[i-1, i]` (M's upper) and `sup[i] = M[i+1, i]` (M's lower)."""
    n = len(diag)
    c = [0.0] * n
    d = [0.0] * n
    c[0] = sup[0] / diag[0]
    d[0] = rhs[0] / diag[0]
    for i in range(1, n):
        den = diag[i] - sub[i] * c[i - 1]
        c[i] = sup[i] / den
        d[i] = (rhs[i] - sub[i] * d[i - 1]) / den
    y = [0.0] * n
    y[-1] = d[-1]
    for i in range(n - 2, -1, -1):
        y[i] = d[i] - c[i] * y[i + 1]
    return y


def _thomas(lower: Floats, diag: Floats, upper: Floats, rhs: Floats) -> list[float]:
    n = len(diag)
    c = [0.0] * n
    d = [0.0] * n
    c[0] = upper[0] / diag[0]
    d[0] = rhs[0] / diag[0]
    for i in range(1, n):
        den = diag[i] - lower[i] * c[i - 1]
        c[i] = upper[i] / den
        d[i] = (rhs[i] - lower[i] * d[i - 1]) / den
    x = [0.0] * n
    x[-1] = d[-1]
    for i in range(n - 2, -1, -1):
        x[i] = d[i] - c[i] * x[i + 1]
    return x


@dataclass
class _Step:
    t: float
    dt: float
    alpha: float
    lower: list[float]
    diag: list[float]
    upper: list[float]
    inner: list[float]


def ladder(m: Model, start: float, payment_times: Floats, k: float, payer: bool,
           exercise_times: Floats, nx: int, steps_per_year: int, width: float
           ) -> tuple[float, list[float], float, float]:
    """Price per unit notional and its derivatives: per curve pillar, `a`, `sigma`."""
    assert m.curve is not None
    a, sig = m.a, m.sigma
    phi = 1.0 if payer else -1.0
    knots = list(exercise_times)
    t_m = knots[-1]
    g = -math.expm1(-2 * a * t_m) / (2 * a)
    sx = sig * math.sqrt(g)
    h = width * sx
    dx = 2 * h / (nx - 1)
    xs = [-h + i * dx for i in range(nx)]
    diff = sig * sig / (2 * dx * dx)
    last = _exercise(m, t_m, xs, payment_times, k, phi)
    v = [max(e, 0.0) for e in last.values]
    steps: list[_Step] = []
    knot_events: list[tuple[int, _Exercise, list[bool]]] = []  # (steps done, exercise, chosen)
    times = [0.0, *knots]
    nx - 2
    inner_x = xs[1:-1]
    cache: dict[float, tuple[list[float], list[float], list[float]]] = {}
    for kk in range(len(times) - 1, 0, -1):
        t_hi, t_lo = times[kk], times[kk - 1]
        n = max(1, math.ceil(steps_per_year * (t_hi - t_lo)))
        dt = (t_hi - t_lo) / n
        if dt not in cache:
            # lower and upper do not depend on t; the diagonal is base + dt alpha(t)
            lower = [-dt * (diff + a * x / (2 * dx)) for x in inner_x]
            upper = [-dt * (diff - a * x / (2 * dx)) for x in inner_x]
            base = [1 + dt * (2 * diff + x) for x in inner_x]
            lower[-1] -= upper[-1]
            upper[0] -= lower[0]
            base[0] += 2 * lower[0]
            base[-1] += 2 * upper[-1]
            cache[dt] = (lower, base, upper)
        ml, base, mu = cache[dt]
        for j in range(n - 1, -1, -1):
            t = t_lo + j * dt
            alpha = _alpha(m, t)
            shift = dt * alpha
            md = [d + shift for d in base]
            inner = _thomas(ml, md, mu, v[1:-1])
            steps.append(_Step(t, dt, alpha, ml, md, mu, inner))
            v = [2 * inner[0] - inner[1], *inner, 2 * inner[-1] - inner[-2]]
        if kk - 1 > 0:
            ex = _exercise(m, t_lo, xs, payment_times, k, phi)
            chosen = [e > vi for e, vi in zip(ex.values, v, strict=True)]
            v = [e if c else vi for e, vi, c in zip(ex.values, v, chosen, strict=True)]
            knot_events.append((len(steps), ex, chosen))
    price = v[nx // 2]

    # --- backward sweep ---------------------------------------------------------------------
    adj = _Adj(logs=[0.0] * len(m.curve.nodes), xs=[0.0] * nx)
    bar_v = [0.0] * nx
    bar_v[nx // 2] = 1.0
    bar_diff = 0.0
    scale_sum = 0.0  # sum of x-bar x from the steps' diagonals
    transposed: dict[int, tuple[list[float], list[float]]] = {}
    events = {done: (ex, chosen) for done, ex, chosen in knot_events}
    for idx in range(len(steps) - 1, -1, -1):
        if idx + 1 in events:
            ex, chosen = events[idx + 1]
            bars = [b if c else 0.0 for b, c in zip(bar_v, chosen, strict=True)]
            bar_v = [0.0 if c else b for b, c in zip(bar_v, chosen, strict=True)]
            _bar_exercise(m, ex, xs, bars, k, phi, adj)
        st = steps[idx]
        y = st.inner
        # v = [2 y0 - y1, y, 2 y_-1 - y_-2]
        bar_y = bar_v[1:-1]
        bar_y[0] += 2 * bar_v[0]
        bar_y[1] -= bar_v[0]
        bar_y[-1] += 2 * bar_v[-1]
        bar_y[-2] -= bar_v[-1]
        # st.lower, st.diag, st.upper hold the matrix after the boundary substitution
        key = id(st.lower)
        if key not in transposed:
            transposed[key] = ([0.0, *st.upper[:-1]], [*st.lower[1:], 0.0])
        sub, sup = transposed[key]
        lam = _transposed_thomas(sub, st.diag, sup, bar_y)
        bar_v = [0.0, *lam, 0.0]  # the right-hand side is the previous interior
        # M-bar = -lam y^T on the three diagonals, then back through the substitution
        # md0 = d0 + 2 l0, mu0 = u0 - l0, ml_-1 = l_-1 - u_-1, md_-1 = d_-1 + 2 u_-1.
        bd = [-lp * yp for lp, yp in zip(lam, y, strict=True)]
        bl = [0.0, *(-lp * yp for lp, yp in zip(lam[1:], y, strict=False))]
        bu = [*(-lp * yp for lp, yp in zip(lam, y[1:], strict=False)), 0.0]
        bl[0] += 2 * bd[0] - bu[0]
        bu[-1] += 2 * bd[-1] - bl[-1]
        dt = st.dt
        s_d = sum(bd)
        bar_diff += dt * (2 * s_d - sum(bl) - sum(bu))
        # conv = a x/(2 dx): its x and dx parts cancel in the scale sum below (conv is
        # invariant to scaling the grid), so only its a part remains.
        adj.a += dt * (math.sumprod(bu, inner_x) - math.sumprod(bl, inner_x)) / (2 * dx)
        scale_sum += dt * math.sumprod(bd, inner_x)
        _bar_alpha(m, st.t, dt * s_d, adj)
    _bar_exercise(m, last, xs, [b if e > 0 else 0.0 for b, e in zip(bar_v, last.values,
                                                                      strict=True)],
                  k, phi, adj)
    # diff = sigma^2/(2 dx^2)
    adj.sigma += bar_diff * sig / (dx * dx)
    adj.dx -= bar_diff * sig * sig / (dx ** 3)
    # xs = sx (width (-1 + 2 i/(nx-1))) and dx = sx (2 width/(nx-1)): both proportional to sx
    bar_sx = (math.fsum(b * x for b, x in zip(adj.xs, xs, strict=True)) + scale_sum
              + adj.dx * dx) / sx
    adj.sigma += bar_sx * sx / sig
    dg = (t_m * math.exp(-2 * a * t_m) - g) / a
    adj.a += bar_sx * sig / (2 * math.sqrt(g)) * dg
    dfs = [math.exp(lg) for lg in m.curve.logs[1:]]
    bar_dfs = [lb / d for lb, d in zip(adj.logs[1:], dfs, strict=True)]
    return price, bar_dfs, adj.a, adj.sigma


def bermudan_ladder(times: Floats, dfs: Floats, a: float, sigma: float, rate_given: bool,
                    start: float, payment_times: Floats, fixed_rate: float, swaption_type: str,
                    notional: float, exercise_times: Floats, nx: int, steps_per_year: int,
                    width: float) -> dict[str, object]:
    """`rates.shortrate.bermudan_ladder`: the Bermudan price and its full ladder."""
    model = curve_model(times, dfs, a, sigma, rate_given)
    grid = make_grid(nx, steps_per_year, width)
    payer = check_bermudan(start, payment_times, swaption_type, exercise_times)
    price, d_dfs, d_a, d_sigma = ladder(model, start, payment_times, fixed_rate, payer,
                                        exercise_times, grid.nx, grid.steps_per_year, grid.width)
    return {"price": notional * price,
            "d_price_d_discount_factors": [notional * d for d in d_dfs],
            "d_price_d_mean_reversion": notional * d_a, "d_price_d_sigma": notional * d_sigma}


guard(globals())
