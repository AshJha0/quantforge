"""Compare a frozen K-8h (sensitivity-based initial margin, placeholder weights; sbim) blind result with the hidden expected values (DR-H2).

Copy of k2_compare.py (stage K wave 2) with the K-8h case list. Fixed before any blind result exists (commit
recorded in program/STAGE_K_BLIND_SBIM.md). Nothing here may change
after the blind lane hands back, except a representation fix that compares no value differently, recorded with
its reason in the record.

    python -I program/stage_h_blind_w2/sbim_compare.py <checkout> <blind_results.json>   # the real run
    python -I program/stage_h_blind_w2/sbim_compare.py <checkout> --self-test            # dry run on fabricated data

Field mapping: every field of sbim_expected.json is looked up in the blind case object by its path, which is the
path of output_template.json's results_skeleton (sbim_make_packet.skeleton); the self-test proves that every expected
path exists in the skeleton the blind lane fills. Fields the blind lane reports but the spec does not print are
not compared.

Tolerance (KR-139 = KR-67; the spec's Acceptance A1; no case of the 29 has a per-case exception):
  numbers   |blind - expected| <= max(1e-12 |expected|, 1e-15)
  booleans, strings  exact; a boolean never matches a number or the reverse (K-8h outputs are all numbers)
  null in the blind result where a value is expected: MISSING

Representation rules (fixed now, so a wrapper or level slip cannot void the run; each use is printed):
  R1 top level: {"cases": {id: obj}}, or {"cases": [{"case_id": id, ...}]}, or {id: obj}; anything else is a
     SHAPE error (exit 2), never a silent pass.
  R2 a case object that holds none of its expected top-level keys but has exactly one of "outputs", "result",
     "results" as an object is unwrapped one level (printed as UNWRAPPED).
  R3 a keyed member given as a list of objects is resolved by the first of id, bucket, group, factor, class,
     name, key that matches the key (printed as LIST-KEYED).
  R4 a number given as a decimal string is read with float() (printed as STRING-NUMBER).
Counting: a case is MATCH only if every expected field matches. Cases that cannot count (named in
program/STAGE_K_BLIND_SBIM.md, fixed now) are compared and reported but never counted as blind: NOT_COUNTED below.
K-8h has no table-lookup field (T_FIELDS empty).
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

REL, ABS = 1e-12, 1e-15
NOT_COUNTED = {"sbim_k-0028": "expected total 0 is stated by the rules text (spec step 9 and KR-136: no records gives total 0)"}
T_FIELDS = set()
GATE = {"K-8h": (29, 18)}  # (value cases, blind matches needed: ceil(0.6 x 29)) from STAGE_K_BLIND_SBIM.md
KEYS = ("id", "bucket", "group", "factor", "class", "name", "key")
WRAP = ("outputs", "result", "results")


class Shape(Exception):
    pass


def split(path):
    """'classes[IR.DELTA].buckets[USD].k_b' -> ['classes', ('IR.DELTA',), 'buckets', ('USD',), 'k_b']."""
    out = []
    for name, key in re.findall(r"([^.\[\]]+)(?:\[([^\]]+)\])?", path):
        out.append(name)
        if key:
            out.append((key,))
    return out


def lookup(obj, path, notes):
    o = obj
    for step in split(path):
        if isinstance(step, tuple):
            k = step[0]
            if isinstance(o, list):
                if k.isdigit() and all(not isinstance(x, dict) for x in o):
                    o = o[int(k)]
                    continue
                hit = [x for x in o if isinstance(x, dict) and any(str(x.get(f)) == k for f in KEYS)]
                if len(hit) != 1:
                    raise KeyError(path)
                notes.add("LIST-KEYED")
                o = hit[0]
            else:
                o = o[k]
        else:
            o = o[step]
    return o


def cases_of(res):
    if isinstance(res, dict) and "cases" in res:
        c = res["cases"]
        if isinstance(c, dict):
            return c
        if isinstance(c, list) and all(isinstance(x, dict) and "case_id" in x for x in c):
            return {x["case_id"]: {k: v for k, v in x.items() if k != "case_id"} for x in c}
        raise Shape("'cases' is neither an object nor a list of objects with case_id")
    if isinstance(res, dict) and res and all(re.fullmatch(r"sbim_k-\d{4}", k) for k in res):
        return res
    raise Shape("no case map found at the top level (R1)")


def same(b, e, notes):
    if isinstance(e, bool) or e is None or isinstance(e, str):
        return type(b) is type(e) and b == e
    if isinstance(b, bool):
        return False
    if isinstance(b, str):
        try:
            b = float(b)
            notes.add("STRING-NUMBER")
        except ValueError:
            return False
    if not isinstance(b, (int, float)) or not math.isfinite(b):
        return False
    return abs(b - e) <= max(REL * abs(e), ABS)


def compare(root, res, out=print):
    exp = json.loads((Path(root) / "program/stage_h_blind_w2/sbim_expected.json").read_text(encoding="utf-8"))["cases"]
    got = cases_of(res)
    summary = {}
    status = {}
    out("case\tfield\texpected\tblind\tresult\tnotes")
    for cid, e in exp.items():
        notes = set()
        obj = got.get(cid)
        res_c = "MATCH"
        if obj is None:
            out(f"{cid}\t-\t-\t-\tMISSING\tcase absent")
            res_c = "MISSING"
        else:
            top = {split(f["path"])[0] for f in e["fields"]}
            if isinstance(obj, dict) and not (top & set(obj)):
                w = [k for k in WRAP if isinstance(obj.get(k), dict)]
                if len(w) == 1:
                    obj = obj[w[0]]
                    notes.add("UNWRAPPED")
            for f in e["fields"]:
                try:
                    b = lookup(obj, f["path"], notes)
                except (KeyError, IndexError, TypeError):
                    b, r = None, "MISSING"
                else:
                    r = "MISSING" if b is None and f["value"] is not None else ("MATCH" if same(b, f["value"], notes) else "MISMATCH")
                if r != "MATCH" and res_c != "MISSING":
                    res_c = r if res_c == "MATCH" or r == "MISMATCH" else res_c
                tf = " T-field" if (cid, f["path"]) in T_FIELDS else ""
                out(f"{cid}\t{f['path']}\t{f['value']!r}\t{b!r}\t{r}\t{','.join(sorted(notes))}{tf}")
        status[cid] = res_c
        s = summary.setdefault(e["item"], {"cases": 0, "MATCH": 0, "MISMATCH": 0, "MISSING": 0, "counted_match": 0, "eligible": 0})
        s["cases"] += 1
        s[res_c] += 1
        if cid not in NOT_COUNTED:
            s["eligible"] += 1
            s["counted_match"] += res_c == "MATCH"
    out("\nitem\tcases\tMATCH\tMISMATCH\tMISSING\teligible\tcounted blind MATCH\tneeded (gate)")
    for item, s in sorted(summary.items()):
        out(f"{item}\t{s['cases']}\t{s['MATCH']}\t{s['MISMATCH']}\t{s['MISSING']}\t{s['eligible']}\t{s['counted_match']}\t{GATE[item][1]}")
    for cid, why in NOT_COUNTED.items():
        out(f"# not counted: {cid}: {why} (compared: {status[cid]})")
    return status


def self_test(root):
    import io
    from sbim_cases import CASES
    from sbim_make_packet import skeleton
    from sbim_ref import load_table
    P = load_table(root)
    exp = json.loads((Path(root) / "program/stage_h_blind_w2/sbim_expected.json").read_text(encoding="utf-8"))["cases"]
    filled = {}
    for cid, inp in CASES:
        sk = skeleton(P, inp)
        for f in exp[cid]["fields"]:
            parts = split(f["path"])
            o = sk
            for st in parts[:-1]:
                o = o[st[0] if isinstance(st, tuple) else st]
            last = parts[-1]
            key = last[0] if isinstance(last, tuple) else last
            if not isinstance(o, dict) or key not in o:
                raise AssertionError(f"self-test: {cid} path {f['path']} not in the packet skeleton")
            o[key] = f["value"]
        filled[cid] = sk

    def run(res):
        buf = io.StringIO()
        try:
            st = compare(root, res, out=lambda s: buf.write(s + "\n"))
        except Shape as e:
            return "SHAPE", str(e), buf.getvalue()
        return st, None, buf.getvalue()

    n = len(exp)
    checks = []

    def perturb(o, fn):
        if isinstance(o, dict):
            return {k: perturb(v, fn) for k, v in o.items()}
        if isinstance(o, list):
            return [perturb(v, fn) for v in o]
        if isinstance(o, (int, float)) and not isinstance(o, bool):
            return fn(o)
        return o

    def rc(d, cid, pc, r):
        return d[cid]["groups"][pc]["risk_classes"][r]

    st, _, _ = run({"cases": filled})
    checks.append(("exact values from the skeleton: all MATCH", list(st.values()).count("MATCH") == n))
    st, _, _ = run({"cases": perturb(filled, lambda x: x * (1 + 1e-14) if x else x)})
    checks.append(("1e-14 relative noise: all MATCH (inside 1e-12)", list(st.values()).count("MATCH") == n))
    st, _, _ = run({"cases": perturb(filled, lambda x: x * (1 + 1e-9) + (1e-9 if x == 0 else 0))})
    checks.append(("1e-9 relative perturbation: every case MISMATCH", all(v == "MISMATCH" for v in st.values())))
    st, _, _ = run({"cases": {k: {"outputs": v} for k, v in filled.items()}})
    checks.append(("wrapped in 'outputs' (R2): all MATCH, unwrapped", list(st.values()).count("MATCH") == n))
    st, _, _ = run(filled)
    checks.append(("bare case map at top level (R1): all MATCH", list(st.values()).count("MATCH") == n))
    st, _, _ = run({"cases": [dict(case_id=k, **v) for k, v in filled.items()]})
    checks.append(("list of cases with case_id (R1): all MATCH", list(st.values()).count("MATCH") == n))
    st, msg, _ = run({"results": {"cases": filled}})
    checks.append(("an extra level above 'cases': SHAPE error, not a pass", st == "SHAPE"))
    st, msg, _ = run({"cases": {k: {"data": {"outputs": v}} for k, v in filled.items()}})
    checks.append(("two wrapper levels: no case MATCH", isinstance(st, dict) and "MATCH" not in st.values()))
    blank = {cid: skeleton(P, inp) for cid, inp in CASES}
    st, _, _ = run({"cases": blank})
    checks.append(("unfilled skeleton (all null): no MATCH, all MISSING", isinstance(st, dict) and set(st.values()) == {"MISSING"}))
    part = dict(filled)
    part.pop("sbim_k-0019")
    st, _, _ = run({"cases": part})
    checks.append(("one case absent: that case MISSING, the rest MATCH",
                   st["sbim_k-0019"] == "MISSING" and list(st.values()).count("MATCH") == n - 1))
    b = copy.deepcopy(filled)
    b["sbim_k-0001"]["total"] = True
    st, _, _ = run({"cases": b})
    checks.append(("True for a number: MISMATCH", st["sbim_k-0001"] == "MISMATCH"))
    s = copy.deepcopy(filled)
    s["sbim_k-0002"]["total"] = repr(s["sbim_k-0002"]["total"])
    dl = rc(s, "sbim_k-0005", "RATES", "IR")["delta"]
    dl["buckets"] = [dict(bucket=k, **v) for k, v in dl["buckets"].items()]
    st, _, _ = run({"cases": s})
    checks.append(("decimal string (R4) and keyed list (R3): MATCH", st["sbim_k-0002"] == "MATCH" and st["sbim_k-0005"] == "MATCH"))
    d = copy.deepcopy(filled)
    rc(d, "sbim_k-0006", "RATES", "IR")["delta"]["buckets"]["USD"]["s_b"] *= -1
    rc(d, "sbim_k-0019", "RATES", "IR")["curvature"]["theta"] = 0.0
    st, _, _ = run({"cases": d})
    checks.append(("wrong sign of a clipped S_b, and theta 0 where it is -1/3: MISMATCH",
                   st["sbim_k-0006"] == "MISMATCH" and st["sbim_k-0019"] == "MISMATCH"))
    e = copy.deepcopy(filled)
    e["sbim_k-0025"]["groups"].pop("EQUITY")
    st, _, _ = run({"cases": e})
    checks.append(("a group missing: MISSING", st["sbim_k-0025"] == "MISSING"))
    ok = True
    for name, good in checks:
        print(f"{'PASS' if good else 'FAIL'}\t{name}")
        ok &= good
    print(f"# self-test: {sum(g for _, g in checks)}/{len(checks)} passed; every one of the {n} cases' expected paths exists in the packet skeleton")
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
