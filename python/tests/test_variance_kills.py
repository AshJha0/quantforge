"""Kill tests for `quantforge_core/variance.py` (GARCH, variance swap, VIX strip).

Lane J-0c: the mutation-report job on PR #39 sampled this module for the `garch_varswap_vix`
(5 of 12 killed) and `garch_vix` (8 of 12) cells. Run the full set locally with
`conformance/mutation/python_sampled_mutants.py --profile variance --sample 100000`.

Two layers. First, every golden case of a `vol.garch.*`, `vol.varswap.*` or `vol.vix.*`
operation is run in process and judged by the neutral runner (independent goldens). Second,
targeted checks for survivors the goldens cannot see. Equivalent survivors are listed in
program/J0C_EQUIVALENT_MUTANTS.md.
"""
import importlib.util
import json
import math
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from quantforge_core import variance as v
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "datasets" / "golden").is_dir())
# Fast suites first; the two with slow `vol.garch.estimate` fits last (the mutation run uses -x).
SUITES = ["stage_e_b/varswap_e", "stage_e_b/vix_e", "stage_e_b/rulings_e_b", "stage_f/e1_vol_3",
          "stage_f/e1_vol_4", "stage_f/e1_vol_5", "stage_f/vix_f", "stage_e_b/garch_e",
          "stage_j/fuzzfix_j", "stage_f/garch_f", "stage_f/e1_vol_1"]
PREFIXES = ("vol.garch.", "vol.varswap.", "vol.vix.")


def _runner():
    spec = importlib.util.spec_from_file_location(
        "qf_runner_variance_kills", ROOT / "conformance" / "runner" / "runner.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _runner()
CLASSES = RUNNER.load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")


@pytest.mark.parametrize("suite", SUITES)
def test_variance_goldens(suite: str) -> None:
    cases = json.loads((ROOT / "datasets" / "golden" / f"{suite}.json").read_text("utf-8"))["cases"]
    results, failures = {}, []
    for case in cases:
        if not case["operation"].startswith(PREFIXES):
            continue
        doc = {"schema_version": "1.0", "case_id": case["case_id"],
               "operation": case["operation"], "inputs": case["inputs"]}
        result = json.loads(json.dumps(run_case(json.dumps(doc))))
        results[case["case_id"]] = result
        status, messages = RUNNER.judge(case, result, CLASSES, results)
        if status != "pass":
            failures.append((case["case_id"], messages[:1]))
            break  # one failure is enough; keeps a mutant run short
    assert not failures, failures[:5]


# --- targeted checks ------------------------------------------------------------------------------
Q = v.Quote
R30 = [0.01 * ((-1) ** i) * (1 + (i % 5) / 10) for i in range(30)]
D0, D1 = date(2026, 1, 1), date(2027, 1, 1)
VS: dict[str, Any] = dict(
    as_of=D0, maturity=D1, spot=100.0, rate=0.0, dividend_yield=0.0,
    put_strikes=[90.0, 100.0], call_strikes=[100.0, 110.0],
    vols=[(90.0, 0.2), (100.0, 0.2), (110.0, 0.2)], extension_step=5.0,
    variance_strike=0.04, variance_notional=1.0)
STRIP = [Q(90.0, 11.0, 11.2, 0.4, 0.6), Q(95.0, 6.5, 6.7, 1.3, 1.5), Q(100.0, 3.0, 3.2, 3.0, 3.2),
         Q(105.0, 1.0, 1.2, 6.0, 6.2), Q(110.0, 0.3, 0.5, 10.3, 10.5)]


def _vs(**kw: Any) -> tuple[float, float, float]:
    return v.varswap_fair_strike(**{**VS, **kw})


def _nulls(q: v.Quote) -> v.Quote:
    return Q(q.strike, None, q.call_ask, q.put_bid, q.put_ask)


# Every error path with its code, field and message. The message text is pinned as a regression
# (current wording, not a spec value); code and field follow the specs.
ERRORS: list[tuple[Callable[[], object], str, str, str]] = [
    (lambda: v.garch_loglik([0.1], 1e-5, 0.1, 0.8, "SAMPLE"),
     "E_INPUT", "returns", "at least 2 returns are needed"),
    (lambda: v.garch_loglik(R30, 1e-5, 0.1, 0.8, "MEAN"),
     "E_INPUT", "initial_variance", "initial_variance must be SAMPLE or a number"),
    (lambda: v.garch_loglik([0.0, 0.0], 1e-5, 0.1, 0.8, "SAMPLE"),
     "E_DOMAIN", "initial_variance", "SAMPLE initial variance is zero"),
    (lambda: v.garch_loglik(R30, 1e-5, 0.1, 0.8, 0.0),
     "E_DOMAIN", "initial_variance", "initial_variance must be positive"),
    (lambda: v.garch_loglik(R30, 0.0, 0.1, 0.8, "SAMPLE"),
     "E_DOMAIN", "omega", "omega must be positive"),
    (lambda: v.garch_loglik(R30, 1e-5, -0.1, 0.8, "SAMPLE"),
     "E_DOMAIN", "alpha", "alpha must not be negative"),
    (lambda: v.garch_loglik(R30, 1e-5, 0.1, -0.8, "SAMPLE"),
     "E_DOMAIN", "beta", "beta must not be negative"),
    (lambda: v.garch_forecast(1e-5, 0.1, 0.8, 1e-4, 0, 252.0),
     "E_INPUT", "horizon", "horizon must be at least 1"),
    (lambda: v.garch_forecast(1e-5, 0.1, 0.8, 1e-4, 1, 0.0),
     "E_INPUT", "periods_per_year", "periods_per_year must be positive"),
    (lambda: v.garch_forecast(1e-5, 0.1, 0.8, 0.0, 1, 252.0),
     "E_DOMAIN", "next_variance", "next_variance must be positive"),
    (lambda: v.garch_forecast(1e-5, 0.2, 0.8, 1e-4, 1, 252.0),
     "E_DOMAIN", "alpha", "alpha + beta must be below 1 for a long-run variance"),
    (lambda: v.garch_fit(R30[:29], "SAMPLE"),
     "E_INPUT", "returns", "at least 30 returns are needed"),
    (lambda: v.garch_loglik_t(R30, 1e-5, 0.1, 0.8, "SAMPLE", "LAPLACE", None, 0.0),
     "E_SCHEMA", "distribution", "distribution is not listed"),
    (lambda: v.garch_loglik_t(R30, 1e-5, 0.1, 0.8, "SAMPLE", "STUDENT_T", None, 0.0),
     "E_INPUT", "degrees_of_freedom", "STUDENT_T needs degrees_of_freedom"),
    (lambda: v.garch_loglik_t(R30, 1e-5, 0.1, 0.8, "SAMPLE", "STUDENT_T", 2.0, 0.0),
     "E_DOMAIN", "degrees_of_freedom", "degrees_of_freedom must be above 2"),
    (lambda: v.garch_loglik_t([0.1], 1e-5, 0.1, 0.8, "SAMPLE", "NORMAL", None, 0.0),
     "E_INPUT", "returns", "at least 2 returns are needed"),
    (lambda: v.garch_estimate(R30, "SAMPLE", "LAPLACE", False),
     "E_SCHEMA", "distribution", "distribution is not listed"),
    (lambda: v.garch_estimate(R30[:29], "SAMPLE", "NORMAL", False),
     "E_INPUT", "returns", "too few returns"),
    (lambda: v.garch_estimate(R30 * 3, "SAMPLE", "STUDENT_T", False),
     "E_INPUT", "returns", "too few returns"),
    (lambda: v.garch_estimate([0.0] * 30, 1e-4, "NORMAL", False),
     "E_DOMAIN", "returns", "the returns are all zero"),
    (lambda: v.garch_estimate([1e200] * 30, "SAMPLE", "NORMAL", False),
     "E_NON_FINITE", "returns", "the sample variance of the returns overflows"),
    (lambda: _vs(maturity=D0), "E_INPUT", "maturity", "maturity must be after as_of"),
    (lambda: _vs(put_strikes=[]), "E_INPUT", "put_strikes", "put_strikes is empty"),
    (lambda: _vs(call_strikes=[]), "E_INPUT", "call_strikes", "call_strikes is empty"),
    (lambda: _vs(put_strikes=[90.0, 90.0]),
     "E_INPUT", "put_strikes", "put_strikes repeats a strike"),
    (lambda: _vs(call_strikes=[110.0, 110.0]),
     "E_INPUT", "call_strikes", "call_strikes repeats a strike"),
    (lambda: _vs(put_strikes=[90.0, 110.0]),
     "E_INPUT", "put_strikes", "a put strike is above spot"),
    (lambda: _vs(call_strikes=[90.0, 110.0]),
     "E_INPUT", "call_strikes", "a call strike is below spot"),
    (lambda: _vs(vols=[(90.0, 0.2), (100.0, 0.2)]),
     "E_INPUT", "vols", "vols must list each strike exactly once"),
    (lambda: _vs(vols=[(90.0, 0.2), (100.0, 0.2), (110.0, 0.2), (110.0, 0.2)]),
     "E_INPUT", "vols", "vols must list each strike exactly once"),
    (lambda: _vs(spot=0.0, put_strikes=[-1.0, 0.0], call_strikes=[0.0, 1.0],
                 vols=[(-1.0, 0.2), (0.0, 0.2), (1.0, 0.2)]),
     "E_DOMAIN", "spot", "spot must be positive"),
    (lambda: _vs(vols=[(90.0, 0.2), (100.0, 0.0), (110.0, 0.2)]),
     "E_DOMAIN", "vols", "a vol is not positive"),
    (lambda: _vs(extension_step=0.0),
     "E_DOMAIN", "extension_step", "extension_step must be positive"),
    (lambda: _vs(extension_step=90.0), "E_DOMAIN", "extension_step",
     "the lowest put strike less the extension step is not positive"),
    (lambda: v.varswap_realized([100.0], 252.0, 0.04, 1.0),
     "E_INPUT", "prices", "at least 2 prices are needed"),
    (lambda: v.varswap_realized([100.0, 0.0], 252.0, 0.04, 1.0),
     "E_DOMAIN", "prices", "a price is not positive"),
    (lambda: v.vix_term_variance(0, 0.0, STRIP),
     "E_INPUT", "minutes_to_expiry", "minutes_to_expiry must be at least 1"),
    (lambda: v.vix_term_variance(100, 0.0, STRIP[:2]),
     "E_INPUT", "strip", "at least 3 strikes are needed"),
    (lambda: v.vix_term_variance(100, 0.0, [*STRIP, STRIP[0]]),
     "E_INPUT", "strip", "a strike is repeated"),
    (lambda: v.vix_term_variance(100, 0.0, [Q(90.0, 2.0, 1.0, 0.4, 0.6), *STRIP[1:]]),
     "E_INPUT", "strip", "a bid is above its ask"),
    (lambda: v.vix_term_variance(100, 0.0, [Q(90.0, 11.0, 11.2, 0.7, 0.6), *STRIP[1:]]),
     "E_INPUT", "strip", "a bid is above its ask"),
    (lambda: v.vix_term_variance(100, 0.0, [Q(90.0, 11.0, 11.2, -0.4, 0.6), *STRIP[1:]]),
     "E_DOMAIN", "strip", "a quote is negative"),
    (lambda: v.vix_term_variance(100, 0.0, [_nulls(q) for q in STRIP]),
     "E_INPUT", "strip", "no strike has both a call and a put quote"),
    (lambda: v.vix_term_variance(100, 0.0, [Q(100.0, 0.0, 0.1, 50.0, 50.2),
                                            Q(105.0, 0.0, 0.1, 55.0, 55.2),
                                            Q(110.0, 0.0, 0.1, 60.0, 60.2)]),
     "E_INPUT", "strip", "no strike is at or below the forward"),
    (lambda: v.vix_term_variance(100, 0.0, STRIP[2:]), "E_INPUT", "strip",
     "no out-of-the-money put or no out-of-the-money call is selected"),
    (lambda: v.vix_index((43300, 0.0, STRIP), (50000, 0.0, STRIP)),
     "E_INPUT", "near", "the terms must bracket 30 days with near before next"),
    (lambda: v.vix_index((40000, 0.0, STRIP), (43100, 0.0, STRIP)),
     "E_INPUT", "near", "the terms must bracket 30 days with near before next"),
    (lambda: v.vix_index((43200, 0.0, STRIP), (43200, 0.0, STRIP)),
     "E_INPUT", "near", "the terms must bracket 30 days with near before next"),
]


@pytest.mark.parametrize("k", range(len(ERRORS)))
def test_error_paths(k: int) -> None:
    call, code, field, message = ERRORS[k]
    with pytest.raises(QfError) as info:
        call()
    assert (info.value.code, info.value.field, info.value.message) == (code, field, message)


# --- closed forms and hand values -----------------------------------------------------------------
EULER = 0.5772156649015329


def test_recursion_hand_values() -> None:
    # Three returns, sigma2_1 = 1e-4: sigma2_{t+1} = omega + alpha r_t^2 + beta sigma2_t by hand.
    r = [0.01, -0.02, 0.015]
    s = [1e-4, 1e-5 + 0.1 * 1e-4 + 0.8 * 1e-4]
    s.append(1e-5 + 0.1 * 4e-4 + 0.8 * s[1])
    nxt = 1e-5 + 0.1 * 2.25e-4 + 0.8 * s[2]
    ll = -0.5 * sum(math.log(2 * math.pi) + math.log(si) + ri * ri / si
                    for ri, si in zip(r, s, strict=True))
    got = v.garch_loglik(r, 1e-5, 0.1, 0.8, 1e-4)
    assert got[0] == pytest.approx(ll, rel=1e-13)
    assert got[1] == pytest.approx(s, rel=1e-13)
    assert got[2] == pytest.approx(nxt, rel=1e-13)
    sample = sum(x * x for x in r) / 3
    assert v.garch_loglik(r, 1e-5, 0.1, 0.8, "SAMPLE")[1][0] == pytest.approx(sample, rel=1e-14)
    # The stage F form with a mean recurses on r - mean.
    t = v.garch_loglik_t([x + 0.003 for x in r], 1e-5, 0.1, 0.8, 1e-4, "NORMAL", None, 0.003)
    assert t[0] == pytest.approx(ll, rel=1e-12)
    assert t[2] == pytest.approx(nxt, rel=1e-12)


def test_student_t_loglik_is_the_t_density() -> None:
    r, nu = [0.01, -0.02, 0.015, 0.004], 6.0
    s, ll = 1e-4, 0.0
    for x in r:  # standardised t density with variance s, written out independently
        ll += (math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2)
               - 0.5 * math.log(math.pi * (nu - 2) * s)
               - (nu + 1) / 2 * math.log(1 + x * x / ((nu - 2) * s)))
        s = 1e-5 + 0.1 * x * x + 0.8 * s
    got = v.garch_loglik_t(r, 1e-5, 0.1, 0.8, 1e-4, "STUDENT_T", nu, 0.0)
    assert got[0] == pytest.approx(ll, rel=1e-13)
    assert got[2] == pytest.approx(s, rel=1e-13)


@pytest.mark.parametrize("student", [False, True])
def test_score_gradient_matches_finite_differences(student: bool) -> None:
    e = [0.01, -0.02, 0.015, 0.004, -0.011, 0.007]
    theta = [1e-5, 0.12, 0.8] + ([7.0] if student else [])
    ll, grad = v._score(e, theta, 1.2e-4, student)
    for k in range(len(theta)):
        h = 1e-6 * theta[k]
        up, dn = list(theta), list(theta)
        up[k] += h
        dn[k] -= h
        fd = (v._score(e, up, 1.2e-4, student)[0] - v._score(e, dn, 1.2e-4, student)[0]) / (2 * h)
        assert grad[k] == pytest.approx(fd, rel=1e-5, abs=1e-6)
    if not student:
        assert ll == pytest.approx(v._recursion(e, 1e-5, 0.12, 0.8, 1.2e-4)[0], rel=1e-14)


@pytest.mark.parametrize(("x", "psi"), [
    (1.0, -EULER), (0.5, -EULER - 2 * math.log(2)), (2.0, 1 - EULER),
    (3.5, -EULER - 2 * math.log(2) + 2 + 2 / 3 + 2 / 5),
    (12.0, sum(1 / k for k in range(1, 12)) - EULER),
])
def test_digamma_closed_forms(x: float, psi: float) -> None:
    assert v._digamma(x) == pytest.approx(psi, rel=1e-13, abs=1e-14)


def test_small_helpers() -> None:
    assert v._t_constant(5.0) == pytest.approx(
        math.lgamma(3.0) - math.lgamma(2.5) - 0.5 * math.log(3 * math.pi), rel=1e-14)
    for x in (-3.0, -0.5, 0.0, 0.7, 4.0):
        assert v._sigmoid(x) == pytest.approx(1 / (1 + math.exp(-x)), rel=1e-15)
        assert v._logit(v._sigmoid(x)) == pytest.approx(x, abs=1e-12)
    assert v._sigmoid(-800.0) == 0.0
    assert v._sigmoid(800.0) == 1.0
    assert v._logit(0.75) == pytest.approx(math.log(3), rel=1e-15)
    assert v._f(110.0, 100.0, 0.5) == pytest.approx(4 * (0.1 - math.log(1.1)), rel=1e-14)


@pytest.mark.parametrize(("p", "h"), [(0.9, 5), (0.0, 3), (0.5, 1)])
def test_forecast_closed_form(p: float, h: int) -> None:
    omega, alpha, nv, ppy = 2e-6, p / 3, 3e-4, 252.0
    lr = omega / (1 - p)
    want = [lr + p ** (k - 1) * (nv - lr) for k in range(1, h + 1)]
    got, total, vol, long_run = v.garch_forecast(omega, alpha, p - alpha, nv, h, ppy)
    assert got == pytest.approx(want, rel=1e-13)
    assert total == pytest.approx(sum(want), rel=1e-13)
    assert vol == pytest.approx(math.sqrt(sum(want) * ppy / h), rel=1e-13)
    assert long_run == pytest.approx(lr, rel=1e-14)


def test_boundaries_are_accepted() -> None:
    # alpha = beta = 0 is allowed (non-negative).
    assert v.garch_forecast(1e-5, 0.0, 0.0, 2e-5, 2, 1.0)[0] == pytest.approx([2e-5, 1e-5])
    assert v.garch_loglik([0.01, 0.02], 1e-5, 0.0, 0.0, 1e-4)[2] == pytest.approx(1e-5)
    assert v.garch_loglik([0.01, 0.02], 1e-5, 0.1, 0.8, "SAMPLE")[1][0] == pytest.approx(2.5e-4)


def test_realized_closed_form() -> None:
    prices = [100.0, 101.0, 99.0, 102.0]
    sq = sum(math.log(b / a) ** 2 for a, b in zip(prices, prices[1:], strict=False))
    var, vol, pay = v.varswap_realized(prices, 252.0, 0.04, 1e4)
    assert var == pytest.approx(252.0 / 3 * sq, rel=1e-14)
    assert vol == pytest.approx(math.sqrt(252.0 / 3 * sq), rel=1e-14)
    assert pay == pytest.approx(1e4 * (252.0 / 3 * sq - 0.04), rel=1e-13)


def _f100(k: float) -> float:
    return 2 * ((k - 100.0) / 100.0 - math.log(k / 100.0))


def test_weights_hand_values() -> None:
    # Slopes of f between consecutive strikes; w_j = s_j - s_{j-1}.
    s0 = abs(_f100(110.0) - _f100(100.0)) / 10
    s1 = abs(_f100(115.0) - _f100(110.0)) / 5
    assert v._weights([100.0, 110.0], 115.0, 100.0, 1.0) == pytest.approx([s0, s1 - s0], rel=1e-13)
    p0 = abs(_f100(90.0) - _f100(100.0)) / 10
    p1 = abs(_f100(85.0) - _f100(90.0)) / 5
    assert v._weights([100.0, 90.0], 85.0, 100.0, 1.0) == pytest.approx([p0, p1 - p0], rel=1e-13)


def test_fair_strike_flat_vol_is_close_to_sigma_squared() -> None:
    # A dense strip under flat 20 % vol replicates about 0.04 (the log contract).
    ks = [float(k) for k in range(30, 301)]
    puts = [k for k in ks if k <= 100]
    calls = [k for k in ks if k >= 100]
    fair, vol, pay = _vs(put_strikes=puts, call_strikes=calls, vols=[(k, 0.2) for k in ks],
                         extension_step=1.0, rate=0.03, dividend_yield=0.01,
                         variance_strike=0.03, variance_notional=100.0)
    assert fair == pytest.approx(0.04, rel=2e-3)
    assert vol == pytest.approx(math.sqrt(fair), rel=1e-15)
    assert pay == pytest.approx(100.0 * math.exp(-0.03) * (fair - 0.03), rel=1e-13)


def test_side_walk() -> None:
    qs = [Q(float(k), b, 1.0, b, 1.0) for k, b in enumerate([0.5, 0.0, 0.4, 0.0, 0.0, 0.3])]
    assert [q.strike for q in v._side(qs, lambda q: q.call_bid)] == [0.0, 2.0]
    nul = [Q(0.0, None, None, 1.0, 1.0), Q(1.0, 0.2, 0.3, 1.0, 1.0)]
    assert [q.strike for q in v._side(nul, lambda q: q.call_bid)] == [1.0]


def test_vix_term_variance_hand_value() -> None:
    # Cboe method by hand for STRIP: K* = 100 (call - put = 0), F = 100, K0 = 100, gaps 5.
    t = 30000 / 525600
    g = math.exp(0.02 * t)
    mids = {90.0: 0.5, 95.0: 1.4, 100.0: 3.1, 105.0: 1.1, 110.0: 0.4}
    want = (2 / t) * g * sum(5.0 / (k * k) * p for k, p in mids.items())
    fwd, k0, var, ks = v.vix_term_variance(30000, 0.02, STRIP)
    assert (fwd, k0, ks) == (100.0, 100.0, [90.0, 95.0, 100.0, 105.0, 110.0])
    assert var == pytest.approx(want, rel=1e-13)


def test_vix_forward_above_k0_and_end_gaps() -> None:
    # K* = 100 with call - put = 0.5, so F = 100.5 > K0 = 100; uneven gaps at the ends.
    strip = [Q(80.0, 21.0, 21.2, 0.2, 0.4), Q(95.0, 6.5, 6.7, 1.3, 1.5),
             Q(100.0, 3.5, 3.7, 3.0, 3.2), Q(102.0, 2.0, 2.2, 4.0, 4.2),
             Q(120.0, 0.3, 0.5, 20.3, 20.5)]
    t = 50000 / 525600
    fwd, k0, var, _ = v.vix_term_variance(50000, 0.0, strip)
    assert fwd == pytest.approx(100.5)
    assert k0 == 100.0
    total = (15 / 80**2 * 0.3 + 10 / 95**2 * 1.4 + 3.5 / 100**2 * 3.35 + 10 / 102**2 * 2.1
             + 18 / 120**2 * 0.4)
    assert var == pytest.approx((2 / t) * total - (1 / t) * 0.005**2, rel=1e-13)


def test_vix_index_interpolation() -> None:
    n1, n2 = 30000, 50000
    v1 = v.vix_term_variance(n1, 0.0, STRIP)[2]
    v2 = v.vix_term_variance(n2, 0.0, STRIP)[2]
    t1, t2 = n1 / 525600, n2 / 525600
    w = t1 * v1 * (n2 - 43200) / (n2 - n1) + t2 * v2 * (43200 - n1) / (n2 - n1)
    got = v.vix_index((n1, 0.0, STRIP), (n2, 0.0, STRIP))
    assert got[0] == pytest.approx(100 * math.sqrt(w * 525600 / 43200), rel=1e-13)
    assert (got[1], got[2]) == (v1, v2)
    # The bracket ends are included: a term at exactly 30 days gives that term's own index.
    own = 100 * math.sqrt(v.vix_term_variance(43200, 0.0, STRIP)[2])
    assert v.vix_index((43200, 0.0, STRIP), (50000, 0.0, STRIP))[0] == pytest.approx(own, rel=1e-12)
    assert v.vix_index((30000, 0.0, STRIP), (43200, 0.0, STRIP))[0] == pytest.approx(own, rel=1e-12)


def test_nelder_mead_finds_a_known_minimum() -> None:
    def f(p: list[float]) -> float:
        return (p[0] - 1) ** 2 + 2 * (p[1] + 3) ** 2 + 5

    x, val = v._nelder_mead(f, [0.0, 0.0], 0.5, 2000)
    assert x == pytest.approx([1.0, -3.0], abs=1e-6)
    assert val == pytest.approx(5.0, abs=1e-12)
