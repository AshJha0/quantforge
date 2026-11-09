"""Equity spot, dividends and forward (specifications/02-curves/equity-forward.md)."""
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from . import curves
from .curves import CurveData
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum


@dataclass(frozen=True)
class ForwardResult:
    forward: float
    discount_factor: float
    carry_factor: float
    pv_dividends: float
    time: float


@dataclass(frozen=True)
class ParityQuote:
    strike: float
    call_bid: float
    call_ask: float
    put_bid: float
    put_ask: float


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


def outright(
    spot: float, as_of: date, expiry: date, funding: CurveData, borrow: CurveData | None,
    dividends: Sequence[tuple[date, float]],
) -> ForwardResult:
    if spot <= 0:
        raise _domain("spot must be positive", "spot")
    d_curve = curves.build(funding)
    b_curve = curves.build(borrow) if borrow is not None else None
    if funding.as_of != as_of or (borrow is not None and borrow.as_of != as_of):
        raise QfError("E_INPUT", "a curve as_of differs from as_of", "as_of")
    if expiry < as_of:
        raise QfError("E_DATE_ORDER", "expiry is before as_of", "expiry")
    if any(amount < 0 for _, amount in dividends):
        raise _domain("a dividend is negative", "dividends")
    if any(a[0] >= b[0] for a, b in itertools.pairwise(dividends)):
        raise QfError("E_INPUT", "ex_dates must be strictly increasing", "dividends")

    def carry(d: date) -> float:
        # Ruling C2: the carry factor is D/B, never D alone.
        if d == as_of:
            return 1.0
        return d_curve.discount(d) / (b_curve.discount(d) if b_curve is not None else 1.0)

    c_t = carry(expiry)
    pv = ordered_sum(a * carry(d) for d, a in dividends if as_of < d <= expiry)
    forward = (spot - pv) / c_t
    if forward <= 0:
        raise _domain("the forward is not positive", "dividends")
    d_t = 1.0 if expiry == as_of else d_curve.discount(expiry)
    return ForwardResult(forward, d_t, c_t, pv, (expiry - as_of).days / 365)


def flat(
    spot: float, rate: float, borrow: float, expiry_years: float,
    dividends: Sequence[tuple[float, float]],
) -> float:
    if spot <= 0:
        raise _domain("spot must be positive", "spot")
    if expiry_years < 0:
        raise _domain("expiry_years is negative", "expiry_years")
    if any(amount < 0 for _, amount in dividends):
        raise _domain("a dividend is negative", "dividends")
    if any(a[0] >= b[0] for a, b in itertools.pairwise(dividends)):
        raise QfError("E_INPUT", "time_years must be strictly increasing", "dividends")
    c = rate - borrow
    forward = spot * math.exp(c * expiry_years) - ordered_sum(
        a * math.exp(c * (expiry_years - t)) for t, a in dividends if 0 < t <= expiry_years
    )
    if forward <= 0:
        raise _domain("the forward is not positive", "dividends")
    return forward


def parity(
    quotes: Sequence[ParityQuote], discount_factor: float | None
) -> tuple[float, float, float, list[float]]:
    if not quotes:
        raise QfError("E_INPUT", "quotes is empty", "quotes")
    for q in quotes:
        if q.strike <= 0 or min(q.call_bid, q.call_ask, q.put_bid, q.put_ask) < 0:
            raise _domain("a strike or quote is out of range", "quotes")
    if discount_factor is not None and discount_factor <= 0:
        raise _domain("discount_factor must be positive", "discount_factor")
    if any(a.strike >= b.strike for a, b in itertools.pairwise(quotes)):
        raise QfError("E_INPUT", "strikes must be strictly increasing", "quotes")
    if any(q.call_bid > q.call_ask or q.put_bid > q.put_ask for q in quotes):
        raise QfError("E_INPUT", "a bid is above its ask", "quotes")
    n = len(quotes)
    if discount_factor is None and n == 1:
        raise QfError("E_INPUT", "one quote cannot fit a discount factor", "quotes")
    ks = [q.strike for q in quotes]
    ys = [(q.call_bid + q.call_ask) / 2 - (q.put_bid + q.put_ask) / 2 for q in quotes]
    if discount_factor is not None:
        d = discount_factor
        f = ordered_sum(k + y / d for k, y in zip(ks, ys, strict=True)) / n
    else:
        k_bar, y_bar = ordered_sum(ks) / n, ordered_sum(ys) / n
        slope = ordered_sum((k - k_bar) * (y - y_bar) for k, y in zip(ks, ys, strict=True))
        slope /= ordered_sum((k - k_bar) ** 2 for k in ks)
        d = -slope
        if d <= 0:
            raise _domain("the fitted discount factor is not positive", "quotes")
        f = (y_bar - slope * k_bar) / d
    if f <= 0:
        raise _domain("the fitted forward is not positive", "quotes")
    residual = max(abs(y - d * (f - k)) for k, y in zip(ks, ys, strict=True))
    outside = [
        q.strike for q in quotes
        if not q.call_bid - q.put_ask <= d * (f - q.strike) <= q.call_ask - q.put_bid
    ]
    return f, d, residual, outside


guard(globals())
