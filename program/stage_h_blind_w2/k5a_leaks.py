"""Leak check for the K-5a blind packet (hidden side; never put this script or its output in the packet).

Model: k2_leaks.py (branch k-w2-spec), itself modelled on paper2_leaks.py. For each of the five cases every
expected output (numbers and the label string) is searched for in every packet file: the plain decimal form, the
comma-grouped form, the forms rounded to 2, 4 and 6 decimals when that keeps at least three significant digits
(the wave-1 packet carried the bounds to 6 decimals, so 6 is searched too), and the sign-flipped form of each
number. Also searched: the spec's check columns (exact revaluation V(y + h), the estimate of V(y + h), V(y),
the error est - exact and the error / bound ratio) recomputed here at 50 digits, because they are intermediates
from which an answer follows. Values equal to a leaf of the case's own inputs are skipped, and so are 0 and 1.

A hit is classified:
  INPUT    in inputs/*.json (allowed; listed)
  LOWINFO  in prose, a value of at most two significant digits (allowed; listed)
  ALLOWED  in prose, listed in ALLOW below with the reason
  HARD     anything else: a leak. Also HARD: any case id outside inputs/ and output_template.json.
    python -I program/stage_h_blind_w2/k5a_leaks.py <checkout> <packet dir> > <outside dir>/k5a_LEAKS.tsv
Exit 1 on any HARD hit.
"""

import json
import re
import sys
from pathlib import Path

import mpmath as mp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from k5a_cases import CASES
from k5a_recheck import exact

mp.mp.dps = 50
GENERIC = {"0", "1", "-0", "-1"}
LABEL = "latency-aware analytics on simulated data"
# (value as searched, packet file, reason). Each entry was read in context when this list was fixed.
ALLOW = [
    (
        LABEL,
        "rulings/stage-k-rulings-k5a.blind.md",
        "KR-10 states the label; the label field is rules-stated and gives no credit (R_FIELDS in k5a_compare.py)",
    ),
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


def variants(v):
    if isinstance(v, str):
        return {v}
    out = set()
    for x in (v, -v):
        s = num_str(x)
        sign = "-" if x < 0 else ""
        a = abs(x)
        out.add(s)
        if float(a).is_integer() and a >= 1000:
            out.add(f"{sign}{int(a):,}")
        if not float(x).is_integer():
            dec = s.split(".")[1] if "." in s else ""
            for nd in (2, 3, 4, 6):
                if len(dec) > nd and sig_digits(f"{a:.{nd}f}") >= 3:
                    out.add(sign + f"{a:.{nd}f}".rstrip("0").rstrip("."))
                    if a >= 1000:
                        out.add(sign + f"{a:,.{nd}f}".rstrip("0").rstrip("."))
            if a >= 1000:
                ip, dp = f"{a!r}".split(".")
                out.add(f"{sign}{int(ip):,}.{dp}")
    return {x for x in out if x not in GENERIC}


def searched(exp):
    """[(case_id, name, value)]: expected fields and the spec's check-column intermediates."""
    out = []
    for cid, _, _, inp in CASES:
        for f in exp[cid]["fields"]:
            out.append((cid, f["path"], f["value"]))
        est, rev, bnd = exact(inp)
        h = mp.mpf(inp["shift"])
        v0 = sum(
            mp.mpf(p["notional"]) * mp.exp(-mp.mpf(p["yield"]) * mp.mpf(p["maturity"]))
            for p in inp["positions"]
        )
        out += [
            (cid, "check: V(y)", float(v0)),
            (cid, "check: exact V(y+h)", float(v0 + rev)),
            (cid, "check: estimate of V(y+h)", float(v0 + est)),
            (cid, "check: exact P&L", float(rev)),
            (cid, "check: est - exact", float(est - rev)),
            (cid, "check: error / bound", float(abs(est - rev) / bnd)),
            (cid, "check: h^3", float(abs(h) ** 3)),
        ]
    return out


def main():
    root, pk = Path(sys.argv[1]), Path(sys.argv[2])
    exp = json.loads(
        (root / "program/stage_h_blind_w2/k5a_expected.json").read_text(
            encoding="utf-8"
        )
    )["cases"]
    files = sorted(
        p for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256"
    )
    lines = [
        (p.relative_to(pk).as_posix(), i + 1, ln)
        for p in files
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines())
    ]
    allow = {(v, f) for v, f, _ in ALLOW}
    used = set()
    hard = 0
    counts = {"INPUT": 0, "LOWINFO": 0, "ALLOWED": 0, "HARD": 0}
    own_of = {
        cid: {num_str(x) if not isinstance(x, str) else x for x in leaves(inp)}
        for cid, _, _, inp in CASES
    }
    print("case\tfield\tvalue\tclass\tfile:line\ttext")
    for cid, path, v in searched(exp):
        if (num_str(v) if not isinstance(v, str) else v) in own_of[cid]:
            continue
        for var in sorted(variants(v)):
            pat = re.compile(r"(?<![\w.,\-])" + re.escape(var) + r"(?![\w%]|[.,]\d)")
            for name, n, ln in lines:
                if not pat.search(ln):
                    continue
                if name.startswith("inputs/"):
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
                print(f"{cid}\t{path}\t{var}\t{cls}\t{name}:{n}\t{ln.strip()[:150]}")
    idpat = re.compile(r"\b(?:idr|e2|e1)_k-\d{4}\b")
    for name, n, ln in lines:
        if name.startswith("inputs/") or name == "output_template.json":
            continue
        if idpat.search(ln):
            hard += 1
            counts["HARD"] += 1
            print(
                f"(case id)\t-\t{idpat.search(ln).group(0)}\tHARD\t{name}:{n}\t{ln.strip()[:150]}"
            )
    for v, fname, why in ALLOW:
        if (v, fname) not in used:
            print(f"# note: ALLOW entry unused: {v} in {fname} ({why})")
    print(f"# counts: {counts}")
    print(f"# hard leaks: {hard}")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
