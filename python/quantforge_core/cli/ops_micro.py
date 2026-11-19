"""Stage H wave 2 verbs: MBP book rebuild and the simulated lit matching engine
(specifications/09-microstructure/order-book.md, specifications/10-execution/lit-matching.md)."""

from typing import Any

from ..errors import QfError
from .inputs import Inputs
from .readers import _objects
from .registry import core, op


@op("micro.book.rebuild")
def micro_book_rebuild(i: Inputs) -> Any:
    return core.order_book.rebuild(
        i.array("messages"),
        i.integer("depth"),
        i.integer("price_decimals"),
        i.integer("qty_decimals"),
        i.array("checkpoints") if i.has("checkpoints") else None,
        i.opt_boolean("emit_checksum_string", False),
    )


@op("exec.sim.lit.run")
def exec_sim_lit_run(i: Inputs) -> Any:
    fees = i.object("fee_schedule").raw
    session = dict(i.object("session").raw) if i.has("session") else None
    return core.lit_matching.run(
        i.string("tick_size"), i.string("lot_size"), i.array("events"), dict(fees), session
    )


@op("exec.sim.dark.run")
def exec_sim_dark_run(i: Inputs) -> Any:
    """One run (`config`, `events`) or several (`scenarios`), specifications/10-execution/dark-pool.md."""
    if i.has("scenarios"):
        runs = []
        for k, s in enumerate(i.array("scenarios")):
            if not isinstance(s, dict):
                raise QfError("E_SCHEMA", f"scenarios/{k}: not an object", "scenarios")
            runs.append(
                core.dark_pool.run(dict(s.get("config") or {}), list(s.get("events") or []))
            )
        return {"scenarios": runs}
    return core.dark_pool.run(dict(i.object("config").raw), i.array("events"))


@op("exec.sim.dark.markouts")
def exec_sim_dark_markouts(i: Inputs) -> Any:
    return core.dark_pool.markouts(i.array("fills"))


@op("exec.sor.allocate")
def exec_sor_allocate(i: Inputs) -> Any:
    return core.sor.allocate(dict(i.raw))


# Stage H H-4b: specifications/09-microstructure/micro-estimators.md (names fixed in its
# "Operation inputs and outputs" table)
CANCEL_OUTCOMES = ("CANCEL", "FILL")


@op("micro.est.arrival_rate")
def micro_est_arrival_rate(i: Inputs) -> Any:
    return core.micro_est.arrival_rate(i.integer("count"), i.real("window"))


@op("micro.est.cancel_rate")
def micro_est_cancel_rate(i: Inputs) -> Any:
    rows = [(o.real("lifetime"), o.enum("outcome", CANCEL_OUTCOMES)) for o in _objects(i, "orders")]
    return core.micro_est.cancel_rate(rows)


@op("micro.est.resilience")
def micro_est_resilience(i: Inputs) -> Any:
    pts = [(p.real("t"), p.real("s")) for p in _objects(i, "points")]
    return core.micro_est.resilience(i.real("s_inf"), pts)


@op("micro.est.liquidity_decay")
def micro_est_liquidity_decay(i: Inputs) -> Any:
    rows = [(p.real("k"), p.real("depth")) for p in _objects(i, "levels")]
    return core.micro_est.liquidity_decay(rows)


@op("micro.est.adverse_selection")
def micro_est_adverse_selection(i: Inputs) -> Any:
    return core.micro_est.adverse_selection(i.reals("x"), i.reals("y"))


@op("micro.est.regime_impact")
def micro_est_regime_impact(i: Inputs) -> Any:
    reg = i.object("regimes")
    rows = {}
    for label in sorted(reg.raw):
        r = reg.object(label)
        rows[label] = (r.reals("x"), r.reals("y"))
    return core.micro_est.regime_impact(rows)


@op("micro.est.passive_vs_aggressive")
def micro_est_passive_vs_aggressive(i: Inputs) -> Any:
    return core.micro_est.passive_vs_aggressive(i.reals("passive"), i.reals("aggressive"))


# Stage H H-16: specifications/10-execution/venue-analytics.md
@op("exec.venue.analytics")
def exec_venue_analytics(i: Inputs) -> Any:
    va = core.venue_analytics
    mids = [(m.real("t"), m.real("mid")) for m in _objects(i, "mids")]
    fills = [
        va.Fill(
            f.string("venue"),
            f.enum("side", ("BUY", "SELL")),
            f.real("quantity"),
            f.real("price"),
            f.real("t"),
        )
        for f in _objects(i, "fills")
    ]
    orders = [
        va.Order(o.string("venue"), o.real("sent"), o.real("filled")) for o in _objects(i, "orders")
    ]
    return va.analytics(mids, fills, orders, i.reals("horizons"))
