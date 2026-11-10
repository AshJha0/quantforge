"""Checks from the stage B specs, beyond the golden files."""
from datetime import date

import pytest

from quantforge_core import curves, hedging, money, ois, schedules, sensitivities
from quantforge_core.calibration import fit
from quantforge_core.errors import QfError
from quantforge_core.ois import OisTrade, Quote

AS_OF = date(2026, 11, 6)
QUOTES = [
    Quote(t, r)
    for t, r in (("1M", 0.037), ("1Y", 0.035), ("2Y", 0.0335), ("5Y", 0.0335), ("10Y", 0.036))
]


@pytest.mark.parametrize("convention", ["SONIA", "SOFR"])
@pytest.mark.parametrize("interpolation", [m for m in curves.INTERPOLATIONS
                                           if m not in ("TENSION_SPLINE", "HYBRID")])
def test_both_solves_agree_and_reprice(convention, interpolation):
    a, error_a = ois.bootstrap(convention, AS_OF, QUOTES, interpolation, "SEQUENTIAL")
    b, error_b = ois.bootstrap(convention, AS_OF, QUOTES, interpolation, "GLOBAL")
    assert error_a < 1e-13 and error_b < 1e-13
    assert a.discount_factors == pytest.approx(b.discount_factors, abs=1e-12)


def test_negative_rates_give_factors_above_one():
    data, _ = ois.bootstrap("SONIA", AS_OF, [Quote("1Y", -0.005)], "LOG_LINEAR_DF")
    assert data.discount_factors[0] > 1


def test_general_floating_leg_is_not_telescoped_with_a_lag():
    data, _ = ois.bootstrap("SOFR", AS_OF, QUOTES, "LOG_LINEAR_DF")
    curve = curves.build(data)
    ps = ois.periods("SOFR", AS_OF, "10Y")
    _, floating = ois.legs("SOFR", ps, curve)
    telescoped = curve.discount(ps[0].start) - curve.discount(ps[-1].end)
    assert abs(floating - telescoped) > 1e-5


def test_key_rates_sum_to_parallel():
    trade = OisTrade("SONIA", "5Y", 0.034, 1e6, "PAY")
    dv01, keys = sensitivities.dv01(AS_OF, QUOTES, "LOG_LINEAR_DF", trade)
    assert sum(keys) == pytest.approx(dv01, rel=1e-5)


def test_money_rounds_half_to_even_and_has_no_negative_zero():
    assert money.round_money("2.675", "GBP")[0] == "2.68"
    assert money.round_money("2.665", "GBP")[0] == "2.66"
    assert money.round_money("-0.001", "GBP")[0] == "0.00"
    assert money.round_money("2.5", "JPY")[0] == "2"
    assert money.add_money("1.50", "GBP", "-1.5", "GBP")[0] == "0"


def test_stub_is_first_and_start_is_kept():
    periods = schedules.generate(
        date(2026, 1, 15), date(2027, 6, 15), 12, "GBLO", False, 0
    )
    assert periods[0].start == date(2026, 1, 15)
    assert len(periods) == 2


def first_order_gap(a, b, w, c, lam, x):
    residual = [sum(r[j] * x[j] for j in range(len(x))) + v for r, v in zip(a, b, strict=True)]
    worst = 0.0
    for i, xi in enumerate(x):
        g = 2 * sum(w[k] * a[k][i] * residual[k] for k in range(len(a)))
        if xi != 0:
            worst = max(worst, abs(g + lam * c[i] * (1 if xi > 0 else -1)))
        else:
            worst = max(worst, abs(g) - lam * c[i])
    return worst


@pytest.mark.parametrize("lam", [0.0, 0.1, 1.0, 50.0])
def test_hedge_first_order_conditions(lam):
    a = [[1.0, 0.2, 0.0], [0.3, 1.0, 0.4], [0.0, 0.3, 1.0], [0.1, 0.1, 0.2]]
    b, w, c = [10.0, -4.0, 6.0, 1.0], [1.0, 2.0, 1.0, 0.5], [1.0, 0.5, 2.0]
    x, _, _ = hedging.solve(a, b, w, c, lam)
    assert first_order_gap(a, b, w, c, lam, x) < 1e-9


def test_bounded_fit_stops_on_the_bound():
    x = [0.0, 1.0, 2.0, 3.0]
    y = [1.0, 3.0, 5.0, 7.0]
    result = fit("LINEAR", x, y, [0.0, 0.0], "LEVENBERG_MARQUARDT",
                 lower=[-10.0, -10.0], upper=[10.0, 1.5])
    assert result.parameters[1] == 1.5


def test_bounds_need_levenberg_marquardt():
    with pytest.raises(QfError) as e:
        fit("LINEAR", [1.0, 2.0], [1.0, 2.0], [0.0, 0.0], "BFGS", lower=[0.0, 0.0])
    assert e.value.code == "E_INPUT"


def test_non_finite_start_stops_at_once():
    with pytest.raises(QfError) as e:
        fit("ROSENBROCK", [], [], [-1.2e300, 1.0], "BFGS")
    assert e.value.code == "E_NON_FINITE"
