"""Stage G wave 4b: deterministic xVA layer on given paths (rulings G-40 to G-44).

- `xva.exposure.collateralised`: netting sets, CSA (thresholds, MTA, independent amount), margin period of risk as a
  lag in grid steps; outputs EE, ENE, PFE, EPE and effective EPE per netting set.
- `xva.adjustments.value`: CVA, DVA, FCA, FBA (with the DVA overlap rule), MVA and KVA from given profiles.
- `xva.sbim.ir_delta`: sensitivity-based initial margin for one currency's IR delta (weights and correlations are
  inputs; the goldens feed it the rule-generated table `specifications/tables/stage_k/sbim-ir-delta-g.json`, KR-150).
  The old id `xva.simm.ir_delta` is a deprecated alias in v1.0.0, removed in the first release after it (KR-152, KR-256); its invariance and E1 cases go to
  `stage_k/sbim_alias_k.json`.
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


# ------------------------------------------------------------------------------------------------ sensitivity-based IR delta
def sbim(inp, mut=None):
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
    # 130 digits: mean_p S_p - e^(-h t) cancels about -log10(h dt) digits (50 at h = 1e-50); 80 are left for the root.
    with mp.workdps(130):
        return _wwr(inp, mut)


def _wwr(inp, mut=None):
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
        # KR-257: bisection on the closed-form bracket [ln h - max bV - 1, ln h - min bV + 1] (f > 0 at the left end,
        # f < 0 at the right end because mean_p S_p(t_(i-1)) = e^(-h t_(i-1))), to 1e-40 relative. The old findroot
        # from ln h (a secant) gave the same roots on the first four goldens and fails for large |b V|.
        c = [b * V[p][i - 1] for p in range(n)]
        lo, hi = mp.log(h) - max(c) - 1, mp.log(h) - min(c) + 1
        assert f(lo) > 0 > f(hi), "closed-form bracket does not change sign"
        while hi - lo > mp.mpf(10) ** -40 * max(1, abs(lo)):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
        a = (lo + hi) / 2
        avals.append(a)
        newS = [S[p] * mp.exp(-mp.exp(a + b * V[p][i - 1]) * dt) for p in range(n)]
        cva += (1 - R) * df[i] * sum(max(V[p][i - 1], 0) * (S[p] - newS[p]) for p in range(n)) / n
        S = newS
    return {"cva": float(cva), "a": [float(x) for x in avals]}


def wwr_closed(inp):
    """Identical V on every path: S_p is the same on every path, so mean_p S_p(t_i) = e^(-h t_i) holds bucket by bucket
    with exp(a_i + b V_i) = h, hence a_i = ln h - b V_i and CVA = (1 - R) sum D_i max(V_i, 0) (e^(-h t_(i-1)) - e^(-h t_i))."""
    t = [mp.mpf(0)] + [mp.mpf(x) for x in inp["times"]]
    h, R, b = mp.mpf(inp["hazard_rate"]), mp.mpf(inp["recovery"]), mp.mpf(inp["wwr_b"])
    v = [mp.mpf(x) for x in inp["values"][0]]
    assert all(row == inp["values"][0] for row in inp["values"])
    cva = sum(mp.mpf(d) * max(v[i], 0) * (mp.exp(-h * t[i]) - mp.exp(-h * t[i + 1])) for i, d in enumerate(inp["discount_factors"]))
    return {"cva": float((1 - R) * cva), "a": [float(mp.log(h) - b * x) for x in v]}


def wwr_root_cases(s):
    """KR-257 (confirmed 2026-11-20): the a(t) root for large |b V| (a mutation lane found the old Newton silently
    returning a = -2.6e33 and cva = 0 for h = 0.01, b = 1, V = 10), tiny and large hazards, the |b V| <= 700 limit,
    and the E_NON_FINITE cases. Identical-V cases are checked against the closed form."""
    op, tg = "xva.wwr.cva_hw", ["xva", "wwr", "kr257"]
    rep = dict(times=[1.0, 2.0], values=[[10.0, 10.0], [10.0, 10.0]], discount_factors=[0.97, 0.94], hazard_rate=0.01, recovery=0.4, wwr_b=1.0)
    mixed = dict(times=[0.5, 1.0, 2.0], values=[[30.0, 25.0, 40.0], [-20.0, 5.0, -35.0], [10.0, 40.0, 0.0], [2.0, -8.0, 15.0]],
                 discount_factors=[0.99, 0.98, 0.955], hazard_rate=0.02, recovery=0.4, wwr_b=1.0)
    one = dict(times=[1.0], discount_factors=[0.97], hazard_rate=0.01, recovery=0.4)
    closed = [(rep, "reported example: b V = 10 on every path (old builds: a = -2.6e33, cva = 0)"),
              (dict(rep, values=[[20.0, 20.0], [20.0, 20.0]]), "b V = 20 on every path"),
              (dict(rep, wwr_b=-1.0), "b V = -10 on every path, positive exposure"),
              (dict(rep, values=[[-30.0, -30.0], [-30.0, -30.0]]), "b V = -30 on every path, no positive exposure"),
              (dict(rep, values=[[60.0, 60.0], [60.0, 60.0]], wwr_b=-1.0), "b V = -60 on every path: root a = 55.4, above the old C++ bracket end 50"),
              (dict(one, values=[[10.0], [10.0]], hazard_rate=1e-50, wwr_b=70.0), "h = 1e-50, b V = 700: root a = -815.1, below the old C++ bracket end -800"),
              (dict(one, values=[[10.0], [10.0]], wwr_b=70.0), "boundary |b V| = 700 on every path"),
              (dict(one, values=[[1.0], [1.0]], hazard_rate=700.0, wwr_b=0.5), "boundary h t = 700: target e^-700 is a normal double"),
              (dict(rep, values=[[3.0, -2.0], [3.0, -2.0]], hazard_rate=1e-10, wwr_b=0.3), "tiny hazard 1e-10: no cancellation in 1 - e^(-h t)")]
    for inp, d in closed:
        out = wwr(inp)
        cf = wwr_closed(inp)
        assert abs(out["cva"] - cf["cva"]) <= 1e-15 * max(1.0, abs(cf["cva"])) and all(abs(x - y) <= 1e-15 * max(1.0, abs(y)) for x, y in zip(out["a"], cf["a"])), d
        s.add(op, inp, out, cls="root_finding", verified=["mpmath-50", "closed-form"], tags=tg, limit=LIM, description=d)
    general = [(mixed, "mixed V across paths, b = 1: |b V| up to 40"), (dict(mixed, wwr_b=-0.75), "mixed V across paths, right way b = -0.75"),
               (dict(one, values=[[10.0], [-10.0]], wwr_b=70.0), "boundary mixed: b V = +700 and -700"),
               (dict(mixed, hazard_rate=2.0, wwr_b=0.1), "hazard 2 with a 1-year bucket: bucket default probability above 1/2"),
               (dict(one, values=[[5.0], [-5.0], [1.0]], hazard_rate=40.0, wwr_b=0.2), "hazard 40: 1 - e^(-h dt) rounds to 1 in binary64"),
               (dict(mixed, hazard_rate=1e-10, wwr_b=0.3), "tiny hazard 1e-10, mixed V")]
    for inp, d in general:
        s.add(op, inp, wwr(inp), cls="root_finding", verified=["mpmath-50"], tags=tg, limit=LIM, description=d)
    errs = [(dict(one, values=[[10.0], [10.0]], wwr_b=70.5), "E_DOMAIN", "|b V| = 705 above 700"),
            (dict(one, values=[[10.0, 1.0], [10.0]], wwr_b=70.5), "E_INPUT", "two errors: path length differs and |b V| above 700"),
            (dict(one, values=[[1.0], [1.0]], hazard_rate=800.0, wwr_b=0.0), "E_NON_FINITE", "target e^-800 underflows"),
            (dict(one, values=[[1.0], [1.0]], hazard_rate=800.0, recovery=1.0, wwr_b=0.0), "E_DOMAIN", "two errors: recovery 1 and target underflow"),
            (dict(one, values=[[1.0], [1.0]], hazard_rate=1e-310, wwr_b=0.0), "E_NON_FINITE", "bucket default probability below the smallest normal double")]
    for inp, code, d in errs:
        s.add(op, inp, error=code, cls="date_and_convention", tags=["invalid", "xva", "kr257"], description=d)


def first_time_cases(s, op, base, other, other_desc):
    """KR-258 (proposed 2026-11-20): a first time at or below 0 is a structural E_INPUT (HR-122 step 4, ordering
    against the implied t_0 = 0), as in Python and Rust; C++ and Java returned E_DOMAIN and no golden sent it."""
    n = len(base["times"])
    rest = list(base["times"][1:])
    errs = [(dict(base, times=[0.0] + rest), "E_INPUT", "first time 0 (the implied t_0 = 0 is not before it)"),
            (dict(base, times=[-0.5] + rest), "E_INPUT", "negative first time"),
            (dict(base, times=[base["times"][0]] * 2 + rest[1:] if n > 1 else base["times"]), "E_INPUT", "two equal times: not increasing"),
            (dict(base, times=list(reversed(base["times"]))), "E_INPUT", "times decreasing"),
            (dict(base, times=[0.0] + rest, **other), "E_INPUT", f"two errors: first time 0 [structural] and {other_desc} [domain]; structural E_INPUT first"),
            (dict(base, times=[-1.0] + rest, **other), "E_INPUT", f"two errors: negative first time [structural] and {other_desc} [domain]; structural E_INPUT first")]
    for inp, code, d in errs:
        s.add(op, inp, error=code, cls="date_and_convention", tags=["invalid", "xva", "kr258"], description=d)


def schema_first_cases(s, op, cases):
    """HR-122 step (1) (KR-230, KR-258 sweep, 2026-11-20): an E_SCHEMA fault anywhere in the request comes before a
    structural or domain fault elsewhere. The four-build sweep found C++ reporting the structural or domain fault
    first in these three operations, because it validated each field as it read it."""
    for inp, d in cases:
        s.add(op, inp, error="E_SCHEMA", cls="date_and_convention", tags=["invalid", "xva", "hr122"], description="two errors: " + d + "; E_SCHEMA first (HR-122)")


OP, ALIAS = "xva.sbim.ir_delta", "xva.simm.ir_delta"  # KR-152, KR-256: the old id is a deprecated alias in v1.0.0, removed in the first release after it


def alias_suite(g):
    """stage_k/sbim_alias_k.json (KR-153): for each sbim_g input an invariance pair (new id `any`, alias `same_as`),
    one E1 case per Real input of the alias (F-2, E_DOMAIN) and one case with two errors at once (HR-66)."""
    a = Suite("sbim_alias_k", "specifications/stage-k-rulings-margin.md", G)
    for c in g.cases:
        a.cases.append({"case_id": "", "operation": OP, "inputs": c["inputs"], "expected": {"status": "any"},
                        "tolerance_class": "date_and_convention", "verified_by": ["rule-F-3-anchor"],
                        "tags": ["alias", "zero_anchor", f"base:{c['case_id']}"], "description": f"new id on the inputs of {c['case_id']}"})
        a.cases.append({"case_id": "", "operation": ALIAS, "inputs": c["inputs"], "expected": {"status": "same_as", "case_id": None},
                        "tolerance_class": c["tolerance_class"], **({"tolerance_limit": c["tolerance_limit"]} if "tolerance_limit" in c else {}),
                        "verified_by": ["rule-KR-152"], "tags": ["alias", "deprecated", f"base:{c['case_id']}"],
                        "description": f"deprecated alias {ALIAS}: same result as {OP} (KR-152)"})
    base = g.cases[0]["inputs"]
    nf = [(["sensitivities", 0], "NaN"), (["risk_weights", 0], "Infinity"), (["correlations", 0, 1], "-Infinity"),
          (["concentration_threshold"], "NaN")]
    for path, tok in nf:
        inp = json.loads(json.dumps(base))
        h = inp
        for p in path[:-1]:
            h = h[p]
        h[path[-1]] = tok
        a.cases.append({"case_id": "", "operation": ALIAS, "inputs": inp, "expected": {"status": "error", "error_code": "E_DOMAIN"},
                        "tolerance_class": "date_and_convention", "verified_by": ["rule-F-2"],
                        "tags": ["e1", "non_finite", tok.lower().lstrip("-"), f"base:{g.cases[0]['case_id']}",
                                 "input:/" + "/".join(map(str, path))],
                        "description": f"alias, {tok} at {'/'.join(map(str, path))}"})
    two = dict(base, risk_weights=base["risk_weights"][:5], concentration_threshold=0.0)
    a.cases.append({"case_id": "", "operation": ALIAS, "inputs": two, "expected": {"status": "error", "error_code": "E_INPUT"},
                    "tolerance_class": "date_and_convention", "verified_by": ["rule-HR-66"], "tags": ["invalid", "two_errors"],
                    "description": "two errors at once: risk_weights one short [structural] and threshold 0 [domain]; structural E_INPUT first"})
    for i, c in enumerate(a.cases, 1):
        c["case_id"] = f"sbim_alias_k-{i:04d}"
    for i, c in enumerate(a.cases):
        if c["expected"].get("status") == "same_as":
            c["expected"]["case_id"] = a.cases[i - 1]["case_id"]
    for c in a.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_k"
    a.write()
    common.GOLDEN = keep


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
    e0 = rows[3][0]
    schema_first_cases(s, "xva.exposure.collateralised", [
        (dict(e0, times=list(reversed(TIMES)), csa={"NS1": dict(csa0, threshold_receive="x")}), "times decreasing [structural] and a string threshold [schema]"),
        (dict(e0, trades=[], pfe_quantile="0.75"), "no trades [structural] and a string pfe_quantile [schema]"),
        (dict(e0, times=list(reversed(TIMES)), trades=[dict(netting_set=1, values=PATHS_A)]), "times decreasing [structural] and a numeric netting_set [schema]")])
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
    first_time_cases(s, "xva.adjustments.value", base, dict(counterparty=dict(hazard_rate=-0.01, recovery=0.4)), "negative counterparty hazard")
    schema_first_cases(s, "xva.adjustments.value", [
        (dict(base, ene=[1.0, -90.0, -100.0, -70.0], funding=dict(lend_spread=0.008, exclude_dva_overlap=False)), "positive ENE [domain] and funding without borrow_spread [schema]"),
        (dict(base, times=[0.0, 1.0, 1.5, 2.0], own=dict(hazard_rate=0.01, recovery=[0.4])), "first time 0 [structural] and a list recovery [schema]"),
        (dict(base, ee=[1.0], funding=dict(base["funding"], exclude_dva_overlap=1)), "ee length differs [structural] and a numeric flag [schema]")])
    write(s)
    n2 = len(s.cases)

    # ---- sensitivity-based IR delta (KR-150 to KR-153): weights and correlations from the rule-generated table
    s = Suite("sbim_g", "specifications/06-risk/xva-framework.md", G)
    table = json.loads((HERE.parents[1] / "specifications" / "tables" / "stage_k" / "sbim-ir-delta-g.json").read_text(encoding="utf-8"))
    assert table["placeholder"] is True and table["label"] == "placeholder weights"
    rw = [float(x) for x in table["risk_weights"]]  # RW = 10 x k (KR-150)
    corr = [[float(x) for x in r] for r in table["correlations"]]  # rho(k, l) = 1 - 0.1 |k - l| (KR-150)
    srows = [(dict(sensitivities=[1000.0, -500.0, 2500.0, 4000.0, -1200.0, 300.0], risk_weights=rw, correlations=corr, concentration_threshold=1e9), "mixed signs, below concentration"),
             (dict(sensitivities=[0.0, 0.0, 10000.0, 0.0, 0.0, 0.0], risk_weights=rw, correlations=corr, concentration_threshold=1e9), "one bucket: margin = RW x s"),
             (dict(sensitivities=[1e6, 1e6, 1e6, 1e6, 1e6, 1e6], risk_weights=rw, correlations=corr, concentration_threshold=1e6), "concentration factor sqrt(6)"),
             (dict(sensitivities=[1000.0, -1000.0, 0.0, 0.0, 0.0, 0.0], risk_weights=[100.0, 100.0, 0, 0, 0, 0], correlations=[[1.0] * 6 for _ in range(6)], concentration_threshold=1e9), "perfect correlation hedge: margin 0")]
    for inp, d in srows:
        s.add(OP, inp, sbim(inp), verified=["mpmath-50"], tags=["xva", "sbim", "placeholder weights"], limit=LIM, description=d)
    assert abs(s.cases[1]["expected"]["outputs"]["margin"] - 10000.0 * rw[2]) < 1e-6
    caught("tenor correlation ignored", abs(sbim(srows[0][0])["margin"] - sbim(srows[0][0], "no_corr")["margin"]))
    errs = [(dict(srows[0][0], risk_weights=rw[:5]), "E_INPUT", "length mismatch"), (dict(srows[0][0], concentration_threshold=0.0), "E_DOMAIN", "threshold 0"),
            (dict(srows[0][0], correlations=[[1.0, 1.5] + [0.0] * 4] + corr[1:]), "E_DOMAIN", "correlation above 1"),
            (dict(srows[0][0], risk_weights=[-1.0] + rw[1:]), "E_DOMAIN", "negative risk weight")]
    for inp, code, d in errs:
        s.add(OP, inp, error=code, cls="date_and_convention", tags=["invalid", "xva"], description=d)
    write(s)
    n3 = len(s.cases)
    alias_suite(s)

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
    wwr_root_cases(s)
    first_time_cases(s, "xva.wwr.cva_hw", wbase, dict(hazard_rate=-0.01), "negative hazard")
    schema_first_cases(s, "xva.wwr.cva_hw", [
        (dict(wbase, times=[0.25, 0.25, 0.75, 1.0], recovery="x"), "times not increasing [structural] and a string recovery [schema]"),
        (dict(wbase, values=[], discount_factors=["1", 0.99, 0.985, 0.98]), "no paths [structural] and a string discount factor [schema]"),
        ({k: v for k, v in dict(wbase, times=[0.0, 0.5, 0.75, 1.0]).items() if k != "wwr_b"}, "first time 0 [structural] and wwr_b missing [schema]")])
    for inp, d in [(dict(wbase, values=[W[0], W[1][:2]] + W[2:], hazard_rate="NaN"), "a short path [structural] and a NaN hazard_rate [finite rule]"),
                   (dict(wbase, times=[0.0, 0.5, 0.75, 1.0], values=[W[0][:3] + ["NaN"]] + W[1:]), "first time 0 [structural] and a NaN value [finite rule]")]:
        s.add("xva.wwr.cva_hw", inp, error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "xva", "hr122"],
              description="two errors: " + d + "; the finite rule (E_DOMAIN) before structural E_INPUT (HR-122)")
    write(s)
    n4 = len(s.cases)
    reg = json.loads((HERE.parent / "outside_register_g.json").read_text(encoding="utf-8"))
    reg = {("sbim_g" if k == "simm_g" else k): v for k, v in reg.items()}  # suite renamed sbim_g (KR-153), position kept
    for k, n in (("collexp_g", n1), ("xvaadj_g", n2), ("sbim_g", n3), ("wwr_g", n4)):
        reg[k] = {"counted": 0, "total": n, "rule": "own formulas on given inputs: not counted (G-40)"}
    (HERE.parent / "outside_register_g.json").write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8", newline="\n")
    for m, g in MUTANTS:
        note(f"  mutant caught: {m} (gap {g:.3e})")


if __name__ == "__main__":
    main()
