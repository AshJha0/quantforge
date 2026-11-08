"""Stage E, E8: CDS options, two-name default copulas and the large homogeneous pool.

Spec: specifications/04-pricing/credit-options-and-copulas.md, rulings E-B22 to E-B26 in
specifications/stage-e-rulings-b.md. Bivariate CDFs are integrals of the conditional form,
by adaptive Gauss-Kronrod (integrate.py) to about 1e-14 relative.
"""
import itertools
import math
from collections.abc import Callable
from datetime import date, timedelta

from . import black, integrate, roots
from .black import Option, big_n, n_inverse, small_n
from .errors import QfError
from .schedules import add_months

_TOL = 1e-16


def _input(message: str, field: str | None = None) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


# --- CDS options ---

def _legs(as_of: date, expiry: date, maturity: date, rate: float,
          hazard: float, recovery: float) -> tuple[float, float]:
    """(protection, risky annuity) per unit notional of the stylised forward CDS (E-B22)."""
    dates = [expiry]
    k = 1
    while dates[-1] < maturity:
        dates.append(min(add_months(expiry, 3 * k), maturity))
        k += 1

    def t(d: date) -> float:
        return (d - as_of).days / 365

    def survival(d: date) -> float:
        return math.exp(-hazard * t(d))

    def discount(d: date) -> float:
        return math.exp(-rate * t(d))

    protection, annuity = 0.0, 0.0
    for a, b in itertools.pairwise(dates):
        mid = a + timedelta(days=(b - a).days // 2)
        lost = survival(a) - survival(b)
        protection += (1 - recovery) * discount(mid) * lost
        annuity += ((b - a).days / 360 * discount(b) * survival(b)
                    + (mid - a).days / 360 * discount(mid) * lost)
    return protection, annuity


def _check_option(as_of: date, expiry: date, maturity: date, hazard: float, recovery: float,
                  strike: float) -> None:
    if expiry <= as_of or maturity <= expiry:
        raise _input("need as_of < expiry < maturity", "expiry")
    if not 0 <= recovery < 1:
        raise _domain("recovery must be in [0, 1)", "recovery")
    if hazard < 0:
        raise _domain("hazard_rate must not be negative", "hazard_rate")
    if strike <= 0:
        raise _domain("strike must be above 0", "strike")


def _terms(as_of: date, expiry: date, maturity: date, rate: float, hazard: float,
           recovery: float, kind: str, strike: float, notional: float
           ) -> tuple[float, float, float, Option]:
    protection, annuity = _legs(as_of, expiry, maturity, rate, hazard, recovery)
    forward = protection / annuity
    t = (expiry - as_of).days / 365
    front = notional * (1 - recovery) * (1 - math.exp(-hazard * t)) * math.exp(-rate * t)
    option = Option(black.BLACK_76, "CALL" if kind == "PAYER" else "PUT", strike, t, forward)
    return forward, annuity, front, option


def cds_option_price(as_of: date, expiry: date, maturity: date, rate: float, hazard: float,
                     recovery: float, kind: str, strike: float, notional: float, vol: float,
                     knock_out: bool) -> dict[str, float]:
    _check_option(as_of, expiry, maturity, hazard, recovery, strike)
    if vol < 0:
        raise _domain("vol must not be negative", "vol")
    forward, annuity, front, option = _terms(as_of, expiry, maturity, rate, hazard, recovery,
                                             kind, strike, notional)
    price = notional * annuity * black.price(option, vol)
    if kind == "PAYER" and not knock_out:
        price += front
    return {"price": price, "forward_spread": forward, "risky_annuity": annuity,
            "front_end_protection": front}


def cds_option_implied(as_of: date, expiry: date, maturity: date, rate: float, hazard: float,
                       recovery: float, kind: str, strike: float, notional: float,
                       premium: float, knock_out: bool) -> float:
    if not knock_out:  # ruling E-B40: before the dates
        raise _input("implied vol is defined for knock-out options only", "knock_out")
    _check_option(as_of, expiry, maturity, hazard, recovery, strike)
    forward, annuity, _, option = _terms(as_of, expiry, maturity, rate, hazard, recovery, kind,
                                         strike, notional)
    scale = notional * annuity
    floor = scale * max(option.phi * (forward - strike), 0.0)
    cap = scale * (forward if kind == "PAYER" else strike)
    if not floor < premium < cap:
        raise _domain("the premium has no implied vol", "premium")

    def gap(v: float) -> float:
        return scale * black.price(option, v) - premium

    high = 1.0
    while gap(high) < 0:
        high *= 2
        if high > 1e6:
            raise QfError("E_NO_CONVERGENCE", "no implied vol bracket", "premium")
    return roots.brent(gap, 0.0, high, x_tol=1e-15, max_iter=500).root


# --- Univariate and bivariate distributions ---

def _beta_fraction(a: float, b: float, x: float) -> float:
    """Continued fraction of the regularised incomplete beta (modified Lentz)."""
    tiny = 1e-300
    c, d = 1.0, 1 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 1000):
        for num in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
                    -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1 + num * d
            d = 1 / (d if abs(d) > tiny else tiny)
            c = 1 + num / c if abs(1 + num / c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1) < 1e-16:
            break
    return h


def _incomplete_beta(a: float, b: float, x: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1) / (a + b + 2):
        return front * _beta_fraction(a, b, x) / a
    return 1 - front * _beta_fraction(b, a, 1 - x) / b


def t_cdf(x: float, nu: float) -> float:
    tail = 0.5 * _incomplete_beta(nu / 2, 0.5, nu / (nu + x * x))
    return tail if x < 0 else 1 - tail


def t_pdf(x: float, nu: float) -> float:
    log = (math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2) - 0.5 * math.log(nu * math.pi)
           - (nu + 1) / 2 * math.log1p(x * x / nu))
    return math.exp(log)


def t_inverse(p: float, nu: float) -> float:
    def gap(x: float) -> float:
        return t_cdf(x, nu) - p

    low, high = -1.0, 1.0
    while gap(low) > 0:
        low *= 2
    while gap(high) < 0:
        high *= 2
    return roots.brent(gap, low, high, x_tol=1e-15, max_iter=500).root


def _integral(f: Callable[[float], float], a: float, b: float) -> float:
    if b <= a:
        return 0.0
    return integrate.gauss_kronrod(f, a, b, tol=_TOL, max_intervals=2000)[0]


def bivariate_normal(h: float, k: float, rho: float) -> float:
    """Phi_2(h, k; rho) = integral to h of n(x) N((k - rho x)/sqrt(1 - rho^2)) dx."""
    root = math.sqrt(1 - rho * rho)
    upper = min(h, 40.0)

    def f(x: float) -> float:
        return small_n(x) * big_n((k - rho * x) / root)

    return _integral(f, -40.0, upper)


def bivariate_t(h: float, k: float, rho: float, nu: float) -> float:
    """T_2,nu: integral to h of t_nu(x) T_{nu+1}((k - rho x) / s(x)), x = h - tan(phi)."""
    one = 1 - rho * rho

    def f(phi: float) -> float:
        x = h - math.tan(phi)
        scale = math.sqrt((nu + x * x) * one / (nu + 1))
        return t_pdf(x, nu) * t_cdf((k - rho * x) / scale, nu + 1) / math.cos(phi) ** 2

    return _integral(f, 0.0, math.pi / 2)


def joint_default(copula: str, probabilities: list[float], rho: float,
                  nu: float | None) -> dict[str, float]:
    if len(probabilities) != 2:
        raise _input("default_probabilities needs two values", "default_probabilities")
    if copula == "STUDENT_T" and nu is None:
        raise _input("STUDENT_T needs degrees_of_freedom", "degrees_of_freedom")
    if any(not 0 < p < 1 for p in probabilities):
        raise _domain("a default probability is outside (0, 1)", "default_probabilities")
    if abs(rho) >= 1:
        raise _domain("|correlation| must be below 1", "correlation")
    p1, p2 = probabilities
    if copula == "GAUSSIAN":
        joint = bivariate_normal(n_inverse(p1), n_inverse(p2), rho)
    else:
        assert nu is not None
        if nu <= 0:
            raise _domain("degrees_of_freedom must be above 0", "degrees_of_freedom")
        joint = bivariate_t(t_inverse(p1, nu), t_inverse(p2, nu), rho, nu)
    correlation = (joint - p1 * p2) / math.sqrt(p1 * (1 - p1) * p2 * (1 - p2))
    return {"joint_default_probability": joint, "default_correlation": correlation}


# --- Large homogeneous pool ---

def _check_pool(p: float, rho: float, recovery: float) -> None:
    if not 0 < p < 1:
        raise _domain("default_probability must be in (0, 1)", "default_probability")
    if not 0 < rho < 1:
        raise _domain("correlation must be in (0, 1)", "correlation")
    if not 0 <= recovery < 1:
        raise _domain("recovery must be in [0, 1)", "recovery")


def _capped_mean(p: float, rho: float, k: float) -> float:
    """E[min(P(M), k)] by ruling E-B25."""
    if k >= 1:
        return p
    if k <= 0:
        return 0.0
    c = n_inverse(p)
    m_star = (c - math.sqrt(1 - rho) * n_inverse(k)) / math.sqrt(rho)
    return p - (bivariate_normal(c, m_star, math.sqrt(rho)) - k * big_n(m_star))


def tranche_loss(p: float, rho: float, recovery: float, attachment: float,
                 detachment: float) -> float:
    if detachment <= attachment or attachment < 0 or detachment > 1:
        raise _input("need 0 <= attachment < detachment <= 1", "attachment")
    _check_pool(p, rho, recovery)
    scale = 1 - recovery
    upper = _capped_mean(p, rho, min(detachment / scale, 1.0))
    lower = _capped_mean(p, rho, min(attachment / scale, 1.0)) if attachment > 0 else 0.0
    return scale * (upper - lower) / (detachment - attachment)


def loss_cdf(p: float, rho: float, recovery: float, losses: list[float]) -> list[float]:
    if not losses:  # ruling E-B40
        raise _input("losses is empty", "losses")
    _check_pool(p, rho, recovery)
    scale = 1 - recovery
    if any(not 0 < x < scale for x in losses):
        raise _domain("a loss is outside (0, 1 - R)", "losses")
    c = n_inverse(p)
    return [big_n((math.sqrt(1 - rho) * n_inverse(x / scale) - c) / math.sqrt(rho))
            for x in losses]

