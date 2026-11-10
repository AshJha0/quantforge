"""Handlers for the rates verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from .. import calendars, conventions, curves
from .. import daycount as _daycount
from ..errors import QfError
from ..overnight import FALLBACKS, METHODS
from ..projection import FraTrade, ProjectionQuote, SwapTrade
from ..schedules import FREQUENCIES
from .inputs import Inputs
from .readers import (
    _OPTION_TYPES,
    _RATE_MODELS,
    _convention,
    _curve,
    _objects,
    _ois_trade,
    _pillars,
    _present,
    _quotes,
    _tenor,
    jumps,
)
from .registry import core, op


@op("rates.schedule.generate")
def schedule(i: Inputs) -> Any:
    start, end = i.date("start"), i.date("end")
    frequency = i.integer("frequency_months")
    if frequency not in FREQUENCIES:
        raise QfError("E_SCHEMA", "frequency_months is not listed", "frequency_months")
    periods = core.schedules.generate(
        start, end, frequency, i.enum("calendar", calendars.CALENDARS),
        i.boolean("end_of_month"), i.integer("payment_lag"),
    )
    return {"periods": [
        {"start": p.start.isoformat(), "end": p.end.isoformat(),
         "payment": p.payment.isoformat()}
        for p in periods
    ]}


@op("rates.curve.discount")
def curve_discount(i: Inputs) -> Any:
    data = _curve(i)
    factors, zeros = core.curves.discount(data, i.dates("dates"))
    return {"discount_factors": factors, "zero_rates": zeros}


@op("rates.curve.forward")
def curve_forward(i: Inputs) -> Any:
    data, start, end = _curve(i), i.date("start"), i.date("end")
    day_count = i.enum("day_count", _daycount.CONVENTIONS)
    _daycount.check_conditional(day_count)
    return {"forward": core.curves.forward(data, start, end, day_count)}


@op("rates.ois.bootstrap")
def bootstrap(i: Inputs) -> Any:
    data, error = core.ois.bootstrap(
        i.enum("convention", conventions.OVERNIGHT), i.date("as_of"), _quotes(i),
        i.enum("interpolation", curves.INTERPOLATIONS),
        i.enum("method", ("SEQUENTIAL", "GLOBAL")), jumps(i),
    )
    return {"pillars": _pillars(data)}, {"max_repricing_error": error}


@op("rates.ois.compound")
def compound(i: Inputs) -> Any:
    days = i.array("days")
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in days):
        raise QfError("E_SCHEMA", "days must be integers", "days")
    denominator = i.integer("denominator")
    if denominator not in (360, 365):
        raise QfError("E_SCHEMA", "denominator is not listed", "denominator")
    return {"compounded_rate": core.ois.compound(i.reals("rates"), days, denominator)}


@op("rates.ois.pv")
def ois_pv(i: Inputs) -> Any:
    value, par, annuity = core.ois.pv(_curve(i), _ois_trade(i), i.opt_string("snapshot_id"))
    return {"valuation": value, "par_rate": par, "annuity": annuity}


def projection_quote(q: Inputs) -> ProjectionQuote:
    kind = q.enum("type", ("DEPOSIT", "FRA", "SWAP"))
    months = q.integer("start_months" if kind == "FRA" else "months")
    return ProjectionQuote(kind, months, q.real("rate"))


def index(i: Inputs) -> str:
    return i.enum("index", conventions.TERM)


@op("rates.projection.bootstrap")
def projection_bootstrap(i: Inputs) -> Any:
    data, error = core.projection.bootstrap(
        _curve(i, "discount"), index(i), i.date("as_of"),
        [projection_quote(q) for q in _objects(i, "quotes")],
        i.enum("interpolation", curves.INTERPOLATIONS),
    )
    return {"pillars": _pillars(data)}, {"max_repricing_error": error}


@op("rates.swap.pv")
def swap_pv(i: Inputs) -> Any:
    t = i.object("trade")
    trade = SwapTrade(index(t), t.integer("tenor_months"), t.real("fixed_rate"),
                      t.real("notional"), t.enum("side", ("PAY", "RECEIVE")))
    value, par = core.projection.swap_pv(
        _curve(i, "discount"), _curve(i, "projection"), trade, i.opt_string("snapshot_id"))
    return {"valuation": value, "par_rate": par}


@op("rates.fra.pv")
def fra_pv(i: Inputs) -> Any:
    t = i.object("trade")
    trade = FraTrade(index(t), t.date("start"), t.real("fixed_rate"), t.real("notional"),
                     t.enum("side", ("PAY", "RECEIVE")))
    value, rate = core.projection.fra_pv(
        _curve(i, "discount"), _curve(i, "projection"), trade, i.opt_string("snapshot_id"))
    return {"valuation": value, "forward_rate": rate}


@op("rates.basis.spread")
def basis(i: Inputs) -> Any:
    return {"spread": core.projection.basis_spread(
        _curve(i, "discount"), _curve(i, "projection"), index(i), i.integer("tenor_months"))}


_BOOT = ("SEQUENTIAL", "GLOBAL")


def _fixings(i: Inputs) -> list[tuple[Any, float]]:
    return [(f.date("date"), f.real("rate")) for f in _objects(i, "fixings")]


@op("rates.ois.compound_dated")
def _compound_dated(i: Inputs) -> Any:
    args = (i.enum("convention", tuple(conventions.REGISTRY)), i.date("start"), i.date("end"),
            i.enum("method", METHODS), i.integer("shift_days"), _fixings(i))
    rate, accrual, interest = core.overnight.compound_dated(*args)
    return {"compounded_rate": rate, "accrual": accrual, "interest": interest}


@op("rates.fallback.rate")
def _fallback(i: Inputs) -> Any:
    args = (i.enum("ibor", tuple(FALLBACKS)), i.date("start"), i.date("end"), _fixings(i))
    rate, spread, total = core.overnight.fallback(*args)
    return {"compounded_rate": rate, "spread_adjustment": spread, "fallback_rate": total}


def _dated_rates(i: Inputs, key: str) -> list[tuple[Any, float]]:
    return [(s.date("date"), s.real("rate")) for s in _objects(i, key)]


@op("rates.ois.step_curve")
def _step_curve(i: Inputs) -> Any:
    args = (i.date("as_of"), i.real("base_rate"), _dated_rates(i, "steps"),
            jumps(i, required=True), i.dates("dates"))
    factors, forwards = core.steps.step_curve(*args)
    return {"discount_factors": factors, "overnight_forwards": forwards}


@op("rates.ois.fit_steps")
def _fit_steps(i: Inputs) -> Any:
    args = (_convention(i, "convention", conventions.OVERNIGHT), i.date("as_of"), i.dates("step_dates"),
            _quotes(i), jumps(i, required=True))
    base, rates, error = core.steps.fit_steps(*args)
    return {"base_rate": base, "step_rates": rates}, {"max_repricing_error": error}


@op("rates.futures.convexity")
def _convexity(i: Inputs) -> Any:
    args = (i.real("price"), i.real("start_years"), i.real("end_years"), i.real("sigma"),
            i.real("mean_reversion"))
    rate, bias, forward = core.futures.convexity(*args)
    return {"futures_rate": rate, "convexity": bias, "forward_rate": forward}


@op("rates.csa.discount")
def _csa(i: Inputs) -> Any:
    _present(i, "fx")
    fx = None
    if i.has("fx"):
        f = i.object("fx")
        fx = (f.real("spot"), [(p.date("date"), p.real("forward")) for p in _objects(f, "forwards")])
    args = (_curve(i), i.real("collateral_spread"), fx, i.dates("dates"))
    return {"discount_factors": core.csa.discount(*args)}


@op("rates.basis.ois_spread")
def _ois_spread(i: Inputs) -> Any:
    args = (_convention(i, "convention", conventions.OVERNIGHT), _tenor(i), _curve(i, "discount"),
            _curve(i, "projection_a"), _curve(i, "projection_b"))
    return {"spread": core.csa.ois_spread(*args)}


def _term_quote(q: Inputs) -> ProjectionQuote:
    kind = q.enum("type", ("DEPOSIT", "FRA", "SWAP"))
    return ProjectionQuote(kind, q.integer("start_months" if kind == "FRA" else "months"),
                           q.real("rate"))


@op("rates.curve.joint_bootstrap")
def _joint(i: Inputs) -> Any:
    ois_quotes = _quotes(Inputs({"quotes": i.array("ois_quotes")}, "ois_"))
    args = (_convention(i, "convention", conventions.OVERNIGHT), _convention(i, "index", conventions.TERM),
            i.date("as_of"), ois_quotes, [_term_quote(q) for q in _objects(i, "term_quotes")],
            i.enum("interpolation", curves.INTERPOLATIONS), i.enum("method", _BOOT))
    disc, proj, error = core.csa.joint_bootstrap(*args)
    return ({"discount_pillars": _pillars(disc), "projection_pillars": _pillars(proj)},
            {"max_repricing_error": error})


_MODELS = ("BLACK_76", "BACHELIER")


@op("rates.cap.price")
def _cap(i: Inputs) -> Any:
    t = i.object("trade")
    raw = i.raw.get("vol")
    vol: Any = i.reals("vol") if isinstance(raw, list) else i.real("vol")
    args = (_curve(i, "discount"), _curve(i, "projection"), i.enum("model", _MODELS), vol,
            t.enum("type", ("CAP", "FLOOR")), t.integer("start_months"), t.integer("tenor_months"),
            t.real("strike"), t.real("notional"))
    caplets, price = core.caps_swaptions.cap_price(*args)
    return {"price": price, "caplets": caplets}


@op("rates.swaption.price")
def _swaption(i: Inputs) -> Any:
    t = i.object("trade")
    args = (_curve(i, "discount"), _curve(i, "projection"), i.enum("model", _MODELS),
            i.real("vol"), t.enum("type", ("PAYER", "RECEIVER")), t.integer("expiry_months"),
            t.integer("tenor_months"), t.real("strike"), t.real("notional"))
    price, forward, annuity = core.caps_swaptions.swaption_price(*args)
    return {"price": price, "forward_rate": forward, "annuity": annuity}


def _curves(i: Inputs) -> tuple[Any, Any]:
    from .readers import _curve

    return _curve(i, "discount"), _curve(i, "projection")


@op("rates.swaption.price_cube")
def _price_cube(i: Inputs) -> Any:
    c, t = i.object("cube"), i.object("trade")
    params = {k: c.matrix(k) for k in ("alpha", "beta", "rho", "nu")}
    months = [c.integer_list(k) for k in ("expiries_months", "tenors_months")]
    args = (*_curves(i), *months, params, t.enum("type", ("PAYER", "RECEIVER")),
            t.integer("expiry_months"), t.integer("tenor_months"), t.real("strike"),
            t.real("notional"))
    return core.rates_vol.price_cube(*args)


@op("rates.cap.strip")
def _cap_strip(i: Inputs) -> Any:
    args = (*_curves(i), i.enum("model", _RATE_MODELS), i.integer("start_months"),
            i.real("strike"), i.integer_list("cap_tenors_months"), i.reals("flat_vols"),
            i.real("notional"))
    vols, prices = core.rates_vol.cap_strip(*args)
    return {"caplet_vols": vols, "cap_prices": prices}


def _futures(i: Inputs) -> tuple[str, float, float, float, float]:
    return (i.enum("type", _OPTION_TYPES), i.real("futures_price"), i.real("strike"),
            i.real("expiry_years"), i.real("discount_factor"))


@op("rates.bondfut.option_price")
def _bondfut_price(i: Inputs) -> Any:
    price, value = core.rates_vol.bondfut_price(*_futures(i), i.real("vol"), i.real("contract_size"))
    return {"price": price, "contract_value": value}


@op("rates.bondfut.implied_vol")
def _bondfut_implied(i: Inputs) -> Any:
    args = (*_futures(i), i.real("premium"), i.real("ctd_yield"), i.real("ctd_modified_duration"))
    price_vol, yield_vol = core.rates_vol.bondfut_implied(*args)
    return {"price_vol": price_vol, "yield_vol": yield_vol}
