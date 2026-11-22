"""Targeted checks for the rates_vol and var_risk survivors of mutation run 44952400895 (PR #65).

Each test pins the contract that a sampled mutant broke: the error code, field and message of a
refusal (the CLI contract), or a value. The cube and bond-futures inputs come from the first ok
golden case of datasets/golden/stage_e_b/ratesvol_e.json.
"""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from quantforge_core import black, rates_vol, var_risk
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError

# Found by walking up, so the file is also found from mutmut's copy of python/.
GOLDEN = next(
    p / "datasets/golden/stage_e_b/ratesvol_e.json"
    for p in Path(__file__).resolve().parents
    if (p / "datasets/golden/stage_e_b/ratesvol_e.json").exists()
)


def _base(operation: str) -> dict[str, Any]:
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
    case = next(c for c in cases if c["operation"] == operation and c["expected"]["status"] == "ok")
    return copy.deepcopy(case["inputs"])


def err(f: Callable[..., object], *args: object) -> tuple[str, str | None, str]:
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code, e.value.field, e.value.message


def run(operation: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return run_case(
        json.dumps(
            {"schema_version": "1.0", "case_id": "t", "operation": operation, "inputs": inputs}
        )
    )


def cli_err(operation: str, inputs: dict[str, Any]) -> tuple[str, str | None, str]:
    r = run(operation, inputs)
    assert r["status"] == "error", r
    e = r["error"]
    return e["code"], e.get("field"), e["message"]


CUBE = "rates.swaption.price_cube"


# --- rates_vol ---


def test_locate_outside_names_the_field() -> None:
    # _locate 10: the field argument dropped.
    assert err(rates_vol._locate, [1.0, 2.0], 3.0, "tenor_months") == (
        "E_INPUT",
        "tenor_months",
        "tenor_months is outside the cube",
    )


def test_single_expiry_row_cube_matches_the_node_row() -> None:
    # _bilinear 8: len(m) - 1 to len(m) + 1 reads a row that a one-row cube does not have.
    inputs = _base(CUBE)
    full = run(CUBE, inputs)["outputs"]
    row = inputs["cube"]["expiries_months"].index(inputs["trade"]["expiry_months"])
    one = copy.deepcopy(inputs)
    one["cube"]["expiries_months"] = [inputs["trade"]["expiry_months"]]
    for k in ("alpha", "beta", "rho", "nu"):
        one["cube"][k] = [inputs["cube"][k][row]]
    single = run(CUBE, one)
    assert single["status"] == "ok", single
    assert single["outputs"]["sabr"] == pytest.approx(full["sabr"], rel=1e-12)
    assert single["outputs"]["price"] == pytest.approx(full["price"], rel=1e-12)


def test_cube_expiry_refusal_names_the_field() -> None:
    # price_cube 48.
    inputs = _base(CUBE)
    inputs["trade"]["expiry_months"] = 1201
    assert cli_err(CUBE, inputs) == ("E_INPUT", "expiry_months", "expiry_months must be at least 1")


def test_cube_node_expiry_refusal_names_the_field() -> None:
    # price_cube 63.
    inputs = _base(CUBE)
    inputs["cube"]["expiries_months"][-1] = 1201
    assert cli_err(CUBE, inputs) == ("E_INPUT", "cube", "a node expiry is out of range")


def test_cube_beta_refusal_message() -> None:
    # price_cube 178, 180: message None, or the field moved into the message slot.
    inputs = _base(CUBE)
    inputs["cube"]["beta"][0][0] = 1.5
    assert cli_err(CUBE, inputs) == ("E_DOMAIN", "cube", "beta must be in [0, 1]")


def test_cap_strip_flat_vol_refusal_names_the_field() -> None:
    # cap_strip 41: the message dropped, so the field moved into the message slot.
    inputs = _base("rates.cap.strip")
    inputs["flat_vols"][1] = 0.0
    assert cli_err("rates.cap.strip", inputs) == (
        "E_DOMAIN",
        "flat_vols",
        "a flat vol is not above 0",
    )


def test_futures_option_discount_refusal_message() -> None:
    # _futures_option 33: message None.
    assert err(rates_vol._futures_option, "CALL", 100.0, 100.0, 0.5, 0.0) == (
        "E_DOMAIN",
        "discount_factor",
        "discount_factor must be above 0",
    )


def test_bondfut_implied_no_bracket_code() -> None:
    # bondfut_implied 60: the E_NO_CONVERGENCE code. With expiry 1e-300 an at-the-money price
    # stays near 0 at every vol up to 2^20, so the bracket search gives up.
    assert err(rates_vol.bondfut_implied, "CALL", 100.0, 100.0, 1e-300, 1.0, 1.0, 0.04, 6.0) == (
        "E_NO_CONVERGENCE",
        "premium",
        "no implied vol bracket",
    )


def test_zc_price_forward_refusal_message() -> None:
    # zc_price 5: message None.
    assert err(rates_vol.zc_price, black.BLACK_76, "CAP", 0.0, 5.0, 0.02, 0.9, 0.03, 1e6) == (
        "E_DOMAIN",
        "forward_index_ratio",
        "BLACK_76 needs a positive forward",
    )


# --- var_risk ---


def test_filtered_historical_lambda_message() -> None:
    # filtered_historical 29: message case.
    assert err(var_risk.filtered_historical, [0.01, -0.02], 1e6, 1.0, 0.99) == (
        "E_DOMAIN",
        "lambda",
        "lambda must be in (0, 1)",
    )


def test_parametric_std_field() -> None:
    # parametric 10: field dropped.
    assert err(var_risk.parametric, 0.0, 0.0, 0.99) == ("E_DOMAIN", "std", "std must be positive")


def test_monte_carlo_size_refusal_field() -> None:
    # monte_carlo 17, 22: field dropped or changed.
    assert err(var_risk.monte_carlo, [0.0, 0.0], [[1.0, 0.0], [0.0, 1.0]], [1.0], 100, 1, 0.99) == (
        "E_INPUT",
        "covariance",
        "mean, covariance and weights must agree in size",
    )


def test_monte_carlo_asymmetric_code() -> None:
    # monte_carlo 42: code None.
    assert err(
        var_risk.monte_carlo, [0.0, 0.0], [[1.0, 0.5], [0.4, 1.0]], [1.0, 1.0], 100, 1, 0.99
    ) == (
        "E_DOMAIN",
        "covariance",
        "covariance must be symmetric",
    )


def test_monte_carlo_singular_covariance_refused() -> None:
    # monte_carlo 69: a zero pivot (s == 0 exactly) must be refused, not accepted as > 0.
    with pytest.raises(QfError) as e:
        var_risk.monte_carlo([0.0, 0.0], [[1.0, 1.0], [1.0, 1.0]], [1.0, 1.0], 100, 1, 0.99)
    assert e.value.code == "E_NOT_POSITIVE_DEFINITE"


def test_christoffersen_short_message() -> None:
    # christoffersen 14: message case.
    assert err(var_risk.christoffersen, [True], 0.99) == (
        "E_INPUT",
        "exceptions",
        "need at least 2 days",
    )


def test_girr_delta_empty_refusal() -> None:
    # girr_delta 7, 10: field dropped, message changed.
    assert err(var_risk.girr_delta, [], False, None) == (
        "E_INPUT",
        "sensitivities",
        "no sensitivities",
    )
