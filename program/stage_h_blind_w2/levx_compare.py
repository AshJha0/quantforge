"""Compare for the K-8i blind packet (lev_k / lex_k). Fixed before any blind result exists.

Tolerances are the goldens' own (`tolerance_limit` of each case: relative 1e-12, absolute 1e-15) with the runner's
rule (conformance/runner/runner.py `same_number`: |a - e| <= abs + rel * max(|a|, |e|)) on every number; strings,
booleans, nulls, list lengths, list order and object keys exact. A case MATCHes only if every output matches.
Eligibility (fixed now): all 9 cases. The leak check's 6 hits are coincidences, stated in
program/STAGE_K_BLIND_K8I.md: 0.03 and 0.4 (shares in lex_k-0008) are the leverage minimum and a leverage CCF of
the other operation; "-8" (lex_k-0009) is the item name "K-8i" / "K-8d". No case is excluded for them.

    python -I program/stage_h_blind_w2/levx_compare.py . <blind_results.json>
    python -I program/stage_h_blind_w2/levx_compare.py . --self-test
"""
import json
import sys
from pathlib import Path

NOCREDIT: set[str] = set()


def diff(a, e, lim, path, out):
    if isinstance(e, dict):
        if not isinstance(a, dict) or set(a) != set(e):
            out.append(f"{path}: keys {sorted(a) if isinstance(a, dict) else a!r} != {sorted(e)}")
            return
        for k in e:
            diff(a[k], e[k], lim, f"{path}.{k}", out)
    elif isinstance(e, list):
        if not isinstance(a, list) or len(a) != len(e):
            out.append(f"{path}: list {a!r} != {e!r}")
            return
        for i, (x, y) in enumerate(zip(a, e)):
            diff(x, y, lim, f"{path}[{i}]", out)
    elif isinstance(e, bool) or e is None or isinstance(e, str):
        if a != e or type(a) is not type(e):
            out.append(f"{path}: {a!r} != {e!r}")
    else:
        if isinstance(a, bool) or not isinstance(a, (int, float)) or \
                abs(a - e) > lim["absolute"] + lim["relative"] * max(abs(a), abs(e)):
            out.append(f"{path}: {a!r} != {e!r}")


def compare(expected, blind):
    lines, counted = [], 0
    for cid, ex in expected.items():
        d = []
        diff(blind["cases"].get(cid, "MISSING"), ex["outputs"], ex["tolerance_limit"], cid, d)
        lines += [f"  DIFF {x}" for x in d]
        ok = not d
        credit = ok and cid not in NOCREDIT
        counted += credit
        lines.append(f"{cid} {'MATCH' if ok else 'MISMATCH'} counted={credit}")
    lines.append(f"TOTAL cases={len(expected)} counted={counted} eligible={len(expected) - len(NOCREDIT)}")
    return lines, counted


def main():
    repo = Path(sys.argv[1])
    expected = json.loads((repo / "program/stage_h_blind_w2/levx_expected.json").read_text(encoding="utf-8"))
    if sys.argv[2] == "--self-test":
        good = {"cases": {k: json.loads(json.dumps(v["outputs"])) for k, v in expected.items()}}
        _, c = compare(expected, good)
        assert c == 9, c
        bad = json.loads(json.dumps(good))
        bad["cases"]["lev_k-0001"]["ratio"] *= 1 + 3e-12
        bad["cases"]["lex_k-0009"]["report"].reverse()
        bad["cases"]["lev_k-0012"]["meets_minimum"] = False
        _, c = compare(expected, bad)
        assert c == 6, c
        print("self-test PASS")
        return
    lines, _ = compare(expected, json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
