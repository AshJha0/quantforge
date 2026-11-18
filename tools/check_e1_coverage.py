#!/usr/bin/env python3
"""Gate for R6-9 (review finding 10): every operation in specifications/name-map.json has an E1 golden, a case whose
inputs carry "NaN", "Infinity" or "-Infinity" and whose expected result is E_DOMAIN (ruling F-2), unless it is listed in
conformance/E1_EXEMPT.json, and an exempt operation must have no Real (JSON float) input in any golden.

Ruling F-2a (owner decision 2026-11-18, "1, refine the gate"; HR-12): an input the spec types as a decimal string
rejects a non-finite token ("NaN", "Infinity", "-Infinity") as a malformed decimal, E_SCHEMA, which comes before
F-2's E_DOMAIN. So an E_SCHEMA case also counts as the operation's E1 golden when (a) the operation's spec page
(its `spec` in the name map, or the `spec` of a golden suite that pins it) cites HR-12, and (b) the non-finite token sits at an input path that holds a decimal
string in the operation's value goldens (list indices ignored). A token at a Real path, or in an operation whose
spec does not cite HR-12, still needs E_DOMAIN. Nothing is exempted by this rule.

    python tools/check_e1_coverage.py              # exit 1 on a gap
    python tools/check_e1_coverage.py --self-test  # shows the gate red on a planted operation (process rule 1)

Standard library only.
"""
import json
import re
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


DEC = re.compile(r"-?[0-9]+(\.[0-9]+)?")


def leaves(v, path=()):
    """(path, value) for every leaf; list indices become "*" so a path names a field, not a position."""
    if isinstance(v, dict):
        for k, x in v.items():
            yield from leaves(x, path + (k,))
    elif isinstance(v, list):
        for x in v:
            yield from leaves(x, path + ("*",))
    else:
        yield path, v


def cites_hr12(spec, root):
    """F-2a (a): the operation's spec page cites ruling HR-12 (decimal-string inputs)."""
    p = Path(root) / spec if spec else None
    return bool(p and p.is_file() and re.search(r"\bHR-12\b", p.read_text(encoding="utf-8")))


def check(name_map, golden, exempt_file, root=ROOT):
    entries = json.loads(Path(name_map).read_text(encoding="utf-8"))["operations"]
    ops = set(entries)
    exempt = json.loads(Path(exempt_file).read_text(encoding="utf-8"))
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(golden).rglob("*.json"))]
    cases = [c for doc in docs for c in doc.get("cases", [])]
    # F-2a (a): the spec pages of an operation are its name-map `spec` and the `spec` of every golden suite that
    # pins it (the name map takes the first page that names the operation, which can be a neighbouring page).
    pages = {op: {e.get("spec")} for op, e in entries.items() if isinstance(e, dict)}
    for doc in docs:
        for c in doc.get("cases", []):
            pages.setdefault(c["operation"], set()).add(doc.get("spec"))
    hr12 = {op for op, ps in pages.items() if any(cites_hr12(p, root) for p in ps)}
    decimal_paths = {}  # F-2a (b): input paths that hold a decimal string in the operation's value goldens
    for c in cases:
        if c["expected"]["status"] == "ok":
            for path, v in leaves(c["inputs"]):
                if isinstance(v, str) and DEC.fullmatch(v):
                    decimal_paths.setdefault(c["operation"], set()).add(path)
    covered, real = set(), set()
    for c in cases:
        op, exp = c["operation"], c["expected"]
        code = exp.get("error_code") if exp["status"] == "error" else None
        if code == "E_DOMAIN" and has_nf(c["inputs"]):
            covered.add(op)
        elif code == "E_SCHEMA" and op in hr12:
            nf = [path for path, v in leaves(c["inputs"]) if isinstance(v, str) and v in NF]
            if nf and all(path in decimal_paths.get(op, set()) for path in nf):
                covered.add(op)
        if has_real(c["inputs"]):
            real.add(op)
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
        # F-2a: decimal-string operation (spec cites HR-12) with an E_SCHEMA non-finite case passes; a Real-input
        # operation with E_SCHEMA fails; an operation with no non-finite case fails.
        (d / "spec_dec.md").write_text("Prices are decimal strings (HR-12).", encoding="utf-8")
        (d / "spec_real.md").write_text("Real inputs.", encoding="utf-8")
        nm = {"operations": {"d.dec.op": {"spec": "spec_dec.md"}, "r.real.op": {"spec": "spec_real.md"},
                             "n.none.op": {"spec": "spec_dec.md"}}}
        (d / "nm2.json").write_text(json.dumps(nm), encoding="utf-8")
        (d / "g2").mkdir()
        rows = [
            {"case_id": "a-1", "operation": "d.dec.op", "inputs": {"price": "100.5"}, "expected": {"status": "ok", "outputs": {}}},
            {"case_id": "a-2", "operation": "d.dec.op", "inputs": {"price": "NaN"}, "expected": {"status": "error", "error_code": "E_SCHEMA"}},
            {"case_id": "a-3", "operation": "r.real.op", "inputs": {"x": 1.5}, "expected": {"status": "ok", "outputs": {}}},
            {"case_id": "a-4", "operation": "r.real.op", "inputs": {"x": "NaN"}, "expected": {"status": "error", "error_code": "E_SCHEMA"}},
            {"case_id": "a-5", "operation": "n.none.op", "inputs": {"price": "1"}, "expected": {"status": "ok", "outputs": {}}},
        ]
        (d / "g2" / "t.json").write_text(json.dumps({"cases": rows}), encoding="utf-8")
        (d / "ex2.json").write_text("{}", encoding="utf-8")
        bad, *_ = check(d / "nm2.json", d / "g2", d / "ex2.json", root=d)
        assert bad == ["n.none.op: no E1 golden", "r.real.op: no E1 golden"], bad
        # A decimal-string operation whose NaN sits at a path that is not a decimal field is not covered either.
        rows[1] = dict(rows[1], inputs={"other": "NaN"})
        (d / "g2" / "t.json").write_text(json.dumps({"cases": rows}), encoding="utf-8")
        bad, *_ = check(d / "nm2.json", d / "g2", d / "ex2.json", root=d)
        assert "d.dec.op: no E1 golden" in bad, bad
    print("self-test: a planted operation with no E1 golden turns the gate red")
    print("self-test F-2a: decimal-string E_SCHEMA passes; Real-input E_SCHEMA and no non-finite case fail")
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
