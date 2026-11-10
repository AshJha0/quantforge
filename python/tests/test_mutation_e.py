"""Tests for stage E modules aimed at mutants that survived the mutation sample."""
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from quantforge_core import fx_smile, variance
from quantforge_core.errors import QfError


def error_of(f: Callable[..., Any], *args: Any) -> tuple[str, str, str | None]:
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code, e.value.message, e.value.field


def _golden(name: str) -> dict[str, Any]:
    """A stage F golden file, found from here or from a copy of python/ (mutmut's)."""
    here = Path(__file__).resolve()
    for p in here.parents:
        f = p / "datasets/golden/stage_f" / name
        if f.exists():
            return json.loads(f.read_text())
    pytest.skip("goldens not found")


def test_fx_delta_out_of_range() -> None:
    for kind in ("SPOT", "FORWARD"):
        assert error_of(fx_smile.delta_to_strike, 1.1, 1.0, 0.03, 0.01, 0.1, "CALL", 1.5,
                        kind) == ("E_DOMAIN", "delta is out of range", "delta")


def test_bracket_up_doubles_its_step() -> None:
    assert fx_smile._bracket_up(lambda x: 3.5 - x, 0.0) == 4.0  # 1, 2, 4: not 3
    assert fx_smile._bracket_up(lambda x: x - 5.5, 0.0) == 8.0
    assert error_of(fx_smile._bracket_up, lambda x: 1.0, 0.0) == (
        "E_NO_CONVERGENCE", "no strike bracket", "delta")


def test_variance_error_messages() -> None:
    assert error_of(variance.garch_forecast, 1e-6, 0.2, 0.8, 1e-4, 5, 252.0) == (
        "E_DOMAIN", "alpha + beta must be below 1 for a long-run variance", "alpha")
    assert error_of(variance.varswap_fair_strike, date(2026, 1, 2), date(2026, 1, 2), 100.0,
                    0.03, 0.0, [90.0], [110.0], [(90.0, 0.2), (110.0, 0.2)], 0.0, 0.04,
                    1.0) == ("E_INPUT", "maturity must be after as_of", "maturity")


def test_garch_estimate_matches_golden() -> None:
    case = next(c for c in _golden("garch_f.json")["cases"] if c["case_id"] == "garch_f-0009")
    i, want = case["inputs"], case["expected"]["outputs"]
    got = variance.garch_estimate(i["returns"], i["initial_variance"], i["distribution"],
                                  i["demean"])
    for key in ("omega", "alpha", "beta"):
        assert got[key] == pytest.approx(want[key], rel=1e-7)
    assert got["loglik"] == pytest.approx(want["loglik"], rel=1e-12)
    for key in ("omega", "alpha", "beta"):
        assert got["std_errors"][key] == pytest.approx(  # type: ignore[index]
            want["std_errors"][key], rel=1e-5)


def test_exotic_positivity_checks() -> None:
    from quantforge_core import exotics
    assert error_of(exotics.asian_geometric, 100.0, 100.0, 0.0, 0.03, 0.0, 0.2, "CALL",
                    "CONTINUOUS", []) == ("E_DOMAIN", "expiry_years must be above 0",
                                          "expiry_years")
    assert error_of(exotics.lookback, 0.0, 1.0, 0.03, 0.0, 0.2, "CALL", 0.0) == (
        "E_DOMAIN", "spot must be above 0", "spot")
    corr = [[1.0, 0.5], [0.5, 1.0]]
    assert error_of(exotics.basket, [100.0, 90.0], [0.0, 0.0], [0.2, 0.3], corr, 95.0, 1.0,
                    0.03, "CALL") == ("E_DOMAIN", "weights must be non-negative and not all 0",
                                      "weights")


def test_credit_option_error_fields() -> None:
    from quantforge_core import credit_options
    assert error_of(credit_options.loss_cdf, 0.02, 0.3, 0.4, [0.7]) == (
        "E_DOMAIN", "a loss is outside (0, 1 - R)", "losses")
    assert error_of(credit_options._check_option, date(2026, 1, 2), date(2026, 6, 2),
                    date(2031, 6, 2), 0.02, 1.0, 0.01) == (
        "E_DOMAIN", "recovery must be in [0, 1)", "recovery")


def test_index_option_strike_hazard_matches_golden() -> None:
    from quantforge_core.cli.operations import execute
    case = next(c for c in _golden("cdsidx_f.json")["cases"] if c["case_id"] == "cdsidx_f-0055")
    out = execute(case["operation"], case["inputs"])
    out = out[0] if isinstance(out, tuple) else out
    want = case["expected"]["outputs"]
    assert out["strike_hazard"] == pytest.approx(want["strike_hazard"], rel=1e-10)
    assert out["strike_annuity"] == pytest.approx(want["strike_annuity"], rel=1e-10)
