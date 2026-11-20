"""Leak check for the PUB blind packet (hidden side; never put this script or its output in the packet).

Model: btk_leaks.py, plus a list of every figure the regulator text prints for these 28 cases (PRINTED below: the
CRE99 Example 1 to 5 figures the generator asserts, oracle/python/gen_stage_k_w1b.py `published_intermediates`, the
five EADs, the worked-example intermediates of sa-ccr.md, and the eleven MAR99 Table 2 percentages).

Two searches over every packet file:
 1. every expected leaf of every case in pub_expected.json: numbers as printed (repr), rounded to 0, 1, 2, 3, 4 and 6
    decimals when that keeps at least three significant digits, integers above 999 also with thousands commas,
    probabilities also as percents (full, 2 and 4 decimals). Booleans, null, strings (zones, ids, keys) are not
    searched; values equal to an input leaf of the case itself are skipped, and so are 0 and 1.
 2. every PRINTED figure, as written in the source and without thousands commas.
A hit is classified:
  PARAM    in tables/: a published constant (allowed; listed)
  INPUT    in inputs/: some case's input (allowed; listed)
  LOWINFO  in prose or the template, a value of at most two significant digits (a PRINTED figure only if it has no
           comma or decimal point): a constant, count, paragraph or page number in rule prose; allowed, every hit listed
  ALLOWED  three or more significant digits, listed in ALLOW with the reason
  HARD     anything else. Also HARD: a case id or suite name (saccr_k, btk_k, tlk_k) outside inputs/ and
           output_template.json, and the words "Example 1" to "Example 5" or "CRE99.2"-"CRE99.97" paragraph numbers
           of the worked examples in any file.

    python -I program/stage_h_blind_w2/pub_leaks.py <checkout> <packet dir> > <outside dir>/pub_LEAKS.tsv
    python -I program/stage_h_blind_w2/pub_leaks.py <checkout> --negative-control > <outside dir>/pub_LEAKS_negctl.tsv
The negative control builds a packet in a temporary folder from the UNSTRIPPED spec, rulings and table files (same
layout, same inputs) and must report HARD hits on the printed figures; it exits 0 only if it does.
Exit 1 on any HARD hit (normal mode).
"""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

GENERIC = {"0", "1", "-0", "1.0", "0.0", "-1", "-1.0"}
# Figures printed in the regulator text for these cases (read 2026-11-19, CRE99 pp.524-540, MAR99 p.758) and the
# worked-example intermediates of sa-ccr.md. As printed; each is also searched without commas.
PRINTED = [
    # EADs, CRE99.40, .58, .76, .79, .97
    "569", "381", "5,406", "936", "1,879", "569.47", "406.76",
    # Example 1
    "78,694", "36,254", "37,428", "7.87", "3.63", "7.49", "7.8694", "3.6254", "7.4856", "-0.2694", "-36,254", "-10,083",
    "10,083", "59,270", "296.35", "50.415", "346.76", "347",
    # Example 2
    "27,858", "51,836", "44,240", "2.79", "5.18", "4.42", "106", "-280", "168", "47.5", "2,253", "77,344", "282", "0.965",
    "52.9", "134.5", "11,207", "8,405", "78,353", "58,765", "28,261", "10,174",
    # Example 3
    "8,660", "-11,340", "-2,041", "2,041", "1,800", "3,841",
    # Example 4
    "629",
    # Example 5
    "27,934", "-12,869", "-3,579", "3,579", "3,550", "-7,100", "7,099.30", "21,039", "105", "123", "639", "1,278", "1,401",
    "0.958", "-120",
    # MAR99 Table 2 (percent)
    "8.11", "28.58", "54.32", "75.81", "89.22", "95.88", "98.63", "99.6", "99.60", "99.89", "99.97", "99.99",
    # frtb-ima-backtest.md worked example (6-decimal cumulative probabilities)
    "0.892188", "0.958817", "0.999750", "0.999946",
]
ALLOW = [
    # (value as searched, packet file, reason). Each read in context when this list was fixed.
    ("1.83", "specs/frtb-ima-backtest.blind.md", "MAR32.9 multiplier band (rule) in Sources and the Formal statement"),
    ("1.88", "specs/frtb-ima-backtest.blind.md", "MAR32.9 multiplier band (rule)"),
    ("1.92", "specs/frtb-ima-backtest.blind.md", "MAR32.9 multiplier band (rule)"),
    ("1.76", "specs/frtb-ima-backtest.blind.md", "MAR32.9 multiplier band (rule)"),
    *[(v, f, "the MAR99.17 red-zone threshold (cdf >= 0.9999, '99.99%' in the quoted rule and the plain idea), a rule "
       "the deriver must apply; it equals the 4-decimal rounding of the 10-exception probability only by coincidence, "
       "and gives nothing at the 1e-10 tolerance")
      for v, f in (("0.9999", "specs/frtb-ima-backtest.blind.md"), ("0.9999", "specs/traffic-light.blind.md"),
                   ("99.99%", "specs/frtb-ima-backtest.blind.md"), ("99.99", "specs/frtb-ima-backtest.blind.md"))],
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
    s = num_str(v)
    out = {s}
    if abs(v) >= 1000:
        out.add(f"{round(v):,}")
    if not float(v).is_integer():
        dec = s.split(".")[1] if "." in s else ""
        for nd in (0, 1, 2, 3, 4, 6):
            r = f"{v:.{nd}f}"
            if len(dec) > nd and sig_digits(r) >= 3:
                out.add(r)
                out.add(r.rstrip("0").rstrip(".") if "." in r else r)
                if abs(v) >= 1000 and nd <= 2:
                    out.add(f"{v:,.{nd}f}")
        if "probability" in path:
            p = v * 100
            out.add(num_str(round(p, 10)) + "%")
            for nd in (2, 4):
                r = f"{p:.{nd}f}"
                out |= {r + "%", r.rstrip("0").rstrip(".") + "%", r}
    return {x for x in out if x not in GENERIC}


def pattern(var):
    return re.compile(r"(?<![\w.,\-])" + re.escape(var) + (r"(?![\w%]|[.,]\d)" if not var.endswith("%") else ""))


def scan(root, pk):
    exp = json.loads((HERE / "pub_expected.json").read_text(encoding="utf-8"))["cases"]
    cases = {c["case_id"]: c for c in json.loads((HERE / "pub_cases.json").read_text(encoding="utf-8"))["cases"]}
    files = sorted(p for p in Path(pk).rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    lines = [(p.relative_to(pk).as_posix(), i + 1, ln) for p in files for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines())]
    allow = {(a, b) for a, b, _ in ALLOW}
    counts = {"PARAM": 0, "INPUT": 0, "LOWINFO": 0, "ALLOWED": 0, "HARD": 0}
    rows = []

    def classify(name, var, low):
        if name.startswith("tables/"):
            return "PARAM"
        if name.startswith("inputs/"):
            return "INPUT"
        if low:
            return "LOWINFO"
        if (var, name) in allow:
            return "ALLOWED"
        return "HARD"

    def hit(tag, field, var, low):
        pat = pattern(var)
        for name, n, ln in lines:
            if pat.search(ln):
                cls = classify(name, var, low)
                counts[cls] += 1
                rows.append(f"{tag}\t{field}\t{var}\t{cls}\t{name}:{n}\t{ln.strip()[:150]}")

    for cid, e in exp.items():
        own = {num_str(x) for x in leaves(cases[cid]["inputs"])}

        def visit(x, path):
            if isinstance(x, dict):
                for k, v in x.items():
                    visit(v, f"{path}/{k}" if path else k)
            elif isinstance(x, list):
                for i, v in enumerate(x):
                    visit(v, f"{path}[{i}]")
            elif isinstance(x, (int, float)) and not isinstance(x, bool):
                if num_str(x) in own or num_str(x) in GENERIC:
                    return
                for var in sorted(variants(x, path)):
                    hit(cid, path, var, sig_digits(num_str(x)) <= 2)
        visit(e["outputs"], "")
    for fig in PRINTED:
        for var in {fig, fig.replace(",", "")}:
            # a printed figure written with a comma or a decimal point is specific even with two significant digits
            hit("(printed)", "-", var, sig_digits(var) <= 2 and "," not in fig and "." not in fig)
    idpat = re.compile(r"\b(?:saccr|btk|tlk)_k\b|\bExample [1-5]\b|\bCRE99\.(?:[2-9]\d)\b")
    for name, n, ln in lines:
        if name.startswith("inputs/") or name == "output_template.json":
            continue
        for m in idpat.finditer(ln):
            counts["HARD"] += 1
            rows.append(f"(case id, suite or example)\t-\t{m.group(0)}\tHARD\t{name}:{n}\t{ln.strip()[:150]}")
    return counts, sorted(set(rows))


def negative_control(root):
    from pub_make_packet import BTK_SPEC, BTK_TABLE, RULINGS, SACCR_PARAMS, SACCR_SPEC, TL_SPEC
    root = Path(root)
    with tempfile.TemporaryDirectory() as d:
        pk = Path(d)
        layout = {"specs/sa-ccr.blind.md": SACCR_SPEC, "specs/frtb-ima-backtest.blind.md": BTK_SPEC,
                  "specs/traffic-light.blind.md": TL_SPEC, "rulings/stage-k-rulings.blind.md": RULINGS,
                  "tables/sa-ccr-parameters.json": SACCR_PARAMS, "tables/frtb-ima-backtest-tables.blind.json": BTK_TABLE}
        for rel, src in layout.items():
            (pk / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(root / src, pk / rel)
        # the printed table keys sit in tables/, which the normal classes call PARAM: move a copy to prose so the
        # control shows the stripping of those keys matters too
        (pk / "specs/table-copy.md").write_text((root / BTK_TABLE).read_text(encoding="utf-8"), encoding="utf-8")
        counts, rows = scan(root, pk)
    return counts, rows


def main():
    root = sys.argv[1]
    if sys.argv[2] == "--negative-control":
        counts, rows = negative_control(root)
        print("case\tfield\tvalue\tclass\tfile:line\ttext")
        print("\n".join(rows))
        hard = [r for r in rows if "\tHARD\t" in r]
        must = ["569", "8.11%", "8.11", "28.58", "5,406", "1,879", "0.958817", "-7,100", "7,099.30", "569.47", "-0.2694"]
        found = {m: any(f"\t{m}\tHARD\t" in r for r in hard) for m in must}
        print(f"# negative control counts: {counts}")
        print(f"# printed figures caught as HARD: {found}")
        return 0 if all(found.values()) else 1
    counts, rows = scan(root, Path(sys.argv[2]))
    print("case\tfield\tvalue\tclass\tfile:line\ttext")
    print("\n".join(rows))
    print(f"# counts: {counts}")
    print(f"# hard leaks: {counts['HARD']}")
    return 1 if counts["HARD"] else 0


if __name__ == "__main__":
    sys.exit(main())
