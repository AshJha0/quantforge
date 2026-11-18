"""Stage H wave 1 (rulings HR-1 to HR-10): execution schedules (10-execution/schedules.md),
Almgren-Chriss trajectory and frontier (10-execution/almgren-chriss.md), square-root and
Obizhaeva-Wang impact (10-execution/impact.md), implementation-shortfall TCA (10-execution/tca.md)
and Avellaneda-Stoikov quotes (09-microstructure/avellaneda-stoikov.md).

Sources, as the specs cite them: [AC00] Almgren and Chriss, J. Risk 3(2), preprint eqs. (5), (8),
(16)-(19); [OW13] Obizhaeva and Wang, J. Financial Markets 16(1), eq. (31); [TLD11] Toth et al.,
Phys. Rev. X 1, 021006 (square-root form, recalled); [Per88] Perold (recalled); [AS08] Avellaneda
and Stoikov, Quantitative Finance 8(3), eqs. (29)-(30)."""

import math
from collections.abc import Sequence
from typing import Any

from .errors import QfError
from .finite import guard

MODES = ("UNITS", "CONTINUOUS")
SIDES = ("BUY", "SELL")
MODEL = "assumed parameters; not calibrated to any venue"  # HR-10


def _fail(code: str, message: str, field: str) -> QfError:
    return QfError(code, message, field)


def _quantity(x: float, units: bool) -> None:
    """HR-2, HR-3: the order is positive, and a whole number of units in UNITS mode."""
    if x <= 0:
        raise _fail("E_INPUT", "quantity must be positive", "quantity")
    if units and x != math.floor(x):
        raise _fail("E_INPUT", "quantity must be a whole number of units in UNITS mode", "quantity")


def _whole(x: float) -> Any:
    """An integral binary64 written as a JSON integer (HR-3: UNITS returns integers)."""
    return int(x)


def _largest_remainder(x: float, exact: list[float]) -> list[Any]:
    """HR-3: floor every share, then give the missing units one at a time to the largest
    remainders, ties to the earliest slice. Rounding of `exact` can leave the floors one unit
    above `x`; the same rule then takes units back from the smallest remainders, ties to the
    latest, so the slices always sum to `x` exactly."""
    floors = [math.floor(q) for q in exact]
    rem = [q - f for q, f in zip(exact, floors, strict=True)]
    short = int(x) - sum(int(f) for f in floors)
    order = sorted(range(len(exact)), key=lambda k: (-rem[k], k))
    for k in order[: max(short, 0)]:
        floors[k] += 1
    for k in order[::-1][: max(-short, 0)]:
        floors[k] -= 1
    return [_whole(f) for f in floors]


def schedule_twap(quantity: float, n_buckets: int, mode: str) -> dict[str, Any]:
    """`exec.schedule.twap`: X / N per bucket; UNITS floors and hands the remainder one unit at a
    time to the earliest slices (HR-3)."""
    units = mode == "UNITS"
    _quantity(quantity, units)
    if n_buckets < 1:
        raise _fail("E_INPUT", "n_buckets must be at least 1", "n_buckets")
    if not units:
        return {"slices": [quantity / n_buckets] * n_buckets}
    total = int(quantity)
    base, extra = divmod(total, n_buckets)
    return {"slices": [base + (1 if k < extra else 0) for k in range(n_buckets)]}


def schedule_vwap(quantity: float, profile: Sequence[float], mode: str) -> dict[str, Any]:
    """`exec.schedule.vwap`: slice i = X w_i / sum w; UNITS by largest remainder (HR-3)."""
    units = mode == "UNITS"
    _quantity(quantity, units)
    if not profile:
        raise _fail("E_INPUT", "profile must not be empty", "profile")
    if any(w < 0 for w in profile):
        raise _fail("E_DOMAIN", "profile weights must be non-negative", "profile")
    total = sum(profile, 0.0)  # array order (cli-contract numeric rules)
    if total == 0:
        raise _fail("E_DOMAIN", "profile is all zero", "profile")
    exact = [quantity * w / total for w in profile]
    return {"slices": _largest_remainder(quantity, exact) if units else exact}


def schedule_pov(
    quantity: float, participation: float, market_volume: Sequence[float], mode: str
) -> dict[str, Any]:
    """`exec.schedule.pov`: child i = min(remaining, p v_i / (1 - p)), p of total volume including
    own fills (HR-4); floored in UNITS. The residual may be positive and is never an error."""
    units = mode == "UNITS"
    _quantity(quantity, units)
    if not 0 < participation < 1:
        raise _fail("E_DOMAIN", "participation must lie in (0, 1)", "participation")
    if not market_volume:
        raise _fail("E_INPUT", "market_volume must not be empty", "market_volume")
    if any(v < 0 for v in market_volume):
        raise _fail("E_DOMAIN", "market_volume must be non-negative", "market_volume")
    ratio = 1.0 - participation
    remaining, filled = quantity, 0.0
    slices: list[Any] = []
    for v in market_volume:
        child = min(remaining, participation * v / ratio)
        if units:
            child = math.floor(child)
        remaining -= child
        filled += child
        slices.append(_whole(child) if units else child)
    residual = quantity - filled
    if units:
        return {"slices": slices, "filled": _whole(filled), "residual": _whole(residual)}
    return {"slices": slices, "filled": filled, "residual": residual}


def _ac_check(
    quantity: float,
    horizon: float,
    n_steps: int,
    sigma: float,
    epsilon: float,
    eta: float,
    gamma: float,
) -> float:
    """The [AC00] checks in the order of almgren-chriss.md (eta_tilde, sigma, T, then N), then the
    remaining sign rules (HR-2). Returns eta_tilde = eta - gamma tau / 2 (HR-5)."""
    if n_steps >= 1 and eta - gamma * (horizon / n_steps) / 2.0 <= 0:
        raise _fail("E_DOMAIN", "eta_tilde = eta - gamma tau / 2 must be positive", "eta")
    if sigma < 0:
        raise _fail("E_DOMAIN", "sigma must be non-negative", "sigma")
    if horizon <= 0:
        raise _fail("E_DOMAIN", "horizon must be positive", "horizon")
    if n_steps < 1:
        raise _fail("E_INPUT", "n_steps must be at least 1", "n_steps")
    if quantity <= 0:
        raise _fail("E_INPUT", "quantity must be positive", "quantity")
    if epsilon < 0:
        raise _fail("E_DOMAIN", "epsilon must be non-negative", "epsilon")
    if gamma < 0:
        raise _fail("E_DOMAIN", "gamma must be non-negative", "gamma")
    return eta - gamma * (horizon / n_steps) / 2.0


def ac_kappa(risk_aversion: float, sigma: float, tau: float, eta_tilde: float) -> float:
    """HR-6: kappa = acosh(1 + y) / tau with y = lambda sigma^2 tau^2 / (2 eta_tilde), written
    log1p(y + sqrt(y (y + 2))) so small y keeps its digits ([AC00] eq. (16) and the line after)."""
    y = risk_aversion * sigma * sigma * tau * tau / (2.0 * eta_tilde)
    return math.log1p(y + math.sqrt(y * (y + 2.0))) / tau


def _sinh_ratio(a: float, b: float) -> float:
    """sinh(a) / sinh(b) for 0 <= a <= b, b > 0; exponential form when b > 700 (HR-6)."""
    if b <= 700.0:
        return math.sinh(a) / math.sinh(b)
    return math.exp(a - b) * (-math.expm1(-2.0 * a)) / (-math.expm1(-2.0 * b))


def _ac_point(
    quantity: float,
    horizon: float,
    n_steps: int,
    sigma: float,
    epsilon: float,
    eta: float,
    gamma: float,
    lam: float,
    eta_tilde: float,
) -> dict[str, Any]:
    tau = horizon / n_steps
    if lam < 0:
        raise _fail("E_DOMAIN", "risk_aversion must be non-negative", "risk_aversion")
    kappa = ac_kappa(lam, sigma, tau, eta_tilde) if lam > 0 else 0.0
    holdings = [quantity]
    for j in range(1, n_steps):
        if kappa > 0:
            holdings.append(quantity * _sinh_ratio(kappa * (horizon - j * tau), kappa * horizon))
        else:  # HR-5: lambda = 0 (or sigma = 0) is the linear trajectory, exactly
            holdings.append(quantity * (n_steps - j) / n_steps)
    holdings.append(0.0)
    trades = [holdings[k - 1] - holdings[k] for k in range(1, n_steps + 1)]
    # [AC00] eq. (8): E = 1/2 gamma X^2 + epsilon X + (eta_tilde / tau) sum n_k^2 (HR-5: epsilon X)
    expected = (
        0.5 * gamma * quantity * quantity
        + epsilon * quantity
        + eta_tilde / tau * sum((n * n for n in trades), 0.0)
    )
    # [AC00] eq. (5): V = sigma^2 tau sum_{k=1..N} x_k^2
    variance = sigma * sigma * tau * sum((x * x for x in holdings[1:]), 0.0)
    return {
        "holdings": holdings,
        "trades": trades,
        "kappa": kappa,
        "expected_cost": expected,
        "variance": variance,
        "objective": expected + lam * variance,
    }


def ac_trajectory(
    quantity: float,
    horizon: float,
    n_steps: int,
    sigma: float,
    epsilon: float,
    eta: float,
    gamma: float,
    risk_aversion: float,
) -> dict[str, Any]:
    """`exec.ac.trajectory`: x_j = X sinh(kappa (T - t_j)) / sinh(kappa T), [AC00] eq. (17)."""
    et = _ac_check(quantity, horizon, n_steps, sigma, epsilon, eta, gamma)
    return _ac_point(quantity, horizon, n_steps, sigma, epsilon, eta, gamma, risk_aversion, et)


def ac_frontier(
    quantity: float,
    horizon: float,
    n_steps: int,
    sigma: float,
    epsilon: float,
    eta: float,
    gamma: float,
    risk_aversions: Sequence[float],
) -> dict[str, Any]:
    """`exec.ac.frontier`: one (lambda, E, V) per entry, in input order."""
    et = _ac_check(quantity, horizon, n_steps, sigma, epsilon, eta, gamma)
    if not risk_aversions:
        raise _fail("E_INPUT", "risk_aversions must not be empty", "risk_aversions")
    if any(lam < 0 for lam in risk_aversions):
        raise _fail("E_DOMAIN", "risk_aversions must be non-negative", "risk_aversions")
    points = [
        _ac_point(quantity, horizon, n_steps, sigma, epsilon, eta, gamma, lam, et)
        for lam in risk_aversions
    ]
    return {
        "risk_aversions": list(risk_aversions),
        "expected_costs": [p["expected_cost"] for p in points],
        "variances": [p["variance"] for p in points],
    }


def impact_sqrt(
    quantity: float, daily_volume: float, daily_vol: float, coefficient: float
) -> dict[str, Any]:
    """`exec.impact.sqrt`: I = Y sigma sqrt(Q / V) as a fraction of price ([TLD11]); Y is an
    assumed input (HR-10)."""
    if quantity < 0:
        raise _fail("E_DOMAIN", "quantity must be non-negative", "quantity")
    if daily_volume <= 0:
        raise _fail("E_DOMAIN", "daily_volume must be positive", "daily_volume")
    if daily_vol < 0:
        raise _fail("E_DOMAIN", "daily_vol must be non-negative", "daily_vol")
    if coefficient < 0:
        raise _fail("E_DOMAIN", "coefficient must be non-negative", "coefficient")
    return {
        "impact": coefficient * daily_vol * math.sqrt(quantity / daily_volume),
        "model": MODEL,
    }


def impact_ow_optimal(quantity: float, horizon: float, resilience: float) -> dict[str, Any]:
    """`exec.impact.ow_optimal`: blocks X / (rho T + 2) at both ends and rate rho X / (rho T + 2)
    in between ([OW13] eq. (31), p. 17)."""
    if quantity <= 0:
        raise _fail("E_INPUT", "quantity must be positive", "quantity")
    if horizon <= 0:
        raise _fail("E_DOMAIN", "horizon must be positive", "horizon")
    if resilience <= 0:
        raise _fail("E_DOMAIN", "resilience must be positive", "resilience")
    d = resilience * horizon + 2.0
    block = quantity / d
    return {"initial_block": block, "rate": resilience * quantity / d, "final_block": block}


def tca_shortfall(
    side: str,
    decision_price: float,
    arrival_price: float,
    end_price: float,
    order_quantity: float,
    fills: Sequence[tuple[float, float]],
    fees: float,
    benchmark_vwap: float | None,
) -> dict[str, Any]:
    """`exec.tca.shortfall`: Perold paper-portfolio decomposition (HR-8): delay on the executed
    quantity, execution against arrival, opportunity on the unexecuted rest, plus fees."""
    s = 1.0 if side == "BUY" else -1.0
    if order_quantity <= 0:
        raise _fail("E_INPUT", "order_quantity must be positive", "order_quantity")
    if any(q <= 0 for q, _ in fills):
        raise _fail("E_INPUT", "fill quantities must be positive", "fills")
    filled = sum((q for q, _ in fills), 0.0)
    if filled > order_quantity:
        raise _fail("E_INPUT", "fills add up to more than the order", "fills")
    prices = [
        ("decision_price", decision_price),
        ("arrival_price", arrival_price),
        ("end_price", end_price),
        *(("fills", p) for _, p in fills),
    ]
    if benchmark_vwap is not None:
        prices.append(("benchmark_vwap", benchmark_vwap))
    for key, p in prices:
        if p <= 0:
            raise _fail("E_DOMAIN", "prices must be positive", key)
    delay = s * filled * (arrival_price - decision_price)
    execution = s * sum((q * (p - arrival_price) for q, p in fills), 0.0)
    opportunity = s * (order_quantity - filled) * (end_price - decision_price)
    total = delay + execution + opportunity + fees
    out: dict[str, Any] = {
        "delay": delay,
        "execution": execution,
        "opportunity": opportunity,
        "total": total,
        "total_bps": total / (order_quantity * decision_price) * 1e4,
    }
    if benchmark_vwap is not None:
        # s Q (avg_fill - VWAP) = s (sum q_i p_i - Q VWAP): no division when Q = 0
        notional = sum((q * p for q, p in fills), 0.0)
        out["vwap_slippage"] = s * (notional - filled * benchmark_vwap)
    return out


def as_quotes(
    mid: float, inventory: float, risk_aversion: float, sigma: float, time_left: float, k: float
) -> dict[str, Any]:
    """`micro.mm.as_quotes`: r = s - q gamma sigma^2 (T - t), [AS08] eq. (29); spread
    gamma sigma^2 (T - t) + (2 / gamma) ln(1 + gamma / k), eq. (30); quotes symmetric about r
    (HR-7)."""
    if risk_aversion <= 0:
        raise _fail("E_DOMAIN", "risk_aversion must be positive", "risk_aversion")
    if k <= 0:
        raise _fail("E_DOMAIN", "k must be positive", "k")
    if sigma < 0:
        raise _fail("E_DOMAIN", "sigma must be non-negative", "sigma")
    if time_left < 0:
        raise _fail("E_DOMAIN", "time_left must be non-negative", "time_left")
    risk = risk_aversion * sigma * sigma * time_left
    reservation = mid - inventory * risk
    spread = risk + 2.0 / risk_aversion * math.log1p(risk_aversion / k)
    return {
        "reservation": reservation,
        "spread": spread,
        "bid": reservation - spread / 2.0,
        "ask": reservation + spread / 2.0,
    }


guard(globals())
