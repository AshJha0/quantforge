"""Bonds, repo and bond futures (specifications/04-pricing/bonds.md)."""
import calendar as _cal
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from . import curves, linalg, roots, schedules
from .curve_fits import _basis
from .curves import Curve, CurveData
from .errors import QfError
from .numeric import ordered_sum

FREQUENCIES = (1, 2, 4)


@dataclass(frozen=True)
class Bond:
    maturity: date
    coupon: float
    frequency: int


def _month_end(d: date) -> bool:
    return d.day == _cal.monthrange(d.year, d.month)[1]


def _back(maturity: date, months: int, k: int) -> date:
    """The k-th date stepping back `months` at a time from maturity, unadjusted (ruling D13)."""
    d = schedules.add_months(maturity, -k * months)
    if _month_end(maturity):
        d = d.replace(day=_cal.monthrange(d.year, d.month)[1])
    return d


def dates_around(maturity: date, frequency: int, settlement: date) -> tuple[date, list[date]]:
    """Returns (prev, dates after settlement in order)."""
    if settlement >= maturity:
        raise QfError("E_DATE_ORDER", "settlement is not before maturity", "settlement")
    months = 12 // frequency
    after: list[date] = []
    k = 0
    while True:
        d = _back(maturity, months, k)
        if d <= settlement:
            return d, after[::-1]
        after.append(d)
        k += 1


@dataclass(frozen=True)
class Flows:
    prev: date
    dates: list[date]
    amounts: list[float]
    accrued: float
    w: float


def flows(bond: Bond, settlement: date) -> Flows:
    prev, ds = dates_around(bond.maturity, bond.frequency, settlement)
    c = 100 * bond.coupon / bond.frequency
    nxt = ds[0]
    accrued = c * (settlement - prev).days / (nxt - prev).days
    w = (nxt - settlement).days / (nxt - prev).days
    amounts = [c] * len(ds)
    amounts[-1] += 100
    return Flows(prev, ds, amounts, accrued, w)


def accrued_at(bond: Bond, d: date) -> float:
    return flows(bond, d).accrued


def _from_yield(fl: Flows, f: int, y: float) -> tuple[float, float, float, float]:
    """Returns (dirty, macaulay, modified, convexity)."""
    if not 1 + y / f > 0:
        raise QfError("E_DOMAIN", "1 + yield/frequency must be positive", "yield")
    v = 1 / (1 + y / f)
    terms = [(k + fl.w, cf) for k, cf in enumerate(fl.amounts)]
    dirty = ordered_sum(cf * v ** e for e, cf in terms)
    mac = ordered_sum(e / f * cf * v ** e for e, cf in terms) / dirty
    conv = ordered_sum(e * (e + 1) / f ** 2 * cf * v ** (e + 2) for e, cf in terms) / dirty
    return dirty, mac, mac * v, conv


def price_from_yield(bond: Bond, settlement: date, y: float) -> dict[str, float]:
    fl = flows(bond, settlement)
    dirty, mac, mod, conv = _from_yield(fl, bond.frequency, y)
    return {"dirty": dirty, "accrued": fl.accrued, "clean": dirty - fl.accrued,
            "modified_duration": mod, "macaulay_duration": mac, "convexity": conv}


def _root_decreasing(f: Callable[[float], float], low: float, high: float) -> float:
    """Root of a decreasing f, widening `high` upward and `low` toward its floor."""
    for _ in range(200):
        if f(high) < 0:
            break
        high = high * 2 + 1
    else:
        raise QfError("E_NO_CONVERGENCE", "no bracket")
    if not f(low) > 0:
        raise QfError("E_NO_CONVERGENCE", "no bracket")
    return roots.brent(f, low, high, x_tol=1e-16, max_iter=1000).root


def yield_from_price(bond: Bond, settlement: date, clean: float) -> dict[str, float]:
    fl = flows(bond, settlement)
    dirty = clean + fl.accrued
    if clean <= 0 or dirty <= 0:
        raise QfError("E_DOMAIN", "the dirty price must be positive", "clean_price")
    f = bond.frequency
    floor = -f * (1 - 1e-12)

    def gap(y: float) -> float:
        return _from_yield(fl, f, y)[0] - dirty

    low = 0.0
    while gap(low) <= 0 and low > floor:
        low = max(floor, low - 0.5 * (low - floor) - 1e-3)
    y = _root_decreasing(gap, low, max(low + 0.01, 0.1))
    return {"yield": y, "dirty": dirty, "accrued": fl.accrued}


def _curve_dirty(fl: Flows, curve: Curve, settlement: date, z: float) -> float:
    def ds(d: date) -> float:
        return curve.discount(d) * math.exp(-z * curve.time(d))

    return ordered_sum(cf * ds(d) for d, cf in zip(fl.dates, fl.amounts, strict=True)) \
        / ds(settlement)


def _curve_setup(bond: Bond, settlement: date, data: CurveData) -> tuple[Flows, Curve]:
    curve = curves.build(data)
    fl = flows(bond, settlement)
    if settlement < curve.as_of:
        raise QfError("E_OUT_OF_RANGE", "settlement is before the curve date", "settlement")
    return fl, curve


def price_from_curve(bond: Bond, settlement: date, data: CurveData) -> dict[str, float]:
    fl, curve = _curve_setup(bond, settlement, data)
    dirty = _curve_dirty(fl, curve, settlement, 0.0)
    return {"dirty": dirty, "accrued": fl.accrued, "clean": dirty - fl.accrued}


def z_spread(bond: Bond, settlement: date, data: CurveData, clean: float) -> float:
    fl, curve = _curve_setup(bond, settlement, data)
    target = clean + fl.accrued
    if target <= 0:
        raise QfError("E_DOMAIN", "the dirty price must be positive", "clean_price")

    def gap(z: float) -> float:
        return _curve_dirty(fl, curve, settlement, z) - target

    low = -0.1
    while gap(low) <= 0:
        low = low * 2
        if low < -100:
            raise QfError("E_NO_CONVERGENCE", "no bracket for the Z-spread")
    return _root_decreasing(gap, low, 0.1)


def asset_swap(bond: Bond, settlement: date, data: CurveData, dirty: float) -> tuple[float, float]:
    """Returns (annuity, spread)."""
    fl, curve = _curve_setup(bond, settlement, data)
    ends = []
    k = 0
    while (d := schedules.add_months(bond.maturity, -3 * k)) > settlement:
        ends.append(d)
        k += 1
    ends.reverse()
    starts = [settlement, *ends[:-1]]
    ds = curve.discount(settlement)
    annuity = ordered_sum((e - s).days / 360 * curve.discount(e) / ds
                          for s, e in zip(starts, ends, strict=True))
    p_curve = _curve_dirty(fl, curve, settlement, 0.0)
    return annuity, (p_curve - dirty) / (100 * annuity)


def frn_price(
    settlement: date, maturity: date, frequency: int, current_rate: float, margin: float,
    dm: float, discount_data: CurveData, projection_data: CurveData,
) -> dict[str, float]:
    d, p = curves.build(discount_data), curves.build(projection_data)
    prev, ends = dates_around(maturity, frequency, settlement)
    if settlement < d.as_of:
        raise QfError("E_OUT_OF_RANGE", "settlement is before the curve date", "settlement")

    def dm_df(x: date) -> float:
        return d.discount(x) * math.exp(-dm * d.time(x))

    starts = [prev, *ends[:-1]]
    terms = []
    for i, (s, e) in enumerate(zip(starts, ends, strict=True)):
        alpha = (e - s).days / 360
        r = current_rate if i == 0 else (p.discount(s) / p.discount(e) - 1) / alpha
        terms.append(100 * (r + margin) * alpha * dm_df(e))
    dirty = (ordered_sum(terms) + 100 * dm_df(maturity)) / dm_df(settlement)
    accrued = 100 * (current_rate + margin) * (settlement - prev).days / 360
    return {"dirty": dirty, "accrued": accrued, "clean": dirty - accrued}


def _repo_setup(bond: Bond, start: date, end: date) -> tuple[float, float, list[tuple[date, float]]]:
    if end <= start:
        raise QfError("E_DATE_ORDER", "end is not after start", "end")
    if end >= bond.maturity:
        raise QfError("E_INPUT", "end must be before maturity", "end")
    fl = flows(bond, start)
    c = 100 * bond.coupon / bond.frequency
    paid = [(x, c) for x in fl.dates if start < x <= end]
    return fl.accrued, accrued_at(bond, end), paid


def repo_forward(
    bond: Bond, start: date, end: date, clean: float, r: float, gc: float | None
) -> dict[str, float | None]:
    acc0, acc1, paid = _repo_setup(bond, start, end)
    dirty = clean + acc0
    days = (end - start).days
    fwd = dirty * (1 + r * days / 360) - ordered_sum(
        c * (1 + r * (end - x).days / 360) for x, c in paid)
    return {
        "dirty": dirty, "forward_dirty": fwd, "forward_clean": fwd - acc1,
        "interest": dirty * r * days / 360,
        "special_spread": None if gc is None else gc - r,
        "specialness_value": None if gc is None else dirty * (gc - r) * days / 360,
    }


def _implied(dirty: float, fwd_dirty: float, end: date, days: int,
             paid: Sequence[tuple[date, float]]) -> float:
    top = fwd_dirty + ordered_sum(c for _, c in paid) - dirty
    bottom = dirty * days / 360 - ordered_sum(c * (end - x).days / 360 for x, c in paid)
    if bottom == 0:
        raise QfError("E_DOMAIN", "the implied repo rate is undefined")
    return top / bottom


def repo_implied(bond: Bond, start: date, end: date, clean: float, fwd_clean: float) -> float:
    acc0, acc1, paid = _repo_setup(bond, start, end)
    return _implied(clean + acc0, fwd_clean + acc1, end, (end - start).days, paid)


def conversion_factor(bond: Bond, year: int, month: int, notional: float) -> float:
    if notional != 0.06:
        raise QfError("E_INPUT", "notional_coupon must be 0.06", "notional_coupon")
    if bond.frequency != 2:
        raise QfError("E_INPUT", "only semi-annual bonds", "bond")
    first = date(year, month, 1)
    if bond.maturity <= first:
        raise QfError("E_DATE_ORDER", "maturity is not after the delivery month", "bond")
    m = bond.maturity
    total = (m.year - first.year) * 12 + (m.month - first.month)
    n, z = total // 12, (total % 12) // 3 * 3
    v = z if z < 7 else 3
    a = 1.03 ** (-v / 6)
    b = (bond.coupon / 2) * (6 - v) / 6
    big_c = 1.03 ** (-2 * n) if z < 7 else 1.03 ** (-2 * n - 1)
    cf = a * (bond.coupon / 2 + (bond.coupon / 0.06) * (1 - big_c) + big_c) - b
    return round(cf, 4)


def _num(v: float | None) -> float:
    assert v is not None
    return v


def futures_basis(
    price: float, settlement: date, delivery: date, r: float,
    bonds: Sequence[tuple[Bond, float, float]],
) -> tuple[list[dict[str, float]], int]:
    out = []
    for bond, clean, cf in bonds:
        forward = repo_forward(bond, settlement, delivery, clean, r, None)
        acc0, acc1, paid = _repo_setup(bond, settlement, delivery)
        invoice = price * cf + acc1
        dirty = clean + acc0
        out.append({
            "invoice": invoice, "gross_basis": clean - price * cf,
            "net_basis": _num(forward["forward_dirty"]) - invoice,
            "implied_repo": _implied(dirty, invoice, delivery, (delivery - settlement).days, paid),
        })
    if not out:
        raise QfError("E_INPUT", "no bonds", "bonds")
    ctd = max(range(len(out)), key=lambda j: out[j]["implied_repo"])
    return out, ctd


def fit_nelson_siegel(
    settlement: date, tau: float, bonds: Sequence[tuple[Bond, float]],
    weights: Sequence[float] | None,
) -> tuple[list[float], list[float]]:
    if weights is not None and len(weights) != len(bonds):
        raise QfError("E_INPUT", "weights need one per bond", "weights")
    w = list(weights) if weights is not None else [1.0] * len(bonds)
    if any(v < 0 for v in w):
        raise QfError("E_DOMAIN", "weights must not be negative", "weights")
    if sum(w) <= 0:
        raise QfError("E_DOMAIN", "weights sum to 0", "weights")
    if sum(1 for v in w if v > 0) < 3:
        raise QfError("E_INPUT", "need at least 3 positive weights", "weights")
    if tau <= 0:
        raise QfError("E_DOMAIN", "tau must be positive", "tau")
    sets = []
    for bond, _ in bonds:
        fl = flows(bond, settlement)
        sets.append([((d - settlement).days / 365, cf) for d, cf in zip(fl.dates, fl.amounts,
                                                                       strict=True)])
    market = [p for _, p in bonds]

    def model(beta: Sequence[float]) -> tuple[list[float], list[list[float]]]:
        values, jac = [], []
        for cfs in sets:
            v, g = 0.0, [0.0, 0.0, 0.0]
            for t, cf in cfs:
                x = _basis(t, tau)
                pv = cf * math.exp(-t * ordered_sum(b * e for b, e in zip(beta, x, strict=True)))
                v += pv
                for p in range(3):
                    g[p] -= t * x[p] * pv
            values.append(v)
            jac.append(g)
        return values, jac

    def objective(beta: Sequence[float]) -> float:
        return ordered_sum(wj * (m - y) ** 2
                           for wj, m, y in zip(w, model(beta)[0], market, strict=True))

    beta, lam = [0.03, 0.0, 0.0], 1e-3
    current = objective(beta)
    for _ in range(500):
        values, jac = model(beta)
        r = [m - y for m, y in zip(values, market, strict=True)]
        a = [[ordered_sum(wj * g[p] * g[q] for wj, g in zip(w, jac, strict=True))
              for q in range(3)] for p in range(3)]
        grad = [ordered_sum(wj * g[p] * rj for wj, g, rj in zip(w, jac, r, strict=True))
                for p in range(3)]
        improved = False
        for _ in range(60):
            damped = [[a[p][q] * (1 + lam if p == q else 1) for q in range(3)] for p in range(3)]
            step = linalg.lu_solve(damped, [-v for v in grad])
            trial = [b + s for b, s in zip(beta, step, strict=True)]
            value = objective(trial)
            if value <= current:
                improved = max(abs(s) for s in step) > 1e-15
                beta, current, lam = trial, value, max(lam / 10, 1e-12)
                break
            lam *= 10
        if not improved:
            break
    values, _ = model(beta)
    return beta, [m - y for m, y in zip(values, market, strict=True)]
