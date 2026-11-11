"""Hedge solvers (specifications/08-hedging/hedge-solvers.md, rulings I-1 to I-14).

Constrained least squares, integer lots, minimum variance, Greek neutralisation, equity beta
futures and the residual risk report. Stage B's `hedging.solve` is unchanged.

The least-squares problems are kept in their square-root form: with `B = [W^(1/2) A; ridge^(1/2) I]`
and `d = [W^(1/2) b; 0]`, `f(x) = |B x + d|^2` and `H = B^T B`. Working on `B` (SVD, QR) instead of
`H` keeps the conditioning at that of `B`, so problems whose weights span many decades stay
accurate. The singularity rule I-3 (an eigenvalue of `Z^T H Z` at most `1e-12` times the largest
eigenvalue of `H`) is applied to squared singular values, which are those eigenvalues.
"""
import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from .errors import QfError
from .finite import guard

Floats = Sequence[float]
Matrix = Sequence[Sequence[float]]
Bounds = Sequence[float | None]
NDArray = Any  # numpy arrays; numpy's own stubs would tie mypy to the numpy version
THRESHOLD = 1e-12  # ruling I-3
_MAX_ENUMERATED = 20_000_000  # integer search points before E_NO_CONVERGENCE (never near it)


def _z(v: float) -> float:
    """Turns -0.0 into 0.0 so that no output carries a negative zero."""
    return float(v) + 0.0


def _zs(values: Any) -> list[float]:
    return [_z(v) for v in values]


def _shape(a: Matrix, b: Floats, weights: Floats) -> tuple[int, int]:
    """Check 1 shared by the least-squares operations: returns (m, n) or raises E_INPUT."""
    m = len(a)
    n = len(a[0]) if m else 0
    if m == 0 or n == 0 or any(len(row) != n for row in a):
        raise QfError("E_INPUT", "a must be a non-empty matrix with rows of one length", "a")
    if len(b) != m:
        raise QfError("E_INPUT", "b must have one entry per row of a", "b")
    if len(weights) != m:
        raise QfError("E_INPUT", "weights must have one entry per row of a", "weights")
    return m, n


def _check_weights_ridge(weights: Floats, ridge: float) -> None:
    if any(w <= 0 for w in weights):
        raise QfError("E_DOMAIN", "weights must be positive", "weights")
    if ridge < 0:
        raise QfError("E_DOMAIN", "ridge must not be negative", "ridge")


def _root_form(a: Matrix, b: Floats, weights: Floats, ridge: float) -> tuple[NDArray, NDArray]:
    """(B, d) with f(x) = |B x + d|^2."""
    root_w = np.sqrt(np.asarray(weights, dtype=float))
    big_b = np.asarray(a, dtype=float) * root_w[:, None]
    d = np.asarray(b, dtype=float) * root_w
    if ridge > 0:
        n = big_b.shape[1]
        big_b = np.vstack([big_b, math.sqrt(ridge) * np.eye(n)])
        d = np.concatenate([d, np.zeros(n)])
    return big_b, d


def _objective(a: Matrix, b: Floats, weights: Floats, ridge: float,
               x: Floats) -> tuple[list[float], float]:
    """(residual A x + b, f(x)) in correctly rounded sums."""
    residual = [math.fsum([*(row[j] * x[j] for j in range(len(x))), v]) for row, v in zip(a, b)]
    value = math.fsum(w * r * r for w, r in zip(weights, residual)) + ridge * math.fsum(
        v * v for v in x)
    return residual, value


def _lstsq_min_norm(m: NDArray, r: NDArray, cut_sq: float) -> tuple[NDArray, int]:
    """The minimum-norm y minimising |m y + r|, dropping singular values whose square is at or
    below `cut_sq`. Returns (y, rank)."""
    if m.shape[1] == 0:
        return np.zeros(0), 0
    u, s, vt = np.linalg.svd(m, full_matrices=False)
    keep = s * s > cut_sq
    y = -vt[keep].T @ ((u[:, keep].T @ r) / s[keep])
    return y, int(keep.sum())


def _equality_split(e_mat: NDArray, rhs: NDArray, cut: float) -> tuple[NDArray, NDArray]:
    """(x_p, Z): the minimum-norm solution of e_mat x = rhs and an orthonormal null-space basis.
    Singular values at or below `cut` count as zero (redundant, consistent rows)."""
    cols = e_mat.shape[1]
    if e_mat.shape[0] == 0 or cols == 0:
        return np.zeros(cols), np.eye(cols)
    u, s, vt = np.linalg.svd(e_mat, full_matrices=True)
    r = int((s > cut).sum())
    x_p = vt[:r].T @ ((u[:, :r].T @ rhs) / s[:r])
    return x_p, vt[r:].T


def _phase_one(e_mat: NDArray, e_rhs: NDArray, lower: Bounds, upper: Bounds) -> NDArray | None:
    """A point with E x = e inside the bounds, or None when there is none (I-14).

    Phase 1 of the simplex method on a dense tableau with Bland's rule. Each variable is moved to
    non-negative form: `l + s`, `u - s`, or `p - q` when free; a finite range adds `s + t = u - l`.
    """
    k, n = e_mat.shape
    columns: list[tuple[int, float]] = []  # (variable, sign) of each structural column
    offset = np.zeros(n)
    ranges: list[tuple[int, float]] = []  # (column of s, u - l)
    for j in range(n):
        lo, hi = lower[j], upper[j]
        if lo is not None:
            offset[j] = lo
            columns.append((j, 1.0))
            if hi is not None:
                ranges.append((len(columns) - 1, hi - lo))
        elif hi is not None:
            offset[j] = hi
            columns.append((j, -1.0))
        else:
            columns.append((j, 1.0))
            columns.append((j, -1.0))
    n_struct = len(columns)
    n_slack = len(ranges)
    rows = k + n_slack
    n_cols = n_struct + n_slack + k  # structural, range slacks t, artificials
    tab = np.zeros((rows + 1, n_cols + 1))
    rhs = e_rhs - e_mat @ offset
    for c, (j, sign) in enumerate(columns):
        tab[:k, c] = sign * e_mat[:, j]
    tab[:k, -1] = rhs
    flip = rhs < 0
    tab[:k][flip] *= -1.0
    for r, (c, width) in enumerate(ranges):
        tab[k + r, c] = 1.0
        tab[k + r, n_struct + r] = 1.0
        tab[k + r, -1] = width
    basis = [n_struct + n_slack + r for r in range(k)] + [n_struct + r for r in range(n_slack)]
    for r in range(k):
        tab[r, n_struct + n_slack + r] = 1.0
    # Phase-1 cost: sum of the artificials, expressed in the non-basic columns.
    tab[-1, :] = -tab[:k, :].sum(axis=0)
    tab[-1, n_struct + n_slack:n_cols] = 0.0
    scale = max(1.0, float(np.abs(tab[:rows, -1]).max(initial=0.0)),
                float(np.abs(tab[:rows, :n_cols]).max(initial=0.0)))
    tol = 1e-11 * scale
    for _ in range(50 * (rows + n_cols) + 100):
        entering = next((c for c in range(n_cols) if tab[-1, c] < -tol), None)
        if entering is None:
            break
        col = tab[:rows, entering]
        best: tuple[float, int, int] | None = None
        for r in range(rows):
            if col[r] > tol:
                ratio = tab[r, -1] / col[r]
                key = (ratio, basis[r], r)
                if best is None or key < best:
                    best = key
        if best is None:  # unbounded direction: impossible with a non-negative cost
            break
        r = best[2]
        tab[r] /= tab[r, entering]
        for other in range(rows + 1):
            if other != r and tab[other, entering] != 0.0:
                tab[other] -= tab[other, entering] * tab[r]
        basis[r] = entering
    else:
        raise QfError("E_NO_CONVERGENCE", "the feasibility search did not settle")
    if -tab[-1, -1] > 1e-9 * scale:
        return None
    values = np.zeros(n_cols)
    for r, c in enumerate(basis):
        values[c] = tab[r, -1]
    x = offset.copy()
    for c, (j, sign) in enumerate(columns):
        x[j] += sign * values[c]
    return x


class _Qp:
    """One bound- and equality-constrained least-squares problem in square-root form."""

    def __init__(self, big_b: NDArray, d: NDArray, e_mat: NDArray, e_rhs: NDArray,
                 lower: Bounds, upper: Bounds, h_largest_sq: float, e_cut: float):
        self.big_b, self.d, self.e_mat, self.e_rhs = big_b, d, e_mat, e_rhs
        self.lower, self.upper = lower, upper
        self.cut_sq = THRESHOLD * h_largest_sq
        self.e_cut = e_cut
        self.n = big_b.shape[1]

    def subproblem(self, free: list[int], x: NDArray) -> NDArray:
        """The minimiser of f with the variables outside `free` held at their values in x and
        E x = e: the equality-constrained step of the active-set method."""
        fixed = [j for j in range(self.n) if j not in set(free)]
        out = x.copy()
        if not free:
            return out
        r0 = self.d + self.big_b[:, fixed] @ x[fixed]
        rhs = self.e_rhs - self.e_mat[:, fixed] @ x[fixed]
        x_p, z = _equality_split(self.e_mat[:, free], rhs, self.e_cut)
        bs = self.big_b[:, free]
        y, _ = _lstsq_min_norm(bs @ z, bs @ x_p + r0, self.cut_sq)
        out[free] = x_p + z @ y
        return out

    def multipliers(self, x: NDArray, free: list[int]) -> NDArray:
        """g + E^T lambda at x, with lambda fitted on the free variables: on a bound in the working
        set this is mu_L at a lower bound and -mu_U at an upper bound."""
        g = 2.0 * (self.big_b.T @ (self.big_b @ x + self.d))
        if self.e_mat.shape[0] and free:
            lam = np.linalg.lstsq(self.e_mat[:, free].T, -g[free], rcond=None)[0]
            g = g + self.e_mat.T @ lam
        return g

    def active_set(self, x: NDArray) -> NDArray:
        """Primal active-set method [NW06 ch. 16] from a feasible x."""
        lower, upper, n = self.lower, self.upper, self.n
        work: dict[int, str] = {}
        for j in range(n):
            if lower[j] is not None and lower[j] == upper[j]:
                work[j] = "F"
            elif lower[j] is not None and x[j] <= lower[j]:
                work[j] = "L"
            elif upper[j] is not None and x[j] >= upper[j]:
                work[j] = "U"
        for j, side in work.items():
            bound = lower[j] if side in "FL" else upper[j]
            x[j] = bound
        grad_scale = float(np.abs(2.0 * (self.big_b.T @ self.d)).max(initial=0.0))
        for _ in range(100 * (n + 1)):
            free = [j for j in range(n) if j not in work]
            target = self.subproblem(free, x)
            p = target - x
            alpha, blocking, side = 1.0, -1, ""
            for j in free:
                lo, hi = lower[j], upper[j]
                if p[j] < 0 and lo is not None:
                    step = max((lo - x[j]) / p[j], 0.0)
                    if step < alpha:
                        alpha, blocking, side = step, j, "L"
                elif p[j] > 0 and hi is not None:
                    step = max((hi - x[j]) / p[j], 0.0)
                    if step < alpha:
                        alpha, blocking, side = step, j, "U"
            if blocking >= 0:
                x = x + alpha * p
                work[blocking] = side
                x[blocking] = lower[blocking] if side == "L" else upper[blocking]
                continue
            x = target
            g = self.multipliers(x, free)
            scale = max(grad_scale, float(np.abs(g).max(initial=0.0)),
                        float(np.abs(2.0 * (self.big_b.T @ (self.big_b @ x))).max(initial=0.0)))
            worst, drop = -1e-11 * scale, -1
            for j, s in work.items():
                mu = g[j] if s == "L" else -g[j] if s == "U" else math.inf
                if mu < worst:
                    worst, drop = mu, j
            if drop < 0:
                return x
            del work[drop]
        raise QfError("E_NO_CONVERGENCE", "the active-set search did not settle")


def _qp_core(a: Matrix, b: Floats, weights: Floats, ridge: float, eq_matrix: Matrix | None,
             eq_rhs: Floats | None, lower: Bounds | None, upper: Bounds | None,
             singular: str) -> dict[str, Any]:
    _, n = _shape(a, b, weights)
    if (eq_matrix is None) != (eq_rhs is None):
        raise QfError("E_INPUT", "eq_matrix and eq_rhs go together", "eq_matrix")
    e_rows: Matrix = eq_matrix or []
    e_vals: Floats = eq_rhs or []
    if any(len(row) != n for row in e_rows):
        raise QfError("E_INPUT", "eq_matrix rows must have one entry per instrument", "eq_matrix")
    if len(e_vals) != len(e_rows):
        raise QfError("E_INPUT", "eq_rhs must have one entry per row of eq_matrix", "eq_rhs")
    for key, bound in (("lower", lower), ("upper", upper)):
        if bound is not None and len(bound) != n:
            raise QfError("E_INPUT", f"{key} must have one entry per instrument", key)
    lo: Bounds = lower if lower is not None else [None] * n
    hi: Bounds = upper if upper is not None else [None] * n
    bounded = any(v is not None for v in (*lo, *hi))
    if singular == "MIN_NORM" and bounded:
        raise QfError("E_INPUT", "MIN_NORM takes no bounds (ruling I-5)", "singular")
    _check_weights_ridge(weights, ridge)
    if any(p is not None and q is not None and p > q for p, q in zip(lo, hi)):
        raise QfError("E_DOMAIN", "a lower bound is above its upper bound", "lower")

    k = len(e_rows)
    e_mat = np.asarray(e_rows, dtype=float).reshape(k, n)
    e_rhs = np.asarray(e_vals, dtype=float)
    e_cut = 0.0
    if k:
        if k > n:
            raise QfError("E_SINGULAR", "more equalities than instruments", "eq_matrix")
        s = np.linalg.svd(e_mat, compute_uv=False)
        if s[-1] <= THRESHOLD * s[0]:
            raise QfError("E_SINGULAR", "the equality rows are dependent", "eq_matrix")
        e_cut = THRESHOLD * float(s[0])

    big_b, d = _root_form(a, b, weights, ridge)
    sb = np.linalg.svd(big_b, compute_uv=False)
    h_largest_sq = float(sb[0]) ** 2
    cut_sq = THRESHOLD * h_largest_sq
    x_p, z = _equality_split(e_mat, e_rhs, e_cut)
    rank = 0
    if k < n:
        sz = np.linalg.svd(big_b @ z, compute_uv=False)
        rank = int((sz * sz > cut_sq).sum())
        if rank < n - k and singular == "ERROR":
            raise QfError("E_SINGULAR", "the hedge has no unique solution", "a")

    qp = _Qp(big_b, d, e_mat, e_rhs, lo, hi, h_largest_sq, e_cut)
    if not bounded:
        y, _ = _lstsq_min_norm(big_b @ z, big_b @ x_p + d, cut_sq)
        x = x_p + z @ y
    else:
        if k:
            start = _phase_one(e_mat, e_rhs, lo, hi)
            if start is None:
                raise QfError("E_INFEASIBLE", "no position meets the equalities and the bounds")
        else:
            start = np.zeros(n)
        for j in range(n):
            if lo[j] is not None:
                start[j] = max(start[j], lo[j])
            if hi[j] is not None:
                start[j] = min(start[j], hi[j])
        x = qp.active_set(start)
    xs = _zs(x)
    residual, value = _objective(a, b, weights, ridge, xs)
    return {"x": xs, "residual": _zs(residual), "objective": _z(value), "rank": rank}


def qp_solve(a: Matrix, b: Floats, weights: Floats, ridge: float = 0.0,
             eq_matrix: Matrix | None = None, eq_rhs: Floats | None = None,
             lower: Bounds | None = None, upper: Bounds | None = None,
             singular: str = "ERROR") -> dict[str, Any]:
    """`hedge.qp.solve`: minimise sum w_i (A x + b)_i^2 + ridge |x|^2 subject to E x = e and
    lower <= x <= upper (a None bound is absent). `singular` is "ERROR" or "MIN_NORM" (I-5).

    Returns {x, residual, objective, rank}. Errors: E_INPUT (shapes, MIN_NORM with a bound),
    E_DOMAIN, E_SINGULAR (equality rank, reduced Hessian), E_INFEASIBLE, in that order."""
    return _qp_core(a, b, weights, ridge, eq_matrix, eq_rhs, lower, upper, singular)


def _round_half_away(v: float) -> int:
    whole = math.floor(abs(v))
    return int(math.copysign(whole + (1 if abs(v) - whole >= 0.5 else 0), v))


def _integer_search(r: NDArray, n0: NDArray, box: list[tuple[int | None, int | None]],
                    incumbent: list[int]) -> list[list[int]]:
    """Every integer point of the box with |R (n - n0)|^2 at most the incumbent's distance (plus a
    relative slack), by Fincke-Pohst enumeration on the upper-triangular R [FP85]."""
    dim = len(n0)

    def dist(v: Sequence[int]) -> float:
        return float(np.sum((r @ (np.asarray(v, dtype=float) - n0)) ** 2))

    best = dist(incumbent)
    found: list[tuple[float, list[int]]] = []
    point = [0] * dim
    visited = 0

    def bound() -> float:
        return best * (1 + 1e-9) + 1e-300

    def descend(i: int, partial: float) -> None:
        nonlocal best, visited
        shift = sum(r[i, j] * (point[j] - n0[j]) for j in range(i + 1, dim))
        centre = n0[i] - shift / r[i, i]
        room = bound() - partial
        if room < 0:
            return
        half = math.sqrt(room) / abs(r[i, i])
        lo, hi = math.ceil(centre - half), math.floor(centre + half)
        lo_box, hi_box = box[i]
        if lo_box is not None:
            lo = max(lo, lo_box)
        if hi_box is not None:
            hi = min(hi, hi_box)
        for v in range(lo, hi + 1):
            visited += 1
            if visited > _MAX_ENUMERATED:
                raise QfError("E_NO_CONVERGENCE", "the integer search is too large")
            point[i] = v
            term = (r[i, i] * (v - n0[i]) + shift) ** 2
            if partial + term > bound():
                continue
            if i == 0:
                total = partial + term
                found.append((total, point.copy()))
                best = min(best, total)
            else:
                descend(i - 1, partial + term)

    descend(dim - 1, 0.0)
    return [p for t, p in found if t <= bound()]


def integer_solve(a: Matrix, b: Floats, weights: Floats, lot_sizes: Floats, ridge: float = 0.0,
                  lower_lots: Sequence[int | None] | None = None,
                  upper_lots: Sequence[int | None] | None = None) -> dict[str, Any]:
    """`hedge.integer.solve`: x_j = lot_sizes_j n_j with n integer, minimising the
    `hedge.qp.solve` objective within optional lot bounds. Ties follow ruling I-7.

    Returns {lots, x, residual, objective, continuous_objective, rounding_cost}."""
    _, n = _shape(a, b, weights)
    if len(lot_sizes) != n:
        raise QfError("E_INPUT", "lot_sizes must have one entry per instrument", "lot_sizes")
    for key, bound in (("lower_lots", lower_lots), ("upper_lots", upper_lots)):
        if bound is not None and len(bound) != n:
            raise QfError("E_INPUT", f"{key} must have one entry per instrument", key)
    lo = list(lower_lots) if lower_lots is not None else [None] * n
    hi = list(upper_lots) if upper_lots is not None else [None] * n
    _check_weights_ridge(weights, ridge)
    if any(s <= 0 for s in lot_sizes):
        raise QfError("E_DOMAIN", "lot sizes must be positive", "lot_sizes")
    if any(p is not None and q is not None and p > q for p, q in zip(lo, hi)):
        raise QfError("E_DOMAIN", "a lower lot bound is above its upper bound", "lower_lots")

    big_b, d = _root_form(a, b, weights, ridge)
    lots_b = big_b * np.asarray(lot_sizes, dtype=float)[None, :]
    s = np.linalg.svd(lots_b, compute_uv=False)
    if int((s * s > THRESHOLD * s[0] ** 2).sum()) < n:
        raise QfError("E_SINGULAR", "the hedge in lot units has no unique solution", "a")

    q, r = np.linalg.qr(lots_b)
    n0 = np.linalg.solve(r, -(q.T @ d))
    box = list(zip(lo, hi))

    def clamp(v: int, j: int) -> int:
        low, high = lo[j], hi[j]
        if low is not None:
            v = max(v, low)
        if high is not None:
            v = min(v, high)
        return v

    def value(v: Sequence[int]) -> float:
        x = [lot_sizes[j] * v[j] for j in range(n)]
        return _objective(a, b, weights, ridge, x)[1]

    incumbent = [clamp(_round_half_away(float(v)), j) for j, v in enumerate(n0)]
    current = value(incumbent)
    improved = True
    while improved:  # one-lot moves: a cheap, tighter starting radius
        improved = False
        for j in range(n):
            for step in (-1, 1):
                trial = incumbent.copy()
                trial[j] = clamp(trial[j] + step, j)
                if trial[j] != incumbent[j]:
                    t = value(trial)
                    if t < current:
                        incumbent, current, improved = trial, t, True
    candidates = _integer_search(r, n0, box, incumbent) or [incumbent]
    scored = [(value(c), c) for c in candidates]
    top = min(v for v, _ in scored)
    tied = [c for v, c in scored if v - top <= THRESHOLD * abs(top)]
    lots = min(tied, key=lambda c: (sum(abs(v) for v in c), c))
    x = [lot_sizes[j] * lots[j] for j in range(n)]
    residual, objective = _objective(a, b, weights, ridge, x)
    relaxed = _qp_core(a, b, weights, ridge, None, None,
                       [None if v is None else v * lot_sizes[j] for j, v in enumerate(lo)],
                       [None if v is None else v * lot_sizes[j] for j, v in enumerate(hi)],
                       "ERROR")["objective"]
    return {"lots": [int(v) for v in lots], "x": _zs(x), "residual": _zs(residual),
            "objective": _z(objective), "continuous_objective": _z(relaxed),
            "rounding_cost": _z(objective - relaxed)}


def _symmetric(s: Matrix, key: str) -> None:
    largest = max((abs(v) for row in s for v in row), default=0.0)
    size = len(s)
    for i in range(size):
        for j in range(i + 1, size):
            if abs(s[i][j] - s[j][i]) > THRESHOLD * largest:
                raise QfError("E_INPUT", f"{key} is not symmetric", key)


def _sample_covariance(series: Sequence[Floats]) -> list[list[float]]:
    count = len(series[0])
    means = [math.fsum(s) / count for s in series]
    centred = [[v - mu for v in s] for s, mu in zip(series, means)]
    return [[math.fsum(p * q for p, q in zip(u, w)) / (count - 1) for w in centred]
            for u in centred]


def minvar_ratio(covariance: Matrix | None = None, exposure_changes: Floats | None = None,
                 hedge_changes: Matrix | None = None) -> dict[str, Any]:
    """`hedge.minvar.ratio`: units held of each hedge instrument, `-S_hh^{-1} S_he`, from a
    covariance (index 0 the position) or from series with divisor T - 1 (I-8).

    Returns {hedge, variance_before, variance_after, effectiveness}."""
    series_given = exposure_changes is not None or hedge_changes is not None
    if (covariance is None) == (not series_given):
        raise QfError("E_INPUT", "give either covariance or the two series", "covariance")
    if covariance is None:
        if exposure_changes is None or hedge_changes is None:
            raise QfError("E_INPUT", "exposure_changes and hedge_changes go together",
                          "hedge_changes")
        k, count = len(hedge_changes), len(exposure_changes)
        if k < 1:
            raise QfError("E_INPUT", "at least one hedge series is needed", "hedge_changes")
        if any(len(s) != count for s in hedge_changes):
            raise QfError("E_INPUT", "the series differ in length", "hedge_changes")
        if count < k + 2:
            raise QfError("E_INPUT", "at least k + 2 observations are needed", "exposure_changes")
        s = _sample_covariance([exposure_changes, *hedge_changes])
    else:
        size = len(covariance)
        if size < 2 or any(len(row) != size for row in covariance):
            raise QfError("E_INPUT", "covariance must be square and at least 2 x 2", "covariance")
        _symmetric(covariance, "covariance")
        s = [list(row) for row in covariance]
    if s[0][0] <= 0:
        raise QfError("E_DOMAIN", "the position has no variance to hedge", "covariance")
    k = len(s) - 1
    s_hh = [[s[i][j] for j in range(1, k + 1)] for i in range(1, k + 1)]
    s_he = [s[i][0] for i in range(1, k + 1)]
    # Cholesky with the pivot rule of check 3.
    largest = max(s_hh[i][i] for i in range(k))
    low = [[0.0] * k for _ in range(k)]
    for j in range(k):
        pivot = s_hh[j][j] - math.fsum(low[j][p] ** 2 for p in range(j))
        if pivot <= THRESHOLD * largest:
            raise QfError("E_SINGULAR", "the hedge instruments are dependent", "covariance")
        low[j][j] = math.sqrt(pivot)
        for i in range(j + 1, k):
            low[i][j] = (s_hh[i][j] - math.fsum(low[i][p] * low[j][p] for p in range(j))) / low[j][j]
    fwd = [0.0] * k
    for i in range(k):
        fwd[i] = (-s_he[i] - math.fsum(low[i][p] * fwd[p] for p in range(i))) / low[i][i]
    hedge = [0.0] * k
    for i in reversed(range(k)):
        hedge[i] = (fwd[i] - math.fsum(low[p][i] * hedge[p] for p in range(i + 1, k))) / low[i][i]
    before = s[0][0]
    after = before + math.fsum(u * v for u, v in zip(s_he, hedge))
    if after < 0:
        raise QfError("E_NOT_POSITIVE_DEFINITE", "the hedged variance is negative", "covariance")
    return {"hedge": _zs(hedge), "variance_before": _z(before), "variance_after": _z(after),
            "effectiveness": _z(1 - after / before)}


GREEKS = ("DELTA", "GAMMA", "VEGA")


def _unit_greeks(spot: float, rate: float, dividend: float, vol: float, kind: str,
                 strike: float | None, expiry: float | None) -> tuple[float, float, float]:
    """(delta, gamma, vega) of one unit under Black-Scholes-Merton; vega per unit volatility."""
    if kind == "UNDERLYING" or strike is None or expiry is None:
        return 1.0, 0.0, 0.0
    root_t = math.sqrt(expiry)
    d1 = (math.log(spot / strike) + (rate - dividend + vol * vol / 2) * expiry) / (vol * root_t)
    carry = math.exp(-dividend * expiry)
    density = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
    if kind == "CALL":
        delta = carry * 0.5 * math.erfc(-d1 / math.sqrt(2))
    else:
        delta = -carry * 0.5 * math.erfc(d1 / math.sqrt(2))
    return delta, carry * density / (spot * vol * root_t), spot * carry * density * root_t


Instrument = tuple[str, float | None, float | None]  # (kind, strike, expiry_years)


def greeks_neutralise(spot: float, rate: float, dividend_yield: float, volatility: float,
                      portfolio: Sequence[tuple[str, float | None, float | None, float]],
                      hedges: Sequence[Instrument], targets: Sequence[str]) -> dict[str, Any]:
    """`hedge.greeks.neutralise`: quantities of the hedges that set the targeted Greeks of the
    book to zero (I-9). Positions are (kind, strike, expiry_years, quantity).

    Returns {quantities, greeks_before, greeks_after}."""
    every: list[Instrument] = [(kind, k, t) for kind, k, t, _ in portfolio] + list(hedges)
    for kind, strike, expiry in every:
        if kind == "UNDERLYING" and (strike is not None or expiry is not None):
            raise QfError("E_INPUT", "the underlying has no strike or expiry", "portfolio")
        if kind != "UNDERLYING" and (strike is None or expiry is None):
            raise QfError("E_INPUT", "an option needs a strike and an expiry", "portfolio")
    if not hedges:
        raise QfError("E_INPUT", "no hedge instruments", "hedges")
    if len(targets) != len(hedges):
        raise QfError("E_INPUT", "one target per hedge instrument (ruling I-9)", "targets")
    if len(set(targets)) != len(targets):
        raise QfError("E_INPUT", "a target is repeated", "targets")
    if spot <= 0:
        raise QfError("E_DOMAIN", "spot must be positive", "spot")
    if volatility <= 0:
        raise QfError("E_DOMAIN", "volatility must be positive", "volatility")
    for kind, strike, expiry in every:
        if kind != "UNDERLYING" and (strike is None or strike <= 0):
            raise QfError("E_DOMAIN", "strikes must be positive", "strike")
        if kind != "UNDERLYING" and (expiry is None or expiry <= 0):
            raise QfError("E_DOMAIN", "expiries must be positive", "expiry_years")

    def greeks(kind: str, strike: float | None, expiry: float | None) -> tuple[float, ...]:
        return _unit_greeks(spot, rate, dividend_yield, volatility, kind, strike, expiry)

    book_terms = [(q, greeks(kind, k, t)) for kind, k, t, q in portfolio]
    before = [math.fsum(q * g[c] for q, g in book_terms) for c in range(3)]
    per_hedge = [greeks(*h) for h in hedges]
    rows = [GREEKS.index(t) for t in targets]
    g = np.array([[per_hedge[j][c] for j in range(len(hedges))] for c in rows])
    s = np.linalg.svd(g, compute_uv=False)
    if s[-1] <= THRESHOLD * s[0]:
        raise QfError("E_SINGULAR", "the hedges cannot set the targets independently", "hedges")
    quantities = np.linalg.solve(g, -np.array([before[c] for c in rows]))
    after = [math.fsum([before[c], *(float(quantities[j]) * per_hedge[j][c]
                                     for j in range(len(hedges)))]) for c in range(3)]

    def named(v: Sequence[float]) -> dict[str, float]:
        return {"delta": _z(v[0]), "gamma": _z(v[1]), "vega": _z(v[2])}

    return {"quantities": _zs(quantities), "greeks_before": named(before),
            "greeks_after": named(after)}


def beta_futures(portfolio_value: float, portfolio_beta: float, target_beta: float,
                 futures_price: float, multiplier: float,
                 rounding: str = "NEAREST") -> dict[str, float]:
    """`hedge.beta.futures`: futures contracts that move the portfolio beta to the target
    [H18 ch. 3]; positive is long. NEAREST rounds half away from zero (I-10)."""
    if portfolio_value <= 0:
        raise QfError("E_DOMAIN", "portfolio_value must be positive", "portfolio_value")
    if futures_price <= 0:
        raise QfError("E_DOMAIN", "futures_price must be positive", "futures_price")
    if multiplier <= 0:
        raise QfError("E_DOMAIN", "multiplier must be positive", "multiplier")
    contracts = (target_beta - portfolio_beta) * portfolio_value / (futures_price * multiplier)
    held = float(_round_half_away(contracts)) if rounding == "NEAREST" else contracts
    after = portfolio_beta + held * futures_price * multiplier / portfolio_value
    return {"contracts": _z(contracts), "contracts_held": _z(held), "beta_after": _z(after)}


def residual_report(a: Matrix, b: Floats, x: Floats, covariance: Matrix) -> dict[str, Any]:
    """`hedge.residual.report`: variance of the residual A x + b under the factor covariance,
    and each factor's Euler contribution r_i (S r)_i (I-11)."""
    m = len(a)
    n = len(a[0]) if m else 0
    if m == 0 or n == 0 or any(len(row) != n for row in a):
        raise QfError("E_INPUT", "a must be a non-empty matrix with rows of one length", "a")
    if len(b) != m:
        raise QfError("E_INPUT", "b must have one entry per row of a", "b")
    if len(x) != n:
        raise QfError("E_INPUT", "x must have one entry per column of a", "x")
    if len(covariance) != m or any(len(row) != m for row in covariance):
        raise QfError("E_INPUT", "covariance must be m x m", "covariance")
    _symmetric(covariance, "covariance")
    eig = np.linalg.eigvalsh(np.asarray(covariance, dtype=float))
    if eig[0] < -THRESHOLD * float(np.abs(eig).max()):
        raise QfError("E_NOT_POSITIVE_DEFINITE", "the covariance has a negative eigenvalue",
                      "covariance")

    def quad(v: Floats) -> tuple[list[float], float]:
        sv = [math.fsum(row[j] * v[j] for j in range(m)) for row in covariance]
        return sv, math.fsum(p * q for p, q in zip(v, sv))

    _, before = quad(b)
    if before <= 0:
        raise QfError("E_DOMAIN", "nothing to hedge: b^T S b is not positive", "b")
    residual = [math.fsum([*(row[j] * x[j] for j in range(n)), v]) for row, v in zip(a, b)]
    s_r, after = quad(residual)
    return {"residual": _zs(residual), "variance_before": _z(before),
            "variance_after": _z(after), "volatility_after": math.sqrt(max(after, 0.0)),
            "effectiveness": _z(1 - after / before),
            "contributions": _zs(r * v for r, v in zip(residual, s_r))}


guard(globals())
