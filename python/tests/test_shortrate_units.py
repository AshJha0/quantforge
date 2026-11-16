"""Unit tests for the one-factor part of quantforge_core.shortrate (03-rates/short-rate-models.md,
rulings G-2 to G-32): Vasicek, CIR and Hull-White bonds and bond options, Jamshidian swaptions,
the noncentral chi-square and incomplete gamma, and the input checks.

Every expected value is independent of the module: bond and option prices are the closed forms
of Brigo and Mercurio, Interest Rate Models (2006), written here from the book (Vasicek 3.2.1,
CIR 3.2.3, Hull-White 3.3); the special functions are SciPy's (scipy.stats.ncx2, scipy.special);
swaptions are checked against the direct sum of Jamshidian's bond options with r* found by
scipy.optimize.brentq, and against payer - receiver = annuity (F - K)."""

import itertools
import math
from typing import Any

import pytest
from scipy.optimize import brentq
from scipy.special import gammainc
from scipy.stats import ncx2, norm

from quantforge_core import shortrate as sr
from quantforge_core.errors import QfError


def _err(fn: Any, code: str, field: str | None) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code and e.value.field == field
    assert isinstance(e.value.message, str) and str(e.value) == e.value.message
    assert "XX" not in e.value.message and e.value.message != e.value.message.upper()


# --- closed forms from Brigo-Mercurio ---------------------------------------------------------


def vasicek_ab(a: float, b: float, sig: float, tau: float) -> tuple[float, float]:
    """B&M (3.8): P = A exp(-B r), B = (1 - e^{-a tau})/a,
    ln A = (b - sig^2/(2a^2)) (B - tau) - sig^2 B^2 / (4a)."""
    big_b = (1 - math.exp(-a * tau)) / a
    return (b - sig * sig / (2 * a * a)) * (big_b - tau) - sig * sig * big_b * big_b / (
        4 * a
    ), big_b


def cir_ab(a: float, b: float, sig: float, tau: float) -> tuple[float, float]:
    """B&M (3.25): h = sqrt(a^2 + 2 sig^2),
    A = [2h e^{(a+h) tau/2} / (2h + (a+h)(e^{h tau} - 1))]^{2ab/sig^2},
    B = 2(e^{h tau} - 1) / (2h + (a+h)(e^{h tau} - 1))."""
    h = math.sqrt(a * a + 2 * sig * sig)
    den = 2 * h + (a + h) * (math.exp(h * tau) - 1)
    ln_a = 2 * a * b / (sig * sig) * math.log(2 * h * math.exp((a + h) * tau / 2) / den)
    return ln_a, 2 * (math.exp(h * tau) - 1) / den


def gauss_call(pt: float, ps: float, k: float, sp: float) -> float:
    """B&M (3.40): ZBC = P(0,S) N(h) - K P(0,T) N(h - sp), h = ln(P(0,S)/(K P(0,T)))/sp + sp/2."""
    h = math.log(ps / (k * pt)) / sp + sp / 2
    return float(ps * norm.cdf(h) - k * pt * norm.cdf(h - sp))


def gauss_sp(a: float, sig: float, t: float, s: float) -> float:
    """B&M (3.41): sp = sig sqrt((1 - e^{-2aT})/(2a)) B(T, S)."""
    return sig * math.sqrt((1 - math.exp(-2 * a * t)) / (2 * a)) * (1 - math.exp(-a * (s - t))) / a


def cir_call(a: float, b: float, sig: float, r0: float, k: float, t: float, s: float) -> float:
    """B&M (3.26) with scipy's noncentral chi-square."""
    h = math.sqrt(a * a + 2 * sig * sig)
    rho = 2 * h / (sig * sig * (math.exp(h * t) - 1))
    psi = (a + h) / (sig * sig)
    la, lb = cir_ab(a, b, sig, s - t)
    rbar = (la - math.log(k)) / lb
    dof = 4 * a * b / (sig * sig)
    pt = math.exp(cir_ab(a, b, sig, t)[0] - cir_ab(a, b, sig, t)[1] * r0)
    ps = math.exp(cir_ab(a, b, sig, s)[0] - cir_ab(a, b, sig, s)[1] * r0)
    nc1 = 2 * rho * rho * r0 * math.exp(h * t) / (rho + psi + lb)
    nc2 = 2 * rho * rho * r0 * math.exp(h * t) / (rho + psi)
    return float(
        ps * ncx2.cdf(2 * rbar * (rho + psi + lb), dof, nc1)
        - k * pt * ncx2.cdf(2 * rbar * (rho + psi), dof, nc2)
    )


A, B, SIG, R0 = 0.3, 0.04, 0.02, 0.03


@pytest.mark.parametrize("a", [0.3, 0.05, 1e-3])  # 1e-3 * tau < 0.5 takes the series branch
def test_vasicek_zcb_closed_form(a: float) -> None:
    m = sr.make_model("VASICEK", a, SIG, B, None, R0)
    for t, s, r in ((0.0, 2.0, R0), (1.0, 6.0, 0.05), (0.5, 0.75, -0.01)):
        la, lb = vasicek_ab(a, B, SIG, s - t)
        out = sr.zcb(m, r, t, s)
        p = math.exp(la - lb * r)
        assert out["discount_factor"] == pytest.approx(p, rel=1e-9 if a < 0.01 else 1e-13, abs=0)
        assert out["zero_rate"] == pytest.approx(-math.log(p) / (s - t), rel=1e-8, abs=0)


def test_cir_zcb_closed_form() -> None:
    m = sr.make_model("CIR", A, 0.1, B, None, R0)
    for t, s, r in ((0.0, 3.0, R0), (2.0, 2.5, 0.07), (0.0, 30.0, 0.0)):
        la, lb = cir_ab(A, B, 0.1, s - t)
        assert sr.zcb(m, r, t, s)["discount_factor"] == pytest.approx(
            math.exp(la - lb * r), rel=1e-13, abs=0
        )


def test_hull_white_zcb_fits_the_curve_and_matches_bm_339() -> None:
    times, dfs = [1.0, 2.0, 5.0], [0.97, 0.94, 0.85]
    m = sr.build_model("HULL_WHITE", A, SIG, None, times, dfs, None)
    # B&M (3.39): P(t,T) = P(0,T)/P(0,t) exp(B f(0,t) - sig^2/(4a)(1 - e^{-2at}) B^2 - B r)
    t, s, r = 1.5, 4.0, 0.025
    p0 = sr.make_curve(times, dfs).discount
    f = -(math.log(0.94) - math.log(0.97)) / 1.0  # log-linear: flat forward on [1, 2]
    big_b = (1 - math.exp(-A * (s - t))) / A
    want = (
        p0(s)
        / p0(t)
        * math.exp(
            big_b * f - SIG * SIG / (4 * A) * (1 - math.exp(-2 * A * t)) * big_b**2 - big_b * r
        )
    )
    assert sr.zcb(m, r, t, s)["discount_factor"] == pytest.approx(want, rel=1e-13, abs=0)
    # at t = 0 the model reprices the curve whatever r is the curve's own short rate
    assert m.p0(2.0) == 0.94 and m.p0(0.0) == 1.0


def test_curve_log_linear_and_flat_extrapolation() -> None:
    c = sr.make_curve([1.0, 3.0], [0.96, 0.9])
    assert c.discount(0.0) == 1.0 and c.discount(-1.0) == 1.0
    assert c.discount(0.5) == pytest.approx(0.96**0.5, rel=1e-15, abs=0)
    assert c.discount(2.0) == pytest.approx(math.sqrt(0.96 * 0.9), rel=1e-15, abs=0)
    f = math.log(0.96 / 0.9) / 2
    assert c.discount(5.0) == pytest.approx(0.9 * math.exp(-f * 2), rel=1e-14, abs=0)
    assert c.forward(1.0) == pytest.approx(f, rel=1e-15, abs=0)  # right-hand forward at a pillar
    assert c.forward(0.99) == pytest.approx(-math.log(0.96), rel=1e-15, abs=0)
    assert c.forward(10.0) == pytest.approx(f, rel=1e-15, abs=0)


@pytest.mark.parametrize("kind", ["VASICEK", "HULL_WHITE"])
def test_gaussian_bond_options(kind: str) -> None:
    if kind == "VASICEK":
        m = sr.make_model("VASICEK", A, SIG, B, None, R0)
        pt, ps = (
            math.exp(la - lb * R0)
            for la, lb in (vasicek_ab(A, B, SIG, 1.0), vasicek_ab(A, B, SIG, 4.0))
        )
    else:
        m = sr.build_model("HULL_WHITE", A, SIG, None, [1.0, 4.0], [0.97, 0.88], None)
        pt, ps = 0.97, 0.88
    k = 0.9
    call = gauss_call(pt, ps, k, gauss_sp(A, SIG, 1.0, 4.0))
    out = sr.zcb_option(m, "CALL", k, 1.0, 4.0, 100.0)
    assert out["price"] == pytest.approx(100 * call, rel=1e-12, abs=0)
    assert out["bond_price_expiry"] == pytest.approx(pt, rel=1e-14, abs=0)
    assert out["bond_price_maturity"] == pytest.approx(ps, rel=1e-14, abs=0)
    put = sr.zcb_option(m, "PUT", k, 1.0, 4.0, 100.0)["price"]
    assert put == pytest.approx(100 * (call - ps + k * pt), rel=1e-12, abs=0)  # parity


def test_cir_bond_option_against_scipy_ncx2() -> None:
    m = sr.make_model("CIR", A, 0.1, B, None, R0)
    for k in (0.85, 0.9, 0.95):
        want = cir_call(A, B, 0.1, R0, k, 1.0, 5.0)
        assert sr.zcb_option(m, "CALL", k, 1.0, 5.0, 1.0)["price"] == pytest.approx(
            want, rel=1e-10, abs=0
        )


@pytest.mark.parametrize(
    "x,k,lam",
    [
        (3.0, 4.0, 0.0),
        (0.5, 1.5, 0.0),
        (20.0, 3.0, 2.0),
        (50.0, 10.0, 40.0),
        (900.0, 30.0, 800.0),
        (2.0, 0.5, 5.0),
    ],
)
def test_ncx2_cdf_against_scipy(x: float, k: float, lam: float) -> None:
    want = ncx2.cdf(x, k, lam) if lam > 0 else gammainc(k / 2, x / 2)
    assert sr.ncx2_cdf(x, k, lam) == pytest.approx(float(want), rel=1e-11, abs=1e-300)


def test_ncx2_and_gamma_edges() -> None:
    assert sr.ncx2_cdf(0.0, 3.0, 1.0) == 0.0 and sr.ncx2_cdf(-1.0, 3.0, 0.0) == 0.0
    assert sr._gamma_p(2.0, 0.0) == 0.0
    for s, x in ((0.5, 0.2), (3.0, 2.0), (3.0, 9.0), (25.0, 20.0), (25.0, 40.0), (200.0, 210.0)):
        assert sr._gamma_p(s, x) == pytest.approx(float(gammainc(s, x)), rel=1e-12, abs=0)


def test_log_helpers() -> None:
    for d in (0.5, -0.3, 0.1, -0.2, 1e-4):
        want = math.log1p(d) - d if abs(d) > 0.05 else -(d**2) / 2 + d**3 / 3 - d**4 / 4 + d**5 / 5
        assert sr._log1pmx(d) == pytest.approx(want, rel=1e-12, abs=0)
    for s in (10.0, 37.5, 400.0):
        want = math.lgamma(s) - ((s - 0.5) * math.log(s) - s + 0.5 * math.log(2 * math.pi))
        # the reference subtracts numbers of size s ln s (rounding ~eps s ln s); the module stops
        # at the 1/s^9 term, so it is off by at most the next Stirling term, 691/(360360 s^11)
        tol = 4 * 2.2e-16 * s * math.log(s) + 691 / (360360 * s**11)
        assert sr._stirling_tail(s) == pytest.approx(want, rel=0, abs=tol)
    for j, mu in ((0, 3.0), (1, 3.0), (7, 2.5), (40, 35.0)):
        want = j * math.log(mu) - mu - math.lgamma(j + 1)
        assert sr._log_poisson(j, mu) == pytest.approx(want, rel=1e-12, abs=0)


# --- Jamshidian swaption ----------------------------------------------------------------------


def _jamshidian_direct(
    a: float, b: float, sig: float, r0: float, t0: float, times: list[float], k: float, payer: bool
) -> float:
    taus = [times[0] - t0] + [y - x for x, y in itertools.pairwise(times)]
    cs = [k * tau for tau in taus]
    cs[-1] += 1

    def p(t: float, s: float, r: float) -> float:
        la, lb = vasicek_ab(a, b, sig, s - t)
        return math.exp(la - lb * r)

    rstar = brentq(lambda r: sum(c * p(t0, s, r) for c, s in zip(cs, times)) - 1, -1, 1, xtol=1e-16)
    pt = p(0, t0, r0)
    total = 0.0
    for c, s in zip(cs, times):
        ki, ps = p(t0, s, rstar), p(0, s, r0)
        call = gauss_call(pt, ps, ki, gauss_sp(a, sig, t0, s))
        total += c * ((call - ps + ki * pt) if payer else call)
    return total


def test_vasicek_swaption_against_direct_jamshidian_and_parity() -> None:
    m = sr.make_model("VASICEK", A, SIG, B, None, R0)
    times, k = [1.5, 2.0, 2.5, 3.0], 0.035
    pay = sr.swaption(m, 1.0, times, k, "PAYER", 1e6)
    rec = sr.swaption(m, 1.0, times, k, "RECEIVER", 1e6)
    assert pay["price"] == pytest.approx(
        1e6 * _jamshidian_direct(A, B, SIG, R0, 1.0, times, k, True), rel=1e-10, abs=0
    )
    assert rec["price"] == pytest.approx(
        1e6 * _jamshidian_direct(A, B, SIG, R0, 1.0, times, k, False), rel=1e-10, abs=0
    )

    def p0(s: float) -> float:
        la, lb = vasicek_ab(A, B, SIG, s)
        return math.exp(la - lb * R0)

    level = sum(0.5 * p0(s) for s in times)
    fwd = (p0(1.0) - p0(3.0)) / level
    assert pay["annuity"] == pytest.approx(1e6 * level, rel=1e-13, abs=0)
    assert pay["forward_swap_rate"] == pytest.approx(fwd, rel=1e-12, abs=0)
    assert pay["price"] - rec["price"] == pytest.approx(1e6 * level * (fwd - k), rel=1e-9, abs=1e-6)


def test_swaption_errors() -> None:
    m = sr.make_model("VASICEK", A, SIG, B, None, R0)
    _err(lambda: sr.swaption(m, 0.0, [1.0], 0.03, "PAYER", 1.0), "E_DOMAIN", "expiry_years")
    _err(lambda: sr.swaption(m, 1.0, [], 0.03, "PAYER", 1.0), "E_INPUT", "payment_times")
    _err(lambda: sr.swaption(m, 1.0, [1.0, 2.0], 0.03, "PAYER", 1.0), "E_INPUT", "payment_times")
    _err(lambda: sr.swaption(m, 1.0, [2.0, 1.5], 0.03, "PAYER", 1.0), "E_INPUT", "payment_times")
    _err(lambda: sr.swaption(m, 1.0, [2.0], 0.03, "STRADDLE", 1.0), "E_INPUT", "swaption_type")
    _err(lambda: sr.swaption(m, 1.0, [2.0], -1.0, "PAYER", 1.0), "E_DOMAIN", "fixed_rate")
    # one period: tau_n = T1 - T0 = 0.5, so K = -2 gives 1 + K tau = 0
    _err(lambda: sr.swaption(m, 1.0, [1.5], -2.0, "PAYER", 1.0), "E_DOMAIN", "fixed_rate")
    cir = sr.make_model("CIR", A, 0.1, B, None, R0)
    # sum c_i P(T0, Ti; 0) < 1 with a negative strike: r* would be negative, CIR refuses
    _err(lambda: sr.swaption(cir, 1.0, [2.0, 3.0], -0.05, "PAYER", 1.0), "E_DOMAIN", "fixed_rate")


# --- input checks -----------------------------------------------------------------------------


def test_model_and_curve_errors() -> None:
    _err(lambda: sr.make_model("BDT", A, SIG, B, None, R0), "E_INPUT", "model")
    _err(lambda: sr.make_model("VASICEK", 0.0, SIG, B, None, R0), "E_DOMAIN", "mean_reversion")
    _err(lambda: sr.make_model("VASICEK", A, 0.0, B, None, R0), "E_DOMAIN", "sigma")
    _err(lambda: sr.make_model("CIR", A, SIG, None, None, R0), "E_DOMAIN", "long_term_mean")
    _err(lambda: sr.make_model("CIR", A, SIG, 0.0, None, R0), "E_DOMAIN", "long_term_mean")
    _err(lambda: sr.make_model("CIR", A, SIG, B, None, -0.01), "E_DOMAIN", "short_rate")
    assert sr.make_model("CIR", A, SIG, B, None, 0.0).r0 == 0.0
    assert sr.make_model("CIR", A, SIG, B, None, None).r0 == 0.0
    _err(lambda: sr.build_model("BDT", A, SIG, B, None, None, R0), "E_INPUT", "model")
    _err(
        lambda: sr.build_model("HULL_WHITE", -A, SIG, None, [1.0], [0.9], None),
        "E_DOMAIN",
        "mean_reversion",
    )
    _err(lambda: sr.build_model("HULL_WHITE", A, SIG, None, None, None, None), "E_INPUT", "curve")
    _err(lambda: sr.curve_model([1.0], [0.9], A, SIG, True), "E_INPUT", "short_rate")
    _err(lambda: sr.make_curve([], []), "E_INPUT", "curve")
    _err(lambda: sr.make_curve([1.0, 2.0], [0.9]), "E_INPUT", "curve")
    _err(lambda: sr.make_curve([0.0, 1.0], [1.0, 0.9]), "E_INPUT", "curve.times")
    _err(lambda: sr.make_curve([2.0, 1.0], [0.9, 0.95]), "E_INPUT", "curve.times")
    _err(lambda: sr.make_curve([1.0, 1.0], [0.9, 0.95]), "E_INPUT", "curve.times")
    _err(lambda: sr.make_curve([1.0], [0.0]), "E_DOMAIN", "curve.discount_factors")


def test_zcb_and_option_errors() -> None:
    m = sr.make_model("VASICEK", A, SIG, B, None, R0)
    _err(lambda: sr.zcb(m, R0, -0.1, 1.0), "E_DOMAIN", "t_years")
    _err(lambda: sr.zcb(m, R0, 1.0, 1.0), "E_DOMAIN", "maturity_years")
    assert sr.zcb(m, R0, 0.0, 1e-6)["discount_factor"] < 1.0  # t = 0 is allowed
    _err(lambda: sr.zcb_option(m, "CALL", 0.9, 0.0, 2.0, 1.0), "E_DOMAIN", "expiry_years")
    _err(lambda: sr.zcb_option(m, "CALL", 0.9, 2.0, 2.0, 1.0), "E_DOMAIN", "maturity_years")
    _err(lambda: sr.zcb_option(m, "CALL", 0.0, 1.0, 2.0, 1.0), "E_DOMAIN", "strike")
    _err(lambda: sr.zcb_option(m, "STRADDLE", 0.9, 1.0, 2.0, 1.0), "E_INPUT", "option_type")
