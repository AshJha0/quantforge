"""Stage H wave 2 execution (rulings HR-59 to HR-66): adaptive algorithms
(10-execution/adaptive-algos.md: arrival price, close, liquidity seeking, pairs, baskets) and the
pre-trade estimate and cost attribution of 10-execution/tca-pretrade.md.

Sources, as the specs cite them: [AC00] Almgren and Chriss, J. Risk 3(2), preprint eq. (17) for
the arrival holdings and eq. (10) for the timing-risk line; [Kis13] Kissell (I-star form,
recalled, UNVERIFIED; parameters are inputs); [Per88] Perold for the total that the attribution
splits. Error precedence is HR-66: structural E_INPUT before any E_DOMAIN.

Reuses the wave-1 schedules (TWAP, VWAP with the HR-3 largest remainder) of `execution`."""

import math
from collections.abc import Sequence
from typing import Any

from .errors import QfError
from .execution import _largest_remainder, _quantity, _whole, schedule_twap, schedule_vwap
from .finite import guard

Level = Sequence[float]  # [price, size]


def _fail(code: str, message: str, field: str) -> QfError:
    return QfError(code, message, field)


def _sign(side: str) -> float:
    return 1.0 if side == "BUY" else -1.0


def _buckets(n: int) -> None:
    if n < 1:
        raise _fail("E_INPUT", "n_buckets must be at least 1", "n_buckets")


def _half_up(x: float) -> int:
    """HR-59, HR-62: floor(x + 1/2). HR-121: `x + 1/2` within 1e-12 relative of an integer is that
    integer, so an exact half that binary64 lands just below (0.3 / 0.2 = 1.4999999999999998)
    still rounds up, as POV and the close do before flooring."""
    t = x + 0.5
    near = round(t)
    return near if abs(t - near) <= 1e-12 * abs(near) else math.floor(t)


def _cosh_over_sinh(a: float, b: float) -> float:
    """cosh(a) / sinh(b) for 0 <= a <= b, b > 0, without overflow."""
    if b <= 700.0:
        return math.cosh(a) / math.sinh(b)
    return math.exp(a - b) * (1.0 + math.exp(-2.0 * a)) / (-math.expm1(-2.0 * b))


def _differences(cumulative: list[int]) -> list[int]:
    return [c - p for p, c in zip([0, *cumulative[:-1]], cumulative, strict=True)]


# ------------------------------------------------------------------ adaptive-algos.md


def algo_arrival(quantity: float, n_buckets: int, urgency: float, mode: str) -> dict[str, Any]:
    """`exec.algo.arrival`: holdings x_j = X sinh(kappa (N - j)) / sinh(kappa N) ([AC00] eq. (17),
    one bucket per time unit); kappa = 0 is TWAP. UNITS by largest remainder (HR-3, HR-67)."""
    units = mode == "UNITS"
    _buckets(n_buckets)
    _quantity(quantity, units)
    if urgency < 0:
        raise _fail("E_DOMAIN", "urgency must be non-negative", "urgency")
    n, k = n_buckets, urgency
    if k == 0:  # the TWAP limit, in both modes (HR-67)
        return schedule_twap(quantity, n, mode)
    # n_j = x_{j-1} - x_j = X 2 sinh(k/2) cosh(k (N - j + 1/2)) / sinh(k N): strictly
    # decreasing in j and free of cancellation.
    h = 2.0 * math.sinh(0.5 * k)
    exact = [quantity * h * _cosh_over_sinh(k * (n - j + 0.5), k * n) for j in range(1, n + 1)]
    # UNITS: largest remainder, ties to the earliest bucket, as HR-3 (HR-67 amends HR-59)
    return {"slices": _largest_remainder(quantity, exact) if units else exact}


def algo_close(
    quantity: float,
    close_volume: float,
    auction_participation: float,
    profile: Sequence[float],
    mode: str,
) -> dict[str, Any]:
    """`exec.algo.close`: auction min(X, p_c V_c) (UNITS floors p_c V_c); the remainder is
    allocated over the profile as `exec.schedule.vwap` (HR-60)."""
    units = mode == "UNITS"
    _quantity(quantity, units)
    if not profile:
        raise _fail("E_INPUT", "profile must not be empty", "profile")
    if not 0 <= auction_participation <= 1:
        raise _fail("E_DOMAIN", "auction_participation must lie in [0, 1]", "auction_participation")
    if close_volume < 0:
        raise _fail("E_DOMAIN", "close_volume must be non-negative", "close_volume")
    if any(w < 0 for w in profile):
        raise _fail("E_DOMAIN", "profile weights must be non-negative", "profile")
    cap = auction_participation * close_volume
    if units:
        near = round(cap)  # within 1e-12 relative of an integer: snap before flooring
        cap = near if abs(cap - near) <= 1e-12 * abs(near) else math.floor(cap)
    auction = min(quantity, cap)
    rest = quantity - auction
    if rest <= 0:
        zero: Any = 0 if units else 0.0
        return {
            "auction_quantity": _whole(auction) if units else auction,
            "slices": [zero] * len(profile),
        }
    if sum(profile, 0.0) == 0:
        raise _fail("E_DOMAIN", "profile is all zero with a remainder to place", "profile")
    slices = schedule_vwap(rest, profile, mode)["slices"]
    return {"auction_quantity": _whole(auction) if units else auction, "slices": slices}


def _inside(buy: bool, price: float, limit: float) -> bool:
    return price <= limit if buy else price >= limit


def algo_liquidity_seek(
    side: str,
    quantity: float,
    limit_price: float,
    take_fraction: float,
    books: Sequence[Sequence[Level]],
) -> dict[str, Any]:
    """`exec.algo.liquidity_seek`: child c_i = min(R_{i-1}, alpha A_i), A_i the depth inside the
    limit; the child walks the levels best first, inside the limit only (HR-61)."""
    buy = side == "BUY"
    if not books:
        raise _fail("E_INPUT", "books must not be empty", "books")
    if quantity <= 0:
        raise _fail("E_INPUT", "quantity must be positive", "quantity")
    for i, book in enumerate(books):
        for k, lvl in enumerate(book):
            if lvl[1] <= 0:
                raise _fail("E_INPUT", "level sizes must be positive", f"books/{i}/{k}")
            if k and not (lvl[0] > book[k - 1][0] if buy else lvl[0] < book[k - 1][0]):
                raise _fail(
                    "E_INPUT",
                    "levels must be strictly ordered best first (asks ascending, bids descending)",
                    f"books/{i}/{k}",
                )
    if not 0 < take_fraction <= 1:
        raise _fail("E_DOMAIN", "take_fraction must lie in (0, 1]", "take_fraction")
    if limit_price <= 0:
        raise _fail("E_DOMAIN", "limit_price must be positive", "limit_price")
    for i, book in enumerate(books):
        for k, lvl in enumerate(book):
            if lvl[0] <= 0:
                raise _fail("E_DOMAIN", "level prices must be positive", f"books/{i}/{k}")
    remaining, filled, notional = quantity, 0.0, 0.0
    slices: list[float] = []
    avg: list[float | None] = []
    for book in books:
        levels = [(p, s) for p, s in book if _inside(buy, p, limit_price)]
        depth = sum((s for _, s in levels), 0.0)
        child = min(remaining, take_fraction * depth)
        left, paid = child, 0.0
        for p, s in levels:
            if left <= 0:
                break
            take = min(left, s)
            paid += take * p
            left -= take
        slices.append(child)
        avg.append(paid / child if child > 0 else None)
        remaining -= child
        filled += child
        notional += paid
    return {
        "slices": slices,
        "avg_prices": avg,
        "filled": filled,
        "residual": remaining,
        "notional": notional,
        "avg_fill_price": notional / filled if filled > 0 else None,
    }


def _cumulative(xs: Sequence[float]) -> list[float]:
    out, c = [], 0.0
    for x in xs:
        c += x
        out.append(c)
    return out


def algo_pair(
    leg_a: tuple[str, float, float],
    leg_b: tuple[str, float],
    pair_mode: str,
    hedge_ratio: float | None,
    n_buckets: int,
    mode: str,
) -> dict[str, Any]:
    """`exec.algo.pair`: leg A is TWAP; leg B follows leg A's cumulative times the ratio r
    (P_A / P_B or h), rounded half up in UNITS (HR-62)."""
    units = mode == "UNITS"
    (side_a, qa, pa), (side_b, pb) = leg_a, leg_b
    _buckets(n_buckets)
    _quantity(qa, units)
    if pair_mode == "CASH_BALANCED" and side_a == side_b:
        raise _fail("E_INPUT", "a cash-balanced pair needs opposite sides", "leg_b")
    if pair_mode == "HEDGED" and hedge_ratio is None:
        raise _fail("E_INPUT", "HEDGED needs hedge_ratio", "hedge_ratio")
    if pa <= 0 or pb <= 0:
        raise _fail("E_DOMAIN", "prices must be positive", "leg_a" if pa <= 0 else "leg_b")
    if pair_mode == "HEDGED" and hedge_ratio is not None and hedge_ratio <= 0:
        raise _fail("E_DOMAIN", "hedge_ratio must be positive", "hedge_ratio")
    slices_a = schedule_twap(qa, n_buckets, mode)["slices"]
    cum_a = _cumulative(slices_a)
    if pair_mode == "HEDGED":
        h = float(hedge_ratio)  # type: ignore[arg-type]
        target = [h * c for c in cum_a]
    else:
        target = [c * pa / pb for c in cum_a]  # P_A C first: C_B P_B stays within ulps of C_A P_A
    if units:
        cum_b: list[float] = [float(_half_up(t)) for t in target]
        slices_b: list[Any] = _differences([int(c) for c in cum_b])
        quantity_b: Any = sum(slices_b)
    else:
        cum_b = target
        slices_b = [c - p for p, c in zip([0.0, *target[:-1]], target, strict=True)]
        quantity_b = target[-1]
    sa, sb = _sign(side_a), _sign(side_b)
    cash = [sa * ca * pa + sb * cb * pb for ca, cb in zip(cum_a, cum_b, strict=True)]
    return {
        "slices_a": slices_a,
        "slices_b": slices_b,
        "quantity_b": quantity_b,
        "cash_imbalance": cash,
    }


def algo_basket(
    legs: Sequence[tuple[str, float, float]], n_buckets: int, mode: str
) -> dict[str, Any]:
    """`exec.algo.basket`: every leg TWAP-sliced (HR-3); per-bucket cash imbalance and gross
    notional, no re-balancing (HR-63)."""
    units = mode == "UNITS"
    if not legs:
        raise _fail("E_INPUT", "legs must not be empty", "legs")
    _buckets(n_buckets)
    for _, q, _ in legs:
        _quantity(q, units)
    if any(p <= 0 for _, _, p in legs):
        raise _fail("E_DOMAIN", "prices must be positive", "legs")
    slices = [schedule_twap(q, n_buckets, mode)["slices"] for _, q, _ in legs]
    cums = [_cumulative(s) for s in slices]
    cash = [
        sum((_sign(side) * cums[k][j] * p for k, (side, _, p) in enumerate(legs)), 0.0)
        for j in range(n_buckets)
    ]
    return {
        "slices": slices,
        "cash_imbalance": cash,
        "gross_notional": sum((q * p for _, q, p in legs), 0.0),
    }


# ------------------------------------------------------------------ tca-pretrade.md


def tca_pretrade(
    quantity: float,
    adv: float,
    daily_vol: float,
    participation: float,
    half_spread_bps: float,
    params: tuple[float, float, float, float, float],
    price: float | None,
) -> dict[str, Any]:
    """`exec.tca.pretrade`: I* = a1 (X/adv)^a2 sigma^a3; impact = b1 I* p^a4 + (1 - b1) I*;
    expected cost = half spread + impact; timing risk 1e4 sigma sqrt(T/3), T = X / (p adv),
    reported beside the cost and never added (HR-64)."""
    a1, a2, a3, a4, b1 = params
    if quantity <= 0:
        raise _fail("E_INPUT", "quantity must be positive", "quantity")
    checks = [
        (adv <= 0, "adv must be positive", "adv"),
        (daily_vol < 0, "daily_vol must be non-negative", "daily_vol"),
        (not 0 < participation < 1, "participation must lie in (0, 1)", "participation"),
        (half_spread_bps < 0, "half_spread_bps must be non-negative", "half_spread_bps"),
        (a1 <= 0, "a1 must be positive", "params"),
        (not 0 <= b1 <= 1, "b1 must lie in [0, 1]", "params"),
        (price is not None and price <= 0, "price must be positive", "price"),
        (daily_vol == 0 and a3 <= 0, "0 to a non-positive power", "daily_vol"),
    ]
    for bad, message, field in checks:
        if bad:
            raise _fail("E_DOMAIN", message, field)
    istar = a1 * (quantity / adv) ** a2 * daily_vol**a3
    impact = b1 * istar * participation**a4 + (1.0 - b1) * istar
    cost = half_spread_bps + impact
    duration = quantity / (participation * adv)
    timing = 1e4 * daily_vol * math.sqrt(duration / 3.0)
    out: dict[str, Any] = {
        "istar_bps": istar,
        "impact_bps": impact,
        "spread_bps": half_spread_bps,
        "expected_cost_bps": cost,
        "duration_days": duration,
        "timing_risk_bps": timing,
    }
    if price is not None:
        out["expected_cost"] = cost * quantity * price / 1e4
        out["timing_risk"] = timing * quantity * price / 1e4
    return out


def tca_attribution(
    side: str,
    decision_price: float,
    arrival_mid: float,
    end_price: float,
    order_quantity: float,
    fills: Sequence[tuple[float, float, float]],
    fees: float,
) -> dict[str, Any]:
    """`exec.tca.attribution`: delay s Q (m_0 - P_d), impact s sum q (m - m_0), spread
    s sum q (p - m) on executed quantity; opportunity and fees as HR-8 (HR-65)."""
    s = _sign(side)
    if order_quantity <= 0:
        raise _fail("E_INPUT", "order_quantity must be positive", "order_quantity")
    if any(q <= 0 for q, _, _ in fills):
        raise _fail("E_INPUT", "fill quantities must be positive", "fills")
    filled = sum((q for q, _, _ in fills), 0.0)
    if filled > order_quantity:
        raise _fail("E_INPUT", "fills add up to more than the order", "fills")
    for key, p in (
        ("decision_price", decision_price),
        ("arrival_mid", arrival_mid),
        ("end_price", end_price),
        *(("fills", x) for _, p_, m in fills for x in (p_, m)),
    ):
        if p <= 0:
            raise _fail("E_DOMAIN", "prices and mids must be positive", key)
    # + 0.0 turns the -0 of a SELL into +0
    delay = s * filled * (arrival_mid - decision_price) + 0.0
    impact = s * sum((q * (m - arrival_mid) for q, _, m in fills), 0.0) + 0.0
    spread = s * sum((q * (p - m) for q, p, m in fills), 0.0) + 0.0
    opportunity = s * (order_quantity - filled) * (end_price - decision_price) + 0.0
    total = delay + impact + spread + opportunity + fees
    return {
        "delay": delay,
        "impact": impact,
        "spread": spread,
        "execution": impact + spread,
        "opportunity": opportunity,
        "fees": fees,
        "total": total,
        "total_bps": total / (order_quantity * decision_price) * 1e4,
    }


guard(globals())
