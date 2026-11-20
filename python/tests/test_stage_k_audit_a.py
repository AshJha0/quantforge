"""Stage K round 1 audit A (institutional-quant-engine-plan/STAGE_K_R1_AUDIT_A.md): one reproduction per Major
finding (KA-A1 to KA-A6, KA-A16), each with the concrete input that shows it. They were committed first as
expected failures (strict xfail, marked with the finding id) on the unfixed code (commit 9edc7348), so the
evidence exists in the history; the fix commit removed the markers. The arithmetic of each expected value is in the test or its ruling
(stage-k-rulings-w1.md and stage-k-rulings-w1b.md, KR-230 onward)."""

import json
import math
import sys
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any

import numpy as np
import pytest
from scipy import stats

from quantforge_core import frtb_backtest as fb
from quantforge_core import saccr
from quantforge_core import stage_k as sk
from quantforge_core.cli.main import run_case
from quantforge_core.saccr import Trade


def _cli(operation: str, inputs: dict[str, Any]) -> dict[str, Any]:
    doc = {"schema_version": "1.0", "case_id": "k", "operation": operation, "inputs": inputs}
    out: dict[str, Any] = json.loads(json.dumps(run_case(json.dumps(doc))))
    return out


def _code(operation: str, inputs: dict[str, Any]) -> str:
    r = _cli(operation, inputs)
    assert r["status"] == "error", r
    code: str = r["error"]["code"]
    return code


def _record(seq: int) -> dict[str, Any]:
    t = "2026-01-01T00:00:00Z"
    return {
        "sequence": seq,
        "series_id": "A",
        "valid_from": t,
        "valid_to": None,
        "knowledge_time": t,
        "value": 0,
    }


def _bt(records: list[dict[str, Any]]) -> dict[str, Any]:
    t = "2026-01-02T00:00:00Z"
    return {"records": records, "series_id": "A", "knowledge_as_of": t, "valid_at": t}


# --- KA-A1: one error order (HR-122: E_SCHEMA, E_LIMIT, finite rule, structural E_INPUT, E_DOMAIN) --------------


def test_ka_a1_a_finite_rule_before_structural_input() -> None:
    """`changes` = [NaN]: the finite rule (cli-contract.md, F-2: "the first rule check of every operation")
    outranks the structural "fewer than two" E_INPUT."""
    inputs = {"changes": ["NaN"], "x_ref": 0.0, "x_now": 0.0, "days_since": 1.0, "k": 3.0}
    assert _code("calib.trigger.check", inputs) == "E_DOMAIN"


def test_ka_a1_b_size_limit_before_domain() -> None:
    """100,001 changes and k = 0: E_LIMIT straight after E_SCHEMA (cli-contract.md order; limits.md B3)."""
    inputs = {
        "changes": [0.0, 1.0] * 50_000 + [0.0],
        "x_ref": 0.0,
        "x_now": 0.0,
        "days_since": 1.0,
        "k": 0.0,
    }
    assert _code("calib.trigger.check", inputs) == "E_LIMIT"


def test_ka_a1_c_size_limit_before_log_checks() -> None:
    """A log above the array limit whose sequence repeats: E_LIMIT before log checks 2 and 3 (rulings.md A2)."""
    assert _code("core.store.bitemporal_query", _bt([_record(1)] * 100_001)) == "E_LIMIT"


def test_ka_a1_d_finite_rule_before_empty_list() -> None:
    """`positions` = [] and `shift` = NaN: E_DOMAIN by the finite rule, before the structural E_INPUT."""
    assert _code("risk.intraday.delta_gamma_bound", {"positions": [], "shift": "NaN"}) == "E_DOMAIN"


# --- KA-A2: the records cap is the generic array cap of limits.md -----------------------------------------------


def test_ka_a2_records_above_the_generic_array_cap() -> None:
    """100,001 well-formed records: limits.md caps any array at 100,000 elements (E_LIMIT)."""
    assert (
        _code("core.store.bitemporal_query", _bt([_record(s) for s in range(1, 100_002)]))
        == "E_LIMIT"
    )


def test_ka_a2_records_at_the_generic_array_cap() -> None:
    """100,000 records is legal (the boundary)."""
    r = _cli("core.store.bitemporal_query", _bt([_record(s) for s in range(1, 100_001)]))
    assert r["status"] == "ok" and r["outputs"]["row"]["sequence"] == 100_000


# --- KA-A3: volatility hedging sets follow CRE52.45 (CRE52.47) --------------------------------------------------


def test_ka_a3_two_equity_volatility_trades_form_one_hedging_set() -> None:
    """Two equity variance swaps on two single names, long and short, effective notional 100 each, labelled
    "V1" and "V2". CRE52.47: "all equity volatility transactions form a single hedging set". SF = 32% x 5 = 1.6,
    a = +-160, rho = 0.5: sqrt((0.5 x 160 - 0.5 x 160)^2 + 0.75 x (160^2 + 160^2)) = sqrt(38,400) = 195.959...
    Two label sets (ruling KR-34) give 160 + 160 = 320."""
    trades = [
        Trade("v1", "EQUITY", 100, 0, 1, treatment="VOLATILITY", hedging_set="V1", entity="X", subclass="SINGLE"),
        Trade(
            "v2", "EQUITY", 100, 0, 1, position="SHORT", treatment="VOLATILITY", hedging_set="V2", entity="Y",
            subclass="SINGLE",
        ),
    ]  # fmt: skip
    r: Any = saccr.ead(trades)
    assert math.isclose(r["addon"]["EQUITY"], math.sqrt(38_400.0), rel_tol=1e-15)
    assert [(h["treatment"], h["key"]) for h in r["hedging_sets"]] == [("VOLATILITY", "")]


# --- KA-A4: the reported false-alarm rate is the rate of the trigger as used ------------------------------------


def test_ka_a4_false_alarm_rate_matches_the_estimated_sigma_trigger() -> None:
    """Noise-only paths drawn the way the trigger is used: a window of n = 4 N(0, 1) changes, then one
    independent N(0, 1) move (d = 1), k = 3. numpy default_rng(20261119), 400,000 paths. The statistic is
    Student-t with n - 1 = 3 degrees of freedom, so the rate is 2 t_3.sf(3) = 0.0577; the old output is the
    known-sigma 2 Phi(-3) = 0.0027. The reported rate must lie inside the 99.9% binomial interval of the count."""
    n, k, paths = 4, 3.0, 400_000
    rng = np.random.default_rng(20261119)
    window = rng.standard_normal((paths, n))
    move = rng.standard_normal(paths)
    sigma = window.std(axis=1, ddof=1)
    fires = int(np.count_nonzero(np.abs(move) > k * sigma))
    rate = sk.trigger_check([1.0, -1.0, 1.0, -1.0], 0.0, 0.0, 1.0, k)["false_alarm_rate"]
    lo, hi = stats.binom.interval(0.999, paths, rate)
    assert lo <= fires <= hi, (fires, rate * paths, lo, hi)
    assert math.isclose(rate, 2 * stats.t.sf(k, n - 1), rel_tol=1e-12)


# --- KA-A5: a constant window is E_DOMAIN whatever the rounding ------------------------------------------------


def test_ka_a5_constant_window_is_a_domain_error() -> None:
    """[0.1, 0.1, 0.1]: the left-to-right mean is 0.10000000000000002 and sigma 1.7e-17 in binary64; a constant
    window has no noise scale (KR-6), so E_DOMAIN."""
    inputs = {"changes": [0.1, 0.1, 0.1], "x_ref": 0.0, "x_now": 0.0, "days_since": 1.0, "k": 3.0}
    assert _code("calib.trigger.check", inputs) == "E_DOMAIN"


# --- KA-A6: the intraday bound holds for small moves -----------------------------------------------------------


def _exact_revaluation(n: float, t: float, y: float, h: float) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 60
        dn, dt, dy, dh = Decimal(n), Decimal(t), Decimal(y), Decimal(h)
        return dn * ((-(dy + dh) * dt).exp() - (-dy * dt).exp())


@pytest.mark.parametrize(
    "h",
    [1e-8, 1e-9, 1e-10, 1e-12],
)
def test_ka_a6_bound_holds_for_tiny_moves(h: float) -> None:
    """One position N = 1e6, T = 5, y = 0.04 against a 60-digit revaluation (decimal module, exactly rounded
    exp): at h = 1e-9 the old binary64 output pair gives |estimate - exact| / bound = 21.6."""
    r = sk.delta_gamma_bound([sk.ZeroPosition(1e6, 5.0, 0.04)], h)
    exact = _exact_revaluation(1e6, 5.0, 0.04, h)
    with localcontext() as ctx:
        ctx.prec = 60
        gap = abs(Decimal(r["estimate_pnl"]) - exact)
    assert gap <= Decimal(r["bound"]), (h, float(gap), r["bound"])


# --- KA-A16: the binomial sum at large n -----------------------------------------------------------------------


sys.set_int_max_str_digits(0)  # the exact rationals below have far more digits


def _exact_cdf(n: int, x: int, p: Fraction) -> Fraction:
    """P(X <= x) for X ~ Binomial(n, p) in exact rational arithmetic, by the integer term recurrence."""
    a, b = p.numerator, p.denominator
    c = b - a  # q = c / b
    term = c**n  # C(n, 0) a^0 c^n
    total = term
    for k in range(x):
        term = term * (n - k) * a // ((k + 1) * c)
        total += term
    return Fraction(total, b**n)


def test_ka_a16_binomial_cdf_at_n_100000() -> None:
    """n = 100,000, x = 1,050, p = 1/100 exact: the class simple_analytic allows 1e-10 relative; the lgamma form
    was 1.3e-10 off (audit). The binary64 p = 0.01 differs from 1/100 by 2.1e-17 relative, which moves this
    cumulative probability by less than 1e-13 relative (n x x / (n p) x 2.1e-17)."""
    exact = _exact_cdf(100_000, 1_050, Fraction(1, 100))
    got = fb.binomial_cdf(100_000, 1_050, 0.01)
    assert abs(Fraction(got) / exact - 1) <= Fraction(1, 10**12)
