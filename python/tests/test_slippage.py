"""Stage I wave 4d: hedge slippage (08-hedging/hedge-slippage.md, rulings I-36 to I-38)."""
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core.errors import QfError
from quantforge_core.slippage import slippage_report

BUY = (1000.0, 100.0, 101.5, 0.02, 0.0001, [(400.0, 100.05), (600.0, 100.12)])
SELL = (-500.0, 50.0, 49.0, 0.01, 0.0, [(-200.0, 49.9)])


def test_one_buy_fully_filled() -> None:
    row = slippage_report([BUY])["orders"][0]
    assert row["filled_quantity"] == 1000.0
    assert row["average_price"] == pytest.approx(100.092, rel=1e-15)
    assert row["execution_cost"] == pytest.approx(92.0, rel=1e-12)
    assert row["opportunity_cost"] == 0.0
    assert row["model_cost"] == pytest.approx(120.0, rel=1e-15)


def test_partial_sell_has_opportunity_cost() -> None:
    row = slippage_report([SELL])["orders"][0]
    assert row["execution_cost"] == pytest.approx(20.0, rel=1e-12)  # sold 0.1 below decision
    assert row["opportunity_cost"] == pytest.approx(300.0, rel=1e-15)  # 300 unsold, price fell 1


def test_nothing_filled_has_a_null_average_price() -> None:
    row = slippage_report([(100.0, 10.0, 11.0, 0.0, 0.0, [])])["orders"][0]
    assert row["average_price"] is None
    assert row["shortfall"] == row["opportunity_cost"] == 100.0


fills = st.lists(st.tuples(st.integers(1, 100), st.integers(9000, 11000)), max_size=5)


@settings(max_examples=60, deadline=None)
@given(st.lists(st.tuples(st.booleans(), fills, st.integers(0, 50)), min_size=1, max_size=4))
def test_property_identities_and_totals(raw: list[tuple[bool, list[Any], int]]) -> None:
    orders = []
    for buy, f, extra in raw:
        sign = 1.0 if buy else -1.0
        size = sum(q for q, _ in f) + extra + 1
        orders.append((sign * size, 100.0, 101.0, 0.01, 1e-4,
                       [(sign * q, p / 100) for q, p in f]))
    out = slippage_report(orders)
    for row in out["orders"]:
        assert row["shortfall"] == pytest.approx(
            row["execution_cost"] + row["opportunity_cost"], rel=1e-12, abs=1e-9)
        assert row["slippage"] == pytest.approx(
            row["execution_cost"] - row["model_cost"], rel=1e-12, abs=1e-9)
    for key, value in out["total"].items():
        assert value == pytest.approx(sum(r[key] for r in out["orders"]), rel=1e-12, abs=1e-9)


@pytest.mark.parametrize(("orders", "expected"), [
    ([], "E_INPUT"),
    ([(0.0, 100.0, 100.0, 0.0, 0.0, [])], "E_INPUT"),
    ([(100.0, 100.0, 100.0, 0.0, 0.0, [(-10.0, 100.0)])], "E_INPUT"),
    ([(100.0, 100.0, 100.0, 0.0, 0.0, [(0.0, 100.0)])], "E_INPUT"),
    ([(100.0, 100.0, 100.0, 0.0, 0.0, [(60.0, 100.0), (50.0, 100.0)])], "E_INPUT"),
    ([(100.0, 0.0, 100.0, 0.0, 0.0, [])], "E_DOMAIN"),
    ([(100.0, 100.0, -1.0, 0.0, 0.0, [])], "E_DOMAIN"),
    ([(100.0, 100.0, 100.0, 0.0, 0.0, [(10.0, 0.0)])], "E_DOMAIN"),
    ([(100.0, 100.0, 100.0, -0.1, 0.0, [])], "E_DOMAIN"),
    ([(100.0, 100.0, 100.0, 0.0, -0.1, [])], "E_DOMAIN"),
])
def test_slippage_checks(orders: list[Any], expected: str) -> None:
    with pytest.raises(QfError) as caught:
        slippage_report(orders)
    assert caught.value.code == expected


def test_slippage_cli_null_average_and_limits() -> None:
    from quantforge_core.cli import operations  # noqa: F401 - registers the verbs
    from quantforge_core.cli.registry import execute

    order = {"quantity": 10.0, "decision_price": 5.0, "final_price": 6.0, "half_spread": 0.0,
             "impact": 0.0, "fills": []}
    out = execute("hedge.slippage.report", {"orders": [order]})
    assert out["orders"][0]["average_price"] is None
    for inputs, expected in (({"orders": [order] * 10_001}, "E_LIMIT"),
                             ({"orders": [{**order, "fills": [{"quantity": 1.0}]}]},
                              "E_SCHEMA")):
        with pytest.raises(QfError) as caught:
            execute("hedge.slippage.report", inputs)
        assert caught.value.code == expected
