"""Handlers for the usecases verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from .. import curves
from .inputs import Inputs
from .readers import (
    OPTIONS,
    _curve,
    _forward_trade,
    _market,
    _objects,
    _ois_trade,
    _parity_quotes,
    _quotes,
    _tenor,
    _valuation,
)
from .registry import core, op


@op("usecase.fx_hedge")
def fx_hedge(i):
    market = _market(i)
    book = [_forward_trade(t) for t in _objects(i, "book")]
    return core.usecases.fx_hedge(market, book, i.real("half_spread"))


@op("usecase.rates_hedge")
def rates_hedge(i):
    tenors = [_tenor(Inputs({"tenor": t})) for t in i.array("hedge_tenors")]
    return core.usecases.rates_hedge(
        i.date("as_of"), _quotes(i), i.enum("interpolation", curves.INTERPOLATIONS),
        _ois_trade(i), tenors, i.real("hedge_unit_notional"), i.real("half_spread_bp"),
    )


@op("usecase.vol_surface")
def _vol_surface(i: Inputs) -> Any:
    slices = [(s.date("expiry"), _parity_quotes(s)) for s in _objects(i, "slices")]
    t = i.object("target")
    target = (t.enum("option_type", OPTIONS), t.real("strike"), t.date("expiry"),
              t.real("quantity"), t.enum("side", ("BUY", "SELL")))
    as_of, curve = i.date("as_of"), _curve(i, "funding_curve")
    k_grid, currency = i.reals("k_grid"), i.string("currency")
    r = core.vol_usecase.vol_surface(as_of, curve, slices, k_grid, target)
    return {
        "forwards": r["forwards"], "svi_rmse": r["svi_rmse"],
        "arbitrage_free": r["arbitrage_free"], "vol": r["vol"],
        "valuation": _valuation(r["pv"], currency, as_of, None), "delta": r["delta"],
        "vega": r["vega"],
    }
