"""Stage H audit rulings HR-121 to HR-129: every golden row of datasets/golden/stage_h/rule_h.json
through the CLI, and the three code changes checked directly against hand values."""

import json
from pathlib import Path
from typing import Any

import pytest

from quantforge_core import adaptive_exec as ax
from quantforge_core import execution as ex
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError

GOLD = Path(__file__).resolve().parents[2] / "datasets" / "golden" / "stage_h"
CASES: list[dict[str, Any]] = json.loads((GOLD / "rule_h.json").read_text(encoding="utf-8"))[
    "cases"
]
AC = (1e6, 5.0, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7)


def _same(got: Any, exp: Any, path: str = "") -> None:
    if isinstance(exp, dict):
        assert isinstance(got, dict) and set(got) == set(exp), path
        for k in exp:
            _same(got[k], exp[k], f"{path}.{k}")
    elif isinstance(exp, list):
        assert isinstance(got, list) and len(got) == len(exp), path
        for k, (g, e) in enumerate(zip(got, exp, strict=True)):
            _same(g, e, f"{path}[{k}]")
    elif exp is None or isinstance(exp, (str, bool)):
        assert got == exp and type(got) is type(exp), (path, got, exp)
    else:
        assert abs(got - exp) <= 1e-12 + 1e-10 * abs(exp), (path, got, exp)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case_id"])
def test_golden(case: dict[str, Any]) -> None:
    doc = {
        "schema_version": "1.0",
        "case_id": "r",
        "operation": case["operation"],
        "inputs": case["inputs"],
    }
    r = run_case(json.dumps(doc))
    exp = case["expected"]
    if exp["status"] == "error":
        assert r["error"]["code"] == exp["error_code"], r
    else:
        assert "outputs" in r, r
        _same(r["outputs"], exp["outputs"])


def test_suite_size() -> None:
    assert len(CASES) == 40
    assert sum(c["expected"]["status"] == "ok" for c in CASES) == 11


def _code(fn: Any) -> str:
    with pytest.raises(QfError) as e:
        fn()
    return e.value.code


def test_pair_rounds_an_exact_half_up() -> None:
    """HR-121: 0.3 / 0.2 is 1.4999999999999998 in binary64 and 1.5 exactly, so leg B is 2."""
    assert 0.3 / 0.2 < 1.5
    r = ax.algo_pair(("BUY", 1, 0.3), ("SELL", 0.2), "CASH_BALANCED", None, 1, "UNITS")
    assert r["quantity_b"] == 2 and r["slices_b"] == [2]
    assert r["cash_imbalance"][0] == pytest.approx(-0.1, abs=1e-15)
    r = ax.algo_pair(("BUY", 5, 0.7), ("SELL", 1.0), "CASH_BALANCED", None, 1, "UNITS")
    assert r["quantity_b"] == 4
    # well away from a half nothing changes: 3 x 0.5 / 1.3 = 1.15 rounds to 1
    r = ax.algo_pair(("BUY", 3, 0.5), ("SELL", 1.3), "CASH_BALANCED", None, 1, "UNITS")
    assert r["quantity_b"] == 1


def test_structural_errors_come_first() -> None:
    """HR-122: with two errors at once the structural E_INPUT comes before every E_DOMAIN."""
    x, t, n, s, e, eta, g = AC
    assert _code(lambda: ex.ac_trajectory(x, t, 0, -1.0, e, eta, g, 0.0)) == "E_INPUT"
    assert _code(lambda: ex.ac_trajectory(0.0, 0.0, n, s, e, eta, g, 0.0)) == "E_INPUT"
    assert _code(lambda: ex.ac_frontier(x, t, n, -1.0, e, eta, g, [])) == "E_INPUT"
    assert _code(lambda: ex.ac_frontier(x, t, n, -1.0, e, eta, g, [0.0])) == "E_DOMAIN"
    assert _code(lambda: ex.schedule_pov(1000.0, 1.5, [], "CONTINUOUS")) == "E_INPUT"
    assert _code(lambda: ex.schedule_pov(1000.0, 1.5, [10.0], "CONTINUOUS")) == "E_DOMAIN"
    # eta_tilde <= 0 is the last domain check: gamma = 2 eta / tau with a negative sigma reports sigma
    with pytest.raises(QfError) as err:
        ex.ac_trajectory(x, t, n, -1.0, e, eta, 2 * eta, 0.0)
    assert (err.value.code, err.value.field) == ("E_DOMAIN", "sigma")
