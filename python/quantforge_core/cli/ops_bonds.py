"""Handlers for the bonds verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from ..bonds import CONTRACTS
from ..errors import QfError
from .inputs import Inputs
from .readers import _bond, _curve, _month, _not_null, _objects, _present
from .registry import core, op


@op("bond.price.from_yield")
def _bond_from_yield(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), i.real("yield"))
    return core.bonds.price_from_yield(*args)


@op("bond.yield.from_price")
def _bond_yield(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), i.real("clean_price"))
    return core.bonds.yield_from_price(*args)


@op("bond.price.from_curve")
def _bond_from_curve(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), _curve(i))
    return core.bonds.price_from_curve(*args)


@op("bond.spread.z")
def _bond_z(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), _curve(i), i.real("clean_price"))
    return {"z_spread": core.bonds.z_spread(*args)}


@op("bond.spread.asset_swap")
def _bond_asw(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), _curve(i), i.real("dirty_price"))
    annuity, spread = core.bonds.asset_swap(*args)
    return {"annuity": annuity, "spread": spread}


@op("bond.frn.price")
def _frn(i: Inputs) -> Any:
    from ..bonds import FREQUENCIES
    frequency = i.integer("frequency")
    if frequency not in FREQUENCIES:
        raise QfError("E_SCHEMA", "frequency must be 1, 2 or 4", "frequency")
    args = (i.date("settlement"), i.date("maturity"), frequency, i.real("current_rate"),
            i.real("margin"), i.real("discount_margin"), _curve(i, "discount"),
            _curve(i, "projection"))
    return core.bonds.frn_price(*args)


@op("repo.forward")
def _repo_forward(i: Inputs) -> Any:
    _present(i, "gc_rate")
    gc = i.real("gc_rate") if i.has("gc_rate") else None
    args = (_bond(i.object("bond")), i.date("start"), i.date("end"), i.real("clean_price"),
            i.real("repo_rate"), gc)
    return core.bonds.repo_forward(*args)


@op("repo.implied_rate")
def _repo_implied(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("start"), i.date("end"), i.real("clean_price"),
            i.real("forward_clean"))
    return {"repo_rate": core.bonds.repo_implied(*args)}


@op("bond.futures.conversion_factor")
def _conversion(i: Inputs) -> Any:
    bond, (year, month) = _bond(i.object("bond")), _month(i, "delivery_month")
    contract = i.enum("contract", CONTRACTS) if i.has("contract") else "TEN_YEAR"
    args = (bond, year, month, i.real("notional_coupon"), contract)
    return {"conversion_factor": core.bonds.conversion_factor(*args)}


@op("bond.futures.basis")
def _futures_basis(i: Inputs) -> Any:
    bonds = [(_bond(b), b.real("clean_price"), b.real("conversion_factor"))
             for b in _objects(i, "bonds")]
    args = (i.real("futures_price"), i.date("settlement"), i.date("delivery"),
            i.real("repo_rate"), bonds)
    rows, ctd = core.bonds.futures_basis(*args)
    return {"bonds": rows, "ctd": ctd}


@op("bond.fit.nelson_siegel")
def _bond_fit(i: Inputs) -> Any:
    _not_null(i, "weights")
    bonds = [(_bond(b), b.real("dirty_price")) for b in _objects(i, "bonds")]
    weights = i.reals("weights") if i.has("weights") else None
    betas, residuals = core.bonds.fit_nelson_siegel(i.date("settlement"), i.real("tau"), bonds,
                                                 weights)
    return {"betas": betas, "residuals": residuals}
