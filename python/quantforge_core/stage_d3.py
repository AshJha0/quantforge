"""Stage D wave 3: caps and swaptions (specifications/05-volatility/caps-and-swaptions.md),
commodity curves (specifications/02-curves/commodity.md) and MBS (specifications/04-pricing/mbs.md)."""
import itertools
import math
from collections.abc import Sequence
from datetime import date

from . import black, curves, daycount, projection
from .black import Option
from .curves import CurveData
from .errors import QfError
from .numeric import ordered_sum

INDEX = "USD-TERM-3M"


# D7 caps and swaptions

def _option(model: str, call: bool, f: float, k: float, vol: float, t: float) -> float:
    return black.price(Option(model, "CALL" if call else "PUT", k, t, f), vol)


def _check_black(model: str, strike: float, forwards: Sequence[float]) -> None:
    if model == black.BLACK_76 and (strike <= 0 or any(f <= 0 for f in forwards)):
        raise QfError("E_DOMAIN", "BLACK_76 needs a positive strike and forwards", "strike")


def _check_tenor(months: int) -> None:
    if not 1 <= months <= 1200:
        raise QfError("E_INPUT", "tenor_months must be 1 to 1200", "tenor_months")


def cap_price(
    discount: CurveData, proj: CurveData, model: str, vol: float | Sequence[float], kind: str,
    start_months: int, tenor_months: int, strike: float, notional: float,
) -> tuple[list[float], float]:
    d, p = curves.build(discount), curves.build(proj)
    if start_months < 1:
        raise QfError("E_INPUT", "start_months must be at least 1", "start_months")
    start = projection._plus_months(INDEX, projection._spot(INDEX, d.as_of), start_months)
    _check_tenor(tenor_months)
    ps = projection._float_periods(INDEX, start, tenor_months)
    vols = [vol] * len(ps) if isinstance(vol, float) else list(vol)
    if len(vols) != len(ps):
        raise QfError("E_INPUT", "one vol per caplet", "vol")
    if any(v < 0 for v in vols):
        raise QfError("E_DOMAIN", "a vol is negative", "vol")
    alphas = [daycount.year_fraction("ACT_360", x.start, x.end) for x in ps]
    forwards = [(p.discount(x.start) / p.discount(x.end) - 1) / a
                for x, a in zip(ps, alphas, strict=True)]
    _check_black(model, strike, forwards)
    caplets = [
        notional * a * d.discount(x.end)
        * _option(model, kind == "CAP", f, strike, v, d.time(x.start))
        for x, a, f, v in zip(ps, alphas, forwards, vols, strict=True)
    ]
    return caplets, ordered_sum(caplets)


def swaption_price(
    discount: CurveData, proj: CurveData, model: str, vol: float, kind: str,
    expiry_months: int, tenor_months: int, strike: float, notional: float,
) -> tuple[float, float, float]:
    d, p = curves.build(discount), curves.build(proj)
    if expiry_months < 1:
        raise QfError("E_INPUT", "expiry_months must be at least 1", "expiry_months")
    _check_tenor(tenor_months)
    s = projection._plus_months(INDEX, projection._spot(INDEX, d.as_of), expiry_months)
    if vol < 0:
        raise QfError("E_DOMAIN", "vol is negative", "vol")
    fixed = projection._fixed_periods(INDEX, s, tenor_months)
    floating = projection._float_periods(INDEX, s, tenor_months)
    annuity, leg = projection._swap_legs(INDEX, fixed, floating, d, p)
    forward = leg / annuity
    _check_black(model, strike, [forward])
    value = notional * annuity * _option(model, kind == "PAYER", forward, strike, vol, d.time(s))
    return value, forward, annuity


# D8 commodities

def commodity_forwards(
    quotes: Sequence[tuple[int, float]], seasonality: Sequence[float] | None,
    months: Sequence[int],
) -> list[float]:
    if not quotes or any(b <= a for (a, _), (b, _) in itertools.pairwise(quotes)):
        raise QfError("E_INPUT", "quote months must be strictly increasing", "quotes")
    if any(v <= 0 for _, v in quotes):
        raise QfError("E_DOMAIN", "prices must be positive", "quotes")
    if seasonality is not None and len(seasonality) != 12:
        raise QfError("E_INPUT", "seasonality needs 12 terms", "seasonality")

    def sigma(k: int) -> float:
        return 0.0 if seasonality is None else seasonality[k % 12]

    ks = [k for k, _ in quotes]
    ls = [math.log(v) - sigma(k) for k, v in quotes]
    out = []
    for k in months:
        if not ks[0] <= k <= ks[-1]:
            raise QfError("E_OUT_OF_RANGE", "a month is outside the quoted range", "months")
        i = min(max(j for j in range(len(ks)) if ks[j] <= k), max(len(ks) - 2, 0))
        if len(ks) == 1:
            level = ls[0]
        else:
            level = ls[i] + (ls[i + 1] - ls[i]) * (k - ks[i]) / (ks[i + 1] - ks[i])
        out.append(math.exp(level + sigma(k)))
    return out


def storage_carry(
    funding: CurveData, forwards: Sequence[tuple[date, float]], u: float,
) -> tuple[list[float], list[float], list[bool]]:
    c = curves.build(funding)
    if len(forwards) < 2 or any(
            b <= a for a, b in itertools.pairwise([c.as_of, *(d for d, _ in forwards)])):
        raise QfError("E_INPUT", "need two or more forwards, increasing after as_of", "forwards")
    if u < 0:
        raise QfError("E_DOMAIN", "storage_cost must not be negative", "storage_cost")
    if any(f <= 0 for _, f in forwards):
        raise QfError("E_DOMAIN", "forward prices must be positive", "forwards")
    ys, values = [], []
    for (d0, f0), (d1, f1) in itertools.pairwise(forwards):
        dt = (d1 - d0).days / 365
        p0, p1 = c.discount(d0), c.discount(d1)
        r = math.log(p0 / p1) / dt
        ys.append(r + u - math.log(f1 / f0) / dt)
        values.append(p1 * f1 - p0 * f0 * math.exp(u * dt))
    return ys, values, [v > 0 for v in values]


# D9 MBS

Pool = tuple[float, float, float, int, int, str, float]
Flows = tuple[list[float], list[float], list[float], list[float], float]


def mbs_cashflows(pool: Pool) -> dict[str, object]:
    bal, interest, sched, prepay, wal = _flows(pool)
    return {"balance": bal, "interest": interest, "scheduled_principal": sched,
            "prepayment": prepay, "wal": wal}


def _flows(pool: Pool) -> Flows:
    balance, wac, net, wam, age, model, speed = pool
    if not 1 <= wam <= 1200 or age < 0:
        raise QfError("E_INPUT", "wam must be at least 1 and age at least 0", "pool")
    if wac <= 0:
        raise QfError("E_DOMAIN", "wac must be positive", "wac")
    if net > wac:
        raise QfError("E_INPUT", "net_coupon is above wac", "net_coupon")
    if balance <= 0 or (model == "CPR" and not 0 <= speed < 1) or (model == "PSA" and speed < 0):
        raise QfError("E_DOMAIN", "balance, rate or speed out of domain", "pool")
    r = wac / 12
    b = balance
    bal, interest, sched, prepay = [], [], [], []
    for k in range(1, wam + 1):
        n = wam - k + 1
        cpr = speed if model == "CPR" else min((age + k) / 30, 1) * 0.06 * speed / 100
        smm = 1 - (1 - cpr) ** (1 / 12)
        if k == wam:
            sp = b
        else:
            sp = b * r / (1 - (1 + r) ** (-n)) - b * r
        pp = smm * (b - sp)
        bal.append(b)
        interest.append(b * net / 12)
        sched.append(sp)
        prepay.append(pp)
        b = b - sp - pp
    wal = ordered_sum(k / 12 * (s + p) for k, (s, p) in enumerate(zip(sched, prepay, strict=True),
                                                                   start=1)) / balance
    return bal, interest, sched, prepay, wal


def mbs_price(pool: Pool, y: float, delay_days: int) -> tuple[float, float, float]:
    _, ints, sched, pre, wal = _flows(pool)
    if delay_days < 0:
        raise QfError("E_INPUT", "delay_days must not be negative", "delay_days")
    if not 1 + y / 12 > 0:
        raise QfError("E_DOMAIN", "1 + yield/12 must be positive", "yield")
    v = 1 / (1 + y / 12)
    terms = []
    for k, (a, b, c) in enumerate(zip(ints, sched, pre, strict=True), start=1):
        t = k + delay_days / 30
        terms.append((t, (a + b + c) * v ** t))
    pv = ordered_sum(x for _, x in terms)
    duration = ordered_sum(t / 12 * x * v for t, x in terms) / pv
    return 100 * pv / pool[0], duration, wal
