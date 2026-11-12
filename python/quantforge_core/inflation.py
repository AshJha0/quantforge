"""Inflation curves, seasonality and linkers (specifications/02-curves/inflation.md)."""
import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date

from . import _cal, bonds, curves
from .bonds import Bond
from .curves import CurveData
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum


def index(year: int, month: int) -> int:
    return 12 * year + month - 1


@dataclass(frozen=True)
class CpiCurveData:
    base: int
    base_cpi: float
    quotes: tuple[tuple[float, float], ...]
    seasonality: tuple[float, ...] | None


class CpiCurve:
    def __init__(self, data: CpiCurveData):
        years = [y for y, _ in data.quotes]
        if not years or any(y <= 0 or y > 100 or y != int(y) for y in years) or any(
                b <= a for a, b in itertools.pairwise(years)):
            raise QfError("E_INPUT", "years must be strictly increasing positive integers",
                          "quotes")
        if any(r <= -1 for _, r in data.quotes):
            raise QfError("E_DOMAIN", "a rate is -1 or below", "quotes")
        if data.seasonality is not None:
            if len(data.seasonality) != 12:
                raise QfError("E_INPUT", "seasonality needs 12 factors", "seasonality")
            if any(s <= 0 for s in data.seasonality):
                raise QfError("E_DOMAIN", "seasonality factors must be positive", "seasonality")
        self.base, self.season = data.base, data.seasonality
        self.ks = [data.base, *(data.base + 12 * int(y) for y in years)]
        self.logs = [math.log(data.base_cpi),
                     *(math.log(data.base_cpi) + y * math.log1p(r) for y, r in data.quotes)]

    def cpi(self, k: int) -> float:
        if k < self.base:
            raise QfError("E_OUT_OF_RANGE", "a month is before base_month")
        ks, xs = self.ks, self.logs
        i = min(max(j for j in range(len(ks)) if ks[j] <= k), len(ks) - 2)
        value = math.exp(xs[i] + (xs[i + 1] - xs[i]) * (k - ks[i]) / (ks[i + 1] - ks[i]))
        if self.season is not None:
            value *= self.season[k % 12] / self.season[self.base % 12]
        return value


def cpi(data: CpiCurveData, months: Sequence[int]) -> list[float]:
    curve = CpiCurve(data)
    return [curve.cpi(k) for k in months]


def zcis_pv(data: CpiCurveData, discount: CurveData, years: int, fixed: float, notional: float,
            side: str, payment: date) -> tuple[float, float]:
    curve, disc = CpiCurve(data), curves.build(discount)
    ratio = curve.cpi(data.base + 12 * years) / data.base_cpi
    sign = 1 if side == "RECEIVE_INFLATION" else -1
    return sign * notional * (ratio - (1 + fixed) ** years) * disc.discount(payment), ratio


def _ref(d: date, get: Callable[[int], float]) -> float:
    """US TIPS reference CPI: three-month lag, daily interpolation."""
    k = index(d.year, d.month)
    i3, i2 = get(k - 3), get(k - 2)
    days = _cal.monthrange(d.year, d.month)[1]
    return i3 + (d.day - 1) / days * (i2 - i3)


def _trunc6(x: float) -> float:
    return math.floor(x * 1e6) / 1e6


def _round5(t: float) -> float:
    return math.floor(t * 1e5 + 0.5) / 1e5


def linker_price(bond: Bond, settlement: date, real_yield: float, base_ref: float,
                 fixings: Sequence[tuple[int, float]]) -> dict[str, float]:
    real = bonds.price_from_yield(bond, settlement, real_yield)
    table = dict(fixings)
    if len(table) != len(fixings):
        raise QfError("E_INPUT", "two fixings for one month", "cpi_fixings")

    def get(k: int) -> float:
        if k not in table:
            raise QfError("E_INPUT", "a needed CPI fixing is missing", "cpi_fixings")
        return table[k]

    # Ruling R6-7.5 (31 CFR 356 App. B): truncate to six decimals, round half up to five.
    ref = _round5(_trunc6(_ref(settlement, get)))
    ratio = _round5(_trunc6(ref / base_ref))
    return {"ref_cpi": ref, "index_ratio": ratio, "real_clean": real["clean"],
            "real_accrued": real["accrued"], "nominal_clean": real["clean"] * ratio,
            "nominal_accrued": real["accrued"] * ratio}


def linker_price_curve(bond: Bond, settlement: date, base_ref: float, data: CpiCurveData,
                       discount: CurveData) -> float:
    curve, disc = CpiCurve(data), curves.build(discount)
    fl = bonds.flows(bond, settlement)
    total = ordered_sum(cf * _ref(d, curve.cpi) / base_ref * disc.discount(d)
                        for d, cf in zip(fl.dates, fl.amounts, strict=True))
    return total / disc.discount(settlement)


guard(globals())
