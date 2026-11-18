"""Leak list for the H-16 venue blind packet (coordinator only; never put it in the packet).

For each venue_h case, every expected output value (bar 0, 1, -1, 2, 5 and 10, which occur as ordinary text) and
each error verdict is searched for in the packet text. A hit on a line that also names the case id is a hard leak;
other hits are listed for the coordinator to judge.
    python -I program/stage_h_blind_w2/venue_leaks.py <checkout> <packet dir> > <outside dir>/venue2_LEAKS.tsv
Exit 1 on any hard leak.
"""
import json
import re
import sys
from pathlib import Path

GENERIC = {"0", "0.0", "1", "1.0", "-1", "-1.0", "2", "2.0", "5", "5.0", "10", "10.0"}


def leaves(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        yield o


def forms(x):
    out = {repr(x), str(x), f"{x:.15g}"}
    if float(x).is_integer():
        out.add(str(int(x)))
    return out - GENERIC


def main():
    root, pk = Path(sys.argv[1]), Path(sys.argv[2])
    lines = [(p.name, i + 1, ln) for p in sorted(pk.glob("*.md"))
             for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines())]
    hard = 0
    print("case\tvalue\tfile:line\tsame_line_case_id\ttext")
    for c in json.loads((root / "datasets/golden/stage_h/venue_h.json").read_text(encoding="utf-8"))["cases"]:
        cid, e = c["case_id"], c["expected"]
        for x in set(leaves(e.get("outputs", {}))):
            for f in forms(x):
                pat = re.compile(r"(?<![\w.])" + re.escape(f) + r"(?![\w])")
                for name, n, ln in lines:
                    if pat.search(ln):
                        same = cid in ln
                        hard += same
                        print(f"{cid}\t{f}\t{name}:{n}\t{'YES' if same else 'no'}\t{ln.strip()[:160]}")
        if e.get("status") == "error":
            for name, n, ln in lines:
                if re.search(re.escape(cid) + r"[^|]{0,40}" + e["error_code"], ln):
                    hard += 1
                    print(f"{cid}\t{e['error_code']}\t{name}:{n}\tYES\t{ln.strip()[:160]}")
    print(f"# hard leaks: {hard}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
