"""Sobol points (specifications/01-core/sobol.md)."""
from collections.abc import Iterator
from functools import lru_cache

from ._sobol_data import DIRECTION_DATA
from .errors import QfError

MAX_DIMENSIONS = 64
_BITS = 32
_SCALE = 2.0**-32


@lru_cache(maxsize=MAX_DIMENSIONS)
def _directions(d: int) -> tuple[int, ...]:
    """v[1..32] for dimension d (from 1). Index 0 is unused."""
    if d == 1:
        return (0, *(1 << (_BITS - k) for k in range(1, _BITS + 1)))
    s, a, m = DIRECTION_DATA[d - 1]
    v = [0] * (_BITS + 1)
    for k in range(1, _BITS + 1):
        if k <= s:
            v[k] = m[k - 1] << (_BITS - k)
        else:
            v[k] = v[k - s] ^ (v[k - s] >> s)
            for j in range(1, s):
                if (a >> (s - 1 - j)) & 1:
                    v[k] ^= v[k - j]
    return tuple(v)


def iter_points(dimensions: int, count: int, skip: int = 0) -> Iterator[list[float]]:
    """Yields the points of indices skip+1 .. skip+count."""
    tables = [_directions(d) for d in range(1, dimensions + 1)]
    gray = skip ^ (skip >> 1)
    x = [0] * dimensions
    for bit in range(_BITS):
        if (gray >> bit) & 1:
            for d, v in enumerate(tables):
                x[d] ^= v[bit + 1]
    for i in range(skip, skip + count):
        c = (~i & (i + 1)).bit_length()
        for d, v in enumerate(tables):
            x[d] ^= v[c]
        yield [xi * _SCALE for xi in x]


def points(dimensions: int, count: int, skip: int = 0) -> list[list[float]]:
    if not 1 <= dimensions <= MAX_DIMENSIONS:
        raise QfError("E_INPUT", "dimensions must be 1 to 64", "dimensions")
    if not 1 <= count <= 1_000_000:
        raise QfError("E_INPUT", "count must be 1 to 1000000", "count")
    if skip < 0 or skip + count >= 1 << 32:
        raise QfError("E_INPUT", "indices must stay below 2^32", "skip")
    return list(iter_points(dimensions, count, skip))
