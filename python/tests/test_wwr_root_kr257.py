"""KR-257 (confirmed 2026-11-20): the wrong-way-risk root `a(t)` of `xva.wwr.cva_hw`.

A mutation lane found the old Newton iteration from `ln h` silently unconverged for large
`|b V|`: with h = 0.01, b = 1 and V = 10 on every path it returned a = -2.6e33 and cva = 0
(exact: a = ln 0.01 - 10 = -14.605, cva = 0.11347). These tests replay every `wwr_g` golden
through the core function and pin the closed form for identical V on every path.
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from quantforge_core import xva
from quantforge_core.errors import QfError

GOLDEN = Path(__file__).resolve().parents[2] / "datasets" / "golden" / "stage_g" / "wwr_g.json"
CASES: list[dict[str, Any]] = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]


def _call(inp: dict[str, Any]) -> dict[str, Any]:
    return xva.wwr_cva(
        inp["times"],
        inp["values"],
        inp["discount_factors"],
        inp["hazard_rate"],
        inp["recovery"],
        inp["wwr_b"],
    )


def _close(got: float, want: float) -> bool:
    return abs(got - want) <= 1e-9 + 1e-12 * abs(want)


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_wwr_golden(case: dict[str, Any]) -> None:
    expected = case["expected"]
    if expected["status"] == "error":
        with pytest.raises(QfError) as err:
            _call(case["inputs"])
        assert err.value.code == expected["error_code"]
        return
    out = _call(case["inputs"])
    want = expected["outputs"]
    assert _close(out["cva"], want["cva"])
    assert len(out["a"]) == len(want["a"])
    assert all(_close(x, y) for x, y in zip(out["a"], want["a"], strict=True))


@pytest.mark.parametrize("bv", [-700.0, -60.0, -10.0, -1.0, 0.0, 1.0, 10.0, 60.0, 700.0])
def test_identical_paths_root_is_closed_form_to_1e_14(bv: float) -> None:
    h = 0.01
    out = _call(
        {
            "times": [1.0, 2.0],
            "values": [[bv, bv], [bv, bv]],
            "discount_factors": [0.97, 0.94],
            "hazard_rate": h,
            "recovery": 0.4,
            "wwr_b": 1.0,
        }
    )
    exact = math.log(h) - bv
    a = out["a"]
    assert isinstance(a, list)
    assert all(abs(x - exact) <= 1e-14 * max(1.0, abs(exact)) for x in a)
    cva = (
        0.6
        * max(bv, 0.0)
        * (0.97 * -math.expm1(-0.01) + 0.94 * (math.exp(-0.01) - math.exp(-0.02)))
    )
    # The spec cva tolerance (1e-12 relative): a + b V carries eps |b V| ~ 1.6e-13 at |b V| = 700.
    assert out["cva"] == pytest.approx(cva, rel=1e-12, abs=1e-300)


def test_limit_and_non_finite_fields() -> None:
    base = {"times": [1.0], "discount_factors": [0.97], "recovery": 0.4}
    with pytest.raises(QfError) as err:
        _call({**base, "values": [[1.0], [-10.0]], "hazard_rate": 0.01, "wwr_b": 70.01})
    assert (err.value.code, err.value.field) == ("E_DOMAIN", "wwr_b")
    with pytest.raises(QfError) as err:
        _call({**base, "values": [[1.0]], "hazard_rate": 709.0, "wwr_b": 0.0})
    assert (err.value.code, err.value.field) == ("E_NON_FINITE", "hazard_rate")
    with pytest.raises(QfError) as err:
        _call({**base, "values": [[1.0]], "hazard_rate": 2e-308, "wwr_b": 0.0})
    assert (err.value.code, err.value.field) == ("E_NON_FINITE", "hazard_rate")
    # The limit is inclusive: |b V| = 700 and h t just below the underflow line both run.
    ok = _call({**base, "values": [[10.0], [-10.0]], "hazard_rate": 708.0, "wwr_b": 70.0})
    assert ok["cva"] == pytest.approx(0.6 * 0.97 * 10.0 / 2, rel=1e-12)
