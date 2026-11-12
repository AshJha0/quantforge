"""Stage I follow-up note (tutorial inputs): every `examples/hedge_*_i.json` case document runs
through the CLI with status ok and the outputs of the golden case it was copied from. Reads
`examples/` and `datasets/` beside `python/`, like test_conformance.py."""
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "datasets" / "golden" / "stage_i"
EXAMPLES = {
    "hedge_greeks_i.json": "hedgegreeks_i-0003", "hedge_minvar_i.json": "hedgemv_i-0006",
    "hedge_beta_i.json": "hedgebeta_i-0001", "hedge_qp_keyrate_i.json": "hedgeqp_i-0009",
    "hedge_qp_minnorm_i.json": "hedgeqp_i-0018", "hedge_integer_i.json": "hedgeint_i-0010",
    "hedge_residual_i.json": "hedgeres_i-0002", "hedge_credit_i.json": "hedgecredit_i-0004",
    "hedge_correlation_i.json": "hedgecorr_i-0003", "hedge_crossasset_i.json": "hedgexa_i-0002",
    "hedge_cost_i.json": "hedgecost_i-0002", "hedge_frontier_i.json": "hedgefrontier_i-0001",
    "hedge_backtest_i.json": "hedgebt_i-0001", "hedge_effectiveness_i.json": "hedgeeff_i-0001",
    "hedge_select_i.json": "hedgeselect_i-0009", "hedge_slippage_i.json": "hedgeslip_i-0003",
}


def golden(case_id: str) -> dict[str, Any]:
    suite = case_id.split("-")[0]
    cases = json.loads((GOLDEN / f"{suite}.json").read_text(encoding="utf-8"))["cases"]
    return next(c for c in cases if c["case_id"] == case_id)


def close(got: Any, want: Any, absolute: float, relative: float) -> bool:
    if isinstance(want, dict):
        return isinstance(got, dict) and all(close(got.get(k), v, absolute, relative)
                                              for k, v in want.items())
    if isinstance(want, list):
        return isinstance(got, list) and len(got) == len(want) and all(
            close(g, w, absolute, relative) for g, w in zip(got, want, strict=True))
    if isinstance(want, float) and isinstance(got, (int, float)):
        return math.isclose(got, want, rel_tol=relative, abs_tol=absolute)
    return bool(got == want)


@pytest.mark.skipif(not GOLDEN.is_dir(), reason="datasets/ is not beside python/")
def test_every_stage_i_example_reproduces_its_golden() -> None:
    names = sorted(EXAMPLES)
    lines = [json.dumps(json.loads((ROOT / "examples" / n).read_text(encoding="utf-8")))
             for n in names]
    p = subprocess.run([sys.executable, "-m", "quantforge_core.cli.main", "batch"],
                       input=("\n".join(lines) + "\n").encode(), capture_output=True,
                       timeout=300, check=False)
    results = [json.loads(line) for line in p.stdout.decode().splitlines()]
    assert len(results) == len(names)
    for name, result in zip(names, results, strict=True):
        case = golden(EXAMPLES[name])
        assert case["inputs"] == json.loads((ROOT / "examples" / name).read_text(
            encoding="utf-8"))["inputs"], name
        assert result["status"] == "ok", (name, result)
        limit = case.get("tolerance_limit") or {}
        assert close(result["outputs"], case["expected"]["outputs"],
                     limit.get("absolute", 1e-10), limit.get("relative", 1e-10)), name
