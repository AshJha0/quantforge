"""SABR: Hagan expansion, density check, calibration, arbitrage-free recipe
(specifications/05-volatility/sabr.md)."""
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

lazy import numpy as np

from .black import BLACK_76, Option, _value, implied
from .errors import QfError
from .finite import guard
from .fitting import best_of
from .numeric import thomas

Floats = Sequence[float]


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


@dataclass(frozen=True)
class Sabr:
    forward: float
    expiry_years: float
    alpha: float
    beta: float
    rho: float
    nu: float
    shift: float = 0.0


def _check(p: Sabr, strikes: Floats) -> None:
    if not strikes:  # ruling C17: ahead of every E_DOMAIN
        raise QfError("E_INPUT", "strikes is empty", "strikes")
    if p.expiry_years <= 0:
        raise _domain("expiry_years must be above 0", "expiry_years")
    if p.alpha <= 0:
        raise _domain("alpha must be above 0", "alpha")
    if not 0 <= p.beta <= 1:
        raise _domain("beta must be in [0, 1]", "beta")
    if abs(p.rho) >= 1:
        raise _domain("|rho| must be below 1", "rho")
    if p.nu < 0:
        raise _domain("nu is negative", "nu")
    if p.forward + p.shift <= 0:
        raise _domain("the shifted forward must be above 0", "forward")
    if any(k + p.shift <= 0 for k in strikes):
        raise _domain("a shifted strike is not above 0", "strikes")


def _hagan(p: Sabr, strike: float) -> float:
    f, x = p.forward + p.shift, strike + p.shift
    alpha, beta, rho, nu, t = p.alpha, p.beta, p.rho, p.nu, p.expiry_years
    big_a = (f * x) ** (1 - beta)
    root_a = math.sqrt(big_a)
    big_l = math.log(f / x)
    c = (1 - beta) ** 2 * big_l * big_l
    z = (nu / alpha) * root_a * big_l
    if abs(z) < 1e-7:
        m = 1 - rho * z / 2 - (3 * rho * rho - 2) * z * z / 12
    else:
        chi = math.log((math.sqrt(1 - 2 * rho * z + z * z) + z - rho) / (1 - rho))
        m = z / chi
    den = root_a * (1 + c / 24 + c * c / 1920)
    h = 1 + t * (
        (1 - beta) ** 2 * alpha * alpha / (24 * big_a)
        + rho * beta * nu * alpha / (4 * root_a)
        + (2 - 3 * rho * rho) * nu * nu / 24
    )
    return float(alpha * m * h / den)


def hagan(p: Sabr, strikes: Floats) -> list[float]:
    _check(p, strikes)
    return [_hagan(p, k) for k in strikes]


def _call(p: Sabr, strike: float) -> float:
    o = Option(
        BLACK_76, "CALL", strike + p.shift, p.expiry_years, p.forward + p.shift
    )
    return _value(o, _hagan(p, strike))


def density(
    p: Sabr, strikes: Floats, h_strike: float, on_negative: str
) -> tuple[list[float], float, bool]:
    _check(p, strikes)
    if h_strike <= 0:
        raise _domain("h_strike must be above 0", "h_strike")
    if any(k + p.shift - h_strike <= 0 for k in strikes):
        raise _domain("a strike less h_strike is not above 0", "h_strike")
    h = h_strike
    values = [
        (_call(p, k + h) - 2 * _call(p, k) + _call(p, k - h)) / (h * h) for k in strikes
    ]
    low = min(values)
    negative = low < -1e-9
    if negative and on_negative == "REJECT":
        raise QfError("E_ARBITRAGE", "the Hagan density is negative", "strikes")
    return values, low, negative


def calibrate(
    forward: float, expiry_years: float, beta: float, shift: float, strikes: Floats, vols: Floats,
    weights: Floats | None,
) -> tuple[float, float, float, float]:
    if len(strikes) != len(vols) or (weights is not None and len(weights) != len(strikes)):
        raise QfError("E_INPUT", "lengths differ", "vols")
    if len(strikes) < 3:
        raise QfError("E_INPUT", "fewer than 3 strikes", "strikes")
    if any(a >= b for a, b in itertools.pairwise(strikes)):
        raise QfError("E_INPUT", "strikes must be strictly increasing", "strikes")
    if min(vols) <= 0:
        raise _domain("a vol is not above 0", "vols")
    if weights is not None and min(weights) <= 0:
        raise _domain("a weight is not above 0", "weights")
    _check(Sabr(forward, expiry_years, 1.0, beta, 0.0, 0.0, shift), strikes)
    target = np.array(vols)
    weight = np.ones_like(target) if weights is None else np.array(weights)
    root_weight = np.sqrt(weight)

    def model(x: np.ndarray) -> Sabr:
        return Sabr(
            forward, expiry_years, math.exp(x[0]), beta, math.tanh(x[1]), math.exp(x[2]), shift
        )

    def residual(x: np.ndarray) -> np.ndarray:
        p = model(x)
        return cast("np.ndarray", root_weight * (np.array([_hagan(p, k) for k in strikes]) - target))

    f = forward + shift
    nearest = min(range(len(strikes)), key=lambda i: abs(strikes[i] - forward))
    alpha = vols[nearest] * f ** (1 - beta)
    starts = [
        np.array((math.log(alpha * a), math.atanh(r), math.log(n)))
        for a in (1.0, 0.7) for r in (-0.6, -0.1, 0.4) for n in (0.1, 0.5, 1.5)
    ]
    best = best_of(residual, starts)
    if best is None:
        raise QfError("E_NO_CONVERGENCE", "the SABR fit found no start")
    p = model(best[0])
    return p.alpha, p.rho, p.nu, math.sqrt(best[1] / float(weight.sum()))


def arbfree(
    p: Sabr, cells: int, cells_below: int, steps: int, strikes: Floats
) -> dict[str, object]:
    _check(p, strikes)
    if p.beta >= 1:
        raise _domain("beta must be below 1", "beta")
    if cells_below < 1 or cells_below >= cells or steps < 1:
        raise QfError("E_INPUT", "cells_below or steps is out of range")
    alpha, beta, rho, nu = p.alpha, p.beta, p.rho, p.nu
    f0 = p.forward + p.shift
    h = f0 / (cells_below - 0.5)
    u_max = cells * h
    xs = [k + p.shift for k in strikes]
    if any(x >= u_max for x in xs):
        raise QfError("E_INPUT", "a strike is at or beyond the top of the grid", "strikes")

    u = (np.arange(1, cells + 1) - 0.5) * h
    z = (u ** (1 - beta) - f0 ** (1 - beta)) / (1 - beta)
    dsq = (alpha * alpha + 2 * rho * alpha * nu * z + nu * nu * z * z) * u ** (2 * beta)
    centre = cells_below - 1
    gap = u - f0
    gap[centre] = 1.0
    g = (u**beta - f0**beta) / gap
    g[centre] = beta * f0 ** (beta - 1) if beta > 0 else 0.0
    if beta == 0:
        g[:] = 0.0

    dt = p.expiry_years / steps
    lam = dt / (h * h)
    q = [0.0] * cells
    q[centre] = 1 / h
    p_left = p_right = 0.0
    for n in range(1, steps + 1):
        m = dsq * np.exp(rho * nu * alpha * g * (n * dt)) / 2
        lm = lam * m
        diag = 1 + 2 * lm
        diag[0] += lm[0]
        diag[-1] += lm[-1]
        lower = np.empty(cells)
        lower[1:] = -lm[:-1]
        lower[0] = 0.0
        upper = np.empty(cells)
        upper[:-1] = -lm[1:]
        upper[-1] = 0.0
        q = thomas(lower.tolist(), diag.tolist(), upper.tolist(), q)
        p_left += 2 * dt * float(m[0]) * q[0] / h
        p_right += 2 * dt * float(m[-1]) * q[-1] / h

    qa = np.array(q)
    calls: list[float] = []
    vols: list[float | None] = []
    for x in xs:
        c = math.floor(x / h) + 1  # 1-based cell holding x
        above = qa[c:]
        value = float(((u[c:] - x) * above).sum()) * h
        value += q[c - 1] * (c * h - x) ** 2 / 2 + (u_max - x) * p_right
        calls.append(value)
        if value <= max(f0 - x, 0.0) or value >= f0:
            vols.append(None)
        else:
            vols.append(implied(Option(BLACK_76, "CALL", x, p.expiry_years, f0), value))
    return {
        "call_prices": calls, "vols": vols, "mass": float(qa.sum()) * h + p_left + p_right,
        "mean": float((u * qa).sum()) * h + u_max * p_right, "absorbed": p_left,
        "min_density": float(qa.min()),
    }


guard(globals())
