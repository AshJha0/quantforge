"""Stage G wave 4b: deterministic xVA layer on given paths (rulings G-40 to G-44).

- `xva.exposure.collateralised`: netting sets, CSA (thresholds, MTA, independent amount), margin period of risk as a
  lag in grid steps; outputs EE, ENE, PFE, EPE and effective EPE per netting set.
- `xva.adjustments.value`: CVA, DVA, FCA, FBA (with the DVA overlap rule), MVA and KVA from given profiles.
- `xva.simm.ir_delta`: SIMM-style margin for one currency's IR delta (weights and correlations are inputs).
- `xva.wwr.cva_hw`: wrong-way CVA with the Hull-White (2012) hazard `exp(a(t) + b V(t))`, `a(t)` fitted to the survival curve.

Values: 50-digit mpmath replicas (`a(t)` by findroot to 1e-40). No outside library: not counted (ORE checks the simulated
EE/PFE/CVA slice, not these deterministic formulas).

    cd oracle/python && uv run python -W ignore gen_stage_g_w4b.py
"""
import json
import math
from pathlib import Path

import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_g_w4b.py"
HERE = Path(__file__).resolve().parent
MUTANTS = []
LIM = {"absolute": 1e-9, "relative": 1e-12, "reason": "sums of products of the inputs"}


def caught(name, gap, tol=1e-9):
    assert gap > tol, f"mutant '{name}' is not caught: gap {gap:.3e}"
    MUTANTS.append((name, float(gap)))


# ------------------------------------------------------------------------------------------------ collateralised exposure
def target(v, csa):
    v = mp.mpf(v)
    return max(v - mp.mpf(csa["threshold_receive"]), 0) - max(-v - mp.mpf(csa["threshold_post"]), 0) + mp.mpf(csa.get("independent_amount", 0.0))


def held(path, csa, mut=None):
    """Collateral held at each grid index: calls K_j decided on V(t_j) with the MTA rule, arriving mpor_steps later."""
    K = [target(path[0], csa)]
    for v in path[1:]:
        t = target(v, csa)
        K.append(t if abs(t - K[-1]) >= mp.mpf(csa["minimum_transfer_amount"]) else K[-1])
    lag = 0 if mut == "no_mpor" else csa["mpor_steps"]
    return [K[max(i - lag, 0)] for i in range(len(path))]


def pfe_q(xs, q):
    s = sorted(xs)
    return s[max(0, math.ceil(mp.mpf(q) * len(s)) - 1)]


def coll_exposure(inp, mut=None):
    times = [mp.mpf(t) for t in inp["times"]]
    sets = {}
    for tr in inp["trades"]:
        S = sets.setdefault(tr["netting_set"], None)
        vals = [[mp.mpf(x) for x in row] for row in tr["values"]]
        sets[tr["netting_set"]] = vals if S is None else [[a + b for a, b in zip(r1, r2)] for r1, r2 in zip(S, vals)]
    out, total = {}, [mp.mpf(0)] * len(times)
    if mut == "no_netting":  # every trade its own set
        sets = {f"t{k}": [[mp.mpf(x) for x in row] for row in tr["values"]] for k, tr in enumerate(inp["trades"])}
    for name in sorted(sets):
        V = sets[name]
        csa = inp.get("csa", {}).get(name)
        E, N = [], []
        for path in V:
            C = held(path, csa, mut) if csa else [mp.mpf(0)] * len(path)
            E.append([max(v - c, 0) for v, c in zip(path, C)])
            N.append([min(v - c, 0) for v, c in zip(path, C)])
        n = len(V)
        ee = [sum(E[p][i] for p in range(n)) / n for i in range(len(times))]
        ene = [sum(N[p][i] for p in range(n)) / n for i in range(len(times))]
        pfe = [pfe_q([E[p][i] for p in range(n)], inp["pfe_quantile"]) for i in range(len(times))]
        dt = [times[i] - times[i - 1] for i in range(1, len(times))]
        epe = sum(ee[i] * dt[i - 1] for i in range(1, len(times))) / (times[-1] - times[0])
        eee, run = [], ee[0]
        for x in ee:
            run = max(run, x)
            eee.append(run)
        one = [i for i in range(1, len(times)) if times[i] <= times[0] + 1]
        span = times[one[-1]] - times[0] if one else None
        eepe = sum(eee[i] * dt[i - 1] for i in one) / span if one else eee[0]
        out[name] = {"ee": [float(x) for x in ee], "ene": [float(x) for x in ene], "pfe": [float(x) for x in pfe],
                     "epe": float(epe), "effective_epe": float(eepe)}
        total = [a + b for a, b in zip(total, ee)]
    return {"netting_sets": out, "total_ee": [float(x) for x in total]}


# ------------------------------------------------------------------------------------------------ adjustments
def surv(h, t):
    return mp.exp(-mp.mpf(h) * mp.mpf(t))


def adjustments(inp, mut=None):
    t = [mp.mpf(0)] + [mp.mpf(x) for x in inp["times"]]
    df = [mp.mpf(1)] + [mp.mpf(x) for x in inp["discount_factors"]]
    ee = [mp.mpf(x) for x in inp["ee"]]
    ene = [mp.mpf(x) for x in inp["ene"]]
    hc, rc = inp["counterparty"]["hazard_rate"], mp.mpf(inp["counterparty"]["recovery"])
    hb, rb = inp["own"]["hazard_rate"], mp.mpf(inp["own"]["recovery"])
    sb, sl = mp.mpf(inp["funding"]["borrow_spread"]), mp.mpf(inp["funding"]["lend_spread"])
    if inp["funding"]["exclude_dva_overlap"] and mut != "overlap":
        sl = max(sl - mp.mpf(hb) * (1 - rb), 0)  # FBA keeps only the part of the lending spread that is not own credit
    cva = dva = fca = fba = mva = kva = mp.mpf(0)
    for i in range(1, len(t)):
        dtc = t[i] - t[i - 1]
        joint = surv(hc, t[i - 1]) * surv(hb, t[i - 1])  # first-to-default: both alive at the start of the bucket
        cva += (1 - rc) * df[i] * ee[i - 1] * (surv(hc, t[i - 1]) - surv(hc, t[i])) * surv(hb, t[i - 1])
        dva += (1 - rb) * df[i] * (-ene[i - 1]) * (surv(hb, t[i - 1]) - surv(hb, t[i])) * surv(hc, t[i - 1])
        fca += sb * df[i] * ee[i - 1] * joint * dtc
        fba += sl * df[i] * (-ene[i - 1]) * joint * dtc
        if "im" in inp:
            mva += mp.mpf(inp["im_spread"]) * df[i] * mp.mpf(inp["im"][i - 1]) * joint * dtc
        if "capital" in inp:
            kva += mp.mpf(inp["hurdle_rate"]) * df[i] * mp.mpf(inp["capital"][i - 1]) * joint * dtc
    out = {"cva": float(cva), "dva": float(dva), "fca": float(fca), "fba": float(fba), "fva": float(fca - fba)}
    if "im" in inp:
        out["mva"] = float(mva)
    if "capital" in inp:
        out["kva"] = float(kva)
    return out


# ------------------------------------------------------------------------------------------------ SIMM-style IR delta
def simm(inp, mut=None):
    s = [mp.mpf(x) for x in inp["sensitivities"]]
    rw = [mp.mpf(x) for x in inp["risk_weights"]]
    rho = [[mp.mpf(x) for x in r] for r in inp["correlations"]]
    T = mp.mpf(inp["concentration_threshold"])
    cr = max(1, mp.sqrt(abs(sum(s)) / T))
    ws = [w * x * cr for w, x in zip(rw, s)]
    k2 = sum(ws[k] * ws[l] * (1 if k == l else (0 if mut == "no_corr" else rho[k][l])) for k in range(len(s)) for l in range(len(s)))
    return {"weighted_sensitivities": [float(x) for x in ws], "concentration_factor": float(cr), "margin": float(mp.sqrt(max(k2, 0)))}


# ------------------------------------------------------------------------------------------------ WWR (Hull-White 2012)
def wwr(inp, mut=None):
    t = [mp.mpf(0)] + [mp.mpf(x) for x in inp["times"]]
    V = [[mp.mpf(x) for x in row] for row in inp["values"]]
    df = [mp.mpf(1)] + [mp.mpf(x) for x in inp["discount_factors"]]
    h, R, b = mp.mpf(inp["hazard_rate"]), mp.mpf(inp["recovery"]), mp.mpf(0 if mut == "no_wwr" else inp["wwr_b"])
    n = len(V)
    S = [mp.mpf(1)] * n
    cva, avals = mp.mpf(0), []
    for i in range(1, len(t)):
        dt = t[i] - t[i - 1]
        tgt = mp.exp(-h * t[i])
        f = lambda a: sum(S[p] * mp.exp(-mp.exp(a + b * V[p][i - 1]) * dt) for p in range(n)) / n - tgt  # noqa: E731
        a = mp.findroot(f, mp.log(h), tol=mp.mpf(10) ** -40)
        avals.append(a)
        newS = [S[p] * mp.exp(-mp.exp(a + b * V[p][i - 1]) * dt) for p in range(n)]
        cva += (1 - R) * df[i] * sum(max(V[p][i - 1], 0) * (S[p] - newS[p]) for p in range(n)) / n
        S = newS
    return {"cva": float(cva), "a": [float(x) for x in avals]}


def write(s):
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_g"
    s.write()
    common.GOLDEN = keep


PATHS_A = [[0.0, 3.0, 5.0, 2.0, -1.0], [0.0, -2.0, -4.0, -6.0, -3.0], [0.0, 1.0, 6.0, 9.0, 4.0], [0.0, 0.5, -1.0, 2.5, 7.0]]
PATHS_B = [[0.0, -1.0, 2.0, 1.0, 0.5], [0.0, 2.0, 1.0, -3.0, -2.0], [0.0, -0.5, -2.0, -1.0, 1.0], [0.0, 1.5, 0.0, 2.0, -4.0]]
TIMES = [0.0, 0.25, 0.5, 0.75, 1.0]


def main():
    # ---- collateralised exposure
    s = Suite("collexp_g", "specifications/06-risk/xva-framework.md", G)
    csa0 = dict(threshold_receive=1.0, threshold_post=1.0, minimum_transfer_amount=0.5, mpor_steps=1)
    rows = [
        (dict(times=TIMES, trades=[dict(netting_set="NS1", values=PATHS_A)], pfe_quantile=0.75), "one set, no CSA"),
        (dict(times=TIMES, trades=[dict(netting_set="NS1", values=PATHS_A), dict(netting_set="NS1", values=PATHS_B)], pfe_quantile=0.75), "two trades netted"),
        (dict(times=TIMES, trades=[dict(netting_set="NS1", values=PATHS_A), dict(netting_set="NS2", values=PATHS_B)], pfe_quantile=0.75), "two sets: no netting across"),
        (dict(times=TIMES, trades=[dict(netting_set="NS1", values=PATHS_A)], pfe_quantile=0.75, csa={"NS1": csa0}), "CSA, MPoR 1 step"),
        (dict(times=TIMES, trades=[dict(netting_set="NS1", values=PATHS_A)], pfe_quantile=0.75, csa={"NS1": dict(csa0, mpor_steps=0)}), "CSA, MPoR 0"),
        (dict(times=TIMES, trades=[dict(netting_set="NS1", values=PATHS_A)], pfe_quantile=0.75, csa={"NS1": dict(csa0, minimum_transfer_amount=3.0)}), "large MTA"),
        (dict(times=TIMES, trades=[dict(netting_set="NS1", values=PATHS_A)], pfe_quantile=0.75, csa={"NS1": dict(csa0, threshold_receive=0.0, threshold_post=0.0, minimum_transfer_amount=0.0, mpor_steps=0)}), "zero thresholds, no lag: exposure 0"),
        (dict(times=TIMES, trades=[dict(netting_set="NS1", values=PATHS_A)], pfe_quantile=0.75, csa={"NS1": dict(csa0, independent_amount=2.0)}), "independent amount 2"),
        (dict(times=TIMES, trades=[dict(netting_set="NS1", values=PATHS_A)], pfe_quantile=1.0), "PFE at quantile 1: the path maximum"),
        (dict(times=[0.0, 0.5, 1.0, 1.5, 2.0], trades=[dict(netting_set="NS1", values=PATHS_A)], pfe_quantile=0.5), "two-year grid: effective EPE over the first year"),
    ]
    for inp, d in rows:
        s.add("xva.exposure.collateralised", inp, coll_exposure(inp), verified=["mpmath-50"], tags=["xva", "collateral"], limit=LIM, description=d)
    z = s.cases[6]["expected"]["outputs"]["netting_sets"]["NS1"]
    assert max(z["ee"]) == 0.0
    nt = s.cases[2]["expected"]["outputs"]
    assert all(abs(a - b - c) < 1e-12 for a, b, c in zip(nt["total_ee"], nt["netting_sets"]["NS1"]["ee"], nt["netting_sets"]["NS2"]["ee"]))
    caught("netting ignored", abs(sum(coll_exposure(rows[1][0])["total_ee"]) - sum(coll_exposure(rows[1][0], "no_netting")["total_ee"])))
    caught("MPoR ignored", abs(coll_exposure(rows[3][0])["netting_sets"]["NS1"]["epe"] - coll_exposure(rows[3][0], "no_mpor")["netting_sets"]["NS1"]["epe"]))
    e = rows[3][0]
    errs = [(dict(e, times=[0.0, 0.5, 0.25, 0.75, 1.0]), "E_INPUT", "times not increasing"),
            (dict(e, trades=[dict(netting_set="NS1", values=[[0.0, 1.0]])]), "E_INPUT", "path length differs from times"),
            (dict(e, pfe_quantile=0.0), "E_DOMAIN", "pfe_quantile 0"),
            (dict(e, csa={"NS1": dict(csa0, threshold_receive=-1.0)}), "E_DOMAIN", "negative threshold"),
            (dict(e, csa={"NS1": dict(csa0, mpor_steps=-1)}), "E_DOMAIN", "negative MPoR"),
            (dict(e, csa={"NS9": csa0}), "E_INPUT", "CSA for an unknown netting set"),
            (dict(e, trades=[]), "E_INPUT", "no trades")]
    for inp, code, d in errs:
        s.add("xva.exposure.collateralised", inp, error=code, cls="date_and_convention", tags=["invalid", "xva"], description=d)
    write(s)
    n1 = len(s.cases)

    # ---- adjustments
    s = Suite("xvaadj_g", "specifications/06-risk/xva-framework.md", G)
    base = dict(times=[0.5, 1.0, 1.5, 2.0], discount_factors=[0.985, 0.97, 0.955, 0.94], ee=[120.0, 150.0, 130.0, 80.0],
                ene=[-60.0, -90.0, -100.0, -70.0], counterparty=dict(hazard_rate=0.02, recovery=0.4), own=dict(hazard_rate=0.01, recovery=0.4),
                funding=dict(borrow_spread=0.008, lend_spread=0.008, exclude_dva_overlap=False))
    arows = [(base, "CVA, DVA, FCA, FBA"),
             (dict(base, funding=dict(base["funding"], exclude_dva_overlap=True)), "FBA without the DVA overlap"),
             (dict(base, im=[200.0, 210.0, 190.0, 150.0], im_spread=0.006), "with MVA"),
             (dict(base, capital=[40.0, 42.0, 38.0, 30.0], hurdle_rate=0.10), "with KVA"),
             (dict(base, own=dict(hazard_rate=0.0, recovery=0.4)), "own hazard 0: DVA 0, unilateral CVA"),
             (dict(base, counterparty=dict(hazard_rate=0.05, recovery=0.0)), "zero recovery")]
    for inp, d in arows:
        s.add("xva.adjustments.value", inp, adjustments(inp), verified=["mpmath-50"], tags=["xva", "adjustments"], limit=LIM, description=d)
    assert s.cases[4]["expected"]["outputs"]["dva"] == 0.0
    caught("DVA overlap kept in FBA", abs(adjustments(arows[1][0])["fba"] - adjustments(arows[1][0], "overlap")["fba"]))
    errs = [(dict(base, ee=[1.0]), "E_INPUT", "ee length differs"), (dict(base, counterparty=dict(hazard_rate=-0.01, recovery=0.4)), "E_DOMAIN", "negative hazard"),
            (dict(base, own=dict(hazard_rate=0.01, recovery=1.0)), "E_DOMAIN", "recovery 1"), (dict(base, ee=[-1.0, 150.0, 130.0, 80.0]), "E_DOMAIN", "negative EE"),
            (dict(base, ene=[1.0, -90.0, -100.0, -70.0]), "E_DOMAIN", "positive ENE"), (dict(base, im=[1.0, 1.0, 1.0, 1.0]), "E_INPUT", "im without im_spread")]
    for inp, code, d in errs:
        s.add("xva.adjustments.value", inp, error=code, cls="date_and_convention", tags=["invalid", "xva"], description=d)
    write(s)
    n2 = len(s.cases)

    # ---- SIMM-style
    s = Suite("simm_g", "specifications/06-risk/xva-framework.md", G)
    rw = [109.0, 105.0, 90.0, 71.0, 66.0, 66.0]  # illustrative, regular-volatility-style magnitudes; inputs, not a SIMM table
    lab = [0.25, 1.0, 2.0, 5.0, 10.0, 30.0]
    corr = [[1.0 if i == j else round(math.exp(-0.3 * abs(math.log(lab[i] / lab[j]))), 6) for j in range(6)] for i in range(6)]
    srows = [(dict(sensitivities=[1000.0, -500.0, 2500.0, 4000.0, -1200.0, 300.0], risk_weights=rw, correlations=corr, concentration_threshold=1e9), "mixed signs, below concentration"),
             (dict(sensitivities=[0.0, 0.0, 10000.0, 0.0, 0.0, 0.0], risk_weights=rw, correlations=corr, concentration_threshold=1e9), "one bucket: margin = RW x s"),
             (dict(sensitivities=[1e6, 1e6, 1e6, 1e6, 1e6, 1e6], risk_weights=rw, correlations=corr, concentration_threshold=1e6), "concentration factor sqrt(6)"),
             (dict(sensitivities=[1000.0, -1000.0, 0.0, 0.0, 0.0, 0.0], risk_weights=[100.0, 100.0, 0, 0, 0, 0], correlations=[[1.0] * 6 for _ in range(6)], concentration_threshold=1e9), "perfect correlation hedge: margin 0")]
    for inp, d in srows:
        s.add("xva.simm.ir_delta", inp, simm(inp), verified=["mpmath-50"], tags=["xva", "simm"], limit=LIM, description=d)
    assert abs(s.cases[1]["expected"]["outputs"]["margin"] - 900000.0) < 1e-6
    caught("tenor correlation ignored", abs(simm(srows[0][0])["margin"] - simm(srows[0][0], "no_corr")["margin"]))
    errs = [(dict(srows[0][0], risk_weights=rw[:5]), "E_INPUT", "length mismatch"), (dict(srows[0][0], concentration_threshold=0.0), "E_DOMAIN", "threshold 0"),
            (dict(srows[0][0], correlations=[[1.0, 1.5] + [0.0] * 4] + corr[1:]), "E_DOMAIN", "correlation above 1"),
            (dict(srows[0][0], risk_weights=[-1.0] + rw[1:]), "E_DOMAIN", "negative risk weight")]
    for inp, code, d in errs:
        s.add("xva.simm.ir_delta", inp, error=code, cls="date_and_convention", tags=["invalid", "xva"], description=d)
    write(s)
    n3 = len(s.cases)

    # ---- WWR
    s = Suite("wwr_g", "specifications/06-risk/xva-framework.md", G)
    W = [[3.0, 5.0, 2.0, -1.0], [-2.0, -4.0, -6.0, -3.0], [1.0, 6.0, 9.0, 4.0], [0.5, -1.0, 2.5, 7.0]]
    wbase = dict(times=[0.25, 0.5, 0.75, 1.0], values=W, discount_factors=[0.995, 0.99, 0.985, 0.98], hazard_rate=0.03, recovery=0.4, wwr_b=0.0)
    wrows = [(wbase, "b = 0: independent CVA"), (dict(wbase, wwr_b=0.1), "wrong-way b = 0.1"), (dict(wbase, wwr_b=0.3), "wrong-way b = 0.3"),
             (dict(wbase, wwr_b=-0.2), "right-way b = -0.2")]
    for inp, d in wrows:
        s.add("xva.wwr.cva_hw", inp, wwr(inp), cls="root_finding", verified=["mpmath-50"], tags=["xva", "wwr"], limit=LIM, description=d)
    cv = [c["expected"]["outputs"]["cva"] for c in s.cases]
    assert cv[2] > cv[1] > cv[0] > cv[3]
    # b = 0: equals the independent bucket CVA on the path-mean EE
    ee = [sum(max(W[p][i], 0) for p in range(4)) / 4 for i in range(4)]
    ind = sum(0.6 * df * e * (math.exp(-0.03 * t0) - math.exp(-0.03 * t1)) for df, e, t0, t1 in zip(wbase["discount_factors"], ee, [0.0, 0.25, 0.5, 0.75], wbase["times"]))
    assert abs(cv[0] - ind) < 1e-12
    caught("wrong-way term dropped", abs(wwr(wrows[2][0])["cva"] - wwr(wrows[2][0], "no_wwr")["cva"]))
    errs = [(dict(wbase, values=[[1.0]]), "E_INPUT", "path length differs"), (dict(wbase, hazard_rate=0.0), "E_DOMAIN", "hazard 0 (a(t) undefined)")]
    for inp, code, d in errs:
        s.add("xva.wwr.cva_hw", inp, error=code, cls="date_and_convention", tags=["invalid", "xva"], description=d)
    write(s)
    n4 = len(s.cases)
    reg = json.loads((HERE.parent / "outside_register_g.json").read_text(encoding="utf-8"))
    for k, n in (("collexp_g", n1), ("xvaadj_g", n2), ("simm_g", n3), ("wwr_g", n4)):
        reg[k] = {"counted": 0, "total": n, "rule": "own formulas on given inputs: not counted (G-40)"}
    (HERE.parent / "outside_register_g.json").write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8")
    for m, g in MUTANTS:
        note(f"  mutant caught: {m} (gap {g:.3e})")


if __name__ == "__main__":
    main()
