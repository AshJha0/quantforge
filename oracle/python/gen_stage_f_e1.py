"""Stage F wave 0, plan item E1: non-finite and negative-zero inputs for every operation (rules F-1 to F-3).

For each operation, the base case is its smallest ok golden case (by input JSON length, then case id) from
every golden suite outside stage_f. Each Real leaf (a JSON float; arrays: element 0 and the last element)
gets NaN, +inf and -inf cases expecting E_DOMAIN, and one negative-zero case: a copy of the base expected
result when the base leaf is exactly zero, else a pair (+0.0 anchor expecting "any", -0.0 expecting
"same_as" the anchor). Files are split by operation domain and kept under 1 MB (plan item E11).
"""
import json
from pathlib import Path

from qf_oracle.common import ROOT

GOLD = ROOT / "datasets" / "golden"
OUT = GOLD / "stage_f"
SPEC = "specifications/stage-f-rulings.md"
TOKENS = ("NaN", "Infinity", "-Infinity")
MAX_BYTES = 900_000


REAL_PATHS = {}
# Real inputs that no ok golden writes as a float; the type is from the spec page named.
REAL_OVERRIDES = {
    "core.integrate.gauss_legendre": {("a",), ("b",)},  # 01-core/integration.md: bounds of [a, b]
}


def norm(path):
    return tuple("*" if isinstance(k, int) else k for k in path)


def float_paths(node, path=()):
    if isinstance(node, bool):
        return
    if isinstance(node, float):
        yield norm(path)
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from float_paths(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from float_paths(v, path + (i,))


def base_cases():
    """Also fills REAL_PATHS: per operation, every input path that holds a float in any golden case (spec type Real)."""
    best = {}
    for p in sorted(GOLD.rglob("*.json")):
        if p.parent.name == "stage_f":
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or "cases" not in doc:
            continue
        for c in doc["cases"]:
            if c.get("expected", {}).get("status") != "ok":
                continue
            # only accepted inputs type a path: error cases may hold a float in an Integer field (E_SCHEMA)
            REAL_PATHS.setdefault(c["operation"], set()).update(float_paths(c["inputs"]))
            key = (len(json.dumps(c["inputs"], sort_keys=True)), c["case_id"])
            op = c["operation"]
            if op not in best or key < best[op][0]:
                best[op] = (key, c)
    for op, paths in REAL_OVERRIDES.items():
        REAL_PATHS.setdefault(op, set()).update(paths)
    return {op: v[1] for op, v in sorted(best.items())}


def real_leaves(node, real, path=()):
    """Paths to Real leaves (a float, or an integer at a path that holds a float elsewhere): dict keys in
    document order; lists at the first and the last non-null element."""
    if isinstance(node, bool):
        return
    if isinstance(node, float) or (isinstance(node, int) and norm(path) in real):
        yield path
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from real_leaves(v, real, path + (k,))
    elif isinstance(node, list):
        idx = [i for i, v in enumerate(node) if v is not None]
        for i in dict.fromkeys(idx[:1] + idx[-1:]):
            yield from real_leaves(node[i], real, path + (i,))


def get(node, path):
    for k in path:
        node = node[k]
    return node


def put(inputs, path, value):
    new = json.loads(json.dumps(inputs))
    node = new
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return new


def judged_fields(base, peer=False):
    """extra_checks hold expected values for the base input, so a same_as case (other input) never takes them."""
    names = ("tolerance_class", "tolerance_limit", "output_classes") + (() if peer else ("extra_checks",))
    keep = {k: base[k] for k in names if k in base}
    return keep


def main():
    bases = base_cases()
    by_domain = {}
    stats = {"operations": len(bases), "no_real_input": [], "leaves": 0}
    for op, b in bases.items():
        dom = op.split(".")[0]
        cases = by_domain.setdefault(dom, [])
        paths = list(dict.fromkeys(real_leaves(b["inputs"], REAL_PATHS.get(op, set()))))
        if not paths:
            stats["no_real_input"].append(op)
            continue
        for path in paths:
            stats["leaves"] += 1
            where = "/" + "/".join(str(k) for k in path)
            for t in TOKENS:
                cases.append({"operation": op, "inputs": put(b["inputs"], path, t),
                              "expected": {"status": "error", "error_code": "E_DOMAIN"},
                              "tolerance_class": "date_and_convention", "verified_by": ["rule-F-2"],
                              "tags": ["e1", "non_finite", t.lower().lstrip("-"), f"base:{b['case_id']}", f"input:{where}"]})
            v = get(b["inputs"], path)
            if v == 0 and not (isinstance(v, float) and str(v).startswith("-")):
                cases.append({"operation": op, "inputs": put(b["inputs"], path, -0.0),
                              "expected": b["expected"], **judged_fields(b),
                              "verified_by": [f"copied:{b['case_id']}", "rule-F-3"],
                              "tags": ["e1", "negative_zero", f"base:{b['case_id']}", f"input:{where}"]})
            else:
                cases.append({"operation": op, "inputs": put(b["inputs"], path, 0.0),
                              "expected": {"status": "any"}, "tolerance_class": "date_and_convention",
                              "verified_by": ["rule-F-3-anchor"],
                              "tags": ["e1", "zero_anchor", f"base:{b['case_id']}", f"input:{where}"]})
                cases.append({"operation": op, "inputs": put(b["inputs"], path, -0.0),
                              "expected": {"status": "same_as", "case_id": None}, **judged_fields(b, peer=True),
                              "verified_by": ["rule-F-3"],
                              "tags": ["e1", "negative_zero", f"base:{b['case_id']}", f"input:{where}"]})
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("e1_*.json"):
        old.unlink()
    total = 0
    written = []
    for dom, cases in sorted(by_domain.items()):
        if not cases:
            continue
        chunks, cur, size = [], [], 0
        for c in cases:
            n = len(json.dumps(c, indent=1)) * 13 // 10 + 8
            # keep an anchor and its negative-zero twin in one file
            if cur and size + n > MAX_BYTES and "zero_anchor" not in cur[-1]["tags"]:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(c)
            size += n
        chunks.append(cur)
        for j, chunk in enumerate(chunks, 1):
            suite = f"e1_{dom}" + (f"_{j}" if len(chunks) > 1 else "")
            for i, c in enumerate(chunk, 1):
                c["case_id"] = f"{suite}-{i:04d}"
            for i, c in enumerate(chunk):
                if c["expected"].get("status") == "same_as":
                    assert "zero_anchor" in chunk[i - 1]["tags"]
                    c["expected"]["case_id"] = chunk[i - 1]["case_id"]
            ordered = [{k: c[k] for k in ("case_id", "operation", "inputs", "expected", "tolerance_class") if k in c}
                       | {k: v for k, v in c.items() if k not in ("case_id", "operation", "inputs", "expected", "tolerance_class")}
                       for c in chunk]
            doc = {"schema_version": "1.0", "suite": suite, "spec": SPEC, "spec_version": "1.0.0",
                   "generator": "oracle/python/gen_stage_f_e1.py",
                   "reviewer": "none: self-assessment until the end-of-project human review", "cases": ordered}
            text = json.dumps(doc, indent=1, ensure_ascii=True) + "\n"
            assert len(text.encode()) < 1_000_000, suite
            (OUT / f"{suite}.json").write_text(text, encoding="utf-8", newline="\n")
            total += len(chunk)
            written.append((suite, len(chunk)))
    stats["cases"] = total
    stats["files"] = written
    (ROOT / "oracle" / "E1_SUMMARY.json").write_text(json.dumps(stats, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"E1: {stats['operations']} operations, {stats['leaves']} real leaves, {total} cases in {len(written)} files; "
          f"{len(stats['no_real_input'])} operations with no real input")


if __name__ == "__main__":
    main()
