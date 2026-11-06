"""FX spot, forwards, swaps and quote-driven basis (specifications/02-curves/fx.md)."""
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from . import calendars, curves, schedules
from .conventions import REGISTRY
from .curves import Curve, CurveData
from .errors import QfError
from .ois import valuation

_DAY = timedelta(days=1)


@dataclass(frozen=True)
class FxMarket:
    pair: str
    spot: float
    as_of: date
    base: CurveData
    quote: CurveData


@dataclass(frozen=True)
class FxForward:
    notional_base: float
    strike: float
    value_date: date
    side: str


@dataclass(frozen=True)
class FxSwap:
    notional_base: float
    near_date: date
    near_rate: float
    far_date: date
    far_rate: float
    far_side: str


def _open_on_all(pair: str, d: date) -> bool:
    return all(calendars.is_business_day(c, d) for c in REGISTRY[pair]["calendars"])


def spot_date(pair: str, trade_date: date) -> date:
    d = trade_date
    left = REGISTRY[pair]["spot_lag"]
    while left:
        d += _DAY
        if _open_on_all(pair, d):
            left -= 1
    return d


class _Built:
    def __init__(self, m: FxMarket):
        if m.spot <= 0:
            raise QfError("E_DOMAIN", "spot must be positive", "spot")
        self.market = m
        self.base: Curve = curves.build(m.base)
        self.quote: Curve = curves.build(m.quote)
        self.sp = spot_date(m.pair, m.as_of)

    def a(self, t: date) -> float:
        return self.base.discount(t) / self.base.discount(self.sp)

    def b(self, t: date) -> float:
        return self.quote.discount(t) / self.quote.discount(self.sp)

    def forward(self, t: date) -> float:
        return self.market.spot * self.a(t) / self.b(t)

    def leg(self, notional: float, strike: float, t: date, sign: int) -> tuple[float, float]:
        f = self.forward(t)
        d = self.quote.discount(t)
        return (sign * notional * (f - strike) * d,
                sign * notional * (f / self.market.spot) * d)


def _sign(side: str) -> int:
    return 1 if side == "BUY" else -1


def outright(m: FxMarket, value_date: date) -> tuple[float, float]:
    built = _Built(m)
    if value_date < built.sp:
        raise QfError("E_DATE_ORDER", "value_date is before the spot date", "value_date")
    f = built.forward(value_date)
    return f, (f - m.spot) / REGISTRY[m.pair]["pip"]


def _value(m: FxMarket, pv: float, model: str) -> dict[str, object]:
    return valuation(pv, REGISTRY[m.pair]["quote"], model, None, m.pair, m.as_of)


def forward_pv(m: FxMarket, trade: FxForward) -> tuple[dict[str, object], float]:
    pv, delta = _Built(m).leg(
        trade.notional_base, trade.strike, trade.value_date, _sign(trade.side)
    )
    return _value(m, pv, "FX_FORWARD_DISCOUNTING"), delta


def swap_pv(m: FxMarket, trade: FxSwap) -> tuple[dict[str, object], float]:
    built = _Built(m)
    sign = _sign(trade.far_side)
    near = built.leg(trade.notional_base, trade.near_rate, trade.near_date, -sign)
    far = built.leg(trade.notional_base, trade.far_rate, trade.far_date, sign)
    return _value(m, near[0] + far[0], "FX_SWAP_DISCOUNTING"), near[1] + far[1]


def implied(m: FxMarket, points: Sequence[tuple[int, float]]) -> list[dict[str, object]]:
    """points are (months, points), in tenor order."""
    built = _Built(m)
    if any(b[0] <= a[0] for a, b in itertools.pairwise(points)):
        raise QfError("E_INPUT", "points are not in tenor order", "points")
    record = REGISTRY[m.pair]
    nodes = []
    for months, value in points:
        t = calendars.adjust(
            record["calendars"][0], schedules.add_months(built.sp, months), "MODIFIED_FOLLOWING"
        )
        while not _open_on_all(m.pair, t):
            t += _DAY
        f = m.spot + value * record["pip"]
        ratio = f / m.spot * built.b(t)
        tau = (t - built.sp).days / 365
        basis = 10000 * (-math.log(ratio) / tau + math.log(built.a(t)) / tau)
        nodes.append({"value_date": t.isoformat(), "implied_ratio": ratio, "basis_bp": basis})
    return nodes
