"""Field-by-field compare of paper blind lane 2 (stage_h_blind/paper2) against the pt_h goldens.

Mapping, fixed and committed before the first run (coordinator instruction 2026-11-18; pattern venue2_compare.py):
- Field names: identity. The packet fixed every output name and shape (paper-trading.md, cli-contract.md).
- Representation only, not a difference: a success output with no `status` wrapper (golden `{status: ok,
  outputs: X}` against blind `X`); key order inside an object.
- Lists are compared position by position (records, results, reasons are ordered by the spec).
- Strings (HR-12 decimal strings, hashes, ids, reasons, labels) are compared exactly; JSON numbers (the binary64
  TCA values, `seq`, `first_bad_seq`, `records`) at 1e-12 relative, or 1e-15 absolute at 0; booleans and null exactly.
- Every golden leaf needs exactly one blind leaf at the same path and no extra blind leaf.
Classes: MATCH; VALUE MISMATCH (paths listed); SHAPE MISMATCH (paths listed).
Not-blind rules applied after the compare (coordinator, 2026-11-18), printed as NOT BLIND with the reason:
- pt_h-0032: the packet lacked exec.sor.allocate and the dark simulator; the lane guessed the allocation.
- a case whose golden has a FILL record from the LIT venue: `child_id` for LIT was unspecified in the packet and
  the lane assumed it; the child_id enters the record hash, the next record's `prev` and `head`, so it decides
  those fields.

    python -I program/stage_h_blind_w2/paper2_compare.py <checkout>
Exit 1 if the frozen file's SHA-256 differs from the record.
"""
import hashlib
import json
import sys
from pathlib import Path

SHA = "8964eebcaba91aeab49db01887c16b389dd8eb770f0485d7d1186c6cb6636627"
PACKET_GAP = {"pt_h-0032": "packet gap: exec.sor.allocate and the dark simulator were not in the packet; allocation guessed"}


def flat(o, pre=""):
    if isinstance(o, dict):
        if not o:
            yield pre, "{}"
        for k, v in o.items():
            yield from flat(v, f"{pre}/{k}")
    elif isinstance(o, list):
        if not o:
            yield pre, "[]"
        for i, v in enumerate(o):
            yield from flat(v, f"{pre}[{i}]")
    else:
        yield pre, o


def agree(a, b):
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return type(a) is type(b) and a == b
    if a == 0 or b == 0:
        return abs(a - b) <= 1e-15
    return abs(a - b) <= 1e-12 * max(abs(a), abs(b))


def lit_fill(outputs):
    recs = outputs.get("records")  # an integer count in paper.ledger.verify (fixed after the first run crashed)
    return isinstance(recs, list) and any(r.get("kind") == "FILL" and r.get("body", {}).get("venue", "LIT") == "LIT"
                                          for r in recs if isinstance(r, dict))


def compare(exp, b):
    if exp["status"] == "error":
        code = b.get("error_code") if isinstance(b, dict) else b
        return ("MATCH", "") if code == exp["error_code"] else ("VALUE MISMATCH", f"{code} vs {exp['error_code']}")
    if isinstance(b, dict) and b.get("status") == "ok" and "outputs" in b:
        b = b["outputs"]
    g, bl = dict(flat(exp["outputs"])), dict(flat(b))
    if set(g) != set(bl):
        return "SHAPE MISMATCH", f"golden only {sorted(set(g) - set(bl))}; blind only {sorted(set(bl) - set(g))}"
    bad = [p for p in g if not agree(g[p], bl[p])]
    return ("VALUE MISMATCH", "; ".join(f"{p}: golden {g[p]!r} blind {bl[p]!r}" for p in bad)) if bad else ("MATCH", "")


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    raw = (root / "stage_h_blind/paper2/blind_results.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA:
        print("frozen paper2 blind file: SHA-256 differs from the record", file=sys.stderr)
        return 1
    blind = json.loads(raw)
    gold = {c["case_id"]: c for c in json.loads((root / "datasets/golden/stage_h/pt_h.json").read_text(encoding="utf-8"))["cases"]}
    for cid in sorted(blind):
        exp = gold[cid]["expected"]
        st, why = compare(exp, blind[cid])
        print(f"{cid}\t{st}" + (f"\t{why}" if why else ""))
        if cid in PACKET_GAP:
            print(f"{cid}\tNOT BLIND\t{PACKET_GAP[cid]}")
        elif exp["status"] == "ok" and lit_fill(exp["outputs"]):
            print(f"{cid}\tNOT BLIND\tLIT child_id unspecified in the packet; it enters hashes, prev and head")
    return 0


if __name__ == "__main__":
    sys.exit(main())
