"""Garman-Kohlhagen vanillas, FX delta conventions, ATM strikes and the smile from
ATM, risk reversal and strangle quotes.

Spec: specifications/05-volatility/fx-smile.md, rulings E-A9 to E-A11 in
specifications/stage-e-rulings.md. Strikes from delta are solved in x = ln(K/F).
"""
import math
from collections.abc import Callable

from . import roots
from .black import big_n, n_inverse, small_n
from .errors import QfError

DELTA_TYPES = ("SPOT", "FORWARD", "SPOT_PA", "FORWARD_PA")
ATM_TYPES = ("SPOT", "FORWARD", "DNS")
_X_TOL = 1e-15


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _positive(**values: float) -> None:
    """The common checks, in input order: each named value must be above 0."""
    for key, value in values.items():
        if not value > 0:
            raise _domain(f"{key} must be above 0", key)


class _Market:
    def __init__(self, spot: float, t: float, rd: float, rf: float, vol: float):
        self.spot, self.t, self.vol = spot, t, vol
        self.forward = spot * math.exp((rd - rf) * t)
        self.dd, self.df = math.exp(-rd * t), math.exp(-rf * t)
        self.root = vol * math.sqrt(t)

    def d1(self, strike: float) -> float:
        return math.log(self.forward / strike) / self.root + self.root / 2

    def delta(self, kind: str, phi: float, strike: float) -> float:
        d1 = self.d1(strike)
        if kind in ("SPOT", "FORWARD"):
            value = phi * big_n(phi * d1)
            return value * self.df if kind == "SPOT" else value
        value = phi * (strike / self.forward) * big_n(phi * (d1 - self.root))
        return value * self.df if kind == "SPOT_PA" else value


def _phi(option_type: str) -> float:
    return 1.0 if option_type == "CALL" else -1.0


def option_price(spot: float, strike: float, t: float, rd: float, rf: float, vol: float,
                 option_type: str, notional: float) -> dict[str, float]:
    _positive(spot=spot, strike=strike, expiry_years=t, vol=vol, notional=notional)
    m, phi = _Market(spot, t, rd, rf, vol), _phi(option_type)
    d1 = m.d1(strike)
    d2 = d1 - m.root
    unit = phi * m.dd * (m.forward * big_n(phi * d1) - strike * big_n(phi * d2))
    density = small_n(d1)
    return {
        "price": notional * unit, "premium_pct_foreign": unit / spot, "forward": m.forward,
        "delta": notional * phi * m.df * big_n(phi * d1),
        "gamma": notional * m.df * density / (spot * m.root),
        "vega": notional * spot * m.df * density * math.sqrt(t),
    }


def delta_from_strike(spot: float, strike: float, t: float, rd: float, rf: float, vol: float,
                      option_type: str) -> dict[str, float]:
    _positive(spot=spot, strike=strike, expiry_years=t, vol=vol)
    m, phi = _Market(spot, t, rd, rf, vol), _phi(option_type)
    return {kind: m.delta(kind, phi, strike) for kind in DELTA_TYPES}


def _brent(f: Callable[[float], float], low: float, high: float) -> float:
    return roots.brent(f, low, high, x_tol=_X_TOL, max_iter=500).root


def _bracket_up(f: Callable[[float], float], start: float) -> float:
    """The first x = start + 2^i (i >= 0) with f(x) of the sign opposite to f(start)."""
    sign, step = f(start) > 0, 1.0
    while (f(start + step) > 0) == sign:
        step *= 2
        if step > 1e6:
            raise QfError("E_NO_CONVERGENCE", "no strike bracket", "delta")
    return start + step


def _pa_call_peak(m: _Market) -> float:
    """x* = ln(K*/F), where v sqrt T N(d2) = n(d2); left of it the PA call delta rises."""
    def h(d2: float) -> float:
        return m.root * big_n(d2) - small_n(d2)

    low = -1.0
    while h(low) > 0:
        low -= 1.0
    high = 1.0
    while h(high) < 0:
        high += 1.0
    d2 = _brent(h, low, high)
    return -m.root * d2 - m.root * m.root / 2


def delta_to_strike(spot: float, t: float, rd: float, rf: float, vol: float, option_type: str,
                    delta: float, delta_type: str) -> float:
    _positive(spot=spot, expiry_years=t, vol=vol)
    m, phi = _Market(spot, t, rd, rf, vol), _phi(option_type)
    if not phi * delta > 0:
        raise _domain("a call delta must be above 0 and a put delta below 0", "delta")
    if delta_type in ("SPOT", "FORWARD"):
        scale = m.df if delta_type == "SPOT" else 1.0
        if not abs(delta) < scale:
            raise _domain("delta is out of range", "delta")
        d1 = phi * n_inverse(phi * delta / scale)
        return m.forward * math.exp(-d1 * m.root + m.root * m.root / 2)

    def gap(x: float) -> float:
        return m.delta(delta_type, phi, m.forward * math.exp(x)) - delta

    if phi > 0:
        peak = _pa_call_peak(m)
        if not delta < m.delta(delta_type, phi, m.forward * math.exp(peak)):
            raise _domain("delta is at or above the premium-adjusted maximum", "delta")
        high = _bracket_up(gap, peak)  # gap > 0 at the peak, falls to -delta far above
        return m.forward * math.exp(_brent(gap, peak, high))
    # PA put: delta falls from 0 (low strikes) towards -infinity (high strikes).
    low = -1.0
    while gap(low) < 0:
        low -= 1.0
        if low < -1e4:
            raise QfError("E_NO_CONVERGENCE", "no strike bracket", "delta")
    high = _bracket_up(gap, low)
    return m.forward * math.exp(_brent(gap, low, high))


def atm_strike(spot: float, t: float, rd: float, rf: float, vol: float, atm_type: str,
               delta_type: str) -> float:
    _positive(spot=spot, expiry_years=t, vol=vol)
    m = _Market(spot, t, rd, rf, vol)
    if atm_type == "SPOT":
        return spot
    if atm_type == "FORWARD":
        return m.forward
    half = vol * vol * t / 2
    return m.forward * math.exp(-half if delta_type.endswith("_PA") else half)


def smile_from_quotes(spot: float, t: float, rd: float, rf: float, atm_vol: float, rr: float,
                      bf: float, delta: float, delta_type: str,
                      atm_type: str) -> dict[str, float]:
    _positive(spot=spot, expiry_years=t, atm_vol=atm_vol)
    if not 0 < delta < 0.5:
        raise _domain("delta must be in (0, 0.5)", "delta")
    call_vol, put_vol = atm_vol + bf + rr / 2, atm_vol + bf - rr / 2
    if not call_vol > 0:
        raise _domain("call_vol is not above 0", "bf")
    if not put_vol > 0:
        raise _domain("put_vol is not above 0", "bf")
    return {
        "atm_strike": atm_strike(spot, t, rd, rf, atm_vol, atm_type, delta_type),
        "call_vol": call_vol, "put_vol": put_vol,
        "call_strike": delta_to_strike(spot, t, rd, rf, call_vol, "CALL", delta, delta_type),
        "put_strike": delta_to_strike(spot, t, rd, rf, put_vol, "PUT", -delta, delta_type),
    }
