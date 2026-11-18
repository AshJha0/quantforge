"""Paper trading: hash-chained ledger, book (positions, cash, financing), daily P&L explain and
pre-trade checks (specifications/10-execution/paper-trading.md, proposed rulings HR-42 to HR-55).

Nothing here talks to a network or a venue: no live order can be placed (HR-42). Fills come
from the simulated venues through `paper_fills.py` (HR-47)."""

import functools
import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from typing import Any

from .errors import QfError
from .finite import guard
from .lit_matching import fmt
from .order_book import EXACT, MAX_INPUT_SCALE, check_range

LABEL = "crypto venue; simulated"
CEILING = "Paper trading on free data; simulated fills; no evidence of tradable profitability."
GENESIS = "0" * 64
KINDS = ("ORDER", "REJECT", "FILL", "CANCEL", "EOD", "TCA")
SIDES = {"BUY": 1, "SELL": -1}
TYPES = ("LIMIT", "MARKET", "IOC", "FOK", "ICEBERG", "POST_ONLY", "PEG_MID", "PEG_PRIMARY")
REASONS = (
    "KILL_SWITCH",
    "MAX_ORDERS",
    "MAX_QTY",
    "PRICE_BAND",
    "MAX_NOTIONAL",
    "MAX_POSITION",
    "NO_SHORT",
    "INSUFFICIENT_CASH",
)
CENT = Decimal("0.01")
COST_STEP = Decimal(1).scaleb(-MAX_INPUT_SCALE)  # average cost is kept to 18 decimals (HR-77)


def exact[**P, T](f: Callable[P, T]) -> Callable[P, T]:
    """Runs `f` in the 200-digit context (HR-58): no in-range sum, difference or product rounds."""

    @functools.wraps(f)
    def run(*args: P.args, **kwargs: P.kwargs) -> T:
        with localcontext(EXACT):
            return f(*args, **kwargs)

    return run


def rng(x: Decimal, name: str) -> Decimal:
    """A computed value must be in the HR-57 range (36 digits, 36 decimals), else E_LIMIT (HR-77)."""
    return check_range(x, name)


def dec(value: Any, name: str) -> Decimal:
    """A decimal input given as a string (HR-44). Floats are refused so they never reach the ledger."""
    if isinstance(value, (bool, float)):
        raise QfError("E_INPUT", f"{name} must be a decimal string", name)
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        raise QfError("E_PARSE", f"{name} is not a decimal", name) from None
    if not d.is_finite():  # HR-12, ruling F-2a: a non-finite token is a malformed decimal
        raise QfError("E_SCHEMA", f"{name} is not a finite decimal", name)
    return check_range(d, name)


def side_sign(side: str) -> int:
    if side not in SIDES:
        raise QfError("E_INPUT", f"unknown side {side!r}", "side")
    return SIDES[side]


# ---------------------------------------------------------------- ledger (HR-43, HR-45, HR-46)


def canonical(record: Mapping[str, Any]) -> bytes:
    """Canonical bytes of a record without its hash (HR-45)."""

    def check(v: Any, path: str) -> None:
        if isinstance(v, dict):
            for k, x in v.items():
                check(x, f"{path}.{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                check(x, f"{path}[{i}]")
        elif isinstance(v, (bool, float)) or (isinstance(v, int) and path != ".seq"):
            raise QfError("E_INPUT", f"{path} must be a string (only seq is an integer)", path)

    body = {k: v for k, v in record.items() if k != "hash"}
    check(body, "")
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def record_hash(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(record)).hexdigest()


class Ledger:
    """Append-only hash-chained ledger held as JSON Lines text."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.head = GENESIS

    def append(self, kind: str, ts: str, body: Mapping[str, Any]) -> dict[str, Any]:
        if kind not in KINDS:
            raise QfError("E_INPUT", f"unknown kind {kind!r}", "kind")
        rec: dict[str, Any] = {
            "seq": len(self.lines),
            "ts": ts,
            "kind": kind,
            "label": LABEL,
            "body": dict(body),
            "prev": self.head,
        }
        rec["hash"] = record_hash(rec)
        self.lines.append(json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        self.head = rec["hash"]
        return rec

    def text(self) -> str:
        return "".join(line + "\n" for line in self.lines)


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A ledger line with a repeated key is PARSE (HR-78): last-wins would hide an edit."""
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key {k!r}")
        out[k] = v
    return out


def verify(text: str) -> dict[str, Any]:
    """`paper.ledger.verify`: never repairs; reports the first bad record."""
    prev = GENESIS
    lines = text.splitlines()
    for n, line in enumerate(lines):

        def bad(reason: str, seq: int = n) -> dict[str, Any]:
            return {"ok": False, "records": seq, "first_bad_seq": seq, "reason": reason}

        try:
            rec = json.loads(line, object_pairs_hook=_no_duplicates)
            if not isinstance(rec, dict):
                return bad("PARSE")
            stored = rec["hash"]
            computed = record_hash(rec)
        except ValueError, KeyError, QfError:
            return bad("PARSE")
        if rec.get("seq") != n:
            return bad("SEQ")
        if computed != stored:
            return bad("HASH")
        if rec.get("prev") != prev:
            return bad("LINK")
        if rec.get("label") != LABEL:
            return bad("LABEL")
        prev = stored
    return {"ok": True, "records": len(lines), "first_bad_seq": None, "reason": None, "head": prev}


# ---------------------------------------------------------------- book (HR-50, HR-52, HR-53)


@dataclass
class Position:
    n: Decimal = Decimal(0)
    c: Decimal = Decimal(0)


@dataclass
class Book:
    cash: Decimal
    positions: dict[str, Position] = field(default_factory=dict)
    realised: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)

    def pos(self, symbol: str) -> Position:
        return self.positions.setdefault(symbol, Position())

    @exact
    def apply_fill(self, symbol: str, side: str, quantity: Any, price: Any, fee: Any = "0") -> None:
        """`paper.book.apply_fill`, average cost (HR-50)."""
        s = side_sign(side)
        q, p, f = dec(quantity, "quantity"), dec(price, "price"), dec(fee, "fee")
        if q <= 0 or p <= 0:
            raise QfError("E_DOMAIN", "quantity and price must be positive", "quantity")
        notional = rng(q * p, "notional")
        self.cash = rng(self.cash - rng(s * notional + f, "cash_flow"), "cash")
        self.fees = rng(self.fees + f, "fees")
        pos = self.pos(symbol)
        if pos.n == 0 or (pos.n > 0) == (s > 0):
            basis = rng(rng(abs(pos.n) * pos.c, "basis") + notional, "basis")
            # HR-77: the one division of the book, rounded half-even to 18 decimals
            pos.c = rng(
                (basis / rng(abs(pos.n) + q, "position")).quantize(COST_STEP, ROUND_HALF_EVEN),
                "avg_cost",
            )
            pos.n = rng(pos.n + s * q, "position")
            return
        closed = min(q, abs(pos.n))
        sign = 1 if pos.n > 0 else -1
        self.realised = rng(
            self.realised + rng(closed * rng(p - pos.c, "pnl") * sign, "pnl"), "realised"
        )
        pos.n = rng(pos.n + s * q, "position")
        if pos.n == 0:
            pos.c = Decimal(0)
        elif (pos.n > 0) != (sign > 0):
            pos.c = p

    @exact
    def nav(self, marks: Mapping[str, Any]) -> Decimal:
        return rng(
            self.cash
            + sum(
                (
                    rng(p.n * dec(marks[sym], f"marks.{sym}"), "market_value")
                    for sym, p in self.positions.items()
                    if p.n != 0
                ),
                Decimal(0),
            ),
            "nav",
        )


@exact
def financing(
    cash_open: Any,
    shorts_open: Iterable[tuple[Any, Any]],
    days: int,
    cash_rate: Any = "0",
    debit_rate: Any = "0",
    borrow_rate: Any = "0",
) -> dict[str, Decimal]:
    """Interest on opening cash and borrow on opening short market value, ACT/365 (HR-52).
    `shorts_open` is (signed position, previous close) per symbol; only negative positions count."""
    if days < 0:
        raise QfError("E_DOMAIN", "days must be >= 0", "days")
    cash = dec(cash_open, "cash_open")
    r = dec(cash_rate, "cash_rate") if cash >= 0 else dec(debit_rate, "debit_rate")
    interest = (rng(cash * r * days, "interest") / 365).quantize(CENT, ROUND_HALF_EVEN)
    smv = sum(
        (-dec(n, "n") * dec(px, "close") for n, px in shorts_open if dec(n, "n") < 0), Decimal(0)
    )
    smv = rng(smv, "short_value")
    borrow = -(rng(smv * dec(borrow_rate, "borrow_rate") * days, "borrow") / 365).quantize(
        CENT, ROUND_HALF_EVEN
    )
    return {
        "interest": interest,
        "borrow": borrow,
        "financing": rng(interest + borrow, "financing"),
    }


@exact
def end_of_day(
    book: Book,
    fills: Sequence[Mapping[str, Any]],
    prev_marks: Mapping[str, Any],
    marks: Mapping[str, Any],
    days: int = 1,
    cash_rate: Any = "0",
    debit_rate: Any = "0",
    borrow_rate: Any = "0",
) -> dict[str, Any]:
    """`paper.book.end_of_day` with `paper.pnl.explain`: applies the day's fills, posts financing on
    the opening balances and returns the explain. total equals the NAV change exactly (HR-53)."""
    opening = {sym: p.n for sym, p in book.positions.items() if p.n != 0}
    nav0 = book.nav(prev_marks) if opening else book.cash
    fin = financing(
        book.cash,
        [(n, prev_marks[s]) for s, n in opening.items()],
        days,
        cash_rate,
        debit_rate,
        borrow_rate,
    )
    market = sum(
        (n * (dec(marks[s], "mark") - dec(prev_marks[s], "prev_mark")) for s, n in opening.items()),
        Decimal(0),
    )
    trading = Decimal(0)
    fees = Decimal(0)
    for f in fills:
        sgn = side_sign(f["side"])
        q, p = dec(f["quantity"], "quantity"), dec(f["price"], "price")
        trading += sgn * q * (dec(marks[f["symbol"]], "mark") - p)
        fees -= dec(f.get("fee", "0"), "fee")
        book.apply_fill(f["symbol"], f["side"], f["quantity"], f["price"], f.get("fee", "0"))
    book.cash += fin["financing"]
    market, trading, fees = rng(market, "market"), rng(trading, "trading"), rng(fees, "fees")
    book.cash = rng(book.cash, "cash")
    total = rng(market + trading + fees + fin["financing"], "total")
    nav1 = book.nav(marks)
    if total != nav1 - nav0:  # HR-53: a residual is a defect
        raise AssertionError(f"explain residual {nav1 - nav0 - total}")
    return {
        "market": market,
        "trading": trading,
        "fees": fees,
        "financing": fin["financing"],
        "interest": fin["interest"],
        "borrow": fin["borrow"],
        "total": total,
        "nav": nav1,
        "label": LABEL,
        "ceiling": CEILING,
    }


# ---------------------------------------------------------------- pre-trade checks (HR-42, HR-49)


@exact
def pretrade_check(
    order: Mapping[str, Any],
    ref_price: Any,
    position: Any,
    cash: Any,
    orders_today: int,
    limits: Mapping[str, Any],
) -> dict[str, Any]:
    """`paper.pretrade.check`: deterministic; all checks run, reasons in the HR-49 order."""
    mode = order.get("mode", "simulated")
    if mode != "simulated":
        raise QfError("E_UNSUPPORTED_OPERATION", "paper trading never places live orders", "mode")
    s = side_sign(order.get("side", ""))
    otype = order.get("type")
    if otype not in TYPES:
        raise QfError("E_INPUT", f"unknown type {otype!r}", "type")
    q = dec(order["quantity"], "quantity")
    p_ref = dec(ref_price, "ref_price")
    band = dec(limits["price_band"], "price_band")
    if q <= 0 or p_ref <= 0:
        raise QfError("E_DOMAIN", "quantity and reference price must be positive", "quantity")
    if otype == "MARKET":
        limit = None
        p_chk = p_ref * (1 + s * band)
    else:
        if "limit_price" not in order:
            raise QfError("E_SCHEMA", "limit_price is missing", "limit_price")
        limit = dec(order["limit_price"], "limit_price")
        if limit <= 0:
            raise QfError("E_DOMAIN", "limit price must be positive", "limit_price")
        p_chk = limit
    after = dec(position, "position") + s * q
    failed = {
        "KILL_SWITCH": bool(limits.get("kill_switch", False)),
        "MAX_ORDERS": orders_today >= int(limits["max_orders_per_day"]),
        "MAX_QTY": q > dec(limits["max_order_qty"], "max_order_qty"),
        # cross-multiplied, so no division (HR-77): |limit - P_ref| / P_ref > band
        "PRICE_BAND": limit is not None
        and rng(abs(limit - p_ref), "band") > rng(band * p_ref, "band"),
        "MAX_NOTIONAL": rng(q * p_chk, "notional") > dec(limits["max_notional"], "max_notional"),
        "MAX_POSITION": abs(after) > dec(limits["max_abs_position"], "max_abs_position"),
        "NO_SHORT": not limits.get("allow_short", True) and after < 0,
        "INSUFFICIENT_CASH": s > 0 and q * p_chk > dec(cash, "cash"),
    }
    reasons = [r for r in REASONS if failed[r]]
    return {"accepted": not reasons, "reasons": reasons, "label": LABEL}


# ---------------------------------------------------------------- CLI cases (cli-contract.md, paper.*)
# One symbol per case; outputs are decimal strings (HR-44) with the HR-43 label.

_SYM = "S"


def _req(m: Mapping[str, Any], key: str, where: str) -> Any:
    if m.get(key) is None:
        raise QfError("E_SCHEMA", f"{where}{key} is missing", where + key)
    return m[key]


def input_decimal(v: Any, name: str) -> Decimal:
    """A decimal input over the CLI must be a JSON string (HR-12, HR-44) with at most 18 decimals and
    36 digits (HR-57 input range), else E_LIMIT (HR-77)."""
    if not isinstance(v, str):
        raise QfError("E_SCHEMA", f"{name} must be a decimal string", name)
    return check_range(dec(v, name), name, MAX_INPUT_SCALE)


def _fill_list(fills: Sequence[Any]) -> list[dict[str, Any]]:
    out = []
    for k, f in enumerate(fills):
        w = f"fills/{k}/"
        if not isinstance(f, Mapping):
            raise QfError("E_SCHEMA", f"{w} is not an object", w)
        side = _req(f, "side", w)
        side_sign(side)
        q, p = (
            input_decimal(_req(f, "quantity", w), w + "quantity"),
            input_decimal(_req(f, "price", w), w + "price"),
        )
        fee = input_decimal(f.get("fee", "0"), w + "fee")
        if q <= 0 or p <= 0:
            raise QfError("E_DOMAIN", "quantity and price must be positive", w + "quantity")
        out.append(
            {"symbol": _SYM, "side": side, "quantity": fmt(q), "price": fmt(p), "fee": fmt(fee)}
        )
    return out


@exact
def book_case(
    fills: Sequence[Any], cash: Any = None, position: Any = "0", avg_cost: Any = "0"
) -> dict[str, Any]:
    """`paper.book.apply_fill`: fills in order on one symbol (HR-50). Without `cash` the output
    gives `cash_delta` (the change of cash) instead of `cash`."""
    start = Decimal(0) if cash is None else input_decimal(cash, "cash")
    book = Book(cash=start)
    pos = book.pos(_SYM)
    pos.n, pos.c = input_decimal(position, "position"), input_decimal(avg_cost, "avg_cost")
    for f in _fill_list(fills):
        book.apply_fill(_SYM, f["side"], f["quantity"], f["price"], f["fee"])
    out = {
        "position": fmt(pos.n),
        "avg_cost": fmt(pos.c),
        "realised": fmt(book.realised),
        "fees": fmt(book.fees),
        "label": LABEL,
    }
    out["cash_delta" if cash is None else "cash"] = fmt(book.cash)
    return out


@exact
def day_case(
    cash_open: Any,
    fills: Sequence[Any] = (),
    position_open: Any = "0",
    avg_cost_open: Any = None,
    prev_close: Any = None,
    close: Any = None,
    days: int = 1,
    cash_rate: Any = "0",
    debit_rate: Any = "0",
    borrow_rate: Any = "0",
) -> dict[str, Any]:
    """`paper.book.end_of_day` with `paper.pnl.explain` for one symbol (HR-51 to HR-53)."""
    cash = input_decimal(cash_open, "cash_open")
    n = input_decimal(position_open, "position_open")
    fl = _fill_list(fills)
    if n != 0 and prev_close is None:
        raise QfError("E_SCHEMA", "prev_close is missing (open position)", "prev_close")
    if (n != 0 or fl) and close is None:
        raise QfError("E_SCHEMA", "close is missing (position or fills)", "close")
    prev = None if prev_close is None else input_decimal(prev_close, "prev_close")
    px = None if close is None else input_decimal(close, "close")
    for name, v in (("prev_close", prev), ("close", px)):
        if v is not None and v <= 0:
            raise QfError("E_DOMAIN", f"{name} must be positive", name)
    rates = {
        "cash_rate": fmt(input_decimal(cash_rate, "cash_rate")),
        "debit_rate": fmt(input_decimal(debit_rate, "debit_rate")),
        "borrow_rate": fmt(input_decimal(borrow_rate, "borrow_rate")),
    }
    book = Book(cash=cash)
    pos = book.pos(_SYM)
    pos.n = n
    if avg_cost_open is not None:
        pos.c = input_decimal(avg_cost_open, "avg_cost_open")
    elif prev is not None:
        pos.c = prev
    prev_marks = {} if prev is None else {_SYM: fmt(prev)}
    marks = {} if px is None else {_SYM: fmt(px)}
    nav_open = cash + (n * prev if n != 0 and prev is not None else 0)
    e = end_of_day(book, fl, prev_marks, marks, days, **rates)
    out = {
        "market": fmt(e["market"]),
        "trading": fmt(e["trading"]),
        "fees": fmt(e["fees"]),
        "financing": fmt(e["financing"]),
        "cash_interest": fmt(e["interest"]),
        "short_borrow": fmt(e["borrow"]),
        "total": fmt(e["total"]),
        "position": fmt(pos.n),
        "cash_close": fmt(book.cash),
        "label": LABEL,
    }
    if px is not None:
        out["nav_open"] = fmt(nav_open)
        out["nav_close"] = fmt(e["nav"])
    return out


@exact
def pretrade_case(
    order: Mapping[str, Any],
    ref_price: Any,
    position: Any,
    cash: Any,
    orders_today: int,
    limits: Mapping[str, Any],
) -> dict[str, Any]:
    """`paper.pretrade.check` over the CLI: schema first, then HR-42, then the checks."""
    for k in ("side", "type", "quantity"):
        _req(order, k, "order/")
    input_decimal(order["quantity"], "order/quantity")
    if order.get("limit_price") is not None:
        input_decimal(order["limit_price"], "order/limit_price")
    for k in ("max_order_qty", "max_notional", "max_abs_position", "price_band"):
        input_decimal(_req(limits, k, "limits/"), "limits/" + k)
    mo = _req(limits, "max_orders_per_day", "limits/")
    if isinstance(mo, bool) or not isinstance(mo, int):
        raise QfError("E_SCHEMA", "limits/max_orders_per_day must be an integer", "limits")
    for k in ("kill_switch", "allow_short"):
        if k in limits and not isinstance(limits[k], bool):
            raise QfError("E_SCHEMA", f"limits/{k} must be a boolean", "limits/" + k)
    r = pretrade_check(
        order,
        input_decimal(ref_price, "ref_price"),
        input_decimal(position, "position"),
        input_decimal(cash, "cash"),
        orders_today,
        limits,
    )
    return {"accepted": r["accepted"], "reasons": r["reasons"], "label": LABEL}


NONFINITE_TOKENS = ("NaN", "Infinity", "-Infinity")


def _no_nonfinite(v: Any, path: str) -> None:
    """Body values are decimal strings (HR-44): a non-finite token is E_SCHEMA (HR-12, F-2a)."""
    if isinstance(v, Mapping):
        for k, x in v.items():
            _no_nonfinite(x, f"{path}/{k}")
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _no_nonfinite(x, f"{path}/{i}")
    elif isinstance(v, str) and v in NONFINITE_TOKENS:
        raise QfError("E_SCHEMA", f"{path} is not a finite decimal", path)


@exact
def record_case(seq: int, ts: str, kind: str, body: Mapping[str, Any], prev: str) -> dict[str, Any]:
    """`paper.ledger.append` for one record: its canonical bytes (HR-45), hash and full record."""
    if kind not in KINDS:
        raise QfError("E_INPUT", f"unknown kind {kind!r}", "kind")
    if seq < 0:
        raise QfError("E_DOMAIN", "seq must be >= 0", "seq")
    _no_nonfinite(body, "body")
    rec: dict[str, Any] = {
        "seq": seq,
        "ts": ts,
        "kind": kind,
        "label": LABEL,
        "body": dict(body),
        "prev": prev,
    }
    raw = canonical(rec)
    rec["hash"] = hashlib.sha256(raw).hexdigest()
    return {
        "canonical_bytes": raw.decode("ascii"),
        "hash": rec["hash"],
        "record": rec,
        "label": LABEL,
    }


def verify_case(text: str) -> dict[str, Any]:
    """`paper.ledger.verify` with a fixed output shape: `head` is null unless ok."""
    r = verify(text)
    return {
        "ok": r["ok"],
        "records": r["records"],
        "first_bad_seq": r["first_bad_seq"],
        "reason": r["reason"],
        "head": r.get("head"),
        "label": LABEL,
    }


guard(globals())  # E1: NaN and infinity at a public input are E_DOMAIN, checked first
