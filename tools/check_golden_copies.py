#!/usr/bin/env python3
"""Gate (plan 14.10 rule 1, R6 wave 3B): a golden case whose inputs equal another case's inputs, with every -0.0 read as
0.0 (rule F-3 twins in stage_f/e1_*), must expect the same result. A regenerated source case with a stale copy is
exactly what this catches (`e1_risk-0372` after R6-3.1 changed `risk_f4-0039`).

    python tools/check_golden_copies.py          # exit 1 on a mismatch
    python tools/check_golden_copies.py --fix    # copy the source's expected result into each stale twin (oracle side only)
    python tools/check_golden_copies.py --self-test

Source = the case outside stage_f/e1_* (the generator's own case); twin = a case in stage_f/e1_*. Standard library only.
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def norm(v):
    if isinstance(v, float) and v == 0.0:
        return 0.0
    if isinstance(v, list):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    return v


def key(c):
    return c["operation"] + json.dumps(norm(c["inputs"]), sort_keys=True)


def scan(golden):
    src, twins = {}, []
    for p in sorted(Path(golden).rglob("*.json")):
        twin = p.parent.name == "stage_f" and p.stem.startswith("e1_")
        for c in json.loads(p.read_text(encoding="utf-8")).get("cases", []):
            if c["expected"]["status"] not in ("ok", "error"):
                continue
            (twins.append((p, c)) if twin else src.setdefault(key(c), c))
    bad = []
    for p, c in twins:
        s = src.get(key(c))
        if s is not None and s["expected"] != c["expected"]:
            bad.append((p, c["case_id"], s["case_id"], s["expected"]))
    return bad


def fix(bad):
    by = {}
    for p, cid, _, exp in bad:
        by.setdefault(p, {})[cid] = exp
    for p, m in by.items():
        t = p.read_text(encoding="utf-8")
        d = json.loads(t)
        fmt = next((i, a) for i in (1, None) for a in (False, True) if json.dumps(d, indent=i, ensure_ascii=a) + "\n" == t)
        for c in d["cases"]:
            if c["case_id"] in m:
                c["expected"] = m[c["case_id"]]
        p.write_text(json.dumps(d, indent=fmt[0], ensure_ascii=fmt[1]) + "\n", encoding="utf-8", newline="\n")


def self_test():
    with tempfile.TemporaryDirectory() as d:
        g = Path(d)
        (g / "stage_x").mkdir()
        (g / "stage_f").mkdir()
        a = {"case_id": "a-1", "operation": "x.y.z", "inputs": {"v": 0.0}, "expected": {"status": "ok", "outputs": {"r": 2.0}}}
        b = {"case_id": "e1_x-1", "operation": "x.y.z", "inputs": {"v": -0.0}, "expected": {"status": "ok", "outputs": {"r": 1.0}}}
        (g / "stage_x" / "a.json").write_text(json.dumps({"cases": [a]}), encoding="utf-8")
        (g / "stage_f" / "e1_x.json").write_text(json.dumps({"cases": [b]}), encoding="utf-8")
        assert [x[1] for x in scan(g)] == ["e1_x-1"]
    print("self-test: a stale negative-zero twin is caught")
    return 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    bad = scan(ROOT / "datasets" / "golden")
    for p, cid, sid, _ in bad:
        print(f"{cid} ({p.name}) differs from its source {sid}")
    if bad and "--fix" in sys.argv:
        fix(bad)
        print(f"fixed {len(bad)}")
        return 0
    print(f"golden copies: {len(bad)} stale")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
