"""Runs every golden case in process, judged by the neutral runner's own comparison."""
import importlib.util
import json
from pathlib import Path

import pytest

from quantforge_core.cli.main import run_case

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = sorted((ROOT / "datasets" / "golden" / "core").glob("*.json"))


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "qf_runner", ROOT / "conformance" / "runner" / "runner.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Golden cases that contradict the spec text. This code follows the spec, and these stay failing
# until the owner rules: see SPEC_QUESTIONS.md, Q1 and Q2. The test fails if the set changes.
DISPUTED = {
    "calendar": {
        f"calendar-{n:04d}"
        for n in (56, 57, 61, 84, 107, 148, 149, 180, 314, 318,
                  608, 609, 613, 636, 659, 700, 701, 732, 866, 870)
    },
    "daycount": {"daycount-1472"},
}

RUNNER = _load_runner()
CLASSES = RUNNER.load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")


@pytest.mark.parametrize("path", GOLDEN, ids=lambda p: p.stem)
def test_golden_suite(path):
    failures = []
    for case in json.loads(path.read_text(encoding="utf-8"))["cases"]:
        document = {
            "schema_version": "1.0",
            "case_id": case["case_id"],
            "operation": case["operation"],
            "inputs": case["inputs"],
        }
        result = json.loads(json.dumps(run_case(json.dumps(document))))
        status, messages = RUNNER.judge(case, result, CLASSES)
        if status != "pass":
            failures.append((case["case_id"], status, messages[:2]))
    unexpected = [f for f in failures if f[0] not in DISPUTED.get(path.stem, set())]
    assert not unexpected, unexpected[:10]
    assert {f[0] for f in failures} == DISPUTED.get(path.stem, set())
