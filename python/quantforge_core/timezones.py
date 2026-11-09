"""Timezones and cut-off (specifications/01-core/timezone-and-cutoff.md).

Instants and local times are whole seconds since 1970-01-01T00:00:00, the first in UTC and the
second on the local clock. The rules are written here, not read from a timezone database.
"""
from datetime import date, timedelta

from . import _cal, calendars
from .errors import QfError
from .finite import guard

ZONES = ("UTC", "Europe/London", "Europe/Berlin", "America/New_York", "Asia/Tokyo")
MIN_YEAR, MAX_YEAR = 2007, 2037
HOUR = 3600
DAY = 86400
_EPOCH = date(1970, 1, 1).toordinal()
_SUNDAY = 6
_STANDARD = {
    "UTC": 0, "Europe/London": 0, "Europe/Berlin": HOUR,
    "America/New_York": -5 * HOUR, "Asia/Tokyo": 9 * HOUR,
}


def date_seconds(d: date) -> int:
    return (d.toordinal() - _EPOCH) * DAY


def to_date(seconds: int) -> date:
    return date.fromordinal(seconds // DAY + _EPOCH)


def _last_sunday(year: int, month: int) -> date:
    last = date(year, month, _cal.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - _SUNDAY) % 7)


def _nth_sunday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(_SUNDAY - first.weekday()) % 7 + 7 * (n - 1))


def _summer(zone: str, year: int) -> tuple[int, int] | None:
    """Summer time [start, end) as UTC instants, or None."""
    if zone in ("Europe/London", "Europe/Berlin"):
        return (
            date_seconds(_last_sunday(year, 3)) + HOUR,
            date_seconds(_last_sunday(year, 10)) + HOUR,
        )
    if zone == "America/New_York":
        return (
            date_seconds(_nth_sunday(year, 3, 2)) + 7 * HOUR,
            date_seconds(_nth_sunday(year, 11, 1)) + 6 * HOUR,
        )
    return None


def _offset(zone: str, instant: int) -> int:
    summer = _summer(zone, to_date(instant).year)
    if summer and summer[0] <= instant < summer[1]:
        return _STANDARD[zone] + HOUR
    return _STANDARD[zone]


def _check_zone(zone: str) -> None:
    if zone not in ZONES:
        raise QfError("E_SCHEMA", f"unknown zone {zone}", "zone")


def _check_year(seconds: int, what: str) -> None:
    if not MIN_YEAR <= to_date(seconds).year <= MAX_YEAR:
        raise QfError("E_DATE_RANGE", f"{what} is outside {MIN_YEAR} to {MAX_YEAR}", what)


def utc_offset(zone: str, instant: int) -> int:
    _check_zone(zone)
    _check_year(instant, "instant")
    return _offset(zone, instant)


def to_local(zone: str, instant: int) -> int:
    return instant + utc_offset(zone, instant)


def to_instant(zone: str, local: int, overlap: str | None = None) -> int:
    _check_zone(zone)
    if overlap not in (None, "EARLIER", "LATER"):
        raise QfError("E_SCHEMA", f"bad overlap {overlap}", "overlap")
    _check_year(local, "local")
    standard = _STANDARD[zone]
    candidates = sorted(
        {
            local - offset
            for offset in (standard, standard + HOUR)
            if _offset(zone, local - offset) == offset
        }
    )
    if not candidates:
        raise QfError("E_NONEXISTENT_LOCAL_TIME", "the local time falls in a gap", "local")
    if len(candidates) == 2 and overlap is None:
        raise QfError("E_AMBIGUOUS_LOCAL_TIME", "the local time falls in an overlap", "local")
    return candidates[-1] if overlap == "LATER" else candidates[0]


def business_date(instant: int, zone: str, cutoff_seconds: int, calendar: str) -> date:
    _check_zone(zone)
    calendars.check_calendar(calendar)
    local = to_local(zone, instant)
    d = to_date(local)
    if local % DAY >= cutoff_seconds:
        d += timedelta(days=1)
    return calendars.adjust(calendar, d, "FOLLOWING")


guard(globals())
