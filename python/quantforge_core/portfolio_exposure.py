"""Exposure profiles of a swap netting set under Hull-White, by exact one-factor integration
(stage G wave 4c, `xva.exposure.portfolio_hw`).

Specification: specifications/06-risk/xva-exposure-portfolio.md; rulings G-12, G-16, G-42.

In the LGM coordinates ORE simulates, `x(t) ~ N(0, zeta(t))` and the deflated value of the
netting set at a reset date `t` is a sum of exponentials `g(x) = sum_k a_k exp(-b_k x)`: one term
for the par floaters (`b = H(t)`) and one per fixed-leg bond (`b = H(T_j)`). Every Gaussian
expectation of `g` over an interval is then closed form,
`E[a e^(-b x) 1{l < x < u}] = a e^(b^2 zeta/2) (N((u + b zeta)/sqrt zeta) - N((l + b zeta)/sqrt
zeta))`, so EE, ENE and the PFE quantiles only need the zeros of `g` (or of `g - y`), found by a
dense scan and Brent refinement.
"""
import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from .black import big_n
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum
from .shortrate import Curve, curve_model

Floats = Sequence[float]
_SCAN = np.linspace(-12.0, 12.0, 6001)  # standard deviations of x(t), ruling R6-5.5


def _input(message: str, field: str) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str) -> QfError:
    return QfError("E_DOMAIN", message, field)


@dataclass(frozen=True)
class Swap:
    notional: float
    fixed_rate: float
    payer: bool
    start: float
    payments: tuple[float, ...]

    @property
    def grid(self) -> tuple[float, ...]:
        return (self.start, *self.payments)


def make_swap(notional: float, fixed_rate: float, side: str, start: float,
              payments: Floats) -> Swap:
    if side not in ("PAY", "RECEIVE"):
        raise _input(f"{side} is not PAY or RECEIVE", "side")
    if not start >= 0:
        raise _domain("start_years must be >= 0", "start_years")
    if not payments or not all(a < b for a, b in itertools.pairwise([start, *payments])):
        raise _input("payment_times must be increasing and start after start_years",
                     "payment_times")
    return Swap(notional, fixed_rate, side == "PAY", start, tuple(payments))


def _interval_mass(lo: float, hi: float) -> float:
    """`N(hi) - N(lo)` without cancellation in either tail."""
    if lo >= 0:
        return big_n(-lo) - big_n(-hi)
    return big_n(hi) - big_n(lo)


class _Profile:
    """`g(x) = sum a_k exp(-b_k x)` with `x ~ N(0, zeta)`."""

    def __init__(self, a: list[float], b: list[float], zeta: float):
        self.a = np.array(a, dtype=float)
        self.b = np.array(b, dtype=float)
        self.zeta = zeta
        self.sd = math.sqrt(zeta)

    def value(self, x: float, y: float = 0.0) -> float:
        return float(np.sum(self.a * np.exp(-self.b * x))) - y

    def slope(self, x: float) -> float:
        return float(-np.sum(self.a * self.b * np.exp(-self.b * x)))

    @staticmethod
    def _bisect(f: Callable[[float], float], lo: float, hi: float) -> float:
        """Bisection to adjacent doubles (at least 1e-14 relative); `f(lo)`, `f(hi)` differ in sign."""
        flo = f(lo)
        for _ in range(2000):
            mid = (lo + hi) / 2
            if mid in (lo, hi) or hi - lo <= 1e-14 * max(abs(lo), abs(hi)):
                break
            fm = f(mid)
            if fm == 0:
                return mid
            if (fm < 0) == (flo < 0):
                lo, flo = mid, fm
            else:
                hi = mid
        return (lo + hi) / 2

    def zeros(self, y: float = 0.0) -> list[float]:
        """Ruling R6-5.5: critical points of `g` bracketed from the analytic `g'` on 6,001
        points over +-12 sd and bisected; `g` is monotone between them, so each piece holds at
        most one root of `g - y`, found by bisection."""
        xs = _SCAN * self.sd
        d = (-(self.a * self.b)[:, None] * np.exp(-self.b[:, None] * xs[None, :])).sum(axis=0)
        cuts = [float(xs[0])]
        for i in range(len(xs) - 1):
            if d[i] == 0:
                cuts.append(float(xs[i]))
            elif d[i] * d[i + 1] < 0:
                cuts.append(self._bisect(self.slope, float(xs[i]), float(xs[i + 1])))
        cuts.append(float(xs[-1]))
        out: list[float] = []
        for lo, hi in itertools.pairwise(cuts):
            if lo >= hi:
                continue
            vlo, vhi = self.value(lo, y), self.value(hi, y)
            if vlo == 0:
                out.append(lo)
            elif vlo * vhi < 0:
                out.append(self._bisect(lambda x: self.value(x, y), lo, hi))
        if self.value(cuts[-1], y) == 0:
            out.append(cuts[-1])
        return sorted(set(out))
    def _intervals(self, y: float, positive: bool) -> list[tuple[float, float]]:
        """Intervals where `g - y > 0` (positive) or `< 0`."""
        cuts = [-math.inf, *self.zeros(y), math.inf]
        out = []
        for lo, hi in itertools.pairwise(cuts):
            if lo == hi:
                continue
            mid = ((lo + hi) / 2 if math.isfinite(lo) and math.isfinite(hi)
                   else (hi - self.sd if math.isfinite(hi) else
                         lo + self.sd if math.isfinite(lo) else 0.0))
            v = self.value(mid, y)
            if (v > 0) == positive and v != 0:
                out.append((lo, hi))
        return out

    def expectation(self, positive: bool) -> float:
        """`E[max(g, 0)]` or `E[min(g, 0)]`."""
        total = []
        for lo, hi in self._intervals(0.0, positive):
            for ak, bk in zip(self.a, self.b, strict=True):
                shift = bk * self.zeta
                weight = float(ak) * math.exp(float(bk) ** 2 * self.zeta / 2)
                total.append(weight * _interval_mass((lo + shift) / self.sd,
                                                     (hi + shift) / self.sd))
        return ordered_sum(total)

    def probability_below(self, y: float) -> float:
        """`P(g <= y)`, as one minus the mass where `g > y`."""
        above = ordered_sum(_interval_mass(lo / self.sd, hi / self.sd)
                            for lo, hi in self._intervals(y, True))
        return 1.0 - above

    def quantile_of_exposure(self, q: float) -> float:
        """Smallest `y >= 0` with `P(max(g, 0) <= y) >= q`."""
        if self.probability_below(0.0) >= q:
            return 0.0
        lo, hi = 0.0, max(1.0, float(np.max(np.abs(self.a))))
        while self.probability_below(hi) < q:
            lo, hi = hi, 2 * hi
        for _ in range(200):
            mid = (lo + hi) / 2
            if mid in (lo, hi) or hi - lo <= 1e-15 * hi:
                break
            if self.probability_below(mid) >= q:
                hi = mid
            else:
                lo = mid
        return hi


def _profile(curve: Curve, a: float, sigma: float, swaps: Sequence[Swap], t: float) -> _Profile:
    def h(s: float) -> float:
        return -math.expm1(-a * s) / a

    zeta = sigma * sigma * math.expm1(2 * a * t) / (2 * a)
    ht = h(t)
    pt = curve.discount(t)
    coeffs: dict[float, float] = {}
    for sw in swaps:
        rest = [s for s in sw.payments if s > t]
        if not rest:
            continue
        sign = sw.notional * (1.0 if sw.payer else -1.0)
        # floater at par: sign * 1 / N(t, x) = sign P(0,t) exp(-H_t x - H_t^2 zeta/2)
        coeffs[ht] = coeffs.get(ht, 0.0) + sign * pt * math.exp(-ht * ht * zeta / 2)
        taus = [rest[0] - t, *(b - a_ for a_, b in itertools.pairwise(rest))]
        for j, (s, tau) in enumerate(zip(rest, taus, strict=True)):
            w = sw.fixed_rate * tau + (1.0 if j == len(rest) - 1 else 0.0)
            hs = h(s)
            coeffs[hs] = coeffs.get(hs, 0.0) - sign * w * curve.discount(s) * math.exp(
                -hs * hs * zeta / 2)
    keys = sorted(k for k, v in coeffs.items() if v != 0)
    return _Profile([coeffs[k] for k in keys], keys, zeta)


def pfe_key(q: float) -> str:
    """Ruling R6-5.6: `deflated_pfe_` and `100 q` with trailing zeros removed."""
    return "deflated_pfe_" + format((Decimal(repr(q)) * 100).normalize(), "f")


def portfolio_hw(times: Floats, discount_factors: Floats, a: float, sigma: float,
                 trades: Sequence[tuple[float, float, str, float, Floats]],
                 exposure_times: Floats, quantiles: Floats, hazard_rate: float,
                 recovery: float) -> dict[str, object]:
    """`xva.exposure.portfolio_hw`: discounted EE, ENE, PFE, EPE and CVA of a netting set."""
    model = curve_model(times, discount_factors, a, sigma)
    assert model.curve is not None
    if not trades:
        raise _input("trades needs at least one swap", "trades")
    swaps = [make_swap(*t) for t in trades]
    common = sorted({d for sw in swaps for d in sw.grid})
    for sw in swaps:
        own = [d for d in common if sw.start <= d <= sw.payments[-1]]
        if tuple(own) != sw.grid:
            raise _input("the trades of a set must share their reset dates", "trades")
    last = max(sw.payments[-1] for sw in swaps)
    resets = {d for d in common if d < last}
    if (not exposure_times or not all(x < y for x, y in itertools.pairwise(exposure_times))
            or any(t not in resets for t in exposure_times)):
        raise _input("exposure_times must be increasing reset dates before the last payment",
                     "exposure_times")
    if not quantiles or any(not 0 < q < 1 for q in quantiles):
        raise _domain("pfe_quantiles must lie in (0, 1)", "pfe_quantiles")
    if not hazard_rate >= 0:
        raise _domain("hazard_rate must be >= 0", "hazard_rate")
    if not 0 <= recovery < 1:
        raise _domain("recovery must be in [0, 1)", "recovery")
    ee, ene = [], []
    pfe: dict[float, list[float]] = {q: [] for q in quantiles}
    for t in exposure_times:
        prof = _profile(model.curve, a, sigma, swaps, t)
        ee.append(prof.expectation(True))
        ene.append(prof.expectation(False))
        for q in quantiles:
            pfe[q].append(prof.quantile_of_exposure(q))
    prev = [0.0, *exposure_times[:-1]]
    epe = ordered_sum(e * (t - p) for e, t, p in zip(ee, exposure_times, prev, strict=True)) / (
        exposure_times[-1])
    cva = (1 - recovery) * ordered_sum(
        e * (math.exp(-hazard_rate * p) - math.exp(-hazard_rate * t))
        for e, t, p in zip(ee, exposure_times, prev, strict=True))
    out: dict[str, object] = {"discounted_ee": ee, "discounted_ene": ene}
    for q in quantiles:
        out[pfe_key(q)] = pfe[q]
    out["epe"] = epe
    out["cva"] = cva
    return out


guard(globals())
