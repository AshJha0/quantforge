"""The stage D golden suites, in process, judged by the conformance runner's own rules.

The golden root is QF_GOLDEN_ROOT if set, else the repository holding this file (K-9 review finding 21: it
used to run only when QF_GOLDEN_ROOT was set, so CI skipped it). The root must hold datasets/golden/stage_d,
conformance/runner/runner.py and conformance/tolerances/policy.yaml. Mutmut's copy of python/ cannot see
datasets/, so there the test skips with the reason listed in tests/expected_skips.txt."""

import json
import os
import sys
from pathlib import Path

import pytest

from quantforge_core.cli.main import run_case

ROOT = os.environ.get("QF_GOLDEN_ROOT") or str(Path(__file__).resolve().parents[2])
pytestmark = pytest.mark.skipif(
    not (Path(ROOT) / "datasets" / "golden" / "stage_d").is_dir(),
    reason="no golden root: datasets/golden/stage_d not found (mutation copy)",
)


def test_stage_d_goldens() -> None:
    root = Path(str(ROOT))
    sys.path.insert(0, str(root / "conformance" / "runner"))
    from runner import judge, load_policy  # type: ignore[import-not-found]

    classes = load_policy(root / "conformance" / "tolerances" / "policy.yaml")
    failures = []
    for path in sorted((root / "datasets" / "golden" / "stage_d").glob("*.json")):
        for case in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            text = json.dumps(
                {
                    "schema_version": "1.0",
                    "case_id": case["case_id"],
                    "operation": case["operation"],
                    "inputs": case["inputs"],
                }
            )
            try:
                result = run_case(text)
            except Exception as e:  # noqa: BLE001 - a mutant may crash; that is a kill
                failures.append(f"{case['case_id']}: crash {e!r}")
                continue
            status, messages = judge(case, result, classes)
            if status != "pass":
                failures.append(f"{case['case_id']}: {messages[:1]}")
    assert not failures, failures[:5]
