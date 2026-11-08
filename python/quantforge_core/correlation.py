"""Stage E, E6: correlation validation, nearest correlation, implied correlation and dispersion.

Spec: specifications/06-risk/correlation.md, rulings E-B18 to E-B21 in
specifications/stage-e-rulings-b.md. NumPy is used for symmetric eigen-decompositions only.
"""
from collections.abc import Sequence

lazy import numpy as np

from .errors import QfError
from .numeric import ordered_sum

Matrix = Sequence[Sequence[float]]
PSD_FLOOR = -1e-10
_MAX_SWEEPS = 100_000


def _input(message: str, field: str | None = None) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _square(m: Matrix) -> int:
    n = len(m)
    if n == 0 or any(len(row) != n for row in m):
        raise _input("matrix must be square and not empty", "matrix")
    return n


def _symmetric(m: Matrix) -> bool:
    return all(m[i][j] == m[j][i] for i in range(len(m)) for j in range(i))


def validate(m: Matrix) -> dict[str, object]:
    n = _square(m)
    a = np.array(m, dtype=float)
    smallest = float(np.linalg.eigvalsh((a + a.T) / 2)[0])
    out: dict[str, object] = {
        "symmetric": _symmetric(m),
        "unit_diagonal": all(m[i][i] == 1 for i in range(n)),
        "in_range": all(-1 <= x <= 1 for row in m for x in row),
        "min_eigenvalue": smallest,
        "psd": smallest >= PSD_FLOOR,
    }
    out["valid"] = all(out[k] for k in ("symmetric", "unit_diagonal", "in_range", "psd"))
    return out


def nearest(m: Matrix) -> tuple[list[list[float]], float]:
    """Higham's alternating projections with Dykstra's correction, until Y stops changing."""
    _square(m)
    if not _symmetric(m):
        raise _input("matrix must be symmetric", "matrix")
    target = np.array(m, dtype=float)
    y = target.copy()
    correction = np.zeros_like(y)
    for _ in range(_MAX_SWEEPS):
        r = y - correction
        w, v = np.linalg.eigh(r)
        x = (v * np.maximum(w, 0.0)) @ v.T
        x = (x + x.T) / 2
        correction = x - r
        previous = y
        y = x.copy()
        np.fill_diagonal(y, 1.0)
        if float(np.abs(y - previous).max()) <= 1e-15:
            break
    else:
        raise QfError("E_NO_CONVERGENCE", "the nearest correlation iteration did not settle",
                      "matrix")
    return y.tolist(), float(np.sqrt(((y - target) ** 2).sum()))


def _implied(weights: Sequence[float], vols: Sequence[float], index_vol: float) -> float:
    n = len(weights)
    own = ordered_sum(w * w * s * s for w, s in zip(weights, vols, strict=True))
    cross = ordered_sum(weights[i] * weights[j] * vols[i] * vols[j]
                        for i in range(n) for j in range(n) if i != j)
    return (index_vol * index_vol - own) / cross


def _names(weights: Sequence[float], *lists: Sequence[float]) -> None:
    if len(weights) < 2 or any(len(x) != len(weights) for x in lists):
        raise _input("at least two names, with lists of one length", "weights")


def implied(weights: Sequence[float], vols: Sequence[float], index_vol: float) -> float:
    _names(weights, vols)
    if any(s <= 0 for s in vols) or index_vol <= 0:
        raise _domain("a vol is not above 0", "vols")
    return _implied(weights, vols, index_vol)


def dispersion(weights: Sequence[float], strikes: Sequence[float], index_strike: float,
               realized: Sequence[float], index_realized: float,
               vega_notional: float) -> dict[str, object]:
    _names(weights, strikes, realized)
    if any(k <= 0 for k in strikes) or index_strike <= 0:
        raise _domain("a vol strike is not above 0", "vol_strikes")
    if any(s <= 0 for s in realized) or index_realized <= 0:
        raise _domain("a realised vol is not above 0", "realized_vols")
    legs = [vega_notional * w / (2 * k) for w, k in zip(weights, strikes, strict=True)]
    index_leg = vega_notional / (2 * index_strike)
    pnl = ordered_sum(n * (s * s - k * k) for n, s, k in zip(legs, realized, strikes,
                                                              strict=True))
    pnl -= index_leg * (index_realized * index_realized - index_strike * index_strike)
    return {
        "pnl": pnl,
        "implied_correlation": _implied(weights, strikes, index_strike),
        "realized_correlation": _implied(weights, realized, index_realized),
        "constituent_variance_notionals": legs,
        "index_variance_notional": index_leg,
    }
