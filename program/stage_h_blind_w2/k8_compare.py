"""Compare a frozen K-8 blind result with the hidden expected values (DR-H2; program/STAGE_K_BLIND_K8.md).

Fixed before any blind result exists (the commit that adds this file, recorded in the record). Nothing here may
change after the blind lane hands back, except a representation fix that compares no value differently, recorded
with its reason in the record.

    python -I program/stage_h_blind_w2/k8_compare.py <checkout> <blind_results.json>   # the real run, once
    python -I program/stage_h_blind_w2/k8_compare.py <checkout> --self-test            # dry run on fabricated data

Expected values: program/stage_h_blind_w2/k8_expected.json, copied from the goldens' `expected.outputs` of the
seven value cases of datasets/golden/stage_k/k8_k.json. The self-test checks that the copy still equals the golden
and that the tolerances equal conformance/tolerances/policy.yaml.

Tolerance (the goldens' own, as the conformance runner applies it; spec bermudan-ladder-k8.md, paragraph "Binary64
and tolerance"): |blind - expected| <= absolute + relative * max(|blind|, |expected|), with
  aad_sensitivity  absolute 1e-10, relative 1e-8    every output of the four `rates.shortrate.bermudan_ladder` cases
  root_finding     absolute 1e-10, relative 1e-10   the price of the three `rates.shortrate.bermudan_swaption` cases
A non-finite or non-numeric blind value, a boolean, or a list of the wrong length is a MISMATCH; null is MISSING.

Representation rules (as k5a_compare.py; each use is printed):
  R1 top level: {"cases": {id: obj}}, or {"cases": [{"case_id": id, ...}]}, or {id: obj}; anything else is a SHAPE
     error (exit 2), never a silent pass.
  R2 a case object that holds none of its expected keys but has exactly one of "outputs", "result", "results" as an
     object is unwrapped one level (printed as UNWRAPPED).
  R4 a number given as a decimal string is read with float() (printed as STRING-NUMBER).

Counting: a case is MATCH only if every expected field matches. Fields stated by the rules text (R_FIELDS: the
ladder entries that spec step 7 says are exactly 0, positions where the golden is 0.0 and the step 7 rule gives
weight 0) are compared but give no credit on their own; every case still has nonzero ladder entries or a price to
count on. Exit 0 when every case is MATCH, 1 on any MISMATCH or MISSING, 2 on a SHAPE error.
"""
import copy
import io
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WRAP = ("outputs", "result", "results")
POLICY = {"aad_sensitivity": (1e-10, 1e-8), "root_finding": (1e-10, 1e-10)}
NEEDED = 5  # K-8 has 7 value cases; the 60% per-item floor needs ceil(0.6 * 7) = 5 counted cases
NOT_COUNTED = {}  # no whole case is stated by the rules text (fixed before any blind result)
NOTE_0004 = "k8_k-0004 has the inputs of k8_k-0001 (price operation); its MATCH adds no evidence beyond 0001's price"


class Shape(Exception):
    pass


def load_expected(root):
    return json.loads((Path(root) / "program/stage_h_blind_w2/k8_expected.json").read_text(encoding="utf-8"))


def zero_weight_nodes(inp):
    """Curve positions that spec step 7 (as corrected 2026-11-19) says give exactly 0: no exercise or payment time
    strictly between the node's neighbours (0 below the first; no upper end for the last two nodes)."""
    ts = inp["curve"]["times"]
    p = len(ts)
    s_all = sorted(set(inp["exercise_times"]) | set(inp["payment_times"]))
    out = []
    for j in range(p):
        lo = ts[j - 1] if j > 0 else 0.0
        hi = ts[j + 1] if j < p - 2 else math.inf
        if not any(lo < s < hi for s in s_all):
            out.append(j)
    return out


def r_fields(exp):
    out = set()
    for cid, e in exp["cases"].items():
        ladder = e["outputs"].get("d_price_d_discount_factors")
        if ladder is None:
            continue
        for j, v in enumerate(ladder):
            if v == 0.0:
                out.add((cid, j))
    return out


def cases_of(res):
    if isinstance(res, dict) and "cases" in res:
        c = res["cases"]
        if isinstance(c, dict):
            return c
        if isinstance(c, list) and all(isinstance(x, dict) and "case_id" in x for x in c):
            return {x["case_id"]: {k: v for k, v in x.items() if k != "case_id"} for x in c}
        raise Shape("'cases' is neither an object nor a list of objects with case_id")
    if isinstance(res, dict) and res and all(re.fullmatch(r"k8_k-\d{4}", k) for k in res):
        return res
    raise Shape("no case map found at the top level (R1)")


def num(b, notes):
    if isinstance(b, bool) or b is None:
        return None
    if isinstance(b, str):
        try:
            b = float(b)
        except ValueError:
            return None
        notes.add("STRING-NUMBER")
    if not isinstance(b, (int, float)) or not math.isfinite(b):
        return None
    return float(b)


def within(b, e, ab, rel):
    return abs(b - e) <= ab + rel * max(abs(b), abs(e))


def compare(root, res, out=print):
    exp = load_expected(root)
    rf = r_fields(exp)
    got = cases_of(res)
    status = {}
    worst = {}
    out("case\tfield\texpected\tblind\trel_diff\tresult\tnotes")
    for cid, e in exp["cases"].items():
        ab, rel = e["absolute"], e["relative"]
        notes = set()
        obj = got.get(cid)
        if obj is None:
            out(f"{cid}\t-\t-\t-\t-\tMISSING\tcase absent")
            status[cid] = "MISSING"
            continue
        if isinstance(obj, dict) and not (set(e["outputs"]) & set(obj)):
            w = [k for k in WRAP if isinstance(obj.get(k), dict)]
            if len(w) == 1:
                obj = obj[w[0]]
                notes.add("UNWRAPPED")
        res_c = "MATCH"
        fields = []
        for k, v in e["outputs"].items():
            if isinstance(v, list):
                bl = obj.get(k) if isinstance(obj, dict) else None
                if bl is None:
                    fields += [(f"{k}[{j}]", x, None, "MISSING") for j, x in enumerate(v)]
                elif not isinstance(bl, list) or len(bl) != len(v):
                    fields.append((k, v, bl, "MISMATCH"))
                else:
                    fields += [(f"{k}[{j}]", x, bl[j], None) for j, x in enumerate(v)]
            else:
                fields.append((k, v, obj.get(k) if isinstance(obj, dict) else None, None))
        for path, ev, bv, forced in fields:
            if forced:
                r, d = forced, "-"
            elif bv is None:
                r, d = "MISSING", "-"
            else:
                b = num(bv, notes)
                if b is None:
                    r, d = "MISMATCH", "-"
                else:
                    r = "MATCH" if within(b, ev, ab, rel) else "MISMATCH"
                    dd = abs(b - ev) / max(abs(ev), abs(b)) if (ev or b) else 0.0
                    d = f"{dd:.2e}"
                    worst[cid] = max(worst.get(cid, 0.0), dd)
            if r == "MISMATCH" or (r == "MISSING" and res_c == "MATCH"):
                res_c = r
            m = re.fullmatch(r"d_price_d_discount_factors\[(\d+)\]", path)
            tag = " R-field (stated by spec step 7, no credit alone)" if m and (cid, int(m.group(1))) in rf else ""
            out(f"{cid}\t{path}\t{ev!r}\t{bv!r}\t{d}\t{r}\t{','.join(sorted(notes))}{tag}")
        status[cid] = res_c
    counted = [c for c, s in status.items() if s == "MATCH" and c not in NOT_COUNTED]
    out(f"\nitem\tcases\tMATCH\tMISMATCH\tMISSING\teligible\tcounted blind MATCH\tneeded (60% per item)")
    vals = list(status.values())
    out(f"K-8\t{len(vals)}\t{vals.count('MATCH')}\t{vals.count('MISMATCH')}\t{vals.count('MISSING')}\t"
        f"{len(vals) - len(NOT_COUNTED)}\t{len(counted)}\t{NEEDED}")
    out("largest relative difference per case: " + ", ".join(f"{c} {w:.2e}" for c, w in worst.items()))
    out(f"# note: {NOTE_0004}")
    return status


def self_test(root):
    root = Path(root)
    exp = load_expected(root)
    checks = []
    gold = json.loads((root / exp["golden"]).read_text(encoding="utf-8"))
    gv = {c["case_id"]: c for c in gold["cases"] if c["expected"]["status"] == "ok"}
    checks.append(("expected file equals the golden's value cases (ids, outputs, classes)",
                   set(gv) == set(exp["cases"]) and all(gv[c]["expected"]["outputs"] == e["outputs"]
                   and gv[c]["tolerance_class"] == e["tolerance_class"] and gv[c]["operation"] == e["operation"]
                   for c, e in exp["cases"].items())))
    pol = (root / "conformance/tolerances/policy.yaml").read_text(encoding="utf-8")
    ok = True
    for cls, (ab, rel) in POLICY.items():
        m = re.search(rf"^  {cls}:\n(?:    #.*\n)*    absolute: ([0-9.e+-]+)\n    relative: ([0-9.e+-]+)", pol, re.M)
        ok &= bool(m) and float(m.group(1)) == ab and float(m.group(2)) == rel
    ok &= all((e["absolute"], e["relative"]) == POLICY[e["tolerance_class"]] for e in exp["cases"].values())
    checks.append(("tolerances equal policy.yaml for both classes", ok))
    rf = r_fields(exp)
    gi = {c: gv[c]["inputs"] for c in gv}
    by_rule = {(c, j) for c, e in exp["cases"].items() if "d_price_d_discount_factors" in e["outputs"]
               for j in zero_weight_nodes(gi[c])}
    checks.append(("R-fields (golden 0.0) are exactly the nodes spec step 7 gives weight 0", rf == by_rule and len(rf) > 0))
    sys.path.insert(0, str(HERE))
    from k8_make_packet import skeleton, value_cases
    filled = {}
    for c in value_cases(root):
        sk = skeleton(c["operation"], c["inputs"])
        e = exp["cases"][c["case_id"]]["outputs"]
        if set(sk) != set(e) or any(isinstance(v, list) and len(sk[k]) != len(v) for k, v in e.items()):
            raise AssertionError(f"self-test: skeleton of {c['case_id']} differs from the expected fields")
        filled[c["case_id"]] = copy.deepcopy(e)
    n = len(exp["cases"])
    ladder = {c for c, e in exp["cases"].items() if e["tolerance_class"] == "aad_sensitivity"}
    price = set(exp["cases"]) - ladder

    def run(res):
        buf = io.StringIO()
        try:
            return compare(root, res, out=lambda s: buf.write(s + "\n"))
        except Shape:
            return "SHAPE"

    def scale(o, f):
        if isinstance(o, dict):
            return {k: scale(v, f) for k, v in o.items()}
        if isinstance(o, list):
            return [scale(v, f) for v in o]
        return f(o) if isinstance(o, float) and not isinstance(o, bool) else o

    st = run({"cases": filled})
    checks.append(("exact values: all MATCH", list(st.values()).count("MATCH") == n))
    st = run({"cases": scale(filled, lambda x: x * (1 + 3e-14))})
    checks.append(("3e-14 relative noise: all MATCH", list(st.values()).count("MATCH") == n))
    st = run({"cases": scale(filled, lambda x: x * (1 + 5e-9))})
    checks.append(("5e-9 relative: ladder cases MATCH (1e-8), price cases MISMATCH (1e-10)",
                   all(st[c] == "MATCH" for c in ladder) and all(st[c] == "MISMATCH" for c in price)))
    st = run({"cases": scale(filled, lambda x: x * (1 + 3e-8))})
    checks.append(("3e-8 relative: every case MISMATCH", all(v == "MISMATCH" for v in st.values())))
    st = run({"cases": scale(filled, lambda x: x * (1 + 5e-11))})
    checks.append(("5e-11 relative: all MATCH", list(st.values()).count("MATCH") == n))
    one = copy.deepcopy(filled)
    one["k8_k-0002"]["d_price_d_discount_factors"][3] *= 1 + 2e-8
    st = run({"cases": one})
    checks.append(("one ladder entry off by 2e-8: only that case MISMATCH",
                   st["k8_k-0002"] == "MISMATCH" and list(st.values()).count("MATCH") == n - 1))
    z = copy.deepcopy(filled)
    z["k8_k-0001"]["d_price_d_discount_factors"][0] = 1e-12
    z["k8_k-0003"]["d_price_d_discount_factors"][9] = 1e-6
    st = run({"cases": z})
    checks.append(("a structural zero given as 1e-12 MATCH (absolute 1e-10), as 1e-6 MISMATCH",
                   st["k8_k-0001"] == "MATCH" and st["k8_k-0003"] == "MISMATCH"))
    sg = copy.deepcopy(filled)
    sg["k8_k-0005"]["d_price_d_mean_reversion"] *= -1
    sg["k8_k-0006"]["price"] = float("nan")
    st = run({"cases": sg})
    checks.append(("a sign flip and a NaN: MISMATCH", st["k8_k-0005"] == "MISMATCH" and st["k8_k-0006"] == "MISMATCH"))
    ln = copy.deepcopy(filled)
    ln["k8_k-0001"]["d_price_d_discount_factors"] = ln["k8_k-0001"]["d_price_d_discount_factors"][:-1]
    st = run({"cases": ln})
    checks.append(("a ladder list one entry short: MISMATCH", st["k8_k-0001"] == "MISMATCH"))
    st = run({"cases": {k: {"outputs": v} for k, v in filled.items()}})
    checks.append(("wrapped in 'outputs' (R2): all MATCH", list(st.values()).count("MATCH") == n))
    st = run(filled)
    checks.append(("bare case map at top level (R1): all MATCH", list(st.values()).count("MATCH") == n))
    st = run({"cases": [dict(case_id=k, **v) for k, v in filled.items()]})
    checks.append(("list of cases with case_id (R1): all MATCH", list(st.values()).count("MATCH") == n))
    checks.append(("an extra level above 'cases': SHAPE", run({"results": {"cases": filled}}) == "SHAPE"))
    st = run({"cases": {k: {"data": {"outputs": v}} for k, v in filled.items()}})
    checks.append(("two wrapper levels: no MATCH", isinstance(st, dict) and "MATCH" not in st.values()))
    blank = {c["case_id"]: skeleton(c["operation"], c["inputs"]) for c in value_cases(root)}
    st = run({"cases": blank})
    checks.append(("unfilled skeleton: all MISSING", isinstance(st, dict) and set(st.values()) == {"MISSING"}))
    part = dict(filled)
    part.pop("k8_k-0007")
    st = run({"cases": part})
    checks.append(("one case absent: MISSING, the rest MATCH", st["k8_k-0007"] == "MISSING" and list(st.values()).count("MATCH") == n - 1))
    s = copy.deepcopy(filled)
    s["k8_k-0004"]["price"] = repr(s["k8_k-0004"]["price"])
    s["k8_k-0005"]["price"] = True
    st = run({"cases": s})
    checks.append(("decimal string (R4) MATCH; true for a number MISMATCH", st["k8_k-0004"] == "MATCH" and st["k8_k-0005"] == "MISMATCH"))
    good = True
    for name, g in checks:
        print(f"{'PASS' if g else 'FAIL'}\t{name}")
        good &= g
    print(f"# self-test: {sum(g for _, g in checks)}/{len(checks)} passed; {n} cases, {len(rf)} R-fields")
    return 0 if good else 1


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
