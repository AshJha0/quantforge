"""Regularised and outlier-robust curve fits (specifications/03-calibration/curve-fits.md)."""
import itertools
import math
from collections.abc import Sequence

from . import linalg
from .errors import QfError
from .numeric import ordered_sum


def smooth(
    knots: Sequence[float], maturities: Sequence[float], zero_rates: Sequence[float],
    lam: float, weights: Sequence[float] | None = None,
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
    rows = [[max(0.0, min(m, edges[k + 1]) - edges[k]) / m for k in range(n)]
            for m in maturities]
    a = [[ordered_sum(wj * r[p] * r[q] for wj, r in zip(w, rows, strict=True))
          for q in range(n)] for p in range(n)]
    for k in range(n - 1):
        a[k][k] += lam
        a[k + 1][k + 1] += lam
        a[k][k + 1] -= lam
        a[k + 1][k] -= lam
    rhs = [ordered_sum(wj * r[p] * y for wj, r, y in zip(w, rows, zero_rates, strict=True))
           for p in range(n)]
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


def robust(
    maturities: Sequence[float], zero_rates: Sequence[float], tau: float, delta: float
) -> tuple[list[float], list[float], list[int], float]:
    """Huber Nelson-Siegel. Returns (betas, residuals, outliers, objective).

    IRLS finds the outlier set; then, with the set and the outliers' signs fixed, the minimum
    solves a linear system exactly. The two steps repeat until the set is consistent."""
    if len(maturities) != len(zero_rates) or len(maturities) < 3:
        raise QfError("E_INPUT", "need at least 3 points of equal length")
    if tau <= 0 or delta <= 0 or any(m <= 0 for m in maturities):
        raise QfError("E_DOMAIN", "tau, delta and maturities must be positive")
    xs = [_basis(m, tau) for m in maturities]
    ys = list(zero_rates)

    def weighted(w: Sequence[float], shift: Sequence[float]) -> list[float]:
        a = [[ordered_sum(wj * x[p] * x[q] for wj, x in zip(w, xs, strict=True))
              for q in range(3)] for p in range(3)]
        b = [ordered_sum(wj * x[p] * y - s * x[p] for wj, x, y, s in zip(w, xs, ys, shift,
                                                                          strict=True))
             for p in range(3)]
        return linalg.lu_solve(a, b)

    def residuals(beta: Sequence[float]) -> list[float]:
        return [ordered_sum(b * v for b, v in zip(beta, x, strict=True)) - y
                for x, y in zip(xs, ys, strict=True)]

    zero = [0.0] * len(ys)
    beta = weighted([1.0] * len(ys), zero)
    signs: list[int] | None = None
    for _ in range(500):
        r = residuals(beta)
        new = [0 if abs(v) <= delta else (1 if v > 0 else -1) for v in r]
        if new == signs:
            break
        signs = new
        # Exact minimiser for this set: inliers by least squares, outliers by their constant pull.
        try:
            exact = weighted([1.0 if s == 0 else 0.0 for s in new], [s * delta for s in new])
        except QfError:
            exact = None
        if exact is not None and [
            0 if abs(v) <= delta else (1 if v > 0 else -1) for v in residuals(exact)
        ] == new:
            beta = exact
            continue
        # Not consistent: take IRLS steps instead, which descend monotonically.
        for _ in range(50):
            r = residuals(beta)
            beta = weighted([1.0 if abs(v) <= delta else delta / abs(v) for v in r], zero)
        signs = None
    else:
        raise QfError("E_NO_CONVERGENCE", "the Huber fit did not settle")
    r = residuals(beta)
    outliers = [j for j, v in enumerate(r) if abs(v) > delta]
    objective = ordered_sum(v * v / 2 if abs(v) <= delta else delta * abs(v) - delta * delta / 2
                            for v in r)
    return beta, r, outliers, objective
