"""Kill tests for `quantforge_core.frtb` mutants that survived the H-0 40-mutant run
(conformance/mutation/python-h0-2026-11-18.md).

Error checks pin the contract (code and field, specifications/06-risk/frtb-sa-*.md), not the
message text. The alternative-specification test checks MAR21.4(5)(b) against the formula
written out here; the `sbm_total` tests check MAR21.7 (ruling R6-4.1) on hand-computed numbers.
"""

import math

import pytest

from quantforge_core import frtb
from quantforge_core.errors import QfError


def _err(fn, *args):
    with pytest.raises(QfError) as e:
        fn(*args)
    return e.value.code, e.value.field


def test_input_errors_carry_their_code_and_field() -> None:
    assert _err(frtb.fx_delta, [], []) == ("E_INPUT", "sensitivities")
    assert _err(frtb.equity_delta, []) == ("E_INPUT", "sensitivities")
    assert _err(frtb.csr_delta, []) == ("E_INPUT", "sensitivities")
    assert _err(frtb.commodity_delta, []) == ("E_INPUT", "sensitivities")
    assert _err(frtb.csr_delta, [("A", 1, "2Y", "BOND", 1.0)]) == ("E_INPUT", "tenor")
    assert _err(frtb.csr_delta, [("A", 1, "1Y", "LOAN", 1.0)]) == ("E_INPUT", "curve")
    assert _err(frtb.csr_delta, [("A", 19, "1Y", "BOND", 1.0)]) == ("E_INPUT", "bucket")
    assert _err(frtb.equity_delta, [("A", 1, "FWD", 1.0)]) == ("E_INPUT", "kind")
    dup = [("WTI", 2, "1Y", "X", 1.0), ("WTI", 2, "1Y", "X", 2.0)]
    assert _err(frtb.commodity_delta, dup) == ("E_INPUT", "sensitivities")
    assert _err(frtb.commodity_delta, [("WTI", 12, "1Y", "X", 1.0)]) == ("E_INPUT", "bucket")
    assert _err(frtb.fx_delta, [("EURUSD", 1.0), ("EURUSD", 2.0)], []) == (
        "E_INPUT",
        "sensitivities",
    )
    assert _err(frtb.vega, "GIRR", [("EUR", None, 1.0, None, 1.0)]) == (
        "E_INPUT",
        "underlying_maturity",
    )
    assert _err(frtb.vega, "FX", [("EURUSD", None, 1.0, 2.0, 1.0)]) == (
        "E_INPUT",
        "underlying_maturity",
    )
    assert _err(frtb.vega, "EQUITY", [(1, None, 1.0, None, 1.0)]) == ("E_INPUT", "name")
    assert _err(frtb.vega, "EQUITY", [(1, "A", 0.0, None, 1.0)]) == ("E_DOMAIN", "option_maturity")
    assert _err(frtb.vega, "GIRR", [("EUR", None, 1.0, -1.0, 1.0)]) == (
        "E_DOMAIN",
        "underlying_maturity",
    )
    assert _err(frtb.vega, "RATES", [("EUR", None, 1.0, 1.0, 1.0)]) == ("E_INPUT", "risk_class")
    assert _err(frtb.curvature, "EQUITY", [], False) == ("E_INPUT", "factors")
    twice = [(1, "A", 1.0, 1.0), (1, "A", 2.0, 2.0)]
    assert _err(frtb.curvature, "EQUITY", twice, False) == ("E_INPUT", "factors")


def test_alternative_specification_when_the_sum_is_negative() -> None:
    """MAR21.4(5)(b): with sum K^2 + sum gamma S_b S_c < 0, S_b is clipped to [-K_b, K_b].

    Equity bucket 9 (name rho 7.5%) holds 20 long issuers and bucket 10 (12.5%) 20 short ones,
    so each K is well below |S| and gamma 15% makes the medium sum negative."""
    n = 20
    rows = [(f"L{i}", 9, "SPOT", 1.0) for i in range(n)]
    rows += [(f"S{i}", 10, "SPOT", -1.0) for i in range(n)]
    out = frtb.equity_delta(rows)
    med = out["scenarios"]["medium"]
    w9, w10 = 0.70, 0.50  # MAR21.77 risk weights
    k9 = math.sqrt(n * w9**2 + n * (n - 1) * 0.075 * w9**2)
    k10 = math.sqrt(n * w10**2 + n * (n - 1) * 0.125 * w10**2)
    s9, s10 = n * w9, -n * w10
    assert k9 * k9 + k10 * k10 + 2 * 0.15 * s9 * s10 < 0
    assert med["alternative_used"] is True
    expected = math.sqrt(k9 * k9 + k10 * k10 + 2 * 0.15 * min(s9, k9) * max(s10, -k10))
    assert med["delta"] == pytest.approx(expected, rel=1e-12)
    assert [b["s_used"] for b in med["buckets"]] == pytest.approx([k9, -k10], rel=1e-12)
    # one bucket alone never needs it
    assert frtb.equity_delta(rows[:n])["scenarios"]["medium"]["alternative_used"] is False


def test_sbm_total_adds_within_a_scenario_then_takes_the_largest() -> None:
    out = frtb.sbm_total(
        [("GIRR", "DELTA", (10.0, 20.0, 5.0)), ("FX", "DELTA", (15.0, 1.0, 30.0))]
    )
    assert out["scenario_totals"] == {"high": 25.0, "medium": 21.0, "low": 35.0}
    assert out["capital"] == 35.0
    assert out["binding_scenario"] == "low"
    assert out["sum_of_component_capitals"] == 50.0
    # a tie goes to the earlier scenario
    tie = frtb.sbm_total([("EQ", "VEGA", (3.0, 3.0, 3.0))])
    assert tie["binding_scenario"] == "high" and tie["capital"] == 3.0


def test_sbm_total_errors() -> None:
    assert _err(frtb.sbm_total, []) == ("E_INPUT", "components")
    neg = [("FX", "DELTA", (1.0, 1.0, 1.0)), ("EQ", "DELTA", (1.0, -1.0, 1.0))]
    assert _err(frtb.sbm_total, neg) == ("E_DOMAIN", "components/1/scenarios")
    dup = [("FX", "DELTA", (1.0, 1.0, 1.0)), ("FX", "DELTA", (2.0, 2.0, 2.0))]
    assert _err(frtb.sbm_total, dup) == ("E_INPUT", "components/1")
