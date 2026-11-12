"""Kill tests for the credit-module mutants that survived the sampled mutation run
(`conformance/mutation/python_sampled_mutants.py --profile credit --seed 20261111`).

Two layers. First, every golden case of a `credit.*` operation is run in process and judged by
the neutral runner, so the unit-test run sees what the conformance run sees (most survivors
changed a formula that only the goldens pinned). Second, targeted checks for the survivors the
goldens cannot see: error codes and fields, the coupon-date roll, bracket growth and iteration
caps. Mutants that change only an error message's wording are not killed on purpose; the
reasons are listed in conformance/mutation/README_python.md.
"""
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import pytest

from quantforge_core.cli.main import run_case

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "datasets" / "golden").is_dir())
SUITES = ["stage_d/credit_d", "stage_d/outside_d", "stage_d/rulings2_d", "stage_d/rulings_d",
          "stage_d/rulings_r1", "stage_e_b/creditopt_e", "stage_e_b/rulings_e_b",
          "stage_f/cdsidx_f", "stage_f/e1_credit"]


def _runner():
    spec = importlib.util.spec_from_file_location(
        "qf_runner_kills", ROOT / "conformance" / "runner" / "runner.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _runner()
CLASSES = RUNNER.load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")


@pytest.mark.parametrize("suite", SUITES)
def test_credit_goldens(suite: str) -> None:
    cases = json.loads((ROOT / "datasets" / "golden" / f"{suite}.json").read_text("utf-8"))["cases"]
    results, failures = {}, []
    for case in cases:
        if not case["operation"].startswith("credit."):
            continue
        doc = {"schema_version": "1.0", "case_id": case["case_id"],
               "operation": case["operation"], "inputs": case["inputs"]}
        result = json.loads(json.dumps(run_case(json.dumps(doc))))
        results[case["case_id"]] = result
        status, messages = RUNNER.judge(case, result, CLASSES, results)
        if status != "pass":
            failures.append((case["case_id"], messages[:1]))
    assert not failures, failures[:5]


# --- targeted checks ------------------------------------------------------------------------------
# Left alive on purpose (equivalent on every allowed input, or message wording only):
# - credit.bootstrap Brent max_iter 1000 -> 1001, credit_options._beta_fraction range(1, 1000)
#   -> 1001, _integral max_intervals 2000 -> 2001: the solves converge far below these caps.
# - credit_options._strike_hazard bracket 2 K/(1 - R) -> 2 K/(2 - R) and growth 2 -> 3, the
#   bootstrap bracket step, implied-vol bracket growth 2 -> 3, beta-fraction stop test: any
#   bracket that holds the root gives the same root to the solver tolerance.
# - error message wording (for example "recovery must be in [0, 1)"): the contract fixes code and
#   field, which the tests below pin, not the text.

DISCOUNT = {"as_of": "2026-11-06", "interpolation": "LOG_LINEAR_DF",
            "pillars": [{"date": "2046-11-06", "discount_factor": 0.458161174870904}]}
HAZARD = {"as_of": "2026-11-06", "pillars": [
    {"date": "2027-06-20", "survival": 0.9953278717430543},
    {"date": "2031-12-20", "survival": 0.8988961248330224},
    {"date": "2036-12-20", "survival": 0.7635674704223004}]}
TRADE = {"maturity": "2031-12-20", "coupon": 0.01}
OPTION = {"as_of": "2026-11-06", "expiry": "2027-03-20", "maturity": "2032-03-20", "rate": 0.035,
          "hazard_rate": 0.02, "recovery": 0.4, "type": "PAYER", "strike": 0.012,
          "notional": 10000000.0, "knock_out": True}


def _run(operation: str, inputs: dict[str, Any]) -> dict[str, Any]:
    doc = {"schema_version": "1.0", "case_id": "kill", "operation": operation, "inputs": inputs}
    result: dict[str, Any] = json.loads(json.dumps(run_case(json.dumps(doc))))
    return result


def _error(operation: str, inputs: dict[str, Any]) -> tuple[str, str | None]:
    out = _run(operation, inputs)
    assert out["status"] == "error", out
    return out["error"]["code"], out["error"].get("field")


def test_bootstrap_equal_maturities_are_input_errors() -> None:
    quotes = [{"tenor": "1Y", "spread": 0.006}, {"tenor": "1Y", "spread": 0.007}]
    assert _error("credit.cds.bootstrap", {"trade_date": "2026-11-06", "discount": DISCOUNT,
                                           "recovery": 0.4, "quotes": quotes}) == (
        "E_INPUT", "quotes")


def test_zero_total_weights_are_domain_errors_with_their_fields() -> None:
    quotes = [{"tenor": "1Y", "spread": 0.006}, {"tenor": "3Y", "spread": 0.009}]
    comp = {"trade_date": "2026-11-06", "discount": DISCOUNT, "recovery": 0.4, "scale": 1.0,
            "constituents": [{"quotes": quotes, "weight": 0.0}, {"quotes": quotes, "weight": 0.0}]}
    assert _error("credit.curve.composite", comp) == ("E_DOMAIN", "constituents")
    names = [{"hazard": HAZARD, "recovery": 0.4, "weight": 0.0}] * 2
    idx = {"trade_date": "2026-11-06", "discount": DISCOUNT, "names": names,
           "trade": TRADE, "quoted_upfront": 0.0}
    assert _error("credit.index.intrinsic", idx) == ("E_DOMAIN", "names")


def test_sell_protection_is_the_negative_of_buy() -> None:
    trade = {"maturity": "2031-12-20", "coupon": 0.01, "notional": 1e7, "side": "BUY_PROTECTION"}
    base = {"trade_date": "2026-11-06", "discount": DISCOUNT, "hazard": HAZARD, "recovery": 0.4,
            "trade": trade, "payout": "STANDARD"}
    buy = _run("credit.cds.price", base)["outputs"]["pv"]
    sell = _run("credit.cds.price", {**base, "trade": {**trade, "side": "SELL_PROTECTION"}})
    assert sell["outputs"]["pv"] == -buy and buy != 0


def test_implied_vol_premium_at_and_near_the_cap() -> None:
    priced = _run("credit.cdsoption.price", {**OPTION, "vol": 0.5})["outputs"]
    cap = OPTION["notional"] * priced["risky_annuity"] * priced["forward_spread"]
    assert _error("credit.cdsoption.implied_vol", {**OPTION, "premium": cap}) == (
        "E_DOMAIN", "premium")
    # Below the cap a root always exists before vol 1e6 (Black at 1e6 rounds to the cap), so the
    # E_NO_CONVERGENCE branch is unreachable and its code-string mutant is equivalent.
    near = _run("credit.cdsoption.implied_vol", {**OPTION, "premium": cap * (1 - 1e-12)})
    assert near["status"] == "ok"


def test_index_option_without_default_risk_has_no_adjusted_forward() -> None:
    inputs = {"as_of": "2026-11-09", "expiry": "2027-02-17", "maturity": "2031-12-20",
              "rate": 0.037, "hazard_rate": 0.0, "recovery": 0.4, "type": "PAYER",
              "strike": 0.0055, "coupon": 0.01, "notional": 1e7, "vol": 0.45}
    assert _error("credit.cdsindex.option_price", inputs) == ("E_DOMAIN", "hazard_rate")


def test_incomplete_beta_at_zero() -> None:
    from quantforge_core import credit_options

    assert credit_options._incomplete_beta(2.0, 3.0, 0.0) == 0.0


def test_credit_series_branch_matches_the_closed_form() -> None:
    from quantforge_core import credit

    x = 9e-5  # inside the series branch; the closed form is accurate to ~1e-12 here, so compare
    # with a long Taylor sum instead
    first = sum((-x) ** k / math.factorial(k + 1) for k in range(12))
    second = sum((-x) ** k * (k + 1) / math.factorial(k + 2) for k in range(12))
    a, b = credit._series(x)
    assert abs(a - first) <= 1e-16 and abs(b - second) <= 1e-16
