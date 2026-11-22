"""Leak check of the aadadj_k blind packet (DR-H2; model k8_leaks.py). Hidden side: reads the goldens.

    python -I program/stage_k_blind_aadadj/aadadj_leaks.py <repo> C:/Work/Claude/qf-blind/k_aadadj > C:/Work/Claude/qf-blind/k_aadadj_LEAKS.tsv

Searches every packet file except MANIFEST.sha256:
1. Strings: every nonzero expected number as printed (repr), with the opposite sign, comma-grouped, and rounded to
   0, 1, 2, 3 and 4 decimals when that keeps at least three significant digits. Hits in inputs.json that equal an
   input value are INPUT (allowed).
2. Proximity: every number with at least three significant digits in a prose file (README, spec, rulings) within
   1% of an expected number is HARD, within 5% NEAR.
3. Case ids in prose files; repo paths and repo file names (program/, datasets/, oracle/, tests/, specifications/,
   qf-wt, .py, golden file names) anywhere.
Exit 1 on any HARD hit.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aadadj_compare import B, SUITE, expected  # noqa: E402

NUM = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.])-?\d+(?:\.\d+)?(?:e[-+]?\d+)?(?![\w])", re.I)
PATHS = re.compile(r"program/|datasets/|oracle/|tests/|specifications/|qf-wt|institutional-quant|gen_stage|aadadj_k\.json|\w\.py\b(?!\))")
ALLOWED = {"2008": "publication year of the Griewank and Walther citation; not a value"}
ALLOWED_PATHS = {"README.md": {"derive.py"}}


def sig(tok):
    s = tok.lower().split("e")[0].replace(",", "").replace("-", "").replace(".", "").lstrip("0")
    return len(s) if "." in tok else len(s.rstrip("0"))


def variants(x):
    out = {repr(x), repr(-x)}
    for d in (0, 1, 2, 3, 4):
        txt = f"{round(abs(x), d):.{d}f}"
        if len(txt.replace(".", "").lstrip("0")) >= 3:
            ip, _, fp = txt.partition(".")
            out |= {txt, f"{int(ip):,}" + (f".{fp}" if fp else "")}
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


def main():
    root, pk = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    exp = [(cid, x) for cid, (e, _) in expected(root).items() for x in nums(e) if x != 0.0]
    pool = sorted({x for _, x in exp})
    input_vals = set(nums(json.loads((pk / "inputs.json").read_text(encoding="utf-8"))))
    files = sorted(p for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    hard = near = inp = 0
    print("kind\tfile\ttoken\tmatches\tnote")
    for p in files:
        rel = p.relative_to(pk).as_posix()
        text = p.read_text(encoding="utf-8")
        prose = rel.endswith(".md")
        for cid, x in exp:
            for v in variants(x):
                if re.search(r"(?<![\w.])" + re.escape(v) + r"(?![\w])", text):
                    if rel == "inputs.json" and abs(float(v.replace(",", ""))) in {abs(u) for u in input_vals}:
                        inp += 1
                        print(f"INPUT\t{rel}\t{v}\t{cid}\tequals an input value")
                    else:
                        hard += 1
                        print(f"HARD\t{rel}\t{v}\t{cid} {x!r}\tstring variant")
        for m in PATHS.finditer(text):
            if m.group(0) not in ALLOWED_PATHS.get(rel, set()) and "derive.py" not in text[m.start() - 6:m.end() + 3]:
                hard += 1
                print(f"HARD\t{rel}\t{m.group(0)}\t-\trepo path or file name")
        if prose:
            for cid in B:
                if cid in text or cid[-5:] in text:
                    hard += 1
                    print(f"HARD\t{rel}\t{cid}\t-\tcase id in a prose file")
            for m in NUM.finditer(text):
                tok = m.group(0)
                try:
                    v = abs(float(tok.replace(",", "")))
                except ValueError:
                    continue
                if v == 0 or sig(tok) < 3:
                    continue
                if tok in ALLOWED:
                    print(f"ALLOWED	{rel}	{tok}	-	{ALLOWED[tok]}")
                    continue
                best = min(pool, key=lambda y: abs(abs(y) - v) / abs(y))
                gap = abs(abs(best) - v) / abs(best)
                if gap <= 0.01:
                    hard += 1
                    print(f"HARD\t{rel}\t{tok}\texpected {best!r}\twithin {gap:.2%}")
                elif gap <= 0.05:
                    near += 1
                    print(f"NEAR\t{rel}\t{tok}\texpected {best!r}\twithin {gap:.2%}")
    print(f"# files {len(files)}; expected nonzero numbers {len(exp)}; HARD {hard}; NEAR {near}; INPUT {inp}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
