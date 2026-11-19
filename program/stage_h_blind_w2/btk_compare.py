"""Compare a frozen K-8e blind result with the hidden expected values (DR-H2), btk_k-0013 to 0024.

Fixed before any blind result exists (commit recorded in program/STAGE_K_BLIND_BTK.md). Nothing here may change
after the deriver hands back, except a representation fix that compares no value differently, recorded with its
reason in the record.

    python -I program/stage_h_blind_w2/btk_compare.py <checkout> <blind_results.json>   # the real run, once
    python -I program/stage_h_blind_w2/btk_compare.py <checkout> --self-test            # dry run on fabricated data

Field mapping: every output of the golden (btk_expected.json, copied from datasets/golden/stage_k/btk_k.json) is read
from the blind case object under the same name; the names are the packet skeleton's (btk_make_packet.FIELDS), and
the self-test fails if any expected field is missing from the skeleton. Every golden output is compared (the
outside-share rule counts a case only if every compared output was checked blind).

Tolerance, from the spec ("Probabilities are binary64 (tolerance class simple_analytic); counts, zones, flags and
the tabulated multiplier compare exactly") and the golden's per-output classes, with the class definitions of
conformance/tolerances/policy.yaml:
  simple_analytic      |b - e| <= 1e-12 + 1e-10 * max(|b|, |e|)      (the cumulative probabilities)
  date_and_convention  exact: integers by value (5 and 5.0 equal), strings, booleans, null, the multiplier (binary64
                       equality), lists element by element; a boolean never equals a number or the reverse
  null in the blind result where a value is expected: MISSING; a value where null is expected: MISMATCH

Representation rules (fixed now, as k2_compare.py, so a wrapper slip cannot void the run; each use is printed):
  R1 top level {"cases": {id: obj}}, {"cases": [{"case_id": id, ...}]} or {id: obj}; anything else is SHAPE (exit 2).
  R2 a case object holding none of its expected keys but exactly one of "outputs", "result", "results" as an object
     is unwrapped one level (UNWRAPPED).
  R4 a number given as a decimal string is read with float() (STRING-NUMBER); not for exact integer fields' lists.
Counting: a case is MATCH only if every expected field matches. NOT_COUNTED cases are compared and reported but never
counted as blind. RULE_FIELDS are compared but give no credit on their own (a case counts on its other fields).
Exit 0 when every case is MATCH, 1 on any MISMATCH or MISSING, 2 on a SHAPE error.
"""
import copy
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ABS, REL = 1e-12, 1e-10
NOT_COUNTED = {
    "btk_k-0017": "the rules text states its answer: the spec Limits and KR-42 say that for n <= 5 zero exceptions is "
                  "amber, with P(X = 0) = 0.99^n; at n = 1 that gives cumulative_probability 0.99, zone AMBER and "
                  "amber_from 0, and red_from 1 follows from cdf(n) = 1",
}
RULE_FIELDS = {
    ("btk_k-0013", "multiplier"): "table lookup (multiplier_250 at 7)",
    ("btk_k-0013", "zone"): "at n = 250 the formal statement's multiplier bands (0 to 4, 5 to 9, from 10) give the zones",
    ("btk_k-0013", "amber_from"): "as zone",
    ("btk_k-0013", "red_from"): "as zone",
    **{(c, "multiplier"): "null by KR-42 (n not 250)" for c in ("btk_k-0014", "btk_k-0015", "btk_k-0016", "btk_k-0018")},
    **{(c, f): "flag from the counts by KR-44" for c in ("btk_k-0019", "btk_k-0020", "btk_k-0021", "btk_k-0022", "btk_k-0023")
       for f in ("breach_99", "breach_975", "eligible")},
}
PUBLISHED, TOTAL = 12, 24  # btk_k-0001..0012 count already (MAR99 Table 2); 24 value cases; floor 60%
NEEDED = math.ceil(0.6 * TOTAL) - PUBLISHED  # 3
WRAP = ("outputs", "result", "results")


class Shape(Exception):
    pass


def load_expected(root):
    return json.loads((Path(root) / "program/stage_h_blind_w2/btk_expected.json").read_text(encoding="utf-8"))["cases"]


def cases_of(res):
    if isinstance(res, dict) and "cases" in res:
        c = res["cases"]
        if isinstance(c, dict):
            return c
        if isinstance(c, list) and all(isinstance(x, dict) and "case_id" in x for x in c):
            return {x["case_id"]: {k: v for k, v in x.items() if k != "case_id"} for x in c}
        raise Shape("'cases' is neither an object nor a list of objects with case_id")
    if isinstance(res, dict) and res and all(re.fullmatch(r"btk_k-\d{4}", k) for k in res):
        return res
    raise Shape("no case map found at the top level (R1)")


def num(b, notes):
    if isinstance(b, bool):
        return None
    if isinstance(b, str):
        try:
            b = float(b)
            notes.add("STRING-NUMBER")
        except ValueError:
            return None
    if not isinstance(b, (int, float)) or not math.isfinite(b):
        return None
    return b


def same(b, e, cls, notes):
    if e is None or isinstance(e, (bool, str)):
        return type(b) is type(e) and b == e
    if isinstance(e, list):
        return (isinstance(b, list) and len(b) == len(e)
                and all(not isinstance(x, bool) and isinstance(x, (int, float)) and x == y for x, y in zip(b, e)))
    b = num(b, notes)
    if b is None:
        return False
    if cls == "simple_analytic":
        return abs(b - e) <= ABS + REL * max(abs(b), abs(e))
    return b == e


def compare(root, res, out=print):
    exp = load_expected(root)
    got = cases_of(res)
    status = {}
    out("case\tfield\texpected\tblind\tresult\tnotes")
    for cid, e in exp.items():
        notes = set()
        obj = got.get(cid)
        res_c = "MATCH"
        if obj is None:
            out(f"{cid}\t-\t-\t-\tMISSING\tcase absent")
            status[cid] = "MISSING"
            continue
        names = {f["path"] for f in e["fields"]}
        if isinstance(obj, dict) and not (names & set(obj)):
            w = [k for k in WRAP if isinstance(obj.get(k), dict)]
            if len(w) == 1:
                obj = obj[w[0]]
                notes.add("UNWRAPPED")
        for f in e["fields"]:
            present = isinstance(obj, dict) and f["path"] in obj
            b = obj.get(f["path"]) if present else None
            if not present or (b is None and f["value"] is not None):
                r = "MISSING"
            else:
                r = "MATCH" if same(b, f["value"], f["class"], notes) else "MISMATCH"
            if r == "MISMATCH":
                res_c = "MISMATCH"
            elif r == "MISSING" and res_c == "MATCH":
                res_c = "MISSING"
            tag = " rule-field" if (cid, f["path"]) in RULE_FIELDS else ""
            out(f"{cid}\t{f['path']}\t{f['value']!r}\t{b!r}\t{r}\t{','.join(sorted(notes))}{tag}")
        status[cid] = res_c
    eligible = [c for c in exp if c not in NOT_COUNTED]
    counted = sum(status[c] == "MATCH" for c in eligible)
    n_match = sum(v == "MATCH" for v in status.values())
    out(f"\nK-8e\tcases {len(exp)}\tMATCH {n_match}\tMISMATCH {sum(v == 'MISMATCH' for v in status.values())}\t"
        f"MISSING {sum(v == 'MISSING' for v in status.values())}\teligible {len(eligible)}\tcounted blind MATCH {counted}\t"
        f"needed {NEEDED}\toutside share {PUBLISHED + counted} of {TOTAL} ({(PUBLISHED + counted) / TOTAL:.1%})")
    for cid, why in NOT_COUNTED.items():
        out(f"# not counted: {cid}: {why} (compared: {status[cid]})")
    return status


def self_test(root):
    import io
    from btk_make_packet import CASES, skeleton
    exp = load_expected(root)
    checks = []
    # 0. the packet's written-out inputs equal the golden's inputs, and every expected field is in the skeleton
    gold = {c["case_id"]: c for c in json.loads((Path(root) / "datasets/golden/stage_k/btk_k.json").read_text(encoding="utf-8"))["cases"]}
    checks.append(("packet inputs equal the golden inputs (12 cases)",
                   len(CASES) == 12 and all(gold[cid]["inputs"] == inp and gold[cid]["operation"] == op for cid, op, inp in CASES)))
    checks.append(("expected values equal the golden outputs",
                   all(gold[cid]["expected"]["outputs"] == {f["path"]: f["value"] for f in e["fields"]} for cid, e in exp.items())))
    filled = {}
    ok_paths = True
    for cid, op, _ in CASES:
        sk = skeleton(op)
        for f in exp[cid]["fields"]:
            ok_paths &= f["path"] in sk
            sk[f["path"]] = f["value"]
        ok_paths &= set(sk) == {f["path"] for f in exp[cid]["fields"]}
        filled[cid] = sk
    checks.append(("skeleton fields equal the expected fields, case by case", ok_paths))

    def run(res):
        buf = io.StringIO()
        try:
            return compare(root, res, out=lambda s: buf.write(s + "\n"))
        except Shape:
            return "SHAPE"

    n = len(exp)
    allm = lambda st: isinstance(st, dict) and list(st.values()).count("MATCH") == n  # noqa: E731
    probs = {(c, f["path"]) for c, e in exp.items() for f in e["fields"] if f["class"] == "simple_analytic"}

    def perturb_probs(fn):
        d = copy.deepcopy(filled)
        for c, p in probs:
            d[c][p] = fn(d[c][p])
        return d

    checks.append(("exact values: all MATCH", allm(run({"cases": filled}))))
    checks.append(("1e-13 relative noise on probabilities: all MATCH", allm(run({"cases": perturb_probs(lambda x: x * (1 + 1e-13))}))))
    st = run({"cases": perturb_probs(lambda x: x * (1 - 1e-8))})
    checks.append(("1e-8 relative perturbation of probabilities: every case with a probability MISMATCH",
                   all(st[c] == "MISMATCH" for c, _ in probs)))
    d = copy.deepcopy(filled)
    d["btk_k-0014"]["red_from"] = 16
    d["btk_k-0015"]["zone"] = "AMBER"
    d["btk_k-0019"]["eligible"] = 1
    d["btk_k-0013"]["multiplier"] = 1.8300000001
    d["btk_k-0024"]["days_actual"] = [1, 2]
    d["btk_k-0016"]["multiplier"] = 2.0
    st = run({"cases": d})
    checks.append(("wrong integer, zone, 1 for True, multiplier off by 1e-10, short list, value for null: MISMATCH each",
                   all(st[c] == "MISMATCH" for c in ("btk_k-0014", "btk_k-0015", "btk_k-0019", "btk_k-0013", "btk_k-0024", "btk_k-0016"))))
    d = copy.deepcopy(filled)
    d["btk_k-0014"]["amber_from"] = 9.0
    d["btk_k-0020"]["cumulative_probability_975"] = repr(d["btk_k-0020"]["cumulative_probability_975"])
    st = run({"cases": d})
    checks.append(("integer as 9.0 and probability as a decimal string (R4): MATCH", st["btk_k-0014"] == "MATCH" and st["btk_k-0020"] == "MATCH"))
    checks.append(("wrapped in 'outputs' (R2): all MATCH", allm(run({"cases": {k: {"outputs": v} for k, v in filled.items()}}))))
    checks.append(("bare case map (R1): all MATCH", allm(run(filled))))
    checks.append(("list of cases with case_id (R1): all MATCH", allm(run({"cases": [dict(case_id=k, **v) for k, v in filled.items()]}))))
    checks.append(("an extra level above 'cases': SHAPE", run({"results": {"cases": filled}}) == "SHAPE"))
    st = run({"cases": {k: {"data": {"outputs": v}} for k, v in filled.items()}})
    checks.append(("two wrapper levels: no case MATCH", isinstance(st, dict) and "MATCH" not in st.values()))
    blank = {cid: skeleton(op) for cid, op, _ in CASES}
    st = run({"cases": blank})
    checks.append(("unfilled skeleton: no case MATCH (cases with a null-expected field still MISSING elsewhere)",
                   isinstance(st, dict) and "MATCH" not in st.values()))
    part = dict(filled)
    part.pop("btk_k-0021")
    st = run({"cases": part})
    checks.append(("one case absent: MISSING, the rest MATCH", st["btk_k-0021"] == "MISSING" and list(st.values()).count("MATCH") == n - 1))
    d = copy.deepcopy(filled)
    del d["btk_k-0022"]["breach_975"]
    st = run({"cases": d})
    checks.append(("one field absent: case MISSING", st["btk_k-0022"] == "MISSING"))
    ok = True
    for name, good in checks:
        print(f"{'PASS' if good else 'FAIL'}\t{name}")
        ok &= bool(good)
    print(f"# self-test: {sum(bool(g) for _, g in checks)}/{len(checks)} passed; needed blind matches {NEEDED} of "
          f"{n - len(NOT_COUNTED)} eligible")
    return 0 if ok else 1


def main():
    root = sys.argv[1]
    if sys.argv[2] == "--self-test":
        return self_test(root)
    res = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    try:
        st = compare(root, res)
    except Shape as e:
        print(f"SHAPE error: {e}")
        return 2
    return 0 if all(v == "MATCH" for v in st.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
