"""Compare blind answers.json with the aadadj_k goldens (hidden side). Fixed before any blind result exists.

Rule per leaf: |a - e| <= abs + rel * max(|a|, |e|) with the golden's own tolerance_limit (KR-265: abs 1e-12,
rel 1e-10); strings, booleans and null exact; a missing or extra leaf is a mismatch; a case counts only if every
output leaf matches. answers.json: {"aadadj_k-0001": {<outputs in the shape of template.json>}, ...}.

    python -I aadadj_compare.py <repo> <answers.json>
    python -I aadadj_compare.py <repo> --self-test
"""
import copy
import json
import pathlib
import sys

SUITE = "datasets/golden/stage_k/aadadj_k.json"
B = ["aadadj_k-%04d" % i for i in range(1, 14)]


def flat(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from flat(v, f"{p}.{k}" if p else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from flat(v, f"{p}[{i}]")
    else:
        yield p, o


def expected(repo):
    cs = {c["case_id"]: c for c in json.loads((pathlib.Path(repo) / SUITE).read_text(encoding="utf-8"))["cases"]}
    return {cid: (cs[cid]["expected"]["outputs"], cs[cid]["tolerance_limit"]) for cid in B}


def judge(exp, got):
    lines, n = [], 0
    for cid in B:
        e, tol = exp[cid]
        g = dict(flat(got.get(cid) or {}))
        ef = dict(flat(e))
        bad = [f"{k}: extra leaf" for k in g if k not in ef]
        for k, v in ef.items():
            a = g.get(k)
            if isinstance(v, (bool, str)) or v is None:
                ok = a == v and type(a) is type(v)
            else:
                ok = isinstance(a, (int, float)) and not isinstance(a, bool) and \
                    abs(a - v) <= tol["absolute"] + tol["relative"] * max(abs(a), abs(v))
            if not ok:
                bad.append(f"{k}: blind {a!r} expected {v!r}")
        n += not bad
        lines.append(f"{cid} {'MATCH' if not bad else 'MISMATCH'} " + "; ".join(bad[:6]) + (" ..." if len(bad) > 6 else ""))
    lines.append(f"MATCH {n} of {len(B)}")
    return lines, n


def self_test(exp):
    good = {c: copy.deepcopy(e) for c, (e, _) in exp.items()}
    _, n = judge(exp, good)
    assert n == len(B), n
    # planted pass: every number moved by half the tolerance still matches
    near = copy.deepcopy(good)
    near["aadadj_k-0001"]["cva"] *= 1 + 4e-11
    _, n2 = judge(exp, near)
    # planted fails: one gradient entry moved by 1e-9 relative, one leaf missing, one extra leaf
    bad = copy.deepcopy(good)
    bad["aadadj_k-0001"]["gradient"]["cva"]["ee"][1] *= 1 + 1e-9
    del bad["aadadj_k-0005"]["gradient"]["dva"]["ene"]
    bad["aadadj_k-0013"]["gradient"]["fva"]["extra"] = 0.0
    lines, m = judge(exp, bad)
    assert n2 == len(B) and m == len(B) - 3, (n2, m)
    assert sum("MISMATCH" in l for l in lines) == 3
    print("self-test PASS (13 of 13 on the goldens; planted near-pass matches; 3 planted fails caught)")


def main():
    repo = sys.argv[1]
    exp = expected(repo)
    if sys.argv[2] == "--self-test":
        self_test(exp)
        return 0
    got = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
    lines, _ = judge(exp, got)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
