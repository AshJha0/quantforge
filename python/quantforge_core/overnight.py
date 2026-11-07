"""Overnight compounding by date, and IBOR fallbacks
(specifications/02-curves/overnight-compounding.md)."""
from collections.abc import Sequence
from datetime import date, timedelta

from . import calendars
from .conventions import REGISTRY
from .errors import QfError

METHODS = ("NONE", "LOOKBACK", "OBSERVATION_SHIFT", "LOCKOUT")
FALLBACKS: dict[str, tuple[str, float]] = {
    "USD-LIBOR-1M": ("SOFR", 0.0011448),
    "USD-LIBOR-3M": ("SOFR", 0.0026161),
    "USD-LIBOR-6M": ("SOFR", 0.0042826),
    "USD-LIBOR-12M": ("SOFR", 0.0071513),
    "GBP-LIBOR-1M": ("SONIA", 0.0003260),
    "GBP-LIBOR-3M": ("SONIA", 0.0011930),
    "GBP-LIBOR-6M": ("SONIA", 0.0027660),
    "GBP-LIBOR-12M": ("SONIA", 0.0046440),
}
_DENOMINATORS = {"ACT_360": 360, "ACT_365F": 365}


def _is_fixing_day(cal: str, sofr: bool, d: date) -> bool:
    """Ruling R1-6: SOFR is never published on Good Friday, even in a USGS early-close year."""
    if sofr and d == calendars.good_friday(d.year):
        return False
    return calendars.is_business_day(cal, d)


def _back(cal: str, sofr: bool, d: date, k: int) -> date:
    if not sofr:
        return calendars.add_business_days(cal, d, -k) if k else d
    calendars.check_range(d)
    while k:
        d -= timedelta(days=1)
        if _is_fixing_day(cal, sofr, d):
            k -= 1
    return d


def _business_days(cal: str, start: date, end: date, sofr: bool = False) -> list[date]:
    days, d = [], start
    while d <= end:
        if _is_fixing_day(cal, sofr, d):
            days.append(d)
        d += timedelta(days=1)
    return days


def compound_dated(
    convention: str, start: date, end: date, method: str, shift_days: int,
    fixings: Sequence[tuple[date, float]],
) -> tuple[float, float, float]:
    """Returns (compounded_rate, accrual, interest)."""
    c = REGISTRY[convention]
    if c["kind"] != "OVERNIGHT":
        raise QfError("E_INPUT", "the convention is not overnight", "convention")
    if end <= start:
        raise QfError("E_DATE_ORDER", "end is not after start", "end")
    cal, k, sofr = c["calendar"], shift_days, convention == "SOFR"
    ds = _business_days(cal, start, end, sofr)
    n = len(ds) - 1
    if (k < 0 or (method == "NONE" and k != 0)
            or (method == "LOCKOUT" and not 1 <= k <= n - 1)):
        raise QfError("E_INPUT", "shift_days is out of range for the method", "shift_days")
    if not (_is_fixing_day(cal, sofr, start) and _is_fixing_day(cal, sofr, end)):
        raise QfError("E_INPUT", "start and end must be business days", "start")
    table: dict[date, float] = {}
    for d, r in fixings:
        if d in table:
            raise QfError("E_INPUT", f"two fixings on {d}", "fixings")
        table[d] = r

    def back(d: date) -> date:
        return _back(cal, sofr, d, k)

    if method == "OBSERVATION_SHIFT":
        obs = [back(d) for d in ds]
        steps = [(obs[i], (obs[i + 1] - obs[i]).days) for i in range(n)]
    elif method == "LOOKBACK":
        steps = [(back(ds[i]), (ds[i + 1] - ds[i]).days) for i in range(n)]
    elif method == "LOCKOUT":
        steps = [(ds[min(i, n - k)], (ds[i + 1] - ds[i]).days) for i in range(n)]
    else:
        steps = [(ds[i], (ds[i + 1] - ds[i]).days) for i in range(n)]
    missing = [d for d, _ in steps if d not in table]
    if missing:
        raise QfError("E_INPUT", f"no fixing for {missing[0]}", "fixings")
    b = _DENOMINATORS[c["day_count"]]
    growth = 1.0
    for d, w in steps:
        growth *= 1 + table[d] * w / b
    rate = (growth - 1) * b / sum(w for _, w in steps)
    accrual = (end - start).days / b
    return rate, accrual, rate * accrual


def fallback(
    ibor: str, start: date, end: date, fixings: Sequence[tuple[date, float]]
) -> tuple[float, float, float]:
    """Returns (compounded_rate, spread_adjustment, fallback_rate)."""
    index, spread = FALLBACKS[ibor]
    rate, _, _ = compound_dated(index, start, end, "OBSERVATION_SHIFT", 2, fixings)
    return rate, spread, rate + spread
