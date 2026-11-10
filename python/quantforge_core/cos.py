"""COS Fourier pricing (specifications/01-core/cos.md)."""
import cmath
import math
from collections.abc import Callable
from dataclasses import dataclass

from .errors import QfError
from .finite import guard


@dataclass(frozen=True)
class BlackScholes:
    sigma: float


@dataclass(frozen=True)
class Heston:
    v0: float
    kappa: float
    theta: float
    sigma: float
    rho: float


def _check(model: BlackScholes | Heston) -> None:
    if isinstance(model, BlackScholes):
        if model.sigma <= 0:
            raise QfError("E_DOMAIN", "sigma must be positive", "model")
        return
    if model.sigma <= 0 or model.v0 <= 0 or model.kappa <= 0 or model.theta <= 0:
        raise QfError("E_DOMAIN", "sigma, v0, kappa and theta must be positive", "model")
    if abs(model.rho) >= 1:
        raise QfError("E_DOMAIN", "need |rho| < 1", "model")


def _characteristic(
    model: BlackScholes | Heston, r: float, q: float, t: float
) -> Callable[[float], complex]:
    if isinstance(model, BlackScholes):
        s2 = model.sigma * model.sigma

        def phi_bs(u: float) -> complex:
            return cmath.exp(1j * u * (r - q - s2 / 2) * t - s2 * u * u * t / 2)

        return phi_bs

    v0, kappa, theta, sigma, rho = model.v0, model.kappa, model.theta, model.sigma, model.rho
    s2 = sigma * sigma

    def phi_heston(u: float) -> complex:
        if u == 0:
            return 1 + 0j
        iu = 1j * u
        beta = kappa - rho * sigma * iu
        d = cmath.sqrt(beta * beta + s2 * (iu + u * u))
        g = (beta - d) / (beta + d)
        decay = cmath.exp(-d * t)
        one_minus = 1 - g * decay
        return cmath.exp(
            iu * (r - q) * t
            + (kappa * theta / s2) * ((beta - d) * t - 2 * cmath.log(one_minus / (1 - g)))
            + (v0 / s2) * (beta - d) * (1 - decay) / one_minus
        )

    return phi_heston


def _total_variance(model: BlackScholes | Heston, t: float) -> float:
    if isinstance(model, BlackScholes):
        return model.sigma * model.sigma * t
    k, theta = model.kappa, model.theta
    return (theta + (model.v0 - theta) * (1 - math.exp(-k * t)) / (k * t)) * t


def european(
    option: str, spot: float, strike: float, r: float, q: float, t: float,
    model: BlackScholes | Heston, terms: int, truncation: float,
) -> tuple[float, float, float]:
    """Returns (price, a, b)."""
    if spot <= 0 or strike <= 0 or t <= 0 or truncation <= 0:
        raise QfError("E_DOMAIN", "spot, strike, t and truncation must be positive")
    _check(model)
    if terms < 2:
        raise QfError("E_INPUT", "need terms >= 2", "terms")

    w = _total_variance(model, t)
    x = math.log(spot / strike)
    c1 = x + (r - q) * t - w / 2
    a = c1 - truncation * math.sqrt(w)
    b = c1 + truncation * math.sqrt(w)
    if a >= 0 or b <= 0:
        raise QfError("E_INPUT", "the range does not hold the strike", "truncation")

    phi = _characteristic(model, r, q, t)
    width = b - a
    exp_a = math.exp(a)
    total = 0.0
    for k in range(terms):
        u = k * math.pi / width
        angle = u * (0 - a)
        chi = (math.cos(angle) + u * math.sin(angle) - exp_a) / (1 + u * u)
        psi = math.sin(angle) / u if k else -a
        v_k = 2 / width * strike * (psi - chi)
        term = (phi(u) * cmath.exp(1j * u * (x - a))).real * v_k
        total += term / 2 if k == 0 else term
    put = math.exp(-r * t) * total
    if option == "PUT":
        return put, a, b
    return put + spot * math.exp(-q * t) - strike * math.exp(-r * t), a, b


guard(globals())
