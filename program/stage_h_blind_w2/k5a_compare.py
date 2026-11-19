"""Compare a frozen K-5a blind result with the hidden expected values (DR-H2).

Fixed before any blind result exists (commit recorded in program/STAGE_K_BLIND_K5A.md). Nothing here may change
after the blind lane hands back, except a representation fix that compares no value differently, recorded with
its reason in the record.

    python -I program/stage_h_blind_w2/k5a_compare.py <checkout> <blind_results.json>   # the real run
    python -I program/stage_h_blind_w2/k5a_compare.py <checkout> --self-test            # dry run on fabricated data

Field mapping: estimate_pnl, bound, label of each case, at the top level of the blind case object (the packet
skeleton, k5a_make_packet.skeleton). Fields the blind lane reports beyond these are not compared.

Tolerance, from the spec (intraday-risk-bounds.md, "Golden value cases": "Tolerance 1e-9 relative on estimate_pnl
and bound"; the goldens' tolerance_limit relative 1e-9, absolute 0), against the expected values at full binary64
precision (not the 6 decimals of the wave-1 packet):
  estimate_pnl, bound   |blind - expected| <= 1e-9 |expected|      (no absolute floor; no expected value is 0)
  label                 exact string
  null where a value is expected: MISSING; a boolean never matches a number
The relative difference of every number is printed, so agreement far inside the tolerance is visible.

Representation rules (as k2_compare.py; each use is printed):
  R1 top level: {"cases": {id: obj}}, or {"cases": [{"case_id": id, ...}]}, or {id: obj}; anything else is a
     SHAPE error (exit 2), never a silent pass.
  R2 a case object that holds none of the three fields but has exactly one of "outputs", "result", "results" as
     an object is unwrapped one level (printed as UNWRAPPED).
  R4 a number given as a decimal string is read with float() (printed as STRING-NUMBER).
Counting: a case is MATCH only if every field matches. R_FIELDS are stated by the rules text (the label, KR-10):
compared, but they give no credit; each case counts on estimate_pnl and bound. NOT_COUNTED: none (see the record).
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

REL = {"estimate_pnl": 1e-9, "bound": 1e-9}
NOT_COUNTED = {}
R_FIELDS = {"label": "stated by KR-10 (rules text)"}
NEEDED = 3  # 60% of the 5 value cases, rounded up
WRAP = ("outputs", "result", "results")
NAMES = ("estimate_pnl", "bound", "label")


class Shape(Exception):
    pass


def cases_of(res):
    if isinstance(res, dict) and "cases" in res:
        c = res["cases"]
        if isinstance(c, dict):
            return c
        if isinstance(c, list) and all(
            isinstance(x, dict) and "case_id" in x for x in c
        ):
            return {
                x["case_id"]: {k: v for k, v in x.items() if k != "case_id"} for x in c
            }
        raise Shape("'cases' is neither an object nor a list of objects with case_id")
    if (
        isinstance(res, dict)
        and res
        and all(re.fullmatch(r"idr_k-\d{4}", k) for k in res)
    ):
        return res
    raise Shape("no case map found at the top level (R1)")


def same(path, b, e, notes):
    """(ok, relative difference or None)."""
    if isinstance(e, str):
        return type(b) is str and b == e, None
    if isinstance(b, bool) or b is None:
        return False, None
    if isinstance(b, str):
        try:
            b = float(b)
            notes.add("STRING-NUMBER")
        except ValueError:
            return False, None
    if not isinstance(b, (int, float)) or not math.isfinite(b):
        return False, None
    rel = abs(b - e) / abs(e)
    return abs(b - e) <= REL[path] * abs(e), rel


def compare(root, res, out=print):
    exp = json.loads(
        (Path(root) / "program/stage_h_blind_w2/k5a_expected.json").read_text(
            encoding="utf-8"
        )
    )["cases"]
    got = cases_of(res)
    status = {}
    out("case\tfield\texpected\tblind\trel diff\tresult\tnotes")
    for cid, e in exp.items():
        notes = set()
        obj = got.get(cid)
        res_c = "MATCH"
        if obj is None:
            out(f"{cid}\t-\t-\t-\t-\tMISSING\tcase absent")
            status[cid] = "MISSING"
            continue
        if isinstance(obj, dict) and not (set(NAMES) & set(obj)):
            w = [k for k in WRAP if isinstance(obj.get(k), dict)]
            if len(w) == 1:
                obj = obj[w[0]]
                notes.add("UNWRAPPED")
        for f in e["fields"]:
            b = obj.get(f["path"]) if isinstance(obj, dict) else None
            if b is None:
                r, rel = "MISSING", None
            else:
                ok, rel = same(f["path"], b, f["value"], notes)
                r = "MATCH" if ok else "MISMATCH"
            if r == "MISMATCH" or (r == "MISSING" and res_c == "MATCH"):
                res_c = r
            tag = " R-field" if f["path"] in R_FIELDS else ""
            rs = "-" if rel is None else f"{rel:.2e}"
            out(
                f"{cid}\t{f['path']}\t{f['value']!r}\t{b!r}\t{rs}\t{r}\t{','.join(sorted(notes))}{tag}"
            )
        status[cid] = res_c
    n = len(exp)
    m = list(status.values()).count("MATCH")
    counted = sum(1 for c, s in status.items() if s == "MATCH" and c not in NOT_COUNTED)
    out(
        "\nitem\tcases\tMATCH\tMISMATCH\tMISSING\teligible\tcounted blind MATCH\tneeded (60%)"
    )
    out(
        f"K-5a\t{n}\t{m}\t{list(status.values()).count('MISMATCH')}\t{list(status.values()).count('MISSING')}"
        f"\t{n - len(NOT_COUNTED)}\t{counted}\t{NEEDED}"
    )
    for f, why in R_FIELDS.items():
        out(f"# rules-stated field, no credit on its own: {f}: {why}")
    return status


def self_test(root):
    import io

    from k5a_cases import CASES
    from k5a_make_packet import skeleton

    exp = json.loads(
        (Path(root) / "program/stage_h_blind_w2/k5a_expected.json").read_text(
            encoding="utf-8"
        )
    )["cases"]
    filled = {}
    for cid, *_ in CASES:
        sk = skeleton()
        for f in exp[cid]["fields"]:
            if f["path"] not in sk:
                raise AssertionError(
                    f"self-test: {cid} field {f['path']} not in the packet skeleton"
                )
            sk[f["path"]] = f["value"]
        filled[cid] = sk
    if set(filled) != set(exp):
        raise AssertionError("self-test: packet cases and expected cases differ")

    def run(res):
        buf = io.StringIO()
        try:
            st = compare(root, res, out=lambda s: buf.write(s + "\n"))
        except Shape as e:
            return "SHAPE", str(e)
        return st, None

    def scale(o, k):
        return {
            c: {f: (v * k if isinstance(v, float) else v) for f, v in d.items()}
            for c, d in o.items()
        }

    n = len(exp)
    checks = []
    st, _ = run({"cases": filled})
    checks.append(("exact values: all MATCH", list(st.values()).count("MATCH") == n))
    st, _ = run({"cases": scale(filled, 1 + 1e-12)})
    checks.append(
        (
            "1e-12 relative noise: all MATCH (inside 1e-9)",
            list(st.values()).count("MATCH") == n,
        )
    )
    st, _ = run({"cases": scale(filled, 1 + 0.9e-9)})
    checks.append(
        (
            "0.9e-9 relative: all MATCH (inside 1e-9)",
            list(st.values()).count("MATCH") == n,
        )
    )
    st, _ = run({"cases": scale(filled, 1 + 2e-9)})
    checks.append(
        ("2e-9 relative: every case MISMATCH", set(st.values()) == {"MISMATCH"})
    )
    r6 = copy.deepcopy(filled)
    for d in r6.values():
        d["bound"] += 4e-7  # inside the wave-1 5e-7 absolute check
    tight = {
        c for c, d in filled.items() if 4e-7 > 1e-9 * abs(d["bound"])
    }  # 1e-9 relative is tighter there
    st, _ = run({"cases": r6})
    checks.append(
        (
            (
                f"bound off by 4e-7 absolute (passes the wave-1 6-decimal check): MISMATCH on the {len(tight)} cases "
                "whose bound is below 400 (idr_k-0004, bound 2132, has 2.1e-6 absolute at 1e-9 relative: MATCH)"
            ),
            tight == {c for c, s in st.items() if s == "MISMATCH"} and len(tight) == 4,
        )
    )
    one = copy.deepcopy(filled)
    one["idr_k-0003"]["bound"] *= 1 + 1e-6
    st, _ = run({"cases": one})
    checks.append(
        (
            "one bound off by 1e-6: that case MISMATCH, the rest MATCH",
            st["idr_k-0003"] == "MISMATCH"
            and list(st.values()).count("MATCH") == n - 1,
        )
    )
    sg = copy.deepcopy(filled)
    sg["idr_k-0001"]["estimate_pnl"] = -sg["idr_k-0001"]["estimate_pnl"]
    st, _ = run({"cases": sg})
    checks.append(
        ("wrong sign of estimate_pnl: MISMATCH", st["idr_k-0001"] == "MISMATCH")
    )
    st, _ = run({"cases": {k: {"outputs": v} for k, v in filled.items()}})
    checks.append(
        ("wrapped in 'outputs' (R2): all MATCH", list(st.values()).count("MATCH") == n)
    )
    st, _ = run(filled)
    checks.append(
        ("bare case map (R1): all MATCH", list(st.values()).count("MATCH") == n)
    )
    st, _ = run({"cases": [dict(case_id=k, **v) for k, v in filled.items()]})
    checks.append(
        (
            "list of cases with case_id (R1): all MATCH",
            list(st.values()).count("MATCH") == n,
        )
    )
    st, _ = run({"results": {"cases": filled}})
    checks.append(("extra level above 'cases': SHAPE", st == "SHAPE"))
    st, _ = run({"cases": {k: {"data": {"outputs": v}} for k, v in filled.items()}})
    checks.append(
        (
            "two wrapper levels: no MATCH",
            isinstance(st, dict) and "MATCH" not in st.values(),
        )
    )
    st, _ = run({"cases": {cid: skeleton() for cid in filled}})
    checks.append(
        (
            "unfilled skeleton: all MISSING",
            isinstance(st, dict) and set(st.values()) == {"MISSING"},
        )
    )
    part = dict(filled)
    part.pop("idr_k-0005")
    st, _ = run({"cases": part})
    checks.append(
        (
            "one case absent: MISSING, rest MATCH",
            st["idr_k-0005"] == "MISSING" and list(st.values()).count("MATCH") == n - 1,
        )
    )
    lb = copy.deepcopy(filled)
    lb["idr_k-0002"]["label"] = "latency-aware analytics on simulated data "
    lb["idr_k-0004"]["bound"] = True
    st, _ = run({"cases": lb})
    checks.append(
        (
            "label with a trailing space, True for a number: MISMATCH both",
            st["idr_k-0002"] == "MISMATCH" and st["idr_k-0004"] == "MISMATCH",
        )
    )
    s = copy.deepcopy(filled)
    s["idr_k-0005"]["bound"] = repr(s["idr_k-0005"]["bound"])
    st, _ = run({"cases": s})
    checks.append(("decimal string (R4): MATCH", st["idr_k-0005"] == "MATCH"))
    ok = True
    for name, good in checks:
        print(f"{'PASS' if good else 'FAIL'}\t{name}")
        ok &= good
    print(
        f"# self-test: {sum(g for _, g in checks)}/{len(checks)} passed; every expected field of the {n} cases exists in the packet skeleton"
    )
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
