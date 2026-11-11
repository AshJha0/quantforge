"""Stage I waves 3 and 4a: the cross-asset hedge (08-hedging/cross-asset-hedge.md, rulings I-20
to I-23) and costs, margin and the risk-against-cost frontier (08-hedging/hedge-costs-and-frontier.md,
rulings I-24 to I-28)."""
import itertools
import math
from typing import Any

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from scipy.optimize import minimize

from quantforge_core import cross_asset_hedge as xa
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


# ----- hedge.crossasset.solve -----

TIMES, RATES = [1.0, 2.0, 5.0, 10.0], [0.03, 0.032, 0.035, 0.037]
MARKET = (100.0, 0.01, 0.2)


def bond(t: float, notional: float = 100.0) -> tuple[str, dict[str, float]]:
    return "ZCB", {"expiry_years": t, "notional": notional}


def solve(book: Any, hedges: Any, weights: Any = None, ridge: float = 0.0,
          times: Any = TIMES, rates: Any = RATES) -> dict[str, Any]:
    w = weights if weights is not None else [1.0] * (1 + len(times))
    return xa.crossasset_solve(*MARKET, times, rates, book, hedges, w, ridge)


BOOK = [("CALL", {"strike": 100.0, "expiry_years": 3.0, "quantity": -100.0}),
        ("FORWARD", {"strike": 95.0, "expiry_years": 7.0, "quantity": 50.0})]
SQUARE = [("FORWARD", {"strike": 100.0, "expiry_years": 1.5}), bond(1.0), bond(2.0), bond(5.0),
          bond(10.0)]


def test_zero_curve_is_flat_then_linear() -> None:
    assert xa._zero(TIMES, RATES, 0.5) == 0.03
    assert xa._zero(TIMES, RATES, 3.5) == pytest.approx(0.0335, rel=1e-14)
    assert xa._zero(TIMES, RATES, 10.0) == 0.037
    assert code(xa._zero, TIMES, RATES, 10.5) == "E_INPUT"


def test_risks_are_the_half_differences_of_the_spec() -> None:
    keys = {"strike": 100.0, "expiry_years": 3.0}
    risks = xa._risks("CALL", keys, *MARKET, TIMES, RATES)

    def value(s: float, z: list[float]) -> float:
        return xa._value("CALL", keys, s, 0.01, 0.2, TIMES, z)

    assert risks[0] == (value(101.0, RATES) - value(99.0, RATES)) / 2
    up, down = list(RATES), list(RATES)
    up[2] += 1e-4
    down[2] -= 1e-4
    assert risks[3] == (value(100.0, up) - value(100.0, down)) / 2
    assert risks[1] == 0.0  # a 3-year maturity sits between pillars 2 and 3
    assert risks[4] == 0.0
    put = xa._value("PUT", keys, 100.0, 0.01, 0.2, TIMES, RATES)
    call = value(100.0, RATES)
    df = math.exp(-xa._zero(TIMES, RATES, 3.0) * 3.0)
    assert call - put == pytest.approx(100.0 * math.exp(-0.03) - 100.0 * df, rel=1e-12)


def test_maturity_before_the_first_pillar_loads_pillar_one_only() -> None:
    risks = xa._risks("ZCB", {"expiry_years": 0.5, "notional": 100.0}, *MARKET, TIMES, RATES)
    assert risks[0] == 0.0 and risks[1] < 0 and risks[2:] == [0.0, 0.0, 0.0]


def test_property_square_regular_hedge_leaves_no_residual() -> None:
    out = solve(BOOK, SQUARE)
    scale = max(map(abs, out["book_risk"]))
    assert all(abs(v) <= 1e-10 * scale for v in out["residual_risk"])
    assert out["objective"] <= 1e-18 * scale * scale


def test_property_bond_book_has_no_equity_risk() -> None:
    out = solve([("ZCB", {"expiry_years": 4.0, "notional": 1e6, "quantity": 1.0})],
                [bond(2.0), bond(5.0)])
    assert out["book_risk"][0] == 0.0
    assert out["residual_risk"][0] == 0.0


@settings(max_examples=30, deadline=None)
@given(st.floats(0.01, 100.0), st.lists(st.floats(0.2, 5.0), min_size=5, max_size=5))
def test_property_weight_scaling_leaves_positions(factor: float, weights: list[float]) -> None:
    hedges = [("UNDERLYING", {}), bond(2.0), bond(10.0)]
    one = solve(BOOK, hedges, weights)
    two = solve(BOOK, hedges, [factor * w for w in weights])
    assert np.allclose(one["positions"], two["positions"], rtol=1e-9, atol=1e-12)


def test_crossasset_matches_weighted_least_squares() -> None:
    hedges = [("UNDERLYING", {}), bond(2.0), bond(10.0)]
    weights = [4.0, 1.0, 2.0, 1.0, 0.5]
    out = solve(BOOK, hedges, weights)
    a = np.array([xa._risks(k, v, *MARKET, TIMES, RATES) for k, v in hedges]).T
    root = np.sqrt(weights)
    ref = np.linalg.lstsq(a * root[:, None], -np.asarray(out["book_risk"]) * root,
                          rcond=None)[0]
    assert np.allclose(out["positions"], ref, rtol=1e-10)


@pytest.mark.parametrize(("change", "expected"), [
    ({"times": [], "rates": []}, "E_INPUT"),
    ({"rates": RATES[:3]}, "E_INPUT"),
    ({"times": [1.0, 1.0, 5.0, 10.0]}, "E_INPUT"),
    ({"times": [0.0, 2.0, 5.0, 10.0]}, "E_INPUT"),
    ({"hedges": [("ZCB", {"expiry_years": 2.0, "notional": 1.0, "strike": 1.0})]}, "E_INPUT"),
    ({"hedges": [("UNDERLYING", {"expiry_years": 1.0})]}, "E_INPUT"),
    ({"book": [("UNDERLYING", {})]}, "E_INPUT"),
    ({"book": []}, "E_INPUT"),
    ({"hedges": []}, "E_INPUT"),
    ({"weights": [1.0] * 4}, "E_INPUT"),
    ({"hedges": [bond(11.0)]}, "E_INPUT"),
    ({"weights": [1.0, 1.0, 0.0, 1.0, 1.0]}, "E_DOMAIN"),
    ({"ridge": -1.0}, "E_DOMAIN"),
    ({"hedges": [bond(2.0, 0.0)]}, "E_DOMAIN"),
    ({"hedges": [("CALL", {"strike": -1.0, "expiry_years": 1.0})]}, "E_DOMAIN"),
    ({"hedges": [bond(2.0), bond(2.0)]}, "E_SINGULAR"),
    ({"hedges": [("UNDERLYING", {}), ("UNDERLYING", {})]}, "E_SINGULAR"),
])
def test_crossasset_checks(change: dict[str, Any], expected: str) -> None:
    args: dict[str, Any] = {"book": BOOK, "hedges": [("UNDERLYING", {})]}
    args.update(change)
    assert code(solve, **args) == expected


def test_crossasset_domain_and_cli() -> None:
    assert code(xa.crossasset_solve, 0.0, 0.01, 0.2, TIMES, RATES, BOOK, [("UNDERLYING", {})],
                [1.0] * 5) == "E_DOMAIN"
    assert code(xa.crossasset_solve, 100.0, 0.01, 0.0, TIMES, RATES, BOOK, [("UNDERLYING", {})],
                [1.0] * 5) == "E_DOMAIN"
    inputs: dict[str, Any] = {
        "spot": 100.0, "dividend_yield": 0.01, "volatility": 0.2,
        "curve": {"times": TIMES, "zero_rates": RATES},
        "book": [{"instrument": "FORWARD", "strike": 95.0, "expiry_years": 7.0, "quantity": 1.0}],
        "hedges": [{"instrument": "UNDERLYING"}], "weights": [1.0] * 5}
    assert len(execute("hedge.crossasset.solve", inputs)["positions"]) == 1
    with pytest.raises(QfError) as caught:
        execute("hedge.crossasset.solve", {**inputs, "curve": {"times": [1.0] * 101,
                                                               "zero_rates": [0.0] * 101}})
    assert caught.value.code == "E_LIMIT"


# ----- hedge.qp.solve with costs and margin -----

def split_reference(a: Any, b: Any, w: Any, spread: Any, impact: Any, weight: float,
                    margin: Any = None, limit: float = 0.0, lower: Any = None,
                    upper: Any = None, eq: Any = None, rhs: Any = None) -> np.ndarray:
    """SciPy SLSQP on the split form x = p - q, where every cost and the margin are smooth."""
    a, b, w = (np.asarray(v, dtype=float) for v in (a, b, w))
    n = a.shape[1]
    spread, impact = np.asarray(spread, dtype=float), np.asarray(impact, dtype=float)

    def f(z: np.ndarray) -> float:
        x = z[:n] - z[n:]
        r = a @ x + b
        return float(w @ (r * r) + weight * (spread @ (z[:n] + z[n:]) + impact @ (x * x)))

    cons: list[dict[str, Any]] = []
    if margin is not None:
        m = np.asarray(margin, dtype=float)
        cons.append({"type": "ineq", "fun": lambda z: limit - m @ (z[:n] + z[n:])})
    if eq is not None:
        e = np.asarray(eq, dtype=float)
        cons.append({"type": "eq", "fun": lambda z: e @ (z[:n] - z[n:]) - np.asarray(rhs)})
    for j in range(n):
        if lower is not None and lower[j] is not None:
            cons.append({"type": "ineq", "fun": lambda z, j=j: z[j] - z[n + j] - lower[j]})
        if upper is not None and upper[j] is not None:
            cons.append({"type": "ineq", "fun": lambda z, j=j: upper[j] - z[j] + z[n + j]})
    res = minimize(f, np.zeros(2 * n), method="SLSQP", bounds=[(0, None)] * (2 * n),
                   constraints=cons, options={"ftol": 1e-15, "maxiter": 1000})
    return res.x[:n] - res.x[n:]


def test_costly_instrument_is_left_out_exactly() -> None:
    out = hs.qp_solve(A3, B3, W3, half_spreads=[0.01, 50.0, 0.01])
    assert out["x"][1] == 0.0
    ref = split_reference(A3, B3, W3, [0.01, 50.0, 0.01], [0.0] * 3, 1.0)
    assert np.allclose(out["x"], ref, atol=1e-6)
    assert out["objective"] == pytest.approx(out["risk"] + out["cost"], rel=1e-15)


@pytest.mark.parametrize("kwargs", [
    {"half_spreads": [0.3, 0.1, 0.2]},
    {"half_spreads": [0.3, 0.1, 0.2], "impact": [0.5, 0.2, 1.0], "cost_weight": 2.0},
    {"half_spreads": [0.3, 0.1, 0.2], "lower": [None, -0.1, None], "upper": [0.4, None, None]},
    {"margin_rates": [1.0, 2.0, 0.5], "margin_limit": 1.0},
    {"half_spreads": [0.1, 0.1, 0.1], "margin_rates": [1.0, 1.0, 1.0], "margin_limit": 0.8,
     "eq_matrix": [[1.0, 1.0, 1.0]], "eq_rhs": [0.2]},
])
def test_costed_qp_agrees_with_scipy_on_the_split_form(kwargs: dict[str, Any]) -> None:
    out = hs.qp_solve(A3, B3, W3, **kwargs)
    ref = split_reference(A3, B3, W3, kwargs.get("half_spreads", [0.0] * 3),
                          kwargs.get("impact", [0.0] * 3), kwargs.get("cost_weight", 1.0),
                          kwargs.get("margin_rates"), kwargs.get("margin_limit", 0.0),
                          kwargs.get("lower"), kwargs.get("upper"), kwargs.get("eq_matrix"),
                          kwargs.get("eq_rhs"))
    assert np.allclose(out["x"], ref, atol=1e-6)
    if "margin_rates" in kwargs:
        assert out["margin"] <= kwargs["margin_limit"] * (1 + 1e-12)


def test_property_zero_cost_weight_is_the_wave1_answer() -> None:
    plain = hs.qp_solve(A3, B3, W3, lower=[None, 0.0, None])
    costed = hs.qp_solve(A3, B3, W3, lower=[None, 0.0, None], half_spreads=[1.0, 1.0, 1.0],
                         impact=[2.0, 2.0, 2.0], cost_weight=0.0)
    assert costed["x"] == plain["x"]
    assert costed["risk"] == costed["objective"] == plain["objective"]
    assert set(plain) == {"x", "residual", "objective", "rank"}
    assert set(costed) == {"x", "residual", "objective", "rank", "risk", "cost"}


@settings(max_examples=30, deadline=None)
@given(st.floats(0.05, 3.0), st.lists(st.floats(0.2, 3.0), min_size=3, max_size=3))
def test_property_active_margin_equals_the_limit(fraction: float, rates: list[float]) -> None:
    free = hs.qp_solve(A3, B3, W3)
    full = math.fsum(r * abs(v) for r, v in zip(rates, free["x"], strict=True))
    limit = fraction * full
    out = hs.qp_solve(A3, B3, W3, margin_rates=rates, margin_limit=limit)
    if fraction < 1:
        assert out["margin"] == pytest.approx(limit, rel=1e-12)
    else:
        assert np.allclose(out["x"], free["x"], rtol=1e-12, atol=1e-15)


def test_impact_regularises_and_spread_does_not() -> None:
    a = [[1.0, 1.0], [0.5, 0.5]]
    assert code(hs.qp_solve, a, [1.0, 1.0], [1.0, 1.0], half_spreads=[0.1, 0.1]) == "E_SINGULAR"
    out = hs.qp_solve(a, [1.0, 1.0], [1.0, 1.0], impact=[0.1, 0.1])
    assert out["x"][0] == pytest.approx(out["x"][1], rel=1e-12)
    assert out["rank"] == 2


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({"half_spreads": [0.1]}, "E_INPUT"),
    ({"impact": [0.1, 0.1, 0.1, 0.1]}, "E_INPUT"),
    ({"margin_rates": [1.0, 1.0, 1.0]}, "E_INPUT"),
    ({"margin_limit": 1.0}, "E_INPUT"),
    ({"half_spreads": [0.1] * 3, "singular": "MIN_NORM"}, "E_INPUT"),
    ({"half_spreads": [0.1, -0.1, 0.1]}, "E_DOMAIN"),
    ({"impact": [0.1, -0.1, 0.1]}, "E_DOMAIN"),
    ({"half_spreads": [0.1] * 3, "cost_weight": -1.0}, "E_DOMAIN"),
    ({"margin_rates": [1.0, -1.0, 1.0], "margin_limit": 1.0}, "E_DOMAIN"),
    ({"margin_rates": [1.0, 1.0, 1.0], "margin_limit": -1.0}, "E_DOMAIN"),
    ({"margin_rates": [1.0, 1.0, 1.0], "margin_limit": 0.5, "lower": [1.0, None, None]},
     "E_INFEASIBLE"),
    ({"margin_rates": [1.0, 1.0, 1.0], "margin_limit": 0.5, "eq_matrix": [[1.0, 1.0, 1.0]],
      "eq_rhs": [2.0]}, "E_INFEASIBLE"),
    ({"half_spreads": [0.1] * 3, "eq_matrix": [[1.0, 1.0, 0.0]], "eq_rhs": [5.0],
      "upper": [1.0, 1.0, None]}, "E_INFEASIBLE"),
])
def test_costed_checks(kwargs: dict[str, Any], expected: str) -> None:
    assert code(hs.qp_solve, A3, B3, W3, **kwargs) == expected


def test_margin_limit_zero_keeps_unmargined_instruments() -> None:
    out = hs.qp_solve(A3, B3, W3, margin_rates=[1.0, 0.0, 1.0], margin_limit=0.0)
    assert out["x"][0] == 0.0 and out["x"][2] == 0.0 and out["x"][1] != 0.0


# ----- hedge.frontier.solve -----

@settings(max_examples=20, deadline=None)
@given(st.lists(st.floats(0.0, 0.5), min_size=3, max_size=3),
       st.lists(st.floats(0.0, 2.0), min_size=3, max_size=3))
def test_property_frontier_is_monotone(spread: list[float], impact: list[float]) -> None:
    assume(any(spread) or any(impact))
    weights = [0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 20.0]
    out = hs.frontier_solve(A3, B3, W3, weights, half_spreads=spread, impact=impact)
    risks = [p["risk"] for p in out["points"]]
    costs = [p["cost"] for p in out["points"]]
    assert all(q >= p * (1 - 1e-9) - 1e-12 for p, q in itertools.pairwise(risks))
    assert all(q <= p * (1 + 1e-9) + 1e-12 for p, q in itertools.pairwise(costs))
    assert [p["cost_weight"] for p in out["points"]] == weights


@pytest.mark.parametrize(("args", "kwargs", "expected"), [
    ([1.0, 0.5], {"half_spreads": [0.1] * 3}, "E_INPUT"),
    ([1.0, 1.0], {"half_spreads": [0.1] * 3}, "E_INPUT"),
    ([], {"half_spreads": [0.1] * 3}, "E_INPUT"),
    ([1.0], {}, "E_INPUT"),
    ([1.0], {"half_spreads": [0.1] * 3, "cost_weight": 1.0}, "E_INPUT"),
    ([-1.0, 1.0], {"half_spreads": [0.1] * 3}, "E_DOMAIN"),
    ([0.5, 1.0], {"half_spreads": [0.1] * 3, "margin_rates": [1.0] * 3, "margin_limit": 0.1,
                  "lower": [1.0, None, None]}, "E_INFEASIBLE"),
])
def test_frontier_checks(args: list[float], kwargs: dict[str, Any], expected: str) -> None:
    assert code(hs.frontier_solve, A3, B3, W3, args, **kwargs) == expected


def test_frontier_cli_and_limit() -> None:
    inputs = {"a": A3, "b": B3, "weights": W3, "half_spreads": [0.1, 0.2, 0.3],
              "cost_weights": [0.0, 1.0]}
    out = execute("hedge.frontier.solve", inputs)
    assert len(out["points"]) == 2
    with pytest.raises(QfError) as caught:
        execute("hedge.frontier.solve", {**inputs, "cost_weights": [float(k) for k in range(51)]})
    assert caught.value.code == "E_LIMIT"
    out = execute("hedge.qp.solve", {"a": A3, "b": B3, "weights": W3, "margin_rates": [1.0] * 3,
                                     "margin_limit": 0.5})
    assert out["margin"] == pytest.approx(0.5, rel=1e-12)
