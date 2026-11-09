"""Handlers for the fx verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from .. import conventions, curves
from ..errors import QfError
from ..fx import FxSwap
from .inputs import Inputs
from .readers import (
    _OPTION_TYPES,
    _convention,
    _curve,
    _forward_trade,
    _market,
    _objects,
    _pillars,
    _present,
    _tenor,
)
from .registry import core, op


def _months(tenor: str) -> int:
    n, unit = int(tenor[:-1]), tenor[-1]
    if unit not in "MY":
        raise QfError("E_SCHEMA", "FX points need a month or year tenor", "tenor")
    return n * 12 if unit == "Y" else n


@op("fx.spot_date")
def spot_date(i):
    d = core.fx.spot_date(i.enum("pair", conventions.PAIRS), i.date("trade_date"))
    return {"spot_date": d.isoformat()}


@op("fx.forward.outright")
def outright(i):
    f, points = core.fx.outright(_market(i), i.date("value_date"))
    return {"forward": f, "points": points}


@op("fx.forward.pv")
def fx_pv(i):
    value, delta = core.fx.forward_pv(_market(i), _forward_trade(i.object("trade")))
    return {"valuation": value, "fx_delta": delta}


@op("fx.swap.pv")
def fx_swap(i):
    t = i.object("trade")
    trade = FxSwap(t.real("notional_base"), t.date("near_date"), t.real("near_rate"),
                   t.date("far_date"), t.real("far_rate"), t.enum("far_side", ("BUY", "SELL")))
    value, delta = core.fx.swap_pv(_market(i), trade)
    return {"valuation": value, "fx_delta": delta}


@op("fx.curve.implied")
def fx_implied(i):
    market = _market(i)
    points = [(_months(_tenor(p)), p.real("points")) for p in _objects(i, "points")]
    return {"nodes": core.fx.implied(market, points)}


@op("fx.xccy.bootstrap")
def _xccy_bootstrap(i: Inputs) -> Any:
    quotes = [(q.integer("months"), q.real("spread")) for q in _objects(i, "quotes")]
    args = (_curve(i, "domestic"), _curve(i, "foreign_projection"),
            _convention(i, "domestic_convention", ("SOFR",)), _convention(i, "foreign_convention", ("ESTR",)),
            i.date("start"), quotes, i.enum("interpolation", curves.INTERPOLATIONS))
    data, error = core.xccy.bootstrap(*args)
    return {"pillars": _pillars(data)}, {"max_repricing_error": error}


@op("fx.xccy.pv")
def _xccy_pv(i: Inputs) -> Any:
    t = i.object("trade")
    args = (_curve(i, "domestic"), _curve(i, "foreign_projection"),
            _curve(i, "foreign_discount"), i.real("spot"), t.date("start"), t.integer("months"),
            t.real("foreign_notional"), t.real("spread"),
            t.enum("side", ("RECEIVE_FOREIGN", "PAY_FOREIGN")))
    foreign, domestic, value = core.xccy.pv(*args)
    return {"pv": value, "foreign_leg": foreign, "domestic_leg": domestic}


@op("fx.ndf.pv")
def _ndf(i: Inputs) -> Any:
    _present(i, "fixing")
    t = i.object("trade")
    fixing = i.real("fixing") if i.has("fixing") else None
    args = (_curve(i, "usd_curve"), _curve(i, "offshore_curve"), i.real("spot"),
            t.date("fixing_date"), t.date("payment_date"), t.real("strike"),
            t.real("usd_notional"), t.enum("side", ("BUY", "SELL")), fixing)
    value, forward = core.xccy.ndf_pv(*args)
    return {"pv": value, "forward": forward}


def _fx_market(i: Inputs) -> tuple[float, float, float, float]:
    return i.real("spot"), i.real("expiry_years"), i.real("domestic_rate"), i.real("foreign_rate")


def _delta_type(i: Inputs) -> str:
    from ..fx_smile import DELTA_TYPES

    return i.enum("delta_type", DELTA_TYPES)


@op("fx.option.price")
def _fx_price(i: Inputs) -> Any:
    spot, t, rd, rf = _fx_market(i)
    args = (spot, i.real("strike"), t, rd, rf, i.real("vol"), i.enum("option_type", _OPTION_TYPES),
            i.real("notional"))
    return core.fx_smile.option_price(*args)


@op("fx.delta.from_strike")
def _fx_delta_from_strike(i: Inputs) -> Any:
    spot, t, rd, rf = _fx_market(i)
    args = (spot, i.real("strike"), t, rd, rf, i.real("vol"), i.enum("option_type", _OPTION_TYPES))
    return {"deltas": core.fx_smile.delta_from_strike(*args)}


@op("fx.delta.to_strike")
def _fx_delta_to_strike(i: Inputs) -> Any:
    args = (*_fx_market(i), i.real("vol"), i.enum("option_type", _OPTION_TYPES), i.real("delta"),
            _delta_type(i))
    return {"strike": core.fx_smile.delta_to_strike(*args)}


@op("fx.atm.strike")
def _fx_atm_strike(i: Inputs) -> Any:
    from ..fx_smile import ATM_TYPES

    args = (*_fx_market(i), i.real("vol"), i.enum("atm_type", ATM_TYPES), _delta_type(i))
    return {"strike": core.fx_smile.atm_strike(*args)}


@op("fx.smile.from_quotes")
def _fx_smile(i: Inputs) -> Any:
    from ..fx_smile import ATM_TYPES

    args = (*_fx_market(i), i.real("atm_vol"), i.real("rr"), i.real("bf"), i.real("delta"),
            _delta_type(i), i.enum("atm_type", ATM_TYPES))
    return core.fx_smile.smile_from_quotes(*args)
