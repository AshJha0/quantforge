#!/usr/bin/env python3
"""Applies rulings R6-10.2 and R6-10.3 to the golden files (idempotent).

R6-10.2: every per-unit output that `tools/check_tolerance_units.py` flags gets `output_classes[key] = "per_unit"`
(policy.yaml: absolute 1e-10, relative 1e-8). Evidence: conformance/tolerances/R6_REJUDGE_{python,rust,cpp}.json, where
the v0.8.0 builds were inside that class on every flagged output.
R6-10.3: `joint_f-0001` keeps class `jacobian_piecewise` (ruling F-40, a kink-straddling stencil) under a named ruling.

Each file is rewritten in the format it had (indent 1 or compact; checked by a round trip before any change).

    python conformance/tolerances/apply_r6_per_unit.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
sys.path.insert(0, str(ROOT / "tools"))
from runner import load_policy  # noqa: E402
from check_tolerance_units import scan  # noqa: E402

KEEP = {"joint_f-0001": "R6-10.3"}


def dump(doc, compact, ascii_only):
    return json.dumps(doc, indent=None if compact else 1, ensure_ascii=ascii_only) + "\n"


def main():
    classes = load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")
    flagged, _ = scan(ROOT / "datasets" / "golden", classes)
    want = {}
    for cid, k, _ in flagged:
        want.setdefault(cid, set()).add(k)
    changed = 0
    for p in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
        text = p.read_text(encoding="utf-8")
        doc = json.loads(text)
        hit = [c for c in doc.get("cases", []) if c["case_id"] in want]
        if not hit:
            continue
        fmt = next(((cm, a) for cm in (False, True) for a in (False, True) if dump(doc, cm, a) == text), None)
        if fmt is None:
            raise SystemExit(f"{p}: does not round-trip; not touched")
        for c in hit:
            if c["case_id"] in KEEP:
                c.setdefault("tolerance_limit", {})["per_unit_ruling"] = KEEP[c["case_id"]]
                continue
            oc = c.setdefault("output_classes", {})
            for k in sorted(want[c["case_id"]]):
                oc[k] = "per_unit"
            changed += 1
        p.write_text(dump(doc, *fmt), encoding="utf-8", newline="\n")
    print(f"{changed} cases moved per-unit outputs to class per_unit; {len(KEEP)} kept under a ruling")


if __name__ == "__main__":
    main()
