"""CSA discounting, OIS index basis and the joint bootstrap
(specifications/02-curves/csa-and-basis.md)."""
import math
from collections.abc import Sequence
from datetime import date

from . import curves, ois, projection
from .curves import CurveData
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum
from .ois import Quote
from .projection import ProjectionQuote

Fx = tuple[float, Sequence[tuple[date, float]]] | None


def discount(
    data: CurveData, spread: float, fx: Fx, dates: Sequence[date]
) -> list[float]:
    curve = curves.build(data)
    forwards: dict[date, float] = {}
    if fx is not None:
        spot, points = fx
        if not spot > 0 or any(not f > 0 for _, f in points):
            raise QfError("E_DOMAIN", "spot and forwards must be positive", "fx")
        for d, f in points:
            if d in forwards:
                raise QfError("E_INPUT", f"two forwards on {d}", "fx")
            forwards[d] = f
        if any(d not in forwards for d in dates):
            raise QfError("E_INPUT", "a date has no FX forward", "fx")
    out = []
    for d in dates:
        value = curve.discount(d) * math.exp(-spread * curve.time(d))
        if fx is not None:
            value *= fx[0] / forwards[d]
        out.append(value)
    return out


def ois_spread(
    convention: str, tenor: str, discount_data: CurveData, a_data: CurveData, b_data: CurveData
) -> float:
    d, a, b = (curves.build(x) for x in (discount_data, a_data, b_data))
    if not d.as_of == a.as_of == b.as_of:
        raise QfError("E_INPUT", "the curves must share one as_of", "discount")
    ps = ois.periods(convention, d.as_of, tenor)
    annuity, _ = ois.legs(convention, ps, d)
    leg_b = ordered_sum(
        (b.discount(p.start) / b.discount(p.end) - 1) * d.discount(p.payment) for p in ps
    )
    leg_a = ordered_sum(
        (a.discount(p.start) / a.discount(p.end) - 1) * d.discount(p.payment) for p in ps
    )
    return (leg_a - leg_b) / annuity


def joint_bootstrap(
    convention: str, index: str, as_of: date, ois_quotes: Sequence[Quote],
    term_quotes: Sequence[ProjectionQuote], interpolation: str, method: str,
) -> tuple[CurveData, CurveData, float]:
    """Block triangular: the OIS block is solved first, then the term block on it (ruling D9)."""
    if not ois_quotes or not term_quotes:
        raise QfError("E_INPUT", "both quote lists need quotes", "ois_quotes")
    disc, e1 = ois.bootstrap(convention, as_of, ois_quotes, interpolation, method)
    proj, e2 = projection.bootstrap(disc, index, as_of, term_quotes, interpolation)
    return disc, proj, max(e1, e2)


guard(globals())
