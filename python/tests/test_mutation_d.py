"""Tests for stage D modules aimed at mutants that survived the mutation sample (commodity, ...).
Error paths pin code, message and field together: a mutant that only changes a message or a
field name otherwise survives every golden case."""
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest

from quantforge_core import commodity
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError


def error_of(f: Callable[..., Any], *args: Any) -> tuple[str, str, str | None]:
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code, e.value.message, e.value.field


def test_commodity_forward_errors() -> None:
    increasing = ("E_INPUT", "quote months must be strictly increasing", "quotes")
    assert error_of(commodity.commodity_forwards, [(3, 1.0), (3, 2.0)], None, [3]) == increasing
    assert error_of(commodity.commodity_forwards, [], None, [3]) == increasing
    assert error_of(commodity.commodity_forwards, [(1, 1.0), (2, 0.0)], None, [1]) == (
        "E_DOMAIN", "prices must be positive", "quotes")
    assert error_of(commodity.commodity_forwards, [(1, 1.0)], [0.0] * 11, [1]) == (
        "E_INPUT", "seasonality needs 12 terms", "seasonality")
    assert error_of(commodity.commodity_forwards, [(1, 1.0), (4, 2.0)], None, [5]) == (
        "E_OUT_OF_RANGE", "a month is outside the quoted range", "months")


def test_commodity_forwards_two_quotes_at_the_ends() -> None:
    out = commodity.commodity_forwards([(2, 80.0), (8, 90.0)], None, [2, 5, 8])
    assert out[0] == pytest.approx(80.0, rel=1e-15)
    assert out[2] == pytest.approx(90.0, rel=1e-15)
    assert out[1] == pytest.approx((80.0 * 90.0) ** 0.5, rel=1e-14)


def test_storage_carry_errors() -> None:
    funding = CurveData(date(2026, 1, 2), "LOG_LINEAR_DF", (date(2027, 1, 2),), (0.96,))
    fwd = [(date(2026, 3, 2), 70.0), (date(2026, 6, 2), 72.0)]
    assert error_of(commodity.storage_carry, funding, fwd, -0.1) == (
        "E_DOMAIN", "storage_cost must not be negative", "storage_cost")
    assert error_of(commodity.storage_carry, funding, fwd[:1], 0.1) == (
        "E_INPUT", "need two or more forwards, increasing after as_of", "forwards")
    assert error_of(commodity.storage_carry, funding, [fwd[0], (date(2026, 6, 2), 0.0)], 0.1) == (
        "E_DOMAIN", "forward prices must be positive", "forwards")
