"""Wave 4c golden fix (Python lane question G-Q4): recompute every expsim_g output in binary64 with robust level-set
crossings, compare with W4C_GOLDEN_RAW.json, and replace the values that change.

The defect: the 50-digit generator found the crossings of f(x) = y on a 601-point grid over +-12 sd and capped the PFE
bisection at the best grid value. Near the flat maximum of a long payer's deflated value the set {f > y} is narrower than
one grid step (about 0.037 sd at 17 years), so crossings were missed and P(max(f, 0) <= y) at the golden y was below q.
Fix: split [-12 sd, 12 sd] at every local extremum of f (each refined to a zero of f' by brentq on the analytic
derivative's sign change, after a 6,001-point scan), so f is monotone on every piece; one crossing per piece at most.
Self-check: the CDF at each golden PFE equals q to 1e-10.

    cd oracle/python && uv run python -W ignore fix_w4c_pfe.py
"""
import json
import math
from pathlib import Path

import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtr
from scipy.integrate import quad

from gen_stage_g_berm import FCurve

HERE = Path(__file__).resolve().parent
ORE = HERE.parent / "ore"
Q = (0.95, 0.99)
HAZ, REC = 0.02, 0.4


def deflated(inp, t):
    cv = FCurve(**inp["curve"])
    a, s = inp["mean_reversion"], inp["sigma"]
    H = lambda u: (1 - math.exp(-a * u)) / a  # noqa: E731
    Zt = s * s * (math.exp(2 * a * t) - 1) / (2 * a)
    Ht, Pt = H(t), cv.P(t)
    terms = []  # (coefficient, H_T - H_t, (H_T^2 - H_t^2) zeta / 2) for each bond; constant 1 for the par legs
    const = 0.0
    for sw in inp["trades"]:
        Ts = [x for x in sw["payment_times"] if x > t]
        if not Ts:
            continue
        sg = 1 if sw["side"] == "PAY" else -1
        n, K = sw["notional"], sw["fixed_rate"]
        prev = [t] + Ts[:-1]
        const += sg * n
        for p, T in zip(prev, Ts):
            c = -sg * n * K * (T - p) - (sg * n if T == Ts[-1] else 0)
            terms.append((c * cv.P(T) / Pt, H(T) - Ht, (H(T) ** 2 - Ht * Ht) * Zt / 2))
    c = np.array([x[0] for x in terms])
    dh = np.array([x[1] for x in terms])
    q2 = np.array([x[2] for x in terms])

    def f(x):
        x = np.asarray(x, dtype=float)
        v = const + (c[:, None] * np.exp(-np.outer(dh, x) - q2[:, None])).sum(0)
        return v * Pt * np.exp(-Ht * x - Ht * Ht * Zt / 2)

    def df(x):
        x = np.asarray(x, dtype=float)
        e = np.exp(-np.outer(dh, x) - q2[:, None])
        v = const + (c[:, None] * e).sum(0)
        dv = (-(c * dh)[:, None] * e).sum(0)
        return (dv - Ht * v) * Pt * np.exp(-Ht * x - Ht * Ht * Zt / 2)
    return (lambda x: float(f([x])[0])), (lambda x: float(df([x])[0])), f, math.sqrt(Zt)


def pieces(f1, df1, fv, sd):
    xs = np.linspace(-12 * sd, 12 * sd, 6001)
    d = np.sign(np.diff(fv(xs)))
    knots = [xs[0]]
    for i in range(1, len(d)):
        if d[i] != d[i - 1]:
            a, b = xs[i - 1], xs[i + 1]
            knots.append(brentq(df1, a, b, xtol=1e-15 * sd, rtol=1e-15) if df1(a) * df1(b) < 0 else xs[i])
    knots.append(xs[-1])
    return sorted(set(knots))


def crossings(f1, y, knots):
    out = []
    for a, b in zip(knots, knots[1:]):
        ga, gb = f1(a) - y, f1(b) - y
        if ga == 0:
            out.append(a)
        elif ga * gb < 0:
            out.append(brentq(lambda x: f1(x) - y, a, b, xtol=1e-15, rtol=1e-15))
    return out


def point(inp, t):
    f1, df1, fv, sd = deflated(inp, t)
    kn = pieces(f1, df1, fv, sd)
    phi = lambda x: math.exp(-x * x / (2 * sd * sd)) / (sd * math.sqrt(2 * math.pi))  # noqa: E731
    pts = [-12 * sd] + crossings(f1, 0.0, kn) + [12 * sd]
    ee = ene = 0.0
    for a, b in zip(pts, pts[1:]):
        inner = sorted(set([a, b] + [k for k in kn if a < k < b]))
        val = sum(quad(lambda x: f1(x) * phi(x), u, v, epsabs=0, epsrel=1e-13, limit=200)[0] for u, v in zip(inner, inner[1:]))
        if f1((a + b) / 2) > 0:
            ee += val
        else:
            ene += val

    def cdf(y):
        pp = [-12 * sd] + crossings(f1, y, kn) + [12 * sd]
        return sum(ndtr(b / sd) - ndtr(a / sd) for a, b in zip(pp, pp[1:]) if f1((a + b) / 2) <= y)
    fmax = max(f1(k) for k in kn)
    pfe = []
    for q in Q:
        if cdf(0.0) >= q:
            pfe.append(0.0)
            continue
        y = brentq(lambda yy: cdf(yy) - q, 0.0, fmax, xtol=1e-12, rtol=1e-15)
        assert abs(cdf(y) - q) < 1e-10, (t, q, cdf(y))
        pfe.append(y)
    return ee, ene, pfe


def golden(inp):
    rows = [point(inp, t) for t in inp["exposure_times"]]
    ts = [0.0] + inp["exposure_times"]
    ee = [r[0] for r in rows]
    epe = sum(e * (ts[i + 1] - ts[i]) for i, e in enumerate(ee)) / ts[-1]
    cva = sum((1 - REC) * e * (math.exp(-HAZ * ts[i]) - math.exp(-HAZ * ts[i + 1])) for i, e in enumerate(ee))
    return {"discounted_ee": ee, "discounted_ene": [r[1] for r in rows], "pfe_95": [r[2][0] for r in rows],
            "pfe_99": [r[2][1] for r in rows], "epe": epe, "cva": cva}


def main():
    raw = json.loads((ORE / "W4C_GOLDEN_RAW.json").read_text())
    rows, new_raw = [], []
    for k, (name, a, s, inp, old) in enumerate(raw):
        new = golden(inp)
        cid = f"expsim_g-{k + 1:04d}"
        fixed = dict(old)
        for key in old:
            ov, nv = old[key], new[key]
            if isinstance(ov, list):
                for i, (x, y) in enumerate(zip(ov, nv)):
                    if abs(x - y) > 1e-8 * max(1.0, abs(x)):
                        rows.append(dict(case=cid, set=name, a=a, sigma=s, output=key, time=inp["exposure_times"][i], old=x, new=y))
                        assert key.startswith("pfe"), (cid, key, x, y)  # only the PFE search was defective
                        fixed[key] = list(fixed[key])
                        fixed[key][i] = y
            elif abs(ov - nv) > 1e-8 * max(1.0, abs(ov)):
                rows.append(dict(case=cid, set=name, a=a, sigma=s, output=key, time=None, old=ov, new=nv))
                raise AssertionError((cid, key, ov, nv))
        new_raw.append([name, a, s, inp, fixed])
        print(cid, name, "changed" if any(r["case"] == cid for r in rows) else "same", flush=True)
    (ORE / "W4C_GOLDEN_RAW.json").write_text(json.dumps(new_raw, indent=1) + "\n")
    (ORE / "W4C_GOLDEN_FIX_DIFF.json").write_text(json.dumps({"rule": "binary64 robust recomputation; values differing by more than 1e-8 relative replaced",
                                                               "changed_values": len(rows), "rows": rows}, indent=1) + "\n")
    print("changed values", len(rows))


if __name__ == "__main__":
    main()
