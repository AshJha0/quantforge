"""Stage I waves 4b and 4c: the dynamic delta-hedge backtest and hedge effectiveness
(08-hedging/dynamic-hedge-and-effectiveness.md, rulings I-29 to I-32) and instrument selection
(08-hedging/instrument-selection.md, rulings I-33 to I-35)."""
import itertools
import math
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core import dynamic_hedge as dh
from quantforge_core import hedge_solvers as hs
from quantforge_core.cli import operations  # noqa: F401 - registers the verbs
from quantforge_core.cli.registry import execute
from quantforge_core.errors import QfError


def code(f: Any, *args: Any, **kwargs: Any) -> str:
    with pytest.raises(QfError) as caught:
        f(*args, **kwargs)
    return caught.value.code


# ----- hedge.effectiveness -----

def test_property_perfect_offset() -> None:
    item = [1.0, -2.0, 0.5, 3.0, -0.25]
    out = dh.effectiveness(item, [-v for v in item])
    assert out == {"dollar_offset": 1.0, "regression_slope": -1.0, "regression_r2": 1.0,
                   "variance_reduction": 1.0}


@settings(max_examples=50, deadline=None)
@given(st.lists(st.tuples(st.integers(-100, 100), st.integers(-100, 100)), min_size=3,
                max_size=30))
def test_effectiveness_matches_numpy(pairs: list[tuple[int, int]]) -> None:
    x = [p / 10 for p, _ in pairs]
    y = [q / 10 for _, q in pairs]
    try:
        out = dh.effectiveness(x, y)
    except QfError as err:
        assert err.code == "E_DOMAIN"
        assert math.fsum(x) == 0 or np.var(x) == 0 or np.var(y) == 0
        return
    cov = np.cov(x, y, ddof=1)
    assert out["regression_slope"] == pytest.approx(cov[0, 1] / cov[0, 0], rel=1e-9, abs=1e-12)
    assert out["regression_r2"] == pytest.approx(cov[0, 1] ** 2 / (cov[0, 0] * cov[1, 1]),
                                                 rel=1e-9, abs=1e-12)
    assert out["variance_reduction"] == pytest.approx(
        1 - np.var(np.add(x, y), ddof=1) / cov[0, 0], rel=1e-9, abs=1e-9)
    assert out["dollar_offset"] == pytest.approx(-sum(y) / sum(x), rel=1e-9)


@pytest.mark.parametrize(("x", "y", "expected"), [
    ([1.0, 2.0, 3.0], [1.0, 2.0], "E_INPUT"),
    ([1.0, 2.0], [1.0, 2.0], "E_INPUT"),
    ([1.0, -1.0, 0.0], [1.0, 2.0, 3.0], "E_DOMAIN"),
    ([1.0, 1.0, 1.0], [1.0, 2.0, 3.0], "E_DOMAIN"),
    ([1.0, 2.0, 3.0], [2.0, 2.0, 2.0], "E_DOMAIN"),
])
def test_effectiveness_checks(x: list[float], y: list[float], expected: str) -> None:
    assert code(dh.effectiveness, x, y) == expected


# ----- hedge.backtest.delta -----

TIMES = [k / 365 for k in range(31)]
SPOTS = [100.0 * math.exp(0.01 * math.sin(k) + 0.002 * k) for k in range(31)]


def run(**change: Any) -> dict[str, Any]:
    args: dict[str, Any] = {"option_type": "CALL", "strike": 100.0, "expiry_years": 30 / 365,
                            "quantity": -10.0, "rate": 0.03, "dividend_yield": 0.01,
                            "hedge_volatility": 0.2, "times": TIMES, "spots": SPOTS}
    args.update(change)
    return dh.backtest_delta(**args)


def test_replay_is_self_financing_from_zero() -> None:
    out = run()
    assert out["portfolio_values"][0] == 0.0
    assert out["option_values"][-1] == max(SPOTS[-1] - 100.0, 0.0)
    assert out["final_pnl"] == out["portfolio_values"][-1]
    assert len(out["shares"]) == len(TIMES) - 1
    assert out["shares"][0] == pytest.approx(10.0 * dh._value_delta(
        "CALL", SPOTS[0], 100.0, 30 / 365, 0.03, 0.01, 0.2)[1], rel=1e-15)


def test_replay_order_by_hand() -> None:
    """Four dates, the I-29 order written out: interest, dividends, mark, then rebalance."""
    times, spots = [0.0, 0.1, 0.2, 0.3], [100.0, 103.0, 98.0, 101.0]
    out = run(times=times, spots=spots, expiry_years=0.5, quantity=2.0, option_type="PUT")
    v = [dh._value_delta("PUT", s, 100.0, 0.5 - t, 0.03, 0.01, 0.2) for t, s in zip(times, spots)]
    h = [-2.0 * d for _, d in v[:3]]
    cash = -2.0 * v[0][0] - h[0] * 100.0
    pi = []
    for i in range(3):
        cash = cash * math.exp(0.03 * 0.1) + h[i] * spots[i] * (math.exp(0.01 * 0.1) - 1)
        pi.append(2.0 * v[i + 1][0] + h[i] * spots[i + 1] + cash)
        if i < 2:
            cash -= (h[i + 1] - h[i]) * spots[i + 1]
    assert np.allclose(out["portfolio_values"][1:], pi, rtol=1e-12, atol=1e-12)


def test_property_constant_spot_replay_is_the_time_decay(monkeypatch: Any) -> None:
    """Wave 4b handover, corrected: on a constant path with zero rates and dividends the replay
    ends at quantity (V_last - V_0). The hedge leg is zero only up to rounding there, so whether
    the statistics see an exactly zero variance is not pinned (SPEC_QUESTIONS I-Q4); they are
    stubbed out to test the replay alone."""
    spots = [100.0] * 31
    monkeypatch.setattr(dh, "effectiveness", lambda item, hedge: {})
    out = run(spots=spots, rate=0.0, dividend_yield=0.0)
    values = out["option_values"]
    assert out["final_pnl"] == pytest.approx(-10.0 * (values[-1] - values[0]), rel=1e-12)
    assert values[-1] == 0.0  # at the money at expiry


def test_backtest_effectiveness_is_the_shared_routine() -> None:
    out = run()
    item = [-10.0 * (b - a) for a, b in zip(out["option_values"], out["option_values"][1:],
                                            strict=False)]
    pi = out["portfolio_values"]
    hedge = [(pi[i + 1] - pi[i]) - item[i] for i in range(len(item))]
    stats = dh.effectiveness(item, hedge)
    assert {k: out[k] for k in stats} == stats
    assert out["regression_r2"] > 0.9


@pytest.mark.parametrize(("change", "expected"), [
    ({"spots": SPOTS[:-1]}, "E_INPUT"),
    ({"times": TIMES[:3], "spots": SPOTS[:3]}, "E_INPUT"),
    ({"times": [0.001, *TIMES[1:]]}, "E_INPUT"),
    ({"times": [0.0, 0.01, 0.01, *TIMES[3:]]}, "E_INPUT"),
    ({"expiry_years": 0.05}, "E_INPUT"),
    ({"spots": [0.0, *SPOTS[1:]]}, "E_DOMAIN"),
    ({"strike": 0.0}, "E_DOMAIN"),
    ({"hedge_volatility": 0.0}, "E_DOMAIN"),
    ({"quantity": 0.0}, "E_DOMAIN"),
])
def test_backtest_checks(change: dict[str, Any], expected: str) -> None:
    assert code(run, **change) == expected


def test_backtest_cli() -> None:
    out = execute("hedge.backtest.delta", {
        "option": {"type": "PUT", "strike": 100.0, "expiry_years": 0.2}, "quantity": 5.0,
        "rate": 0.02, "dividend_yield": 0.0, "hedge_volatility": 0.25, "times": TIMES[:10],
        "spots": SPOTS[:10]})
    assert len(out["portfolio_values"]) == 10
    with pytest.raises(QfError) as caught:
        execute("hedge.effectiveness", {"item_changes": [1.0, 2.0, "x"],
                                        "hedge_changes": [1.0, 2.0, 3.0]})
    assert caught.value.code == "E_SCHEMA"


# ----- hedge.select.solve -----

A = [[1.0, 0.2, 0.0, 0.5, 0.1], [0.3, 1.0, 0.4, 0.0, 0.2], [0.0, 0.5, 1.0, 0.3, 0.6],
     [0.2, 0.0, 0.3, 1.0, 0.4], [0.1, 0.3, 0.0, 0.2, 1.0]]
B = [-2.0, 1.0, -1.5, 0.8, 0.4]
W = [1.0, 2.0, 1.0, 0.5, 1.5]


def test_property_all_instruments_is_the_qp_answer_and_more_never_hurts() -> None:
    full = hs.qp_solve(A, B, W)
    best = [hs.select_solve(A, B, W, k)["objective"] for k in range(1, 6)]
    assert all(q <= p * (1 + 1e-12) for p, q in itertools.pairwise(best))
    out = hs.select_solve(A, B, W, 5)
    assert out["selected"] == [0, 1, 2, 3, 4]
    assert np.allclose(out["x"], full["x"], rtol=1e-12)


def test_selection_is_exhaustive() -> None:
    """The chosen pair is the best of every pair (golden hedgeselect_i-0009 pins a case where
    forward selection fails)."""
    out = hs.select_solve(A, B, W, 2)
    pairs = [(i, j) for i in range(5) for j in range(i + 1, 5)]
    best = min(pairs, key=lambda p: hs.qp_solve([[r[p[0]], r[p[1]]] for r in A], B, W)["objective"])
    assert out["selected"] == list(best)
    single = hs.select_solve(A, B, W, 1)
    assert out["objective"] <= single["objective"]


def test_selection_ties() -> None:
    sym = hs.select_solve([[1.0, 0.0], [0.0, 1.0]], [-1.0, -1.0], [1.0, 1.0], 1)
    assert sym["selected"] == [0] and sym["x"] == [1.0, 0.0]
    # A second instrument that adds nothing: the smaller subset wins.
    out = hs.select_solve([[1.0, 0.0], [0.0, 1.0]], [-1.0, 0.0], [1.0, 1.0], 2)
    assert out["selected"] == [0]


def test_selection_respects_bounds() -> None:
    out = hs.select_solve(A, B, W, 2, lower=[0.0] * 5)
    assert all(v >= 0 for v in out["x"])
    assert len(out["selected"]) <= 2


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({"max_instruments": 0}, "E_INPUT"),
    ({"max_instruments": 6}, "E_INPUT"),
    ({"extra_inputs": ["eq_matrix"]}, "E_INPUT"),
    ({"lower": [0.1, None, None, None, None]}, "E_DOMAIN"),
    ({"upper": [None, -0.1, None, None, None]}, "E_DOMAIN"),
    ({"weights": [1.0, -1.0, 1.0, 1.0, 1.0]}, "E_DOMAIN"),
    ({"lower": [None]}, "E_INPUT"),
    ({"a": [[1.0, 1.0, 0.0], [2.0, 2.0, 1.0]], "b": [1.0, 1.0], "weights": [1.0, 1.0]},
     "E_SINGULAR"),
])
def test_selection_checks(kwargs: dict[str, Any], expected: str) -> None:
    args: dict[str, Any] = {"a": A, "b": B, "weights": W, "max_instruments": 2}
    args.update(kwargs)
    assert code(hs.select_solve, **args) == expected


def test_selection_cli_and_limit() -> None:
    inputs: dict[str, Any] = {"a": A, "b": B, "weights": W, "max_instruments": 2}
    assert len(execute("hedge.select.solve", inputs)["selected"]) <= 2
    for extra, expected in (({"singular": "ERROR"}, "E_INPUT"),
                            ({"a": [[1.0] * 21] * 5}, "E_LIMIT")):
        with pytest.raises(QfError) as caught:
            execute("hedge.select.solve", {**inputs, **extra})
        assert caught.value.code == expected
