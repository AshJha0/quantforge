"""Unit tests for the G2++ lane of quantforge_core.shortrate and its small-a building blocks
(02-curves short-rate spec, rulings G-2, G-3, G-14). The series branches are checked against the
closed forms near the switch and against leading Taylor terms; the G2++ variance against
scipy.integrate.quad of its defining integral (Brigo and Mercurio, eq. 4.10)."""

import math

import pytest
from scipy.integrate import quad
from scipy.stats import norm

from quantforge_core import shortrate as sr
from quantforge_core.errors import QfError


def _err(fn, code: str, field: str) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code and e.value.field == field


def test_b_factor_and_series() -> None:
    assert sr.b_factor(0.5, 2.0) == pytest.approx((1 - math.exp(-1.0)) / 0.5)
    assert sr.b_factor(1e-12, 3.0) == pytest.approx(3.0, rel=1e-10)
    # B - tau for tiny u: -a tau^2 / 2 + a^2 tau^3 / 6
    a, t = 1e-3, 2.0
    assert sr._b_minus_tau(a, t) == pytest.approx(-a * t * t / 2 + a * a * t**3 / 6, rel=1e-6)
    for a, t in ((0.2, 2.4), (0.24, 2.0), (0.3, 2.0), (1.0, 3.0)):
        closed = -math.expm1(-a * t) / a - t
        assert sr._b_minus_tau(a, t) == pytest.approx(closed, rel=1e-12)


def _q_closed(u: float) -> float:
    return (1.5 - 2 * math.exp(-u) + math.exp(-2 * u) / 2 - u) / u**3


def test_q_series_and_gauss_variance() -> None:
    assert sr._q_series(0.0) == pytest.approx(-1 / 3)
    assert sr._q_series(1e-4) == pytest.approx(-1 / 3 + 0.25e-4, rel=1e-8)
    for u in (0.1, 0.3, 0.49):
        assert sr._q_series(u) == pytest.approx(_q_closed(u), rel=1e-9)
    for a, s, t in ((0.1, 0.01, 2.0), (0.3, 0.02, 1.0), (0.5, 0.01, 5.0), (0.01, 0.02, 10.0)):
        integral = quad(lambda x, a=a, s=s: (s * (1 - math.exp(-a * x)) / a) ** 2, 0, t)[0]
        assert sr._gauss_variance(a, s, t) == pytest.approx(integral, rel=1e-9)


def test_cross_term() -> None:
    for a, b, t in ((0.1, 0.05, 2.0), (0.3, 0.4, 1.0), (0.5, 0.2, 3.0), (0.01, 0.02, 5.0)):
        integral = quad(
            lambda x, a=a, b=b: (1 - math.exp(-a * x)) / a * (1 - math.exp(-b * x)) / b, 0, t
        )[0]
        assert sr._cross_term(a, b, t) == pytest.approx(integral, rel=1e-9)
    # leading term tau^3 / 3 as the rates vanish
    assert sr._cross_term(1e-6, 2e-6, 1.5) == pytest.approx(1.5**3 / 3, rel=1e-5)


def test_curve() -> None:
    c = sr.make_curve([1.0, 2.0], [0.95, 0.9])
    assert c.discount(0.0) == 1.0
    assert c.discount(-1.0) == 1.0
    assert c.discount(0.5) == pytest.approx(math.sqrt(0.95))
    assert c.discount(1.0) == pytest.approx(0.95)
    assert c.discount(1.5) == pytest.approx(math.sqrt(0.95 * 0.9))
    assert c.discount(2.0) == pytest.approx(0.9)
    f2 = math.log(0.95 / 0.9)
    assert c.discount(3.0) == pytest.approx(0.9 * math.exp(-f2))
    assert c.forward(0.5) == pytest.approx(-math.log(0.95))
    assert c.forward(1.0) == pytest.approx(f2)
    assert c.forward(5.0) == pytest.approx(f2)
    assert c.forward(-1.0) == pytest.approx(-math.log(0.95))
    _err(lambda: sr.make_curve([], []), "E_INPUT", "curve")
    _err(lambda: sr.make_curve([1.0], [0.9, 0.8]), "E_INPUT", "curve")
    _err(lambda: sr.make_curve([0.0, 1.0], [0.9, 0.8]), "E_INPUT", "curve.times")
    _err(lambda: sr.make_curve([2.0, 1.0], [0.9, 0.8]), "E_INPUT", "curve.times")
    _err(lambda: sr.make_curve([1.0, 2.0], [0.9, 0.0]), "E_DOMAIN", "curve.discount_factors")


CURVE = sr.make_curve([1.0, 5.0, 10.0], [0.97, 0.85, 0.7])


def _v_integral(m: sr.G2, tau: float) -> float:
    def f(x: float) -> float:
        ba = (1 - math.exp(-m.a * x)) / m.a
        bb = (1 - math.exp(-m.b * x)) / m.b
        return (m.sigma * ba) ** 2 + (m.eta * bb) ** 2 + 2 * m.rho * m.sigma * m.eta * ba * bb

    return quad(f, 0, tau)[0]


def test_make_g2_and_variance() -> None:
    m = sr.make_g2(CURVE, 0.5, 0.01, 0.1, 0.008, -0.7)
    for tau in (0.5, 2.0, 7.0):
        assert m.v(tau) == pytest.approx(_v_integral(m, tau), rel=1e-9)
    _err(lambda: sr.make_g2(CURVE, 0.0, 0.01, 0.1, 0.01, 0.0), "E_DOMAIN", "a")
    _err(lambda: sr.make_g2(CURVE, 0.1, 0.0, 0.1, 0.01, 0.0), "E_DOMAIN", "sigma")
    _err(lambda: sr.make_g2(CURVE, 0.1, 0.01, -0.1, 0.01, 0.0), "E_DOMAIN", "b")
    _err(lambda: sr.make_g2(CURVE, 0.1, 0.01, 0.1, 0.0, 0.0), "E_DOMAIN", "eta")
    _err(lambda: sr.make_g2(CURVE, 0.1, 0.01, 0.1, 0.01, 1.0), "E_DOMAIN", "rho")
    _err(lambda: sr.make_g2(CURVE, 0.1, 0.01, 0.1, 0.01, -1.0), "E_DOMAIN", "rho")
    _err(sr.no_states, "E_INPUT", "x")


def test_g2pp_zcb() -> None:
    m = sr.make_g2(CURVE, 0.5, 0.01, 0.1, 0.008, -0.7)
    # at t = 0 with zero states the model returns the curve
    out = sr.g2pp_zcb(m, 0.0, 0.0, 0.0, 5.0)
    assert out["discount_factor"] == pytest.approx(0.85, rel=1e-12)
    assert out["zero_rate"] == pytest.approx(-math.log(0.85) / 5.0)
    t, mat, x, y = 1.0, 5.0, 0.01, -0.005
    tau = mat - t
    ln_p = (
        math.log(0.85 / 0.97)
        + 0.5 * (_v_integral(m, tau) - _v_integral(m, mat) + _v_integral(m, t))
        - (1 - math.exp(-0.5 * tau)) / 0.5 * x
        - (1 - math.exp(-0.1 * tau)) / 0.1 * y
    )
    got = sr.g2pp_zcb(m, x, y, t, mat)
    assert got["discount_factor"] == pytest.approx(math.exp(ln_p), rel=1e-9)
    assert got["zero_rate"] == pytest.approx(-ln_p / tau, rel=1e-8)
    _err(lambda: sr.g2pp_zcb(m, 0.0, 0.0, -0.1, 5.0), "E_DOMAIN", "t_years")
    _err(lambda: sr.g2pp_zcb(m, 0.0, 0.0, 5.0, 5.0), "E_DOMAIN", "maturity_years")


def test_g2pp_zcb_option() -> None:
    m = sr.make_g2(CURVE, 0.5, 0.01, 0.1, 0.008, -0.7)
    e, mat, k = 1.0, 5.0, 0.87
    ba, bb = (1 - math.exp(-0.5 * 4)) / 0.5, (1 - math.exp(-0.1 * 4)) / 0.1
    var = (
        0.01**2 / (2 * 0.5) * ba**2 * (1 - math.exp(-2 * 0.5 * e))
        + 0.008**2 / (2 * 0.1) * bb**2 * (1 - math.exp(-2 * 0.1 * e))
        + 2 * -0.7 * 0.01 * 0.008 / 0.6 * ba * bb * (1 - math.exp(-0.6 * e))
    )
    sp = math.sqrt(var)
    pt, ps = 0.97, 0.85
    h = math.log(ps / (k * pt)) / sp + sp / 2
    call = ps * norm.cdf(h) - k * pt * norm.cdf(h - sp)
    put = k * pt * norm.cdf(-h + sp) - ps * norm.cdf(-h)
    c = sr.g2pp_zcb_option(m, "CALL", k, e, mat, 100.0)
    assert c["price"] == pytest.approx(100 * call, rel=1e-9)
    assert c["bond_price_expiry"] == pytest.approx(pt)
    assert c["bond_price_maturity"] == pytest.approx(ps)
    p = sr.g2pp_zcb_option(m, "PUT", k, e, mat, 100.0)
    assert p["price"] == pytest.approx(100 * put, rel=1e-9)
    f = sr.g2pp_zcb_option
    _err(lambda: f(m, "CALL", k, 0.0, mat, 1.0), "E_DOMAIN", "expiry_years")
    _err(lambda: f(m, "CALL", k, e, e, 1.0), "E_DOMAIN", "maturity_years")
    _err(lambda: f(m, "CALL", 0.0, e, mat, 1.0), "E_DOMAIN", "strike")
    _err(lambda: f(m, "STRADDLE", k, e, mat, 1.0), "E_INPUT", "option_type")


def test_gaussian_helpers() -> None:
    a, s, e, mat = 0.1, 0.01, 1.0, 3.0
    expect = s * (1 - math.exp(-a * 2)) / a * math.sqrt((1 - math.exp(-2 * a * e)) / (2 * a))
    assert sr.gaussian_sigma_p(a, s, e, mat) == pytest.approx(expect)
    h = math.log(0.9 / (0.95 * 0.92)) / 0.02 + 0.01
    expect_c = 0.9 * norm.cdf(h) - 0.95 * 0.92 * norm.cdf(h - 0.02)
    assert sr.gaussian_call(0.9, 0.95, 0.92, 0.02) == pytest.approx(expect_c, rel=1e-9)
