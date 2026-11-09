"""Input readers shared by the handlers of several domains."""
from datetime import date
from typing import Any

from .. import conventions, curves
from ..black import BACHELIER, BLACK_76, BLACK_SCHOLES, Option
from ..calendars import TENOR
from ..curves import CurveData
from ..equity import ParityQuote
from ..errors import QfError
from ..fx import FxForward, FxMarket
from ..ois import OisTrade, Quote
from ..smile import Surface
from .inputs import Inputs


def _tenor(i: Inputs) -> str:
    tenor = i.string("tenor")
    if TENOR.fullmatch(tenor) is None:
        raise QfError("E_SCHEMA", f"bad tenor {tenor}", "tenor")
    return tenor


Result = Any


def _objects(i: Inputs, key: str) -> list[Inputs]:
    items = i.array(key)
    if not all(isinstance(v, dict) for v in items):
        raise QfError("E_SCHEMA", f"{key} must hold objects", key)
    return [Inputs(v, f"{key}.") for v in items]


def jumps(i: Inputs, required: bool = False) -> tuple[tuple[date, float], ...]:
    """Optional `jumps` (ruling D10): absent means none, null is E_SCHEMA."""
    if "jumps" in i.raw and i.raw["jumps"] is None:
        raise QfError("E_SCHEMA", "jumps: null is not allowed", "jumps")
    if "jumps" not in i.raw and not required:
        return ()
    return tuple((j.date("date"), j.real("factor")) for j in _objects(i, "jumps"))


def _curve(i: Inputs, key: str = "curve") -> CurveData:
    c = i.object(key)
    pillars = _objects(c, "pillars")
    return CurveData(
        c.date("as_of"),
        c.enum("interpolation", curves.INTERPOLATIONS),
        tuple(p.date("date") for p in pillars),
        tuple(p.real("discount_factor") for p in pillars),
        jumps(c),
    )


def _pillars(data: CurveData) -> list[dict[str, Any]]:
    return [
        {"date": d.isoformat(), "discount_factor": v}
        for d, v in zip(data.dates, data.discount_factors, strict=True)
    ]


def _quotes(i: Inputs) -> list[Quote]:
    quotes = []
    for q in _objects(i, "quotes"):
        if q.has("rate"):
            quotes.append(Quote(_tenor(q), q.real("rate")))
        else:
            quotes.append(Quote(_tenor(q), None, q.real("bid"), q.real("ask")))
    return quotes


def _ois_trade(i: Inputs) -> OisTrade:
    t = i.object("trade")
    return OisTrade(
        t.enum("convention", conventions.OVERNIGHT), _tenor(t), t.real("fixed_rate"),
        t.real("notional"), t.enum("side", ("PAY", "RECEIVE")),
    )


def _market(i: Inputs) -> FxMarket:
    return FxMarket(
        i.enum("pair", conventions.PAIRS), i.real("spot"), i.date("as_of"),
        _curve(i, "base_curve"), _curve(i, "quote_curve"), i.opt_string("snapshot_id"),
    )


def _forward_trade(t: Inputs) -> FxForward:
    return FxForward(
        t.real("notional_base"), t.real("strike"), t.date("value_date"),
        t.enum("side", ("BUY", "SELL")),
    )


OPTIONS = ("CALL", "PUT")


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


def _valuation(pv: float, currency: str, as_of: Any, snapshot_id: str | None) -> dict[str, Any]:
    return {
        "pv": pv, "currency": currency, "model": "BLACK_76_EQUITY", "data_version": snapshot_id,
        "conventions": "EQUITY_FORWARD", "as_of": as_of.isoformat(),
    }


def _surface(i: Inputs) -> Surface:
    s = i.object("surface")
    return Surface(s.reals("expiry_years"), s.reals("log_moneyness"), s.matrix("vols"))


def _convention(i: Inputs, key: str, allowed: tuple[str, ...]) -> str:
    """Ruling D45: an unlisted id is E_SCHEMA, a listed id of the wrong kind E_INPUT."""
    value = i.enum(key, tuple(conventions.REGISTRY))
    if value not in allowed:
        raise QfError("E_INPUT", f"{value} is not allowed here", key)
    return value


def _bond(b: Inputs) -> Any:
    from ..bonds import FREQUENCIES, Bond
    frequency = b.integer("frequency")
    if frequency not in FREQUENCIES:
        raise QfError("E_SCHEMA", "frequency must be 1, 2 or 4", "frequency")
    return Bond(b.date("maturity"), b.real("coupon"), frequency)


def _month(i: Inputs, key: str) -> tuple[int, int]:
    import re
    text = i.string(key)
    m = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if m is None or not 1 <= int(m[2]) <= 12 or int(m[1]) < 1:
        raise QfError("E_SCHEMA", f"{key} is not YYYY-MM", key)
    return int(m[1]), int(m[2])


def _month_index(i: Inputs, key: str) -> int:
    year, month = _month(i, key)
    return 12 * year + month - 1


_OPTION_TYPES = ("CALL", "PUT")


_RATE_MODELS = ("BLACK_76", "BACHELIER")
