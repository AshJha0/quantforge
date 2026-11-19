"""Compare a frozen PUB blind result with the hidden expected values (DR-H2): the 28 cases whose only outside record
was a figure printed in the regulator text (KA-C18, KR-210): saccr_k-0001..0005, btk_k-0001..0012, tlk_k-0001..0011.

Fixed before any blind result exists (commit recorded in program/STAGE_K_BLIND_PUB.md). Nothing here may change
after the deriver hands back, except a representation fix that compares no value differently, recorded with its
reason in the record.

    python -I program/stage_h_blind_w2/pub_compare.py <checkout> <blind_results.json>   # the real run, once
    python -I program/stage_h_blind_w2/pub_compare.py <checkout> --self-test            # dry run on fabricated data

Field mapping: every output of the golden (pub_expected.json, copied by pub_extract.py from the three golden files,
their SHA-256 recorded there) is read from the blind case object under the same name, recursively: objects by key,
arrays by position (the specs fix the order: SA-CCR hedging sets by class, treatment, key; trades in input order).
Every golden leaf is compared; a case is MATCH only if every leaf matches (the outside-share rule counts a case only
if every compared output was checked at the golden's tolerance).

Tolerance, from the specs and the goldens' own classes (conformance/tolerances/policy.yaml):
  simple_analytic      |b - e| <= 1e-12 + 1e-10 * max(|b|, |e|)   every real of risk.saccr.ead (sa-ccr.md: "Reals are
                       binary64; tolerance class simple_analytic"), every cumulative probability (frtb-ima-backtest.md:
                       "Probabilities are binary64 (tolerance class simple_analytic)"; var-es-and-backtests.md)
  date_and_convention  exact: the golden's per-output classes (saccr `margined`, `capped`, `mpor_days`; btk
                       `exceptions`, `zone`, `amber_from`, `red_from`, `multiplier`; tlk `zone`, `plus_factor`);
                       integers by value (5 and 5.0 equal), binary64 equality for the multiplier and plus factor
  strings, booleans and null are always exact; a boolean never equals a number; a value where null is expected is a
  MISMATCH; null or absent where a value is expected is MISSING.

Representation rules (as btk_compare.py, fixed now): R1 top level {"cases": {id: obj}}, {"cases": [{"case_id": id,
...}]} or {id: obj}, anything else SHAPE (exit 2); R2 a case object holding none of its expected keys but exactly
one of "outputs", "result", "results" is unwrapped one level (UNWRAPPED); R4 a number given as a decimal string is
read with float() (STRING-NUMBER).
RULE_FIELDS are compared but give no credit on their own (a case counts on its computed fields). NOT_COUNTED is
empty when fixed: no case's answer is stated by the packet's rules text (see the record).
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
WRAP = ("outputs", "result", "results")
NOT_COUNTED = {}
_B = [f"btk_k-{i:04d}" for i in range(1, 13)]
_T = [f"tlk_k-{i:04d}" for i in range(1, 12)]
_S = [f"saccr_k-{i:04d}" for i in range(1, 6)]
RULE_FIELDS = {
    **{(c, f): "at 250 observations the formal statement's multiplier bands and KR-42 give it (the count is the input)"
       for c in _B for f in ("exceptions", "zone", "amber_from", "red_from", "multiplier")},
    **{(c, f): "at 250 and 0.99 the traffic-light section states the zone bands and the 1996 plus factors"
       for c in _T for f in ("zone", "plus_factor")},
    **{(c, f): "an input echo or sum (V, C, margined)" for c in _S for f in ("v", "c", "margined")},
}
# Counts before the run (tools/outside_shares.py under KR-210) and per-item floors (plan 15, 60%).
ITEMS = {"K-8d": (_S, 7, 16), "K-8e": (_B, 11, 24), "F (existing traffic_light)": (_T, 0, 11)}
STAGE_K = (50, 87)


class Shape(Exception):
    pass


def load_expected(root):
    return json.loads((Path(root) / "program/stage_h_blind_w2/pub_expected.json").read_text(encoding="utf-8"))["cases"]


def cases_of(res):
    if isinstance(res, dict) and "cases" in res:
        c = res["cases"]
        if isinstance(c, dict):
            return c
        if isinstance(c, list) and all(isinstance(x, dict) and "case_id" in x for x in c):
            return {x["case_id"]: {k: v for k, v in x.items() if k != "case_id"} for x in c}
        raise Shape("'cases' is neither an object nor a list of objects with case_id")
    if isinstance(res, dict) and res and all(re.fullmatch(r"(saccr|btk|tlk)_k-\d{4}", k) for k in res):
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


def leaf_cmp(b, e, cls, notes):
    """MATCH, MISMATCH or MISSING for one expected leaf e."""
    if b is None:
        return "MATCH" if e is None else "MISSING"
    if e is None or isinstance(e, (bool, str)):
        return "MATCH" if (type(b) is type(e) and b == e) else "MISMATCH"
    v = num(b, notes)
    if v is None:
        return "MISMATCH"
    if cls == "simple_analytic":
        return "MATCH" if abs(v - e) <= ABS + REL * max(abs(v), abs(e)) else "MISMATCH"
    return "MATCH" if v == e else "MISMATCH"


def walk(b, e, cls, path, notes, rows):
    """Append (path, expected, blind, result) for every expected leaf under e."""
    if isinstance(e, dict):
        if not isinstance(b, dict):
            rows.append((path, "{...}", b, "MISSING" if b is None else "MISMATCH"))
            return
        for k, ev in e.items():
            walk(b.get(k), ev, cls, f"{path}/{k}", notes, rows) if k in b else rows.append((f"{path}/{k}", ev, None, "MISSING"))
        return
    if isinstance(e, list):
        if not isinstance(b, list) or len(b) != len(e):
            rows.append((path, f"[{len(e)} items]", b if not isinstance(b, list) else f"[{len(b)} items]",
                         "MISSING" if b is None else "MISMATCH"))
            return
        for i, (bv, ev) in enumerate(zip(b, e)):
            walk(bv, ev, cls, f"{path}[{i}]", notes, rows)
        return
    rows.append((path, e, b, leaf_cmp(b, e, cls, notes)))


def compare(root, res, out=print):
    exp = load_expected(root)
    got = cases_of(res)
    status = {}
    out("case\tpath\texpected\tblind\tresult\tnotes")
    for cid, e in exp.items():
        obj = got.get(cid)
        if obj is None:
            out(f"{cid}\t-\t-\t-\tMISSING\tcase absent")
            status[cid] = "MISSING"
            continue
        notes = set()
        names = set(e["outputs"])
        if isinstance(obj, dict) and not (names & set(obj)):
            w = [k for k in WRAP if isinstance(obj.get(k), dict)]
            if len(w) == 1:
                obj = obj[w[0]]
                notes.add("UNWRAPPED")
        rows = []
        for k, ev in e["outputs"].items():
            cls = e["output_classes"].get(k, e["tolerance_class"])
            if isinstance(obj, dict) and k in obj:
                walk(obj[k], ev, cls, k, notes, rows)
            else:
                rows.append((k, ev, None, "MISSING"))
        res_c = "MATCH"
        for path, ev, bv, r in rows:
            if r == "MISMATCH":
                res_c = "MISMATCH"
            elif r == "MISSING" and res_c == "MATCH":
                res_c = "MISSING"
            tag = " rule-field" if (cid, path.split("/")[0].split("[")[0]) in RULE_FIELDS else ""
            out(f"{cid}\t{path}\t{ev!r}\t{bv!r}\t{r}\t{','.join(sorted(notes))}{tag}")
        status[cid] = res_c
    n_match = sum(v == "MATCH" for v in status.values())
    out(f"\nPUB\tcases {len(exp)}\tMATCH {n_match}\tMISMATCH {sum(v == 'MISMATCH' for v in status.values())}\t"
        f"MISSING {sum(v == 'MISSING' for v in status.values())}\teligible {len(exp) - len(NOT_COUNTED)}")
    added = 0
    for item, (ids, before, total) in ITEMS.items():
        c = sum(status.get(i) == "MATCH" for i in ids if i not in NOT_COUNTED)
        added += c
        need = max(0, math.ceil(0.6 * total) - before)
        out(f"{item}\tcounted blind MATCH {c} of {len(ids)}\tneeded {need}\tshare {before + c} of {total} "
            f"({(before + c) / total:.1%}){'' if before + c >= 0.6 * total else ' UNDER FLOOR'}")
    out(f"stage K\t{STAGE_K[0] + added} of {STAGE_K[1]} ({(STAGE_K[0] + added) / STAGE_K[1]:.1%})")
    for cid, why in NOT_COUNTED.items():
        out(f"# not counted: {cid}: {why} (compared: {status.get(cid)})")
    return status


def self_test(root):
    import hashlib
    import io
    from pub_make_packet import FIELDS, skeleton
    exp = load_expected(root)
    doc = json.loads((Path(root) / "program/stage_h_blind_w2/pub_expected.json").read_text(encoding="utf-8"))
    cases = json.loads((HERE / "pub_cases.json").read_text(encoding="utf-8"))["cases"]
    checks = []
    gold = {}
    sha_ok = True
    for rel, sha in doc["golden_sha256"].items():
        raw = (Path(root) / rel).read_bytes()
        sha_ok &= hashlib.sha256(raw).hexdigest() == sha
        gold.update({c["case_id"]: c for c in json.loads(raw.decode("utf-8"))["cases"]})
    checks.append(("golden files unchanged since pub_expected.json was written (SHA-256)", sha_ok))
    checks.append(("packet inputs equal the golden inputs (28 cases)",
                   len(cases) == 28 and all(gold[c["case_id"]]["inputs"] == c["inputs"] and gold[c["case_id"]]["operation"] == c["operation"] for c in cases)))
    checks.append(("expected values equal the golden outputs",
                   len(exp) == 28 and all(gold[cid]["expected"]["outputs"] == e["outputs"] for cid, e in exp.items())))
    checks.append(("skeleton fields equal the expected top-level fields, case by case",
                   all(set(skeleton(e["operation"])) == set(e["outputs"]) for e in exp.values())
                   and set(FIELDS) == {e["operation"] for e in exp.values()}))
    filled = {cid: copy.deepcopy(e["outputs"]) for cid, e in exp.items()}

    def run(res):
        buf = io.StringIO()
        try:
            return compare(root, res, out=lambda s: buf.write(s + "\n"))
        except Shape:
            return "SHAPE"

    n = len(exp)
    allm = lambda st: isinstance(st, dict) and list(st.values()).count("MATCH") == n  # noqa: E731

    def scale(o, f, cls_of):
        """Multiply every real under a simple_analytic output by f (exact classes untouched)."""
        out = copy.deepcopy(o)
        for cid, e in exp.items():
            for k in e["outputs"]:
                if e["output_classes"].get(k, e["tolerance_class"]) == "simple_analytic":
                    out[cid][k] = cls_of(out[cid][k], f)
        return out

    def mul(x, f):
        if isinstance(x, dict):
            return {k: mul(v, f) for k, v in x.items()}
        if isinstance(x, list):
            return [mul(v, f) for v in x]
        return x * f if isinstance(x, float) and x != 0.0 else x

    checks.append(("exact values: all MATCH", allm(run({"cases": filled}))))
    checks.append(("1e-13 relative noise on every real: all MATCH", allm(run({"cases": scale(filled, 1 + 1e-13, mul)}))))
    st = run({"cases": scale(filled, 1 - 1e-8, mul)})
    checks.append(("1e-8 relative perturbation of every real: every case MISMATCH", isinstance(st, dict) and all(v == "MISMATCH" for v in st.values())))
    d = copy.deepcopy(filled)
    d["saccr_k-0001"]["ead"] = 569.0  # the printed figure, not the full-precision value
    d["btk_k-0001"]["cumulative_probability"] = 0.0811  # the printed Table 2 figure
    d["tlk_k-0006"]["cumulative_probability"] = 0.9588
    d["saccr_k-0002"]["trades"][1]["delta"] = 1.0
    d["saccr_k-0005"]["hedging_sets"] = d["saccr_k-0005"]["hedging_sets"][::-1]
    d["saccr_k-0003"]["capped"] = 0
    d["btk_k-0007"]["multiplier"] = 1.7600000001
    d["tlk_k-0001"]["plus_factor"] = None
    d["btk_k-0012"]["zone"] = "AMBER"
    st = run({"cases": d})
    bad = ("saccr_k-0001", "btk_k-0001", "tlk_k-0006", "saccr_k-0002", "saccr_k-0005", "saccr_k-0003", "btk_k-0007", "btk_k-0012")
    checks.append(("printed rounded figures (569, 0.0811, 0.9588), a wrong delta sign, hedging sets reordered, 0 for "
                   "False, multiplier off by 1e-10, wrong zone: MISMATCH each; null for a value: MISSING",
                   all(st[c] == "MISMATCH" for c in bad) and st["tlk_k-0001"] == "MISSING"))
    d = copy.deepcopy(filled)
    d["btk_k-0003"]["amber_from"] = 5.0
    d["saccr_k-0004"]["ead"] = repr(d["saccr_k-0004"]["ead"])
    st = run({"cases": d})
    checks.append(("integer as 5.0 and a real as a decimal string (R4): MATCH", st["btk_k-0003"] == "MATCH" and st["saccr_k-0004"] == "MATCH"))
    d = copy.deepcopy(filled)
    d["saccr_k-0001"]["trades"].append(d["saccr_k-0001"]["trades"][0])
    d["saccr_k-0002"]["addon"].pop("FX")
    st = run({"cases": d})
    checks.append(("an extra trade, a missing addon class: MISMATCH, MISSING", st["saccr_k-0001"] == "MISMATCH" and st["saccr_k-0002"] == "MISSING"))
    checks.append(("wrapped in 'outputs' (R2): all MATCH", allm(run({"cases": {k: {"outputs": v} for k, v in filled.items()}}))))
    checks.append(("bare case map (R1): all MATCH", allm(run(filled))))
    checks.append(("list of cases with case_id (R1): all MATCH", allm(run({"cases": [dict(case_id=k, **v) for k, v in filled.items()]}))))
    checks.append(("an extra level above 'cases': SHAPE", run({"results": {"cases": filled}}) == "SHAPE"))
    st = run({"cases": {k: {"data": {"outputs": v}} for k, v in filled.items()}})
    checks.append(("two wrapper levels: no case MATCH", isinstance(st, dict) and "MATCH" not in st.values()))
    blank = {c["case_id"]: skeleton(c["operation"]) for c in cases}
    st = run({"cases": blank})
    checks.append(("unfilled skeleton: no case MATCH", isinstance(st, dict) and "MATCH" not in st.values()))
    part = dict(filled)
    part.pop("tlk_k-0011")
    st = run({"cases": part})
    checks.append(("one case absent: MISSING, the rest MATCH", st["tlk_k-0011"] == "MISSING" and list(st.values()).count("MATCH") == n - 1))
    ok = True
    for name, good in checks:
        print(f"{'PASS' if good else 'FAIL'}\t{name}")
        ok &= bool(good)
    print(f"# self-test: {sum(bool(g) for _, g in checks)}/{len(checks)} passed")
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
