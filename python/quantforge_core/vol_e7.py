"""Stage E, E7: GARCH(1,1), variance swaps and a VIX-style index.

Specs: specifications/05-volatility/garch.md, variance-swaps.md, vix-index.md, with rulings E-B1 to
E-B7 in specifications/stage-e-rulings-b.md. Each function applies its checks in spec order.
"""
import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from . import black
from .errors import QfError
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
    call_bid: float
    call_ask: float
    put_bid: float
    put_ask: float

    @property
    def call(self) -> float:
        return (self.call_bid + self.call_ask) / 2

    @property
    def put(self) -> float:
        return (self.put_bid + self.put_ask) / 2


MINUTES_PER_YEAR = 525600
MINUTES_30D = 43200


def _side(quotes: Sequence[Quote], bid: Callable[[Quote], float]) -> list[Quote]:
    """Walks away from K0 (not included): bid 0 is skipped, a second consecutive 0 stops."""
    used, zeros = [], 0
    for q in quotes:
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
    if any(q.call_bid > q.call_ask or q.put_bid > q.put_ask for q in strip):
        raise _input("a bid is above its ask", "strip")
    if any(min(q.call_bid, q.call_ask, q.put_bid, q.put_ask) < 0 for q in strip):
        raise _domain("a quote is negative", "strip")
    t = minutes / MINUTES_PER_YEAR
    growth = math.exp(rate * t)
    ordered = sorted(strip, key=lambda q: q.strike)
    star = min(ordered, key=lambda q: abs(q.call - q.put))  # first, so lowest, on a tie
    forward = star.strike + growth * (star.call - star.put)
    below = [q for q in ordered if q.strike <= forward]
    if not below:
        raise _input("no strike is at or below the forward", "strip")
    k0 = below[-1]
    i0 = ordered.index(k0)
    puts = _side(ordered[i0 - 1::-1] if i0 else [], lambda q: q.put_bid)
    calls = _side(ordered[i0 + 1:], lambda q: q.call_bid)
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
    v1 = vix_term_variance(*near)[2]
    v2 = vix_term_variance(*next_)[2]
    if not (n1 < n2 and n1 <= MINUTES_30D <= n2):
        raise _input("the terms must bracket 30 days with near before next", "near")
    t1, t2 = n1 / MINUTES_PER_YEAR, n2 / MINUTES_PER_YEAR
    bracket = (t1 * v1 * (n2 - MINUTES_30D) / (n2 - n1)
               + t2 * v2 * (MINUTES_30D - n1) / (n2 - n1))
    if bracket < 0:
        raise _domain("the interpolated variance is negative", "near")
    return 100 * math.sqrt(bracket * MINUTES_PER_YEAR / MINUTES_30D), v1, v2
