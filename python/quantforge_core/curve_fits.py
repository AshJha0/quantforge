"""Regularised and outlier-robust curve fits (specifications/03-calibration/curve-fits.md)."""

import itertools
import math
from collections.abc import Sequence

from . import linalg
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum


def smooth(
    knots: Sequence[float],
    maturities: Sequence[float],
    zero_rates: Sequence[float],
    lam: float,
    weights: Sequence[float] | None = None,
) -> tuple[list[float], list[float], float]:
    """Returns (forwards, fitted, objective)."""
    w = list(weights) if weights is not None else [1.0] * len(maturities)
    if not maturities or len(maturities) != len(zero_rates) or len(w) != len(maturities):
        raise QfError("E_INPUT", "maturities, zero_rates and weights need one equal length")
    if not knots or knots[0] <= 0 or any(b <= a for a, b in itertools.pairwise(knots)):
        raise QfError("E_INPUT", "knots must be positive and increasing", "knots")
    if lam < 0 or any(v < 0 for v in w) or any(m <= 0 for m in maturities):
        raise QfError("E_DOMAIN", "lambda, weights and maturities are out of domain")
    if any(m > knots[-1] for m in maturities):
        raise QfError("E_INPUT", "a maturity is past the last knot", "maturities")
    n = len(knots)
    edges = [0.0, *knots]
    rows = [[max(0.0, min(m, edges[k + 1]) - edges[k]) / m for k in range(n)] for m in maturities]
    a = [
        [ordered_sum(wj * r[p] * r[q] for wj, r in zip(w, rows, strict=True)) for q in range(n)]
        for p in range(n)
    ]
    for k in range(n - 1):
        a[k][k] += lam
        a[k + 1][k + 1] += lam
        a[k][k + 1] -= lam
        a[k + 1][k] -= lam
    rhs = [
        ordered_sum(wj * r[p] * y for wj, r, y in zip(w, rows, zero_rates, strict=True))
        for p in range(n)
    ]
    f = linalg.lu_solve(a, rhs)
    fitted = [ordered_sum(c * x for c, x in zip(r, f, strict=True)) for r in rows]
    objective = ordered_sum(
        wj * (z - y) ** 2 for wj, z, y in zip(w, fitted, zero_rates, strict=True)
    ) + lam * ordered_sum((f[k + 1] - f[k]) ** 2 for k in range(n - 1))
    return f, fitted, objective


def _basis(m: float, tau: float) -> list[float]:
    x = m / tau
    e = -math.expm1(-x) / x
    return [1.0, e, e - math.exp(-x)]


RCOND_MIN = 1e-12


def basis_rcond(xs: Sequence[Sequence[float]]) -> float:
    """Ruling D38b: reciprocal 1-norm condition number of the basis Gram matrix X^T X, columns
    scaled to unit diagonal, from the explicit 3x3 inverse (adjugate over determinant). The
    operation order is fixed so the four languages give the same bits. 0 when det <= 0."""
    g = [[0.0] * 3 for _ in range(3)]
    for x in xs:
        for p in range(3):
            for q in range(3):
                g[p][q] += x[p] * x[q]
    s = [1.0 / math.sqrt(g[p][p]) for p in range(3)]
    a = [[g[p][q] * s[p] * s[q] for q in range(3)] for p in range(3)]
    c = [
        [
            a[1][1] * a[2][2] - a[1][2] * a[2][1],
            a[1][2] * a[2][0] - a[1][0] * a[2][2],
            a[1][0] * a[2][1] - a[1][1] * a[2][0],
        ],
        [
            a[0][2] * a[2][1] - a[0][1] * a[2][2],
            a[0][0] * a[2][2] - a[0][2] * a[2][0],
            a[0][1] * a[2][0] - a[0][0] * a[2][1],
        ],
        [
            a[0][1] * a[1][2] - a[0][2] * a[1][1],
            a[0][2] * a[1][0] - a[0][0] * a[1][2],
            a[0][0] * a[1][1] - a[0][1] * a[1][0],
        ],
    ]
    det = a[0][0] * c[0][0] + a[0][1] * c[0][1] + a[0][2] * c[0][2]
    if not det > 0.0:
        return 0.0
    norm_a = max(abs(a[0][q]) + abs(a[1][q]) + abs(a[2][q]) for q in range(3))
    # Column q of the inverse is row q of the cofactor matrix over det.
    norm_inv = max((abs(c[q][0]) + abs(c[q][1]) + abs(c[q][2])) / det for q in range(3))
    return 1.0 / (norm_a * norm_inv)


ITERATIONS = 1000


def robust(
    maturities: Sequence[float], zero_rates: Sequence[float], tau: float, delta: float
) -> tuple[list[float], list[float], list[int], float]:
    """Huber Nelson-Siegel. Returns (betas, residuals, outliers, objective).

    An active-set method on the dual finds the outlier set and signs exactly; the betas then
    solve the inlier/outlier normal equations."""
    if len(maturities) != len(zero_rates) or len(maturities) < 3:
        raise QfError("E_INPUT", "need at least 3 points of equal length")
    if tau <= 0 or delta <= 0 or any(m <= 0 for m in maturities):
        raise QfError("E_DOMAIN", "tau, delta and maturities must be positive")
    if len(set(maturities)) < 3:
        raise QfError("E_SINGULAR", "three distinct maturities are needed to fix three betas")
    xs = [_basis(m, tau) for m in maturities]
    if not basis_rcond(xs) >= RCOND_MIN:
        raise QfError(
            "E_SINGULAR", "the Nelson-Siegel basis is singular to working precision (D38b)"
        )
    ys = list(zero_rates)

    def weighted(w: Sequence[float], shift: Sequence[float]) -> list[float]:
        a = [
            [ordered_sum(wj * x[p] * x[q] for wj, x in zip(w, xs, strict=True)) for q in range(3)]
            for p in range(3)
        ]
        b = [
            ordered_sum(
                wj * x[p] * y - s * x[p] for wj, x, y, s in zip(w, xs, ys, shift, strict=True)
            )
            for p in range(3)
        ]
        return linalg.lu_solve(a, b)

    def residuals(beta: Sequence[float]) -> list[float]:
        return [
            ordered_sum(b * v for b, v in zip(beta, x, strict=True)) - y
            for x, y in zip(xs, ys, strict=True)
        ]

    # Primal active-set method on the dual problem (Nocedal and Wright, Numerical Optimization,
    # 2nd ed., algorithm 16.3). Huber's rho is the Moreau envelope of delta |.|, so the dual is
    #   minimise ||theta||^2 / 2 + y^T theta  subject to  X^T theta = 0, |theta_j| <= delta,
    # strictly convex with the solution theta_j = clip(r_j, -delta, delta), and the betas are the
    # multipliers of X^T theta = 0. With the bound set W (theta_j = s_j delta) fixed, the
    # subproblem's optimality conditions are the inlier/outlier normal equations below, and the
    # free theta_j equal the residuals. Start: theta = 0, nothing bound (least squares). A step
    # toward the subproblem's minimiser stops at the first free theta_j to reach +-delta, which
    # joins W; at a subproblem minimum the bound j with the most negative multiplier
    # s_j r_j - delta leaves W; when none is negative the point is optimal. The dual objective
    # falls at every step, so no working set repeats and the method ends in finitely many steps.
    # Rows at three distinct maturities stay free throughout: with exactly that many the free
    # theta are fixed by X^T theta = 0, so no step can bind another.
    n = len(ys)
    theta = [0.0] * n
    bound = [0] * n  # s_j: 0 free, +1 or -1 bound at s_j delta
    for _ in range(ITERATIONS):
        beta = weighted([1.0 if s == 0 else 0.0 for s in bound], [s * delta for s in bound])
        r = residuals(beta)
        alpha, block = 1.0, -1
        for j in range(n):
            p = r[j] - theta[j]
            if bound[j] != 0 or p == 0.0:
                continue
            limit = ((delta if p > 0 else -delta) - theta[j]) / p
            if limit < alpha:
                alpha, block = limit, j
        if block >= 0:
            for j in range(n):
                if bound[j] == 0:
                    theta[j] += alpha * (r[j] - theta[j])
            bound[block] = 1 if r[block] - theta[block] > 0 else -1
            theta[block] = bound[block] * delta
            continue
        theta = [delta * s if s != 0 else v for s, v in zip(bound, r, strict=True)]
        worst, leave = 0.0, -1
        for j in range(n):
            if bound[j] != 0 and bound[j] * r[j] - delta < worst:
                worst, leave = bound[j] * r[j] - delta, j
        if leave < 0:
            break
        bound[leave] = 0
    else:
        raise QfError("E_NO_CONVERGENCE", "the Huber fit did not settle")
    r = residuals(beta)
    outliers = [j for j, v in enumerate(r) if abs(v) > delta]
    objective = ordered_sum(
        v * v / 2 if abs(v) <= delta else delta * abs(v) - delta * delta / 2 for v in r
    )
    return beta, r, outliers, objective


guard(globals())
