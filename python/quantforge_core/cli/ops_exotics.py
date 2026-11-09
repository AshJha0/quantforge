"""Handlers for the exotics verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from .inputs import Inputs
from .readers import _OPTION_TYPES
from .registry import core, op


def _option_common(i: Inputs) -> tuple[float, float, float, float, float, float, str]:
    return (i.real("spot"), i.real("strike"), i.real("expiry_years"), i.real("rate"),
            i.real("dividend_yield"), i.real("vol"), i.enum("option_type", _OPTION_TYPES))


@op("exotic.digital.price")
def _digital(i: Inputs) -> Any:
    args = (*_option_common(i), i.enum("payoff", ("CASH_OR_NOTHING", "ASSET_OR_NOTHING")),
            i.real("cash"))
    return {"price": core.exotics.digital(*args)}


@op("exotic.barrier.price")
def _barrier(i: Inputs) -> Any:
    kinds = ("DOWN_IN", "DOWN_OUT", "UP_IN", "UP_OUT")
    args = (*_option_common(i), i.real("barrier"), i.real("rebate"), i.enum("barrier_type", kinds))
    return {"price": core.exotics.barrier(*args)}


@op("exotic.asian.geometric")
def _asian(i: Inputs) -> Any:
    args = (*_option_common(i), i.enum("averaging", ("CONTINUOUS", "DISCRETE")),
            i.reals("fixing_years"))
    return {"price": core.exotics.asian_geometric(*args)}


@op("exotic.lookback.floating")
def _lookback(i: Inputs) -> Any:
    args = (i.real("spot"), i.real("expiry_years"), i.real("rate"), i.real("dividend_yield"),
            i.real("vol"), i.enum("option_type", _OPTION_TYPES), i.real("running_extreme"))
    return {"price": core.exotics.lookback(*args)}


@op("exotic.quanto.price")
def _quanto(i: Inputs) -> Any:
    args = (i.real("spot"), i.real("strike"), i.real("expiry_years"), i.real("domestic_rate"),
            i.real("foreign_rate"), i.real("dividend_yield"), i.real("vol"), i.real("fx_vol"),
            i.real("correlation"), i.enum("option_type", _OPTION_TYPES))
    return {"price": core.exotics.quanto(*args)}


@op("exotic.chooser.price")
def _chooser(i: Inputs) -> Any:
    args = (i.real("spot"), i.real("strike"), i.real("expiry_years"), i.real("rate"),
            i.real("dividend_yield"), i.real("vol"), i.real("choose_years"))
    return {"price": core.exotics.chooser(*args)}


@op("exotic.spread.kirk")
def _kirk(i: Inputs) -> Any:
    args = (i.real("forward_1"), i.real("forward_2"), i.real("strike"), i.real("expiry_years"),
            i.real("rate"), i.real("vol_1"), i.real("vol_2"), i.real("correlation"))
    return {"price": core.exotics.kirk(*args)}


@op("exotic.basket.moment")
def _basket(i: Inputs) -> Any:
    args = (i.reals("forwards"), i.reals("weights"), i.reals("vols"), i.matrix("correlation"),
            i.real("strike"), i.real("expiry_years"), i.real("rate"),
            i.enum("option_type", _OPTION_TYPES))
    return core.exotics.basket(*args)


@op("exotic.american.crr")
def _crr(i: Inputs) -> Any:
    return core.exotics.crr(*_option_common(i), i.integer("steps"))


@op("exotic.american.baw")
def _baw(i: Inputs) -> Any:
    return {"price": core.exotics.baw(*_option_common(i))}


@op("exotic.american.fd")
def _fd(i: Inputs) -> Any:
    g = i.object("grid")
    args = (*_option_common(i), i.enum("exercise", ("AMERICAN", "EUROPEAN")), g.integer("nx"),
            g.integer("nt"), g.real("width"))
    return core.exotics.fd(*args)
