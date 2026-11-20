"""One error order for every stage K operation (ruling KR-230, HR-122; audit A finding KA-A1).

The general rule of cli-contract.md: E_SCHEMA, E_LIMIT for the input sizes, the F-2 finite rule (E_DOMAIN),
structural E_INPUT, E_DOMAIN for one value, then a check that only arises after validation (for stage K the
stale-cache E_INPUT of curve.incremental.update). Every stage K golden with two errors names the step of each
error in brackets in its description ([schema], [limit], [finite], [structural], [domain], [after]); the
K-8 goldens, whose generator belongs to another lane, are classified in the table below. This test fails when
a two-error golden expects a code other than the earlier step's, when a two-error golden is not classified,
or when a registered stage K operation has no two-error golden."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from quantforge_core.cli.operations import OPERATIONS

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "datasets" / "golden" / "stage_k"
ORDER = ("schema", "limit", "finite", "structural", "domain", "after")
CODE = {
    "schema": "E_SCHEMA",
    "limit": "E_LIMIT",
    "finite": "E_DOMAIN",
    "structural": "E_INPUT",
    "domain": "E_DOMAIN",
    "after": "E_INPUT",
}
# k8_k (generator oracle/python/gen_stage_k_k8.py, another lane's file): the steps read from each description.
K8 = {
    "k8_k-0012": ("schema", "domain"),  # unlisted method and sigma = 0
    "k8_k-0013": ("structural", "domain"),  # bad exercise time and width = 0
    "k8_k-0014": ("domain", "limit"),  # sigma = 0 and nx above the limit
}
# The stage K operations (wave 1, wave 1b and the K-8 method); each needs a two-error golden.
STAGE_K_OPERATIONS = (
    "core.store.bitemporal_query",
    "curve.bootstrap.par_annual",
    "curve.incremental.update",
    "calib.trigger.check",
    "risk.intraday.delta_gamma_bound",
    "num.richardson.check",
    "risk.saccr.ead",
    "risk.frtb.backtest.zone",
    "risk.frtb.backtest.desk",
    "risk.frtb.backtest.count",
    "rates.shortrate.bermudan_swaption",
    "rates.shortrate.bermudan_ladder",
)


def _two_error_cases() -> list[dict[str, Any]]:
    out = []
    for path in sorted(GOLD.glob("*.json")):
        for case in json.loads(path.read_text("utf-8"))["cases"]:
            tags = set(case.get("tags", ()))
            if tags & {"two-errors", "two_errors"} or "two errors" in case.get("description", ""):
                out.append(case)
    return out


CASES = _two_error_cases()


def _steps(case: dict[str, Any]) -> tuple[str, ...]:
    if case["case_id"] in K8:
        return K8[case["case_id"]]
    return tuple(
        re.findall(
            r"\[(schema|limit|finite|structural|domain|after)\]", case.get("description", "")
        )
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case_id"])
def test_two_error_golden_follows_the_general_order(case: dict[str, Any]) -> None:
    steps = _steps(case)
    assert len(steps) == 2, (
        f"{case['case_id']}: name both steps in brackets: {case.get('description')!r}"
    )
    first = min(steps, key=ORDER.index)
    assert case["expected"]["status"] == "error"
    assert case["expected"]["error_code"] == CODE[first], (case["case_id"], steps, case["expected"])


def test_every_stage_k_operation_has_a_two_error_golden() -> None:
    covered = {c["operation"] for c in CASES}
    for name in STAGE_K_OPERATIONS:
        assert name in OPERATIONS, name
        assert name in covered, f"{name} has no two-error golden"


def test_the_audit_pairs_are_pinned() -> None:
    """The four pairs of audit A (KA-A1 a to d) each have a golden."""
    text = " ".join(c.get("description", "") for c in CASES)
    for pair in ("audit A pair a", "audit A pair b", "audit A pair c", "audit A pair d"):
        assert pair in text, pair
