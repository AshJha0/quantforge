"""Stage J wave 2 property tests (program/STAGE_J_HANDOVER.md, "WAVE 2 READY", property tests):
mean-variance KKT, closed form and bound monotonicity; risk-parity shares; Euler additivity;
Ledoit-Wolf shrinkage range; Black-Litterman forms; Z2 invariances; Baum-Welch EM properties."""

import itertools
import math
import random
import struct
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core.errors import QfError
from quantforge_core.research_w2 import (
    backtest_es_z2,
    contrib_euler,
    estimate_black_litterman,
    estimate_ledoit_wolf,
    portfolio_mean_variance,
    portfolio_risk_parity,
    regime_baum_welch,
)

SETTINGS = settings(max_examples=100, deadline=None)
seeds = st.integers(min_value=0, max_value=10**6)
sizes = st.integers(min_value=1, max_value=6)


def _cov(rng: random.Random, n: int) -> list[list[float]]:
    a = [[rng.gauss(0, 0.2) for _ in range(n)] for _ in range(n)]
    return [
        [sum(a[i][k] * a[j][k] for k in range(n)) + (0.01 if i == j else 0.0) for j in range(n)]
        for i in range(n)
    ]


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            m[r] = [x - f * y for x, y in zip(m[r], m[c], strict=True)]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (m[i][n] - sum(m[i][k] * x[k] for k in range(i + 1, n))) / m[i][i]
    return x


@SETTINGS
@given(seeds, sizes)
def test_mean_variance_kkt_and_monotone_upper_bound(seed, n):
    rng = random.Random(seed)
    sigma, mu, gamma = _cov(rng, n), [rng.gauss(0.05, 0.05) for _ in range(n)], 3.0
    up = [rng.uniform(0.3, 1.0) for _ in range(n)]
    if sum(up) < 1:
        up = [1.0] * n
    r = portfolio_mean_variance(mu, sigma, gamma, [0.0] * n, up)
    w = r["weights"]
    assert abs(sum(w) - 1) < 1e-12
    h = [mu[i] - gamma * sum(sigma[i][j] * w[j] for j in range(n)) for i in range(n)]
    free = [i for i in range(n) if r["at_bound"][i] == 0]
    nu = sum(h[i] for i in free) / len(free) if free else None
    for i in range(n):
        if nu is None:
            break
        g = h[i] - nu
        if r["at_bound"][i] == 0:
            assert abs(g) < 1e-9
        elif r["at_bound"][i] < 0:
            assert g < 1e-9
        else:
            assert g > -1e-9
    binding = [i for i in range(n) if r["at_bound"][i] > 0]
    if binding:
        up2 = list(up)
        up2[binding[0]] += 0.1
        r2 = portfolio_mean_variance(mu, sigma, gamma, [0.0] * n, up2)
        assert r2["objective"] >= r["objective"] - 1e-12


@SETTINGS
@given(seeds, sizes)
def test_mean_variance_wide_bounds_equal_closed_form(seed, n):
    rng = random.Random(seed)
    sigma, mu, gamma = _cov(rng, n), [rng.gauss(0.05, 0.02) for _ in range(n)], 50.0
    r = portfolio_mean_variance(mu, sigma, gamma, [-1e6] * n, [1e6] * n)
    a, e = _solve(sigma, mu), _solve(sigma, [1.0] * n)
    nu = (sum(a) - gamma) / sum(e)
    for wi, ai, ei in zip(r["weights"], a, e, strict=True):
        assert abs(wi - (ai - nu * ei) / gamma) < 1e-8 * max(1.0, abs(wi))


@SETTINGS
@given(seeds, sizes, st.floats(min_value=0.1, max_value=10.0))
def test_risk_parity_shares_equal_budgets_and_scale_invariant(seed, n, c):
    rng = random.Random(seed)
    sigma = _cov(rng, n)
    raw = [rng.uniform(0.1, 1.0) for _ in range(n)]
    b = [x / math.fsum(raw) for x in raw]
    if abs(math.fsum(b) - 1) > 1e-12:
        return
    r = portfolio_risk_parity(sigma, b)
    for ci, bi in zip(r["contributions"], b, strict=True):
        assert abs(ci / r["volatility"] - bi) < 1e-10
    r2 = portfolio_risk_parity([[c * x for x in row] for row in sigma], b)
    for w1, w2 in zip(r["weights"], r2["weights"], strict=True):
        assert abs(w1 - w2) < 1e-10


@SETTINGS
@given(seeds, sizes, st.floats(min_value=0.1, max_value=10.0))
def test_euler_contributions_sum_to_volatility_and_scale(seed, n, c):
    rng = random.Random(seed)
    sigma, w = _cov(rng, n), [rng.gauss(0, 1) for _ in range(n)]
    r = contrib_euler(w, sigma)
    assert abs(math.fsum(r["contributions"]) - r["volatility"]) <= 1e-10 * r["volatility"]
    r2 = contrib_euler([c * x for x in w], sigma)
    for a, b in zip(r["contributions"], r2["contributions"], strict=True):
        assert abs(c * a - b) <= 1e-10 * max(1.0, abs(b))


@SETTINGS
@given(seeds, sizes, st.integers(min_value=2, max_value=30))
def test_ledoit_wolf_shrinkage_in_unit_interval_and_shift_invariant(seed, n, t):
    rng = random.Random(seed)
    x = [[rng.gauss(0, 1) for _ in range(n)] for _ in range(t)]
    r = estimate_ledoit_wolf(x)
    assert 0 <= r["shrinkage"] <= 1
    r2 = estimate_ledoit_wolf([[v + 0.5 for v in row] for row in x])
    assert abs(r["shrinkage"] - r2["shrinkage"]) < 1e-9


@SETTINGS
@given(seeds, sizes, st.integers(min_value=1, max_value=4))
def test_black_litterman_update_equals_precision_form(seed, n, k):
    rng = random.Random(seed)
    sigma, tau = _cov(rng, n), 0.05
    pi = [rng.gauss(0.05, 0.02) for _ in range(n)]
    p = [[rng.gauss(0, 1) for _ in range(n)] for _ in range(k)]
    q = [rng.gauss(0.05, 0.05) for _ in range(k)]
    om = [[(0.01 + rng.random() * 0.01) if a == c else 0.0 for c in range(k)] for a in range(k)]
    r = estimate_black_litterman(sigma, pi, p, q, om, tau)
    # Precision form: [(tau S)^-1 + P' O^-1 P] x = (tau S)^-1 pi + P' O^-1 q.
    ts = [[tau * v for v in row] for row in sigma]
    inv_cols = [_solve(ts, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    prec = [
        [inv_cols[j][i] + sum(p[a][i] * p[a][j] / om[a][a] for a in range(k)) for j in range(n)]
        for i in range(n)
    ]
    rhs = [
        sum(inv_cols[j][i] * pi[j] for j in range(n))
        + sum(p[a][i] * q[a] / om[a][a] for a in range(k))
        for i in range(n)
    ]
    for x, y in zip(r["posterior_returns"], _solve(prec, rhs), strict=True):
        assert abs(x - y) < 1e-10 * max(1.0, abs(y)) or abs(x - y) < 1e-8
    big = estimate_black_litterman(sigma, pi, p, q, [[v * 1e12 for v in row] for row in om], tau)
    for x, y in zip(big["posterior_returns"], pi, strict=True):
        assert abs(x - y) < 1e-9


@SETTINGS
@given(seeds, st.integers(min_value=1, max_value=50), st.floats(min_value=0.01, max_value=100))
def test_z2_no_exceptions_and_scale_invariance(seed, t, c):
    rng = random.Random(seed)
    loss = [rng.gauss(0, 1) for _ in range(t)]
    var = [2.0 + rng.random() for _ in range(t)]
    es = [v + 0.5 for v in var]
    calm = backtest_es_z2([min(x, 1.9) for x in loss], var, es, 0.025)
    assert calm["z2"] == 1.0 and calm["exceptions"] == 0
    r = backtest_es_z2(loss, var, es, 0.1)
    r2 = backtest_es_z2([c * x for x in loss], [c * x for x in var], [c * x for x in es], 0.1)
    assert abs(r["z2"] - r2["z2"]) < 1e-12 * max(1.0, abs(r["z2"]))
    assert r["exceptions"] == r2["exceptions"]


def _hmm_data(rng: random.Random, t: int) -> list[float]:
    s, out = 0, []
    for _ in range(t):
        if rng.random() < 0.1:
            s = 1 - s
        out.append(rng.gauss(-1.0 if s == 0 else 1.5, 0.7 if s == 0 else 1.0))
    return out


def _bytes(r: dict[str, Any]) -> bytes:
    flat = [
        *r["initial"],
        *(x for row in r["transition"] for x in row),
        *r["means"],
        *r["sds"],
        r["log_likelihood"],
    ]
    return struct.pack(f"<{len(flat)}d", *flat)


@settings(max_examples=25, deadline=None)
@given(seeds)
def test_baum_welch_monotone_reproducible_and_permutation_equivariant(seed):
    rng = random.Random(seed)
    y = _hmm_data(rng, 60)
    start = ([0.5, 0.5], [[0.9, 0.1], [0.2, 0.8]], [-0.5, 1.0], [1.0, 1.2])
    lls = []
    for m in range(1, 8):
        try:
            lls.append(
                regime_baum_welch(y, *start, tolerance=1e-300, max_iterations=m)["log_likelihood"]
            )
        except QfError:
            return
    for a, b in itertools.pairwise(lls):
        assert b >= a - 1e-9 * abs(a)
    r1 = regime_baum_welch(y, *start, max_iterations=50)
    assert _bytes(r1) == _bytes(regime_baum_welch(y, *start, max_iterations=50))
    perm = ([0.5, 0.5], [[0.8, 0.2], [0.1, 0.9]], [1.0, -0.5], [1.2, 1.0])
    r2 = regime_baum_welch(y, *perm, max_iterations=50)
    assert r2["iterations"] == r1["iterations"]
    assert abs(r2["means"][0] - r1["means"][1]) < 1e-9 * max(1.0, abs(r1["means"][1]))
    assert abs(r2["transition"][1][0] - r1["transition"][0][1]) < 1e-9


@SETTINGS
@given(seeds, st.integers(min_value=2, max_value=40))
def test_baum_welch_one_state_stops_at_two_with_sample_moments(seed, t):
    rng = random.Random(seed)
    y = [rng.gauss(0, 1) for _ in range(t)]
    r = regime_baum_welch(y, [1.0], [[1.0]], [0.0], [1.0])
    m = sum(y) / t
    assert r["iterations"] == 2 and r["converged"]
    assert abs(r["means"][0] - m) < 1e-12
    assert abs(r["sds"][0] - math.sqrt(sum((v - m) ** 2 for v in y) / t)) < 1e-12


def test_infeasible_bounds_and_indefinite_covariance_are_domain():
    with pytest.raises(QfError) as e:
        portfolio_mean_variance([0.1, 0.1], [[1.0, 2.0], [2.0, 1.0]], 1.0)
    assert e.value.code == "E_DOMAIN"


# --- Rulings J-W2-17 to J-W2-22 (program/WAVE2_*_NOTES.md doubts) -----------------------------


def _limit_code(op: str, raw: dict[str, object]) -> str | None:
    from quantforge_core.cli.limits import check_limits

    try:
        check_limits(op, raw)
    except QfError as e:
        return e.code
    return None


def test_j_w2_17_ragged_matrix_width_counts() -> None:
    cov = [[1.0, 0.0, 0.0], [0.0] * 501, [0.0, 0.0, 1.0]]
    raw = {"expected_returns": [0.1, 0.1, 0.1], "covariance": cov, "risk_aversion": 1.0}
    assert _limit_code("research.portfolio.mean_variance", raw) == "E_LIMIT"
    raw["covariance"] = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    assert _limit_code("research.portfolio.mean_variance", raw) is None


def test_j_w2_18_k_is_the_longest_input() -> None:
    raw = {
        "observations": [0.1, 0.2],
        "initial": [0.5, 0.5],
        "transition": [[0.5, 0.5], [0.5, 0.5]],
        "means": [0.0] * 17,
        "sds": [1.0, 1.0],
    }
    assert _limit_code("research.regime.baum_welch", raw) == "E_LIMIT"
    raw["means"] = [0.0, 1.0]
    raw["transition"] = [[0.5, 0.5], [0.5] * 17]
    assert _limit_code("research.regime.baum_welch", raw) == "E_LIMIT"


def test_j_w2_19_default_budgets_are_not_sum_tested() -> None:
    cov = [[1.0 if i == j else 0.1 for j in range(7)] for i in range(7)]
    r = portfolio_risk_parity(cov)
    assert all(s == pytest.approx(1 / 7, abs=1e-10) for s in r["weights"])


def test_j_w2_20_all_weights_at_bound_start() -> None:
    cov = [[0.04, 0.01, 0.0], [0.01, 0.09, 0.02], [0.0, 0.02, 0.16]]
    r = portfolio_mean_variance([0.3, 0.1, 0.2], cov, 2.0, lower=[0.2, 0.3, 0.5])
    assert r["weights"] == [0.2, 0.3, 0.5]
    assert r["at_bound"] == [-1, -1, -1]


def test_j_w2_21_degenerate_problem_terminates() -> None:
    # Equal means, identity covariance: both weights sit on their upper bound with zero multiplier.
    r = portfolio_mean_variance([0.1, 0.1], [[1.0, 0.0], [0.0, 1.0]], 1.0, upper=[0.5, 0.5])
    assert r["weights"] == [0.5, 0.5]
    # A fixed weight (lower = upper) never leaves the working set.
    r = portfolio_mean_variance(
        [0.1, 0.9, 0.1],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        1.0,
        lower=[0.0, 0.3, 0.0],
        upper=[1.0, 0.3, 1.0],
    )
    assert r["weights"][1] == 0.3 and r["at_bound"][1] == -1


def test_j_w2_22_ledoit_wolf_sizes() -> None:
    assert _limit_code("research.estimate.ledoit_wolf", {"returns": [[0.0] * 501] * 2}) == "E_LIMIT"
    assert (
        _limit_code("research.estimate.ledoit_wolf", {"returns": [[0.0, 0.0], [0.0] * 500]}) is None
    )
    rows = [[0.0]] * 20_001 + [[0.0] * 500]
    assert _limit_code("research.estimate.ledoit_wolf", {"returns": rows}) == "E_LIMIT"
