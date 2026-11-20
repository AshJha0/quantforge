"""`xva.sens.aad` on `xva.adjustments.value` (06-risk/xva-aad-adjustments.md, rulings KR-262 to KR-268).

A2 of the spec: on 1,000 seeded random requests every gradient entry equals the 50-digit Richardson central bump
(Python `decimal`, the KR-265 rule) within 1e-12 + 1e-10 max(|AAD|, |ref|), which implies the plan's
|AAD - bump| <= 1e-8 max(1, |bump|). The goldens (A1) are checked here too, with the CLI's error order."""

import json
import random
from pathlib import Path
from typing import Any

import pytest
from xva_aad_reference import close as _close
from xva_aad_reference import flat as _flat
from xva_aad_reference import random_request as _random_request
from xva_aad_reference import reference

from quantforge_core import xva_aad
from quantforge_core.cli.limits import check_limits
from quantforge_core.cli.operations import OPERATIONS
from quantforge_core.cli.registry import execute
from quantforge_core.errors import QfError
from quantforge_core.xva import Name

ROOT = Path(__file__).resolve().parents[2]
GOLD = json.loads((ROOT / "datasets/golden/stage_k/aadadj_k.json").read_text("utf-8"))["cases"]
VALUE = [c for c in GOLD if c["expected"]["status"] == "ok"]
ERRORS = [c for c in GOLD if c["expected"]["status"] == "error"]


def _run(inputs: dict[str, Any]) -> Any:
    return execute("xva.sens.aad", json.loads(json.dumps(inputs)))


# ---------------------------------------------------------------- goldens (A1)


@pytest.mark.parametrize("case", VALUE, ids=lambda c: c["case_id"])
def test_value_goldens(case: dict[str, Any]) -> None:
    got, exp = _run(case["inputs"]), case["expected"]["outputs"]
    assert set(got) == set(exp)
    for k in exp:
        if k != "gradient":
            assert _close(got[k], exp[k]), k
    a, e = _flat(got["gradient"]), _flat(exp["gradient"])
    assert set(a) == set(e)
    bad = [(k, a[k], e[k]) for k in e if not _close(a[k], e[k])]
    assert not bad, bad[:3]


@pytest.mark.parametrize("case", ERRORS, ids=lambda c: c["case_id"])
def test_error_goldens(case: dict[str, Any]) -> None:
    with pytest.raises(QfError) as info:
        _run(case["inputs"])
    assert info.value.code == case["expected"]["error_code"]


def test_values_are_those_of_the_wrapped_operation() -> None:
    for case in VALUE:
        inner = case["inputs"]["inputs"]
        plain = execute("xva.adjustments.value", json.loads(json.dumps(inner)))
        got = _run(case["inputs"])
        assert {k: got[k] for k in plain} == plain


# ---------------------------------------------------------------- the 50-digit reference (KR-265)


def _worst(inp: dict[str, Any]) -> float:
    got = _flat(_run({"operation": "xva.adjustments.value", "inputs": inp})["gradient"])
    ref = reference(inp)
    assert set(got) == set(ref)
    worst = 0.0
    for k, e in ref.items():
        a = got[k]
        assert _close(a, e), (k, a, e, inp)
        assert abs(a - e) <= 1e-8 * max(1.0, abs(e))  # the plan's form (14.8 K-8)
        worst = max(worst, abs(a - e) / max(1.0, abs(e)))
    return worst


def test_a2_aad_equals_the_50_digit_bump_on_1000_random_requests() -> None:
    rng = random.Random(20261120)
    worst = max(_worst(_random_request(rng)) for _ in range(1000))
    assert (
        worst <= 1e-8
    )  # measured 2.4e-12 (largest |AAD - ref| / max(1, |ref|)); the gate is per entry above


@pytest.mark.parametrize("case", VALUE, ids=lambda c: c["case_id"])
def test_a1_goldens_against_the_reference_computed_here(case: dict[str, Any]) -> None:
    if "wrt" not in case["inputs"]:
        _worst(case["inputs"]["inputs"])


# ---------------------------------------------------------------- properties and edges


def _base_request() -> dict[str, Any]:
    req: dict[str, Any] = json.loads(json.dumps(VALUE[0]["inputs"]))
    return req


def test_bucket_entries_sum_to_the_flat_entry_and_recovery_closed_forms() -> None:
    for case in VALUE:
        got = _run(case["inputs"])
        for o, row in got["gradient"].items():
            for name in ("counterparty", "own"):
                if f"{name}.hazard_buckets" in row:
                    flat, b = row[f"{name}.hazard_rate"], row[f"{name}.hazard_buckets"]
                    assert abs(flat - sum(b)) <= 1e-12 * max(1.0, abs(flat)), (o, name)
        g = got["gradient"]
        if "counterparty.recovery" in g["cva"]:
            r_c = case["inputs"]["inputs"]["counterparty"]["recovery"]
            assert _close(g["cva"]["counterparty.recovery"], -got["cva"] / (1 - r_c))


def test_wrt_keeps_canonical_order_and_only_listed_keys() -> None:
    req = _base_request()
    req["wrt"] = ["ee", "counterparty.hazard_rate"]
    got = _run(req)
    for row in got["gradient"].values():
        assert list(row) == ["counterparty.hazard_rate", "ee"]


def test_keys_with_im_and_capital() -> None:
    assert xva_aad._keys(True, True)[-4:] == ("im", "im_spread", "capital", "hurdle_rate")
    assert xva_aad._keys(False, False) == xva_aad.BASE_KEYS


def test_zero_branch_of_the_overlap_floor_has_exact_zeros() -> None:
    req = _base_request()
    req["inputs"]["own"]["hazard_rate"] = 0.02
    req["inputs"]["funding"]["exclude_dva_overlap"] = True
    g = _run(req)["gradient"]["fba"]
    for k, v in g.items():
        for x in v if isinstance(v, list) else [v]:
            assert x == 0.0, k


def test_kink_takes_the_linear_branch() -> None:
    req = _base_request()
    req["inputs"]["own"] = {"hazard_rate": 0.01, "recovery": 0.5}
    req["inputs"]["funding"].update(lend_spread=0.005, exclude_dva_overlap=True)
    got = _run(req)
    g = got["gradient"]["fba"]
    assert got["fba"] == 0.0
    assert g["funding.lend_spread"] > 0
    assert _close(g["own.hazard_rate"], -0.5 * g["funding.lend_spread"])
    assert _close(g["own.recovery"], 0.01 * g["funding.lend_spread"])


@pytest.mark.parametrize(
    ("wrt", "code"),
    [([], "E_INPUT"), (["ee", "ee"], "E_INPUT"), (["im"], "E_INPUT"), (["x"], "E_INPUT")],
)
def test_wrt_rules(wrt: list[str], code: str) -> None:
    n = Name(0.01, 0.4)
    with pytest.raises(QfError) as info:
        xva_aad.adjustments_aad(
            [1.0], [1.0], [1.0], [-1.0], n, n, 0.0, 0.0, False, None, None, None, None, wrt
        )
    assert info.value.code == code


def test_limit_counts_every_profile() -> None:
    for key in ("times", "discount_factors", "ee", "ene", "im", "capital"):
        inner = {key: [0.0] * 10_000}
        check_limits("xva.sens.aad", {"inputs": inner})
        inner[key].append(0.0)
        with pytest.raises(QfError) as info:
            check_limits("xva.sens.aad", {"inputs": inner})
        assert info.value.code == "E_LIMIT"
    check_limits("xva.sens.aad", {"inputs": None})


def test_registered() -> None:
    assert "xva.sens.aad" in OPERATIONS
