"""Projection curves, FRAs, swaps, basis (specifications/02-curves/projection-and-fra.md)."""
import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from . import calendars, curves, daycount, schedules
from .conventions import REGISTRY
from .curves import Curve, CurveData
from .errors import QfError
from .numeric import ordered_sum
from .ois import valuation
from .schedules import Period

_MF = "MODIFIED_FOLLOWING"


@dataclass(frozen=True)
class ProjectionQuote:
    kind: str
    months: int
    rate: float


@dataclass(frozen=True)
class SwapTrade:
    index: str
    tenor_months: int
    fixed_rate: float
    notional: float
    side: str


@dataclass(frozen=True)
class FraTrade:
    index: str
    start: date
    fixed_rate: float
    notional: float
    side: str


def _spot(index: str, as_of: date) -> date:
    c = REGISTRY[index]
    return calendars.add_business_days(c["calendar"], as_of, c["spot_lag"])


def _plus_months(index: str, d: date, months: int) -> date:
    return calendars.adjust(REGISTRY[index]["calendar"], schedules.add_months(d, months), _MF)


def _schedule(index: str, spot: date, months: int, frequency: int) -> list[Period]:
    end = schedules.add_months(spot, months)
    return schedules.generate(spot, end, frequency, REGISTRY[index]["calendar"], False, 0)


def _fixed_periods(index: str, spot: date, months: int) -> list[Period]:
    return _schedule(index, spot, months, REGISTRY[index]["fixed_months"])


def _float_periods(index: str, spot: date, months: int) -> list[Period]:
    return _schedule(index, spot, months, REGISTRY[index]["months"])


def _alpha(index: str, s: date, e: date) -> float:
    return daycount.year_fraction(REGISTRY[index]["day_count"], s, e)


def _swap_legs(
    index: str, fixed: Sequence[Period], floating: Sequence[Period], discount: Curve,
    projection: Curve,
) -> tuple[float, float]:
    day_count = REGISTRY[index]["fixed_day_count"]
    annuity = ordered_sum(
        daycount.year_fraction(day_count, p.start, p.end) * discount.discount(p.end)
        for p in fixed
    )
    leg = ordered_sum(
        (projection.discount(p.start) / projection.discount(p.end) - 1) * discount.discount(p.end)
        for p in floating
    )
    return annuity, leg


def bootstrap(
    discount_data: CurveData, index: str, as_of: date, quotes: Sequence[ProjectionQuote],
    interpolation: str,
) -> tuple[CurveData, float]:
    discount = curves.build(discount_data)
    if not quotes:
        raise QfError("E_INPUT", "no quotes", "quotes")
    spot = _spot(index, as_of)
    pillars: list[date] = []
    models: list[curves.Model] = []
    for q in quotes:
        if q.kind == "SWAP":
            fixed = _fixed_periods(index, spot, q.months)
            floating = _float_periods(index, spot, q.months)
            pillars.append(fixed[-1].end)

            def swap_rate(p: Curve, fixed: list[Period] = fixed,
                          floating: list[Period] = floating) -> float:
                annuity, leg = _swap_legs(index, fixed, floating, discount, p)
                return leg / annuity

            models.append(swap_rate)
        else:
            s = spot if q.kind == "DEPOSIT" else _plus_months(index, spot, q.months)
            e = _plus_months(index, spot if q.kind == "DEPOSIT" else s,
                             q.months if q.kind == "DEPOSIT" else REGISTRY[index]["months"])
            pillars.append(e)
            alpha = _alpha(index, s, e)

            def simple_rate(p: Curve, s: date = s, e: date = e, alpha: float = alpha) -> float:
                return (p.discount(s) / p.discount(e) - 1) / alpha

            models.append(simple_rate)
    if any(b <= a for a, b in itertools.pairwise(pillars)):
        raise QfError("E_INPUT", "quotes are not in pillar order", "quotes")
    targets = [q.rate for q in quotes]
    factors, error = curves.solve_pillars(as_of, interpolation, pillars, models, targets)
    curves.check_solved(error)
    return CurveData(as_of, interpolation, tuple(pillars), tuple(factors)), error


def swap_pv(
    discount_data: CurveData, projection_data: CurveData, trade: SwapTrade,
    snapshot_id: str | None = None,
) -> tuple[dict[str, object], float]:
    discount, projection = curves.build(discount_data), curves.build(projection_data)
    spot = _spot(trade.index, discount.as_of)
    fixed = _fixed_periods(trade.index, spot, trade.tenor_months)
    floating = _float_periods(trade.index, spot, trade.tenor_months)
    annuity, leg = _swap_legs(trade.index, fixed, floating, discount, projection)
    sign = 1 if trade.side == "PAY" else -1
    value = sign * trade.notional * (leg - trade.fixed_rate * annuity)
    currency = REGISTRY[trade.index]["currency"]
    result = valuation(value, currency, "SWAP_DISCOUNTING", snapshot_id, trade.index,
                       discount.as_of)
    return result, leg / annuity


def fra_pv(
    discount_data: CurveData, projection_data: CurveData, trade: FraTrade,
    snapshot_id: str | None = None,
) -> tuple[dict[str, object], float]:
    discount, projection = curves.build(discount_data), curves.build(projection_data)
    index = trade.index
    e = _plus_months(index, trade.start, REGISTRY[index]["months"])
    alpha = _alpha(index, trade.start, e)
    rate = (projection.discount(trade.start) / projection.discount(e) - 1) / alpha
    sign = 1 if trade.side == "PAY" else -1
    value = (
        sign * trade.notional * alpha * (rate - trade.fixed_rate) / (1 + alpha * rate)
        * discount.discount(trade.start)
    )
    currency = REGISTRY[index]["currency"]
    return valuation(value, currency, "FRA_DISCOUNTING", snapshot_id, index, discount.as_of), rate


def basis_spread(
    discount_data: CurveData, projection_data: CurveData, index: str, tenor_months: int
) -> float:
    d, p = curves.build(discount_data), curves.build(projection_data)
    ps = _float_periods(index, _spot(index, d.as_of), tenor_months)
    top = ordered_sum(
        (p.discount(x.start) / p.discount(x.end) - d.discount(x.start) / d.discount(x.end))
        * d.discount(x.end)
        for x in ps
    )
    return top / ordered_sum(_alpha(index, x.start, x.end) * d.discount(x.end) for x in ps)
