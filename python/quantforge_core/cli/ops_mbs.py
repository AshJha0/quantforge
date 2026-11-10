"""Handlers for the mbs verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from .inputs import Inputs
from .registry import core, op


def _pool(i: Inputs) -> Any:
    p = i.object("pool")
    pre = p.object("prepayment")
    model = pre.enum("model", ("CPR", "PSA"))
    speed = pre.real("rate" if model == "CPR" else "speed")
    return (p.real("balance"), p.real("wac"), p.real("net_coupon"), p.integer("wam"),
            p.integer("age"), model, speed)


@op("mbs.cashflows")
def _mbs_cashflows(i: Inputs) -> Any:
    return core.mbs.mbs_cashflows(_pool(i))


@op("mbs.price")
def _mbs_price(i: Inputs) -> Any:
    price, duration, wal = core.mbs.mbs_price(_pool(i), i.real("yield"), i.integer("delay_days"))
    return {"price": price, "modified_duration": duration, "wal": wal}
