"""The two `calendar` functions the core uses. The stdlib module imports `locale`, which costs a
noticeable share of CLI start-up, and batch fuzzing starts a process per chunk."""
from datetime import date

_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def isleap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def monthrange(year: int, month: int) -> tuple[int, int]:
    """(weekday of the first day, Monday 0; number of days), as calendar.monthrange."""
    days = 29 if month == 2 and isleap(year) else _DAYS[month - 1]
    return date(year, month, 1).weekday(), days
