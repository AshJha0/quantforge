"""Leak check for the K-8e blind packet (hidden side; never put this script or its output in the packet).

Model: k2_leaks.py. For each of the 12 cases, every expected output in btk_expected.json is searched for in every
packet file: numbers as printed (repr), rounded to 2, 4 and 6 decimals when that keeps at least three significant
digits, and probabilities also as percents (full, 2 and 4 decimals); the day lists as printed. Booleans, null and the
zone names (an enumeration the schema must state: GREEN, AMBER, RED) carry no case information and are not searched.
Values equal to an input leaf of the case itself are skipped (an input is not a leak), and so are 0 and 1.

A hit is classified:
  PARAM    in tables/: a published constant or multiplier (allowed; listed)
  INPUT    in inputs/: some case's input (allowed; listed)
  LOWINFO  in prose or the template, a value of at most two significant digits (5, 10, 15, 0.99 ...): a constant,
           count, paragraph or page number in rule prose; allowed, every hit listed
  ALLOWED  in prose, three or more significant digits, listed in ALLOW with the reason
  HARD     anything else. Also HARD: a case id (btk_k-NNNN, tlk_k-NNNN) or a suite name (btk_k, tlk_k) outside
           inputs/ and output_template.json.
    python -I program/stage_h_blind_w2/btk_leaks.py <checkout> <packet dir> > <outside dir>/btk_LEAKS.tsv
Exit 1 on any HARD hit.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from btk_make_packet import CASES  # noqa: E402

GENERIC = {"0", "1", "-0", "1.0", "0.0"}
ENUM = {"GREEN", "AMBER", "RED"}
# (value as searched, packet file, reason). Each entry was read in context when this list was fixed.
ALLOW = [
    ("1.83", "specs/frtb-ima-backtest.blind.md", "the MAR32.9 Table 1 multiplier band printed in Sources and in the "
     "Formal statement; btk_k-0013 multiplier is a rule field (table lookup) and gives that case no credit"),
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
    return len(re.sub(r"[^0-9]", "", s).lstrip("0").rstrip("0"))


def variants(v, path):
    if isinstance(v, list):
        return {json.dumps(v), json.dumps(v, separators=(",", ":"))}
    s = num_str(v)
    out = {s}
    if not float(v).is_integer():
        dec = s.split(".")[1] if "." in s else ""
        for nd in (2, 4, 6):
            r = f"{v:.{nd}f}"
            if len(dec) > nd and sig_digits(r) >= 3:
                out.add(r)
                out.add(r.rstrip("0").rstrip("."))
        if "probability" in path:
            p = v * 100
            out.add(num_str(round(p, 10)) + "%")
            for nd in (2, 4):
                r = f"{p:.{nd}f}"
                out.add(r + "%")
                out.add(r.rstrip("0").rstrip(".") + "%")
                out.add(r)
    return {x for x in out if x not in GENERIC}


def main():
    root, pk = Path(sys.argv[1]), Path(sys.argv[2])
    exp = json.loads((root / "program/stage_h_blind_w2/btk_expected.json").read_text(encoding="utf-8"))["cases"]
    files = sorted(p for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    lines = [(p.relative_to(pk).as_posix(), i + 1, ln) for p in files for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines())]
    hard = 0
    counts = {"PARAM": 0, "INPUT": 0, "LOWINFO": 0, "ALLOWED": 0, "HARD": 0}
    print("case\tfield\tvalue\tclass\tfile:line\ttext")
    for cid, _, inp in CASES:
        own = {num_str(x) for x in leaves(inp)}
        for f in exp[cid]["fields"]:
            v = f["value"]
            if isinstance(v, bool) or v is None or (isinstance(v, str) and v in ENUM):
                continue
            if not isinstance(v, list) and num_str(v) in own:
                continue
            for var in sorted(variants(v, f["path"])):
                pat = re.compile(r"(?<![\w.,\-])" + re.escape(var) + (r"(?![\w%]|[.,]\d)" if not var.endswith("%") else ""))
                for name, n, ln in lines:
                    if not pat.search(ln):
                        continue
                    if name.startswith("tables/"):
                        cls = "PARAM"
                    elif name.startswith("inputs/"):
                        cls = "INPUT"
                    elif not isinstance(v, list) and sig_digits(num_str(v)) <= 2:
                        cls = "LOWINFO"
                    elif (var, name) in {(a, b) for a, b, _ in ALLOW}:
                        cls = "ALLOWED"
                    else:
                        cls = "HARD"
                        hard += 1
                    counts[cls] += 1
                    print(f"{cid}\t{f['path']}\t{var}\t{cls}\t{name}:{n}\t{ln.strip()[:150]}")
    idpat = re.compile(r"\b(?:btk|tlk)_k\b")
    for name, n, ln in lines:
        if name.startswith("inputs/") or name == "output_template.json":
            continue
        m = idpat.search(ln)
        if m:
            hard += 1
            counts["HARD"] += 1
            print(f"(case id or suite)\t-\t{m.group(0)}\tHARD\t{name}:{n}\t{ln.strip()[:150]}")
    print(f"# counts: {counts}")
    print(f"# hard leaks: {hard}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
