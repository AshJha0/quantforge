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
from scipy.special import gammainc, gammaincc
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


def test_make_model_fields_and_defaults() -> None:
    m = sr.make_model("VASICEK", A, SIG, None, None, None)
    assert (m.kind, m.a, m.sigma, m.b, m.curve, m.r0) == ("VASICEK", A, SIG, 0.0, None, 0.0)
    m = sr.make_model("VASICEK", A, SIG, B, None, R0)
    assert (m.b, m.r0) == (B, R0)
    m = sr.make_model("CIR", A, SIG, B, None, 0.0)
    assert (m.kind, m.b, m.r0) == ("CIR", B, 0.0)
    # Vasicek takes a negative short rate and any long-term mean; only CIR checks them
    assert sr.make_model("VASICEK", A, SIG, -0.01, None, -0.02).r0 == -0.02
    _err(lambda: sr.make_model("CIR", A, SIG, -B, None, R0), "E_DOMAIN", "long_term_mean")
    # the order of the checks: model, a, sigma, then the CIR rules
    _err(lambda: sr.make_model("BDT", 0.0, 0.0, None, None, -1.0), "E_INPUT", "model")
    _err(lambda: sr.make_model("CIR", 0.0, 0.0, None, None, -1.0), "E_DOMAIN", "mean_reversion")
    _err(lambda: sr.make_model("CIR", A, -1.0, None, None, -1.0), "E_DOMAIN", "sigma")
    _err(lambda: sr.make_model("CIR", A, SIG, None, None, -1.0), "E_DOMAIN", "long_term_mean")


# --- more special-function cases (scipy) ---------------------------------------------------------


@pytest.mark.parametrize(
    "s,x",
    [
        (0.5, 1.4999),  # just below s + 1: the series
        (0.5, 1.5001),  # just above: the continued fraction
        (4.0, 5.0),  # exactly s + 1: the continued fraction
        (2.5, 0.01),
        (12.0, 3.0),  # s >= 10 front with x far below s
        (60.0, 100.0),
        (1000.0, 1001.0),
        (7.0, 60.0),
    ],
)
def test_gamma_p_against_scipy_both_tails(s: float, x: float) -> None:
    p = sr._gamma_p(s, x)
    assert p == pytest.approx(float(gammainc(s, x)), rel=1e-12, abs=0)
    q = float(gammaincc(s, x))
    if q > 1e-6:  # the upper tail through 1 - P keeps about 1e-16 / q of relative precision
        assert 1 - p == pytest.approx(q, rel=1e-9, abs=0)


@pytest.mark.parametrize(
    "x,k,lam",
    [
        (1.0, 10.0, 1.0),  # left tail, about 1e-4
        (0.5, 20.0, 3.0),  # deep left tail
        (3.0, 2.0, 1e-3),  # tiny noncentrality: the mode is j = 0
        (1900.0, 1.0, 2000.0),  # large noncentrality, summed both ways from the mode
        (40.0, 4.0, 10.5),
        (8.0, 6.0, 2.5),
    ],
)
def test_ncx2_cdf_more_cases(x: float, k: float, lam: float) -> None:
    assert sr.ncx2_cdf(x, k, lam) == pytest.approx(float(ncx2.cdf(x, k, lam)), rel=1e-10, abs=0)


def test_ncx2_upper_tail_through_the_complement() -> None:
    for x, k, lam in ((60.0, 4.0, 10.0), (30.0, 3.0, 5.0)):
        q = float(ncx2.sf(x, k, lam))
        assert 1 - sr.ncx2_cdf(x, k, lam) == pytest.approx(q, rel=1e-8, abs=0)


# --- Hull-White helpers from Brigo-Mercurio, on a log-linear curve -------------------------------

HW_T = [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
HW_DF = [math.exp(-(0.02 + 0.002 * t) * t) for t in HW_T]
HW_A, HW_SIG = 0.1, 0.012
_NODES = [0.0, *HW_T]
_LOGS = [0.0, *(math.log(d) for d in HW_DF)]


def _seg(t: float) -> int:
    return min(max(i for i in range(len(_NODES)) if _NODES[i] <= t), len(_NODES) - 2)


def loglin(t: float) -> float:
    """Log-linear interpolation of HW_DF with (0, 1) as the first node, flat forward after."""
    if t <= 0:
        return 1.0
    j = _seg(t)
    w = (t - _NODES[j]) / (_NODES[j + 1] - _NODES[j])
    return math.exp(_LOGS[j] + (_LOGS[j + 1] - _LOGS[j]) * w)


def fwd0(t: float) -> float:
    """The right-hand instantaneous forward of the log-linear curve (ruling G-3)."""
    j = _seg(t)
    return -(_LOGS[j + 1] - _LOGS[j]) / (_NODES[j + 1] - _NODES[j])


def hw_bond(a: float, sig: float, t: float, s: float, r: float) -> float:
    """B&M (3.39)."""
    big_b = (1 - math.exp(-a * (s - t))) / a
    var = sig * sig / (4 * a) * (1 - math.exp(-2 * a * t)) * big_b**2
    return loglin(s) / loglin(t) * math.exp(big_b * fwd0(t) - var - big_b * r)


def hw_swaption(
    a: float, sig: float, t0: float, times: list[float], k: float, payer: bool
) -> float:
    """Jamshidian's decomposition written out: r* by brentq, then B&M (3.40)-(3.41) bond options."""
    taus = [times[0] - t0] + [y - x for x, y in itertools.pairwise(times)]
    cs = [k * tau for tau in taus]
    cs[-1] += 1

    def total(r: float) -> float:
        return sum(c * hw_bond(a, sig, t0, s, r) for c, s in zip(cs, times)) - 1

    rstar = brentq(total, -1, 1, xtol=1e-16)
    pt = loglin(t0)
    out = 0.0
    for c, s in zip(cs, times):
        ki, ps = hw_bond(a, sig, t0, s, rstar), loglin(s)
        call = gauss_call(pt, ps, ki, gauss_sp(a, sig, t0, s))
        out += c * ((call - ps + ki * pt) if payer else call)
    return out


def hw_model() -> sr.Model:
    return sr.curve_model(HW_T, HW_DF, HW_A, HW_SIG)


def test_hw_swaption_against_direct_jamshidian() -> None:
    m = hw_model()
    times = [2.0, 2.5, 3.0, 3.5, 4.0]
    for k, kind in ((0.03, "PAYER"), (0.025, "RECEIVER"), (0.05, "RECEIVER")):
        want = hw_swaption(HW_A, HW_SIG, 1.5, times, k, kind == "PAYER")
        got = sr.swaption(m, 1.5, times, k, kind, 1e4)["price"]
        assert got == pytest.approx(1e4 * want, rel=1e-10, abs=0)


def _bond_sum(cs: list[float], times: list[float], r: float) -> float:
    total = 0.0
    for c, s in zip(cs, times):
        la, lb = vasicek_ab(A, B, SIG, s - 1.0)
        total += c * math.exp(la - lb * r)
    return total


def test_critical_rate_solves_the_bond_sum() -> None:
    m = sr.make_model("VASICEK", A, SIG, B, None, R0)
    times = [1.5, 2.0, 2.5]
    for cs in ([0.02, 0.02, 1.02], [0.4, 0.4, 1.4], [-0.004, -0.004, 0.996]):
        want = brentq(lambda r, cs=cs: _bond_sum(cs, times, r) - 1, -1, 1, xtol=1e-17)
        got = sr._critical_rate(m, 1.0, times, cs)
        assert got == pytest.approx(want, rel=0, abs=1e-14)
        assert _bond_sum(cs, times, got) == pytest.approx(1.0, rel=0, abs=4e-16)
    # sum c_i P(T0, Ti; -1) < 1: no sign change in [-1, 1]
    _err(lambda: sr._critical_rate(m, 1.0, times, [0.0, 0.0, 0.1]), "E_DOMAIN", "fixed_rate")
    # sum c_i P(T0, Ti; 1) > 1: no sign change either
    _err(lambda: sr._critical_rate(m, 1.0, times, [5.0, 5.0, 6.0]), "E_DOMAIN", "fixed_rate")


# --- caps and floors ---------------------------------------------------------------------------


def _vas_p0(t: float) -> float:
    la, lb = vasicek_ab(A, B, SIG, t)
    return math.exp(la - lb * R0)


@pytest.mark.parametrize("kind", ["VASICEK", "HULL_WHITE"])
def test_capfloor_caplets_as_bond_puts_and_parity(kind: str) -> None:
    if kind == "VASICEK":
        m, a, sig, p0 = sr.make_model("VASICEK", A, SIG, B, None, R0), A, SIG, _vas_p0
    else:
        m, a, sig, p0 = hw_model(), HW_A, HW_SIG, loglin
    times, k, n = [0.5, 1.0, 1.75, 2.5], 0.028, 1e6
    cap = sr.capfloor(m, times, k, "CAP", n)
    floor = sr.capfloor(m, times, k, "FLOOR", n)
    want_caplets = []
    for s, e in itertools.pairwise(times):
        tau = e - s
        kb = 1 / (1 + k * tau)
        call = gauss_call(p0(s), p0(e), kb, gauss_sp(a, sig, s, e))
        # B&M (3.42)-(3.43): caplet = (1 + K tau) ZBP(0, s, e, 1/(1 + K tau)), put by parity
        want_caplets.append(n * (1 + k * tau) * (call - p0(e) + kb * p0(s)))
    caplets = cap["caplet_prices"]
    assert isinstance(caplets, list) and len(caplets) == 3
    for got, want in zip(caplets, want_caplets):
        assert got == pytest.approx(want, rel=1e-11, abs=0)
    assert cap["price"] == pytest.approx(sum(want_caplets), rel=1e-12, abs=0)
    # cap - floor = sum (P(s) - (1 + K tau) P(e)), the value of the payer swap
    swap = sum(p0(s) - (1 + k * (e - s)) * p0(e) for s, e in itertools.pairwise(times))
    cp, fp = cap["price"], floor["price"]
    assert isinstance(cp, float) and isinstance(fp, float)
    assert cp - fp == pytest.approx(n * swap, rel=1e-9, abs=1e-6)
    floorlets = floor["caplet_prices"]
    assert isinstance(floorlets, list) and len(floorlets) == 3
    assert fp == pytest.approx(sum(floorlets), rel=1e-13, abs=0)


def test_capfloor_cir_parity() -> None:
    m = sr.make_model("CIR", A, 0.1, B, None, R0)
    times, k = [1.0, 1.5, 2.0], 0.04

    def p0(t: float) -> float:
        la, lb = cir_ab(A, B, 0.1, t)
        return math.exp(la - lb * R0)

    cap, floor = (sr.capfloor(m, times, k, w, 1.0)["price"] for w in ("CAP", "FLOOR"))
    assert isinstance(cap, float) and isinstance(floor, float)
    swap = sum(p0(s) - (1 + k * (e - s)) * p0(e) for s, e in itertools.pairwise(times))
    assert cap - floor == pytest.approx(swap, rel=1e-9, abs=1e-14)


def test_capfloor_errors() -> None:
    m = sr.make_model("VASICEK", A, SIG, B, None, R0)
    _err(lambda: sr.capfloor(m, [1.0], 0.03, "CAP", 1.0), "E_INPUT", "period_times")
    _err(lambda: sr.capfloor(m, [], 0.03, "CAP", 1.0), "E_INPUT", "period_times")
    _err(lambda: sr.capfloor(m, [2.0, 1.0], 0.03, "CAP", 1.0), "E_INPUT", "period_times")
    _err(lambda: sr.capfloor(m, [1.0, 1.0], 0.03, "CAP", 1.0), "E_INPUT", "period_times")
    _err(lambda: sr.capfloor(m, [0.0, 1.0], 0.03, "CAP", 1.0), "E_DOMAIN", "period_times")
    _err(lambda: sr.capfloor(m, [-0.5, 1.0], 0.03, "CAP", 1.0), "E_DOMAIN", "period_times")
    # tau = 0.5, K = -2: 1 + K tau = 0 exactly
    _err(lambda: sr.capfloor(m, [0.5, 1.0], -2.0, "CAP", 1.0), "E_DOMAIN", "strike")
    # only the second period breaks the rule (tau 0.5 then 2: K = -0.6 gives 0.7 then -0.2)
    _err(lambda: sr.capfloor(m, [0.5, 1.0, 3.0], -0.6, "CAP", 1.0), "E_DOMAIN", "strike")
    _err(lambda: sr.capfloor(m, [0.5, 1.0], 0.03, "CAPLET", 1.0), "E_INPUT", "cap_floor")
    # the strike rule is checked before the type, the times before both
    _err(lambda: sr.capfloor(m, [0.5, 1.0], -2.0, "CAPLET", 1.0), "E_DOMAIN", "strike")
    _err(lambda: sr.capfloor(m, [0.0, 1.0], -2.0, "CAPLET", 1.0), "E_DOMAIN", "period_times")
    # a negative strike with 1 + K tau > 0 is allowed: one floorlet, worth a bond call
    kb = 1 / (1 - 0.005)
    want = (1 - 0.005) * gauss_call(_vas_p0(0.5), _vas_p0(1.0), kb, gauss_sp(A, SIG, 0.5, 1.0))
    got = sr.capfloor(m, [0.5, 1.0], -0.01, "FLOOR", 1.0)["price"]
    assert got == pytest.approx(want, rel=1e-11, abs=0)


# --- calibration -------------------------------------------------------------------------------


def test_make_quote_checks_and_fields() -> None:
    q = sr.make_quote(1.0, [1.5, 2.0], 0.03, "RECEIVER", 0.0)  # a zero target is allowed
    assert (q.expiry, q.payment_times, q.fixed_rate, q.payer, q.target) == (
        1.0,
        (1.5, 2.0),
        0.03,
        False,
        0.0,
    )
    assert sr.make_quote(1.0, [1.5], 0.03, "PAYER", 0.01).payer is True
    _err(lambda: sr.make_quote(1.0, [1.5], 0.03, "PAYER", -1e-12), "E_DOMAIN", "target_price")
    _err(lambda: sr.make_quote(0.0, [1.5], 0.03, "PAYER", 0.01), "E_DOMAIN", "expiry_years")
    _err(lambda: sr.make_quote(1.0, [1.0], 0.03, "PAYER", 0.01), "E_INPUT", "payment_times")
    _err(lambda: sr.make_quote(1.0, [1.5], 0.03, "CAP", -1.0), "E_INPUT", "swaption_type")


def test_hw_calibrate_recovers_sigma() -> None:
    strip: list[Any] = []
    for expiry, times, k in ((1.0, [1.5, 2.0, 2.5, 3.0], 0.025), (2.0, [3.0, 4.0, 5.0], 0.03)):
        for payer in (True, False):
            target = hw_swaption(HW_A, 0.011, expiry, times, k, payer)
            strip.append((expiry, times, k, "PAYER" if payer else "RECEIVER", target))
    out = sr.hw_calibrate(HW_T, HW_DF, HW_A, strip)
    assert out["sigma"] == pytest.approx(0.011, rel=1e-7, abs=0)
    assert isinstance(out["rmse"], float) and out["rmse"] < 1e-12
    fitted = out["fitted_prices"]
    assert isinstance(fitted, list) and len(fitted) == 4
    for f, q in zip(fitted, strip):
        assert f == pytest.approx(q[4], rel=1e-9, abs=0)
    _err(lambda: sr.hw_calibrate(HW_T, HW_DF, HW_A, []), "E_INPUT", "swaptions")
    _err(lambda: sr.hw_calibrate(HW_T, HW_DF, 0.0, strip), "E_DOMAIN", "mean_reversion")


# --- the G-18 grid -----------------------------------------------------------------------------


def test_make_grid_checks() -> None:
    g = sr.make_grid(5, 1, 1e-9)  # the smallest grid allowed
    assert (g.nx, g.steps_per_year, g.width) == (5, 1, 1e-9)
    for nx in (3, 4, 6, 100):
        _err(lambda nx=nx: sr.make_grid(nx, 10, 5.0), "E_INPUT", "grid.nx")
    _err(lambda: sr.make_grid(7, 0, 5.0), "E_INPUT", "grid.steps_per_year")
    _err(lambda: sr.make_grid(7, 10, 0.0), "E_DOMAIN", "grid.width")
    _err(lambda: sr.make_grid(4, 0, 0.0), "E_INPUT", "grid.nx")
    _err(lambda: sr.make_grid(7, 0, 0.0), "E_INPUT", "grid.steps_per_year")


def test_thomas_against_dense_solve() -> None:
    import numpy as np

    lower, diag, upper = [0.0, -1.0, 0.5, -0.3], [4.0, 3.0, 5.0, 2.5], [1.0, -0.7, 0.2, 0.0]
    rhs = [1.0, 2.0, -1.0, 0.5]
    dense = np.diag(diag) + np.diag(upper[:-1], 1) + np.diag(lower[1:], -1)
    want = np.linalg.solve(dense, rhs)
    for got, w in zip(sr._thomas(lower, diag, upper, rhs), want):
        assert got == pytest.approx(float(w), rel=1e-13, abs=1e-15)


def test_bermudan_with_one_exercise_is_the_european_swaption() -> None:
    m = hw_model()
    times = [2.0, 2.5, 3.0, 3.5, 4.0]
    coarse, fine = sr.make_grid(201, 100, 6.0), sr.make_grid(201, 400, 6.0)
    for k, kind in ((0.03, "PAYER"), (0.03, "RECEIVER")):
        want = hw_swaption(HW_A, HW_SIG, 1.5, times, k, kind == "PAYER")
        got = sr.bermudan_swaption(m, 1.5, times, k, kind, 1.0, [1.5], fine)["price"]
        assert got == pytest.approx(want, rel=BERM_TOL, abs=0)
        # the implicit scheme is first order in time: four times the steps, about a third the error
        rough = sr.bermudan_swaption(m, 1.5, times, k, kind, 1.0, [1.5], coarse)["price"]
        assert 2 * abs(got - want) < abs(rough - want) < 6 * abs(got - want)


BERM_TOL = 1e-3


def test_bermudan_bounds() -> None:
    m = hw_model()
    times = [2.0, 2.5, 3.0, 3.5, 4.0]
    grid = sr.make_grid(101, 50, 6.0)
    k, ex = 0.03, [1.5, 2.0, 2.5, 3.0]
    berm = sr.bermudan_swaption(m, 1.5, times, k, "PAYER", 1.0, ex, grid)["price"]
    euros = [hw_swaption(HW_A, HW_SIG, t0, [s for s in times if s > t0], k, True) for t0 in ex]
    # a Bermudan is worth at least each European it contains and at most their sum
    assert max(euros) * (1 - 2e-3) <= berm <= sum(euros)
    assert berm > max(euros) * 1.01


def test_callable_bond_without_calls_is_the_bullet() -> None:
    m = hw_model()
    times, c = [1.0, 2.0, 3.0, 4.0], 0.04
    grid = sr.make_grid(201, 100, 6.0)
    bullet = sum(c * loglin(t) for t in times) + loglin(4.0)  # coupons plus face, discounted
    got = sr.callable_bond(m, times, c, 1.0, [], 1.0, grid)["price"]
    assert got == pytest.approx(bullet, rel=BOND_TOL, abs=0)
    # an issuer call can only lower the value; a call price above any value changes nothing
    called = sr.callable_bond(m, times, c, 1.0, [2.0, 3.0], 1.0, grid)["price"]
    assert called < got
    far = sr.callable_bond(m, times, c, 1.0, [2.0, 3.0], 10.0, grid)["price"]
    assert far == pytest.approx(got, rel=1e-14, abs=0)


BOND_TOL = 1e-4


# --- swap exposure ------------------------------------------------------------------------------


def test_swap_ee_hw_is_the_forward_swaption() -> None:
    m = hw_model()
    times, k = [1.5, 2.0, 2.5, 3.0], 0.027
    out = sr.swap_ee_hw(m, 1.0, times, k, "PAY", 1e6, [1.0, 2.0, 2.5], 0.02, 0.4)
    ee = out["discounted_ee"]
    assert isinstance(ee, list) and len(ee) == 3
    ts = (1.0, 2.0, 2.5)
    want = [hw_swaption(HW_A, HW_SIG, t, [s for s in times if s > t], k, True) for t in ts]
    for got, w in zip(ee, want):
        assert got == pytest.approx(1e6 * w, rel=1e-10, abs=0)
    # CVA = (1 - R) sum EE(t_i) (e^{-h t_{i-1}} - e^{-h t_i}), t_0 = 0 (xva-exposure, G-16)
    edges = [0.0, *ts]
    cva = 0.6 * sum(
        e * (math.exp(-0.02 * lo) - math.exp(-0.02 * hi)) for e, lo, hi in zip(ee, edges, edges[1:])
    )
    assert out["cva"] == pytest.approx(cva, rel=1e-13, abs=0)
    rec = sr.swap_ee_hw(m, 1.0, times, k, "RECEIVE", 1e6, [2.0], None, None)
    assert "cva" not in rec
    rw = hw_swaption(HW_A, HW_SIG, 2.0, [2.5, 3.0], k, False)
    assert rec["discounted_ee"] == pytest.approx([1e6 * rw], rel=1e-10, abs=0)
    zero = sr.swap_ee_hw(m, 1.0, times, k, "PAY", 1.0, [1.0], 0.0, 0.0)
    assert zero["cva"] == 0.0


def test_swap_ee_hw_errors() -> None:
    m = hw_model()

    def call(**kw: Any) -> Any:
        args: dict[str, Any] = {
            "start": 1.0,
            "payment_times": [1.5, 2.0],
            "fixed_rate": 0.03,
            "side": "PAY",
            "notional": 1.0,
            "exposure_times": [1.0],
            "hazard_rate": None,
            "recovery": None,
        }
        args.update(kw)
        return lambda: sr.swap_ee_hw(m, **args)

    _err(call(side="BUY"), "E_INPUT", "side")
    _err(call(side="BUY", start=-1.0), "E_INPUT", "side")
    _err(call(start=-0.1), "E_DOMAIN", "start_years")
    _err(call(start=-0.1, payment_times=[]), "E_DOMAIN", "start_years")
    _err(call(payment_times=[]), "E_INPUT", "payment_times")
    _err(call(payment_times=[2.0, 1.5]), "E_INPUT", "payment_times")
    _err(call(payment_times=[1.0, 2.0]), "E_INPUT", "payment_times")
    _err(call(exposure_times=[]), "E_INPUT", "exposure_times")
    _err(call(start=0.0, exposure_times=[0.0]), "E_DOMAIN", "exposure_times")
    _err(call(exposure_times=[-1.0, 1.0]), "E_DOMAIN", "exposure_times")
    _err(call(exposure_times=[1.2]), "E_INPUT", "exposure_times")
    _err(call(exposure_times=[1.5, 1.0]), "E_INPUT", "exposure_times")
    _err(call(exposure_times=[2.0]), "E_INPUT", "exposure_times")  # the last payment is no reset
    _err(call(hazard_rate=0.01), "E_INPUT", "hazard_rate")
    _err(call(recovery=0.4), "E_INPUT", "hazard_rate")
    _err(call(hazard_rate=-0.01, recovery=0.4), "E_DOMAIN", "hazard_rate")
    _err(call(hazard_rate=0.01, recovery=1.0), "E_DOMAIN", "recovery")
    _err(call(hazard_rate=0.01, recovery=-0.1), "E_DOMAIN", "recovery")
    _err(call(hazard_rate=-0.01, recovery=1.0), "E_DOMAIN", "hazard_rate")
    _err(call(exposure_times=[1.0, 1.5], recovery=0.4), "E_INPUT", "hazard_rate")
    # start 0 with an exposure at the first payment's reset is fine
    ok = sr.swap_ee_hw(m, 0.0, [0.5, 1.0], 0.03, "PAY", 1.0, [0.5], 0.0, 0.0)
    assert isinstance(ok["discounted_ee"], list) and ok["cva"] == 0.0


def test_bermudan_and_callable_errors() -> None:
    m = hw_model()
    g = sr.make_grid(21, 10, 5.0)
    t = [2.0, 2.5, 3.0]

    def berm(start: float, times: list[float], kind: str, ex: list[float]) -> Any:
        return lambda: sr.bermudan_swaption(m, start, times, 0.03, kind, 1.0, ex, g)

    _err(berm(0.0, t, "PAYER", [2.0]), "E_DOMAIN", "expiry_years")
    _err(berm(1.5, [1.5, 2.0], "PAYER", [1.5]), "E_INPUT", "payment_times")
    _err(berm(1.5, t, "CAP", [1.5]), "E_INPUT", "swaption_type")
    _err(berm(1.5, t, "PAYER", []), "E_INPUT", "exercise_times")
    _err(berm(1.5, t, "PAYER", [2.0, 1.5]), "E_INPUT", "exercise_times")
    _err(berm(1.5, t, "PAYER", [1.5, 1.5]), "E_INPUT", "exercise_times")
    _err(berm(1.5, t, "PAYER", [1.7]), "E_INPUT", "exercise_times")
    _err(berm(1.5, t, "PAYER", [3.0]), "E_INPUT", "exercise_times")  # the last payment
    assert sr.check_bermudan(1.5, t, "PAYER", [1.5, 2.0, 2.5]) is True
    assert sr.check_bermudan(1.5, t, "RECEIVER", [2.5]) is False

    def bond(times: list[float], calls: list[float], price: float) -> Any:
        return lambda: sr.callable_bond(m, times, 0.04, 1.0, calls, price, g)

    _err(bond([], [], 1.0), "E_INPUT", "payment_times")
    _err(bond([0.0, 1.0], [], 1.0), "E_INPUT", "payment_times")
    _err(bond([2.0, 1.0], [], 1.0), "E_INPUT", "payment_times")
    _err(bond([1.0, 2.0, 3.0], [2.0, 1.0], 1.0), "E_INPUT", "call_times")
    _err(bond([1.0, 2.0, 3.0], [3.0], 1.0), "E_INPUT", "call_times")
    _err(bond([1.0, 2.0, 3.0], [1.5], 1.0), "E_INPUT", "call_times")
    _err(bond([1.0, 2.0, 3.0], [2.0], 0.0), "E_DOMAIN", "call_price")
    _err(bond([1.0, 2.0, 3.0], [1.5], 0.0), "E_INPUT", "call_times")


def test_callable_bond_called_at_par_with_zero_vol_limit() -> None:
    # With a call at every coupon date and a call price of par plus nothing, a bond whose coupon
    # is far above every forward is called at the first call date: its value is the coupons up
    # to that date plus the call price, discounted on the curve (hand calculation).
    m = sr.curve_model(HW_T, HW_DF, HW_A, 1e-4)
    times, c = [1.0, 2.0, 3.0, 4.0], 0.2
    got = sr.callable_bond(m, times, c, 100.0, [1.0, 2.0, 3.0], 1.0, sr.make_grid(101, 200, 6.0))
    want = 100 * (c * loglin(1.0) + loglin(1.0))
    assert got["price"] == pytest.approx(want, rel=2e-4, abs=0)


def _msg(fn: Any, code: str, field: str, message: str) -> None:
    """Like _err, and the message too where two checks share a code and a field."""
    with pytest.raises(QfError) as e:
        fn()
    assert (e.value.code, e.value.field, e.value.message) == (code, field, message)


def test_swaption_strike_rules_by_message() -> None:
    m = sr.make_model("VASICEK", A, SIG, B, None, R0)
    rule = "1 + K tau_n must be above 0"
    none = "no critical rate in [-1, 1]"
    # one period of 0.5: K = -2 gives 1 + K tau = 0 exactly, refused by the strike rule
    _msg(lambda: sr.swaption(m, 1.0, [1.5], -2.0, "PAYER", 1.0), "E_DOMAIN", "fixed_rate", rule)
    # two periods, tau_n = 2.0 - 1.5 = 0.5 (not T_n - T_0 = 1): K = -1.2 passes the strike rule
    # (1 - 0.6 > 0) and fails at the critical rate (-0.6 P1 + 0.4 P2 < 1 for every r in [-1, 1])
    _msg(
        lambda: sr.swaption(m, 1.0, [1.5, 2.0], -1.2, "PAYER", 1.0), "E_DOMAIN", "fixed_rate", none
    )
    # K = -0.6, tau = 0.5: 1 + K tau = 0.7 > 0 and a root exists, so it prices
    got = sr.swaption(m, 1.0, [1.5], -0.6, "RECEIVER", 1.0)["price"]
    want = _jamshidian_direct(A, B, SIG, R0, 1.0, [1.5], -0.6, False)
    assert got == pytest.approx(want, rel=1e-10, abs=0)


def test_cir_swaption_critical_rate_rule_and_parity() -> None:
    sig = 0.1
    m = sr.make_model("CIR", A, sig, B, None, R0)
    t0, times = 1.0, [1.3, 2.0, 3.0]  # unequal periods
    taus = [0.3, 0.7, 1.0]

    def p(t: float, s: float, r: float) -> float:
        la, lb = cir_ab(A, B, sig, s - t)
        return math.exp(la - lb * r)

    # sum K tau_i P(T0, Ti; 0) + P(T0, Tn; 0) >= 1 is needed for r* >= 0 (CIR rates are >= 0):
    # the boundary strike is the swap rate at r = 0, K* = (1 - P_n) / sum tau_i P_i
    k_star = (1 - p(t0, 3.0, 0.0)) / sum(tau * p(t0, s, 0.0) for tau, s in zip(taus, times))
    why = "CIR has no non-negative critical rate"
    _msg(
        lambda: sr.swaption(m, t0, times, k_star - 1e-6, "PAYER", 1.0),
        "E_DOMAIN",
        "fixed_rate",
        why,
    )
    sr.swaption(m, t0, times, k_star + 1e-6, "PAYER", 1.0)  # just above: allowed
    # payer - receiver = P(0, T0) - P(0, Tn) - K sum tau_i P(0, Ti), the forward swap
    k = 0.04
    pay = sr.swaption(m, t0, times, k, "PAYER", 1.0)["price"]
    rec = sr.swaption(m, t0, times, k, "RECEIVER", 1.0)["price"]
    p0 = [p(0.0, s, R0) for s in times]
    swap = p(0.0, t0, R0) - p0[-1] - k * sum(tau * q for tau, q in zip(taus, p0))
    assert pay - rec == pytest.approx(swap, rel=1e-9, abs=1e-14)


def test_cir_bond_option_at_a_later_expiry() -> None:
    m = sr.make_model("CIR", A, 0.1, B, None, R0)
    for k in (0.88, 0.93):  # expiry 2 so that gamma * t and gamma / t differ
        want = cir_call(A, B, 0.1, R0, k, 2.0, 4.5)
        got = sr.zcb_option(m, "CALL", k, 2.0, 4.5, 1.0)["price"]
        assert got == pytest.approx(want, rel=1e-10, abs=0)


def test_capfloor_strike_rule_is_k_times_tau() -> None:
    m = sr.make_model("VASICEK", A, SIG, B, None, R0)
    # K = -0.6, tau = 0.5: 1 + K tau = 0.7 > 0 is allowed (K / tau would be -1.2)
    got = sr.capfloor(m, [0.5, 1.0], -0.6, "FLOOR", 1.0)["price"]
    kb = 1 / 0.7
    want = 0.7 * gauss_call(_vas_p0(0.5), _vas_p0(1.0), kb, gauss_sp(A, SIG, 0.5, 1.0))
    assert got == pytest.approx(want, rel=1e-11, abs=0)
    rule = "1 + K tau must be above 0 in every period"
    _msg(lambda: sr.capfloor(m, [0.5, 1.0], -2.0, "CAP", 1.0), "E_DOMAIN", "strike", rule)


def _strip(sigma: float, bump: float) -> list[Any]:
    strip: list[Any] = []
    for expiry, times, k in ((1.0, [1.5, 2.0, 2.5, 3.0], 0.025), (2.0, [3.0, 4.0, 5.0], 0.03)):
        for payer in (True, False):
            target = hw_swaption(HW_A, sigma, expiry, times, k, payer) + bump * len(strip)
            strip.append((expiry, times, k, "PAYER" if payer else "RECEIVER", target))
    return strip


def test_hw_calibrate_least_squares_optimum() -> None:
    # targets off the model by 0, 2e-4, 4e-4, 6e-4: no sigma fits, so the answer is the
    # least-squares optimum, checked against the objective rebuilt from B&M closed forms
    strip = _strip(0.011, 2e-4)
    out = sr.hw_calibrate(HW_T, HW_DF, HW_A, strip)
    sig = out["sigma"]
    assert isinstance(sig, float)

    def objective(s: float) -> float:
        return math.fsum(
            (hw_swaption(HW_A, s, q[0], q[1], q[2], q[3] == "PAYER") - q[4]) ** 2 for q in strip
        )

    f0 = objective(sig)
    for step in (1e-3, 1e-5):
        assert f0 <= objective(sig * (1 + step)) and f0 <= objective(sig * (1 - step))

    # the optimum's first-order condition: F'(sigma) = 0, with F' a central difference of the
    # objective above and its root found by brentq
    def slope(s: float) -> float:
        return (objective(s * (1 + 1e-6)) - objective(s * (1 - 1e-6))) / (2e-6 * s)

    assert sig == pytest.approx(brentq(slope, 0.009, 0.014, xtol=1e-15), rel=1e-8, abs=0)
    fitted = out["fitted_prices"]
    assert isinstance(fitted, list)
    for f, q in zip(fitted, strip):
        assert f == pytest.approx(
            hw_swaption(HW_A, sig, q[0], q[1], q[2], q[3] == "PAYER"), rel=1e-10
        )
    # rmse = sqrt(sum (fitted - target)^2 / n)
    rmse = math.sqrt(sum((f - q[4]) ** 2 for f, q in zip(fitted, strip)) / 4)
    assert out["rmse"] == pytest.approx(rmse, rel=1e-12, abs=0)


def test_hw_calibrate_minimum_at_the_end() -> None:
    # every target 0: the objective falls as sigma falls, so its minimum is the end 1e-4
    strip = [(q[0], q[1], q[2], q[3], 0.0) for q in _strip(0.011, 0.0)]
    why = "the minimum is at an end of [1e-4, 1]"
    _msg(lambda: sr.hw_calibrate(HW_T, HW_DF, HW_A, strip), "E_NO_CONVERGENCE", "sigma", why)


def test_grid_boundary_rows_on_a_narrow_grid() -> None:
    # At width 2 the linear-extrapolation rows at both ends of the grid carry weight, and the
    # scheme still reprices the bullet bond (coupons plus face on the curve) to about 2e-6.
    # Unequal periods so that each coupon uses its own tau and the step count per period differs.
    m = hw_model()
    times, c = [0.5, 1.0, 2.0, 3.5], 0.04
    taus = [0.5, 0.5, 1.0, 1.5]
    bullet = sum(c * tau * loglin(t) for tau, t in zip(taus, times)) + loglin(3.5)
    got = sr.callable_bond(m, times, c, 1.0, [], 1.0, sr.make_grid(81, 400, 2.0))["price"]
    assert got == pytest.approx(bullet, rel=2e-5, abs=0)
    swap = [2.0, 2.5, 3.0, 3.5, 4.0]
    want = hw_swaption(HW_A, HW_SIG, 1.5, swap, 0.03, True)
    grid = sr.make_grid(81, 400, 2.0)
    berm = sr.bermudan_swaption(m, 1.5, swap, 0.03, "PAYER", 1.0, [1.5], grid)["price"]
    assert berm == pytest.approx(want, rel=1e-3, abs=0)


def test_build_model_order_and_messages() -> None:
    # a and sigma are checked before the curve (spec order)
    _err(
        lambda: sr.build_model("HULL_WHITE", 0.0, SIG, None, None, None, None),
        "E_DOMAIN",
        "mean_reversion",
    )
    _err(lambda: sr.build_model("HULL_WHITE", A, 0.0, None, None, None, None), "E_DOMAIN", "sigma")
    hw = "short_rate is not an input of this Hull-White operation"
    _msg(lambda: sr.curve_model([1.0], [0.9], A, SIG, True), "E_INPUT", "short_rate", hw)
    _msg(
        lambda: sr.make_model("CIR", A, SIG, None, None, R0),
        "E_DOMAIN",
        "long_term_mean",
        "CIR needs long_term_mean above 0",
    )
    _msg(
        lambda: sr.make_model("CIR", A, SIG, B, None, -0.01),
        "E_DOMAIN",
        "short_rate",
        "CIR needs short_rate >= 0",
    )
    # a Vasicek model has no curve: its bonds today come from r0 (B&M 3.8)
    m = sr.build_model("VASICEK", A, SIG, B, None, None, R0)
    assert m.curve is None
    assert m.p0(2.0) == pytest.approx(_vas_p0(2.0), rel=1e-13, abs=0)
    assert m.p0(0.0) == 1.0 and m.p0(-1.0) == 1.0
