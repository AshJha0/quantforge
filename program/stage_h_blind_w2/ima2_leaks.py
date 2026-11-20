"""Leak check for the K-8f second blind packet (hidden side; never put this script or its output in the packet).

Model: btk_leaks.py. For each of the 8 cases, every expected output in ima2_expected.json is searched for in every
packet file: numbers as printed (repr), rounded to 2, 4 and 6 decimals when that keeps at least three significant
digits, and the KS statistic and p-value also as percents (full, 2 and 4 decimals). List outputs (es_by_horizon) are
searched element by element. The zone names (an enumeration the schema must state) carry no case information and are
not searched. Values equal to an input leaf of the case itself are skipped (an input is not a leak), and so are 0
and 1. The normal ES factor is also searched as a product with sqrt(12) (es_k-0002) and as z = 1.95996 (the
quantile, rounded to 4 and 6 decimals), which would give the answer in one step.

A hit is classified:
  INPUT    in inputs/: some case's input (allowed; listed)
  LOWINFO  in prose or the template, a value of at most two significant digits (0.2, 0.12, 30 ...): a constant,
           count, paragraph or page number in rule prose; allowed, every hit listed
  ALLOWED  in prose, three or more significant digits, listed in ALLOW with the reason
  HARD     anything else. Also HARD: a case id or suite name (pla_k, es_k, ima_k, with or without a number, and the
           error-case form pla_ke) outside inputs/ and output_template.json.
    python -I program/stage_h_blind_w2/ima2_leaks.py <checkout> <packet dir> > <outside dir>/ima2_LEAKS.tsv
Exit 1 on any HARD hit.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ima2_make_packet import CASES  # noqa: E402

GENERIC = {"0", "1", "-0", "1.0", "0.0"}
ENUM = {"GREEN", "AMBER", "RED"}
ALLOW = []  # (value as searched, packet file, reason); none needed when this list was fixed
EXTRA = [("es_k-0001", "z (quantile)", ["1.9600", "1.959964", "1.95996"])]


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
    return len(re.sub(r"[^0-9]", "", s.split("e")[0]).lstrip("0").rstrip("0"))


def variants(v, path):
    s = num_str(v)
    out = {s}
    if not float(v).is_integer():
        dec = s.split(".")[1] if "." in s and "e" not in s else ""
        for nd in (2, 4, 6):
            r = f"{v:.{nd}f}"
            if len(dec) > nd and sig_digits(r) >= 3:
                out.add(r)
                out.add(r.rstrip("0").rstrip("."))
        if path in ("ks", "ks_pvalue_asymptotic"):
            p = v * 100
            out.add(num_str(round(p, 10)) + "%")
            for nd in (2, 4):
                r = f"{p:.{nd}f}"
                if sig_digits(r) >= 1:
                    out.add(r + "%")
                    out.add(r.rstrip("0").rstrip(".") + "%")
    return {x for x in out if x not in GENERIC and x not in ("0%", "0.00%", "0.0000%")}


def main():
    root, pk = Path(sys.argv[1]), Path(sys.argv[2])
    exp = json.loads((root / "program/stage_h_blind_w2/ima2_expected.json").read_text(encoding="utf-8"))["cases"]
    files = sorted(p for p in pk.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    lines = [(p.relative_to(pk).as_posix(), i + 1, ln) for p in files for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines())]
    hard = 0
    counts = {"INPUT": 0, "LOWINFO": 0, "ALLOWED": 0, "HARD": 0}
    print("case\tfield\tvalue\tclass\tfile:line\ttext")

    def search(cid, path, value_for_class, vars_):
        nonlocal hard
        for var in sorted(vars_):
            pat = re.compile(r"(?<![\w.,\-])" + re.escape(var) + (r"(?![\w%]|[.,]\d)" if not var.endswith("%") else ""))
            for name, n, ln in lines:
                if not pat.search(ln):
                    continue
                if name.startswith("inputs/"):
                    cls = "INPUT"
                elif sig_digits(num_str(value_for_class)) <= 2:
                    cls = "LOWINFO"
                elif (var, name) in {(a, b) for a, b, _ in ALLOW}:
                    cls = "ALLOWED"
                else:
                    cls = "HARD"
                    hard += 1
                counts[cls] += 1
                print(f"{cid}\t{path}\t{var}\t{cls}\t{name}:{n}\t{ln.strip()[:150]}")

    for cid, _, inp in CASES:
        own = {num_str(x) for x in leaves(inp)}
        for f in exp[cid]["fields"]:
            v = f["value"]
            if isinstance(v, str) and v in ENUM:
                continue
            for x in (v if isinstance(v, list) else [v]):
                if num_str(x) in own or num_str(x) in GENERIC:
                    continue
                search(cid, f["path"], x, variants(x, f["path"]))
    for cid, path, vs in EXTRA:
        search(cid, path, 1.959963984540054, set(vs))
    idpat = re.compile(r"\b(?:pla|es|ima)_ke?(?:-\d{4})?\b")
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
