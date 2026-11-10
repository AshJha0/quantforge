"""Meeting-date step curves and their fit (specifications/02-curves/meeting-steps.md)."""
import itertools
import math
from collections.abc import Callable, Sequence
from datetime import date

from . import curves, ois, roots
from .conventions import REGISTRY
from .errors import QfError
from .finite import guard
from .ois import Quote
from .schedules import Period

Jumps = tuple[tuple[date, float], ...]


class StepCurve:
    """Flat instantaneous forward between steps, with jumps. Has the `discount` the OIS legs use."""

    def __init__(self, as_of: date, base_rate: float, steps: Sequence[tuple[date, float]],
                 jumps: Jumps):
        self.as_of, self.base_rate, self.steps, self.jumps = as_of, base_rate, list(steps), jumps

    def forward(self, d: date) -> float:
        rate = self.base_rate
        for day, r in self.steps:
            if day <= d:
                rate = r
        return rate

    def discount(self, d: date) -> float:
        if d < self.as_of:
            raise QfError("E_OUT_OF_RANGE", f"{d} is before as_of")
        integral, left, rate = 0.0, self.as_of, self.base_rate
        for day, r in self.steps:
            if day >= d:
                break
            integral += rate * (day - left).days
            left, rate = day, r
        integral += rate * (d - left).days
        factor = math.exp(-integral / 365)
        for day, f in self.jumps:
            if day < d:
                factor *= f
        return factor


def _check_step_dates(as_of: date, dates: Sequence[date]) -> None:
    if any(b <= a for a, b in itertools.pairwise([as_of, *dates])):
        raise QfError("E_INPUT", "step dates must be increasing and after as_of", "steps")


def step_curve(
    as_of: date, base_rate: float, steps: Sequence[tuple[date, float]], jumps: Jumps,
    dates: Sequence[date],
) -> tuple[list[float], list[float]]:
    _check_step_dates(as_of, [d for d, _ in steps])
    curves.check_jumps(as_of, jumps)
    if not dates:
        raise QfError("E_INPUT", "no dates", "dates")
    curve = StepCurve(as_of, base_rate, steps, jumps)
    factors = [curve.discount(d) for d in dates]
    return factors, [curve.forward(d) for d in dates]


def fit_steps(
    convention: str, as_of: date, step_dates: Sequence[date], quotes: Sequence[Quote],
    jumps: Jumps,
) -> tuple[float, list[float], float]:
    """Returns (base_rate, step_rates, max_repricing_error)."""
    if REGISTRY[convention]["kind"] != "OVERNIGHT":
        raise QfError("E_INPUT", "the convention is not overnight", "convention")
    m = len(step_dates)
    if m == 0:
        raise QfError("E_INPUT", "no step dates (ruling D64)", "step_dates")
    if len(quotes) != m + 1:
        raise QfError("E_INPUT", "need one more quote than step dates", "quotes")
    _check_step_dates(as_of, step_dates)
    swaps = [ois.periods(convention, as_of, q.tenor) for q in quotes]
    bounds = [as_of, *step_dates]
    for j, ps in enumerate(swaps):
        p = ps[-1].payment
        if not (bounds[j] < p and (j == m or p <= bounds[j + 1])):
            raise QfError("E_INPUT", "quote pillars must sit between step dates", "quotes")
    curves.check_jumps(as_of, jumps)
    rates: list[float] = []
    for j, (ps, q) in enumerate(zip(swaps, quotes, strict=True)):
        def error(x: float, ps: list[Period] = ps, q: Quote = q, j: int = j) -> float:
            values = [*rates, x]
            curve = StepCurve(as_of, values[0], list(zip(step_dates[:j], values[1:],
                                                         strict=True)), jumps)
            return ois.par_rate(convention, ps, curve) - q.mid

        rates.append(_solve(error, rates[-1] if rates else q.mid))
    final = StepCurve(as_of, rates[0], list(zip(step_dates, rates[1:], strict=True)), jumps)
    worst = max(abs(ois.par_rate(convention, ps, final) - q.mid)
                for ps, q in zip(swaps, quotes, strict=True))
    curves.check_solved(worst)
    return rates[0], rates[1:], worst


def _solve(f: Callable[[float], float], guess: float) -> float:
    width = 0.01
    for _ in range(40):
        low, high = guess - width, guess + width
        if (f(low) > 0) != (f(high) > 0):
            return roots.brent(f, low, high, x_tol=1e-16, max_iter=500).root
        width *= 2
    raise QfError("E_NO_CONVERGENCE", "the step fit found no bracket")


guard(globals())
