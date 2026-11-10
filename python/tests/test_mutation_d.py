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


def test_fx_point_tenor_months() -> None:
    from quantforge_core.cli.ops_fx import _months
    assert [_months(t) for t in ("1M", "6M", "18M", "1Y", "2Y", "10Y")] == [1, 6, 18, 12, 24, 120]
    assert error_of(_months, "2W") == ("E_SCHEMA", "FX points need a month or year tenor", "tenor")


def test_mbs_error_contracts() -> None:
    from quantforge_core import mbs
    good = (1e6, 0.06, 0.055, 360, 0, "PSA", 150.0)
    assert error_of(mbs.mbs_price, (1e6, 0.0, -0.01, 360, 0, "PSA", 150.0), 0.05, 0) == (
        "E_DOMAIN", "wac must be positive", "wac")
    for bad in ((0.0, *good[1:]), (*good[:5], "CPR", 1.0), (*good[:6], -1.0)):
        assert error_of(mbs.mbs_price, bad, 0.05, 0) == (
            "E_DOMAIN", "balance, rate or speed out of domain", "pool")
    assert error_of(mbs.mbs_price, good, -12.0, 0) == (
        "E_DOMAIN", "1 + yield/12 must be positive", "yield")


def test_cpi_curve_checks() -> None:
    from quantforge_core.inflation import CpiCurve, CpiCurveData
    years_rule = ("E_INPUT", "years must be strictly increasing positive integers")
    for quotes in (((0.0, 0.02),), ((1.0, 0.02), (1.0, 0.03)), ((101.0, 0.02),), ((1.5, 0.02),)):
        assert error_of(CpiCurve, CpiCurveData(24300, 300.0, quotes, None))[:2] == years_rule
    assert error_of(CpiCurve, CpiCurveData(24300, 300.0, ((1.0, 0.02),), (1.0,) * 11)) == (
        "E_INPUT", "seasonality needs 12 factors", "seasonality")


def test_compound_dated_checks() -> None:
    from quantforge_core.overnight import compound_dated
    mon, next_mon = date(2026, 11, 2), date(2026, 11, 9)
    fix = [(date(2026, 10, 26) + __import__("datetime").timedelta(days=i), 0.04)
           for i in range(15)]
    shift = ("E_INPUT", "shift_days is out of range for the method", "shift_days")
    assert error_of(compound_dated, "SOFR", mon, next_mon, "LOCKOUT", 5, fix) == shift
    assert error_of(compound_dated, "SOFR", mon, next_mon, "LOCKOUT", 0, fix) == shift
    assert error_of(compound_dated, "SOFR", date(2026, 11, 7), next_mon, "NONE", 0, fix) == (
        "E_INPUT", "start and end must be business days", "start")
    assert error_of(compound_dated, "SOFR", mon, next_mon, "NONE", 0,
                    [(mon, 0.04), (mon, 0.05)]) == (
        "E_INPUT", "two fixings on 2026-11-02", "fixings")
    compound_dated("SOFR", mon, next_mon, "LOCKOUT", 4, fix)  # k = n - 1 is allowed


def test_swaption_input_checks() -> None:
    from quantforge_core.caps_swaptions import swaption_price
    curve = CurveData(date(2026, 11, 9), "LOG_LINEAR_DF", (date(2027, 11, 9), date(2036, 11, 10)),
                      (0.96, 0.69))
    assert error_of(swaption_price, curve, curve, "BLACK_76", 0.2, "PAYER", 0, 60, 0.04,
                    1e6) == ("E_INPUT", "expiry_months must be at least 1", "expiry_months")
    assert error_of(swaption_price, curve, curve, "BLACK_76", -0.2, "PAYER", 12, 60, 0.04,
                    1e6) == ("E_DOMAIN", "vol is negative", "vol")
