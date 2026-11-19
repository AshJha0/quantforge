"""Field-by-field compare of the SA-CCR blind derivation (stage_k_blind/saccr) with datasets/golden/stage_k/saccr_k.json.

Mapping and tolerances, fixed and committed before the first run:
- Field names: identity (the spec names every output: ead, rc, pfe, multiplier, addon_aggregate, addon, v, c, margined,
  mpor_days, ead_unmargined, capped, hedging_sets[asset_class, treatment, key, addon], trades[id,
  supervisory_duration, adjusted_notional, maturity_factor, delta, effective_notional, supervisory_factor]).
- Not compared (spec says only "the margined figures when margined", no names): any per-trade key other than the
  seven named above. Such keys are listed as UNNAMED, never as a match or a mismatch.
- Numbers: tolerance class simple_analytic as the spec states, 1e-12 absolute + 1e-10 relative:
  |a - b| <= 1e-12 + 1e-10 |golden|. Integer against float is representation only. Booleans, strings, null exact.
- The golden wraps outputs in an "outputs" object (found by run 1, which compared nothing: every leaf was shape-only);
  representation only, so the compare reads gold["expected"]["outputs"] (run 2 is the record).
- Arrays (hedging_sets, trades) compared by position (the spec fixes their order).
- Verdicts: MATCH (every named leaf present on both sides and equal), VALUE MISMATCH (a shared leaf differs),
  SHAPE MISMATCH (a named leaf missing on one side, values otherwise equal).
- NOT BLIND cases (leaks listed in stage_k_blind/saccr/notes.md: 0006, 0013, 0015, 0016) are compared and reported but
  do not count toward the outside share.
- The frozen file's SHA-256 is checked first.

    python -I program/stage_h_blind_w2/saccr_compare.py .
"""
import hashlib
import json
import sys
from pathlib import Path

SHA = "370a54bd09f9a68c8041c9d5ecd18bed857b704b960cc15333e9ec6e4738e47b"
NOT_BLIND = {"saccr_k-0006", "saccr_k-0013", "saccr_k-0015", "saccr_k-0016"}
TRADE_KEYS = {"id", "supervisory_duration", "adjusted_notional", "maturity_factor", "delta", "effective_notional",
              "supervisory_factor"}


def leaves(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from leaves(v, f"{path}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from leaves(v, f"{path}[{i}]")
    else:
        yield path, x


def named(path):
    if path.startswith("/trades["):
        return path.split("/")[-1] in TRADE_KEYS
    return True


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def agree(g, b):
    if num(g) and num(b):
        return abs(g - b) <= 1e-12 + 1e-10 * abs(g)
    return g == b and type(g) is type(b)


def main():
    root = Path(sys.argv[1])
    bp = root / "stage_k_blind/saccr/blind_results.json"
    if hashlib.sha256(bp.read_bytes()).hexdigest() != SHA:
        print("FROZEN FILE HASH MISMATCH")
        return 2
    blind = json.loads(bp.read_text(encoding="utf-8"))
    gold = {c["case_id"]: c for c in json.loads((root / "datasets/golden/stage_k/saccr_k.json").read_text(encoding="utf-8"))["cases"]}
    bad = 0
    for cid in sorted(blind):
        g = dict(leaves(gold[cid]["expected"]["outputs"]))
        b = dict(leaves(blind[cid]))
        val, shape, unnamed = [], [], []
        for p in sorted(set(g) | set(b)):
            if not named(p):
                unnamed.append(p)
                continue
            if p in g and p in b:
                if not agree(g[p], b[p]):
                    val.append((p, g[p], b[p]))
            else:
                shape.append((p, "golden-only" if p in g else "blind-only"))
        v = "VALUE MISMATCH" if val else ("SHAPE MISMATCH" if shape else "MATCH")
        tag = "NOT BLIND" if cid in NOT_BLIND else "blind"
        print(f"{cid}\t{v}\t{tag}\tleaves={len(g)}\tunnamed={len(unnamed)}")
        for p, gv, bv in val:
            print(f"   VALUE {p}: golden={gv!r} blind={bv!r}")
        for p, w in shape:
            print(f"   SHAPE {p}: {w}")
        if v != "MATCH":
            bad += 1
    print("non-MATCH cases:", bad)
    return 0


sys.exit(main())
