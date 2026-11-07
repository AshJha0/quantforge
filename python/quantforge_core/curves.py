"""The discount curve object (specifications/02-curves/curve-framework.md)."""
import math
from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from . import daycount, roots
from .errors import QfError

INTERPOLATIONS = ("LOG_LINEAR_DF", "LINEAR_ZERO")
MAX_REPRICING_ERROR = 1e-13


@dataclass(frozen=True)
class CurveData:
    """Market data as given: not yet checked."""

    as_of: date
    interpolation: str
    dates: tuple[date, ...]
    discount_factors: tuple[float, ...]
    jumps: tuple[tuple[date, float], ...] = ()


class Curve:
    def __init__(self, data: CurveData):
        self.as_of = data.as_of
        self.interpolation = data.interpolation
        self.jumps = data.jumps
        self.times = [0.0, *(self.time(d) for d in data.dates)]
        self.logs = [0.0, *(math.log(v / self.jump(d))
                            for d, v in zip(data.dates, data.discount_factors, strict=True))]
        self.zeros = [0.0, *(-x / t for x, t in zip(self.logs[1:], self.times[1:], strict=True))]
        self.zeros[0] = self.zeros[1]

    def time(self, d: date) -> float:
        return (d - self.as_of).days / 365

    def jump(self, d: date) -> float:
        """J(d): the product of jump factors dated strictly before d (ruling D2)."""
        product = 1.0
        for day, factor in self.jumps:
            if day < d:
                product *= factor
        return product

    def discount(self, d: date) -> float:
        return self._smooth(d) * self.jump(d)

    def _smooth(self, d: date) -> float:
        t = self.time(d)
        if t < 0:
            raise QfError("E_OUT_OF_RANGE", f"{d} is before the curve date")
        if t == 0:
            return 1.0
        ts, xs = self.times, self.logs
        n = len(ts) - 1
        if t >= ts[n]:
            forward = -(xs[n] - xs[n - 1]) / (ts[n] - ts[n - 1])
            return math.exp(xs[n] - forward * (t - ts[n]))
        i = bisect_right(ts, t) - 1
        u = (t - ts[i]) / (ts[i + 1] - ts[i])
        if self.interpolation == "LOG_LINEAR_DF":
            return math.exp((1 - u) * xs[i] + u * xs[i + 1])
        return math.exp(-((1 - u) * self.zeros[i] + u * self.zeros[i + 1]) * t)


def check_jumps(as_of: date, jumps: Sequence[tuple[date, float]]) -> None:
    previous = as_of
    for d, _ in jumps:
        if d <= previous:
            raise QfError("E_INPUT", "jump dates must be increasing and after as_of", "jumps")
        previous = d
    if any(not f > 0 for _, f in jumps):
        raise QfError("E_DOMAIN", "jump factors must be positive", "jumps")


def build(data: CurveData) -> Curve:
    previous = data.as_of
    if not data.dates:
        raise QfError("E_INPUT", "a curve needs pillars", "pillars")
    for d in data.dates:
        if d <= previous:
            raise QfError("E_INPUT", "pillars must be increasing and after as_of", "pillars")
        previous = d
    if any(v <= 0 for v in data.discount_factors):
        raise QfError("E_DOMAIN", "discount factors must be positive", "pillars")
    check_jumps(data.as_of, data.jumps)
    return Curve(data)


def discount(data: CurveData, dates: Sequence[date]) -> tuple[list[float], list[float | None]]:
    curve = build(data)
    factors = [curve.discount(d) for d in dates]
    zeros: list[float | None] = [
        None if d == curve.as_of else -math.log(v) / curve.time(d)
        for d, v in zip(dates, factors, strict=True)
    ]
    return factors, zeros


def forward(data: CurveData, start: date, end: date, day_count: str) -> float:
    curve = build(data)
    if end <= start:
        raise QfError("E_DATE_ORDER", "end is not after start", "end")
    alpha = daycount.year_fraction(day_count, start, end)
    return (curve.discount(start) / curve.discount(end) - 1) / alpha


Model = Callable[[Curve], float]


def solve_pillars(
    as_of: date,
    interpolation: str,
    pillars: Sequence[date],
    models: Sequence[Model],
    targets: Sequence[float],
    jumps: tuple[tuple[date, float], ...] = (),
) -> tuple[list[float], float]:
    """One unknown at a time. Every date quote j needs lies on or before pillar j, so each solve
    sees only pillars already fixed and its own. Returns (discount factors, largest error)."""
    logs: list[float] = []

    def curve_with(x: float, count: int) -> Curve:
        factors = (*(math.exp(v) for v in logs), math.exp(x))
        return Curve(CurveData(as_of, interpolation, tuple(pillars[:count]), factors, jumps))

    for j, (model, target) in enumerate(zip(models, targets, strict=True)):
        def error(x: float, model: Model = model, target: float = target, j: int = j) -> float:
            return model(curve_with(x, j + 1)) - target

        t = (pillars[j] - as_of).days / 365
        guess = logs[-1] - target * 0.1 if logs else -target * t
        logs.append(_solve(error, guess))

    final = Curve(CurveData(as_of, interpolation, tuple(pillars),
                            tuple(math.exp(v) for v in logs), jumps))
    return [math.exp(v) for v in logs], repricing_error(final, models, targets)


def _solve(error: Callable[[float], float], guess: float) -> float:
    width = 0.01
    low, high = guess - width, guess + width
    for _ in range(40):
        if (error(low) > 0) != (error(high) > 0):
            return roots.brent(error, low, high, x_tol=1e-15, max_iter=500).root
        width *= 2
        low, high = guess - width, guess + width
    raise QfError("E_NO_CONVERGENCE", "the curve solve found no bracket")


def repricing_error(curve: Curve, models: Sequence[Model], targets: Sequence[float]) -> float:
    return max(abs(m(curve) - q) for m, q in zip(models, targets, strict=True))


def check_solved(error: float) -> None:
    if not error < MAX_REPRICING_ERROR:
        raise QfError("E_NO_CONVERGENCE", f"repricing error {error} is above the limit")
