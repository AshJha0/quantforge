"""Paper trading fills (HR-47), routing (SOR) and per-order TCA (HR-55).

Spec: specifications/10-execution/paper-trading.md. Every fill comes from a simulated venue
replaying a recorded (or synthetic) book snapshot: `lit_matching.run`, `dark_pool.run`, or the
children of `sor.allocate`. Nothing here talks to a network or a venue (HR-42); the optional
snapshot loader reads a local JSON Lines file only. Labels: "crypto venue; simulated".

Snapshot form: {"ts", "symbol", "bids": [[price, qty], ...], "asks": [[price, qty], ...]}, best
level first, decimal strings. The replayed book does not remember our earlier fills (no permanent
impact) and a resting remainder never fills later in the day: it is cancelled at the close
(HR-48). SOR children: M goes to the lit book as MARKET, a LIT L_k rests at the same-side best
price (so it fills only if it crosses, which it does not on a static snapshot), a DARK L_k goes to
the dark pool with the caller's synthetic contra events; child fills beyond the parent quantity
are dropped (the parent never overfills, E_INPUT in the spec).
"""

import json
import pathlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from . import dark_pool, lit_matching, sor
from .errors import QfError
from .execution import tca_shortfall
from .finite import guard
from .lit_matching import fmt
from .paper import (
    CEILING,
    LABEL,
    Book,
    Ledger,
    dec,
    end_of_day,
    exact,
    input_decimal,
    pretrade_check,
    side_sign,
)

TRADER = "PAPER"
VENUES = ("LIT", "DARK", "SOR")


def load_snapshots(path: str | pathlib.Path) -> list[dict[str, Any]]:
    """Optional loader for recorded crypto snapshots (local JSON Lines; no network)."""
    out = []
    for k, line in enumerate(pathlib.Path(path).read_text(encoding="utf-8").splitlines()):
        if line.strip():
            snap = json.loads(line)
            if not isinstance(snap, dict) or not {"bids", "asks"} <= snap.keys():
                raise QfError("E_SCHEMA", f"line {k}: snapshot needs bids and asks", "snapshot")
            snap["label"] = LABEL
            out.append(snap)
    return out


def venue_run(venue: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """The single dispatch every paper fill goes through (A7 replays the venue goldens here)."""
    if venue == "LIT":
        return lit_matching.run(
            inputs["tick_size"],
            inputs["lot_size"],
            list(inputs["events"]),
            dict(inputs["fee_schedule"]),
        )
    if venue == "DARK":
        return dark_pool.run(dict(inputs["config"]), list(inputs["events"]))
    if venue == "SOR":
        return sor.allocate(dict(inputs))
    raise QfError("E_INPUT", f"unknown venue {venue!r}", "venue")


def mid(snap: Mapping[str, Any]) -> Decimal:
    if not snap.get("bids") or not snap.get("asks"):
        raise QfError("E_INPUT", "snapshot has an empty side; no mid", "snapshot")
    return (dec(snap["bids"][0][0], "bid") + dec(snap["asks"][0][0], "ask")) / 2


def _seed(snap: Mapping[str, Any]) -> list[dict[str, Any]]:
    ev = []
    for name, side in (("asks", "SELL"), ("bids", "BUY")):
        for i, (p, q) in enumerate(snap[name]):
            ev.append(
                {
                    "op": "NEW",
                    "id": f"BOOK-{name}-{i}",
                    "trader": "BOOK",
                    "side": side,
                    "type": "LIMIT",
                    "price": p,
                    "qty": q,
                }
            )
    return ev


@dataclass
class Fill:
    quantity: Decimal
    price: Decimal
    fee: Decimal
    venue: str
    child_id: str


def lit_child(
    cfg: Mapping[str, Any],
    snap: Mapping[str, Any],
    cid: str,
    side: str,
    otype: str,
    qty: Decimal,
    limit: Decimal | None,
) -> tuple[list[Fill], Decimal]:
    """Replay one child into the lit engine seeded with the snapshot; (fills, resting qty)."""
    ev: dict[str, Any] = {
        "op": "NEW",
        "id": cid,
        "trader": TRADER,
        "side": side,
        "type": otype,
        "qty": fmt(qty),
    }
    if otype != "MARKET":
        ev["price"] = fmt(dec(limit, "limit_price"))
    fees = cfg["fee_schedule"]
    out = venue_run("LIT", {**cfg, "events": [*_seed(snap), ev]})
    rej = [r for r in out["rejects"] if r["id"] == cid]
    if rej:
        return [], Decimal(0)
    taker, rebate = dec(fees["taker_fee"], "taker_fee"), dec(fees["maker_rebate"], "maker_rebate")
    fills = []
    for f in out["fills"]:
        if cid in (f["taker_id"], f["maker_id"]):
            q, p = dec(f["qty"], "qty"), dec(f["price"], "price")
            rate = taker if f["taker_id"] == cid else -rebate
            fills.append(Fill(q, p, rate * q * p, "LIT", cid))
    if sum((f.fee for f in fills), Decimal(0)) != dec(out["fees"].get(TRADER, "0"), "fee"):
        raise AssertionError("per-fill fees do not add to the venue fee")  # pragma: no cover
    return fills, dec(out["conservation"][cid]["resting"], "resting")


def dark_child(
    cfg: Mapping[str, Any],
    snap: Mapping[str, Any],
    contra: Sequence[Mapping[str, Any]],
    cid: str,
    side: str,
    qty: Decimal,
    limit: Decimal | None,
) -> tuple[list[Fill], Decimal]:
    """Replay one child into the dark pool at the snapshot mid against synthetic contra orders."""
    book = {"op": "BOOK", "bid": snap["bids"][0][0], "ask": snap["asks"][0][0]}
    ev: dict[str, Any] = {"op": "NEW", "id": cid, "side": side, "qty": fmt(qty), "kind": "FIRM"}
    if limit is not None:
        ev["limit"] = fmt(limit)
    out = venue_run("DARK", {"config": cfg, "events": [book, *map(dict, contra), ev]})
    fills = [
        Fill(dec(f["qty"], "qty"), dec(f["price"], "price"), Decimal(0), "DARK", cid)
        for f in out["fills"]
        if cid in (f["buy_id"], f["sell_id"])
    ]
    rest = next((dec(r["open_qty"], "q") for r in out["resting"] if r["id"] == cid), Decimal(0))
    return fills, rest


@dataclass
class _Open:
    order: dict[str, Any]
    decision: Decimal
    arrival: Decimal
    fills: list[Fill] = field(default_factory=list)
    resting: Decimal = Decimal(0)


class Session:
    """One paper account: pre-trade gate, simulated fills, ledger, TCA per order, daily close."""

    def __init__(
        self,
        cash: Any,
        limits: Mapping[str, Any],
        lit_cfg: Mapping[str, Any],
        dark_cfg: Mapping[str, Any] | None = None,
    ) -> None:
        self.ledger = Ledger()
        self.book = Book(cash=dec(cash, "cash"))
        self.limits, self.lit_cfg, self.dark_cfg = limits, lit_cfg, dark_cfg
        self.today: list[_Open] = []
        self.day_fills: list[dict[str, Any]] = []
        self.orders_today = 0

    def _position(self, symbol: str) -> Decimal:
        n = self.book.pos(symbol).n
        return n + sum(
            (
                side_sign(f["side"]) * dec(f["quantity"], "q")
                for f in self.day_fills
                if f["symbol"] == symbol
            ),
            Decimal(0),
        )

    def _cash(self) -> Decimal:
        return self.book.cash - sum(
            (
                side_sign(f["side"]) * dec(f["quantity"], "q") * dec(f["price"], "p")
                + dec(f["fee"], "f")
                for f in self.day_fills
            ),
            Decimal(0),
        )

    def submit(
        self,
        order: Mapping[str, Any],
        ts: str,
        snap: Mapping[str, Any],
        contra: Sequence[Mapping[str, Any]] = (),
        router: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Pre-trade check, then replay into the order's venue; returns the order status."""
        venue = order.get("venue", "LIT")
        if venue not in VENUES:
            raise QfError("E_INPUT", f"unknown venue {venue!r}", "venue")
        if any(o.order["order_id"] == order["order_id"] for o in self.today):
            raise QfError("E_INPUT", "duplicate order_id", "order_id")
        p_ref = mid(snap)
        sym = order["symbol"]
        chk = pretrade_check(
            order, p_ref, self._position(sym), self._cash(), self.orders_today, self.limits
        )
        self.orders_today += 1
        body = {k: v for k, v in order.items() if k != "mode"}
        if not chk["accepted"]:
            self.ledger.append("REJECT", ts, {**body, "reasons": chk["reasons"]})
            return {"status": "REJECTED", "reasons": chk["reasons"]}
        self.ledger.append("ORDER", ts, {**body, "decision_price": fmt(p_ref)})
        side, oid, qty = order["side"], order["order_id"], dec(order["quantity"], "quantity")
        limit = None if order["type"] == "MARKET" else dec(order["limit_price"], "limit_price")
        # arrival = mid at venue entry; with one snapshot per order it equals the decision mid
        rec = _Open(dict(order), p_ref, mid(snap))
        if venue == "LIT":
            rec.fills, rec.resting = lit_child(
                self.lit_cfg, snap, oid, side, order["type"], qty, limit
            )
        elif venue == "DARK":
            rec.fills, rec.resting = dark_child(self._dark(), snap, contra, oid, side, qty, limit)
        else:
            rec.fills = self._route(order, snap, contra, router, qty, limit)
        for f in rec.fills:
            fb = {
                "order_id": oid,
                "child_id": f.child_id,
                "venue": f.venue,
                "symbol": sym,
                "side": side,
                "quantity": fmt(f.quantity),
                "price": fmt(f.price),
                "fee": fmt(f.fee),
            }
            self.ledger.append("FILL", ts, fb)
            self.day_fills.append(fb)
        filled = sum((f.quantity for f in rec.fills), Decimal(0))
        if rec.resting == 0 and filled < qty:
            self.ledger.append("CANCEL", ts, {"order_id": oid, "quantity": fmt(qty - filled)})
        self.today.append(rec)
        return {"status": "OPEN" if rec.resting else "DONE", "filled": fmt(filled)}

    def _dark(self) -> Mapping[str, Any]:
        if self.dark_cfg is None:
            raise QfError("E_SCHEMA", "dark venue configuration is missing", "dark_cfg")
        return self.dark_cfg

    def _route(
        self,
        order: Mapping[str, Any],
        snap: Mapping[str, Any],
        contra: Sequence[Mapping[str, Any]],
        router: Mapping[str, Any] | None,
        qty: Decimal,
        limit: Decimal | None,
    ) -> list[Fill]:
        if router is None:
            raise QfError("E_SCHEMA", "SOR order needs the router input", "router")
        alloc = venue_run("SOR", {**router, "S": fmt(qty)})
        oid, side = order["order_id"], order["side"]
        best = snap["bids" if side == "BUY" else "asks"][0][0]
        fills: list[Fill] = []
        children: list[tuple[str, str, Decimal]] = [("M", "MARKET", dec(alloc["M"], "M"))]
        for k, (v, lk) in enumerate(zip(router["venues"], alloc["L"], strict=True)):
            children.append((f"L{k}", v["kind"], dec(lk, "L")))
        for name, kind, q in children:
            if q == 0:
                continue
            cid = f"{oid}.{name}"
            if kind == "MARKET":
                got, _ = lit_child(self.lit_cfg, snap, cid, side, "MARKET", q, None)
            elif kind == "LIT":
                got, _ = lit_child(self.lit_cfg, snap, cid, side, "LIMIT", q, dec(best, "best"))
            else:
                got, _ = dark_child(self._dark(), snap, contra, cid, side, q, limit)
            for g in got:  # the parent never overfills
                room = qty - sum((x.quantity for x in fills), Decimal(0))
                if room <= 0:
                    break
                if g.quantity > room:
                    g = Fill(room, g.price, g.fee * room / g.quantity, g.venue, g.child_id)
                fills.append(g)
        return fills

    def close_day(
        self,
        ts: str,
        prev_marks: Mapping[str, Any],
        marks: Mapping[str, Any],
        days: int = 1,
        **rates: Any,
    ) -> dict[str, Any]:
        """Cancel resting remainders (HR-48), write one TCA per final order, then EOD."""
        tcas = []
        for rec in self.today:
            o = rec.order
            oid, qty = o["order_id"], dec(o["quantity"], "quantity")
            filled = sum((f.quantity for f in rec.fills), Decimal(0))
            if rec.resting:
                self.ledger.append("CANCEL", ts, {"order_id": oid, "quantity": fmt(qty - filled)})
            fees = sum((f.fee for f in rec.fills), Decimal(0))
            t = tca_shortfall(
                o["side"],
                float(rec.decision),
                float(rec.arrival),
                float(dec(marks[o["symbol"]], "close")),
                float(qty),
                [(float(f.quantity), float(f.price)) for f in rec.fills],
                float(fees),
                None,
            )
            body = {"order_id": oid, **{k: fmt(Decimal(repr(float(v)))) for k, v in t.items()}}
            self.ledger.append("TCA", ts, body)
            tcas.append(t)
        eod = end_of_day(self.book, self.day_fills, prev_marks, marks, days, **rates)
        self.ledger.append(
            "EOD",
            ts,
            {k: (fmt(v) if isinstance(v, Decimal) else v) for k, v in eod.items()},
        )
        self.today, self.day_fills, self.orders_today = [], [], 0
        return {"eod": eod, "tca": tcas}


@exact
def session_case(
    cash: Any,
    limits: Mapping[str, Any],
    lit: Mapping[str, Any],
    script: Sequence[Any],
    dark: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """`paper.session.run`: replays a script of SUBMIT and CLOSE steps through one Session and
    returns every ledger record (with its hash), the head, positions and cash (cli-contract.md).
    Deterministic (A8); simulated only (HR-42)."""
    input_decimal(cash, "cash")
    for key0 in ("tick_size", "lot_size", "fee_schedule"):
        if lit.get(key0) is None:
            raise QfError("E_SCHEMA", f"lit/{key0} is missing", "lit/" + key0)
    s = Session(cash, limits, lit, dark)
    results: list[dict[str, Any]] = []
    symbols: set[str] = set()
    for k, step in enumerate(script):
        w = f"script/{k}/"
        if not isinstance(step, Mapping) or step.get("op") not in ("SUBMIT", "CLOSE"):
            raise QfError("E_SCHEMA", f"{w}op must be SUBMIT or CLOSE", w + "op")
        ts = step.get("ts")
        if not isinstance(ts, str):
            raise QfError("E_SCHEMA", f"{w}ts is missing", w + "ts")
        if step["op"] == "SUBMIT":
            order, snap = step.get("order"), step.get("snapshot")
            if not isinstance(order, Mapping) or not isinstance(snap, Mapping):
                raise QfError("E_SCHEMA", f"{w}order and snapshot are required", w + "order")
            for key in ("order_id", "symbol", "side", "type", "quantity"):
                if order.get(key) is None:
                    raise QfError("E_SCHEMA", f"{w}order/{key} is missing", w + "order/" + key)
            # mistyped text fields are E_SCHEMA (an array symbol crashed the symbol set; fuzz run
            # 44937631714 found the same fault in paper.book.apply_fill); a null venue stays E_INPUT
            for key in ("order_id", "symbol", "side", "type", "venue"):
                if order.get(key) is not None and not isinstance(order[key], str):
                    raise QfError("E_SCHEMA", f"{w}order/{key} must be a string", w + "order/" + key)
            for key in ("quantity", "limit_price"):
                if order.get(key) is not None:
                    input_decimal(order[key], f"{w}order/{key}")
            symbols.add(order["symbol"])
            results.append(
                s.submit(order, ts, snap, list(step.get("contra") or []), step.get("router"))
            )
        else:
            days = step.get("days", 1)
            if isinstance(days, bool) or not isinstance(days, int):
                raise QfError("E_SCHEMA", f"{w}days must be an integer", w + "days")
            rates = {r: step.get(r, "0") for r in ("cash_rate", "debit_rate", "borrow_rate")}
            for r, v in rates.items():
                input_decimal(v, w + r)
            for name in ("prev_marks", "marks"):
                for sym, v in (step.get(name) or {}).items():
                    input_decimal(v, f"{w}{name}/{sym}")
            out = s.close_day(
                ts, dict(step.get("prev_marks") or {}), dict(step.get("marks") or {}), days, **rates
            )
            e = out["eod"]
            results.append(
                {
                    "status": "CLOSED",
                    "eod": {k2: (fmt(v) if isinstance(v, Decimal) else v) for k2, v in e.items()},
                }
            )
    records = [json.loads(line) for line in s.ledger.lines]
    return {
        "results": results,
        "records": records,
        "head": s.ledger.head,
        "positions": {sym: fmt(s._position(sym)) for sym in sorted(symbols)},
        "cash": fmt(s._cash()),
        "label": LABEL,
        "ceiling": CEILING,
    }


guard(globals())
