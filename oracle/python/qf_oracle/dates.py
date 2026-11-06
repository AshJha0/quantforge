"""Exact (rational) reading of specifications/01-core/daycount.md and calendars.md.

This is the hand-case oracle. It is cross-checked against QuantLib and Strata in gen_dates.py.
"""
import calendar as _c
from datetime import date, timedelta
from fractions import Fraction as Fr

leap = _c.isleap


def dim(y, m):
    return _c.monthrange(y, m)[1]


def eofeb(d):
    return d.month == 2 and d.day == dim(d.year, 2)


def diy(y):
    return 366 if leap(y) else 365


def contains_feb29(a, b):
    """True when a 29 Feb lies in (a, b]."""
    return any(leap(y) and a < date(y, 2, 29) <= b for y in range(a.year, b.year + 1))


def eofeb29(d):
    return d.month == 2 and d.day == 29


def t360(y1, m1, d1, y2, m2, d2):
    return Fr(360 * (y2 - y1) + 30 * (m2 - m1) + (d2 - d1), 360)


def years_back(e, n):
    y = e.year - n
    if e.month == 2 and e.day == 28 and leap(y):
        return date(y, 2, 29)
    return date(y, e.month, min(e.day, dim(y, e.month)))


def yf(conv, s, e, *, ref_start=None, ref_end=None, frequency=None, termination=None, calendar=None):
    days = (e - s).days
    if conv == "ACT_360":
        return Fr(days, 360)
    if conv == "ACT_365F":
        return Fr(days, 365)
    if conv == "ACT_364":
        return Fr(days, 364)
    if conv == "ACT_365_25":
        return Fr(days * 4, 1461)
    if conv == "ONE_ONE":
        return Fr(1) if days > 0 else Fr(0)
    if conv == "NL_365":
        n = sum(1 for y in range(s.year, e.year + 1) if leap(y) and s < date(y, 2, 29) <= e)
        return Fr(days - n, 365)
    if conv == "ACT_365L":
        if days == 0:
            return Fr(0)
        if frequency == 1:
            return Fr(days, 366 if contains_feb29(s, e) else 365)
        return Fr(days, 366 if leap(e.year) else 365)
    if conv == "ACT_ACT_ISDA":
        if s.year == e.year:
            return Fr(days, diy(s.year))
        return (Fr((date(s.year + 1, 1, 1) - s).days, diy(s.year)) + (e.year - s.year - 1)
                + Fr((e - date(e.year, 1, 1)).days, diy(e.year)))
    if conv == "ACT_ACT_ICMA":
        return Fr(days, frequency * (ref_end - ref_start).days)
    if conv == "ACT_ACT_AFB":
        end, n = e, 0
        while years_back(e, n + 1) >= s:
            n += 1
            end = years_back(e, n)
        return n + Fr((end - s).days, 366 if s < end and (contains_feb29(s, end - timedelta(1)) or eofeb29(s)) else 365)
    y1, m1, d1, y2, m2, d2 = s.year, s.month, s.day, e.year, e.month, e.day
    if conv == "THIRTY_360_BOND":
        if d1 == 31:
            d1 = 30
        if d2 == 31 and d1 == 30:
            d2 = 30
        return t360(y1, m1, d1, y2, m2, d2)
    if conv == "THIRTY_360_US":
        if eofeb(s) and eofeb(e):
            d2 = 30
        if eofeb(s):
            d1 = 30
        if d2 == 31 and d1 >= 30:
            d2 = 30
        if d1 == 31:
            d1 = 30
        return t360(y1, m1, d1, y2, m2, d2)
    if conv == "THIRTY_E_360":
        return t360(y1, m1, min(d1, 30), y2, m2, min(d2, 30))
    if conv == "THIRTY_E_360_ISDA":
        if d1 == 31 or eofeb(s):
            d1 = 30
        if d2 == 31 or (eofeb(e) and e != termination):
            d2 = 30
        return t360(y1, m1, d1, y2, m2, d2)
    if conv == "THIRTY_E_PLUS_360":
        if d1 == 31:
            d1 = 30
        if d2 == 31:
            m2, d2 = m2 + 1, 1
        return t360(y1, m1, d1, y2, m2, d2)
    if conv == "BUS_252":
        n, d = 0, s
        while d < e:
            n += is_business(calendar, d)
            d += timedelta(1)
        return Fr(n, 252)
    raise KeyError(conv)


def easter(y):
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mo, da = divmod(h + l - 7 * m + 114, 31)
    return date(y, mo, da + 1)


def nth(y, m, wd, n):
    d = date(y, m, 1)
    d += timedelta((wd - d.weekday()) % 7)
    return d + timedelta(7 * (n - 1))


def last(y, m, wd):
    d = date(y, m, dim(y, m))
    return d - timedelta((d.weekday() - wd) % 7)


def sun_mon(d):
    return d + timedelta(1) if d.weekday() == 6 else d


def sat_fri_sun_mon(d):
    return d - timedelta(1) if d.weekday() == 5 else sun_mon(d)


GBLO_ONEOFF = {date(2002, 6, 3), date(2011, 4, 29), date(2012, 6, 5), date(2022, 6, 3),
               date(2022, 9, 19), date(2023, 5, 8)}
USGS_ONEOFF = {date(2004, 6, 11), date(2012, 10, 30), date(2018, 12, 5)}
USGS_REMOVED = set()
EUTA_ONEOFF = {date(2001, 12, 31)}


def holidays(cal, y):
    gf = easter(y) - timedelta(2)
    em = easter(y) + timedelta(1)
    if cal == "GBLO":
        h = set()
        j = date(y, 1, 1)
        h.add(j + timedelta({5: 2, 6: 1}.get(j.weekday(), 0)))
        h |= {gf, em}
        h.add(date(2020, 5, 8) if y == 2020 else nth(y, 5, 0, 1))
        h.add({2002: date(2002, 6, 4), 2012: date(2012, 6, 4), 2022: date(2022, 6, 2)}.get(y, last(y, 5, 0)))
        h.add(last(y, 8, 0))
        x = date(y, 12, 25)
        wd = x.weekday()
        if wd == 5:
            h |= {date(y, 12, 27), date(y, 12, 28)}
        elif wd == 6:
            h |= {date(y, 12, 26), date(y, 12, 27)}
        elif wd == 4:
            h |= {x, date(y, 12, 28)}
        else:
            h |= {x, date(y, 12, 26)}
        return h | {d for d in GBLO_ONEOFF if d.year == y}
    if cal == "EUTA":
        return ({date(y, 1, 1), gf, em, date(y, 5, 1), date(y, 12, 25), date(y, 12, 26)}
                | {d for d in EUTA_ONEOFF if d.year == y})
    if cal == "USGS":
        h = {sun_mon(date(y, 1, 1)), nth(y, 1, 0, 3), nth(y, 2, 0, 3), gf, last(y, 5, 0),
             sat_fri_sun_mon(date(y, 7, 4)), nth(y, 9, 0, 1), nth(y, 10, 0, 2),
             sun_mon(date(y, 11, 11)), nth(y, 11, 3, 4), sat_fri_sun_mon(date(y, 12, 25))}
        if y >= 2022:
            h.add(sat_fri_sun_mon(date(y, 6, 19)))
        return (h - USGS_REMOVED) | {d for d in USGS_ONEOFF if d.year == y}
    raise KeyError(cal)


_cache = {}


def is_business(cal, d):
    if d.weekday() >= 5:
        return False
    k = (cal, d.year)
    if k not in _cache:
        _cache[k] = holidays(cal, d.year)
    return d not in _cache[k]
