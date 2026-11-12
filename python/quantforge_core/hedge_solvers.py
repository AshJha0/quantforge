"""Hedge solvers (specifications/08-hedging/hedge-solvers.md, rulings I-1 to I-14).

Constrained least squares, integer lots, minimum variance, Greek neutralisation, equity beta
futures and the residual risk report. Stage B's `hedging.solve` is unchanged.

The least-squares problems are kept in their square-root form: with `B = [W^(1/2) A; ridge^(1/2) I]`
and `d = [W^(1/2) b; 0]`, `f(x) = |B x + d|^2` and `H = B^T B`. Working on `B` (SVD, QR) instead of
`H` keeps the conditioning at that of `B`, so problems whose weights span many decades stay
accurate. The singularity rule I-3 (an eigenvalue of `Z^T H Z` at most `1e-12` times the largest
eigenvalue of `H`) is applied to squared singular values, which are those eigenvalues.
"""
import itertools
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
_MAX_ENUMERATED = 1_000_000  # integer search points or nodes before E_NO_CONVERGENCE (R6-6.1)
_ITER_SLOPE, _ITER_BASE = 10, 100  # active-set and sign-state loops: 10 n + 100 (R6-6.1)


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


def _scaled_form(big_b: NDArray, e_mat: NDArray,
                 e_rhs: NDArray) -> tuple[NDArray, NDArray, NDArray, NDArray] | None:
    """Ruling R6-6.2: Jacobi scaling `D_jj = 1/sqrt(H_jj)` (H = B^T B), equality rows at unit
    norm, then the I-3 test on `Z^T D H D Z` against the largest eigenvalue of `D H D`.
    Returns (D, B D, x~_p, Z) or None when singular."""
    norms = np.sqrt((big_b * big_b).sum(axis=0))
    if not np.all(norms > 0):
        return None
    col = 1.0 / norms
    bs = big_b * col[None, :]
    es, rs = e_mat * col[None, :], e_rhs
    if es.shape[0]:
        rows = np.sqrt((es * es).sum(axis=1))
        es, rs = es / rows[:, None], e_rhs / rows
        se = np.linalg.svd(es, compute_uv=False)
        if se[-1] <= THRESHOLD * se[0]:
            return None
    xs_p, zs = _equality_split(es, rs, 0.0)
    top = float(np.linalg.svd(bs, compute_uv=False)[0]) ** 2
    sz = np.linalg.svd(bs @ zs, compute_uv=False)
    if zs.shape[1] and (len(sz) < zs.shape[1] or float(sz[-1]) ** 2 <= THRESHOLD * top):
        return None
    return col, bs, xs_p, zs


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
        for _ in range(_ITER_SLOPE * n + _ITER_BASE):
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


def _simplex(a_eq: NDArray, b_eq: NDArray, cost: NDArray) -> NDArray | None:
    """argmin cost z subject to a_eq z = b_eq, z >= 0, or None when no z is feasible.

    Two-phase dense tableau simplex with Bland's rule. Used for the wave 4a feasible start: the
    least-margin point that meets the equalities and the bounds."""
    rows, cols = a_eq.shape
    tab = np.zeros((rows + 1, cols + rows + 1))
    tab[:rows, :cols] = a_eq
    tab[:rows, -1] = b_eq
    negative = b_eq < 0
    tab[:rows][negative] *= -1.0
    tab[:rows, cols:cols + rows] = np.eye(rows)
    basis = list(range(cols, cols + rows))
    scale = max(1.0, float(np.abs(tab[:rows]).max(initial=0.0)))
    tol = 1e-11 * scale

    def pivot(r: int, c: int) -> None:
        tab[r] /= tab[r, c]
        for other in range(rows + 1):
            if other != r and tab[other, c] != 0.0:
                tab[other] -= tab[other, c] * tab[r]
        basis[r] = c

    def run(allowed: int) -> None:
        for _ in range(50 * (rows + cols) + 100):
            entering = next((c for c in range(allowed) if tab[-1, c] < -tol), None)
            if entering is None:
                return
            best: tuple[float, int, int] | None = None
            for r in range(rows):
                if tab[r, entering] > tol:
                    key = (tab[r, -1] / tab[r, entering], basis[r], r)
                    if best is None or key < best:
                        best = key
            if best is None:
                raise QfError("E_NO_CONVERGENCE", "the margin search is unbounded")
            pivot(best[2], entering)
        raise QfError("E_NO_CONVERGENCE", "the margin search did not settle")

    tab[-1, :] = -tab[:rows].sum(axis=0)
    tab[-1, cols:cols + rows] = 0.0
    run(cols + rows)
    if -tab[-1, -1] > 1e-9 * scale:
        return None
    for r in range(rows):  # move degenerate artificials out where a structural pivot exists
        if basis[r] >= cols:
            c = next((c for c in range(cols) if abs(tab[r, c]) > tol), None)
            if c is not None:
                pivot(r, c)
    tab[-1, :] = 0.0
    tab[-1, :cols] = cost
    for r, c in enumerate(basis):
        if c < cols and tab[-1, c] != 0.0:
            tab[-1] -= tab[-1, c] * tab[r]
    run(cols)  # artificials never re-enter
    z = np.zeros(cols)
    for r, c in enumerate(basis):
        if c < cols:
            z[c] = tab[r, -1]
    return z


def _least_margin(e_mat: NDArray, e_rhs: NDArray, lower: Bounds, upper: Bounds,
                  rates: NDArray) -> NDArray | None:
    """The point of least margin sum m_j |x_j| with E x = e inside the bounds, or None.
    Variables x = p - q with p, q >= 0; each finite bound is a row with a slack."""
    k, n = e_mat.shape
    rows: list[NDArray] = []
    rhs: list[float] = []
    bound_rows = [(j, v, 1.0) for j, v in enumerate(upper) if v is not None] + [
        (j, v, -1.0) for j, v in enumerate(lower) if v is not None]
    cols = 2 * n + len(bound_rows)
    for r in range(k):
        row = np.zeros(cols)
        row[:n], row[n:2 * n] = e_mat[r], -e_mat[r]
        rows.append(row)
        rhs.append(float(e_rhs[r]))
    for s, (j, v, sign) in enumerate(bound_rows):  # x_j + t = u, or x_j - t = l
        row = np.zeros(cols)
        row[j], row[n + j], row[2 * n + s] = 1.0, -1.0, sign
        rows.append(row)
        rhs.append(v)
    if not rows:
        return np.zeros(n)
    cost = np.concatenate([rates, rates, np.zeros(len(bound_rows))])
    z = _simplex(np.vstack(rows), np.asarray(rhs), cost)
    if z is None:
        return None
    return z[:n] - z[n:2 * n]


class _CostQp:
    """`hedge.qp.solve` with the wave 4a costs and margin (rulings I-24 to I-27).

    Inside each sign orthant of the instruments with a kink (a spread cost or a margin rate) the
    objective is the wave 1 one plus a linear term `c_j s_j x_j`, and the margin is one linear
    inequality `sum m_j s_j x_j <= limit`. Each orthant problem is solved by a primal active-set
    method. At a position sitting at 0, the subgradient test either confirms the optimum or flips
    that instrument's orthant; a flip lowers the objective strictly, so the search ends."""

    def __init__(self, big_b: NDArray, d: NDArray, e_mat: NDArray, e_rhs: NDArray,
                 lower: Bounds, upper: Bounds, h_largest_sq: float, spread: NDArray,
                 rates: NDArray | None, limit: float):
        self.big_b, self.d, self.e_mat, self.e_rhs = big_b, d, e_mat, e_rhs
        self.lower, self.upper = lower, upper
        self.cut_sq = THRESHOLD * h_largest_sq
        self.spread = spread
        self.n = big_b.shape[1]
        self.rates = rates if rates is not None else np.zeros(self.n)
        self.limit = limit if rates is not None else math.inf
        self.kinked = [bool(spread[j] > 0 or self.rates[j] > 0) for j in range(self.n)]

    def _orthant_bounds(self, signs: list[int]) -> tuple[list[float | None], list[float | None]]:
        lo, hi = list(self.lower), list(self.upper)
        for j, s in enumerate(signs):
            low, high = lo[j], hi[j]
            if s > 0:
                lo[j] = 0.0 if low is None else max(low, 0.0)
            elif s < 0:
                hi[j] = 0.0 if high is None else min(high, 0.0)
        return lo, hi

    def _step(self, free: list[int], x: NDArray, lin: NDArray, row: NDArray | None) -> NDArray:
        """The minimiser over the free variables, the others held, on the working rows: E and,
        when the margin is active, the margin row."""
        out = x.copy()
        if not free:
            return out
        fixed = [j for j in range(self.n) if j not in set(free)]
        mats = [self.e_mat[:, free]]
        rhs = [self.e_rhs - self.e_mat[:, fixed] @ x[fixed]]
        if row is not None:
            mats.append(row[free][None, :])
            rhs.append(np.array([self.limit - row[fixed] @ x[fixed]]))
        e_s, e_v = np.vstack(mats), np.concatenate(rhs)
        largest = float(np.linalg.svd(e_s, compute_uv=False)[0]) if e_s.size else 0.0
        x_p, z = _equality_split(e_s, e_v, THRESHOLD * largest)
        if z.shape[1]:
            bs = self.big_b[:, free]
            r = bs @ x_p + self.d + self.big_b[:, fixed] @ x[fixed]
            u, s, vt = np.linalg.svd(bs @ z, full_matrices=False)
            keep = s * s > self.cut_sq
            lz = vt[keep] @ (z.T @ lin[free])
            y = -vt[keep].T @ ((u[:, keep].T @ r) / s[keep] + lz / (2 * s[keep] ** 2))
            out[free] = x_p + z @ y
        else:
            out[free] = x_p
        return out

    def _orthant(self, x: NDArray, signs: list[int]) -> tuple[NDArray, NDArray, float]:
        """Active-set solve inside one orthant from a feasible x. Returns (x, the smooth gradient
        plus E^T lambda + mu a, the margin multiplier mu)."""
        lo, hi = self._orthant_bounds(signs)
        sign = np.asarray(signs, dtype=float)
        lin, a_row = self.spread * sign, self.rates * sign
        margin = math.isfinite(self.limit)
        work: dict[int, str] = {}
        for j in range(self.n):
            low, high = lo[j], hi[j]
            if low is not None and low == high:
                work[j], x[j] = "F", low
            elif low is not None and x[j] <= low:
                work[j], x[j] = "L", low
            elif high is not None and x[j] >= high:
                work[j], x[j] = "U", high
        margin_on = margin and float(a_row @ x) >= self.limit
        scale0 = max(float(np.abs(2.0 * (self.big_b.T @ self.d)).max(initial=0.0)),
                     float(np.abs(lin).max(initial=0.0)), 1e-300)
        k = self.e_mat.shape[0]
        for _ in range(_ITER_SLOPE * self.n + _ITER_BASE):
            free = [j for j in range(self.n) if j not in work]
            target = self._step(free, x, lin, a_row if margin_on else None)
            p = target - x
            alpha, block, side = 1.0, -1, ""
            for j in free:
                low, high = lo[j], hi[j]
                if p[j] < 0 and low is not None:
                    t = max((low - x[j]) / p[j], 0.0)
                    if t < alpha:
                        alpha, block, side = t, j, "L"
                elif p[j] > 0 and high is not None:
                    t = max((high - x[j]) / p[j], 0.0)
                    if t < alpha:
                        alpha, block, side = t, j, "U"
            if margin and not margin_on:
                rise = float(a_row @ p)
                if rise > 0:
                    t = max((self.limit - float(a_row @ x)) / rise, 0.0)
                    if t < alpha:
                        alpha, block = t, -2
            if block != -1:
                x = x + alpha * p
                if block == -2:
                    margin_on = True
                else:
                    work[block] = side
                    x[block] = lo[block] if side == "L" else hi[block]
                continue
            x = target
            g = 2.0 * (self.big_b.T @ (self.big_b @ x + self.d)) + lin
            full = np.vstack([self.e_mat] + ([a_row[None, :]] if margin_on else []))
            mults = (np.linalg.lstsq(full[:, free].T, -g[free], rcond=None)[0]
                     if free and len(full) else np.zeros(len(full)))
            r = g + full.T @ mults if len(full) else g
            mu = float(mults[k]) if margin_on else 0.0
            scale = max(scale0, float(np.abs(g).max(initial=0.0)))
            worst, drop = -1e-11 * scale, -1
            for j, s in work.items():
                v = r[j] if s == "L" else -r[j] if s == "U" else math.inf
                if v < worst:
                    worst, drop = v, j
            if margin_on and mu < worst:
                drop = -2
            if drop == -1:
                return x, r - lin - mu * a_row, mu
            if drop == -2:
                margin_on = False
            else:
                del work[drop]
        raise QfError("E_NO_CONVERGENCE", "the active-set search did not settle")

    def solve(self, start: NDArray) -> NDArray:
        """The minimiser from a feasible start (costs, margin, bounds and equalities)."""
        x = start.copy()
        signs: list[int] = []
        for j in range(self.n):
            high = self.upper[j]
            if not self.kinked[j]:
                signs.append(0)
            elif x[j] > 0 or (x[j] == 0 and (high is None or high > 0)):
                signs.append(1)
            else:
                signs.append(-1)
        for _ in range(_ITER_SLOPE * self.n + _ITER_BASE):
            x, smooth, mu = self._orthant(x, signs)
            scale = max(float(np.abs(smooth).max(initial=0.0)),
                        float(self.spread.max(initial=0.0)), 1e-300)
            worst, flip = 1e-11 * scale, -1
            for j in range(self.n):
                if not self.kinked[j] or x[j] != 0.0:
                    continue
                allowance = self.spread[j] + mu * self.rates[j]
                low, high = self.lower[j], self.upper[j]
                if signs[j] > 0 and (low is None or low < 0):
                    excess = smooth[j] - allowance  # f falls if x_j goes below 0
                elif signs[j] < 0 and (high is None or high > 0):
                    excess = -smooth[j] - allowance  # f falls if x_j goes above 0
                else:
                    continue
                if excess > worst:
                    worst, flip = excess, j
            if flip < 0:
                return x
            signs[flip] = -signs[flip]
        raise QfError("E_NO_CONVERGENCE", "the sign search did not settle")


def _qp_core(a: Matrix, b: Floats, weights: Floats, ridge: float, eq_matrix: Matrix | None,
             eq_rhs: Floats | None, lower: Bounds | None, upper: Bounds | None,
             singular: str, costs: Costs | None = None) -> dict[str, Any]:
    _, n = _shape(a, b, weights)
    if (eq_matrix is None) != (eq_rhs is None):
        raise QfError("E_INPUT", "eq_matrix and eq_rhs go together", "eq_matrix")
    if eq_matrix is not None and not eq_matrix:  # R6-11.13
        raise QfError("E_INPUT", "an empty eq_matrix: leave out both keys", "eq_matrix")
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
    if costs is not None:
        costs.check(n, singular)

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
    if costs is not None and costs.impact is not None and costs.cost_weight > 0:
        extra = np.diag(np.sqrt(costs.cost_weight * np.asarray(costs.impact, dtype=float)))
        big_b = np.vstack([big_b, extra])
        d = np.concatenate([d, np.zeros(n)])
    sb = np.linalg.svd(big_b, compute_uv=False)
    h_largest_sq = float(sb[0]) ** 2
    cut_sq = THRESHOLD * h_largest_sq
    x_p, z = _equality_split(e_mat, e_rhs, e_cut)
    rank = 0
    scaled = None
    if k < n and singular == "ERROR":
        scaled = _scaled_form(big_b, e_mat, e_rhs)
        if scaled is None:
            raise QfError("E_SINGULAR", "the hedge has no unique solution", "a")
        rank = n - k
    elif k < n:
        sz = np.linalg.svd(big_b @ z, compute_uv=False)
        rank = int((sz * sz > cut_sq).sum())
    qp = _Qp(big_b, d, e_mat, e_rhs, lo, hi, h_largest_sq, e_cut)
    if costs is not None and costs.kinked():
        x = _costed(costs, big_b, d, e_mat, e_rhs, lo, hi, h_largest_sq, n)
    elif not bounded and scaled is not None:
        col, bs, xs_p, zs = scaled  # R6-6.2: solve in the scaled variables, x = D x~
        y, _ = _lstsq_min_norm(bs @ zs, bs @ xs_p + d, 0.0)
        x = col * (xs_p + zs @ y)
    elif not bounded:
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
    out: dict[str, Any] = {"x": xs, "residual": _zs(residual), "objective": _z(value),
                           "rank": rank}
    if costs is not None:
        cost = costs.cost(xs)
        out["risk"] = out["objective"]
        out["cost"] = _z(cost)
        out["objective"] = _z(value + costs.cost_weight * cost)
        if costs.margin_rates is not None:
            out["margin"] = _z(math.fsum(m * abs(v) for m, v in zip(costs.margin_rates, xs)))
    return out


def _costed(costs: Costs, big_b: NDArray, d: NDArray, e_mat: NDArray, e_rhs: NDArray,
            lo: Bounds, hi: Bounds, h_largest_sq: float, n: int) -> NDArray:
    """The wave 4a solve: a feasible start of least margin, then the orthant search."""
    spread = costs.cost_weight * np.asarray(costs.half_spreads or [0.0] * n, dtype=float)
    rates = (np.asarray(costs.margin_rates, dtype=float) if costs.margin_rates is not None
             else None)
    limit = costs.margin_limit if costs.margin_limit is not None else math.inf
    if rates is not None:
        start = _least_margin(e_mat, e_rhs, lo, hi, rates)
        if start is None or math.fsum(abs(float(m * v)) for m, v in zip(rates, start)) > (
                limit * (1 + 1e-9) + 1e-12):
            raise QfError("E_INFEASIBLE", "no position meets the constraints and the margin limit")
    elif e_mat.shape[0]:
        start = _phase_one(e_mat, e_rhs, lo, hi)
        if start is None:
            raise QfError("E_INFEASIBLE", "no position meets the equalities and the bounds")
    else:
        start = np.zeros(n)
    for j in range(n):
        low, high = lo[j], hi[j]
        if low is not None:
            start[j] = max(start[j], low)
        if high is not None:
            start[j] = min(start[j], high)
    return _CostQp(big_b, d, e_mat, e_rhs, lo, hi, h_largest_sq, spread, rates,
                   limit).solve(start)


class Costs:
    """The wave 4a optional inputs of `hedge.qp.solve` (rulings I-24 to I-27)."""

    def __init__(self, half_spreads: Floats | None = None, impact: Floats | None = None,
                 cost_weight: float | None = None, margin_rates: Floats | None = None,
                 margin_limit: float | None = None):
        self.half_spreads, self.impact = half_spreads, impact
        self.cost_weight = 1.0 if cost_weight is None else cost_weight
        self.margin_rates, self.margin_limit = margin_rates, margin_limit

    def given(self) -> bool:
        """True when any wave 4a input is present (ruling I-27)."""
        return any(v is not None for v in (self.half_spreads, self.impact, self.margin_rates,
                                           self.margin_limit)) or self.cost_weight != 1.0

    def check(self, n: int, singular: str) -> None:
        """Ruling I-25: lengths and the margin pair, MIN_NORM, then signs."""
        for key, v in (("half_spreads", self.half_spreads), ("impact", self.impact),
                       ("margin_rates", self.margin_rates)):
            if v is not None and len(v) != n:
                raise QfError("E_INPUT", f"{key} must have one entry per instrument", key)
        if (self.margin_rates is None) != (self.margin_limit is None):
            raise QfError("E_INPUT", "margin_rates and margin_limit go together", "margin_rates")
        if singular == "MIN_NORM":
            raise QfError("E_INPUT", "MIN_NORM takes no cost or margin input", "singular")
        for key, v in (("half_spreads", self.half_spreads), ("impact", self.impact),
                       ("margin_rates", self.margin_rates)):
            if v is not None and any(e < 0 for e in v):
                raise QfError("E_DOMAIN", f"{key} must not be negative", key)
        if self.cost_weight < 0:
            raise QfError("E_DOMAIN", "cost_weight must not be negative", "cost_weight")
        if self.margin_limit is not None and self.margin_limit < 0:
            raise QfError("E_DOMAIN", "margin_limit must not be negative", "margin_limit")

    def kinked(self) -> bool:
        """True when a |x| term is present: a spread cost that counts, or a margin."""
        spread = self.cost_weight > 0 and any(v > 0 for v in self.half_spreads or [])
        return spread or self.margin_rates is not None

    def cost(self, x: Floats) -> float:
        """C(x) = sum half_spreads |x| + impact x^2."""
        spreads = self.half_spreads or [0.0] * len(x)
        impact = self.impact or [0.0] * len(x)
        return math.fsum(h * abs(v) + i * v * v for h, i, v in zip(spreads, impact, x))


def qp_solve(a: Matrix, b: Floats, weights: Floats, ridge: float = 0.0,
             eq_matrix: Matrix | None = None, eq_rhs: Floats | None = None,
             lower: Bounds | None = None, upper: Bounds | None = None,
             singular: str = "ERROR", half_spreads: Floats | None = None,
             impact: Floats | None = None, cost_weight: float | None = None,
             margin_rates: Floats | None = None,
             margin_limit: float | None = None) -> dict[str, Any]:
    """`hedge.qp.solve`: minimise sum w_i (A x + b)_i^2 + ridge |x|^2 subject to E x = e and
    lower <= x <= upper (a None bound is absent). `singular` is "ERROR" or "MIN_NORM" (I-5).

    The optional wave 4a inputs add `cost_weight (sum half_spreads |x| + impact x^2)` to the
    objective (`cost_weight` defaults to 1) and `sum margin_rates |x| <= margin_limit` to the
    constraints (rulings I-24 to I-27).

    Returns {x, residual, objective, rank}, plus `risk`, `cost` and (with margin inputs)
    `margin` when any wave 4a input is given. Errors: E_INPUT (shapes, MIN_NORM with a bound or
    a cost), E_DOMAIN, E_SINGULAR (equality rank, reduced Hessian), E_INFEASIBLE, in that order."""
    extras = (half_spreads, impact, cost_weight, margin_rates, margin_limit)
    costs = Costs(*extras) if any(v is not None for v in extras) else None
    return _qp_core(a, b, weights, ridge, eq_matrix, eq_rhs, lower, upper, singular, costs)


def frontier_solve(a: Matrix, b: Floats, weights: Floats, cost_weights: Floats,
                   ridge: float = 0.0, eq_matrix: Matrix | None = None,
                   eq_rhs: Floats | None = None, lower: Bounds | None = None,
                   upper: Bounds | None = None, singular: str = "ERROR",
                   half_spreads: Floats | None = None, impact: Floats | None = None,
                   margin_rates: Floats | None = None, margin_limit: float | None = None,
                   cost_weight: float | None = None) -> dict[str, Any]:
    """`hedge.frontier.solve`: the costed `hedge.qp.solve` once per cost weight, in order; the
    first error stops it. Returns {points: [{cost_weight, x, risk, cost}]}."""
    if cost_weight is not None:
        raise QfError("E_INPUT", "give cost_weights, not cost_weight", "cost_weight")
    if not cost_weights or any(q <= p for p, q in itertools.pairwise(cost_weights)):
        raise QfError("E_INPUT", "cost_weights must be non-empty and increasing", "cost_weights")
    if half_spreads is None and impact is None:
        raise QfError("E_INPUT", "a frontier needs half_spreads or impact", "half_spreads")
    points = []
    for weight in cost_weights:
        costs = Costs(half_spreads, impact, weight, margin_rates, margin_limit)
        out = _qp_core(a, b, weights, ridge, eq_matrix, eq_rhs, lower, upper, singular, costs)
        points.append({"cost_weight": _z(weight), "x": out["x"], "risk": out["risk"],
                       "cost": out["cost"]})
    return {"points": points}


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

    relaxed_out = _qp_core(a, b, weights, ridge, None, None,
                           [None if v is None else v * lot_sizes[j] for j, v in enumerate(lo)],
                           [None if v is None else v * lot_sizes[j] for j, v in enumerate(hi)],
                           "ERROR")
    if any(abs(v / s_j) > 2.0 ** 52 for v, s_j in zip(relaxed_out["x"], lot_sizes)):
        raise QfError("E_LIMIT", "a lot count is beyond 2^52 (ruling I-49)", "lot_sizes")
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
    relaxed = relaxed_out["objective"]
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
    # Cholesky of the Jacobi-scaled (correlation) form, lower triangle (R6-6.2, R6-11.7):
    # a negative pivot is E_NOT_POSITIVE_DEFINITE, one at or below 1e-12 is E_SINGULAR.
    for j in range(k):
        if s_hh[j][j] < 0:
            raise QfError("E_NOT_POSITIVE_DEFINITE", "a hedge variance is negative", "covariance")
        if s_hh[j][j] == 0:
            raise QfError("E_SINGULAR", "the hedge instruments are dependent", "covariance")
    scale = [1 / math.sqrt(s_hh[j][j]) for j in range(k)]
    low = [[0.0] * k for _ in range(k)]
    for j in range(k):
        pivot = s_hh[j][j] * scale[j] ** 2 - math.fsum(low[j][p] ** 2 for p in range(j))
        if pivot < 0:
            raise QfError("E_NOT_POSITIVE_DEFINITE", "the hedge covariance is indefinite",
                          "covariance")
        if pivot <= THRESHOLD:
            raise QfError("E_SINGULAR", "the hedge instruments are dependent", "covariance")
        low[j][j] = math.sqrt(pivot)
        for i in range(j + 1, k):
            low[i][j] = (s_hh[i][j] * scale[i] * scale[j]
                         - math.fsum(low[i][p] * low[j][p] for p in range(j))) / low[j][j]
    fwd = [0.0] * k
    for i in range(k):
        fwd[i] = (-s_he[i] * scale[i] - math.fsum(low[i][p] * fwd[p] for p in range(i))) / low[i][i]
    unit = [0.0] * k
    for i in reversed(range(k)):
        unit[i] = (fwd[i] - math.fsum(low[p][i] * unit[p] for p in range(i + 1, k))) / low[i][i]
    hedge = [u * c for u, c in zip(unit, scale, strict=True)]
    before = s[0][0]
    after = before + math.fsum(u * v for u, v in zip(s_he, hedge))
    if after < -THRESHOLD * before:
        raise QfError("E_NOT_POSITIVE_DEFINITE", "the hedged variance is negative", "covariance")
    after = max(after, 0.0)  # ruling I-44: rounding of a perfect hedge
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
                      portfolio: Sequence[tuple[str, float | None, float | None, float | None]],
                      hedges: Sequence[Instrument], targets: Sequence[str],
                      unexpected: Sequence[str] = ()) -> dict[str, Any]:
    """`hedge.greeks.neutralise`: quantities of the hedges that set the targeted Greeks of the
    book to zero (I-9). Positions are (kind, strike, expiry_years, quantity). `unexpected`
    names keys outside an instrument's fixed set; those, and a missing portfolio `quantity`, are
    E_INPUT (ruling I-41).

    Returns {quantities, greeks_before, greeks_after}."""
    if unexpected:
        raise QfError("E_INPUT", f"{unexpected[0]} is not a key of a Greek instrument (I-41)",
                      unexpected[0])
    if any(q is None for *_, q in portfolio):
        raise QfError("E_INPUT", "a portfolio position needs a quantity (ruling I-41)",
                      "quantity")
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

    book_terms = [(q or 0.0, greeks(kind, k, t)) for kind, k, t, q in portfolio]
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


def select_solve(a: Matrix, b: Floats, weights: Floats, max_instruments: int,
                 ridge: float = 0.0, lower: Bounds | None = None, upper: Bounds | None = None,
                 extra_inputs: Sequence[str] = ()) -> dict[str, Any]:
    """`hedge.select.solve`: the subset of at most `max_instruments` hedge instruments with the
    least `hedge.qp.solve` objective, the others held at 0 (rulings I-33, I-34). Every subset is
    solved; ties within 1e-12 relative go to the smaller subset, then the lexicographically
    smaller index list. `extra_inputs` names given inputs that selection refuses.

    Returns {selected (0-based, ascending), x, residual, objective}."""
    _, n = _shape(a, b, weights)
    for key, bound in (("lower", lower), ("upper", upper)):
        if bound is not None and len(bound) != n:
            raise QfError("E_INPUT", f"{key} must have one entry per instrument", key)
    lo: Bounds = lower if lower is not None else [None] * n
    hi: Bounds = upper if upper is not None else [None] * n
    _check_weights_ridge(weights, ridge)
    if any(p is not None and q is not None and p > q for p, q in zip(lo, hi)):
        raise QfError("E_DOMAIN", "a lower bound is above its upper bound", "lower")
    if not 1 <= max_instruments <= n:
        raise QfError("E_INPUT", "max_instruments must be between 1 and n", "max_instruments")
    if extra_inputs:
        raise QfError("E_INPUT", f"selection takes no {extra_inputs[0]} (ruling I-33)",
                      extra_inputs[0])
    if any((p is not None and p > 0) or (q is not None and q < 0) for p, q in zip(lo, hi)):
        raise QfError("E_DOMAIN", "every bound must admit 0 (ruling I-33)", "lower")
    big_b, _ = _root_form(a, b, weights, ridge)
    sv = np.linalg.svd(big_b, compute_uv=False)
    if int((sv * sv > THRESHOLD * sv[0] ** 2).sum()) < n:
        raise QfError("E_SINGULAR", "the full hedge has no unique solution", "a")

    scored: list[tuple[float, tuple[int, ...], list[float]]] = []
    for size in range(1, max_instruments + 1):
        for subset in itertools.combinations(range(n), size):
            cols = [[row[j] for j in subset] for row in a]
            out = _qp_core(cols, b, weights, ridge, None, None, [lo[j] for j in subset],
                           [hi[j] for j in subset], "ERROR")
            scored.append((out["objective"], subset, out["x"]))
    best = min(v for v, _, _ in scored)
    tied = [t for t in scored if t[0] - best <= THRESHOLD * abs(best)]
    _, chosen, part = min(tied, key=lambda t: (len(t[1]), t[1]))
    x = [0.0] * n
    for j, v in zip(chosen, part):
        x[j] = v
    residual, objective = _objective(a, b, weights, ridge, x)
    return {"selected": list(chosen), "x": x, "residual": _zs(residual),
            "objective": _z(objective)}


def option_hedge_lots(spot: float, rate: float, dividend_yield: float, volatility: float,
                      portfolio: Sequence[tuple[str, float | None, float | None, float | None]],
                      hedges: Sequence[tuple[str, float | None, float | None, float, float]],
                      targets: Sequence[str], max_lots: int,
                      unexpected: Sequence[str] = ()) -> dict[str, Any]:
    """`usecase.option_hedge_lots` (use case 6, ruling R6-11.20): the book's Greeks hedged in
    whole lots by `hedge.integer.solve` with weights `1 / max(1, |b_t|)^2`."""
    if unexpected:
        raise QfError("E_INPUT", f"{unexpected[0]} is not a key of a Greek instrument (I-41)",
                      unexpected[0])
    if not hedges:
        raise QfError("E_INPUT", "no hedge instruments", "hedges")
    if not targets or len(set(targets)) != len(targets):
        raise QfError("E_INPUT", "targets must be a non-empty set", "targets")
    if any(q is None for *_, q in portfolio):
        raise QfError("E_INPUT", "a portfolio position needs a quantity (ruling I-41)",
                      "quantity")
    every: list[Instrument] = ([(kind, k, t) for kind, k, t, _ in portfolio]
                               + [(kind, k, t) for kind, k, t, _, _ in hedges])
    for kind, strike, expiry in every:
        if kind == "UNDERLYING" and (strike is not None or expiry is not None):
            raise QfError("E_INPUT", "the underlying has no strike or expiry", "portfolio")
        if kind != "UNDERLYING" and (strike is None or expiry is None):
            raise QfError("E_INPUT", "an option needs a strike and an expiry", "portfolio")
    if spot <= 0:
        raise QfError("E_DOMAIN", "spot must be positive", "spot")
    if volatility <= 0:
        raise QfError("E_DOMAIN", "volatility must be positive", "volatility")
    for kind, strike, expiry in every:
        if kind != "UNDERLYING" and (strike is None or strike <= 0):
            raise QfError("E_DOMAIN", "strikes must be positive", "strike")
        if kind != "UNDERLYING" and (expiry is None or expiry <= 0):
            raise QfError("E_DOMAIN", "expiries must be positive", "expiry_years")
    for *_, lot, spread in hedges:
        if lot <= 0:
            raise QfError("E_DOMAIN", "lot_size must be positive", "lot_size")
        if spread < 0:
            raise QfError("E_DOMAIN", "half_spread must not be negative", "half_spread")
    if max_lots < 1:
        raise QfError("E_DOMAIN", "max_lots must be at least 1", "max_lots")

    def greeks(kind: str, strike: float | None, expiry: float | None) -> tuple[float, ...]:
        return _unit_greeks(spot, rate, dividend_yield, volatility, kind, strike, expiry)

    before = [math.fsum((q or 0.0) * greeks(kind, k, t)[c] for kind, k, t, q in portfolio)
              for c in range(3)]
    per_lot = [[h[3] * g for g in greeks(h[0], h[1], h[2])] for h in hedges]
    rows = [GREEKS.index(t) for t in targets]
    a = [[per_lot[j][c] for j in range(len(hedges))] for c in rows]
    b = [before[c] for c in rows]
    weights = [1.0 / max(1.0, abs(v)) ** 2 for v in b]
    solved = integer_solve(a, b, weights, [1.0] * len(hedges), 0.0,
                           [-max_lots] * len(hedges), [max_lots] * len(hedges))
    lots = solved["lots"]
    after = [math.fsum([before[c], *(lots[j] * per_lot[j][c] for j in range(len(hedges)))])
             for c in range(3)]
    cost = math.fsum(abs(lots[j]) * h[3] * h[4] for j, h in enumerate(hedges))

    def named(v: Sequence[float]) -> dict[str, float]:
        return {"delta": _z(v[0]), "gamma": _z(v[1]), "vega": _z(v[2])}

    return {"greeks_before": named(before), "lots": lots, "greeks_after": named(after),
            "hedge_cost": _z(cost), "rounding_cost": solved["rounding_cost"]}


guard(globals())
