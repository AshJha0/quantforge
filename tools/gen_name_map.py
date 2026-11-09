#!/usr/bin/env python3
"""Generates specifications/name-map.json (plan item E4, rule F-5 in specifications/stage-f-rulings.md).

Operation names come from the spec pages (every backticked `<domain>.<area>.<verb>` whose domain is a
registered operation prefix and that has golden cases); input and output keys come from the golden cases
that pin each operation. Standard library only.

    python tools/gen_name_map.py           write the file
    python tools/gen_name_map.py --check   exit 1 if the file is stale
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "specifications" / "name-map.json"
OP = re.compile(r"`([a-z]+(?:\.[a-z0-9_]+){2,3})`")
UNIT_SUFFIXES = ("_years", "_days", "_bp", "_pct", "_minutes", "_months", "_ns")
UNIT_WORDS = ("expiry", "maturity", "tenor", "horizon", "spread", "shift", "bump")


def camel(s, first_upper=False):
    parts = [p for p in s.split("_") if p]
    out = "".join(p[:1].upper() + p[1:] for p in parts)
    return out if first_upper else out[:1].lower() + out[1:]


def golden_ops():
    keys = {}
    for p in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        for c in doc.get("cases", []):
            k = keys.setdefault(c["operation"], {"inputs": set(), "outputs": set(), "spec": doc.get("spec")})
            if isinstance(c.get("inputs"), dict):
                k["inputs"].update(c["inputs"])
            outs = (c.get("expected") or {}).get("outputs")
            if isinstance(outs, dict):
                k["outputs"].update(outs)
    return keys


def spec_ops():
    found = {}
    for p in sorted((ROOT / "specifications").rglob("*.md")):
        for m in OP.finditer(p.read_text(encoding="utf-8")):
            found.setdefault(m.group(1), p.relative_to(ROOT).as_posix())
    return found


def build():
    gold, specs = golden_ops(), spec_ops()
    rows, warnings = {}, []
    for op in sorted(gold):
        dom, area, verb = op.split(".")[0], op.split(".")[1], "_".join(op.split(".")[2:])
        fn = f"{area}_{verb}"
        k = gold[op]
        rows[op] = {
            "spec": specs.get(op) or k["spec"],
            "rust": f"quantforge::{dom}::{fn}",
            "python": f"quantforge.{dom}.{fn}",
            "java": f"{camel(dom, True)}.{camel(area)}{camel(verb, True)}",
            "cpp": f"qf::{dom}::{fn}",
            "inputs": {i: {"java": camel(i)} for i in sorted(k["inputs"])},
            "outputs": sorted(k["outputs"]),
        }
        for i in sorted(k["inputs"]):
            if any(w in i for w in UNIT_WORDS) and not i.endswith(UNIT_SUFFIXES) and not i.endswith(("_date", "_dates", "s")):
                warnings.append(f"{op}: {i}")
    return {"generated_by": "tools/gen_name_map.py", "rule": "specifications/stage-f-rulings.md F-5",
            "operations": rows, "unit_warnings": warnings,
            "spec_only": sorted(o for o in specs if o not in gold and o.split(".")[0] in {x.split(".")[0] for x in gold})}


def main():
    text = json.dumps(build(), indent=1, sort_keys=False) + "\n"
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("specifications/name-map.json is stale: run python tools/gen_name_map.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    d = json.loads(text)
    print(f"name map: {len(d['operations'])} operations, {len(d['unit_warnings'])} unit warnings, {len(d['spec_only'])} spec-only names")
    return 0


if __name__ == "__main__":
    sys.exit(main())
