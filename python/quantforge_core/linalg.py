"""Dense linear algebra (specifications/01-core/differentiation-and-linalg.md)."""
import math
from collections.abc import Sequence

from .errors import QfError
from .finite import guard

Matrix = Sequence[Sequence[float]]


def _check_square(a: Matrix) -> int:
    n = len(a)
    if n == 0 or any(len(row) != n for row in a):
        raise QfError("E_INPUT", "the matrix must be square and not empty", "a")
    return n


def _largest(a: Matrix) -> float:
    return max(abs(v) for row in a for v in row)


def _check_symmetric(a: Matrix) -> None:
    limit = 1e-12 * _largest(a)
    for i, row in enumerate(a):
        for j in range(i):
            if abs(row[j] - a[j][i]) > limit:
                raise QfError("E_INPUT", "the matrix is not symmetric", "a")


def lu_solve(a: Matrix, b: Sequence[float], singular_below: float = 0.0) -> list[float]:
    """Gaussian elimination with partial pivoting."""
    n = len(a)
    m = [list(row) for row in a]
    x = list(b)
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(m[i][k]))
        if abs(m[p][k]) <= singular_below:
            raise QfError("E_SINGULAR", "the matrix is singular to working precision", "a")
        if p != k:
            m[k], m[p] = m[p], m[k]
            x[k], x[p] = x[p], x[k]
        for i in range(k + 1, n):
            factor = m[i][k] / m[k][k]
            if factor != 0:
                for j in range(k, n):
                    m[i][j] -= factor * m[k][j]
                x[i] -= factor * x[k]
    for i in range(n - 1, -1, -1):
        total = x[i]
        for j in range(i + 1, n):
            total -= m[i][j] * x[j]
        x[i] = total / m[i][i]
    return x


def solve(a: Matrix, b: Sequence[float]) -> list[float]:
    n = _check_square(a)
    if len(b) != n:
        raise QfError("E_INPUT", "b has the wrong length", "b")
    return lu_solve(a, b, 1e-14 * _largest(a))


def cholesky(a: Matrix) -> list[list[float]]:
    n = _check_square(a)
    _check_symmetric(a)
    low = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            total = a[i][j]
            for k in range(j):
                total -= low[i][k] * low[j][k]
            if i == j:
                if total <= 0:
                    raise QfError("E_NOT_POSITIVE_DEFINITE", f"pivot {i} is not positive", "a")
                low[i][i] = math.sqrt(total)
            else:
                low[i][j] = total / low[j][j]
    return low


def eigen_symmetric(a: Matrix) -> list[float]:
    _check_square(a)
    _check_symmetric(a)
    import numpy  # loaded only here, to keep CLI start-up short

    return [float(v) for v in numpy.linalg.eigvalsh(numpy.array(a, dtype=float))]


guard(globals())
