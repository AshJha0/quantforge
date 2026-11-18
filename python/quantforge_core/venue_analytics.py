"""Venue analytics: markouts, fill rates, toxicity (specifications/10-execution/venue-analytics.md,
stage H H-16; rulings HR-72, HR-75a).

Each input number is read as the decimal it prints as (shortest round trip) and every sum, and the
sign test of the toxicity indicator, is exact on those decimals; each output is rounded once to
binary64 (the spec's "Exact sums" paragraph)."""

from bisect import bisect_right
from collections.abc import Sequence
from fractions import Fraction
from itertools import pairwise
from typing import Any, NamedTuple

from .errors import QfError
from .finite import guard


class Fill(NamedTuple):
    venue: str
    side: str
    quantity: float
    price: float
    t: float


class Order(NamedTuple):
    venue: str
    sent: float
    filled: float


def _fail(code: str, message: str, field: str) -> QfError:
    return QfError(code, message, field)


def _q(x: float) -> Fraction:
    return Fraction(repr(float(x)))


def analytics(
    mids: Sequence[tuple[float, float]],
    fills: Sequence[Fill],
    orders: Sequence[Order],
    horizons: Sequence[float],
) -> dict[str, Any]:
    """`exec.venue.analytics`: per venue and horizon, markout, markout_bps and toxicity; per venue
    fill_rate. The mid at u is the last mid stamped at or before u (HR-72)."""
    # HR-75a: structural E_INPUT first, then E_DOMAIN, then the mid lookups
    if any(o.filled > o.sent for o in orders):
        raise _fail("E_INPUT", "filled exceeds sent", "orders")
    times = [_q(t) for t, _ in mids]
    if any(b <= a for a, b in pairwise(times)):
        raise _fail("E_INPUT", "mid times must be strictly increasing", "mids")
    if any(m <= 0 for _, m in mids):
        raise _fail("E_DOMAIN", "mids must be positive", "mids")
    if any(f.price <= 0 for f in fills):
        raise _fail("E_DOMAIN", "fill prices must be positive", "fills")
    if any(f.quantity <= 0 for f in fills):
        raise _fail("E_DOMAIN", "fill quantities must be positive", "fills")
    if any(o.sent <= 0 for o in orders):
        raise _fail("E_DOMAIN", "sent must be positive", "orders")
    if any(o.filled < 0 for o in orders):
        raise _fail("E_DOMAIN", "filled must be non-negative", "orders")
    if any(h < 0 for h in horizons):
        raise _fail("E_DOMAIN", "horizons must be non-negative", "horizons")
    values = [_q(m) for _, m in mids]
    hs = [_q(h) for h in horizons]

    def mid_at(u: Fraction) -> Fraction:
        k = bisect_right(times, u)
        if k == 0:
            raise _fail("E_INPUT", "no mid at or before a fill time plus horizon", "fills")
        return values[k - 1]

    exact = [
        (f.venue, 1 if f.side == "BUY" else -1, _q(f.quantity), _q(f.price), _q(f.t)) for f in fills
    ]
    markouts: list[dict[str, Any]] = []
    for venue in sorted({f.venue for f in fills}):
        mine = [e for e in exact if e[0] == venue]
        sq = sum((e[2] for e in mine), Fraction(0))
        sqp = sum((e[2] * e[3] for e in mine), Fraction(0))
        for h, hq in zip(horizons, hs, strict=True):
            num, toxic = Fraction(0), Fraction(0)
            for _, s, q, p, t in mine:
                move = s * (mid_at(t + hq) - p)
                num += q * move
                if move < 0:
                    toxic += q
            markouts.append(
                {
                    "venue": venue,
                    "h": h,
                    "markout": float(num / sq),
                    "markout_bps": float(10_000 * num / sqp),
                    "toxicity": float(toxic / sq),
                }
            )
    rates: dict[str, float] = {}
    for venue in sorted({o.venue for o in orders}):
        sent = sum((_q(o.sent) for o in orders if o.venue == venue), Fraction(0))
        got = sum((_q(o.filled) for o in orders if o.venue == venue), Fraction(0))
        rates[venue] = float(got / sent)
    return {"fill_rates": rates, "markouts": markouts}


guard(globals())
