"""Handlers for the hedging verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from ..errors import QfError
from .inputs import Inputs
from .ops_credit import _hazard
from .readers import _curve, _objects
from .registry import core, op


@op("hedge.solve")
def hedge_solve(i: Inputs) -> Any:
    x, residual, objective = core.hedging.solve(
        i.matrix("a"), i.reals("b"), i.reals("weights"), i.reals("costs"), i.real("lambda"))
    return {"x": x, "residual": residual, "objective": objective}


@op("hedge.spread_cost")
def spread_cost(i: Inputs) -> Any:
    return {"cost": core.hedging.spread_cost(i.reals("quantities"), i.reals("half_spreads"))}


# Stage I wave 1 (08-hedging/hedge-solvers.md). `null` is legal only inside the bound lists (I-12).

def _opt_matrix(i: Inputs, key: str) -> list[list[float]] | None:
    return i.matrix(key) if i.has(key) else None


def _opt_reals(i: Inputs, key: str) -> list[float] | None:
    return i.reals(key) if i.has(key) else None


def _opt_bounds(i: Inputs, key: str) -> list[float | None] | None:
    return i.nullable_reals(key) if i.has(key) else None


def _opt_lot_bounds(i: Inputs, key: str) -> list[int | None] | None:
    if not i.has(key):
        return None
    values = i.array(key)
    if not all(v is None or (not isinstance(v, bool) and isinstance(v, int)) for v in values):
        raise QfError("E_SCHEMA", f"{key}: not an array of integers and nulls", key)
    return values


def _least_squares(i: Inputs) -> tuple[list[list[float]], list[float], list[float], float]:
    return i.matrix("a"), i.reals("b"), i.reals("weights"), i.opt_real("ridge", 0.0)


def _qp_args(i: Inputs) -> tuple[Any, ...]:
    """Every `hedge.qp.solve` input after a, b, weights and ridge, wave 4a ones included."""
    singular = i.enum("singular", ("ERROR", "MIN_NORM")) if i.has("singular") else "ERROR"
    return (_opt_matrix(i, "eq_matrix"), _opt_reals(i, "eq_rhs"), _opt_bounds(i, "lower"),
            _opt_bounds(i, "upper"), singular, _opt_reals(i, "half_spreads"),
            _opt_reals(i, "impact"))


@op("hedge.qp.solve")
def hedge_qp_solve(i: Inputs) -> Any:
    a, b, weights, ridge = _least_squares(i)
    args = (*_qp_args(i), i.opt_real("cost_weight"), _opt_reals(i, "margin_rates"),
            i.opt_real("margin_limit"))
    return core.hedge_solvers.qp_solve(a, b, weights, ridge, *args)


@op("hedge.frontier.solve")
def hedge_frontier_solve(i: Inputs) -> Any:
    a, b, weights, ridge = _least_squares(i)
    args = (*_qp_args(i), _opt_reals(i, "margin_rates"), i.opt_real("margin_limit"),
            i.opt_real("cost_weight"))
    return core.hedge_solvers.frontier_solve(a, b, weights, i.reals("cost_weights"), ridge,
                                             *args)


@op("hedge.integer.solve")
def hedge_integer_solve(i: Inputs) -> Any:
    a, b, weights, ridge = _least_squares(i)
    lots = i.reals("lot_sizes")
    lower, upper = _opt_lot_bounds(i, "lower_lots"), _opt_lot_bounds(i, "upper_lots")
    return core.hedge_solvers.integer_solve(a, b, weights, lots, ridge, lower, upper)


@op("hedge.minvar.ratio")
def hedge_minvar_ratio(i: Inputs) -> Any:
    return core.hedge_solvers.minvar_ratio(
        _opt_matrix(i, "covariance"), _opt_reals(i, "exposure_changes"),
        _opt_matrix(i, "hedge_changes"))


def _instruments(i: Inputs, key: str, held: bool) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []
    for k, item in enumerate(i.array(key)):
        if not isinstance(item, dict):
            raise QfError("E_SCHEMA", f"{key}/{k}: not an object", key)
        p = Inputs(item, f"{key}/{k}.")
        entry = (p.enum("instrument", ("CALL", "PUT", "UNDERLYING")), p.opt_real("strike"),
                 p.opt_real("expiry_years"))
        out.append((*entry, p.real("quantity")) if held else entry)
    return out


@op("hedge.greeks.neutralise")
def hedge_greeks_neutralise(i: Inputs) -> Any:
    market = (i.real("spot"), i.real("rate"), i.real("dividend_yield"), i.real("volatility"))
    portfolio = _instruments(i, "portfolio", True)
    hedges = _instruments(i, "hedges", False)
    targets = i.array("targets")
    if not all(isinstance(t, str) and t in ("DELTA", "GAMMA", "VEGA") for t in targets):
        raise QfError("E_SCHEMA", "targets: each must be DELTA, GAMMA or VEGA", "targets")
    return core.hedge_solvers.greeks_neutralise(*market, portfolio, hedges, targets)


@op("hedge.beta.futures")
def hedge_beta_futures(i: Inputs) -> Any:
    args = (i.real("portfolio_value"), i.real("portfolio_beta"), i.real("target_beta"),
            i.real("futures_price"), i.real("multiplier"))
    rounding = i.enum("rounding", ("NEAREST", "NONE")) if i.has("rounding") else "NEAREST"
    return core.hedge_solvers.beta_futures(*args, rounding)


@op("hedge.residual.report")
def hedge_residual_report(i: Inputs) -> Any:
    return core.hedge_solvers.residual_report(
        i.matrix("a"), i.reals("b"), i.reals("x"), i.matrix("covariance"))


# Stage I wave 2 (08-hedging/credit-and-correlation-hedges.md).

def _targets(i: Inputs) -> list[str]:
    targets = i.array("targets")
    if not all(isinstance(t, str) for t in targets):
        raise QfError("E_SCHEMA", "targets: not an array of strings", "targets")
    return targets


@op("hedge.credit.cds")
def hedge_credit_cds(i: Inputs) -> Any:
    as_of, dates, survival = _hazard(i.object("hazard"))
    book = [(t.date("maturity"), t.real("coupon"), t.real("notional"),
             t.enum("side", ("BUY_PROTECTION", "SELL_PROTECTION"))) for t in _objects(i, "book")]
    hedges = [(t.date("maturity"), t.real("coupon")) for t in _objects(i, "hedges")]
    args = (i.date("trade_date"), _curve(i, "discount"), as_of, dates, survival,
            i.real("recovery"), book, hedges, _targets(i))
    return core.credit_correlation_hedges.credit_cds(*args)


_KINDS = ("EXCHANGE", "CALL_1", "PUT_1", "CALL_2", "PUT_2", "UNDERLYING_1", "UNDERLYING_2")


def _positions(i: Inputs, key: str,
               kinds: tuple[str, ...] = _KINDS) -> list[tuple[str, dict[str, float]]]:
    """(instrument, its other keys as numbers). Which keys a kind takes is the core's E_INPUT."""
    out = []
    for p in _objects(i, key):
        kind = p.enum("instrument", kinds)
        out.append((kind, {k: p.real(k) for k in p.raw if k != "instrument" and p.has(k)}))
    return out


@op("hedge.correlation.neutralise")
def hedge_correlation_neutralise(i: Inputs) -> Any:
    market = tuple(i.real(k) for k in ("spot1", "spot2", "rate", "yield1", "yield2", "vol1",
                                       "vol2", "correlation"))
    args = (*market, _positions(i, "book"), _positions(i, "hedges"), _targets(i))
    return core.credit_correlation_hedges.correlation_neutralise(*args)


# Stage I wave 3 (08-hedging/cross-asset-hedge.md).

@op("hedge.crossasset.solve")
def hedge_crossasset_solve(i: Inputs) -> Any:
    curve = i.object("curve")
    kinds = ("CALL", "PUT", "FORWARD", "ZCB", "UNDERLYING")
    args = (i.real("spot"), i.real("dividend_yield"), i.real("volatility"), curve.reals("times"),
            curve.reals("zero_rates"), _positions(i, "book", kinds),
            _positions(i, "hedges", kinds), i.reals("weights"), i.opt_real("ridge", 0.0))
    return core.cross_asset_hedge.crossasset_solve(*args)
