"""Handlers for the risk verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from .. import conventions, curves
from ..smile import Position
from .inputs import Inputs
from .readers import (
    OPTIONS,
    _bond,
    _curve,
    _objects,
    _ois_trade,
    _option,
    _quotes,
    _surface,
    _tenor,
)
from .registry import core, op


@op("risk.ois.dv01")
def dv01(i: Inputs) -> Any:
    value, keys = core.sensitivities.dv01(
        i.date("as_of"), _quotes(i), i.enum("interpolation", curves.INTERPOLATIONS),
        _ois_trade(i),
    )
    return {"dv01": value, "key_rate": keys}


@op("risk.cashflows")
def cashflows(i: Inputs) -> Any:
    flows = [(c.real("t"), c.real("amount")) for c in _objects(i, "cashflows")]
    pv, duration, convexity = core.sensitivities.cashflows(flows, i.real("yield"))
    return {"pv": pv, "duration": duration, "convexity": convexity}


@op("risk.vol.greeks")
def _greeks(i: Inputs) -> Any:
    o, vol = _option(i), i.real("vol")
    return core.black.greeks(o, vol)


@op("risk.vol.bump_greeks")
def _bump_greeks(i: Inputs) -> Any:
    o, vol = _option(i), i.real("vol")
    return core.black.bump_greeks(o, vol)


@op("risk.vol.surface_vega")
def _surface_vega(i: Inputs) -> Any:
    s = _surface(i)
    book = [
        Position(p.enum("option_type", OPTIONS), p.real("forward"), p.real("strike"),
                 p.real("discount_factor"), p.real("expiry_years"), p.real("quantity"))
        for p in _objects(i, "positions")
    ]
    return core.smile.surface_vega(s, book)


def _product(i: Inputs) -> Any:
    from ..risk_curve import Product
    from .readers import _ois_trade
    p = i.object("product")
    kind = p.enum("kind", ("OIS", "BOND"))
    if kind == "OIS":
        return Product("OIS", trade=_ois_trade(p))
    return Product("BOND", bond=_bond(p.object("bond")), settlement=p.date("settlement"),
                   notional=p.real("notional"))


def _bump(i: Inputs) -> float:
    return i.opt_real("bump_bp", 1.0)


def _scheme(i: Inputs) -> str:
    from ..risk_curve import SCHEMES
    return i.enum("scheme", SCHEMES) if i.has("scheme") else "CENTRAL"


def _ois_inputs(i: Inputs) -> tuple[Any, ...]:
    return (i.date("as_of"), i.enum("convention", conventions.OVERNIGHT), _quotes_at(i, "quotes"))


def _quotes_at(i: Inputs, key: str) -> Any:
    from ..ois import Quote
    from .readers import _objects
    out = []
    for q in _objects(i, key):
        if q.has("rate"):
            out.append(Quote(_tenor(q), q.real("rate")))
        else:
            out.append(Quote(_tenor(q), None, q.real("bid"), q.real("ask")))
    return out


@op("risk.curve.par")
def _risk_par(i: Inputs) -> Any:
    as_of, convention, quotes = _ois_inputs(i)
    args = (as_of, convention, quotes, i.enum("interpolation", curves.INTERPOLATIONS),
            _product(i), _bump(i), _scheme(i))
    return core.risk_curve.par(*args)


@op("risk.curve.key_rate")
def _risk_key_rate(i: Inputs) -> Any:
    from ..risk_curve import MODES
    mode = i.enum("mode", MODES)
    keys = i.dates("key_dates") if i.has("key_dates") else None
    args = (_curve(i), mode, keys, _product(i), _bump(i), _scheme(i))
    return core.risk_curve.key_rate(*args)


@op("risk.curve.jacobian")
def _risk_jacobian(i: Inputs) -> Any:
    as_of, convention, quotes = _ois_inputs(i)
    args = (as_of, convention, quotes, i.enum("interpolation", curves.INTERPOLATIONS), _bump(i))
    return core.risk_curve.jacobian(*args)


@op("risk.pnl.explain")
def _pnl_explain(i: Inputs) -> Any:
    as_of, convention = i.date("as_of"), i.enum("convention", conventions.OVERNIGHT)
    start, end = _quotes_at(i, "quotes_start"), _quotes_at(i, "quotes_end")
    args = (as_of, convention, i.enum("interpolation", curves.INTERPOLATIONS), start, end,
            _product(i), _bump(i))
    return core.risk_curve.pnl_explain(*args)


@op("risk.corr.validate")
def _corr_validate(i: Inputs) -> Any:
    return core.correlation.validate(i.matrix("matrix"))


@op("risk.corr.nearest")
def _corr_nearest(i: Inputs) -> Any:
    matrix, distance = core.correlation.nearest(i.matrix("matrix"))
    return {"matrix": matrix, "frobenius_distance": distance}


@op("risk.corr.implied")
def _corr_implied(i: Inputs) -> Any:
    args = (i.reals("weights"), i.reals("vols"), i.real("index_vol"))
    return {"correlation": core.correlation.implied(*args)}


@op("risk.corr.dispersion")
def _corr_dispersion(i: Inputs) -> Any:
    args = (i.reals("weights"), i.reals("vol_strikes"), i.real("index_vol_strike"),
            i.reals("realized_vols"), i.real("index_realized_vol"), i.real("vega_notional"))
    return core.correlation.dispersion(*args)
