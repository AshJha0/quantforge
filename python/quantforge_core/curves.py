"""The discount curve object (specifications/02-curves/curve-framework.md)."""
import math
from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from . import curve_interp, daycount, linalg, roots
from .errors import QfError
from .finite import guard

INTERPOLATIONS = ("LOG_LINEAR_DF", "LINEAR_ZERO", *curve_interp.NEW_METHODS)
MAX_TENSION = 1000.0
MAX_REPRICING_ERROR = 1e-13


@dataclass(frozen=True)
class CurveData:
    """Market data as given: not yet checked."""

    as_of: date
    interpolation: str
    dates: tuple[date, ...]
    discount_factors: tuple[float, ...]
    jumps: tuple[tuple[date, float], ...] = ()
    tension: float | None = None
    step_end: date | None = None


def check_options(interpolation: str, tension: float | None, step_end: date | None,
                  pillars: Sequence[date]) -> None:
    """Stage F curve keys: `tension` for TENSION_SPLINE, `step_end` (a pillar) for HYBRID."""
    if interpolation == "TENSION_SPLINE":
        if tension is None:
            raise QfError("E_INPUT", "TENSION_SPLINE needs tension", "tension")
        if not 0 < tension <= MAX_TENSION:
            raise QfError("E_DOMAIN", "tension must be in (0, 1000]", "tension")
    if interpolation == "HYBRID":
        if step_end is None:
            raise QfError("E_INPUT", "HYBRID needs step_end", "step_end")
        if step_end not in pillars:
            raise QfError("E_INPUT", "step_end must be a pillar date", "step_end")


class Curve:
    _interp: curve_interp.Interpolator | None = None

    def __init__(self, data: CurveData):
        self.as_of = data.as_of
        self.interpolation = data.interpolation
        self.jumps = data.jumps
        self.dates = data.dates
        self.times = [0.0, *(self.time(d) for d in data.dates)]
        self.logs = [0.0, *(math.log(v / self.jump(d))
                            for d, v in zip(data.dates, data.discount_factors, strict=True))]
        self.zeros = [0.0, *(-x / t for x, t in zip(self.logs[1:], self.times[1:], strict=True))]
        if data.dates:  # an empty curve is only the bare prefix of a curve solve
            self.zeros[0] = self.zeros[1]
        self._memo: dict[date, float] = {}
        self._stable_until = date.min
        self._stable = self._memo
        self.tension, self.step_end = data.tension, data.step_end
        if data.interpolation in curve_interp.NEW_METHODS and data.dates:
            k = data.dates.index(data.step_end) + 1 if data.step_end in data.dates else None
            self._interp = curve_interp.make(data.interpolation, self.times, self.logs,
                                             data.tension, k)

    @classmethod
    def _extended(cls, prefix: Curve, d: date, factor: float) -> Curve:
        """The curve `prefix` with one more pillar (d, factor), computed element by element as
        __init__ would: the fixed pillars' times, logs and zeros are reused, not recomputed."""
        if prefix.interpolation in curve_interp.NEW_METHODS:
            return cls(CurveData(prefix.as_of, prefix.interpolation, (*prefix.dates, d),
                                 (*(math.exp(x) * prefix.jump(p)
                                    for x, p in zip(prefix.logs[1:], prefix.dates, strict=True)),
                                  factor), prefix.jumps, prefix.tension, prefix.step_end))
        curve = cls.__new__(cls)
        curve.as_of, curve.interpolation, curve.jumps = prefix.as_of, prefix.interpolation, prefix.jumps
        curve.dates = (*prefix.dates, d)
        t = curve.time(d)
        x = math.log(factor / curve.jump(d))
        curve.times = [*prefix.times, t]
        curve.logs = [*prefix.logs, x]
        curve.zeros = [*prefix.zeros, -x / t]
        curve.zeros[0] = curve.zeros[1]
        curve._memo = {}
        curve._stable_until = date.min
        curve._stable = curve._memo
        return curve

    def share_stable(self, until: date, memo: dict[date, float]) -> Curve:
        """Uses `memo` for dates on or before `until`. For the curve solve: while the last
        pillar moves, a date on or before the previous pillar discounts to the same bits."""
        self._stable_until, self._stable = until, memo
        return self

    def stable_part(self) -> tuple[dict[date, float], date]:
        """The shared memo and its bound, as given to share_stable: a model may treat terms on
        dates up to the bound as fixed for as long as it sees the same memo."""
        return self._stable, self._stable_until

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
        # A curve is immutable, so a date's factor is memoised: swap legs ask for each period
        # boundary more than once. The arithmetic is unchanged.
        # The stable memo holds only dates on or before its bound, so it is looked in first
        # without comparing dates.
        value = self._stable.get(d)
        if value is not None:
            return value
        memo = self._stable if d <= self._stable_until else self._memo
        value = memo.get(d)
        if value is None:
            value = self._smooth(d) * self.jump(d) if self.jumps else self._smooth(d)
            memo[d] = value
        return value

    def _smooth(self, d: date) -> float:
        t = self.time(d)
        if t < 0:
            raise QfError("E_OUT_OF_RANGE", f"{d} is before the curve date")
        if t == 0:
            return 1.0
        if self._interp is not None:
            return math.exp(self._interp.log(t))
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

    def instantaneous_forward(self, d: date) -> float:
        """f = -d ln S/dt of the smooth curve: right-hand at a node, the extrapolation
        forward at and after the last pillar."""
        t = self.time(d)
        if t < 0:
            raise QfError("E_OUT_OF_RANGE", f"{d} is before the curve date")
        if self._interp is not None:
            return self._interp.forward(t)
        ts, xs = self.times, self.logs
        n = len(ts) - 1
        i = n - 1 if t >= ts[n] else bisect_right(ts, t) - 1
        h = ts[i + 1] - ts[i]
        if self.interpolation == "LOG_LINEAR_DF" or t >= ts[n]:
            return -(xs[i + 1] - xs[i]) / h
        slope = (self.zeros[i + 1] - self.zeros[i]) / h
        u = (t - ts[i]) / h
        return (1 - u) * self.zeros[i] + u * self.zeros[i + 1] + t * slope


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
    check_options(data.interpolation, data.tension, data.step_end, data.dates)
    return Curve(data)


def discount(data: CurveData, dates: Sequence[date]) -> tuple[list[float], list[float | None]]:
    curve = build(data)
    factors = [curve.discount(d) for d in dates]
    zeros: list[float | None] = [
        None if d == curve.as_of else -math.log(v) / curve.time(d)
        for d, v in zip(dates, factors, strict=True)
    ]
    return factors, zeros


def inspect(data: CurveData, dates: Sequence[date]
            ) -> tuple[list[float], list[float | None], list[float]]:
    factors, zeros = discount(data, dates)
    curve = build(data)
    return factors, zeros, [curve.instantaneous_forward(d) for d in dates]


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
    tension: float | None = None,
    step_end: date | None = None,
) -> tuple[list[float], float]:
    """One unknown at a time. Every date quote j needs lies on or before pillar j, so each solve
    sees only pillars already fixed and its own. Returns (discount factors, largest error).
    A stage F method is not local, so the one-at-a-time log-linear solve is only the start of
    a Newton solve on all pillars (ruling F-21)."""
    if interpolation in curve_interp.NEW_METHODS:
        check_options(interpolation, tension, step_end, pillars)
        start, _ = solve_pillars(as_of, "LOG_LINEAR_DF", pillars, models, targets, jumps)
        return global_solve(as_of, interpolation, pillars, models, targets, jumps,
                            tension, step_end, [math.log(v) for v in start])
    logs: list[float] = []

    def curve_with(x: float, count: int) -> Curve:
        return Curve._extended(prefix, pillars[count - 1], math.exp(x))

    for j, (model, target) in enumerate(zip(models, targets, strict=True)):
        stable_until = pillars[j - 1] if j else as_of
        stable: dict[date, float] = {}
        # The pillars before j are fixed while pillar j is solved, so their part of the curve is
        # built once here. With no fixed pillar the prefix is the bare curve date.
        prefix = Curve(CurveData(as_of, interpolation, tuple(pillars[:j]),
                                 tuple(math.exp(v) for v in logs), jumps))

        def error(x: float, model: Model = model, target: float = target, j: int = j,
                  until: date = stable_until, memo: dict[date, float] = stable) -> float:
            return model(curve_with(x, j + 1).share_stable(until, memo)) - target

        t = (pillars[j] - as_of).days / 365
        guess = logs[-1] - target * 0.1 if logs else -target * t
        logs.append(_solve(error, guess))

    final = Curve(CurveData(as_of, interpolation, tuple(pillars),
                            tuple(math.exp(v) for v in logs), jumps))
    return [math.exp(v) for v in logs], repricing_error(final, models, targets)


def global_solve(
    as_of: date, interpolation: str, pillars: Sequence[date], models: Sequence[Model],
    targets: Sequence[float], jumps: tuple[tuple[date, float], ...] = (),
    tension: float | None = None, step_end: date | None = None,
    start: Sequence[float] | None = None,
) -> tuple[list[float], float]:
    """Newton on all pillars together, on log discount factors, with a bumped Jacobian."""
    check_options(interpolation, tension, step_end, pillars)
    n = len(pillars)
    xs = list(start) if start is not None else [
        -q * (d - as_of).days / 365 for q, d in zip(targets, pillars, strict=True)]

    def errors(x: Sequence[float]) -> list[float]:
        data = CurveData(as_of, interpolation, tuple(pillars), tuple(math.exp(v) for v in x),
                         jumps, tension, step_end)
        curve = Curve(data)
        return [m(curve) - q for m, q in zip(models, targets, strict=True)]

    for _ in range(50):
        r = errors(xs)
        if max(abs(v) for v in r) < 1e-15:
            break
        jacobian = [[0.0] * n for _ in range(n)]
        h = 1e-7
        for j in range(n):
            up = errors([*xs[:j], xs[j] + h, *xs[j + 1:]])
            down = errors([*xs[:j], xs[j] - h, *xs[j + 1:]])
            for i in range(n):
                jacobian[i][j] = (up[i] - down[i]) / (2 * h)
        step = linalg.lu_solve(jacobian, [-v for v in r])
        xs = [x + s for x, s in zip(xs, step, strict=True)]
        if max(abs(s) for s in step) < 1e-15:
            break
    final = errors(xs)
    return [math.exp(v) for v in xs], max(abs(v) for v in final)


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


guard(globals())
