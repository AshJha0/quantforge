"""R6-13 oracle lane 2: per-case outside checks for stage F backtests (risk.backtest.kupiec, .christoffersen).
Reads the committed goldens; never writes them.

Different formulation (D6): the spec computes the likelihood-ratio statistics from the closed-form MLEs
(p_hat = x/n, pi_ij = n_ij / row sum) typed into the LR formula. Here the unrestricted and restricted log
likelihoods are MAXIMISED NUMERICALLY by scipy.optimize.minimize_scalar (bounded Brent) on the Bernoulli and
first-order Markov-chain likelihoods, the transitions are counted by numpy on the exception array, and p-values
come from scipy.stats.chi2.sf. A wrong MLE, a wrong 0 ln 0 rule or a wrong transition count shows up as a gap.

Tolerance: bounded Brent with xatol 1e-15 leaves an error in the maximised log likelihood of order
n * (xatol / p)^2 at an interior optimum and n * xatol at a boundary optimum (p_hat = 0 or 1), so LR is judged
at 1e-7 absolute (n <= 2,000 here) and p-values at 1e-7 absolute (|dp/dLR| <= 0.5 near LR > 0; below that the
F-32 rule LR < 1e-12 -> 0 and p = 1 is applied to both sides). Transitions are exact.

    cd oracle/python && uv run python -W ignore outside_f_r6.py
"""
import json
import math
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import minimize_scalar
from scipy.stats import chi2

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "datasets" / "golden" / "stage_f" / "risk_f4.json"
LIB = f"scipy {scipy.__version__} minimize_scalar (bounded Brent) on the Bernoulli and Markov likelihoods; numpy {np.__version__} transition counts; scipy chi2.sf"
TOL = 1e-7


def xlogy(a, b):
    return 0.0 if a == 0 else a * math.log(b)


def max_bernoulli(k, m):
    """max over q in [0,1] of k ln q + (m - k) ln(1 - q), numerically."""
    if m == 0:
        return 0.0
    f = lambda q: -(xlogy(k, q) + xlogy(m - k, 1 - q))  # noqa: E731
    r = minimize_scalar(f, bounds=(0.0, 1.0), method="bounded", options={"xatol": 1e-15, "maxiter": 2000})
    best = min(r.fun, f(0.0) if k == 0 else math.inf, f(1.0) if k == m else math.inf)
    return -float(best)


def lr_uc(n, x, c):
    p = 1 - c
    lr = 2 * (max_bernoulli(x, n) - (xlogy(n - x, 1 - p) + xlogy(x, p)))
    return 0.0 if lr < 1e-12 else lr


def christoffersen(exc, c):
    e = np.asarray(exc, dtype=int)
    prev, cur = e[:-1], e[1:]
    n = {f"n{i}{j}": int(np.sum((prev == i) & (cur == j))) for i in (0, 1) for j in (0, 1)}
    luc = lr_uc(len(e), int(e.sum()), c)
    restricted = max_bernoulli(n["n01"] + n["n11"], len(e) - 1)
    unrestricted = max_bernoulli(n["n01"], n["n00"] + n["n01"]) + max_bernoulli(n["n11"], n["n10"] + n["n11"])
    lind = 2 * (unrestricted - restricted)
    lind = 0.0 if lind < 1e-12 else lind
    p = lambda lr, k: 1.0 if lr == 0.0 else float(chi2.sf(lr, k))  # noqa: E731
    return {"lr_uc": luc, "lr_ind": lind, "lr_cc": luc + lind, "p_uc": p(luc, 1), "p_ind": p(lind, 1),
            "p_cc": float(chi2.sf(luc + lind, 2)) if luc + lind > 0 else 1.0, "transitions": n}


def compare(gold, out):
    chk = []
    for k, gv in gold.items():
        ov = out[k]
        if isinstance(gv, dict):
            ok = gv == ov
            chk.append({"output": k, "golden": gv, "outside": ov, "tolerance": "exact", "pass": ok})
        else:
            chk.append({"output": k, "golden": gv, "outside": ov, "gap": gv - ov, "tolerance": TOL, "pass": bool(abs(gv - ov) <= TOL)})
    return chk


def main():
    g = json.loads(GOLD.read_text(encoding="utf-8"))
    res = {"kupiec": [], "christoffersen": []}
    for c in g["cases"]:
        if c["expected"]["status"] != "ok":
            continue
        i = c["inputs"]
        if c["operation"] == "risk.backtest.kupiec":
            lr = lr_uc(i["observations"], i["exceptions"], i["confidence"])
            out = {"lr_uc": lr, "p_value": 1.0 if lr == 0 else float(chi2.sf(lr, 1))}
            key = "kupiec"
        elif c["operation"] == "risk.backtest.christoffersen":
            out, key = christoffersen(i["exceptions"], i["confidence"]), "christoffersen"
        else:
            continue
        chk = compare(c["expected"]["outputs"], out)
        res[key].append({"case_id": c["case_id"], "pass": all(x["pass"] for x in chk), "checks": chk})
    for k, rs in res.items():
        bad = [(r["case_id"], [(x["output"], x.get("gap")) for x in r["checks"] if not x["pass"]]) for r in rs if not r["pass"]]
        print(f"{k}: {sum(r['pass'] for r in rs)} of {len(rs)} pass; fail {bad}")
    doc = {"rule": "per case; every output within tolerance", "library": LIB, "tolerance": TOL, "suites": {"risk_f4": res}}
    (ROOT / "oracle" / "OUTSIDE_F_R6.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
