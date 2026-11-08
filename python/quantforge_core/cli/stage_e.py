"""Handlers for the stage E operations. As in stage_c.py, a handler reads every input first; the
first call through `E`, the gated core modules, ends the E_SCHEMA stage."""
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from .inputs import Inputs
from .stage_b import _objects

Handler = Callable[[Inputs], Any]
_OPS: dict[str, Handler] = {}
E = SimpleNamespace()


def op(name: str) -> Callable[[Handler], Handler]:
    def register(f: Handler) -> Handler:
        _OPS[name] = f
        return f

    return register


def handlers(core: SimpleNamespace) -> dict[str, Handler]:
    E.__dict__.update(core.__dict__)
    return _OPS


# E7: GARCH, variance swaps, VIX (garch.md, variance-swaps.md, vix-index.md)

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
    args = (i.reals("returns"), *_weights(i), _initial_variance(i))
    loglik, variances, nxt = E.vol_e7.garch_loglik(*args)
    return {"loglik": loglik, "variances": variances, "next_variance": nxt}


@op("vol.garch.forecast")
def _garch_forecast(i: Inputs) -> Any:
    args = (*_weights(i), i.real("next_variance"), i.integer("horizon"),
            i.real("periods_per_year"))
    variances, total, vol, long_run = E.vol_e7.garch_forecast(*args)
    return {"variances": variances, "total_variance": total, "annualized_vol": vol,
            "long_run_variance": long_run}


@op("vol.garch.fit")
def _garch_fit(i: Inputs) -> Any:
    return {"loglik": E.vol_e7.garch_fit(i.reals("returns"), _initial_variance(i))}


@op("vol.varswap.fair_strike")
def _fair_strike(i: Inputs) -> Any:
    args = (i.date("as_of"), i.date("maturity"), i.real("spot"), i.real("rate"),
            i.real("dividend_yield"), i.reals("put_strikes"), i.reals("call_strikes"),
            [(v.real("strike"), v.real("vol")) for v in _objects(i, "vols")],
            i.real("extension_step"), i.real("variance_strike"), i.real("variance_notional"))
    fair, vol, pv = E.vol_e7.varswap_fair_strike(*args)
    return {"fair_variance": fair, "fair_vol": vol, "pv": pv}


@op("vol.varswap.realized")
def _realized(i: Inputs) -> Any:
    args = (i.reals("prices"), i.real("periods_per_year"), i.real("variance_strike"),
            i.real("variance_notional"))
    variance, vol, payoff = E.vol_e7.varswap_realized(*args)
    return {"realized_variance": variance, "realized_vol": vol, "payoff": payoff}


_QUOTE_KEYS = ("strike", "call_bid", "call_ask", "put_bid", "put_ask")


def _term(i: Inputs) -> tuple[int, float, list[Any]]:
    from ..vol_e7 import Quote

    strip = [Quote(*(q.real(k) for k in _QUOTE_KEYS)) for q in _objects(i, "strip")]
    return i.integer("minutes_to_expiry"), i.real("rate"), strip


@op("vol.vix.term_variance")
def _term_variance(i: Inputs) -> Any:
    forward, k0, variance, used = E.vol_e7.vix_term_variance(*_term(i))
    return {"forward": forward, "k0": k0, "variance": variance, "strikes_used": used}


@op("vol.vix.index")
def _vix_index(i: Inputs) -> Any:
    near, nxt = _term(i.object("near")), _term(i.object("next"))
    index, v1, v2 = E.vol_e7.vix_index(near, nxt)
    return {"index": index, "near_variance": v1, "next_variance": v2}



# E1: arbitrage-free surfaces, local and forward vol (arb-free-surfaces.md,
# local-and-forward-vol.md)

def _svi(i: Inputs) -> Any:
    from ..smile import Svi

    p = i.object("svi")
    return Svi(p.real("a"), p.real("b"), p.real("rho"), p.real("m"), p.real("sigma"))


def _svi_out(p: Any) -> dict[str, float]:
    return {"a": p.a, "b": p.b, "rho": p.rho, "m": p.m, "sigma": p.sigma}


def _slices(i: Inputs) -> list[Any]:
    from ..vol_e1 import Slice

    return [Slice(s.real("expiry_years"), _svi(s)) for s in _objects(i, "slices")]


@op("vol.svi.surface_check")
def _surface_check(i: Inputs) -> Any:
    args = (_slices(i), i.reals("log_moneyness"), i.boolean("reject"))
    return E.vol_e1.surface_check(*args)


@op("vol.ssvi.to_svi")
def _ssvi_to_svi(i: Inputs) -> Any:
    args = (i.real("rho"), i.real("eta"), i.real("gamma"), i.real("theta"))
    return {"svi": _svi_out(E.vol_e1.ssvi_to_svi(*args))}


@op("vol.svi.fit_surface")
def _fit_surface(i: Inputs) -> Any:
    args = (i.reals("expiry_years"), i.reals("log_moneyness"), i.matrix("total_variance"),
            i.boolean("reject"))
    slices, rmse, report = E.vol_e1.fit_surface(*args)
    fitted = [{"expiry_years": s.expiry_years, "svi": _svi_out(s.svi)} for s in slices]
    return {"slices": fitted, "rmse": rmse, **report}


@op("vol.local.dupire")
def _dupire(i: Inputs) -> Any:
    points = [(p.real("expiry_years"), p.real("log_moneyness")) for p in _objects(i, "points")]
    w, vols, local = E.vol_e1.dupire(_slices(i), points)
    return {"total_variance": w, "implied_vol": vols, "local_vol": local}


@op("vol.forward.vol")
def _forward_vol(i: Inputs) -> Any:
    return {"forward_vols": E.vol_e1.forward_vols(i.reals("expiry_years"), i.reals("vols"))}


@op("vol.smile.dynamics")
def _smile_dynamics(i: Inputs) -> Any:
    args = (_svi(i), i.real("expiry_years"), i.real("spot"), i.real("spot_shifted"),
            i.real("rate"), i.real("dividend_yield"), i.reals("strikes"),
            i.enum("rule", ("STICKY_STRIKE", "STICKY_DELTA")), i.enum("option_type", ("CALL", "PUT")))
    return E.vol_e1.smile_dynamics(*args)


@op("vol.volofvol.measure")
def _vol_of_vol(i: Inputs) -> Any:
    args = (i.reals("vols"), i.real("periods_per_year"), i.enum("method", ("LOG", "ABSOLUTE")))
    vov, mean = E.vol_e1.vol_of_vol(*args)
    return {"vol_of_vol": vov, "mean_change": mean}


# E3: FX smile (fx-smile.md)

_OPTION_TYPES = ("CALL", "PUT")


def _fx_market(i: Inputs) -> tuple[float, float, float, float]:
    return i.real("spot"), i.real("expiry_years"), i.real("domestic_rate"), i.real("foreign_rate")


def _delta_type(i: Inputs) -> str:
    from ..fx_smile import DELTA_TYPES

    return i.enum("delta_type", DELTA_TYPES)


@op("fx.option.price")
def _fx_price(i: Inputs) -> Any:
    spot, t, rd, rf = _fx_market(i)
    args = (spot, i.real("strike"), t, rd, rf, i.real("vol"), i.enum("option_type", _OPTION_TYPES),
            i.real("notional"))
    return E.fx_smile.option_price(*args)


@op("fx.delta.from_strike")
def _fx_delta_from_strike(i: Inputs) -> Any:
    spot, t, rd, rf = _fx_market(i)
    args = (spot, i.real("strike"), t, rd, rf, i.real("vol"), i.enum("option_type", _OPTION_TYPES))
    return {"deltas": E.fx_smile.delta_from_strike(*args)}


@op("fx.delta.to_strike")
def _fx_delta_to_strike(i: Inputs) -> Any:
    args = (*_fx_market(i), i.real("vol"), i.enum("option_type", _OPTION_TYPES), i.real("delta"),
            _delta_type(i))
    return {"strike": E.fx_smile.delta_to_strike(*args)}


@op("fx.atm.strike")
def _fx_atm_strike(i: Inputs) -> Any:
    from ..fx_smile import ATM_TYPES

    args = (*_fx_market(i), i.real("vol"), i.enum("atm_type", ATM_TYPES), _delta_type(i))
    return {"strike": E.fx_smile.atm_strike(*args)}


@op("fx.smile.from_quotes")
def _fx_smile(i: Inputs) -> Any:
    from ..fx_smile import ATM_TYPES

    args = (*_fx_market(i), i.real("atm_vol"), i.real("rr"), i.real("bf"), i.real("delta"),
            _delta_type(i), i.enum("atm_type", ATM_TYPES))
    return E.fx_smile.smile_from_quotes(*args)


# E4: rates and inflation vol (rates-vol-cube.md)

_RATE_MODELS = ("BLACK_76", "BACHELIER")


def _curves(i: Inputs) -> tuple[Any, Any]:
    from .stage_b import _curve

    return _curve(i, "discount"), _curve(i, "projection")


@op("rates.swaption.price_cube")
def _price_cube(i: Inputs) -> Any:
    c, t = i.object("cube"), i.object("trade")
    params = {k: c.matrix(k) for k in ("alpha", "beta", "rho", "nu")}
    months = [c.integer_list(k) for k in ("expiries_months", "tenors_months")]
    args = (*_curves(i), *months, params, t.enum("type", ("PAYER", "RECEIVER")),
            t.integer("expiry_months"), t.integer("tenor_months"), t.real("strike"),
            t.real("notional"))
    return E.rates_vol.price_cube(*args)


@op("rates.cap.strip")
def _cap_strip(i: Inputs) -> Any:
    args = (*_curves(i), i.enum("model", _RATE_MODELS), i.integer("start_months"),
            i.real("strike"), i.integer_list("cap_tenors_months"), i.reals("flat_vols"),
            i.real("notional"))
    vols, prices = E.rates_vol.cap_strip(*args)
    return {"caplet_vols": vols, "cap_prices": prices}


def _futures(i: Inputs) -> tuple[str, float, float, float, float]:
    return (i.enum("type", _OPTION_TYPES), i.real("futures_price"), i.real("strike"),
            i.real("expiry_years"), i.real("discount_factor"))


@op("rates.bondfut.option_price")
def _bondfut_price(i: Inputs) -> Any:
    price, value = E.rates_vol.bondfut_price(*_futures(i), i.real("vol"), i.real("contract_size"))
    return {"price": price, "contract_value": value}


@op("rates.bondfut.implied_vol")
def _bondfut_implied(i: Inputs) -> Any:
    args = (*_futures(i), i.real("premium"), i.real("ctd_yield"), i.real("ctd_modified_duration"))
    price_vol, yield_vol = E.rates_vol.bondfut_implied(*args)
    return {"price_vol": price_vol, "yield_vol": yield_vol}


_CAP_TYPES = ("CAP", "FLOOR")


@op("infl.cap.yoy_price")
def _yoy(i: Inputs) -> Any:
    periods = [(p.real("accrual"), p.real("discount_factor"), p.real("yoy_forward"),
                p.real("expiry_years"), p.real("vol")) for p in _objects(i, "periods")]
    args = (i.enum("model", _RATE_MODELS), i.enum("type", _CAP_TYPES), i.real("strike"),
            i.real("notional"), periods)
    caplets, price = E.rates_vol.yoy_price(*args)
    return {"caplets": caplets, "price": price}


@op("infl.cap.zc_price")
def _zc(i: Inputs) -> Any:
    args = (i.enum("model", _RATE_MODELS), i.enum("type", _CAP_TYPES),
            i.real("forward_index_ratio"), i.real("years"), i.real("strike"),
            i.real("discount_factor"), i.real("vol"), i.real("notional"))
    price, ratio = E.rates_vol.zc_price(*args)
    return {"price": price, "strike_ratio": ratio}


# E2: Heston, Bates, Merton, SLV (heston-family.md)

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
    return {"prices": E.heston.heston_price(*args)}


@op("vol.heston.cf")
def _heston_cf(i: Inputs) -> Any:
    re, im = E.heston.heston_cf(i.real("expiry_years"), _heston(i), i.reals("u"))
    return {"re": re, "im": im}


@op("vol.bates.price")
def _bates_price(i: Inputs) -> Any:
    args = (*_common(i), _heston(i), _jumps(i), i.enum("option_type", _OPTION_TYPES))
    return {"prices": E.heston.bates_price(*args)}


@op("vol.merton.price")
def _merton_price(i: Inputs) -> Any:
    args = (*_common(i), i.real("vol"), _jumps(i), i.enum("option_type", _OPTION_TYPES))
    return {"prices": E.heston.merton_price(*args)}


@op("vol.slv.leverage")
def _slv(i: Inputs) -> Any:
    from ..heston import Grid

    g = i.object("grid")
    grid = Grid(g.integer("nx"), g.integer("nv"), g.integer("nt"), g.real("x_min"),
                g.real("x_max"), g.real("v_max"))
    args = (i.real("spot"), i.real("expiry_years"), i.real("rate"), i.real("dividend_yield"),
            _heston(i), _slices(i), grid)
    return E.heston.slv_leverage(*args)


# E6: correlation (06-risk/correlation.md)

@op("risk.corr.validate")
def _corr_validate(i: Inputs) -> Any:
    return E.correlation.validate(i.matrix("matrix"))


@op("risk.corr.nearest")
def _corr_nearest(i: Inputs) -> Any:
    matrix, distance = E.correlation.nearest(i.matrix("matrix"))
    return {"matrix": matrix, "frobenius_distance": distance}


@op("risk.corr.implied")
def _corr_implied(i: Inputs) -> Any:
    args = (i.reals("weights"), i.reals("vols"), i.real("index_vol"))
    return {"correlation": E.correlation.implied(*args)}


@op("risk.corr.dispersion")
def _corr_dispersion(i: Inputs) -> Any:
    args = (i.reals("weights"), i.reals("vol_strikes"), i.real("index_vol_strike"),
            i.reals("realized_vols"), i.real("index_realized_vol"), i.real("vega_notional"))
    return E.correlation.dispersion(*args)
