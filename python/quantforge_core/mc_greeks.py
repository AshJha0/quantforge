"""Monte Carlo Greeks of a European option under GBM: pathwise (with a call-spread smoothed
digital), likelihood ratio, and central bump with common draws.

Specification: specifications/06-risk/mc-greeks.md; rulings G-10, G-10b and G-15. Draws are the
`core.rng` stream 0 of `seed`, one AS 241 normal per path, path `i` the `i`-th normal.
"""
import math
from collections.abc import Callable, Sequence

from .errors import QfError
from .finite import guard
from .rng import normals

PAYOFFS = ("CALL", "PUT", "DIGITAL_CALL")
METHODS = ("PATHWISE", "LIKELIHOOD_RATIO", "BUMP")


def _input(message: str, field: str) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _payoff(kind: str, k: float) -> Callable[[float], float]:
    if kind == "CALL":
        return lambda s: max(s - k, 0.0)
    if kind == "PUT":
        return lambda s: max(k - s, 0.0)
    return lambda s: 1.0 if s > k else 0.0


def mean_and_se(values: Sequence[float]) -> tuple[float, float]:
    """Sample mean (compensated sum, as the spec allows) and standard error, divisor `n - 1`."""
    n = len(values)
    mean = math.fsum(values) / n
    var = math.fsum((x - mean) ** 2 for x in values) / (n - 1)
    return mean, math.sqrt(var / n)


def check(s: float, k: float, t: float, v: float, payoff: str, method: str, paths: int,
          smoothing_width: float | None, bump_relative: float | None) -> None:
    """The error checks of `risk.mc.greeks`, in the spec order (after F-2)."""
    if payoff not in PAYOFFS:
        raise _input(f"{payoff} is not a payoff", "payoff")
    if method not in METHODS:
        raise _input(f"{method} is not a method", "method")
    if paths < 2:
        raise _input("paths must be at least 2", "paths")
    for key, value in (("spot", s), ("strike", k), ("expiry_years", t), ("vol", v)):
        if not value > 0:
            raise _domain(f"{key} must be above 0", key)
    wants_eps = method == "PATHWISE" and payoff == "DIGITAL_CALL"
    if wants_eps != (smoothing_width is not None):
        raise _input("smoothing_width goes with PATHWISE on DIGITAL_CALL only", "smoothing_width")
    if smoothing_width is not None and not smoothing_width > 0:
        raise _domain("smoothing_width must be above 0", "smoothing_width")
    if (method == "BUMP") != (bump_relative is not None):
        raise _input("bump_relative goes with BUMP only", "bump_relative")
    if bump_relative is not None and not 0 < bump_relative < 1:
        raise _domain("bump_relative must be in (0, 1)", "bump_relative")


def per_path_terms(s: float, k: float, t: float, r: float, q: float, v: float, payoff: str,
                   method: str, z: Sequence[float], smoothing_width: float | None = None,
                   bump_relative: float | None = None
                   ) -> tuple[list[float], list[float], list[float]]:
    """The per-path price, delta and vega terms of the spec's table."""
    f = _payoff(payoff, k)
    disc = math.exp(-r * t)
    rt = math.sqrt(t)

    def terminal(spot: float, vol: float, x: float) -> float:
        return spot * math.exp((r - q - vol * vol / 2) * t + vol * rt * x)

    prices, deltas, vegas = [], [], []
    for x in z:
        st = terminal(s, v, x)
        prices.append(disc * f(st))
        ds_dv = st * (rt * x - v * t)
        if method == "PATHWISE":
            if payoff == "CALL":
                w = 1.0 if st > k else 0.0
            elif payoff == "PUT":
                w = -1.0 if st < k else 0.0
            else:
                assert smoothing_width is not None
                w = (1.0 / (2 * smoothing_width)) if abs(st - k) < smoothing_width else 0.0
            deltas.append(disc * w * st / s)
            vegas.append(disc * w * ds_dv)
        elif method == "LIKELIHOOD_RATIO":
            fv = disc * f(st)
            deltas.append(fv * x / (s * v * rt))
            vegas.append(fv * ((x * x - 1) / v - x * rt))
        else:
            assert bump_relative is not None
            h = bump_relative
            up, dn = f(terminal(s * (1 + h), v, x)), f(terminal(s * (1 - h), v, x))
            deltas.append((disc * up - disc * dn) / (2 * h * s))
            vu, vd = f(terminal(s, v * (1 + h), x)), f(terminal(s, v * (1 - h), x))
            vegas.append((disc * vu - disc * vd) / (2 * h * v))
    return prices, deltas, vegas


def greeks(s: float, k: float, t: float, r: float, q: float, v: float, payoff: str, method: str,
           paths: int, seed: int, smoothing_width: float | None,
           bump_relative: float | None) -> dict[str, float]:
    """`risk.mc.greeks`: price, delta and vega with their standard errors."""
    check(s, k, t, v, payoff, method, paths, smoothing_width, bump_relative)
    z = normals(seed, 0, paths)
    prices, deltas, vegas = per_path_terms(s, k, t, r, q, v, payoff, method, z, smoothing_width,
                                           bump_relative)
    out: dict[str, float] = {}
    for name, values in (("price", prices), ("delta", deltas), ("vega", vegas)):
        out[name], out[f"{name}_se"] = mean_and_se(values)
    return out


guard(globals())
