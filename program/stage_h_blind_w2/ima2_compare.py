"""Compare a frozen K-8f second-lane blind result with the hidden expected values (DR-H2): pla_k-0001 to 0006,
es_k-0001, es_k-0002 (the ima_k value cases whose only outside check was SciPy).

Fixed before any blind result exists (commit recorded in program/STAGE_K_BLIND_W2.md, "Second blind lane"). Nothing
here may change after the deriver hands back, except a representation fix that compares no value differently,
recorded with its reason in the record.

    python -I program/stage_h_blind_w2/ima2_compare.py <checkout> <blind_results.json>   # the real run, once
    python -I program/stage_h_blind_w2/ima2_compare.py <checkout> --self-test            # dry run on fabricated data

Field mapping: every compared output of the golden (ima2_expected.json, copied from datasets/golden/stage_k/ima_k.json)
is read from the blind case object under the same name; the names are the packet skeleton's
(ima2_make_packet.FIELDS) and the self-test fails if the skeleton and the expected fields differ. Golden outputs not
asked for (n, regulatory_window, label, mode: an input length, a rule on it, a fixed string, the input mode) are
listed in ima2_expected.json "omitted_fields"; they carry no derivation.

Tolerance, from ruling KR-67, frtb-ima.md A1 and the golden's tolerance_limit (relative 1e-12, absolute 1e-15), in the
form k2_compare.py used for the same specs:
  real   |b - e| <= max(1e-12 |e|, 1e-15)   (spearman, ks, ks_pvalue_asymptotic, es, each es_by_horizon element)
  exact  ks_count by integer value (30 and 30.0 equal), zone as a string; a boolean never equals a number
Stated so nobody is surprised: pla_k-0004's p-value is 1.88e-17, so the 1e-15 absolute floor accepts any value in
[-1e-15, 1e-15] there; the case still counts on its other fields.

Representation rules (as btk_compare.py; each use is printed):
  R1 top level {"cases": {id: obj}}, {"cases": [{"case_id": id, ...}]} or {id: obj}; anything else is SHAPE (exit 2).
  R2 a case object holding none of its expected keys but exactly one of "outputs", "result", "results" as an object
     is unwrapped one level (UNWRAPPED).
  R4 a number given as a decimal string is read with float() (STRING-NUMBER).
Counting: a case is MATCH only if every expected field matches. NOT_COUNTED cases are compared but never counted.
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
NOT_COUNTED = {}  # none: the packet's rules text states no answer (KR-57's numeric factor is cut; leak check)
COUNTED_BEFORE, TOTAL = 19, 33  # 4 printed + 15 first blind lane (STAGE_K_BLIND_W2.md correction 2026-11-19)
NEEDED = math.ceil(0.6 * TOTAL) - COUNTED_BEFORE  # 1
WRAP = ("outputs", "result", "results")
IDPAT = r"(?:pla|es)_k-\d{4}"


class Shape(Exception):
    pass


def load_expected(root):
    return json.loads((Path(root) / "program/stage_h_blind_w2/ima2_expected.json").read_text(encoding="utf-8"))["cases"]


def cases_of(res):
    if isinstance(res, dict) and "cases" in res:
        c = res["cases"]
        if isinstance(c, dict):
            return c
        if isinstance(c, list) and all(isinstance(x, dict) and "case_id" in x for x in c):
            return {x["case_id"]: {k: v for k, v in x.items() if k != "case_id"} for x in c}
        raise Shape("'cases' is neither an object nor a list of objects with case_id")
    if isinstance(res, dict) and res and all(re.fullmatch(IDPAT, k) for k in res):
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


def close(b, e, notes):
    b = num(b, notes)
    return b is not None and abs(b - e) <= max(REL * abs(e), ABS)


def same(b, e, cls, notes):
    if isinstance(e, str):
        return isinstance(b, str) and b == e
    if isinstance(e, list):
        return isinstance(b, list) and len(b) == len(e) and all(close(x, y, notes) for x, y in zip(b, e))
    if cls == "exact":
        b = num(b, notes)
        return b is not None and b == e
    return close(b, e, notes)


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
            if not present or b is None or (isinstance(b, list) and None in b):
                r = "MISSING"
            else:
                r = "MATCH" if same(b, f["value"], f["class"], notes) else "MISMATCH"
            if r == "MISMATCH":
                res_c = "MISMATCH"
            elif r == "MISSING" and res_c == "MATCH":
                res_c = "MISSING"
            out(f"{cid}\t{f['path']}\t{f['value']!r}\t{b!r}\t{r}\t{','.join(sorted(notes))}")
        status[cid] = res_c
    eligible = [c for c in exp if c not in NOT_COUNTED]
    counted = sum(status[c] == "MATCH" for c in eligible)
    n_match = sum(v == "MATCH" for v in status.values())
    out(f"\nK-8f second lane\tcases {len(exp)}\tMATCH {n_match}\tMISMATCH {sum(v == 'MISMATCH' for v in status.values())}\t"
        f"MISSING {sum(v == 'MISSING' for v in status.values())}\teligible {len(eligible)}\tcounted blind MATCH {counted}\t"
        f"needed {NEEDED}\toutside share {COUNTED_BEFORE + counted} of {TOTAL} ({(COUNTED_BEFORE + counted) / TOTAL:.1%})")
    for cid, why in NOT_COUNTED.items():
        out(f"# not counted: {cid}: {why} (compared: {status[cid]})")
    return status


def self_test(root):
    import io
    from ima2_make_packet import CASES, skeleton
    exp = load_expected(root)
    checks = []
    gold = {c["case_id"]: c for c in json.loads((Path(root) / "datasets/golden/stage_k/ima_k.json").read_text(encoding="utf-8"))["cases"]}
    meta = json.loads((Path(root) / "program/stage_h_blind_w2/ima2_expected.json").read_text(encoding="utf-8"))
    checks.append(("packet inputs equal the golden inputs (8 cases)",
                   len(CASES) == 8 and all(gold[cid]["inputs"] == inp and gold[cid]["operation"] == op for cid, op, inp in CASES)))
    checks.append(("expected values equal the golden outputs minus the omitted fields",
                   all({k: v for k, v in gold[cid]["expected"]["outputs"].items() if k not in meta["omitted_fields"]}
                       == {f["path"]: f["value"] for f in e["fields"]} for cid, e in exp.items())))
    checks.append(("these 8 are exactly the ima_k value cases with no printed figure, no blind match, not a table lookup",
                   sorted(exp) == sorted(c for c, g in gold.items() if g["expected"]["status"] == "ok"
                                         and "table_lookup" not in g["tags"] and "published" not in g["tags"]
                                         and not any("blind re-derivation" in v for v in g["verified_by"]))))
    filled = {}
    ok_paths = True
    for cid, op, _ in CASES:
        sk = skeleton(op)
        ok_paths &= set(sk) == {f["path"] for f in exp[cid]["fields"]}
        for f in exp[cid]["fields"]:
            sk[f["path"]] = copy.deepcopy(f["value"])
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
    reals = [(c, f["path"]) for c, e in exp.items() for f in e["fields"] if f["class"] == "real"]

    def perturb(fn):
        d = copy.deepcopy(filled)
        for c, p in reals:
            v = d[c][p]
            d[c][p] = [fn(x) for x in v] if isinstance(v, list) else fn(v)
        return d

    checks.append(("exact values: all MATCH", allm(run({"cases": filled}))))
    checks.append(("1e-14 relative noise on every real: all MATCH", allm(run({"cases": perturb(lambda x: x * (1 + 1e-14))}))))
    st = run({"cases": perturb(lambda x: x * (1 - 1e-9) if abs(x) > 1e-6 else x)})
    checks.append(("1e-9 relative perturbation of every real above 1e-6: every case MISMATCH", all(v == "MISMATCH" for v in st.values())))
    d = copy.deepcopy(filled)
    d["pla_k-0003"]["zone"] = "RED"
    d["pla_k-0002"]["ks_count"] = 10
    d["pla_k-0006"]["ks_pvalue_asymptotic"] += 2e-15  # above the 1e-15 absolute floor (1e-12 x 1.35e-4 is below it)
    d["es_k-0001"]["es_by_horizon"] = d["es_k-0001"]["es_by_horizon"][:4]
    d["es_k-0002"]["es"] = 8.098386428338472 * (1 + 2e-12)
    d["pla_k-0005"]["ks_count"] = True
    st = run({"cases": d})
    checks.append(("wrong zone, wrong count, p-value 2e-15 off, short list, es 2e-12 off, True for a count: MISMATCH each",
                   all(st[c] == "MISMATCH" for c in ("pla_k-0003", "pla_k-0002", "pla_k-0006", "es_k-0001", "es_k-0002", "pla_k-0005"))))
    d = copy.deepcopy(filled)
    d["es_k-0001"]["es_by_horizon"][1] = 1e-16
    d["pla_k-0004"]["ks_pvalue_asymptotic"] = 0.0
    st = run({"cases": d})
    checks.append(("1e-16 where 0 is expected, 0 for the 1.9e-17 p-value (absolute floor): MATCH",
                   st["es_k-0001"] == "MATCH" and st["pla_k-0004"] == "MATCH"))
    d = copy.deepcopy(filled)
    d["pla_k-0003"]["ks_count"] = 30.0
    d["pla_k-0002"]["spearman"] = repr(d["pla_k-0002"]["spearman"])
    st = run({"cases": d})
    checks.append(("count as 30.0 and a real as a decimal string (R4): MATCH", st["pla_k-0003"] == "MATCH" and st["pla_k-0002"] == "MATCH"))
    checks.append(("wrapped in 'outputs' (R2): all MATCH", allm(run({"cases": {k: {"outputs": v} for k, v in filled.items()}}))))
    checks.append(("bare case map (R1): all MATCH", allm(run(filled))))
    checks.append(("list of cases with case_id (R1): all MATCH", allm(run({"cases": [dict(case_id=k, **v) for k, v in filled.items()]}))))
    checks.append(("an extra level above 'cases': SHAPE", run({"results": {"cases": filled}}) == "SHAPE"))
    st = run({"cases": {k: {"data": {"outputs": v}} for k, v in filled.items()}})
    checks.append(("two wrapper levels: no case MATCH", isinstance(st, dict) and "MATCH" not in st.values()))
    st = run({"cases": {cid: skeleton(op) for cid, op, _ in CASES}})
    checks.append(("unfilled skeleton: every case MISSING", isinstance(st, dict) and set(st.values()) == {"MISSING"}))
    part = dict(filled)
    part.pop("es_k-0002")
    st = run({"cases": part})
    checks.append(("one case absent: MISSING, the rest MATCH", st["es_k-0002"] == "MISSING" and list(st.values()).count("MATCH") == n - 1))
    d = copy.deepcopy(filled)
    del d["pla_k-0001"]["ks"]
    st = run({"cases": d})
    checks.append(("one field absent: case MISSING", st["pla_k-0001"] == "MISSING"))
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
