"""Handlers for the commodity verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from .inputs import Inputs
from .readers import _curve, _month_index, _objects, _present
from .registry import core, op


@op("cmdty.curve.forward")
def _cmdty_forward(i: Inputs) -> Any:
    _present(i, "seasonality")
    season = i.reals("seasonality") if i.has("seasonality") else None
    quotes = [(_month_index(q, "month"), q.real("price")) for q in _objects(i, "quotes")]
    months = [_month_index(Inputs({"m": m}), "m") for m in i.array("months")]
    return {"forwards": core.commodity.commodity_forwards(quotes, season, months)}


@op("cmdty.storage.carry")
def _storage(i: Inputs) -> Any:
    forwards = [(f.date("date"), f.real("price")) for f in _objects(i, "forwards")]
    ys, values, flags = core.commodity.storage_carry(_curve(i, "funding"), forwards,
                                                 i.real("storage_cost"))
    return {"convenience_yields": ys, "carry_values": values, "arbitrage": flags}
