"""Invariants of the stage I hedge solvers (08-hedging/hedge-solvers.md and
hedge-costs-and-frontier.md): scale and permutation invariance, the subgradient optimality test
of the costed QP, and integer lots never beating the relaxed problem."""
import math
from typing import Any

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from quantforge_core import hedge_solvers as hs
from quantforge_core.errors import QfError

unit = st.integers(-20, 20).map(lambda v: v / 10)
positive = st.integers(1, 30).map(lambda v: v / 10)


@st.composite
def problems(draw: st.DrawFn, max_n: int = 4) -> dict[str, Any]:
    n = draw(st.integers(1, max_n))
    m = draw(st.integers(n, n + 3))
    return {"a": [[draw(unit) for _ in range(n)] for _ in range(m)],
            "b": [draw(unit) for _ in range(m)],
            "weights": [draw(positive) for _ in range(m)]}


def solve(**kwargs: Any) -> dict[str, Any]:
    try:
        return hs.qp_solve(**kwargs)
    except QfError as err:
        assume(err.code not in ("E_SINGULAR", "E_INFEASIBLE"))
        raise


@settings(max_examples=60, deadline=None)
@given(problems(), st.sampled_from([0.01, 0.5, 7.0, 1e3]))
def test_weight_scaling_leaves_x(p: dict[str, Any], c: float) -> None:
    one = solve(**p)
    two = solve(**{**p, "weights": [c * w for w in p["weights"]]})
    assert np.allclose(one["x"], two["x"], rtol=1e-9, atol=1e-11)
    assert two["objective"] == pytest.approx(c * one["objective"], rel=1e-9, abs=1e-12)


@settings(max_examples=60, deadline=None)
@given(problems(), st.sampled_from([-3.0, 0.25, 4.0]))
def test_exposure_scaling_scales_x(p: dict[str, Any], c: float) -> None:
    one = solve(**p)
    two = solve(**{**p, "b": [c * v for v in p["b"]]})
    assert np.allclose(two["x"], [c * v for v in one["x"]], rtol=1e-9, atol=1e-11)


@settings(max_examples=60, deadline=None)
@given(problems(), st.data())
def test_instrument_units_rescale_positions(p: dict[str, Any], data: st.DataObject) -> None:
    """Quoting instrument j in units s_j times larger divides its position by s_j (no ridge)."""
    n = len(p["a"][0])
    s = [data.draw(st.sampled_from([0.1, 2.0, 25.0])) for _ in range(n)]
    one = solve(**p)
    two = solve(**{**p, "a": [[row[j] * s[j] for j in range(n)] for row in p["a"]]})
    assert np.allclose([two["x"][j] * s[j] for j in range(n)], one["x"], rtol=1e-8, atol=1e-10)


@settings(max_examples=60, deadline=None)
@given(problems(), st.data())
def test_permutations_of_instruments_and_factors(p: dict[str, Any],
                                                 data: st.DataObject) -> None:
    n, m = len(p["a"][0]), len(p["a"])
    cols = data.draw(st.permutations(range(n)))
    rows = data.draw(st.permutations(range(m)))
    lower = [data.draw(st.one_of(st.none(), unit)) for _ in range(n)]
    upper = [None if lo is None else lo + 1.0 for lo in lower]
    one = solve(**p, lower=lower, upper=upper, half_spreads=[0.05] * n)
    two = solve(a=[[p["a"][r][c] for c in cols] for r in rows], b=[p["b"][r] for r in rows],
                weights=[p["weights"][r] for r in rows], lower=[lower[c] for c in cols],
                upper=[upper[c] for c in cols], half_spreads=[0.05] * n)
    assert np.allclose(two["x"], [one["x"][c] for c in cols], rtol=1e-9, atol=1e-11)
    assert two["objective"] == pytest.approx(one["objective"], rel=1e-10, abs=1e-12)


@settings(max_examples=60, deadline=None)
@given(problems(), st.data())
def test_costed_qp_meets_the_subgradient_conditions(p: dict[str, Any],
                                                    data: st.DataObject) -> None:
    """At the answer: g_j + c_j sign(x_j) = 0 where x_j != 0, |g_j| <= c_j where x_j = 0
    (no bounds, no margin), with g the gradient of the smooth part [spec, Solution]."""
    n = len(p["a"][0])
    spread = [data.draw(st.sampled_from([0.0, 0.1, 0.5, 3.0])) for _ in range(n)]
    impact = [data.draw(st.sampled_from([0.0, 0.2])) for _ in range(n)]
    out = solve(**p, half_spreads=spread, impact=impact)
    a, b, w, x = (np.asarray(v, dtype=float) for v in (p["a"], p["b"], p["weights"], out["x"]))
    g = 2 * (a.T @ (w * (a @ x + b))) + 2 * np.asarray(impact) * x
    scale = max(1.0, float(np.abs(2 * a.T @ (w * b)).max()), max(spread))
    for j in range(n):
        if x[j] != 0:
            assert abs(g[j] + spread[j] * math.copysign(1.0, x[j])) <= 1e-9 * scale
        else:
            assert abs(g[j]) <= spread[j] + 1e-9 * scale


@settings(max_examples=40, deadline=None)
@given(problems(max_n=3), st.data())
def test_integer_lots_never_beat_the_bounded_relaxation(p: dict[str, Any],
                                                        data: st.DataObject) -> None:
    n = len(p["a"][0])
    lots = [data.draw(st.sampled_from([0.5, 1.0, 3.0])) for _ in range(n)]
    lower = [data.draw(st.one_of(st.none(), st.integers(-3, 0))) for _ in range(n)]
    upper = [data.draw(st.one_of(st.none(), st.integers(0, 3))) for _ in range(n)]
    big = {**p, "b": [10 * v for v in p["b"]]}
    try:
        out = hs.integer_solve(**big, lot_sizes=lots, ridge=0.01, lower_lots=lower,
                               upper_lots=upper)
    except QfError as err:
        assume(err.code != "E_SINGULAR")
        raise
    relaxed = hs.qp_solve(**big, ridge=0.01,
                          lower=[None if v is None else v * s for v, s in zip(lower, lots)],
                          upper=[None if v is None else v * s for v, s in zip(upper, lots)])
    assert out["continuous_objective"] == pytest.approx(relaxed["objective"], rel=1e-12)
    assert out["objective"] >= relaxed["objective"] * (1 - 1e-12) - 1e-12
    assert all((lo is None or v >= lo) and (hi is None or v <= hi)
               for v, lo, hi in zip(out["lots"], lower, upper))
