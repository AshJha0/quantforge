"""risk.backtest.traffic_light (stage J) at large n against exact rationals.

Audit A (KA-A16) found that the FRTB backtesting binomial sum, written with lgamma, drifts as `observations`
grows (1.3e-10 relative at n = 100,000); ruling KR-237 replaced it with one arithmetic-only algorithm. The
audit response noted that the stage J traffic light uses the same lgamma form up to n = 1,000,000. This file
reproduces that defect (written first, failing on the lgamma code) and pins the KR-237 algorithm after the
switch (ruling KR-253, `specifications/stage-k-rulings-w1b.md`).

p is 1 - confidence as the operation computes it in binary64 (for 0.99 that is 0.010000000000000009), taken
exactly as a rational, so the reference is the exact cumulative probability of the binary64 input.
"""

import sys
from fractions import Fraction

import pytest

from quantforge_core import var_risk

sys.set_int_max_str_digits(0)


def _exact_cdf(n: int, x: int, p: Fraction) -> Fraction:
    """P(X <= x) for X ~ Binomial(n, p), exact, by the integer term recurrence."""
    a, b = p.numerator, p.denominator
    c = b - a
    term = c**n
    total = term
    for k in range(x):
        term = term * (n - k) * a // ((k + 1) * c)
        total += term
    return Fraction(total, b**n)


@pytest.mark.parametrize(
    ("n", "x", "confidence"),
    [
        (100_000, 1_050, 0.99),  # near the 95% line
        (100_000, 1_000, 0.99),  # at the mean
        (100_000, 2_600, 0.975),  # 97.5% coverage, above the mean
        (20_000, 160, 0.99),  # below the mean
    ],
)
def test_traffic_light_cumulative_matches_exact_rationals(n: int, x: int, confidence: float) -> None:
    exact = _exact_cdf(n, x, Fraction(1.0 - confidence))
    got = var_risk.traffic_light(n, x, confidence)["cumulative_probability"]
    assert isinstance(got, float)
    assert abs(Fraction(got) / exact - 1) <= Fraction(1, 10**12), float(Fraction(got) / exact - 1)


def test_traffic_light_small_n_unchanged_by_the_switch() -> None:
    """The stage J table point: n = 250, c = 0.99. P(X <= 4) by the exact sum, and the zones of the table."""
    exact = _exact_cdf(250, 4, Fraction(1.0 - 0.99))
    r = var_risk.traffic_light(250, 4, 0.99)
    assert abs(Fraction(r["cumulative_probability"]) / exact - 1) <= Fraction(1, 10**14)  # type: ignore[arg-type]
    assert [var_risk.traffic_light(250, k, 0.99)["zone"] for k in (4, 5, 9, 10)] == [
        "GREEN",
        "YELLOW",
        "YELLOW",
        "RED",
    ]


def test_traffic_light_all_exceptions_is_one() -> None:
    assert var_risk.traffic_light(7, 7, 0.99)["cumulative_probability"] == 1.0
