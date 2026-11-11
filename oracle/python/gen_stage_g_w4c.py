"""Stage G wave 4c: exposure profiles of Hull-White swap portfolios by exact one-factor integration, checked against ORE
1.8.17 simulations (ruling G-42).

`xva.exposure.portfolio_hw`: for one netting set of fixed-float swaps (annual resets common to the set), at each exposure
time t (a reset date): discounted EE and ENE, PFE at 95% and 99% of the discounted exposure under the LGM measure, EPE,
and bucketed CVA (G-16 buckets). Hull-White is written in LGM form (H(t) = (1 - e^{-at})/a, zeta(t) = sigma^2 (e^{2at} - 1)/(2a)),
x(t) ~ N(0, zeta(t)) under the LGM measure, numeraire N(t, x) = exp(H x + H^2 zeta / 2) / P(0, t), bonds
P(t, T, x) = P(0, T)/P(0, t) exp(-(H_T - H_t) x - (H_T^2 - H_t^2) zeta / 2) [Lichters, Stamm, Gallagher, *Modern Derivatives
Pricing and Credit Exposure Analysis*, Palgrave, 2015, ch. 11]. Goldens: 40-digit mpmath quadrature split at the zeros of
the deflated value. Outside: ORE 1.8.17 (Python wheel, under WSL), one run per (a, sigma) in `oracle/ore/`, checked per case
within 3 Monte Carlo standard errors (`oracle/ore/ORE_CHECK_4C.json`).

    cd oracle/python && uv run python -W ignore gen_stage_g_w4c.py [cases|check]
"""
import json
import math
import sys
from pathlib import Path

import mpmath as mp

from gen_stage_g_w1 import CURVE, Curve

mp.mp.dps = 25
HERE = Path(__file__).resolve().parent
ORE = HERE.parent / "ore"
OP = "xva.exposure.portfolio_hw"
Q = (0.95, 0.99)
HAZ, REC = 0.02, 0.4


def lgm(a, s):
    a, s = mp.mpf(a), mp.mpf(s)
    return (lambda t: (1 - mp.exp(-a * t)) / a), (lambda t: s * s * (mp.exp(2 * a * t) - 1) / (2 * a))


def deflated_value(inp, t):
    """f(x): sum over trades of V(t, x)/N(t, x), V the remaining swap at reset date t (payer = floater minus fixed)."""
    cv = Curve(**inp["curve"])
    H, Z = lgm(inp["mean_reversion"], inp["sigma"])
    t = mp.mpf(t)
    Ht, Zt, Pt = H(t), Z(t), cv.P(t)
    legs = []
    for sw in inp["trades"]:
        Ts = [mp.mpf(x) for x in sw["payment_times"] if x > t]
        if not Ts:
            continue
        prev = [t] + Ts[:-1]
        sgn = 1 if sw["side"] == "PAY" else -1
        K, n = mp.mpf(sw["fixed_rate"]), mp.mpf(sw["notional"])
        legs.append((sgn, K, n, Ts, [T - p for p, T in zip(prev, Ts)]))

    def f(x):
        x = mp.mpf(x)
        N = mp.exp(Ht * x + Ht * Ht * Zt / 2) / Pt
        P = lambda T: cv.P(T) / Pt * mp.exp(-(H(T) - Ht) * x - (H(T) ** 2 - Ht * Ht) * Zt / 2)  # noqa: E731
        v = 0
        for sgn, K, n, Ts, taus in legs:
            v += sgn * n * (1 - P(Ts[-1]) - K * sum(tau * P(T) for tau, T in zip(taus, Ts)))
        return v / N
    return f, mp.sqrt(Zt)


def zeros(f, sd):
    xs = [sd * (-12 + 24 * mp.mpf(i) / 600) for i in range(601)]
    vs = [f(x) for x in xs]
    z = []
    for x0, x1, v0, v1 in zip(xs, xs[1:], vs, vs[1:]):
        if v0 == 0:
            z.append(x0)
        elif v0 * v1 < 0:
            z.append(mp.findroot(f, (x0, x1), solver="bisect" if False else "anderson"))
    return z, xs, vs


def profile_point(inp, t):
    f, sd = deflated_value(inp, t)
    z, xs, vs = zeros(f, sd)
    phi = lambda x: mp.exp(-x * x / (2 * sd * sd)) / (sd * mp.sqrt(2 * mp.pi))  # noqa: E731
    pts = [-12 * sd] + z + [12 * sd]
    ee = ene = 0
    for a, b in zip(pts, pts[1:]):
        mid = f((a + b) / 2)
        val = mp.quad(lambda x: f(x) * phi(x), [a, b])
        if mid > 0:
            ee += val
        else:
            ene += val
    # PFE: smallest y >= 0 with P(max(f, 0) <= y) >= q; the CDF is computed on the sorted level sets of f
    def cdf(y):
        g = lambda x: f(x) - y  # noqa: E731
        zz = []
        gv = [v - y for v in vs]
        for x0, x1, v0, v1 in zip(xs, xs[1:], gv, gv[1:]):
            if v0 * v1 < 0:
                zz.append(mp.findroot(g, (x0, x1), solver="anderson"))
        pp = [-12 * sd] + zz + [12 * sd]
        return sum(mp.ncdf(b / sd) - mp.ncdf(a / sd) for a, b in zip(pp, pp[1:]) if g((a + b) / 2) <= 0)
    pfe = []
    for q in Q:
        if cdf(mp.mpf(0)) >= q:
            pfe.append(mp.mpf(0))
            continue
        lo, hi = mp.mpf(0), max(vs)
        for _ in range(200):
            mid = (lo + hi) / 2
            if cdf(mid) >= q:
                hi = mid
            else:
                lo = mid
            if hi - lo <= mp.mpf(10) ** -11 * max(1, hi):
                break
        pfe.append(hi)
    return ee, ene, pfe


def golden(inp):
    rows = [profile_point(inp, t) for t in inp["exposure_times"]]
    ts = [mp.mpf(0)] + [mp.mpf(t) for t in inp["exposure_times"]]
    ee = [r[0] for r in rows]
    epe = sum(e * (ts[i + 1] - ts[i]) for i, e in enumerate(ee)) / ts[-1]
    cva = sum((1 - mp.mpf(REC)) * e * (mp.exp(-HAZ * ts[i]) - mp.exp(-HAZ * ts[i + 1])) for i, e in enumerate(ee))
    return {"discounted_ee": [float(x) for x in ee], "discounted_ene": [float(r[1]) for r in rows],
            "pfe_95": [float(r[2][0]) for r in rows], "pfe_99": [float(r[2][1]) for r in rows],
            "epe": float(epe), "cva": float(cva)}


# ------------------------------------------------------------------------------------------------ case design
MATS = (2, 5, 10, 20)
PARAMS = [(a, s) for s in (0.005, 0.01, 0.015) for a in (0.03, 0.10)]


def swap(m, side, k, n=1e7):
    return dict(notional=n, fixed_rate=k, side=side, start_years=0.0, payment_times=[float(i) for i in range(1, m + 1)])


PORTS = {
    "P1": [swap(5, "PAY", 0.035), swap(10, "RECEIVE", 0.04)],
    "P2": [swap(10, "PAY", 0.03), swap(10, "PAY", 0.045, 5e6)],
    "P3": [swap(2, "PAY", 0.04), swap(5, "PAY", 0.038), swap(20, "RECEIVE", 0.037)],
    "P4": [swap(5, "RECEIVE", 0.036), swap(5, "PAY", 0.041)],
    "P5": [swap(10, "RECEIVE", 0.03, 2e7), swap(20, "PAY", 0.035)],
    "P6": [swap(2, "RECEIVE", 0.039), swap(10, "RECEIVE", 0.039)],
    "P7": [swap(20, "PAY", 0.039), swap(20, "RECEIVE", 0.041)],
    "P8": [swap(5, "PAY", 0.039, 3e7), swap(10, "RECEIVE", 0.039, 1.5e7), swap(2, "RECEIVE", 0.039, 1e7)],
}


def cases():
    out = []
    for a, s in PARAMS:
        sets = {}
        for m in MATS:
            for side in ("PAY", "RECEIVE"):
                sets[f"S{m}{side[0]}"] = [swap(m, side, 0.039)]
        sets.update(PORTS)
        out.append((a, s, sets))
    return out


def case_input(a, s, trades):
    last = max(t for sw in trades for t in sw["payment_times"])
    return dict(curve=CURVE, mean_reversion=a, sigma=s, trades=trades, exposure_times=[float(t) for t in range(1, int(last))],
                pfe_quantiles=list(Q), hazard_rate=HAZ, recovery=REC)


def write_ore_cases(samples=5000):
    sys.path.insert(0, str(ORE))
    import build_case
    for i, (a, s, sets) in enumerate(cases()):
        case = dict(curve=CURVE, mean_reversion=a, sigma=s, samples=samples, seed=20261111 + i, grid=[float(t) for t in range(1, 21)],
                    netting_sets={k: {"trades": v} for k, v in sets.items()})
        build_case.write(str(ORE / f"run{i}"), case)
        (ORE / f"run{i}.json").write_text(json.dumps(case, indent=1) + "\n")


if __name__ == "__main__":
    if "ore" in sys.argv:
        write_ore_cases()


def _gold(args):
    a, s, name, trades = args
    inp = case_input(a, s, trades)
    return name, a, s, inp, golden(inp)


def build_goldens():
    from multiprocessing import Pool
    jobs = [(a, s, name, trades) for a, s, sets in cases() for name, trades in sets.items()]
    with Pool(6) as p:
        res = p.map(_gold, jobs, chunksize=1)
    (HERE.parent / "ore" / "W4C_GOLDEN_RAW.json").write_text(json.dumps(res, indent=1) + "\n")
    print("goldens", len(res))


if __name__ == "__main__" and "gold" in sys.argv:
    build_goldens()


def ore_samples(run):
    """{netting set: {time: [deflated NPV per sample]}} from ORE's netcube."""
    import csv
    from datetime import date
    from collections import defaultdict
    vals = defaultdict(lambda: defaultdict(dict))
    for row in csv.reader(open(ORE / f"run{run}" / "Output" / "netcube.csv")):
        if row[0].startswith("#"):
            continue
        t = (date.fromisoformat(row[3]) - date(2026, 11, 10)).days / 365
        vals[row[0]][round(t, 9)][int(row[4])] = float(row[6])
    return vals


def check_case(gold, inp, samples):
    """Every output within 3 MC standard errors of ORE (PFE by the empirical CDF at the golden quantile)."""
    ts = inp["exposure_times"]
    X = [[samples[round(t, 9)][k] for k in sorted(samples[round(t, 9)])] for t in ts]
    n = len(X[0])
    zs = []

    def z_mean(vals, g):
        m = sum(vals) / n
        se = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1) / n)
        return (m - g) / se if se > 0 else (0.0 if abs(m - g) < 1e-6 * max(1, abs(g)) else 99.0)
    for i in range(len(ts)):
        zs.append(("ee", ts[i], z_mean([max(v, 0) for v in X[i]], gold["discounted_ee"][i])))
        zs.append(("ene", ts[i], z_mean([min(v, 0) for v in X[i]], gold["discounted_ene"][i])))
        for q, key in zip(Q, ("pfe_95", "pfe_99")):
            y = gold[key][i]
            F = sum(1 for v in X[i] if max(v, 0) <= y * (1 + 1e-12)) / n
            se = math.sqrt(q * (1 - q) / n)
            zs.append((key, ts[i], (F - q) / se if y > 0 else min(0.0, (F - q) / se)))
    t0 = [0.0] + ts
    per_epe = [sum(max(X[i][p], 0) * (t0[i + 1] - t0[i]) for i in range(len(ts))) / ts[-1] for p in range(n)]
    per_cva = [sum((1 - REC) * max(X[i][p], 0) * (math.exp(-HAZ * t0[i]) - math.exp(-HAZ * t0[i + 1])) for i in range(len(ts))) for p in range(n)]
    zs.append(("epe", None, z_mean(per_epe, gold["epe"])))
    zs.append(("cva", None, z_mean(per_cva, gold["cva"])))
    worst = max(zs, key=lambda r: abs(r[2]))
    # G-42, registered before any ORE result was read: Bonferroni over the case's m checks at a family-wise 1%
    from statistics import NormalDist
    zc = max(3.0, NormalDist().inv_cdf(1 - 0.01 / (2 * len(zs))))
    return all(abs(r[2]) <= zc for r in zs), worst, len(zs)


def write_suite():
    sys.path.insert(0, str(HERE))
    from qf_oracle import common
    from qf_oracle.common import Suite
    raw = json.loads((ORE / "W4C_GOLDEN_RAW.json").read_text())
    s = Suite("expsim_g", "specifications/06-risk/xva-exposure-portfolio.md", "oracle/python/gen_stage_g_w4c.py")
    runs = {}
    report, n_out = [], 0
    params = [(a, sg) for a, sg, _ in cases()]
    for name, a, sg, inp, gold in raw:
        r = params.index((a, sg))
        if r not in runs:
            runs[r] = ore_samples(r)
        ok, worst, nchk = check_case(gold, inp, runs[r][name])
        n_out += ok
        report.append({"case": name, "run": r, "mean_reversion": a, "sigma": sg, "counted": ok, "checks": nchk,
                       "worst": {"output": worst[0], "time": worst[1], "z": worst[2]}})
        s.add(OP, inp, gold, cls="root_finding", verified=["mpmath-25-quadrature"] + (["ore-1.8.17-3se"] if ok else []),
              tags=["xva", "exposure", "portfolio" if name.startswith("P") else "single", "synthetic"],
              limit={"absolute": 1e-4, "relative": 1e-8, "reason": "quadrature and quantile root to 1e-11 relative"},
              description=f"HW a={a} sigma={sg}, netting set {name} ({len(inp['trades'])} trade(s)), {len(inp['exposure_times'])} reset dates")
    e = case_input(0.05, 0.01, [swap(5, "PAY", 0.03)])
    errs = [(dict(e, trades=[]), "E_INPUT", "no trades"),
            (dict(e, trades=[swap(5, "PAY", 0.03), dict(swap(5, "PAY", 0.03), payment_times=[0.5, 1.5, 2.5])]), "E_INPUT", "reset dates not common to the set"),
            (dict(e, exposure_times=[1.5]), "E_INPUT", "exposure time not a reset date"),
            (dict(e, pfe_quantiles=[1.0]), "E_DOMAIN", "quantile 1"),
            (dict(e, sigma=0.0), "E_DOMAIN", "sigma 0"),
            (dict(e, hazard_rate=-0.01), "E_DOMAIN", "negative hazard")]
    for inp, code, d in errs:
        s.add(OP, inp, error=code, cls="date_and_convention", tags=["invalid", "xva", "synthetic"], description=d)
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_g"
    s.compact = True
    s.write()
    common.GOLDEN = keep
    (ORE / "ORE_CHECK_4C.json").write_text(json.dumps({"ore": "1.8.17.0 (open-source-risk-engine wheel, WSL Ubuntu)", "samples": 5000,
                                                        "counted": n_out, "total": len(s.cases), "cases": report}, indent=1) + "\n")
    reg = json.loads((HERE.parent / "outside_register_g.json").read_text(encoding="utf-8"))
    reg["expsim_g"] = {"counted": n_out, "total": len(s.cases), "rule": "ORE 1.8.17 simulation (LGM = Hull-White), every output within 3 MC SE (G-42)"}
    (HERE.parent / "outside_register_g.json").write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8")
    print("counted", n_out, "of", len(s.cases))


if __name__ == "__main__" and "suite" in sys.argv:
    write_suite()


# ------------------------------------------------------------------------------------------------ G-42b (registered before its runs)
SEED_B = 20261211
H_SIM = 30 / 365


def eps_p():
    """Bound on ORE's log bond-price error from log-linear re-interpolation of the simulated curve at pillars H_SIM apart:
    a forward jump df inside an interval misprices ln P by at most H_SIM df / 4; doubled for the LGM shift term and the
    index curve (G-42b)."""
    t = [0.0] + CURVE["times"]
    p = [1.0] + CURVE["discount_factors"]
    f = [-(math.log(p[i]) - math.log(p[i - 1])) / (t[i] - t[i - 1]) for i in range(1, len(t))]
    return H_SIM * max(abs(f[i] - f[i - 1]) for i in range(1, len(f))) / 2


def gross_deflated(inp, t):
    """Deflated gross PV at x = 0 of every remaining leg cash flow (notional at the end plus fixed coupons, and the par leg)."""
    cv = Curve(**inp["curve"])
    g = 0
    for sw in inp["trades"]:
        Ts = [x for x in sw["payment_times"] if x > t]
        if not Ts:
            continue
        prev = [t] + Ts[:-1]
        g += sw["notional"] * (float(cv.P(t)) + float(cv.P(Ts[-1])) + sw["fixed_rate"] * sum((T - p) * float(cv.P(T)) for p, T in zip(prev, Ts)))
    return g


def prob_positive(inp, t, sign=1):
    f, sd = deflated_value(inp, t)
    z, _, _ = zeros(f, sd)
    pts = [-12 * sd] + z + [12 * sd]
    return float(sum(mp.ncdf(b / sd) - mp.ncdf(a / sd) for a, b in zip(pts, pts[1:]) if sign * f((a + b) / 2) > 0))


def check_case_b(gold, inp, samples):
    from statistics import NormalDist
    ts = inp["exposure_times"]
    X = [[samples[round(t, 9)][k] for k in sorted(samples[round(t, 9)])] for t in ts]
    n = len(X[0])
    eps = eps_p()
    checks = []  # (name, time, ok or None for not testable)
    raw = []

    def mean_check(vals, g):
        m = sum(vals) / n
        se = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1) / n)
        return m, se, g
    for i, t in enumerate(ts):
        pp, pn = prob_positive(inp, t, 1), prob_positive(inp, t, -1)
        raw.append(("ee", t, mean_check([max(v, 0) for v in X[i]], gold["discounted_ee"][i]) if n * pp >= 3 else None))
        raw.append(("ene", t, mean_check([min(v, 0) for v in X[i]], gold["discounted_ene"][i]) if n * pn >= 3 else None))
        D = eps * gross_deflated(inp, t)
        s = sorted(max(v, 0) for v in X[i])
        for q, key in zip(Q, ("pfe_95", "pfe_99")):
            raw.append((key, t, ("pfe", s, q, gold[key][i], D) if n * (1 - q) >= 3 else None))
    t0 = [0.0] + ts
    raw.append(("epe", None, mean_check([sum(max(X[i][p], 0) * (t0[i + 1] - t0[i]) for i in range(len(ts))) / ts[-1] for p in range(n)], gold["epe"])))
    raw.append(("cva", None, mean_check([sum((1 - REC) * max(X[i][p], 0) * (math.exp(-HAZ * t0[i]) - math.exp(-HAZ * t0[i + 1])) for i in range(len(ts))) for p in range(n)], gold["cva"])))
    m = sum(1 for r in raw if r[2] is not None)
    zc = max(3.0, NormalDist().inv_cdf(1 - 0.01 / (2 * m)))
    worst = (None, None, 0.0)
    for name, t, r in raw:
        if r is None:
            checks.append((name, t, None))
            continue
        if r[0] == "pfe":
            _, s, q, y, D = r
            half = zc * math.sqrt(n * q * (1 - q))
            lo = s[max(0, math.floor(n * q - half) - 1)]
            hi = s[min(n - 1, math.ceil(n * q + half) - 1)]
            ok = lo - D <= y <= hi + D
            checks.append((name, t, ok))
            if not ok:
                worst = (name, t, (y - hi - D) if y > hi + D else (y - lo + D))
        else:
            mm, se, g = r
            z = (mm - g) / se if se > 0 else float("inf")
            ok = abs(z) <= zc
            checks.append((name, t, ok))
            if abs(z) > abs(worst[2]):
                worst = (name, t, z)
    testable = [c for c in checks if c[2] is not None]
    counted = bool(testable) and all(c[2] for c in testable) and any(c[0] == "ee" and c[2] is not None for c in checks)
    return counted, worst, len(testable), len(checks) - len(testable), zc


def write_ore_cases_b(samples=5000):
    sys.path.insert(0, str(ORE))
    import build_case
    for i, (a, s, sets) in enumerate(cases()):
        case = dict(curve=CURVE, mean_reversion=a, sigma=s, samples=samples, seed=SEED_B + i, grid=[float(t) for t in range(1, 21)],
                    netting_sets={k: {"trades": v} for k, v in sets.items()})
        build_case.write(str(ORE / f"runb{i}"), case)
        txt = (ORE / f"runb{i}" / "ore.xml").read_text()
        (ORE / f"runb{i}" / "ore.xml").write_text(txt.replace('<Parameter name="outputPath">Output</Parameter>', f'<Parameter name="outputPath">/home/ashish/ore_out/runb{i}</Parameter>'))
        (ORE / f"runb{i}.json").write_text(json.dumps(case, indent=1) + "\n")


if __name__ == "__main__" and "oreb" in sys.argv:
    write_ore_cases_b()
    print("eps_p", eps_p())
