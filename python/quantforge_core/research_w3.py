"""Stage J wave 3 operations (rulings J-W3-1 to J-W3-9): the scenario stress engine
(06-risk/scenario-stress.md) and the interpolation backtests (11-research/interp-backtest.md)."""
import itertools
import math
from collections.abc import Sequence
from datetime import date
from typing import Any

from . import interp
from .errors import QfError
from .finite import guard

Matrix = Sequence[Sequence[float]]
LOO_METHODS = ("linear", "log_linear", "cubic_natural", "monotone_pchip")
SURFACE_METHODS = ("linear", "cubic_natural", "monotone_pchip")


def _tenors(t: Sequence[float], field: str) -> None:
    if any(not v > 0 for v in t) or any(b <= a for a, b in itertools.pairwise(t)):
        raise QfError("E_DOMAIN", f"{field} must be positive and strictly increasing", field)


# --- Scenarios (J-W3-2 to J-W3-5) ---------------------------------------------------------------

def scenario_historical_shock(dates: Sequence[date], tenors: Sequence[float], yields: Matrix,
                              start: date, end: date) -> dict[str, Any]:
    n = len(tenors)
    if not dates or n == 0 or len(yields) != len(dates) or any(len(r) != n for r in yields):
        raise QfError("E_INPUT", "need one row per date and one column per tenor", "yields")
    if any(b <= a for a, b in itertools.pairwise(dates)):
        raise QfError("E_DATE_ORDER", "dates must be strictly increasing", "dates")
    _tenors(tenors, "tenors")
    if end <= start:
        raise QfError("E_DATE_ORDER", "end_date must be after start_date", "end_date")
    index = {d: i for i, d in enumerate(dates)}
    for d, field in ((start, "start_date"), (end, "end_date")):
        if d not in index:
            raise QfError("E_DOMAIN", f"{field} is not in dates", field)
    y0, y1 = list(yields[index[start]]), list(yields[index[end]])
    shift = [100.0 * (b - a) for a, b in zip(y0, y1, strict=True)]
    return {"start_yields": y0, "end_yields": y1, "shift_bp": shift,
            "level_bp": math.fsum(shift) / n, "slope_bp": shift[-1] - shift[0]}


def _flat_linear(x: Sequence[float], y: Sequence[float], t: float) -> float:
    if t <= x[0]:
        return y[0]
    if t >= x[-1]:
        return y[-1]
    i = max(j for j in range(len(x) - 1) if x[j] <= t)
    u = (t - x[i]) / (x[i + 1] - x[i])
    return y[i] + u * (y[i + 1] - y[i])


def scenario_replay(base_tenors: Sequence[float], base_yields: Sequence[float],
                    shock_tenors: Sequence[float], shock_bp: Sequence[float], scale: float = 1.0,
                    dv01: Sequence[float] | None = None) -> dict[str, Any]:
    if not base_tenors or len(base_yields) != len(base_tenors):
        raise QfError("E_INPUT", "base_yields must match base_tenors", "base_yields")
    if not shock_tenors or len(shock_bp) != len(shock_tenors):
        raise QfError("E_INPUT", "shock_bp must match shock_tenors", "shock_bp")
    if dv01 is not None and len(dv01) != len(base_tenors):
        raise QfError("E_INPUT", "dv01 must match base_tenors", "dv01")
    _tenors(base_tenors, "base_tenors")
    _tenors(shock_tenors, "shock_tenors")
    applied = [scale * _flat_linear(shock_tenors, shock_bp, t) for t in base_tenors]
    out: dict[str, Any] = {"applied_bp": applied,
                           "shocked_yields": [y + a / 100.0 for y, a in zip(base_yields, applied, strict=True)]}
    if dv01 is not None:
        out["pnl"] = -math.fsum(d * a for d, a in zip(dv01, applied, strict=True))
    return out


# --- Interpolation backtests (J-W3-8, J-W3-9) --------------------------------------------------

def _summary(errors: Sequence[float]) -> tuple[float, float]:
    return max(abs(e) for e in errors), math.sqrt(math.fsum(e * e for e in errors) / len(errors))


def backtest_interp_loo(method: str, x: Sequence[float], y: Sequence[float]) -> dict[str, Any]:
    n = len(x)
    if len(y) != n or n < 3 or n - 1 < interp.MIN_KNOTS[method]:
        raise QfError("E_INPUT", "need equal lengths, n >= 3 and n - 1 at the method's minimum knots", "x")
    if any(b <= a for a, b in itertools.pairwise(x)):
        raise QfError("E_INPUT", "knots must be strictly increasing", "x")
    errors = []
    for i in range(1, n - 1):
        xs, ys = list(x[:i]) + list(x[i + 1:]), list(y[:i]) + list(y[i + 1:])
        errors.append(interp.evaluate(method, xs, ys, [x[i]])[0][0] - y[i])
    mx, rmse = _summary(errors)
    return {"errors": errors, "max_abs_error": mx, "rmse": rmse}


def backtest_surface_holdout(method: str, expiries: Sequence[float], strikes: Sequence[float],
                             vols: Matrix, holdout: Sequence[int]) -> dict[str, Any]:
    m = len(strikes)
    if not expiries or len(vols) != len(expiries) or any(len(r) != m for r in vols):
        raise QfError("E_INPUT", "vols must have one row per expiry and one column per strike", "vols")
    if any(b <= a for a, b in itertools.pairwise(strikes)):
        raise QfError("E_INPUT", "strikes must be strictly increasing", "strikes")
    if not holdout or any(not 0 < h < m - 1 for h in holdout) or any(b <= a for a, b in itertools.pairwise(holdout)):
        raise QfError("E_INPUT", "holdout must be distinct sorted interior strike indices", "holdout")
    kept = [j for j in range(m) if j not in set(holdout)]
    if len(kept) < interp.MIN_KNOTS[method]:
        raise QfError("E_INPUT", "too few kept strikes for the method", "holdout")
    if any(not t > 0 for t in expiries):
        raise QfError("E_DOMAIN", "expiries must be positive", "expiries")
    if any(not v > 0 for r in vols for v in r):
        raise QfError("E_DOMAIN", "vols must be positive", "vols")
    errors: list[list[float]] = []
    for t, row in zip(expiries, vols, strict=True):
        w = [row[j] * row[j] * t for j in kept]
        fit = interp.evaluate(method, [strikes[j] for j in kept], w, [strikes[h] for h in holdout])[0]
        if any(not v > 0 for v in fit):
            raise QfError("E_DOMAIN", "interpolated total variance is not positive", "vols")
        errors.append([math.sqrt(v / t) - row[h] for v, h in zip(fit, holdout, strict=True)])
    mx, rmse = _summary([e for r in errors for e in r])
    return {"errors": errors, "max_abs_error": mx, "rmse": rmse}


guard(globals())
