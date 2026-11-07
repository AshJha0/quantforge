"""Year fractions (specifications/01-core/daycount.md)."""
import calendar as _cal
from datetime import date

from . import calendars
from .errors import QfError, required

FREQUENCIES = (1, 2, 3, 4, 6, 12)
_SIMPLE = {"ACT_360": 360.0, "ACT_365F": 365.0, "ACT_364": 364.0, "ACT_365_25": 365.25}
_THIRTY = (
    "THIRTY_360_BOND", "THIRTY_360_US", "THIRTY_E_360", "THIRTY_E_360_ISDA", "THIRTY_E_PLUS_360",
)
CONVENTIONS = (
    *_SIMPLE, *_THIRTY, "NL_365", "ONE_ONE", "BUS_252",
    "ACT_365L", "ACT_ACT_ISDA", "ACT_ACT_ICMA", "ACT_ACT_AFB",
)


def _year_days(y: int) -> int:
    return 366 if _cal.isleap(y) else 365


def _feb29_closed_open(low: date, high: date) -> int:
    """29 Februaries d with low <= d < high."""
    return sum(
        1
        for y in range(low.year, high.year + 1)
        if _cal.isleap(y) and low <= date(y, 2, 29) < high
    )


def _feb29_open_closed(start: date, end: date) -> int:
    """29 Februaries d with start < d <= end."""
    return sum(
        1
        for y in range(start.year, end.year + 1)
        if _cal.isleap(y) and start < date(y, 2, 29) <= end
    )


def _eofeb(d: date) -> bool:
    return d.month == 2 and d.day == _cal.monthrange(d.year, 2)[1]


def _back(end: date, n: int) -> date | None:
    """end moved back n >= 1 calendar years, under the ACT_ACT_AFB rules. None below year 1."""
    y = end.year - n
    if y < 1:
        return None
    if end.month == 2 and end.day == 28 and _cal.isleap(y):
        return date(y, 2, 29)
    if end.month == 2 and end.day == 29 and not _cal.isleap(y):
        return date(y, 2, 28)
    return date(y, end.month, end.day)


def _afb(start: date, end: date) -> float:
    n = 0
    e = end
    while True:
        previous = _back(end, n + 1)
        if previous is None or previous < start:
            break
        n += 1
        e = previous
    d = 366 if _feb29_closed_open(start, e) else 365
    return n + (e - start).days / d


def _thirty(convention: str, start: date, end: date, termination: date | None) -> float:
    y1, m1, d1 = start.year, start.month, start.day
    y2, m2, d2 = end.year, end.month, end.day
    if convention == "THIRTY_360_BOND":
        if d1 == 31:
            d1 = 30
        if d2 == 31 and d1 == 30:
            d2 = 30
    elif convention == "THIRTY_360_US":
        if _eofeb(start) and _eofeb(end):
            d2 = 30
        if _eofeb(start):
            d1 = 30
        if d2 == 31 and d1 >= 30:
            d2 = 30
        if d1 == 31:
            d1 = 30
    elif convention == "THIRTY_E_360":
        if d1 == 31:
            d1 = 30
        if d2 == 31:
            d2 = 30
    elif convention == "THIRTY_E_360_ISDA":
        if d1 == 31 or _eofeb(start):
            d1 = 30
        if d2 == 31 or (_eofeb(end) and end != termination):
            d2 = 30
    else:
        if d1 == 31:
            d1 = 30
        if d2 == 31:
            d2 = 1
            m2 += 1
    return (360 * (y2 - y1) + 30 * (m2 - m1) + (d2 - d1)) / 360


def _act_act_isda(start: date, end: date) -> float:
    y1, y2 = start.year, end.year
    if y1 == y2:
        return (end - start).days / _year_days(y1)
    head = (date(y1 + 1, 1, 1) - start).days / _year_days(y1)
    tail = (end - date(y2, 1, 1)).days / _year_days(y2)
    return head + (y2 - y1 - 1) + tail


def _required(convention: str, **values: object) -> None:
    for key, value in values.items():
        if value is None:
            raise QfError("E_SCHEMA", f"{convention} needs {key}", key)


def check_conditional(
    convention: str,
    frequency: int | None = None,
    ref_start: date | None = None,
    ref_end: date | None = None,
    termination: date | None = None,
    calendar: str | None = None,
) -> None:
    """Check 1 of the spec: the E_SCHEMA stage."""
    if convention not in CONVENTIONS:
        raise QfError("E_SCHEMA", f"unknown convention {convention}", "convention")
    if convention == "ACT_ACT_ICMA":
        _required(convention, frequency=frequency, ref_start=ref_start, ref_end=ref_end)
    elif convention == "ACT_365L":
        _required(convention, frequency=frequency)
    elif convention == "THIRTY_E_360_ISDA":
        _required(convention, termination=termination)
    elif convention == "BUS_252":
        _required(convention, calendar=calendar)
        calendars.check_calendar(required(calendar, "calendar"))
    if convention in ("ACT_ACT_ICMA", "ACT_365L") and frequency not in FREQUENCIES:
        raise QfError("E_SCHEMA", f"frequency {frequency} is not listed", "frequency")


def year_fraction(
    convention: str,
    start: date,
    end: date,
    frequency: int | None = None,
    ref_start: date | None = None,
    ref_end: date | None = None,
    termination: date | None = None,
    calendar: str | None = None,
) -> float:
    check_conditional(convention, frequency, ref_start, ref_end, termination, calendar)

    if end < start:
        raise QfError("E_DATE_ORDER", "end is before start", "end")
    if convention == "ACT_ACT_ICMA" and (
        required(ref_end, "ref_end") <= required(ref_start, "ref_start")
        or start < required(ref_start, "ref_start") or end > required(ref_end, "ref_end")
    ):
        raise QfError("E_INPUT", "the accrual must lie inside the reference period")

    if convention == "BUS_252":
        return calendars.business_days_between(required(calendar, "calendar"), start, end) / 252
    if start == end:
        return 0.0

    days = (end - start).days
    if convention in _SIMPLE:
        return days / _SIMPLE[convention]
    if convention in _THIRTY:
        return _thirty(convention, start, end, termination)
    if convention == "NL_365":
        return (days - _feb29_open_closed(start, end)) / 365
    if convention == "ONE_ONE":
        return 1.0
    if convention == "ACT_365L":
        if frequency == 1:
            return days / (366 if _feb29_open_closed(start, end) else 365)
        return days / _year_days(end.year)
    if convention == "ACT_ACT_ISDA":
        return _act_act_isda(start, end)
    if convention == "ACT_ACT_ICMA":
        span = (required(ref_end, "ref_end") - required(ref_start, "ref_start")).days
        return days / (required(frequency, "frequency") * span)
    return _afb(start, end)
