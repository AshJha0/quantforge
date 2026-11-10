"""Boundary tests for bonds.py aimed at mutants that survived the stage D mutation sample
(dates_around, _root_decreasing, z_spread, _repo_setup)."""
import math
from datetime import date

import pytest

from quantforge_core import bonds
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError

BOND = bonds.Bond(date(2030, 6, 15), 0.05, 2)
FLAT = CurveData(date(2026, 6, 15), "LOG_LINEAR_DF", (date(2027, 6, 15), date(2036, 6, 15)),
                 (math.exp(-0.04 * 365 / 365), math.exp(-0.04 * 3653 / 365)))


def test_dates_around_settlement_on_a_coupon_date() -> None:
    prev, after = bonds.dates_around(date(2030, 6, 15), 2, date(2029, 12, 15))
    assert prev == date(2029, 12, 15)
    assert after == [date(2030, 6, 15)]


def test_dates_around_between_coupons() -> None:
    prev, after = bonds.dates_around(date(2030, 6, 15), 2, date(2029, 3, 1))
    assert prev == date(2028, 12, 15)
    assert after == [date(2029, 6, 15), date(2029, 12, 15), date(2030, 6, 15)]


def test_dates_around_quarterly_and_annual() -> None:
    assert bonds.dates_around(date(2030, 6, 15), 4, date(2030, 1, 1)) == (
        date(2029, 12, 15), [date(2030, 3, 15), date(2030, 6, 15)])
    assert bonds.dates_around(date(2030, 6, 15), 1, date(2029, 6, 16)) == (
        date(2029, 6, 15), [date(2030, 6, 15)])


@pytest.mark.parametrize("settlement", [date(2030, 6, 15), date(2030, 7, 1)])
def test_dates_around_settlement_not_before_maturity(settlement: date) -> None:
    with pytest.raises(QfError) as e:
        bonds.dates_around(date(2030, 6, 15), 2, settlement)
    assert e.value.code == "E_DATE_ORDER"


def test_root_decreasing_widens_high() -> None:
    root = bonds._root_decreasing(lambda x: 50.0 - x, 0.0, 1.0)
    assert abs(root - 50.0) < 1e-12


def test_root_decreasing_root_inside_first_bracket() -> None:
    assert abs(bonds._root_decreasing(lambda x: 0.25 - x, 0.0, 1.0) - 0.25) < 1e-15


def test_root_decreasing_low_not_positive() -> None:
    with pytest.raises(QfError) as e:
        bonds._root_decreasing(lambda x: -1.0 - x, 0.0, 1.0)
    assert e.value.code == "E_NO_CONVERGENCE"
    with pytest.raises(QfError):
        bonds._root_decreasing(lambda x: -x, 0.0, 1.0)  # f(low) == 0 is not > 0


def test_root_decreasing_no_upper_bracket() -> None:
    with pytest.raises(QfError) as e:
        bonds._root_decreasing(lambda x: 1.0, 0.0, 1.0)
    assert e.value.code == "E_NO_CONVERGENCE"


def _dirty(z: float, settlement: date) -> float:
    fl, curve = bonds._curve_setup(BOND, settlement, FLAT)
    return bonds._curve_dirty(fl, curve, settlement, z)


@pytest.mark.parametrize("z", [-0.35, -0.02, 0.0, 0.03, 0.4])
def test_z_spread_round_trip(z: float) -> None:
    settlement = date(2026, 6, 15)
    fl, _ = bonds._curve_setup(BOND, settlement, FLAT)
    clean = _dirty(z, settlement) - fl.accrued
    assert abs(bonds.z_spread(BOND, settlement, FLAT, clean) - z) < 1e-10


def test_z_spread_needs_positive_dirty() -> None:
    settlement = date(2026, 7, 1)
    fl, _ = bonds._curve_setup(BOND, settlement, FLAT)
    with pytest.raises(QfError) as e:
        bonds.z_spread(BOND, settlement, FLAT, -fl.accrued)
    assert e.value.code == "E_DOMAIN"


def test_repo_setup_boundaries() -> None:
    with pytest.raises(QfError) as e:
        bonds._repo_setup(BOND, date(2027, 1, 1), date(2027, 1, 1))
    assert e.value.code == "E_DATE_ORDER"
    with pytest.raises(QfError) as e:
        bonds._repo_setup(BOND, date(2027, 1, 1), BOND.maturity)
    assert e.value.code == "E_INPUT"


def test_repo_setup_coupon_on_end_counts_and_on_start_does_not() -> None:
    acc0, acc1, paid = bonds._repo_setup(BOND, date(2026, 12, 15), date(2027, 6, 15))
    assert paid == [(date(2027, 6, 15), 2.5)]
    assert acc0 == 0.0 and acc1 == 0.0
    _, _, none = bonds._repo_setup(BOND, date(2026, 12, 16), date(2027, 6, 14))
    assert none == []
    acc0, acc1, two = bonds._repo_setup(BOND, date(2026, 12, 1), date(2027, 12, 20))
    assert [d for d, _ in two] == [date(2026, 12, 15), date(2027, 6, 15), date(2027, 12, 15)]
    assert acc0 > 0 and acc1 > 0


def test_error_fields_and_messages() -> None:
    with pytest.raises(QfError) as e:
        bonds._repo_setup(BOND, date(2027, 1, 1), date(2026, 12, 1))
    assert e.value.field == "end"
    with pytest.raises(QfError) as e:
        bonds.dates_around(date(2030, 6, 15), 2, date(2030, 6, 15))
    assert str(e.value.message) == "settlement is not before maturity"
    assert e.value.field == "settlement"


def test_z_spread_exactly_at_the_first_lower_bound() -> None:
    """Settlement on a coupon date (accrued 0), so the gap at z = -0.1 is exactly 0: the bracket
    must still widen below it."""
    settlement = date(2026, 6, 15)
    fl, _ = bonds._curve_setup(BOND, settlement, FLAT)
    assert fl.accrued == 0.0
    clean = _dirty(-0.1, settlement)
    assert abs(bonds.z_spread(BOND, settlement, FLAT, clean) + 0.1) < 1e-12
