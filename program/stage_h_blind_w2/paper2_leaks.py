"""Leak list for paper blind packet 2 (coordinator only; never put it in the packet).

For each packet case, every expected output leaf (string or number) that does not also occur in that case's own
inputs, and is not a generic token (labels, statuses, sides, small integers), is searched for in every packet
file. A hit on a line that also names the case id is a hard leak; other hits are listed for the coordinator.
    python -I program/stage_h_blind_w2/paper2_leaks.py <checkout> <packet dir> > <outside dir>/paper2_LEAKS.tsv
Exit 1 on any hard leak.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper2_blind import CASES  # noqa: E402

GENERIC = {"0", "1", "2", "3", "-1", "ok", "DONE", "REJECTED", "CLOSED", "BUY", "SELL", "LIT", "SOR", "DARK",
           "BTC-USD", "ORDER", "FILL", "LIMIT", "MARKET", "crypto venue; simulated",
           "0000000000000000000000000000000000000000000000000000000000000000"}


def leaves(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)
    elif o is not None and not isinstance(o, bool):
        yield str(o)


def main():
    root, pk = Path(sys.argv[1]), Path(sys.argv[2])
    files = sorted(p for p in pk.iterdir() if p.suffix in (".md", ".json"))
    lines = [(p.name, i + 1, ln) for p in files for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines())]
    gold = {c["case_id"]: c for c in json.loads((root / "datasets/golden/stage_h/pt_h.json").read_text(encoding="utf-8"))["cases"]}
    hard = 0
    print("case\tvalue\tfile:line\tsame_line_case_id\ttext")
    for cid in CASES:
        c = gold[cid]
        own = set(leaves(c["inputs"]))
        vals = {v for v in leaves(c["expected"].get("outputs", {}))
                if v not in GENERIC and v not in own and len(v) > 1 and not v.startswith("Paper trading on free data")}
        for v in sorted(vals):
            pat = re.compile(r"(?<![\w.])" + re.escape(v) + r"(?![\w])")
            for name, n, ln in lines:
                if pat.search(ln):
                    same = cid in ln
                    hard += same
                    print(f"{cid}\t{v[:40]}\t{name}:{n}\t{'YES' if same else 'no'}\t{ln.strip()[:140]}")
        for name, n, ln in lines:  # the case named next to a verdict word
            if cid in ln and name != "pt_h.inputs.json" and re.search(r"PARSE|HASH|LINK|LABEL|trimmed|E_LIMIT|28-digit", ln):
                hard += 1
                print(f"{cid}\t(verdict)\t{name}:{n}\tYES\t{ln.strip()[:140]}")
    print(f"# hard leaks: {hard}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
