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
import itertools
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
VS: dict[str, Any] = {
    "as_of": D0, "maturity": D1, "spot": 100.0, "rate": 0.0, "dividend_yield": 0.0,
    "put_strikes": [90.0, 100.0], "call_strikes": [100.0, 110.0],
    "vols": [(90.0, 0.2), (100.0, 0.2), (110.0, 0.2)], "extension_step": 5.0,
    "variance_strike": 0.04, "variance_notional": 1.0}
STRIP = [Q(90.0, 11.0, 11.2, 0.4, 0.6), Q(95.0, 6.5, 6.7, 1.3, 1.5), Q(100.0, 3.0, 3.2, 3.0, 3.2),
         Q(105.0, 1.0, 1.2, 6.0, 6.2), Q(110.0, 0.3, 0.5, 10.3, 10.5)]


def _vs(**kw: Any) -> tuple[float, float, float]:
    return v.varswap_fair_strike(**{**VS, **kw})


def _golden_inputs(case_id: str) -> dict[str, Any]:
    cases = json.loads((ROOT / "datasets" / "golden" / "stage_f" / "garch_f.json")
                       .read_text("utf-8"))["cases"]
    inputs: dict[str, Any] = next(c for c in cases if c["case_id"] == case_id)["inputs"]
    return inputs


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
    (lambda: _vs(rate=0.5, put_strikes=[99.0, 100.0], call_strikes=[100.0, 101.0],
                 vols=[(99.0, 0.01), (100.0, 0.01), (101.0, 0.01)], extension_step=0.5),
     "E_DOMAIN", "vols", "the replicated variance is negative"),
    (lambda: Q(1.0, None, 1.0, 1.0, 1.0).call, "E_INPUT", "strip", "a null quote is used"),
    (lambda: Q(1.0, 1.0, 1.0, 1.0, None).put, "E_INPUT", "strip", "a null quote is used"),
    (lambda: v.garch_estimate(_golden_inputs("garch_f-0017")["returns"], "SAMPLE", "NORMAL", False),
     "E_NO_CONVERGENCE", "returns", "no interior maximum"),
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
    (lambda: v.vix_term_variance(100, 0.0, [Q(90.0, 11.0, 11.2, 0.4, 0.6),
                                            Q(95.0, 6.9, 7.1, 0.9, 1.1),
                                            Q(100.0, 3.0, 3.2, None, 3.2),
                                            Q(105.0, 1.0, 1.2, 6.0, 6.2)]),
     "E_INPUT", "strip", "the K0 call or put has a null quote"),
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
    sq = sum(math.log(b / a) ** 2 for a, b in itertools.pairwise(prices))
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


# --- garch_estimate properties (slow: two 2000-return fits, shared by the tests below) -----------
def _estimate_case(case_id: str) -> tuple[list[float], dict[str, Any], dict[str, Any]]:
    cases = json.loads((ROOT / "datasets" / "golden" / "stage_f" / "garch_f.json")
                       .read_text("utf-8"))["cases"]
    case = next(c for c in cases if c["case_id"] == case_id)
    i = case["inputs"]
    out = v.garch_estimate(i["returns"], i["initial_variance"], i["distribution"], i["demean"])
    return i["returns"], i, out


@pytest.fixture(scope="module", params=["garch_f-0011", "garch_f-0012"])
def estimate(request: pytest.FixtureRequest) -> tuple[list[float], dict[str, Any], dict[str, Any]]:
    return _estimate_case(request.param)


def test_estimate_properties(estimate: tuple[list[float], dict[str, Any], dict[str, Any]]) -> None:
    returns, i, out = estimate
    student = i["distribution"] == "STUDENT_T"
    nu = out["degrees_of_freedom"]
    assert (nu is not None) == student
    mu = sum(returns) / len(returns)
    assert out["mean"] == pytest.approx(mu, rel=1e-12)
    assert out["persistence"] == out["alpha"] + out["beta"]
    # The reported loglik is the likelihood at the reported parameters.
    ll = v.garch_loglik_t(returns, out["omega"], out["alpha"], out["beta"], "SAMPLE",
                          i["distribution"], nu, mu)[0]
    assert out["loglik"] == pytest.approx(ll, rel=1e-12)
    # First-order condition: an interior maximum has a zero score (relative to the scale).
    e = [r - mu for r in returns]
    s0 = sum(x * x for x in e) / len(e)
    theta = [out["omega"], out["alpha"], out["beta"]] + ([nu] if student else [])
    grad = v._score(e, theta, s0, student)[1]
    scale = [s0, 1.0, 1.0, 1.0]
    assert max(abs(g) * s for g, s in zip(grad, scale, strict=False)) < 1e-6 * len(e)
    # Standard errors: sqrt of the diagonal of the inverse observed information, with the Hessian
    # from an independent central difference of the log-likelihood itself.
    import numpy as np

    n = len(theta)
    h = np.zeros((n, n))
    for a in range(n):
        for b in range(n):
            da, db = 1e-4 * theta[a], 1e-4 * theta[b]

            def ll_at(sa: float, sb: float, a: int = a, b: int = b, da: float = da,
                      db: float = db) -> float:
                t = list(theta)
                t[a] += sa * da
                t[b] += sb * db
                return v._score(e, t, s0, student)[0]

            h[a, b] = (ll_at(1, 1) - ll_at(1, -1) - ll_at(-1, 1) + ll_at(-1, -1)) / (4 * da * db)
    se = np.sqrt(np.diag(np.linalg.inv(-h)))
    keys = ["omega", "alpha", "beta", "degrees_of_freedom"]
    for j, k in enumerate(keys):
        if j < n:
            assert out["std_errors"][k] == pytest.approx(float(se[j]), rel=2e-3)
        else:
            assert out["std_errors"][k] is None


# --- Nelder-Mead against an independent reference -------------------------------------------------
def _reference_nm(f: Callable[[list[float]], float], start: list[float], step: float,
                  iterations: int) -> tuple[list[float], float, int]:
    """Textbook Nelder-Mead (reflection 1, expansion 2, contraction 1/2, shrink 1/2; Lagarias et
    al. 1998 acceptance rules), written separately from the module and with the same rounding
    order (c + t (w - c)) so paths agree to the bit. Also returns the evaluation count."""
    calls = 0

    def g(x: list[float]) -> float:
        nonlocal calls
        calls += 1
        return f(x)

    n = len(start)
    pts = [list(start)]
    for i in range(n):
        p = list(start)
        p[i] += step
        pts.append(p)
    vals = [g(p) for p in pts]
    for _ in range(iterations):
        pairs = sorted(zip(vals, range(n + 1), strict=True))
        pts = [pts[k] for _, k in pairs]
        vals = [val for val, _ in pairs]
        lo, second, hi = vals[0], vals[n - 1], vals[n]
        if hi - lo <= 1e-14 * (1 + abs(lo)):
            break
        c = [sum(p[j] for p in pts[:n]) / n for j in range(n)]
        w = pts[n]
        xr = [c[j] - (w[j] - c[j]) for j in range(n)]
        fr = g(xr)
        if fr < lo:
            xe = [c[j] - 2 * (w[j] - c[j]) for j in range(n)]
            fe = g(xe)
            pts[n], vals[n] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < second:
            pts[n], vals[n] = xr, fr
        else:
            if fr < hi:  # outside contraction
                xc = [c[j] - 0.5 * (w[j] - c[j]) for j in range(n)]
            else:  # inside contraction
                xc = [c[j] + 0.5 * (w[j] - c[j]) for j in range(n)]
            fc = g(xc)
            if fc < min(fr, hi):
                pts[n], vals[n] = xc, fc
            else:
                pts = [pts[0]] + [[a + 0.5 * (b - a) for a, b in zip(pts[0], p, strict=True)]
                                  for p in pts[1:]]
                vals = [vals[0]] + [g(p) for p in pts[1:]]
    k = min(range(n + 1), key=vals.__getitem__)
    return pts[k], vals[k], calls


def _rosen(p: list[float]) -> float:
    return 100 * (p[1] - p[0] ** 2) ** 2 + (1 - p[0]) ** 2


def _ridge(p: list[float]) -> float:
    return abs(p[0] - 0.3) + 4 * abs(p[1] + 0.2) + 0.5 * abs(p[2])


def _cone(p: list[float]) -> float:
    # Square-root cusps make contractions fail, so this path exercises the shrink step.
    return math.sqrt(abs(p[0])) + math.sqrt(abs(p[1] - 0.1))


def _bowl(p: list[float]) -> float:
    return (p[0] - 1) ** 2 + 5


@pytest.mark.parametrize("iterations", [1, 2, 3, 5, 8, 13, 40, 400, 5000])
@pytest.mark.parametrize(("f", "start", "step"), [
    (_rosen, [-1.2, 1.0], 0.5), (_ridge, [1.0, 1.0, 1.0], 0.7), (_bowl, [4.0], 0.5), (_cone, [0.7, 0.9], 0.6)])
def test_nelder_mead_matches_reference(f: Callable[[list[float]], float], start: list[float],
                                       step: float, iterations: int) -> None:
    count = 0

    def counted(x: list[float]) -> float:
        nonlocal count
        count += 1
        return f(x)

    x, val = v._nelder_mead(counted, start, step, iterations)
    rx, rval, rcount = _reference_nm(f, start, step, iterations)
    assert x == pytest.approx(rx, rel=1e-12, abs=1e-15)
    assert val == pytest.approx(rval, rel=1e-12, abs=1e-15)
    assert count == rcount


def test_minimum_sizes_are_accepted() -> None:
    # The lower bounds are inclusive: 1 minute, 30 returns for the fit (spec minimums).
    assert v.vix_term_variance(1, 0.0, STRIP)[1] == 100.0
    assert math.isfinite(v.garch_fit(R30, "SAMPLE"))
    for returns, dist in ((R30, "NORMAL"), ((R30 * 4)[:100], "STUDENT_T")):
        try:
            v.garch_estimate(returns, "SAMPLE", dist, False)
        except QfError as err:  # these toy series may have no interior maximum
            assert err.code == "E_NO_CONVERGENCE"


def test_more_boundaries() -> None:
    # NORMAL ignores a stray degrees_of_freedom; nu just above 2 and spot = 1 are accepted.
    r = [0.01, -0.02, 0.015]
    normal = v.garch_loglik(r, 1e-5, 0.1, 0.8, 1e-4)[0]
    assert v.garch_loglik_t(r, 1e-5, 0.1, 0.8, 1e-4, "NORMAL", 5.0, 0.0)[0] == normal
    assert math.isfinite(v.garch_loglik_t(r, 1e-5, 0.1, 0.8, 1e-4, "STUDENT_T", 2.5, 0.0)[0])
    fair = _vs(spot=1.0, put_strikes=[0.9, 1.0], call_strikes=[1.0, 1.1],
               vols=[(0.9, 0.2), (1.0, 0.2), (1.1, 0.2)], extension_step=0.05)[0]
    assert fair > 0
    # The lowest put less the step may be any positive number, here exactly 1.
    assert _vs(put_strikes=[2.0, 100.0], vols=[(2.0, 0.2), (100.0, 0.2), (110.0, 0.2)],
               extension_step=1.0)[0] > 0


def test_price_of_one_and_frozen_quote() -> None:
    # A price of exactly 1 is positive and allowed; Quote is immutable (a frozen dataclass).
    assert v.varswap_realized([1.0, math.e], 1.0, 0.0, 1.0)[0] == pytest.approx(1.0, rel=1e-15)
    with pytest.raises(AttributeError):
        STRIP[0].strike = 1.0  # type: ignore[misc]


# --- J-0 audit follow-up: survivors once listed as equivalent ---------------------------------
def _garch_series(n: int, seed: int, scale: float = 1.0, df: int | None = None) -> list[float]:
    """A GARCH(1,1) path (omega 0.05, alpha 0.1, beta 0.85), Student-t shocks when df is set."""
    import random

    rng = random.Random(seed)
    s2, out = 0.05 / (1 - 0.1 - 0.85), []
    for _ in range(n):
        z = rng.gauss(0, 1)
        if df:
            chi = sum(rng.gauss(0, 1) ** 2 for _ in range(df)) / df
            z = z / math.sqrt(chi) * math.sqrt((df - 2) / df)
        r = math.sqrt(s2) * z
        out.append(r * scale)
        s2 = 0.05 + 0.1 * r * r + 0.85 * s2
    return out


def test_fit_overflowing_squares_has_no_finite_likelihood() -> None:
    # Line 185 is reachable: the squares of 1e200 overflow, so every start is infinite.
    with pytest.raises(QfError) as err:
        v.garch_fit([1e200] * 30, "SAMPLE")
    assert err.value.code == "E_NO_CONVERGENCE"
    assert err.value.message == "the GARCH fit found no finite likelihood"


def test_zero_fair_variance_is_allowed() -> None:
    # Line 422: both options are so far out of the money that they price exactly 0, the forward
    # term is 0 (rate = dividend = 0), so fair = 0.0 exactly. Zero is not negative.
    got = _vs(put_strikes=[1.0], call_strikes=[1e6], vols=[(1.0, 0.01), (1e6, 0.01)],
              extension_step=0.5, variance_strike=0.0)
    assert got == (0.0, 0.0, 0.0)


def test_zero_bracket_variance_is_allowed() -> None:
    # Line 559: a strip whose term variance is exactly 0.0 (found by an ulp scan in the J-0
    # audit), near term at exactly 30 days so the next term has weight 0. bracket = 0.0.
    strip = [Q(99.0, 10.00001, 10.00001, 1e-5, 1e-5), Q(100.0, 1.601, 1.601, 0.001, 0.001),
             Q(102.0, 0.04083039237832999, 0.04083039237832999, 5.0, 5.0)]
    assert v.vix_term_variance(43200, 0.0, strip)[2] == 0.0
    assert v.vix_index((43200, 0.0, strip), (86400, 0.0, strip)) == (0.0, 0.0, 0.0)


def test_estimate_is_scale_equivariant() -> None:
    # Line 339: the Newton stop test is relative to `sample` for omega. Independent check: the
    # GARCH MLE is scale-equivariant, so returns times 1e4 give omega times 1e8, the same alpha
    # and beta, and a log-likelihood lower by n ln(1e4).
    base = _garch_series(400, 3)
    small = v.garch_estimate(base, "SAMPLE", "NORMAL", True)
    big = v.garch_estimate([r * 1e4 for r in base], "SAMPLE", "NORMAL", True)
    assert big["omega"] == pytest.approx(small["omega"] * 1e8, rel=1e-6)  # type: ignore[operator]
    assert big["alpha"] == pytest.approx(small["alpha"], rel=1e-6)
    assert big["beta"] == pytest.approx(small["beta"], rel=1e-6)
    assert big["loglik"] == pytest.approx(
        small["loglik"] - 400 * math.log(1e4), rel=1e-9)  # type: ignore[operator]


@pytest.mark.parametrize(("n", "seed", "df", "expected"), [
    (120, 7, 4, -116.54250545385293),
    (300, 1, None, -389.6476421536659),
    (150, 5, 3, -161.0634970215938),
])
def test_fit_reaches_the_reference_optimum(n: int, seed: int, df: int | None,
                                           expected: float) -> None:
    # Lines 161 and 176: the start map and the beta map steer the multi-start search. Expected
    # values are independent: scipy Nelder-Mead on `garch_loglik` over (omega, alpha, beta) from
    # 15 starts, xatol 1e-12 (J-0 audit follow-up, 2026-11-14). The fit must reach that optimum.
    got = v.garch_fit(_garch_series(n, seed, df=df), "SAMPLE")
    assert got == pytest.approx(expected, rel=1e-11)


@pytest.mark.parametrize(("n", "seed", "scale", "df", "dist", "demean", "expected"), [
    (400, 2, 1.0, None, "NORMAL", False,
     (0.0599267705898633, 0.07776585249457289, 0.8631607506434537, None, -567.2913052519141)),
    (400, 5, 1e-3, None, "NORMAL", True,
     (3.1569470544083495e-08, 0.0764464765984754, 0.8971215508179281, None, 2165.321304346979)),
    (600, 4, 1.0, 5, "STUDENT_T", True,
     (0.14725931171122297, 0.16042488842740876, 0.6933883509638681, 5.116785025899286,
      -788.8653065537608)),
    (600, 8, 1.0, 30, "STUDENT_T", False,
     (0.21509788346067585, 0.06853208993157327, 0.677832848284892, 16.645171942881394,
      -794.7791031876749)),
])
def test_estimate_pinned_workloads(n: int, seed: int, scale: float, df: int | None, dist: str,
                                   demean: bool, expected: tuple[Any, ...]) -> None:
    # The interior guard (lines 327, 328), the Hessian (323) and the Newton update (341, 349)
    # change the status or the estimate on these series, including a small-scale one (returns
    # times 1e-3) where the omega bound 1e-6 * sample matters. The expected values are PINNED
    # current output (2026-11-14), not independent; tolerances sit above optimiser noise.
    got = v.garch_estimate(_garch_series(n, seed, scale, df), "SAMPLE", dist, demean)
    keys = ("omega", "alpha", "beta", "degrees_of_freedom", "loglik")
    for key, want in zip(keys, expected, strict=True):
        if want is None:
            assert got[key] is None
        else:
            assert got[key] == pytest.approx(want, rel=1e-9 if key == "loglik" else 1e-6), key
