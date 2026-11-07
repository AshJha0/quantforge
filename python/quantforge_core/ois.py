"""OIS legs, bootstrap and PV (specifications/02-curves/ois-curves.md).

Instrument: OisTrade. Product model: periods. Market data: Curve. Pricing model: legs, ois_pv.
"""
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from . import calendars, curves, daycount, linalg, schedules
from .conventions import REGISTRY
from .curves import Curve, CurveData
from .errors import QfError, required
from .numeric import ordered_sum
from .schedules import Period

_MF = "MODIFIED_FOLLOWING"


class Discounting(Protocol):
    def discount(self, d: date) -> float: ...


@dataclass(frozen=True)
class Quote:
    tenor: str
    rate: float | None = None
    bid: float | None = None
    ask: float | None = None

    @property
    def mid(self) -> float:
        if self.rate is not None:
            return self.rate
        return (required(self.bid, "bid") + required(self.ask, "ask")) / 2


@dataclass(frozen=True)
class OisTrade:
    convention: str
    tenor: str
    fixed_rate: float
    notional: float
    side: str


def valuation(
    pv: float, currency: str, model: str, data_version: str | None, conventions: str, as_of: date
) -> dict[str, object]:
    return {
        "pv": pv, "currency": currency, "model": model, "data_version": data_version,
        "conventions": conventions, "as_of": as_of.isoformat(),
    }


def periods(convention: str, as_of: date, tenor: str) -> list[Period]:
    c = REGISTRY[convention]
    cal = c["calendar"]
    spot = calendars.add_business_days(cal, as_of, c["spot_lag"])
    n, unit = int(tenor[:-1]), tenor[-1]
    months = n * 12 if unit == "Y" else n
    lag = c["payment_lag"]
    if unit in "DW" or months <= c["fixed_months"]:
        end = calendars.add_tenor(cal, spot, tenor, _MF, True)
        payment = calendars.add_business_days(cal, end, lag) if lag else end
        return [Period(spot, end, payment)]
    eom = spot >= calendars.last_business_day(cal, spot.year, spot.month)
    end = schedules.add_months(spot, months)
    return schedules.generate(spot, end, c["fixed_months"], cal, eom, lag)


def _alphas(convention: str, ps: Sequence[Period]) -> list[float]:
    fixed_day_count = REGISTRY[convention]["fixed_day_count"]
    return [daycount.year_fraction(fixed_day_count, p.start, p.end) for p in ps]


def legs(
    convention: str, ps: Sequence[Period], curve: Discounting,
    alphas: Sequence[float] | None = None,
) -> tuple[float, float]:
    """Returns (annuity, floating), in the general form: never telescoped. `alphas`, the fixed
    year fractions, may be passed in precomputed; the sums are the same."""
    if alphas is None:
        alphas = _alphas(convention, ps)
    annuity = ordered_sum(a * curve.discount(p.payment) for a, p in zip(alphas, ps, strict=True))
    floating = ordered_sum(
        (curve.discount(p.start) / curve.discount(p.end) - 1) * curve.discount(p.payment)
        for p in ps
    )
    return annuity, floating


def par_rate(convention: str, ps: Sequence[Period], curve: Discounting) -> float:
    annuity, floating = legs(convention, ps, curve)
    return floating / annuity


def _models(convention: str, swaps: Sequence[Sequence[Period]]) -> list[curves.Model]:
    def model(ps: Sequence[Period]) -> curves.Model:
        alphas = _alphas(convention, ps)  # fixed for the whole solve

        def rate(c: curves.Curve) -> float:
            annuity, floating = legs(convention, ps, c, alphas)
            return floating / annuity

        return rate

    return [model(ps) for ps in swaps]


def _global_solve(
    as_of: date, interpolation: str, pillars: Sequence[date], models: Sequence[curves.Model],
    targets: Sequence[float], jumps: tuple[tuple[date, float], ...] = (),
) -> tuple[list[float], float]:
    """Newton on all pillars together, on log discount factors, with a bumped Jacobian."""
    n = len(pillars)
    xs = [-q * (d - as_of).days / 365 for q, d in zip(targets, pillars, strict=True)]

    def errors(x: Sequence[float]) -> list[float]:
        data = CurveData(as_of, interpolation, tuple(pillars), tuple(math.exp(v) for v in x),
                         jumps)
        curve = Curve(data)
        return [m(curve) - q for m, q in zip(models, targets, strict=True)]

    best = math.inf
    for _ in range(50):
        r = errors(xs)
        size = max(abs(v) for v in r)
        best = min(best, size)
        if size < 1e-15:
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


def _check_quotes(
    convention: str, as_of: date, quotes: Sequence[Quote]
) -> tuple[list[list[Period]], list[date]]:
    if not quotes:
        raise QfError("E_INPUT", "no quotes", "quotes")
    swaps = [periods(convention, as_of, q.tenor) for q in quotes]
    pillars = [ps[-1].payment for ps in swaps]
    if any(b <= a for a, b in itertools.pairwise(pillars)):
        raise QfError("E_INPUT", "pillars are not strictly increasing", "quotes")
    if any(q.rate is None and required(q.bid, "bid") > required(q.ask, "ask") for q in quotes):
        raise QfError("E_INPUT", "bid is above ask", "quotes")
    return swaps, pillars


def bootstrap(
    convention: str, as_of: date, quotes: Sequence[Quote], interpolation: str,
    method: str = "SEQUENTIAL", jumps: tuple[tuple[date, float], ...] = (),
) -> tuple[CurveData, float]:
    """Returns (curve, max_repricing_error)."""
    curves.check_jumps(as_of, jumps)
    swaps, pillars = _check_quotes(convention, as_of, quotes)
    models = _models(convention, swaps)
    targets = [q.mid for q in quotes]
    solve = curves.solve_pillars if method == "SEQUENTIAL" else _global_solve
    factors, error = solve(as_of, interpolation, pillars, models, targets, jumps)
    curves.check_solved(error)
    return CurveData(as_of, interpolation, tuple(pillars), tuple(factors), jumps), error


def compound(rates: Sequence[float], days: Sequence[int], denominator: int) -> float:
    if len(rates) != len(days) or not rates or any(n < 1 for n in days):
        raise QfError("E_INPUT", "need equal lengths and days of at least 1")
    growth = 1.0
    for r, n in zip(rates, days, strict=True):
        growth *= 1 + r * n / denominator
    return (growth - 1) * denominator / sum(days)


def trade_pv(trade: OisTrade, ps: Sequence[Period], curve: Curve) -> tuple[float, float, float]:
    """Returns (pv, par rate, annuity)."""
    annuity, floating = legs(trade.convention, ps, curve)
    sign = 1 if trade.side == "PAY" else -1
    pv = sign * trade.notional * (floating - trade.fixed_rate * annuity)
    return pv, floating / annuity, annuity


def pv(
    data: CurveData, trade: OisTrade, snapshot_id: str | None = None
) -> tuple[dict[str, object], float, float]:
    curve = curves.build(data)
    ps = periods(trade.convention, curve.as_of, trade.tenor)
    value, par, annuity = trade_pv(trade, ps, curve)
    currency = REGISTRY[trade.convention]["currency"]
    result = valuation(value, currency, "OIS_DISCOUNTING", snapshot_id, trade.convention,
                       curve.as_of)
    return result, par, annuity
