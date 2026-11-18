"""Stage H wave 2 comparison (DR-H2): spec-lane expected vs frozen blind results.

Usage: python -I wave2_compare.py <quantforge checkout> <blind_results.json>

Expected values are read from the "Golden value cases" tables (Case | Input |
Expected) of order-book.md and lit-matching.md. blind_results.json maps case id
to the blind lane's output object. Each pair is compared byte for byte after
canonical JSON (sorted keys, no spaces, HR-29); numbers that the spec gives as
decimal strings must be strings on both sides (HR-12), so no float coercion is
done. On a mismatch the book is compared level by level (MBP levels and, for
lit cases, MBO orders) and the other top-level keys are listed. Prints one
line per case: MATCH, MISMATCH or MISSING. Exit code 1 if any is not MATCH.
"""
import json
import sys
from pathlib import Path

SPECS = ["specifications/09-microstructure/order-book.md", "specifications/10-execution/lit-matching.md"]


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def expected(root):
    out = {}
    for rel in SPECS:
        intable = False
        for line in (Path(root) / rel).read_text(encoding="utf-8").splitlines():
            if line.startswith("| Case | Input | Expected |"):
                intable = True
                continue
            if intable and line.startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if cells[0].startswith(("ob_h-", "lit_h-")):
                    out[cells[0]] = json.loads(cells[2])
            elif intable:
                intable = False
    return out


def level_diff(e, b, side_key):
    rows = []
    ev, bv = e.get(side_key, []), b.get(side_key, [])
    for k in range(max(len(ev), len(bv))):
        x = ev[k] if k < len(ev) else None
        y = bv[k] if k < len(bv) else None
        if canon(x) != canon(y):
            rows.append(f"    {side_key}[{k}]: spec={canon(x)} blind={canon(y)}")
    return rows


def main():
    root, blind_path = sys.argv[1], sys.argv[2]
    exp = expected(root)
    blind = json.loads(Path(blind_path).read_text(encoding="utf-8"))
    bad = 0
    for cid in sorted(exp):
        if cid not in blind:
            print(f"{cid}\tMISSING")
            bad += 1
            continue
        e, b = exp[cid], blind[cid]
        if canon(e) == canon(b):
            print(f"{cid}\tMATCH")
            continue
        bad += 1
        print(f"{cid}\tMISMATCH")
        for key in sorted(set(e) | set(b)):
            if canon(e.get(key)) != canon(b.get(key)) and key not in ("book", "mbp"):
                print(f"  {key}: spec={canon(e.get(key))} blind={canon(b.get(key))}")
        for bk in ("book", "mbp"):
            eb, bb = e.get(bk) or {}, b.get(bk) or {}
            for side in ("bids", "asks"):
                for r in level_diff(eb, bb, side):
                    print(f"  {bk}:" + r.strip())
    extra = sorted(set(blind) - set(exp))
    if extra:
        print("blind-only cases (ignored): " + ", ".join(extra))
    print(f"{len(exp) - bad}/{len(exp)} MATCH")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
