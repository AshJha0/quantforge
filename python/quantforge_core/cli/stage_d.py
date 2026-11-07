"""Handlers for the stage D operations. As in stage_c.py, a handler reads every input first; the
first call through `D`, the gated core modules, ends the E_SCHEMA stage."""
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from .. import conventions, curves
from ..calendars import TENOR
from ..errors import QfError
from ..overnight import FALLBACKS, METHODS
from ..projection import ProjectionQuote
from .inputs import Inputs
from .stage_b import _curve, _objects, _pillars, _quotes, jumps
from .stage_c import _not_null, _present

Handler = Callable[[Inputs], Any]
_OPS: dict[str, Handler] = {}
D = SimpleNamespace()
_BOOT = ("SEQUENTIAL", "GLOBAL")


def op(name: str) -> Callable[[Handler], Handler]:
    def register(f: Handler) -> Handler:
        _OPS[name] = f
        return f

    return register


def _fixings(i: Inputs) -> list[tuple[Any, float]]:
    return [(f.date("date"), f.real("rate")) for f in _objects(i, "fixings")]


@op("rates.ois.compound_dated")
def _compound_dated(i: Inputs) -> Any:
    args = (i.enum("convention", tuple(conventions.REGISTRY)), i.date("start"), i.date("end"),
            i.enum("method", METHODS), i.integer("shift_days"), _fixings(i))
    rate, accrual, interest = D.overnight.compound_dated(*args)
    return {"compounded_rate": rate, "accrual": accrual, "interest": interest}


@op("rates.fallback.rate")
def _fallback(i: Inputs) -> Any:
    args = (i.enum("ibor", tuple(FALLBACKS)), i.date("start"), i.date("end"), _fixings(i))
    rate, spread, total = D.overnight.fallback(*args)
    return {"compounded_rate": rate, "spread_adjustment": spread, "fallback_rate": total}


def _dated_rates(i: Inputs, key: str) -> list[tuple[Any, float]]:
    return [(s.date("date"), s.real("rate")) for s in _objects(i, key)]


@op("rates.ois.step_curve")
def _step_curve(i: Inputs) -> Any:
    args = (i.date("as_of"), i.real("base_rate"), _dated_rates(i, "steps"),
            jumps(i, required=True), i.dates("dates"))
    factors, forwards = D.steps.step_curve(*args)
    return {"discount_factors": factors, "overnight_forwards": forwards}


@op("rates.ois.fit_steps")
def _fit_steps(i: Inputs) -> Any:
    args = (i.enum("convention", conventions.OVERNIGHT), i.date("as_of"), i.dates("step_dates"),
            _quotes(i), jumps(i, required=True))
    base, rates, error = D.steps.fit_steps(*args)
    return {"base_rate": base, "step_rates": rates}, {"max_repricing_error": error}


@op("rates.futures.convexity")
def _convexity(i: Inputs) -> Any:
    args = (i.real("price"), i.real("start_years"), i.real("end_years"), i.real("sigma"),
            i.real("mean_reversion"))
    rate, bias, forward = D.futures.convexity(*args)
    return {"futures_rate": rate, "convexity": bias, "forward_rate": forward}


@op("rates.csa.discount")
def _csa(i: Inputs) -> Any:
    _present(i, "fx")
    fx = None
    if i.has("fx"):
        f = i.object("fx")
        fx = (f.real("spot"), [(p.date("date"), p.real("forward")) for p in _objects(f, "forwards")])
    args = (_curve(i), i.real("collateral_spread"), fx, i.dates("dates"))
    return {"discount_factors": D.csa.discount(*args)}


def _tenor(i: Inputs) -> str:
    tenor = i.string("tenor")
    if TENOR.fullmatch(tenor) is None:
        raise QfError("E_SCHEMA", f"bad tenor {tenor}", "tenor")
    return tenor


@op("rates.basis.ois_spread")
def _ois_spread(i: Inputs) -> Any:
    args = (i.enum("convention", conventions.OVERNIGHT), _tenor(i), _curve(i, "discount"),
            _curve(i, "projection_a"), _curve(i, "projection_b"))
    return {"spread": D.csa.ois_spread(*args)}


def _term_quote(q: Inputs) -> ProjectionQuote:
    kind = q.enum("type", ("DEPOSIT", "FRA", "SWAP"))
    return ProjectionQuote(kind, q.integer("start_months" if kind == "FRA" else "months"),
                           q.real("rate"))


@op("rates.curve.joint_bootstrap")
def _joint(i: Inputs) -> Any:
    ois_quotes = _quotes(Inputs({"quotes": i.array("ois_quotes")}, "ois_"))
    args = (i.enum("convention", conventions.OVERNIGHT), i.enum("index", conventions.TERM),
            i.date("as_of"), ois_quotes, [_term_quote(q) for q in _objects(i, "term_quotes")],
            i.enum("interpolation", curves.INTERPOLATIONS), i.enum("method", _BOOT))
    disc, proj, error = D.csa.joint_bootstrap(*args)
    return ({"discount_pillars": _pillars(disc), "projection_pillars": _pillars(proj)},
            {"max_repricing_error": error})


@op("calib.curve.smooth")
def _smooth(i: Inputs) -> Any:
    _not_null(i, "weights")
    weights = i.reals("weights") if i.has("weights") else None
    args = (i.reals("knots"), i.reals("maturities"), i.reals("zero_rates"), i.real("lambda"),
            weights)
    forwards, fitted, objective = D.curve_fits.smooth(*args)
    return {"forwards": forwards, "fitted": fitted, "objective": objective}


@op("calib.curve.robust")
def _robust(i: Inputs) -> Any:
    args = (i.reals("maturities"), i.reals("zero_rates"), i.real("tau"), i.real("delta"))
    betas, residuals, outliers, objective = D.curve_fits.robust(*args)
    return {"betas": betas, "residuals": residuals, "outliers": outliers, "objective": objective}


def handlers(core: SimpleNamespace) -> dict[str, Handler]:
    D.__dict__.update(core.__dict__)
    return _OPS
