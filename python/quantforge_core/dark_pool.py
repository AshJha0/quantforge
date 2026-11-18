"""`exec.sim.dark.run` and `exec.sim.dark.markouts`: a simulated midpoint dark pool.

Spec: specifications/10-execution/dark-pool.md (rulings HR-32 to HR-36). Simulated venue; not a
real dark pool. The reference price is the mid of a lit book supplied per event (for example the
best levels of `exec.sim.lit.run`, see `lit_matching.py`); prices and quantities are exact
decimals (HR-12), with the decimal helpers shared with the lit engine.

Crossing (HR-32, HR-33): after every event, while a mid exists, scan buys by `seq` and for each
buy the sells by `seq`; the first pair within both limits whose fill `min(open_buy, open_sell)`
meets both `min_qty` is the match; it fills at the mid. A pair with a `CONDITIONAL` side first
sends an invitation (HR-34): the owner firms up with probability `p_firm` (a `core.rng` draw only
when 0 < p_firm < 1). With `firm_delay` d > 0 both orders are held out of the scan until event
`event + d`, when the firm-up is decided and the pair fills at the mid of that event if it is still
eligible. A decline suspends the conditional for events `event + 1` to `event + penalty_events`.

Also here: the Kaplan-Meier tail of censored per-venue fills ([GKNV09], fill-probability model 1)
with its Greenwood standard error, used by the router and by the planted-recovery tests.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any

from .errors import QfError
from .finite import guard
from .lit_matching import _dec, fmt
from .rng import Xoshiro256

LABEL = "simulated venue; not a real dark pool"
MAX_EVENTS = 10_000_000
_SIX = Decimal("0.000001")


@dataclass
class _Order:
    id: str
    buy: bool
    open: Decimal
    limit: Decimal | None
    min_qty: Decimal
    conditional: bool
    seq: int
    suspended_to: int = 0  # eligible only after this event
    held_to: int = 0  # invitation pending until this event


def _on_grid(x: Decimal, step: Decimal, path: str) -> None:
    if x % step != 0:
        raise QfError("E_DOMAIN", f"{path}: not on the grid {fmt(step)}", path)


class _Pool:
    def __init__(self, cfg: dict[str, Any]):
        self.tick = _dec(cfg.get("tick_size"), "config/tick_size")
        self.lot = _dec(cfg.get("lot_size"), "config/lot_size")
        if self.tick <= 0 or self.lot <= 0:
            raise QfError("E_DOMAIN", "tick_size and lot_size must be positive", "config/tick_size")
        self.p_firm = _dec(cfg.get("p_firm", "0.8"), "config/p_firm")
        if not 0 <= self.p_firm <= 1:
            raise QfError("E_DOMAIN", "p_firm outside [0, 1]", "config/p_firm")
        self.delay = _int(cfg.get("firm_delay", 0), "config/firm_delay")
        self.penalty = _int(cfg.get("penalty_events", 0), "config/penalty_events")
        self.rng = Xoshiro256.seeded(_int(cfg.get("seed", 0), "config/seed"))
        self.mid: Decimal | None = None
        self.orders: dict[str, _Order] = {}
        self.seq = 0
        self.fills: list[dict[str, Any]] = []
        self.invitations: list[dict[str, Any]] = []
        self.suspensions: list[dict[str, Any]] = []
        self.pending: list[tuple[int, _Order, _Order]] = []

    # ---------------------------------------------------------------- events
    def book(self, e: dict[str, Any], k: int) -> None:
        bid = _dec(e.get("bid"), f"events/{k}/bid") if e.get("bid") is not None else None
        ask = _dec(e.get("ask"), f"events/{k}/ask") if e.get("ask") is not None else None
        for v, name in ((bid, "bid"), (ask, "ask")):
            if v is not None:
                _on_grid(v, self.tick, f"events/{k}/{name}")
        self.mid = None if bid is None or ask is None or bid >= ask else (bid + ask) / 2

    def new(self, e: dict[str, Any], k: int) -> None:
        oid = e.get("id")
        if not isinstance(oid, str):
            raise QfError("E_SCHEMA", f"events/{k}/id: not a string", "events")
        if oid in self.orders:
            raise QfError("E_INPUT", f"events/{k}: duplicate id {oid}", "events")
        if e.get("side") not in ("BUY", "SELL") or e.get("kind") not in ("FIRM", "CONDITIONAL"):
            raise QfError("E_SCHEMA", f"events/{k}: side or kind", "events")
        qty = _dec(e.get("qty"), f"events/{k}/qty")
        mq = _dec(e.get("min_qty", fmt(self.lot)), f"events/{k}/min_qty")
        if qty <= 0 or mq <= 0 or mq > qty:
            raise QfError(
                "E_DOMAIN", f"events/{k}: qty must be positive and min_qty <= qty", "events"
            )
        _on_grid(qty, self.lot, f"events/{k}/qty")
        lim = _dec(e["limit"], f"events/{k}/limit") if e.get("limit") is not None else None
        self.seq += 1
        self.orders[oid] = _Order(
            oid, e["side"] == "BUY", qty, lim, mq, e["kind"] == "CONDITIONAL", self.seq
        )

    def cancel(self, e: dict[str, Any], k: int) -> None:
        if e.get("id") not in self.orders:
            raise QfError("E_INPUT", f"events/{k}: unknown id", "events")
        self.orders[e["id"]].open = Decimal(0)

    # ---------------------------------------------------------------- matching
    def _eligible(self, o: _Order, n: int) -> bool:
        if o.open <= 0 or n <= o.suspended_to or n < o.held_to or self.mid is None:
            return False
        if o.limit is None:
            return True
        return o.limit >= self.mid if o.buy else o.limit <= self.mid

    @staticmethod
    def _pair_ok(b: _Order, s: _Order) -> bool:
        q = min(b.open, s.open)
        return q >= b.min_qty and q >= s.min_qty

    def _firm(self) -> bool:
        if self.p_firm == 1:
            return True
        if self.p_firm == 0:
            return False
        return Decimal(repr(self.rng.uniform())) < self.p_firm

    def _fill(self, b: _Order, s: _Order) -> None:
        assert self.mid is not None
        q = min(b.open, s.open)
        b.open -= q
        s.open -= q
        self.fills.append(
            {
                "buy_id": b.id,
                "sell_id": s.id,
                "price": fmt(self.mid),
                "qty": fmt(q),
                "seq": len(self.fills) + 1,
            }
        )

    def _invite(self, b: _Order, s: _Order, n: int) -> bool:
        """Invitations for the conditional side(s); True when every one firms up."""
        ok = True
        for o, c in ((b, s), (s, b)):
            if not o.conditional:
                continue
            firmed = self._firm()
            self.invitations.append(
                {
                    "id": o.id,
                    "contra_id": c.id,
                    "event": n,
                    "result": "FIRMED" if firmed else "DECLINED",
                }
            )
            if not firmed:
                ok = False
                o.suspended_to = n + self.penalty
                if self.penalty > 0:
                    self.suspensions.append(
                        {"id": o.id, "from_event": n + 1, "to_event": n + self.penalty}
                    )
        return ok

    def settle(self, n: int) -> None:
        due = [p for p in self.pending if p[0] == n]
        self.pending = [p for p in self.pending if p[0] != n]
        for _, b, s in due:
            b.held_to = s.held_to = 0
            if (
                self._invite(b, s, n)
                and self._eligible(b, n)
                and self._eligible(s, n)
                and self._pair_ok(b, s)
            ):
                self._fill(b, s)

    def cross(self, n: int) -> None:
        while self.mid is not None:
            live = sorted(
                (o for o in self.orders.values() if self._eligible(o, n)), key=lambda o: o.seq
            )
            pair = next(
                ((b, s) for b in live if b.buy for s in live if not s.buy and self._pair_ok(b, s)),
                None,
            )
            if pair is None:
                return
            b, s = pair
            if not (b.conditional or s.conditional):
                self._fill(b, s)
            elif self.delay > 0:
                b.held_to = s.held_to = n + self.delay
                self.pending.append((n + self.delay, b, s))
            elif self._invite(b, s, n):
                self._fill(b, s)

    def output(self) -> dict[str, Any]:
        rest = sorted((o for o in self.orders.values() if o.open > 0), key=lambda o: o.seq)
        return {
            "fills": self.fills,
            "invitations": self.invitations,
            "suspensions": self.suspensions,
            "resting": [
                {
                    "id": o.id,
                    "side": "BUY" if o.buy else "SELL",
                    "open_qty": fmt(o.open),
                    "seq": o.seq,
                }
                for o in rest
            ],
            "label": LABEL,
        }


def _int(v: Any, path: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise QfError("E_DOMAIN", f"{path}: not a non-negative integer", path)
    return v


ASSET_CLASSES = ("EQUITY", "FX", "RATES")


def asset_class(v: Any, path: str, dark: bool = False) -> str:
    """HR-93: `asset_class` (default EQUITY); a dark venue of another class is E_UNSUPPORTED_OPERATION."""
    v = "EQUITY" if v is None else v
    if v not in ASSET_CLASSES:
        raise QfError("E_SCHEMA", f"{path}: not EQUITY, FX or RATES", path)
    if dark and v != "EQUITY":
        raise QfError(
            "E_UNSUPPORTED_OPERATION", f"{path}: dark pool is equities only (HR-93)", path
        )
    return str(v)


def run(config: dict[str, Any], events: list[Any]) -> dict[str, Any]:
    """One pool run over `events` (BOOK, NEW, CANCEL), numbered from 1."""
    asset_class(config.get("asset_class"), "config/asset_class", dark=True)
    if len(events) > MAX_EVENTS:
        raise QfError("E_LIMIT", "more than 10,000,000 events", "events")
    pool = _Pool(config)
    for k, e in enumerate(events):
        n = k + 1
        op = e.get("op") if isinstance(e, dict) else None
        if op == "BOOK":
            pool.book(e, k)
        elif op == "NEW":
            pool.new(e, k)
        elif op == "CANCEL":
            pool.cancel(e, k)
        else:
            raise QfError("E_SCHEMA", f"events/{k}: not an event", "events")
        pool.settle(n)
        pool.cross(n)
    return pool.output()


def markouts(fills: list[Any]) -> dict[str, Any]:
    """Markout in bp per horizon: side_sign x (mid - fill_price) / fill_price x 10000, rounded
    half-even to 6 decimals (positive is good for the order's owner)."""
    out = []
    for k, f in enumerate(fills):
        if not isinstance(f, dict) or f.get("side") not in ("BUY", "SELL"):
            raise QfError("E_SCHEMA", f"fills/{k}: side", "fills")
        px = _dec(f.get("fill_price"), f"fills/{k}/fill_price")
        if px <= 0:
            raise QfError("E_DOMAIN", f"fills/{k}/fill_price: not positive", "fills")
        mids = f.get("mid_at")
        if not isinstance(mids, dict):
            raise QfError("E_SCHEMA", f"fills/{k}/mid_at: not an object", "fills")
        sign = 1 if f["side"] == "BUY" else -1
        bp = {}
        with localcontext() as ctx:
            ctx.prec = 60
            for h, m in mids.items():
                v = sign * (_dec(m, f"fills/{k}/mid_at/{h}") - px) / px * 10000
                bp[h] = fmt(v.quantize(_SIX, rounding=ROUND_HALF_EVEN))
        out.append({"markouts_bp": bp, "label": LABEL})
    return {"fills": out}


def km_tail(obs: list[tuple[int, int]], s_max: int) -> list[tuple[float, float]]:
    """Kaplan-Meier tail T(s) = P(liquidity >= s), s = 1..s_max, from (v, r) observations
    ([GKNV09] section 2: r < v is a direct observation of s = r; r = v is censored, s >= v).
    Returns (estimate, Greenwood standard error) per s; plain KM, no optimistic modification."""
    t, gw, out = 1.0, 0.0, []
    for s in range(1, s_max + 1):
        j = s - 1  # hazard at j: P(S = j | S >= j)
        at_risk = sum(1 for v, r in obs if (r < v and r >= j) or (r == v and v > j))
        d = sum(1 for v, r in obs if r < v and r == j)
        if at_risk > 0 and d > 0:
            t *= 1 - d / at_risk
            if at_risk > d:
                gw += d / (at_risk * (at_risk - d))
        out.append((t, t * gw**0.5))
    return out


guard(globals())
