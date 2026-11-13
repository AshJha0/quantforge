"""GARCH(1,1), variance swaps and a VIX-style index.

Specs: specifications/05-volatility/garch.md, variance-swaps.md, vix-index.md, with rulings E-B1 to
E-B7 in specifications/stage-e-rulings-b.md. Each function applies its checks in spec order.
"""
import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from . import black
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum

Floats = Sequence[float]
_LN_2PI = math.log(2 * math.pi)


def _input(message: str, field: str | None = None) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


# --- GARCH(1,1) -------------------------------------------------------------------------------

def _initial_variance(returns: Floats, initial: str | float) -> float:
    if isinstance(initial, str):
        value = ordered_sum(r * r for r in returns) / len(returns)
        if value <= 0:
            raise _domain("SAMPLE initial variance is zero", "initial_variance")
        return value
    if initial <= 0:
        raise _domain("initial_variance must be positive", "initial_variance")
    return initial


def _check_initial_text(initial: str | float) -> None:
    if isinstance(initial, str) and initial != "SAMPLE":
        raise _input("initial_variance must be SAMPLE or a number", "initial_variance")


def _check_weights(omega: float, alpha: float, beta: float) -> None:
    if omega <= 0:
        raise _domain("omega must be positive", "omega")
    if alpha < 0:
        raise _domain("alpha must not be negative", "alpha")
    if beta < 0:
        raise _domain("beta must not be negative", "beta")


def _recursion(returns: Floats, omega: float, alpha: float, beta: float,
               sigma2: float) -> tuple[float, list[float], float]:
    """(loglik, sigma2_1..sigma2_n, sigma2_{n+1}): every term from t = 1, with ln(2 pi)."""
    variances = []
    total = 0.0
    for r in returns:
        variances.append(sigma2)
        total += _LN_2PI + math.log(sigma2) + r * r / sigma2
        sigma2 = omega + alpha * r * r + beta * sigma2
    return -0.5 * total, variances, sigma2


def garch_loglik(returns: Floats, omega: float, alpha: float, beta: float,
                 initial: str | float) -> tuple[float, list[float], float]:
    if len(returns) < 2:
        raise _input("at least 2 returns are needed", "returns")
    _check_initial_text(initial)
    _check_weights(omega, alpha, beta)
    return _recursion(returns, omega, alpha, beta, _initial_variance(returns, initial))


def garch_forecast(omega: float, alpha: float, beta: float, next_variance: float, horizon: int,
                   periods_per_year: float) -> tuple[list[float], float, float, float]:
    if horizon < 1:
        raise _input("horizon must be at least 1", "horizon")
    if periods_per_year <= 0:
        raise _input("periods_per_year must be positive", "periods_per_year")
    _check_weights(omega, alpha, beta)
    if next_variance <= 0:
        raise _domain("next_variance must be positive", "next_variance")
    p = alpha + beta
    if p >= 1:
        raise _domain("alpha + beta must be below 1 for a long-run variance", "alpha")
    long_run = omega / (1 - p)
    variances = []
    weight = 1.0  # p^(h-1), with p^0 = 1 also when p = 0
    for _ in range(horizon):
        variances.append(long_run + weight * (next_variance - long_run))
        weight *= p
    total = ordered_sum(variances)
    return variances, total, math.sqrt(total * periods_per_year / horizon), long_run


def _nelder_mead(f: Callable[[list[float]], float], start: list[float], step: float,
                 iterations: int) -> tuple[list[float], float]:
    """Minimises f. Standard coefficients; only the end point is used."""
    n = len(start)
    simplex = [start] + [[x + (step if i == j else 0.0) for j, x in enumerate(start)]
                         for i in range(n)]
    values = [f(x) for x in simplex]
    for _ in range(iterations):
        order = sorted(range(n + 1), key=values.__getitem__)
        simplex, values = [simplex[i] for i in order], [values[i] for i in order]
        if abs(values[-1] - values[0]) <= 1e-14 * (1 + abs(values[0])):
            break
        centre = [sum(x[j] for x in simplex[:-1]) / n for j in range(n)]

        def toward(c: float, centre: list[float] = centre,
                   worst: list[float] = simplex[-1]) -> list[float]:
            return [m + c * (w - m) for m, w in zip(centre, worst, strict=True)]

        reflected = toward(-1.0)
        fr = f(reflected)
        if fr < values[0]:
            expanded = toward(-2.0)
            fe = f(expanded)
            simplex[-1], values[-1] = (expanded, fe) if fe < fr else (reflected, fr)
        elif fr < values[-2]:
            simplex[-1], values[-1] = reflected, fr
        else:
            contracted = toward(0.5 if fr >= values[-1] else -0.5)
            fc = f(contracted)
            if fc < min(fr, values[-1]):
                simplex[-1], values[-1] = contracted, fc
            else:
                best = simplex[0]
                simplex = [best] + [[b + 0.5 * (x - b) for b, x in zip(best, s, strict=True)]
                                    for s in simplex[1:]]
                values = [values[0]] + [f(x) for x in simplex[1:]]
    i = min(range(n + 1), key=values.__getitem__)
    return simplex[i], values[i]


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x)) if x >= 0 else math.exp(x) / (1 + math.exp(x))


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def garch_fit(returns: Floats, initial: str | float) -> float:
    """Maximum likelihood over omega > 0, alpha, beta >= 0, alpha + beta < 1, initial variance
    held fixed. Nelder-Mead from several starts on an unconstrained map, then the best point is
    polished with Nelder-Mead restarts. Returns the log-likelihood at the optimum."""
    if len(returns) < 30:
        raise _input("at least 30 returns are needed", "returns")
    _check_initial_text(initial)
    sigma2 = _initial_variance(returns, initial)
    sample = ordered_sum(r * r for r in returns) / len(returns)

    def params(x: list[float]) -> tuple[float, float, float]:
        persistence = _sigmoid(x[1])
        alpha = persistence * _sigmoid(x[2])
        return math.exp(x[0]), alpha, persistence - alpha

    def objective(x: list[float]) -> float:
        try:
            omega, alpha, beta = params(x)
            if not (omega > 0 and math.isfinite(omega)):
                return math.inf
            value = -_recursion(returns, omega, alpha, beta, sigma2)[0]
        except (OverflowError, ValueError, ZeroDivisionError):
            return math.inf
        return value if math.isfinite(value) else math.inf

    best: tuple[list[float], float] | None = None
    for p in (0.5, 0.9, 0.97):
        for share in (0.05, 0.15, 0.3):
            start = [math.log(sample * (1 - p)), _logit(p), _logit(share)]
            x, v = _nelder_mead(objective, start, 0.5, 2000)
            if best is None or v < best[1]:
                best = (x, v)
    assert best is not None
    x, v = best
    for step in (0.1, 0.01, 1e-3, 1e-4):
        x, v = _nelder_mead(objective, x, step, 4000)
    if not math.isfinite(v):
        raise QfError("E_NO_CONVERGENCE", "the GARCH fit found no finite likelihood")
    return -v


# --- Stage F (R8): Student-t, a mean, and the estimate with standard errors -------------------

DISTRIBUTIONS = ("NORMAL", "STUDENT_T")
NU_MAX = 500.0


def _digamma(x: float) -> float:
    """psi(x) for x > 0: recurrence up to 10, then the asymptotic series (about 1e-15)."""
    total = 0.0
    while x < 10:
        total -= 1 / x
        x += 1
    inv = 1 / (x * x)
    series = inv * (1 / 12 - inv * (1 / 120 - inv * (1 / 252 - inv * (1 / 240 - inv / 132))))
    return total + math.log(x) - 0.5 / x - series


def _t_constant(nu: float) -> float:
    return math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2) - 0.5 * math.log(math.pi * (nu - 2))


def _score(e: Floats, theta: Sequence[float], sigma2: float,
           student: bool) -> tuple[float, list[float]]:
    """(loglik, gradient) in (omega, alpha, beta[, nu]), by the recursion's derivatives."""
    omega, alpha, beta = theta[0], theta[1], theta[2]
    nu = theta[3] if student else 0.0
    c = _t_constant(nu) if student else 0.0
    dc = (0.5 * _digamma((nu + 1) / 2) - 0.5 * _digamma(nu / 2) - 0.5 / (nu - 2)
          if student else 0.0)
    s, ds = sigma2, [0.0, 0.0, 0.0]
    total, grad = 0.0, [0.0] * (4 if student else 3)
    for r in e:
        if student:
            u = r * r / ((nu - 2) * s)
            total += c - 0.5 * math.log(s) - (nu + 1) / 2 * math.log1p(u)
            dl_ds = -0.5 / s + (nu + 1) / 2 * u / (1 + u) / s
            grad[3] += dc - 0.5 * math.log1p(u) + (nu + 1) / 2 * u / (1 + u) / (nu - 2)
        else:
            total += -0.5 * (_LN_2PI + math.log(s) + r * r / s)
            dl_ds = -0.5 * (1 / s - r * r / (s * s))
        for k in range(3):
            grad[k] += dl_ds * ds[k]
        ds = [1 + beta * ds[0], r * r + beta * ds[1], s + beta * ds[2]]
        s = omega + alpha * r * r + beta * s
    return total, grad


def _check_distribution(distribution: str, nu: float | None) -> None:
    if distribution not in DISTRIBUTIONS:
        raise QfError("E_SCHEMA", "distribution is not listed", "distribution")
    if distribution == "STUDENT_T":
        if nu is None:
            raise _input("STUDENT_T needs degrees_of_freedom", "degrees_of_freedom")
        if nu <= 2:
            raise _domain("degrees_of_freedom must be above 2", "degrees_of_freedom")


def garch_loglik_t(returns: Floats, omega: float, alpha: float, beta: float,
                   initial: str | float, distribution: str, nu: float | None,
                   mean: float) -> tuple[float, list[float], float]:
    """vol.garch.loglik with the stage F options: the recursion on e_t = r_t - mean."""
    if len(returns) < 2:
        raise _input("at least 2 returns are needed", "returns")
    _check_initial_text(initial)
    _check_weights(omega, alpha, beta)
    _check_distribution(distribution, nu)
    e = [r - mean for r in returns]
    sigma2 = _initial_variance(e, initial)
    loglik, variances, nxt = _recursion(e, omega, alpha, beta, sigma2)
    if distribution == "STUDENT_T" and nu is not None:
        loglik = _score(e, [omega, alpha, beta, nu], sigma2, True)[0]
    return loglik, variances, nxt


def garch_estimate(returns: Floats, initial: str | float, distribution: str,
                   demean: bool) -> dict[str, object]:
    """Interior MLE, Newton-polished, with observed-information standard errors (F-11 to F-14)."""
    import numpy as np

    student = distribution == "STUDENT_T"
    if distribution not in DISTRIBUTIONS:
        raise QfError("E_SCHEMA", "distribution is not listed", "distribution")
    if len(returns) < (100 if student else 30):
        raise _input("too few returns", "returns")
    _check_initial_text(initial)
    mu = ordered_sum(returns) / len(returns) if demean else 0.0
    e = [r - mu for r in returns]
    sample = ordered_sum(r * r for r in e) / len(e)
    if not math.isfinite(sample):  # rulings R6-8.1, J-0b.2: the squares overflow binary64
        raise QfError("E_NON_FINITE", "the sample variance of the returns overflows", "returns")
    sigma2 = _initial_variance(e, initial)
    if sample <= 0:
        raise _domain("the returns are all zero", "returns")

    def params(x: Sequence[float]) -> list[float]:
        persistence = _sigmoid(x[1])
        alpha = persistence * _sigmoid(x[2])
        out = [math.exp(x[0]), alpha, persistence - alpha]
        if student:
            out.append(2 + (NU_MAX - 2) * _sigmoid(x[3]))
        return out

    def objective(x: list[float]) -> float:
        try:
            value = -_score(e, params(x), sigma2, student)[0]
        except (OverflowError, ValueError, ZeroDivisionError):
            return math.inf
        return value if math.isfinite(value) else math.inf

    best: tuple[list[float], float] | None = None
    for p in (0.5, 0.9, 0.97):
        for share in (0.05, 0.15, 0.3):
            start = [math.log(sample * (1 - p)), _logit(p), _logit(share)]
            if student:
                start.append(_logit((8 - 2) / (NU_MAX - 2)))
            x, v = _nelder_mead(objective, start, 0.5, 3000)
            if best is None or v < best[1]:
                best = (x, v)
    assert best is not None
    x, v = best
    for step in (0.1, 0.01, 1e-3):
        x, v = _nelder_mead(objective, x, step, 4000)
    theta = params(x)
    scale = [sample, 1.0, 1.0, 1.0]
    n = len(theta)

    def hessian(t: list[float]) -> Any:
        h = np.zeros((n, n))
        for j in range(n):
            step = 1e-5 * abs(t[j])
            up, down = list(t), list(t)
            up[j] += step
            down[j] -= step
            gu, gd = _score(e, up, sigma2, student)[1], _score(e, down, sigma2, student)[1]
            h[:, j] = [(a - b) / (2 * step) for a, b in zip(gu, gd, strict=True)]
        return 0.5 * (h + h.T)

    def interior(t: list[float]) -> bool:
        ok = t[0] > 1e-6 * sample and t[1] > 1e-6 and t[2] > 1e-6 and t[1] + t[2] < 1 - 1e-6
        return ok and (not student or 2 + 1e-6 < t[3] < NU_MAX * (1 - 1e-6))

    def fail() -> QfError:
        return QfError("E_NO_CONVERGENCE", "no interior maximum", "returns")

    try:
        for _ in range(60):
            if not interior(theta):
                raise fail()
            grad = np.array(_score(e, theta, sigma2, student)[1])
            step = np.linalg.solve(hessian(theta), grad).tolist()
            rel = max(abs(b) / max(abs(a), s)
                      for a, b, s in zip(theta, step, scale[:n], strict=True))
            theta = [a - b for a, b in zip(theta, step, strict=True)]
            if rel < 1e-12:
                break
        else:
            raise fail()
        h = hessian(theta)
    except (np.linalg.LinAlgError, OverflowError, ValueError, ZeroDivisionError):
        raise fail() from None
    if not interior(theta) or not bool(np.all(np.linalg.eigvalsh(h) < 0)):
        raise fail()
    errors = np.sqrt(np.diag(np.linalg.inv(-h))).tolist()
    keys = ["omega", "alpha", "beta", "degrees_of_freedom"]
    std = {k: (float(errors[j]) if j < n else None) for j, k in enumerate(keys)}
    return {"omega": theta[0], "alpha": theta[1], "beta": theta[2],
            "degrees_of_freedom": theta[3] if student else None, "mean": mu,
            "loglik": _score(e, theta, sigma2, student)[0], "std_errors": std,
            "persistence": theta[1] + theta[2]}


# --- Variance swaps ---------------------------------------------------------------------------

def _f(k: float, s0: float, t: float) -> float:
    return (2 / t) * ((k - s0) / s0 - math.log(k / s0))


def _weights(strikes: Floats, extra: float, s0: float, t: float) -> list[float]:
    """QuantLib's walk: w_j = s_j - s_{j-1}, s_j the slope from K_j to K_{j+1}, s_{-1} = 0."""
    ks = [*strikes, extra]
    weights, previous = [], 0.0
    for j in range(len(strikes)):
        slope = abs(_f(ks[j + 1], s0, t) - _f(ks[j], s0, t)) / abs(ks[j + 1] - ks[j])
        weights.append(slope - previous)
        previous = slope
    return weights


def varswap_fair_strike(
    as_of: date, maturity: date, spot: float, rate: float, dividend_yield: float,
    put_strikes: Floats, call_strikes: Floats, vols: Sequence[tuple[float, float]],
    extension_step: float, variance_strike: float, variance_notional: float,
) -> tuple[float, float, float]:
    if maturity <= as_of:
        raise _input("maturity must be after as_of", "maturity")
    for key, ks in (("put_strikes", put_strikes), ("call_strikes", call_strikes)):
        if not ks:
            raise _input(f"{key} is empty", key)
        if len(set(ks)) != len(ks):
            raise _input(f"{key} repeats a strike", key)
    if any(k > spot for k in put_strikes):
        raise _input("a put strike is above spot", "put_strikes")
    if any(k < spot for k in call_strikes):
        raise _input("a call strike is below spot", "call_strikes")
    listed = [k for k, _ in vols]
    if len(set(listed)) != len(listed) or set(listed) != set(put_strikes) | set(call_strikes):
        raise _input("vols must list each strike exactly once", "vols")
    if spot <= 0:
        raise _domain("spot must be positive", "spot")
    if any(v <= 0 for _, v in vols):
        raise _domain("a vol is not positive", "vols")
    if extension_step <= 0:
        raise _domain("extension_step must be positive", "extension_step")
    if min(put_strikes) - extension_step <= 0:
        raise _domain("the lowest put strike less the extension step is not positive",
                      "extension_step")
    t = (maturity - as_of).days / 365
    vol_of = dict(vols)
    puts = sorted(put_strikes, reverse=True)
    calls = sorted(call_strikes)

    def leg(ks: list[float], extra: float, kind: str) -> float:
        total = 0.0
        for k, w in zip(ks, _weights(ks, extra, spot, t), strict=True):
            option = black.Option(black.BLACK_SCHOLES, kind, k, t, spot, rate, dividend_yield)
            total += w * black.price(option, vol_of[k])
        return total

    strip = leg(calls, calls[-1] + extension_step, "CALL") + leg(
        puts, puts[-1] - extension_step, "PUT")
    discount = math.exp(-rate * t)
    forward = spot * math.exp((rate - dividend_yield) * t)
    fair = (2 / t) * ((rate - dividend_yield) * t - (forward / spot - 1)) + strip / discount
    if fair < 0:
        raise _domain("the replicated variance is negative", "vols")
    return fair, math.sqrt(fair), variance_notional * discount * (fair - variance_strike)


def varswap_realized(prices: Floats, periods_per_year: float, variance_strike: float,
                     variance_notional: float) -> tuple[float, float, float]:
    if len(prices) < 2:
        raise _input("at least 2 prices are needed", "prices")
    if any(p <= 0 for p in prices):
        raise _domain("a price is not positive", "prices")
    m = len(prices) - 1
    squares = ordered_sum(math.log(b / a) ** 2 for a, b in itertools.pairwise(prices))
    variance = periods_per_year / m * squares
    return variance, math.sqrt(variance), variance_notional * (variance - variance_strike)


# --- VIX --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Quote:
    strike: float
    call_bid: float | None  # None is a null quote (ruling F-15)
    call_ask: float | None
    put_bid: float | None
    put_ask: float | None

    @property
    def call(self) -> float:
        return (_q(self.call_bid) + _q(self.call_ask)) / 2

    @property
    def put(self) -> float:
        return (_q(self.put_bid) + _q(self.put_ask)) / 2

    @property
    def null_call(self) -> bool:
        return self.call_bid is None or self.call_ask is None

    @property
    def null_put(self) -> bool:
        return self.put_bid is None or self.put_ask is None


MINUTES_PER_YEAR = 525600
MINUTES_30D = 43200


def _q(value: float | None) -> float:
    if value is None:
        raise _input("a null quote is used", "strip")
    return value


def _side(quotes: Sequence[Quote], bid: Callable[[Quote], float | None]) -> list[Quote]:
    """Walks away from K0 (not included): bid 0 is skipped, a second consecutive 0 stops. A null
    series is removed before the walk starts (ruling F-15)."""
    used, zeros = [], 0
    for q in quotes:
        if bid(q) is None:
            continue
        if bid(q) == 0:
            zeros += 1
            if zeros == 2:
                break
            continue
        zeros = 0
        used.append(q)
    return used


def vix_term_variance(minutes: int, rate: float,
                      strip: Sequence[Quote]) -> tuple[float, float, float, list[float]]:
    if minutes < 1:
        raise _input("minutes_to_expiry must be at least 1", "minutes_to_expiry")
    strikes = [q.strike for q in strip]
    if len(strikes) < 3:
        raise _input("at least 3 strikes are needed", "strip")
    if len(set(strikes)) != len(strikes):
        raise _input("a strike is repeated", "strip")
    def crossed(b: float | None, a: float | None) -> bool:
        return b is not None and a is not None and b > a

    if any(crossed(q.call_bid, q.call_ask) or crossed(q.put_bid, q.put_ask) for q in strip):
        raise _input("a bid is above its ask", "strip")
    values = [v for q in strip for v in (q.call_bid, q.call_ask, q.put_bid, q.put_ask)
              if v is not None]
    if any(v < 0 for v in values):
        raise _domain("a quote is negative", "strip")
    t = minutes / MINUTES_PER_YEAR
    growth = math.exp(rate * t)
    ordered = sorted(strip, key=lambda q: q.strike)
    candidates = [q for q in ordered if not (q.null_call or q.null_put)]
    if not candidates:
        raise _input("no strike has both a call and a put quote", "strip")
    star = min(candidates, key=lambda q: abs(q.call - q.put))  # first, so lowest, on a tie
    forward = star.strike + growth * (star.call - star.put)
    below = [q for q in ordered if q.strike <= forward]
    if not below:
        raise _input("no strike is at or below the forward", "strip")
    k0 = below[-1]
    if k0.null_call or k0.null_put:
        raise _input("the K0 call or put has a null quote", "strip")
    i0 = ordered.index(k0)
    puts = _side(ordered[i0 - 1::-1] if i0 else [], lambda q: None if q.null_put else q.put_bid)
    calls = _side(ordered[i0 + 1:], lambda q: None if q.null_call else q.call_bid)
    if not puts or not calls:  # ruling E-B15, Cboe methodology 3(a)(iii)
        raise _input("no out-of-the-money put or no out-of-the-money call is selected", "strip")
    chosen = [(q.strike, q.put) for q in reversed(puts)]
    chosen.append((k0.strike, (k0.call + k0.put) / 2))
    chosen += [(q.strike, q.call) for q in calls]
    ks = [k for k, _ in chosen]
    total = 0.0
    for i, (k, price) in enumerate(chosen):
        if len(ks) == 1:
            gap = 0.0
        elif i == 0:
            gap = ks[1] - ks[0]
        elif i == len(ks) - 1:
            gap = ks[-1] - ks[-2]
        else:
            gap = (ks[i + 1] - ks[i - 1]) / 2
        total += gap / (k * k) * price
    variance = (2 / t) * growth * total - (1 / t) * (forward / k0.strike - 1) ** 2
    return forward, k0.strike, variance, ks


def vix_index(near: tuple[int, float, Sequence[Quote]],
              next_: tuple[int, float, Sequence[Quote]]) -> tuple[float, float, float]:
    n1, n2 = near[0], next_[0]
    if not (n1 < n2 and n1 <= MINUTES_30D <= n2):  # ruling E-B34: the bracket first
        raise _input("the terms must bracket 30 days with near before next", "near")
    v1 = vix_term_variance(*near)[2]
    v2 = vix_term_variance(*next_)[2]
    t1, t2 = n1 / MINUTES_PER_YEAR, n2 / MINUTES_PER_YEAR
    bracket = (t1 * v1 * (n2 - MINUTES_30D) / (n2 - n1)
               + t2 * v2 * (MINUTES_30D - n1) / (n2 - n1))
    if bracket < 0:
        raise _domain("the interpolated variance is negative", "near")
    return 100 * math.sqrt(bracket * MINUTES_PER_YEAR / MINUTES_30D), v1, v2


guard(globals())
