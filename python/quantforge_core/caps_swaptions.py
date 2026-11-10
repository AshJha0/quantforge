"""Caps, floors and swaptions on Black, shifted Black and Bachelier
(specifications/05-volatility/caps-and-swaptions.md)."""
from collections.abc import Sequence

from . import black, curves, daycount, projection
from .black import Option
from .curves import CurveData
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum

INDEX = "USD-TERM-3M"

def _option(model: str, call: bool, f: float, k: float, vol: float, t: float) -> float:
    return black.price(Option(model, "CALL" if call else "PUT", k, t, f), vol)


def _check_black(model: str, strike: float, forwards: Sequence[float]) -> None:
    if model == black.BLACK_76 and (strike <= 0 or any(f <= 0 for f in forwards)):
        raise QfError("E_DOMAIN", "BLACK_76 needs a positive strike and forwards", "strike")


def _check_tenor(months: int) -> None:
    if not 1 <= months <= 1200:
        raise QfError("E_INPUT", "tenor_months must be 1 to 1200", "tenor_months")


def cap_price(
    discount: CurveData, proj: CurveData, model: str, vol: float | Sequence[float], kind: str,
    start_months: int, tenor_months: int, strike: float, notional: float,
) -> tuple[list[float], float]:
    d, p = curves.build(discount), curves.build(proj)
    if start_months < 1:
        raise QfError("E_INPUT", "start_months must be at least 1", "start_months")
    start = projection._plus_months(INDEX, projection._spot(INDEX, d.as_of), start_months)
    _check_tenor(tenor_months)
    ps = projection._float_periods(INDEX, start, tenor_months)
    vols = [vol] * len(ps) if isinstance(vol, float) else list(vol)
    if len(vols) != len(ps):
        raise QfError("E_INPUT", "one vol per caplet", "vol")
    if any(v < 0 for v in vols):
        raise QfError("E_DOMAIN", "a vol is negative", "vol")
    alphas = [daycount.year_fraction("ACT_360", x.start, x.end) for x in ps]
    forwards = [(p.discount(x.start) / p.discount(x.end) - 1) / a
                for x, a in zip(ps, alphas, strict=True)]
    _check_black(model, strike, forwards)
    caplets = [
        notional * a * d.discount(x.end)
        * _option(model, kind == "CAP", f, strike, v, d.time(x.start))
        for x, a, f, v in zip(ps, alphas, forwards, vols, strict=True)
    ]
    return caplets, ordered_sum(caplets)


def swaption_price(
    discount: CurveData, proj: CurveData, model: str, vol: float, kind: str,
    expiry_months: int, tenor_months: int, strike: float, notional: float,
) -> tuple[float, float, float]:
    d, p = curves.build(discount), curves.build(proj)
    if expiry_months < 1:
        raise QfError("E_INPUT", "expiry_months must be at least 1", "expiry_months")
    _check_tenor(tenor_months)
    s = projection._plus_months(INDEX, projection._spot(INDEX, d.as_of), expiry_months)
    if vol < 0:
        raise QfError("E_DOMAIN", "vol is negative", "vol")
    fixed = projection._fixed_periods(INDEX, s, tenor_months)
    floating = projection._float_periods(INDEX, s, tenor_months)
    annuity, leg = projection._swap_legs(INDEX, fixed, floating, d, p)
    forward = leg / annuity
    _check_black(model, strike, [forward])
    value = notional * annuity * _option(model, kind == "PAYER", forward, strike, vol, d.time(s))
    return value, forward, annuity


guard(globals())
