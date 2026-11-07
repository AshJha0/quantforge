"""Black-Scholes, Black-76, Bachelier, and their Greeks (specifications/05-volatility/black-models.md,
specifications/06-risk/vol-greeks.md)."""
import math
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any

from .equity import ForwardResult
from .errors import QfError

_SQRT2 = math.sqrt(2.0)
_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)
BLACK_SCHOLES, BLACK_76, BACHELIER = "BLACK_SCHOLES", "BLACK_76", "BACHELIER"


def big_n(x: float) -> float:
    return 0.5 * math.erfc(-x / _SQRT2)


def small_n(x: float) -> float:
    return math.exp(-0.5 * x * x) * _INV_SQRT_2PI


@lru_cache(maxsize=1)
def _unit() -> Any:
    from statistics import NormalDist  # lazy: statistics is slow to import

    return NormalDist()


def n_inverse(p: float) -> float:
    return _unit().inv_cdf(p)


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


@dataclass(frozen=True)
class Option:
    """Terms of one European option. `underlying` is the spot or forward, as the model takes."""

    model: str
    option_type: str
    strike: float
    expiry_years: float
    underlying: float
    rate: float = 0.0
    dividend_yield: float = 0.0
    discount_factor: float = 1.0
    shift: float = 0.0

    @property
    def phi(self) -> float:
        return 1.0 if self.option_type == "CALL" else -1.0

    @property
    def discount(self) -> float:
        if self.model == BLACK_SCHOLES:
            return math.exp(-self.rate * self.expiry_years)
        return self.discount_factor

    @property
    def forward(self) -> float:
        """Unshifted."""
        if self.model == BLACK_SCHOLES:
            growth = (self.rate - self.dividend_yield) * self.expiry_years
            return self.underlying * math.exp(growth)
        return self.underlying


def check(o: Option, vol: float | None) -> None:
    if o.expiry_years < 0:
        raise _domain("expiry_years is negative", "expiry_years")
    if vol is not None and vol < 0:
        raise _domain("vol is negative", "vol")
    if o.discount_factor <= 0:
        raise _domain("discount_factor must be positive", "discount_factor")
    if o.model != BACHELIER:
        if o.underlying + o.shift <= 0:
            raise _domain("the underlying must be positive", "forward")
        if o.strike + o.shift <= 0:
            raise _domain("the strike must be positive", "strike")


def _d1(f: float, k: float, v: float, t: float) -> float:
    root = v * math.sqrt(t)
    return (math.log(f / k) + 0.5 * root * root) / root


def _value(o: Option, v: float) -> float:
    t, phi, d = o.expiry_years, o.phi, o.discount
    f, k = o.forward + o.shift, o.strike + o.shift
    if t == 0 or v == 0:
        return d * max(phi * (f - k), 0.0)
    if o.model == BACHELIER:
        root = v * math.sqrt(t)
        x = (f - k) / root
        return d * (phi * (f - k) * big_n(phi * x) + root * small_n(x))
    d1 = _d1(f, k, v, t)
    d2 = d1 - v * math.sqrt(t)
    return d * phi * (f * big_n(phi * d1) - k * big_n(phi * d2))


def price(o: Option, vol: float) -> float:
    check(o, vol)
    return _value(o, vol)


def _vega(o: Option, v: float) -> float:
    t, d = o.expiry_years, o.discount
    f, k = o.forward + o.shift, o.strike + o.shift
    if o.model == BACHELIER:
        return d * math.sqrt(t) * small_n((f - k) / (v * math.sqrt(t)))
    return d * f * small_n(_d1(f, k, v, t)) * math.sqrt(t)


def implied(o: Option, target: float) -> float:
    check(o, None)
    if o.expiry_years == 0:
        raise _domain("expiry_years is zero", "expiry_years")
    phi, d = o.phi, o.discount
    f, k = o.forward + o.shift, o.strike + o.shift
    intrinsic = d * max(phi * (f - k), 0.0)
    if target < intrinsic:
        raise _domain("price is below intrinsic", "price")
    if o.model != BACHELIER and target >= d * (f if phi > 0 else k):
        raise _domain("price is at or above the upper bound", "price")
    if target == intrinsic:
        return 0.0
    t = o.expiry_years
    if o.model == BACHELIER:
        v = (target - intrinsic) / d * math.sqrt(2.0 * math.pi / t) + 1e-12
    else:
        v = math.sqrt(2.0 * abs(math.log(f / k)) / t) + 0.2
    low, high = 0.0, math.inf
    for _ in range(400):
        error = _value(o, v) - target
        if error == 0:
            return v
        if error > 0:
            high = v
        else:
            low = v
        vega = _vega(o, v)
        step = v - error / vega if vega > 0 else math.nan
        if not low < step < min(high, 4.0 * v):
            step = 2.0 * v if math.isinf(high) else 0.5 * (low + high)
        if abs(step - v) <= 1e-15 * v:
            v = step
            break
        v = step
    if abs(_value(o, v) - target) > 1e-12 * max(1.0, target):
        raise QfError("E_NO_CONVERGENCE", "the implied vol solve did not converge", "price")
    return v


def greeks(o: Option, vol: float) -> dict[str, float]:
    check(o, vol)
    if vol <= 0:
        raise _domain("vol must be positive", "vol")
    t = o.expiry_years
    if t <= 0:
        raise _domain("expiry_years must be positive", "expiry_years")
    phi, d, v, root_t = o.phi, o.discount, vol, math.sqrt(o.expiry_years)
    f, k = o.forward + o.shift, o.strike + o.shift
    value = _value(o, v)
    if o.model == BACHELIER:
        x = (f - k) / (v * root_t)
        n = small_n(x)
        vega = d * root_t * n
        return {
            "price": value, "delta": d * phi * big_n(phi * x), "gamma": d * n / (v * root_t),
            "vega": vega, "theta": -d * v * n / (2 * root_t), "rho": -t * value,
            "vanna": -d * n * x / v, "volga": d * root_t * n * x * x / v,
        }
    d1 = _d1(f, k, v, t)
    d2 = d1 - v * root_t
    n = small_n(d1)
    if o.model == BLACK_SCHOLES:
        s, r, q = o.underlying, o.rate, o.dividend_yield
        big_q = math.exp(-q * t)
        vega = s * big_q * n * root_t
        return {
            "price": value, "delta": big_q * phi * big_n(phi * d1),
            "gamma": big_q * n / (s * v * root_t), "vega": vega,
            "theta": -s * big_q * n * v / (2 * root_t) - phi * r * k * d * big_n(phi * d2)
            + phi * q * s * big_q * big_n(phi * d1),
            "rho": phi * k * t * d * big_n(phi * d2), "vanna": -big_q * n * d2 / v,
            "volga": vega * d1 * d2 / v,
        }
    vega = d * f * n * root_t
    return {
        "price": value, "delta": d * phi * big_n(phi * d1), "gamma": d * n / (f * v * root_t),
        "vega": vega, "theta": -d * f * n * v / (2 * root_t), "rho": -t * value,
        "vanna": -d * n * d2 / v, "volga": vega * d1 * d2 / v,
    }


def bump_greeks(o: Option, vol: float) -> dict[str, float]:
    check(o, vol)
    if vol <= 0:
        raise _domain("vol must be positive", "vol")
    if o.expiry_years <= 0:
        raise _domain("expiry_years must be positive", "expiry_years")
    u = o.underlying
    if o.model == BACHELIER:
        hu = 1e-4 * max(abs(u), 1.0)
    else:
        hu = 1e-4 * (u + o.shift)
    hv = 1e-3 * vol
    up, down = replace(o, underlying=u + hu), replace(o, underlying=u - hu)
    v_up, v_down = vol + hv, vol - hv
    mid = _value(o, vol)
    s_up, s_down = _value(up, vol), _value(down, vol)
    w_up, w_down = _value(o, v_up), _value(o, v_down)
    return {
        "delta": (s_up - s_down) / (2 * hu),
        "gamma": (s_up - 2 * mid + s_down) / (hu * hu),
        "vega": (w_up - w_down) / (2 * hv),
        "volga": (w_up - 2 * mid + w_down) / (hv * hv),
        "vanna": (
            _value(up, v_up) - _value(up, v_down) - _value(down, v_up) + _value(down, v_down)
        ) / (4 * hu * hv),
    }


def black76_position(
    option_type: str, forward: float, strike: float, discount: float, expiry_years: float,
    vol: float, signed_quantity: float,
) -> tuple[float, float, float]:
    """PV, delta against the forward, and vega of a signed position. Needs T, vol above 0."""
    phi = 1.0 if option_type == "CALL" else -1.0
    o = Option(BLACK_76, option_type, strike, expiry_years, forward, discount_factor=discount)
    d1 = _d1(forward, strike, vol, expiry_years)
    vega = discount * forward * small_n(d1) * math.sqrt(expiry_years)
    delta = discount * phi * big_n(phi * d1)
    return signed_quantity * _value(o, vol), signed_quantity * delta, signed_quantity * vega


def equity_option(
    r: ForwardResult, option_type: str, strike: float, vol: float, quantity: float, side: str
) -> dict[str, float]:
    if r.time == 0:
        raise _domain("expiry equals as_of", "expiry")
    if vol <= 0:
        raise _domain("vol must be positive", "vol")
    if strike <= 0:
        raise _domain("strike must be positive", "strike")
    if quantity <= 0:
        raise _domain("quantity must be positive", "quantity")
    signed = quantity if side == "BUY" else -quantity
    f, c, t = r.forward, r.carry_factor, r.time
    pv, forward_delta, vega = black76_position(
        option_type, f, strike, r.discount_factor, t, vol, signed
    )
    n = small_n(_d1(f, strike, vol, t))
    gamma = signed * r.discount_factor * n / (f * vol * math.sqrt(t) * c * c)
    return {"pv": pv, "delta": forward_delta / c, "gamma": gamma, "vega": vega}
