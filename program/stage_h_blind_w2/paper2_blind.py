"""Paper-trading blind packet 2 (H-21): the pt_h value cases with no blind check yet. Run by
`wave2_make_packet.sh <checkout> <packet dir> paper2` after the awk extraction.

Writes into the packet: the paper section of cli-contract.md (operations, inputs, byte-exact hash rule), and
pt_h.inputs.json (case id, operation, inputs only). Removes from the stripped spec the passages that state or hint
an expected result of a packet case; each removal must match exactly once, so a moved passage fails the build.
Leak list: `paper2_leaks.py`, kept outside the packet.

    python -I paper2_blind.py <checkout> <packet dir>
"""
import json
import re
import sys
from pathlib import Path

CASES = ["pt_h-0030", "pt_h-0031", "pt_h-0032", "pt_h-0050", "pt_h-0051", "pt_h-0054"]
RULES = [
    # HR-77 names the packet goldens with their outcomes (trim result, context failure, E_LIMIT pair).
    ("paper-trading.blind.md", r" Goldens pt_h-0032 \(SOR trim[^|]*?`E_LIMIT`\)\."),
    # HR-78 names pt_h-0054 as the duplicate-key golden, which gives its verdict.
    ("paper-trading.blind.md", r" Golden pt_h-0054\."),
    # Describes pt_h-0030/0031 outcomes and the earlier blind status.
    ("paper-trading.blind.md", r" Further hand cases in the golden file, not blind: pt_h-0030 and 0031 .*?also not blind\)\."),
]


def main():
    root, pk = Path(sys.argv[1]), Path(sys.argv[2])
    contract = (root / "specifications/cli-contract.md").read_text(encoding="utf-8")
    m = re.search(r"^## Stage H paper trading operations.*?(?=^## |\Z)", contract, flags=re.S | re.M)
    if not m:
        print("cli-contract.md: paper section not found", file=sys.stderr)
        return 1
    (pk / "paper-cli.blind.md").write_text(m.group(0), encoding="utf-8", newline="\n")
    for name, pat in RULES:
        p = pk / name
        s = p.read_text(encoding="utf-8")
        s2, n = re.subn(pat, "", s, flags=re.S)
        if n != 1:
            print(f"{name}: rule {pat!r} matched {n} times", file=sys.stderr)
            return 1
        p.write_text(s2, encoding="utf-8", newline="\n")
    gold = json.loads((root / "datasets/golden/stage_h/pt_h.json").read_text(encoding="utf-8"))["cases"]
    by = {c["case_id"]: c for c in gold}
    out = {cid: {"operation": by[cid]["operation"], "inputs": by[cid]["inputs"]} for cid in CASES}
    (pk / "pt_h.inputs.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
