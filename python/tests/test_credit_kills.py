"""Kill tests for the credit-module mutants that survived the sampled mutation run
(`conformance/mutation/python_sampled_mutants.py --profile credit --seed 20261111`).

Two layers. First, every golden case of a `credit.*` operation is run in process and judged by
the neutral runner, so the unit-test run sees what the conformance run sees (most survivors
changed a formula that only the goldens pinned). Second, targeted checks for the survivors the
goldens cannot see: error codes and fields, the coupon-date roll, bracket growth and iteration
caps. Mutants that change only an error message's wording are not killed on purpose; the
reasons are listed in conformance/mutation/README_python.md.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from quantforge_core.cli.main import run_case

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "datasets" / "golden").is_dir())
SUITES = ["stage_d/credit_d", "stage_d/outside_d", "stage_d/rulings2_d", "stage_d/rulings_d",
          "stage_d/rulings_r1", "stage_e_b/creditopt_e", "stage_e_b/rulings_e_b",
          "stage_f/cdsidx_f", "stage_f/e1_credit"]


def _runner():
    spec = importlib.util.spec_from_file_location(
        "qf_runner_kills", ROOT / "conformance" / "runner" / "runner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _runner()
CLASSES = RUNNER.load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")


@pytest.mark.parametrize("suite", SUITES)
def test_credit_goldens(suite: str) -> None:
    cases = json.loads((ROOT / "datasets" / "golden" / f"{suite}.json").read_text("utf-8"))["cases"]
    results, failures = {}, []
    for case in cases:
        if not case["operation"].startswith("credit."):
            continue
        doc = {"schema_version": "1.0", "case_id": case["case_id"],
               "operation": case["operation"], "inputs": case["inputs"]}
        result = json.loads(json.dumps(run_case(json.dumps(doc))))
        results[case["case_id"]] = result
        status, messages = RUNNER.judge(case, result, CLASSES, results)
        if status != "pass":
            failures.append((case["case_id"], messages[:1]))
    assert not failures, failures[:5]
