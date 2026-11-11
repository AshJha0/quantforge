"""Handlers for the stage G rates verbs: short-rate models, G2++, the products on them, and the
closed-form swap exposure. A handler reads every input first; the first call through `core` ends
the E_SCHEMA stage."""
from typing import Any

from ..errors import QfError
from .inputs import Inputs
from .registry import core, op

_GAUSS_OR_CIR = ("VASICEK", "CIR")


def _curve(i: Inputs) -> tuple[list[float], list[float]]:
    c = i.object("curve")
    return c.reals("times"), c.reals("discount_factors")


def _model(i: Inputs, rate: str, default: str | None = None) -> Any:
    """Reads a short-rate model. `rate` is the `short_rate` rule: "always" (required for every
    model), or "affine" (required for Vasicek and CIR, E_INPUT for Hull-White, ruling G-5)."""
    kind = i.string("model") if default is None or i.has("model") else default
    a, sigma = i.real("mean_reversion"), i.real("sigma")
    b = times = dfs = r0 = None
    given = False
    if kind in _GAUSS_OR_CIR:
        b, r0 = i.real("long_term_mean"), i.real("short_rate")
    elif kind == "HULL_WHITE":
        times, dfs = _curve(i)
        if rate == "always":
            r0 = i.real("short_rate")
        else:
            given = i.has("short_rate")
    return kind, a, sigma, b, times, dfs, r0, given


def _build(m: Any) -> Any:
    kind, a, sigma, b, times, dfs, r0, given = m
    return core.shortrate.build_model(kind, a, sigma, b, times, dfs, r0, given)


@op("rates.shortrate.zcb")
def _zcb(i: Inputs) -> Any:
    m = _model(i, "always")
    t, mat = i.real("t_years"), i.real("maturity_years")
    model = _build(m)
    return core.shortrate.zcb(model, m[6], t, mat)


def _option_args(i: Inputs) -> tuple[str, float, float, float, float]:
    return (i.string("option_type"), i.real("strike"), i.real("expiry_years"),
            i.real("maturity_years"), i.real("notional"))


@op("rates.shortrate.zcb_option")
def _zcb_option(i: Inputs) -> Any:
    m = _model(i, "affine")
    args = _option_args(i)
    return core.shortrate.zcb_option(_build(m), *args)


def _swap(i: Inputs, expiry: str) -> tuple[float, list[float], float]:
    return i.real(expiry), i.reals("payment_times"), i.real("fixed_rate")


@op("rates.shortrate.swaption")
def _swaption(i: Inputs) -> Any:
    m = _model(i, "affine", default="HULL_WHITE")
    t0, times, k = _swap(i, "expiry_years")
    kind, notional = i.string("swaption_type"), i.real("notional")
    return core.shortrate.swaption(_build(m), t0, times, k, kind, notional)


@op("rates.shortrate.capfloor")
def _capfloor(i: Inputs) -> Any:
    m = _model(i, "affine")
    args = (i.reals("period_times"), i.real("strike"), i.string("cap_floor"), i.real("notional"))
    return core.shortrate.capfloor(_build(m), *args)


def _hw(i: Inputs) -> Any:
    times, dfs = _curve(i)
    return times, dfs, i.real("mean_reversion"), i.real("sigma"), i.has("short_rate")


@op("rates.shortrate.hw_calibrate")
def _hw_calibrate(i: Inputs) -> Any:
    times, dfs = _curve(i)
    a = i.real("mean_reversion")
    strip = []
    for k, item in enumerate(i.array("swaptions")):
        if not isinstance(item, dict):
            raise QfError("E_SCHEMA", f"swaptions/{k}: not an object", f"swaptions/{k}")
        q = Inputs(item, f"swaptions/{k}.")
        strip.append((q.real("expiry_years"), q.reals("payment_times"), q.real("fixed_rate"),
                      q.string("swaption_type"), q.real("target_price")))
    return core.shortrate.hw_calibrate(times, dfs, a, strip)


def _grid(i: Inputs) -> tuple[int, int, float]:
    g = i.object("grid")
    return g.integer("nx"), g.integer("steps_per_year"), g.real("width")


@op("rates.shortrate.bermudan_swaption")
def _bermudan(i: Inputs) -> Any:
    hw = _hw(i)
    t0, times, k = _swap(i, "start_years")
    kind, notional = i.string("swaption_type"), i.real("notional")
    exercise, grid = i.reals("exercise_times"), _grid(i)
    model = core.shortrate.curve_model(*hw)
    return core.shortrate.bermudan_swaption(model, t0, times, k, kind, notional, exercise,
                                            core.shortrate.make_grid(*grid))


@op("rates.shortrate.callable_bond")
def _callable(i: Inputs) -> Any:
    hw = _hw(i)
    args = (i.reals("payment_times"), i.real("coupon_rate"), i.real("notional"),
            i.reals("call_times"), i.real("call_price"))
    grid = _grid(i)
    model = core.shortrate.curve_model(*hw)
    return core.shortrate.callable_bond(model, *args, core.shortrate.make_grid(*grid))


@op("xva.exposure.swap_ee_hw")
def _exposure(i: Inputs) -> Any:
    hw = _hw(i)
    t0, times, k = _swap(i, "start_years")
    args = (i.string("side"), i.real("notional"), i.reals("exposure_times"),
            i.opt_real("hazard_rate"), i.opt_real("recovery"))
    model = core.shortrate.curve_model(*hw)
    return core.shortrate.swap_ee_hw(model, t0, times, k, *args)


def _g2(i: Inputs) -> tuple[Any, ...]:
    times, dfs = _curve(i)
    return (times, dfs, i.real("a"), i.real("sigma"), i.real("b"), i.real("eta"), i.real("rho"))


def _g2_model(raw: tuple[Any, ...]) -> Any:
    times, dfs, *params = raw
    return core.shortrate.make_g2(core.shortrate.make_curve(times, dfs), *params)


@op("rates.g2pp.zcb")
def _g2_zcb(i: Inputs) -> Any:
    raw = _g2(i)
    args = (i.real("x"), i.real("y"), i.real("t_years"), i.real("maturity_years"))
    return core.shortrate.g2pp_zcb(_g2_model(raw), *args)


@op("rates.g2pp.zcb_option")
def _g2_option(i: Inputs) -> Any:
    raw = _g2(i)
    states = i.has("x") or i.has("y")
    args = _option_args(i)
    model = _g2_model(raw)
    if states:
        core.shortrate.no_states()
    return core.shortrate.g2pp_zcb_option(model, *args)


@op("risk.mc.greeks")
def _mc_greeks(i: Inputs) -> Any:
    args = (i.real("spot"), i.real("strike"), i.real("expiry_years"), i.real("rate"),
            i.real("dividend_yield"), i.real("vol"), i.string("payoff"), i.string("method"),
            i.integer("paths"), i.u64("seed"), i.opt_real("smoothing_width"),
            i.opt_real("bump_relative"))
    return core.mc_greeks.greeks(*args)
