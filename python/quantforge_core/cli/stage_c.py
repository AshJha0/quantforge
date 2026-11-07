"""Handlers for the stage C operations. As in stage_b.py, a handler reads every input first; the
first call through `C`, the gated core modules, ends the E_SCHEMA stage."""
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from ..black import BACHELIER, BLACK_76, BLACK_SCHOLES, Option
from ..equity import ParityQuote
from ..errors import QfError
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
        raise _schema(sorted(foreign)[0], f"not an input of {model}")
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


# --- handlers below are added item by item ---


def handlers(core: SimpleNamespace) -> dict[str, Handler]:
    C.__dict__.update(core.__dict__)
    return _OPS
