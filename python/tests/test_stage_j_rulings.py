"""Rulings J-20 to J-22 (specifications/stage-j-rulings-w1.md) through the CLI entry point."""

import json

from quantforge_core.cli.main import run_case


def _run(operation: str, inputs: dict) -> dict:
    doc = {"schema_version": "1.0", "case_id": "c", "operation": operation, "inputs": inputs}
    return run_case(json.dumps(doc))


def _backtest(n: int) -> dict:
    return _run("research.backtest.run", {"prices": [100.0] * n, "targets": [0.0] * n})


def test_j20_page_limit_replaces_general_array_limit() -> None:
    assert _backtest(100_001)["status"] == "ok"  # above the general 100,000, inside J-5
    assert _backtest(1_000_001)["error"]["code"] == "E_LIMIT"  # just over J-5


def test_j21_power_arguments_outside_unit_interval_are_domain() -> None:
    for alpha, power in ((0.0, 0.8), (-0.1, 0.8), (0.05, 1.0), (0.05, 1.5)):
        r = _run("research.stats.power", {"years": 5.0, "alpha": alpha, "power": power})
        assert r["error"]["code"] == "E_DOMAIN"


def test_j22_empty_viterbi_input_is_input_error() -> None:
    base = {"initial": [0.5, 0.5], "transition": [[0.9, 0.1], [0.1, 0.9]]}
    assert _run("research.regime.viterbi", {**base, "emission": []})["error"]["code"] == "E_INPUT"
    gauss = {**base, "observations": [], "means": [0.0, 1.0], "sds": [1.0, 1.0]}
    assert _run("research.regime.viterbi", gauss)["error"]["code"] == "E_INPUT"


def test_j20_pbo_rows_judged_by_cell_cap() -> None:
    r = _run("research.stats.pbo", {"performance": [[0.0, 1.0]] * 100_002, "n_partitions": 2})
    assert r.get("error", {}).get("code") != "E_LIMIT"
