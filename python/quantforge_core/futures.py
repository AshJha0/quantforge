"""Rate futures convexity under Hull-White (specifications/02-curves/futures-convexity.md)."""
import math

from .errors import QfError
from .finite import guard


def _b(a: float, x: float) -> float:
    """(1 - e^{-a x})/a, with limit x at a = 0."""
    return x if a == 0 else -math.expm1(-a * x) / a


def exponent(t: float, big_t: float, sigma: float, a: float) -> float:
    """z of the Hull-White bias, convexity = (1 - e^{-z}) (rate + 1/d)."""
    d = big_t - t
    bd, bt, big_l = _b(a, d), _b(a, t), _b(2 * a, t) * 2
    return sigma * sigma / 2 * (big_l * bd * bd + bd * bt * bt)


def convexity(
    price: float, t: float, big_t: float, sigma: float, a: float
) -> tuple[float, float, float]:
    """Returns (futures_rate, convexity, forward_rate)."""
    if big_t <= t:
        raise QfError("E_INPUT", "end_years must be after start_years", "end_years")
    if t < 0 or sigma < 0 or a < 0:
        raise QfError("E_DOMAIN", "start_years, sigma and mean_reversion must not be negative")
    rate = (100 - price) / 100
    d = big_t - t
    z = exponent(t, big_t, sigma, a)
    bias = -math.expm1(-z) * (rate + 1 / d)
    return rate, bias, rate - bias


guard(globals())
