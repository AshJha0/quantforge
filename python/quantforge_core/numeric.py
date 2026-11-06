"""Small numeric helpers shared by the core modules.

The builtin sum() compensates float rounding since Python 3.12. The contract asks for plain sums in
array order, so float sums here go through ordered_sum.
"""
from collections.abc import Iterable, Sequence


def ordered_sum(values: Iterable[float]) -> float:
    total = 0.0
    for v in values:
        total += v
    return total


def thomas(
    lower: Sequence[float], diag: Sequence[float], upper: Sequence[float], rhs: Sequence[float]
) -> list[float]:
    """Solves a tridiagonal system. lower[0] and upper[-1] are not used."""
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
