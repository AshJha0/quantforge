"""Stage K item K-8b: 50-digit oracle values for the xVA extras (CANDIDATE goldens, PENDING implementation).

The operations below are specified (specs PROPOSED) but not implemented in any build, so their goldens cannot sit
in `datasets/golden/` (the conformance runner counts an unimplemented case as a failure, runner.py). This script
writes them as candidate files under `oracle/xva_k8b_candidates/`, in the golden-file shape, with a SHA-256
manifest. The implementation lane moves each file to `datasets/golden/stage_k/` with the operation, and adds the
suite to `tools/outside_shares.py` STAGE_K_ITEMS.

Every value is computed from the spec formulas in mpmath at 50 digits (closed forms; `Phi_2` by adaptive
quadrature of `int phi(x) Phi((b - c x)/r) dx`; derivatives by `mpmath.diff` at raised precision) and rounded
once to binary64. Inputs are binary64 numbers; where a case table writes a formula (`D = exp(-0.03 t)`), the input
is the binary64 rounding of the exact value, written into the case.

Survival convention: proposed ruling KR-296 (`specifications/stage-k-rulings-xva.md`): FCA, FBA, MVA and the
ColVA survival weight all take survival at the START of each bucket. `--convention end` recomputes the cases that
move under the old wording (MVA and ColVA at bucket end) for the ruling's table; it writes nothing.

    python -I oracle/python/gen_stage_k_xva_k8b.py            write oracle/xva_k8b_candidates/
    python -I oracle/python/gen_stage_k_xva_k8b.py --check    regenerate in memory; exit 1 if a file differs
    python -I oracle/python/gen_stage_k_xva_k8b.py --convention end   print the old-convention values
"""
import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import mpmath as mp

mp.mp.dps = 50
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "oracle" / "xva_k8b_candidates"
GEN = "oracle/python/gen_stage_k_xva_k8b.py"
REVIEWER = "none: self-assessment; no second review (owner decision 2026-11-18)"
CONV = {"surv": "start"}  # KR-296 (proposed): survival at the bucket start for FCA, FBA, MVA, ColVA

M = mp.mpf


def f64(x):
    return float(x)


def rnd(x):
    """Round a nested structure of mpf to binary64 (once)."""
    if isinstance(x, dict):
        return {k: rnd(v) for k, v in x.items()}
    if isinstance(x, list):
        return [rnd(v) for v in x]
    if isinstance(x, (bool, str, int)) or x is None:
        return x
    return float(x)


def S(h, t):
    return mp.exp(-M(h) * M(t))


def Phi(x):
    return mp.ncdf(x)


def phi(x):
    return mp.npdf(x)


def Phi_inv(p):
    return mp.sqrt(2) * mp.erfinv(2 * M(p) - 1)


def Phi2(a, b, c):
    """P(X <= a, Y <= b), corr c, by quadrature over x (50 digits)."""
    a, b, c = M(a), M(b), M(c)
    if c == 0:
        return Phi(a) * Phi(b)
    r = mp.sqrt(1 - c * c)
    f = lambda x: phi(x) * Phi((b - c * x) / r)
    lo = M(-40)  # phi(-40) < 1e-340: the tail below is far under 50 digits
    if a <= lo:
        return M(0)
    return mp.quad(f, [lo] + ([a - 10] if a - 10 > lo else []) + [a])


# ------------------------------------------------------------------------------------------------- curves (KR-164)
def spread_T(curve, T):
    """s(T) T: linear in T between pillars, (0, 0) at the origin, flat forward beyond the last pillar."""
    ten = [M(x) for x in curve["tenors"]]
    sT = [M(s) * t for s, t in zip(curve["zero_spreads"], ten)]
    T = M(T)
    if T == 0:
        return M(0)
    xs, ys = [M(0)] + ten, [M(0)] + sT
    if T >= xs[-1]:
        slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        return ys[-1] + slope * (T - xs[-1])
    for k in range(1, len(xs)):
        if T <= xs[k]:
            w = (T - xs[k - 1]) / (xs[k] - xs[k - 1])
            return ys[k - 1] + w * (ys[k] - ys[k - 1])
    raise AssertionError


def forwards(curve, times):
    t = [M(0)] + [M(x) for x in times]
    return [(spread_T(curve, t[i]) - spread_T(curve, t[i - 1])) / (t[i] - t[i - 1]) for i in range(1, len(t))]


# ------------------------------------------------------------------------------------------------- operations
def adjustments(inp):
    """G-41 xva.adjustments.value (as gen_stage_g_w4b.py; survival at bucket start)."""
    t = [M(0)] + [M(x) for x in inp["times"]]
    df = [None] + [M(x) for x in inp["discount_factors"]]
    ee, ene = [M(x) for x in inp["ee"]], [M(x) for x in inp["ene"]]
    hc, rc = M(inp["counterparty"]["hazard_rate"]), M(inp["counterparty"]["recovery"])
    hb, rb = M(inp["own"]["hazard_rate"]), M(inp["own"]["recovery"])
    sb, sl = M(inp["funding"]["borrow_spread"]), M(inp["funding"]["lend_spread"])
    if inp["funding"]["exclude_dva_overlap"]:
        sl = max(sl - hb * (1 - rb), M(0))
    cva = dva = fca = fba = M(0)
    for i in range(1, len(t)):
        dt = t[i] - t[i - 1]
        joint = S(hc, t[i - 1]) * S(hb, t[i - 1])
        cva += (1 - rc) * df[i] * ee[i - 1] * (S(hc, t[i - 1]) - S(hc, t[i])) * S(hb, t[i - 1])
        dva += (1 - rb) * df[i] * (-ene[i - 1]) * (S(hb, t[i - 1]) - S(hb, t[i])) * S(hc, t[i - 1])
        fca += sb * df[i] * ee[i - 1] * joint * dt
        fba += sl * df[i] * (-ene[i - 1]) * joint * dt
    return {"cva": cva, "dva": dva, "fca": fca, "fba": fba, "fva": fca - fba}


def funding(inp):
    """xva.funding.asymmetric (KR-164; survival at t_(i-1), KR-296)."""
    t = [M(0)] + [M(x) for x in inp["times"]]
    df = [M(x) for x in inp["discount_factors"]]
    ee, ene = [M(x) for x in inp["ee"]], [M(x) for x in inp["ene"]]
    hc, hb = M(inp["counterparty"]["hazard_rate"]), M(inp["own"]["hazard_rate"])
    rb = M(inp["own"]["recovery"])
    fb = forwards(inp["borrow_curve"], inp["times"])
    fl = forwards(inp["lend_curve"], inp["times"])
    if inp.get("exclude_dva_overlap", False):
        fl = [max(f - hb * (1 - rb), M(0)) for f in fl]
    fca = fba = M(0)
    for i in range(1, len(t)):
        d = t[i] - t[i - 1]
        w = S(hc, t[i - 1]) * S(hb, t[i - 1]) * df[i - 1] * d
        fca += fb[i - 1] * w * ee[i - 1]
        fba += fl[i - 1] * w * abs(ene[i - 1])
    return {"fca": fca, "fba": fba, "fva": fca - fba, "forward_borrow": fb, "forward_lend": fl}


def im_project(spec):
    m = spec["method"]
    if m == "GIVEN":
        return {"expected_im": [M(x) for x in spec["profile"]]}
    if m == "NORMAL_MPOR":
        z = Phi_inv(spec.get("quantile", 0.99))
        k = mp.sqrt(M(spec["mpor_days"]) / M(spec.get("days_per_year", 250)))
        return {"expected_im": [z * M(s) * k for s in spec["stdev"]]}
    if m == "REGRESSION":
        x = [M(v) for v in spec["regressor"]]
        X = [M(v) for v in spec["increment"]]
        n = spec["order"]
        A = mp.matrix([[xi ** j for j in range(n + 1)] for xi in x])
        y = mp.matrix([v * v for v in X])
        beta = mp.lu_solve(A.T * A, A.T * y)
        mean = sum(X) / len(X)
        fit = [sum(beta[j] * xi ** j for j in range(n + 1)) for xi in x]
        z = Phi_inv(spec.get("quantile", 0.99))
        im = [z * mp.sqrt(max(f - mean * mean, M(0))) for f in fit]
        return {"im": im, "expected_im": sum(im) / len(im)}
    raise ValueError(m)


def mva(inp):
    """xva.mva.value (KR-165); survival at the bucket start under KR-296, at the end under the old wording."""
    t = [M(0)] + [M(x) for x in inp["times"]]
    df = [M(x) for x in inp["discount_factors"]]
    e = inp["expected_im"]
    im = [M(x) for x in e] if isinstance(e, list) else im_project(e)["expected_im"]
    if "borrow_curve" in inp:
        fb = forwards(inp["borrow_curve"], inp["times"])
    else:
        fb = [M(inp["borrow_spread"])] * len(df)
    sI = M(inp["im_spread"])
    hc, hb = M(inp["counterparty"]["hazard_rate"]), M(inp["own"]["hazard_rate"])
    terms = []
    for i in range(1, len(t)):
        ts = t[i - 1] if CONV["surv"] == "start" else t[i]
        terms.append((fb[i - 1] - sI) * (t[i] - t[i - 1]) * S(hc, ts) * S(hb, ts) * df[i - 1] * im[i - 1])
    out = {"mva": sum(terms), "terms": terms}
    if not isinstance(e, list):
        out["expected_im"] = im
    return out


def colva(inp):
    """xva.colva.value; W_i at the bucket start t_i under KR-296 (old wording: t_(i+1))."""
    t = [M(x) for x in inp["times"]]
    n = len(t) - 1
    df = [M(x) for x in inp["discount_factors"]]
    C = [M(x) for x in inp["collateral"]]
    sp = inp["spread"]
    sp = [M(sp)] * n if not isinstance(sp, list) else [M(x) for x in sp]
    surv = inp.get("survival", "NONE")

    def W(i):
        if surv == "NONE":
            return M(1)
        h = M(inp["counterparty"]["hazard_rate"]) + M(inp["own"]["hazard_rate"])
        return mp.exp(-h * (t[i] if CONV["surv"] == "start" else t[i + 1]))
    terms = [-C[i] * sp[i] * (t[i + 1] - t[i]) * df[i] * W(i) for i in range(n)]
    out = {"colva": sum(terms), "terms": terms}
    if "overnight_rates" in inp:
        r = [M(x) for x in inp["overnight_rates"]]
        out["collateral_floor"] = sum(-C[i] * max(-r[i], M(0)) * (t[i + 1] - t[i]) * df[i] * W(i) for i in range(n))
    return out


def g40_paths(inp, ns="NS1"):
    """G-40 held collateral per path (C_i = K_(max(i-l,0))) and netted values."""
    tr = [x for x in inp["trades"] if x["netting_set"] == ns]
    P, n = len(tr[0]["values"]), len(inp["times"])
    V = [[sum(M(x["values"][p][i]) for x in tr) for i in range(n)] for p in range(P)]
    csa = inp["csa"][ns]
    Hr, Hp = M(csa["threshold_receive"]), M(csa["threshold_post"])
    mta, ia, lag = M(csa["minimum_transfer_amount"]), M(csa.get("independent_amount", 0)), csa["mpor_steps"]
    T = lambda v: max(v - Hr, M(0)) - max(-v - Hp, M(0)) + ia
    C = []
    for p in range(P):
        K = [T(V[p][0])]
        for j in range(1, n):
            tj = T(V[p][j])
            K.append(tj if abs(tj - K[-1]) >= mta else K[-1])
        C.append([K[max(i - lag, 0)] for i in range(n)])
    return V, C, lag


def exposure_stats(times, E, N, q):
    P, n = len(E), len(times)
    t = [M(x) for x in times]
    ee = [sum(E[p][i] for p in range(P)) / P for i in range(n)]
    ene = [sum(N[p][i] for p in range(P)) / P for i in range(n)]
    k = math.ceil(q * P)
    pfe = [sorted(E[p][i] for p in range(P))[k - 1] for i in range(n)]
    epe = sum(ee[i] * (t[i] - t[i - 1]) for i in range(1, n)) / (t[-1] - t[0])
    eee = [ee[0]]
    for i in range(1, n):
        eee.append(max(eee[-1], ee[i]))
    within = [i for i in range(1, n) if t[i] - t[0] <= 1]
    eff = sum(eee[i] * (t[i] - t[i - 1]) for i in within) / (t[within[-1]] - t[0])
    return {"ee": ee, "ene": ene, "pfe": pfe, "epe": epe, "effective_epe": eff}


def closeout_paths(inp):
    """xva.exposure.closeout (KR-170) for netting set NS1 with an IM profile."""
    V, C, lag = g40_paths(inp)
    n = len(inp["times"])
    imr = [M(x) for x in inp.get("im_received", [0] * n)]
    imp = [M(x) for x in inp.get("im_posted", [0] * n)]
    IMr = [imr[max(i - lag, 0)] for i in range(n)]
    IMp = [imp[max(i - lag, 0)] for i in range(n)]
    E = [[max(V[p][i] - C[p][i] - IMr[i], M(0)) for i in range(n)] for p in range(len(V))]
    N = [[min(V[p][i] - C[p][i] + IMp[i], M(0)) for i in range(n)] for p in range(len(V))]
    E0 = [[max(V[p][i] - C[p][i], M(0)) for i in range(n)] for p in range(len(V))]
    out = exposure_stats(inp["times"], E, N, inp["pfe_quantile"])
    out["ee_no_im"] = exposure_stats(inp["times"], E0, N, inp["pfe_quantile"])["ee"]
    return {"netting_sets": {"NS1": out}}


def colva_paths(inp):
    """xva.colva.value path form: C_i = path mean of G-40 held collateral at t_0 .. t_(n-1)."""
    V, C, _ = g40_paths(inp)
    n = len(inp["times"]) - 1
    prof = [sum(C[p][i] for p in range(len(C))) / len(C) for i in range(n)]
    sub = {k: inp[k] for k in ("times", "discount_factors", "spread")}
    sub["collateral"] = prof
    out = colva(sub)
    out["collateral_profile"] = prof
    return out


def closeout_normal(inp):
    s = M(inp["sigma"]) * mp.sqrt(M(inp["mpor_days"]) / M(inp.get("days_per_year", 250)))
    v0, H = M(inp["v0"]), M(inp["threshold_receive"])
    vm = max(v0 - H, M(0))
    im = Phi_inv(inp["im_quantile"]) * s if "im_quantile" in inp else M(inp["im"])
    m = v0 - vm - im
    return {"s": s, "vm": vm, "im": im, "ee": m * Phi(m / s) + s * phi(m / s)}


def mpor_days(inp):
    F = 5 if inp["repo_only"] else 10
    if inp["max_trades_last_quarter"] > 5000 or inp["illiquid"]:
        F = 20
    if inp["long_disputes_last_two_quarters"] > 2:
        F = 2 * F
    out = {"floor_days": F + inp["remargin_days"] - 1}
    if "model_mpor_days" in inp:
        out["mpor_days"] = max(inp["model_mpor_days"], out["floor_days"])
        out["binding"] = out["floor_days"] > inp["model_mpor_days"]
    return out


def stressed(inp):
    g = [M(x) for x in inp["grid"]]
    alpha = M(inp.get("alpha", 1.4))
    sets, kc, ks = {}, M(0), M(0)
    for ns in inp["netting_sets"]:
        mat = ns.get("maturity")
        Ts = M(mat) if (mat is not None and M(mat) < 1) else M(1)
        r = {}
        for cal in ("current", "stressed"):
            ee = [M(x) for x in ns[f"ee_{cal}"]]
            eee = [ee[0]]
            for k in range(1, len(ee)):
                eee.append(max(eee[-1], ee[k]))
            eepe = sum(eee[k] * (g[k] - g[k - 1]) for k in range(1, len(g)) if g[k] <= Ts) / Ts
            r[f"eee_{cal}"], r[f"eepe_{cal}"], r[f"ead_{cal}"] = eee, eepe, alpha * eepe
        w = M(ns["capital_weight"])
        kc += w * r["ead_current"]
        ks += w * r["ead_stressed"]
        sets[ns["id"]] = r
    cal = "stressed" if ks > kc else "current"
    for r in sets.values():
        r["ead_used"] = r[f"ead_{cal}"]
    return {"netting_sets": sets, "k_current": kc, "k_stressed": ks, "calibration": cal}


def replay(base, ten, bp, scale=1):
    out = []
    for T in base:
        T = M(T)
        if T <= ten[0]:
            v = M(bp[0])
        elif T >= ten[-1]:
            v = M(bp[-1])
        else:
            k = next(j for j in range(1, len(ten)) if T <= ten[j])
            w = (T - M(ten[k - 1])) / (M(ten[k]) - M(ten[k - 1]))
            v = M(bp[k - 1]) + w * (M(bp[k]) - M(bp[k - 1]))
        out.append(M(scale) * v)
    return out


def shocked_curve(inp):
    sc = inp["scenario"]
    ap = replay(inp["curve"]["tenors"], sc["tenors"], sc["shift_bp"], inp.get("scale", 1))
    z = [M(zj) + a / 10000 for zj, a in zip(inp["curve"]["zero_rates"], ap)]
    return {"applied_bp": ap, "shocked_zero_rates": z,
            "shocked_discount_factors": [mp.exp(-zj * M(T)) for zj, T in zip(z, inp["curve"]["tenors"])]}


def wwr(inp, rho=None):
    rho = M(inp["rho"]) if rho is None else M(rho)
    c, R = -rho, M(inp["recovery"])
    r = mp.sqrt(1 - c * c)
    times = [M(x) for x in inp["times"]]
    if "pd_at_times" in inp:
        pd = [M(0)] + [M(x) for x in inp["pd_at_times"]]
    else:
        pd = [M(0)] + [1 - mp.exp(-M(inp["hazard_rate"]) * t) for t in times]
    beta = [None] + [Phi_inv(p) for p in pd[1:]]

    def G(mu, s, b):
        if b is None:
            return M(0)
        a = -mu / s
        P = Phi(b) - Phi2(a, b, c)
        EZ = phi(a) * Phi((b - c * a) / r) - c * phi(b) * Phi((c * b - a) / r)
        return mu * P + s * EZ
    terms, fac = [], []
    for i in range(1, len(pd)):
        mu, s, D = M(inp["mean"][i - 1]), M(inp["stdev"][i - 1]), M(inp["discount_factors"][i - 1])
        dG = G(mu, s, beta[i]) - G(mu, s, beta[i - 1])
        EE = mu * Phi(mu / s) + s * phi(mu / s)
        terms.append((1 - R) * D * dG)
        fac.append(dG / (EE * (pd[i] - pd[i - 1])))
    return {"cva": sum(terms), "bucket_terms": terms, "wwr_factor": fac}


def wwr_full(inp):
    out = wwr(inp)
    out["cva_independent"] = wwr(inp, rho=0)["cva"]
    return out


def portfolio_cva(inp):
    """xva.exposure.portfolio_hw CVA on a fixed exact EE (the expsim_g golden's discounted_ee)."""
    t = [M(0)] + [M(x) for x in inp["exposure_times"]]
    if "discounted_ee" in inp:
        dee = [M(x) for x in inp["discounted_ee"]]
    else:  # the real operation's inputs: the exact EE is the matching expsim_g golden's (mpmath-25 quadrature)
        key = {k: v for k, v in inp.items() if k not in ("hazard_rate", "recovery")}
        hit = [c for c in EXPSIM.values() if {k: v for k, v in c["inputs"].items() if k not in ("hazard_rate", "recovery")} == key]
        dee = [M(x) for x in hit[0]["expected"]["outputs"]["discounted_ee"]]
    h, R = M(inp["hazard_rate"]), M(inp["recovery"])
    return {"cva": (1 - R) * sum(dee[i - 1] * (S(h, t[i - 1]) - S(h, t[i])) for i in range(1, len(t)))}


OPS = {"xva.adjustments.value": adjustments, "xva.funding.asymmetric": funding, "xva.mva.value": mva,
       "xva.colva.value": lambda i: colva_paths(i) if "trades" in i else colva(i),
       "xva.wwr.cva_gaussian_copula": wwr_full, "xva.exposure.closeout_normal": closeout_normal,
       "xva.exposure.portfolio_hw": portfolio_cva}


# ------------------------------------------------------------------------------------------------- AAD (KR-161)
def get_path(d, path):
    for part in path.replace("]", "").replace("[", ".").split("."):
        d = d[int(part)] if part.isdigit() else d[part]
    return d


def set_path(d, path, v):
    parts = path.replace("]", "").replace("[", ".").split(".")
    for part in parts[:-1]:
        d = d[int(part)] if part.isdigit() else d[part]
    last = parts[-1]
    if last.isdigit():
        d[int(last)] = v
    else:
        d[last] = v


def aad(op, inputs, wrt, outs):
    fn = OPS[op]
    grad = {o: {} for o in outs}
    for p in wrt:
        x0 = M(get_path(inputs, p))
        for o in outs:
            def g(x, o=o, p=p):
                ii = copy.deepcopy(inputs)
                set_path(ii, p, x)
                return fn(ii)[o]
            with mp.workdps(70):
                grad[o][p] = +mp.diff(g, x0)
    val = fn(inputs)
    return {**{o: val[o] for o in outs}, "gradient": grad}


# ------------------------------------------------------------------------------------------------- inputs
def b64(x):
    return float(x)


G_ADJ = json.loads((ROOT / "datasets/golden/stage_g/xvaadj_g.json").read_text(encoding="utf-8"))["cases"]
XVAADJ = {c["case_id"]: c["inputs"] for c in G_ADJ}
COLLEXP = {c["case_id"]: c["inputs"] for c in
           json.loads((ROOT / "datasets/golden/stage_g/collexp_g.json").read_text(encoding="utf-8"))["cases"]}
EXPSIM = {c["case_id"]: c for c in
          json.loads((ROOT / "datasets/golden/stage_g/expsim_g.json").read_text(encoding="utf-8"))["cases"]}
SHOCKS = {s["name"]: s for s in json.loads((ROOT / "datasets/scenarios/us_treasury_shocks.json").read_text(encoding="utf-8"))["scenarios"]}

g1 = XVAADJ["xvaadj_g-0001"]
CP = {"hazard_rate": 0.02, "recovery": 0.4}
OWN = {"hazard_rate": 0.01, "recovery": 0.4}


def fva_base():
    return {"times": [1.0, 2.0], "discount_factors": [b64(mp.exp(-M(0.03) * t)) for t in (1, 2)],
            "ee": [10.0, 6.0], "ene": [-4.0, -8.0], "counterparty": dict(CP), "own": dict(OWN),
            "borrow_curve": {"tenors": [1.0, 2.0], "zero_spreads": [0.010, 0.012]},
            "lend_curve": {"tenors": [1.0, 2.0], "zero_spreads": [0.004, 0.005]}}


def fva_g(**kw):
    d = {k: copy.deepcopy(g1[k]) for k in ("times", "discount_factors", "ee", "ene", "counterparty", "own")}
    d.update(kw)
    return d


BORROW4 = {"tenors": [0.75, 3.0], "zero_spreads": [0.009, 0.015]}
FLAT8 = {"tenors": [1.0], "zero_spreads": [0.008]}


def cases():
    C = []  # (suite, case_id, operation, inputs, description, tolerance, outputs-filter)
    T12 = {"absolute": 1e-12, "relative": 1e-12, "reason": "spec Acceptance A1: exact arithmetic on given inputs"}
    # ---- funding
    C.append(("fva_k", "fva_k-0001", "xva.funding.asymmetric", fva_base(), "two dates, two curves", T12))
    d = fva_base(); d["own"]["recovery"] = 0.6; d["exclude_dva_overlap"] = True
    C.append(("fva_k", "fva_k-0002", "xva.funding.asymmetric", d, "DVA overlap removed", T12))
    C.append(("fva_k", "fva_k-0003", "xva.funding.asymmetric",
              fva_g(borrow_curve=copy.deepcopy(FLAT8), lend_curve=copy.deepcopy(FLAT8)), "flat curves = G-41", T12))
    lend5 = {"tenors": [5.0], "zero_spreads": [0.004]}
    C.append(("fva_k", "fva_k-0004", "xva.funding.asymmetric",
              fva_g(borrow_curve=copy.deepcopy(BORROW4), lend_curve=copy.deepcopy(lend5)), "interpolation inside buckets", T12))
    C.append(("fva_k", "fva_k-0005", "xva.funding.asymmetric",
              fva_g(borrow_curve=copy.deepcopy(BORROW4), lend_curve={"tenors": [1.0, 2.0], "zero_spreads": [0.002, 0.009]},
                    exclude_dva_overlap=True), "overlap binding in two buckets of four", T12))
    C.append(("fva_k", "fva_k-0006", "xva.funding.asymmetric",
              fva_g(ee=[0.0, 0.0, 0.0, 0.0], borrow_curve=copy.deepcopy(BORROW4), lend_curve=copy.deepcopy(lend5)),
              "no positive exposure: FCA 0", T12))
    # ---- MVA
    mb = {"times": [0.5, 1.0, 1.5, 2.0], "discount_factors": [0.985, 0.97, 0.955, 0.94],
          "counterparty": {"hazard_rate": 0.02}, "own": {"hazard_rate": 0.01}, "borrow_spread": 0.008, "im_spread": 0.001}
    C.append(("mva_k", "mva_k-0001", "xva.mva.value", {**copy.deepcopy(mb), "expected_im": [100.0, 90.0, 70.0, 40.0]}, "given IM", T12))
    C.append(("mva_k", "mva_k-0002", "xva.mva.value", {**copy.deepcopy(mb), "expected_im": {
        "method": "NORMAL_MPOR", "stdev": [1000.0, 1200.0, 900.0, 500.0], "mpor_days": 10, "quantile": 0.99}}, "normal MPoR IM", T12))
    T10 = {"absolute": 1e-12, "relative": 1e-10, "reason": "spec A1: regression cases (least squares conditioning)"}
    reg = {"method": "REGRESSION", "regressor": [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5], "increment": [3.0, -2.0, 1.0, -1.0, 2.0, -4.0],
           "order": 1, "quantile": 0.99}
    C.append(("mva_k", "mva_k-0003", "xva.im.project", reg, "regression IM, order 1", T10))
    C.append(("mva_k", "mva_k-0004", "xva.im.project", {**reg, "order": 0}, "regression IM, order 0", T10))
    d = {**copy.deepcopy(mb), "expected_im": [100.0, 90.0, 70.0, 40.0], "borrow_curve": copy.deepcopy(BORROW4)}
    del d["borrow_spread"]
    C.append(("mva_k", "mva_k-0005", "xva.mva.value", d, "given IM, borrow curve", T12))
    # ---- ColVA
    cb = {"times": [0.0, 0.5, 1.0, 1.5, 2.0], "discount_factors": [b64(mp.exp(-M(0.03) * M(t))) for t in (0.5, 1.0, 1.5, 2.0)]}
    C.append(("colva_k", "colva_k-0001", "xva.colva.value", {**cb, "collateral": [100.0, 80.0, 50.0, 20.0], "spread": 0.001}, "constant spread", T12))
    C.append(("colva_k", "colva_k-0002", "xva.colva.value", {**cb, "collateral": [100.0, 80.0, 50.0, 20.0], "spread": 0.001,
              "survival": "BOTH", "counterparty": {"hazard_rate": 0.02}, "own": {"hazard_rate": 0.01}}, "with survival", T12))
    C.append(("colva_k", "colva_k-0003", "xva.colva.value", {**cb, "collateral": [100.0, 80.0, 50.0, 20.0], "spread": 0.001,
              "overnight_rates": [-0.005, 0.0, 0.01, -0.002]}, "floor output", T12))
    C.append(("colva_k", "colva_k-0004", "xva.colva.value", {**cb, "collateral": [100.0, -40.0, -60.0, 20.0],
              "spread": [0.001, 0.001, -0.0005, -0.0005]}, "mixed signs", T12))
    C.append(("colva_k", "colva_k-0005", "xva.colva.value", {**cb, "collateral": [100.0, 80.0, 50.0, 20.0],
              "spread": [0.002, 0.0015, 0.001, 0.0005], "survival": "BOTH", "counterparty": {"hazard_rate": 0.03},
              "own": {"hazard_rate": 0.015}}, "time-dependent spread with survival", T12))
    ce = copy.deepcopy(COLLEXP["collexp_g-0004"])
    d = {"times": ce["times"], "trades": ce["trades"], "csa": ce["csa"], "spread": 0.001,
         "discount_factors": [b64(mp.exp(-M(0.03) * M(t))) for t in ce["times"][1:]]}
    C.append(("colva_k", "colva_k-0006", "xva.colva.value", d, "path form on collexp_g-0004 (simulated)", T12))
    # ---- stressed
    A = {"id": "A", "ee_current": [10.0, 14.0, 12.0, 15.0, 11.0], "ee_stressed": [10.0, 20.0, 24.0, 22.0, 18.0], "capital_weight": 0.08}
    B = {"id": "B", "ee_current": [20.0, 18.0, 22.0, 19.0, 16.0], "ee_stressed": [20.0, 16.0, 15.0, 14.0, 12.0], "capital_weight": 0.04}
    grid = [0.0, 0.25, 0.5, 0.75, 1.0]
    C.append(("str_k", "str_k-0001", "xva.exposure.stressed_eepe", {"grid": grid, "netting_sets": [A, B]}, "portfolio uses stressed", T12))
    C.append(("str_k", "str_k-0002", "xva.exposure.stressed_eepe", {"grid": grid, "netting_sets": [{**A, "capital_weight": 0.004}, B]}, "choice flips", T12))
    C.append(("str_k", "str_k-0003", "xva.exposure.stressed_eepe", {"grid": grid, "netting_sets": [
        {"id": "A", "ee_current": [5.0, 6.0, 7.0, 8.0, 9.0], "ee_stressed": [5.0, 6.0, 7.0, 8.0, 9.0], "capital_weight": 0.08}]}, "tie: current", T12))
    C.append(("str_k", "str_k-0004", "xva.exposure.stressed_eepe", {"grid": grid, "netting_sets": [
        {"id": "A", "ee_current": [10.0, 12.0, 9.0, 0.0, 0.0], "ee_stressed": [10.0, 15.0, 11.0, 0.0, 0.0], "capital_weight": 0.08,
         "maturity": 0.5}]}, "horizon 0.5", T12))
    C.append(("str_k", "str_k-0005", "xva.exposure.stressed_eepe", {"grid": grid, "netting_sets": [A, B], "alpha": 1.25,
              "own_alpha": True}, "own alpha 1.25", T12))
    gm = [k / 12 for k in range(13)]
    C.append(("str_k", "str_k-0006", "xva.exposure.stressed_eepe", {"grid": gm, "netting_sets": [
        {"id": "A", "ee_current": [b64(100 * mp.sqrt(M(t))) for t in gm], "ee_stressed": [b64(150 * mp.sqrt(M(t))) for t in gm],
         "capital_weight": 0.08}]}, "monthly grid, sqrt profile", T12))
    # ---- MPoR, close-out
    T9 = {"absolute": 1e-9, "relative": 1e-12, "reason": "spec A1"}
    base = {"repo_only": False, "max_trades_last_quarter": 10, "illiquid": False, "long_disputes_last_two_quarters": 0, "remargin_days": 1}
    for cid, kw in (("0001", {"repo_only": True}), ("0002", {}), ("0003", {"remargin_days": 5}),
                    ("0004", {"max_trades_last_quarter": 6000}), ("0005", {"long_disputes_last_two_quarters": 3}),
                    ("0006", {"illiquid": True, "long_disputes_last_two_quarters": 3, "remargin_days": 3, "model_mpor_days": 15})):
        C.append(("mpor_k", f"mpor_k-{cid}", "xva.mpor.days", {**base, **kw}, "CRE53 floor", T9))
    TN = {"absolute": 1e-9, "relative": 1e-12, "reason": "closed form with Phi and phi"}
    nb = {"v0": 5e6, "sigma": 1e6, "mpor_days": 10, "threshold_receive": 0.0, "im": 0.0}
    for cid, kw in (("0001", {}), ("0002", {"threshold_receive": 1e6}), ("0003", {"v0": 5e5, "threshold_receive": 1e6}),
                    ("0004", {"im_quantile": 0.99}), ("0005", {"threshold_receive": 1e6, "im_quantile": 0.99})):
        d = {**nb, **kw}
        if "im_quantile" in d:
            del d["im"]
        C.append(("cln_k", f"cln_k-{cid}", "xva.exposure.closeout_normal", d, "normal close-out", TN))
    d = copy.deepcopy(COLLEXP["collexp_g-0004"])
    d["im_received"] = [0.0, 0.5, 0.5, 0.5, 0.5]
    C.append(("clp_k", "clp_k-0001", "xva.exposure.closeout", d, "collexp_g-0004 with received IM (simulated)", T12))
    # ---- shocks
    for cid, sc in (("0001", "hikes_2022"), ("0002", "covid_2020")):
        s = SHOCKS[sc]
        C.append(("shk_k", f"shk_k-{cid}", "xva.stress.shocked", {
            "curve": {"tenors": [1.0, 2.0, 5.0, 15.0, 20.0], "zero_rates": [0.03] * 5},
            "scenario": {"tenors": s["tenors"], "shift_bp": s["shift_bp"]}}, f"curve outputs, {sc}", T12))
    # ---- WWR
    TW = {"absolute": 1e-15, "relative": 1e-12, "reason": "spec A1 (special_function; Phi_2 dominates)"}
    one = {"times": [1.0], "discount_factors": [1.0], "stdev": [1.0], "pd_at_times": [0.02], "recovery": 0.0}
    for cid, mu, rho in (("0001", 0.0, 0.5), ("0002", 0.0, 0.0), ("0003", 0.0, -0.5), ("0004", 0.5, 0.3), ("0005", -0.5, 0.3)):
        C.append(("wwr_k", f"wwr_k-{cid}", "xva.wwr.cva_gaussian_copula", {**copy.deepcopy(one), "mean": [mu], "rho": rho}, "single bucket", TW))
    two = lambda mu, rho: {"times": [1.0, 2.0], "discount_factors": [b64(mp.exp(-M(0.03) * t)) for t in (1, 2)],
                           "mean": [mu * 1.0, mu * 2.0], "stdev": [1.0, b64(mp.sqrt(2))], "hazard_rate": 0.02,
                           "recovery": 0.4, "rho": rho}
    for cid, mu, rho in (("0006", 0.0, 0.0), ("0007", 0.0, 0.5), ("0008", 0.0, -0.5), ("0009", 0.2, 0.3)):
        C.append(("wwr_k", f"wwr_k-{cid}", "xva.wwr.cva_gaussian_copula", two(mu, rho), "two buckets", TW))
    tt = [float(k) for k in range(1, 11)]
    C.append(("wwr_k", "wwr_k-0010", "xva.wwr.cva_gaussian_copula", {
        "times": tt, "discount_factors": [b64(mp.exp(-M(0.02) * M(t))) for t in tt],
        "mean": [b64(M(0.05) * M(t) * (10 - M(t))) for t in tt], "stdev": [b64(M(0.3) * mp.sqrt(M(t))) for t in tt],
        "hazard_rate": 0.03, "recovery": 0.4, "rho": 0.4}, "ten annual buckets", TW))
    # ---- AAD (gradients over the case's `wrt` list)
    TA = {"absolute": 1e-12, "relative": 1e-10, "reason": "spec A1/A2: AAD of the operation as computed (KR-161)"}

    def aadc(cid, op, inp, wrt, outs, desc, tol=TA):
        C.append(("aadx_k", cid, "xva.sens.aad", {"operation": op, "inputs": inp, "wrt": wrt, "outputs": outs}, desc, tol))
    n4 = range(4)
    adj_wrt = ([f"discount_factors[{i}]" for i in n4] + [f"ee[{i}]" for i in n4] + [f"ene[{i}]" for i in n4]
               + ["counterparty.hazard_rate", "counterparty.recovery", "own.hazard_rate", "own.recovery",
                  "funding.borrow_spread", "funding.lend_spread"])
    adj_out = ["cva", "dva", "fca", "fba", "fva"]
    aadc("aadx_k-0001", "xva.adjustments.value", copy.deepcopy(XVAADJ["xvaadj_g-0001"]), adj_wrt, adj_out, "G-41 on xvaadj_g-0001")
    aadc("aadx_k-0002", "xva.adjustments.value", copy.deepcopy(XVAADJ["xvaadj_g-0002"]), adj_wrt, adj_out, "G-41 overlap on (xvaadj_g-0002)")
    c5 = [c for c in C if c[1] == "colva_k-0005"][0][3]
    aadc("aadx_k-0003", "xva.colva.value", copy.deepcopy(c5),
         [f"collateral[{i}]" for i in n4] + [f"spread[{i}]" for i in n4] + [f"discount_factors[{i}]" for i in n4]
         + ["counterparty.hazard_rate", "own.hazard_rate"], ["colva"], "ColVA on colva_k-0005")
    f4 = [c for c in C if c[1] == "fva_k-0004"][0][3]
    aadc("aadx_k-0004", "xva.funding.asymmetric", copy.deepcopy(f4),
         [f"discount_factors[{i}]" for i in n4] + [f"ee[{i}]" for i in n4] + [f"ene[{i}]" for i in n4]
         + ["counterparty.hazard_rate", "own.hazard_rate", "own.recovery", "borrow_curve.zero_spreads[0]",
            "borrow_curve.zero_spreads[1]", "lend_curve.zero_spreads[0]"], ["fca", "fba", "fva"], "funding on fva_k-0004")
    m2 = [c for c in C if c[1] == "mva_k-0002"][0][3]
    aadc("aadx_k-0005", "xva.mva.value", copy.deepcopy(m2),
         [f"expected_im.stdev[{i}]" for i in n4] + [f"discount_factors[{i}]" for i in n4]
         + ["borrow_spread", "im_spread", "counterparty.hazard_rate", "own.hazard_rate"], ["mva"], "MVA on mva_k-0002 through sigma")
    w9 = [c for c in C if c[1] == "wwr_k-0009"][0][3]
    aadc("aadx_k-0006", "xva.wwr.cva_gaussian_copula", copy.deepcopy(w9),
         ["rho", "hazard_rate", "mean[0]", "mean[1]", "stdev[0]", "stdev[1]"], ["cva"], "WWR on wwr_k-0009",
         {"absolute": 1e-15, "relative": 1e-10, "reason": "spec A4 (KR-161) on a special_function golden"})
    cl5 = {"v0": 5e6, "sigma": 1e6, "mpor_days": 10, "threshold_receive": 1e6,
           "im": b64(Phi_inv(0.99) * M(1e6) * mp.sqrt(M(10) / 250))}
    aadc("aadx_k-0007", "xva.exposure.closeout_normal", cl5, ["sigma", "im", "v0", "threshold_receive"], ["ee"],
         "close-out on cln_k-0005 with the IM given as a number")
    es = EXPSIM["expsim_g-0003"]
    pin = copy.deepcopy(es["inputs"])
    aadc("aadx_k-0008", "xva.exposure.portfolio_hw", pin, ["hazard_rate", "recovery"], ["cva"],
         "CVA of expsim_g-0003 (S5P); the oracle holds the golden's discounted_ee fixed (KR-162)")
    return C


def evaluate(op, inp):
    if op == "xva.sens.aad":
        return aad(inp["operation"], inp["inputs"], inp["wrt"], inp["outputs"])
    if op == "xva.im.project":
        return im_project(inp)
    if op == "xva.mpor.days":
        return mpor_days(inp)
    if op == "xva.exposure.stressed_eepe":
        return stressed(inp)
    if op == "xva.exposure.closeout":
        return closeout_paths(inp)
    if op == "xva.stress.shocked":
        return shocked_curve(inp)
    return OPS[op](inp)


SPEC = {"fva_k": "xva-funding-asymmetric.md", "mva_k": "xva-mva-im.md", "colva_k": "xva-colva.md",
        "str_k": "xva-stressed-exposure.md", "mpor_k": "xva-mpor-closeout.md", "cln_k": "xva-mpor-closeout.md",
        "clp_k": "xva-mpor-closeout.md", "shk_k": "xva-stress-shocks.md", "wwr_k": "xva-wwr-copula.md",
        "aadx_k": "xva-aad-sensitivities.md"}


def self_checks():
    """Generator checks against released goldens (G-40, G-41, G-42b), before any value is written."""
    for cid in ("xvaadj_g-0001", "xvaadj_g-0002"):
        got = rnd(adjustments(XVAADJ[cid]))
        exp = [c for c in G_ADJ if c["case_id"] == cid][0]["expected"]["outputs"]
        assert all(abs(got[k] - exp[k]) <= 1e-12 * abs(exp[k]) + 1e-12 for k in exp), cid
    ce = COLLEXP["collexp_g-0004"]
    V, C, _ = g40_paths(ce)
    E = [[max(V[p][i] - C[p][i], M(0)) for i in range(len(ce["times"]))] for p in range(len(V))]
    N = [[min(V[p][i] - C[p][i], M(0)) for i in range(len(ce["times"]))] for p in range(len(V))]
    got = rnd(exposure_stats(ce["times"], E, N, ce["pfe_quantile"]))
    exp = [c for c in json.loads((ROOT / "datasets/golden/stage_g/collexp_g.json").read_text(encoding="utf-8"))["cases"]
           if c["case_id"] == "collexp_g-0004"][0]["expected"]["outputs"]["netting_sets"]["NS1"]
    assert got == exp, (got, exp)
    es = EXPSIM["expsim_g-0003"]
    cva = float(portfolio_cva({"exposure_times": es["inputs"]["exposure_times"],
                               "discounted_ee": es["expected"]["outputs"]["discounted_ee"],
                               "hazard_rate": es["inputs"]["hazard_rate"], "recovery": es["inputs"]["recovery"]})["cva"])
    assert abs(cva - es["expected"]["outputs"]["cva"]) <= 1e-12 * cva, cva
    assert abs(Phi2(0.3, -0.7, 0.4) - (Phi2(-0.7, 0.3, 0.4))) < M(10) ** -45


def build():
    self_checks()
    suites = {}
    for suite, cid, op, inp, desc, tol in cases():
        out = rnd(evaluate(op, inp))
        suites.setdefault(suite, []).append({
            "case_id": cid, "operation": op, "inputs": inp, "expected": {"status": "ok", "outputs": out},
            "tolerance_limit": tol, "verified_by": ["mpmath-50"], "tags": ["xva", "k8b", "candidate"],
            "description": desc})
    files = {}
    for suite, cs in suites.items():
        doc = {"schema_version": "1.0", "suite": suite, "status": "PENDING implementation (candidate golden; K-8b specs PROPOSED)",
               "spec": f"specifications/06-risk/{SPEC[suite]}", "generator": GEN, "reviewer": REVIEWER,
               "survival_convention": "KR-296 (proposed): survival at the bucket start for FCA, FBA, MVA, ColVA", "cases": cs}
        files[f"{suite}.json"] = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    man = "".join(f"{hashlib.sha256(t.encode('utf-8')).hexdigest()}  {n}\n" for n, t in sorted(files.items()))
    files["MANIFEST.sha256"] = man
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--convention", choices=("start", "end"), default="start")
    a = ap.parse_args()
    CONV["surv"] = a.convention
    if a.convention == "end":
        for suite, cid, op, inp, desc, tol in cases():
            if suite in ("mva_k", "colva_k") or cid == "aadx_k-0005" or cid == "aadx_k-0003":
                print(cid, json.dumps(rnd(evaluate(op, inp)))[:400])
        return 0
    files = build()
    if a.check:
        bad = [n for n, t in files.items() if not (OUT / n).is_file() or (OUT / n).read_text(encoding="utf-8") != t]
        print("xva k8b candidates:", "OK" if not bad else f"DIFFER {bad}")
        return 1 if bad else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for n, t in files.items():
        (OUT / n).write_text(t, encoding="utf-8", newline="\n")
    print(f"wrote {len(files) - 1} candidate files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
