"""Unit tests for `quantforge_core.frtb_backtest` that run inside the mutation harness (K-8e).

test_stage_k_w1b.py reads specifications/ outside python/, which the mutmut copy of python/ does not
hold, so it cannot be in the mutmut tests_dir. These tests pin the same contract with values written
out here: the MAR99 Table 2 zones and multipliers at 250 observations, the MAR32.19 desk limits, and
binomial probabilities checked against exact rational sums (math.comb with fractions, computed once
when the test was written; evidence class: measured). Error checks pin code, field and message.
"""

from typing import Any

import pytest

from quantforge_core import frtb_backtest as fb
from quantforge_core.errors import QfError


def _err(f: Any, *args: Any) -> tuple[str, str | None, str]:
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code, e.value.field, e.value.message


def test_constants() -> None:
    assert fb.COVERAGE == 0.99 and fb.AMBER_FROM == 0.95 and fb.RED_FROM == 0.9999
    assert fb.TABLE_OBSERVATIONS == 250 and fb.MULTIPLIER_RED == 2.0
    assert fb.MULTIPLIER_250 == (1.50, 1.50, 1.50, 1.50, 1.50, 1.70, 1.76, 1.83, 1.88, 1.92)
    assert fb.DESK_LIMIT_99 == 12 and fb.DESK_LIMIT_975 == 30 and fb.MAX_OBSERVATIONS == 1_000_000


def test_binomial_cdf_values() -> None:
    assert fb.binomial_cdf(250, 4, 0.01) == pytest.approx(0.8921876269036253, abs=1e-12)
    assert fb.binomial_cdf(250, 9, 0.01) == pytest.approx(0.9997498099312595, abs=1e-12)
    assert fb.binomial_cdf(10, 2, 0.3) == pytest.approx(0.3827827864, abs=1e-12)
    assert fb.binomial_cdf(10, 0, 0.3) == pytest.approx(0.0282475249, abs=1e-15)
    assert fb.binomial_cdf(10, -1, 0.3) == 0.0
    assert fb.binomial_cdf(10, 10, 0.3) == 1.0
    assert fb.binomial_cdf(10, 11, 0.3) == 1.0
    assert fb.binomial_cdf(2, 1, 0.5) == pytest.approx(0.75, abs=1e-15)
    assert fb.binomial_cdf(1, 0, 0.25) == pytest.approx(0.75, abs=1e-15)


def _fal(n: int, p: float, level: float) -> int:
    # audit A signature: the partial sums are built once by the caller
    return fb._first_at_least(fb.binomial_partial_sums(n, p), n, level)


def test_first_at_least() -> None:
    assert _fal(250, 0.01, 0.95) == 5
    assert _fal(250, 0.01, 0.9999) == 10
    assert _fal(500, 0.01, 0.95) == 9
    assert _fal(500, 0.01, 0.9999) == 15
    assert _fal(100, 0.01, 0.95) == 3
    assert _fal(100, 0.01, 0.9999) == 6
    assert _fal(1, 0.01, 0.95) == 0
    assert _fal(1, 0.01, 0.9999) == 1
    assert _fal(2, 0.5, 0.7) == 1
    assert _fal(2, 0.5, 0.999) == 2
    # exact ties in binary64 (KF-10): P(X <= 1) equals the level, so k = 1; kills `>=` -> `>`
    assert _fal(2, 0.01, 0.9999) == 1  # the KA-A17 tie
    assert _fal(2, 0.5, 0.75) == 1


@pytest.mark.parametrize(
    ("x", "zone", "mult"),
    [
        (0, "GREEN", 1.50),
        (1, "GREEN", 1.50),
        (4, "GREEN", 1.50),
        (5, "AMBER", 1.70),
        (6, "AMBER", 1.76),
        (7, "AMBER", 1.83),
        (8, "AMBER", 1.88),
        (9, "AMBER", 1.92),
        (10, "RED", 2.00),
        (11, "RED", 2.00),
        (250, "RED", 2.00),
    ],
)
def test_zone_table_250(x: int, zone: str, mult: float) -> None:
    for a, h in ((x, 0), (0, x), (x, x)):
        r = fb.backtest_zone(250, a, h)
        assert r["zone"] == zone and r["multiplier"] == mult and r["exceptions"] == x
        assert r["amber_from"] == 5 and r["red_from"] == 10


def test_zone_full_result() -> None:
    assert fb.backtest_zone(250, 3, 5) == {
        "exceptions": 5,
        "cumulative_probability": pytest.approx(0.9588168159302313, abs=1e-12),
        "zone": "AMBER",
        "amber_from": 5,
        "red_from": 10,
        "multiplier": 1.7,
    }
    assert fb.backtest_zone(1, 0, 1) == {
        "exceptions": 1,
        "cumulative_probability": 1.0,
        "zone": "RED",
        "amber_from": 0,
        "red_from": 1,
        "multiplier": None,
    }
    r = fb.backtest_zone(500, 8, 2)
    assert (r["zone"], r["amber_from"], r["red_from"], r["multiplier"]) == ("GREEN", 9, 15, None)
    assert fb.backtest_zone(500, 9, 2)["zone"] == "AMBER"
    assert fb.backtest_zone(500, 2, 15)["zone"] == "RED"
    assert fb.backtest_zone(249, 0, 0)["multiplier"] is None
    assert fb.backtest_zone(251, 0, 0)["multiplier"] is None


def test_zone_errors() -> None:
    assert _err(fb.backtest_zone, 0, 0, 0) == (
        "E_DOMAIN",
        "observations",
        "observations must be at least 1",
    )
    assert _err(fb.backtest_zone, 1_000_001, 0, 0) == (
        "E_LIMIT",
        "observations",
        "observations is above its limit of 1000000",
    )
    assert _err(fb.backtest_zone, 10, -1, 0) == (
        "E_DOMAIN",
        "exceptions_actual",
        "exceptions_actual must be in [0, observations]",
    )
    assert _err(fb.backtest_zone, 10, 11, 0)[:2] == ("E_DOMAIN", "exceptions_actual")
    assert _err(fb.backtest_zone, 10, 0, -1) == (
        "E_DOMAIN",
        "exceptions_hypothetical",
        "exceptions_hypothetical must be in [0, observations]",
    )
    assert _err(fb.backtest_zone, 10, 0, 11)[:2] == ("E_DOMAIN", "exceptions_hypothetical")
    fb._observations(1_000_000)
    fb._observations(1)
    fb._count(10, 0, "f")
    fb._count(10, 10, "f")


def test_desk() -> None:
    assert fb.backtest_desk(250, 13, 2, 30, 31) == {
        "exceptions_99": 13,
        "exceptions_975": 31,
        "cumulative_probability_99": pytest.approx(0.999999673538539, abs=1e-12),
        "cumulative_probability_975": pytest.approx(0.9999999999999977, abs=1e-12),
        "breach_99": True,
        "breach_975": True,
        "eligible": False,
    }
    r = fb.backtest_desk(100, 2, 1, 3, 4)
    assert (r["exceptions_99"], r["exceptions_975"]) == (2, 4)
    assert r["cumulative_probability_99"] == pytest.approx(0.9206267977478196, abs=1e-12)
    assert r["cumulative_probability_975"] == pytest.approx(0.8937310006202928, abs=1e-12)
    assert (r["breach_99"], r["breach_975"], r["eligible"]) == (False, False, True)
    r = fb.backtest_desk(250, 12, 12, 30, 30)
    assert (r["breach_99"], r["breach_975"], r["eligible"]) == (False, False, True)
    r = fb.backtest_desk(250, 0, 13, 0, 0)
    assert (r["exceptions_99"], r["breach_99"], r["breach_975"], r["eligible"]) == (
        13,
        True,
        False,
        False,
    )
    r = fb.backtest_desk(250, 0, 0, 0, 31)
    assert (r["exceptions_975"], r["breach_99"], r["breach_975"], r["eligible"]) == (
        31,
        False,
        True,
        False,
    )
    r = fb.backtest_desk(250, 0, 0, 31, 0)
    assert (r["exceptions_975"], r["breach_975"]) == (31, True)


@pytest.mark.parametrize(
    "field",
    [
        "exceptions_99_actual",
        "exceptions_99_hypothetical",
        "exceptions_975_actual",
        "exceptions_975_hypothetical",
    ],
)
def test_desk_errors(field: str) -> None:
    order = [
        "exceptions_99_actual",
        "exceptions_99_hypothetical",
        "exceptions_975_actual",
        "exceptions_975_hypothetical",
    ]
    for bad in (-1, 11):
        args = [0, 0, 0, 0]
        args[order.index(field)] = bad
        assert _err(fb.backtest_desk, 10, *args) == (
            "E_DOMAIN",
            field,
            f"{field} must be in [0, observations]",
        )
    assert _err(fb.backtest_desk, 0, 0, 0, 0, 0)[:2] == ("E_DOMAIN", "observations")
    assert _err(fb.backtest_desk, 1_000_001, 0, 0, 0, 0)[:2] == ("E_LIMIT", "observations")


def test_count_exceptions() -> None:
    var = [1.0, 1.0, None, 2.0, 1.0]
    actual = [-1.0, -1.5, 0.0, None, 0.5]
    hyp = [-1.0000001, 0.0, 0.0, 0.0, -0.9]
    assert fb.count_exceptions(var, actual, hyp) == {
        "observations": 5,
        "exceptions_actual": 3,
        "exceptions_hypothetical": 2,
        "exceptions": 3,
        "days_actual": [1, 2, 3],
        "days_hypothetical": [0, 2],
    }
    r = fb.count_exceptions([1.0], [0.0], [-2.0])
    assert (r["exceptions_actual"], r["exceptions_hypothetical"], r["exceptions"]) == (0, 1, 1)
    assert r["days_hypothetical"] == [0] and r["observations"] == 1


def test_count_exceptions_errors() -> None:
    assert _err(fb.count_exceptions, [], [], []) == ("E_INPUT", "var", "var is empty")
    assert _err(fb.count_exceptions, [1.0], [], [0.0]) == (
        "E_INPUT",
        "actual",
        "actual and var differ in length",
    )
    assert _err(fb.count_exceptions, [1.0], [0.0], [0.0, 1.0]) == (
        "E_INPUT",
        "hypothetical",
        "hypothetical and var differ in length",
    )
