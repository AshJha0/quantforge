"""`micro.book.rebuild`: market-by-price book rebuild from Kraken-style L2 messages.

Spec: specifications/09-microstructure/order-book.md (rulings HR-11 to HR-17, HR-29, HR-41).
Prices and quantities are exact decimal strings (HR-12); the book keeps the strings as received.
Checksum failures, crossed and locked books are counted and reported, never raised.
"""

import re
import zlib
from datetime import datetime
from decimal import Context, Decimal
from typing import Any

from .errors import QfError
from .finite import guard

DEPTHS = (10, 25, 100, 500, 1000)
MAX_MESSAGES = 50_000_000
MAX_EVENTS = 10_000
_DEC = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_STATS = (
    "messages",
    "snapshots",
    "updates",
    "level_changes",
    "deletes_of_absent_level",
    "truncated_levels",
    "checksum_checked",
    "checksum_failed",
    "checkpoint_checked",
    "checkpoint_failed",
    "crossed",
    "locked",
    "gaps",
    "resyncs",
)


# HR-57: the exact decimal range shared by all four languages. A value c * 10^-s (s >= 0 and as
# small as possible) is in range when |c| < 10^36 and s <= 36; an input string also needs s <= 18.
MAX_DIGITS = 36
MAX_SCALE = 36
MAX_INPUT_SCALE = 18
# Wide enough that every sum, difference and product of in-range values is exact (HR-58).
EXACT = Context(prec=200)


def check_range(x: Decimal, path: str, max_scale: int = MAX_SCALE) -> Decimal:
    """HR-57/HR-58: `x` unchanged if in range, else `E_LIMIT` (never a rounded value)."""
    if x.is_zero():
        return x
    _, digits, exp = x.normalize(EXACT).as_tuple()
    assert isinstance(exp, int)
    n, scale = (len(digits) + exp, 0) if exp >= 0 else (len(digits), -exp)
    if n > MAX_DIGITS or scale > max_scale:
        raise QfError(
            "E_LIMIT",
            f"{path}: decimal outside the exact range (36 digits, {max_scale} decimals; HR-57)",
            path,
        )
    return x


def input_dec(v: Any, path: str) -> Decimal:
    """A decimal-string input (HR-12): `E_SCHEMA` if malformed, `E_LIMIT` if out of range (HR-57)."""
    if not isinstance(v, str) or _DEC.fullmatch(v) is None:
        raise QfError("E_SCHEMA", f"{path}: not a decimal string", path)
    return check_range(Decimal(v), path, MAX_INPUT_SCALE)


_dec = input_dec


def _levels(raw: Any, path: str) -> list[tuple[Decimal, str, Decimal, str]]:
    if not isinstance(raw, list):
        raise QfError("E_SCHEMA", f"{path}: not an array", path)
    out = []
    for k, lv in enumerate(raw):
        if not isinstance(lv, list) or len(lv) != 2:
            raise QfError("E_SCHEMA", f"{path}/{k}: not a [price, qty] pair", path)
        p, q = _dec(lv[0], f"{path}/{k}/0"), _dec(lv[1], f"{path}/{k}/1")
        if p <= 0:
            raise QfError("E_DOMAIN", f"{path}/{k}: price must be positive", path)
        if q < 0:
            raise QfError("E_DOMAIN", f"{path}/{k}: negative quantity", path)
        out.append((p, lv[0], q, lv[1]))
    return out


def _component(text: str, decimals: int) -> str:
    """[KR-CRC]: the value at the pair's precision, decimal point and leading zeros removed."""
    value = Decimal(text)
    fixed = value.quantize(Decimal(1).scaleb(-decimals), context=EXACT)
    if fixed != value:
        raise QfError("E_DOMAIN", f"{text} has more than {decimals} decimals", text)
    return format(fixed, "f").replace(".", "").lstrip("0") or "0"


class _Book:
    def __init__(self, depth: int):
        self.depth = depth
        self.bids: dict[Decimal, str] = {}
        self.asks: dict[Decimal, str] = {}
        self.ptext: dict[Decimal, str] = {}

    def side(self, bid: bool) -> dict[Decimal, str]:
        return self.bids if bid else self.asks

    def ordered(self, bid: bool) -> list[tuple[str, str]]:
        d = self.side(bid)
        return [(self.ptext[p], d[p]) for p in sorted(d, reverse=bid)]

    def truncate(self) -> int:
        dropped = 0
        for bid in (True, False):
            d = self.side(bid)
            for p in sorted(d, reverse=bid)[self.depth :]:
                del d[p]
                dropped += 1
        return dropped

    def checksum_string(self, pdec: int, qdec: int) -> str:
        parts = []
        for bid in (False, True):  # asks ascending, then bids descending
            for p, q in self.ordered(bid)[:10]:
                parts.append(_component(p, pdec) + _component(q, qdec))
        return "".join(parts)


def _instant(text: Any, path: str) -> datetime:
    if not isinstance(text, str):
        raise QfError("E_SCHEMA", f"{path}: not a timestamp", path)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise QfError("E_SCHEMA", f"{path}: not a timestamp", path) from None


def crc32_of(book_string: str) -> int:
    return zlib.crc32(book_string.encode("ascii")) & 0xFFFFFFFF


def rebuild(
    messages: list[Any],
    depth: int,
    price_decimals: int,
    qty_decimals: int,
    checkpoints: list[Any] | None = None,
    emit_checksum_string: bool = False,
) -> dict[str, Any]:
    if depth not in DEPTHS:
        raise QfError("E_DOMAIN", "depth must be one of 10, 25, 100, 500, 1000", "depth")
    if not 0 <= price_decimals <= 18 or not 0 <= qty_decimals <= 18:
        raise QfError("E_DOMAIN", "decimals out of range", "price_decimals")
    if len(messages) > MAX_MESSAGES:
        raise QfError("E_LIMIT", "more than 50,000,000 messages", "messages")
    # Parse everything first: schema and domain errors come before any counting.
    parsed: list[tuple[str, Any, Any, Any, bool, datetime | None]] = []
    for i, m in enumerate(messages):
        if not isinstance(m, dict) or m.get("type") not in ("snapshot", "update", "gap"):
            raise QfError("E_SCHEMA", f"messages/{i}: not a message", "messages")
        if m["type"] == "gap":
            parsed.append(("gap", None, None, None, False, None))
            continue
        cs = m.get("checksum")
        if cs is not None and (
            isinstance(cs, bool) or not isinstance(cs, int) or not 0 <= cs < 2**32
        ):
            raise QfError("E_SCHEMA", f"messages/{i}/checksum: not a u32", "messages")
        t = _instant(m["t"], f"messages/{i}/t") if m.get("t") is not None else None
        parsed.append(
            (
                m["type"],
                _levels(m.get("bids", []), f"messages/{i}/bids"),
                _levels(m.get("asks", []), f"messages/{i}/asks"),
                cs,
                m.get("resubscribe") is True,
                t,
            )
        )
    cps = []
    for k, c in enumerate(checkpoints or []):
        if not isinstance(c, dict):
            raise QfError("E_SCHEMA", f"checkpoints/{k}: not an object", "checkpoints")
        cps.append(
            (
                _instant(c.get("t"), f"checkpoints/{k}/t"),
                _levels(c.get("bids", []), f"checkpoints/{k}/bids"),
                _levels(c.get("asks", []), f"checkpoints/{k}/asks"),
            )
        )

    stats = dict.fromkeys(_STATS, 0)
    events: list[dict[str, Any]] = []
    omitted = 0
    book = _Book(depth)
    live = False
    pending_resync = False
    cp_next = 0

    def event(i: int, kind: str) -> None:
        nonlocal omitted
        if len(events) < MAX_EVENTS:
            events.append({"i": i, "kind": kind})
        else:
            omitted += 1

    def checkpoint(i: int, upto: datetime | None) -> None:
        nonlocal cp_next
        while cp_next < len(cps) and (upto is None or cps[cp_next][0] < upto):
            _, cb, ca = cps[cp_next]
            cp_next += 1
            stats["checkpoint_checked"] += 1
            ok = True
            for bid, lv in ((True, cb), (False, ca)):
                ours = sorted(book.side(bid).items(), reverse=bid)[: len(lv)]
                want = sorted(((p, q) for p, _, q, _ in lv), reverse=bid)
                if len(ours) != len(want) or any(
                    a[0] != b[0] or Decimal(a[1]) != b[1] for a, b in zip(ours, want)
                ):
                    ok = False
            if not ok:
                stats["checkpoint_failed"] += 1
                event(i, "CHECKPOINT_FAIL")

    for i, (kind, bids, asks, cs, resub, t) in enumerate(parsed):
        if kind == "gap":
            stats["gaps"] += 1
            book = _Book(depth)
            live = False
            event(i, "GAP")
            continue
        if cps and t is not None:
            checkpoint(i - 1, t)
        stats["messages"] += 1
        if kind == "snapshot":
            stats["snapshots"] += 1
            if resub and pending_resync:
                stats["resyncs"] += 1
            pending_resync = False
            book = _Book(depth)
            for bid, lv in ((True, bids), (False, asks)):
                for p, ptxt, q, qtxt in lv:
                    if q != 0:
                        book.side(bid)[p] = qtxt
                        book.ptext[p] = ptxt
            live = True
        else:
            stats["updates"] += 1
            if not live:
                event(i, "UPDATE_BEFORE_SNAPSHOT")
                continue
            for bid, lv in ((True, bids), (False, asks)):
                d = book.side(bid)
                for p, ptxt, q, qtxt in lv:
                    stats["level_changes"] += 1
                    if q == 0:
                        if p in d:
                            del d[p]
                        else:
                            stats["deletes_of_absent_level"] += 1
                    else:
                        d[p] = qtxt
                        book.ptext[p] = ptxt
        stats["truncated_levels"] += book.truncate()
        if cs is not None:
            stats["checksum_checked"] += 1
            if crc32_of(book.checksum_string(price_decimals, qty_decimals)) != cs:
                stats["checksum_failed"] += 1
                pending_resync = True
                event(i, "CHECKSUM_FAIL")
        if book.bids and book.asks:
            bb, ba = max(book.bids), min(book.asks)
            if bb > ba:
                stats["crossed"] += 1
                event(i, "CROSSED")
            elif bb == ba:
                stats["locked"] += 1
                event(i, "LOCKED")
    if cps:
        checkpoint(len(parsed) - 1, None)

    final = book.checksum_string(price_decimals, qty_decimals)
    out: dict[str, Any] = {
        "book": {
            "bids": [list(x) for x in book.ordered(True)],
            "asks": [list(x) for x in book.ordered(False)],
        },
        "stats": stats,
        "events": events,
        "crc32": crc32_of(final),
    }
    if omitted:
        out["events_omitted"] = omitted
    if emit_checksum_string:
        out["checksum_string"] = final
    return out


guard(globals())
