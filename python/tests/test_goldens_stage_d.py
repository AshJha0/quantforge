"""The stage D golden suites, in process, judged by the conformance runner's own rules.

For mutation testing: mutmut's copy of python/ cannot see datasets/, so this runs only when
QF_GOLDEN_ROOT names a directory holding datasets/golden/stage_d, conformance/runner/runner.py and
conformance/tolerances/policy.yaml. The normal conformance run covers the same cases."""
import json
import os
import sys
from pathlib import Path

import pytest

from quantforge_core.cli.main import run_case

ROOT = os.environ.get("QF_GOLDEN_ROOT")
pytestmark = pytest.mark.skipif(not ROOT, reason="QF_GOLDEN_ROOT is not set")


def test_stage_d_goldens() -> None:
    root = Path(str(ROOT))
    sys.path.insert(0, str(root / "conformance" / "runner"))
    from runner import judge, load_policy  # type: ignore[import-not-found]
    classes = load_policy(root / "conformance" / "tolerances" / "policy.yaml")
    failures = []
    for path in sorted((root / "datasets" / "golden" / "stage_d").glob("*.json")):
        for case in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            text = json.dumps({"schema_version": "1.0", "case_id": case["case_id"],
                               "operation": case["operation"], "inputs": case["inputs"]})
            try:
                result = run_case(text)
            except Exception as e:  # noqa: BLE001 - a mutant may crash; that is a kill
                failures.append(f"{case['case_id']}: crash {e!r}")
                continue
            status, messages = judge(case, result, classes)
            if status != "pass":
                failures.append(f"{case['case_id']}: {messages[:1]}")
    assert not failures, failures[:5]
