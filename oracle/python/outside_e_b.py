"""Outside-oracle verifier for stage E, spec B slices (plan rule 11.2.5).

For each golden case in datasets/golden/stage_e_b it reads the case's own inputs, builds the instrument from QuantLib's own
convention objects (only through qf_oracle/convmap_e_b.py, never inline), prices it in QuantLib and compares every output
with the golden under the case's own tolerance. A case counts only if every output is matched this way or is a named
identity of matched outputs (for example fair_vol = sqrt(fair_variance)). Nothing here reads the generator.

It also runs a second, float-only replay of the cases QuantLib cannot price (GARCH, VIX, ...), written separately from
the generator's mpmath replicas. That replay is a self-check; it never counts as outside oracle.

Writes oracle/outside_register_e_b.json and prints the coverage table.

    cd oracle/python && uv run python -W ignore outside_e_b.py [--write-map]
"""
import json
import math
import sys
from datetime import date
from pathlib import Path

import QuantLib as ql

from qf_oracle import convmap_e_b as CM

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
import runner  # noqa: E402  (tolerance comparison only)

POLICY = runner.load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")
FOLDER = "stage_e_b"
D = date.fromisoformat
QD = lambda d: ql.Date(d.day, d.month, d.year)  # noqa: E731


class Used:
    def __init__(self):
        self.rows = set()

    def __call__(self, row, *a):
        self.rows.add(row)
        return CM.obj(row, *a)


# ---------------------------------------------------------------- E7 variance swap (QuantLib)
def h_varswap(u, i, exp):
    if i["dividend_yield"] != 0:
        raise NotImplementedError("QuantLib's replicating engine drops q from the drift term (ruling E-B3)")
    a, m = QD(D(i["as_of"])), QD(D(i["maturity"]))
    ql.Settings.instance().evaluationDate = a
    ks = sorted({x["strike"] for x in i["vols"]})
    vol = {x["strike"]: x["vol"] for x in i["vols"]}
    M = ql.Matrix(len(ks), 2)
    for j, k in enumerate(ks):
        M[j][0] = M[j][1] = vol[k]
    surf = u("VOL.STRIKE_TABLE", a, [m, m + 365], ks, M)
    proc = u("PROC.BSM", ql.QuoteHandle(ql.SimpleQuote(i["spot"])), u("CRV.FLAT_CONT_365F", a, 0.0), u("CRV.FLAT_CONT_365F", a, i["rate"]), ql.BlackVolTermStructureHandle(surf))
    vs = u("VS.INSTRUMENT", i["variance_strike"], i["variance_notional"], a, m)
    vs.setPricingEngine(u("VS.DDKZ_SPOT", proc, i["extension_step"], i["call_strikes"], i["put_strikes"]))
    v = vs.variance()
    return {"fair_variance": v, "fair_vol": math.sqrt(v), "pv": vs.NPV()}


# ---------------------------------------------------------------- E4 (QuantLib)
def _od():
    import outside_d as OD
    return OD


def _ot(u, cp):
    return ql.Option.Call if cp else ql.Option.Put


def h_cube(u, i, exp):
    OD = _od()
    disc, t0 = OD.curve(u, i["discount"])
    proj, _ = OD.curve(u, i["projection"])
    disc.enableExtrapolation()
    proj.enableExtrapolation()
    ql.Settings.instance().evaluationDate = QD(t0)
    tr, cb = i["trade"], i["cube"]
    spot = OD._spot(u, t0)
    cal, mf, dc = u("CAL.USGS"), u("BDC.MODIFIED_FOLLOWING"), u("DC.ACT_365F")
    ex = lambda m: cal.adjust(QD(OD.add_months(spot, m)), mf)  # noqa: E731
    ts = [dc.yearFraction(QD(t0), ex(m)) for m in cb["expiries_months"]]
    ls = [m / 12 for m in cb["tenors_months"]]
    st = D(ex(tr["expiry_months"]).ISO())
    t, L = dc.yearFraction(QD(t0), QD(st)), tr["tenor_months"] / 12
    par = {}
    for k in ("alpha", "beta", "rho", "nu"):
        M = ql.Matrix(len(ls), len(ts))
        for a in range(len(ts)):
            for b in range(len(ls)):
                M[b][a] = cb[k][a][b]
        par[k] = u("INTERP.BILINEAR", ts, ls, M)(t, L)
    fx, fl = OD._sched(u, st, tr["tenor_months"], 12), OD._sched(u, st, tr["tenor_months"], 3)
    idx = OD._ibor(u, proj, 3)
    sw = ql.VanillaSwap(ql.Swap.Payer if tr["type"] == "PAYER" else ql.Swap.Receiver, tr["notional"], fx, tr["strike"], u("DC.THIRTY_360_BOND"), fl, idx, 0.0, u("DC.ACT_360"))
    dh = ql.YieldTermStructureHandle(disc)
    sw.setPricingEngine(ql.DiscountingSwapEngine(dh))
    Aa, Sr = abs(sw.fixedLegBPS()) / 1e-4 / tr["notional"], sw.fairRate()
    vol = u("SABR.SECTION", t, Sr, par["alpha"], par["beta"], par["rho"], par["nu"]).volatility(tr["strike"])
    so = ql.Swaption(sw, ql.EuropeanExercise(QD(st)))
    so.setPricingEngine(u("SWO.BLACK_ENGINE", dh, vol))
    return {"price": so.NPV(), "forward_rate": Sr, "annuity": Aa, "vol": vol, "sabr": par}


def h_strip(u, i, exp):
    """Counted by a reprice check, as stage D credit.cds.bootstrap: each cap at the golden caplet vols, priced in QuantLib's
    cap engine, equals the same cap at its flat vol in QuantLib within the case tolerance."""
    OD = _od()
    gv = exp["caplet_vols"]
    prices = []
    for M, fv in zip(i["cap_tenors_months"], i["flat_vols"]):
        trade = {"type": "CAP", "start_months": i["start_months"], "tenor_months": M, "strike": i["strike"], "notional": i["notional"]}
        base = {"discount": i["discount"], "projection": i["projection"], "model": i["model"], "trade": trade}
        flat = OD.h_cap(u, {**base, "vol": fv}, None)["price"]
        quoted = OD.h_cap(u, {**base, "vol": gv[:M // 3]}, None)["price"]
        if abs(flat - quoted) > 1e-9 * i["notional"]:
            return {"caplet_vols": [None] * len(gv), "cap_prices": []}
        prices.append(flat)
    return {"caplet_vols": gv, "cap_prices": prices}


def h_bf_price(u, i, exp):
    p = u("OPT.BLACK_FORMULA")(_ot(u, i["type"] == "CALL"), i["strike"], i["futures_price"], i["vol"] * math.sqrt(i["expiry_years"]), i["discount_factor"])
    return {"price": p, "contract_value": p * i["contract_size"] / 100}


def h_bf_iv(u, i, exp):
    sd = u("OPT.BLACK_IMPLIED")(_ot(u, i["type"] == "CALL"), i["strike"], i["futures_price"], i["premium"], i["discount_factor"], 0.0, 0.2, 1e-14, 1000)
    v = sd / math.sqrt(i["expiry_years"])
    return {"price_vol": v, "yield_vol": v / (i["ctd_modified_duration"] * i["ctd_yield"])}


def _fml(u, model, cp, F, K, v, t, Dd):
    if model == "BLACK_76":
        return u("OPT.BLACK_FORMULA")(_ot(u, cp), K, F, v * math.sqrt(t), Dd)
    return u("OPT.BACHELIER_FORMULA")(_ot(u, cp), K, F, v * math.sqrt(t), Dd)


def h_yoy(u, i, exp):
    c = [i["notional"] * p["accrual"] * _fml(u, i["model"], i["type"] == "CAP", p["yoy_forward"], i["strike"], p["vol"], p["expiry_years"], p["discount_factor"]) for p in i["periods"]]
    return {"caplets": c, "price": math.fsum(c)}


def h_zc(u, i, exp):
    Kr = (1 + i["strike"]) ** i["years"]
    return {"price": i["notional"] * _fml(u, i["model"], i["type"] == "CAP", i["forward_index_ratio"], Kr, i["vol"], i["years"], i["discount_factor"]), "strike_ratio": Kr}


# ---------------------------------------------------------------- E6 (QuantLib)
def _qm(M):
    return ql.Matrix([[float(x) for x in r] for r in M])


def h_validate(u, i, exp):
    M = i["matrix"]
    n = len(M)
    me = min(u("CORR.EIGEN", _qm(M)).eigenvalues())
    sym = all(M[a][b] == M[b][a] for a in range(n) for b in range(n))
    dg = all(M[a][a] == 1.0 for a in range(n))
    rg = all(-1 <= x <= 1 for r in M for x in r)
    psd = me >= -1e-10
    return {"symmetric": sym, "unit_diagonal": dg, "in_range": rg, "min_eigenvalue": me, "psd": psd, "valid": sym and dg and rg and psd}


def h_nearest(u, i, exp):
    M = i["matrix"]
    n = len(M)
    Sq = u("CORR.HIGHAM", _qm(M))
    X = [[sum(Sq[a][k] * Sq[b][k] for k in range(n)) for b in range(n)] for a in range(n)]
    if max(abs(X[a][a] - 1) for a in range(n)) > 2e-5:
        raise NotImplementedError("QuantLib's Higham stopped at its iteration cap before the unit diagonal held; not a check of the golden")
    return {"matrix": X, "frobenius_distance": math.sqrt(sum((X[a][b] - M[a][b]) ** 2 for a in range(n) for b in range(n)))}


HANDLERS = {"risk.corr.validate": h_validate, "risk.corr.nearest": h_nearest, "vol.varswap.fair_strike": h_varswap, "rates.swaption.price_cube": h_cube, "rates.cap.strip": h_strip, "rates.bondfut.option_price": h_bf_price,
            "rates.bondfut.implied_vol": h_bf_iv, "infl.cap.yoy_price": h_yoy, "infl.cap.zc_price": h_zc}


# ---------------------------------------------------------------- second-route float replays (self-check, not counted)
def r_garch_loglik(i):
    r = i["returns"]
    s2 = sum(x * x for x in r) / len(r) if i["initial_variance"] == "SAMPLE" else i["initial_variance"]
    v, ll = [], 0.0
    for x in r:
        v.append(s2)
        ll -= 0.5 * (math.log(2 * math.pi) + math.log(s2) + x * x / s2)
        s2 = i["omega"] + i["alpha"] * x * x + i["beta"] * s2
    return {"loglik": ll, "variances": v, "next_variance": s2}


def r_garch_forecast(i):
    p = i["alpha"] + i["beta"]
    VL = i["omega"] / (1 - p)
    v = [VL + p ** (h - 1) * (i["next_variance"] - VL) for h in range(1, i["horizon"] + 1)]
    t = math.fsum(v)
    return {"variances": v, "total_variance": t, "annualized_vol": math.sqrt(t * i["periods_per_year"] / i["horizon"]), "long_run_variance": VL}


def r_realized(i):
    p = i["prices"]
    lr = [math.log(p[k] / p[k - 1]) for k in range(1, len(p))]
    rv = i["periods_per_year"] * math.fsum(x * x for x in lr) / len(lr)
    return {"realized_variance": rv, "realized_vol": math.sqrt(rv), "payoff": i["variance_notional"] * (rv - i["variance_strike"])}


def r_vix_term(i):
    st = sorted(i["strip"], key=lambda x: x["strike"])
    T = i["minutes_to_expiry"] / 525600
    g = math.exp(i["rate"] * T)
    K = [x["strike"] for x in st]
    C = [(x["call_bid"] + x["call_ask"]) / 2 for x in st]
    P = [(x["put_bid"] + x["put_ask"]) / 2 for x in st]
    j = min(range(len(K)), key=lambda n: (abs(C[n] - P[n]), K[n]))
    F = K[j] + g * (C[j] - P[j])
    i0 = max(n for n in range(len(K)) if K[n] <= F)
    used = {i0: (C[i0] + P[i0]) / 2}
    for step, bid, q in ((-1, "put_bid", P), (1, "call_bid", C)):
        n, z = i0 + step, 0
        while 0 <= n < len(K):
            if st[n][bid] == 0:
                z += 1
                if z == 2:
                    break
            else:
                z = 0
                used[n] = q[n]
            n += step
    ks = sorted(used)
    tot = 0.0
    for m, n in enumerate(ks):
        lo, hi = ks[max(m - 1, 0)], ks[min(m + 1, len(ks) - 1)]
        dk = (K[hi] - K[lo]) / (2 if 0 < m < len(ks) - 1 else 1)
        tot += dk / K[n] ** 2 * used[n]
    var = 2 / T * g * tot - (F / K[i0] - 1) ** 2 / T
    return {"forward": F, "k0": K[i0], "variance": var, "strikes_used": [K[n] for n in ks]}


def r_vix_index(i):
    a, b = r_vix_term(i["near"]), r_vix_term(i["next"])
    N1, N2 = i["near"]["minutes_to_expiry"], i["next"]["minutes_to_expiry"]
    T1, T2 = N1 / 525600, N2 / 525600
    x = (T1 * a["variance"] * (N2 - 43200) / (N2 - N1) + T2 * b["variance"] * (43200 - N1) / (N2 - N1)) * 525600 / 43200
    return {"index": 100 * math.sqrt(x), "near_variance": a["variance"], "next_variance": b["variance"]}


REPLAYS = {"vol.garch.loglik": r_garch_loglik, "vol.garch.forecast": r_garch_forecast, "vol.varswap.realized": r_realized,
           "vol.vix.term_variance": r_vix_term, "vol.vix.index": r_vix_index}


# ---------------------------------------------------------------- driver
def judge(case, got):
    exp = case["expected"]["outputs"]
    if set(got) != set(exp):
        return False, f"keys {sorted(got)} vs {sorted(exp)}"
    cls = POLICY[case["tolerance_class"]]
    per = case.get("output_classes", {})
    msgs = []
    for k, e in exp.items():
        msgs += runner.compare(got[k], e, POLICY[per[k]] if k in per else cls, None if k in per else case.get("tolerance_limit"), k)
    return not msgs, "; ".join(msgs[:2])


def load():
    for p in sorted((ROOT / "datasets" / "golden" / FOLDER).glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        yield d["suite"], d["cases"]


NO_ORACLE = {
    "corr_e": "implied correlation and dispersion have no QuantLib object (closed forms, hand-checked); on 4 harder matrices QuantLib's Higham stops at its iteration cap before convergence",
    "garch_e": "QuantLib's Garch11 is not in the Python wheel; checked by mpmath replica and a separate float replay",
    "varswap_e": "q != 0 cases: QuantLib's drift term omits q (ruling E-B3); realized-variance cases have no QuantLib object",
    "ratesvol_e": "only error cases are not counted",
    "vix_e": "no QuantLib object for the Cboe strip method; hand case plus exact-rational replica and a float replay",
}


def verify_all(show=True):
    reg, table, bad = [], [], []
    for suite, cases in load():
        k = 0
        for c in cases:
            if c["expected"]["status"] != "ok":
                continue
            if c["operation"] in REPLAYS:
                ok, why = judge(c, REPLAYS[c["operation"]](c["inputs"]))
                if not ok:
                    bad.append(f"replay {c['case_id']}: {why}")
            h = HANDLERS.get(c["operation"])
            if not h:
                continue
            u = Used()
            try:
                ok, why = judge(c, h(u, c["inputs"], c["expected"]["outputs"]))
            except NotImplementedError as e:
                ok, why = False, f"not mapped: {e}"
            except RuntimeError as e:
                ok, why = False, f"QuantLib refused: {e}"
            if ok:
                k += 1
                reg.append({"case_id": c["case_id"], "operation": c["operation"], "library": CM.LIBRARY, "version": CM.VERSION,
                            "convention_rows": sorted(u.rows), "map_review": CM.REVIEW})
            elif show and not why.startswith("not mapped"):
                bad.append(f"outside {c['case_id']}: {why}")
        table.append((suite, k, len(cases)))
    return reg, table, bad


def write_map():
    import inspect
    import re
    L = ["# Convention map for stage E spec B outside-oracle checks", "",
         "Plan rule 11.2.5. Rows used by `oracle/python/outside_e_b.py`, from `oracle/python/qf_oracle/convmap_e_b.py`. Base rows are the stage D table "
         "(`oracle/CONVENTION_MAP.md`); only the new rows are listed here.", "",
         f"Library: QuantLib {CM.VERSION} (Python wheel). Version recorded per case in `oracle/outside_register_e_b.json`.", "",
         f"Review: {CM.REVIEW}. Self-assessment, not an outside review.", "",
         "| Row | Spec | QuantLib object | Note |", "|---|---|---|---|"]
    for k, (spec, fn, nt) in CM.NEW.items():
        src = inspect.getsource(fn).strip()
        m = re.search(r"lambda[^:]*:\s*(.*)", src)
        body = (m.group(1).rstrip(" ),") if m else src).replace("|", "\\|")
        body = body if len(body) <= 110 else body[:107] + "..."
        L.append(f"| `{k}` | {spec} | `{body}` | {nt} |")
    (ROOT / "oracle" / "CONVENTION_MAP_E_B.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


def main():
    if "--write-map" in sys.argv:
        write_map()
    text = (ROOT / "oracle" / "CONVENTION_MAP_E_B.md").read_text(encoding="utf-8")
    missing = [r for r in CM.NEW if f"`{r}`" not in text]
    if missing:
        print("rows missing from CONVENTION_MAP_E_B.md:", missing)
        return 1
    reg, table, bad = verify_all()
    for b in bad:
        print(" ", b)
    k, n = sum(t[1] for t in table), sum(t[2] for t in table)
    print("| Suite | Outside-oracle cases | Cases | Share | Why not more |\n|---|---|---|---|---|")
    for s, a, b in table:
        print(f"| `{s}` | {a} | {b} | {100 * a / b:.0f}% | {NO_ORACLE.get(s, '')} |")
    print(f"| **stage E spec B** | **{k}** | **{n}** | **{100 * k / n:.1f}%** | |")
    (ROOT / "oracle" / "outside_register_e_b.json").write_text(json.dumps({"rule": "plan 11.2.5", "library": CM.LIBRARY, "version": CM.VERSION, "map_review": CM.REVIEW,
                                                                         "cases": reg}, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
