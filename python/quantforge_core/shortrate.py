"""One-factor short-rate models (Vasicek, CIR, Hull-White) and G2++, with the products built on
them: bond options, Jamshidian swaptions, caps and floors, Hull-White sigma calibration, the pinned
Bermudan and callable-bond scheme, and closed-form swap exposure with CVA.

Specification: specifications/04-pricing/short-rate-models.md and
specifications/06-risk/xva-exposure.md; rulings G-1 to G-21 in specifications/stage-g-rulings.md.

Times are year fractions. Every model exposes its bond as `P(t, T; r) = A exp(-B r)`, so the
Jamshidian decomposition, the caps and the swap exposure are written once over a `_Model`.
"""
import bisect
import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .black import big_n
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum

Floats = Sequence[float]
MODELS = ("VASICEK", "CIR", "HULL_WHITE")
# Below this value of a*tau the cancelling closed forms are replaced by their power series (G-2).
# The series are entire, so the switch point only trades terms against cancellation.
_SERIES_BELOW = 0.5
_SERIES_TERMS = 40


def _input(message: str, field: str | None = None) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _positive(**values: float) -> None:
    for key, value in values.items():
        if not value > 0:
            raise _domain(f"{key} must be above 0", key)


def _increasing(values: Floats) -> bool:
    return all(a < b for a, b in itertools.pairwise(values))


# --- small-a building blocks (ruling G-2) -------------------------------------------------------


def b_factor(a: float, tau: float) -> float:
    """`B = (1 - e^{-a tau}) / a`, by expm1 so that small `a` keeps its digits."""
    return -math.expm1(-a * tau) / a


def _b_minus_tau(a: float, tau: float) -> float:
    """`B - tau`, by its series `tau sum_{n>=1} (-u)^n / (n+1)!` for small `u = a tau`."""
    u = a * tau
    if u >= _SERIES_BELOW:
        return b_factor(a, tau) - tau
    total, term = 0.0, 1.0
    for n in range(1, _SERIES_TERMS):
        term *= -u / (n + 1) if n > 1 else -u / 2
        total += term
    return tau * total


def _q_series(u: float) -> float:
    """`Q(u) = (3/2 - 2 e^{-u} + e^{-2u}/2 - u) / u^3` for small `u`, by its Taylor series
    `sum_{n>=3} (-1)^n (2^{n-1} - 2) / n! u^{n-3}`."""
    total, fact, power = 0.0, 6.0, 1.0
    for n in range(3, _SERIES_TERMS):
        if n > 3:
            fact *= n
            power *= u
        total += (-1) ** n * (2.0 ** (n - 1) - 2.0) / fact * power
    return total


def _gauss_variance(a: float, sigma: float, tau: float) -> float:
    """`sigma^2/a^2 (tau + 2 e^{-a tau}/a - e^{-2 a tau}/(2a) - 3/(2a))`, the one-factor variance
    integral of G2++ and of the Vasicek `A`; equal to `-sigma^2 tau^3 Q(a tau)`."""
    u = a * tau
    if u < _SERIES_BELOW:
        return -sigma * sigma * tau ** 3 * _q_series(u)
    return sigma * sigma / (a * a) * (tau + 2 / a * math.exp(-u) - math.exp(-2 * u) / (2 * a)
                                      - 1.5 / a)


def _cross_term(a: float, b: float, tau: float) -> float:
    """`(tau - B_a - B_b + B_{a+b}) / (a b)`, the G2++ cross integral, by series for small rates."""
    if (a + b) * tau >= _SERIES_BELOW:
        return (tau - b_factor(a, tau) - b_factor(b, tau) + b_factor(a + b, tau)) / (a * b)
    # tau sum_{n>=2} (-tau)^n/(n+1)! ((a+b)^n - a^n - b^n) / (a b); the bracket over a b is the
    # positive sum sum_{k=1}^{n-1} C(n, k) a^{k-1} b^{n-k-1}.
    total = 0.0
    for n in range(2, _SERIES_TERMS):
        inner = ordered_sum(math.comb(n, k) * a ** (k - 1) * b ** (n - k - 1) for k in range(1, n))
        total += (-tau) ** n / math.factorial(n + 1) * inner
    return tau * total


# --- the curve -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Curve:
    """Log-linear discount curve with `(0, 1)` as the first node and flat forward after the last
    pillar; the forward at a pillar time is the right-hand one (G-3)."""

    nodes: tuple[float, ...]
    logs: tuple[float, ...]

    def discount(self, t: float) -> float:
        if t <= 0:
            return 1.0
        n = self.nodes
        j = bisect.bisect_right(n, t) - 1
        if j >= len(n) - 1:
            j = len(n) - 2
        w = (t - n[j]) / (n[j + 1] - n[j])
        return math.exp(self.logs[j] + (self.logs[j + 1] - self.logs[j]) * w)

    def forward(self, t: float) -> float:
        n = self.nodes
        j = min(max(bisect.bisect_right(n, t) - 1, 0), len(n) - 2)
        return -(self.logs[j + 1] - self.logs[j]) / (n[j + 1] - n[j])


def make_curve(times: Floats, discount_factors: Floats) -> Curve:
    """Checks the curve rules: pillars strictly increasing and above 0 (E_INPUT), discount factors
    above 0 (E_DOMAIN), at least one pillar."""
    if not times or len(times) != len(discount_factors):
        raise _input("the curve needs at least one pillar and one factor per time", "curve")
    if times[0] <= 0 or not _increasing(times):
        raise _input("curve times must be strictly increasing and above 0", "curve.times")
    if any(not d > 0 for d in discount_factors):
        raise _domain("curve discount factors must be above 0", "curve.discount_factors")
    return Curve((0.0, *times), (0.0, *(math.log(d) for d in discount_factors)))


# --- the models ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Model:
    """A one-factor affine model: `kind`, `a`, `sigma`, and `b` (Vasicek, CIR) or `curve` (Hull-White),
    plus the short rate today (`r0`, Vasicek and CIR)."""

    kind: str
    a: float
    sigma: float
    b: float = 0.0
    curve: Curve | None = None
    r0: float = 0.0

    def ab(self, t: float, s: float) -> tuple[float, float]:
        """`(ln A, B)` of the bond from `t` to `s`, so that `P(t, s; r) = exp(ln A - B r)`."""
        a, sig, tau = self.a, self.sigma, s - t
        if self.kind == "CIR":
            gamma = math.sqrt(a * a + 2 * sig * sig)
            em1 = math.expm1(gamma * tau)
            den = (gamma + a) * em1 + 2 * gamma
            big_b = 2 * em1 / den
            ln_a = 2 * a * self.b / (sig * sig) * (
                math.log(2 * gamma / den) + (a + gamma) * tau / 2)
            return ln_a, big_b
        big_b = b_factor(a, tau)
        if self.kind == "VASICEK":
            u = a * tau
            if u < _SERIES_BELOW:
                # ln A = b (B - tau) - sigma^2/(2 a^2) (B - tau + a B^2 / 2); the second bracket
                # is a^2 tau^3 Q(u).
                ln_a = self.b * _b_minus_tau(a, tau) - sig * sig * tau ** 3 * _q_series(u) / 2
            else:
                ln_a = ((big_b - tau) * (a * a * self.b - sig * sig / 2) / (a * a)
                        - sig * sig * big_b * big_b / (4 * a))
            return ln_a, big_b
        curve = self.curve
        assert curve is not None
        ln_a = (math.log(curve.discount(s) / curve.discount(t)) + big_b * curve.forward(t)
                + sig * sig / (4 * a) * math.expm1(-2 * a * t) * big_b * big_b)
        return ln_a, big_b

    def bond(self, t: float, s: float, r: float) -> float:
        ln_a, big_b = self.ab(t, s)
        return math.exp(ln_a - big_b * r)

    def p0(self, t: float) -> float:
        """The model's bond price today, `P(0, t)`."""
        if self.curve is not None:
            return self.curve.discount(t)
        return 1.0 if t <= 0 else self.bond(0.0, t, self.r0)

    def option(self, call: bool, strike: float, expiry: float, maturity: float) -> float:
        """Bond option per unit face at `expiry` on the bond to `maturity`."""
        pt, ps = self.p0(expiry), self.p0(maturity)
        if self.kind == "CIR":
            c = self._cir_call(strike, expiry, maturity, pt, ps)
        else:
            sp = gaussian_sigma_p(self.a, self.sigma, expiry, maturity)
            c = gaussian_call(ps, pt, strike, sp)
        return c if call else c - ps + strike * pt

    def _cir_call(self, k: float, t: float, s: float, pt: float, ps: float) -> float:
        a, sig, r = self.a, self.sigma, self.r0
        gamma = math.sqrt(a * a + 2 * sig * sig)
        rho = 2 * gamma / (sig * sig * math.expm1(gamma * t))
        psi = (a + gamma) / (sig * sig)
        ln_a, big_b = self.ab(t, s)
        rbar = (ln_a - math.log(k)) / big_b
        dof = 4 * a * self.b / (sig * sig)
        egt = math.exp(gamma * t)
        x1, x2 = rho + psi + big_b, rho + psi
        return (ps * ncx2_cdf(2 * rbar * x1, dof, 2 * rho * rho * r * egt / x1)
                - k * pt * ncx2_cdf(2 * rbar * x2, dof, 2 * rho * rho * r * egt / x2))


def gaussian_sigma_p(a: float, sigma: float, expiry: float, maturity: float) -> float:
    """Bond-option volatility of Vasicek and Hull-White."""
    return sigma * b_factor(a, maturity - expiry) * math.sqrt(-math.expm1(-2 * a * expiry) / (2 * a))


def gaussian_call(ps: float, pt: float, k: float, sp: float) -> float:
    h = math.log(ps / (k * pt)) / sp + sp / 2
    return ps * big_n(h) - k * pt * big_n(h - sp)


def make_model(kind: str, a: float, sigma: float, b: float | None, curve: Curve | None,
               r0: float | None) -> Model:
    """Checks model, `a`, `sigma`, the CIR rules and the curve, in the spec order (curve already
    built by `make_curve`, so its rules ran when the caller made it)."""
    if kind not in MODELS:
        raise _input(f"{kind} is not a short-rate model", "model")
    _positive(mean_reversion=a, sigma=sigma)
    if kind == "CIR":
        if b is None or not b > 0:
            raise _domain("CIR needs long_term_mean above 0", "long_term_mean")
        if r0 is not None and r0 < 0:
            raise _domain("CIR needs short_rate >= 0", "short_rate")
    return Model(kind, a, sigma, b or 0.0, curve, r0 or 0.0)


def build_model(kind: str, a: float, sigma: float, b: float | None, times: Floats | None,
                discount_factors: Floats | None, r0: float | None,
                rate_given_to_hull_white: bool = False) -> Model:
    """The model of a case, checked in the spec order: model, `a` and `sigma`, the CIR rules, the
    curve, then the G-5 rule (`short_rate` given to a Hull-White option is E_INPUT)."""
    if kind not in MODELS:
        raise _input(f"{kind} is not a short-rate model", "model")
    _positive(mean_reversion=a, sigma=sigma)
    curve = None
    if kind == "HULL_WHITE":
        curve = make_curve(times or (), discount_factors or ())
        if rate_given_to_hull_white:
            raise _input("short_rate is not an input of this Hull-White operation", "short_rate")
    return make_model(kind, a, sigma, b, curve, r0)


def curve_model(times: Floats, discount_factors: Floats, a: float, sigma: float,
                rate_given: bool = False) -> Model:
    """A Hull-White model of the operations that take only a curve."""
    return build_model("HULL_WHITE", a, sigma, None, times, discount_factors, None, rate_given)


# --- noncentral chi-square --------------------------------------------------------------------


def _log1pmx(d: float) -> float:
    """`ln(1 + d) - d` without cancellation for small `d`."""
    if abs(d) > 0.25:
        return math.log1p(d) - d
    total, power = 0.0, d * d
    for n in range(2, 60):
        term = power / n
        total += -term if n % 2 == 0 else term
        if abs(term) < 1e-18 * abs(total):
            break
        power *= d
    return total


def _stirling_tail(s: float) -> float:
    """`lnGamma(s) - ((s - 1/2) ln s - s + ln(2 pi)/2)` for `s >= 10`."""
    inv = 1.0 / s
    inv2 = inv * inv
    return inv * (1 / 12 - inv2 * (1 / 360 - inv2 * (1 / 1260 - inv2 * (1 / 1680
                                                                           - inv2 / 1188))))


def _log_front(s: float, x: float) -> float:
    """`s ln x - x - lnGamma(s)`, the log prefactor of the incomplete gamma. For large `s` the
    three terms are each of order `s` and cancel, so the form `s (ln(1 + d) - d) + ln(s)/2 -
    ln(2 pi)/2 - stirling_tail(s)`, `d = (x - s)/s`, keeps its digits (G-32)."""
    if s < 10:
        return s * math.log(x) - x - math.lgamma(s)
    return (s * _log1pmx((x - s) / s) + 0.5 * math.log(s / (2 * math.pi)) - _stirling_tail(s))


def _log_poisson(j: int, mu: float) -> float:
    """`j ln mu - mu - lnGamma(j + 1)`."""
    if j == 0:
        return -mu
    return _log_front(j, mu) - math.log(j)


def _gamma_p(s: float, x: float) -> float:
    """Regularised lower incomplete gamma `P(s, x)`: series below `s + 1`, continued fraction
    (modified Lentz) above."""
    if x <= 0:
        return 0.0
    log_front = _log_front(s, x)
    if x < s + 1:
        term = total = 1.0 / s
        k = s
        for _ in range(100_000):
            k += 1
            term *= x / k
            total += term
            if abs(term) < abs(total) * 1e-17:
                break
        return total * math.exp(log_front)
    tiny = 1e-300
    bb = x + 1 - s
    c, d = 1 / tiny, 1 / bb
    h = d
    for i in range(1, 100_000):
        an = -i * (i - s)
        bb += 2
        d = an * d + bb
        d = tiny if abs(d) < tiny else d
        c = bb + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-17:
            break
    return 1.0 - math.exp(log_front) * h


def ncx2_cdf(x: float, k: float, lam: float) -> float:
    """Noncentral chi-square CDF by the Poisson-weighted series of central CDFs, summed from the
    Poisson mode outward with log weights (G-32), so `exp(-lambda/2)` never underflows alone. A
    non-positive argument gives 0."""
    if x <= 0:
        return 0.0
    half = lam / 2
    if half <= 0:
        return _gamma_p(k / 2, x / 2)
    j0 = math.floor(half)

    def term(j: int) -> float:
        return math.exp(_log_poisson(j, half)) * _gamma_p(k / 2 + j, x / 2)

    total = term(j0)
    j = j0 + 1
    while True:  # upward: weights fall past the mode
        t = term(j)
        total += t
        if t <= 1e-17 * total and (total > 0 or j > half + 10):
            break
        j += 1
    j = j0 - 1
    while j >= 0:  # downward
        t = term(j)
        total += t
        if t <= 1e-17 * total and total > 0:
            break
        j -= 1
    return total


# --- bonds and bond options ---------------------------------------------------------------------


def zcb(model: Model, r: float, t: float, maturity: float) -> dict[str, float]:
    """`rates.shortrate.zcb`: `P(t, T)` given the short rate at `t`, and its zero rate."""
    if t < 0:
        raise _domain("t_years must be >= 0", "t_years")
    if not maturity > t:
        raise _domain("maturity_years must be above t_years", "maturity_years")
    ln_a, big_b = model.ab(t, maturity)
    ln_p = ln_a - big_b * r
    return {"discount_factor": math.exp(ln_p), "zero_rate": -ln_p / (maturity - t)}


def _option_dates(strike: float, expiry: float, maturity: float) -> None:
    if not expiry > 0:
        raise _domain("expiry_years must be above 0", "expiry_years")
    if not maturity > expiry:
        raise _domain("maturity_years must be above expiry_years", "maturity_years")
    if not strike > 0:
        raise _domain("strike must be above 0", "strike")


def _option_type(option_type: str) -> bool:
    if option_type not in ("CALL", "PUT"):
        raise _input(f"{option_type} is not an option type", "option_type")
    return option_type == "CALL"


def zcb_option(model: Model, option_type: str, strike: float, expiry: float, maturity: float,
               notional: float) -> dict[str, float]:
    """`rates.shortrate.zcb_option`: European option on a zero-coupon bond."""
    _option_dates(strike, expiry, maturity)
    call = _option_type(option_type)
    return {"price": notional * model.option(call, strike, expiry, maturity),
            "bond_price_expiry": model.p0(expiry), "bond_price_maturity": model.p0(maturity)}


# --- Jamshidian swaption ------------------------------------------------------------------------


def _swap_times(expiry: float, payment_times: Floats) -> None:
    if not expiry > 0:
        raise _domain("expiry_years must be above 0", "expiry_years")
    if not payment_times or not _increasing(payment_times) or not payment_times[0] > expiry:
        raise _input("payment_times must be strictly increasing and start after expiry",
                     "payment_times")


def _swaption_type(kind: str) -> bool:
    if kind not in ("PAYER", "RECEIVER"):
        raise _input(f"{kind} is not a swaption type", "swaption_type")
    return kind == "PAYER"


def _critical_rate(model: Model, t0: float, times: Floats, coupons: Floats) -> float:
    """`r*` with `sum c_i P(T0, Ti; r*) = 1` (G-13, G-29): Newton from 0 kept inside the bracket
    `[-1, 1]`, solved until the sum is within 1e-15 relative of 1. With a negative strike the
    sum need not be monotone, so a bracket without a sign change is E_DOMAIN."""
    factors = [model.ab(t0, t) for t in times]

    def g(r: float) -> tuple[float, float]:
        terms = [c * math.exp(la - bb * r) for c, (la, bb) in zip(coupons, factors, strict=True)]
        return (ordered_sum(terms) - 1.0,
                -ordered_sum(term * bb for term, (_, bb) in zip(terms, factors, strict=True)))

    lo, hi = -1.0, 1.0
    if not (g(lo)[0] > 0 > g(hi)[0]):
        raise _domain("no critical rate in [-1, 1]", "fixed_rate")
    r = 0.0
    for _ in range(500):
        f, df = g(r)
        if abs(f) <= 1e-15:
            return r
        if f > 0:
            lo = r
        else:
            hi = r
        step = r - f / df if df != 0 else math.nan
        if not lo < step < hi:
            step = (lo + hi) / 2
        if step == r:
            return r
        r = step
    return r


def _jamshidian(model: Model, payer: bool, t0: float, times: Floats, k: float,
                notional: float) -> float:
    taus = [times[0] - t0, *(b - a for a, b in itertools.pairwise(times))]
    coupons = [k * tau for tau in taus]
    coupons[-1] += 1.0
    r_star = _critical_rate(model, t0, times, coupons)
    legs = [c * model.option(not payer, model.bond(t0, t, r_star), t0, t)
            for c, t in zip(coupons, times, strict=True)]
    return notional * ordered_sum(legs)


def swaption(model: Model, expiry: float, payment_times: Floats, fixed_rate: float,
             swaption_type: str, notional: float) -> dict[str, float]:
    """`rates.shortrate.swaption`: European swaption by Jamshidian's decomposition."""
    _swap_times(expiry, payment_times)
    payer = _swaption_type(swaption_type)
    if not 1 + fixed_rate * (payment_times[-1] - (payment_times[-2] if len(payment_times) > 1
                                                  else expiry)) > 0:
        raise _domain("1 + K tau_n must be above 0", "fixed_rate")
    if model.kind == "CIR":
        taus = [payment_times[0] - expiry,
                *(b - a for a, b in itertools.pairwise(payment_times))]
        at_zero = ordered_sum(fixed_rate * tau * model.bond(expiry, t, 0.0)
                              for tau, t in zip(taus, payment_times, strict=True))
        if at_zero + model.bond(expiry, payment_times[-1], 0.0) < 1.0:
            raise _domain("CIR has no non-negative critical rate", "fixed_rate")
    taus = [payment_times[0] - expiry,
            *(b - a for a, b in itertools.pairwise(payment_times))]
    level = ordered_sum(tau * model.p0(t) for tau, t in zip(taus, payment_times, strict=True))
    forward = (model.p0(expiry) - model.p0(payment_times[-1])) / level
    price = _jamshidian(model, payer, expiry, payment_times, fixed_rate, notional)
    return {"price": price, "forward_swap_rate": forward, "annuity": notional * level}


# --- caps and floors ----------------------------------------------------------------------------


def capfloor(model: Model, period_times: Floats, strike: float, cap_floor: str,
             notional: float) -> dict[str, float | list[float]]:
    """`rates.shortrate.capfloor`: caplets as bond puts, floorlets as bond calls (G-19)."""
    if len(period_times) < 2 or not _increasing(period_times):
        raise _input("period_times needs at least two strictly increasing times", "period_times")
    if not period_times[0] > 0:
        raise _domain("the first period time must be above 0", "period_times")
    taus = [b - a for a, b in itertools.pairwise(period_times)]
    if any(not 1 + strike * tau > 0 for tau in taus):
        raise _domain("1 + K tau must be above 0 in every period", "strike")
    if cap_floor not in ("CAP", "FLOOR"):
        raise _input(f"{cap_floor} is not CAP or FLOOR", "cap_floor")
    call = cap_floor == "FLOOR"
    lets = [notional * (1 + strike * tau)
            * model.option(call, 1 / (1 + strike * tau), start, end)
            for tau, start, end in zip(taus, period_times, period_times[1:], strict=False)]
    return {"price": ordered_sum(lets), "caplet_prices": lets}


# --- Hull-White calibration ---------------------------------------------------------------------


@dataclass(frozen=True)
class Quote:
    """One swaption of a calibration strip, priced per unit notional."""

    expiry: float
    payment_times: tuple[float, ...]
    fixed_rate: float
    payer: bool
    target: float


def make_quote(expiry: float, payment_times: Floats, fixed_rate: float, swaption_type: str,
               target: float) -> Quote:
    _swap_times(expiry, payment_times)
    payer = _swaption_type(swaption_type)
    if not target >= 0:
        raise _domain("target_price must be >= 0", "target_price")
    return Quote(expiry, tuple(payment_times), fixed_rate, payer, target)


RawQuote = tuple[float, Sequence[float], float, str, float]


def hw_calibrate(times: Floats, discount_factors: Floats, a: float,
                 strip: Sequence[RawQuote]) -> dict[str, float | list[float]]:
    """`rates.shortrate.hw_calibrate`: least-squares `sigma` on `[1e-4, 1]` with `a` fixed (G-17).
    A log scan brackets the minimum; bisection on `F'` then runs to a relative width of 1e-13."""
    _positive(mean_reversion=a)
    curve = make_curve(times, discount_factors)
    if not strip:
        raise _input("swaptions needs at least one swaption", "swaptions")
    quotes = [make_quote(*q) for q in strip]

    def prices(sigma: float) -> list[float]:
        m = Model("HULL_WHITE", a, sigma, curve=curve)
        return [_jamshidian(m, q.payer, q.expiry, q.payment_times, q.fixed_rate, 1.0)
                for q in quotes]

    def objective(sigma: float) -> float:
        return ordered_sum((p - q.target) ** 2 for p, q in zip(prices(sigma), quotes, strict=True))

    def slope(sigma: float) -> float:
        # F' = 2 sum (m_i - t_i) m_i', with m_i' by Richardson-extrapolated central differences.
        h = 1e-4 * sigma
        up, dn = prices(sigma + h), prices(sigma - h)
        up2, dn2 = prices(sigma + h / 2), prices(sigma - h / 2)
        base = prices(sigma)
        total = 0.0
        for k, q in enumerate(quotes):
            d1 = (up[k] - dn[k]) / (2 * h)
            d2 = (up2[k] - dn2[k]) / h
            total += (base[k] - q.target) * (4 * d2 - d1) / 3
        return 2 * total

    lo_end, hi_end, count = 1e-4, 1.0, 161
    grid = [lo_end * (hi_end / lo_end) ** (j / (count - 1)) for j in range(count)]
    grid[-1] = hi_end
    def scanned(sigma: float) -> float:
        # Far from the minimum a large sigma can overflow the bond formula; that point is then
        # simply not the minimum.
        try:
            return objective(sigma)
        except (OverflowError, ZeroDivisionError, ValueError, QfError):
            return math.inf

    values = [scanned(s) for s in grid]
    best = min(range(count), key=values.__getitem__)
    # An interior minimum must be clearly below both ends (a flat objective near an end is the
    # end's minimum in rounding noise) and must bracket a sign change of F'.
    ends = min(values[0], values[-1])
    if best in (0, count - 1) or not values[best] < ends - 1e-12 * abs(ends):
        raise QfError("E_NO_CONVERGENCE", "the minimum is at an end of [1e-4, 1]", "sigma")
    lo, hi = grid[best - 1], grid[best + 1]
    g_lo = slope(lo)
    if not (g_lo < 0 < slope(hi)):
        raise QfError("E_NO_CONVERGENCE", "no interior minimum of the objective", "sigma")
    for _ in range(200):
        mid = (lo + hi) / 2
        if hi - lo <= 1e-13 * mid:
            break
        g_mid = slope(mid)
        if g_mid == 0:
            lo = hi = mid
            break
        if (g_mid < 0) == (g_lo < 0):
            lo, g_lo = mid, g_mid
        else:
            hi = mid
    sigma = (lo + hi) / 2
    fitted = prices(sigma)
    rss = ordered_sum((p - q.target) ** 2 for p, q in zip(fitted, quotes, strict=True))
    return {"sigma": sigma, "fitted_prices": fitted, "rmse": math.sqrt(rss / len(quotes))}


# --- the pinned Bermudan scheme (G-18) ----------------------------------------------------------


@dataclass(frozen=True)
class Grid:
    nx: int
    steps_per_year: int
    width: float


def make_grid(nx: int, steps_per_year: int, width: float) -> Grid:
    if nx < 5 or nx % 2 == 0:
        raise _input("nx must be odd and at least 5", "grid.nx")
    if steps_per_year < 1:
        raise _input("steps_per_year must be at least 1", "grid.steps_per_year")
    if not width > 0:
        raise _domain("width must be above 0", "grid.width")
    return Grid(nx, steps_per_year, width)


def _hw_alpha(model: Model, t: float) -> float:
    curve = model.curve
    assert curve is not None
    a, sig = model.a, model.sigma
    return curve.forward(t) + sig * sig / (2 * a * a) * math.expm1(-a * t) ** 2


def _backward(model: Model, grid: Grid, knots: Floats,
              start: list[float], at_knot: Callable[[int, float, list[float], list[float]], None]
              ) -> float:
    """Runs the G-18 scheme from `knots[-1]` to 0 and returns `V` at the centre node.

    `start` is `V` at the last knot. `at_knot(k, t, xs, v)` changes `v` in place on arrival at each
    knot `t = knots[k] > 0`, `k < len(knots) - 1`."""
    a, sig = model.a, model.sigma
    nx = grid.nx
    t_m = knots[-1]
    sx = sig * math.sqrt(-math.expm1(-2 * a * t_m) / (2 * a))
    h = grid.width * sx
    dx = 2 * h / (nx - 1)
    xs = [-h + i * dx for i in range(nx)]
    v = start
    diff = sig * sig / (2 * dx * dx)
    times = [0.0, *knots]
    for k in range(len(times) - 1, 0, -1):
        t_hi, t_lo = times[k], times[k - 1]
        n = max(1, math.ceil(grid.steps_per_year * (t_hi - t_lo)))
        dt = (t_hi - t_lo) / n
        for j in range(n - 1, -1, -1):
            t = t_lo + j * dt
            alpha = _hw_alpha(model, t)
            m = nx - 2
            lower = [0.0] * m
            diag = [0.0] * m
            upper = [0.0] * m
            for p in range(m):
                x = xs[p + 1]
                conv = a * x / (2 * dx)
                lower[p] = -dt * (diff + conv)
                diag[p] = 1 + dt * (2 * diff + x + alpha)
                upper[p] = -dt * (diff - conv)
            # Linear extrapolation at both ends, substituted into the first and last rows.
            diag[0] += 2 * lower[0]
            upper[0] -= lower[0]
            lower[-1] -= upper[-1]
            diag[-1] += 2 * upper[-1]
            inner = _thomas(lower, diag, upper, v[1:-1])
            v = [2 * inner[0] - inner[1], *inner, 2 * inner[-1] - inner[-2]]
        if k - 1 > 0:
            at_knot(k - 2, t_lo, xs, v)
    return v[nx // 2]


def _thomas(lower: list[float], diag: list[float], upper: list[float],
            rhs: list[float]) -> list[float]:
    n = len(diag)
    c = [0.0] * n
    d = [0.0] * n
    c[0] = upper[0] / diag[0]
    d[0] = rhs[0] / diag[0]
    for i in range(1, n):
        den = diag[i] - lower[i] * c[i - 1]
        c[i] = upper[i] / den
        d[i] = (rhs[i] - lower[i] * d[i - 1]) / den
    x = [0.0] * n
    x[-1] = d[-1]
    for i in range(n - 2, -1, -1):
        x[i] = d[i] - c[i] * x[i + 1]
    return x


def _exercise_values(model: Model, t: float, xs: Floats, times: Floats, k: float,
                     phi: float) -> list[float]:
    """Per unit notional, `phi (1 - P(t, Tn) - K sum tau_j P(t, Tj))` over the payments after `t`."""
    after = [s for s in times if s > t]
    taus = [after[0] - t, *(b - a for a, b in itertools.pairwise(after))]
    factors = [model.ab(t, s) for s in after]
    alpha = _hw_alpha(model, t)
    out = []
    for x in xs:
        r = x + alpha
        bonds = [math.exp(la - bb * r) for la, bb in factors]
        fixed = ordered_sum(tau * p for tau, p in zip(taus, bonds, strict=True))
        out.append(phi * (1 - bonds[-1] - k * fixed))
    return out


def check_bermudan(start: float, payment_times: Floats, swaption_type: str,
                   exercise_times: Floats) -> bool:
    """The swap and exercise checks of the Bermudan operations; True for a payer."""
    _swap_times(start, payment_times)
    payer = _swaption_type(swaption_type)
    resets = {start, *payment_times[:-1]}
    if (not exercise_times or not _increasing(exercise_times)
            or any(t not in resets for t in exercise_times)):
        raise _input("exercise_times must be strictly increasing reset dates before the last "
                     "payment", "exercise_times")
    return payer


def bermudan_swaption(model: Model, start: float, payment_times: Floats, fixed_rate: float,
                      swaption_type: str, notional: float, exercise_times: Floats,
                      grid: Grid) -> dict[str, float]:
    """`rates.shortrate.bermudan_swaption` on the pinned reference scheme (G-18)."""
    payer = check_bermudan(start, payment_times, swaption_type, exercise_times)
    phi = 1.0 if payer else -1.0
    knots = list(exercise_times)
    nx = grid.nx
    t_m = knots[-1]
    sx = model.sigma * math.sqrt(-math.expm1(-2 * model.a * t_m) / (2 * model.a))
    h = grid.width * sx
    dx = 2 * h / (nx - 1)
    xs = [-h + i * dx for i in range(nx)]
    last = _exercise_values(model, t_m, xs, payment_times, fixed_rate, phi)
    v0 = [max(e, 0.0) for e in last]

    def exercise(k: int, t: float, grid_x: list[float], v: list[float]) -> None:
        ex = _exercise_values(model, t, grid_x, payment_times, fixed_rate, phi)
        for i, e in enumerate(ex):
            v[i] = max(v[i], e)

    return {"price": notional * _backward(model, grid, knots, v0, exercise)}


def callable_bond(model: Model, payment_times: Floats, coupon_rate: float, notional: float,
                  call_times: Floats, call_price: float, grid: Grid) -> dict[str, float]:
    """`rates.shortrate.callable_bond`: issuer-callable bond on the G-18 scheme (G-21)."""
    if not payment_times or not _increasing(payment_times) or not payment_times[0] > 0:
        raise _input("payment_times must be strictly increasing and start above 0",
                     "payment_times")
    earlier = set(payment_times[:-1])
    if not _increasing(call_times) or any(t not in earlier for t in call_times):
        raise _input("call_times must be strictly increasing payment times before the last",
                     "call_times")
    if not call_price > 0:
        raise _domain("call_price must be above 0", "call_price")
    taus = [payment_times[0], *(b - a for a, b in itertools.pairwise(payment_times))]
    calls = set(call_times)
    v0 = [1 + coupon_rate * taus[-1]] * grid.nx

    def coupon(k: int, t: float, grid_x: list[float], v: list[float]) -> None:
        cap = t in calls
        for i in range(len(v)):
            if cap and v[i] > call_price:
                v[i] = call_price
            v[i] += coupon_rate * taus[k]

    return {"price": notional * _backward(model, grid, list(payment_times), v0, coupon)}


# --- closed-form swap exposure under Hull-White (G-16) ------------------------------------------


def swap_ee_hw(model: Model, start: float, payment_times: Floats, fixed_rate: float, side: str,
               notional: float, exposure_times: Floats, hazard_rate: float | None,
               recovery: float | None) -> dict[str, float | list[float]]:
    """`xva.exposure.swap_ee_hw`: discounted EE at reset dates and an optional bucketed CVA."""
    if side not in ("PAY", "RECEIVE"):
        raise _input(f"{side} is not PAY or RECEIVE", "side")
    if start < 0:
        raise _domain("start_years must be >= 0", "start_years")
    if not payment_times or not _increasing(payment_times) or not payment_times[0] > start:
        raise _input("payment_times must be strictly increasing and start after start_years",
                     "payment_times")
    if not exposure_times:
        raise _input("exposure_times needs at least one time", "exposure_times")
    if any(not t > 0 for t in exposure_times):
        raise _domain("exposure times must be above 0", "exposure_times")
    resets = {start, *payment_times[:-1]}
    if not _increasing(exposure_times) or any(t not in resets for t in exposure_times):
        raise _input("exposure_times must be strictly increasing reset dates before the last "
                     "payment", "exposure_times")
    if (hazard_rate is None) != (recovery is None):
        raise _input("hazard_rate and recovery go together", "hazard_rate")
    if hazard_rate is not None and recovery is not None:
        if not hazard_rate >= 0:
            raise _domain("hazard_rate must be >= 0", "hazard_rate")
        if not 0 <= recovery < 1:
            raise _domain("recovery must be in [0, 1)", "recovery")
    payer = side == "PAY"
    ee = [_jamshidian(model, payer, t, [s for s in payment_times if s > t], fixed_rate, notional)
          for t in exposure_times]
    out: dict[str, float | list[float]] = {"discounted_ee": ee}
    if hazard_rate is not None and recovery is not None:
        prev = 0.0
        buckets = []
        for t, e in zip(exposure_times, ee, strict=True):
            buckets.append(e * (math.exp(-hazard_rate * prev) - math.exp(-hazard_rate * t)))
            prev = t
        out["cva"] = (1 - recovery) * ordered_sum(buckets)
    return out


# --- G2++ ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class G2:
    curve: Curve
    a: float
    sigma: float
    b: float
    eta: float
    rho: float

    def v(self, tau: float) -> float:
        cross = 2 * self.rho * self.sigma * self.eta * _cross_term(self.a, self.b, tau)
        return (_gauss_variance(self.a, self.sigma, tau) + _gauss_variance(self.b, self.eta, tau)
                + cross)


def make_g2(curve: Curve, a: float, sigma: float, b: float, eta: float, rho: float) -> G2:
    _positive(a=a, sigma=sigma, b=b, eta=eta)
    if not -1 < rho < 1:
        raise _domain("rho must be strictly inside (-1, 1)", "rho")
    return G2(curve, a, sigma, b, eta, rho)


def no_states() -> None:
    """`rates.g2pp.zcb_option` starts both factors at 0, so `x` or `y` given is E_INPUT (G-14)."""
    raise _input("x and y are not inputs of rates.g2pp.zcb_option", "x")


def g2pp_zcb(model: G2, x: float, y: float, t: float, maturity: float) -> dict[str, float]:
    """`rates.g2pp.zcb`: `P(t, T)` given the factor states at `t`."""
    if t < 0:
        raise _domain("t_years must be >= 0", "t_years")
    if not maturity > t:
        raise _domain("maturity_years must be above t_years", "maturity_years")
    c = model.curve
    tau = maturity - t
    ln_p = (math.log(c.discount(maturity) / c.discount(t))
            + 0.5 * (model.v(tau) - model.v(maturity) + model.v(t))
            - b_factor(model.a, tau) * x - b_factor(model.b, tau) * y)
    return {"discount_factor": math.exp(ln_p), "zero_rate": -ln_p / tau}


def g2pp_zcb_option(model: G2, option_type: str, strike: float, expiry: float, maturity: float,
                    notional: float) -> dict[str, float]:
    """`rates.g2pp.zcb_option`: Gaussian bond option with the G2++ variance."""
    _option_dates(strike, expiry, maturity)
    call = _option_type(option_type)
    a, b, s, e, rho = model.a, model.b, model.sigma, model.eta, model.rho
    d = maturity - expiry
    ba, bb = b_factor(a, d), b_factor(b, d)
    var = (s * s / 2 * ba * ba * -math.expm1(-2 * a * expiry) / a
           + e * e / 2 * bb * bb * -math.expm1(-2 * b * expiry) / b
           + 2 * rho * s * e * ba * bb * -math.expm1(-(a + b) * expiry) / (a + b))
    pt, ps = model.curve.discount(expiry), model.curve.discount(maturity)
    c = gaussian_call(ps, pt, strike, math.sqrt(var))
    price = c if call else c - ps + strike * pt
    return {"price": notional * price, "bond_price_expiry": pt, "bond_price_maturity": ps}


guard(globals())
