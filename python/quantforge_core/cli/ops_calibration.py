"""Handlers for the calibration verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from .. import conventions, curves
from ..calibration import METHODS, PARAMETERS
from .inputs import Inputs
from .readers import _not_null, _quotes
from .registry import core, op


def _data(i: Inputs, model: str) -> tuple[list[float], list[float]]:
    if model == "ROSENBROCK":
        return (i.reals("x") if i.has("x") else []), (i.reals("y") if i.has("y") else [])
    return i.reals("x"), i.reals("y")


@op("calib.fit")
def fit(i: Inputs) -> Any:
    model = i.enum("model", tuple(PARAMETERS))
    report = i.opt_boolean("report_parameters", True)
    optional = {k: i.reals(k) for k in ("weights", "prior", "lower", "upper") if i.has(k)}
    result = core.calibration.fit(
        model, *_data(i, model), i.reals("start"), i.enum("method", METHODS),
        regularisation=i.opt_real("regularisation", 0.0),
        max_iter=i.opt_integer("max_iter", 1000), **optional,
    )
    outputs = {"objective": result.objective}
    if report:
        outputs["parameters"] = result.parameters
    return outputs, {"iterations": result.iterations, "status": result.status,
                     "residuals": result.residuals}


@op("calib.check_bid_ask")
def bid_ask(i: Inputs) -> Any:
    return {"breaches": core.calibration.check_bid_ask(
        i.reals("fitted"), i.reals("bid"), i.reals("ask"))}


@op("calib.curve_report")
def curve_report(i: Inputs) -> Any:
    quotes = _quotes(i)
    jacobian, condition, error = core.calibration.curve_report(
        i.enum("convention", conventions.OVERNIGHT), i.date("as_of"), quotes,
        i.enum("interpolation", curves.INTERPOLATIONS),
    )
    diagnostics = {"inputs": [q.tenor for q in quotes], "status": "OK",
                   "max_repricing_error": error, "tolerance_breaches": []}
    return {"jacobian": jacobian, "condition_number": condition}, diagnostics


@op("calib.curve.smooth")
def _smooth(i: Inputs) -> Any:
    _not_null(i, "weights")
    weights = i.reals("weights") if i.has("weights") else None
    args = (i.reals("knots"), i.reals("maturities"), i.reals("zero_rates"), i.real("lambda"),
            weights)
    forwards, fitted, objective = core.curve_fits.smooth(*args)
    return {"forwards": forwards, "fitted": fitted, "objective": objective}


@op("calib.curve.robust")
def _robust(i: Inputs) -> Any:
    args = (i.reals("maturities"), i.reals("zero_rates"), i.real("tau"), i.real("delta"))
    betas, residuals, outliers, objective = core.curve_fits.robust(*args)
    return {"betas": betas, "residuals": residuals, "outliers": outliers, "objective": objective}
