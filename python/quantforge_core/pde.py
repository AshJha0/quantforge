"""Finite-difference Black-Scholes (specifications/01-core/pde.md)."""
import math
from dataclasses import dataclass

from .errors import QfError


@dataclass(frozen=True)
class PdeResult:
    price: float
    delta: float
    gamma: float
    grid_h: float


def _cell_average(call: bool, x: float, h: float, strike: float, k: float) -> float:
    low, up = x - h / 2, x + h / 2
    if call:
        if up <= k:
            return 0.0
        edge = max(low, k)
        return (math.exp(up) - math.exp(edge) - strike * (up - edge)) / h
    if low >= k:
        return 0.0
    edge = min(up, k)
    return (strike * (edge - low) - math.exp(edge) + math.exp(low)) / h


def bs_european(
    option: str, spot: float, strike: float, r: float, q: float, sigma: float, t: float,
    space_steps: int, time_steps: int, width: float = 6.0, rannacher_steps: int = 2,
) -> PdeResult:
    big_j, big_m, big_r = space_steps, time_steps, rannacher_steps
    if spot <= 0 or strike <= 0 or sigma <= 0 or t <= 0 or width <= 0:
        raise QfError("E_DOMAIN", "spot, strike, sigma, t and width must be positive")
    if big_j % 2 or big_j < 20 or big_m < 2 or big_r < 0 or big_r >= big_m:
        raise QfError("E_INPUT", "need even J >= 20, M >= 2 and 0 <= R < M")

    call = option == "CALL"
    a = sigma * sigma / 2
    b = r - q - a
    h = 2 * width * sigma * math.sqrt(t) / big_j
    dt = t / big_m
    x0 = math.log(spot)
    half = big_j // 2
    xs = [x0 + (j - half) * h for j in range(big_j + 1)]
    k = math.log(strike)
    s_low, s_high = math.exp(xs[0]), math.exp(xs[big_j])

    def boundary(tau: float) -> tuple[float, float]:
        if call:
            return 0.0, s_high * math.exp(-q * tau) - strike * math.exp(-r * tau)
        return strike * math.exp(-r * tau) - s_low * math.exp(-q * tau), 0.0

    lo = a / (h * h) - b / (2 * h)
    ce = -2 * a / (h * h) - r
    up = a / (h * h) + b / (2 * h)
    v = [_cell_average(call, x, h, strike, k) for x in xs]
    interior = big_j - 1
    c_prime = [0.0] * interior
    d_prime = [0.0] * interior

    def step(tau: float, s: float, theta: float) -> None:
        v[0], v[big_j] = boundary(tau)
        new_low, new_high = boundary(tau + s)
        ex = (1 - theta) * s
        im = theta * s
        sub, dia, sup = -im * lo, 1 - im * ce, -im * up
        for i in range(interior):
            j = i + 1
            rhs = v[j] + ex * (lo * v[j - 1] + ce * v[j] + up * v[j + 1])
            if i == 0:
                rhs += im * lo * new_low
                c_prime[0] = sup / dia
                d_prime[0] = rhs / dia
            else:
                if i == interior - 1:
                    rhs += im * up * new_high
                den = dia - sub * c_prime[i - 1]
                c_prime[i] = sup / den
                d_prime[i] = (rhs - sub * d_prime[i - 1]) / den
        v[0], v[big_j] = new_low, new_high
        v[interior] = d_prime[interior - 1]
        for i in range(interior - 2, -1, -1):
            v[i + 1] = d_prime[i] - c_prime[i] * v[i + 2]

    for n in range(big_r):
        step(n * dt, dt / 2, 1.0)
        step(n * dt + dt / 2, dt / 2, 1.0)
    for n in range(big_r, big_m):
        step(n * dt, dt, 0.5)

    vx = (v[half + 1] - v[half - 1]) / (2 * h)
    vxx = (v[half + 1] - 2 * v[half] + v[half - 1]) / (h * h)
    return PdeResult(v[half], vx / spot, (vxx - vx) / (spot * spot), h)
