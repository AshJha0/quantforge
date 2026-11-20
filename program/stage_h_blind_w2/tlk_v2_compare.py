"""Compare for the tlk_k v2 blind packet. Fixed before any blind result exists.

Tolerances are the goldens' own (`tolerance_limit` of each case) with the runner's rule
(conformance/runner/runner.py `same_number`: |a - e| <= abs + rel * max(|a|, |e|)); zone exact string; plus_factor
exact (number or null). A case MATCHes only if every output matches.
Eligibility (fixed now): tlk_k-0016, -0017, -0018 (n = 1, x = 0) are compared but NOT counted (R_NOCREDIT): with
q = c taken exactly, P(X <= 0) = q^1 is the input itself, so the rules text gives the answer. Eligible 6 of 9.

    python -I program/stage_h_blind_w2/tlk_v2_compare.py . <blind_results.json>
    python -I program/stage_h_blind_w2/tlk_v2_compare.py . --self-test
"""
import json
import sys
from pathlib import Path

NOCREDIT = {"tlk_k-0016", "tlk_k-0017", "tlk_k-0018"}


def same(a, e, lim):
    if a is None or e is None:
        return a is None and e is None
    if isinstance(e, str) or isinstance(a, str):
        return a == e
    return abs(a - e) <= lim["absolute"] + lim["relative"] * max(abs(a), abs(e))


def compare(expected, blind):
    lines, counted = [], 0
    for cid, ex in expected.items():
        got = blind["cases"].get(cid, {})
        ok = True
        for f, ev in ex["outputs"].items():
            gv = got.get(f, "MISSING")
            lim = ex["tolerance_limit"] if f == "cumulative_probability" else {"absolute": 0.0, "relative": 0.0}
            m = gv != "MISSING" and same(gv, ev, lim)
            ok &= m
            lines.append(f"{cid} {f} expected={ev!r} got={gv!r} {'ok' if m else 'DIFF'}")
        tag = "MATCH" if ok else "MISMATCH"
        credit = ok and cid not in NOCREDIT
        counted += credit
        lines.append(f"{cid} {tag}{' (R_NOCREDIT)' if cid in NOCREDIT else ''} counted={credit}")
    lines.append(f"TOTAL cases={len(expected)} counted={counted} eligible={len(expected) - len(NOCREDIT)}")
    return lines, counted


def main():
    repo = Path(sys.argv[1])
    expected = json.loads((repo / "program/stage_h_blind_w2/tlk_v2_expected.json").read_text())
    if sys.argv[2] == "--self-test":
        good = {"cases": {k: dict(v["outputs"]) for k, v in expected.items()}}
        _, c = compare(expected, good)
        assert c == 6, c
        bad = json.loads(json.dumps(good))
        e = bad["cases"]["tlk_k-0012"]["cumulative_probability"]
        bad["cases"]["tlk_k-0012"]["cumulative_probability"] = e * (1 + 3e-12)
        bad["cases"]["tlk_k-0013"]["zone"] = "GREEN"
        _, c = compare(expected, bad)
        assert c == 4, c
        print("self-test PASS")
        return
    lines, _ = compare(expected, json.loads(Path(sys.argv[2]).read_text()))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
