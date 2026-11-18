"""`exec.sim.lit.run`: a simulated lit matching engine (price-time priority).

Spec: specifications/10-execution/lit-matching.md (rulings HR-25 to HR-31). Simulated venue;
not a real exchange. Prices, quantities and fees are exact decimals (HR-12); the engine is
deterministic, so the same event list always gives the same output.

Priority within a price (HR-27): displayed quantity by `seq`, then non-displayed `PEG_MID`
orders by `seq`. An iceberg's hidden quantity is refreshed into a new displayed slice at the
back of the queue (new `seq`) as soon as its shown part is filled ([CME-FIFO]), so hidden
quantity always trades after every displayed order that was ahead of the refresh.
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

from .errors import QfError
<<<<<<< HEAD
from .order_book import EXACT, check_range, input_dec
=======
from .finite import guard
>>>>>>> h-darksor

LABEL = "simulated venue; not a real exchange"
MAX_EVENTS = 10_000_000
TYPES = ("LIMIT", "MARKET", "IOC", "FOK", "ICEBERG", "POST_ONLY", "PEG_MID", "PEG_PRIMARY")
PEGS = ("PEG_MID", "PEG_PRIMARY")


def fmt(x: Decimal) -> str:
    """No exponent, no trailing zeros, "0" for zero (HR-12)."""
    if x == 0:
        return "0"
    s = format(x.normalize(), "f")
    return s


_dec = input_dec


def _c(x: Decimal) -> Decimal:
    """Every sum, difference and product is range-checked (HR-58)."""
    return check_range(x, "value")


@dataclass
class Order:
    id: str
    trader: str
    buy: bool
    type: str
    cap: Decimal | None  # the limit; for pegs the cap
    price: Decimal | None  # current resting price; None for an unpriced peg
    display: Decimal
    hidden: Decimal
    slice: Decimal  # iceberg display size
    seq: int

    def open(self) -> Decimal:
        return _c(self.display + self.hidden)


class _Engine:
    def __init__(self, tick: Decimal, lot: Decimal, taker_fee: Decimal, maker_rebate: Decimal):
        self.tick, self.lot = tick, lot
        self.taker_fee, self.maker_rebate = taker_fee, maker_rebate
        self.resting: dict[str, Order] = {}
        self.seen: set[str] = set()
        self.seq = 0
        self.fills: list[dict[str, Any]] = []
        self.rejects: list[dict[str, str]] = []
        self.cancelled: list[dict[str, str]] = []
        self.fees: dict[str, Decimal] = {}
        self.cons: dict[str, dict[str, Decimal]] = {}

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def on_grid(self, x: Decimal, unit: Decimal, what: str) -> None:
        if x % unit != 0:
            raise QfError("E_DOMAIN", f"{what} {x} is not a multiple of {unit}", what)

    # ---- book queries
    def side(self, buy: bool) -> list[Order]:
        return [o for o in self.resting.values() if o.buy == buy and o.price is not None]

    def best(
        self, buy: bool, exclude_mid: bool = False, exclude: str | None = None
    ) -> Decimal | None:
        ps = [
            o.price
            for o in self.side(buy)
            if o.price is not None and not (exclude_mid and o.type == "PEG_MID") and o.id != exclude
        ]
        if not ps:
            return None
        return max(ps) if buy else min(ps)

    def marketable(self, buy: bool, limit: Decimal | None, price: Decimal) -> bool:
        return limit is None or (price <= limit if buy else price >= limit)

    def available(self, buy: bool, limit: Decimal | None) -> Decimal:
        total = Decimal(0)
        for o in self.side(not buy):
            if o.price is not None and self.marketable(buy, limit, o.price):
                total = _c(total + o.open())
        return total

    def queue_at(self, buy_side: bool, price: Decimal) -> list[Order]:
        at = [o for o in self.side(buy_side) if o.price == price]
        shown = sorted((o for o in at if o.type != "PEG_MID"), key=lambda o: o.seq)
        mid = sorted((o for o in at if o.type == "PEG_MID"), key=lambda o: o.seq)
        return shown + mid

    # ---- matching
    def match(self, taker: Order, limit: Decimal | None, qty: Decimal) -> Decimal:
        """Trades `qty` of the taker against the opposite side; returns the unfilled rest."""
        while qty > 0:
            p = self.best(not taker.buy)
            if p is None or not self.marketable(taker.buy, limit, p):
                break
            maker = self.queue_at(not taker.buy, p)[0]
            avail = maker.hidden if maker.type == "PEG_MID" else maker.display
            q = min(qty, avail)
            self.trade(taker, maker, p, q)
            qty = _c(qty - q)
            if maker.type == "PEG_MID":
                maker.hidden = _c(maker.hidden - q)
            else:
                maker.display = _c(maker.display - q)
                if maker.display == 0 and maker.hidden > 0:  # iceberg refresh, back of the queue
                    maker.display = min(maker.slice, maker.hidden)
                    maker.hidden = _c(maker.hidden - maker.display)
                    maker.seq = self.next_seq()
            if maker.open() == 0:
                del self.resting[maker.id]
        return qty

    def trade(self, taker: Order, maker: Order, price: Decimal, q: Decimal) -> None:
        self.fills.append(
            {
                "taker_id": taker.id,
                "maker_id": maker.id,
                "price": fmt(price),
                "qty": fmt(q),
                "seq": len(self.fills) + 1,
            }
        )
        notional = _c(price * q)
        self.fees[taker.trader] = _c(
            self.fees.get(taker.trader, Decimal(0)) + _c(self.taker_fee * notional)
        )
        self.fees[maker.trader] = _c(
            self.fees.get(maker.trader, Decimal(0)) - _c(self.maker_rebate * notional)
        )
        self.cons[taker.id]["filled"] = _c(self.cons[taker.id]["filled"] + q)
        self.cons[maker.id]["filled"] = _c(self.cons[maker.id]["filled"] + q)

    # ---- pegs
    def peg_price(self, o: Order) -> Decimal | None:
        if o.type == "PEG_MID":
            bb, ba = self.best(True, exclude_mid=True), self.best(False, exclude_mid=True)
            if bb is None or ba is None:
                return None
            # Exact: prices are positive, so the truncated quotient is the floor (HR-58).
            q, r = divmod(_c(bb + ba), _c(2 * self.tick))
            ticks = _c(q if o.buy or r == 0 else q + 1)
            p = _c(ticks * self.tick)
        else:
            same = self.best(o.buy, exclude_mid=True, exclude=o.id)
            if same is None:
                return None
            p = same
        assert o.cap is not None
        p = min(p, o.cap) if o.buy else max(p, o.cap)
        # HR-28, rounded away from crossing: a peg never takes, so it stays a tick away from the
        # opposite best, other pegs included (two PEG_MIDs on an on-grid mid would otherwise lock).
        opp = self.best(not o.buy, exclude=o.id)
        if opp is not None and (p >= opp if o.buy else p <= opp):
            p = _c(opp - self.tick if o.buy else opp + self.tick)
        return p if p > 0 else None

    def reprice(self) -> None:
        for o in sorted((o for o in self.resting.values() if o.type in PEGS), key=lambda o: o.seq):
            if o.id not in self.resting:
                continue
            p = self.peg_price(o)
            if p != o.price:
                o.price = p
                o.seq = self.next_seq()

    # ---- events
    def new(self, e: dict[str, Any], k: int) -> None:
        path = f"events/{k}"
        oid, trader = e.get("id"), e.get("trader")
        if not isinstance(oid, str) or not isinstance(trader, str):
            raise QfError("E_SCHEMA", f"{path}: id and trader must be strings", path)
        if e.get("side") not in ("BUY", "SELL") or e.get("type") not in TYPES:
            raise QfError("E_SCHEMA", f"{path}: bad side or type", path)
        typ = e["type"]
        qty = _dec(e.get("qty"), f"{path}/qty")
        limit = None if typ == "MARKET" else _dec(e.get("price"), f"{path}/price")
        if typ == "MARKET" and e.get("price") is not None:
            raise QfError("E_SCHEMA", f"{path}: MARKET takes no price", path)
        if qty <= 0:
            raise QfError("E_DOMAIN", f"{path}: quantity must be positive", path)
        self.on_grid(qty, self.lot, "qty")
        if limit is not None:
            if limit <= 0:
                raise QfError("E_DOMAIN", f"{path}: price must be positive", path)
            self.on_grid(limit, self.tick, "price")
        slice_ = qty
        if typ == "ICEBERG":
            slice_ = _dec(e.get("display_qty"), f"{path}/display_qty")
            if slice_ <= 0 or slice_ > qty:
                raise QfError("E_DOMAIN", f"{path}: display_qty must be in (0, qty]", path)
            self.on_grid(slice_, self.lot, "display_qty")
        if oid in self.seen:
            raise QfError("E_INPUT", f"{path}: duplicate id {oid}", path)
        self.seen.add(oid)
        zero = Decimal(0)
        self.cons[oid] = {
            "submitted": qty,
            "filled": zero,
            "resting": zero,
            "cancelled": zero,
            "rejected": zero,
        }
        buy = e["side"] == "BUY"
        o = Order(oid, trader, buy, typ, limit, limit, zero, zero, slice_, 0)
        if typ == "FOK" and self.available(buy, limit) < qty:
            self.reject(oid, "FOK_UNFILLABLE", qty)
            return
        if typ == "POST_ONLY":
            p = self.best(not buy)
            if p is not None and self.marketable(buy, limit, p):
                self.reject(oid, "POST_ONLY_WOULD_CROSS", qty)
                return
        if typ in PEGS:
            o.price = self.peg_price(o)
            o.seq = self.next_seq()
            if typ == "PEG_MID":
                o.hidden = qty
            else:
                o.display = qty
            self.resting[oid] = o
            return
        rest = self.match(o, limit, qty)
        if rest == 0:
            return
        if typ in ("MARKET", "IOC"):
            self.cancelled.append({"id": oid, "qty": fmt(rest)})
            self.cons[oid]["cancelled"] = _c(self.cons[oid]["cancelled"] + rest)
            return
        o.display = min(slice_, rest)
        o.hidden = _c(rest - o.display)
        o.seq = self.next_seq()
        self.resting[oid] = o

    def reject(self, oid: str, reason: str, qty: Decimal) -> None:
        self.rejects.append({"id": oid, "reason": reason})
        self.cons[oid]["rejected"] = _c(self.cons[oid]["rejected"] + qty)

    def cancel(self, e: dict[str, Any], k: int) -> None:
        oid = e.get("id")
        if not isinstance(oid, str):
            raise QfError("E_SCHEMA", f"events/{k}: id must be a string", f"events/{k}")
        o = self.resting.pop(oid, None)
        if o is None:
            self.rejects.append({"id": oid, "reason": "UNKNOWN_ID"})
            return
        self.cancelled.append({"id": oid, "qty": fmt(o.open())})
        self.cons[oid]["cancelled"] = _c(self.cons[oid]["cancelled"] + o.open())

    def modify(self, e: dict[str, Any], k: int) -> None:
        path = f"events/{k}"
        oid = e.get("id")
        if not isinstance(oid, str):
            raise QfError("E_SCHEMA", f"{path}: id must be a string", path)
        qty = _dec(e.get("qty"), f"{path}/qty")
        if qty <= 0:
            raise QfError("E_DOMAIN", f"{path}: quantity must be positive", path)
        self.on_grid(qty, self.lot, "qty")
        if e.get("price") is not None:
            raise QfError("E_SCHEMA", f"{path}: MODIFY takes id and qty only (wave 1b)", path)
        o = self.resting.get(oid)
        if o is None:
            self.rejects.append({"id": oid, "reason": "UNKNOWN_ID"})
            return
        # `qty` is the new open displayed quantity; a PEG_MID's whole quantity is non-displayed.
        old = o.hidden if o.type == "PEG_MID" else o.display
        if qty == old:
            return
        if o.type == "PEG_MID":
            o.hidden = qty
        else:
            o.display = qty
        if qty < old:
            self.cons[oid]["cancelled"] = _c(self.cons[oid]["cancelled"] + _c(old - qty))
        else:
            self.cons[oid]["submitted"] = _c(self.cons[oid]["submitted"] + _c(qty - old))
            o.seq = self.next_seq()

    # ---- output
    def output(self) -> dict[str, Any]:
        def entry(o: Order) -> dict[str, Any]:
            return {
                "id": o.id,
                "price": None if o.price is None else fmt(o.price),
                "display_qty": fmt(o.display),
                "hidden_qty": fmt(o.hidden),
                "seq": o.seq,
            }

        book: dict[str, list[dict[str, Any]]] = {}
        mbp: dict[str, list[list[str]]] = {}
        for name, buy in (("bids", True), ("asks", False)):
            orders = [o for o in self.resting.values() if o.buy == buy]
            priced = sorted(
                (o for o in orders if o.price is not None),
                key=lambda o: ((-(o.price or 0) if buy else (o.price or 0)), o.seq),
            )
            unpriced = sorted((o for o in orders if o.price is None), key=lambda o: o.seq)
            book[name] = [entry(o) for o in priced + unpriced]
            levels: dict[Decimal, Decimal] = {}
            for o in priced:
                assert o.price is not None
                levels[o.price] = _c(levels.get(o.price, Decimal(0)) + o.display)
            mbp[name] = [[fmt(p), fmt(q)] for p, q in sorted(levels.items(), reverse=buy) if q > 0]
        for oid, c in self.cons.items():
            live = self.resting.get(oid)
            c["resting"] = live.open() if live is not None else Decimal(0)
        return {
            "fills": self.fills,
            "rejects": self.rejects,
            "cancelled": self.cancelled,
            "book": book,
            "mbp": mbp,
            "fees": {t: fmt(v) for t, v in sorted(self.fees.items())},
            "conservation": {
                oid: {k: fmt(v) for k, v in c.items()} for oid, c in sorted(self.cons.items())
            },
            "label": LABEL,
        }


def run(
    tick_size: str, lot_size: str, events: list[Any], fee_schedule: dict[str, Any]
) -> dict[str, Any]:
    # Wide enough that no sum, difference or product of in-range values rounds (HR-58).
    with localcontext(EXACT):
        return _run(tick_size, lot_size, events, fee_schedule)


def _run(
    tick_size: str, lot_size: str, events: list[Any], fee_schedule: dict[str, Any]
) -> dict[str, Any]:
    tick, lot = _dec(tick_size, "tick_size"), _dec(lot_size, "lot_size")
    if tick <= 0 or lot <= 0:
        raise QfError("E_DOMAIN", "tick_size and lot_size must be positive", "tick_size")
    taker = _dec(fee_schedule.get("taker_fee"), "fee_schedule/taker_fee")
    rebate = _dec(fee_schedule.get("maker_rebate"), "fee_schedule/maker_rebate")
    if len(events) > MAX_EVENTS:
        raise QfError("E_LIMIT", "more than 10,000,000 events", "events")
    eng = _Engine(tick, lot, taker, rebate)
    for k, e in enumerate(events):
        if not isinstance(e, dict) or e.get("op") not in ("NEW", "CANCEL", "MODIFY"):
            raise QfError("E_SCHEMA", f"events/{k}: not an event", "events")
        if e["op"] == "NEW":
            eng.new(e, k)
        elif e["op"] == "CANCEL":
            eng.cancel(e, k)
        else:
            eng.modify(e, k)
        eng.reprice()
    return eng.output()


guard(globals())
