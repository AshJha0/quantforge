"""Checks taken from the specs themselves, beyond the golden files."""
import itertools
import json
import math
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from scipy import integrate as sp_integrate
from scipy import interpolate as sp_interpolate
from scipy import stats as sp_stats

from quantforge_core import (
    calendars,
    compounding,
    cos,
    daycount,
    integrate,
    interp,
    monte_carlo,
    pde,
    rng,
    roots,
    snapshot,
    sobol,
    stats,
    timezones,
)
from quantforge_core._sobol_data import DIRECTION_DATA
from quantforge_core.errors import QfError

ROOT = Path(__file__).resolve().parents[2]


def black_scholes_call(s, k, r, q, sigma, t):
    d1 = (math.log(s / k) + (r - q + sigma**2 / 2) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    n = sp_stats.norm.cdf
    return s * math.exp(-q * t) * n(d1) - k * math.exp(-r * t) * n(d2)


@pytest.mark.parametrize(
    ("convention", "start", "end", "kwargs", "expected"),
    [
        ("ACT_360", date(2024, 1, 1), date(2024, 7, 1), {}, 182 / 360),
        ("ACT_ACT_ISDA", date(2003, 11, 1), date(2004, 5, 1), {}, 61 / 365 + 121 / 366),
        ("ACT_ACT_ICMA", date(2003, 11, 1), date(2004, 5, 1),
         {"frequency": 2, "ref_start": date(2003, 11, 1), "ref_end": date(2004, 5, 1)}, 0.5),
        ("ACT_ACT_AFB", date(1994, 2, 10), date(1997, 6, 30), {}, 3 + 140 / 365),
        ("THIRTY_360_BOND", date(2024, 1, 31), date(2024, 3, 31), {}, 60 / 360),
        ("THIRTY_E_PLUS_360", date(2024, 1, 30), date(2024, 3, 31), {}, 61 / 360),
    ],
)
def test_daycount_worked_examples(convention, start, end, kwargs, expected):
    assert daycount.year_fraction(convention, start, end, **kwargs) == pytest.approx(expected)


@pytest.mark.parametrize("convention", ["THIRTY_E_PLUS_360", "THIRTY_E_360_ISDA", "ONE_ONE"])
def test_equal_dates_give_zero(convention):
    d = date(2024, 2, 29) if convention == "THIRTY_E_360_ISDA" else date(2024, 1, 31)
    assert daycount.year_fraction(convention, d, d, termination=d) == 0


def test_easter_known_dates():
    assert calendars.easter_sunday(2024) == date(2024, 3, 31)
    assert calendars.easter_sunday(2000) == date(2000, 4, 23)


def test_calendar_range_at_the_edge():
    with pytest.raises(QfError) as e:
        calendars.adjust("GBLO", date(2000, 1, 1), "PRECEDING")
    assert e.value.code == "E_DATE_RANGE"


def test_end_of_month_needs_the_last_business_day_itself():
    # 2024-03-29 is Good Friday, so it is not the last business day of March. SPEC_QUESTIONS.md Q1.
    args = ("GBLO", date(2024, 3, 29), "1M", "MODIFIED_FOLLOWING")
    assert calendars.add_tenor(*args, True) == date(2024, 4, 29)
    assert calendars.add_tenor("GBLO", date(2024, 3, 28), "1M", "FOLLOWING", True) == date(
        2024, 4, 30
    )


def test_summary_at_a_large_offset():
    s = stats.summary([1000000001.0, 1000000002.0, 1000000004.0, 1000000003.0, 1000000007.0])
    assert s["skewness"] == pytest.approx(stats.summary([1.0, 2.0, 4.0, 3.0, 7.0])["skewness"])


@pytest.mark.parametrize(
    ("c", "expected"),
    [
        (compounding.Compounding("SIMPLE"), 1 / 1.1),
        (compounding.Compounding("PERIODIC", 2), 1.025**-4),
        (compounding.Compounding("CONTINUOUS"), math.exp(-0.1)),
    ],
)
def test_compounding_examples(c, expected):
    assert compounding.discount_factor(0.05, 2, c) == pytest.approx(expected, rel=1e-14)


def test_snapshot_worked_example():
    form, _ = snapshot.hash_document('{"b":1,"a":[true,null,"x\\n"]}')
    assert form == '{"a":[true,null,"x\\u000a"],"b":#3ff0000000000000}'


def test_snapshot_syntax_error_beats_overflow():
    with pytest.raises(QfError) as e:
        snapshot.hash_document('{"a":1e400,')
    assert e.value.code == "E_PARSE"


def test_snapshot_nested_id_stays_and_negative_zero_is_plus_zero():
    form, _ = snapshot.hash_document('{"snapshot_id":"x","n":{"snapshot_id":-0.0}}')
    assert form == '{"n":{"snapshot_id":#0000000000000000}}'


def test_snapshot_nesting_of_64_levels():
    snapshot.hash_document('{"a":' + "[" * 63 + "]" * 63 + "}")


def test_rng_reference_vector():
    assert rng.set_state_next_u64([1, 2, 3, 4], 3) == [11520, 0, 1509978240]


@given(st.floats(min_value=1e-12, max_value=1 - 1e-12))
def test_ppnd16_inverts_the_normal_cdf(p):
    z = rng.ppnd16(p)
    assert sp_stats.norm.cdf(z) == pytest.approx(p, rel=1e-10)


def test_sobol_table_equals_the_spec_data():
    path = ROOT / "specifications" / "01-core" / "data" / "sobol-joe-kuo-d6-64.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["dimensions"]
    assert [(r["s"], r["a"], tuple(r["m"])) for r in rows] == list(DIRECTION_DATA)


def test_sobol_skip_equals_walking():
    walked = sobol.points(5, 40)
    assert sobol.points(5, 10, skip=30) == walked[30:]


def test_sobol_first_point():
    assert sobol.points(64, 1) == [[0.5] * 64]


@pytest.mark.parametrize("finder", [roots.bisection, roots.brent])
def test_root_targets(finder):
    r = finder(lambda x: math.exp(x) - 2, 0.0, 1.0)
    assert r.root == pytest.approx(math.log(2), abs=1e-10)
    assert r.iterations <= (60 if finder is roots.bisection else 20)


def test_newton_stays_in_bracket():
    r = roots.newton(lambda x: math.atan(1000 * (x - 0.3)),
                     lambda x: 1000 / (1 + 1e6 * (x - 0.3) ** 2), 0.9, 0.0, 1.0)
    assert r.root == pytest.approx(0.3, abs=1e-10)


def test_gauss_legendre_target():
    assert integrate.gauss_legendre(math.exp, 0, 1, 16) == pytest.approx(math.e - 1, abs=1e-14)


@pytest.mark.parametrize("n", [1, 2, 5, 16, 33, 64])
def test_legendre_weights_sum_to_two(n):
    nodes, weights = integrate.legendre_rule(n)
    assert math.fsum(weights) == pytest.approx(2, abs=1e-13)
    assert list(nodes) == sorted(nodes)


def test_kronrod_handles_the_singular_end():
    value, _ = integrate.gauss_kronrod(lambda x: 1 / math.sqrt(x), 0, 1)
    assert value == pytest.approx(2, abs=1e-9)


def test_kronrod_against_scipy():
    def f(x):
        return math.cos(50 * x) * math.exp(-x)

    value, _ = integrate.gauss_kronrod(f, 0, 2)
    assert value == pytest.approx(sp_integrate.quad(f, 0, 2, limit=500)[0], abs=1e-9)


X = [0.0, 0.5, 1.5, 2.0, 4.0, 4.5]
Y = [1.0, 2.0, 1.5, 3.0, 2.5, 4.0]
AT = [0.0, 0.3, 0.5, 1.1, 2.0, 3.3, 4.5]


@pytest.mark.parametrize(
    ("method", "reference", "params"),
    [
        ("cubic_natural", sp_interpolate.CubicSpline(X, Y, bc_type="natural"), {}),
        ("cubic_not_a_knot", sp_interpolate.CubicSpline(X, Y, bc_type="not-a-knot"), {}),
        ("cubic_clamped", sp_interpolate.CubicSpline(X, Y, bc_type=((1, 0.5), (1, -1.0))),
         {"slope_start": 0.5, "slope_end": -1.0}),
    ],
)
def test_splines_against_scipy(method, reference, params):
    values, derivatives = interp.evaluate(method, X, Y, AT, **params)
    assert values == pytest.approx(list(reference(AT)), abs=1e-11)
    assert derivatives == pytest.approx(list(reference(AT, 1)), abs=1e-10)


def test_pchip_does_not_overshoot():
    x, y = [0.0, 1.0, 2.0, 5.0], [0.0, 0.0, 1.0, 1.1]
    grid = [i * 0.05 for i in range(101)]
    values, _ = interp.evaluate("monotone_pchip", x, y, grid)
    assert all(b >= a - 1e-14 for a, b in itertools.pairwise(values))


@pytest.mark.parametrize("p", [0.5, 3.0, 50.0])
def test_tension_reproduces_knots_with_continuous_slope(p):
    values, _ = interp.evaluate("tension", X, Y, X, tension=p)
    assert values == pytest.approx(Y, abs=1e-12)
    _, left = interp.evaluate("tension", X, Y, [1.5 - 1e-9], tension=p)
    _, right = interp.evaluate("tension", X, Y, [1.5], tension=p)
    assert left[0] == pytest.approx(right[0], abs=1e-5)


def test_tension_zero_is_natural_cubic():
    assert interp.evaluate("tension", X, Y, AT, tension=0.0) == interp.evaluate(
        "cubic_natural", X, Y, AT
    )


@given(
    st.lists(st.floats(min_value=-0.02, max_value=0.1), min_size=2, max_size=8),
    st.booleans(),
)
def test_monotone_convex_reprices_every_input(rates, positive):
    t = [0.5 * (i + 1) for i in range(len(rates))]
    try:
        _, zero_rates = interp.monotone_convex(t, rates, t, positive)
    except QfError as e:
        assert e.code == "E_DOMAIN" and positive
        return
    assert zero_rates == pytest.approx(rates, abs=1e-12)


def test_normal_left_tail():
    _, cdf = stats.normal([-37.0])
    assert cdf[0] == pytest.approx(5.7255712225239e-300, rel=1e-12)


def test_summary_constant_series():
    s = stats.summary([0.1, 0.1, 0.1])
    assert s["variance"] == 0 and s["skewness"] is None and s["excess_kurtosis"] is None


def test_rolling_leaves_no_residue():
    assert stats.rolling([1e8, 1.0, 2.0, 3.0], 2, "STDEV")[-1] == pytest.approx(math.sqrt(0.5))


def test_ols_against_scipy():
    x = [1.0, 2.0, 4.0, 7.0, 8.0]
    y = [1.1, 1.9, 4.4, 6.5, 8.3]
    fit = stats.ols(x, y)
    ref = sp_stats.linregress(x, y)
    assert fit.beta == pytest.approx(ref.slope)
    assert fit.se_beta == pytest.approx(ref.stderr)
    assert fit.se_alpha == pytest.approx(ref.intercept_stderr)


def test_pde_target_and_second_order():
    exact = black_scholes_call(100, 100, 0.05, 0.02, 0.2, 1)

    def error(j, m):
        return abs(pde.bs_european("CALL", 100, 100, 0.05, 0.02, 0.2, 1, j, m).price - exact)

    assert error(400, 200) < 1e-3
    assert 3 < error(200, 100) / error(400, 200) < 5


def test_monte_carlo_targets():
    args = ("CALL", 100.0, 100.0, 0.05, 0.02, 0.2, 1.0)
    plain = monte_carlo.gbm_european(*args, 100000, 1, 7, 0, "PLAIN")
    anti = monte_carlo.gbm_european(*args, 100000, 1, 7, 0, "ANTITHETIC")
    control = monte_carlo.gbm_european(*args, 100000, 1, 7, 0, "CONTROL_VARIATE")
    quasi = monte_carlo.gbm_european(*args, 65536, 1, 7, 0, "SOBOL")
    exact = black_scholes_call(100, 100, 0.05, 0.02, 0.2, 1)
    assert plain[1] == pytest.approx(0.045, abs=0.002)
    assert anti[1] < plain[1] and control[1] < plain[1]
    assert abs(plain[0] - exact) <= 4 * plain[1]
    assert abs(quasi[0] - exact) < 0.01


def test_cos_black_scholes_target():
    price, _, _ = cos.european(
        "CALL", 100, 100, 0.05, 0.02, 1, cos.BlackScholes(0.2), 256, 10.0
    )
    assert price == pytest.approx(black_scholes_call(100, 100, 0.05, 0.02, 0.2, 1), abs=1e-10)


def test_cos_heston_near_zero_vol_of_vol():
    h = cos.Heston(0.04, 1.5, 0.04, 1e-3, -0.7)
    price, _, _ = cos.european("PUT", 100, 100, 0.0, 0.0, 1, h, 256, 10.0)
    assert price == pytest.approx(black_scholes_call(100, 100, 0, 0, 0.2, 1), abs=1e-3)


def seconds(y, mo, d, h=0, mi=0, s=0):
    return timezones.date_seconds(date(y, mo, d)) + h * 3600 + mi * 60 + s


@pytest.mark.parametrize(
    ("zone", "instant", "offset"),
    [
        ("Europe/London", seconds(2024, 3, 31, 0, 59, 59), 0),
        ("Europe/London", seconds(2024, 3, 31, 1), 3600),
        ("Europe/London", seconds(2024, 10, 27, 0, 59, 59), 3600),
        ("Europe/London", seconds(2024, 10, 27, 1), 0),
        ("Europe/Berlin", seconds(2024, 7, 1), 7200),
        ("America/New_York", seconds(2024, 3, 10, 6, 59, 59), -18000),
        ("America/New_York", seconds(2024, 3, 10, 7), -14400),
        ("America/New_York", seconds(2024, 11, 3, 6), -18000),
        ("Asia/Tokyo", seconds(2024, 7, 1), 32400),
    ],
)
def test_zone_transitions(zone, instant, offset):
    assert timezones.utc_offset(zone, instant) == offset


def test_overlap_choices():
    local = seconds(2024, 10, 27, 1, 30)
    earlier = timezones.to_instant("Europe/London", local, "EARLIER")
    later = timezones.to_instant("Europe/London", local, "LATER")
    assert later - earlier == 3600
    assert earlier == seconds(2024, 10, 27, 0, 30)


def test_cutoff_boundary_and_weekend():
    assert timezones.business_date(
        seconds(2024, 7, 1, 14, 59, 59), "Europe/London", 16 * 3600, "GBLO"
    ) == date(2024, 7, 1)
    assert timezones.business_date(
        seconds(2024, 7, 1, 15), "Europe/London", 16 * 3600, "GBLO"
    ) == date(2024, 7, 2)
    assert timezones.business_date(
        seconds(2024, 7, 6, 10), "Europe/London", 16 * 3600, "GBLO"
    ) == date(2024, 7, 8)
