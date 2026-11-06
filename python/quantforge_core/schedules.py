"""Regular schedules with a short first stub (specifications/02-curves/schedules.md)."""
import calendar as _cal
import itertools
from dataclasses import dataclass
from datetime import date

from . import calendars
from .errors import QfError

FREQUENCIES = (1, 2, 3, 4, 6, 12)
_MF = "MODIFIED_FOLLOWING"


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    payment: date


def add_months(d: date, months: int) -> date:
    """Unadjusted, with the day clipped to the month."""
    total = d.year * 12 + d.month - 1 + months
    year, month = total // 12, total % 12 + 1
    if not calendars.MIN_YEAR <= year <= calendars.MAX_YEAR:
        raise QfError("E_DATE_RANGE", f"{months} months from {d} leaves the calendar's years")
    return date(year, month, min(d.day, _cal.monthrange(year, month)[1]))


def generate(
    start: date, end: date, frequency_months: int, calendar: str, end_of_month: bool,
    payment_lag: int,
) -> list[Period]:
    if end <= start:
        raise QfError("E_DATE_ORDER", "end is not after start", "end")
    if payment_lag < 0:
        raise QfError("E_INPUT", "payment_lag must not be negative", "payment_lag")
    unadjusted = []
    k = 0
    d = end
    while d > start:
        unadjusted.append(d)
        k += 1
        d = add_months(end, -k * frequency_months)
    dates = [start]
    for d in reversed(unadjusted):
        if end_of_month:
            adjusted = calendars.last_business_day(calendar, d.year, d.month)
        else:
            adjusted = calendars.adjust(calendar, d, _MF)
        if adjusted > dates[-1]:
            dates.append(adjusted)
    return [
        Period(s, e, _payment(calendar, e, payment_lag))
        for s, e in itertools.pairwise(dates)
    ]


def _payment(calendar: str, end: date, lag: int) -> date:
    return calendars.add_business_days(calendar, end, lag) if lag else end
