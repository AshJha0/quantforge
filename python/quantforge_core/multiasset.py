"""Multi-asset microstructure: equities (H-22), FX spot (H-23) and rates (H-24).

Specs: specifications/09-microstructure/asset-conventions.md, specifications/10-execution/auction.md,
fx-rfq-venue.md and rates-futures-venue.md (rulings HR-80 to HR-103 in
specifications/stage-h-rulings-multiasset.md). Every venue number is a parameter with a sourced
default (HR-80). Prices, quantities, fees and rates are decimal strings (HR-12), computed exactly
in a 200-digit context and range-checked (HR-57, HR-58). Every output carries its label (HR-94).
Error order HR-66: E_SCHEMA, then structural E_INPUT, then E_DOMAIN, then E_LIMIT; each function
parses every field before it checks any domain.

The futures venue reuses the lit engine unchanged (`lit_matching.run`); the auction uncross is the
call-phase step whose residual limit orders rest in that engine.
"""

import re
from collections.abc import Callable
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal, localcontext
from itertools import pairwise
from typing import Any

from . import lit_matching
from .errors import QfError
from .finite import guard
from .lit_matching import fmt
from .order_book import EXACT, check_range, input_dec

EQ_LABEL = "simulated venue; not a real exchange"
IEX_LABEL = "IEX only; one venue"
FX_LABEL = "simulated venue; not a real exchange; no real FX data"
RATES_LABEL = "simulated venue; not a real exchange; no real rates data"

DEFAULT_TICK_TABLE = (("0", "0.0001"), ("1.00", "0.01"))  # [REGNMS-612], penny tier
HALF_PENNY_TABLE = (("0", "0.0001"), ("1.00", "0.005"))  # [REGNMS-612] current, narrow-spread tier
# Dated rule versions (coordinator ruling 2026-11-18 after the HR-98 source check): the current
# Rule 612/610 text applies on and after RULE_2024_COMPLIANCE; an `as_of` before it selects the old
# regime. The compliance date is a parameter whose default is UNVERIFIED (source check could not
# confirm it). Fee caps per share at $1.00 or more, and as a fraction of price below.
RULE_2024_COMPLIANCE = "2026-11-03"
FEE_CAP_CURRENT = (Decimal("0.001"), Decimal("0.001"))  # [REGNMS-610] read 2026-11-18
FEE_CAP_OLD = (Decimal("0.003"), Decimal("0.003"))
CCY_ORDER = ("EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY")  # HR-88
T1_PAIRS = ("USDCAD",)  # HR-89 [BIS-FX]
CONTRACTS = {  # HR-91, [CME-ZN] and [CME-ZB]
    "ZN": ("100000", "0.015625"),
    "ZB": ("100000", "0.03125"),
}
RESOLUTIONS = (32, 64, 128, 256)
_EIGHTHS = {"": 0, "1": 1, "2": 2, "3": 3, "+": 4, "5": 5, "6": 6, "7": 7}
_EIGHTH_TEXT = {v: k for k, v in _EIGHTHS.items()}
_32NDS = re.compile(r"([0-9]+)-([0-9]{2})([1235-7+]?)")
MAX_CANDIDATES = 1_000_000
MAX_ORDERS = 10_000_000
MAX_DAYS = 3660


# ------------------------------------------------------------------ parsing helpers (E_SCHEMA)


def _obj(raw: Any, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise QfError("E_SCHEMA", f"{path}: not an object", path)
    return raw


def _need(raw: dict[str, Any], key: str, path: str = "") -> Any:
    if key not in raw:
        p = f"{path}{key}"
        raise QfError("E_SCHEMA", f"{p}: missing", p)
    return raw[key]


def _dec(raw: dict[str, Any], key: str, default: str | None = None, path: str = "") -> Decimal:
    v = raw.get(key, default) if default is not None else _need(raw, key, path)
    return input_dec(v, f"{path}{key}")


def _int(raw: dict[str, Any], key: str, default: int | None = None, path: str = "") -> int:
    v = raw.get(key, default) if default is not None else _need(raw, key, path)
    if isinstance(v, bool) or not isinstance(v, int):
        raise QfError("E_SCHEMA", f"{path}{key}: not an integer", f"{path}{key}")
    return v


def _bool(raw: dict[str, Any], key: str, default: bool) -> bool:
    v = raw.get(key, default)
    if not isinstance(v, bool):
        raise QfError("E_SCHEMA", f"{key}: not a boolean", key)
    return v


def _str(raw: dict[str, Any], key: str, path: str = "") -> str:
    v = _need(raw, key, path)
    if not isinstance(v, str):
        raise QfError("E_SCHEMA", f"{path}{key}: not a string", f"{path}{key}")
    return v


def _enum(raw: dict[str, Any], key: str, allowed: tuple[str, ...], path: str = "") -> str:
    v = _str(raw, key, path)
    if v not in allowed:
        raise QfError("E_SCHEMA", f"{path}{key}: not one of {allowed}", f"{path}{key}")
    return v


def _date(v: Any, path: str) -> date:
    if not isinstance(v, str):
        raise QfError("E_SCHEMA", f"{path}: not an ISO date", path)
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise QfError("E_SCHEMA", f"{path}: not an ISO date", path) from None


def _dates(v: Any, path: str) -> set[date]:
    if not isinstance(v, list):
        raise QfError("E_SCHEMA", f"{path}: not an array", path)
    return {_date(x, f"{path}/{k}") for k, x in enumerate(v)}


def _list(raw: dict[str, Any], key: str) -> list[Any]:
    v = _need(raw, key)
    if not isinstance(v, list):
        raise QfError("E_SCHEMA", f"{key}: not an array", key)
    return v


def _c(x: Decimal) -> Decimal:
    return check_range(x, "value")


def _places(step: Decimal) -> int:
    exp = step.normalize(EXACT).as_tuple().exponent
    assert isinstance(exp, int)
    return max(0, -exp)


def _at(x: Decimal, places: int) -> str:
    """`x` printed with exactly `places` decimals (HR-100 "printed at the tick decimals")."""
    return format(x.quantize(Decimal(1).scaleb(-places), context=EXACT), "f")


def _exact(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    def wrapped(raw: dict[str, Any]) -> dict[str, Any]:
        with localcontext(EXACT):
            return fn(_obj(raw, "inputs"))

    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


# ------------------------------------------------------------------ equities (H-22)


def _current(raw: dict[str, Any]) -> bool:
    """True when the current (2024-amended) Rule 612/610 text applies at `as_of`."""
    cd = _date(raw.get("compliance_date", RULE_2024_COMPLIANCE), "compliance_date")
    return "as_of" not in raw or _date(raw["as_of"], "as_of") >= cd


def _tick_table(raw: dict[str, Any]) -> list[tuple[Decimal, Decimal]]:
    tier = raw.get("tick_tier", "PENNY")
    if tier not in ("PENNY", "HALF_PENNY"):
        raise QfError("E_SCHEMA", "tick_tier: not PENNY or HALF_PENNY", "tick_tier")
    current = _current(raw)
    if tier == "HALF_PENNY" and not current:
        raise QfError("E_INPUT", "tick_tier HALF_PENNY before the compliance date", "tick_tier")
    if tier == "HALF_PENNY" and "tick_table" in raw:
        raise QfError("E_INPUT", "tick_tier HALF_PENNY with an explicit tick_table", "tick_tier")
    dflt = HALF_PENNY_TABLE if tier == "HALF_PENNY" else DEFAULT_TICK_TABLE
    v = raw.get("tick_table", [list(r) for r in dflt])
    if not isinstance(v, list):
        raise QfError("E_SCHEMA", "tick_table: not an array", "tick_table")
    rows = []
    for k, r in enumerate(v):
        if not isinstance(r, list) or len(r) != 2:
            raise QfError("E_SCHEMA", f"tick_table/{k}: not a [floor, tick] pair", "tick_table")
        rows.append((input_dec(r[0], f"tick_table/{k}/0"), input_dec(r[1], f"tick_table/{k}/1")))
    if not rows or rows[0][0] != 0 or any(a[0] >= b[0] for a, b in pairwise(rows)):
        raise QfError("E_INPUT", "tick_table: floors must start at 0 and increase", "tick_table")
    if any(t <= 0 for _, t in rows):
        raise QfError("E_DOMAIN", "tick_table: ticks must be positive", "tick_table")
    return rows


def _tick_at(table: list[tuple[Decimal, Decimal]], price: Decimal) -> Decimal:
    return [t for f, t in table if f <= price][-1]


def _label_eq(raw: dict[str, Any]) -> str:
    src = raw.get("data_source", "SIMULATED")
    if src not in ("SIMULATED", "IEX"):
        raise QfError("E_SCHEMA", "data_source: not SIMULATED or IEX", "data_source")
    return IEX_LABEL if src == "IEX" else EQ_LABEL


@_exact
def eq_round_price(raw: dict[str, Any]) -> dict[str, Any]:
    """`micro.eq.round_price` (HR-81): a buy rounds down to the grid, a sell up."""
    label = _label_eq(raw)
    price = _dec(raw, "price")
    buy = _enum(raw, "side", ("BUY", "SELL")) == "BUY"
    table = _tick_table(raw)
    if price <= 0:
        raise QfError("E_DOMAIN", "price must be positive", "price")
    tick = _tick_at(table, price)
    r = _c((price / tick).to_integral_value(ROUND_FLOOR if buy else ROUND_CEILING) * tick)
    # A sell rounded up across a floor lands on the floor, which is on both grids (HR-81).
    return {"label": label, "price": _at(r, _places(_tick_at(table, r)))}


@_exact
def eq_fee_check(raw: dict[str, Any]) -> dict[str, Any]:
    """`micro.eq.fee_check` (HR-85): the [REGNMS-610] access-fee cap for the price band."""
    label = _label_eq(raw)
    price = _dec(raw, "price")
    fee = _dec(raw, "taker_fee")
    check = _bool(raw, "cap_check", True)
    per_share, frac = FEE_CAP_CURRENT if _current(raw) else FEE_CAP_OLD
    if price <= 0:
        raise QfError("E_DOMAIN", "price must be positive", "price")
    cap = per_share if price >= 1 else _c(frac * price)
    if check and fee > cap:
        raise QfError("E_DOMAIN", "taker_fee above the Rule 610 cap", "taker_fee")
    return {"cap": fmt(cap), "label": label, "taker_fee": fmt(fee)}


def _good(d: date, holidays: set[date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def _add_good(d: date, n: int, ok: Callable[[date], bool]) -> date:
    for _ in range(n):
        d += timedelta(days=1)
        for _ in range(MAX_DAYS):
            if ok(d):
                break
            d += timedelta(days=1)
        else:
            raise QfError("E_DOMAIN", "no business day within ten years", "holidays")
    return d


ROUND_LOTS_CURRENT = (  # amended Reg NMS 242.600(b)(93), source check 2026-11-18 (retry)
    (Decimal(250), 100),
    (Decimal(1000), 40),
    (Decimal(10000), 10),
)


@_exact
def eq_round_lot(raw: dict[str, Any]) -> dict[str, Any]:
    """`micro.eq.round_lot` (HR-82 as dated rule versions): 100 shares under the old regime; under
    the current one 100 up to $250.00, 40 to $1,000.00, 10 to $10,000.00 and 1 above."""
    label = _label_eq(raw)
    price = _dec(raw, "price")
    current = _current(raw)
    if price <= 0:
        raise QfError("E_DOMAIN", "price must be positive", "price")
    lot = 100
    if current:
        lot = next((n for cap, n in ROUND_LOTS_CURRENT if price <= cap), 1)
    return {"label": label, "round_lot": lot}


@_exact
def eq_settle_date(raw: dict[str, Any]) -> dict[str, Any]:
    """Equities settlement date (HR-86): `settle_lag` business days on the supplied calendar."""
    label = _label_eq(raw)
    trade = _date(_need(raw, "trade_date"), "trade_date")
    lag = _int(raw, "settle_lag", 1)
    hol = _dates(raw.get("holidays", []), "holidays")
    if not 0 <= lag <= 30:
        raise QfError("E_DOMAIN", "settle_lag outside 0..30", "settle_lag")
    return {
        "label": label,
        "settle_date": _add_good(trade, lag, lambda d: _good(d, hol)).isoformat(),
    }


# ------------------------------------------------------------------ equity auction (HR-84, HR-96, HR-101)


@_exact
def auction_uncross(raw: dict[str, Any]) -> dict[str, Any]:
    """`exec.sim.auction.uncross`: one price that trades the most shares (auction.md)."""
    label = _label_eq(raw)
    tick = _dec(raw, "tick_size")
    ref = _dec(raw, "ref_price")
    _enum(raw, "phase", ("OPEN", "CLOSE"))
    tie = raw.get("tie_break", "CBOE")
    if tie not in ("CBOE", "IEX"):
        raise QfError("E_SCHEMA", "tie_break: not CBOE or IEX", "tie_break")
    orders = _list(raw, "orders")
    if len(orders) > MAX_ORDERS:
        raise QfError("E_LIMIT", "more than 10,000,000 orders", "orders")
    parsed = []
    nb = ns = 0
    for k, o in enumerate(orders):
        p = f"orders/{k}/"
        o = _obj(o, p[:-1])
        buy = _enum(o, "side", ("BUY", "SELL"), p) == "BUY"
        lim = _need(o, "limit", p)
        limit = None if lim == "MARKET" else input_dec(lim, p + "limit")
        qty = _int(o, "qty", path=p)
        on_close = o.get("on_close", False)
        if not isinstance(on_close, bool):
            raise QfError("E_SCHEMA", p + "on_close: not a boolean", p + "on_close")
        nb, ns = (nb + 1, ns) if buy else (nb, ns + 1)
        oid = o.get("id", f"b{nb}" if buy else f"a{ns}")
        if not isinstance(oid, str):
            raise QfError("E_SCHEMA", p + "id: not a string", p + "id")
        seq = _int(o, "seq", k + 1, p)
        parsed.append((oid, buy, limit, qty, seq, on_close))
    if len({x[0] for x in parsed}) != len(parsed):
        raise QfError("E_INPUT", "duplicate order id", "orders")
    if tick <= 0:
        raise QfError("E_DOMAIN", "tick_size must be positive", "tick_size")
    if ref <= 0:
        raise QfError("E_DOMAIN", "ref_price must be positive", "ref_price")
    for k, (_, _, limit, qty, _, _) in enumerate(parsed):
        if qty <= 0:
            raise QfError("E_DOMAIN", f"orders/{k}: qty must be positive", "orders")
        if limit is not None and (limit <= 0 or limit % tick != 0):
            raise QfError("E_DOMAIN", f"orders/{k}: limit not a positive tick multiple", "orders")
    places = _places(tick)
    buys = sorted(
        (x for x in parsed if x[1]),
        key=lambda x: (0 if x[2] is None else 1, -(x[2] or 0), x[4]),
    )
    sells = sorted(
        (x for x in parsed if not x[1]),
        key=lambda x: (0 if x[2] is None else 1, x[2] or 0, x[4]),
    )
    limits = [x[2] for x in parsed if x[2] is not None]
    best: tuple[Decimal, int, int] | None = None
    if buys and sells and limits:
        lo, hi = min(limits), max(limits)
        n = int((hi - lo) / tick) + 1
        if n > MAX_CANDIDATES:
            raise QfError("E_LIMIT", "more than 1,000,000 candidate prices", "orders")
        cands: list[tuple[Decimal, int, int]] = []
        for i in range(n):
            px = lo + i * tick
            b = sum(x[3] for x in buys if x[2] is None or x[2] >= px)
            s = sum(x[3] for x in sells if x[2] is None or x[2] <= px)
            cands.append((px, min(b, s), b - s))
        vmax = max(v for _, v, _ in cands)
        if vmax > 0:
            keep = [c for c in cands if c[1] == vmax]
            if tie == "IEX":  # nearest the reference-range midpoint (`ref_price`), then higher
                dmin = min(abs(c[0] - ref) for c in keep)
                best = max((c for c in keep if abs(c[0] - ref) == dmin), key=lambda c: c[0])
        if vmax > 0 and tie == "CBOE":
            keep = [c for c in cands if c[1] == vmax]
            imin = min(abs(c[2]) for c in keep)
            keep = [c for c in keep if abs(c[2]) == imin]
            if all(c[2] > 0 for c in keep):
                keep = [max(keep, key=lambda c: c[0])]
            elif all(c[2] < 0 for c in keep):
                keep = [min(keep, key=lambda c: c[0])]
            dmin = min(abs(c[0] - ref) for c in keep)
            best = max((c for c in keep if abs(c[0] - ref) == dmin), key=lambda c: c[0])
    fills: list[dict[str, Any]] = []
    residual: list[dict[str, Any]] = []
    cancelled: list[str] = []
    price = best[0] if best else None
    for side in (buys, sells):
        left = best[1] if best else 0
        for oid, buy, limit, qty, _, on_close in side:
            q = min(qty, left)
            if q > 0:
                assert price is not None
                fills.append(
                    {"id": oid, "price": _at(price, places), "qty": q, "side": "B" if buy else "S"}
                )
                left -= q
            if qty - q > 0:
                if limit is None or on_close:
                    cancelled.append(oid)
                else:
                    residual.append(
                        {
                            "id": oid,
                            "limit": _at(limit, places),
                            "qty": qty - q,
                            "side": "B" if buy else "S",
                        }
                    )
    return {
        "cancelled": cancelled,
        "fills": fills,
        "imbalance": best[2] if best else 0,
        "label": label,
        "price": None if price is None else _at(price, places),
        "residual": residual,
        "volume": best[1] if best else 0,
    }


# ------------------------------------------------------------------ FX spot (H-23)


def _pair(raw: dict[str, Any], key: str = "pair") -> tuple[str, str]:
    p = _str(raw, key)
    base, quote = p[:3], p[3:]
    if len(p) != 6 or base not in CCY_ORDER or quote not in CCY_ORDER or base == quote:
        raise QfError("E_INPUT", f"{key}: not a pair of two listed currencies", key)
    if CCY_ORDER.index(base) > CCY_ORDER.index(quote):
        raise QfError("E_INPUT", f"{key}: base must rank before quote (HR-88)", key)
    return base, quote


def _pip(quote: str) -> Decimal:
    return Decimal("0.01") if quote == "JPY" else Decimal("0.0001")


@_exact
def fx_pip_value(raw: dict[str, Any]) -> dict[str, Any]:
    """FX pip value in the quote currency (HR-87): notional x pip."""
    notional = _dec(raw, "notional")
    _, quote = _pair(raw)
    if notional < 0:
        raise QfError("E_DOMAIN", "notional must not be negative", "notional")
    return {"currency": quote, "label": FX_LABEL, "pip_value": fmt(_c(notional * _pip(quote)))}


@_exact
def fx_spot_date(raw: dict[str, Any]) -> dict[str, Any]:
    """FX spot value date (HR-89): T+2 (T+1 pairs) good days in both currencies, then a USD day."""
    trade = _date(_need(raw, "trade_date"), "trade_date")
    hraw = raw.get("holidays", {})
    if not isinstance(hraw, dict):
        raise QfError("E_SCHEMA", "holidays: not an object of currency -> dates", "holidays")
    hol = {c: _dates(v, f"holidays/{c}") for c, v in hraw.items()}
    t1 = raw.get("t1_pairs", list(T1_PAIRS))
    if not isinstance(t1, list) or not all(isinstance(x, str) for x in t1):
        raise QfError("E_SCHEMA", "t1_pairs: not an array of strings", "t1_pairs")
    base, quote = _pair(raw)
    empty: set[date] = set()

    def both(d: date) -> bool:
        return _good(d, hol.get(base, empty)) and _good(d, hol.get(quote, empty))

    def non_usd(d: date) -> bool:  # a USD-only holiday on T+1 does not stop the count
        return all(_good(d, hol.get(c, empty)) for c in (base, quote) if c != "USD")

    if base + quote in t1:
        d = _add_good(trade, 1, both)
    else:
        d = _add_good(_add_good(trade, 1, non_usd), 1, both)
    d = _add_good(d - timedelta(days=1), 1, lambda x: both(x) and _good(x, hol.get("USD", empty)))
    return {"label": FX_LABEL, "spot_date": d.isoformat()}


@_exact
def fx_stream(raw: dict[str, Any]) -> dict[str, Any]:
    """`exec.sim.fx.stream`: bid rounded down and ask rounded up to the tick (fx-rfq-venue.md)."""
    path = _list(raw, "mid_path")
    hs = _dec(raw, "half_spread_pips")
    pts = []
    for k, x in enumerate(path):
        x = _obj(x, f"mid_path/{k}")
        pts.append((_int(x, "time", path=f"mid_path/{k}/"), _dec(x, "mid", path=f"mid_path/{k}/")))
    _, quote = _pair(raw)
    pip = _pip(quote)
    tick = _dec(raw, "tick", fmt(pip / 10))
    if not pts:
        raise QfError("E_INPUT", "mid_path is empty", "mid_path")
    if tick <= 0 or hs < 0:
        raise QfError("E_DOMAIN", "tick must be positive and half_spread_pips not negative", "tick")
    places = _places(tick)
    out = []
    for t, mid in pts:
        if mid <= 0:
            raise QfError("E_DOMAIN", "mid must be positive", "mid_path")
        bid = (_c(mid - hs * pip) / tick).to_integral_value(ROUND_FLOOR) * tick
        ask = (_c(mid + hs * pip) / tick).to_integral_value(ROUND_CEILING) * tick
        out.append({"ask": _at(ask, places), "bid": _at(bid, places), "mid": fmt(mid), "time": t})
    return {"label": FX_LABEL, "quotes": out}


@_exact
def fx_request(raw: dict[str, Any]) -> dict[str, Any]:
    """`exec.sim.fx.request`: last look (HR-97); strict comparisons, exact decimals."""
    q = _obj(_need(raw, "quote"), "quote")
    bid, ask, qmid = (_dec(q, k, path="quote/") for k in ("bid", "ask", "quote_mid"))
    buy = _enum(raw, "side", ("BUY", "SELL")) == "BUY"
    qty = _dec(raw, "qty")
    after = _dec(raw, "mid_after")
    thr = _dec(raw, "threshold_pips")
    sym = _bool(raw, "symmetric", True)
    prr = _dec(raw, "p_random_reject")
    u = _dec(raw, "u")
    _, quote = _pair(raw)
    if bid > ask:
        raise QfError("E_INPUT", "quote: bid above ask", "quote")
    if qty <= 0 or thr < 0 or not 0 <= prr <= 1 or not 0 <= u < 1:
        raise QfError("E_DOMAIN", "qty > 0, threshold >= 0, p in [0, 1], u in [0, 1)", "u")
    move = _c((after - qmid) / _pip(quote))
    adverse = move if buy else -move
    if (abs(move) if sym else adverse) > thr:
        outcome = "LL_PRICE"
    elif u < prr:
        outcome = "LL_RANDOM"
    else:
        outcome = "FILL"
    price = fmt(ask if buy else bid) if outcome == "FILL" else None
    return {"label": FX_LABEL, "move_pips": fmt(move), "outcome": outcome, "price": price}


# ------------------------------------------------------------------ rates (H-24)


def parse_32nds(text: Any, path: str = "text") -> Decimal:
    """`H-FF[f]` (HR-90; `3` = 3/8 of a 32nd, see the module notes) to its exact value."""
    if not isinstance(text, str):
        raise QfError("E_SCHEMA", f"{path}: not a string", path)
    m = _32NDS.fullmatch(text)
    if m is None:
        raise QfError("E_INPUT", f"{path}: not H-FF[f]", path)
    ff = int(m.group(2))
    if ff > 31:
        raise QfError("E_DOMAIN", f"{path}: 32nds above 31", path)
    return check_range(
        Decimal(int(m.group(1))) + (ff + Decimal(_EIGHTHS[m.group(3)]) / 8) / 32, path
    )


def format_32nds(x: Decimal, resolution: int) -> str:
    if resolution not in RESOLUTIONS:
        raise QfError("E_DOMAIN", "resolution not 32, 64, 128 or 256", "resolution")
    if x < 0 or (x * resolution) % 1 != 0:
        raise QfError("E_DOMAIN", "value not on the requested grid", "value")
    h = int(x)
    eighths = int((x - h) * 256)
    ff, f = divmod(eighths, 8)
    return f"{h}-{ff:02d}{_EIGHTH_TEXT[f]}"


@_exact
def rates_parse_32nds(raw: dict[str, Any]) -> dict[str, Any]:
    """32nds text to a decimal (HR-90)."""
    return {"label": RATES_LABEL, "value": fmt(parse_32nds(_need(raw, "text")))}


@_exact
def rates_format_32nds(raw: dict[str, Any]) -> dict[str, Any]:
    """A decimal to 32nds text at `resolution` parts per point (HR-90)."""
    x = _dec(raw, "value")
    res = _int(raw, "resolution")
    return {"label": RATES_LABEL, "text": format_32nds(x, res)}


def _contract(raw: dict[str, Any]) -> tuple[Decimal, Decimal]:
    c = _obj(raw.get("contract", {"symbol": "ZN"}), "contract")
    sym = c.get("symbol")
    if sym is not None and not isinstance(sym, str):
        raise QfError("E_SCHEMA", "contract/symbol: not a string", "contract/symbol")
    face_d, tick_d = CONTRACTS.get(sym or "", (None, None))
    face = input_dec(c.get("face", face_d), "contract/face")
    tick = input_dec(c.get("tick", tick_d), "contract/tick")
    if face <= 0 or tick <= 0:
        raise QfError("E_DOMAIN", "contract face and tick must be positive", "contract")
    return face, tick


def _tick_value(face: Decimal, tick: Decimal) -> Decimal:
    return _c(face * tick / 100)


@_exact
def rates_tick_value(raw: dict[str, Any]) -> dict[str, Any]:
    """Futures tick value = face x tick / 100 (HR-91)."""
    face, tick = _dec(raw, "face"), _dec(raw, "tick")
    if face <= 0 or tick <= 0:
        raise QfError("E_DOMAIN", "face and tick must be positive", "face")
    return {"label": RATES_LABEL, "tick_value": fmt(_tick_value(face, tick))}


def _price9(p: Decimal) -> str:
    return fmt(p.quantize(Decimal("1E-9"), rounding=ROUND_HALF_EVEN, context=EXACT))


@_exact
def rates_bond_price(raw: dict[str, Any]) -> dict[str, Any]:
    """Coupon bond price on a coupon date, street convention (HR-92), 9 decimals."""
    c, y = _dec(raw, "coupon"), _dec(raw, "yield")
    f, n = _int(raw, "frequency"), _int(raw, "periods")
    if f not in (1, 2, 4, 12):
        raise QfError("E_DOMAIN", "frequency not 1, 2, 4 or 12", "frequency")
    if not 1 <= n <= 1200:
        raise QfError("E_DOMAIN", "periods outside 1..1200", "periods")
    g = 1 + y / f
    if g <= 0:
        raise QfError("E_DOMAIN", "yield at or below -frequency", "yield")
    cpn = 100 * c / f
    p = sum((cpn / g**i for i in range(1, n + 1)), Decimal(0)) + 100 / g**n
    return {"label": RATES_LABEL, "price": _price9(_c(p.quantize(Decimal("1E-30"))))}


@_exact
def rates_bill_price(raw: dict[str, Any]) -> dict[str, Any]:
    """Bill price on the discount basis [UST-BILL]: 100 (1 - d days / 360), 9 decimals."""
    d = _dec(raw, "discount")
    days = _int(raw, "days")
    if not 0 <= days <= 366:
        raise QfError("E_DOMAIN", "days outside 0..366", "days")
    return {"label": RATES_LABEL, "price": _price9(100 * (1 - d * days / 360))}


def _fut_ticks(v: Any, tick: Decimal, path: str) -> int:
    x = parse_32nds(v, path) if isinstance(v, str) and "-" in v[1:] else input_dec(v, path)
    if x < 0 or x % tick != 0:
        raise QfError("E_DOMAIN", f"{path}: price off the contract grid", path)
    return int(x / tick)


@_exact
def fut_to_ticks(raw: dict[str, Any]) -> dict[str, Any]:
    """Futures price (32nds text or decimal) to integer ticks (rates-futures-venue.md)."""
    v = _need(raw, "price")
    _, tick = _contract(raw)
    return {"label": RATES_LABEL, "ticks": _fut_ticks(v, tick, "price")}


@_exact
def fut_to_text(raw: dict[str, Any]) -> dict[str, Any]:
    """Integer ticks to 32nds text at the contract resolution."""
    t = _int(raw, "ticks")
    _, tick = _contract(raw)
    if t < 0:
        raise QfError("E_DOMAIN", "ticks must not be negative", "ticks")
    res = 1 / tick
    if res % 1 != 0 or int(res) not in RESOLUTIONS:
        raise QfError("E_DOMAIN", "contract tick is not 1/32, 1/64, 1/128 or 1/256", "contract")
    return {"label": RATES_LABEL, "text": format_32nds(t * tick, int(res))}


@_exact
def fut_pnl(raw: dict[str, Any]) -> dict[str, Any]:
    """One participant's round trip (HR-102): (sell - buy) ticks x qty x tick value - fees."""
    qty = _int(raw, "qty")
    bp, sp = _need(raw, "buy_price"), _need(raw, "sell_price")
    fee = _dec(raw, "fee_per_contract", "0")
    face, tick = _contract(raw)
    if qty <= 0 or fee < 0:
        raise QfError("E_DOMAIN", "qty must be positive and fee not negative", "qty")
    d = _fut_ticks(sp, tick, "sell_price") - _fut_ticks(bp, tick, "buy_price")
    fees = _c(fee * 2 * qty)
    return {
        "fees": fmt(fees),
        "label": RATES_LABEL,
        "pnl": fmt(_c(d * qty * _tick_value(face, tick) - fees)),
    }


@_exact
def fut_variation(raw: dict[str, Any]) -> dict[str, Any]:
    """Daily variation margin (HR-92, HR-103): previous mark = fill price on the trade day."""
    buy = _enum(raw, "side", ("BUY", "SELL")) == "BUY"
    qty = _int(raw, "qty")
    p0 = _need(raw, "price")
    settles = _list(raw, "settlements")
    face, tick = _contract(raw)
    if not settles:
        raise QfError("E_INPUT", "settlements is empty", "settlements")
    if qty <= 0:
        raise QfError("E_DOMAIN", "qty must be positive", "qty")
    mark = _fut_ticks(p0, tick, "price")
    tv, sign = _tick_value(face, tick), 1 if buy else -1
    out = []
    for k, s in enumerate(settles):
        t = _fut_ticks(s, tick, f"settlements/{k}")
        out.append(fmt(_c((t - mark) * sign * qty * tv)))
        mark = t
    return {"label": RATES_LABEL, "variation_margin": out}


@_exact
def fut_run(raw: dict[str, Any]) -> dict[str, Any]:
    """`exec.sim.fut.run`: the lit engine unchanged on the contract tick grid, plus P&L per trader
    marked at the last trade, minus `fee_per_contract` per contract per side (HR-102)."""
    events = _list(raw, "events")
    fee = _dec(raw, "fee_per_contract", "0")
    face, tick = _contract(raw)
    if fee < 0:
        raise QfError("E_DOMAIN", "fee_per_contract must not be negative", "fee_per_contract")
    trader: dict[str, str] = {}
    mapped = []
    for k, e in enumerate(events):
        e = dict(_obj(e, f"events/{k}"))
        if isinstance(e.get("price"), str):
            e["price"] = fmt(_fut_ticks(e["price"], tick, f"events/{k}/price") * tick)
        if (
            e.get("op") == "NEW"
            and isinstance(e.get("id"), str)
            and isinstance(e.get("trader"), str)
        ):
            trader[e["id"]] = e["trader"]
        mapped.append(e)
    zero = {"maker_rebate": "0", "taker_fee": "0"}
    out = lit_matching.run(fmt(tick), "1", mapped, zero)
    tv = _tick_value(face, tick)
    pos: dict[str, Decimal] = {}
    cash: dict[str, Decimal] = {}
    fees: dict[str, Decimal] = {}
    last: Decimal | None = None
    buyer: dict[str, bool] = {
        e["id"]: e.get("side") == "BUY" for e in mapped if e.get("op") == "NEW"
    }
    for f in out["fills"]:
        p, q = Decimal(f["price"]), Decimal(f["qty"])
        last = p
        for oid in (f["maker_id"], f["taker_id"]):
            t = trader[oid]
            s = 1 if buyer[oid] else -1
            pos[t] = pos.get(t, Decimal(0)) + s * q
            cash[t] = cash.get(t, Decimal(0)) - s * q * p / tick
            fees[t] = _c(fees.get(t, Decimal(0)) + fee * q)
    pnl = {}
    for t in sorted(pos):
        mark = (last or Decimal(0)) / tick
        pnl[t] = fmt(_c((pos[t] * mark + cash[t]) * tv - fees[t]))
    out["fees"] = {t: fmt(v) for t, v in sorted(fees.items())}
    out["pnl"] = pnl
    out["label"] = RATES_LABEL
    return out


guard(globals())
