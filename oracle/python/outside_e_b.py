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


HANDLERS = {"vol.varswap.fair_strike": h_varswap}


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
    "garch_e": "QuantLib's Garch11 is not in the Python wheel; checked by mpmath replica and a separate float replay",
    "varswap_e": "q != 0 cases: QuantLib's drift term omits q (ruling E-B3); realized-variance cases have no QuantLib object",
    "vix_e": "no QuantLib object for the CBOE strip method; hand case plus exact-rational replica and a float replay",
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
