"""Kill tests for `quantforge_core.credit_options` and `fx_smile` mutants that survived the H-0
Actions run 44317826833 (conformance/mutation/python-h0-2026-11-18.md).

Credit: Pedersen's index option (rulings F-7 to F-10). A payer is a Black call on the adjusted
forward and a receiver a put, so payer - receiver = N A (F_adj - K_adj); the front-end protection
is (1 - R)(1 - exp(-h t)) P(0, t). FX: the premium-adjusted delta conventions of
specifications/04-pricing/fx-smile*.md (a call delta must be above 0; a PA call delta has a
maximum). Error checks pin code and field, not message text.
"""

import math
import threading
from datetime import date
from typing import Any

import pytest

from quantforge_core import black, credit_options, fx_smile
from quantforge_core.errors import QfError

AS_OF = date(2026, 11, 9)
ARGS = (AS_OF, date(2027, 3, 20), date(2031, 12, 20), 0.03, 0.02, 0.4)


def _err(fn: Any, *args: Any) -> tuple[str, str | None]:
    with pytest.raises(QfError) as e:
        fn(*args)
    return e.value.code, e.value.field


def test_index_option_payer_is_a_black_call_and_fep_formula() -> None:
    payer: dict[str, Any] = credit_options.cds_index_option_price(
        *ARGS, "PAYER", 0.012, 0.01, 1e7, 0.5
    )
    receiver: dict[str, Any] = credit_options.cds_index_option_price(
        *ARGS, "RECEIVER", 0.012, 0.01, 1e7, 0.5
    )
    t = (ARGS[1] - AS_OF).days / 365
    f, k, a = payer["adjusted_forward"], payer["adjusted_strike"], payer["risky_annuity"]
    call = black.price(black.Option(black.BLACK_76, "CALL", k, t, f), 0.5)
    assert payer["price"] == pytest.approx(1e7 * a * call, rel=1e-12)
    assert payer["price"] - receiver["price"] == pytest.approx(1e7 * a * (f - k), rel=1e-10)
    fep = 1e7 * (1 - 0.4) * (1 - math.exp(-0.02 * t)) * math.exp(-0.03 * t)
    assert payer["front_end_protection"] == pytest.approx(fep, rel=1e-12)


def test_index_option_notional_error_field() -> None:
    assert _err(credit_options.cds_index_option_price, *ARGS, "PAYER", 0.012, 0.01, 0.0, 0.5) == (
        "E_DOMAIN",
        "notional",
    )


def test_fx_delta_errors_carry_the_delta_field() -> None:
    dts = fx_smile.delta_to_strike
    assert _err(dts, 1.1, 0.5, 0.03, 0.02, 0.1, "CALL", 0.0, "SPOT") == ("E_DOMAIN", "delta")
    assert _err(dts, 1.1, 0.5, 0.03, 0.02, 0.1, "CALL", 0.999, "SPOT_PA") == ("E_DOMAIN", "delta")
    sfq = fx_smile.smile_from_quotes
    assert _err(sfq, 1.1, 0.5, 0.03, 0.02, 0.1, 0.01, 0.002, 0.5, "SPOT", "FORWARD") == (
        "E_DOMAIN",
        "delta",
    )


def test_pa_call_strike_at_high_total_vol() -> None:
    """vol sqrt(T) = 2.4 > 1.53, so the PA call peak lies below d2 = -1 and the search must widen
    left. The solve runs in a daemon thread with a time limit, so a search that never ends fails
    the test instead of hanging the run."""
    spot, t, rd, rf, vol = 1.1, 9.0, 0.03, 0.02, 0.8
    out: list[float] = []
    worker = threading.Thread(
        target=lambda: out.append(
            fx_smile.delta_to_strike(spot, t, rd, rf, vol, "CALL", 0.05, "FORWARD_PA")
        ),
        daemon=True,
    )
    worker.start()
    worker.join(30.0)
    assert out, "the PA call strike search did not finish"
    k = out[0]
    fwd = spot * math.exp((rd - rf) * t)
    d2 = (math.log(fwd / k) - vol * vol * t / 2) / (vol * math.sqrt(t))
    pa = (k / fwd) * 0.5 * math.erfc(-d2 / math.sqrt(2))
    assert pa == pytest.approx(0.05, abs=1e-12)
