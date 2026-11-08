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
