"""Kill tests for `quantforge_core.equity_curves`, `xva` and `curve_fits` mutants that survived the
H-0 Actions run 44332353267 (conformance/mutation/python-h0-2026-11-18.md).

Error checks pin code and field (the CLI contract), not the message text. The value checks come
from the specifications: the borrow-rate bracket `[-0.5, 0.5]` (02-curves/equity-curves.md),
dividends with ex-date in `(as_of, end]` for a TRS (04-pricing/equity-index.md), and prices that
need only be positive (equity-curves.md, dividend-implied futures).
"""

import math
from datetime import date
from typing import Any

import pytest

from quantforge_core import curve_fits, equity_curves, xva
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError

AS_OF = date(2026, 6, 15)
FUND = CurveData(
    AS_OF,
    "LOG_LINEAR_DF",
    (date(2027, 6, 15), date(2036, 6, 15)),
    (math.exp(-0.04 * 365 / 365), math.exp(-0.04 * 3653 / 365)),
)


def _err(fn: Any, *args: Any) -> tuple[str, str | None]:
    with pytest.raises(QfError) as e:
        fn(*args)
    return e.value.code, e.value.field


# --- equity_curves ------------------------------------------------------------------------------


def test_equity_error_codes_and_fields() -> None:
    assert _err(equity_curves.borrow_implied, 100.0, FUND, [], AS_OF, 100.0) == (
        "E_DATE_ORDER",
        "expiry",
    )
    assert _err(equity_curves.index_dividends, 0.0, [], [], []) == ("E_DOMAIN", "divisor")
    period = (date(2026, 7, 1), date(2026, 12, 31))
    assert _err(equity_curves.index_dividends, 1.0, [], [period], []) == (
        "E_INPUT",
        "implied_period_points",
    )
    assert _err(equity_curves.rebalance, 0.0, [("A", 1.0, 10.0)], [("A", 1.0, 10.0)]) == (
        "E_DOMAIN",
        "divisor",
    )
    assert _err(
        equity_curves.trs_pv,
        100.0,
        FUND,
        0.0,
        [],
        date(2026, 1, 15),
        date(2027, 1, 15),
        100.0,
        1.0,
        0.0,
        "RECEIVE_EQUITY",
        None,
    ) == ("E_INPUT", "current_rate")


def test_rebalance_zero_new_capitalisation_is_a_domain_error() -> None:
    # New basket with no capitalisation: weights c / total are undefined.
    old = [("A", 10.0, 50.0)]
    new = [("A", 0.0, 50.0)]
    assert _err(equity_curves.rebalance, 5.0, old, new) == ("E_DOMAIN", "constituents")
    assert _err(equity_curves.rebalance, 5.0, [("A", 0.0, 50.0)], old) == (
        "E_DOMAIN",
        "constituents",
    )


def test_borrow_rate_outside_the_spec_bracket_is_not_bracketed() -> None:
    # F = S exp((r - b) t) on a flat 4% curve; b = 0.8 lies outside [-0.5, 0.5].
    expiry = date(2027, 6, 15)
    forward = 100.0 * math.exp((0.04 - 0.8) * 1.0)
    assert _err(equity_curves.borrow_implied, 100.0, FUND, [], expiry, forward)[0] == (
        "E_NOT_BRACKETED"
    )
    # Inside the bracket the same set-up solves.
    inside = 100.0 * math.exp((0.04 - 0.3) * 1.0)
    assert equity_curves.borrow_implied(100.0, FUND, [], expiry, inside) == pytest.approx(
        0.3, abs=1e-12
    )


def test_dividend_implied_accepts_a_positive_price_below_one() -> None:
    xs, _, yields = equity_curves.dividend_implied(0.9, FUND, 0.0, [(date(2027, 6, 15), 0.5)])
    assert len(xs) == 1 and math.isfinite(yields[0])


def test_trs_leaves_out_a_dividend_going_ex_on_as_of() -> None:
    args = (date(2026, 7, 15), date(2027, 1, 15), 100.0, 10.0, 0.001, "RECEIVE_EQUITY", None)
    base = equity_curves.trs_pv(100.0, FUND, 0.0, [], *args)
    on_as_of = equity_curves.trs_pv(100.0, FUND, 0.0, [(AS_OF, 2.0)], *args)
    assert on_as_of == pytest.approx(base, rel=0, abs=1e-12)
    inside = equity_curves.trs_pv(100.0, FUND, 0.0, [(date(2026, 9, 15), 2.0)], *args)
    assert inside[0] != pytest.approx(base[0], abs=1e-9)


# --- xva ----------------------------------------------------------------------------------------


def test_xva_error_fields() -> None:
    times = [0.5, 1.0]
    trades = [("S", [[1.0, 2.0]])]
    assert _err(xva.collateralised, times, trades, {}, 0.0) == ("E_DOMAIN", "pfe_quantile")
    name = xva.Name(0.01, 0.4)
    one = [1.0, 1.0]
    for key, im, spread, cap, hurdle in (
        ("im", [1.0], 0.01, None, None),
        ("capital", None, None, [1.0], 0.1),
    ):
        assert _err(
            xva.adjustments,
            times,
            one,
            one,
            one,
            name,
            name,
            0.0,
            0.0,
            False,
            im,
            spread,
            cap,
            hurdle,
        ) == ("E_INPUT", key)
    assert _err(xva.simm_ir_delta, [1.0], [1.0, 2.0], [[1.0]], 1.0) == ("E_INPUT", "sensitivities")
    assert _err(xva.wwr_cva, [1.0, 0.5], [[1.0, 1.0]], [1.0, 1.0], 0.01, 0.4, 0.0) == (
        "E_INPUT",
        "times",
    )


# --- curve_fits ---------------------------------------------------------------------------------


def test_smooth_maturity_past_last_knot_names_the_field() -> None:
    assert _err(curve_fits.smooth, [1.0, 2.0], [1.0, 3.0], [0.01, 0.02], 0.0) == (
        "E_INPUT",
        "maturities",
    )
