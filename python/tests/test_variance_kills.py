"""Kill tests for `quantforge_core/variance.py` (GARCH, variance swap, VIX strip).

Lane J-0c: the mutation-report job on PR #39 sampled this module for the `garch_varswap_vix`
(5 of 12 killed) and `garch_vix` (8 of 12) cells. Run the full set locally with
`conformance/mutation/python_sampled_mutants.py --profile variance --sample 100000`.

Two layers. First, every golden case of a `vol.garch.*`, `vol.varswap.*` or `vol.vix.*`
operation is run in process and judged by the neutral runner (independent goldens). Second,
targeted checks for survivors the goldens cannot see. Equivalent survivors are listed in
program/J0C_EQUIVALENT_MUTANTS.md.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from quantforge_core.cli.main import run_case

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "datasets" / "golden").is_dir())
# Fast suites first; the two with slow `vol.garch.estimate` fits last (the mutation run uses -x).
SUITES = ["stage_e_b/varswap_e", "stage_e_b/vix_e", "stage_e_b/rulings_e_b", "stage_f/e1_vol_3",
          "stage_f/e1_vol_4", "stage_f/e1_vol_5", "stage_f/vix_f", "stage_e_b/garch_e",
          "stage_j/fuzzfix_j", "stage_f/garch_f", "stage_f/e1_vol_1"]
PREFIXES = ("vol.garch.", "vol.varswap.", "vol.vix.")


def _runner():
    spec = importlib.util.spec_from_file_location(
        "qf_runner_variance_kills", ROOT / "conformance" / "runner" / "runner.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _runner()
CLASSES = RUNNER.load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")


@pytest.mark.parametrize("suite", SUITES)
def test_variance_goldens(suite: str) -> None:
    cases = json.loads((ROOT / "datasets" / "golden" / f"{suite}.json").read_text("utf-8"))["cases"]
    results, failures = {}, []
    for case in cases:
        if not case["operation"].startswith(PREFIXES):
            continue
        doc = {"schema_version": "1.0", "case_id": case["case_id"],
               "operation": case["operation"], "inputs": case["inputs"]}
        result = json.loads(json.dumps(run_case(json.dumps(doc))))
        results[case["case_id"]] = result
        status, messages = RUNNER.judge(case, result, CLASSES, results)
        if status != "pass":
            failures.append((case["case_id"], messages[:1]))
            break  # one failure is enough; keeps a mutant run short
    assert not failures, failures[:5]
