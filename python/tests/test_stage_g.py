"""Stage G property tests: short-rate models, G2++, Jamshidian swaptions, caps, the pinned
Bermudan and callable-bond scheme, swap exposure, discrete barriers (R9) and Monte Carlo Greeks
(Q9 part 1, G-10 and G-10b). The goldens are run by test_conformance.py; these check the
identities and acceptance runs the specs ask each build to add."""
import itertools
import math
import os

import pytest

from quantforge_core import exotics, mc_greeks, shortrate
from quantforge_core.black import big_n
from quantforge_core.errors import QfError
from quantforge_core.rng import normals

TIMES = [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
         10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782]
DFS = [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]
ACCEPTANCE = os.environ.get("QF_ACCEPTANCE") == "1"


def _hw(a: float = 0.05, sigma: float = 0.01) -> shortrate.Model:
    return shortrate.curve_model(TIMES, DFS, a, sigma)


def _models() -> list[shortrate.Model]:
    return [shortrate.build_model("VASICEK", 0.15, 0.012, 0.045, None, None, 0.035),
            shortrate.build_model("CIR", 0.2, 0.08, 0.045, None, None, 0.035),
            _hw()]


@pytest.mark.parametrize("model", _models(), ids=lambda m: m.kind)
def test_put_call_parity(model: shortrate.Model) -> None:
    for strike, t, s in ((0.86, 1.0, 5.0), (0.95, 0.5, 2.0), (0.5, 3.0, 20.0)):
        call = model.option(True, strike, t, s)
        put = model.option(False, strike, t, s)
        assert abs(call - put - (model.p0(s) - strike * model.p0(t))) <= 1e-12


def test_hull_white_bond_at_zero_is_the_curve() -> None:
    m = _hw()
    for t in (0.25, 1.0, 2.0, 4.0, 12.0, 30.019178082191782, 40.0):
        r0 = m.curve.forward(0.0) if m.curve else 0.0
        p = shortrate.zcb(m, r0, 0.0, t)["discount_factor"]
        assert abs(p / m.p0(t) - 1) <= 1e-14


@pytest.mark.parametrize("model", _models(), ids=lambda m: m.kind)
def test_zero_rate_tends_to_short_rate(model: shortrate.Model) -> None:
    for r in (0.0, 0.02, 0.05):
        out = shortrate.zcb(model, r, 1.0, 1.0 + 1e-6)
        assert abs(out["zero_rate"] - r) <= 1e-6


def test_small_mean_reversion_matches_ho_lee_limit() -> None:
    # The series branch (G-2) and the direct branch must agree across the switch point.
    for kind in ("VASICEK",):
        lo = shortrate.build_model(kind, 0.5 / 5 - 1e-9, 0.01, 0.04, None, None, 0.03)
        hi = shortrate.build_model(kind, 0.5 / 5 + 1e-9, 0.01, 0.04, None, None, 0.03)
        p_lo, p_hi = lo.bond(0.0, 5.0, 0.03), hi.bond(0.0, 5.0, 0.03)
        assert abs(p_lo / p_hi - 1) < 1e-9


def test_noncentral_chi_square_central_limit() -> None:
    # lambda = 0: the central chi-square, for k = 2 the CDF is 1 - exp(-x/2).
    for x in (0.1, 1.0, 5.0, 30.0):
        assert abs(shortrate.ncx2_cdf(x, 2.0, 0.0) - (1 - math.exp(-x / 2))) <= 1e-15


def _swaption(model: shortrate.Model, kind: str, k: float) -> dict[str, float]:
    return shortrate.swaption(model, 1.0, [2.0, 3.0, 4.0, 5.0, 6.0], k, kind, 1.0)


@pytest.mark.parametrize("model", _models(), ids=lambda m: m.kind)
def test_payer_minus_receiver_is_the_forward_swap(model: shortrate.Model) -> None:
    for k in (0.02, 0.04, 0.06):
        pay, rec = _swaption(model, "PAYER", k), _swaption(model, "RECEIVER", k)
        assert abs(pay["price"] - rec["price"]
                   - pay["annuity"] * (pay["forward_swap_rate"] - k)) <= 1e-8


def test_cir_swaption_without_a_non_negative_critical_rate_is_domain() -> None:
    cir = _models()[1]
    with pytest.raises(QfError) as e:
        _swaption(cir, "PAYER", -0.5)
    assert e.value.code == "E_DOMAIN"


def test_g2pp_one_factor_limit_and_curve() -> None:
    curve = shortrate.make_curve(TIMES, DFS)
    g2 = shortrate.make_g2(curve, 0.05, 0.01, 0.3, 1e-12, 0.3)
    hw = _hw()
    for t, s, k in ((1.0, 5.0, 0.86), (2.0, 10.0, 0.75)):
        g = shortrate.g2pp_zcb_option(g2, "CALL", k, t, s, 1.0)["price"]
        assert abs(g - hw.option(True, k, t, s)) <= 1e-12
    for t in (0.5, 3.0, 25.0):
        assert abs(shortrate.g2pp_zcb(g2, 0.0, 0.0, 0.0, t)["discount_factor"] / curve.discount(t)
                   - 1) <= 1e-14


def test_g2pp_put_call_parity_and_states_refused() -> None:
    curve = shortrate.make_curve(TIMES, DFS)
    g2 = shortrate.make_g2(curve, 0.5, 0.01, 0.05, 0.008, -0.75)
    c = shortrate.g2pp_zcb_option(g2, "CALL", 0.86, 1.0, 5.0, 1.0)
    p = shortrate.g2pp_zcb_option(g2, "PUT", 0.86, 1.0, 5.0, 1.0)
    assert abs(c["price"] - p["price"] - (c["bond_price_maturity"]
                                          - 0.86 * c["bond_price_expiry"])) <= 1e-12
    with pytest.raises(QfError):
        shortrate.no_states()
    with pytest.raises(QfError):
        shortrate.make_g2(curve, 0.5, 0.01, 0.05, 0.008, 1.0)


def test_g2pp_series_branch_is_continuous() -> None:
    a, b = 0.1, 0.2
    left = shortrate._cross_term(a, b, 0.5 / (a + b) * (1 - 1e-12))
    right = shortrate._cross_term(a, b, 0.5 / (a + b) * (1 + 1e-12))
    assert abs(left / right - 1) < 1e-9
    v_lo = shortrate._gauss_variance(0.1, 0.01, 5.0 * (1 - 1e-12))
    v_hi = shortrate._gauss_variance(0.1, 0.01, 5.0 * (1 + 1e-12))
    assert abs(v_lo / v_hi - 1) < 1e-9


@pytest.mark.parametrize("model", _models(), ids=lambda m: m.kind)
def test_cap_minus_floor_is_the_swaplet_sum(model: shortrate.Model) -> None:
    times = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    for k in (0.03, 0.05):
        cap = shortrate.capfloor(model, times, k, "CAP", 1.0)["price"]
        floor = shortrate.capfloor(model, times, k, "FLOOR", 1.0)["price"]
        swaplets = sum(model.p0(a) - (1 + k * (b - a)) * model.p0(b)
                       for a, b in itertools.pairwise(times))
        assert isinstance(cap, float) and isinstance(floor, float)
        assert abs(cap - floor - swaplets) <= 1e-12


def test_bermudan_one_date_converges_to_jamshidian() -> None:
    m = _hw()
    pay = [2.0, 3.0, 4.0, 5.0, 6.0]
    european = shortrate.swaption(m, 1.0, pay, 0.04, "PAYER", 1.0)["price"]
    errors = []
    for nx, spy in ((51, 25), (101, 50), (201, 100)):
        grid = shortrate.make_grid(nx, spy, 6.0)
        price = shortrate.bermudan_swaption(m, 1.0, pay, 0.04, "PAYER", 1.0, [1.0], grid)["price"]
        errors.append(abs(price - european))
    assert errors[0] > errors[1] > errors[2]
    assert 0.6 < math.log2(errors[1] / errors[2]) < 1.6


def test_bermudan_is_at_least_the_first_european() -> None:
    m = _hw()
    pay = [2.0, 3.0, 4.0, 5.0, 6.0]
    grid = shortrate.make_grid(101, 50, 6.0)
    for kind in ("PAYER", "RECEIVER"):
        berm = shortrate.bermudan_swaption(m, 1.0, pay, 0.04, kind, 1.0, [1.0, 2.0, 3.0, 4.0, 5.0],
                                           grid)["price"]
        # G-28: bounded by the scheme's own single-date price on the same grid, never Jamshidian
        one = shortrate.bermudan_swaption(m, 1.0, pay, 0.04, kind, 1.0, [1.0], grid)["price"]
        assert berm >= one


def test_callable_bond_limits() -> None:
    m = _hw()
    pay = [float(k) for k in range(1, 11)]
    c = 0.045
    straight = sum(c * m.p0(t) for t in pay) + m.p0(10.0)
    errors = []
    for nx, spy in ((51, 25), (101, 50), (201, 100)):
        grid = shortrate.make_grid(nx, spy, 6.0)
        errors.append(abs(shortrate.callable_bond(m, pay, c, 1.0, [], 1.0, grid)["price"]
                          - straight))
    assert 0.8 < math.log2(errors[1] / errors[2]) < 1.2
    grid = shortrate.make_grid(101, 50, 6.0)
    called = shortrate.callable_bond(m, pay, c, 1.0, pay[2:9], 1.0, grid)["price"]
    no_call = shortrate.callable_bond(m, pay, c, 1.0, [], 1.0, grid)["price"]
    assert called <= no_call  # G-28: the scheme's own no-call bond, not the exact straight bond
    deep = shortrate.callable_bond(m, pay, c, 1.0, [5.0], 10.0, grid)["price"]
    assert deep <= no_call


def test_exposure_pay_minus_receive_is_the_forward_value() -> None:
    m = _hw()
    pay = [1.0, 2.0, 3.0, 4.0, 5.0]
    k = 0.03
    ee_p = shortrate.swap_ee_hw(m, 0.0, pay, k, "PAY", 1.0, [1.0, 2.0, 3.0, 4.0], None, None)
    ee_r = shortrate.swap_ee_hw(m, 0.0, pay, k, "RECEIVE", 1.0, [1.0, 2.0, 3.0, 4.0], 0.02, 0.4)
    assert "cva" not in ee_p and "cva" in ee_r
    p, r = ee_p["discounted_ee"], ee_r["discounted_ee"]
    assert isinstance(p, list) and isinstance(r, list)
    for idx, t in enumerate([1.0, 2.0, 3.0, 4.0]):
        rest = [s for s in pay if s > t]
        fixed = sum((b - a) * m.p0(b) for a, b in zip([t, *rest], rest, strict=False))
        forward = m.p0(t) - m.p0(rest[-1]) - k * fixed
        assert abs(p[idx] - r[idx] - forward) <= 1e-12


def test_exposure_zero_vol_limit() -> None:
    m = _hw(sigma=1e-9)
    pay = [1.0, 2.0, 3.0]
    ee = shortrate.swap_ee_hw(m, 0.0, pay, 0.01, "PAY", 1.0, [1.0, 2.0], None, None)
    out = ee["discounted_ee"]
    assert isinstance(out, list)
    for idx, t in enumerate([1.0, 2.0]):
        rest = [s for s in pay if s > t]
        fixed = sum((b - a) * m.p0(b) for a, b in zip([t, *rest], rest, strict=False))
        assert abs(out[idx] - max(m.p0(t) - m.p0(rest[-1]) - 0.01 * fixed, 0.0)) < 1e-9


def test_calibration_recovers_a_known_sigma() -> None:
    m = _hw(a=0.01, sigma=0.007)
    strip = []
    for t in (1.0, 2.0, 3.0, 5.0, 7.0):
        pay = [float(k) for k in range(int(t) + 1, 11)]
        fwd = shortrate.swaption(m, t, pay, 0.0, "PAYER", 1.0)["forward_swap_rate"]
        price = shortrate.swaption(m, t, pay, fwd, "PAYER", 1.0)["price"]
        strip.append((t, pay, fwd, "PAYER", price))
    out = shortrate.hw_calibrate(TIMES, DFS, 0.01, strip)
    assert abs(out["sigma"] / 0.007 - 1) < 1e-9  # type: ignore[operator]


def test_calibration_minimum_at_an_end_does_not_converge() -> None:
    strip = [(1.0, [2.0, 3.0], 0.03, "PAYER", 0.0)]
    with pytest.raises(QfError) as e:
        shortrate.hw_calibrate(TIMES, DFS, 0.05, strip)
    assert e.value.code == "E_NO_CONVERGENCE"


# --- R9: discrete barrier monitoring -------------------------------------------------------------


def test_discrete_shift_moves_the_barrier_away_from_spot() -> None:
    base = (100.0, 100.0, 1.0, 0.05, 0.02, 0.25, "CALL")
    cont = exotics.barrier(*base, 90.0, 0.0, "DOWN_OUT")
    daily = exotics.barrier(*base, 90.0, 0.0, "DOWN_OUT", "DISCRETE", 252)
    shifted = exotics.barrier(*base, 90.0 * math.exp(-0.5826 * 0.25 / math.sqrt(252)), 0.0,
                              "DOWN_OUT")
    assert daily == shifted and daily > cont
    up = exotics.barrier(100.0, 100.0, 1.0, 0.05, 0.02, 0.25, "PUT", 110.0, 0.0, "UP_OUT",
                         "DISCRETE", 12)
    assert up > exotics.barrier(100.0, 100.0, 1.0, 0.05, 0.02, 0.25, "PUT", 110.0, 0.0, "UP_OUT")


@pytest.mark.skipif(not ACCEPTANCE, reason="R9 acceptance (40,000 x 252 draws): QF_ACCEPTANCE=1")
def test_r9_acceptance_daily_down_and_out() -> None:
    s, k, h, r, q, v, n_dates, n_paths = 100.0, 100.0, 90.0, 0.05, 0.02, 0.25, 252, 40_000
    dt = 1.0 / n_dates
    drift, vol = (r - q - v * v / 2) * dt, v * math.sqrt(dt)
    z = normals(20261109, 0, n_dates * n_paths)
    disc = math.exp(-r)
    calls, puts = [], []
    for p in range(n_paths):
        x, alive = math.log(s), True
        for j in range(n_dates):
            x += drift + vol * z[p * n_dates + j]
            if math.exp(x) <= h:
                alive = False
                break
        st = math.exp(x)
        calls.append(disc * max(st - k, 0.0) if alive else 0.0)
        puts.append(disc * max(k - st, 0.0) if alive else 0.0)
    for kind, values in (("CALL", calls), ("PUT", puts)):
        mean, se = mc_greeks.mean_and_se(values)
        bgk = exotics.barrier(s, k, 1.0, r, q, v, kind, h, 0.0, "DOWN_OUT", "DISCRETE", n_dates)
        assert abs(bgk - mean) <= 3 * se, (kind, bgk, mean, se)


# --- Q9 part 1: Monte Carlo Greeks ---------------------------------------------------------------


def _bs_digital_delta(s: float, k: float, t: float, r: float, q: float, v: float) -> float:
    d2 = (math.log(s / k) + (r - q - v * v / 2) * t) / (v * math.sqrt(t))
    return math.exp(-r * t) * math.exp(-d2 * d2 / 2) / math.sqrt(2 * math.pi) / (s * v * math.sqrt(t))


def test_call_greeks_agree_with_black_scholes() -> None:
    s, k, t, r, q, v = 100.0, 100.0, 1.0, 0.03, 0.01, 0.2
    d1 = (math.log(s / k) + (r - q + v * v / 2) * t) / (v * math.sqrt(t))
    delta = math.exp(-q * t) * big_n(d1)
    for method, extra in (("PATHWISE", {}), ("LIKELIHOOD_RATIO", {}),
                          ("BUMP", {"bump_relative": 0.01})):
        out = mc_greeks.greeks(s, k, t, r, q, v, "CALL", method, 20_000, 20261109,
                               None, extra.get("bump_relative"))
        assert abs(out["delta"] - delta) <= 4 * out["delta_se"]


def test_g10_registered_variance_test_reports() -> None:
    # G-10 as registered: recorded as inconclusive, low power; reported, not gating.
    s, k, t, r, q, v, n = 100.0, 100.0, 1.0, 0.03, 0.0, 0.2, 100_000 if ACCEPTANCE else 20_000
    z = normals(20261109, 0, n)
    _, pw, _ = mc_greeks.per_path_terms(s, k, t, r, q, v, "DIGITAL_CALL", "PATHWISE", z,
                                        smoothing_width=1.0)
    _, bump, _ = mc_greeks.per_path_terms(s, k, t, r, q, v, "DIGITAL_CALL", "BUMP", z,
                                          bump_relative=0.01)
    _, lr, _ = mc_greeks.per_path_terms(s, k, t, r, q, v, "DIGITAL_CALL", "LIKELIHOOD_RATIO", z)
    mean, se = mc_greeks.mean_and_se(lr)
    assert abs(mean - _bs_digital_delta(s, k, t, r, q, v)) <= 3 * se
    var_pw = mc_greeks.mean_and_se(pw)[1] ** 2 * n
    var_b = mc_greeks.mean_and_se(bump)[1] ** 2 * n
    assert 0.9 < var_pw / var_b < 1.1  # the two estimators are nearly the same call spread


def _kurtosis(values: list[float]) -> tuple[float, float]:
    n = len(values)
    m = math.fsum(values) / n
    s2 = math.fsum((x - m) ** 2 for x in values) / (n - 1)
    m4 = math.fsum((x - m) ** 4 for x in values) / n
    return s2, m4 / (s2 * s2)


def test_g10b_powered_variance_test() -> None:
    """G-10b (gating): smoothed pathwise (eps = 1, stream 0) against a central bump (h = 0.001,
    stream 1), 60,000 paths each, seed 20261110; pass when Z > 1.6449."""
    s, k, t, r, q, v, n = 100.0, 100.0, 1.0, 0.03, 0.0, 0.2, 60_000
    z0, z1 = normals(20261110, 0, n), normals(20261110, 1, n)
    _, pw, _ = mc_greeks.per_path_terms(s, k, t, r, q, v, "DIGITAL_CALL", "PATHWISE", z0,
                                        smoothing_width=1.0)
    _, bump, _ = mc_greeks.per_path_terms(s, k, t, r, q, v, "DIGITAL_CALL", "BUMP", z1,
                                          bump_relative=0.001)
    s_pw, k_pw = _kurtosis(pw)
    s_b, k_b = _kurtosis(bump)
    z_stat = (math.log(s_b) - math.log(s_pw)) / math.sqrt((k_pw - 1) / n + (k_b - 1) / n)
    assert z_stat > 1.6449
    assert s_pw / s_b < 0.2
