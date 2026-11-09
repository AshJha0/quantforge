"""Handlers for the credit verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from ..errors import QfError
from .inputs import Inputs
from .readers import _curve, _objects, _tenor
from .registry import core, op


def _isda(curve: Any) -> None:
    """Ruling R1-4: the first rule check of every credit.* operation."""
    if curve.interpolation != "LOG_LINEAR_DF":
        raise QfError("E_INPUT", "credit needs LOG_LINEAR_DF discounting",
                      "discount.interpolation")


def _hazard(h: Inputs) -> Any:
    pillars = _objects(h, "pillars")
    dates = [p.date("date") for p in pillars]
    return h.date("as_of"), dates, [p.real("survival") for p in pillars]


def _cds_quotes(i: Inputs, key: str = "quotes") -> list[tuple[str, float]]:
    return [(_tenor(q), q.real("spread")) for q in _objects(i, key)]


@op("credit.cds.price")
def _cds_price(i: Inputs) -> Any:
    t = i.object("trade")
    as_of, dates, survival = _hazard(i.object("hazard"))
    args = (i.date("trade_date"), _curve(i, "discount"), i.real("recovery"), t.date("maturity"),
            t.real("coupon"), t.real("notional"),
            t.enum("side", ("BUY_PROTECTION", "SELL_PROTECTION")),
            i.enum("payout", ("STANDARD", "DIGITAL")))
    _isda(args[1])
    hazard = core.credit.check_hazard(as_of, dates, survival)
    return core.credit.price(args[0], args[1], hazard, *args[2:])


@op("credit.cds.bootstrap")
def _cds_bootstrap(i: Inputs) -> Any:
    args = (i.date("trade_date"), _curve(i, "discount"), i.real("recovery"), _cds_quotes(i))
    _isda(args[1])
    pillars = core.credit.bootstrap(*args)
    return {"pillars": [{"date": d.isoformat(), "survival": q} for d, q in pillars]}


@op("credit.index.intrinsic")
def _cds_index(i: Inputs) -> Any:
    t = i.object("trade")
    raw = [(_hazard(n.object("hazard")), n.real("recovery"), n.real("weight"))
           for n in _objects(i, "names")]
    trade_date, disc = i.date("trade_date"), _curve(i, "discount")
    mat, coupon, quoted = t.date("maturity"), t.real("coupon"), i.real("quoted_upfront")
    _isda(disc)
    names = [(core.credit.check_hazard(*h), r, w) for h, r, w in raw]
    ups, intrinsic, basis = core.credit.index_intrinsic(trade_date, disc, names, mat, coupon,
                                                     quoted)
    return {"name_upfronts": ups, "intrinsic_upfront": intrinsic, "basis": basis}


@op("credit.curve.composite")
def _cds_composite(i: Inputs) -> Any:
    constituents = [(_cds_quotes(c), c.real("weight")) for c in _objects(i, "constituents")]
    args = (i.date("trade_date"), _curve(i, "discount"), i.real("recovery"), constituents,
            i.real("scale"))
    _isda(args[1])
    spreads, pillars = core.credit.composite(*args)
    return {"spreads": spreads,
            "pillars": [{"date": d.isoformat(), "survival": q} for d, q in pillars]}


def _cds_option(i: Inputs) -> tuple[Any, ...]:
    return (i.date("as_of"), i.date("expiry"), i.date("maturity"), i.real("rate"),
            i.real("hazard_rate"), i.real("recovery"), i.enum("type", ("PAYER", "RECEIVER")),
            i.real("strike"), i.real("notional"))


@op("credit.cdsoption.price")
def _cds_option_price(i: Inputs) -> Any:
    args = (*_cds_option(i), i.real("vol"), i.boolean("knock_out"))
    return core.credit_options.cds_option_price(*args)


@op("credit.cdsoption.implied_vol")
def _cds_option_implied(i: Inputs) -> Any:
    args = (*_cds_option(i), i.real("premium"), i.boolean("knock_out"))
    return {"vol": core.credit_options.cds_option_implied(*args)}


@op("credit.copula.joint_default")
def _joint_default(i: Inputs) -> Any:
    args = (i.enum("copula", ("GAUSSIAN", "STUDENT_T")), i.reals("default_probabilities"),
            i.real("correlation"), i.opt_real("degrees_of_freedom"))
    return core.credit_options.joint_default(*args)


def _pool(i: Inputs) -> tuple[float, float, float]:
    return i.real("default_probability"), i.real("correlation"), i.real("recovery")


@op("credit.lhp.tranche_loss")
def _tranche_loss(i: Inputs) -> Any:
    args = (*_pool(i), i.real("attachment"), i.real("detachment"))
    return {"expected_loss_fraction": core.credit_options.tranche_loss(*args)}


@op("credit.lhp.loss_cdf")
def _loss_cdf(i: Inputs) -> Any:
    return {"cdf": core.credit_options.loss_cdf(*_pool(i), i.reals("losses"))}
