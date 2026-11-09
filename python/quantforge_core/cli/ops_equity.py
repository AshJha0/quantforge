"""Handlers for the equity verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from .inputs import Inputs
from .readers import _curve, _forward_args, _objects, _parity_quotes, _present
from .registry import core, op


@op("eq.forward.outright")
def _outright(i: Inputs) -> Any:
    r = core.equity.outright(*_forward_args(i))
    return {
        "forward": r.forward, "discount_factor": r.discount_factor,
        "carry_factor": r.carry_factor, "pv_dividends": r.pv_dividends,
    }


@op("eq.forward.flat")
def _flat(i: Inputs) -> Any:
    dividends = [(d.real("time_years"), d.real("amount")) for d in _objects(i, "dividends")]
    forward = core.equity.flat(
        i.real("spot"), i.real("rate"), i.real("borrow"), i.real("expiry_years"), dividends
    )
    return {"forward": forward}


@op("eq.forward.parity")
def _parity(i: Inputs) -> Any:
    _present(i, "discount_factor")
    quotes = _parity_quotes(i)
    d = i.real("discount_factor") if i.has("discount_factor") else None
    f, d, residual, outside = core.equity.parity(quotes, d)
    return {
        "forward": f, "discount_factor": d, "max_residual": residual, "outside_spread": outside,
    }


def _divs(i: Inputs, key: str = "dividends") -> list[tuple[Any, float]]:
    return [(d.date("ex_date"), d.real("amount")) for d in _objects(i, key)]


@op("eq.dividend.implied")
def _div_implied(i: Inputs) -> Any:
    futures = [(f.date("expiry"), f.real("price")) for f in _objects(i, "futures")]
    args = (i.real("spot"), _curve(i, "funding"), i.real("borrow_rate"), futures)
    xs, periods, yields = core.equity_curves.dividend_implied(*args)
    return {"pv_dividends": xs, "period_pv_dividends": periods, "dividend_yields": yields}


@op("eq.borrow.implied")
def _borrow_implied(i: Inputs) -> Any:
    args = (i.real("spot"), _curve(i, "funding"), _divs(i), i.date("expiry"), i.real("forward"))
    return {"borrow_rate": core.equity_curves.borrow_implied(*args)}


@op("eq.futures.basis")
def _eq_futures_basis(i: Inputs) -> Any:
    args = (i.real("spot"), _curve(i, "funding"), i.real("borrow_rate"),
            i.real("financing_spread"), _divs(i), i.date("expiry"), i.real("futures_price"))
    fair, basis, implied = core.equity_curves.futures_basis(*args)
    return {"fair_price": fair, "basis": basis, "implied_financing_spread": implied}


@op("eq.index.dividends")
def _index_divs(i: Inputs) -> Any:
    cons = [(c.string("id"), c.real("shares"), c.real("price"), _divs(c))
            for c in _objects(i, "constituents")]
    periods = [(p.date("start"), p.date("end")) for p in _objects(i, "periods")]
    args = (i.real("divisor"), cons, periods, i.reals("implied_period_points"))
    return core.equity_curves.index_dividends(*args)


def _members(i: Inputs, key: str) -> list[tuple[str, float, float]]:
    return [(c.string("id"), c.real("shares"), c.real("price")) for c in _objects(i, key)]


@op("eq.index.rebalance")
def _rebalance(i: Inputs) -> Any:
    args = (i.real("divisor"), _members(i, "constituents"), _members(i, "new_constituents"))
    level, divisor, weights = core.equity_curves.rebalance(*args)
    return {"level": level, "new_divisor": divisor, "weights": weights}


_ACTION_KEYS = {"SPLIT": ("ratio",), "REVERSE_SPLIT": ("ratio",),
                "RIGHTS": ("new_per_old", "subscription_price"), "SPECIAL_DIVIDEND": ("amount",)}


@op("eq.corporate_action.adjust")
def _corporate_action(i: Inputs) -> Any:
    action = i.enum("action", tuple(_ACTION_KEYS))
    params = {k: i.real(k) for k in _ACTION_KEYS[action]}
    args = (action, i.real("cum_price"), i.real("shares"), i.real("strike"), params)
    return core.equity_curves.corporate_action(*args)


@op("eq.trs.pv")
def _trs(i: Inputs) -> Any:
    _present(i, "current_rate")
    t = i.object("trade")
    current = i.real("current_rate") if i.has("current_rate") else None
    args = (i.real("spot"), _curve(i, "funding"), i.real("borrow_rate"), _divs(i),
            t.date("start"), t.date("end"), t.real("initial_price"), t.real("shares"),
            t.real("spread"), t.enum("side", ("RECEIVE_EQUITY", "PAY_EQUITY")), current)
    equity, funding_leg, value = core.equity_curves.trs_pv(*args)
    return {"equity_leg": equity, "funding_leg": funding_leg, "pv": value}
