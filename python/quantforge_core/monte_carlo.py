"""Monte Carlo for a European option under GBM (specifications/01-core/monte-carlo.md)."""
import math
from collections.abc import Iterator, Sequence

from . import sobol
from .errors import QfError
from .numeric import ordered_sum
from .rng import Xoshiro256, ppnd16

METHODS = ("PLAIN", "ANTITHETIC", "CONTROL_VARIATE", "SOBOL")


def _draws(method: str, paths: int, steps: int, seed: int, stream: int) -> Iterator[list[float]]:
    if method == "SOBOL":
        for point in sobol.iter_points(steps, paths):
            yield [ppnd16(u) for u in point]
    else:
        g = Xoshiro256.seeded(seed, stream)
        for _ in range(paths):
            yield [g.normal() for _ in range(steps)]


def _mean_and_stderr(samples: Sequence[float]) -> tuple[float, float]:
    n = len(samples)
    mean = ordered_sum(samples) / n
    variance = ordered_sum((v - mean) * (v - mean) for v in samples) / (n - 1)
    return mean, math.sqrt(variance / n)


def gbm_european(
    option: str, spot: float, strike: float, r: float, q: float, sigma: float, t: float,
    paths: int, steps: int, seed: int, stream: int, method: str,
) -> tuple[float, float]:
    """Returns (price, stderr)."""
    if spot <= 0 or strike <= 0 or sigma <= 0 or t <= 0:
        raise QfError("E_DOMAIN", "spot, strike, sigma and t must be positive")
    if paths < 2 or paths > 10_000_000 or steps < 1:
        raise QfError("E_INPUT", "need 2 <= paths <= 10000000 and steps >= 1")
    if method == "SOBOL" and steps > sobol.MAX_DIMENSIONS:
        raise QfError("E_INPUT", "SOBOL allows at most 64 steps", "steps")

    dt = t / steps
    drift = (r - q - sigma * sigma / 2) * dt
    vol = sigma * math.sqrt(dt)
    log_spot = math.log(spot)
    discount = math.exp(-r * t)
    call = option == "CALL"

    def terminal(zs: Sequence[float], sign: float) -> float:
        log_s = log_spot
        for z in zs:
            log_s += drift + vol * (sign * z)
        return math.exp(log_s)

    def payoff(s_t: float) -> float:
        return discount * max(s_t - strike if call else strike - s_t, 0.0)

    samples: list[float] = []
    controls: list[float] = []
    for zs in _draws(method, paths, steps, seed, stream):
        s_t = terminal(zs, 1.0)
        if method == "ANTITHETIC":
            samples.append((payoff(s_t) + payoff(terminal(zs, -1.0))) / 2)
        else:
            samples.append(payoff(s_t))
            if method == "CONTROL_VARIATE":
                controls.append(discount * s_t)

    if method == "CONTROL_VARIATE":
        known = spot * math.exp(-q * t)
        mean_p = ordered_sum(samples) / paths
        mean_c = ordered_sum(controls) / paths
        cov = ordered_sum((p - mean_p) * (c - mean_c) for p, c in zip(samples, controls))
        var = ordered_sum((c - mean_c) * (c - mean_c) for c in controls)
        beta = cov / var
        samples = [p - beta * (c - known) for p, c in zip(samples, controls)]
    return _mean_and_stderr(samples)
