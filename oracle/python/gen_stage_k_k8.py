"""Stage K, item K-8: goldens of `CN_RANNACHER_SMOOTHED` (specifications/06-risk/bermudan-ladder-k8.md 0.2.0,
rulings KR-8 and KR-15) on `rates.shortrate.bermudan_swaption` and `rates.shortrate.bermudan_ladder`.

Expected values come from the Python build through its CLI (`quantforge_core.cli.main.run_case`): the scheme is a
pinned deterministic reference scheme, as G-18 is, so the golden pins the scheme, not the model value. This file is
NOT an independent oracle implementation; what stands behind the numbers is recorded per case in `verified_by`:
the Java build agrees to 1e-9 of the row scale (BermudanK8Test), the ladder equals its own Richardson bumps to 1e-8
(test_k8_ladder_equals_its_own_bumps), and at the default grid every judged entry is within 1% of the QuantLib
fine-grid bump reference (oracle/K8_ACCEPTANCE_W2.json; worst 0.40%).

Error cases: `method` is a schema field, so an unlisted value is E_SCHEMA before anything else. Every other check is
the operation's own stage G check (the size limit on `nx` is applied when the field is read). The generator asserts
that each error case gives the same code with `method` set to `G18_IMPLICIT`, with one recorded exception:
k8_k-0013 (a bad exercise time together with width = 0). The repo-wide order (HR-66) and the Java build give
E_INPUT there (the schedule is structural); the Python G-18 path checks the grid first and gives E_DOMAIN. The K-8
path follows HR-66 in both builds; the Python G-18 path is outside this lane's files and is reported to the
coordinator (program/K8_PORT_NOTE.md). Three cases carry two errors at once.

    cd python && uv run python ../oracle/python/gen_stage_k_k8.py
"""

import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from quantforge_core.cli.main import run_case  # noqa: E402

METHOD = "CN_RANNACHER_SMOOTHED"
SPEC = "specifications/06-risk/bermudan-ladder-k8.md"
OUT = ROOT / "datasets/golden/stage_k/k8_k.json"
LADDER = "rates.shortrate.bermudan_ladder"
PRICE = "rates.shortrate.bermudan_swaption"
VALUE_EVIDENCE = [
    "python build float64 (pinned reference scheme, spec 0.2.0)",
    "java build equal to 1e-9 of the row scale (BermudanK8Test, 2026-11-19)",
]
LIMIT = {
    "absolute": 1e-10,
    "relative": 1e-08,
    "reason": "Q3a rule per unit notional (G-9), as aadladder_g; the scheme is deterministic",
}


def base(index: int) -> dict[str, Any]:
    doc = json.loads((ROOT / "datasets/golden/stage_g/aadladder_g.json").read_text("utf-8"))
    out: dict[str, Any] = copy.deepcopy(doc["cases"][index]["inputs"])
    out["method"] = METHOD
    return out


def with_(i: dict[str, Any], **kw: Any) -> dict[str, Any]:
    out = copy.deepcopy(i)
    for k, v in kw.items():
        if k in ("nx", "steps_per_year", "width"):
            out["grid"][k] = v
        else:
            out[k] = v
    return out


def run(operation: str, inputs: dict[str, Any]) -> dict[str, Any]:
    doc = {"schema_version": "1.0", "case_id": "k8", "operation": operation, "inputs": inputs}
    out: dict[str, Any] = json.loads(json.dumps(run_case(json.dumps(doc))))
    return out


def build() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    def value(operation: str, inputs: dict[str, Any], description: str, extra: list[str]) -> None:
        r = run(operation, inputs)
        assert r["status"] == "ok", r
        case = {
            "case_id": f"k8_k-{len(cases) + 1:04d}",
            "operation": operation,
            "inputs": inputs,
            "expected": {"status": "ok", "outputs": r["outputs"]},
            "tolerance_class": "aad_sensitivity" if operation == LADDER else "root_finding",
            "verified_by": VALUE_EVIDENCE + extra,
            "tags": ["stage_k", "k8", "bermudan", "synthetic"],
            "description": description,
        }
        if operation == LADDER:
            case["tolerance_limit"] = LIMIT
        cases.append(case)

    def error(
        operation: str, inputs: dict[str, Any], code: str, description: str, two: bool = False, g18: str | None = None
    ) -> None:
        r = run(operation, inputs)
        assert r["status"] == "error" and r["error"]["code"] == code, (description, r)
        if inputs["method"] == METHOD:
            assert run(operation, with_(inputs, method="G18_IMPLICIT"))["error"]["code"] == (g18 or code), description
        cases.append(
            {
                "case_id": f"k8_k-{len(cases) + 1:04d}",
                "operation": operation,
                "inputs": inputs,
                "expected": {"status": "error", "error_code": code},
                "tolerance_class": "simple_analytic",
                "verified_by": ["hand (error order HR-66)", "java build (StageKCliTest, 2026-11-19)"],
                "tags": ["stage_k", "k8", "bermudan", "synthetic", "error", *(["two_errors"] if two else [])],
                "description": description,
            }
        )

    accept = "default grid: every judged entry within 1% of the QuantLib fine-grid bump (oracle/K8_ACCEPTANCE_W2.json)"
    bumps = "ladder equals its own Richardson bumps to 1e-8 on a small grid (test_k8_ladder_equals_its_own_bumps)"
    for index, name in enumerate(("payer at the money", "payer 50 bp out of the money", "receiver 50 bp out")):
        value(LADDER, with_(base(index), nx=201, steps_per_year=100), f"ladder at the default grid 201/100, {name}", [accept, bumps])
    value(PRICE, with_(base(0), nx=201, steps_per_year=100), "price at the default grid; equals the ladder price of k8_k-0001", [accept])
    value(LADDER, with_(base(2), nx=41, steps_per_year=20), "coarse grid 41/20, receiver", [bumps])
    value(PRICE, with_(base(1), nx=101, steps_per_year=50, exercise_times=[1.0]), "one exercise date (European) on 101/50", [])
    value(
        PRICE,
        with_(base(0), nx=51, steps_per_year=1, exercise_times=[1.0, 3.0]),
        "one step a year: the 1 to 3 interval has two steps, both start-up steps; 0 to 1 has one",
        [],
    )
    error(LADDER, with_(base(0), method="CN"), "E_SCHEMA", "unlisted method")
    error(LADDER, with_(base(0), sigma=0.0), "E_DOMAIN", "sigma = 0 with the K-8 method")
    error(PRICE, with_(base(0), exercise_times=[1.5]), "E_INPUT", "exercise time that is not a reset date")
    error(PRICE, with_(base(0), nx=20001), "E_LIMIT", "nx above 10,001")
    error(LADDER, with_(base(0), method="CN", sigma=0.0), "E_SCHEMA", "unlisted method and sigma = 0: schema first", True)
    error(PRICE, with_(base(0), exercise_times=[1.5], width=0.0), "E_INPUT", "bad exercise time and width = 0: the schedule (structural) first, HR-66", True, "E_DOMAIN")
    error(LADDER, with_(base(0), sigma=0.0, nx=20001), "E_LIMIT", "sigma = 0 and nx above the limit: the limit is applied when nx is read", True)
    return cases


def main() -> None:
    doc = {
        "schema_version": "1.0",
        "suite": "k8_k",
        "spec": SPEC,
        "spec_version": "0.2.0",
        "generator": "oracle/python/gen_stage_k_k8.py",
        "reviewer": "none: self-assessment; no second review (owner decision 2026-11-18)",
        "cases": build(),
    }
    OUT.write_text(json.dumps(doc, indent=1) + "\n", "utf-8", newline="\n")
    print(len(doc["cases"]), "cases")


if __name__ == "__main__":
    main()
