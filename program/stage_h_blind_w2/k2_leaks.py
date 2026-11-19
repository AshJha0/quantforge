"""Leak check for the stage K wave 2 blind packet (hidden side; never put this script or its output in the packet).

Model: paper2_leaks.py. For each of the 58 cases, every expected output value in k2_expected.json (numbers and date
strings; booleans and null carry no digits and are not searched) is searched for in every packet file, as printed:
the plain decimal form (signed as printed; a negative value is searched with its sign), the comma-grouped form, the
forms rounded to 2 and 4 decimals when the value has more digits, and the percent form for ratios, shares and hbr.
Values equal to a leaf of the case's own inputs are skipped (an input is not a leak), and so are 0 and 1.

A hit is classified:
  PARAM    in tables/*.json: a published parameter (allowed; listed)
  INPUT    in inputs/*.json: some case's input (allowed; listed)
  LOWINFO  in prose (.md or the template), for a value of at most two significant digits (3, 15, 20, 0.5, 250,
           12000 ...). Such a token occurs in rule prose as a constant, a count, a paragraph or page number; it cannot
           tell the deriver which case it belongs to or that it is an answer. Allowed, every hit listed.
  ALLOWED  in prose, a value of three or more significant digits, listed in ALLOW below with the reason
  HARD     anything else: a leak. Also HARD: any case id outside inputs/ and output_template.json.
    python -I program/stage_h_blind_w2/k2_leaks.py <checkout> <packet dir> > <outside dir>/k2_LEAKS.tsv
Exit 1 on any HARD hit.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from k2_cases import CASES  # noqa: E402

GENERIC = {"0", "1", "-0"}

# (value as searched, packet file, reason). Each entry was read in context when this list was fixed.
ALLOW = [
]


def leaves(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from leaves(v)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v)
    elif o is not None and not isinstance(o, bool):
        yield o


def num_str(x):
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return repr(x) if isinstance(x, float) else str(x)


def sig_digits(s):
    d = re.sub(r"[^0-9]", "", s).lstrip("0").rstrip("0")
    return len(d)


def variants(v, path):
    if isinstance(v, str):
        return {v}
    s = num_str(v)
    sign = "-" if v < 0 else ""
    a = abs(v)
    out = {s}
    if float(a).is_integer() and a >= 1000:
        out.add(f"{sign}{int(a):,}")
    if not float(v).is_integer():
        dec = s.split(".")[1]
        for nd in (2, 4):
            if len(dec) > nd and sig_digits(f"{a:.{nd}f}") >= 3:  # a 1- or 2-digit rounding is not "the printed digits"
                out.add(sign + f"{a:.{nd}f}".rstrip("0").rstrip("."))
                if a >= 1000:
                    out.add(sign + f"{a:,.{nd}f}".rstrip("0").rstrip("."))
        if a >= 1000:
            ip, dp = f"{a!r}".split(".")
            out.add(f"{sign}{int(ip):,}.{dp}")
    if 0 < a < 1 and re.search(r"ratio|share|hbr", path):
        p = a * 100
        out.add(num_str(round(p, 10)) + "%")
        out.add(f"{p:.2f}".rstrip("0").rstrip(".") + "%")
    return {x for x in out if x not in GENERIC}


def main():
    root, pk = Path(sys.argv[1]), Path(sys.argv[2])
    exp = json.loads((root / "program/stage_h_blind_w2/k2_expected.json").read_text(encoding="utf-8"))["cases"]
    files = sorted(p for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    lines = [(p.relative_to(pk).as_posix(), i + 1, ln) for p in files for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines())]
    allow = {(v, f) for v, f, _ in ALLOW}
    used = set()
    hard = 0
    counts = {"PARAM": 0, "INPUT": 0, "LOWINFO": 0, "ALLOWED": 0, "HARD": 0}
    print("case\tfield\tvalue\tclass\tfile:line\ttext")
    for cid, _, _, inp in CASES:
        own = {num_str(x) if not isinstance(x, str) else x for x in leaves(inp)}
        for f in exp[cid]["fields"]:
            v = f["value"]
            if isinstance(v, bool) or v is None:
                continue
            if (num_str(v) if not isinstance(v, str) else v) in own:
                continue
            for var in sorted(variants(v, f["path"])):
                # not inside a longer number, an identifier (KR-55, MAR22.45) or a range (16-17)
                pat = re.compile(r"(?<![\w.,\-])" + re.escape(var) + r"(?![\w%]|[.,]\d)" if not var.endswith("%")
                                 else r"(?<![\w.,\-])" + re.escape(var))
                for name, n, ln in lines:
                    if not pat.search(ln):
                        continue
                    if name.startswith("tables/"):
                        cls = "PARAM"
                    elif name.startswith("inputs/"):
                        cls = "INPUT"
                    elif not isinstance(v, str) and sig_digits(num_str(v)) <= 2:
                        cls = "LOWINFO"
                    elif (var, name) in allow:
                        cls = "ALLOWED"
                        used.add((var, name))
                    else:
                        cls = "HARD"
                        hard += 1
                    counts[cls] += 1
                    print(f"{cid}\t{f['path']}\t{var}\t{cls}\t{name}:{n}\t{ln.strip()[:150]}")
    idpat = re.compile(r"\b(?:drc|ctp|sec|rrao|es|est|imcc|ses|cap|rfet|pla|lh|cva|df|sacva|lev|lex)_ke?-\d{4}\b")
    for name, n, ln in lines:
        if name.startswith("inputs/") or name == "output_template.json":
            continue
        if idpat.search(ln):
            hard += 1
            counts["HARD"] += 1
            print(f"(case id)\t-\t{idpat.search(ln).group(0)}\tHARD\t{name}:{n}\t{ln.strip()[:150]}")
    for v, fname, why in ALLOW:
        if (v, fname) not in used:
            print(f"# note: ALLOW entry unused: {v} in {fname} ({why})")
    print(f"# counts: {counts}")
    print(f"# hard leaks: {hard}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
