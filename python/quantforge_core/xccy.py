"""Cross-currency basis and NDFs (specifications/02-curves/cross-currency.md)."""
from collections.abc import Sequence
from datetime import date, timedelta

from . import calendars, curves, schedules
from .conventions import REGISTRY
from .curves import Curve, CurveData
from .errors import QfError
from .numeric import ordered_sum


def _joint(cals: Sequence[str], d: date) -> bool:
    return all(calendars.is_business_day(c, d) for c in cals)


def _mod_following(cals: Sequence[str], d: date) -> date:
    x = d
    while not _joint(cals, x):
        x += timedelta(days=1)
    if x.month != d.month:
        x = d
        while not _joint(cals, x):
            x -= timedelta(days=1)
    return x


def schedule(conventions: Sequence[str], start: date, months: int) -> list[date]:
    """Period ends: start + 3k months, MODIFIED_FOLLOWING on the joint calendar (ruling D17)."""
    cals = [REGISTRY[c]["calendar"] for c in conventions]
    if not _joint(cals, start):
        raise QfError("E_INPUT", "start must be a business day on both calendars", "start")
    if months <= 0 or months % 3:
        raise QfError("E_INPUT", "months must be a positive multiple of 3", "months")
    return [_mod_following(cals, schedules.add_months(start, 3 * k))
            for k in range(1, months // 3 + 1)]


def leg(notional: float, start: date, ends: Sequence[date], p: Curve, d: Curve,
        spread: float) -> float:
    starts = [start, *ends[:-1]]
    coupons = ordered_sum(
        ((p.discount(s) / p.discount(e) - 1) + spread * (e - s).days / 360) * d.discount(e)
        for s, e in zip(starts, ends, strict=True))
    return notional * (coupons + d.discount(ends[-1]) - d.discount(start))


def bootstrap(
    domestic: CurveData, foreign_projection: CurveData, dom_conv: str, for_conv: str,
    start: date, quotes: Sequence[tuple[int, float]], interpolation: str,
) -> tuple[CurveData, float]:
    curves.build(domestic)
    p = curves.build(foreign_projection)
    if not quotes:
        raise QfError("E_INPUT", "no quotes", "quotes")
    tables = [schedule((dom_conv, for_conv), start, m) for m, _ in quotes]
    if any(b[0] <= a[0] for a, b in zip(quotes, quotes[1:], strict=False)):
        raise QfError("E_INPUT", "months must be strictly increasing", "quotes")
    pillars = [ends[-1] for ends in tables]
    models: list[curves.Model] = [
        lambda c, ends=ends, m=m: leg(1.0, start, ends, p, c, m)
        for ends, (_, m) in zip(tables, quotes, strict=True)
    ]
    as_of = domestic.as_of
    factors, error = curves.solve_pillars(as_of, interpolation, pillars, models,
                                          [0.0] * len(quotes))
    curves.check_solved(error)
    return CurveData(as_of, interpolation, tuple(pillars), tuple(factors)), error


def pv(
    domestic: CurveData, foreign_projection: CurveData, foreign_discount: CurveData,
    spot: float, start: date, months: int, notional: float, spread: float, side: str,
) -> tuple[float, float, float]:
    """Returns (foreign_leg, domestic_leg, pv)."""
    dd, pf, df = (curves.build(x) for x in (domestic, foreign_projection, foreign_discount))
    ends = schedule(("SOFR", "ESTR"), start, months)
    foreign = leg(notional, start, ends, pf, df, spread)
    dom = leg(notional * spot, start, ends, dd, dd, 0.0)
    sign = 1 if side == "RECEIVE_FOREIGN" else -1
    return foreign, dom, sign * (spot * foreign - dom)


def ndf_pv(
    usd: CurveData, offshore: CurveData, spot: float, fixing_date: date, payment: date,
    strike: float, notional: float, side: str, fixing: float | None,
) -> tuple[float, float]:
    """Returns (pv, forward)."""
    u, o = curves.build(usd), curves.build(offshore)
    if payment < fixing_date:
        raise QfError("E_DATE_ORDER", "payment_date is before fixing_date", "payment_date")
    if fixing is None and fixing_date <= u.as_of:
        raise QfError("E_INPUT", "a past fixing must be given", "fixing")
    if spot <= 0 or strike <= 0 or (fixing is not None and fixing <= 0):
        raise QfError("E_DOMAIN", "spot, fixing and strike must be positive")
    forward = fixing if fixing is not None else spot * u.discount(payment) / o.discount(payment)
    sign = 1 if side == "BUY" else -1
    return sign * notional * (1 - strike / forward) * u.discount(payment), forward
