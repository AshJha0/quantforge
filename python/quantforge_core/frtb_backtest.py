"""FRTB internal models approach: backtesting zones and desk-level exception limits (plan item K-8e).

Specification: specifications/06-risk/frtb-ima-backtest.md; rulings KR-40 to KR-47
(specifications/stage-k-rulings-w1b.md). Sources: Basel Framework MAR32.5, MAR32.9, MAR32.18,
MAR32.19 and MAR99.8 to MAR99.17 (Table 2), read 2026-11-19 in the Basel Framework PDF generated
11/11/2026, pages 659 to 662 and 755 to 759.

The zone table is data shared by the four builds: specifications/06-risk/frtb-ima-backtest-tables.json.
"""

import math
from collections.abc import Sequence

from .errors import QfError

COVERAGE = 0.99  # MAR32.5: bank-wide VaR at the 99th percentile; MAR99.17: true coverage 99%
AMBER_FROM = 0.95  # MAR99.17: amber begins where P(X <= k) >= 95%
RED_FROM = 0.9999  # MAR99.17: red begins where P(X <= k) >= 99.99%
TABLE_OBSERVATIONS = 250
# MAR32.9 Table 1 and MAR99.17 Table 2: backtesting-dependent multiplier by exception count at 250
# observations; 10 or more is 2.00.
MULTIPLIER_250 = (1.50, 1.50, 1.50, 1.50, 1.50, 1.70, 1.76, 1.83, 1.88, 1.92)
MULTIPLIER_RED = 2.00
DESK_LIMIT_99 = 12  # MAR32.19: more than 12 exceptions at the 99th percentile
DESK_LIMIT_975 = 30  # MAR32.19: (more than) 30 exceptions at the 97.5th percentile (ruling KR-44)
MAX_OBSERVATIONS = 1_000_000  # ruling KR-46, as risk.backtest.traffic_light (J-W3-17)


def binomial_cdf(n: int, x: int, p: float) -> float:
    """P(X <= x) for X ~ Binomial(n, p), 0 < p < 1, by a compensated sum of log-space terms."""
    if x < 0:
        return 0.0
    if x >= n:
        return 1.0
    lp, lq = math.log(p), math.log1p(-p)
    head = math.lgamma(n + 1)
    terms = [
        math.exp(head - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * lp + (n - k) * lq)
        for k in range(x + 1)
    ]
    return min(math.fsum(terms), 1.0)


def _first_at_least(n: int, p: float, level: float) -> int:
    """The smallest k in 0..n with P(X <= k) >= level (exists: P(X <= n) = 1)."""
    lp, lq = math.log(p), math.log1p(-p)
    head = math.lgamma(n + 1)
    terms: list[float] = []
    for k in range(n + 1):
        terms.append(
            math.exp(head - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * lp + (n - k) * lq)
        )
        if k == n or math.fsum(terms) >= level:
            return k
    raise AssertionError("unreachable")  # pragma: no cover


def _observations(n: int) -> None:
    if n > MAX_OBSERVATIONS:
        raise QfError(
            "E_LIMIT", f"observations is above its limit of {MAX_OBSERVATIONS}", "observations"
        )
    if n < 1:
        raise QfError("E_DOMAIN", "observations must be at least 1", "observations")


def _count(n: int, x: int, field: str) -> None:
    if not 0 <= x <= n:
        raise QfError("E_DOMAIN", f"{field} must be in [0, observations]", field)


def backtest_zone(
    observations: int, exceptions_actual: int, exceptions_hypothetical: int
) -> dict[str, object]:
    """Bank-wide backtesting zone (MAR32.5, MAR32.9, MAR99.8, MAR99.17)."""
    _observations(observations)
    _count(observations, exceptions_actual, "exceptions_actual")
    _count(observations, exceptions_hypothetical, "exceptions_hypothetical")
    x = max(exceptions_actual, exceptions_hypothetical)  # MAR99.8
    p = 1.0 - COVERAGE
    cumulative = binomial_cdf(observations, x, p)
    amber_from = _first_at_least(observations, p, AMBER_FROM)
    red_from = _first_at_least(observations, p, RED_FROM)
    zone = "RED" if x >= red_from else "AMBER" if x >= amber_from else "GREEN"
    multiplier: float | None = None
    if observations == TABLE_OBSERVATIONS:
        multiplier = MULTIPLIER_250[x] if x < len(MULTIPLIER_250) else MULTIPLIER_RED
    return {
        "exceptions": x,
        "cumulative_probability": cumulative,
        "zone": zone,
        "amber_from": amber_from,
        "red_from": red_from,
        "multiplier": multiplier,
    }


def backtest_desk(
    observations: int,
    exceptions_99_actual: int,
    exceptions_99_hypothetical: int,
    exceptions_975_actual: int,
    exceptions_975_hypothetical: int,
) -> dict[str, object]:
    """Trading desk backtesting eligibility (MAR32.18, MAR32.19)."""
    _observations(observations)
    for field, v in (
        ("exceptions_99_actual", exceptions_99_actual),
        ("exceptions_99_hypothetical", exceptions_99_hypothetical),
        ("exceptions_975_actual", exceptions_975_actual),
        ("exceptions_975_hypothetical", exceptions_975_hypothetical),
    ):
        _count(observations, v, field)
    x99 = max(exceptions_99_actual, exceptions_99_hypothetical)
    x975 = max(exceptions_975_actual, exceptions_975_hypothetical)
    breach_99 = x99 > DESK_LIMIT_99
    breach_975 = x975 > DESK_LIMIT_975
    return {
        "exceptions_99": x99,
        "exceptions_975": x975,
        "cumulative_probability_99": binomial_cdf(observations, x99, 0.01),
        "cumulative_probability_975": binomial_cdf(observations, x975, 0.025),
        "breach_99": breach_99,
        "breach_975": breach_975,
        "eligible": not (breach_99 or breach_975),
    }


def count_exceptions(
    var: Sequence[float | None],
    actual: Sequence[float | None],
    hypothetical: Sequence[float | None],
) -> dict[str, object]:
    """Exceptions of a daily P&L series against a daily VaR (MAR32.5(1)-(2), MAR32.18(1)-(2)).

    VaR is a positive number for a loss; a day is an exception when the loss -pnl strictly exceeds
    VaR, or when either the P&L or the VaR of that day is missing (null)."""
    n = len(var)
    if n == 0:
        raise QfError("E_INPUT", "var is empty", "var")
    if len(actual) != n:
        raise QfError("E_INPUT", "actual and var differ in length", "actual")
    if len(hypothetical) != n:
        raise QfError("E_INPUT", "hypothetical and var differ in length", "hypothetical")

    def days(pnl: Sequence[float | None]) -> list[int]:
        out = []
        for t in range(n):
            v, q = var[t], pnl[t]
            if v is None or q is None or -q > v:
                out.append(t)
        return out

    a, h = days(actual), days(hypothetical)
    return {
        "observations": n,
        "exceptions_actual": len(a),
        "exceptions_hypothetical": len(h),
        "exceptions": max(len(a), len(h)),
        "days_actual": a,
        "days_hypothetical": h,
    }
