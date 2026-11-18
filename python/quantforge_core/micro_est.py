"""Microstructure estimators with planted truth (specifications/09-microstructure/micro-estimators.md,
stage H H-4b; rulings HR-70, HR-71, HR-74, HR-75).

Each estimator returns its point estimate and a standard error `se`. Sums use `math.fsum`, so an
exact fit (HR-74) gives SE 0 or a value at the rounding floor. Error order HR-75 as amended (HR-66): structural
`E_INPUT` (lengths, counts, labels), then `E_DOMAIN`, then value-dependent `E_INPUT`."""

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import QfError
from .finite import guard


def _fail(code: str, message: str, field: str) -> QfError:
    return QfError(code, message, field)


def ols_origin(x: Sequence[float], y: Sequence[float], field: str = "x") -> tuple[float, float]:
    """OLS through the origin: beta = sum x y / sum x^2, s2 = SSR / (n - 1), SE = sqrt(s2 / sum x^2)."""
    if len(x) != len(y) or len(x) < 2:
        raise _fail("E_INPUT", "x and y need equal lengths of at least 2", field)
    n = len(x)
    sxx = math.fsum(a * a for a in x)
    if sxx == 0:
        raise _fail("E_INPUT", "the sum of x^2 is 0", field)
    beta = math.fsum(a * b for a, b in zip(x, y, strict=True)) / sxx
    ssr = math.fsum((b - beta * a) ** 2 for a, b in zip(x, y, strict=True))
    return beta, math.sqrt(ssr / (n - 1) / sxx)


def _ols_slope(t: Sequence[float], y: Sequence[float], field: str) -> tuple[float, float]:
    """OLS with intercept; the slope and its SE with n - 2 degrees of freedom."""
    n = len(t)
    tm, ym = math.fsum(t) / n, math.fsum(y) / n
    stt = math.fsum((a - tm) ** 2 for a in t)
    if stt == 0:
        raise _fail("E_INPUT", "all abscissae are equal", field)
    slope = math.fsum((a - tm) * (b - ym) for a, b in zip(t, y, strict=True)) / stt
    icpt = ym - slope * tm
    ssr = math.fsum((b - icpt - slope * a) ** 2 for a, b in zip(t, y, strict=True))
    return slope, math.sqrt(ssr / (n - 2) / stt)


def arrival_rate(count: int, window: float) -> dict[str, Any]:
    """`micro.est.arrival_rate`: Poisson MLE lambda = N / T, SE = sqrt(lambda / T)."""
    if count < 0:
        raise _fail("E_DOMAIN", "count must be non-negative", "count")
    if window <= 0:
        raise _fail("E_DOMAIN", "window must be positive", "window")
    lam = count / window
    return {"lambda": lam, "se": math.sqrt(lam / window)}


def cancel_rate(orders: Sequence[tuple[float, str]]) -> dict[str, Any]:
    """`micro.est.cancel_rate`: censored exponential MLE theta = C / sum L, SE = theta / sqrt(C)."""
    if any(life <= 0 for life, _ in orders):
        raise _fail("E_DOMAIN", "lifetimes must be positive", "orders")
    c = sum(1 for _, outcome in orders if outcome == "CANCEL")
    if c == 0:
        raise _fail("E_INPUT", "no cancelled order", "orders")
    theta = c / math.fsum(life for life, _ in orders)
    return {"theta": theta, "se": theta / math.sqrt(c)}


def resilience(s_inf: float, points: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """`micro.est.resilience`: kappa = -slope of ln(S - S_inf) on t (OLS with intercept)."""
    if len(points) < 3:
        raise _fail("E_INPUT", "need at least 3 points", "points")
    if any(s <= s_inf for _, s in points):
        raise _fail("E_DOMAIN", "every spread must exceed s_inf", "points")
    slope, se = _ols_slope(
        [t for t, _ in points], [math.log(s - s_inf) for _, s in points], "points"
    )
    return {"kappa": -slope, "se": se}


def liquidity_decay(levels: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """`micro.est.liquidity_decay`: alpha = -slope of ln D on k (resilience with S_inf = 0)."""
    if len(levels) < 3:
        raise _fail("E_INPUT", "need at least 3 levels", "levels")
    if any(d <= 0 for _, d in levels):
        raise _fail("E_DOMAIN", "every depth must be positive", "levels")
    slope, se = _ols_slope([k for k, _ in levels], [math.log(d) for _, d in levels], "levels")
    return {"alpha": -slope, "se": se}


def adverse_selection(x: Sequence[float], y: Sequence[float]) -> dict[str, Any]:
    """`micro.est.adverse_selection`: dm = lambda_as s q + e, OLS through the origin."""
    beta, se = ols_origin(x, y)
    return {"lambda_as": beta, "se": se}


def regime_impact(regimes: Mapping[str, tuple[Sequence[float], Sequence[float]]]) -> dict[str, Any]:
    """`micro.est.regime_impact`: adverse selection per regime label; ratio stressed / calm."""
    for need in ("calm", "stressed"):
        if need not in regimes:
            raise _fail("E_INPUT", f"regime {need!r} is missing", "regimes")
    for label, (x, y) in regimes.items():
        if len(x) != len(y) or len(x) < 2:
            raise _fail("E_INPUT", "x and y need equal lengths of at least 2", f"regimes.{label}")
    out: dict[str, Any] = {}
    for label in sorted(regimes):
        x, y = regimes[label]
        beta, se = ols_origin(x, y, f"regimes.{label}")
        out[label] = {"lambda_as": beta, "se": se}
    calm = out["calm"]["lambda_as"]
    if calm == 0:
        raise _fail("E_DOMAIN", "calm lambda_as is 0; the ratio is undefined", "regimes")
    return {"regimes": out, "ratio": out["stressed"]["lambda_as"] / calm}


def _mean_var(v: Sequence[float], field: str) -> tuple[float, float, int]:
    n = len(v)
    if n < 2:
        raise _fail("E_INPUT", "need at least 2 fills per class", field)
    m = math.fsum(v) / n
    return m, math.fsum((a - m) ** 2 for a in v) / (n - 1), n


def passive_vs_aggressive(passive: Sequence[float], aggressive: Sequence[float]) -> dict[str, Any]:
    """`micro.est.passive_vs_aggressive`: delta = mean(aggressive) - mean(passive), Welch SE."""
    for v, field in ((passive, "passive"), (aggressive, "aggressive")):
        if len(v) < 2:
            raise _fail("E_INPUT", "need at least 2 fills per class", field)
    mp_, vp, n_p = _mean_var(passive, "passive")
    ma, va, n_a = _mean_var(aggressive, "aggressive")
    return {"delta": ma - mp_, "se": math.sqrt(va / n_a + vp / n_p)}


guard(globals())
