"""Rates sensitivities, by bump and rebuild (specifications/06-risk/rates-sensitivities.md)."""
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from . import curves, ois
from .curves import Curve
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum
from .ois import OisTrade, Quote

BP = 1e-4


@dataclass(frozen=True)
class BumpedCurves:
    """Rebuilt once, then shared by every trade priced on them."""

    parallel: tuple[Curve, Curve]
    keys: list[tuple[Curve, Curve]]


def bump_curves(
    convention: str, as_of: date, quotes: Sequence[Quote], interpolation: str
) -> BumpedCurves:
    return _bump_curves(convention, as_of, tuple(quotes), interpolation)


@lru_cache(maxsize=8)
def _bump_curves(
    convention: str, as_of: date, quotes: tuple[Quote, ...], interpolation: str
) -> BumpedCurves:
    """A pure function of its inputs, so a book of trades on one quote set rebuilds the 2n + 2
    curves once. No number changes (BT7): a cached curve is the curve a rebuild would give."""
    mids = [q.mid for q in quotes]

    def rebuilt(shifts: Sequence[float]) -> Curve:
        moved = [Quote(q.tenor, m + s) for q, m, s in zip(quotes, mids, shifts, strict=True)]
        return curves.build(ois.bootstrap(convention, as_of, moved, interpolation)[0])

    n = len(quotes)
    keys = [
        (rebuilt([BP if k == j else 0.0 for k in range(n)]),
         rebuilt([-BP if k == j else 0.0 for k in range(n)]))
        for j in range(n)
    ]
    return BumpedCurves((rebuilt([BP] * n), rebuilt([-BP] * n)), keys)


def dv01_on(trade: OisTrade, as_of: date, bumped: BumpedCurves) -> tuple[float, list[float]]:
    ps = ois.periods(trade.convention, as_of, trade.tenor)

    def difference(pair: tuple[Curve, Curve]) -> float:
        return (ois.trade_pv(trade, ps, pair[0])[0] - ois.trade_pv(trade, ps, pair[1])[0]) / 2

    return difference(bumped.parallel), [difference(pair) for pair in bumped.keys]


def dv01(
    as_of: date, quotes: Sequence[Quote], interpolation: str, trade: OisTrade
) -> tuple[float, list[float]]:
    return dv01_on(trade, as_of, bump_curves(trade.convention, as_of, quotes, interpolation))


def cashflows(flows: Sequence[tuple[float, float]], y: float) -> tuple[float, float, float]:
    """flows are (t, amount). Returns (pv, duration, convexity)."""
    if not flows:
        raise QfError("E_INPUT", "need at least 1 cashflow", "cashflows")
    if any(t < 0 for t, _ in flows):
        raise QfError("E_DOMAIN", "t must not be negative", "cashflows")
    values = [(t, c * math.exp(-y * t)) for t, c in flows]
    pv = ordered_sum(v for _, v in values)
    if pv == 0:
        raise QfError("E_DOMAIN", "pv is zero", "cashflows")
    return (
        pv,
        ordered_sum(t * v for t, v in values) / pv,
        ordered_sum(t * t * v for t, v in values) / pv,
    )


guard(globals())
