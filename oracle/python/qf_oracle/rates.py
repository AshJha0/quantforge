"""Independent replay of the stage B rates specs. Plain floats; solved tightly so solver paths do not matter."""
import math
from datetime import date, timedelta

import numpy as np
from scipy.optimize import brentq

from .dates import dim, is_business, yf

CONV = {
    "SONIA": dict(currency="GBP", day_count="ACT_365F", calendar="GBLO", spot_lag=0, payment_lag=0, fixed_months=12, fixed_day_count="ACT_365F"),
    "SOFR": dict(currency="USD", day_count="ACT_360", calendar="USGS", spot_lag=2, payment_lag=2, fixed_months=12, fixed_day_count="ACT_360"),
}


def add_months(d, n):
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    m += 1
    return date(y, m, min(d.day, dim(y, m)))


def adjust(cal, d, how="MODIFIED_FOLLOWING"):
    if how == "UNADJUSTED":
        return d
    r = d
    while not is_business(cal, r):
        r += timedelta(1)
    if how == "FOLLOWING" or r.month == d.month:
        return r
    r = d
    while not is_business(cal, r):
        r -= timedelta(1)
    return r


def add_bd(cal, d, n):
    if n == 0:
        return adjust(cal, d, "FOLLOWING")
    k = 0
    while k < n:
        d += timedelta(1)
        k += is_business(cal, d)
    return d


def last_bd(cal, d):
    x = date(d.year, d.month, dim(d.year, d.month))
    while not is_business(cal, x):
        x -= timedelta(1)
    return x


def tenor_months(t):
    n, u = int(t[:-1]), t[-1]
    return n * 12 if u == "Y" else n if u == "M" else None


def end_date(cal, start, tenor):
    if tenor[-1] in "DW":
        days = int(tenor[:-1]) * (7 if tenor[-1] == "W" else 1)
        return adjust(cal, start + timedelta(days))
    m = tenor_months(tenor)
    if start >= last_bd(cal, start):
        return last_bd(cal, add_months(start, m))
    return adjust(cal, add_months(start, m))


def schedule(cal, start, end_unadj, months, eom=False):
    """Backward from the end; a short stub falls first. Returns adjusted period boundaries."""
    dates = [end_unadj]
    k = 1
    while True:
        d = add_months(end_unadj, -months * k)
        if d <= start:
            break
        dates.append(d)
        k += 1
    dates.append(start)
    dates.reverse()
    if eom:
        dates = [dates[0]] + [last_bd(cal, d) for d in dates[1:]]
    else:
        dates = [dates[0]] + [adjust(cal, d) for d in dates[1:]]
    return [dates[0]] + [d for d in dates[1:] if d > dates[0]]


class Curve:
    def __init__(self, as_of, dates, dfs, interp="LOG_LINEAR_DF"):
        self.as_of, self.interp = as_of, interp
        self.t = [0.0] + [(d - as_of).days / 365 for d in dates]
        self.d = [1.0] + list(dfs)

    def df(self, d):
        t = (d - self.as_of).days / 365
        if t == 0:
            return 1.0
        T, D = self.t, self.d
        if t >= T[-1]:
            i = len(T) - 2
            if self.interp == "LOG_LINEAR_DF":
                return D[-1] * math.exp(math.log(D[-1] / D[-2]) / (T[-1] - T[-2]) * (t - T[-1]))
            f = -math.log(D[-1] / D[-2]) / (T[-1] - T[-2])
            return D[-1] * math.exp(-f * (t - T[-1]))
        i = next(k for k in range(len(T) - 1) if t < T[k + 1])
        u = (t - T[i]) / (T[i + 1] - T[i])
        if self.interp == "LOG_LINEAR_DF":
            return math.exp((1 - u) * math.log(D[i]) + u * math.log(D[i + 1]))
        z0 = -math.log(D[1]) / T[1] if i == 0 else -math.log(D[i]) / T[i]
        z1 = -math.log(D[i + 1]) / T[i + 1]
        return math.exp(-((1 - u) * z0 + u * z1) * t)


def ois_periods(conv, as_of, tenor):
    c = CONV[conv]
    cal = c["calendar"]
    spot = add_bd(cal, adjust(cal, as_of, "FOLLOWING"), c["spot_lag"])
    end = end_date(cal, spot, tenor)
    if tenor[-1] in "DW" or (tenor_months(tenor) or 0) <= c["fixed_months"]:
        b = [spot, end]
    else:
        b = schedule(cal, spot, add_months(spot, tenor_months(tenor)), c["fixed_months"], eom=spot >= last_bd(cal, spot))
    return [(s, e, add_bd(cal, e, c["payment_lag"])) for s, e in zip(b, b[1:])]


def ois_legs(conv, periods, curve):
    fdc = CONV[conv]["fixed_day_count"]
    annuity = sum(float(yf(fdc, s, e)) * curve.df(p) for s, e, p in periods)
    flt = sum((curve.df(s) / curve.df(e) - 1) * curve.df(p) for s, e, p in periods)
    return annuity, flt


def ois_par(conv, periods, curve):
    a, f = ois_legs(conv, periods, curve)
    return f / a


def bootstrap(as_of, pillars, repricers, interp):
    """pillars: dates. repricers[i](curve) gives model minus quote. Sequential solve, tight tolerance."""
    dfs = []
    for i, d in enumerate(pillars):
        prev = dfs[-1] if dfs else 1.0

        def err(ln):
            return repricers[i](Curve(as_of, pillars[:i + 1], dfs + [math.exp(ln)], interp))
        lo, hi = math.log(prev) - 1.0, math.log(prev) + 1.0
        ln = brentq(err, lo, hi, xtol=1e-15, rtol=1e-15, maxiter=500)
        dfs.append(math.exp(ln))
    return Curve(as_of, pillars, dfs, interp), dfs


def bootstrap_ois(conv, as_of, quotes, interp="LOG_LINEAR_DF"):
    """quotes: list of (tenor, rate)."""
    per = [ois_periods(conv, as_of, t) for t, _ in quotes]
    pillars = [p[-1][2] for p in per]
    rep = [(lambda c, p=p, r=r: ois_par(conv, p, c) - r) for p, (_, r) in zip(per, quotes)]
    return bootstrap(as_of, pillars, rep, interp) + (per,)


def jac_fd(fn, x, h):
    x = np.array(x, float)
    cols = []
    for i in range(len(x)):
        u, d = x.copy(), x.copy()
        u[i] += h
        d[i] -= h
        cols.append((np.array(fn(u)) - np.array(fn(d))) / (2 * h))
    return np.array(cols).T
