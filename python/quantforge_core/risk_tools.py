"""Stage F carry-over risk tools: reverse stress, limits, concentration, liquidity-adjusted VaR,
volatility by horizon (F4, ruling G-46) and the F3 sensitivities inflation01, dividend and
borrow, and correlation (ruling G-47).

Specifications: specifications/06-risk/portfolio-risk-tools.md, 06-risk/f3-sensitivities.md.
"""
import math
from collections.abc import Mapping, Sequence

from .black import big_n, small_n
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum

Floats = Sequence[float]
_ORDER = {"OK": 0, "WARN": 1, "BREACH": 2}


def _input(message: str, field: str) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str) -> QfError:
    return QfError("E_DOMAIN", message, field)


def reverse_stress(direction: Floats, delta: Floats, gamma: Sequence[Floats],
                   target_loss: float) -> dict[str, object]:
    """`risk.stress.reverse`: smallest `k > 0` with delta-gamma P&L `b k + a k^2 = -L`."""
    n = len(direction)
    if n < 1 or len(delta) != n or len(gamma) != n or any(len(r) != n for r in gamma):
        raise _input("direction, delta and gamma must match", "direction")
    if not target_loss > 0:
        raise _domain("target_loss must be above 0", "target_loss")
    b = ordered_sum(x * d for x, d in zip(delta, direction, strict=True))
    a = ordered_sum(direction[i] * gamma[i][j] * direction[j]
                    for i in range(n) for j in range(n)) / 2
    loss = target_loss
    roots: list[float] = []
    if a == 0:
        if b != 0:
            roots.append(-loss / b)
    else:
        disc = b * b - 4 * a * loss
        if disc >= 0:
            q = -(b + math.copysign(math.sqrt(disc), b)) / 2
            if q != 0:
                roots += [q / a, loss / q]
    positive = [k for k in roots if k > 0]
    if not positive:
        raise _domain("no positive scale reaches the target loss", "target_loss")
    k = min(positive)
    return {"scale": k, "shocks": [k * d for d in direction], "pnl": -loss}


def limits_check(measures: Mapping[str, float],
                 limits: Mapping[str, tuple[float, float]]) -> dict[str, object]:
    """`risk.limits.check`: utilisation and status per measure, and the worst status."""
    for name, (soft, hard) in limits.items():
        if not 0 <= soft <= hard:
            raise _domain("need 0 <= soft <= hard", f"limits.{name}")
    for name in measures:
        if name not in limits:
            raise _input(f"{name} has no limit", "limits")
    out: dict[str, object] = {}
    worst = "OK"
    for name in sorted(measures):
        soft, hard = limits[name]
        v = abs(measures[name])
        status = "BREACH" if v > hard else "WARN" if v >= soft else "OK"
        worst = max(worst, status, key=_ORDER.__getitem__)
        out[name] = {"utilisation": v / hard if hard else math.inf, "status": status}
    return {"measures": out, "overall": worst}


def concentration(exposures: Floats, top_n: int) -> dict[str, object]:
    """`risk.concentration.measures`: HHI, effective number and top-n share."""
    if not exposures or not top_n >= 1 or top_n > len(exposures):
        if exposures and top_n >= 1:
            raise _input("top_n is above the number of exposures", "top_n")
        if not exposures:
            raise _domain("exposures needs at least one value", "exposures")
        raise _input("top_n must be at least 1", "top_n")
    total = ordered_sum(abs(x) for x in exposures)
    if total == 0:
        raise _domain("exposures are all zero", "exposures")
    w = [abs(x) / total for x in exposures]
    hhi = ordered_sum(x * x for x in w)
    return {"hhi": hhi, "effective_number": 1 / hhi,
            "top_n_share": ordered_sum(sorted(w, reverse=True)[:top_n]), "weights": w}


def liquidity_adjusted(var: float, z: float, values: Floats, spread_mean: Floats,
                       spread_vol: Floats) -> dict[str, float]:
    """`risk.var.liquidity_adjusted`: VaR plus the exogenous spread cost (Bangia et al.)."""
    if len(spread_mean) != len(values) or len(spread_vol) != len(values):
        raise _input("position_values and spreads must match", "position_values")
    if not var >= 0:
        raise _domain("var must be >= 0", "var")
    if any(not m >= 0 for m in spread_mean) or any(not s >= 0 for s in spread_vol):
        raise _domain("spreads must be >= 0", "spread_mean")
    cost = 0.5 * ordered_sum(abs(p) * (m + z * s)
                             for p, m, s in zip(values, spread_mean, spread_vol, strict=True))
    return {"liquidity_cost": cost, "lvar": var + cost}


def vol_horizon(daily_vol: float, ar1: float, horizon_days: int) -> dict[str, float]:
    """`risk.vol.horizon`: h-day volatility of AR(1) daily returns (Lo-MacKinlay)."""
    if not daily_vol > 0:
        raise _domain("daily_vol must be above 0", "daily_vol")
    if not abs(ar1) < 1:
        raise _domain("|ar1| must be below 1", "ar1")
    if horizon_days < 1:
        raise _domain("horizon_days must be at least 1", "horizon_days")
    h = horizon_days
    ratio_sum = h + 2 * ordered_sum((h - k) * ar1 ** k for k in range(1, h))
    return {"vol": daily_vol * math.sqrt(ratio_sum), "sqrt_rule_vol": daily_vol * math.sqrt(h),
            "variance_ratio": ratio_sum / h}


# --- F3 sensitivities ---------------------------------------------------------------------------


def inflation01(notional: float, years: int, fixed_rate: float, market_rate: float,
                discount_factor: float) -> dict[str, float]:
    """`risk.sens.inflation01`: receive-inflation ZCIS value, analytic and bumped inflation01."""
    if years < 1:
        raise _domain("years must be at least 1", "years")
    if not 1 + market_rate > 0:
        raise _domain("1 + market_rate must be above 0", "market_rate")
    if not discount_factor > 0:
        raise _domain("discount_factor must be above 0", "discount_factor")

    def pv(z: float) -> float:
        return notional * discount_factor * ((1 + z) ** years - (1 + fixed_rate) ** years)

    base = pv(market_rate)
    return {"pv": base,
            "inflation01": notional * discount_factor * years * (1 + market_rate) ** (years - 1)
            * 1e-4,
            "inflation01_bump": pv(market_rate + 1e-4) - base}


def dividend_borrow(s: float, k: float, t: float, r: float, q: float, borrow: float, v: float,
                    option_type: str) -> dict[str, float]:
    """`risk.sens.dividend_borrow`: BSM with yield `q + borrow`; dV/dy per 1 bp, equal for both."""
    if option_type not in ("CALL", "PUT"):
        raise _input(f"{option_type} is not an option type", "option_type")
    for key, value in (("spot", s), ("strike", k), ("expiry_years", t), ("vol", v)):
        if not value > 0:
            raise _domain(f"{key} must be above 0", key)
    y = q + borrow
    sd = v * math.sqrt(t)
    d1 = (math.log(s / k) + (r - y + v * v / 2) * t) / sd
    d2 = d1 - sd
    fwd, disc = s * math.exp(-y * t), math.exp(-r * t)
    if option_type == "CALL":
        price = fwd * big_n(d1) - k * disc * big_n(d2)
        dv = -t * fwd * big_n(d1)
    else:
        price = k * disc * big_n(-d2) - fwd * big_n(-d1)
        dv = t * fwd * big_n(-d1)
    return {"price": price, "dividend01": dv * 1e-4, "borrow01": dv * 1e-4}


def correlation01(s1: float, s2: float, q1: float, q2: float, y1: float, y2: float,
                  v1: float, v2: float, rho: float, t: float) -> dict[str, float]:
    """`risk.sens.correlation`: Margrabe exchange option and its sensitivity per 1 point of rho."""
    for key, value in (("spot1", s1), ("spot2", s2), ("vol1", v1), ("vol2", v2),
                       ("expiry_years", t)):
        if not value > 0:
            raise _domain(f"{key} must be above 0", key)
    if not -1 <= rho <= 1:
        raise _domain("correlation must be in [-1, 1]", "correlation")
    var = v1 * v1 + v2 * v2 - 2 * rho * v1 * v2
    if not var > 0:
        raise _domain("the spread volatility is zero", "correlation")
    sv = math.sqrt(var)
    f1, f2 = q1 * s1 * math.exp(-y1 * t), q2 * s2 * math.exp(-y2 * t)
    sd = sv * math.sqrt(t)
    d1 = (math.log(f1 / f2) + sd * sd / 2) / sd
    price = f1 * big_n(d1) - f2 * big_n(d1 - sd)
    dv_ds = f1 * small_n(d1) * math.sqrt(t)
    return {"price": price, "correlation01": dv_ds * (-v1 * v2 / sv) * 0.01, "spread_vol": sv}


guard(globals())
