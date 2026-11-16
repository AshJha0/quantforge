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
        assert hs.Costs(**kw).given(), kw  # type: ignore[arg-type]
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
