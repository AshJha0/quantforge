"""Leak check of the K-8 blind packet (DR-H2; model k5a_leaks.py). Hidden side: reads the expected file.

    python -I program/stage_h_blind_w2/k8_leaks.py <checkout> C:/Work/Claude/qf-blind/k8_packet > C:/Work/Claude/qf-blind/k8_LEAKS.tsv

Two searches over every packet file:
1. Strings: every nonzero expected number, as printed (repr), with the opposite sign, comma-grouped, and rounded to
   0, 1, 2 and 4 decimals when that keeps at least three significant digits. Also every case id in the prose files.
2. Proximity: every number written in a prose file (README, specs, rulings, output template) with at least three
   significant digits is parsed; if it lies within 1% of the magnitude of any expected number, or of any hint
   number (QuantLib reference values of acceptance 1, the stage G `aadladder_g` and `bermudan_g` goldens on the same
   curve, which sit close to the K-8 values), it is a hard leak. Within 5% it is listed as NEAR for a human look.
Hits inside inputs/K-8.inputs.json that equal an input value are INPUT (allowed). Case ids are expected in
output_template.json (the skeleton is keyed by them) and are searched in the other prose files only. Tokens in
ALLOWED are listed with their reason instead of counted. Exit 1 on any hard leak.
"""
import json
import re
import sys
from pathlib import Path

NUM = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.])-?\d+(?:\.\d+)?(?:e[-+]?\d+)?(?![\w])", re.I)


ALLOWED = {
    "10.000000000000009": "G-18 step 3, the binary64 example `100 x (1.1 - 1.0)` (R5 L9); a rule, not a value of any case",
}


def sig_digits(tok):
    s = tok.lower().split("e")[0].replace(",", "").replace("-", "").replace(".", "").lstrip("0")
    return len(s.rstrip("0")) if "." not in tok else len(s)


def variants(x):
    out = {repr(x), repr(-x)}
    for d in (0, 1, 2, 4):
        r = round(abs(x), d)
        txt = f"{r:.{d}f}"
        if len(txt.replace(".", "").lstrip("0")) >= 3:
            out.add(txt)
            ip, _, fp = txt.partition(".")
            grouped = f"{int(ip):,}" + (f".{fp}" if fp else "")
            out.add(grouped)
    return {v for v in out if len(v.replace("-", "").replace(".", "").replace(",", "").lstrip("0")) >= 3}


def nums(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from nums(v)
    elif isinstance(o, list):
        for v in o:
            yield from nums(v)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        yield float(o)


def hints(root):
    out = []
    ref = json.loads((root / "oracle/K8_REFERENCE_QL.json").read_text(encoding="utf-8"))
    for c in ref["cases"].values():
        for g in c.values():
            out.append(g["price"])
            out += [row[3] for row in g["d"]]  # bump 1e-4
    for s in ("aadladder_g", "bermudan_g"):
        g = json.loads((root / f"datasets/golden/stage_g/{s}.json").read_text(encoding="utf-8"))
        for c in (g["cases"] if isinstance(g, dict) else g):
            out += list(nums(c.get("expected", {}).get("outputs", {})))
    return [h for h in out if abs(h) >= 1.0]


def main():
    root, pk = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    exp = json.loads((root / "program/stage_h_blind_w2/k8_expected.json").read_text(encoding="utf-8"))
    expected = [(cid, x) for cid, e in exp["cases"].items() for x in nums(e["outputs"]) if x != 0.0]
    hint = hints(root)
    inputs = json.loads((pk / "inputs/K-8.inputs.json").read_text(encoding="utf-8"))
    input_vals = set(nums(inputs))
    files = sorted(p for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    hard = near = allowed = 0
    print("kind\tfile\ttoken\tmatches\tnote")
    for p in files:
        rel = p.relative_to(pk).as_posix()
        text = p.read_text(encoding="utf-8")
        prose = rel != "inputs/K-8.inputs.json"
        for cid, x in expected:
            for v in variants(x):
                if re.search(r"(?<![\w.])" + re.escape(v) + r"(?![\w])", text):
                    if not prose and float(v.replace(",", "")) in input_vals:
                        allowed += 1
                        print(f"INPUT\t{rel}\t{v}\t{cid}\tequals an input value")
                    else:
                        hard += 1
                        print(f"HARD\t{rel}\t{v}\t{cid} {x!r}\tstring variant")
        if prose:
            for cid in exp["cases"]:
                if cid in text and rel != "output_template.json":
                    hard += 1
                    print(f"HARD\t{rel}\t{cid}\t-\tcase id in a prose file")
            for m in NUM.finditer(text):
                tok = m.group(0)
                try:
                    v = abs(float(tok.replace(",", "")))
                except ValueError:
                    continue
                if v < 1.0 or sig_digits(tok) < 3:
                    continue
                if tok in ALLOWED:
                    print(f"ALLOWED	{rel}	{tok}	-	{ALLOWED[tok]}")
                    continue
                for label, pool in (("expected", [x for _, x in expected]), ("hint", hint)):
                    best = min(pool, key=lambda y: abs(abs(y) - v) / abs(y))
                    gap = abs(abs(best) - v) / abs(best)
                    if gap <= 0.01:
                        hard += 1
                        print(f"HARD\t{rel}\t{tok}\t{label} {best!r}\twithin {gap:.2%}")
                    elif gap <= 0.05:
                        near += 1
                        print(f"NEAR\t{rel}\t{tok}\t{label} {best!r}\twithin {gap:.2%}")
    print(f"# files {len(files)}; expected numbers {len(expected)}; hint numbers {len(hint)}; "
          f"hard {hard}; near {near}; input coincidences {allowed}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
