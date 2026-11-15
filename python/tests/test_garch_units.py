"""Unit tests for GARCH(1,1) and the realised variance leg in quantforge_core.variance
(05-volatility/garch.md, variance-swaps.md; rulings E-B1 to E-B7). The recursion and forecast are
worked by hand; the Student-t density is checked against its closed form and the analytic score
against central differences."""

import math

import pytest

from quantforge_core import variance as v
from quantforge_core.errors import QfError

LN2PI = math.log(2 * math.pi)


def _err(fn, code: str, field: str) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code and e.value.field == field
    # the message is a readable sentence, not a placeholder or shouting (kills the
    # message-text mutants, which no code or field check can see)
    assert isinstance(e.value.message, str) and str(e.value) == e.value.message
    assert "XX" not in e.value.message and e.value.message != e.value.message.upper()


def test_loglik_recursion_by_hand() -> None:
    r = [0.1, -0.2, 0.05]
    ll, var, nxt = v.garch_loglik(r, 0.01, 0.1, 0.8, 0.04)
    s1 = 0.04
    s2 = 0.01 + 0.1 * 0.01 + 0.8 * s1
    s3 = 0.01 + 0.1 * 0.04 + 0.8 * s2
    s4 = 0.01 + 0.1 * 0.0025 + 0.8 * s3
    assert var == pytest.approx([s1, s2, s3])
    assert nxt == pytest.approx(s4)
    expect = -0.5 * sum(LN2PI + math.log(s) + x * x / s for s, x in zip([s1, s2, s3], r))
    assert ll == pytest.approx(expect)
    # SAMPLE starts at the mean square
    _, var2, _ = v.garch_loglik(r, 0.01, 0.1, 0.8, "SAMPLE")
    assert var2[0] == pytest.approx((0.01 + 0.04 + 0.0025) / 3)
    # zero alpha and beta: constant omega after the first step
    _, var3, n3 = v.garch_loglik(r, 0.02, 0.0, 0.0, 0.5)
    assert var3 == pytest.approx([0.5, 0.02, 0.02]) and n3 == pytest.approx(0.02)


def test_loglik_errors() -> None:
    r = [0.1, -0.2]
    _err(lambda: v.garch_loglik([0.1], 0.01, 0.1, 0.8, 0.04), "E_INPUT", "returns")
    _err(lambda: v.garch_loglik(r, 0.01, 0.1, 0.8, "MEAN"), "E_INPUT", "initial_variance")
    _err(lambda: v.garch_loglik(r, 0.0, 0.1, 0.8, 0.04), "E_DOMAIN", "omega")
    _err(lambda: v.garch_loglik(r, 0.01, -0.1, 0.8, 0.04), "E_DOMAIN", "alpha")
    _err(lambda: v.garch_loglik(r, 0.01, 0.1, -0.8, 0.04), "E_DOMAIN", "beta")
    _err(lambda: v.garch_loglik(r, 0.01, 0.1, 0.8, 0.0), "E_DOMAIN", "initial_variance")
    _err(
        lambda: v.garch_loglik([0.0, 0.0], 0.01, 0.1, 0.8, "SAMPLE"), "E_DOMAIN", "initial_variance"
    )
    assert v.garch_loglik(r, 0.01, 0.0, 0.0, 0.04)[1][0] == 0.04


def test_forecast_by_hand() -> None:
    var, total, vol, lr = v.garch_forecast(0.02, 0.1, 0.7, 0.2, 3, 252.0)
    assert lr == pytest.approx(0.1)
    assert var == pytest.approx([0.2, 0.1 + 0.8 * 0.1, 0.1 + 0.64 * 0.1])
    assert total == pytest.approx(sum(var))
    assert vol == pytest.approx(math.sqrt(total * 252.0 / 3))
    var0, _, _, lr0 = v.garch_forecast(0.05, 0.0, 0.0, 0.3, 2, 1.0)
    assert lr0 == pytest.approx(0.05) and var0 == pytest.approx([0.3, 0.05])
    one = v.garch_forecast(0.02, 0.1, 0.7, 0.2, 1, 12.0)
    assert one[0] == pytest.approx([0.2]) and one[2] == pytest.approx(math.sqrt(0.2 * 12.0))


def test_forecast_errors() -> None:
    f = v.garch_forecast
    _err(lambda: f(0.02, 0.1, 0.7, 0.2, 0, 252.0), "E_INPUT", "horizon")
    _err(lambda: f(0.02, 0.1, 0.7, 0.2, 1, 0.0), "E_INPUT", "periods_per_year")
    _err(lambda: f(0.0, 0.1, 0.7, 0.2, 1, 252.0), "E_DOMAIN", "omega")
    _err(lambda: f(0.02, 0.1, 0.7, 0.0, 1, 252.0), "E_DOMAIN", "next_variance")
    _err(lambda: f(0.02, 0.5, 0.5, 0.2, 1, 252.0), "E_DOMAIN", "alpha")
    _err(lambda: f(0.02, 0.6, 0.5, 0.2, 1, 252.0), "E_DOMAIN", "alpha")
    assert f(0.02, 0.5, 0.49, 0.2, 1, 252.0)[3] == pytest.approx(2.0)


def test_digamma_known_values() -> None:
    euler = 0.5772156649015329
    assert v._digamma(1.0) == pytest.approx(-euler, abs=1e-13)
    assert v._digamma(0.5) == pytest.approx(-euler - 2 * math.log(2), abs=1e-13)
    assert v._digamma(2.0) == pytest.approx(1 - euler, abs=1e-13)
    assert v._digamma(10.0) == pytest.approx(2.251752589066721, abs=1e-13)
    assert v._digamma(25.0) == pytest.approx(
        math.fsum(1 / k for k in range(1, 25)) - euler, abs=1e-13
    )


def _t_logpdf(x: float, s: float, nu: float) -> float:
    c = math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2) - 0.5 * math.log(math.pi * (nu - 2) * s)
    return c - (nu + 1) / 2 * math.log1p(x * x / ((nu - 2) * s))


def test_loglik_t_matches_density() -> None:
    r = [0.1, -0.2, 0.05, 0.0]
    ll, var, nxt = v.garch_loglik_t(r, 0.01, 0.1, 0.8, 0.04, "STUDENT_T", 5.0, 0.02)
    e = [x - 0.02 for x in r]
    _, var_n, nxt_n = v.garch_loglik(e, 0.01, 0.1, 0.8, 0.04)
    assert var == pytest.approx(var_n) and nxt == pytest.approx(nxt_n)
    assert ll == pytest.approx(sum(_t_logpdf(x, s, 5.0) for x, s in zip(e, var_n)))
    lln, _, _ = v.garch_loglik_t(r, 0.01, 0.1, 0.8, 0.04, "NORMAL", None, 0.02)
    assert lln == pytest.approx(v.garch_loglik(e, 0.01, 0.1, 0.8, 0.04)[0])
    _, vs, _ = v.garch_loglik_t(r, 0.01, 0.1, 0.8, "SAMPLE", "NORMAL", None, 0.02)
    assert vs[0] == pytest.approx(sum(x * x for x in e) / 4)


def test_loglik_t_errors() -> None:
    r = [0.1, -0.2]
    f = v.garch_loglik_t
    _err(lambda: f([0.1], 0.01, 0.1, 0.8, 0.04, "NORMAL", None, 0.0), "E_INPUT", "returns")
    _err(lambda: f(r, 0.01, 0.1, 0.8, "X", "NORMAL", None, 0.0), "E_INPUT", "initial_variance")
    _err(lambda: f(r, 0.0, 0.1, 0.8, 0.04, "NORMAL", None, 0.0), "E_DOMAIN", "omega")
    _err(lambda: f(r, 0.01, 0.1, 0.8, 0.04, "LAPLACE", None, 0.0), "E_SCHEMA", "distribution")
    _err(
        lambda: f(r, 0.01, 0.1, 0.8, 0.04, "STUDENT_T", None, 0.0), "E_INPUT", "degrees_of_freedom"
    )
    _err(
        lambda: f(r, 0.01, 0.1, 0.8, 0.04, "STUDENT_T", 2.0, 0.0), "E_DOMAIN", "degrees_of_freedom"
    )
    assert f(r, 0.01, 0.1, 0.8, 0.04, "STUDENT_T", 2.01, 0.0)[0] < 0


@pytest.mark.parametrize("student", [False, True])
def test_score_gradient_matches_differences(student: bool) -> None:
    e = [0.1, -0.2, 0.05, 0.15, -0.03]
    theta = [0.01, 0.1, 0.8, 6.0] if student else [0.01, 0.1, 0.8]
    ll, grad = v._score(e, theta, 0.04, student)
    if student:
        _, var, _ = v.garch_loglik(e, theta[0], theta[1], theta[2], 0.04)
        assert ll == pytest.approx(sum(_t_logpdf(x, s, 6.0) for x, s in zip(e, var)))
    else:
        assert ll == pytest.approx(v.garch_loglik(e, theta[0], theta[1], theta[2], 0.04)[0])
    for k in range(len(theta)):
        h = 1e-6
        up, dn = list(theta), list(theta)
        up[k] += h
        dn[k] -= h
        fd = (v._score(e, up, 0.04, student)[0] - v._score(e, dn, 0.04, student)[0]) / (2 * h)
        assert grad[k] == pytest.approx(fd, rel=1e-5, abs=1e-6)


def test_varswap_realized() -> None:
    p = [100.0, 110.0, 99.0]
    var, vol, pnl = v.varswap_realized(p, 252.0, 0.04, 1000.0)
    sq = math.log(1.1) ** 2 + math.log(0.9) ** 2
    assert var == pytest.approx(252.0 / 2 * sq)
    assert vol == pytest.approx(math.sqrt(252.0 / 2 * sq))
    assert pnl == pytest.approx(1000.0 * (252.0 / 2 * sq - 0.04))
    _err(lambda: v.varswap_realized([100.0], 252.0, 0.04, 1.0), "E_INPUT", "prices")
    _err(lambda: v.varswap_realized([100.0, 0.0], 252.0, 0.04, 1.0), "E_DOMAIN", "prices")
