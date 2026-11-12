"""Rulings after the stage I builds (specifications/stage-i-rulings.md I-41 to I-50): one test
per behaviour the Python lane changed or confirmed."""
import math
from typing import Any

import pytest

from quantforge_core import dynamic_hedge as dh
from quantforge_core import hedge_solvers as hs
from quantforge_core.cli import operations  # noqa: F401 - registers the verbs
from quantforge_core.cli.registry import execute
from quantforge_core.errors import QfError

GREEKS: dict[str, Any] = {
    "spot": 100.0, "rate": 0.03, "dividend_yield": 0.01, "volatility": 0.25,
    "portfolio": [{"instrument": "CALL", "strike": 100.0, "expiry_years": 0.5,
                   "quantity": -1000.0}],
    "hedges": [{"instrument": "UNDERLYING"}], "targets": ["DELTA"]}


def cli_code(operation: str, inputs: dict[str, Any]) -> str:
    with pytest.raises(QfError) as caught:
        execute(operation, inputs)
    return caught.value.code


@pytest.mark.parametrize("change", [
    {"hedges": [{"instrument": "UNDERLYING", "quantity": 5.0}]},
    {"hedges": [{"instrument": "UNDERLYING", "notional": 1.0}]},
    {"portfolio": [{"instrument": "CALL", "strike": 100.0, "expiry_years": 0.5}]},
])
def test_i41_greek_instruments_have_fixed_keys(change: dict[str, Any]) -> None:
    assert cli_code("hedge.greeks.neutralise", {**GREEKS, **change}) == "E_INPUT"


def test_i42_unknown_targets_are_schema_errors() -> None:
    assert cli_code("hedge.greeks.neutralise", {**GREEKS, "targets": ["RHO"]}) == "E_SCHEMA"
    corr = {"spot1": 100.0, "spot2": 95.0, "rate": 0.03, "yield1": 0.01, "yield2": 0.02,
            "vol1": 0.25, "vol2": 0.2, "correlation": 0.6,
            "book": [{"instrument": "UNDERLYING_1", "quantity": 1.0}],
            "hedges": [{"instrument": "UNDERLYING_1"}], "targets": ["THETA"]}
    assert cli_code("hedge.correlation.neutralise", corr) == "E_SCHEMA"


def test_i43_zero_tests_are_relative() -> None:
    # A hedge leg of rounding size against a real item: var(y) <= 1e-20 var(x).
    with pytest.raises(QfError) as caught:
        dh.effectiveness([1.0, -2.0, 4.0], [1e-15, -1e-15, 2e-15])
    assert caught.value.code == "E_DOMAIN"
    # An item summing to rounding noise relative to its size.
    with pytest.raises(QfError) as caught:
        dh.effectiveness([0.1, 0.2, -0.30000000000000004], [1.0, 2.0, 3.0])
    assert caught.value.code == "E_DOMAIN"
    # A small but real hedge passes.
    assert dh.effectiveness([1.0, -2.0, 4.0], [-1e-6, 2e-6, -3e-6])["regression_r2"] > 0.9
    # The constant-spot backtest of I-43 (hedgebt_i-0016's shape) is E_DOMAIN.
    times = [k / 365 for k in range(10)]
    with pytest.raises(QfError) as caught:
        dh.backtest_delta("CALL", 100.0, 9 / 365, -100.0, 0.0, 0.0, 0.2, times, [100.0] * 10)
    assert caught.value.code == "E_DOMAIN"


def test_i44_rounding_below_zero_is_a_perfect_hedge() -> None:
    s = 0.04
    cov = [[s, 0.06], [0.06, 0.09]]  # rho = 1: hedged variance 0 up to rounding
    out = hs.minvar_ratio(cov)
    assert out["variance_after"] >= 0.0 and out["effectiveness"] == pytest.approx(1.0, abs=1e-12)
    with pytest.raises(QfError) as caught:
        hs.minvar_ratio([[s, 0.0601], [0.0601, 0.09]])
    assert caught.value.code == "E_NOT_POSITIVE_DEFINITE"


def test_i45_lot_sizes_longer_than_the_columns_is_e_input() -> None:
    inputs = {"a": [[1.0, 0.0], [0.0, 1.0]], "b": [1.0, -1.0], "weights": [1.0, 1.0],
              "lot_sizes": [1.0] * 13}
    assert cli_code("hedge.integer.solve", inputs) == "E_INPUT"
    assert cli_code("hedge.integer.solve", {**inputs, "a": [[1.0] * 13], "b": [1.0],
                                            "weights": [1.0]}) == "E_LIMIT"


@pytest.mark.parametrize(("operation", "inputs"), [
    ("hedge.qp.solve", {"a": [[1.0]], "b": [1.0], "weights": [1.0], "ridge": None}),
    ("hedge.beta.futures", {"portfolio_value": 1.0, "portfolio_beta": 0.0, "target_beta": 1.0,
                            "futures_price": 1.0, "multiplier": 1.0, "rounding": None}),
    ("hedge.backtest.delta", {"option": {"type": "CALL", "strike": 1.0, "expiry_years": 1.0,
                                         "note": None}, "quantity": 1.0}),
])
def test_i47_null_optional_keys_are_schema_errors(operation: str,
                                                  inputs: dict[str, Any]) -> None:
    assert cli_code(operation, inputs) == "E_SCHEMA"


def test_i47_null_stays_legal_inside_bounds() -> None:
    out = execute("hedge.qp.solve", {"a": [[1.0]], "b": [1.0], "weights": [1.0],
                                     "lower": [None], "upper": [None]})
    assert out["x"] == [-1.0]


def test_i49_lot_counts_beyond_two_to_the_52_are_e_limit() -> None:
    with pytest.raises(QfError) as caught:
        hs.integer_solve([[1.0]], [-(2.0 ** 60)], [1.0], [1.0])
    assert caught.value.code == "E_LIMIT"
    assert hs.integer_solve([[1.0]], [-(2.0 ** 40)], [1.0], [1.0])["lots"] == [2 ** 40]


def test_i50_one_order_keeps_the_general_array_limit() -> None:
    fill = {"quantity": 1.0, "price": 1.0}
    order = {"quantity": 2e5, "decision_price": 1.0, "final_price": 1.0, "half_spread": 0.0,
             "impact": 0.0, "fills": [fill] * 100_001}
    assert cli_code("hedge.slippage.report", {"orders": [order]}) == "E_LIMIT"
    assert math.isfinite(execute("hedge.slippage.report", {
        "orders": [{**order, "fills": [fill] * 10}]})["total"]["shortfall"])


def test_i53_selection_limits_the_number_of_subsets() -> None:
    a = [[1.0 if i == j else 0.1 for j in range(20)] for i in range(20)]
    base = {"a": a, "b": [-1.0] * 20, "weights": [1.0] * 20}
    assert cli_code("hedge.select.solve", {**base, "max_instruments": 7}) == "E_LIMIT"
    # 21 instruments is the I-35 limit, also before the rule checks.
    wide = {"a": [[1.0] * 21], "b": [1.0], "weights": [1.0], "max_instruments": 1}
    assert cli_code("hedge.select.solve", wide) == "E_LIMIT"
    small = execute("hedge.select.solve", {"a": [r[:6] for r in a[:6]], "b": [-1.0] * 6,
                                           "weights": [1.0] * 6, "max_instruments": 6})
    assert len(small["selected"]) <= 6

