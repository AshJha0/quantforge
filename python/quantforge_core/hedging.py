"""Hedge solve and spread cost (specifications/08-hedging/stage-b-hedges.md).

min |A x + b|_W^2 + lambda sum c_i |x_i|. With G = A^T W A and h = A^T W b, coordinate descent finds
the sign pattern, and one linear solve on that pattern then gives x exactly.
"""
import math
from collections.abc import Sequence

from .errors import QfError
from .finite import guard
from .linalg import lu_solve
from .numeric import ordered_sum

Floats = Sequence[float]
_SWEEPS = 200_000
_POLISH_EVERY = 20


def _soft(v: float, limit: float) -> float:
    return math.copysign(max(abs(v) - limit, 0.0), v)


def _exact_on_pattern(
    g: Sequence[Sequence[float]], h: Sequence[float], penalty: Sequence[float], x: list[float],
) -> list[float] | None:
    """Solves on the current support and signs. None if the conditions fail there."""
    n = len(x)
    support = [i for i in range(n) if x[i] != 0]
    result = [0.0] * n
    if support:
        a = [[g[i][j] for j in support] for i in support]
        rhs = [-h[i] - math.copysign(penalty[i], x[i]) for i in support]
        for i, v in zip(support, lu_solve(a, rhs), strict=True):
            if v * x[i] <= 0:
                return None
            result[i] = v
    for i in range(n):
        slope = h[i] + math.fsum(g[i][j] * result[j] for j in range(n))
        if result[i] == 0 and abs(slope) > penalty[i] * (1 + 1e-12) + 1e-12 * abs(h[i]):
            return None
    return result


def solve(
    a: Sequence[Floats], b: Floats, weights: Floats, costs: Floats, lam: float
) -> tuple[list[float], list[float], float]:
    """Returns (x, residual, objective)."""
    rows = len(a)
    n = len(a[0]) if rows else 0
    if (
        rows == 0 or n == 0 or any(len(r) != n for r in a)
        or len(b) != rows or len(weights) != rows or len(costs) != n
    ):
        raise QfError("E_INPUT", "a, b, weights and costs do not fit together")
    if any(w <= 0 for w in weights):
        raise QfError("E_DOMAIN", "weights must be positive", "weights")
    if any(c < 0 for c in costs):
        raise QfError("E_DOMAIN", "costs must not be negative", "costs")
    if lam < 0:
        raise QfError("E_DOMAIN", "lambda must not be negative", "lambda")

    g = [
        [math.fsum(weights[k] * a[k][i] * a[k][j] for k in range(rows)) for j in range(n)]
        for i in range(n)
    ]
    h = [math.fsum(weights[k] * a[k][i] * b[k] for k in range(rows)) for i in range(n)]
    largest = max(abs(v) for row in g for v in row)
    x = lu_solve(g, [-v for v in h], 1e-12 * largest)
    penalty = [lam * c / 2 for c in costs]

    exact = None
    if not any(penalty):
        exact = x
    else:
        for sweep in range(1, _SWEEPS + 1):
            for i in range(n):
                rest = h[i] + math.fsum(g[i][j] * x[j] for j in range(n) if j != i)
                x[i] = _soft(-rest, penalty[i]) / g[i][i]
            if sweep % _POLISH_EVERY == 0:
                exact = _exact_on_pattern(g, h, penalty, x)
                if exact is not None:
                    break
        if exact is None:
            raise QfError("E_NO_CONVERGENCE", "the hedge solve did not settle")

    residual = [
        ordered_sum(row[j] * exact[j] for j in range(n)) + v
        for row, v in zip(a, b, strict=True)
    ]
    objective = ordered_sum(
        w * r * r for w, r in zip(weights, residual, strict=True)
    ) + lam * ordered_sum(c * abs(v) for c, v in zip(costs, exact, strict=True))
    return exact, residual, objective


def spread_cost(quantities: Floats, half_spreads: Floats) -> float:
    if len(quantities) != len(half_spreads):
        raise QfError("E_INPUT", "quantities and half_spreads differ in length")
    if any(s < 0 for s in half_spreads):
        raise QfError("E_DOMAIN", "half_spreads must not be negative", "half_spreads")
    return ordered_sum(abs(q) * s for q, s in zip(quantities, half_spreads, strict=True))


guard(globals())
