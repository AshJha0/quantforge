"""Stage J wave 1 property tests (program/STAGE_J_HANDOVER.md, "Property tests"): the two
backtest engines agree, attribution closes, the look-ahead canary is caught; purged folds never
leak; Viterbi equals brute force; DSR and PSR move the right way; PBO is a probability."""

import itertools
import math
import random

from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core import research

SETTINGS = settings(max_examples=200, deadline=None)
series = st.integers(min_value=2, max_value=40)


def _walk(rng: random.Random, t: int) -> list[float]:
    prices = [100.0]
    for _ in range(t - 1):
        prices.append(prices[-1] * math.exp(rng.gauss(0.0, 0.01)))
    return prices


def _close(a: float, b: float, rel: float) -> bool:
    return abs(a - b) <= rel * max(1.0, abs(a), abs(b))


@SETTINGS
@given(series, st.integers(min_value=0, max_value=10**6), st.integers(min_value=0, max_value=3))
def test_event_equals_vector_and_attribution_closes(t, seed, lag):
    rng = random.Random(seed)
    prices = _walk(rng, t)
    targets = [float(rng.randint(-5, 5)) for _ in range(t)]
    costs = (rng.uniform(0, 20), rng.uniform(0, 0.1), rng.uniform(0, 2), rng.uniform(0.5, 50))
    lag = min(lag, t - 1)
    event = research.backtest_run(prices, targets, lag, *costs, "EVENT")
    vector = research.backtest_run(prices, targets, lag, *costs, "VECTOR")
    for key, value in event.items():
        other = vector[key]
        if isinstance(value, list):
            assert all(_close(a, b, 1e-10) for a, b in zip(value, other, strict=True)), key
        else:
            assert _close(value, other, 1e-10), key
    parts = [
        event[k]
        for k in ("total_gross", "total_spread_cost", "total_commission", "total_fixed_cost")
    ]
    identity = parts[0] - parts[1] - parts[2] - parts[3]
    assert abs(identity - event["total_net"]) <= 1e-12 * max(1.0, *map(abs, parts))


@SETTINGS
@given(series, st.integers(min_value=0, max_value=10**6))
def test_zero_costs_and_doubled_costs(t, seed):
    rng = random.Random(seed)
    prices = _walk(rng, t)
    targets = [float(rng.randint(-5, 5)) for _ in range(t)]
    free = research.backtest_run(prices, targets)
    assert free["pnl_net"] == free["pnl_gross"]
    one = research.backtest_run(prices, targets, 1, 3.0, 0.02, 0.5)
    two = research.backtest_run(prices, targets, 1, 6.0, 0.04, 1.0)
    for key in ("total_spread_cost", "total_commission", "total_fixed_cost"):
        assert two[key] == 2 * one[key]


def test_look_ahead_canary_detected_at_lag_zero_only():
    """Q7 / J-2: a target of sign(p_{t+1} - p_t) peeks one bar ahead. Shifted one bar and run at
    lag 0 it trades on the move it earns, so gross P&L is large; at lag 1 it is noise."""
    rng = random.Random(7)
    prices = _walk(rng, 2001)
    peek = [math.copysign(1.0, b - a) for a, b in itertools.pairwise(prices)] + [0.0]
    shifted = [0.0, *peek[:-1]]  # target at t = sign(p_t - p_{t-1}): known only at close t
    cheat = research.backtest_run(prices, peek, lag=0)["total_gross"]
    honest = research.backtest_run(prices, shifted, lag=0)["total_gross"]
    moves = math.fsum(abs(b - a) for a, b in itertools.pairwise(prices))
    assert cheat > 0.9 * moves  # earns almost every absolute move: detected
    assert abs(honest) < 0.2 * moves  # driftless walk: no edge without look-ahead
    lagged = research.backtest_run(prices, peek, lag=1)["total_gross"]
    assert abs(lagged) < 0.2 * moves


@SETTINGS
@given(st.integers(min_value=2, max_value=60), st.integers(min_value=0, max_value=10**6))
def test_purged_folds_never_overlap_and_reduce_to_kfold(n, seed):
    rng = random.Random(seed)
    t0 = sorted(rng.uniform(0, 100) for _ in range(n))
    t1 = [a + rng.uniform(0, 10) for a in t0]
    k = rng.randint(2, n)
    result = research.cv_purged_kfold(t0, t1, k, rng.uniform(0, 0.3))
    for fold in result["folds"]:
        test = fold["test"]
        lo, hi = t0[test[0]], max(t1[i] for i in test)
        assert not set(test) & set(fold["train"])
        assert all(t1[j] < lo or t0[j] > hi for j in fold["train"])
        assert fold["train"] == sorted(fold["train"])
    plain = research.cv_purged_kfold(t0, t0, k)
    for fold in plain["folds"]:
        assert sorted(fold["test"] + fold["train"]) == list(range(n))


@settings(max_examples=300, deadline=None)
@given(
    st.integers(min_value=1, max_value=3),
    st.integers(min_value=1, max_value=6),
    st.integers(min_value=0, max_value=10**6),
)
def test_viterbi_equals_brute_force(k, t, seed):
    rng = random.Random(seed)

    def simplex() -> list[float]:
        w = [rng.uniform(0.05, 1.0) for _ in range(k)]
        return [x / math.fsum(w) for x in w]

    initial, transition = simplex(), [simplex() for _ in range(k)]
    emission = [[rng.uniform(0.01, 1.0) for _ in range(k)] for _ in range(t)]
    result = research.regime_viterbi(initial, transition, emission)

    def score(path: tuple[int, ...]) -> float:
        s = math.log(initial[path[0]]) + math.log(emission[0][path[0]])
        for u in range(1, t):
            s += math.log(transition[path[u - 1]][path[u]]) + math.log(emission[u][path[u]])
        return s

    best = max(itertools.product(range(k), repeat=t), key=score)
    assert math.isclose(result["log_probability"], score(best), rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(score(tuple(result["states"])), score(best), rel_tol=1e-12, abs_tol=1e-12)


def test_viterbi_ties_take_smallest_index():
    result = research.regime_viterbi([0.5, 0.5], [[0.5, 0.5], [0.5, 0.5]], [[1.0, 1.0], [1.0, 1.0]])
    assert result["states"] == [0, 0]


@SETTINGS
@given(
    st.floats(min_value=0.01, max_value=0.3),
    st.integers(min_value=10, max_value=5000),
    st.integers(min_value=2, max_value=1000),
    st.floats(min_value=1e-4, max_value=0.01),
)
def test_dsr_decreases_in_trials_and_variance(sr, n_obs, n_trials, var):
    base = research.stats_dsr(sr, n_obs, n_trials, var)["dsr"]
    assert research.stats_dsr(sr, n_obs, n_trials + 1, var)["dsr"] <= base
    assert research.stats_dsr(sr, n_obs, n_trials, var * 1.5)["dsr"] <= base


@SETTINGS
@given(st.floats(min_value=-0.5, max_value=0.5), st.integers(min_value=2, max_value=5000))
def test_psr_at_benchmark_is_half(sr, n_obs):
    assert research.stats_psr(sr, n_obs, sr_benchmark=sr)["psr"] == 0.5


@SETTINGS
@given(
    st.integers(min_value=2, max_value=6),
    st.sampled_from([2, 4, 6]),
    st.integers(min_value=0, max_value=10**6),
)
def test_pbo_is_a_probability_and_zero_under_domination(n, s, seed):
    rng = random.Random(seed)
    rows = [[rng.gauss(0, 1) for _ in range(n)] for _ in range(3 * s)]
    pbo = research.stats_pbo(rows, s)["pbo"]
    assert 0.0 <= pbo <= 1.0
    dominated = [[r[0] + 100.0, *r[1:]] for r in rows]
    assert research.stats_pbo(dominated, s, "MEAN")["pbo"] == 0.0
