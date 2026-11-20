"""Compare blind v2 results with the candidate goldens (hidden side). Each case is judged at its own
tolerance_limit, rule |a - e| <= abs + rel * max(|a|, |e|); strings and booleans exact; a case counts only if
every output leaf matches.

    python -I xva_compare_v2.py <repo> <blind_results.json>
    python -I xva_compare_v2.py <repo> --self-test
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from xva_make_packet_v2 import B, SUITES  # noqa: E402


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
    out = {}
    for s in SUITES:
        for c in json.loads((pathlib.Path(repo) / "oracle/xva_k8b_candidates" / f"{s}.json").read_text(encoding="utf-8"))["cases"]:
            if c["case_id"] in B:
                out[c["case_id"]] = (c["expected"]["outputs"], c["tolerance_limit"])
    return out


def judge(exp, got):
    lines, n = [], 0
    for cid in B:
        e, tol = exp[cid]
        g = dict(flat(got.get(cid) or {}))
        bad = []
        for k, v in flat(e):
            a = g.get(k)
            if isinstance(v, (bool, str)) or v is None:
                ok = a == v
            else:
                ok = isinstance(a, (int, float)) and not isinstance(a, bool) and \
                    abs(a - v) <= tol["absolute"] + tol["relative"] * max(abs(a), abs(v))
            if not ok:
                bad.append(f"{k}: blind {a} expected {v}")
        n += not bad
        lines.append(f"{cid} {'MATCH' if not bad else 'MISMATCH'} " + "; ".join(bad[:6]) + (" ..." if len(bad) > 6 else ""))
    lines.append(f"MATCH {n} of {len(B)}")
    return lines, n


def main():
    repo = sys.argv[1]
    exp = expected(repo)
    if sys.argv[2] == "--self-test":
        good = {c: e for c, (e, _) in exp.items()}
        _, n = judge(exp, good)
        bad = json.loads(json.dumps(good))
        bad["mpor_k-0001"]["floor_days"] += 1
        _, m = judge(exp, bad)
        assert n == len(B) and m == len(B) - 1, (n, m)
        print("self-test PASS")
        return 0
    got = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
    lines, _ = judge(exp, got)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
