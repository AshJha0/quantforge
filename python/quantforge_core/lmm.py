"""LIBOR market model, closed-form layer: Black caplets on the integrated abcd variance and
Rebonato's frozen-weight swaption volatility, plus the terminal-measure simulation that the
caplet acceptance (ruling G-26) checks.

Specification: specifications/04-pricing/lmm.md; rulings G-22, G-25, G-26.
"""
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .black import big_n
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum
from .shortrate import Curve, make_curve

Floats = Sequence[float]
_NODES = 96  # Gauss-Legendre nodes: the integrand is entire, so this is exact to rounding


def _input(message: str, field: str) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str) -> QfError:
    return QfError("E_DOMAIN", message, field)


@dataclass(frozen=True)
class Abcd:
    """Instantaneous volatility `(a + b x) exp(-c x) + d` at time to fixing `x`."""

    a: float
    b: float
    c: float
    d: float

    def vol(self, x: float) -> float:
        return (self.a + self.b * x) * math.exp(-self.c * x) + self.d


def make_abcd(a: float, b: float, c: float, d: float) -> Abcd:
    if not c > 0:
        raise _domain("c must be above 0", "abcd.c")
    if not d >= 0:
        raise _domain("d must be >= 0", "abcd.d")
    if not a + d > 0:
        raise _domain("a + d must be above 0 (volatility at the fixing)", "abcd.a")
    return Abcd(a, b, c, d)


@lru_cache(maxsize=1)
def _legendre() -> tuple[tuple[float, ...], tuple[float, ...]]:
    x, w = np.polynomial.legendre.leggauss(_NODES)
    return tuple(float(v) for v in x), tuple(float(v) for v in w)


def covariance(v: Abcd, ti: float, tj: float, u: float) -> float:
    """`C(T_i, T_j; u) = integral_0^u sigma_Ti(t) sigma_Tj(t) dt` by Gauss-Legendre."""
    if u <= 0:
        return 0.0
    xs, ws = _legendre()
    half = u / 2
    return half * ordered_sum(w * v.vol(ti - (half * x + half)) * v.vol(tj - (half * x + half))
                              for x, w in zip(xs, ws, strict=True))


def black(forward: float, strike: float, stdev: float, call: bool) -> float:
    """Undiscounted Black value with total standard deviation `stdev`."""
    if stdev == 0:
        return max(forward - strike, 0.0) if call else max(strike - forward, 0.0)
    d1 = (math.log(forward / strike) + stdev * stdev / 2) / stdev
    d2 = d1 - stdev
    if call:
        return forward * big_n(d1) - strike * big_n(d2)
    return strike * big_n(-d2) - forward * big_n(-d1)


def _forwards(curve: Curve, times: Floats) -> list[float]:
    out = []
    for s, t in itertools.pairwise(times):
        f = (curve.discount(s) / curve.discount(t) - 1) / (t - s)
        if not f > 0:
            raise _domain("every forward rate must be above 0 (lognormal LMM)", "curve")
        out.append(f)
    return out


def capfloor(times: Floats, discount_factors: Floats, abcd: tuple[float, float, float, float],
             period_times: Floats, strike: float, cap_floor: str,
             notional: float) -> dict[str, float | list[float]]:
    """`rates.lmm.capfloor`: Black caplets on the abcd variance to each fixing date."""
    curve = make_curve(times, discount_factors)
    vol = make_abcd(*abcd)
    if len(period_times) < 2 or not all(a < b for a, b in itertools.pairwise(period_times)):
        raise _input("period_times needs at least two increasing times", "period_times")
    if not period_times[0] > 0:
        raise _domain("the first fixing must be after 0", "period_times")
    if not strike > 0:
        raise _domain("strike must be above 0 (lognormal LMM)", "strike")
    if cap_floor not in ("CAP", "FLOOR"):
        raise _input(f"{cap_floor} is not CAP or FLOOR", "cap_floor")
    fwds = _forwards(curve, period_times)
    lets, vols = [], []
    for f, (s, t) in zip(fwds, itertools.pairwise(period_times), strict=True):
        sd = math.sqrt(covariance(vol, s, s, s))
        vols.append(sd / math.sqrt(s))
        lets.append(notional * (t - s) * curve.discount(t) * black(f, strike, sd, cap_floor == "CAP"))
    return {"price": ordered_sum(lets), "caplet_prices": lets, "forward_rates": fwds,
            "black_vols": vols}


def swaption_rebonato(times: Floats, discount_factors: Floats,
                      abcd: tuple[float, float, float, float], beta: float, expiry: float,
                      payment_times: Floats, fixed_rate: float, side: str,
                      notional: float) -> dict[str, float]:
    """`rates.lmm.swaption_rebonato`: Black on Rebonato's frozen-weight swap-rate volatility."""
    curve = make_curve(times, discount_factors)
    vol = make_abcd(*abcd)
    if not beta >= 0:
        raise _domain("correlation_beta must be >= 0", "correlation_beta")
    if not expiry > 0:
        raise _domain("expiry_years must be above 0", "expiry_years")
    grid = [expiry, *payment_times]
    if not payment_times or not all(a < b for a, b in itertools.pairwise(grid)):
        raise _input("payment_times must be increasing and start after expiry", "payment_times")
    if not fixed_rate > 0:
        raise _domain("fixed_rate must be above 0 (lognormal LMM)", "fixed_rate")
    if side not in ("PAY", "RECEIVE"):
        raise _input(f"{side} is not PAY or RECEIVE", "side")
    fwds = _forwards(curve, grid)
    taus = [t - s for s, t in itertools.pairwise(grid)]
    level = ordered_sum(tau * curve.discount(t) for tau, t in zip(taus, payment_times, strict=True))
    w = [tau * curve.discount(t) / level for tau, t in zip(taus, payment_times, strict=True)]
    rate = ordered_sum(wi * fi for wi, fi in zip(w, fwds, strict=True))
    fix = grid[:-1]
    var = ordered_sum(
        w[i] * w[j] * fwds[i] * fwds[j] * math.exp(-beta * abs(fix[i] - fix[j]))
        * covariance(vol, fix[i], fix[j], expiry)
        for i in range(len(w)) for j in range(len(w))) / (rate * rate)
    sd = math.sqrt(var)
    price = notional * level * black(rate, fixed_rate, sd, side == "PAY")
    return {"price": price, "swap_rate": rate, "annuity": level, "black_vol": sd / math.sqrt(expiry)}


def simulate_caplets(curve: Curve, vol: Abcd, beta: float, grid: Floats, strike: float,
                     paths: int, steps_per_year: int, seed: int) -> list[tuple[float, float]]:
    """Terminal-measure LMM caplets (G-26): log-Euler, predictor-corrector drift, volatility at
    the step midpoint, fixings on step boundaries, Cholesky correlation. Returns, per caplet on
    `F_k` (fixing `grid[k]`, `k >= 1`), the price and its standard error per unit notional."""
    n = len(grid) - 1  # forwards F_0 .. F_(n-1), F_k on [grid[k], grid[k+1]]
    taus = np.array([grid[k + 1] - grid[k] for k in range(n)])
    f0 = np.array([(curve.discount(grid[k]) / curve.discount(grid[k + 1]) - 1) / taus[k]
                   for k in range(n)])
    fix = np.array(grid[:-1])
    rho = np.exp(-beta * np.abs(fix[:, None] - fix[None, :]))
    chol = np.linalg.cholesky(rho)
    rng = np.random.Generator(np.random.PCG64(seed))
    times = [0.0]
    for k in range(1, n):
        steps = max(1, math.ceil(steps_per_year * (grid[k] - grid[k - 1]) - 1e-12))
        times += [grid[k - 1] + (grid[k] - grid[k - 1]) * (j + 1) / steps for j in range(steps)]
    log_f = np.tile(np.log(f0), (paths, 1))
    snapshots: dict[int, np.ndarray] = {}
    for step in range(len(times) - 1):
        t0, t1 = times[step], times[step + 1]
        dt = t1 - t0
        mid = (t0 + t1) / 2
        alive = fix > t0 + 1e-14
        sig = np.array([vol.vol(fix[k] - mid) if alive[k] else 0.0 for k in range(n)])
        z = rng.standard_normal((paths, n)) @ chol.T

        def drift(lf: np.ndarray, sig: np.ndarray = sig) -> np.ndarray:
            f = np.exp(lf)
            x = taus * sig * f / (1 + taus * f)  # (paths, n)
            mu = np.zeros_like(f)
            for k in range(n):
                later = rho[k, k + 1:] @ x[:, k + 1:].T if k + 1 < n else 0.0
                mu[:, k] = -sig[k] * later
            return mu

        mu0 = drift(log_f)
        pred = log_f + (mu0 - sig * sig / 2) * dt + sig * math.sqrt(dt) * z
        mu1 = drift(pred)
        log_f = log_f + ((mu0 + mu1) / 2 - sig * sig / 2) * dt + sig * math.sqrt(dt) * z
        for k in range(1, n):
            if abs(t1 - grid[k]) < 1e-12:
                snapshots[k] = np.exp(log_f.copy())
    p_n = curve.discount(grid[-1])
    out = []
    for k in range(1, n):
        f_fix = snapshots[k][:, k]
        f_pay = snapshots[k + 1] if k + 1 < n else None
        growth = np.ones(paths)
        if f_pay is not None:
            for j in range(k + 1, n):
                growth *= 1 + taus[j] * f_pay[:, j]
        payoff = p_n * taus[k] * np.maximum(f_fix - strike, 0.0) * growth
        out.append((float(payoff.mean()), float(payoff.std(ddof=1) / math.sqrt(paths))))
    return out


guard(globals())
