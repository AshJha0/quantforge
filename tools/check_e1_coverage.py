#!/usr/bin/env python3
"""Gate for R6-9 (review finding 10): every operation in specifications/name-map.json has an E1 golden, a case whose
inputs carry "NaN", "Infinity" or "-Infinity" and whose expected result is E_DOMAIN (ruling F-2), unless it is listed in
conformance/E1_EXEMPT.json, and an exempt operation must have no Real (JSON float) input in any golden.

    python tools/check_e1_coverage.py              # exit 1 on a gap
    python tools/check_e1_coverage.py --self-test  # shows the gate red on a planted operation (process rule 1)

Standard library only.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NF = {"NaN", "Infinity", "-Infinity"}


def has_nf(v):
    if isinstance(v, str):
        return v in NF
    if isinstance(v, list):
        return any(has_nf(x) for x in v)
    if isinstance(v, dict):
        return any(has_nf(x) for x in v.values())
    return False


def has_real(v):
    if isinstance(v, float):
        return True
    if isinstance(v, list):
        return any(has_real(x) for x in v)
    if isinstance(v, dict):
        return any(has_real(x) for x in v.values())
    return False


def check(name_map, golden, exempt_file):
    ops = set(json.loads(Path(name_map).read_text(encoding="utf-8"))["operations"])
    exempt = json.loads(Path(exempt_file).read_text(encoding="utf-8"))
    covered, real = set(), set()
    for p in Path(golden).rglob("*.json"):
        for c in json.loads(p.read_text(encoding="utf-8")).get("cases", []):
            if c["expected"]["status"] == "error" and c["expected"].get("error_code") == "E_DOMAIN" and has_nf(c["inputs"]):
                covered.add(c["operation"])
            if has_real(c["inputs"]):
                real.add(c["operation"])
    problems = [f"{op}: no E1 golden" for op in sorted(ops - covered - set(exempt))]
    problems += [f"{op}: exempt but has a Real input in a golden" for op in sorted(set(exempt) & real)]
    problems += [f"{op}: exempt but not in the name map" for op in sorted(set(exempt) - ops)]
    return problems, len(ops), len(covered & ops), len(exempt)


def self_test():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "g").mkdir()
        (d / "nm.json").write_text(json.dumps({"operations": {"x.y.covered": {}, "x.y.planted": {}}}), encoding="utf-8")
        (d / "ex.json").write_text("{}", encoding="utf-8")
        case = {"case_id": "t-0001", "operation": "x.y.covered", "inputs": {"v": "NaN"}, "expected": {"status": "error", "error_code": "E_DOMAIN"}}
        (d / "g" / "t.json").write_text(json.dumps({"cases": [case]}), encoding="utf-8")
        bad, *_ = check(d / "nm.json", d / "g", d / "ex.json")
        assert bad == ["x.y.planted: no E1 golden"], bad
    print("self-test: a planted operation with no E1 golden turns the gate red")
    return 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    bad, n, cov, ex = check(ROOT / "specifications" / "name-map.json", ROOT / "datasets" / "golden", ROOT / "conformance" / "E1_EXEMPT.json")
    for b in bad:
        print(b)
    print(f"E1 coverage: {cov} of {n} operations have an E1 golden, {ex} exempt (no Real input), {len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
