"""ISDA CDS, index CDS and composite curves (specifications/04-pricing/credit.md)."""
import itertools
import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from . import curves, roots, schedules
from .curves import Curve, CurveData
from .errors import QfError
from .numeric import ordered_sum

DAY = timedelta(days=1)


def _weekday(d: date) -> date:
    while d.weekday() >= 5:
        d += DAY
    return d


def _add_weekdays(d: date, n: int) -> date:
    for _ in range(n):
        d = _weekday(d + DAY)
    return d


def maturity(trade_date: date, tenor: str) -> date:
    t = trade_date
    if t >= date(t.year, 9, 20):
        roll = date(t.year, 12, 20)
    elif t >= date(t.year, 3, 20):
        roll = date(t.year, 6, 20)
    else:
        roll = date(t.year - 1, 12, 20)
    n, unit = int(tenor[:-1]), tenor[-1]
    if unit not in "MY":
        raise QfError("E_SCHEMA", "a CDS tenor is in months or years", "tenor")
    return schedules.add_months(roll, n * 12 if unit == "Y" else n)


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    payment: date
    alpha: float


def periods(trade_date: date, mat: date) -> list[Period]:
    first = date(trade_date.year, 12, 20)
    while first > trade_date:
        m = first.month - 3
        first = date(first.year - (m <= 0), m + 12 if m <= 0 else m, 20)
    raw = [first]
    while raw[-1] < mat:
        raw.append(schedules.add_months(raw[-1], 3))
    raw[-1] = mat
    out = []
    for i, (s, e) in enumerate(itertools.pairwise(raw)):
        last = i == len(raw) - 2
        start = _weekday(s)
        end = e if last else _weekday(e)
        alpha = ((end - start).days + (1 if last else 0)) / 360
        out.append(Period(start, end, _weekday(e), alpha))
    if any(p.start == trade_date for p in out) or any(p.payment == trade_date for p in out):
        raise QfError("E_INPUT", "the trade date is on a coupon date", "trade_date")
    return out


class Hazard:
    def __init__(self, as_of: date, dates: Sequence[date], survival: Sequence[float]):
        self.as_of, self.dates = as_of, list(dates)
        self.times = [0.0, *((d - as_of).days / 365 for d in dates)]
        self.logs = [0.0, *(math.log(q) for q in survival)]

    def q(self, t: float) -> float:
        ts, xs = self.times, self.logs
        if t <= 0:
            return 1.0
        n = len(ts) - 1
        if t >= ts[n]:
            h = (xs[n - 1] - xs[n]) / (ts[n] - ts[n - 1])
            return math.exp(xs[n] - h * (t - ts[n]))
        i = bisect_right(ts, t) - 1
        u = (t - ts[i]) / (ts[i + 1] - ts[i])
        return math.exp((1 - u) * xs[i] + u * xs[i + 1])


def check_hazard(as_of: date, dates: Sequence[date], survival: Sequence[float]) -> Hazard:
    if not dates:
        raise QfError("E_INPUT", "a hazard curve needs pillars", "hazard")
    previous = as_of
    for d in dates:
        if d <= previous:
            raise QfError("E_INPUT", "hazard pillars must be increasing and after as_of", "hazard")
        previous = d
    if any(not q > 0 for q in survival):
        raise QfError("E_DOMAIN", "survival must be positive", "hazard")
    return Hazard(as_of, dates, survival)


def _series(x: float) -> tuple[float, float]:
    """((1 - e^-x)/x, (1 - e^-x (1 + x))/x^2), with a Taylor series near 0."""
    if abs(x) < 1e-4:
        return (1 - x / 2 + x * x / 6 - x ** 3 / 24 + x ** 4 / 120,
                0.5 - x / 3 + x * x / 8 - x ** 3 / 30 + x ** 4 / 144)
    e = math.exp(-x)
    return (1 - e) / x, (1 - e * (1 + x)) / (x * x)


class Model:
    def __init__(self, trade_date: date, discount: Curve, hazard: Hazard):
        self.t0, self.p, self.h = trade_date, discount, hazard
        self.nodes = sorted({*discount.dates, *hazard.dates})

    def time(self, d: date) -> float:
        return (d - self.t0).days / 365

    def qp(self, d: date) -> tuple[float, float, float]:
        t = self.time(d)
        q, p = self.h.q(t), self.p.discount(d)
        return t, q, p

    def pieces(self, a: date, b: date) -> list[tuple[float, float, float, float, float]]:
        """(t0, D, h, k, QP(t0)) for each piece of [a, b] between nodes."""
        cuts = [a, *(n for n in self.nodes if a < n < b), b]
        out = []
        for x, y in itertools.pairwise(cuts):
            t0, q0, p0 = self.qp(x)
            t1, q1, p1 = self.qp(y)
            span = t1 - t0
            h = math.log(q0 / q1) / span
            f = math.log(p0 / p1) / span
            out.append((t0, span, h, f + h, q0 * p0))
        return out

    def protection(self, mat: date) -> float:
        return ordered_sum(h * qp0 * span * _series(k * span)[0]
                           for _, span, h, k, qp0 in self.pieces(self.t0, mat))

    def rpv01(self, ps: Sequence[Period]) -> float:
        total = []
        for per in ps:
            obs = per.payment - DAY
            _, q, _ = self.qp(obs)
            total.append(per.alpha * q * self.p.discount(per.payment))
            s = max(per.start - DAY, self.t0)
            tacc = self.time(per.start - DAY)
            aod = ordered_sum(
                h * qp0 * ((t0 - tacc) * span * a + span * span * b)
                for t0, span, h, k, qp0 in self.pieces(s, obs)
                for a, b in (_series(k * span),))
            total.append(365 / 360 * aod)
        return ordered_sum(total)


def _check_recovery(r: float) -> None:
    if not 0 <= r < 1:
        raise QfError("E_DOMAIN", "recovery must be in [0, 1)", "recovery")


@dataclass(frozen=True)
class Price:
    protection_leg: float
    rpv01: float
    accrued: float
    par_spread: float
    upfront: float
    pcs: float


def _price(model: Model, mat: date, coupon: float, lgd: float) -> Price:
    ps = periods(model.t0, mat)
    prot = lgd * model.protection(mat)
    rpv01 = model.rpv01(ps)
    accrual_days = (model.t0 + DAY - ps[0].start).days / 360
    pcs = model.p.discount(_add_weekdays(model.t0, 3))
    par = prot / (rpv01 - accrual_days * pcs)
    accrued = coupon * accrual_days
    upfront = (prot - coupon * rpv01) / pcs + accrued
    return Price(prot, rpv01, accrued, par, upfront, pcs)


def price(
    trade_date: date, discount: CurveData, hazard: Hazard, recovery: float, mat: date,
    coupon: float, notional: float, side: str, payout: str,
) -> dict[str, float]:
    model = Model(trade_date, curves.build(discount), hazard)
    _check_recovery(recovery)
    r = _price(model, mat, coupon, 1.0 if payout == "DIGITAL" else 1 - recovery)
    sign = 1 if side == "BUY_PROTECTION" else -1
    pv = sign * notional * (r.protection_leg - coupon * r.rpv01 + r.accrued * r.pcs)
    return {"protection_leg": r.protection_leg, "rpv01": r.rpv01, "accrued": r.accrued,
            "par_spread": r.par_spread, "upfront": r.upfront, "pv": pv}


def bootstrap(
    trade_date: date, discount: CurveData, recovery: float, quotes: Sequence[tuple[str, float]],
) -> list[tuple[date, float]]:
    disc = curves.build(discount)
    _check_recovery(recovery)
    if not quotes:
        raise QfError("E_INPUT", "no quotes", "quotes")
    mats = [maturity(trade_date, t) for t, _ in quotes]
    if any(b <= a for a, b in itertools.pairwise(mats)):
        raise QfError("E_INPUT", "maturities must be strictly increasing", "quotes")
    if any(s <= 0 for _, s in quotes):
        raise QfError("E_DOMAIN", "spreads must be positive", "quotes")
    periods(trade_date, mats[-1])
    logs: list[float] = []
    for j, (mat, (_, spread)) in enumerate(zip(mats, quotes, strict=True)):
        def gap(x: float, j: int = j, mat: date = mat, spread: float = spread) -> float:
            h = Hazard(trade_date, mats[:j + 1], [math.exp(v) for v in [*logs, x]])
            return _price(Model(trade_date, disc, h), mat, spread, 1 - recovery).par_spread \
                - spread

        t = (mat - trade_date).days / 365
        guess = -spread / (1 - recovery) * t
        low, high = guess - 0.05, min(guess + 0.05, logs[-1] if logs else 0.0)
        for _ in range(60):
            if gap(low) > 0 > gap(high):
                break
            low -= (high - low)
        else:
            raise QfError("E_NO_CONVERGENCE", "the hazard solve found no bracket")
        logs.append(roots.brent(gap, low, high, x_tol=1e-16, max_iter=1000).root)
    return [(d, math.exp(v)) for d, v in zip(mats, logs, strict=True)]


def index_intrinsic(
    trade_date: date, discount: CurveData, names: Sequence[tuple[Hazard, float, float]],
    mat: date, coupon: float, quoted: float,
) -> tuple[list[float], float, float]:
    disc = curves.build(discount)
    if not names:
        raise QfError("E_INPUT", "no names", "names")
    ups = []
    for hazard, recovery, _ in names:
        _check_recovery(recovery)
        ups.append(_price(Model(trade_date, disc, hazard), mat, coupon, 1 - recovery).upfront)
    total_w = ordered_sum(w for _, _, w in names)
    if total_w <= 0:
        raise QfError("E_DOMAIN", "weights must sum above 0", "names")
    intrinsic = ordered_sum(u * w for u, (_, _, w) in zip(ups, names, strict=True)) / total_w
    return ups, intrinsic, quoted - intrinsic


def composite(
    trade_date: date, discount: CurveData, recovery: float,
    constituents: Sequence[tuple[Sequence[tuple[str, float]], float]], scale: float,
) -> tuple[list[float], list[tuple[date, float]]]:
    curves.build(discount)
    if not constituents:
        raise QfError("E_INPUT", "no constituents", "constituents")
    tenors = [t for t, _ in constituents[0][0]]
    if any([t for t, _ in qs] != tenors for qs, _ in constituents):
        raise QfError("E_INPUT", "constituents must share tenors", "constituents")
    if not scale > 0:
        raise QfError("E_DOMAIN", "scale must be positive", "scale")
    total_w = ordered_sum(w for _, w in constituents)
    if total_w <= 0 or any(w < 0 for _, w in constituents):
        raise QfError("E_DOMAIN", "weights must be non-negative and sum above 0", "constituents")
    spreads = [scale * ordered_sum(qs[j][1] * w for qs, w in constituents) / total_w
               for j in range(len(tenors))]
    pillars = bootstrap(trade_date, discount, recovery, list(zip(tenors, spreads, strict=True)))
    return spreads, pillars
