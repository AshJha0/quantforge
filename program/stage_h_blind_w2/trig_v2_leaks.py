"""K-4c v2 leak check: searches every packet file for each expected number of trig_v2_expected.json, as printed by
repr, with the opposite sign, and rounded to 3, 4, 6, 8, 10 and 12 significant digits (also in e-notation and as
a percentage). A hit is HARD unless listed in ALLOWED. Prints a TSV; exit 1 on any HARD hit.

    python -I program/stage_h_blind_w2/trig_v2_leaks.py . C:/Work/Claude/qf-blind/trig_k_v2_packet
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Inputs printed in the packet are not leaks: values that equal an input (threshold = k when sigma = d = 1:
# 2.5, and 1000 for k = 1e3; sigma 1.0).
ALLOWED_VALUES = {1.0, 2.5, 1000.0}


def forms(v):
    out = {repr(v), repr(-v)}
    for sig in (3, 4, 6, 8, 10, 12):
        s = f"{v:.{sig}g}"
        out.add(s)
        out.add(f"{v:.{sig - 1}e}")
        out.add(f"{100 * v:.{sig}g}%")
    return {s for s in out if len(re.sub(r"[^0-9]", "", s).lstrip("0")) >= 3}


def main():
    root, pk = Path(sys.argv[1]), Path(sys.argv[2])
    exp = json.loads((HERE / "trig_v2_expected.json").read_text(encoding="utf-8"))
    texts = {p.relative_to(pk).as_posix(): p.read_text(encoding="utf-8") for p in pk.rglob("*") if p.is_file()
             and p.name != "MANIFEST.sha256"}
    hard = 0
    print("kind\tcase\tfield\tform\tfile")
    for cid, e in exp["cases"].items():
        for f, v in e["outputs"].items():
            if isinstance(v, bool):
                continue
            for s in forms(v):
                pat = r"(?<![0-9.])" + re.escape(s) + r"(?![0-9])"
                for fn, t in texts.items():
                    if re.search(pat, t):
                        kind = "ALLOWED" if v in ALLOWED_VALUES else "HARD"
                        hard += kind == "HARD"
                        print(f"{kind}\t{cid}\t{f}\t{s}\t{fn}")
    for fn, t in texts.items():
        if fn.endswith(".md") and re.search(r"trig_k-\d{4}", t):
            hard += 1
            print(f"HARD\t-\tcase id\t-\t{fn}")
    print(f"# hard hits: {hard}", file=sys.stderr)
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
