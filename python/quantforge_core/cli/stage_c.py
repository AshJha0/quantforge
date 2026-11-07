"""Handlers for the stage C operations. As in stage_b.py, a handler reads every input first; the
first call through `C`, the gated core modules, ends the E_SCHEMA stage."""
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from ..black import BACHELIER, BLACK_76, BLACK_SCHOLES, Option
from ..equity import ParityQuote
from ..errors import QfError
from ..sabr import Sabr
from ..smile import Position, Surface, Svi
from .inputs import Inputs
from .stage_b import _curve, _objects

Handler = Callable[[Inputs], Any]
OPTIONS = ("CALL", "PUT")
_OPS: dict[str, Handler] = {}
C = SimpleNamespace()


def op(name: str) -> Callable[[Handler], Handler]:
    def register(f: Handler) -> Handler:
        _OPS[name] = f
        return f

    return register


def _schema(key: str, why: str) -> QfError:
    return QfError("E_SCHEMA", f"{key}: {why}", key)


def _not_null(i: Inputs, *keys: str) -> None:
    """Ruling C9: an optional key may be absent, but null is E_SCHEMA."""
    for key in keys:
        if key in i.raw and i.raw[key] is None:
            raise _schema(key, "null is not allowed")


def _present(i: Inputs, *keys: str) -> None:
    """Ruling C9: a key whose null carries meaning must still be there."""
    for key in keys:
        if key not in i.raw:
            raise _schema(key, "missing")


def _opt_shift(i: Inputs) -> float:
    _not_null(i, "shift")
    return i.opt_real("shift", 0.0)


def _opt_weights(i: Inputs) -> list[float] | None:
    _not_null(i, "weights")
    return i.reals("weights") if i.has("weights") else None


def _forward_args(i: Inputs) -> tuple[Any, ...]:
    _present(i, "borrow_curve")
    borrow = _curve(i, "borrow_curve") if i.has("borrow_curve") else None
    dividends = [(d.date("ex_date"), d.real("amount")) for d in _objects(i, "dividends")]
    return (
        i.real("spot"), i.date("as_of"), i.date("expiry"), _curve(i, "funding_curve"), borrow,
        dividends,
    )


def _parity_quotes(i: Inputs) -> list[ParityQuote]:
    return [
        ParityQuote(q.real("strike"), q.real("call_bid"), q.real("call_ask"), q.real("put_bid"),
                    q.real("put_ask"))
        for q in _objects(i, "quotes")
    ]


@op("eq.forward.outright")
def _outright(i: Inputs) -> Any:
    r = C.equity.outright(*_forward_args(i))
    return {
        "forward": r.forward, "discount_factor": r.discount_factor,
        "carry_factor": r.carry_factor, "pv_dividends": r.pv_dividends,
    }


@op("eq.forward.flat")
def _flat(i: Inputs) -> Any:
    dividends = [(d.real("time_years"), d.real("amount")) for d in _objects(i, "dividends")]
    forward = C.equity.flat(
        i.real("spot"), i.real("rate"), i.real("borrow"), i.real("expiry_years"), dividends
    )
    return {"forward": forward}


@op("eq.forward.parity")
def _parity(i: Inputs) -> Any:
    _present(i, "discount_factor")
    quotes = _parity_quotes(i)
    d = i.real("discount_factor") if i.has("discount_factor") else None
    f, d, residual, outside = C.equity.parity(quotes, d)
    return {
        "forward": f, "discount_factor": d, "max_residual": residual, "outside_spread": outside,
    }


_MODEL_KEYS = {
    BLACK_SCHOLES: {"spot", "rate", "yield"},
    BLACK_76: {"forward", "discount_factor", "shift"},
    BACHELIER: {"forward", "discount_factor"},
}
_ALL_MODEL_KEYS = set().union(*_MODEL_KEYS.values())


def _option(i: Inputs) -> Option:
    model = i.enum("model", tuple(_MODEL_KEYS))
    foreign = (_ALL_MODEL_KEYS - _MODEL_KEYS[model]) & set(i.raw)
    if foreign:
        raise _schema(min(foreign), f"not an input of {model}")
    common = (
        model, i.enum("option_type", OPTIONS), i.real("strike"), i.real("expiry_years"),
    )
    if model == BLACK_SCHOLES:
        return Option(
            *common, i.real("spot"), rate=i.real("rate"), dividend_yield=i.real("yield")
        )
    shift = _opt_shift(i) if model == BLACK_76 else 0.0
    return Option(
        *common, i.real("forward"), discount_factor=i.real("discount_factor"), shift=shift
    )


@op("vol.option.price")
def _option_price(i: Inputs) -> Any:
    o, vol = _option(i), i.real("vol")
    return {"price": C.black.price(o, vol), "forward": o.forward}


@op("vol.option.implied")
def _option_implied(i: Inputs) -> Any:
    o, target = _option(i), i.real("price")
    return {"vol": C.black.implied(o, target)}


@op("risk.vol.greeks")
def _greeks(i: Inputs) -> Any:
    o, vol = _option(i), i.real("vol")
    return C.black.greeks(o, vol)


@op("risk.vol.bump_greeks")
def _bump_greeks(i: Inputs) -> Any:
    o, vol = _option(i), i.real("vol")
    return C.black.bump_greeks(o, vol)


def _valuation(pv: float, currency: str, as_of: Any, snapshot_id: str | None) -> dict[str, Any]:
    return {
        "pv": pv, "currency": currency, "model": "BLACK_76_EQUITY", "data_version": snapshot_id,
        "conventions": "EQUITY_FORWARD", "as_of": as_of.isoformat(),
    }


@op("vol.equity.price")
def _equity_price(i: Inputs) -> Any:
    _not_null(i, "snapshot_id")
    args = _forward_args(i)
    option_type, strike, vol = i.enum("option_type", OPTIONS), i.real("strike"), i.real("vol")
    quantity, side = i.real("quantity"), i.enum("side", ("BUY", "SELL"))
    currency, snapshot_id = i.string("currency"), i.opt_string("snapshot_id")
    r = C.equity.outright(*args)
    g = C.black.equity_option(r, option_type, strike, vol, quantity, side)
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
    return {"strike": C.smile.delta_to_strike(*args)}


@op("vol.delta.from_strike")
def _from_strike(i: Inputs) -> Any:
    args = (i.real("forward"), i.real("vol"), i.real("expiry_years"),
            i.enum("option_type", OPTIONS), i.real("strike"), *_delta_args(i))
    return {"delta": C.smile.delta_from_strike(*args)}


@op("vol.smile.rr_bf")
def _rr_bf(i: Inputs) -> Any:
    args = (i.real("forward"), i.real("expiry_years"), i.real("atm_vol"),
            i.enum("atm_convention", ("ATM_FORWARD", "DELTA_NEUTRAL")), i.real("rr"), i.real("bf"),
            i.real("delta"), *_delta_args(i))
    return C.smile.rr_bf(*args)


def _svi(i: Inputs) -> Svi:
    p = i.object("svi")
    return Svi(p.real("a"), p.real("b"), p.real("rho"), p.real("m"), p.real("sigma"))


def _svi_out(p: Svi) -> dict[str, float]:
    return {"a": p.a, "b": p.b, "rho": p.rho, "m": p.m, "sigma": p.sigma}


@op("vol.svi.evaluate")
def _svi_evaluate(i: Inputs) -> Any:
    args = (_svi(i), i.reals("log_moneyness"), i.real("expiry_years"))
    return C.smile.svi_evaluate(*args)


@op("vol.svi.calibrate")
def _svi_calibrate(i: Inputs) -> Any:
    args = (i.reals("log_moneyness"), i.reals("total_variance"), _opt_weights(i))
    p, rmse = C.smile.svi_calibrate(*args)
    return {"svi": _svi_out(p), "rmse": rmse}


@op("vol.ssvi.evaluate")
def _ssvi_evaluate(i: Inputs) -> Any:
    args = (i.real("rho"), i.real("eta"), i.real("gamma"), i.reals("thetas"),
            i.reals("log_moneyness"))
    return C.smile.ssvi_evaluate(*args)


@op("vol.ssvi.calibrate")
def _ssvi_calibrate(i: Inputs) -> Any:
    args = (i.reals("thetas"), i.reals("log_moneyness"), i.matrix("total_variance"))
    rho, eta, gamma, rmse = C.smile.ssvi_calibrate(*args)
    return {"rho": rho, "eta": eta, "gamma": gamma, "rmse": rmse}


def _surface(i: Inputs) -> Surface:
    s = i.object("surface")
    return Surface(s.reals("expiry_years"), s.reals("log_moneyness"), s.matrix("vols"))


@op("vol.surface.query")
def _surface_query(i: Inputs) -> Any:
    s = _surface(i)
    points = [(p.real("expiry_years"), p.real("log_moneyness")) for p in _objects(i, "points")]
    ws, vols = C.smile.surface_query(s, points)
    return {"total_variance": ws, "vols": vols}


@op("vol.surface.check")
def _surface_check(i: Inputs) -> Any:
    s = _surface(i)
    return C.smile.surface_check(s)


@op("risk.vol.surface_vega")
def _surface_vega(i: Inputs) -> Any:
    s = _surface(i)
    book = [
        Position(p.enum("option_type", OPTIONS), p.real("forward"), p.real("strike"),
                 p.real("discount_factor"), p.real("expiry_years"), p.real("quantity"))
        for p in _objects(i, "positions")
    ]
    return C.smile.surface_vega(s, book)


def _sabr(i: Inputs) -> Sabr:
    return Sabr(i.real("forward"), i.real("expiry_years"), i.real("alpha"), i.real("beta"),
                i.real("rho"), i.real("nu"), _opt_shift(i))


@op("vol.sabr.hagan")
def _sabr_hagan(i: Inputs) -> Any:
    p, strikes = _sabr(i), i.reals("strikes")
    return {"vols": C.sabr.hagan(p, strikes)}


@op("vol.sabr.density")
def _sabr_density(i: Inputs) -> Any:
    args = (_sabr(i), i.reals("strikes"), i.real("h_strike"),
            i.enum("on_negative", ("REPORT", "REJECT")))
    values, low, negative = C.sabr.density(*args)
    return {"density": values, "min_density": low, "negative_density": negative}


@op("vol.sabr.calibrate")
def _sabr_calibrate(i: Inputs) -> Any:
    args = (i.real("forward"), i.real("expiry_years"), i.real("beta"), _opt_shift(i),
            i.reals("strikes"), i.reals("vols"), _opt_weights(i))
    alpha, rho, nu, rmse = C.sabr.calibrate(*args)
    return {"alpha": alpha, "rho": rho, "nu": nu, "rmse": rmse}


@op("vol.sabr.arbfree")
def _sabr_arbfree(i: Inputs) -> Any:
    args = (_sabr(i), i.integer("cells"), i.integer("cells_below"), i.integer("steps"),
            i.reals("strikes"))
    return C.sabr.arbfree(*args)


@op("usecase.vol_surface")
def _vol_surface(i: Inputs) -> Any:
    slices = [(s.date("expiry"), _parity_quotes(s)) for s in _objects(i, "slices")]
    t = i.object("target")
    target = (t.enum("option_type", OPTIONS), t.real("strike"), t.date("expiry"),
              t.real("quantity"), t.enum("side", ("BUY", "SELL")))
    as_of, curve = i.date("as_of"), _curve(i, "funding_curve")
    k_grid, currency = i.reals("k_grid"), i.string("currency")
    r = C.vol_usecase.vol_surface(as_of, curve, slices, k_grid, target)
    return {
        "forwards": r["forwards"], "svi_rmse": r["svi_rmse"],
        "arbitrage_free": r["arbitrage_free"], "vol": r["vol"],
        "valuation": _valuation(r["pv"], currency, as_of, None), "delta": r["delta"],
        "vega": r["vega"],
    }



def handlers(core: SimpleNamespace) -> dict[str, Handler]:
    C.__dict__.update(core.__dict__)
    return _OPS
