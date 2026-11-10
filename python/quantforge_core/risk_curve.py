"""Par and key-rate risk, the bootstrap Jacobian and P&L explain, by bump and revalue
(specifications/06-risk/par-and-key-rate.md, specifications/06-risk/pnl-explain.md)."""
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date

from . import bonds, curves, ois
from .curves import Curve, CurveData
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum
from .ois import OisTrade, Quote

BP = 1e-4
SCHEMES = ("CENTRAL", "FORWARD")
MODES = ("TRIANGULAR", "PILLAR")


@dataclass(frozen=True)
class Product:
    """kind OIS: trade. kind BOND: bond, settlement, notional (face)."""

    kind: str
    trade: OisTrade | None = None
    bond: bonds.Bond | None = None
    settlement: date | None = None
    notional: float = 0.0

    @property
    def size(self) -> float:
        """N, the notional of the floor term in the P&L threshold."""
        return self.trade.notional if self.trade is not None else self.notional


class _Shifted:
    """D(t) exp(-s(t) t): a zero-rate shift s on a built curve, jumps and interpolation kept."""

    def __init__(self, base: Curve, shift: Callable[[float], float]):
        self.base, self.shift, self.as_of = base, shift, base.as_of

    def time(self, d: date) -> float:
        return self.base.time(d)

    def discount(self, d: date) -> float:
        t = self.base.time(d)
        return self.base.discount(d) * math.exp(-self.shift(t) * t)


Pricer = Callable[[Curve], float]


def check_bump(bump_bp: float, product: Product) -> None:
    if not 0 < bump_bp <= 100:
        raise QfError("E_DOMAIN", "bump_bp must be in (0, 100]", "bump_bp")
    if product.kind == "BOND" and not product.notional > 0:
        raise QfError("E_DOMAIN", "notional must be positive", "product.notional")


def _check_convention(product: Product, convention: str) -> None:
    if product.trade is not None and product.trade.convention != convention:
        raise QfError("E_INPUT", "the trade convention differs from the curve's", "product")


def pricer(product: Product, as_of: date) -> Pricer:
    """Fixes the product's own dates, so only the curve moves."""
    if product.trade is not None:
        trade = product.trade
        ps = ois.periods(trade.convention, as_of, trade.tenor)
        return lambda c: ois.trade_pv(trade, ps, c)[0]
    bond, settlement = product.bond, product.settlement
    assert bond is not None and settlement is not None
    fl = bonds.flows(bond, settlement)
    if settlement < as_of:
        raise QfError("E_OUT_OF_RANGE", "settlement is before the curve date", "settlement")
    notional = product.notional
    return lambda c: notional * bonds._curve_dirty(fl, c, settlement, 0.0) / 100


def _risk(value: Callable[[float], float], v0: float, bump_bp: float, scheme: str) -> float:
    """value(s) prices with every bumped input moved by s bp (s = +h or -h)."""
    up = value(bump_bp)
    if scheme == "FORWARD":
        return (up - v0) / bump_bp
    return (up - value(-bump_bp)) / (2 * bump_bp)


def _rebuild(convention: str, as_of: date, quotes: Sequence[Quote], interpolation: str,
             shifts: Sequence[float]) -> Curve:
    moved = [Quote(q.tenor, q.mid + s) for q, s in zip(quotes, shifts, strict=True)]
    return curves.build(ois.bootstrap(convention, as_of, moved, interpolation)[0])


def _par(price: Pricer, convention: str, as_of: date, quotes: Sequence[Quote],
         interpolation: str, bump_bp: float, scheme: str) -> tuple[float, float, list[float]]:
    v0 = price(_rebuild(convention, as_of, quotes, interpolation, [0.0] * len(quotes)))
    n = len(quotes)

    def moved(only: int | None) -> Callable[[float], float]:
        def value(s: float) -> float:
            shifts = [s * BP if only is None or k == only else 0.0 for k in range(n)]
            return price(_rebuild(convention, as_of, quotes, interpolation, shifts))
        return value

    parallel = _risk(moved(None), v0, bump_bp, scheme)
    buckets = [_risk(moved(j), v0, bump_bp, scheme) for j in range(n)]
    return v0, parallel, buckets


def par(as_of: date, convention: str, quotes: Sequence[Quote], interpolation: str,
        product: Product, bump_bp: float, scheme: str) -> dict[str, object]:
    check_bump(bump_bp, product)
    _check_convention(product, convention)
    ois._check_quotes(convention, as_of, quotes)
    price = pricer(product, as_of)
    v0, parallel, buckets = _par(price, convention, as_of, quotes, interpolation, bump_bp, scheme)
    return {"value": v0, "par_dv01": parallel, "par_buckets": buckets}


def _triangle(keys: Sequence[float], i: int) -> Callable[[float], float]:
    n = len(keys)

    def w(t: float) -> float:
        k = keys[i]
        if t <= k:
            if i == 0:
                return 1.0
            lo = keys[i - 1]
            return 0.0 if t <= lo else (t - lo) / (k - lo)
        if i == n - 1:
            return 1.0
        hi = keys[i + 1]
        return 0.0 if t >= hi else (hi - t) / (hi - k)

    return w


def key_rate(data: CurveData, mode: str, key_dates: Sequence[date] | None, product: Product,
             bump_bp: float, scheme: str) -> dict[str, object]:
    check_bump(bump_bp, product)
    if mode == "TRIANGULAR":
        if not key_dates:
            raise QfError("E_INPUT", "TRIANGULAR needs at least 1 key date", "key_dates")
        previous = data.as_of
        for d in key_dates:
            if d <= previous:
                raise QfError("E_INPUT", "key dates must be increasing and after as_of",
                              "key_dates")
            previous = d
    elif key_dates is not None:
        raise QfError("E_INPUT", "PILLAR takes no key dates", "key_dates")
    base = curves.build(data)
    price = pricer(product, data.as_of)
    v0 = price(base)

    def shifted(weight: Callable[[float], float]) -> Callable[[float], float]:
        return lambda s: price(_Shifted(base, lambda t: weight(t) * s * BP))  # type: ignore[arg-type]

    def pillar(i: int) -> Callable[[float], float]:
        def value(s: float) -> float:
            t = (data.dates[i] - data.as_of).days / 365
            factors = list(data.discount_factors)
            factors[i] = factors[i] * math.exp(-s * BP * t)
            return price(curves.build(replace(data, discount_factors=tuple(factors))))
        return value

    if mode == "TRIANGULAR":
        assert key_dates is not None
        keys = [(d - data.as_of).days / 365 for d in key_dates]
        bucket_values = [shifted(_triangle(keys, i)) for i in range(len(keys))]
    else:
        bucket_values = [pillar(i) for i in range(len(data.dates))]
    return {
        "value": v0,
        "key_rates": [_risk(v, v0, bump_bp, scheme) for v in bucket_values],
        "zero_dv01": _risk(shifted(lambda t: 1.0), v0, bump_bp, scheme),
    }


def jacobian(as_of: date, convention: str, quotes: Sequence[Quote], interpolation: str,
             bump_bp: float) -> dict[str, object]:
    if not 0 < bump_bp <= 100:
        raise QfError("E_DOMAIN", "bump_bp must be in (0, 100]", "bump_bp")
    n, h = len(quotes), bump_bp * BP

    def zeros(shifts: Sequence[float]) -> tuple[CurveData, list[float]]:
        moved = [Quote(q.tenor, q.mid + s) for q, s in zip(quotes, shifts, strict=True)]
        data = ois.bootstrap(convention, as_of, moved, interpolation)[0]
        return data, [-math.log(v) / ((d - as_of).days / 365)
                      for d, v in zip(data.dates, data.discount_factors, strict=True)]

    data, z0 = zeros([0.0] * n)
    columns = []
    for j in range(n):
        up = zeros([h if k == j else 0.0 for k in range(n)])[1]
        down = zeros([-h if k == j else 0.0 for k in range(n)])[1]
        columns.append([(u - d) / (2 * h) if i >= j else 0.0
                        for i, (u, d) in enumerate(zip(up, down, strict=True))])
    matrix = [[columns[j][i] for j in range(n)] for i in range(n)]
    return {"pillar_dates": [d.isoformat() for d in data.dates], "zero_rates": z0,
            "jacobian": matrix}


def pnl_explain(as_of: date, convention: str, interpolation: str, start: Sequence[Quote],
                end: Sequence[Quote], product: Product, bump_bp: float) -> dict[str, object]:
    check_bump(bump_bp, product)
    _check_convention(product, convention)
    ois._check_quotes(convention, as_of, start)
    if [q.tenor for q in start] != [q.tenor for q in end]:
        raise QfError("E_INPUT", "quotes_start and quotes_end differ in tenors", "quotes_end")
    ois._check_quotes(convention, as_of, end)
    price = pricer(product, as_of)
    v0, _, buckets = _par(price, convention, as_of, start, interpolation, bump_bp, "CENTRAL")
    v1 = price(_rebuild(convention, as_of, end, interpolation, [0.0] * len(end)))
    moves = [(e.mid - s.mid) / BP for s, e in zip(start, end, strict=True)]
    full = v1 - v0
    risk = ordered_sum(b * m for b, m in zip(buckets, moves, strict=True))
    gross = ordered_sum(abs(b) * abs(m) for b, m in zip(buckets, moves, strict=True))
    threshold = 0.05 * max(abs(full), gross) + 1e-8 * product.size
    unexplained = full - risk
    return {
        "value_start": v0, "value_end": v1, "full_pnl": full, "par_buckets": buckets,
        "risk_pnl": risk, "unexplained": unexplained, "gross_risk_pnl": gross,
        "threshold": threshold, "explained": abs(unexplained) <= threshold,
    }


guard(globals())
