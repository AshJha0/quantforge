"""Stage G: kill tests for the credit-module mutants that survived PR #29's sample.

Survivors from that run: credit.x_maturity__mutmut_68, credit_options.x__strike_hazard__mutmut_35
and credit_options.x_joint_default__mutmut_44. The mutant diffs were not regenerated locally (no
mutmut on Windows), so these tests pin every boundary, error code, message and field of the three
functions rather than one guessed edit.
"""
import math
from datetime import date

import pytest

from quantforge_core import credit
from quantforge_core import credit_options as co
from quantforge_core.errors import QfError


def _err(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code, e.value.message, e.value.field


# credit.maturity

@pytest.mark.parametrize("trade,tenor,expected", [
    (date(2026, 9, 20), "5Y", date(2031, 12, 20)),   # on the September roll date
    (date(2026, 9, 19), "5Y", date(2031, 6, 20)),    # the day before it
    (date(2026, 3, 20), "1Y", date(2027, 6, 20)),    # on the March roll date
    (date(2026, 3, 19), "1Y", date(2026, 12, 20)),   # the day before: previous December
    (date(2026, 1, 2), "3M", date(2026, 3, 20)),
    (date(2026, 12, 31), "6M", date(2027, 6, 20)),
    (date(2026, 11, 6), "10Y", date(2036, 12, 20)),
    (date(2026, 11, 6), "18M", date(2028, 6, 20)),
])
def test_maturity_roll_boundaries(trade, tenor, expected) -> None:
    assert credit.maturity(trade, tenor) == expected


@pytest.mark.parametrize("tenor", ["5W", "5D", "5y", "5m"])
def test_maturity_rejects_other_units(tenor) -> None:
    assert _err(credit.maturity, date(2026, 11, 6), tenor) == (
        "E_SCHEMA", "a CDS tenor is in months or years", "tenor")


# credit_options._strike_hazard

@pytest.mark.parametrize("strike,recovery", [(0.0001, 0.4), (0.01, 0.4), (0.05, 0.25), (0.3, 0.0)])
def test_strike_hazard_solves_the_strike(strike, recovery) -> None:
    expiry, mat = date(2027, 3, 20), date(2031, 12, 20)
    h_k, annuity = co._strike_hazard(expiry, mat, 0.03, recovery, strike)
    protection, a = co._legs(expiry, expiry, mat, 0.03, h_k, recovery)
    assert annuity == a
    assert protection / annuity == pytest.approx(strike, rel=1e-12)
    # the bisection is tight: a hazard one part in 1e-6 off misses the strike
    off = co._legs(expiry, expiry, mat, 0.03, h_k * (1 + 1e-6), recovery)
    assert off[0] / off[1] != pytest.approx(strike, rel=1e-12)


# credit_options.joint_default

def test_joint_default_values_and_correlation() -> None:
    p1, p2 = 0.02, 0.03
    for copula, nu in (("GAUSSIAN", None), ("STUDENT_T", 4.0)):
        out = co.joint_default(copula, [p1, p2], 0.3, nu)
        assert set(out) == {"joint_default_probability", "default_correlation"}
        joint = out["joint_default_probability"]
        assert out["default_correlation"] == pytest.approx(
            (joint - p1 * p2) / math.sqrt(p1 * (1 - p1) * p2 * (1 - p2)), rel=1e-14)
    independent = co.joint_default("GAUSSIAN", [p1, p2], 0.0, None)
    assert independent["joint_default_probability"] == pytest.approx(p1 * p2, rel=1e-9)
    assert independent["default_correlation"] == pytest.approx(0.0, abs=1e-9)
    # asymmetric probabilities: swapping p1 and p2 inside the formula would still pass above
    assert co.joint_default("GAUSSIAN", [0.01, 0.2], -0.5, None)["joint_default_probability"] \
        < 0.01 * 0.2
    # nu is ignored for the Gaussian copula
    assert co.joint_default("GAUSSIAN", [p1, p2], 0.3, 4.0) == co.joint_default(
        "GAUSSIAN", [p1, p2], 0.3, None)


@pytest.mark.parametrize("args,expected", [
    (("GAUSSIAN", [0.1], 0.3, None),
     ("E_INPUT", "default_probabilities needs two values", "default_probabilities")),
    (("GAUSSIAN", [0.1, 0.1, 0.1], 0.3, None),
     ("E_INPUT", "default_probabilities needs two values", "default_probabilities")),
    (("STUDENT_T", [0.1, 0.1], 0.3, None),
     ("E_INPUT", "STUDENT_T needs degrees_of_freedom", "degrees_of_freedom")),
    (("GAUSSIAN", [0.0, 0.1], 0.3, None),
     ("E_DOMAIN", "a default probability is outside (0, 1)", "default_probabilities")),
    (("GAUSSIAN", [0.1, 1.0], 0.3, None),
     ("E_DOMAIN", "a default probability is outside (0, 1)", "default_probabilities")),
    (("GAUSSIAN", [0.1, 0.1], 1.0, None),
     ("E_DOMAIN", "|correlation| must be below 1", "correlation")),
    (("GAUSSIAN", [0.1, 0.1], -1.0, None),
     ("E_DOMAIN", "|correlation| must be below 1", "correlation")),
    (("STUDENT_T", [0.1, 0.1], 0.3, 0.0),
     ("E_DOMAIN", "degrees_of_freedom must be above 0", "degrees_of_freedom")),
    (("STUDENT_T", [0.1, 0.1], 0.3, -1.0),
     ("E_DOMAIN", "degrees_of_freedom must be above 0", "degrees_of_freedom")),
])
def test_joint_default_errors(args, expected) -> None:
    assert _err(co.joint_default, *args) == expected


def test_joint_default_edges_accepted() -> None:
    co.joint_default("GAUSSIAN", [1e-9, 1 - 1e-9], 0.999, None)
    co.joint_default("STUDENT_T", [0.1, 0.1], -0.999, 0.5)
