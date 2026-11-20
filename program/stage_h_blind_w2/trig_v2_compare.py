"""K-4c v2 compare (DR-H2), fixed before any blind result exists.

Tolerances are the goldens' own, applied with the runner's rule (conformance/runner/runner.py same_number:
|a - e| <= abs + rel * max(|a|, |e|)):
  fire              exact boolean
  false_alarm_rate  class tail_probability: absolute 0, relative 1e-11 (cpp/rust/java golden replay tables)
  sigma, threshold, nominal_rate: the case's tolerance_limit (relative 1e-14; trig_k-0021 relative 3e-8)
Credit (R_NOCREDIT): trig_k-0004 `fire` is gap-decided by KR-13; it is compared but the case is not counted.
A case counts only if every compared output matches. Shape: {"cases": {id: {field: value}}}; one wrapper level
"outputs" inside a case is tolerated; anything else is SHAPE (exit 2). A number given as a decimal string is parsed.

    python -I program/stage_h_blind_w2/trig_v2_compare.py . <blind_results.json>
    python -I program/stage_h_blind_w2/trig_v2_compare.py . --self-test
Exit 0 all MATCH, 1 any MISMATCH or MISSING, 2 SHAPE.
"""
import copy
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED = HERE / "trig_v2_expected.json"
CLASS_REL = {"false_alarm_rate": 1e-11}
R_NOCREDIT = {"trig_k-0004": "fire decided by gap ruling KR-13"}


def num(v):
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def compare(exp, blind):
    if not isinstance(blind, dict) or set(blind) != {"cases"} or not isinstance(blind["cases"], dict):
        return None
    rows = []
    for cid, e in exp["cases"].items():
        b = blind["cases"].get(cid)
        if isinstance(b, dict) and set(b) == {"outputs"}:
            b = b["outputs"]
        if not isinstance(b, dict):
            rows.append((cid, "MISSING", [], False))
            continue
        res, det = "MATCH", []
        for f, ev in e["outputs"].items():
            bv = b.get(f)
            if f == "fire":
                ok = bv is ev
                det.append(f"{f}: blind {bv!r} expected {ev!r} {'ok' if ok else 'DIFF'}")
            else:
                a = num(bv)
                rel = CLASS_REL.get(f, e["rel"])
                if a is None or not math.isfinite(a):
                    ok = False
                    det.append(f"{f}: blind {bv!r} not a finite number")
                else:
                    d = abs(a - ev)
                    ok = d <= rel * max(abs(a), abs(ev))
                    rd = d / abs(ev) if ev else (0.0 if d == 0 else math.inf)
                    det.append(f"{f}: blind {a!r} expected {ev!r} rel {rd:.3g} limit {rel:g} {'ok' if ok else 'DIFF'}")
            if bv is None:
                res = "MISSING" if res == "MATCH" else res
            elif not ok:
                res = "MISMATCH"
        rows.append((cid, res, det, res == "MATCH" and cid not in R_NOCREDIT))
    return rows


def report(rows):
    for cid, res, det, counted in rows:
        print(f"{cid} {res} counted={'yes' if counted else 'no'}" + (f" ({R_NOCREDIT[cid]})" if cid in R_NOCREDIT else ""))
        for d in det:
            print("   ", d)
    n = len(rows)
    m = sum(r[1] == "MATCH" for r in rows)
    c = sum(r[3] for r in rows)
    print(f"TOTAL {n} cases: MATCH {m}, counted {c}, needed for 60% of {n}: {math.ceil(0.6 * n)}")
    return 0 if m == n else 1


def self_test(exp):
    def fake(fn):
        return {"cases": {cid: fn(cid, dict(e["outputs"])) for cid, e in exp["cases"].items()}}

    def scale(f, x):
        def g(cid, o):
            for k in o:
                if k != "fire" and (f is None or k == f):
                    o[k] = o[k] * (1 + x)
            return o
        return g

    def tally(b):
        r = compare(exp, b)
        return None if r is None else [x[1] for x in r]

    n = len(exp["cases"])
    checks = []
    checks.append(("exact", tally(fake(lambda c, o: o)) == ["MATCH"] * n))
    checks.append(("1e-15 noise", tally(fake(scale(None, 1e-15))) == ["MATCH"] * n))
    checks.append(("fa 9e-12", tally(fake(scale("false_alarm_rate", 9e-12))) == ["MATCH"] * n))
    checks.append(("fa 2e-11", tally(fake(scale("false_alarm_rate", 2e-11))) == ["MISMATCH"] * n))
    t = tally(fake(scale("sigma", 5e-14)))
    want = ["MATCH" if exp["cases"][c]["rel"] > 1e-13 else "MISMATCH" for c in exp["cases"]]
    checks.append(("sigma 5e-14 (only the 3e-8 case passes)", t == want))
    checks.append(("fire flipped", tally(fake(lambda c, o: dict(o, fire=not o["fire"]))) == ["MISMATCH"] * n))
    checks.append(("fire as 1", tally(fake(lambda c, o: dict(o, fire=int(o["fire"])))) == ["MISMATCH"] * n))
    checks.append(("outputs wrapper", tally({"cases": {c: {"outputs": e["outputs"]} for c, e in exp["cases"].items()}}) == ["MATCH"] * n))
    checks.append(("extra level is SHAPE", tally({"results": fake(lambda c, o: o)}) is None))
    checks.append(("skeleton MISSING", tally(fake(lambda c, o: dict.fromkeys(o))) == ["MISSING"] * n))
    b = fake(lambda c, o: o)
    first = next(iter(exp["cases"]))
    del b["cases"][first]
    checks.append(("absent case", tally(b)[0] == "MISSING"))
    checks.append(("decimal string", tally(fake(lambda c, o: {k: (repr(v) if k != "fire" else v) for k, v in o.items()})) == ["MATCH"] * n))
    checks.append(("sign flip", tally(fake(lambda c, o: dict(o, sigma=-o["sigma"]))) == ["MISMATCH"] * n))
    r = compare(exp, fake(lambda c, o: o))
    checks.append(("0004 not counted", all(x[3] == (x[0] != "trig_k-0004") for x in r)))
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    print(f"{sum(ok for _, ok in checks)}/{len(checks)} PASS")
    return 0 if all(ok for _, ok in checks) else 1


def main():
    exp = json.loads(EXPECTED.read_text(encoding="utf-8"))
    if sys.argv[2] == "--self-test":
        sys.exit(self_test(exp))
    blind = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    rows = compare(exp, copy.deepcopy(blind))
    if rows is None:
        print("SHAPE: expected {\"cases\": {case_id: {field: value}}}")
        sys.exit(2)
    sys.exit(report(rows))


if __name__ == "__main__":
    main()
