"""R6-9: E1 (non-finite input) goldens for every operation of specifications/name-map.json that lacked one (finding 10).

For each such operation, the first `ok` golden case (in file order) is taken, and its first binary64 input (depth first, in
document order, ruling F-2) is replaced by "NaN"; a second case replaces the last binary64 input by "-Infinity". Rule
F-2: the finite check comes after E_PARSE, E_SCHEMA and E_LIMIT and before every other check, so the expected code is
E_DOMAIN whatever else the inputs hold. Only values written as JSON reals (Python float) are replaced, never integers,
so an Integer field cannot become a Real.

Operations with no Real input anywhere in their goldens are exempt (they cannot receive a non-finite value); the list is
written to conformance/E1_EXEMPT.json and checked by tools/check_e1_coverage.py.

    cd oracle/python && uv run python -W ignore gen_r6_e1.py
    cd oracle/python && uv run python -W ignore gen_r6_e1.py J   # stage J: e1_j for operations still uncovered

Mode J writes datasets/golden/stage_j/e1_j.json for the operations that e1_r6 and every other golden leave uncovered
(stage J waves 1 to 3 and the curves operations), so the e1_r6 case ids stay as they are. It does not rewrite
conformance/E1_EXEMPT.json beyond adding newly exempt operations (no Real input in any golden).
"""
import copy
import json
import sys
from pathlib import Path

from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_r6_e1.py"
STAGE_J = "J" in sys.argv[1:]
SUITE, OUT_DIR = ("e1_j", "stage_j") if STAGE_J else ("e1_r6", "r6")
ROOT = Path(__file__).resolve().parents[2]
NF = {"NaN", "Infinity", "-Infinity"}


def has_nf(v):
    if isinstance(v, str):
        return v in NF
    if isinstance(v, list):
        return any(has_nf(x) for x in v)
    if isinstance(v, dict):
        return any(has_nf(x) for x in v.values())
    return False


def real_paths(v, path=()):
    if isinstance(v, float):
        yield path
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from real_paths(x, path + (i,))
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from real_paths(x, path + (k,))


def put(d, path, val):
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = val


def main():
    ops = sorted(json.loads((ROOT / "specifications" / "name-map.json").read_text(encoding="utf-8"))["operations"])
    first, covered, any_real = {}, set(), {}
    for p in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
        if p.parent.name == OUT_DIR and p.stem == SUITE:
            continue
        for c in json.loads(p.read_text(encoding="utf-8")).get("cases", []):
            op = c["operation"]
            if c["expected"]["status"] == "error" and c["expected"].get("error_code") == "E_DOMAIN" and has_nf(c["inputs"]):
                covered.add(op)
            if c["expected"]["status"] == "ok" and op not in first and "limit" not in c["case_id"] and "limit" not in c.get("tags", []):
                first[op] = c
            any_real[op] = any_real.get(op, False) or any(True for _ in real_paths(c["inputs"]))
    s = Suite(SUITE, "specifications/stage-f-rulings.md", G)
    exempt = {}
    for op in ops:
        if op in covered:
            continue
        if not any_real.get(op):
            exempt[op] = "no Real input in any golden: a non-finite value cannot be sent"
            continue
        c = first.get(op)
        paths = list(real_paths(c["inputs"])) if c else []
        if not paths:
            src = next(cc for p in sorted((ROOT / "datasets" / "golden").rglob("*.json")) for cc in json.loads(p.read_text(encoding="utf-8")).get("cases", [])
                       if cc["operation"] == op and any(True for _ in real_paths(cc["inputs"])))
            c, paths = src, list(real_paths(src["inputs"]))
        for path, tok in ((paths[0], "NaN"), (paths[-1], "-Infinity")):
            inp = copy.deepcopy(c["inputs"])
            put(inp, path, tok)
            s.add(op, inp, error="E_DOMAIN", cls="date_and_convention", tags=["r6", "e1", "non-finite-input"],
                  description=f"F-2: {tok} at {'/'.join(map(str, path))} (from {c['case_id']})")
            if len(paths) == 1:
                break
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / OUT_DIR
    s.write()
    common.GOLDEN = keep
    if STAGE_J:
        known = json.loads((ROOT / "conformance" / "E1_EXEMPT.json").read_text(encoding="utf-8"))
        assert set(known) <= set(exempt), f"an exempt operation gained a Real input: {sorted(set(known) - set(exempt))}"
        (ROOT / "conformance" / "E1_EXEMPT.json").write_text(json.dumps(exempt, indent=1, sort_keys=True) + "\n",
                                                             encoding="utf-8", newline="\n")
        note(f"exempt: {len(exempt)} operations, new {sorted(set(exempt) - set(known))}")
        note(f"{SUITE}: {len(s.cases)} cases for {len({c['operation'] for c in s.cases})} operations")
        return
    (ROOT / "conformance" / "E1_EXEMPT.json").write_text(json.dumps(exempt, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    note(f"e1_r6: {len(s.cases)} cases for {len({c['operation'] for c in s.cases})} operations; {len(exempt)} exempt")


if __name__ == "__main__":
    main()
