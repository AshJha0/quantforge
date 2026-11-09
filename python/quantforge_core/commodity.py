"""Commodity forward curves and storage carry (specifications/02-curves/commodity.md)."""
import itertools
import math
from collections.abc import Sequence
from datetime import date

from . import curves
from .curves import CurveData
from .errors import QfError


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
