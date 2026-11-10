"""Use case 3: from option quotes to an SVI surface and a priced target
(specifications/04-pricing/use-cases.md)."""
import itertools
import math
from collections.abc import Sequence
from datetime import date
from typing import Any

from . import curves, equity, smile
from .black import BLACK_76, Option, black76_position, implied
from .curves import CurveData
from .equity import ParityQuote
from .errors import QfError
from .finite import guard


def vol_surface(
    as_of: date, funding: CurveData, slices: Sequence[tuple[date, Sequence[ParityQuote]]],
    k_grid: Sequence[float], target: tuple[str, float, date, float, str],
) -> dict[str, Any]:
    if not slices or not k_grid or not all(quotes for _, quotes in slices):
        raise QfError("E_INPUT", "slices, k_grid and quotes must not be empty", "slices")
    curve = curves.build(funding)
    if funding.as_of != as_of:
        raise QfError("E_INPUT", "the curve as_of differs from as_of", "as_of")
    if any(a[0] >= b[0] for a, b in itertools.pairwise(slices)):
        raise QfError("E_INPUT", "slices must be in expiry order", "slices")
    forwards, rmses, times, discounts, fits = [], [], [], [], []
    for expiry, quotes in slices:
        t = (expiry - as_of).days / 365
        d = curve.discount(expiry)
        f = equity.parity(quotes, d)[0]
        ks, ws = [], []
        for q in quotes:
            is_call = q.strike >= f
            mid = (q.call_bid + q.call_ask) / 2 if is_call else (q.put_bid + q.put_ask) / 2
            o = Option(BLACK_76, "CALL" if is_call else "PUT", q.strike, t, f, discount_factor=d)
            v = implied(o, mid)
            ks.append(math.log(q.strike / f))
            ws.append(v * v * t)
        fit, rmse = smile.svi_calibrate(ks, ws, None)
        forwards.append(f)
        rmses.append(rmse)
        times.append(t)
        discounts.append(d)
        fits.append(fit)
    vols = [
        [math.sqrt(p.total_variance(k) / t) for k in k_grid]
        for p, t in zip(fits, times, strict=True)
    ]
    check = smile.surface_check(smile.Surface(times, list(k_grid), vols))
    option_type, strike, expiry, quantity, side = target
    index = next((n for n, s in enumerate(slices) if s[0] == expiry), None)
    if index is None:
        raise QfError("E_INPUT", "target.expiry is not a slice's", "target")
    if strike <= 0:
        raise QfError("E_DOMAIN", "strike must be positive", "target")
    if quantity <= 0:
        raise QfError("E_DOMAIN", "quantity must be positive", "target")
    f, t = forwards[index], times[index]
    vol = math.sqrt(fits[index].total_variance(math.log(strike / f)) / t)
    signed = quantity if side == "BUY" else -quantity
    pv, delta, vega = black76_position(option_type, f, strike, discounts[index], t, vol, signed)
    return {
        "forwards": forwards, "svi_rmse": rmses, "arbitrage_free": check["arbitrage_free"],
        "vol": vol, "pv": pv, "delta": delta, "vega": vega,
    }


guard(globals())
