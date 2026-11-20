"""Audit A response checks (rulings KR-232, KR-234, KR-237; STAGE_K_R1_AUDIT_A.md KA-A4, KA-A6, KA-A16).

    python check_stage_k_audit_a.py cases OUT.jsonl        write the KR-234 sweep as CLI cases (one per book and move)
    python check_stage_k_audit_a.py judge OUT.jsonl RES... judge each build's batch output at 50 digits
    python check_stage_k_audit_a.py accuracy               KR-232 and KR-237 accuracy grids

`judge` checks abs(estimate_pnl - V_exact) <= bound for every case of every result file (one per build), with V_exact
the revaluation at 50 digits (mpmath). `accuracy` transcribes the stated algorithms of KR-232 (Student-t tail) and
KR-237 (binomial cdf) and measures them against mpmath, SciPy and exact rationals. Results go to
oracle/STAGE_K_AUDIT_A_CHECKS.json (merged by key). Our own oracle, not an outside check, except where SciPy is named.
"""
import itertools
import json
import math
import random
import sys
from fractions import Fraction
from pathlib import Path

import mpmath as mp

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "oracle" / "STAGE_K_AUDIT_A_CHECKS.json"
mp.mp.dps = 50

SWEEP_H = ([0.0] + [x * 10.0 ** -e for e in (30, 25, 20, 16, 14, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1) for x in (1.0, -1.0)]
           + [0.5, -0.5, 1.0, -1.0, 1.0 / 3.0, -0.07])
SWEEP_T = (1e-6, 1e-3, 0.25, 1.0, 5.0, 30.0, 100.0)
SWEEP_Y = (-1.0, -0.01, 0.0, 0.04, 0.3, 1.0)
SWEEP_N = (0.0, 1e-6, 1.0, 1e6, -1e6, 1e15, -1e15)


def books():
    """The same books as python/tests/test_stage_k_w1.py::sweep_books (KR-234 acceptance)."""
    out = [[(n, t, y)] for n, t, y in itertools.product(SWEEP_N, SWEEP_T, SWEEP_Y)]
    for t, y in itertools.product(SWEEP_T, SWEEP_Y):
        out.append([(1e6, t, y), (-1e6 * (1 + 1e-12), t, y)])
        out.append([(1e6, t, y), (-1e6, t, y)])
        if 2 * t <= 100:
            out.append([(1e6, t, y), (-1e6 * t * math.exp(-y * t) / (2 * t * math.exp(-y * 2 * t)), 2 * t, y)])
    rnd = random.Random(20261119)
    for _ in range(300):
        out.append([(rnd.uniform(-1e9, 1e9), rnd.choice(SWEEP_T) * rnd.uniform(0.5, 1.0), rnd.uniform(-0.05, 0.1))
                    for _ in range(rnd.randint(1, 20))])
    return out


def merge(key, value):
    doc = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {}
    doc[key] = value
    OUT.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def cmd_cases(path):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for b, book in enumerate(books()):
            for i, h in enumerate(SWEEP_H):
                f.write(json.dumps({"schema_version": "1.0", "case_id": f"sweep-{b:04d}-{i:02d}",
                                    "operation": "risk.intraday.delta_gamma_bound",
                                    "inputs": {"positions": [{"notional": n, "maturity": t, "yield": y} for n, t, y in book],
                                               "shift": h}}) + "\n")


def exact(inputs):
    h = mp.mpf(inputs["shift"])
    return mp.fsum(mp.mpf(p["notional"]) * (mp.exp(-(mp.mpf(p["yield"]) + h) * mp.mpf(p["maturity"]))
                                           - mp.exp(-mp.mpf(p["yield"]) * mp.mpf(p["maturity"])))
                   for p in inputs["positions"])


def cmd_judge(cases_path, results):
    cases = {}
    for line in open(cases_path, encoding="utf-8"):
        c = json.loads(line)
        cases[c["case_id"]] = c["inputs"]
    ref = {cid: exact(inp) for cid, inp in cases.items()}
    summary = {}
    for res in results:
        got = [json.loads(line) for line in open(res, encoding="utf-8") if line.strip().startswith("{")]
        bad, worst, n = [], 0.0, 0
        for r in got:
            cid = r.get("case_id")
            if cid not in ref:
                continue
            n += 1
            if r.get("status") != "ok":
                bad.append([cid, "status " + str(r.get("error"))])
                continue
            est, bound = mp.mpf(r["outputs"]["estimate_pnl"]), mp.mpf(r["outputs"]["bound"])
            gap = abs(est - ref[cid])
            if gap > bound:
                bad.append([cid, float(gap), float(bound)])
            elif bound:
                worst = max(worst, float(gap / bound))
        summary[Path(res).name] = {"cases": n, "expected": len(ref), "violations": len(bad), "first": bad[:5],
                                   "worst_gap_over_bound": worst}
        print(Path(res).name, summary[Path(res).name])
    merge("kr234_sweep_50_digits", summary)
    return 0 if all(v["violations"] == 0 and v["cases"] == len(ref) for v in summary.values()) else 1


# ---- KR-232 transcription (Student-t two-sided tail) ----
TWO_OVER_PI = 0.6366197723675814


def t_tail(nu, k):
    rn = math.sqrt(nu)
    if k <= rn:
        den = nu + k * k
        c2 = nu / den
        root = math.sqrt(den)
        s, c = k / root, rn / root
    else:
        r = rn / k
        w = math.sqrt(1.0 + r * r)
        s, c = 1.0 / w, r / w
        c2 = c * c
    odd = nu % 2 == 1
    m = (nu - 1) // 2 if odd else nu // 2

    def step(t, j):
        return (t * ((2 * j + 2) * c2)) / (2 * j + 3) if odd else (t * ((2 * j + 1) * c2)) / (2 * j + 2)

    t, total, e = 1.0, 0.0, 0
    for j in range(m):
        if e == 0:
            total += t
        t = step(t, j)
        if 0.0 < t < 2.0 ** -500:
            t, e = t * 2.0 ** 500, e + 1
    a = TWO_OVER_PI * (math.atan2(c, s) - s * c * total) if odd else 1.0 - s * total
    if a >= 0.125:
        return a
    rem, j = 0.0, m
    while True:
        rem += t
        t = step(t, j)
        j += 1
        if t <= rem * 2.0 ** -60:
            break
        if t < 2.0 ** -500:
            t, rem, e = t * 2.0 ** 500, rem * 2.0 ** 500, e + 1
    out = TWO_OVER_PI * s * c * rem if odd else s * rem
    for _ in range(e):
        out *= 2.0 ** -500
    return out


# ---- KR-237 transcription (binomial cdf) ----
def binom_cdf(n, x, p):
    if x < 0:
        return 0.0
    if x >= n:
        return 1.0
    q = 1.0 - p
    mode = math.floor((n + 1) * p)
    w, s, c, e, k = 1.0, 0.0, 0.0, 0, 0
    sums = []
    while True:
        t = s + w
        c += (s - t) + w if abs(s) >= abs(w) else (w - t) + s
        s = t
        sums.append((s + c, e))
        if k == n:
            break
        r = ((n - k) * p) / ((k + 1) * q)
        w *= r
        k += 1
        if k > mode and r <= 0.5 and w <= (s + c) * 2.0 ** -64:
            break
        if w > 2.0 ** 600:
            w, s, c, e = w * 2.0 ** -600, s * 2.0 ** -600, c * 2.0 ** -600, e + 1
    if x >= len(sums) - 1:
        return 1.0
    v = sums[x][0] / sums[-1][0]
    for _ in range(sums[-1][1] - sums[x][1]):
        v *= 2.0 ** -600
    return min(v, 1.0)


def exact_cdf(n, x, p):
    a, b = p.numerator, p.denominator
    cc = b - a
    term = cc ** n
    total = term
    for k in range(x):
        term = term * (n - k) * a // ((k + 1) * cc)
        total += term
    return Fraction(total, b ** n)


def cmd_accuracy():
    from scipy import stats
    sys.set_int_max_str_digits(0)
    grid, worst, worst_sp = [], 0.0, 0.0
    for nu in (1, 2, 3, 4, 5, 6, 9, 10, 29, 30, 99, 249, 1000, 9999, 10000, 99998, 99999):
        for k in (1e-8, 0.001, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0, 30.0, 316.0, 317.0, 1e3, 1e10):
            got = t_tail(nu, k)
            try:
                ref = mp.betainc(mp.mpf(nu) / 2, mp.mpf(1) / 2, 0, mp.mpf(nu) / (mp.mpf(nu) + mp.mpf(k) ** 2),
                                 regularized=True)
            except ValueError:  # mpmath gives up on values far below binary64
                ref = None
            if ref is None or ref < mp.mpf(2) ** -1022:
                grid.append([nu, k, got, None, "reference below the normal range"])
                continue
            rel = float(abs(mp.mpf(got) - ref) / ref)
            sp = float(2 * stats.t.sf(k, nu))
            rel_sp = abs(sp / float(ref) - 1)
            worst, worst_sp = max(worst, rel), max(worst_sp, rel_sp)
            grid.append([nu, k, got, rel, rel_sp])
    merge("kr232_t_tail_accuracy", {"worst_relative_vs_mpmath": worst, "worst_scipy_vs_mpmath": worst_sp,
                                    "columns": ["nu", "k", "algorithm", "rel_err_vs_mpmath50", "scipy_rel_err"],
                                    "grid": grid})
    print("KR-232 worst", worst, "scipy", worst_sp)
    rows, worst_b = [], 0.0
    for n, xs in ((2, (1,)), (250, (0, 4, 9, 10)), (1000, (5, 15, 24)), (10000, (80, 120, 140)),
                  (100000, (950, 1050, 1100)), (1000000, (9800, 10164, 10300))):
        for x in xs:
            for p, pf in ((0.01, Fraction(1, 100)), (0.025, Fraction(1, 40))):
                got = binom_cdf(n, x if p == 0.01 else int(x * 2.5), p)
                xx = x if p == 0.01 else int(x * 2.5)
                ex = exact_cdf(n, xx, pf) if n <= 100000 else None
                if ex is None:
                    ref = mp.betainc(n - xx, xx + 1, 0, 1 - mp.mpf(pf.numerator) / pf.denominator, regularized=True)
                    rel, how = float(abs(mp.mpf(got) / ref - 1)), "mpmath 50 digits"
                else:
                    rel, how = float(abs(Fraction(got) / ex - 1)), "exact rational"
                worst_b = max(worst_b, rel)
                rows.append([n, xx, p, got, rel, how])
    merge("kr237_binomial_accuracy", {"worst_relative": worst_b, "p_reference": "exact 1/100 and 1/40",
                                      "columns": ["n", "x", "p", "algorithm", "rel_err", "reference"], "rows": rows})
    print("KR-237 worst", worst_b)
    return 0


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "cases":
        sys.exit(cmd_cases(sys.argv[2]))
    if what == "judge":
        sys.exit(cmd_judge(sys.argv[2], sys.argv[3:]))
    sys.exit(cmd_accuracy())
