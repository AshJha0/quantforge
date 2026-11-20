"""Compare blind xVA results with the expected values (rule |a-e| <= abs + rel*max(|a|,|e|)).
Usage: python -I xva_compare.py <repo> <blind_results.json> | --self-test"""
import json, pathlib, sys

def load(repo):
    return json.loads((pathlib.Path(repo) / "program/stage_k_blind_xva/xva_expected.json").read_text())

def ok(a, e, rel, ab):
    if isinstance(e, (bool, str)) or e is None or isinstance(a, (bool, str)) or a is None:
        return a == e
    return abs(a - e) <= ab + rel * max(abs(a), abs(e))

def compare(exp, got):
    out = []
    for cid, outs in exp["cases"].items():
        rel, ab = exp["_tol"][cid.split("_")[0]]
        g = got.get(cid, {})
        bad = [f"{k}: blind {g.get(k)!r} expected {v!r}" for k, v in outs.items() if not ok(g.get(k), v, rel, ab)]
        out.append((cid, "MATCH" if not bad else "MISMATCH", bad))
    return out

if __name__ == "__main__":
    exp = load(sys.argv[1])
    if sys.argv[2] == "--self-test":
        good = {c: dict(o) for c, o in exp["cases"].items()}
        bad = json.loads(json.dumps(good)); bad["colva_k-0001"]["colva"] *= 1 + 1e-9
        r1, r2 = compare(exp, good), compare(exp, bad)
        assert all(s == "MATCH" for _, s, _ in r1)
        assert [c for c, s, _ in r2 if s != "MATCH"] == ["colva_k-0001"]
        print("self-test PASS"); sys.exit(0)
    res = compare(exp, json.loads(pathlib.Path(sys.argv[2]).read_text()))
    for cid, s, bad in res:
        print(cid, s, "; ".join(bad))
    print("MATCH", sum(s == "MATCH" for _, s, _ in res), "of", len(res))
