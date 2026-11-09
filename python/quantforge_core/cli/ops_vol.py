"""Handlers for the vol verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from typing import Any

from ..sabr import Sabr
from ..smile import Svi
from .inputs import Inputs
from .readers import (
    _OPTION_TYPES,
    OPTIONS,
    _forward_args,
    _not_null,
    _objects,
    _opt_shift,
    _option,
    _present,
    _surface,
    _valuation,
)
from .registry import core, op


def _opt_weights(i: Inputs) -> list[float] | None:
    _not_null(i, "weights")
    return i.reals("weights") if i.has("weights") else None


@op("vol.option.price")
def _option_price(i: Inputs) -> Any:
    o, vol = _option(i), i.real("vol")
    return {"price": core.black.price(o, vol), "forward": o.forward}


@op("vol.option.implied")
def _option_implied(i: Inputs) -> Any:
    o, target = _option(i), i.real("price")
    return {"vol": core.black.implied(o, target)}


@op("vol.equity.price")
def _equity_price(i: Inputs) -> Any:
    _not_null(i, "snapshot_id")
    args = _forward_args(i)
    option_type, strike, vol = i.enum("option_type", OPTIONS), i.real("strike"), i.real("vol")
    quantity, side = i.real("quantity"), i.enum("side", ("BUY", "SELL"))
    currency, snapshot_id = i.string("currency"), i.opt_string("snapshot_id")
    r = core.equity.outright(*args)
    g = core.black.equity_option(r, option_type, strike, vol, quantity, side)
    return {
        "valuation": _valuation(g["pv"], currency, args[1], snapshot_id), "forward": r.forward,
        "delta": g["delta"], "gamma": g["gamma"], "vega": g["vega"],
    }


def _delta_args(i: Inputs) -> tuple[Any, ...]:
    _present(i, "scale")
    return (i.enum("convention", ("FORWARD", "SPOT")),
            i.real("scale") if i.has("scale") else None)


@op("vol.delta.to_strike")
def _to_strike(i: Inputs) -> Any:
    args = (i.real("forward"), i.real("vol"), i.real("expiry_years"),
            i.enum("option_type", OPTIONS), i.real("delta"), *_delta_args(i))
    return {"strike": core.smile.delta_to_strike(*args)}


@op("vol.delta.from_strike")
def _from_strike(i: Inputs) -> Any:
    args = (i.real("forward"), i.real("vol"), i.real("expiry_years"),
            i.enum("option_type", OPTIONS), i.real("strike"), *_delta_args(i))
    return {"delta": core.smile.delta_from_strike(*args)}


@op("vol.smile.rr_bf")
def _rr_bf(i: Inputs) -> Any:
    args = (i.real("forward"), i.real("expiry_years"), i.real("atm_vol"),
            i.enum("atm_convention", ("ATM_FORWARD", "DELTA_NEUTRAL")), i.real("rr"), i.real("bf"),
            i.real("delta"), *_delta_args(i))
    return core.smile.rr_bf(*args)


def _svi(i: Inputs) -> Svi:
    p = i.object("svi")
    return Svi(p.real("a"), p.real("b"), p.real("rho"), p.real("m"), p.real("sigma"))


def _svi_out(p: Svi) -> dict[str, float]:
    return {"a": p.a, "b": p.b, "rho": p.rho, "m": p.m, "sigma": p.sigma}


@op("vol.svi.evaluate")
def _svi_evaluate(i: Inputs) -> Any:
    args = (_svi(i), i.reals("log_moneyness"), i.real("expiry_years"))
    return core.smile.svi_evaluate(*args)


@op("vol.svi.calibrate")
def _svi_calibrate(i: Inputs) -> Any:
    args = (i.reals("log_moneyness"), i.reals("total_variance"), _opt_weights(i))
    p, rmse = core.smile.svi_calibrate(*args)
    return {"svi": _svi_out(p), "rmse": rmse}


@op("vol.ssvi.evaluate")
def _ssvi_evaluate(i: Inputs) -> Any:
    args = (i.real("rho"), i.real("eta"), i.real("gamma"), i.reals("thetas"),
            i.reals("log_moneyness"))
    return core.smile.ssvi_evaluate(*args)


@op("vol.ssvi.calibrate")
def _ssvi_calibrate(i: Inputs) -> Any:
    args = (i.reals("thetas"), i.reals("log_moneyness"), i.matrix("total_variance"))
    rho, eta, gamma, rmse = core.smile.ssvi_calibrate(*args)
    return {"rho": rho, "eta": eta, "gamma": gamma, "rmse": rmse}


@op("vol.surface.query")
def _surface_query(i: Inputs) -> Any:
    s = _surface(i)
    points = [(p.real("expiry_years"), p.real("log_moneyness")) for p in _objects(i, "points")]
    ws, vols = core.smile.surface_query(s, points)
    return {"total_variance": ws, "vols": vols}


@op("vol.surface.check")
def _surface_check(i: Inputs) -> Any:
    s = _surface(i)
    return core.smile.surface_check(s)


def _sabr(i: Inputs) -> Sabr:
    return Sabr(i.real("forward"), i.real("expiry_years"), i.real("alpha"), i.real("beta"),
                i.real("rho"), i.real("nu"), _opt_shift(i))


@op("vol.sabr.hagan")
def _sabr_hagan(i: Inputs) -> Any:
    p, strikes = _sabr(i), i.reals("strikes")
    return {"vols": core.sabr.hagan(p, strikes)}


@op("vol.sabr.density")
def _sabr_density(i: Inputs) -> Any:
    args = (_sabr(i), i.reals("strikes"), i.real("h_strike"),
            i.enum("on_negative", ("REPORT", "REJECT")))
    values, low, negative = core.sabr.density(*args)
    return {"density": values, "min_density": low, "negative_density": negative}


@op("vol.sabr.calibrate")
def _sabr_calibrate(i: Inputs) -> Any:
    args = (i.real("forward"), i.real("expiry_years"), i.real("beta"), _opt_shift(i),
            i.reals("strikes"), i.reals("vols"), _opt_weights(i))
    alpha, rho, nu, rmse = core.sabr.calibrate(*args)
    return {"alpha": alpha, "rho": rho, "nu": nu, "rmse": rmse}


@op("vol.sabr.arbfree")
def _sabr_arbfree(i: Inputs) -> Any:
    args = (_sabr(i), i.integer("cells"), i.integer("cells_below"), i.integer("steps"),
            i.reals("strikes"))
    return core.sabr.arbfree(*args)


def _initial_variance(i: Inputs) -> str | float:
    """A string or a number; any other JSON type is E_SCHEMA (cli-contract, spec B notes)."""
    value = i.raw.get("initial_variance")
    if isinstance(value, str):
        return value
    return i.real("initial_variance")


def _weights(i: Inputs) -> tuple[float, float, float]:
    return i.real("omega"), i.real("alpha"), i.real("beta")


@op("vol.garch.loglik")
def _garch_loglik(i: Inputs) -> Any:
    distribution = (i.enum("distribution", ("NORMAL", "STUDENT_T"))
                    if i.raw.get("distribution") is not None else "NORMAL")
    nu = i.opt_real("degrees_of_freedom") if distribution == "STUDENT_T" else None
    args = (i.reals("returns"), *_weights(i), _initial_variance(i), distribution, nu,
            i.opt_real("mean", 0.0))
    loglik, variances, nxt = core.variance.garch_loglik_t(*args)
    return {"loglik": loglik, "variances": variances, "next_variance": nxt}


@op("vol.garch.estimate")
def _garch_estimate(i: Inputs) -> Any:
    args = (i.reals("returns"), _initial_variance(i),
            i.enum("distribution", ("NORMAL", "STUDENT_T")), i.boolean("demean"))
    return core.variance.garch_estimate(*args)


@op("vol.garch.forecast")
def _garch_forecast(i: Inputs) -> Any:
    args = (*_weights(i), i.real("next_variance"), i.integer("horizon"),
            i.real("periods_per_year"))
    variances, total, vol, long_run = core.variance.garch_forecast(*args)
    return {"variances": variances, "total_variance": total, "annualized_vol": vol,
            "long_run_variance": long_run}


@op("vol.garch.fit")
def _garch_fit(i: Inputs) -> Any:
    return {"loglik": core.variance.garch_fit(i.reals("returns"), _initial_variance(i))}


@op("vol.varswap.fair_strike")
def _fair_strike(i: Inputs) -> Any:
    args = (i.date("as_of"), i.date("maturity"), i.real("spot"), i.real("rate"),
            i.real("dividend_yield"), i.reals("put_strikes"), i.reals("call_strikes"),
            [(v.real("strike"), v.real("vol")) for v in _objects(i, "vols")],
            i.real("extension_step"), i.real("variance_strike"), i.real("variance_notional"))
    fair, vol, pv = core.variance.varswap_fair_strike(*args)
    return {"fair_variance": fair, "fair_vol": vol, "pv": pv}


@op("vol.varswap.realized")
def _realized(i: Inputs) -> Any:
    args = (i.reals("prices"), i.real("periods_per_year"), i.real("variance_strike"),
            i.real("variance_notional"))
    variance, vol, payoff = core.variance.varswap_realized(*args)
    return {"realized_variance": variance, "realized_vol": vol, "payoff": payoff}


_QUOTE_KEYS = ("strike", "call_bid", "call_ask", "put_bid", "put_ask")


def _term(i: Inputs) -> tuple[int, float, list[Any]]:
    from ..variance import Quote

    def quote(q: Inputs) -> Any:  # each side may be null (ruling F-15), but never left out
        sides = [None if k in q.raw and q.raw[k] is None else q.real(k) for k in _QUOTE_KEYS[1:]]
        return Quote(q.real("strike"), *sides)

    strip = [quote(q) for q in _objects(i, "strip")]
    return i.integer("minutes_to_expiry"), i.real("rate"), strip


@op("vol.vix.term_variance")
def _term_variance(i: Inputs) -> Any:
    forward, k0, variance, used = core.variance.vix_term_variance(*_term(i))
    return {"forward": forward, "k0": k0, "variance": variance, "strikes_used": used}


@op("vol.vix.index")
def _vix_index(i: Inputs) -> Any:
    near, nxt = _term(i.object("near")), _term(i.object("next"))
    index, v1, v2 = core.variance.vix_index(near, nxt)
    return {"index": index, "near_variance": v1, "next_variance": v2}


def _slices(i: Inputs) -> list[Any]:
    from ..arb_surface import Slice

    return [Slice(s.real("expiry_years"), _svi(s)) for s in _objects(i, "slices")]


@op("vol.svi.surface_check")
def _vol_svi_surface_check(i: Inputs) -> Any:
    args = (_slices(i), i.reals("log_moneyness"), i.boolean("reject"))
    return core.arb_surface.surface_check(*args)


@op("vol.ssvi.to_svi")
def _ssvi_to_svi(i: Inputs) -> Any:
    args = (i.real("rho"), i.real("eta"), i.real("gamma"), i.real("theta"))
    return {"svi": _svi_out(core.arb_surface.ssvi_to_svi(*args))}


@op("vol.svi.fit_surface")
def _fit_surface(i: Inputs) -> Any:
    args = (i.reals("expiry_years"), i.reals("log_moneyness"), i.matrix("total_variance"),
            i.boolean("reject"))
    slices, rmse, report = core.arb_surface.fit_surface(*args)
    fitted = [{"expiry_years": s.expiry_years, "svi": _svi_out(s.svi)} for s in slices]
    return {"slices": fitted, "rmse": rmse, **report}


@op("vol.local.dupire")
def _dupire(i: Inputs) -> Any:
    points = [(p.real("expiry_years"), p.real("log_moneyness")) for p in _objects(i, "points")]
    w, vols, local = core.arb_surface.dupire(_slices(i), points)
    return {"total_variance": w, "implied_vol": vols, "local_vol": local}


@op("vol.forward.vol")
def _forward_vol(i: Inputs) -> Any:
    return {"forward_vols": core.arb_surface.forward_vols(i.reals("expiry_years"), i.reals("vols"))}


@op("vol.smile.dynamics")
def _smile_dynamics(i: Inputs) -> Any:
    args = (_svi(i), i.real("expiry_years"), i.real("spot"), i.real("spot_shifted"),
            i.real("rate"), i.real("dividend_yield"), i.reals("strikes"),
            i.enum("rule", ("STICKY_STRIKE", "STICKY_DELTA")), i.enum("option_type", ("CALL", "PUT")))
    return core.arb_surface.smile_dynamics(*args)


@op("vol.volofvol.measure")
def _vol_of_vol(i: Inputs) -> Any:
    args = (i.reals("vols"), i.real("periods_per_year"), i.enum("method", ("LOG", "ABSOLUTE")))
    vov, mean = core.arb_surface.vol_of_vol(*args)
    return {"vol_of_vol": vov, "mean_change": mean}


def _heston(i: Inputs) -> Any:
    from ..heston import Heston

    h = i.object("heston")
    return Heston(*(h.real(k) for k in ("v0", "kappa", "theta", "xi", "rho")))


def _jumps(i: Inputs) -> Any:
    from ..heston import Jumps

    j = i.object("jumps")
    return Jumps(*(j.real(k) for k in ("intensity", "mean_log_jump", "log_jump_vol")))


def _common(i: Inputs) -> tuple[float, list[float], float, float, float]:
    return (i.real("spot"), i.reals("strikes"), i.real("expiry_years"), i.real("rate"),
            i.real("dividend_yield"))


@op("vol.heston.price")
def _heston_price(i: Inputs) -> Any:
    args = (*_common(i), _heston(i), i.enum("option_type", _OPTION_TYPES))
    return {"prices": core.heston.heston_price(*args)}


@op("vol.heston.cf")
def _heston_cf(i: Inputs) -> Any:
    re, im = core.heston.heston_cf(i.real("expiry_years"), _heston(i), i.reals("u"))
    return {"re": re, "im": im}


@op("vol.bates.price")
def _bates_price(i: Inputs) -> Any:
    args = (*_common(i), _heston(i), _jumps(i), i.enum("option_type", _OPTION_TYPES))
    return {"prices": core.heston.bates_price(*args)}


@op("vol.merton.price")
def _merton_price(i: Inputs) -> Any:
    args = (*_common(i), i.real("vol"), _jumps(i), i.enum("option_type", _OPTION_TYPES))
    return {"prices": core.heston.merton_price(*args)}


@op("vol.slv.leverage")
def _slv(i: Inputs) -> Any:
    from ..heston import Grid

    g = i.object("grid")
    grid = Grid(g.integer("nx"), g.integer("nv"), g.integer("nt"), g.real("x_min"),
                g.real("x_max"), g.real("v_max"))
    args = (i.real("spot"), i.real("expiry_years"), i.real("rate"), i.real("dividend_yield"),
            _heston(i), _slices(i), grid)
    return core.heston.slv_leverage(*args)
