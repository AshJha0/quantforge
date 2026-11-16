"""Unit tests for quantforge_core.hedge_solvers: every input check (code, message and field),
the helpers the solvers are built from, and hand or independent oracles for the outputs.

The PR mutation gate samples 40 mutants of this module; the full-run survivors of seed 54 showed
that the checks were tested by code only and that several helpers (_cap, _phase_one, _simplex,
_least_margin, the costed orthant search) had no direct test. Expected values here come from
independent reasoning: closed forms worked by hand, numpy/scipy solves of the same problem, or
brute-force enumeration, never from running the code under test."""

import math
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from scipy.optimize import lsq_linear
from scipy.stats import norm

from quantforge_core import hedge_solvers as hs
from quantforge_core.errors import QfError

A2 = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
B2 = [-1.0, -2.0, -2.5]
W2 = [1.0, 1.0, 1.0]


def err(f: Any, *args: Any, **kwargs: Any) -> tuple[str, str, str | None]:
    with pytest.raises(QfError) as caught:
        f(*args, **kwargs)
    e = caught.value
    assert str(e) == e.message
    return e.code, e.message, e.field


# --------------------------------------------------------------------------------------------
# Small helpers


def test_cap_counts_equalities_finite_bounds_and_the_margin_limit() -> None:
    # R6-6.1: 10 (n + p) + 100 with p = equality rows + finite bounds + finite margin limit.
    full = SimpleNamespace(
        e_mat=np.zeros((2, 5)),
        lower=[None, 1.0, None, 0.0],
        upper=[2.0, None, None, None],
        limit=3.0,
    )
    assert hs._cap(4, full) == 10 * (4 + 2 + 3 + 1) + 100
    assert hs._cap(4, SimpleNamespace()) == 10 * 4 + 100
    assert hs._cap(3, SimpleNamespace(limit=math.inf, upper=[1.0])) == 10 * (3 + 1) + 100
    assert hs._cap(3, SimpleNamespace(lower=[-1.0, None])) == 10 * (3 + 1) + 100
    assert hs._cap(2, SimpleNamespace(e_mat=np.zeros((3, 2)))) == 10 * (2 + 3) + 100


def test_z_clears_the_sign_of_zero_only() -> None:
    assert math.copysign(1.0, hs._z(-0.0)) == 1.0
    assert hs._z(-2.5) == -2.5
    assert hs._zs([-0.0, 1.5]) == [0.0, 1.5]
    assert math.copysign(1.0, hs._zs([-0.0])[0]) == 1.0


def test_round_half_away_from_zero() -> None:
    cases = {
        0.5: 1,
        -0.5: -1,
        1.5: 2,
        -1.5: -2,
        2.4999: 2,
        -2.4999: -2,
        2.5: 3,
        -2.5: -3,
        0.0: 0,
        0.49: 0,
        7.0: 7,
        -7.0: -7,
    }
    for v, want in cases.items():
        got = hs._round_half_away(v)
        assert got == want and isinstance(got, int), v


def test_symmetric_check_uses_a_relative_threshold() -> None:
    hs._symmetric([], "s")  # nothing to compare
    hs._symmetric([[0.0, 0.0], [0.0, 0.0]], "s")  # zero difference against a zero scale
    hs._symmetric([[1e6, 1.0], [1.0 + 1e-9, 1.0]], "s")  # 1e-9 <= 1e-12 * 1e6
    assert err(hs._symmetric, [[1.0, 1.0], [1.0 + 1e-9, 1.0]], "covariance") == (
        "E_INPUT",
        "covariance is not symmetric",
        "covariance",
    )
    assert err(hs._symmetric, [[1.0, 0.0, 0.5], [0.0, 1.0, 0.0], [0.4, 0.0, 1.0]], "s")[2] == "s"


def test_sample_covariance_divisor_and_constant_series() -> None:
    x = [1.0, 2.0, 4.0, 7.0]
    y = [0.0, 1.0, 1.0, 2.0]
    mx, my = 3.5, 1.0
    vxx = sum((v - mx) ** 2 for v in x) / 3
    vxy = sum((p - mx) * (q - my) for p, q in zip(x, y)) / 3
    vyy = sum((q - my) ** 2 for q in y) / 3
    assert hs._sample_covariance([x, y]) == [[vxx, vxy], [vxy, vyy]]
    assert vxx == 7.0 and vxy == 2.0 and vyy == pytest.approx(2.0 / 3.0, rel=1e-15)
    # Ruling J-I.4: a constant series has variance exactly 0, also where fsum / count rounds.
    c = [0.1] * 3
    assert math.fsum(c) / 3 != 0.1  # the rounding the rule guards against
    out = hs._sample_covariance([c, [1.0, 2.0, 3.0]])
    assert out[0] == [0.0, 0.0]


def bs_greeks(
    s: float, r: float, q: float, v: float, kind: str, k: float, t: float
) -> tuple[float, ...]:
    """Black-Scholes-Merton delta, gamma, vega per unit vol, from scipy's normal distribution."""
    d1 = (math.log(s / k) + (r - q + 0.5 * v * v) * t) / (v * math.sqrt(t))
    disc = math.exp(-q * t)
    delta = disc * norm.cdf(d1) if kind == "CALL" else -disc * norm.cdf(-d1)
    return (
        delta,
        disc * norm.pdf(d1) / (s * v * math.sqrt(t)),
        s * disc * norm.pdf(d1) * math.sqrt(t),
    )


def test_unit_greeks_match_black_scholes() -> None:
    for kind in ("CALL", "PUT"):
        for k, t in ((90.0, 0.5), (110.0, 2.0)):
            got = hs._unit_greeks(100.0, 0.03, 0.01, 0.25, kind, k, t)
            want = bs_greeks(100.0, 0.03, 0.01, 0.25, kind, k, t)
            assert got == pytest.approx(want, rel=1e-12, abs=1e-15)
    for args in (
        ("UNDERLYING", None, None),
        ("UNDERLYING", 100.0, 1.0),
        ("CALL", 100.0, None),
        ("PUT", None, 1.0),
    ):
        out = hs._unit_greeks(100.0, 0.03, 0.01, 0.25, *args)
        assert out == (1.0, 0.0, 0.0) and all(isinstance(v, float) for v in out)


def test_costs_given_kinked_and_cost() -> None:
    assert not hs.Costs().given()
    assert hs.Costs(cost_weight=2.0).given()
    assert not hs.Costs(cost_weight=1.0).given()
    for kw in (
        {"half_spreads": [0.0]},
        {"impact": [0.0]},
        {"margin_rates": [0.0]},
        {"margin_limit": 0.0},
    ):
        assert hs.Costs(**kw).given(), kw
    assert hs.Costs(half_spreads=[0.1], cost_weight=1.0).kinked()
    assert not hs.Costs(half_spreads=[0.1], cost_weight=0.0).kinked()
    assert not hs.Costs(half_spreads=[0.0, 0.0]).kinked()
    assert not hs.Costs(impact=[1.0]).kinked()
    assert hs.Costs(margin_rates=[0.0], margin_limit=1.0).kinked()
    assert (
        hs.Costs(half_spreads=[0.5, 0.25], impact=[2.0, 0.0]).cost([-2.0, 4.0])
        == 0.5 * 2 + 2 * 4 + 1.0
    )
    assert hs.Costs(impact=[1.0, 3.0]).cost([2.0, -1.0]) == 4.0 + 3.0
    assert hs.Costs(half_spreads=[1.0, 2.0]).cost([-1.0, 3.0]) == 7.0


def test_equality_split_particular_point_and_null_space() -> None:
    e = np.array([[1.0, 1.0, 0.0]])
    x_p, z = hs._equality_split(e, np.array([2.0]), 0.0)
    assert x_p == pytest.approx([1.0, 1.0, 0.0], abs=1e-15)
    assert z.shape == (3, 2)
    assert np.abs(e @ z).max() < 1e-15 and np.allclose(z.T @ z, np.eye(2), atol=1e-15)
    # No rows, or no columns: x_p = 0 and Z = I.
    x0, z0 = hs._equality_split(np.zeros((0, 2)), np.zeros(0), 0.0)
    assert x0.tolist() == [0.0, 0.0] and z0.tolist() == [[1.0, 0.0], [0.0, 1.0]]
    x1, z1 = hs._equality_split(np.zeros((1, 0)), np.array([0.0]), 0.0)
    assert x1.shape == (0,) and z1.shape == (0, 0)
    # A singular value equal to the cut counts as zero: the row drops out.
    xc, zc = hs._equality_split(np.array([[2.0, 0.0]]), np.array([4.0]), 2.0)
    assert xc.tolist() == [0.0, 0.0] and zc.shape == (2, 2)


def test_lstsq_min_norm_cut_is_strict() -> None:
    y, rank = hs._lstsq_min_norm(np.zeros((2, 0)), np.ones(2), 0.0)
    assert y.shape == (0,) and rank == 0
    m = np.array([[2.0, 0.0], [0.0, 1.0]])
    y, rank = hs._lstsq_min_norm(m, np.array([4.0, 3.0]), 0.0)
    assert rank == 2 and y == pytest.approx([-2.0, -3.0], abs=1e-15)
    y, rank = hs._lstsq_min_norm(m, np.array([4.0, 3.0]), 1.0)  # s^2 = 1 is at the cut: dropped
    assert rank == 1 and y == pytest.approx([-2.0, 0.0], abs=1e-15)


# --------------------------------------------------------------------------------------------
# Input checks: code, message and field of every error


def test_shape_checks() -> None:
    f = hs.qp_solve
    msg_a = ("E_INPUT", "a must be a non-empty matrix with rows of one length", "a")
    assert err(f, [], [], []) == msg_a
    assert err(f, [[]], [1.0], [1.0]) == msg_a
    assert err(f, [[1.0, 2.0], [1.0]], [1.0, 1.0], [1.0, 1.0]) == msg_a
    assert err(f, [[1.0]], [1.0, 2.0], [1.0]) == (
        "E_INPUT",
        "b must have one entry per row of a",
        "b",
    )
    assert err(f, [[1.0]], [1.0], [1.0, 1.0]) == (
        "E_INPUT",
        "weights must have one entry per row of a",
        "weights",
    )
    assert hs._shape([[1.0, 2.0, 3.0]], [1.0], [1.0]) == (1, 3)


def test_weight_and_ridge_checks() -> None:
    assert err(hs.qp_solve, A2, B2, [1.0, 0.0, 1.0]) == (
        "E_DOMAIN",
        "weights must be positive",
        "weights",
    )
    assert err(hs.qp_solve, A2, B2, W2, ridge=-1e-300) == (
        "E_DOMAIN",
        "ridge must not be negative",
        "ridge",
    )
    hs.qp_solve(A2, B2, W2, ridge=0.0)


def test_qp_input_checks_in_order() -> None:
    f = hs.qp_solve
    assert err(f, A2, B2, W2, eq_matrix=[[1.0, 1.0]]) == (
        "E_INPUT",
        "eq_matrix and eq_rhs go together",
        "eq_matrix",
    )
    assert err(f, A2, B2, W2, eq_rhs=[1.0]) == (
        "E_INPUT",
        "eq_matrix and eq_rhs go together",
        "eq_matrix",
    )
    assert err(f, A2, B2, W2, eq_matrix=[], eq_rhs=[]) == (
        "E_INPUT",
        "an empty eq_matrix: leave out both keys",
        "eq_matrix",
    )
    assert err(f, A2, B2, W2, eq_matrix=[[1.0]], eq_rhs=[1.0]) == (
        "E_INPUT",
        "eq_matrix rows must have one entry per instrument",
        "eq_matrix",
    )
    assert err(f, A2, B2, W2, eq_matrix=[[1.0, 1.0]], eq_rhs=[1.0, 2.0]) == (
        "E_INPUT",
        "eq_rhs must have one entry per row of eq_matrix",
        "eq_rhs",
    )
    assert err(f, A2, B2, W2, lower=[0.0]) == (
        "E_INPUT",
        "lower must have one entry per instrument",
        "lower",
    )
    assert err(f, A2, B2, W2, upper=[0.0, 1.0, 2.0]) == (
        "E_INPUT",
        "upper must have one entry per instrument",
        "upper",
    )
    assert err(f, A2, B2, W2, upper=[None, 1.0], singular="MIN_NORM") == (
        "E_INPUT",
        "MIN_NORM takes no bounds (ruling I-5)",
        "singular",
    )
    assert err(f, A2, B2, W2, lower=[0.0, None], singular="MIN_NORM") == (
        "E_INPUT",
        "MIN_NORM takes no bounds (ruling I-5)",
        "singular",
    )
    f(A2, B2, W2, lower=[None, None], upper=[None, None], singular="MIN_NORM")
    assert err(f, A2, B2, W2, lower=[0.0, 2.0], upper=[1.0, 1.0]) == (
        "E_DOMAIN",
        "a lower bound is above its upper bound",
        "lower",
    )
    pinned = f(A2, B2, W2, lower=[0.5, None], upper=[0.5, None])
    assert pinned["x"][0] == 0.5
    # Shape errors come before domain errors.
    assert err(f, A2, B2, [1.0, -1.0, 1.0], lower=[0.0]) == (
        "E_INPUT",
        "lower must have one entry per instrument",
        "lower",
    )


def test_qp_equality_rank_checks() -> None:
    f = hs.qp_solve
    assert err(f, [[1.0]], [1.0], [1.0], eq_matrix=[[1.0], [2.0]], eq_rhs=[1.0, 2.0]) == (
        "E_SINGULAR",
        "more equalities than instruments",
        "eq_matrix",
    )
    assert err(f, A2, B2, W2, eq_matrix=[[1.0, 2.0], [2.0, 4.0]], eq_rhs=[1.0, 2.0]) == (
        "E_SINGULAR",
        "the equality rows are dependent",
        "eq_matrix",
    )
    assert err(f, [[1.0, 1.0]], [1.0], [1.0]) == (
        "E_SINGULAR",
        "the hedge has no unique solution",
        "a",
    )
    # k == n: the equalities alone fix x; nothing is left to the objective.
    out = f(A2, B2, W2, eq_matrix=[[1.0, 0.0], [0.0, 1.0]], eq_rhs=[3.0, -1.0])
    assert out["x"] == [3.0, -1.0] and out["rank"] == 0


def test_costs_checks() -> None:
    f = hs.qp_solve
    for key in ("half_spreads", "impact", "margin_rates"):
        kw: dict[str, Any] = {key: [0.0]}
        if key == "margin_rates":
            kw["margin_limit"] = 1.0
        assert err(f, A2, B2, W2, **kw) == (
            "E_INPUT",
            f"{key} must have one entry per instrument",
            key,
        )
    assert err(f, A2, B2, W2, margin_rates=[1.0, 1.0]) == (
        "E_INPUT",
        "margin_rates and margin_limit go together",
        "margin_rates",
    )
    assert err(f, A2, B2, W2, margin_limit=1.0) == (
        "E_INPUT",
        "margin_rates and margin_limit go together",
        "margin_rates",
    )
    assert err(f, A2, B2, W2, impact=[1.0, 1.0], singular="MIN_NORM") == (
        "E_INPUT",
        "MIN_NORM takes no cost or margin input",
        "singular",
    )
    for key in ("half_spreads", "impact", "margin_rates"):
        kw = {key: [0.0, -1e-300]}
        if key == "margin_rates":
            kw["margin_limit"] = 1.0
        assert err(f, A2, B2, W2, **kw) == ("E_DOMAIN", f"{key} must not be negative", key)
    assert err(f, A2, B2, W2, cost_weight=-1e-300) == (
        "E_DOMAIN",
        "cost_weight must not be negative",
        "cost_weight",
    )
    assert err(f, A2, B2, W2, margin_rates=[1.0, 1.0], margin_limit=-1e-300) == (
        "E_DOMAIN",
        "margin_limit must not be negative",
        "margin_limit",
    )
    out = f(
        A2,
        B2,
        W2,
        half_spreads=[0.0, 0.0],
        impact=[0.0, 0.0],
        cost_weight=0.0,
        margin_rates=[0.0, 0.0],
        margin_limit=0.0,
    )
    assert out["cost"] == 0.0 and out["margin"] == 0.0


def test_frontier_checks() -> None:
    f = hs.frontier_solve
    assert err(f, A2, B2, W2, [1.0], half_spreads=[0.1, 0.1], cost_weight=1.0) == (
        "E_INPUT",
        "give cost_weights, not cost_weight",
        "cost_weight",
    )
    msg = ("E_INPUT", "cost_weights must be non-empty and increasing", "cost_weights")
    assert err(f, A2, B2, W2, [], half_spreads=[0.1, 0.1]) == msg
    assert err(f, A2, B2, W2, [1.0, 1.0], half_spreads=[0.1, 0.1]) == msg
    assert err(f, A2, B2, W2, [0.0, 2.0, 1.0], half_spreads=[0.1, 0.1]) == msg
    assert err(f, A2, B2, W2, [1.0]) == (
        "E_INPUT",
        "a frontier needs half_spreads or impact",
        "half_spreads",
    )
    f(A2, B2, W2, [1.0], impact=[0.1, 0.1])


def test_integer_checks() -> None:
    f = hs.integer_solve
    assert err(f, A2, B2, W2, [1.0]) == (
        "E_INPUT",
        "lot_sizes must have one entry per instrument",
        "lot_sizes",
    )
    assert err(f, A2, B2, W2, [1.0, 1.0], lower_lots=[0]) == (
        "E_INPUT",
        "lower_lots must have one entry per instrument",
        "lower_lots",
    )
    assert err(f, A2, B2, W2, [1.0, 1.0], upper_lots=[0, 1, 2]) == (
        "E_INPUT",
        "upper_lots must have one entry per instrument",
        "upper_lots",
    )
    assert err(f, A2, B2, [0.0, 1.0, 1.0], [1.0, 1.0]) == (
        "E_DOMAIN",
        "weights must be positive",
        "weights",
    )
    assert err(f, A2, B2, W2, [1.0, 0.0]) == ("E_DOMAIN", "lot sizes must be positive", "lot_sizes")
    assert err(f, A2, B2, W2, [1.0, 1.0], lower_lots=[0, 3], upper_lots=[1, 2]) == (
        "E_DOMAIN",
        "a lower lot bound is above its upper bound",
        "lower_lots",
    )
    pinned = f(A2, B2, W2, [1.0, 1.0], lower_lots=[2, None], upper_lots=[2, None])
    assert pinned["lots"][0] == 2
    assert err(f, [[1.0, 2.0], [2.0, 4.0]], [1.0, 1.0], [1.0, 1.0], [1.0, 1.0]) == (
        "E_SINGULAR",
        "the hedge in lot units has no unique solution",
        "a",
    )
    assert err(f, [[1.0]], [-(2.0**53)], [1.0], [1.0]) == (
        "E_LIMIT",
        "a lot count is beyond 2^52 (ruling I-49)",
        "lot_sizes",
    )
    # The limit is on the lot count x / lot_size, not on x: x = 2^53 in lots of 4 is 2^51 lots.
    out = f([[1.0]], [-(2.0**53)], [1.0], [4.0])
    assert out["lots"] == [2**51]


def test_minvar_checks() -> None:
    f = hs.minvar_ratio
    both = ("E_INPUT", "give either covariance or the two series", "covariance")
    assert err(f) == both
    assert err(f, [[1.0, 0.0], [0.0, 1.0]], [1.0, 2.0, 3.0]) == both
    assert err(f, [[1.0, 0.0], [0.0, 1.0]], None, [[1.0, 2.0, 3.0]]) == both
    assert err(f, None, [1.0, 2.0, 3.0]) == (
        "E_INPUT",
        "exposure_changes and hedge_changes go together",
        "hedge_changes",
    )
    assert err(f, None, None, [[1.0, 2.0, 3.0]]) == (
        "E_INPUT",
        "exposure_changes and hedge_changes go together",
        "hedge_changes",
    )
    assert err(f, None, [1.0, 2.0, 3.0], []) == (
        "E_INPUT",
        "at least one hedge series is needed",
        "hedge_changes",
    )
    assert err(f, None, [1.0, 2.0, 3.0], [[1.0, 2.0, 3.0], [1.0, 2.0]]) == (
        "E_INPUT",
        "the series differ in length",
        "hedge_changes",
    )
    assert err(f, None, [1.0, 2.0, 4.0], [[1.0, 3.0, 2.0], [0.0, 1.0, 5.0]]) == (
        "E_INPUT",
        "at least k + 2 observations are needed",
        "exposure_changes",
    )
    f(None, [1.0, 2.0, 4.0, 3.0], [[1.0, 3.0, 2.0, 5.0], [0.0, 1.0, 5.0, 2.0]])  # T = k + 2
    sq = ("E_INPUT", "covariance must be square and at least 2 x 2", "covariance")
    assert err(f, [[1.0]]) == sq
    assert err(f, [[1.0, 0.0], [0.0]]) == sq
    assert err(f, [[1.0, 0.5], [0.4, 1.0]]) == (
        "E_INPUT",
        "covariance is not symmetric",
        "covariance",
    )
    assert err(f, [[0.0, 0.0], [0.0, 1.0]]) == (
        "E_DOMAIN",
        "the position has no variance to hedge",
        "covariance",
    )
    assert err(f, [[1.0, 0.0], [0.0, -1.0]]) == (
        "E_NOT_POSITIVE_DEFINITE",
        "a hedge variance is negative",
        "covariance",
    )
    assert err(f, [[1.0, 0.0], [0.0, 0.0]]) == (
        "E_SINGULAR",
        "the hedge instruments are dependent",
        "covariance",
    )
    assert err(f, [[1.0, 0.0, 0.0], [0.0, 1.0, 2.0], [0.0, 2.0, 1.0]]) == (
        "E_NOT_POSITIVE_DEFINITE",
        "the hedge covariance is indefinite",
        "covariance",
    )
    assert err(f, [[1.0, 0.0, 0.0], [0.0, 1.0, 1.0], [0.0, 1.0, 1.0]]) == (
        "E_SINGULAR",
        "the hedge instruments are dependent",
        "covariance",
    )
    assert err(f, [[1.0, 2.0], [2.0, 1.0]]) == (
        "E_NOT_POSITIVE_DEFINITE",
        "the hedged variance is negative",
        "covariance",
    )


def test_minvar_singularity_is_judged_on_the_correlation_form() -> None:
    # Hedge variances of 1e-8 (a 1e-4 daily vol) are not small once scaled to correlations.
    tiny = [[1.0, 2e-5, 0.0], [2e-5, 1e-8, 0.0], [0.0, 0.0, 1e-8]]
    out = hs.minvar_ratio(tiny)
    assert out["hedge"] == pytest.approx([-2000.0, 0.0], rel=1e-12)
    assert out["variance_after"] == pytest.approx(1.0 - 2e-5 * 2000.0, rel=1e-9, abs=1e-12)
    # 1 - rho^2 = 5e-13 is below the 1e-12 pivot rule: the two hedges are dependent.
    rho = math.sqrt(1.0 - 5e-13)
    near = [[1.0, 0.5, 0.5], [0.5, 1.0, rho], [0.5, rho, 1.0]]
    assert err(hs.minvar_ratio, near)[0] == "E_SINGULAR"
    rho = math.sqrt(1.0 - 4e-12)
    ok = [[1.0, 0.5, 0.5], [0.5, 1.0, rho], [0.5, rho, 1.0]]
    assert len(hs.minvar_ratio(ok)["hedge"]) == 2


def test_minvar_three_hedges_against_a_direct_solve() -> None:
    s = np.array(
        [
            [4.0, 1.2, -0.8, 0.6],
            [1.2, 2.0, 0.3, -0.4],
            [-0.8, 0.3, 1.5, 0.2],
            [0.6, -0.4, 0.2, 0.9],
        ]
    )
    out = hs.minvar_ratio(s.tolist())
    want = -np.linalg.solve(s[1:, 1:], s[1:, 0])
    assert out["hedge"] == pytest.approx(want.tolist(), rel=1e-13)
    after = 4.0 + float(s[1:, 0] @ want)
    assert out["variance_before"] == 4.0
    assert out["variance_after"] == pytest.approx(after, rel=1e-12)
    assert out["effectiveness"] == pytest.approx(1 - after / 4.0, rel=1e-12)


def test_minvar_rounding_below_zero_is_clamped_relative_to_the_position() -> None:
    # after = 1e6 - (1000 + d)^2 is about -9e-10: a rounding-sized miss next to 1e6 (I-44).
    he = 1000.0 + 4.5e-13
    out = hs.minvar_ratio([[1e6, he], [he, 1.0]])
    assert 1e6 - he * he < 0
    assert out["variance_after"] == 0.0 and out["effectiveness"] == 1.0


def test_greeks_checks() -> None:
    f = hs.greeks_neutralise
    book = [("CALL", 100.0, 1.0, 10.0)]
    hedges = [("UNDERLYING", None, None)]
    m = (100.0, 0.03, 0.0, 0.2)
    assert err(f, *m, book, hedges, ["DELTA"], ["foo", "bar"]) == (
        "E_INPUT",
        "foo is not a key of a Greek instrument (I-41)",
        "foo",
    )
    assert err(
        f, *m, [("CALL", 100.0, 1.0, 1.0), ("CALL", 100.0, 1.0, None)], hedges, ["DELTA"]
    ) == ("E_INPUT", "a portfolio position needs a quantity (ruling I-41)", "quantity")
    und = ("E_INPUT", "the underlying has no strike or expiry", "portfolio")
    assert err(f, *m, book, [("UNDERLYING", 1.0, None)], ["DELTA"]) == und
    assert err(f, *m, book, [("UNDERLYING", None, 1.0)], ["DELTA"]) == und
    opt = ("E_INPUT", "an option needs a strike and an expiry", "portfolio")
    assert err(f, *m, book, [("CALL", None, 1.0)], ["DELTA"]) == opt
    assert err(f, *m, [("PUT", 100.0, None, 1.0)], hedges, ["DELTA"]) == opt
    assert err(f, *m, book, [], []) == ("E_INPUT", "no hedge instruments", "hedges")
    assert err(f, *m, book, hedges, ["DELTA", "GAMMA"]) == (
        "E_INPUT",
        "one target per hedge instrument (ruling I-9)",
        "targets",
    )
    assert err(f, *m, book, [*hedges, ("CALL", 90.0, 1.0)], ["DELTA", "DELTA"]) == (
        "E_INPUT",
        "a target is repeated",
        "targets",
    )
    assert err(f, 0.0, 0.03, 0.0, 0.2, book, hedges, ["DELTA"]) == (
        "E_DOMAIN",
        "spot must be positive",
        "spot",
    )
    assert err(f, 100.0, 0.03, 0.0, 0.0, book, hedges, ["DELTA"]) == (
        "E_DOMAIN",
        "volatility must be positive",
        "volatility",
    )
    assert err(f, *m, [("CALL", 0.0, 1.0, 1.0)], hedges, ["DELTA"]) == (
        "E_DOMAIN",
        "strikes must be positive",
        "strike",
    )
    assert err(f, *m, book, [("PUT", 100.0, 0.0)], ["DELTA"]) == (
        "E_DOMAIN",
        "expiries must be positive",
        "expiry_years",
    )
    assert err(
        f, *m, book, [("UNDERLYING", None, None), ("UNDERLYING", None, None)], ["DELTA", "GAMMA"]
    ) == ("E_SINGULAR", "the hedges cannot set the targets independently", "hedges")
    # Small but positive inputs are accepted.
    f(0.5, 0.03, 0.0, 0.2, [("UNDERLYING", None, None, 1.0)], hedges, ["DELTA"])


def greeks_oracle(m: tuple[float, ...], kind: str, k: Any, t: Any) -> tuple[float, ...]:
    s, r, q, v = m
    return (1.0, 0.0, 0.0) if kind == "UNDERLYING" else bs_greeks(s, r, q, v, kind, k, t)


def test_greeks_neutralise_against_a_direct_solve() -> None:
    m = (100.0, 0.04, 0.015, 0.3)
    book = [
        ("CALL", 105.0, 0.75, 120.0),
        ("PUT", 95.0, 1.5, -40.0),
        ("UNDERLYING", None, None, 25.0),
        ("CALL", 80.0, 0.25, 0.0),
    ]
    hedges = [("UNDERLYING", None, None), ("CALL", 100.0, 0.5), ("PUT", 90.0, 2.0)]
    targets = ["GAMMA", "DELTA", "VEGA"]
    out = hs.greeks_neutralise(*m, book, hedges, targets)
    before = [sum(q * greeks_oracle(m, kd, k, t)[c] for kd, k, t, q in book) for c in range(3)]
    per = [greeks_oracle(m, *h) for h in hedges]
    order = [1, 0, 2]
    g = np.array([[per[j][c] for j in range(3)] for c in order])
    q = np.linalg.solve(g, -np.array([before[c] for c in order]))
    assert out["quantities"] == pytest.approx(q.tolist(), rel=1e-10)
    assert list(out["greeks_before"]) == ["delta", "gamma", "vega"]
    assert [out["greeks_before"][k] for k in ("delta", "gamma", "vega")] == pytest.approx(
        before, rel=1e-12
    )
    assert all(abs(v) < 1e-9 for v in out["greeks_after"].values())
    # Only two targets: vega is left as it falls.
    out2 = hs.greeks_neutralise(*m, book, hedges[:2], ["DELTA", "GAMMA"])
    g2 = np.array([[per[j][c] for j in range(2)] for c in (0, 1)])
    q2 = np.linalg.solve(g2, -np.array(before[:2]))
    assert out2["quantities"] == pytest.approx(q2.tolist(), rel=1e-10)
    vega_after = before[2] + sum(q2[j] * per[j][2] for j in range(2))
    assert out2["greeks_after"]["vega"] == pytest.approx(vega_after, rel=1e-10)
    assert out2["greeks_after"]["gamma"] == pytest.approx(0.0, abs=1e-12)


def test_greeks_singularity_is_relative() -> None:
    # Two hedges whose gamma/vega columns are exactly proportional are singular for (GAMMA, VEGA).
    m = (100.0, 0.0, 0.0, 0.2)
    book = [("CALL", 100.0, 1.0, 1.0)]
    same = [("CALL", 100.0, 1.0), ("CALL", 100.0, 1.0)]
    assert err(hs.greeks_neutralise, *m, book, same, ["GAMMA", "VEGA"])[0] == "E_SINGULAR"
    # Large but well-conditioned: an underlying and an option scaled up stay solvable.
    out = hs.greeks_neutralise(
        1e4,
        0.0,
        0.0,
        0.2,
        [("CALL", 1e4, 1.0, 1.0)],
        [("UNDERLYING", None, None), ("CALL", 9e3, 1.0)],
        ["DELTA", "GAMMA"],
    )
    assert len(out["quantities"]) == 2


def test_beta_futures_checks_and_values() -> None:
    f = hs.beta_futures
    assert err(f, 0.0, 1.0, 0.5, 100.0, 50.0) == (
        "E_DOMAIN",
        "portfolio_value must be positive",
        "portfolio_value",
    )
    assert err(f, 1e6, 1.0, 0.5, 0.0, 50.0) == (
        "E_DOMAIN",
        "futures_price must be positive",
        "futures_price",
    )
    assert err(f, 1e6, 1.0, 0.5, 100.0, 0.0) == (
        "E_DOMAIN",
        "multiplier must be positive",
        "multiplier",
    )
    # (0.5 - 1.2) * 1e6 / (4000 * 50) = -3.5 -> -4 held (half away from zero).
    out = f(1e6, 1.2, 0.5, 4000.0, 50.0)
    assert out == {
        "contracts": -3.5,
        "contracts_held": -4.0,
        "beta_after": 1.2 - 4 * 4000 * 50 / 1e6,
    }
    exact = f(1e6, 1.2, 0.5, 4000.0, 50.0, rounding="NONE")
    assert exact["contracts_held"] == -3.5 and exact["beta_after"] == pytest.approx(0.5, rel=1e-15)
    small = f(0.5, 1.0, 1.0, 0.5, 0.5)
    assert small["contracts"] == 0.0 and math.copysign(1.0, small["contracts"]) == 1.0


def test_residual_report_checks() -> None:
    f = hs.residual_report
    cov = [[1.0, 0.0], [0.0, 1.0]]
    msg_a = ("E_INPUT", "a must be a non-empty matrix with rows of one length", "a")
    assert err(f, [], [], [], []) == msg_a
    assert err(f, [[], []], [1.0, 1.0], [], cov) == msg_a
    assert err(f, [[1.0], [1.0, 2.0]], [1.0, 1.0], [1.0], cov) == msg_a
    assert err(f, [[1.0], [1.0]], [1.0], [1.0], cov) == (
        "E_INPUT",
        "b must have one entry per row of a",
        "b",
    )
    assert err(f, [[1.0], [1.0]], [1.0, 1.0], [1.0, 2.0], cov) == (
        "E_INPUT",
        "x must have one entry per column of a",
        "x",
    )
    mm = ("E_INPUT", "covariance must be m x m", "covariance")
    assert err(f, [[1.0], [1.0]], [1.0, 1.0], [1.0], [[1.0, 0.0]]) == mm
    assert err(f, [[1.0], [1.0]], [1.0, 1.0], [1.0], [[1.0, 0.0], [0.0]]) == mm
    assert err(f, [[1.0], [1.0]], [1.0, 1.0], [1.0], [[1.0, 0.1], [0.2, 1.0]]) == (
        "E_INPUT",
        "covariance is not symmetric",
        "covariance",
    )
    assert err(f, [[1.0], [1.0]], [1.0, 1.0], [1.0], [[1.0, 0.0], [0.0, -1e-6]]) == (
        "E_NOT_POSITIVE_DEFINITE",
        "the covariance has a negative eigenvalue",
        "covariance",
    )
    assert err(f, [[1.0], [1.0]], [0.0, 0.0], [1.0], cov) == (
        "E_DOMAIN",
        "nothing to hedge: b^T S b is not positive",
        "b",
    )
    # A PSD covariance with a zero eigenvalue is accepted; a rounding-sized negative one too.
    f([[1.0], [1.0]], [1.0, 0.0], [0.5], [[1.0, 1.0], [1.0, 1.0]])
    f([[1.0], [1.0]], [1.0, 0.0], [0.5], [[1e6, 0.0], [0.0, -1e-7]])


def test_residual_report_values() -> None:
    a = [[1.0, 0.5], [0.2, 1.0], [0.0, 0.3]]
    b = [-1.0, 2.0, 0.5]
    x = [0.4, -1.5]
    cov = np.array([[2.0, 0.3, 0.1], [0.3, 1.0, -0.2], [0.1, -0.2, 0.5]])
    out = hs.residual_report(a, b, x, cov.tolist())
    r = np.array(a) @ np.array(x) + np.array(b)
    after = float(r @ cov @ r)
    before = float(np.array(b) @ cov @ np.array(b))
    assert out["residual"] == pytest.approx(r.tolist(), rel=1e-15)
    assert out["variance_before"] == pytest.approx(before, rel=1e-14)
    assert out["variance_after"] == pytest.approx(after, rel=1e-14)
    assert out["volatility_after"] == pytest.approx(math.sqrt(after), rel=1e-14)
    assert out["effectiveness"] == pytest.approx(1 - after / before, rel=1e-13)
    assert out["contributions"] == pytest.approx((r * (cov @ r)).tolist(), rel=1e-13)
    assert sum(out["contributions"]) == pytest.approx(after, rel=1e-13)


def test_select_checks() -> None:
    f = hs.select_solve
    assert err(f, A2, B2, W2, 1, lower=[0.0]) == (
        "E_INPUT",
        "lower must have one entry per instrument",
        "lower",
    )
    assert err(f, A2, B2, W2, 1, upper=[0.0]) == (
        "E_INPUT",
        "upper must have one entry per instrument",
        "upper",
    )
    assert err(f, A2, B2, [1.0, 1.0, 0.0], 1) == ("E_DOMAIN", "weights must be positive", "weights")
    assert err(f, A2, B2, W2, 1, lower=[0.0, 1.0], upper=[1.0, 0.5]) == (
        "E_DOMAIN",
        "a lower bound is above its upper bound",
        "lower",
    )
    mx = ("E_INPUT", "max_instruments must be between 1 and n", "max_instruments")
    assert err(f, A2, B2, W2, 0) == mx
    assert err(f, A2, B2, W2, 3) == mx
    assert err(f, A2, B2, W2, 1, extra_inputs=["eq_matrix", "impact"]) == (
        "E_INPUT",
        "selection takes no eq_matrix (ruling I-33)",
        "eq_matrix",
    )
    adm = ("E_DOMAIN", "every bound must admit 0 (ruling I-33)", "lower")
    assert err(f, A2, B2, W2, 1, lower=[0.1, None]) == adm
    assert err(f, A2, B2, W2, 1, upper=[None, -0.1]) == adm
    f(A2, B2, W2, 1, lower=[0.0, 0.0], upper=[0.0, 0.0])
    assert err(f, [[1.0, 2.0], [2.0, 4.0]], [1.0, 1.0], [1.0, 1.0], 1) == (
        "E_SINGULAR",
        "the full hedge has no unique solution",
        "a",
    )


def test_option_hedge_lots_checks() -> None:
    f = hs.option_hedge_lots
    m = (100.0, 0.03, 0.0, 0.2)
    book = [("UNDERLYING", None, None, 1000.0)]
    und = [("UNDERLYING", None, None, 100.0, 0.01)]
    assert err(f, *m, book, und, ["DELTA"], 5, ["lot", "x"]) == (
        "E_INPUT",
        "lot is not a key of a Greek instrument (I-41)",
        "lot",
    )
    assert err(f, *m, book, [], ["DELTA"], 5) == ("E_INPUT", "no hedge instruments", "hedges")
    tg = ("E_INPUT", "targets must be a non-empty set", "targets")
    assert err(f, *m, book, und, [], 5) == tg
    assert err(f, *m, book, und, ["DELTA", "GAMMA", "DELTA"], 5) == tg
    assert err(
        f, *m, [("UNDERLYING", None, None, 1.0), ("CALL", 100.0, 1.0, None)], und, ["DELTA"], 5
    ) == ("E_INPUT", "a portfolio position needs a quantity (ruling I-41)", "quantity")
    u = ("E_INPUT", "the underlying has no strike or expiry", "portfolio")
    assert err(f, *m, book, [("UNDERLYING", 1.0, None, 1.0, 0.0)], ["DELTA"], 5) == u
    assert err(f, *m, [("UNDERLYING", None, 1.0, 1.0)], und, ["DELTA"], 5) == u
    o = ("E_INPUT", "an option needs a strike and an expiry", "portfolio")
    assert err(f, *m, book, [("CALL", None, 1.0, 1.0, 0.0)], ["DELTA"], 5) == o
    assert err(f, *m, [("PUT", 100.0, None, 1.0)], und, ["DELTA"], 5) == o
    assert err(f, 0.0, 0.03, 0.0, 0.2, book, und, ["DELTA"], 5) == (
        "E_DOMAIN",
        "spot must be positive",
        "spot",
    )
    assert err(f, 100.0, 0.03, 0.0, 0.0, book, und, ["DELTA"], 5) == (
        "E_DOMAIN",
        "volatility must be positive",
        "volatility",
    )
    assert err(f, *m, book, [("CALL", 0.0, 1.0, 1.0, 0.0)], ["DELTA"], 5) == (
        "E_DOMAIN",
        "strikes must be positive",
        "strike",
    )
    assert err(f, *m, book, [("CALL", 100.0, 0.0, 1.0, 0.0)], ["DELTA"], 5) == (
        "E_DOMAIN",
        "expiries must be positive",
        "expiry_years",
    )
    assert err(f, *m, book, [("UNDERLYING", None, None, 0.0, 0.0)], ["DELTA"], 5) == (
        "E_DOMAIN",
        "lot_size must be positive",
        "lot_size",
    )
    assert err(f, *m, book, [("UNDERLYING", None, None, 1.0, -1e-300)], ["DELTA"], 5) == (
        "E_DOMAIN",
        "half_spread must not be negative",
        "half_spread",
    )
    assert err(f, *m, book, und, ["DELTA"], 0) == (
        "E_DOMAIN",
        "max_lots must be at least 1",
        "max_lots",
    )
    # Boundary values that are allowed: small spot, vol and lot, zero spread, one lot.
    out = f(
        0.5,
        0.03,
        0.0,
        0.5,
        [("UNDERLYING", None, None, 3.0)],
        [("UNDERLYING", None, None, 0.5, 0.0)],
        ["DELTA"],
        1,
    )
    assert out["lots"] == [-1] and out["hedge_cost"] == 0.0
    assert out["greeks_after"] == {"delta": 2.5, "gamma": 0.0, "vega": 0.0}


def lots_oracle(
    m: tuple[float, ...], book: Any, hedges: Any, targets: list[str], max_lots: int
) -> dict[str, Any]:
    """Brute force over every lot vector in [-max_lots, max_lots]^k with the use-case weights
    1 / max(1, |b_t|)^2; ties to the least total lots, then lexicographic (ruling I-7)."""
    import itertools

    before = [sum(q * greeks_oracle(m, kd, k, t)[c] for kd, k, t, q in book) for c in range(3)]
    per = [[h[3] * g for g in greeks_oracle(m, h[0], h[1], h[2])] for h in hedges]
    rows = [("DELTA", "GAMMA", "VEGA").index(t) for t in targets]
    b = np.array([before[c] for c in rows])
    a = np.array([[per[j][c] for j in range(len(hedges))] for c in rows])
    w = np.array([1.0 / max(1.0, abs(v)) ** 2 for v in b])

    def f(x: Any) -> float:
        r = a @ np.asarray(x, dtype=float) + b
        return float(w @ (r * r))

    grid = list(itertools.product(range(-max_lots, max_lots + 1), repeat=len(hedges)))
    vals = [(f(v), v) for v in grid]
    top = min(v for v, _ in vals)
    tied = [v for val, v in vals if val - top <= 1e-12 * abs(top)]
    lots = list(min(tied, key=lambda c: (sum(abs(v) for v in c), c)))
    root = np.sqrt(w)
    cont = lsq_linear(
        a * root[:, None], -b * root, bounds=(-max_lots, max_lots), method="bvls", tol=1e-15
    )
    after = [before[c] + sum(lots[j] * per[j][c] for j in range(len(hedges))) for c in range(3)]
    cost = sum(abs(lots[j]) * h[3] * h[4] for j, h in enumerate(hedges))
    return {
        "before": before,
        "lots": lots,
        "after": after,
        "cost": cost,
        "rounding": f(lots) - f(cont.x),
    }


@pytest.mark.parametrize("case", range(3))
def test_option_hedge_lots_against_brute_force(case: int) -> None:
    m = (100.0, 0.02, 0.01, 0.25)
    if case == 0:  # three targets, two hedges: the weights decide the compromise
        book = [("CALL", 100.0, 0.5, -30.0), ("PUT", 90.0, 1.0, 12.0), ("CALL", 120.0, 0.25, 0.0)]
        hedges = [("UNDERLYING", None, None, 5.0, 0.01), ("CALL", 95.0, 0.75, 4.0, 0.2)]
        targets, max_lots = ["DELTA", "GAMMA", "VEGA"], 8
    elif case == 1:  # the upper lot bound binds
        book = [("PUT", 100.0, 1.0, 400.0)]
        hedges = [("UNDERLYING", None, None, 10.0, 0.05)]
        targets, max_lots = ["DELTA"], 6
    else:  # gamma and vega with options only; a small |b| uses weight 1
        book = [("CALL", 100.0, 1.0, 3.0), ("PUT", 110.0, 2.0, -1.0)]
        hedges = [("CALL", 105.0, 0.5, 1.0, 0.1), ("PUT", 95.0, 1.5, 1.0, 0.3)]
        targets, max_lots = ["VEGA", "GAMMA"], 7
    out = hs.option_hedge_lots(*m, book, hedges, targets, max_lots)
    want = lots_oracle(m, book, hedges, targets, max_lots)
    assert out["lots"] == want["lots"]
    for name, k in (("greeks_before", "before"), ("greeks_after", "after")):
        assert list(out[name]) == ["delta", "gamma", "vega"]
        assert [out[name][g] for g in ("delta", "gamma", "vega")] == pytest.approx(
            want[k], rel=1e-12, abs=1e-12
        )
    assert out["hedge_cost"] == pytest.approx(want["cost"], rel=1e-14, abs=1e-15)
    assert out["rounding_cost"] == pytest.approx(want["rounding"], rel=1e-7, abs=1e-12)
    if case == 1:
        assert out["lots"] == [6]


# --------------------------------------------------------------------------------------------
# The linear-programming helpers: simplex, phase 1, least margin


def test_simplex_phase_two_moves_to_the_cheaper_vertex() -> None:
    # min 2 z1 + z2, z1 + z2 = 3, z >= 0: phase 1 (Bland) enters z1 first; phase 2 must swap to z2.
    z = hs._simplex(np.array([[1.0, 1.0]]), np.array([3.0]), np.array([2.0, 1.0]))
    assert z is not None and z.tolist() == [0.0, 3.0]
    z = hs._simplex(np.array([[1.0, 1.0]]), np.array([3.0]), np.array([1.0, 2.0]))
    assert z is not None and z.tolist() == [3.0, 0.0]
    # A negative right-hand side is flipped before the artificials start at b.
    z = hs._simplex(np.array([[-1.0, -1.0]]), np.array([-3.0]), np.array([2.0, 1.0]))
    assert z is not None and z.tolist() == [0.0, 3.0]


def test_simplex_degenerate_artificials_and_redundant_rows() -> None:
    cost = np.array([2.0, 1.0])
    z = hs._simplex(np.array([[1.0, 1.0], [2.0, 2.0]]), np.array([3.0, 6.0]), cost)
    assert z is not None and z.tolist() == [0.0, 3.0]
    z = hs._simplex(np.array([[1.0, 1.0], [0.0, 0.0]]), np.array([3.0, 0.0]), cost)
    assert z is not None and z.tolist() == [0.0, 3.0]
    z = hs._simplex(np.array([[0.0, 0.0], [1.0, 1.0]]), np.array([0.0, 3.0]), cost)
    assert z is not None and z.tolist() == [0.0, 3.0]


def test_simplex_infeasible_and_unbounded() -> None:
    assert hs._simplex(np.array([[1.0, 1.0]]), np.array([-1.0]), np.array([1.0, 1.0])) is None
    assert hs._simplex(np.array([[1.0], [1.0]]), np.array([1.0, 2.0]), np.array([1.0])) is None
    assert err(hs._simplex, np.array([[1.0, -1.0]]), np.array([1.0]), np.array([-1.0, 0.0])) == (
        "E_NO_CONVERGENCE",
        "the margin search is unbounded",
        None,
    )


@pytest.mark.parametrize("seed", range(6))
def test_simplex_matches_scipy_on_random_bounded_programs(seed: int) -> None:
    from scipy.optimize import linprog

    rng = np.random.default_rng(seed)
    a = rng.normal(size=(3, 7))
    b = a @ rng.uniform(0.0, 2.0, size=7)  # feasible by construction
    if seed % 2:  # some negative right-hand sides
        a[b > 0] *= -1.0
        b = -np.abs(b)
    cost = rng.uniform(0.5, 3.0, size=7)
    want = linprog(cost, A_eq=a, b_eq=b, bounds=(0, None), method="highs")
    z = hs._simplex(a, b, cost)
    assert want.status == 0 and z is not None
    assert float(cost @ z) == pytest.approx(want.fun, rel=1e-10)
    assert z == pytest.approx(want.x, abs=1e-9)
    assert np.abs(a @ z - b).max() < 1e-10 and z.min() >= 0.0


def test_phase_one_handles_every_kind_of_bound() -> None:
    # E = I fixes the point, so each column form is used: u - s, p - q, l + s, l + s with s + t = u - l.
    lower = [None, None, 0.0, -1.0]
    upper = [1.0, None, None, 2.0]
    x = hs._phase_one(np.eye(4), np.array([-2.0, -4.0, 0.5, 1.25]), lower, upper)
    assert x is not None and x.tolist() == [-2.0, -4.0, 0.5, 1.25]
    x = hs._phase_one(np.eye(2), np.array([3.0, 0.75]), [None, 0.25], [None, 0.75])
    assert x is not None and x.tolist() == [3.0, 0.75]


def test_phase_one_finds_a_feasible_point_or_none() -> None:
    e = np.array([[1.0, 2.0, -1.0], [0.5, -1.0, 1.0]])
    rhs = np.array([1.5, -0.25])
    lower = [-1.0, 0.0, None]
    upper = [1.0, None, 3.0]
    x = hs._phase_one(e, rhs, lower, upper)
    assert x is not None
    assert np.abs(e @ x - rhs).max() < 1e-14
    assert -1.0 <= x[0] <= 1.0 and x[1] >= 0.0 and x[2] <= 3.0
    assert hs._phase_one(np.array([[1.0, 1.0]]), np.array([3.0]), [0.0, 0.0], [1.0, 1.0]) is None
    assert (
        hs._phase_one(np.array([[1.0, -1.0]]), np.array([-0.5]), [0.0, None], [None, 0.0]) is None
    )


def test_phase_one_infeasibility_is_judged_relative_to_the_data_scale() -> None:
    # 100 x = 100 + 1e-8 with x <= 1 misses by 1e-8: well inside 1e-9 of the data scale (100).
    x = hs._phase_one(np.array([[100.0]]), np.array([100.0 + 1e-8]), [0.0], [1.0])
    assert x is not None and x.tolist() == [1.0]
    assert hs._phase_one(np.array([[100.0]]), np.array([100.0 + 1e-6]), [0.0], [1.0]) is None


def test_least_margin_points() -> None:
    e = np.array([[1.0, 1.0]])
    rates = np.array([1.0, 3.0])
    # min |x1| + 3 |x2| with x1 + x2 = 3: x1 = 3 unless a bound stops it.
    got = hs._least_margin(e, np.array([3.0]), [None, None], [None, None], rates)
    assert got is not None and got.tolist() == [3.0, 0.0]
    got = hs._least_margin(e, np.array([3.0]), [None, None], [2.0, None], rates)
    assert got is not None and got.tolist() == [2.0, 1.0]
    got = hs._least_margin(e, np.array([3.0]), [None, 1.5], [2.0, None], rates)
    assert got is not None and got.tolist() == [1.5, 1.5]
    got = hs._least_margin(e, np.array([-3.0]), [-2.0, None], [None, None], rates)
    assert got is not None and got.tolist() == [-2.0, -1.0]
    # Bounds alone: the point nearest 0 in each box.
    no_rows = np.zeros((0, 3))
    got = hs._least_margin(no_rows, np.zeros(0), [1.0, None, -4.0], [2.0, -0.5, None], np.ones(3))
    assert got is not None and got.tolist() == [1.0, -0.5, 0.0]
    got = hs._least_margin(np.zeros((0, 2)), np.zeros(0), [None, None], [None, None], np.ones(2))
    assert got is not None and got.tolist() == [0.0, 0.0]
    assert hs._least_margin(e, np.array([3.0]), [None, None], [1.0, 1.0], rates) is None


# --------------------------------------------------------------------------------------------
# Integer search


def test_integer_search_returns_the_points_within_the_incumbent_radius() -> None:
    free: list[tuple[int | None, int | None]] = [(None, None)] * 2
    r = np.array([[2.0, 1.0], [0.0, 1.0]])
    # |R (n - n0)|^2 at (0, 0) is 0.4 and at the incumbent (0, -1) 1.6; only (0, 0) survives.
    assert hs._integer_search(r, np.array([0.4, -0.6]), free, [0, -1]) == [[0, 0]]
    # A tie at 0.25: both points come back, in enumeration order.
    assert hs._integer_search(np.eye(2), np.array([0.5, 0.0]), free, [0, 0]) == [[0, 0], [1, 0]]
    # n0 on the lattice: radius 0, the point itself.
    assert hs._integer_search(np.eye(2), np.array([1.0, 2.0]), free, [1, 2]) == [[1, 2]]
    # The box clips the ellipse.
    box: list[tuple[int | None, int | None]] = [(1, None), (None, None)]
    assert hs._integer_search(np.eye(2), np.array([0.2, 0.0]), box, [1, 0]) == [[1, 0]]


def test_integer_search_node_limit() -> None:
    # One dimension, R = 1e-7, incumbent far away: exactly 1,000,000 values are visited in the
    # box [0, 999999], which is allowed (the radius shrinks to 0 at v = 0 but every value of the
    # first sweep is still visited); one more value is E_NO_CONVERGENCE.
    r = np.array([[1e-7]])
    assert hs._integer_search(r, np.array([0.0]), [(0, 999_999)], [999_999]) == [[0]]
    assert err(hs._integer_search, r, np.array([0.0]), [(0, 1_000_000)], [1_000_000]) == (
        "E_NO_CONVERGENCE",
        "the integer search is too large",
        None,
    )


# --------------------------------------------------------------------------------------------
# qp_solve thresholds and paths


def test_qp_equality_dependence_threshold_is_relative_and_inclusive() -> None:
    a = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    edge = err(hs.qp_solve, a, B2, W2, eq_matrix=[[1.0, 0.0], [0.0, 1e-12]], eq_rhs=[1.0, 0.0])
    assert edge[0] == "E_SINGULAR"
    out = hs.qp_solve(a, B2, W2, eq_matrix=[[1e6, 0.0], [0.0, 1e-5]], eq_rhs=[1e6, 2e-5])
    assert out["x"] == pytest.approx([1.0, 2.0], rel=1e-9)
    big = err(hs.qp_solve, a, B2, W2, eq_matrix=[[1e6, 0.0], [0.0, 1e-7]], eq_rhs=[1.0, 0.0])
    assert big[0] == "E_SINGULAR"


def test_min_norm_rank_cut_is_relative_to_the_largest_squared_singular_value() -> None:
    # Columns with singular values 1e3 and s: kept when s^2 > 1e-12 * 1e6 = 1e-6.
    for s, rank in ((1e-2, 2), (1e-4, 1), (2e-3, 2), (5e-4, 1)):
        out = hs.qp_solve([[1e3, 0.0], [0.0, s]], [-1e3, -s], [1.0, 1.0], singular="MIN_NORM")
        assert out["rank"] == rank, s
        assert out["x"] == pytest.approx([1.0, 1.0 if rank == 2 else 0.0], rel=1e-12)


def test_scaled_solve_falls_back_to_caller_units_when_the_equalities_drift() -> None:
    # Column norms 1e5 and 1e-8: x = D x~ misses sum x = 1 in rounding, so the solve is repeated
    # unscaled. Oracle: eliminate x1 = 1 - x0 - x2 and solve the 2-column least squares.
    a = np.array([[1e5, 1e-8, 2e5], [3e5, -2e-8, 1e5], [-1e5, 1e-8, 1e5], [2e5, 3e-8, -1e5]])
    b = np.array([1.0, -0.5, 0.25, 2.0])
    out = hs.qp_solve(a.tolist(), b.tolist(), [1.0] * 4, eq_matrix=[[1.0, 1.0, 1.0]], eq_rhs=[1.0])
    red = a[:, [0, 2]] - a[:, [1]]
    y = np.linalg.lstsq(red, -(b + a[:, 1]), rcond=None)[0]
    want = [y[0], 1.0 - y[0] - y[1], y[1]]
    assert out["x"] == pytest.approx(want, rel=1e-9)
    assert abs(sum(out["x"]) - 1.0) <= 1e-15
    assert out["rank"] == 2


# --------------------------------------------------------------------------------------------
# Constrained and costed solves against an independent optimiser


def costed_oracle(
    a: Any,
    b: Any,
    w: Any,
    ridge: float,
    e: Any,
    rhs: Any,
    lower: Any,
    upper: Any,
    spreads: Any,
    impact: Any,
    cw: float,
    rates: Any,
    limit: Any,
) -> tuple[np.ndarray, float]:
    """The same problem in split variables x = p - q, p, q >= 0 (smooth), solved by SLSQP."""
    from scipy import optimize

    minimize: Any = optimize.minimize  # scipy's overloads do not model the dict constraints
    a, b, w = (np.asarray(v, dtype=float) for v in (a, b, w))
    n = a.shape[1]
    h = np.zeros(n) if spreads is None else np.asarray(spreads, dtype=float)
    imp = np.zeros(n) if impact is None else np.asarray(impact, dtype=float)

    def f(z: Any) -> float:
        x = z[:n] - z[n:]
        r = a @ x + b
        return float(w @ (r * r) + ridge * x @ x + cw * (h @ (z[:n] + z[n:]) + imp @ (x * x)))

    def grad(z: Any) -> Any:
        x = z[:n] - z[n:]
        gx = 2 * a.T @ (w * (a @ x + b)) + 2 * ridge * x + 2 * cw * imp * x
        return np.concatenate([gx + cw * h, -gx + cw * h])

    cons: list[dict[str, Any]] = []
    if e is not None:
        em, ev = np.asarray(e, dtype=float), np.asarray(rhs, dtype=float)
        cons.append(
            {
                "type": "eq",
                "fun": lambda z: em @ (z[:n] - z[n:]) - ev,
                "jac": lambda z: np.hstack([em, -em]),
            }
        )
    for j in range(n):
        if lower is not None and lower[j] is not None:
            cons.append({"type": "ineq", "fun": lambda z, j=j: z[j] - z[n + j] - lower[j]})
        if upper is not None and upper[j] is not None:
            cons.append({"type": "ineq", "fun": lambda z, j=j: upper[j] - z[j] + z[n + j]})
    if rates is not None:
        mr = np.asarray(rates, dtype=float)
        cons.append(
            {
                "type": "ineq",
                "fun": lambda z: limit - mr @ (z[:n] + z[n:]),
                "jac": lambda z: -np.concatenate([mr, mr]),
            }
        )
    best: Any = None
    for start in (np.zeros(2 * n), np.full(2 * n, 0.5), np.ones(2 * n)):
        res = minimize(
            f,
            start,
            jac=grad,
            bounds=[(0, None)] * (2 * n),
            constraints=cons,
            method="SLSQP",
            options={"ftol": 1e-16, "maxiter": 2000},
        )
        if best is None or (res.success and res.fun < best.fun):
            best = res
    x = best.x[:n] - best.x[n:]
    return x, float(best.fun)


def costed_problem(seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(100 + seed)
    n, m = 3, 5
    kw: dict[str, Any] = {
        "a": rng.normal(size=(m, n)).tolist(),
        "b": (2.0 * rng.normal(size=m)).tolist(),
        "weights": rng.uniform(0.5, 2.0, size=m).tolist(),
        "ridge": 0.0 if seed % 3 else 0.1,
        "half_spreads": rng.uniform(0.0, 1.5, size=n).tolist(),
    }
    if seed % 4 == 1:
        kw["impact"] = rng.uniform(0.0, 0.5, size=n).tolist()
        kw["cost_weight"] = 0.7
    x0 = 0.3 * rng.normal(size=n)
    if seed % 2:
        e = rng.normal(size=(1, n))
        kw["eq_matrix"], kw["eq_rhs"] = e.tolist(), (e @ x0).tolist()
    if seed % 3 == 2:
        kw["lower"] = [float(x0[0]) - 0.4, None, float(x0[2]) - 2.0]
        kw["upper"] = [None, float(x0[1]) + 0.3, float(x0[2]) + 0.2]
    if seed % 4 in (2, 3):
        rates = rng.uniform(0.5, 2.0, size=n)
        kw["margin_rates"] = rates.tolist()
        kw["margin_limit"] = float(rates @ np.abs(x0)) + 0.4
    return kw


@pytest.mark.parametrize("seed", range(16))
def test_costed_qp_matches_an_independent_optimiser(seed: int) -> None:
    kw = costed_problem(seed)
    out = hs.qp_solve(**kw)
    cw = kw.get("cost_weight", 1.0)
    want, best = costed_oracle(
        kw["a"],
        kw["b"],
        kw["weights"],
        kw["ridge"],
        kw.get("eq_matrix"),
        kw.get("eq_rhs"),
        kw.get("lower"),
        kw.get("upper"),
        kw.get("half_spreads"),
        kw.get("impact"),
        cw,
        kw.get("margin_rates"),
        kw.get("margin_limit"),
    )
    x = np.asarray(out["x"])
    # Feasible, at least as good as the optimiser, and the same (unique) minimiser.
    if "eq_matrix" in kw:
        assert np.abs(np.asarray(kw["eq_matrix"]) @ x - kw["eq_rhs"]).max() < 1e-12
    for j in range(3):
        lo = kw.get("lower", [None] * 3)[j]
        hi = kw.get("upper", [None] * 3)[j]
        assert lo is None or x[j] >= lo - 1e-15
        assert hi is None or x[j] <= hi + 1e-15
    if "margin_rates" in kw:
        assert out["margin"] <= kw["margin_limit"] * (1 + 1e-12)
        assert out["margin"] == pytest.approx(
            sum(r * abs(v) for r, v in zip(kw["margin_rates"], x)), rel=1e-14
        )
    assert out["objective"] <= best + 1e-9 * max(1.0, abs(best))
    assert out["objective"] == pytest.approx(best, rel=1e-8, abs=1e-10)
    assert x == pytest.approx(want, abs=2e-5)
    # The reported parts add up.
    cost = sum(h * abs(v) for h, v in zip(kw["half_spreads"], x)) + sum(
        i * v * v for i, v in zip(kw.get("impact", [0.0] * 3), x)
    )
    assert out["cost"] == pytest.approx(cost, rel=1e-13, abs=1e-15)
    assert out["objective"] == pytest.approx(out["risk"] + cw * out["cost"], rel=1e-14)


@pytest.mark.parametrize("seed", range(10))
def test_bounded_equality_qp_matches_an_independent_optimiser(seed: int) -> None:
    rng = np.random.default_rng(300 + seed)
    n = 4
    a = rng.normal(size=(6, n))
    b = 3.0 * rng.normal(size=6)
    w = rng.uniform(0.5, 2.0, size=6)
    x0 = 0.2 * rng.normal(size=n)
    k = seed % 3
    e = rng.normal(size=(k, n)) if k else None
    lower = [float(x0[j]) - 0.3 if j % 2 == 0 else None for j in range(n)]
    upper = [float(x0[j]) + 0.25 if j != 2 else None for j in range(n)]
    kw: dict[str, Any] = {"lower": lower, "upper": upper}
    if e is not None:
        kw["eq_matrix"], kw["eq_rhs"] = e.tolist(), (e @ x0).tolist()
    out = hs.qp_solve(a.tolist(), b.tolist(), w.tolist(), **kw)
    want, best = costed_oracle(
        a,
        b,
        w,
        0.0,
        kw.get("eq_matrix"),
        kw.get("eq_rhs"),
        lower,
        upper,
        None,
        None,
        1.0,
        None,
        None,
    )
    assert out["objective"] <= best + 1e-9 * max(1.0, best)
    assert out["x"] == pytest.approx(want.tolist(), abs=2e-5)
    assert out["rank"] == n - k


def test_every_position_on_a_bound_with_one_equality() -> None:
    # The unconstrained optimum (5, -5) is outside the box; x0 + x1 = 1 then leaves only the
    # corner (1, 0), with both positions on bounds and no free variable (the interval rule).
    out = hs.qp_solve(
        [[1.0, 0.0], [0.0, 1.0]],
        [-5.0, 5.0],
        [1.0, 1.0],
        eq_matrix=[[1.0, 1.0]],
        eq_rhs=[1.0],
        lower=[0.0, 0.0],
        upper=[1.0, 1.0],
    )
    assert out["x"] == [1.0, 0.0]
    assert out["residual"] == [-4.0, 5.0] and out["objective"] == 41.0
    # Mirrored: the equality has a negative coefficient, so the multiplier interval flips.
    out = hs.qp_solve(
        [[1.0, 0.0], [0.0, 1.0]],
        [-5.0, 5.0],
        [1.0, 1.0],
        eq_matrix=[[1.0, -1.0]],
        eq_rhs=[1.0],
        lower=[0.0, 0.0],
        upper=[1.0, 1.0],
    )
    assert out["x"] == [1.0, 0.0]
    # A fixed position (lower == upper) and one at a bound.
    out = hs.qp_solve(
        [[1.0, 0.0], [0.0, 1.0]],
        [-5.0, 5.0],
        [1.0, 1.0],
        eq_matrix=[[1.0, 2.0]],
        eq_rhs=[0.5],
        lower=[0.5, -1.0],
        upper=[0.5, 1.0],
    )
    assert out["x"] == [0.5, 0.0]


def test_every_position_on_a_bound_with_two_equalities() -> None:
    a = np.eye(3)
    b = np.array([-4.0, 4.0, -4.0])
    e = [[1.0, 1.0, 0.0], [0.0, 1.0, 1.0]]
    # x = (1, 0, 1) meets both rows; the objective pulls x0 and x2 up and x1 down, all at bounds.
    out = hs.qp_solve(
        a.tolist(),
        b.tolist(),
        [1.0] * 3,
        eq_matrix=e,
        eq_rhs=[1.0, 1.0],
        lower=[0.0, 0.0, 0.0],
        upper=[1.0, 1.0, 1.0],
    )
    assert out["x"] == pytest.approx([1.0, 0.0, 1.0], abs=1e-15)


def test_costed_margin_feasibility_tolerance() -> None:
    a = [[1.0, 0.0], [0.0, 1.0]]
    b = [-1.0, -1.0]
    # x0 is fixed at 1 by the equality; margin 1 * |1| = 1 meets a limit of exactly 1.
    out = hs.qp_solve(
        a,
        b,
        [1.0, 1.0],
        eq_matrix=[[1.0, 0.0]],
        eq_rhs=[1.0],
        margin_rates=[1.0, 0.0],
        margin_limit=1.0,
    )
    assert out["x"] == pytest.approx([1.0, 1.0], abs=1e-15) and out["margin"] <= 1.0
    # 1e-12 against a zero limit is inside the absolute allowance; 1e-11 is not.
    out = hs.qp_solve(
        a,
        b,
        [1.0, 1.0],
        eq_matrix=[[1.0, 0.0]],
        eq_rhs=[1e-12],
        margin_rates=[1.0, 0.0],
        margin_limit=0.0,
    )
    # The equality and the margin row disagree by 1e-12, inside the allowance: the solve settles
    # between them (both rows are working rows), so x0 is only pinned to [0, 1e-12].
    assert 0.0 <= out["x"][0] <= 1e-12
    assert err(
        hs.qp_solve,
        a,
        b,
        [1.0, 1.0],
        eq_matrix=[[1.0, 0.0]],
        eq_rhs=[1e-11],
        margin_rates=[1.0, 0.0],
        margin_limit=0.0,
    ) == ("E_INFEASIBLE", "no position meets the constraints and the margin limit", None)
    assert err(
        hs.qp_solve,
        a,
        b,
        [1.0, 1.0],
        eq_matrix=[[1.0, 0.0]],
        eq_rhs=[1.0],
        margin_rates=[1.0, 0.0],
        margin_limit=0.99,
    ) == ("E_INFEASIBLE", "no position meets the constraints and the margin limit", None)
    assert err(
        hs.qp_solve,
        a,
        b,
        [1.0, 1.0],
        eq_matrix=[[1.0, 1.0]],
        eq_rhs=[3.0],
        lower=[None, None],
        upper=[1.0, 1.0],
        half_spreads=[0.1, 0.1],
    ) == ("E_INFEASIBLE", "no position meets the equalities and the bounds", None)
    assert err(
        hs.qp_solve, a, b, [1.0, 1.0], eq_matrix=[[1.0, 1.0]], eq_rhs=[3.0], upper=[1.0, 1.0]
    ) == ("E_INFEASIBLE", "no position meets the equalities and the bounds", None)


def test_costed_start_respects_bounds_and_equalities() -> None:
    # Spread costs with an equality and bounds, no margin: the phase-1 start, clamped to the box.
    a = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    out = hs.qp_solve(
        a,
        [-2.0, 1.0, 0.0],
        [1.0, 1.0, 1.0],
        eq_matrix=[[1.0, 1.0]],
        eq_rhs=[1.0],
        lower=[-3.0, -3.0],
        upper=[3.0, 0.5],
        half_spreads=[0.2, 0.2],
    )
    want, _ = costed_oracle(
        a,
        [-2.0, 1.0, 0.0],
        [1.0] * 3,
        0.0,
        [[1.0, 1.0]],
        [1.0],
        [-3.0, -3.0],
        [3.0, 0.5],
        [0.2, 0.2],
        None,
        1.0,
        None,
        None,
    )
    assert out["x"] == pytest.approx(want.tolist(), abs=1e-6)
    # Bounds only, spreads large enough to keep a position at 0.
    out = hs.qp_solve(
        a, [-2.0, 0.1, 0.0], [1.0] * 3, lower=[0.5, -1.0], upper=[4.0, 1.0], half_spreads=[0.1, 5.0]
    )
    assert out["x"][1] == 0.0
    assert out["x"][0] == pytest.approx((4.0 - 0.1) / 4.0, rel=1e-14)  # f = (x - 2)^2 + x^2 + 0.1 x


def test_sign_search_flips_a_position_through_zero() -> None:
    # f = (x + b)^2 + 0.5 |x|: x = -b - 0.25 sign(x) when |b| > 0.25, else 0. A start at 0 with an
    # upper bound of 0 begins in the negative orthant, a lower bound of 0 in the positive one.
    out = hs.qp_solve([[1.0]], [-3.0], [1.0], half_spreads=[0.5])
    assert out["x"] == [2.75]
    out = hs.qp_solve([[1.0]], [3.0], [1.0], half_spreads=[0.5])
    assert out["x"] == [-2.75]
    out = hs.qp_solve([[1.0]], [-3.0], [1.0], upper=[0.0], half_spreads=[0.5])
    assert out["x"] == [0.0]
    out = hs.qp_solve([[1.0]], [3.0], [1.0], lower=[0.0], half_spreads=[0.5])
    assert out["x"] == [0.0]
    out = hs.qp_solve([[1.0]], [3.0], [1.0], upper=[0.0], half_spreads=[0.5])
    assert out["x"] == [-2.75]
    out = hs.qp_solve([[1.0]], [-0.2], [1.0], half_spreads=[0.5])
    assert out["x"] == [0.0]
    # With a margin the allowance at 0 includes mu * rate.
    out = hs.qp_solve(
        [[1.0, 0.0], [0.0, 1.0]], [-3.0, 2.0], [1.0, 1.0], margin_rates=[1.0, 1.0], margin_limit=1.0
    )
    # min (x0 - 3)^2 + (x1 + 2)^2 s.t. |x0| + |x1| <= 1: x0 - x1 direction, x = (1, 0).
    assert out["x"] == pytest.approx([1.0, 0.0], abs=1e-15) and out["margin"] == pytest.approx(1.0)


# --------------------------------------------------------------------------------------------
# Active-set internals: multipliers and the iteration caps


def qp_of(big_b: Any, d: Any, e: Any) -> Any:
    n = len(big_b[0])
    e_arr = np.asarray(e, dtype=float).reshape(len(e), n)
    return hs._Qp(
        np.asarray(big_b, dtype=float),
        np.asarray(d, dtype=float),
        e_arr,
        np.zeros(len(e)),
        [None] * n,
        [None] * n,
        0.0,
    )


def test_multipliers_without_equalities_are_the_gradient() -> None:
    # g = 2 B^T (B x + d) with B = I, d = (-5, 5), x = (1, 0): g = 2 (-4, 5).
    q = qp_of([[1.0, 0.0], [0.0, 1.0]], [-5.0, 5.0], [])
    assert q.multipliers(np.array([1.0, 0.0]), [], {0: "U", 1: "L"}).tolist() == [-8.0, 10.0]


def test_multipliers_one_equality_no_free_position_takes_the_interval_midpoint() -> None:
    q = qp_of([[1.0, 0.0], [0.0, 1.0]], [-5.0, 5.0], [[1.0, 1.0]])
    x = np.array([1.0, 0.0])  # g = (-8, 10)
    # j = 0 at an upper bound, coefficient +1: -g0 - lambda >= 0, lambda <= 8 (an upper end).
    # j = 1 at a lower bound, coefficient +1: g1 + lambda >= 0, lambda >= -10 (a lower end).
    # lambda = (-10 + 8) / 2 = -1, and g + lambda (1, 1) = (-9, 9).
    assert q.multipliers(x, [], {0: "U", 1: "L"}).tolist() == [-9.0, 9.0]
    # Only lower ends: lambda is the largest of them; only upper ends: the smallest.
    assert q.multipliers(x, [], {0: "L", 1: "L"}).tolist() == [0.0, 18.0]  # lambda = max(8, -10)
    assert q.multipliers(x, [], {0: "U", 1: "U"}).tolist() == [-18.0, 0.0]  # lambda = min(8, -10)
    # A fixed position or a zero coefficient gives no end: lambda = 0 with neither.
    assert q.multipliers(x, [], {0: "F", 1: "F"}).tolist() == [-8.0, 10.0]
    q0 = qp_of([[1.0, 0.0], [0.0, 1.0]], [-5.0, 5.0], [[0.0, 2.0]])
    # j = 0 has coefficient 0 and is skipped; j = 1 (L, +2): 10 + 2 lambda >= 0, lambda >= -5.
    assert q0.multipliers(x, [], {0: "U", 1: "L"}).tolist() == [-8.0, 0.0]
    # Skipping a fixed position must not stop the scan: j = 1 still contributes.
    assert q.multipliers(x, [], {0: "F", 1: "L"}).tolist() == [-18.0, 0.0]


def test_multipliers_negative_coefficient_swaps_the_interval_ends() -> None:
    q = qp_of([[1.0, 0.0], [0.0, 1.0]], [-5.0, 5.0], [[-2.0, 1.0]])
    x = np.array([1.0, 0.0])  # g = (-8, 10)
    # j = 0 (U, -2): -(g0 - 2 lambda) >= 0, lambda >= -4: a lower end at -g0 / coef = -4.
    # j = 1 (U, +1): -(g1 + lambda) >= 0, lambda <= -10: an upper end.
    # Midpoint -7: g + (-7) (-2, 1) = (6, 3).
    assert q.multipliers(x, [], {0: "U", 1: "U"}).tolist() == [6.0, 3.0]


def test_multipliers_with_free_positions_fit_lambda_on_them() -> None:
    q = qp_of(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], [-1.0, 2.0, 3.0], [[1.0, 1.0, 2.0]]
    )
    x = np.array([0.0, 0.0, 0.0])  # g = (-2, 4, 6)
    # Free {1}: lambda = -4 makes g1 + lambda = 0; then g = (-6, 0, -2).
    assert q.multipliers(x, [1], {0: "L", 2: "U"}).tolist() == [-6.0, 0.0, -2.0]
    # Free {1, 2}: least squares of (1, 2) lambda = -(4, 6): lambda = -16 / 5.
    got = q.multipliers(x, [1, 2], {0: "L"})
    assert got == pytest.approx([-2.0 - 3.2, 4.0 - 3.2, 6.0 - 6.4], abs=1e-14)


def test_multipliers_two_equalities_no_free_position_least_squares() -> None:
    q = qp_of([[1.0, 0.0], [0.0, 1.0]], [-5.0, 5.0], [[1.0, 0.0], [0.0, 1.0]])
    # E = I: lambda = -g exactly, every multiplier 0.
    assert q.multipliers(np.array([1.0, 0.0]), [], {0: "U", 1: "L"}).tolist() == [0.0, 0.0]


def test_iteration_caps_raise_no_convergence(monkeypatch: pytest.MonkeyPatch) -> None:
    # R6-6.1 caps the loops at 10 (n + p) + 100; with the cap forced to 0 each loop must report.
    monkeypatch.setattr(hs, "_cap", lambda n, problem: 0)
    assert err(hs.qp_solve, A2, B2, W2, lower=[0.0, 0.0]) == (
        "E_NO_CONVERGENCE",
        "the active-set search did not settle",
        None,
    )
    assert err(hs.qp_solve, A2, B2, W2, half_spreads=[0.1, 0.1]) == (
        "E_NO_CONVERGENCE",
        "the sign search did not settle",
        None,
    )
    # The sign loop gets one pass, the orthant solve inside it none.
    caps = iter([1, 0])
    monkeypatch.setattr(hs, "_cap", lambda n, problem: next(caps))
    assert err(hs.qp_solve, A2, B2, W2, half_spreads=[0.1, 0.1]) == (
        "E_NO_CONVERGENCE",
        "the active-set search did not settle",
        None,
    )


# --------------------------------------------------------------------------------------------
# Degenerate small problems (integer data, positions on bounds, kinks at 0), each checked
# against the SLSQP oracle above. Found by a mutation-guided search; the expected values come
# from the oracle, not from the code under test.

DEGENERATE: list[tuple[Any, Any, dict[str, Any]]] = [
    (  # unit weights, bounds on two of three, two equalities
        [[-2.0, 1.0, -1.0], [2.0, 2.0, -1.0], [0.0, 0.0, 0.0], [2.0, 1.0, 1.0]],
        [1.0, -2.0, 1.0, -1.0],
        {
            "lower": [None, None, -2.0],
            "upper": [0.0, None, None],
            "eq_matrix": [[-1.0, 0.0, 1.0], [0.0, -1.0, 0.0]],
            "eq_rhs": [-1.0, 1.0],
        },
    ),
    (  # a fixed position (lower == upper == 0) and a ridge
        [[1.0, -1.0, -1.0], [2.0, 0.0, 0.0]],
        [0.0, 1.0],
        {
            "lower": [0.0, 0.0, None],
            "upper": [0.0, 3.0, None],
            "eq_matrix": [[1.0, 1.0, 0.0], [1.0, 0.0, 0.0]],
            "eq_rhs": [1.0, 0.0],
            "ridge": 0.5,
        },
    ),
    (  # a spread of 0 on one instrument (not kinked), two equalities, ridge
        [[2.0, 2.0, 0.0], [2.0, -1.0, -1.0], [0.0, -1.0, -2.0], [1.0, 0.0, 2.0]],
        [-2.0, -2.0, 1.0, 1.0],
        {
            "eq_matrix": [[-1.0, 1.0, 1.0], [0.0, 0.0, -1.0]],
            "eq_rhs": [1.0, -1.0],
            "half_spreads": [0.0, 1.0, 2.0],
            "ridge": 0.5,
        },
    ),
    (  # margin on a position pinned at 1 by its bounds
        [[-2.0, 0.0], [2.0, 0.0], [0.0, 2.0]],
        [1.0, -2.0, 1.0],
        {
            "lower": [1.0, None],
            "upper": [1.0, None],
            "margin_rates": [1.0, 0.0],
            "margin_limit": 3.0,
        },
    ),
    (  # margin, an equality and mixed bounds; the optimum is a vertex
        [[2.0, 2.0, -1.0], [2.0, -1.0, -1.0], [0.0, 0.0, 2.0], [-2.0, 0.0, 1.0]],
        [0.0, 3.0, 2.0, -2.0],
        {
            "lower": [None, -1.0, 0.0],
            "upper": [1.0, 2.0, None],
            "eq_matrix": [[1.0, -1.0, 0.0]],
            "eq_rhs": [-2.0],
            "margin_rates": [1.0, 1.0, 1.0],
            "margin_limit": 3.0,
        },
    ),
    (  # one residual row, an upper bound below 0 and an equality: a negative start
        [[1.0, 2.0]],
        [3.0],
        {
            "upper": [-1.0, None],
            "eq_matrix": [[-1.0, -1.0]],
            "eq_rhs": [2.0],
            "margin_rates": [2.0, 2.0],
            "margin_limit": 5.0,
        },
    ),
    (  # spreads with an equality pair, an upper bound below 0 and a box
        [[2.0, 1.0, 2.0], [-2.0, 2.0, 2.0], [1.0, 2.0, 1.0], [2.0, 2.0, 0.0]],
        [2.0, 3.0, -1.0, -3.0],
        {
            "lower": [None, None, 0.0],
            "upper": [None, -1.0, 2.0],
            "eq_matrix": [[-1.0, 0.0, -1.0], [-1.0, -1.0, 1.0]],
            "eq_rhs": [1.0, 2.0],
            "half_spreads": [1.0, 0.0, 1.0],
        },
    ),
    (  # a position that must leave 0 for the negative side ([0, 2] -> free below 0 too)
        [[0.0, 0.0, -2.0], [0.0, 0.0, 1.0], [0.0, -2.0, -2.0], [0.0, 1.0, 2.0]],
        [2.0, 1.0, -3.0, 2.0],
        {
            "lower": [0.0, 0.0, None],
            "upper": [None, 3.0, 2.0],
            "half_spreads": [2.0, 2.0, 2.0],
            "ridge": 0.5,
        },
    ),
]


@pytest.mark.parametrize("case", range(len(DEGENERATE)))
def test_degenerate_small_problems_match_the_oracle(case: int) -> None:
    a, b, kw = DEGENERATE[case]
    w = [1.0] * len(b)
    out = hs.qp_solve(a, b, w, **kw)
    want, best = costed_oracle(
        a,
        b,
        w,
        kw.get("ridge", 0.0),
        kw.get("eq_matrix"),
        kw.get("eq_rhs"),
        kw.get("lower"),
        kw.get("upper"),
        kw.get("half_spreads"),
        None,
        1.0,
        kw.get("margin_rates"),
        kw.get("margin_limit"),
    )
    assert out["objective"] == pytest.approx(best, rel=1e-8, abs=1e-9)
    assert out["x"] == pytest.approx(want.tolist(), abs=1e-5)


def test_phase_one_on_a_pair_of_rows_with_mixed_bounds() -> None:
    e = np.array([[-2.0, 2.0, 1.0], [-2.0, -2.0, 0.0]])
    rhs = np.array([0.0, 8.0])
    lower = [-3.0, -4.0, -1.0]
    upper = [0.0, -1.0, None]
    x = hs._phase_one(e, rhs, lower, upper)
    assert x is not None
    assert np.abs(e @ x - rhs).max() < 1e-14
    assert all(lo <= v for lo, v in zip(lower, x))
    assert x[0] <= 0.0 and x[1] <= -1.0


@pytest.mark.parametrize(
    "a, b, cost",
    [
        ([[-1.0, 1.0, 1.0], [-2.0, -1.0, -2.0]], [2.0, -2.0], [0.0, 3.0, 0.0]),
        (
            [[2.0, 2.0, 1.0, 2.0, 1.0], [-1.0, 2.0, 1.0, 1.0, 2.0], [2.0, 2.0, 1.0, 2.0, 1.0]],
            [2.0, 4.0, 2.0],
            [-1.0, 0.0, -1.0, -1.0, 3.0],
        ),
        ([[0.0, 0.0], [-1.0, -1.0], [-2.0, 0.0], [0.0, 0.0]], [0.0, -2.0, 0.0, 0.0], [0.0, -1.0]),
    ],
)
def test_simplex_degenerate_programs_match_scipy(a: Any, b: Any, cost: Any) -> None:
    from scipy.optimize import linprog

    want = linprog(cost, A_eq=a, b_eq=b, bounds=(0, None), method="highs")
    z = hs._simplex(np.asarray(a), np.asarray(b), np.asarray(cost))
    assert want.status == 0 and z is not None
    assert float(np.asarray(cost) @ z) == pytest.approx(want.fun, abs=1e-12)
    assert np.abs(np.asarray(a) @ z - b).max() < 1e-12 and z.min() >= 0.0


def test_integer_solve_output_keys_and_values() -> None:
    # Two instruments, lot sizes 2 and 0.5; the lot vector is checked against brute force.
    import itertools

    a = [[0.3, -0.3], [-0.9, -0.5], [-1.0, 0.1]]
    b = [4.0, -1.5, -1.9]
    lots_sz = [2.0, 0.5]
    out = hs.integer_solve(a, b, [1.0, 1.0, 1.0], lots_sz, 0.0, [-2, None], [None, None])
    assert list(out) == [
        "lots",
        "x",
        "residual",
        "objective",
        "continuous_objective",
        "rounding_cost",
    ]

    def f(n: Any) -> float:
        x = np.array([lots_sz[0] * n[0], lots_sz[1] * n[1]])
        r = np.asarray(a) @ x + b
        return float(r @ r)

    best = min(itertools.product(range(-2, 30), range(-60, 60)), key=f)
    assert out["lots"] == list(best)
    assert out["x"] == [lots_sz[0] * best[0], lots_sz[1] * best[1]]
    r = np.asarray(a) @ np.asarray(out["x"]) + b
    assert out["residual"] == pytest.approx(r.tolist(), abs=1e-15)
    assert out["objective"] == pytest.approx(f(best), rel=1e-14)
    cont = lsq_linear(
        np.asarray(a), -np.asarray(b), bounds=([-4.0, -np.inf], [np.inf, np.inf]), tol=1e-15
    )
    assert out["continuous_objective"] == pytest.approx(2 * cont.cost, rel=1e-9)
    assert out["rounding_cost"] == pytest.approx(f(best) - 2 * cont.cost, rel=1e-7)


def test_integer_tie_tolerance_is_relative_to_the_objective() -> None:
    # A = 1000, lot 1, b = -(500 + d): f(0) = (500 + d)^2 and f(1) = (500 - d)^2 differ by 2000 d. With d = 1e-11
    # that is 2e-8, inside 1e-12 * 2.5e5: a tie (I-7), so the lighter n = 0 wins although n = 1 is lower.
    assert hs.integer_solve([[1000.0]], [-(500.0 + 1e-11)], [1.0], [1.0])["lots"] == [0]
    assert hs.integer_solve([[1000.0]], [-(500.0 + 1e-9)], [1.0], [1.0])["lots"] == [1]


def test_select_tie_goes_to_the_smaller_subset_then_the_first_indices() -> None:
    # A = I (3 x 3) with b = (-1, -1, 0): instrument 2 does nothing, so {0, 1} and {0, 1, 2} tie at 0; the
    # smaller subset wins. {0} and {1} tie at 1 for max 1; the lexicographically first wins.
    a = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    out = hs.select_solve(a, [-1.0, -1.0, 0.0], [1.0, 1.0, 1.0], 3)
    assert out["selected"] == [0, 1] and out["x"] == [1.0, 1.0, 0.0] and out["objective"] == 0.0
    one = hs.select_solve(a, [-1.0, -1.0, 0.0], [1.0, 1.0, 1.0], 1)
    assert one["selected"] == [0] and one["x"] == [1.0, 0.0, 0.0] and one["objective"] == 1.0
    assert one["residual"] == [0.0, -1.0, 0.0]
    # Bounds limit each instrument; the better single instrument is then 1.
    out = hs.select_solve(a, [-1.0, -2.0, 0.0], [1.0, 1.0, 1.0], 1, upper=[None, 1.5, None])
    assert out["selected"] == [1] and out["x"] == [0.0, 1.5, 0.0] and out["objective"] == 1.25


def test_strikes_below_one_are_valid() -> None:
    # The domain rule is strike > 0, not strike > 1: a strike of 0.5 on a spot of 0.5 is an at-the-money option.
    m = (0.5, 0.0, 0.0, 0.2)
    book = [("CALL", 0.5, 1.0, 10.0)]
    out = hs.greeks_neutralise(*m, book, [("UNDERLYING", None, None)], ["DELTA"])
    want = 10.0 * bs_greeks(0.5, 0.0, 0.0, 0.2, "CALL", 0.5, 1.0)[0]
    assert out["quantities"] == pytest.approx([-want], rel=1e-12)
    lots = hs.option_hedge_lots(*m, book, [("CALL", 0.5, 1.0, 1.0, 0.0)], ["DELTA"], 20)
    assert lots["lots"] == [-10]
