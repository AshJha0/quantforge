"""Handlers for the inflation verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from .inputs import Inputs
from .readers import _RATE_MODELS, _bond, _curve, _month_index, _objects, _present
from .registry import core, op


def _cpi_curve(c: Inputs) -> Any:
    from ..inflation import CpiCurveData
    _present(c, "seasonality")
    season = tuple(c.reals("seasonality")) if c.has("seasonality") else None
    quotes = tuple((q.real("years"), q.real("rate")) for q in _objects(c, "quotes"))
    return CpiCurveData(_month_index(c, "base_month"), c.real("base_cpi"), quotes, season)


@op("infl.curve.cpi")
def _cpi(i: Inputs) -> Any:
    data = _cpi_curve(i)
    months = [_month_index(Inputs({"m": m}), "m") for m in i.array("months")]
    return {"cpi": core.inflation.cpi(data, months)}


@op("infl.zcis.pv")
def _zcis(i: Inputs) -> Any:
    t = i.object("trade")
    args = (_cpi_curve(i.object("curve")), _curve(i, "discount"), t.integer("years"),
            t.real("fixed_rate"), t.real("notional"),
            t.enum("side", ("RECEIVE_INFLATION", "PAY_INFLATION")), t.date("payment_date"))
    value, ratio = core.inflation.zcis_pv(*args)
    return {"pv": value, "index_ratio": ratio}


@op("infl.linker.price")
def _linker(i: Inputs) -> Any:
    fixings = [(_month_index(f, "month"), f.real("value")) for f in _objects(i, "cpi_fixings")]
    args = (_bond(i.object("bond")), i.date("settlement"), i.real("real_yield"),
            i.real("base_ref_cpi"), fixings)
    return core.inflation.linker_price(*args)


@op("infl.linker.price_curve")
def _linker_curve(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), i.real("base_ref_cpi"),
            _cpi_curve(i.object("curve")), _curve(i, "discount"))
    return {"nominal_dirty": core.inflation.linker_price_curve(*args)}


_CAP_TYPES = ("CAP", "FLOOR")


@op("infl.cap.yoy_price")
def _yoy(i: Inputs) -> Any:
    periods = [(p.real("accrual"), p.real("discount_factor"), p.real("yoy_forward"),
                p.real("expiry_years"), p.real("vol")) for p in _objects(i, "periods")]
    args = (i.enum("model", _RATE_MODELS), i.enum("type", _CAP_TYPES), i.real("strike"),
            i.real("notional"), periods)
    caplets, price = core.rates_vol.yoy_price(*args)
    return {"caplets": caplets, "price": price}


@op("infl.cap.zc_price")
def _zc(i: Inputs) -> Any:
    args = (i.enum("model", _RATE_MODELS), i.enum("type", _CAP_TYPES),
            i.real("forward_index_ratio"), i.real("years"), i.real("strike"),
            i.real("discount_factor"), i.real("vol"), i.real("notional"))
    price, ratio = core.rates_vol.zc_price(*args)
    return {"price": price, "strike_ratio": ratio}
