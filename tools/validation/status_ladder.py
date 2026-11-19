#!/usr/bin/env python3
"""Writes the generated tables of docs/validation/status-ladder.md from oracle/OUTSIDE_SHARES.json.

    python tools/validation/status_ladder.py            rewrite the block between the two markers
    python tools/validation/status_ladder.py --check    exit 1 if the committed block differs
    python tools/validation/status_ladder.py --json F   read another shares file (e.g. a lane branch's copy)

The shares themselves are computed by tools/outside_shares.py (rule R6-13, decision D6, plan section 15); this
script only lays them out, so the page cannot carry a total that the tool did not compute. Standard library only.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "validation" / "status-ladder.md"
BEGIN = "<!-- generated:status-ladder:begin (tools/validation/status_ladder.py; do not edit by hand) -->"
END = "<!-- generated:status-ladder:end -->"


def pct(x):
    return f"{100 * x:.1f}%"


def render(doc):
    floor = doc["floor"]
    out = [
        f"Source: `oracle/OUTSIDE_SHARES.json` (written by `tools/outside_shares.py`). Floor: {pct(floor)} of value-checked "
        "cases, without generated sweeps. \"Library\" counts `library-object` and `library-primitive`; \"with re-derivation\" "
        "adds blind `independent-rederivation` cases where the rule allows them.",
        "",
        "| Stage | Value cases | Library | Library share | With re-derivation | Share with re-derivation | Floor |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for stage, s in doc["stages"].items():
        w = s["without_sweeps"]
        out.append(f"| {stage} | {w['cases']} | {w['counted']} | {pct(w['share'])} | {w['counted_with_rederivation']} | "
                   f"{pct(w['share_with_rederivation'])} | {'met' if s.get('meets_floor') else 'NOT MET'} |")
    for stage, s in doc["stages"].items():
        items = s.get("per_item")
        if not items:
            continue
        out += ["", f"Stage {stage} per plan item (plan section 15: at least {pct(floor)} of each item's value cases):", "",
                "| Item | Suites | Value cases | Counted | Share | Per item |", "|---|---|---:|---:|---:|---|"]
        for item, v in sorted(items.items(), key=lambda kv: kv[0]):
            suites = ", ".join(f"`{x}`" for x in v.get("suites", []))
            out.append(f"| {item} | {suites} | {v['cases']} | {v['counted_with_rederivation']} | "
                       f"{pct(v['share_with_rederivation'])} | {'met' if v.get('meets_item_floor') else 'NOT MET'} |")
    return "\n".join(out)


def splice(text, block):
    i, j = text.index(BEGIN) + len(BEGIN), text.index(END)
    return text[:i] + "\n" + block + "\n" + text[j:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", default=str(ROOT / "oracle" / "OUTSIDE_SHARES.json"))
    a = ap.parse_args()
    doc = json.loads(Path(a.json).read_text(encoding="utf-8"))
    text = PAGE.read_text(encoding="utf-8")
    new = splice(text, render(doc))
    if a.check:
        if new != text:
            print(f"{PAGE.relative_to(ROOT)} is stale: run python tools/validation/status_ladder.py", file=sys.stderr)
            return 1
        print("status ladder page up to date")
        return 0
    PAGE.write_text(new, encoding="utf-8", newline="\n")
    print(f"wrote {PAGE.relative_to(ROOT)}: {len(doc['stages'])} stages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
