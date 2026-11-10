"""Stage F Q1 properties (curve-framework.md, "Locality and smoothness", "Convergence")."""
import itertools
import math
from datetime import date, timedelta

import pytest

from quantforge_core import curve_interp, curves
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError

AS_OF = date(2026, 11, 9)
TS = [0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0]
RATES = [0.043, 0.0425, 0.0412, 0.039, 0.0365, 0.0355, 0.0352, 0.0356, 0.0364, 0.0376, 0.038,
         0.0368]
XS = [0.0, *(-r * t for r, t in zip(RATES, TS[1:], strict=True))]


def _make(method: str, xs: list[float] = XS, tension: float = 0.5, k: int = 3
          ) -> curve_interp.Interpolator:
    return curve_interp.make(method, TS, xs, tension, k)


@pytest.mark.parametrize("method", curve_interp.NEW_METHODS)
def test_nodes_are_returned(method: str) -> None:
    f = _make(method)
    for t, x in zip(TS, XS, strict=True):
        assert abs(f.log(t) - x) < 1e-14


@pytest.mark.parametrize("method", ["MONOTONE_CONVEX", "MONOTONIC_LOG_CUBIC", "TENSION_SPLINE"])
def test_forward_continuous_at_pillars(method: str) -> None:
    f = _make(method)
    for t in TS[1:-1]:
        assert abs(f.forward(t - 1e-12) - f.forward(t)) < 1e-9


def test_forward_is_derivative_of_log() -> None:
    for method in curve_interp.NEW_METHODS:
        f = _make(method)
        for t in (0.05, 0.7, 4.0, 12.5, 25.0, 35.0):
            h = 1e-6
            assert abs(-(f.log(t + h) - f.log(t - h)) / (2 * h) - f.forward(t)) < 1e-7, method


def test_tension_slope_continuous() -> None:
    f = _make("TENSION_SPLINE")
    assert isinstance(f, curve_interp.TensionSpline)
    for t in TS[1:-1]:
        assert abs(f.forward_slope(t - 1e-13) - f.forward_slope(t)) < 1e-8


def test_monotone_convex_locality() -> None:
    base = _make("MONOTONE_CONVEX")
    j = 6
    moved = list(XS)
    moved[j] -= 1e-4
    bumped = _make("MONOTONE_CONVEX", moved)
    for k in range(2000):
        t = 30.0 * k / 2000
        section = bisect(t)
        if section < j - 1 or section > j + 2:
            assert abs(bumped.forward(t) - base.forward(t)) < 1e-15


def bisect(t: float) -> int:
    """The spec's section number: section i runs from t_{i-1} to t_i."""
    return next(i for i in range(1, len(TS)) if t < TS[i])


def test_hybrid_steps_untouched_by_later_pillars() -> None:
    base = _make("HYBRID")
    moved = list(XS)
    moved[8] -= 1e-4
    bumped = _make("HYBRID", moved)
    for k in range(100):
        t = TS[3] * k / 100
        assert bumped.log(t) == base.log(t)


def test_monotone_convex_flat_curve() -> None:
    f = _make("MONOTONE_CONVEX", [-0.03 * t for t in TS])
    for t in (0.0, 0.3, 9.0, 40.0):
        assert abs(f.forward(t) - 0.03) < 1e-14


def test_tension_limits() -> None:
    cubic = _make("TENSION_SPLINE", tension=1e-9)
    errors = []
    for sigma in (0.08, 0.04, 0.02, 0.01):
        f = _make("TENSION_SPLINE", tension=sigma)
        errors.append(max(abs(f.log(t) - cubic.log(t)) for t in (0.3, 1.7, 6.0, 18.0)))
    for a, b in itertools.pairwise(errors):
        assert 3.5 < a / b < 4.5  # O(sigma^2)
    stiff = _make("TENSION_SPLINE", tension=1000.0)
    linear = curve_interp.LogLinear(TS, XS)
    assert max(abs(stiff.log(t) - linear.log(t)) for t in (0.3, 1.7, 6.0, 18.0)) < 1e-5


def _data(method: str, **kw: object) -> CurveData:
    dates = tuple(AS_OF + timedelta(days=round(t * 365)) for t in TS[1:])
    return CurveData(AS_OF, method, dates, tuple(math.exp(x) for x in XS[1:]), (),
                     kw.get("tension"), kw.get("step_end"))  # type: ignore[arg-type]


def test_option_checks() -> None:
    with pytest.raises(QfError) as e:
        curves.build(_data("TENSION_SPLINE"))
    assert e.value.code == "E_INPUT"
    with pytest.raises(QfError) as e:
        curves.build(_data("TENSION_SPLINE", tension=0.0))
    assert e.value.code == "E_DOMAIN"
    with pytest.raises(QfError) as e:
        curves.build(_data("HYBRID", step_end=AS_OF + timedelta(days=3)))
    assert e.value.code == "E_INPUT"


def test_tension_small_z_against_series() -> None:
    """Ruling F-35: below z = 1e-3 the coefficients match their Taylor series."""
    from quantforge_core.curve_interp import TensionSpline, chm, shm
    for x in (1e-7, 1e-4, 1e-3, 0.3, 0.7):
        assert abs(shm(x) - (x ** 3 / 6 + x ** 5 / 120 + x ** 7 / 5040)) <= 1e-15 * x ** 3 + x ** 9
        assert abs(chm(x) - (x * x / 2 + x ** 4 / 24 + x ** 6 / 720)) <= 1e-15 * x * x + x ** 8
    sigma, h = 1e-3, 0.5  # z = 5e-4
    z = sigma * h
    f = TensionSpline([0.0, h, 2 * h], [0.0, -0.02, -0.035], sigma)
    alpha = h / 6 * (1 - 7 * z * z / 60)
    beta = h / 3 * (1 - z * z / 15)
    # M_1 solves (beta + beta) M_1 = s_1 - s_0 with natural ends.
    expected = ((-0.035 + 0.02) / h - (-0.02) / h) / (2 * beta)
    assert abs(f.big_m[1] - expected) < 1e-12 * abs(expected)
    for u in (0.0, 0.1, 0.25, 0.5):
        series = (u / h) * (u * u - h * h) / 6 * (1 + sigma ** 2 * (3 * u * u - 7 * h * h) / 60)
        assert abs(f._r(u, h)[0] - series) <= 1e-15 + 1e-12 * abs(series)
    assert alpha > 0
