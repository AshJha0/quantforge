"""Stage I wave 1: hedge solvers (specifications/08-hedging/hedge-solvers.md, rulings I-1 to I-14).

Hand cases for each check and output, the property tests the handover names (KKT, integer
optimality, the minimum-variance R^2, Euler contributions), and second checks against SciPy."""
import itertools
import math
from typing import Any

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from scipy.optimize import lsq_linear

from quantforge_core import hedge_solvers as hs
from quantforge_core.cli import operations  # noqa: F401 - registers the verbs
from quantforge_core.cli.registry import execute
from quantforge_core.errors import QfError

A3 = [[1.0, 0.5, 0.2], [0.3, 1.2, 0.4], [0.1, 0.6, 1.5], [0.8, 0.2, 0.9], [0.4, 0.9, 0.3]]
B3 = [-2.0, 1.5, -0.7, 0.9, -1.1]
W3 = [1.0, 2.0, 0.5, 1.5, 1.0]


def code(f: Any, *args: Any, **kwargs: Any) -> str:
    with pytest.raises(QfError) as caught:
        f(*args, **kwargs)
    return caught.value.code


def cli_code(operation: str, inputs: dict[str, Any]) -> str:
    with pytest.raises(QfError) as caught:
        execute(operation, inputs)
    return caught.value.code


def kkt_residual(a: Any, b: Any, w: Any, ridge: float, x: Any, e: Any = None, rhs: Any = None,
                 lower: Any = None, upper: Any = None) -> float:
    """Largest KKT violation relative to the gradient scale (NW06 theorem 12.1)."""
    a, b, w, x = (np.asarray(v, dtype=float) for v in (a, b, w, x))
    n = len(x)
    h = a.T @ (w[:, None] * a) + ridge * np.eye(n)
    g = 2 * (h @ x + a.T @ (w * b))
    scale = max(1.0, float(np.abs(2 * a.T @ (w * b)).max()), float(np.abs(2 * h @ x).max()))
    lo = [None] * n if lower is None else lower
    hi = [None] * n if upper is None else upper
    tight = 1e-9 * (1 + float(np.abs(x).max()))
    at_lo = [lo[j] is not None and abs(x[j] - lo[j]) <= tight for j in range(n)]
    at_hi = [hi[j] is not None and abs(x[j] - hi[j]) <= tight for j in range(n)]
    free = [j for j in range(n) if not at_lo[j] and not at_hi[j]]
    if e is not None and len(e):
        em = np.asarray(e, dtype=float)
        if free:
            lam = np.linalg.lstsq(em[:, free].T, -g[free], rcond=None)[0]
        else:
            # Every position on a bound: any lambda that makes the bound multipliers non-negative
            # certifies optimality (single equality row; the interval of admissible lambda).
            lows = [-g[j] / em[0, j] for j in range(n) if em[0, j] and at_lo[j] != (em[0, j] < 0)]
            ups = [-g[j] / em[0, j] for j in range(n) if em[0, j] and at_lo[j] == (em[0, j] < 0)]
            lam = np.array([max(lows) if lows else min(ups) if ups else 0.0])
        g = g + em.T @ lam
    worst = 0.0
    for j in range(n):
        if at_lo[j] and at_hi[j]:
            continue
        if at_lo[j]:
            worst = max(worst, -g[j])
        elif at_hi[j]:
            worst = max(worst, g[j])
        else:
            worst = max(worst, abs(g[j]))
    return worst / scale


# ----- hedge.qp.solve -----

def test_unconstrained_qp_is_weighted_least_squares() -> None:
    out = hs.qp_solve(A3, B3, W3)
    root = np.sqrt(W3)
    ref = np.linalg.lstsq(np.asarray(A3) * root[:, None], -np.asarray(B3) * root, rcond=None)[0]
    assert np.allclose(out["x"], ref, rtol=1e-12, atol=1e-13)
    assert out["rank"] == 3
    r = np.asarray(A3) @ ref + B3
    assert out["objective"] == pytest.approx(float(np.sum(np.asarray(W3) * r * r)), rel=1e-13)


def test_ridge_shrinks_and_matches_the_normal_equations() -> None:
    out = hs.qp_solve(A3, B3, W3, ridge=0.1)
    a, w, b = np.asarray(A3), np.asarray(W3), np.asarray(B3)
    ref = np.linalg.solve(a.T @ (w[:, None] * a) + 0.1 * np.eye(3), -a.T @ (w * b))
    assert np.allclose(out["x"], ref, rtol=1e-11)
    plain = hs.qp_solve(A3, B3, W3)
    assert np.linalg.norm(out["x"]) < np.linalg.norm(plain["x"])


def test_bounds_agree_with_scipy_bvls() -> None:
    lower: list[float | None] = [0.0, -0.3, None]
    upper: list[float | None] = [1.0, None, -0.5]
    out = hs.qp_solve(A3, B3, W3, lower=lower, upper=upper)
    root = np.sqrt(W3)
    ref = lsq_linear(np.asarray(A3) * root[:, None], -np.asarray(B3) * root,
                     bounds=([0.0, -0.3, -np.inf], [1.0, np.inf, -0.5]), method="bvls",
                     tol=1e-15).x
    assert np.allclose(out["x"], ref, rtol=1e-9, atol=1e-12)
    assert kkt_residual(A3, B3, W3, 0.0, out["x"], lower=lower, upper=upper) < 1e-10


def test_fixed_variable_stays_at_its_value() -> None:
    out = hs.qp_solve(A3, B3, W3, lower=[0.25, None, None], upper=[0.25, None, None])
    assert out["x"][0] == 0.25
    assert out["rank"] == 3


def test_budget_equality_holds_and_rank_drops() -> None:
    out = hs.qp_solve(A3, B3, W3, eq_matrix=[[1.0, 1.0, 1.0]], eq_rhs=[0.0])
    assert math.fsum(out["x"]) == pytest.approx(0.0, abs=1e-14)
    assert out["rank"] == 2
    assert kkt_residual(A3, B3, W3, 0.0, out["x"], e=[[1.0, 1.0, 1.0]]) < 1e-10


def test_equalities_fixing_every_position() -> None:
    e = [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [1.0, 1.0, 1.0]]
    out = hs.qp_solve(A3, B3, W3, eq_matrix=e, eq_rhs=[1.0, 2.0, 0.0])
    assert np.allclose(out["x"], [1.0, 1.0, -2.0], atol=1e-14)
    assert out["rank"] == 0


def test_equality_and_bounds_together() -> None:
    e, lower, upper = [[1.0, 1.0, 1.0]], [-0.2, -0.2, -0.2], [0.6, 0.6, 0.6]
    out = hs.qp_solve(A3, B3, W3, eq_matrix=e, eq_rhs=[0.5], lower=lower, upper=upper)
    assert math.fsum(out["x"]) == pytest.approx(0.5, abs=1e-13)
    assert all(-0.2 <= v <= 0.6 for v in out["x"])
    assert kkt_residual(A3, B3, W3, 0.0, out["x"], [[1.0, 1.0, 1.0]], None, lower, upper) < 1e-10


def test_min_norm_splits_duplicates_and_leaves_a_zero_column() -> None:
    a = [[1.0, 1.0, 0.0], [0.5, 0.5, 0.0], [0.2, 0.2, 0.0]]
    out = hs.qp_solve(a, [-2.0, -1.0, -0.4], [1.0, 1.0, 1.0], singular="MIN_NORM")
    assert out["x"][0] == pytest.approx(out["x"][1], rel=1e-13)
    assert out["x"][2] == 0.0
    assert out["rank"] == 1
    assert out["x"][0] + out["x"][1] == pytest.approx(2.0, rel=1e-13)


def test_min_norm_on_a_regular_problem_equals_the_unique_solution() -> None:
    plain = hs.qp_solve(A3, B3, W3)
    least = hs.qp_solve(A3, B3, W3, singular="MIN_NORM")
    assert np.allclose(plain["x"], least["x"], rtol=1e-13)


def test_min_norm_with_an_equality_matches_the_pseudo_inverse() -> None:
    a = [[1.0, 1.0, 0.5], [0.5, 0.5, 1.0]]
    out = hs.qp_solve(a, [-1.0, 0.3], [1.0, 1.0], eq_matrix=[[1.0, -1.0, 2.0]], eq_rhs=[0.4],
                      singular="MIN_NORM")
    # Every minimiser is x_p + Z y; the least-norm one is orthogonal to the free direction.
    x = np.asarray(out["x"])
    assert float(np.asarray([1.0, -1.0, 2.0]) @ x) == pytest.approx(0.4, abs=1e-14)
    ref = np.linalg.lstsq(np.vstack([a, [[1.0, -1.0, 2.0]]]), [1.0, -0.3, 0.4], rcond=None)[0]
    assert np.allclose(x, ref, atol=1e-12)


def test_ridge_regularises_duplicate_instruments() -> None:
    a = [[1.0, 1.0], [0.5, 0.5]]
    assert code(hs.qp_solve, a, [1.0, 1.0], [1.0, 1.0]) == "E_SINGULAR"
    out = hs.qp_solve(a, [1.0, 1.0], [1.0, 1.0], ridge=0.01)
    assert out["x"][0] == pytest.approx(out["x"][1], rel=1e-12)
    assert out["rank"] == 2


def test_duplicates_made_regular_by_an_equality() -> None:
    out = hs.qp_solve([[1.0, 1.0], [0.5, 0.5]], [1.0, 1.0], [1.0, 1.0],
                      eq_matrix=[[1.0, -1.0]], eq_rhs=[0.0])
    assert out["x"][0] == pytest.approx(out["x"][1], rel=1e-13)
    assert out["rank"] == 1


def test_weights_spanning_six_decades_stay_accurate() -> None:
    w = [1e-3, 1.0, 1e3, 10.0, 0.1]
    out = hs.qp_solve(A3, B3, w)
    root = np.sqrt(w)
    ref = np.linalg.lstsq(np.asarray(A3) * root[:, None], -np.asarray(B3) * root, rcond=None)[0]
    assert np.allclose(out["x"], ref, rtol=1e-11)


def test_already_hedged_book_and_negative_zero() -> None:
    out = hs.qp_solve(A3, [0.0, -0.0, 0.0, 0.0, 0.0], W3)
    assert out["x"] == [0.0, 0.0, 0.0]
    assert all(math.copysign(1.0, v) > 0 for v in out["x"] + out["residual"])
    assert out["objective"] == 0.0


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({"b": [1.0]}, "E_INPUT"),
    ({"a": [[1.0, 2.0], [1.0]]}, "E_INPUT"),
    ({"a": []}, "E_INPUT"),
    ({"weights": [1.0]}, "E_INPUT"),
    ({"eq_matrix": [[1.0, 1.0]]}, "E_INPUT"),
    ({"eq_matrix": [[1.0]], "eq_rhs": [0.0]}, "E_INPUT"),
    ({"eq_matrix": [[1.0, 1.0]], "eq_rhs": [0.0, 1.0]}, "E_INPUT"),
    ({"lower": [0.0]}, "E_INPUT"),
    ({"upper": [0.0, 1.0, 2.0]}, "E_INPUT"),
    ({"lower": [0.0, None], "singular": "MIN_NORM"}, "E_INPUT"),
    ({"weights": [1.0, 0.0]}, "E_DOMAIN"),
    ({"ridge": -1.0}, "E_DOMAIN"),
    ({"lower": [1.0, None], "upper": [0.0, None]}, "E_DOMAIN"),
    ({"eq_matrix": [[1.0, 1.0], [2.0, 2.0]], "eq_rhs": [0.0, 0.0]}, "E_SINGULAR"),
    ({"eq_matrix": [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], "eq_rhs": [0.0, 0.0, 0.0]},
     "E_SINGULAR"),
    ({"eq_matrix": [[1.0, 1.0]], "eq_rhs": [5.0], "upper": [1.0, 1.0]}, "E_INFEASIBLE"),
    ({"eq_matrix": [[1.0, -1.0]], "eq_rhs": [3.0], "lower": [0.0, 0.0], "upper": [1.0, 1.0]},
     "E_INFEASIBLE"),
    ({"eq_matrix": [[1.0, 0.0]], "eq_rhs": [2.0], "lower": [1.0, None], "upper": [1.0, None]},
     "E_INFEASIBLE"),
])
def test_qp_checks(kwargs: dict[str, Any], expected: str) -> None:
    base: dict[str, Any] = {"a": [[1.0, 0.0], [0.0, 1.0]], "b": [1.0, -1.0],
                            "weights": [1.0, 1.0]}
    base.update(kwargs)
    assert code(hs.qp_solve, **base) == expected


def test_qp_check_order() -> None:
    # A zero weight with a singular a is E_DOMAIN (hedgeqp_i-0044); singular and infeasible is
    # E_SINGULAR (I-14).
    assert code(hs.qp_solve, [[1.0, 1.0], [0.5, 0.5]], [1.0, 1.0], [0.0, 1.0]) == "E_DOMAIN"
    assert code(hs.qp_solve, [[1.0, 1.0], [0.5, 0.5]], [1.0, 1.0], [1.0, 1.0],
                eq_matrix=[[1.0, 1.0]], eq_rhs=[9.0], upper=[1.0, 1.0]) == "E_SINGULAR"


def test_feasible_tight_box_is_not_infeasible() -> None:
    out = hs.qp_solve([[1.0, 0.0], [0.0, 1.0]], [1.0, -1.0], [1.0, 1.0],
                      eq_matrix=[[1.0, 1.0]], eq_rhs=[2.0], upper=[1.0, 1.0])
    assert out["x"] == pytest.approx([1.0, 1.0], abs=1e-14)


bounded = st.one_of(st.none(), st.floats(-2.0, 2.0))


@settings(max_examples=60, deadline=None)
@given(st.integers(1, 4), st.integers(1, 6), st.data())
def test_property_qp_kkt_bounds_and_equalities(n: int, m: int, data: st.DataObject) -> None:
    unit = st.floats(-2.0, 2.0)
    a = [[data.draw(unit) for _ in range(n)] for _ in range(m)]
    b = [data.draw(unit) for _ in range(m)]
    w = [data.draw(st.floats(0.1, 3.0)) for _ in range(m)]
    ridge = data.draw(st.sampled_from([0.0, 0.0, 0.05]))
    lower = [data.draw(bounded) for _ in range(n)]
    upper = [None if lo is None else lo + data.draw(st.floats(0.0, 2.0)) for lo in lower]
    with_eq = n > 1 and data.draw(st.booleans())
    e = [[1.0] * n] if with_eq else None
    rhs = [data.draw(st.floats(-1.0, 1.0))] if with_eq else None
    try:
        out = hs.qp_solve(a, b, w, ridge, e, rhs, lower, upper)
    except QfError as err:
        assume(err.code not in ("E_SINGULAR", "E_INFEASIBLE"))
        raise
    x = out["x"]
    for j in range(n):
        lo, hi = lower[j], upper[j]
        assert lo is None or x[j] >= lo
        assert hi is None or x[j] <= hi
    if e is not None and rhs is not None:
        # The equality holds to rounding relative to the size of x, not to an absolute 1e-12.
        assert math.fsum(x) == pytest.approx(rhs[0], abs=1e-12 * (1 + max(map(abs, x))))
    assert kkt_residual(a, b, w, ridge, x, e, rhs, lower, upper) < 1e-8


@settings(max_examples=40, deadline=None)
@given(st.integers(1, 4), st.data())
def test_property_min_norm_equals_the_unique_solution(n: int, data: st.DataObject) -> None:
    m = n + 2
    a = [[data.draw(st.floats(-2.0, 2.0)) for _ in range(n)] for _ in range(m)]
    b = [data.draw(st.floats(-2.0, 2.0)) for _ in range(m)]
    w = [1.0] * m
    # R6-6.2 / R6-6.2a: ERROR decides uniqueness on the column-scaled problem, MIN_NORM counts
    # rank unscaled. They agree only when the unscaled problem is itself well conditioned.
    assume(np.linalg.cond(np.asarray(a, dtype=float)) < 1e5)
    try:
        unique = hs.qp_solve(a, b, w)
    except QfError as err:
        assume(err.code != "E_SINGULAR")
        raise
    least = hs.qp_solve(a, b, w, singular="MIN_NORM")
    assert least["rank"] == unique["rank"] == n
    assert np.allclose(least["x"], unique["x"], rtol=1e-9, atol=1e-9)


# ----- hedge.integer.solve -----

def brute_force(a: Any, b: Any, w: Any, lots: Any, ridge: float, box: int) -> list[int]:
    best: tuple[float, int, tuple[int, ...]] | None = None
    for n in itertools.product(range(-box, box + 1), repeat=len(lots)):
        x = [s * v for s, v in zip(lots, n, strict=True)]
        r = [math.fsum([*(row[j] * x[j] for j in range(len(x))), v]) for row, v in zip(a, b)]
        f = math.fsum(wi * ri * ri for wi, ri in zip(w, r)) + ridge * math.fsum(v * v for v in x)
        key = (f, sum(map(abs, n)), n)
        if best is None or f < best[0] * (1 - 1e-12) or (
                abs(f - best[0]) <= 1e-12 * abs(best[0]) and key[1:] < best[1:]):
            best = key
    assert best is not None
    return list(best[2])


def test_integer_matches_brute_force() -> None:
    out = hs.integer_solve(A3, B3, W3, [0.5, 2.0, 1.0])
    assert out["lots"] == brute_force(A3, B3, W3, [0.5, 2.0, 1.0], 0.0, 6)
    assert out["x"] == [0.5 * out["lots"][0], 2.0 * out["lots"][1], out["lots"][2]]
    assert out["rounding_cost"] == pytest.approx(out["objective"] - out["continuous_objective"])
    assert out["rounding_cost"] >= 0


def test_integer_ties_follow_ruling_i7() -> None:
    # f(n) = (n + 0.5)^2: 0 and -1 tie exactly; the smaller sum |n| wins.
    assert hs.integer_solve([[1.0]], [0.5], [1.0], [1.0])["lots"] == [0]
    # f(n) = (n - 1.5)^2: 1 and 2 tie; 1 wins.
    assert hs.integer_solve([[1.0]], [-1.5], [1.0], [1.0])["lots"] == [1]
    # Two independent half-way coordinates with mirrored signs: equal sum |n|, the
    # lexicographically smallest of {(0, 0), (0, 1), (-1, 0), (-1, 1)} by sum is (0, 0).
    out = hs.integer_solve([[1.0, 0.0], [0.0, 1.0]], [0.5, -0.5], [1.0, 1.0], [1.0, 1.0])
    assert out["lots"] == [0, 0]
    out = hs.integer_solve([[1.0, 0.0], [0.0, 1.0]], [0.5, -0.5], [1.0, 1.0], [1.0, 1.0],
                           lower_lots=[None, 1], upper_lots=[None, None])
    assert out["lots"] == [0, 1]
    out = hs.integer_solve([[1.0, 0.0], [0.0, 1.0]], [0.5, 0.5], [1.0, 1.0], [1.0, 1.0],
                           lower_lots=[None, None], upper_lots=[-1, None])
    assert out["lots"] == [-1, 0]


def test_integer_beats_rounding_on_a_correlated_problem() -> None:
    a = [[1.0, 0.99], [0.99, 1.0]]
    b = [-3.4, -3.3]
    out = hs.integer_solve(a, b, [1.0, 1.0], [1.0, 1.0])
    assert out["lots"] == brute_force(a, b, [1.0, 1.0], [1.0, 1.0], 0.0, 12)


def test_integer_bounds_bind_and_relaxation_uses_them() -> None:
    out = hs.integer_solve(A3, B3, W3, [0.1, 0.1, 0.1], lower_lots=[0, 0, None],
                           upper_lots=[5, None, None])
    assert 0 <= out["lots"][0] <= 5 and out["lots"][1] >= 0
    relaxed = hs.qp_solve(A3, B3, W3, lower=[0.0, 0.0, None], upper=[0.5, None, None])
    assert out["continuous_objective"] == pytest.approx(relaxed["objective"], rel=1e-13)


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({"lot_sizes": [1.0]}, "E_INPUT"),
    ({"lower_lots": [0]}, "E_INPUT"),
    ({"lot_sizes": [1.0, 0.0]}, "E_DOMAIN"),
    ({"weights": [-1.0, 1.0]}, "E_DOMAIN"),
    ({"ridge": -0.5}, "E_DOMAIN"),
    ({"lower_lots": [2, None], "upper_lots": [1, None]}, "E_DOMAIN"),
    ({"a": [[1.0, 1.0], [2.0, 2.0]]}, "E_SINGULAR"),
    ({"a": [[1.0, 1.0]], "b": [1.0], "weights": [1.0]}, "E_SINGULAR"),
    ({"a": [[1.0, 1.0], [2.0, 2.0]], "lower_lots": [0, 0], "upper_lots": [1, 1]}, "E_SINGULAR"),
])
def test_integer_checks(kwargs: dict[str, Any], expected: str) -> None:
    base: dict[str, Any] = {"a": [[1.0, 0.0], [0.0, 1.0]], "b": [1.0, -1.0],
                            "weights": [1.0, 1.0], "lot_sizes": [1.0, 1.0]}
    base.update(kwargs)
    assert code(hs.integer_solve, **base) == expected


@settings(max_examples=40, deadline=None)
@given(st.integers(1, 3), st.data())
def test_property_integer_optimal_against_neighbours(n: int, data: st.DataObject) -> None:
    m = n + 1
    a = [[data.draw(st.floats(-2.0, 2.0)) for _ in range(n)] for _ in range(m)]
    b = [data.draw(st.floats(-10.0, 10.0)) for _ in range(m)]
    w = [data.draw(st.floats(0.2, 2.0)) for _ in range(m)]
    lots = [data.draw(st.sampled_from([0.5, 1.0, 2.0])) for _ in range(n)]
    try:
        out = hs.integer_solve(a, b, w, lots, ridge=0.01)
    except QfError as err:
        assume(err.code != "E_SINGULAR")
        raise
    assert out["objective"] >= out["continuous_objective"] * (1 - 1e-12) - 1e-12
    for j in range(n):
        for step in (-1, 1):
            n2 = list(out["lots"])
            n2[j] += step
            x = [s * v for s, v in zip(lots, n2, strict=True)]
            _, f = hs._objective(a, b, w, 0.01, x)
            assert f >= out["objective"] * (1 - 1e-12)


# ----- hedge.minvar.ratio -----

def test_minvar_single_hedge_is_minus_hulls_ratio() -> None:
    sigma_s, sigma_f, rho = 0.2, 0.25, 0.8
    cov = [[sigma_s**2, rho * sigma_s * sigma_f], [rho * sigma_s * sigma_f, sigma_f**2]]
    out = hs.minvar_ratio(cov)
    assert out["hedge"][0] == pytest.approx(-rho * sigma_s / sigma_f, rel=1e-14)
    assert out["effectiveness"] == pytest.approx(rho * rho, rel=1e-13)


@settings(max_examples=40, deadline=None)
@given(st.integers(1, 3), st.integers(0, 10), st.data())
def test_property_minvar_effectiveness_is_ols_r_squared(k: int, extra: int,
                                                        data: st.DataObject) -> None:
    t = k + 2 + extra
    grid = st.integers(-100, 100).map(lambda v: v / 100)
    hedges = [[data.draw(grid) for _ in range(t)] for _ in range(k)]
    exposure = [data.draw(grid) for _ in range(t)]
    try:
        out = hs.minvar_ratio(exposure_changes=exposure, hedge_changes=hedges)
    except QfError as err:
        assume(err.code not in ("E_SINGULAR", "E_DOMAIN"))
        raise
    design = np.column_stack([np.ones(t), *hedges])
    coef, *_ = np.linalg.lstsq(design, exposure, rcond=None)
    fitted = design @ coef
    y = np.asarray(exposure)
    # R-squared is undefined for a constant exposure series (zero total sum of squares); numpy's
    # reference then turns rounding noise into a ratio, so the property only holds with variance.
    assume(float(np.sum((y - y.mean()) ** 2)) > 1e-12)
    r2 = 1 -float(np.sum((y - fitted) ** 2)) / float(np.sum((y - y.mean()) ** 2))
    assert out["effectiveness"] == pytest.approx(r2, abs=1e-8)
    assert np.allclose(out["hedge"], -coef[1:], rtol=1e-7, atol=1e-8)


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({}, "E_INPUT"),
    ({"covariance": [[1.0, 0.0], [0.0, 1.0]], "exposure_changes": [1.0, 2.0, 3.0]}, "E_INPUT"),
    ({"exposure_changes": [1.0, 2.0, 3.0]}, "E_INPUT"),
    ({"hedge_changes": [[1.0, 2.0, 3.0]]}, "E_INPUT"),
    ({"covariance": [[1.0]]}, "E_INPUT"),
    ({"covariance": [[1.0, 0.2], [0.2]]}, "E_INPUT"),
    ({"covariance": [[1.0, 0.2], [0.3, 1.0]]}, "E_INPUT"),
    ({"exposure_changes": [1.0, 2.0], "hedge_changes": [[1.0, 0.0]]}, "E_INPUT"),
    ({"exposure_changes": [1.0, 2.0, 4.0], "hedge_changes": [[1.0, 0.0]]}, "E_INPUT"),
    ({"exposure_changes": [1.0, 2.0, 4.0], "hedge_changes": []}, "E_INPUT"),
    ({"covariance": [[0.0, 0.0], [0.0, 1.0]]}, "E_DOMAIN"),
    ({"covariance": [[1.0, 0.0], [0.0, 0.0]]}, "E_SINGULAR"),
    ({"covariance": [[1.0, 0.5, 0.5], [0.5, 1.0, 1.0], [0.5, 1.0, 1.0]]}, "E_SINGULAR"),
    ({"covariance": [[1.0, 1.2], [1.2, 1.0]]}, "E_NOT_POSITIVE_DEFINITE"),
])
def test_minvar_checks(kwargs: dict[str, Any], expected: str) -> None:
    assert code(hs.minvar_ratio, **kwargs) == expected


# ----- hedge.greeks.neutralise -----

MARKET = (100.0, 0.03, 0.01, 0.25)
BOOK = [("CALL", 100.0, 0.5, -1000.0), ("PUT", 90.0, 1.0, 500.0)]


def test_unit_greeks_against_finite_differences() -> None:
    def price(s: float, v: float) -> float:
        k, t, r, q = 105.0, 0.75, 0.03, 0.01
        d1 = (math.log(s / k) + (r - q + v * v / 2) * t) / (v * math.sqrt(t))
        d2 = d1 - v * math.sqrt(t)
        cdf = lambda z: 0.5 * math.erfc(-z / math.sqrt(2))
        return s * math.exp(-q * t) * cdf(d1) - k * math.exp(-r * t) * cdf(d2)

    delta, gamma, vega = hs._unit_greeks(100.0, 0.03, 0.01, 0.2, "CALL", 105.0, 0.75)
    h = 1e-3
    assert delta == pytest.approx((price(100 + h, 0.2) - price(100 - h, 0.2)) / (2 * h), rel=1e-8)
    assert gamma == pytest.approx(
        (price(100 + h, 0.2) - 2 * price(100, 0.2) + price(100 - h, 0.2)) / h**2, rel=1e-5)
    assert vega == pytest.approx((price(100, 0.2 + 1e-5) - price(100, 0.2 - 1e-5)) / 2e-5,
                                 rel=1e-7)
    put = hs._unit_greeks(100.0, 0.03, 0.01, 0.2, "PUT", 105.0, 0.75)
    assert put[0] == pytest.approx(delta - math.exp(-0.01 * 0.75), rel=1e-13)
    assert put[1:] == (gamma, vega)


def test_delta_gamma_vega_hedge_zeroes_the_targets() -> None:
    hedges = [("UNDERLYING", None, None), ("CALL", 105.0, 0.25), ("PUT", 95.0, 2.0)]
    out = hs.greeks_neutralise(*MARKET, BOOK, hedges, ["DELTA", "GAMMA", "VEGA"])
    scale = max(1.0, *map(abs, out["greeks_before"].values()))
    for name in ("delta", "gamma", "vega"):
        assert abs(out["greeks_after"][name]) <= 1e-10 * scale


def test_target_order_does_not_change_the_answer() -> None:
    hedges = [("CALL", 105.0, 0.25), ("PUT", 95.0, 2.0)]
    one = hs.greeks_neutralise(*MARKET, BOOK, hedges, ["GAMMA", "VEGA"])
    two = hs.greeks_neutralise(*MARKET, BOOK, hedges, ["VEGA", "GAMMA"])
    assert np.allclose(one["quantities"], two["quantities"], rtol=1e-12)
    assert one["greeks_after"]["delta"] == pytest.approx(two["greeks_after"]["delta"], rel=1e-12)


@pytest.mark.parametrize(("change", "expected"), [
    ({"targets": ["DELTA"]}, "E_INPUT"),
    ({"targets": ["DELTA", "DELTA"]}, "E_INPUT"),
    ({"hedges": [], "targets": []}, "E_INPUT"),
    ({"portfolio": [("UNDERLYING", 100.0, None, 1.0)]}, "E_INPUT"),
    ({"portfolio": [("CALL", 100.0, None, 1.0)]}, "E_INPUT"),
    ({"volatility": 0.0}, "E_DOMAIN"),
    ({"spot": -1.0}, "E_DOMAIN"),
    ({"portfolio": [("CALL", -100.0, 1.0, 1.0)]}, "E_DOMAIN"),
    ({"portfolio": [("PUT", 100.0, 0.0, 1.0)]}, "E_DOMAIN"),
    ({"hedges": [("UNDERLYING", None, None), ("UNDERLYING", None, None)]}, "E_SINGULAR"),
    ({"hedges": [("CALL", 105.0, 0.25), ("CALL", 105.0, 0.25)]}, "E_SINGULAR"),
])
def test_greeks_checks(change: dict[str, Any], expected: str) -> None:
    args: dict[str, Any] = {"spot": 100.0, "rate": 0.03, "dividend_yield": 0.01,
                            "volatility": 0.25, "portfolio": BOOK,
                            "hedges": [("UNDERLYING", None, None), ("CALL", 105.0, 0.25)],
                            "targets": ["DELTA", "GAMMA"]}
    args.update(change)
    assert code(hs.greeks_neutralise, **args) == expected


# ----- hedge.beta.futures -----

def test_hulls_thirty_contracts() -> None:
    out = hs.beta_futures(5_050_000, 1.5, 0.0, 1010.0, 250.0)
    assert out == {"contracts": -30.0, "contracts_held": -30.0, "beta_after": 0.0}


@pytest.mark.parametrize(("value", "held"), [(2.5, 3.0), (-2.5, -3.0), (2.4999, 2.0),
                                             (-0.4, 0.0), (0.5, 1.0), (-7.6, -8.0)])
def test_beta_rounds_half_away_from_zero(value: float, held: float) -> None:
    # contracts = (target - beta) V / (F m) with V = F m = 1 and beta = 0.
    out = hs.beta_futures(1.0, 0.0, value, 1.0, 1.0)
    assert out["contracts_held"] == held
    assert math.copysign(1.0, out["contracts_held"]) == math.copysign(1.0, held)
    assert hs.beta_futures(1.0, 0.0, value, 1.0, 1.0, "NONE")["contracts_held"] == value


@pytest.mark.parametrize("bad", [{"portfolio_value": 0.0}, {"futures_price": 0.0},
                                 {"multiplier": -250.0}])
def test_beta_checks(bad: dict[str, float]) -> None:
    args = {"portfolio_value": 1e6, "portfolio_beta": 1.2, "target_beta": 0.5,
            "futures_price": 4000.0, "multiplier": 50.0}
    args.update(bad)
    assert code(hs.beta_futures, **args) == "E_DOMAIN"


# ----- hedge.residual.report -----

COV = [[4e-4, 1e-4, 0.0], [1e-4, 2.5e-4, 5e-5], [0.0, 5e-5, 1e-4]]


def test_residual_report_values() -> None:
    a = [[1.0, 0.2], [0.4, 1.0], [0.1, 0.5]]
    out = hs.residual_report(a, [-1.0, 0.5, -0.3], [0.5, -0.2], COV)
    r = np.asarray(a) @ [0.5, -0.2] + [-1.0, 0.5, -0.3]
    s = np.asarray(COV)
    assert np.allclose(out["residual"], r, rtol=1e-14)
    assert out["variance_after"] == pytest.approx(float(r @ s @ r), rel=1e-13)
    assert out["volatility_after"] == pytest.approx(math.sqrt(out["variance_after"]), rel=1e-15)
    assert out["effectiveness"] == pytest.approx(
        1 - out["variance_after"] / out["variance_before"], rel=1e-15)


@settings(max_examples=50, deadline=None)
@given(st.integers(1, 4), st.integers(1, 3), st.data())
def test_property_contributions_sum_to_variance(m: int, n: int, data: st.DataObject) -> None:
    unit = st.floats(-1.0, 1.0)
    a = [[data.draw(unit) for _ in range(n)] for _ in range(m)]
    b = [data.draw(unit) for _ in range(m)]
    x = [data.draw(unit) for _ in range(n)]
    root = np.asarray([[data.draw(unit) for _ in range(m)] for _ in range(m)])
    cov = (root @ root.T + 0.01 * np.eye(m)).tolist()
    cov = [[(cov[i][j] + cov[j][i]) / 2 for j in range(m)] for i in range(m)]
    try:
        out = hs.residual_report(a, b, x, cov)
    except QfError as err:
        assume(err.code != "E_DOMAIN")
        raise
    assert math.fsum(out["contributions"]) == pytest.approx(
        out["variance_after"], rel=1e-12, abs=1e-15)


@pytest.mark.parametrize(("change", "expected"), [
    ({"x": [1.0]}, "E_INPUT"),
    ({"b": [1.0]}, "E_INPUT"),
    ({"a": [[1.0, 0.0], [1.0]]}, "E_INPUT"),
    ({"covariance": [[1.0, 0.0], [0.1, 1.0]]}, "E_INPUT"),
    ({"covariance": [[1.0]]}, "E_INPUT"),
    ({"covariance": [[1.0, 0.0], [0.0, -1.0]]}, "E_NOT_POSITIVE_DEFINITE"),
    ({"b": [0.0, 0.0]}, "E_DOMAIN"),
])
def test_residual_checks(change: dict[str, Any], expected: str) -> None:
    args: dict[str, Any] = {"a": [[1.0, 0.0], [0.0, 1.0]], "b": [1.0, -1.0], "x": [0.5, 0.5],
                            "covariance": [[1.0, 0.0], [0.0, 1.0]]}
    args.update(change)
    assert code(hs.residual_report, **args) == expected


# ----- the CLI: schema, null bounds, limits, finite rule -----

def test_cli_null_bounds_and_defaults() -> None:
    out = execute("hedge.qp.solve", {"a": A3, "b": B3, "weights": W3,
                                     "lower": [0.0, None, None], "upper": [None, None, None]})
    assert out["x"][0] >= 0
    out = execute("hedge.integer.solve", {"a": [[1.0]], "b": [0.5], "weights": [1.0],
                                          "lot_sizes": [1.0], "lower_lots": [None],
                                          "upper_lots": [None]})
    assert out["lots"] == [0]
    assert execute("hedge.beta.futures", {"portfolio_value": 1.0, "portfolio_beta": 0.0,
                                          "target_beta": 2.5, "futures_price": 1.0,
                                          "multiplier": 1.0})["contracts_held"] == 3.0


def test_cli_greeks_and_residual_and_minvar() -> None:
    out = execute("hedge.greeks.neutralise", {
        "spot": 100.0, "rate": 0.03, "dividend_yield": 0.01, "volatility": 0.25,
        "portfolio": [{"instrument": "CALL", "strike": 100.0, "expiry_years": 0.5,
                       "quantity": -1000.0}],
        "hedges": [{"instrument": "UNDERLYING"}], "targets": ["DELTA"]})
    assert abs(out["greeks_after"]["delta"]) < 1e-9
    out = execute("hedge.residual.report", {"a": [[1.0]], "b": [-1.0], "x": [1.0],
                                            "covariance": [[1.0]]})
    assert out["effectiveness"] == 1.0
    out = execute("hedge.minvar.ratio", {"exposure_changes": [1.0, 2.0, 4.0],
                                         "hedge_changes": [[1.0, 2.0, 3.5]]})
    assert out["effectiveness"] > 0.99


@pytest.mark.parametrize(("operation", "inputs", "expected"), [
    ("hedge.qp.solve", {"a": A3, "b": B3, "weights": W3, "lower": [0.0, None, "x"]}, "E_SCHEMA"),
    ("hedge.qp.solve", {"a": A3, "b": [None, *B3[1:]], "weights": W3}, "E_SCHEMA"),
    ("hedge.qp.solve", {"a": A3, "b": B3, "weights": W3, "singular": "PINV"}, "E_SCHEMA"),
    ("hedge.integer.solve", {"a": [[1.0]], "b": [1.0], "weights": [1.0], "lot_sizes": [1.0],
                             "lower_lots": [0.5]}, "E_SCHEMA"),
    ("hedge.greeks.neutralise", {"spot": 100.0, "rate": 0.0, "dividend_yield": 0.0,
                                 "volatility": 0.2, "portfolio": [1], "hedges": [],
                                 "targets": []}, "E_SCHEMA"),
    ("hedge.greeks.neutralise", {"spot": 100.0, "rate": 0.0, "dividend_yield": 0.0,
                                 "volatility": 0.2, "portfolio": [], "hedges": [],
                                 "targets": ["THETA"]}, "E_SCHEMA"),
    ("hedge.beta.futures", {"portfolio_value": 1.0, "portfolio_beta": 0.0, "target_beta": 1.0,
                            "futures_price": 1.0, "multiplier": 1.0, "rounding": "UP"},
     "E_SCHEMA"),
])
def test_cli_schema(operation: str, inputs: dict[str, Any], expected: str) -> None:
    assert cli_code(operation, inputs) == expected


def test_cli_limits_follow_ruling_i4() -> None:
    wide = [[1.0] * 13]
    assert cli_code("hedge.integer.solve", {"a": wide, "b": [1.0], "weights": [1.0],
                                            "lot_sizes": [1.0] * 13}) == "E_LIMIT"
    assert cli_code("hedge.qp.solve", {"a": [[1.0] * 201], "b": [1.0],
                                       "weights": [1.0]}) == "E_LIMIT"
    assert cli_code("hedge.qp.solve", {"a": [[1.0]] * 1001, "b": [1.0] * 1001,
                                       "weights": [1.0] * 1001}) == "E_LIMIT"
    assert cli_code("hedge.qp.solve", {"a": [[1.0]], "b": [1.0], "weights": [1.0],
                                       "eq_matrix": [[1.0]] * 201,
                                       "eq_rhs": [0.0] * 201}) == "E_LIMIT"
    hedge = {"instrument": "UNDERLYING"}
    assert cli_code("hedge.greeks.neutralise", {
        "spot": 100.0, "rate": 0.0, "dividend_yield": 0.0, "volatility": 0.2, "portfolio": [],
        "hedges": [hedge] * 4, "targets": ["DELTA"] * 4}) == "E_LIMIT"
    assert cli_code("hedge.residual.report", {"a": [[1.0]], "b": [1.0], "x": [1.0],
                                              "covariance": [[1.0] * 1001] * 1001}) == "E_LIMIT"
    assert cli_code("hedge.minvar.ratio", {"covariance": [[1.0] * 202] * 202}) == "E_LIMIT"


def test_cli_limit_comes_before_the_finite_rule() -> None:
    assert cli_code("hedge.integer.solve", {"a": [[math.nan] * 13], "b": [1.0], "weights": [1.0],
                                            "lot_sizes": [1.0] * 13}) == "E_LIMIT"
    assert cli_code("hedge.beta.futures", {"portfolio_value": 1.0, "portfolio_beta": math.inf,
                                           "target_beta": 0.0, "futures_price": 1.0,
                                           "multiplier": 1.0}) == "E_DOMAIN"
