"""Field-by-field re-compare of the frozen micro blind output (H-4b mest_h, H-16 venue_h) against the goldens.

Coordinator decision 2026-11-18: the first micro compare (wave2_compare.py ... micro) matched numbers as sorted
multisets, which cannot see two values swapped between fields, so its SHAPE-ONLY cases were not counted. The spec
now fixes every output name, so this script maps each blind name to one spec name with the fixed table FIELD_MAP
below (written before this compare was run, one to one), then compares leaf by leaf.

A case is FIELDWISE MATCH only when (a) every blind leaf maps to a golden output path, (b) every golden output
leaf is reached by exactly one blind leaf, and (c) every pair agrees to the spec tolerance (1e-12 relative,
1e-15 absolute at 0). Anything else is NOT COUNTED, with the reason. Error cases compare the code exactly.

    python -I program/stage_h_blind_w2/micro_fieldwise.py <checkout>
Standard library only. Exit 1 if the frozen file's SHA-256 differs from the record.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

SHA = "975000bfcf123c983b3e444f6234685ce2b666378405f173585ab9318a6bf0f3"
# Blind name -> spec name (one to one). Leaf keys only; structure rules below.
FIELD_MAP = {"beta": "lambda_as", "SE": "se", "ratio": "ratio",
             "lambda": "lambda", "theta": "theta", "kappa": "kappa", "alpha": "alpha", "delta": "delta",
             "markout": "markout", "markout_bps": "markout_bps", "toxicity": "toxicity"}
# Structure: mest_h-0009 "<regime>.<leaf>" -> "regimes.<regime>.<leaf'>"; venue "<V>|h=<H>.<leaf>" -> the markouts
# element with venue V and h H; venue "fill_rate|<V>" -> "fill_rates.<V>"; any other top-level leaf -> its mapped name.
VENUE_KEY = re.compile(r"^(?P<v>[^|]+)\|h=(?P<h>-?[0-9.]+)$")
FILL_KEY = re.compile(r"^fill_rate\|(?P<v>.+)$")


def close(a, b):
    return abs(a - b) <= 1e-15 if a == 0 or b == 0 else abs(a - b) <= 1e-12 * max(abs(a), abs(b))


def golden_leaves(out):
    """Golden outputs as {path: number}; markouts elements keyed by (venue, h)."""
    leaves = {}
    for k, v in out.items():
        if k == "markouts":
            for m in v:
                for f in ("markout", "markout_bps", "toxicity"):
                    leaves[f"markouts[{m['venue']},{float(m['h'])}].{f}"] = m[f]
            if not v:
                leaves["markouts"] = "[]"
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, dict):
                    for k3, v3 in v2.items():
                        leaves[f"{k}.{k2}.{k3}"] = v3
                else:
                    leaves[f"{k}.{k2}"] = v2
        else:
            leaves[k] = v
    return leaves


def blind_leaves(cid, b):
    """Blind output mapped to golden paths; raises KeyError on an unmapped name."""
    out = {}
    for k, v in b.items():
        mv, mf = VENUE_KEY.match(k), FILL_KEY.match(k)
        if mv:
            for f, x in v.items():
                out[f"markouts[{mv['v']},{float(mv['h'])}].{FIELD_MAP[f]}"] = x
        elif mf:
            out[f"fill_rates.{mf['v']}"] = v
        elif isinstance(v, dict):  # mest_h-0009 regimes
            for f, x in v.items():
                out[f"regimes.{k}.{FIELD_MAP[f]}"] = x
        else:
            out[FIELD_MAP[k]] = v
    return out


def compare(exp, b):
    if exp["status"] == "error":
        return ("FIELDWISE MATCH", "") if b == exp["error_code"] else ("NOT COUNTED", f"code {b} vs {exp['error_code']}")
    if not isinstance(b, dict):
        return "NOT COUNTED", f"blind gave {b!r}"
    try:
        bl = blind_leaves(None, b)
    except KeyError as e:
        return "NOT COUNTED", f"unmapped blind name {e}"
    gl = golden_leaves(exp["outputs"])
    if set(bl) - set(gl):
        return "NOT COUNTED", f"blind paths not in golden: {sorted(set(bl) - set(gl))}"
    if set(gl) - set(bl):
        return "NOT COUNTED", f"golden fields the blind lane did not produce: {sorted(set(gl) - set(bl))}"
    bad = [p for p in gl if not close(float(gl[p]), float(bl[p]))]
    return ("NOT COUNTED", f"values differ at {bad}") if bad else ("FIELDWISE MATCH", "")


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    raw = (root / "stage_h_blind/micro/blind_results.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA:
        print("frozen micro blind file: SHA-256 differs from the record", file=sys.stderr)
        return 1
    blind = json.loads(raw)
    for suite in ("mest_h", "venue_h"):
        for c in json.loads((root / f"datasets/golden/stage_h/{suite}.json").read_text(encoding="utf-8"))["cases"]:
            cid = c["case_id"]
            if cid not in blind:
                print(f"{cid}\tNOT IN PACKET")
                continue
            st, why = compare(c["expected"], blind[cid])
            if st == "FIELDWISE MATCH" and "not blind" in " ".join(c["verified_by"]):
                st, why = "NOT COUNTED", "golden marked not blind-checked (input changed after the blind lane)"
            print(f"{cid}\t{st}" + (f"\t{why}" if why else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
