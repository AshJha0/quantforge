"""Kill tests for `quantforge_core.caps_swaptions` (module group misc_d) and `cross_asset_hedge`
(hedge_cross) mutants that survived the H-0 Actions run 44317826833
(conformance/mutation/python-h0-2026-11-18.md).

Caps and swaptions: specifications/05-volatility/caps-and-swaptions.md (a zero vol is allowed and
gives the discounted intrinsic value; a one-month expiry is allowed). Cross-asset hedge:
specifications/08-hedging/cross-asset-hedge.md (ridge defaults to 0, so a book the hedges can
replicate is hedged exactly; an instrument without a maturity never fails the I-20 pillar check).
Error checks pin code and field, not the message text.
"""

import math
from datetime import date
from typing import Any

import pytest

from quantforge_core import caps_swaptions as cs
from quantforge_core import cross_asset_hedge as xa
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError

AS_OF = date(2026, 11, 6)


def _flat(rate: float = 0.035) -> CurveData:
    ds = (date(2027, 11, 8), date(2031, 11, 6), date(2046, 11, 6))
    return CurveData(
        AS_OF, "LOG_LINEAR_DF", ds, tuple(math.exp(-rate * (d - AS_OF).days / 365) for d in ds)
    )


def _err(fn: Any, *args: Any) -> tuple[str, str | None]:
    with pytest.raises(QfError) as e:
        fn(*args)
    return e.value.code, e.value.field


def test_cap_and_swaption_errors_carry_code_and_field() -> None:
    d, p = _flat(), _flat(0.036)
    assert _err(cs.cap_price, d, p, "BLACK_76", 0.2, "CAP", 0, 12, 0.035, 1.0) == (
        "E_INPUT",
        "start_months",
    )
    assert _err(cs.cap_price, d, p, "BLACK_76", 0.2, "CAP", 3, 0, 0.035, 1.0) == (
        "E_INPUT",
        "tenor_months",
    )
    assert _err(cs.cap_price, d, p, "BLACK_76", [0.2], "CAP", 3, 12, 0.035, 1.0) == (
        "E_INPUT",
        "vol",
    )
    assert _err(
        cs.cap_price, d, p, "BLACK_76", [0.2, 0.2, -0.1, 0.2], "CAP", 3, 12, 0.035, 1.0
    ) == (
        "E_DOMAIN",
        "vol",
    )
    assert _err(cs.cap_price, d, p, "BLACK_76", 0.2, "CAP", 3, 12, -0.01, 1.0) == (
        "E_DOMAIN",
        "strike",
    )


def test_swaption_zero_vol_is_intrinsic_and_one_month_expiry_prices() -> None:
    d, p = _flat(), _flat(0.036)
    value, forward, annuity = cs.swaption_price(d, p, "BLACK_76", 0.0, "PAYER", 12, 60, 0.03, 1e6)
    assert forward > 0.03
    assert value == pytest.approx(1e6 * annuity * (forward - 0.03), rel=1e-12)
    short, f1, a1 = cs.swaption_price(d, p, "BLACK_76", 0.2, "PAYER", 1, 60, 0.03, 1e6)
    assert short > 1e6 * a1 * (f1 - 0.03) > 0  # time value on top of intrinsic


TIMES, RATES = [1.0, 2.0, 5.0, 10.0], [0.03, 0.032, 0.035, 0.037]
BOOK = [("CALL", {"strike": 100.0, "expiry_years": 3.0, "quantity": -100.0})]
HEDGE: list[tuple[str, dict[str, float]]] = [("UNDERLYING", {})]


def test_crossasset_errors_carry_code_and_field() -> None:
    f = xa.crossasset_solve
    w = [1.0] * 5
    assert _err(f, 100.0, 0.01, 0.2, TIMES, RATES[:3], BOOK, HEDGE, w) == ("E_INPUT", "curve")
    bad_book = [("CALL", {"strike": 100.0, "expiry_years": 3.0})]  # no quantity
    assert _err(f, 100.0, 0.01, 0.2, TIMES, RATES, bad_book, HEDGE, w) == ("E_INPUT", "book")
    bad_hedge = [("CALL", {"strike": 100.0})]
    assert _err(f, 100.0, 0.01, 0.2, TIMES, RATES, BOOK, bad_hedge, w) == ("E_INPUT", "hedges")
    assert _err(f, 100.0, 0.01, 0.2, TIMES, RATES, BOOK, HEDGE, w[:4]) == ("E_INPUT", "weights")
    assert _err(f, 100.0, 0.01, 0.2, TIMES, RATES, BOOK, HEDGE, w, -1.0) == ("E_DOMAIN", "ridge")


def test_crossasset_default_ridge_hedges_a_replicable_book_exactly() -> None:
    """Short-dated curve (last pillar 0.5 years): spot positions carry no maturity, so the pillar
    check passes, and 10 units of the underlying are hedged by -10 with no ridge shrinkage."""
    book = [("UNDERLYING", {"quantity": 10.0})]
    out = xa.crossasset_solve(100.0, 0.01, 0.2, [0.25, 0.5], [0.03, 0.031], book, HEDGE, [1.0] * 3)
    assert out["positions"] == pytest.approx([-10.0], rel=1e-12)
    assert max(abs(v) for v in out["residual_risk"]) < 1e-9
