"""Stage K wave-1 blind packet (k1 mode of wave2_make_packet.sh) and its leak list.

    python -I k1_blind.py build <checkout> <packet dir>
    python -I k1_blind.py leaks <checkout> <packet dir> > <outside dir>/LEAKS.tsv

build: for each wave-1 spec, drops every block between "<!-- blind:strip -->" and "<!-- /blind:strip -->"
(derivations, hand intermediates, the oracle-pending idr_k-0005) and, in every markdown table, every column whose
header starts with "Expected", "Check", "Why" or "Derivation". Output field names stay in the text above each
table, so the blind lane knows what to produce. The rulings file is copied unchanged.

leaks: reads the removed Expected/Check cells from the source specs and searches the packet for each value
(numbers in several spellings, error codes and status words next to a case id). A hit on a line naming the case
id is a hard leak; other hits are listed for the coordinator. Exit 1 on any hard leak or on a strip marker left
in the packet. The leak list never goes into the packet.
"""
import re
import sys
from pathlib import Path

SPECS = {
    "bitemporal-store": "specifications/01-core/bitemporal-store.md",
    "incremental-update": "specifications/02-curves/incremental-update.md",
    "recalibration-triggers": "specifications/03-calibration/recalibration-triggers.md",
    "intraday-risk-bounds": "specifications/06-risk/intraday-risk-bounds.md",
    "bermudan-ladder-k8": "specifications/06-risk/bermudan-ladder-k8.md",
}
RULINGS = "specifications/stage-k-rulings-w1.md"
DROP = ("Expected", "Check", "Why", "Derivation")
CASE = re.compile(r"\b(bt|inc|trig|idr|rich)_k-\d{4}\b")
GENERIC = {"0", "1", "2", "3", "4", "5", "10", "0.0", "1.0", "2.0", "10.0", "null", "true", "false"}


def cells(row):
    r = row.replace("\\|", "\x01")
    return [c.strip().replace("\x01", "\\|") for c in r.split("|")[1:-1]]


def strip(text):
    out, skip, keep, removed, table = [], False, None, [], False
    for ln in text.splitlines():
        s = ln.strip()
        if s == "<!-- blind:strip -->":
            skip = True
            continue
        if s == "<!-- /blind:strip -->":
            skip = False
            continue
        if skip:
            removed.append(("prose", ln, ""))
            continue
        if s.startswith("|"):
            c = cells(s)
            if not table:
                table, head = True, c
                keep = [i for i, h in enumerate(c) if not h.startswith(DROP)]
            elif not set(s) <= set("|-: "):
                cid = c[0]
                given = " | ".join(c[i] for i in keep if i < len(c))
                for i, h in enumerate(head):
                    if i not in keep and i < len(c) and h.startswith(("Expected", "Check")):
                        removed.append((cid, c[i], given))
            out.append("| " + " | ".join(c[i] for i in keep if i < len(c)) + " |")
            continue
        table = False
        out.append(ln)
    if skip:
        raise SystemExit("unclosed blind:strip block")
    return "\n".join(out) + "\n", removed


def build(root, pk):
    pk.mkdir(parents=True, exist_ok=True)
    for name, rel in SPECS.items():
        blind, _ = strip((root / rel).read_text(encoding="utf-8"))
        (pk / f"{name}.blind.md").write_text(blind, encoding="utf-8", newline="\n")
    (pk / Path(RULINGS).name).write_bytes((root / RULINGS).read_bytes())


def forms(v):
    out = set()
    for tok in re.findall(r"(?<![\w-])-?[\d,]*\d(?:\.\d+)?(?:e-?\d+)?|E_[A-Z]+|[A-Z][A-Z_]{3,}", v):
        t = tok.replace(",", "")
        out |= {tok, t}
        try:
            x = float(t)
            out |= {repr(x), f"{x:.15g}", f"{x:.10g}"}
            if "." in t and len(t.split(".")[1]) > 6:
                out.add(t[: t.index(".") + 7])  # a six-decimal prefix also leaks
        except ValueError:
            pass
    return {f for f in out if f not in GENERIC and len(f.lstrip("-")) > 1}


def leaks(root, pk):
    lines = [(p.name, i + 1, ln) for p in sorted(pk.glob("*.md"))
             for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines())]
    hard = sum("blind:strip" in ln for _, _, ln in lines)
    for _, _, ln in lines:
        if "blind:strip" in ln:
            print(f"MARKER\t-\t-\tYES\t{ln.strip()[:160]}")
    if any("idr_k-0005" in ln for _, _, ln in lines):
        hard += 1
        print("idr_k-0005\toracle-pending case present in packet\t-\tYES\t-")
    print("case\tvalue\tfile:line\tsame_line_case_id\ttext")
    for rel in SPECS.values():
        _, removed = strip((root / rel).read_text(encoding="utf-8"))
        for cid, val, given in removed:
            if cid == "prose" or not CASE.fullmatch(cid):
                continue
            # A value equal to one of the case's own inputs (trig_k-0004/0005: threshold = k when sigma = 1) is
            # given by the inputs, not leaked.
            for f in sorted(forms(val) - forms(given)):
                pat = re.compile(r"(?<![\w.])" + re.escape(f) + r"(?![\w])")
                for name, n, ln in lines:
                    if pat.search(ln):
                        same = cid in ln
                        hard += same
                        print(f"{cid}\t{f}\t{name}:{n}\t{'YES' if same else 'no'}\t{ln.strip()[:160]}")
    print(f"# hard leaks: {hard}")
    return 1 if hard else 0


if __name__ == "__main__":
    mode, root, pk = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if mode == "build":
        build(root, pk)
    else:
        sys.exit(leaks(root, pk))
