"""Validation evidence pack, option C: outside-library checks for stage B and C curve cases that had none.

Reads the committed goldens and never changes a golden value. Each check runs QuantLib 1.44 (the oracle's pinned
version, oracle/python/uv.lock) on the golden's own inputs and compares every compared output at the golden's own
tolerance class (conformance/tolerances/policy.yaml). An output that is plain arithmetic on library outputs is marked
`"via": "arithmetic"`, as in outside_j.py. A case passes only if every compared output passes. A disagreement stops
the run with exit code 1 and is reported; goldens are never edited to match.

    cd oracle/python && <python with QuantLib 1.44> -W ignore outside_validation.py           writes oracle/OUTSIDE_VALIDATION.json
    ... outside_validation.py --apply   also appends the library tag to `verified_by` of every passing case (only that
                                        field changes; the file is rewritten in the generator's own format)
    ... outside_validation.py --check   exit 1 if a golden carries a tag from this script without a passing entry

QuantLib's Windows DLL may be blocked by an application-control policy; the pack was run under WSL
(`UV_PROJECT_ENVIRONMENT=~/qf-oracle-venv uv sync` in oracle/python).

Checks:
  fx.forward.outright   QuantLib FxForward.fairForwardRate on DiscountingFxForwardEngine (GBP base curve, USD quote
                        curve, spot quote), settlement 2 days on JointCalendar(UK Settlement, US GovernmentBond).
                        Curves: DiscountCurve, log-linear on discount factors, Actual365Fixed, with D(as_of) = 1.
                        points = (F - S) / 1e-4 is arithmetic on the library forward.
  eq.forward.outright   QuantLib AnalyticDividendEuropeanEngine (escrowed dividends) on a BlackScholesMertonProcess
                        with the funding curve as risk-free and the borrow curve as dividend yield; the forward comes
                        from put-call parity F = K + (C - P) / D(T) at K = spot. discount_factor and carry_factor are
                        the library curves' D_r(T) and D_r(T)/D_b(T); pv_dividends = S - F * carry is arithmetic.
  vol.svi.evaluate      QuantLib SviSmileSection variance; implied_vol is the library's volatility(). g and min_g
                        (Durrleman g, Gatheral-Jacquier 2014 eq. 2.1) are arithmetic on the library's total variance
                        by central differences (step 1e-4) and are checked at 1e-6 absolute; butterfly_free is
                        min_g >= 0 on those values.
  vol.ssvi.evaluate     each slice is the raw SVI slice of Gatheral-Jacquier 2014, Lemma 3.3 (a = theta/2 (1 - rho^2),
                        b = theta phi / 2, m = -rho / phi, sigma = sqrt(1 - rho^2) / phi) evaluated by
                        QuantLib SviSmileSection. butterfly_free and calendar_free are the spec's sufficient
                        conditions on the parameters (G-J 2014 Theorem 4.2 and Corollary 4.1), which no library
                        computes: they are recomputed as arithmetic and marked so.
"""
import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path


try:
    import QuantLib as ql
except ImportError:  # --check needs only the standard library
    ql = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GOLD = ROOT / "datasets" / "golden"
OUT = ROOT / "oracle" / "OUTSIDE_VALIDATION.json"
QLV = "quantlib-1.44"
TAG = {"fx.forward.outright": QLV + "-fxforward", "eq.forward.outright": QLV + "-dividend-engine",
       "vol.svi.evaluate": QLV, "vol.ssvi.evaluate": QLV + "-svi-slices"}
SUITES = {"fx.forward.outright": ["stage_b/fx.json", "stage_b/fx_deep.json"],
          "eq.forward.outright": ["stage_c/equity_forward.json"],
          "vol.svi.evaluate": ["stage_c/smile.json"], "vol.ssvi.evaluate": ["stage_c/smile.json"]}
TOL = {"simple_analytic": (1e-12, 1e-10), "per_unit": (1e-10, 1e-8), "interpolation": (1e-10, 1e-8),
       "root_finding": (1e-10, 1e-10), "date_and_convention": None}
# Disagreements that trace to a stated convention difference, not a value error. Recorded, never tagged, never
# used to change a golden. Reported in docs/validation/equity-forward.md for the reviewer to rule on.
KNOWN = {"equity_forward-0012": "boundary convention: the spec ignores a dividend with ex_date <= as_of "
         "(equity-forward.md line 25); QuantLib AnalyticDividendEuropeanEngine counts a dividend dated on the evaluation "
         "date. With the as_of dividend removed from the inputs, QuantLib agrees on all four outputs (probe below)."}
GTOL = (1e-6, 0.0)  # central-difference g on library variance; truncation error about 1e-8 at step 1e-4


def Q(s):
    d = date.fromisoformat(s)
    return ql.Date(d.day, d.month, d.year)


def tol_for(case, out):
    t = TOL[case.get("output_classes", {}).get(out, case["tolerance_class"])]
    lim = case.get("tolerance_limit")
    if lim and t is not None:
        t = (lim.get("absolute", t[0]), lim.get("relative", t[1]))
    return t


def cmp(case, out, outside, via="library", tol=None):
    g = case["expected"]["outputs"][out]
    t = tol if tol is not None else tol_for(case, out)
    if t is None or isinstance(g, bool):
        ok = g == outside
        return {"output": out, "golden": g, "outside": outside, "tolerance": "exact", "via": via, "pass": bool(ok)}
    gs = g if isinstance(g, list) else [g]
    os_ = outside if isinstance(outside, list) else [outside]
    gs = [x for row in gs for x in (row if isinstance(row, list) else [row])]
    os_ = [x for row in os_ for x in (row if isinstance(row, list) else [row])]
    if len(gs) != len(os_):
        return {"output": out, "golden": g, "outside": outside, "tolerance": "shape", "via": via, "pass": False}
    err = max(abs(a - b) - (t[0] + t[1] * max(abs(a), abs(b))) for a, b in zip(gs, os_))
    worst = max(abs(a - b) for a, b in zip(gs, os_))
    return {"output": out, "golden": g, "outside": outside, "tolerance": {"absolute": t[0], "relative": t[1]},
            "max_abs_diff": worst, "via": via, "pass": bool(err <= 0)}


def curve(c, as_of):
    """Golden LOG_LINEAR_DF curve as a QuantLib DiscountCurve with D(as_of) = 1 (curve-framework.md)."""
    assert c["interpolation"] == "LOG_LINEAR_DF", c["interpolation"]
    ds = [Q(as_of)] + [Q(p["date"]) for p in c["pillars"]]
    vs = [1.0] + [p["discount_factor"] for p in c["pillars"]]
    k = ql.DiscountCurve(ds, vs, ql.Actual365Fixed())
    k.enableExtrapolation()
    return k


def fx_forward(case):
    i = case["inputs"]
    assert i["pair"] == "GBPUSD"
    ql.Settings.instance().evaluationDate = Q(i["as_of"])
    cal = ql.JointCalendar(ql.UnitedKingdom(ql.UnitedKingdom.Settlement), ql.UnitedStates(ql.UnitedStates.GovernmentBond), ql.JoinHolidays)
    bc = ql.YieldTermStructureHandle(curve(i["base_curve"], i["as_of"]))
    qc = ql.YieldTermStructureHandle(curve(i["quote_curve"], i["as_of"]))
    f = ql.FxForward(1e6, ql.GBPCurrency(), ql.USDCurrency(), 1.0, Q(i["value_date"]), False, 2, cal)
    f.setPricingEngine(ql.DiscountingFxForwardEngine(bc, qc, ql.QuoteHandle(ql.SimpleQuote(i["spot"]))))
    F = f.fairForwardRate().rate() if hasattr(f.fairForwardRate(), "rate") else f.fairForwardRate()
    return [cmp(case, "forward", F), cmp(case, "points", (F - i["spot"]) / 1e-4, via="arithmetic")]


def eq_forward(case):
    i = case["inputs"]
    if i["expiry"] == i["as_of"]:
        return None, "expiry on as_of: no option to price, so the engine has nothing to check (F = S by the spec's own rule)"
    ql.Settings.instance().evaluationDate = Q(i["as_of"])
    r = curve(i["funding_curve"], i["as_of"])
    b = curve(i["borrow_curve"], i["as_of"]) if i["borrow_curve"] else ql.FlatForward(Q(i["as_of"]), 0.0, ql.Actual365Fixed())
    S, T = i["spot"], Q(i["expiry"])
    vol = ql.BlackConstantVol(Q(i["as_of"]), ql.NullCalendar(), 0.2, ql.Actual365Fixed())
    proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(S)), ql.YieldTermStructureHandle(b),
                                        ql.YieldTermStructureHandle(r), ql.BlackVolTermStructureHandle(vol))
    divs = ql.DividendVector([Q(d["ex_date"]) for d in i["dividends"]], [d["amount"] for d in i["dividends"]])
    eng = ql.AnalyticDividendEuropeanEngine(proc, divs)
    px = {}
    for k, ty in (("c", ql.Option.Call), ("p", ql.Option.Put)):
        o = ql.VanillaOption(ql.PlainVanillaPayoff(ty, S), ql.EuropeanExercise(T))
        o.setPricingEngine(eng)
        px[k] = o.NPV()
    D = r.discount(T)
    carry = D / b.discount(T)
    F = S + (px["c"] - px["p"]) / D
    return [cmp(case, "forward", F), cmp(case, "discount_factor", D), cmp(case, "carry_factor", carry),
            cmp(case, "pv_dividends", S - F * carry, via="arithmetic")], None


def svi_section(T, a, b, rho, m, sig):
    return ql.SviSmileSection(T, 100.0, [a, b, sig, rho, m])


def w_of(sec, T, k):
    return sec.variance(100.0 * math.exp(k))


def g_fn(sec, T, k, h=1e-4):
    w0, wp, wm = w_of(sec, T, k), w_of(sec, T, k + h), w_of(sec, T, k - h)
    w1, w2 = (wp - wm) / (2 * h), (wp - 2 * w0 + wm) / (h * h)
    return (1 - k * w1 / (2 * w0)) ** 2 - w1 * w1 / 4 * (1 / w0 + 0.25) + w2 / 2


def svi(case):
    i = case["inputs"]
    p, T, ks = i["svi"], i["expiry_years"], i["log_moneyness"]
    sec = svi_section(T, p["a"], p["b"], p["rho"], p["m"], p["sigma"])
    w = [w_of(sec, T, k) for k in ks]
    iv = [sec.volatility(100.0 * math.exp(k)) for k in ks]
    g = [g_fn(sec, T, k) for k in ks]
    return [cmp(case, "total_variance", w), cmp(case, "implied_vol", iv),
            cmp(case, "g", g, via="arithmetic", tol=GTOL), cmp(case, "min_g", min(g), via="arithmetic", tol=GTOL),
            cmp(case, "butterfly_free", min(g) >= 0, via="arithmetic")], None


def ssvi(case):
    i = case["inputs"]
    rho, eta, gam, ths, ks = i["rho"], i["eta"], i["gamma"], i["thetas"], i["log_moneyness"]
    rows, phis = [], []
    for th in ths:
        phi = eta / (th ** gam * (1 + th) ** (1 - gam))
        phis.append(phi)
        a, b, m, sig = th / 2 * (1 - rho * rho), th * phi / 2, -rho / phi, math.sqrt(1 - rho * rho) / phi
        sec = svi_section(1.0, a, b, rho, m, sig)
        rows.append([w_of(sec, 1.0, k) for k in ks])
    m1 = [4 - th * p * (1 + abs(rho)) for th, p in zip(ths, phis)] + [4 - th * p * p * (1 + abs(rho)) for th, p in zip(ths, phis)]
    m2 = [1 + math.sqrt(1 - rho * rho) - rho * rho * (1 - gam) / (1 + th) for th in ths]
    return [cmp(case, "total_variance", rows), cmp(case, "butterfly_free", min(m1) > 0, via="arithmetic"),
            cmp(case, "calendar_free", min(m2) >= 0, via="arithmetic")], None


RUN = {"fx.forward.outright": lambda c: (fx_forward(c), None), "eq.forward.outright": eq_forward,
       "vol.svi.evaluate": svi, "vol.ssvi.evaluate": ssvi}


def cases(op):
    for rel in SUITES[op]:
        for c in json.loads((GOLD / rel).read_text(encoding="utf-8"))["cases"]:
            if c["operation"] == op and c["expected"]["status"] == "ok":
                yield rel, c


def run():
    res = {"generator": "oracle/python/outside_validation.py", "library": f"QuantLib {ql.__version__}", "operations": {}}
    bad = []
    for op in SUITES:
        ent = []
        for rel, c in cases(op):
            outs, why = RUN[op](c)
            if outs is None:
                ent.append({"case_id": c["case_id"], "suite": rel, "covered": False, "reason": why})
                continue
            ok = all(o["pass"] for o in outs)
            cls = "library-object" if all(o["via"] == "library" for o in outs) else "library-primitive"
            ent.append({"case_id": c["case_id"], "suite": rel, "covered": True, "pass": ok, "class": cls, "tag": TAG[op], "outputs": outs})
            if not ok and c["case_id"] in KNOWN:
                ent[-1]["known_difference"] = KNOWN[c["case_id"]]
                probe = json.loads(json.dumps(c))
                probe["inputs"]["dividends"] = [d for d in probe["inputs"]["dividends"] if d["ex_date"] > probe["inputs"]["as_of"]]
                ent[-1]["probe_without_as_of_dividend_pass"] = all(o["pass"] for o in RUN[op](probe)[0])
            elif not ok:
                bad.append(c["case_id"])
        res["operations"][op] = {"cases": len(ent), "passed": sum(e.get("pass", False) for e in ent), "entries": ent}
    return res, bad


def apply(res):
    passing = {e["case_id"]: e["tag"] for o in res["operations"].values() for e in o["entries"] if e.get("pass")}
    for rel in sorted({r for v in SUITES.values() for r in v}):
        p = GOLD / rel
        doc = json.loads(p.read_text(encoding="utf-8"))
        n = 0
        for c in doc["cases"]:
            t = passing.get(c["case_id"])
            if t and t not in c["verified_by"]:
                c["verified_by"].append(t)
                n += 1
        if n:
            p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"{rel}: {n} cases tagged")


def check():
    reg = json.loads(OUT.read_text(encoding="utf-8"))
    passing = {e["case_id"] for o in reg["operations"].values() for e in o["entries"] if e.get("pass")}
    tags = set(TAG.values()) - {QLV}
    bad = [c["case_id"] for op in SUITES for _, c in cases(op) if set(c["verified_by"]) & tags and c["case_id"] not in passing]
    print("outside_validation check:", "ok" if not bad else f"tagged without a passing entry: {bad}")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return check()
    res, bad = run()
    for op, o in res["operations"].items():
        print(f"{op}: {o['passed']} of {o['cases']} pass" + "".join(f"; {e['case_id']} not covered: {e['reason']}" for e in o["entries"] if not e["covered"]))
    if bad:
        for op, o in res["operations"].items():
            for e in o["entries"]:
                if e.get("covered") and not e["pass"]:
                    print("DISAGREE", e["case_id"], [(x["output"], x.get("max_abs_diff"), x["golden"] if not isinstance(x["golden"], list) else "...", x["outside"] if not isinstance(x["outside"], list) else "...") for x in e["outputs"] if not x["pass"]])
        return 1
    OUT.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    if a.apply:
        apply(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
