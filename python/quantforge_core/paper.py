"""Paper trading: hash-chained ledger, book (positions, cash, financing), daily P&L explain and
pre-trade checks (specifications/10-execution/paper-trading.md, proposed rulings HR-42 to HR-55).

Nothing here talks to a network or a venue: no live order can be placed (HR-42). Fills come
from the simulated venues; their wiring is not implemented yet (HR-47)."""

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from .errors import QfError
from .finite import guard

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


def dec(value: Any, name: str) -> Decimal:
    """A decimal input given as a string (HR-44). Floats are refused so they never reach the ledger."""
    if isinstance(value, (bool, float)):
        raise QfError("E_INPUT", f"{name} must be a decimal string", name)
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        raise QfError("E_PARSE", f"{name} is not a decimal", name) from None
    if not d.is_finite():
        raise QfError(
            "E_DOMAIN", f"{name} is not finite", name
        )  # E1: a non-finite input is E_DOMAIN
    return d


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


def verify(text: str) -> dict[str, Any]:
    """`paper.ledger.verify`: never repairs; reports the first bad record."""
    prev = GENESIS
    lines = text.splitlines()
    for n, line in enumerate(lines):

        def bad(reason: str, seq: int = n) -> dict[str, Any]:
            return {"ok": False, "records": seq, "first_bad_seq": seq, "reason": reason}

        try:
            rec = json.loads(line)
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

    def apply_fill(self, symbol: str, side: str, quantity: Any, price: Any, fee: Any = "0") -> None:
        """`paper.book.apply_fill`, average cost (HR-50)."""
        s = side_sign(side)
        q, p, f = dec(quantity, "quantity"), dec(price, "price"), dec(fee, "fee")
        if q <= 0 or p <= 0:
            raise QfError("E_DOMAIN", "quantity and price must be positive", "quantity")
        self.cash -= s * q * p + f
        self.fees += f
        pos = self.pos(symbol)
        if pos.n == 0 or (pos.n > 0) == (s > 0):
            pos.c = (abs(pos.n) * pos.c + q * p) / (abs(pos.n) + q)
            pos.n += s * q
            return
        closed = min(q, abs(pos.n))
        sign = 1 if pos.n > 0 else -1
        self.realised += closed * (p - pos.c) * sign
        pos.n += s * q
        if pos.n == 0:
            pos.c = Decimal(0)
        elif (pos.n > 0) != (sign > 0):
            pos.c = p

    def nav(self, marks: Mapping[str, Any]) -> Decimal:
        return self.cash + sum(
            (
                p.n * dec(marks[sym], f"marks.{sym}")
                for sym, p in self.positions.items()
                if p.n != 0
            ),
            Decimal(0),
        )


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
    interest = (cash * r * days / 365).quantize(CENT, ROUND_HALF_EVEN)
    smv = sum(
        (-dec(n, "n") * dec(px, "close") for n, px in shorts_open if dec(n, "n") < 0), Decimal(0)
    )
    borrow = -(smv * dec(borrow_rate, "borrow_rate") * days / 365).quantize(CENT, ROUND_HALF_EVEN)
    return {"interest": interest, "borrow": borrow, "financing": interest + borrow}


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
    total = market + trading + fees + fin["financing"]
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
        "PRICE_BAND": limit is not None and abs(limit - p_ref) / p_ref > band,
        "MAX_NOTIONAL": q * p_chk > dec(limits["max_notional"], "max_notional"),
        "MAX_POSITION": abs(after) > dec(limits["max_abs_position"], "max_abs_position"),
        "NO_SHORT": not limits.get("allow_short", True) and after < 0,
        "INSUFFICIENT_CASH": s > 0 and q * p_chk > dec(cash, "cash"),
    }
    reasons = [r for r in REASONS if failed[r]]
    return {"accepted": not reasons, "reasons": reasons, "label": LABEL}


guard(globals())  # E1: NaN and infinity at a public input are E_DOMAIN, checked first
