"""Stage H wave 2 verbs: MBP book rebuild and the simulated lit matching engine
(specifications/09-microstructure/order-book.md, specifications/10-execution/lit-matching.md)."""

from typing import Any

from ..errors import QfError
from .inputs import Inputs
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
    return core.lit_matching.run(
        i.string("tick_size"), i.string("lot_size"), i.array("events"), dict(fees)
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
