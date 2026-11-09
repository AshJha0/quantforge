"""Equity dividend, borrow and financing curves; index dividends, rebalancing, corporate actions
and TRS (specifications/02-curves/equity-curves.md, specifications/04-pricing/equity-index.md)."""
import itertools
import math
from collections.abc import Callable, Sequence
from datetime import date

from . import curves, roots
from .curves import Curve, CurveData
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum

Dividends = Sequence[tuple[date, float]]


def _carry(curve: Curve, b: float, s: float, d: date) -> float:
    """C = D/B times the financing factor exp(-s t)."""
    t = curve.time(d)
    return curve.discount(d) * math.exp(b * t) * math.exp(-s * t)


def _forward(spot: float, curve: Curve, b: float, s: float, divs: Dividends, expiry: date) -> float:
    pv = ordered_sum(a * _carry(curve, b, s, d) for d, a in divs if curve.as_of < d <= expiry)
    return (spot - pv) / _carry(curve, b, s, expiry)


def dividend_implied(
    spot: float, funding: CurveData, b: float, futures: Sequence[tuple[date, float]],
) -> tuple[list[float], list[float], list[float]]:
    curve = curves.build(funding)
    if not futures:
        raise QfError("E_INPUT", "no futures", "futures")
    if any(y <= x for x, y in itertools.pairwise([curve.as_of, *(d for d, _ in futures)])):
        raise QfError("E_INPUT", "expiries must be increasing and after as_of", "futures")
    if spot <= 0 or any(p <= 0 for _, p in futures):
        raise QfError("E_DOMAIN", "spot and prices must be positive")
    xs = [spot - p * _carry(curve, b, 0.0, d) for d, p in futures]
    periods = [xs[0], *(y - x for x, y in itertools.pairwise(xs))]
    yields = [-math.log(p * _carry(curve, b, 0.0, d) / spot) / curve.time(d) for d, p in futures]
    return xs, periods, yields


def _solve_rate(g: Callable[[float], float], what: str) -> float:
    lo, hi = -0.5, 0.5
    if (g(lo) > 0) == (g(hi) > 0):
        raise QfError("E_NOT_BRACKETED", f"no {what} in [-0.5, 0.5]")
    return roots.brent(g, lo, hi, x_tol=1e-16, max_iter=1000).root


def _check_expiry(curve: Curve, expiry: date) -> None:
    if expiry <= curve.as_of:
        raise QfError("E_DATE_ORDER", "expiry is not after as_of", "expiry")


def borrow_implied(spot: float, funding: CurveData, divs: Dividends, expiry: date,
                   forward: float) -> float:
    curve = curves.build(funding)
    _check_expiry(curve, expiry)
    return _solve_rate(lambda b: _forward(spot, curve, b, 0.0, divs, expiry) - forward,
                       "borrow rate")


def futures_basis(spot: float, funding: CurveData, b: float, s: float, divs: Dividends,
                  expiry: date, price: float) -> tuple[float, float, float]:
    curve = curves.build(funding)
    _check_expiry(curve, expiry)
    fair = _forward(spot, curve, b, s, divs, expiry)
    implied = _solve_rate(lambda x: _forward(spot, curve, b, x, divs, expiry) - price,
                          "financing spread")
    return fair, price - fair, implied


def index_dividends(
    divisor: float, constituents: Sequence[tuple[str, float, float, Dividends]],
    periods: Sequence[tuple[date, date]], implied: Sequence[float],
) -> dict[str, object]:
    if divisor <= 0:
        raise QfError("E_DOMAIN", "divisor must be positive", "divisor")
    if any(e < s for s, e in periods):
        raise QfError("E_DATE_ORDER", "a period ends before it starts", "periods")
    if len(periods) != len(implied):
        raise QfError("E_INPUT", "one implied value per period", "implied_period_points")
    level = ordered_sum(n * p for _, n, p, _ in constituents) / divisor
    by_day: dict[date, list[float]] = {}
    for _, n, _, divs in constituents:
        for d, a in divs:
            by_day.setdefault(d, []).append(n * a)
    days = sorted(by_day)
    points = [ordered_sum(by_day[d]) / divisor for d in days]
    period_points = [ordered_sum(x for d, x in zip(days, points, strict=True) if s <= d <= e)
                     for s, e in periods]
    return {"level": level, "ex_dates": [d.isoformat() for d in days], "points": points,
            "period_points": period_points,
            "basis": [i - p for i, p in zip(implied, period_points, strict=True)]}


def rebalance(
    divisor: float, old: Sequence[tuple[str, float, float]], new: Sequence[tuple[str, float, float]],
) -> tuple[float, float, list[float]]:
    for group in (old, new):
        ids = [i for i, _, _ in group]
        if len(set(ids)) != len(ids):
            raise QfError("E_INPUT", "duplicate id", "constituents")
    if divisor <= 0:
        raise QfError("E_DOMAIN", "divisor must be positive", "divisor")
    level = ordered_sum(n * p for _, n, p in old) / divisor
    caps = [n * p for _, n, p in new]
    total = ordered_sum(caps)
    if level <= 0 or total <= 0:
        raise QfError("E_DOMAIN", "capitalisation must be positive", "constituents")
    return level, total / level, [c / total for c in caps]


def corporate_action(action: str, price: float, shares: float, strike: float,
                     params: dict[str, float]) -> dict[str, float]:
    if action in ("SPLIT", "REVERSE_SPLIT"):
        ratio = params["ratio"]
        if ratio <= 0:
            raise QfError("E_DOMAIN", "ratio must be positive", "ratio")
        f = 1 / ratio
    elif action == "RIGHTS":
        m, k = params["new_per_old"], params["subscription_price"]
        if m <= 0 or k <= 0:
            raise QfError("E_DOMAIN", "new_per_old and subscription_price must be positive")
        f = (price + m * k) / (1 + m) / price
    else:
        amount = params["amount"]
        if amount <= 0 or amount >= price:
            raise QfError("E_DOMAIN", "amount must be in (0, cum_price)", "amount")
        f = (price - amount) / price
    return {"factor": f, "ex_price": f * price, "adjusted_shares": shares / f,
            "adjusted_strike": f * strike}


def trs_pv(spot: float, funding: CurveData, b: float, divs: Dividends, start: date, end: date,
           s0: float, n: float, spread: float, side: str, current: float | None
           ) -> tuple[float, float, float]:
    curve = curves.build(funding)
    if end <= start:
        raise QfError("E_DATE_ORDER", "end is not after start", "end")
    if start < curve.as_of and current is None:
        raise QfError("E_INPUT", "current_rate is needed once the period has started",
                      "current_rate")
    d_end = curve.discount(end)
    paid = ordered_sum(a for d, a in divs if curve.as_of < d <= end)
    equity = n * d_end * (_forward(spot, curve, b, 0.0, divs, end) + paid - s0)
    alpha = (end - start).days / 360
    r = current if current is not None else (curve.discount(start) / d_end - 1) / alpha
    funding_leg = n * s0 * (r + spread) * alpha * d_end
    sign = 1 if side == "RECEIVE_EQUITY" else -1
    return equity, funding_leg, sign * (equity - funding_leg)


guard(globals())
