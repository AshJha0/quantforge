"""Holiday calendars and business-day rules (specifications/01-core/calendars.md)."""
import calendar as _cal
import re
from datetime import date, timedelta
from functools import lru_cache

from .errors import QfError

CALENDARS = ("GBLO", "EUTA", "USGS")
CONVENTIONS = ("UNADJUSTED", "FOLLOWING", "PRECEDING", "MODIFIED_FOLLOWING", "MODIFIED_PRECEDING")
MIN_YEAR, MAX_YEAR = 2000, 2099
MON, THU, FRI, SAT, SUN = 0, 3, 4, 5, 6
_DAY = timedelta(days=1)
TENOR = re.compile(r"[1-9][0-9]{0,3}[DWMY]")


def check_calendar(name: str) -> None:
    if name not in CALENDARS:
        raise QfError("E_SCHEMA", f"unknown calendar {name}", "calendar")


def check_range(d: date) -> None:
    if not MIN_YEAR <= d.year <= MAX_YEAR:
        raise QfError("E_DATE_RANGE", f"{d} is outside {MIN_YEAR} to {MAX_YEAR}")


def easter_sunday(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = (h + ell - 7 * m + 114) % 31 + 1
    return date(y, month, day)


def _nth_weekday(y: int, month: int, weekday: int, n: int) -> date:
    first = date(y, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(y: int, month: int, weekday: int) -> date:
    last = date(y, month, _cal.monthrange(y, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    """Friday if a Saturday, Monday if a Sunday."""
    if d.weekday() == SAT:
        return d - _DAY
    if d.weekday() == SUN:
        return d + _DAY
    return d


def _gblo(y: int) -> set[date]:
    easter = easter_sunday(y)
    new_year = date(y, 1, 1)
    if new_year.weekday() >= SAT:
        new_year = _nth_weekday(y, 1, MON, 1)
    early_may = date(2020, 5, 8) if y == 2020 else _nth_weekday(y, 5, MON, 1)
    spring = {2002: date(2002, 6, 4), 2012: date(2012, 6, 4), 2022: date(2022, 6, 2)}.get(
        y, _last_weekday(y, 5, MON)
    )
    xmas_weekday = date(y, 12, 25).weekday()
    xmas_days = {SAT: (27, 28), SUN: (26, 27), FRI: (25, 28)}.get(xmas_weekday, (25, 26))
    days = {
        new_year,
        easter - 2 * _DAY,
        easter + _DAY,
        early_may,
        spring,
        _last_weekday(y, 8, MON),
        date(y, 12, xmas_days[0]),
        date(y, 12, xmas_days[1]),
    }
    one_offs = (
        date(2002, 6, 3), date(2011, 4, 29), date(2012, 6, 5),
        date(2022, 6, 3), date(2022, 9, 19), date(2023, 5, 8),
    )
    return days | {d for d in one_offs if d.year == y}


def _euta(y: int) -> set[date]:
    easter = easter_sunday(y)
    days = {
        date(y, 1, 1), easter - 2 * _DAY, easter + _DAY,
        date(y, 5, 1), date(y, 12, 25), date(y, 12, 26),
    }
    if y == 2001:
        days.add(date(2001, 12, 31))
    return days


# Ruling R1-6: Good Fridays with a SIFMA early close are business days.
USGS_GOOD_FRIDAY_OPEN = frozenset({2007, 2010, 2012, 2015, 2021, 2023, 2026})


def good_friday(y: int) -> date:
    return easter_sunday(y) - 2 * _DAY


def _usgs(y: int) -> set[date]:
    days = {
        _nth_weekday(y, 1, MON, 3),
        _nth_weekday(y, 2, MON, 3),
        _last_weekday(y, 5, MON),
        _observed(date(y, 7, 4)),
        _nth_weekday(y, 9, MON, 1),
        _nth_weekday(y, 10, MON, 2),
        _nth_weekday(y, 11, THU, 4),
        _observed(date(y, 12, 25)),
    }
    new_year = date(y, 1, 1)
    days.add(new_year + _DAY if new_year.weekday() == SUN else new_year)
    veterans = date(y, 11, 11)
    days.add(veterans + _DAY if veterans.weekday() == SUN else veterans)
    if y >= 2022:
        days.add(_observed(date(y, 6, 19)))
    if y not in USGS_GOOD_FRIDAY_OPEN:
        days.add(good_friday(y))
    one_offs = (date(2004, 6, 11), date(2012, 10, 30), date(2018, 12, 5))
    return days | {d for d in one_offs if d.year == y}


_RULES = {"GBLO": _gblo, "EUTA": _euta, "USGS": _usgs}


@lru_cache(maxsize=512)
def _holiday_set(name: str, year: int) -> frozenset[date]:
    return frozenset(d for d in _RULES[name](year) if d.weekday() < SAT)


def holidays(name: str, year: int) -> list[date]:
    check_calendar(name)
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise QfError("E_DATE_RANGE", f"{year} is outside {MIN_YEAR} to {MAX_YEAR}", "year")
    return sorted(_holiday_set(name, year))


def is_business_day(name: str, d: date) -> bool:
    check_calendar(name)
    check_range(d)
    return d.weekday() < SAT and d not in _holiday_set(name, d.year)


def _search(name: str, d: date, step: timedelta) -> date:
    while not is_business_day(name, d):
        d += step
    return d


def adjust(name: str, d: date, convention: str) -> date:
    check_calendar(name)
    if convention not in CONVENTIONS:
        raise QfError("E_SCHEMA", f"unknown convention {convention}", "convention")
    check_range(d)
    if convention == "UNADJUSTED":
        return d
    forward = convention in ("FOLLOWING", "MODIFIED_FOLLOWING")
    result = _search(name, d, _DAY if forward else -_DAY)
    if convention.startswith("MODIFIED") and result.month != d.month:
        result = _search(name, d, -_DAY if forward else _DAY)
    return result


def add_business_days(name: str, d: date, days: int) -> date:
    check_calendar(name)
    check_range(d)
    if days == 0:
        return adjust(name, d, "FOLLOWING")
    step = _DAY if days > 0 else -_DAY
    left = abs(days)
    while left:
        d += step
        if is_business_day(name, d):
            left -= 1
    return d


def business_days_between(name: str, start: date, end: date) -> int:
    check_calendar(name)
    check_range(start)
    check_range(end)
    if end < start:
        raise QfError("E_DATE_ORDER", "end is before start", "end")
    count = 0
    d = start
    while d < end:
        if is_business_day(name, d):
            count += 1
        d += _DAY
    return count


def last_business_day(name: str, year: int, month: int) -> date:
    return _search(name, date(year, month, _cal.monthrange(year, month)[1]), -_DAY)


def add_tenor(name: str, d: date, tenor: str, convention: str, end_of_month: bool) -> date:
    check_calendar(name)
    if convention not in CONVENTIONS:
        raise QfError("E_SCHEMA", f"unknown convention {convention}", "convention")
    if TENOR.fullmatch(tenor) is None:
        raise QfError("E_SCHEMA", f"bad tenor {tenor}", "tenor")
    check_range(d)
    n, unit = int(tenor[:-1]), tenor[-1]
    if unit in "DW":
        target = d + timedelta(days=n * (7 if unit == "W" else 1))
        check_range(target)
        return adjust(name, target, convention)
    months = d.year * 12 + (d.month - 1) + n * (12 if unit == "Y" else 1)
    year, month = months // 12, months % 12 + 1
    if year > MAX_YEAR:
        raise QfError("E_DATE_RANGE", f"{tenor} from {d} is after {MAX_YEAR}")
    target_last = _cal.monthrange(year, month)[1]
    if end_of_month:
        if convention == "UNADJUSTED":
            if d.day == _cal.monthrange(d.year, d.month)[1]:
                return date(year, month, target_last)
        elif d >= last_business_day(name, d.year, d.month):
            return last_business_day(name, year, month)
    return adjust(name, date(year, month, min(d.day, target_last)), convention)
