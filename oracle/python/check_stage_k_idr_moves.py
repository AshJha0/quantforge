"""Stage K wave 1, K-5a acceptance cross-check at 50 digits (ruling KR-17).

Reads the 1,000-move logs that the Python and Java acceptance tests write (program/stage_k_w1/acceptance_python.json
key `intraday_bound_1000_moves`, program/stage_k_w1/acceptance_java.jsonl same key), and for every move recomputes
with mpmath at 50 digits, on the same binary64 book and shift (`mp.mpf(float)` is exact):
- the exact delta-gamma estimate, the exact revaluation and the exact Lagrange bound (KR-7 with |N|, KR-15);
- that the exact remainder |estimate - revaluation| is inside the exact bound (Taylor's theorem; must hold always);
- the rounding error of each binary64 output the test compared (estimate, revaluation, bound);
- the margin of the binary64 comparison: (bound - |estimate - revaluation|) in binary64, against the summed rounding.
Writes oracle/IDR_K_MOVES_CHECK_W1.json. This is our own oracle, not an outside check (KR-11).

    wsl: cd oracle/python && ~/qf-oracle-venv/bin/python -W ignore check_stage_k_idr_moves.py
"""
import json
from pathlib import Path

import mpmath as mp

mp.mp.dps = 50
ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "program" / "stage_k_w1"


def exact(book, h):
    h = mp.mpf(h)
    est = rev = bnd = mp.mpf(0)
    for n, t, y in book:
        n, t, y = mp.mpf(n), mp.mpf(t), mp.mpf(y)
        v = n * mp.exp(-y * t)
        est += v * (-t * h + t * t * h * h / 2)
        rev += n * mp.exp(-(y + h) * t) - v
        bnd += abs(h) ** 3 * t ** 3 * abs(n) * mp.exp(-t * min(y, y + h)) / 6
    return est, rev, bnd


def check(log):
    book, worst_exact, worst_round, min_margin = log["book"], mp.mpf(0), mp.mpf(0), None
    violations_exact = violations_f64 = 0
    for h, est_f, rev_f, bnd_f in log["moves"]:
        est, rev, bnd = exact(book, h)
        rem = abs(est - rev)
        violations_exact += rem > bnd
        violations_f64 += abs(est_f - rev_f) > bnd_f
        worst_exact = max(worst_exact, rem / bnd)
        rounding = abs(mp.mpf(est_f) - est) + abs(mp.mpf(rev_f) - rev) + abs(mp.mpf(bnd_f) - bnd)
        worst_round = max(worst_round, rounding / bnd)
        margin = (bnd - rem) / bnd
        min_margin = margin if min_margin is None else min(min_margin, margin)
    return {
        "moves": len(log["moves"]),
        "exact_violations": int(violations_exact),
        "binary64_violations": int(violations_f64),
        "worst_exact_remainder_over_bound": float(worst_exact),
        "min_exact_relative_margin": float(min_margin),
        "worst_binary64_rounding_over_bound": float(worst_round),
        "binary64_comparison_safe": bool(worst_round < min_margin),
    }


def main():
    out = {"digits": 50, "generator": "oracle/python/check_stage_k_idr_moves.py", "ruling": "KR-17",
           "note": "our own oracle, not an outside check (KR-11)"}
    py = json.loads((EV / "acceptance_python.json").read_text("utf-8"))["intraday_bound_1000_moves"]
    out["python"] = check(py)
    jp = EV / "acceptance_java.jsonl"
    if jp.exists():
        rows = [json.loads(line) for line in jp.read_text("utf-8").splitlines() if line.strip()]
        java = [r["value"] for r in rows if r["key"] == "intraday_bound_1000_moves"]
        if java:
            out["java"] = check(java[-1])
    for k in ("python", "java"):
        if k in out:
            assert out[k]["exact_violations"] == 0 and out[k]["binary64_violations"] == 0, (k, out[k])
    (ROOT / "oracle" / "IDR_K_MOVES_CHECK_W1.json").write_text(json.dumps(out, indent=1) + "\n", "utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
