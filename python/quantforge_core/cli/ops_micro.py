"""Stage H wave 2 verbs: MBP book rebuild and the simulated lit matching engine
(specifications/09-microstructure/order-book.md, specifications/10-execution/lit-matching.md)."""

from typing import Any

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
