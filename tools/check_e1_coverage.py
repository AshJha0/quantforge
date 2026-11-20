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

Ruling KR-112 (owner decision 2026-11-19, option A of program/STAGE_K_E1_ZONE_DECISION.md): an exempt operation may
carry a Real (JSON float) input ONLY in goldens whose expected result is E_SCHEMA, the golden that checks a
non-integer is refused. A Real in any other golden (a value case, or an error case expecting anything but E_SCHEMA)
still makes the exemption a problem. Nothing changes for non-exempt operations.

Rulings KR-251 and KR-252 (audit KA-C20, specifications/stage-k-rulings-audit-c.md; proposed): tightenings, nothing
is exempted by them.
  KR-251  the KR-112 allowance holds only where the Real sits at an input path that holds a JSON integer in the
          operation's value goldens (list indices ignored): the E_SCHEMA golden then refuses a non-integer where an
          integer belongs. A Real at any other path (a genuine Real field next to a missing key, say) still makes the
          exemption a problem, as F-2a (b) does for decimal strings.
  KR-252  an exempt operation that uses the KR-112 allowance, or whose exemption reason states that "a non-finite
          token is E_SCHEMA", must have a golden that sends a non-finite token ("NaN", "Infinity", "-Infinity") at an
          integer path of its value goldens and expects E_SCHEMA: the stated premise is pinned by a shared golden.
Known gap, not closed here (KA-C20 (2)): `has_real` sees JSON floats only, so a Real field written as an integer in
every golden is invisible; closing it needs typed inputs in the name map. The self-test pins the blind spot.

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
    int_paths = {}  # KR-251: input paths that hold a JSON integer in the operation's value goldens
    for c in cases:
        if c["expected"]["status"] == "ok":
            for path, v in leaves(c["inputs"]):
                if isinstance(v, int) and not isinstance(v, bool):
                    int_paths.setdefault(c["operation"], set()).add(path)
    covered, real, uses_kr112, pinned = set(), set(), set(), set()
    for c in cases:
        op, exp = c["operation"], c["expected"]
        code = exp.get("error_code") if exp["status"] == "error" else None
        if code == "E_DOMAIN" and has_nf(c["inputs"]):
            covered.add(op)
        elif code == "E_SCHEMA" and op in hr12:
            nf = [path for path, v in leaves(c["inputs"]) if isinstance(v, str) and v in NF]
            if nf and all(path in decimal_paths.get(op, set()) for path in nf):
                covered.add(op)
        # KR-112: a Real in a golden expecting E_SCHEMA is the refusal of a non-integer, not a Real the operation uses;
        # KR-251: only when every Real sits at an integer path of the value goldens
        if has_real(c["inputs"]):
            if code != "E_SCHEMA":
                real.add(op)
            elif all(path in int_paths.get(op, set()) for path, v in leaves(c["inputs"]) if isinstance(v, float)):
                uses_kr112.add(op)
            else:
                real.add(op)
        # KR-252: a non-finite token at an integer path refused as E_SCHEMA pins the Integer-only premise
        if code == "E_SCHEMA":
            nf = [path for path, v in leaves(c["inputs"]) if isinstance(v, str) and v in NF]
            if nf and all(path in int_paths.get(op, set()) for path in nf):
                pinned.add(op)
    problems = [f"{op}: no E1 golden" for op in sorted(ops - covered - set(exempt))]
    problems += [f"{op}: exempt but has a Real input in a golden" for op in sorted(set(exempt) & real)]
    problems += [f"{op}: exempt but not in the name map" for op in sorted(set(exempt) - ops)]
    premise = {op for op, why in exempt.items() if (op in uses_kr112 or "non-finite token is E_SCHEMA" in str(why))}
    problems += [f"{op}: exempt on the premise that a non-finite token is E_SCHEMA, but no golden sends one at an "
                 f"integer input and expects E_SCHEMA (KR-252)" for op in sorted(premise - pinned)]
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
        # KR-112, planted faults (a) to (d)
        nm3 = {"operations": {"r.real.op": {}, "i.int.op": {}, "i.int.bad": {}}}
        (d / "nm3.json").write_text(json.dumps(nm3), encoding="utf-8")
        (d / "g3").mkdir()
        nan_real = {"case_id": "c-1", "operation": "r.real.op", "inputs": {"x": "NaN"}, "expected": {"status": "error", "error_code": "E_DOMAIN"}}
        real_val = {"case_id": "c-2", "operation": "r.real.op", "inputs": {"x": 1.5}, "expected": {"status": "ok", "outputs": {}}}
        int_val = {"case_id": "c-3", "operation": "i.int.op", "inputs": {"n": 250, "k": 3}, "expected": {"status": "ok", "outputs": {}}}
        int_schema = {"case_id": "c-4", "operation": "i.int.op", "inputs": {"n": 250, "k": 1.5}, "expected": {"status": "error", "error_code": "E_SCHEMA"}}
        bad_val = {"case_id": "c-5", "operation": "i.int.bad", "inputs": {"n": 250, "k": 3}, "expected": {"status": "ok", "outputs": {}}}
        # KR-252 (added with KA-C20): the allowance needs its premise pinned, so the fixture carries the non-finite
        # E_SCHEMA golden at the integer path; (a) to (d) test what they tested before
        int_nan = {"case_id": "c-6", "operation": "i.int.op", "inputs": {"n": 250, "k": "NaN"}, "expected": {"status": "error", "error_code": "E_SCHEMA"}}

        def run3(rows, exempt):
            (d / "g3" / "t.json").write_text(json.dumps({"cases": rows}), encoding="utf-8")
            (d / "ex3.json").write_text(json.dumps(exempt), encoding="utf-8")
            return check(d / "nm3.json", d / "g3", d / "ex3.json", root=d)[0]
        ex_ok = {"i.int.op": "integers only", "i.int.bad": "integers only"}
        # (d) the shape of btk_k-0029: an exempt integer-only operation with a Real only in an E_SCHEMA golden passes
        assert run3([nan_real, real_val, int_val, int_schema, int_nan, bad_val], ex_ok) == [], "KR-112 (d)"
        # (a) a non-exempt operation without its NaN golden still fails
        assert run3([real_val, int_val, int_schema, int_nan, bad_val], ex_ok) == ["r.real.op: no E1 golden"], "KR-112 (a)"
        # (b) an exempt operation with a Real in a golden expecting anything other than E_SCHEMA fails
        for exp in ({"status": "error", "error_code": "E_DOMAIN"}, {"status": "error", "error_code": "E_INPUT"},
                    {"status": "error", "error_code": "E_LIMIT"}, {"status": "ok", "outputs": {}}):
            got = run3([nan_real, real_val, int_val, dict(int_schema, expected=exp), int_nan, bad_val], ex_ok)
            assert got == ["i.int.op: exempt but has a Real input in a golden"], ("KR-112 (b)", exp, got)
        # (c) an operation with a genuine Real input put on the exemption list fails
        got = run3([nan_real, real_val, int_val, int_schema, int_nan, bad_val], dict(ex_ok, **{"r.real.op": "planted"}))
        assert got == ["r.real.op: exempt but has a Real input in a golden"], ("KR-112 (c)", got)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "g").mkdir()
        (d / "nm.json").write_text(json.dumps({"operations": {"i.int.op": {}}}), encoding="utf-8")
        val = {"case_id": "k-1", "operation": "i.int.op", "inputs": {"n": 250, "k": 3}, "expected": {"status": "ok", "outputs": {}}}
        schema_k = {"case_id": "k-2", "operation": "i.int.op", "inputs": {"n": 250, "k": 1.5}, "expected": {"status": "error", "error_code": "E_SCHEMA"}}
        nan_k = {"case_id": "k-3", "operation": "i.int.op", "inputs": {"n": 250, "k": "NaN"}, "expected": {"status": "error", "error_code": "E_SCHEMA"}}

        def run4(rows, reason="integers only"):
            (d / "g" / "t.json").write_text(json.dumps({"cases": rows}), encoding="utf-8")
            (d / "ex.json").write_text(json.dumps({"i.int.op": reason}), encoding="utf-8")
            return check(d / "nm.json", d / "g", d / "ex.json", root=d)[0]
        # the btk_k-0029 shape with its premise pinned passes
        assert run4([val, schema_k, nan_k]) == [], "KR-251/252 clean"
        # KR-251 planted fault (KA-C20 (1)): a genuine Real field at a path the value goldens never hold as an integer,
        # beside a missing key, expecting E_SCHEMA, fails
        planted = dict(schema_k, inputs={"n": 250, "rate": 0.25})
        got = run4([val, planted, nan_k])
        assert got == ["i.int.op: exempt but has a Real input in a golden"], ("KR-251", got)
        # KR-252 planted fault (KA-C20 (3)): the KR-112 allowance used, no non-finite E_SCHEMA golden, fails
        got = run4([val, schema_k])
        assert got == ["i.int.op: exempt on the premise that a non-finite token is E_SCHEMA, but no golden sends one at "
                       "an integer input and expects E_SCHEMA (KR-252)"], ("KR-252 allowance", got)
        # KR-252: a reason that states the premise, no Real anywhere, no non-finite golden, fails
        got = run4([val], reason="three Integer counts; a non-finite token is E_SCHEMA, not an integer")
        assert len(got) == 1 and "KR-252" in got[0], ("KR-252 reason", got)
        # KR-252: the non-finite token at a non-integer path does not pin the premise
        got = run4([val, schema_k, dict(nan_k, inputs={"n": 250, "k": 3, "x": "NaN"})])
        assert len(got) == 1 and "KR-252" in got[0], ("KR-252 path", got)
        # an exemption that neither uses the allowance nor states the premise is unchanged (no new demand)
        assert run4([val], reason="no Real input in any golden: a non-finite value cannot be sent") == [], "KR-252 scope"
        # KA-C20 (2), known gap pinned: a Real field written as an integer in every golden is invisible to the gate
        assert run4([dict(val, inputs={"n": 250, "k": 3, "rate": 1})]) == [], "gap (2) pinned"
    print("self-test KR-251: a Real at a non-integer path of an E_SCHEMA golden fails; KR-252: the KR-112 allowance or a "
          "stated premise without a non-finite E_SCHEMA golden at an integer path fails; gap (2) pinned (still invisible)")
    print("self-test: a planted operation with no E1 golden turns the gate red")
    print("self-test KR-112: (a) missing NaN golden fails; (b) exempt Real outside E_SCHEMA fails; "
          "(c) a Real-input operation on the exemption list fails; (d) a Real only in an E_SCHEMA golden of an exempt operation passes")
    print("self-test F-2a: decimal-string E_SCHEMA passes; Real-input E_SCHEMA and no non-finite case fail")
    return 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    bad, n, cov, ex = check(ROOT / "specifications" / "name-map.json", ROOT / "datasets" / "golden", ROOT / "conformance" / "E1_EXEMPT.json")
    for b in bad:
        print(b)
    print(f"E1 coverage: {cov} of {n} operations have an E1 golden, {ex} exempt (no Real input outside E_SCHEMA goldens, KR-112), {len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
