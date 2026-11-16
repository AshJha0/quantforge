"""Unit tests for the rest of quantforge_core.variance: the GARCH fit and estimate, the variance
swap fair strike and the VIX-style index (05-volatility/garch.md, variance-swaps.md, vix-index.md;
rulings E-B1 to E-B34, F-11 to F-15).

Expected values are derived independently: the fit and estimate against a SciPy optimiser on a
NumPy likelihood written here, the standard errors against a finite-difference Hessian of that
likelihood, the variance swap against Black-Scholes prices from scipy.stats and the textbook
limit sigma^2 (Demeterfi, Derman, Kamal and Zou 1999), and the VIX against the Cboe white-paper
formula worked by hand on a five-strike strip."""

import math
from datetime import date
from typing import Any

import numpy as np
import pytest
from scipy.optimize import minimize as _minimize
from scipy.stats import norm

from quantforge_core import variance as v
from quantforge_core.errors import QfError


def _err(fn: Any, code: str, field: str | None) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code and e.value.field == field
    # the message is a readable sentence (kills the message-text mutants)
    assert isinstance(e.value.message, str) and str(e.value) == e.value.message
    assert "XX" not in e.value.message and e.value.message != e.value.message.upper()


# --- GARCH fit and estimate -------------------------------------------------------------------


def _simulate(n: int, omega: float, alpha: float, beta: float, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    s2, out = omega / (1 - alpha - beta), []
    for z in rng.standard_normal(n):
        r = math.sqrt(s2) * float(z)
        out.append(r)
        s2 = omega + alpha * r * r + beta * s2
    return out


def _nll(theta: Any, r: np.ndarray, s0: float) -> float:
    """Negative Gaussian GARCH(1,1) log-likelihood, written from the spec formula."""
    omega, alpha, beta = theta
    s, total = s0, 0.0
    for x in r:
        total += math.log(2 * math.pi) + math.log(s) + x * x / s
        s = omega + alpha * x * x + beta * s
    return 0.5 * total


minimize: Any = _minimize  # the SciPy stubs reject a plain Python objective


def _scipy_best(r: list[float], s0: float) -> Any:
    arr = np.asarray(r)
    cons = [{"type": "ineq", "fun": lambda t: 1 - 1e-8 - t[1] - t[2]}]
    best = None
    for start in ([0.1 * s0, 0.05, 0.9], [0.5 * s0, 0.2, 0.4], [0.03 * s0, 0.1, 0.85]):
        res = minimize(
            _nll,
            start,
            args=(arr, s0),
            method="SLSQP",
            bounds=[(1e-10, None), (0.0, 1.0), (0.0, 1.0)],
            constraints=cons,
            options={"ftol": 1e-14, "maxiter": 500},
        )
        if best is None or res.fun < best.fun:
            best = res
    return best


RETURNS = _simulate(250, 0.05, 0.12, 0.8, seed=11)


def test_garch_fit_matches_scipy_optimum() -> None:
    s0 = sum(x * x for x in RETURNS) / len(RETURNS)
    ref = _scipy_best(RETURNS, s0)
    got = v.garch_fit(RETURNS, "SAMPLE")
    assert got == pytest.approx(-ref.fun, abs=1e-5)
    # a fixed initial variance changes the first term only: the optimum moves, check it too
    got2 = v.garch_fit(RETURNS, 2.0)
    assert got2 == pytest.approx(-_scipy_best(RETURNS, 2.0).fun, abs=1e-5)
    assert got2 != pytest.approx(got, abs=1e-6)


def test_garch_fit_errors() -> None:
    _err(lambda: v.garch_fit([0.1] * 29, "SAMPLE"), "E_INPUT", "returns")
    _err(lambda: v.garch_fit([0.1] * 30, "MEAN"), "E_INPUT", "initial_variance")
    _err(lambda: v.garch_fit([0.0] * 30, "SAMPLE"), "E_DOMAIN", "initial_variance")
    _err(lambda: v.garch_fit([0.1] * 30, -1.0), "E_DOMAIN", "initial_variance")


def _hessian(theta: list[float], r: np.ndarray, s0: float) -> np.ndarray:
    n = len(theta)
    h = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            hi, hj = 1e-4 * theta[i], 1e-4 * theta[j]

            def f(di: float, dj: float, i: int = i, j: int = j) -> float:
                t = list(theta)
                t[i] += di
                t[j] += dj
                return -_nll(t, r, s0)

            h[i, j] = (f(hi, hj) - f(hi, -hj) - f(-hi, hj) + f(-hi, -hj)) / (4 * hi * hj)
    return h


def test_garch_estimate_normal_matches_scipy_and_observed_information() -> None:
    out: Any = v.garch_estimate(RETURNS, "SAMPLE", "NORMAL", False)
    s0 = sum(x * x for x in RETURNS) / len(RETURNS)
    ref = _scipy_best(RETURNS, s0)
    theta = [out["omega"], out["alpha"], out["beta"]]
    assert theta == pytest.approx(list(ref.x), rel=2e-3, abs=1e-5)
    assert out["loglik"] == pytest.approx(-_nll(theta, np.asarray(RETURNS), s0), rel=1e-12)
    assert out["loglik"] == pytest.approx(-ref.fun, abs=1e-6)
    assert out["persistence"] == out["alpha"] + out["beta"]
    assert out["mean"] == 0.0 and out["degrees_of_freedom"] is None
    se = np.sqrt(np.diag(np.linalg.inv(-_hessian(theta, np.asarray(RETURNS), s0))))
    std = out["std_errors"]
    assert [std["omega"], std["alpha"], std["beta"]] == pytest.approx(list(se), rel=1e-3)
    assert std["degrees_of_freedom"] is None


def test_garch_estimate_demean_subtracts_the_sample_mean() -> None:
    shifted = [x + 0.3 for x in RETURNS]
    out: Any = v.garch_estimate(shifted, "SAMPLE", "NORMAL", True)
    mu = math.fsum(shifted) / len(shifted)
    assert out["mean"] == pytest.approx(mu, rel=1e-14)
    # demeaned data is the original data shifted by 0.3 - mu (a tiny constant)
    e = np.asarray([x - mu for x in shifted])
    s0 = float(np.mean(e * e))
    assert out["loglik"] == pytest.approx(-_scipy_best(list(e), s0).fun, abs=1e-6)


def test_garch_estimate_student_t() -> None:
    rng = np.random.default_rng(5)
    nu = 6.0
    z = rng.standard_t(nu, 400) * math.sqrt((nu - 2) / nu)
    s2, r = 0.05 / 0.1, []
    for x in z:
        r.append(math.sqrt(s2) * float(x))
        s2 = 0.05 + 0.1 * r[-1] ** 2 + 0.8 * s2
    out: Any = v.garch_estimate(r, "SAMPLE", "STUDENT_T", False)
    s0 = sum(x * x for x in r) / len(r)
    theta = [out["omega"], out["alpha"], out["beta"], out["degrees_of_freedom"]]
    # the log-likelihood is the t density sum, written here from the closed form
    ll = v.garch_loglik_t(r, theta[0], theta[1], theta[2], s0, "STUDENT_T", theta[3], 0.0)[0]
    assert out["loglik"] == pytest.approx(ll, rel=1e-12)
    # an interior maximum: nudging any parameter lowers the likelihood
    for j in range(4):
        for d in (1.01, 0.99):
            t = list(theta)
            t[j] *= d
            assert v.garch_loglik_t(r, t[0], t[1], t[2], s0, "STUDENT_T", t[3], 0.0)[0] < ll
    assert 2 < out["degrees_of_freedom"] < v.NU_MAX
    std = out["std_errors"]
    assert all(std[k] > 0 for k in ("omega", "alpha", "beta", "degrees_of_freedom"))


def test_garch_estimate_errors() -> None:
    _err(lambda: v.garch_estimate(RETURNS, "SAMPLE", "LAPLACE", False), "E_SCHEMA", "distribution")
    _err(lambda: v.garch_estimate([0.1] * 29, "SAMPLE", "NORMAL", False), "E_INPUT", "returns")
    _err(lambda: v.garch_estimate([0.1] * 99, "SAMPLE", "STUDENT_T", False), "E_INPUT", "returns")
    _err(lambda: v.garch_estimate([0.1] * 30, "X", "NORMAL", False), "E_INPUT", "initial_variance")
    _err(lambda: v.garch_estimate([1e200] * 30, 1.0, "NORMAL", False), "E_NON_FINITE", "returns")
    _err(lambda: v.garch_estimate([0.0] * 30, 1.0, "NORMAL", False), "E_DOMAIN", "returns")
    _err(
        lambda: v.garch_estimate([0.0] * 30, "SAMPLE", "NORMAL", False),
        "E_DOMAIN",
        "initial_variance",
    )
    # constant squared returns carry no GARCH effect: the maximum is on the alpha = 0 boundary
    _err(
        lambda: v.garch_estimate([0.1, -0.1] * 20, "SAMPLE", "NORMAL", False),
        "E_NO_CONVERGENCE",
        "returns",
    )


# --- Variance swap fair strike ----------------------------------------------------------------


def _bs(kind: str, k: float, t: float, s: float, r: float, q: float, vol: float) -> float:
    d1 = (math.log(s / k) + (r - q + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    if kind == "CALL":
        return s * math.exp(-q * t) * norm.cdf(d1) - k * math.exp(-r * t) * norm.cdf(d2)
    return k * math.exp(-r * t) * norm.cdf(-d2) - s * math.exp(-q * t) * norm.cdf(-d1)


AS_OF, MAT = date(2025, 1, 2), date(2026, 1, 2)  # 365 days, t = 1


def test_varswap_one_put_one_call_by_hand() -> None:
    s, r, q, t, step = 100.0, 0.03, 0.01, 1.0, 10.0
    vols = [(90.0, 0.25), (110.0, 0.2)]
    fair, vol, value = v.varswap_fair_strike(
        AS_OF, MAT, s, r, q, [90.0], [110.0], vols, step, 0.04, 1000.0
    )

    def f(k: float) -> float:  # the log-contract payoff, (2/T)((K - S)/S - ln(K/S))
        return 2 / t * ((k - s) / s - math.log(k / s))

    w_call = abs(f(120.0) - f(110.0)) / 10.0  # one strike: the weight is the first slope
    w_put = abs(f(80.0) - f(90.0)) / 10.0
    strip = w_call * _bs("CALL", 110.0, t, s, r, q, 0.2) + w_put * _bs(
        "PUT", 90.0, t, s, r, q, 0.25
    )
    fwd = s * math.exp((r - q) * t)
    want = 2 / t * ((r - q) * t - (fwd / s - 1)) + strip / math.exp(-r * t)
    assert fair == pytest.approx(want, rel=1e-12)
    assert vol == pytest.approx(math.sqrt(want), rel=1e-12)
    assert value == pytest.approx(1000.0 * math.exp(-r * t) * (want - 0.04), rel=1e-12)


def test_varswap_two_strikes_per_side_uses_slope_differences() -> None:
    s, t = 100.0, 1.0
    puts, calls = [95.0, 85.0], [105.0, 115.0]
    vols = [(k, 0.2) for k in (*puts, *calls)]
    fair = v.varswap_fair_strike(AS_OF, MAT, s, 0.0, 0.0, puts, calls, vols, 10.0, 0.0, 1.0)[0]

    def f(k: float) -> float:
        return 2 / t * ((k - s) / s - math.log(k / s))

    def leg(ks: list[float], extra: float, kind: str) -> float:
        pts = [*ks, extra]
        slopes = [abs(f(pts[j + 1]) - f(pts[j])) / abs(pts[j + 1] - pts[j]) for j in range(len(ks))]
        weights = [slopes[0], slopes[1] - slopes[0]]
        return sum(w * _bs(kind, k, t, s, 0.0, 0.0, 0.2) for w, k in zip(weights, ks))

    want = leg([105.0, 115.0], 125.0, "CALL") + leg([95.0, 85.0], 75.0, "PUT")
    assert fair == pytest.approx(want, rel=1e-12)


def test_varswap_dense_flat_smile_tends_to_sigma_squared() -> None:
    # DDKZ 1999: with a flat smile and a fine, wide strike strip, K_var -> sigma^2
    s, sig = 100.0, 0.3
    puts = [s - 0.5 * i for i in range(190)]
    calls = [s + 0.5 * i for i in range(1, 800)]
    vols = [(k, sig) for k in (*puts, *calls)]
    fair = v.varswap_fair_strike(AS_OF, MAT, s, 0.02, 0.0, puts, calls, vols, 0.5, 0.0, 1.0)[0]
    assert fair == pytest.approx(sig * sig, rel=2e-3)


def test_varswap_errors() -> None:
    def call(**kw: Any) -> Any:
        args: dict[str, Any] = {
            "as_of": AS_OF,
            "maturity": MAT,
            "spot": 100.0,
            "rate": 0.0,
            "dividend_yield": 0.0,
            "put_strikes": [90.0],
            "call_strikes": [110.0],
            "vols": [(90.0, 0.2), (110.0, 0.2)],
            "extension_step": 10.0,
            "variance_strike": 0.04,
            "variance_notional": 1.0,
        }
        args.update(kw)
        return lambda: v.varswap_fair_strike(**args)

    _err(call(maturity=AS_OF), "E_INPUT", "maturity")
    _err(call(put_strikes=[]), "E_INPUT", "put_strikes")
    _err(call(call_strikes=[]), "E_INPUT", "call_strikes")
    _err(call(put_strikes=[90.0, 90.0]), "E_INPUT", "put_strikes")
    _err(call(call_strikes=[110.0, 110.0]), "E_INPUT", "call_strikes")
    _err(call(put_strikes=[101.0], vols=[(101.0, 0.2), (110.0, 0.2)]), "E_INPUT", "put_strikes")
    _err(call(call_strikes=[99.0], vols=[(90.0, 0.2), (99.0, 0.2)]), "E_INPUT", "call_strikes")
    _err(call(vols=[(90.0, 0.2)]), "E_INPUT", "vols")
    _err(call(vols=[(90.0, 0.2), (110.0, 0.2), (110.0, 0.3)]), "E_INPUT", "vols")
    _err(call(vols=[(90.0, 0.2), (111.0, 0.2)]), "E_INPUT", "vols")
    _err(
        call(spot=-1.0, put_strikes=[-2.0], call_strikes=[1.0], vols=[(-2.0, 0.2), (1.0, 0.2)]),
        "E_DOMAIN",
        "spot",
    )
    _err(call(vols=[(90.0, 0.0), (110.0, 0.2)]), "E_DOMAIN", "vols")
    _err(call(extension_step=0.0), "E_DOMAIN", "extension_step")
    _err(call(extension_step=90.0), "E_DOMAIN", "extension_step")
    # strikes at spot are allowed on both sides (K <= S for puts, K >= S for calls)
    v.varswap_fair_strike(
        AS_OF, MAT, 100.0, 0.0, 0.0, [100.0], [100.0], [(100.0, 0.2)], 10.0, 0.0, 1.0
    )
    # one day: t = 1/365 (ACT/365)
    one = v.varswap_fair_strike(
        AS_OF,
        date(2025, 1, 3),
        100.0,
        0.0,
        0.0,
        [90.0],
        [110.0],
        [(90.0, 0.2), (110.0, 0.2)],
        10.0,
        0.0,
        1.0,
    )
    tt = 1 / 365
    f = lambda k: 2 / tt * ((k - 100) / 100 - math.log(k / 100))
    want = abs(f(120) - f(110)) / 10 * _bs("CALL", 110, tt, 100, 0, 0, 0.2) + abs(
        f(80) - f(90)
    ) / 10 * _bs("PUT", 90, tt, 100, 0, 0, 0.2)
    assert one[0] == pytest.approx(want, rel=1e-9)


# --- VIX --------------------------------------------------------------------------------------


def _quote(k: float, call: float | None, put: float | None, half: float = 0.05) -> v.Quote:
    cb = None if call is None else call - half
    ca = None if call is None else call + half
    pb = None if put is None else put - half
    pa = None if put is None else put + half
    return v.Quote(k, cb, ca, pb, pa)


# mids: put-call parity around a forward near 100; the 100 strike has the smallest |C - P|
STRIP = [
    _quote(90.0, 10.6, 0.5),
    _quote(95.0, 6.4, 1.5),
    _quote(100.0, 4.2, 4.0),
    _quote(105.0, 2.0, 7.1),
    _quote(110.0, 0.75, 10.9),
]


def _hand_variance(minutes: int, rate: float) -> tuple[float, float]:
    t = minutes / 525600
    g = math.exp(rate * t)
    fwd = 100.0 + g * (4.2 - 4.0)
    pieces = [(90.0, 0.5), (95.0, 1.5), (100.0, (4.2 + 4.0) / 2), (105.0, 2.0), (110.0, 0.75)]
    total = sum(5.0 / (k * k) * p for k, p in pieces)  # every gap is 5, ends included
    return fwd, 2 / t * g * total - 1 / t * (fwd / 100.0 - 1) ** 2


def test_vix_term_variance_by_hand() -> None:
    fwd, k0, var, ks = v.vix_term_variance(30000, 0.04, STRIP)
    want_f, want_v = _hand_variance(30000, 0.04)
    assert fwd == pytest.approx(want_f, rel=1e-15)
    assert k0 == 100.0 and ks == [90.0, 95.0, 100.0, 105.0, 110.0]
    assert var == pytest.approx(want_v, rel=1e-13)
    # order of the strip does not matter
    assert v.vix_term_variance(30000, 0.04, list(reversed(STRIP)))[2] == var


def test_vix_uneven_gaps_and_zero_bids() -> None:
    strip = [
        _quote(70.0, 30.0, 0.2),
        _quote(80.0, 20.0, 0.0, half=0.0),  # zero bid then 70 nonzero: skipped, walk goes on
        _quote(90.0, 10.6, 0.5),
        _quote(100.0, 4.2, 4.0),
        _quote(102.0, 3.0, 5.0),
        _quote(120.0, 0.0, 20.0, half=0.0),  # one zero bid is skipped
        _quote(130.0, 0.0, 30.0, half=0.0),  # a second consecutive zero stops the walk
        _quote(140.0, 0.5, 40.0),
    ]
    t = 30000 / 525600
    fwd, k0, var, ks = v.vix_term_variance(30000, 0.0, strip)
    assert fwd == pytest.approx(100.2, rel=1e-15) and k0 == 100.0
    assert ks == [70.0, 90.0, 100.0, 102.0]
    pieces = [(70.0, 20.0, 0.2), (90.0, 15.0, 0.5), (100.0, 6.0, 4.1), (102.0, 2.0, 3.0)]
    total = sum(gap / (k * k) * p for k, gap, p in pieces)
    assert var == pytest.approx(2 / t * total - 1 / t * (100.2 / 100 - 1) ** 2, rel=1e-13)


def test_vix_null_quotes() -> None:
    strip = [
        _quote(90.0, None, 0.5),  # a null call: not a forward candidate, the put still counts
        _quote(95.0, 6.4, None),  # a null put: removed from the put walk
        _quote(100.0, 4.2, 4.0),
        _quote(105.0, 2.0, 7.1),
        _quote(110.0, None, 10.9),  # a null call: removed from the call walk
    ]
    fwd, k0, var, ks = v.vix_term_variance(30000, 0.0, strip)
    assert k0 == 100.0 and ks == [90.0, 100.0, 105.0]
    t = 30000 / 525600
    total = 10 / 8100 * 0.5 + 7.5 / 10000 * 4.1 + 5 / 11025 * 2.0
    assert var == pytest.approx(2 / t * total - 1 / t * (fwd / 100 - 1) ** 2, rel=1e-13)
    # a null quote that is used raises
    q = v.Quote(1.0, None, 1.0, 1.0, 1.0)
    _err(lambda: q.call, "E_INPUT", "strip")


def test_vix_term_errors() -> None:
    s = STRIP
    _err(lambda: v.vix_term_variance(0, 0.0, s), "E_INPUT", "minutes_to_expiry")
    _err(lambda: v.vix_term_variance(1, 0.0, s[:2]), "E_INPUT", "strip")
    _err(lambda: v.vix_term_variance(1, 0.0, [s[0], s[0], s[1]]), "E_INPUT", "strip")
    _err(lambda: v.vix_term_variance(1, 0.0, [v.Quote(80, 2.0, 1.0, 1, 1), *s]), "E_INPUT", "strip")
    _err(lambda: v.vix_term_variance(1, 0.0, [v.Quote(80, 1, 1, 2.0, 1.0), *s]), "E_INPUT", "strip")
    _err(lambda: v.vix_term_variance(1, 0.0, [v.Quote(80, -1.0, 1, 1, 1), *s]), "E_DOMAIN", "strip")
    nulls = [v.Quote(k, None, None, 1, 1) for k in (1.0, 2.0, 3.0)]
    _err(lambda: v.vix_term_variance(1, 0.0, nulls), "E_INPUT", "strip")
    # forward below every strike: put-call parity gives F = 100 + (C - P) far below 200
    high = [_quote(k, 1.0, 99.0 + k - 200) for k in (200.0, 210.0, 220.0)]
    _err(lambda: v.vix_term_variance(1, 0.0, high), "E_INPUT", "strip")
    # K0 has a null side: forward 100.2 from strike 100, K0 = 100... make K0 the 101 null strike
    k0null = [
        _quote(90.0, 10.6, 0.5),
        _quote(100.0, 4.2, 4.0),
        _quote(100.1, None, 4.0),
        _quote(110.0, 0.75, 10.9),
    ]
    _err(lambda: v.vix_term_variance(30000, 0.0, k0null), "E_INPUT", "strip")
    # no OTM call selected: every call bid above K0 is zero twice
    nocall = [_quote(90.0, 10.6, 0.5), _quote(100.0, 4.2, 4.0)] + [
        _quote(k, 0.0, 9.0, 0.0) for k in (105.0, 110.0)
    ]
    _err(lambda: v.vix_term_variance(30000, 0.0, nocall), "E_INPUT", "strip")
    noput = [_quote(k, 9.0, 0.0, 0.0) for k in (90.0, 95.0)] + [
        _quote(100.0, 4.2, 4.0),
        _quote(110.0, 0.75, 10.9),
    ]
    _err(lambda: v.vix_term_variance(30000, 0.0, noput), "E_INPUT", "strip")
    # K0 is the lowest strike: no put side at all
    lowest = [_quote(100.0, 4.2, 4.0), _quote(105.0, 2.0, 7.1), _quote(110.0, 0.75, 10.9)]
    _err(lambda: v.vix_term_variance(30000, 0.0, lowest), "E_INPUT", "strip")


def test_vix_index_interpolates_to_30_days() -> None:
    n1, n2 = 30000, 50000
    vix, v1, v2 = v.vix_index((n1, 0.04, STRIP), (n2, 0.05, STRIP))
    w1, w2 = _hand_variance(n1, 0.04)[1], _hand_variance(n2, 0.05)[1]
    assert (v1, v2) == pytest.approx((w1, w2), rel=1e-13)
    t1, t2 = n1 / 525600, n2 / 525600
    mix = t1 * w1 * (n2 - 43200) / (n2 - n1) + t2 * w2 * (43200 - n1) / (n2 - n1)
    assert vix == pytest.approx(100 * math.sqrt(mix * 525600 / 43200), rel=1e-13)
    # at exactly 30 days the near term is the index
    at = v.vix_index((43200, 0.04, STRIP), (50000, 0.05, STRIP))[0]
    assert at == pytest.approx(100 * math.sqrt(_hand_variance(43200, 0.04)[1]), rel=1e-13)
    at2 = v.vix_index((30000, 0.04, STRIP), (43200, 0.05, STRIP))[0]
    assert at2 == pytest.approx(100 * math.sqrt(_hand_variance(43200, 0.05)[1]), rel=1e-13)


def test_vix_index_errors() -> None:
    _err(lambda: v.vix_index((50000, 0.0, STRIP), (30000, 0.0, STRIP)), "E_INPUT", "near")
    _err(lambda: v.vix_index((43300, 0.0, STRIP), (50000, 0.0, STRIP)), "E_INPUT", "near")
    _err(lambda: v.vix_index((30000, 0.0, STRIP), (43100, 0.0, STRIP)), "E_INPUT", "near")
    _err(lambda: v.vix_index((43200, 0.0, STRIP), (43200, 0.0, STRIP)), "E_INPUT", "near")
    # F = 10 + 9.9 = 19.9 sits far above K0 = 10: (F/K0 - 1)^2 = 0.98 beats 2 * sum = 0.74,
    # so both term variances, and the bracket, are negative
    wide = [
        _quote(5.0, 15.0, 0.001, 0.0),
        _quote(10.0, 9.901, 0.001, 0.0),
        _quote(20.0, 0.001, 20.0, 0.0),
    ]
    assert v.vix_term_variance(30000, 0.0, wide)[2] < 0
    _err(lambda: v.vix_index((30000, 0.0, wide), (50000, 0.0, wide)), "E_DOMAIN", "near")
