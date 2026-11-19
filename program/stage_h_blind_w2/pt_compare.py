"""Field-by-field compare of the frozen wave 2b blind file (pt_h part) against datasets/golden/stage_h/pt_h.json.

Mapping, fixed before the first run (coordinator instruction 2026-11-18; written and committed before this script
was ever executed):
- Field names: identity. The spec's golden output shapes took the blind lane's names, so nothing is renamed.
- Representation only, not a difference:
  - decimal strings compared as exact decimals ("-0.60" equals "-0.6"); every other leaf compared exactly;
  - the golden `paper.ledger.verify` output is flat, the blind one wraps it in `verify`: the wrapper is removed;
  - a success golden `{status: ok, outputs: X}` against blind `X`; an error golden against blind `{"error": code}`;
  - key order.
- Golden leaves not compared, because the blind packet never asked for them: `label` (the HR-43 tag, added to every
  CLI output after the blind run) and `head` (verify output added by the CLI lane).
- Nothing else is excluded. A case is MATCH when every remaining golden leaf has exactly one blind leaf at the same
  path, there is no extra blind leaf, and every pair agrees. Otherwise VALUE MISMATCH or SHAPE MISMATCH, with paths.
- Cases in the golden file that the blind lane did not compute (pt_h-0030 onward) are NOT COMPUTED.

    python -I program/stage_h_blind_w2/pt_compare.py <checkout>
Exit 1 if the frozen file's SHA-256 differs from the record in program/STAGE_H_BLIND_WAVE2B.md.
"""
import hashlib
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

SHA = "75856d3012237785452d033e262cb504407b53b621abef3f4007c02eae1352b0"
SKIP = {"label", "head"}


def flat(o, pre=""):
    if isinstance(o, dict):
        for k, v in o.items():
            if pre == "" and k in SKIP:
                continue
            yield from flat(v, f"{pre}/{k}")
    elif isinstance(o, list):
        if not o:
            yield pre, "[]"
        for i, v in enumerate(o):
            yield from flat(v, f"{pre}[{i}]")
    else:
        yield pre, o


def agree(a, b):
    if isinstance(a, str) and isinstance(b, str):
        try:
            return Decimal(a) == Decimal(b)
        except InvalidOperation:
            return a == b
    return type(a) is type(b) and a == b


def compare(exp, b):
    if exp["status"] == "error":
        code = b.get("error") if isinstance(b, dict) else b
        return ("MATCH", "") if code == exp["error_code"] else ("VALUE MISMATCH", f"{code} vs {exp['error_code']}")
    if isinstance(b, dict) and set(b) == {"verify"}:
        b = b["verify"]
    g, bl = dict(flat(exp["outputs"])), dict(flat(b))
    if set(g) != set(bl):
        return "SHAPE MISMATCH", f"golden only {sorted(set(g) - set(bl))}, blind only {sorted(set(bl) - set(g))}"
    bad = [p for p in g if not agree(g[p], bl[p])]
    return ("VALUE MISMATCH", f"{[(p, g[p], bl[p]) for p in bad]}") if bad else ("MATCH", "")


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    raw = (root / "stage_h_blind/wave2b/blind_results.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA:
        print("frozen wave2b blind file: SHA-256 differs from the record", file=sys.stderr)
        return 1
    blind = json.loads(raw)
    blind = blind.get("results", blind)
    for c in json.loads((root / "datasets/golden/stage_h/pt_h.json").read_text(encoding="utf-8"))["cases"]:
        cid = c["case_id"]
        if cid not in blind:
            print(f"{cid}\tNOT COMPUTED")
            continue
        st, why = compare(c["expected"], blind[cid])
        print(f"{cid}\t{st}" + (f"\t{why}" if why else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
