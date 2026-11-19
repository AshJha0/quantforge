"""Field-by-field compare of the second H-16 blind derivation (stage_h_blind/venue2) against venue_h goldens.

Mapping, fixed before the first run (coordinator instruction 2026-11-18):
- Field names: identity. The packet fixed every output name (`fill_rates`, `markouts` elements
  `{venue, h, markout, markout_bps, toxicity}`), so no name is renamed.
- Representation only, not a difference: `h` as integer or float (5 vs 5.0); a success output with no
  `status` wrapper (golden `{status: ok, outputs: X}` against blind `X`); key order inside an object.
- Order of `markouts` is compared as given (spec: venues in code-point order, horizons in input order).
- Error cases: the code must be equal.
- Values: 1e-12 relative, or 1e-15 absolute at 0 (spec tolerance); venue_h-0010 at 1e-12 relative with absolute 0,
  as its golden states.
A case is MATCH when every golden output leaf has exactly one blind leaf at the same path, there is no extra blind
leaf, and every pair agrees. Otherwise VALUE MISMATCH or SHAPE MISMATCH, with the paths.

    python -I program/stage_h_blind_w2/venue2_compare.py <checkout>
Exit 1 if the frozen file's SHA-256 differs from the record or any case does not MATCH.
"""
import hashlib
import json
import sys
from pathlib import Path

SHA = "bae6257fd95e6b447a3b480dc7bb55fe2ecdffb5b35d00e46a2941455c86d0e2"
ABS0 = {"venue_h-0010"}


def flat(o, pre=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from flat(v, f"{pre}/{k}")
    elif isinstance(o, list):
        if not o:
            yield pre, "[]"
        for i, v in enumerate(o):
            yield from flat(v, f"{pre}[{i}]")
    else:
        yield pre, o


def agree(a, b, abs0):
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    if a == 0 or b == 0:
        return a == b if abs0 else abs(a - b) <= 1e-15
    return abs(a - b) <= 1e-12 * max(abs(a), abs(b))


def compare(cid, exp, b):
    if exp["status"] == "error":
        code = b.get("error_code") if isinstance(b, dict) else b
        return ("MATCH", "") if code == exp["error_code"] else ("VALUE MISMATCH", f"{code} vs {exp['error_code']}")
    if isinstance(b, dict) and b.get("status") == "ok" and "outputs" in b:
        b = b["outputs"]
    g, bl = dict(flat(exp["outputs"])), dict(flat(b))
    if set(g) != set(bl):
        return "SHAPE MISMATCH", f"golden only {sorted(set(g) - set(bl))}, blind only {sorted(set(bl) - set(g))}"
    bad = [p for p in g if not agree(g[p], bl[p], cid in ABS0)]
    return ("VALUE MISMATCH", f"{[(p, g[p], bl[p]) for p in bad]}") if bad else ("MATCH", "")


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    raw = (root / "stage_h_blind/venue2/blind_results.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA:
        print("frozen venue2 blind file: SHA-256 differs from the record", file=sys.stderr)
        return 1
    blind = json.loads(raw)
    bad = 0
    for c in json.loads((root / "datasets/golden/stage_h/venue_h.json").read_text(encoding="utf-8"))["cases"]:
        cid = c["case_id"]
        if cid not in blind:
            print(f"{cid}\tNOT COMPUTED")
            continue
        st, why = compare(cid, c["expected"], blind[cid])
        bad += st != "MATCH"
        print(f"{cid}\t{st}" + (f"\t{why}" if why else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
