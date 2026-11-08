"""Outside-oracle verifier for stage E, spec A slices (plan rule 11.2.5).

As outside_d.py: for each golden case it reads only the case's inputs, builds the result from QuantLib's own
objects (taken only from qf_oracle/convmap_e_a.py), and compares every output with the golden under the
case's own tolerance. A case counts only if every output is matched, or is the spec's stated algebra on
matched QuantLib values or inputs, which the handler names. Nothing here reads the generator's replays.

Writes oracle/outside_register_e_a.json and oracle/OUTSIDE_E_A.md (coverage per suite, and the map).

    cd oracle/python && uv run python -W ignore outside_e_a.py [--write-map]
"""
import inspect
import json
import math
import re
import sys
from pathlib import Path

import QuantLib as ql

from qf_oracle import convmap_e_a as CM

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
import runner  # noqa: E402  (tolerance comparison only)

POLICY = runner.load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")
SUITES = ["surf_e", "lv_e", "fxs_e", "heston_e", "slv_e", "exotic_e", "american_e", "rulings_e_a"]  # spec A suites; later slices append


class Used:
    """Records the map rows a handler used, and any output it had to compute by the spec's own algebra (ruling E-A17)."""
    def __init__(self):
        self.rows = set()
        self.self_outputs = set()

    def __call__(self, row, *a):
        self.rows.add(row)
        return CM.obj(row, *a)


# ---------------------------------------------------------------- E1
def h_surface_check(u, x):
    """Total variance from QuantLib SviSmileSection; butterfly from the sign of QuantLib's numerical density;
    wing rules are the spec's algebra on the input parameters (asymptotic slopes, not a QuantLib quantity)."""
    u.self_outputs |= {"wing_violations", "arbitrage_free"}
    secs = [u("SVI.RAW", s["expiry_years"], 1.0, s["svi"]) for s in x["slices"]]
    ks = x["log_moneyness"]
    bf, cal, wing = [], [], []
    for j, sec in enumerate(secs):
        for i, k in enumerate(ks):
            if u("SVI.DENSITY", sec, math.exp(k)) < 0:
                bf.append({"expiry_index": j, "k_index": i})
    for j in range(1, len(secs)):
        for i, k in enumerate(ks):
            if secs[j].variance(math.exp(k)) < secs[j - 1].variance(math.exp(k)):
                cal.append({"expiry_index": j, "k_index": i})

    def asym(p):
        b, rho, a, m = p["b"], p["rho"], p["a"], p["m"]
        return b * (1 - rho), a + b * (1 - rho) * m, b * (1 + rho), a - b * (1 + rho) * m
    for j, s in enumerate(x["slices"]):
        sl, cl, sr, cr = asym(s["svi"])
        for side, v in (("LEFT", sl), ("RIGHT", sr)):
            if v >= 2:
                wing.append({"expiry_index": j, "side": side, "kind": "LEE"})
        if j:
            pl, pcl, pr, pcr = asym(x["slices"][j - 1]["svi"])
            for side, v, c, pv, pc in (("LEFT", sl, cl, pl, pcl), ("RIGHT", sr, cr, pr, pcr)):
                if (c < pc) if v == pv else (v < pv):
                    wing.append({"expiry_index": j, "side": side, "kind": "CALENDAR"})
    return {"butterfly_violations": bf, "calendar_violations": cal, "wing_violations": wing, "arbitrage_free": not (bf or cal or wing)}


def h_forward_vol(u, x):
    ref = ql.Date(6, 11, 2026)
    ql.Settings.instance().evaluationDate = ref
    days = [round(t * 365) for t in x["expiry_years"]]
    if any(abs(d / 365 - t) > 0 for d, t in zip(days, x["expiry_years"])):
        raise NotImplementedError("expiries not whole days on ACT/365F")
    c = u("VOL.CURVE", ref, [ref + d for d in days], x["vols"])
    Ts = x["expiry_years"]
    return {"forward_vols": [c.blackVol(Ts[0], 1.0)] + [c.blackForwardVol(Ts[i - 1], Ts[i], 1.0) for i in range(1, len(Ts))]}


def h_dynamics(u, x):
    T, S0, S1, r, q = x["expiry_years"], x["spot"], x["spot_shifted"], x["rate"], x["dividend_yield"]
    D = math.exp(-r * T)
    F0, F1 = S0 * math.exp((r - q) * T), S1 * math.exp((r - q) * T)
    sec0 = u("SVI.RAW", T, F0, x["svi"])
    sec1 = sec0 if x["rule"] == "STICKY_STRIKE" else u("SVI.RAW", T, F1, x["svi"])
    out = {"vols_base": [], "vols_shifted": [], "prices_base": [], "prices_shifted": [], "deltas": []}
    for K in x["strikes"]:
        v0, v1 = sec0.volatility(K), sec1.volatility(K)
        out["vols_base"].append(v0)
        out["vols_shifted"].append(v1)
        out["prices_base"].append(u("OPT.BLACK_FORMULA", x["option_type"], K, F0, v0 * math.sqrt(T), D))
        out["prices_shifted"].append(u("OPT.BLACK_FORMULA", x["option_type"], K, F1, v1 * math.sqrt(T), D))
        bc = u("OPT.BLACK_CALC", x["option_type"], K, F0, v0 * math.sqrt(T), D)
        dvds = 0.0
        if x["rule"] == "STICKY_DELTA":
            u.self_outputs.add("deltas")
            # spec: d sigma/dS = -(dsigma/dk)/S at fixed K; dsigma/dk from QuantLib's own smile, 4-point difference in k
            h = 1e-4
            vol = lambda kk: sec0.volatility(F0 * math.exp(kk))  # noqa: E731
            k0 = math.log(K / F0)
            dv = (-vol(k0 + 2 * h) + 8 * vol(k0 + h) - 8 * vol(k0 - h) + vol(k0 - 2 * h)) / (12 * h)
            dvds = -dv / S0
        out["deltas"].append(bc.delta(S0) + bc.vega(T) * dvds)
    return out


def h_volofvol(u, x):
    v = x["vols"]
    ch = [math.log(b / a) if x["method"] == "LOG" else b - a for a, b in zip(v, v[1:])]
    st = u("STAT.SAMPLE")
    for c in ch:
        st.add(c)
    return {"vol_of_vol": math.sqrt(x["periods_per_year"]) * st.standardDeviation(), "mean_change": st.mean()}


HANDLERS = {
    "vol.svi.surface_check": h_surface_check,
    "vol.forward.vol": h_forward_vol,
    "vol.smile.dynamics": h_dynamics,
    "vol.volofvol.measure": h_volofvol,
}


# ---------------------------------------------------------------- E3
def _fx(x):
    T = x["expiry_years"]
    return x["spot"], math.exp(-x["domestic_rate"] * T), math.exp(-x["foreign_rate"] * T), T


def h_fx_price(u, x):
    ref = ql.Date(6, 11, 2026)
    ql.Settings.instance().evaluationDate = ref
    d = round(x["expiry_years"] * 365)
    if d / 365 != x["expiry_years"]:
        raise NotImplementedError("expiry not whole days")
    pr = u("FX.GK", ref, x["spot"], x["domestic_rate"], x["foreign_rate"], x["vol"])
    o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if x["option_type"] == "CALL" else ql.Option.Put, x["strike"]), ql.EuropeanExercise(ref + d))
    o.setPricingEngine(ql.AnalyticEuropeanEngine(pr))
    N, S = x["notional"], x["spot"]
    return {"price": N * o.NPV(), "premium_pct_foreign": o.NPV() / S, "forward": S * pr.dividendYield().discount(ref + d) / pr.riskFreeRate().discount(ref + d),
            "delta": N * o.delta(), "gamma": N * o.gamma(), "vega": N * o.vega()}


def h_fx_from_strike(u, x):
    S, Dd, Df, T = _fx(x)
    sd = x["vol"] * math.sqrt(T)
    return {"deltas": {dt: u("FX.DELTA_CALC", x["option_type"], u("FX.DELTA_TYPE", dt), S, Dd, Df, sd).deltaFromStrike(x["strike"]) for dt in ("SPOT", "FORWARD", "SPOT_PA", "FORWARD_PA")}}


def h_fx_to_strike(u, x):
    S, Dd, Df, T = _fx(x)
    c = u("FX.DELTA_CALC", x["option_type"], u("FX.DELTA_TYPE", x["delta_type"]), S, Dd, Df, x["vol"] * math.sqrt(T))
    return {"strike": c.strikeFromDelta(x["delta"])}


def h_fx_atm(u, x):
    S, Dd, Df, T = _fx(x)
    c = u("FX.DELTA_CALC", "CALL", u("FX.DELTA_TYPE", x["delta_type"]), S, Dd, Df, x["vol"] * math.sqrt(T))
    return {"strike": c.atmStrike(u("FX.ATM_TYPE", x["atm_type"]))}


def h_fx_smile(u, x):
    S, Dd, Df, T = _fx(x)
    a, rr, bf, dl = x["atm_vol"], x["rr"], x["bf"], x["delta"]
    cv, pv = a + bf + rr / 2, a + bf - rr / 2
    dtq = u("FX.DELTA_TYPE", x["delta_type"])
    st = lambda ot, v, d: u("FX.DELTA_CALC", ot, dtq, S, Dd, Df, v * math.sqrt(T)).strikeFromDelta(d)  # noqa: E731
    return {"atm_strike": u("FX.DELTA_CALC", "CALL", dtq, S, Dd, Df, a * math.sqrt(T)).atmStrike(u("FX.ATM_TYPE", x["atm_type"])),
            "call_vol": cv, "put_vol": pv, "call_strike": st("CALL", cv, dl), "put_strike": st("PUT", pv, -dl)}


HANDLERS.update({"fx.option.price": h_fx_price, "fx.delta.from_strike": h_fx_from_strike, "fx.delta.to_strike": h_fx_to_strike,
                 "fx.atm.strike": h_fx_atm, "fx.smile.from_quotes": h_fx_smile})


# ---------------------------------------------------------------- E2
def _opt_prices(x, eng, ref):
    d = round(x["expiry_years"] * 365)
    if d / 365 != x["expiry_years"]:
        raise NotImplementedError("expiry not whole days")
    out = []
    for K in x["strikes"]:
        o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call if x["option_type"] == "CALL" else ql.Option.Put, K), ql.EuropeanExercise(ref + d))
        o.setPricingEngine(eng)
        out.append(o.NPV())
    return {"prices": out}


def _curves(u, x):
    ref = ql.Date(6, 11, 2026)
    ql.Settings.instance().evaluationDate = ref
    return ref, u("TS.FLAT_CONT", ref, x["rate"]), u("TS.FLAT_CONT", ref, x["dividend_yield"])


def h_heston(u, x):
    ref, rt, qt = _curves(u, x)
    return _opt_prices(x, u("HESTON.ENGINE", ql.HestonModel(u("HESTON.PROCESS", rt, qt, x["spot"], x["heston"]))), ref)


def h_bates(u, x):
    ref, rt, qt = _curves(u, x)
    return _opt_prices(x, u("BATES.ENGINE", ql.BatesModel(u("BATES.PROCESS", rt, qt, x["spot"], x["heston"], x["jumps"]))), ref)




HANDLERS.update({"vol.heston.price": h_heston, "vol.bates.price": h_bates})


# ---------------------------------------------------------------- E5
REF = ql.Date(6, 11, 2026)


def _days(t):
    d = round(t * 365)
    if d / 365 != t:
        raise NotImplementedError("time not whole days")
    return d


def _bsm(u, x):
    ql.Settings.instance().evaluationDate = REF
    return u("BSM.PROCESS", REF, x["spot"], x["rate"], x["dividend_yield"], x["vol"])


def h_digital(u, x):
    o = ql.VanillaOption(u("PAY.DIGITAL", x["payoff"], u("OPT.TYPE", x["option_type"]), x["strike"], x["cash"]), ql.EuropeanExercise(REF + _days(x["expiry_years"])))
    o.setPricingEngine(ql.AnalyticEuropeanEngine(_bsm(u, x)))
    return {"price": o.NPV()}


def h_barrier(u, x):
    pr = _bsm(u, x)
    o = ql.BarrierOption(u("BARRIER.TYPE", x["barrier_type"]), x["barrier"], x["rebate"], ql.PlainVanillaPayoff(u("OPT.TYPE", x["option_type"]), x["strike"]),
                         ql.EuropeanExercise(REF + _days(x["expiry_years"])))
    o.setPricingEngine(u("ENG.BARRIER", pr))
    return {"price": o.NPV()}


def h_asian(u, x):
    pr = _bsm(u, x)
    pay = ql.PlainVanillaPayoff(u("OPT.TYPE", x["option_type"]), x["strike"])
    ex = ql.EuropeanExercise(REF + _days(x["expiry_years"]))
    if x["averaging"] == "CONTINUOUS":
        o = ql.ContinuousAveragingAsianOption(ql.Average.Geometric, pay, ex)
        o.setPricingEngine(u("ENG.ASIAN_GEO_CONT", pr))
    else:
        o = ql.DiscreteAveragingAsianOption(ql.Average.Geometric, 1.0, 0, [REF + _days(t) for t in x["fixing_years"]], pay, ex)
        o.setPricingEngine(u("ENG.ASIAN_GEO_DISC", pr))
    return {"price": o.NPV()}


def h_lookback(u, x):
    pr = _bsm(u, x)
    o = ql.ContinuousFloatingLookbackOption(x["running_extreme"], ql.FloatingTypePayoff(u("OPT.TYPE", x["option_type"])), ql.EuropeanExercise(REF + _days(x["expiry_years"])))
    o.setPricingEngine(u("ENG.LOOKBACK_FLOAT", pr))
    return {"price": o.NPV()}


def h_quanto(u, x):
    ql.Settings.instance().evaluationDate = REF
    pr = u("BSM.PROCESS", REF, x["spot"], x["domestic_rate"], x["dividend_yield"], x["vol"])
    o = ql.QuantoVanillaOption(ql.PlainVanillaPayoff(u("OPT.TYPE", x["option_type"]), x["strike"]), ql.EuropeanExercise(REF + _days(x["expiry_years"])))
    o.setPricingEngine(u("ENG.QUANTO", pr, REF, x["foreign_rate"], x["fx_vol"], x["correlation"]))
    return {"price": o.NPV()}


def h_chooser(u, x):
    pr = _bsm(u, x)
    o = ql.SimpleChooserOption(REF + _days(x["choose_years"]), x["strike"], ql.EuropeanExercise(REF + _days(x["expiry_years"])))
    o.setPricingEngine(u("ENG.CHOOSER", pr))
    return {"price": o.NPV()}


def h_kirk(u, x):
    ql.Settings.instance().evaluationDate = REF
    o = ql.BasketOption(ql.SpreadBasketPayoff(ql.PlainVanillaPayoff(ql.Option.Call, x["strike"])), ql.EuropeanExercise(REF + _days(x["expiry_years"])))
    o.setPricingEngine(u("ENG.KIRK", REF, x["forward_1"], x["forward_2"], x["rate"], x["vol_1"], x["vol_2"], x["correlation"]))
    return {"price": o.NPV()}


def h_baw(u, x):
    pr = _bsm(u, x)
    o = ql.VanillaOption(ql.PlainVanillaPayoff(u("OPT.TYPE", x["option_type"]), x["strike"]), ql.AmericanExercise(REF, REF + _days(x["expiry_years"])))
    o.setPricingEngine(u("ENG.BAW", pr))
    return {"price": o.NPV()}


HANDLERS.update({"exotic.digital.price": h_digital, "exotic.barrier.price": h_barrier, "exotic.asian.geometric": h_asian, "exotic.lookback.floating": h_lookback,
                 "exotic.quanto.price": h_quanto, "exotic.chooser.price": h_chooser, "exotic.spread.kirk": h_kirk, "exotic.american.baw": h_baw})

NO_ORACLE = {
    "exotic.american.crr": "spec uses the Hull CRR probability (e^{(r-q)dt} - d)/(u - d); the QuantLib crr tree uses 1/2 + drift dt/(2 dx), so values differ. Checked by replay and the Black-Scholes limit",
    "exotic.american.fd": "reference scheme judged as a recipe; checked against a 2000-step tree within 2e-2",
    "exotic.basket.moment": "QuantLib has no moment-matched arithmetic basket engine; 30-digit mpmath and the perfect-correlation limit",
    "vol.merton.price": "the QuantLib 1.44 Python wheel does not expose JumpDiffusionEngine or Merton76Process pricing; checked by Poisson series, Lewis at 256 nodes and 30-digit mpmath",
    "vol.heston.cf": "QuantLib does not expose the characteristic function; checked against 30-digit mpmath",
    "vol.slv.leverage": "a reference scheme, judged as a recipe; QuantLib HestonSLVFDMModel uses another grid and scheme, so it cannot reproduce the numbers",
    "vol.ssvi.to_svi": "QuantLib has no SSVI; checked by replay through vol.ssvi.evaluate",
    "vol.svi.fit_surface": "fit judged on known-truth parameters; QuantLib's SviInterpolatedSmileSection fits by its own optimiser path",
    "vol.local.dupire": "QuantLib's LocalVolSurface needs a BlackVolTermStructure; none reproduces SVI slices linear in total variance. Checked by a 40-digit price-based Dupire",
}


def judge(case, got):
    exp = case["expected"]["outputs"]
    if set(got) != set(exp):
        return False, f"keys {sorted(got)} vs {sorted(exp)}"
    cls = POLICY[case["tolerance_class"]]
    per = case.get("output_classes", {})
    msgs = []
    for k, e in exp.items():
        c = POLICY[per[k]] if k in per else cls
        msgs += runner.compare(got[k], e, c, None if k in per else case.get("tolerance_limit"), k)
    return not msgs, "; ".join(msgs[:2])


def verify(show=True):
    reg, table = [], []
    global partial
    partial = []
    for suite in SUITES:
        p = ROOT / "datasets" / "golden" / "stage_e" / f"{suite}.json"
        if not p.exists():
            continue
        cases = json.loads(p.read_text(encoding="utf-8"))["cases"]
        k = 0
        for c in cases:
            h = HANDLERS.get(c["operation"])
            if not h or c["expected"]["status"] != "ok":
                continue
            u = Used()
            try:
                ok, why = judge(c, h(u, c["inputs"]))
            except (NotImplementedError, RuntimeError) as e:
                ok, why = False, str(e)
            if ok and u.self_outputs:
                partial.append({"case_id": c["case_id"], "operation": c["operation"], "outputs_self": sorted(u.self_outputs)})
            elif ok:
                k += 1
                reg.append({"case_id": c["case_id"], "operation": c["operation"], "library": CM.LIBRARY, "version": CM.VERSION,
                            "convention_rows": sorted(u.rows), "map_review": CM.REVIEW})
            elif show:
                print(f"  not verified {c['case_id']} {c['operation']}: {why}")
        table.append((suite, k, len(cases)))
    return reg, table


def map_lines():
    L = ["## Convention map (rule 11.2.5)", "", f"QuantLib {CM.VERSION}. Review: {CM.REVIEW}, self-assessment, not an outside review. "
         "Written from `oracle/python/qf_oracle/convmap_e_a.py`.", "", "| Row | Spec | QuantLib object | Note |", "|---|---|---|---|"]
    for k, (spec, fn, nt) in CM.ROWS.items():
        src = inspect.getsource(fn).strip()
        m = re.search(r"lambda[^:]*:\s*(.*)", src)
        body = (m.group(1).rstrip(" ),") if m else src).replace("|", "\\|")
        L.append(f"| `{k}` | {spec} | `{body[:110]}` | {nt} |")
    return L


def main():
    reg, table = verify()
    k, n = sum(t[1] for t in table), sum(t[2] for t in table)
    L = ["# Stage E spec A: outside-oracle coverage", "", "Written by `oracle/python/outside_e_a.py`. A case counts only if QuantLib, built from the objects in the map below, "
         "reproduces every output within the case's own tolerance, and every output is a QuantLib value or plain arithmetic on QuantLib values (ruling E-A17). "
         "Cases where QuantLib matches but some output is the spec's own algebra (SVI wing lists, the sticky-delta smile term) are listed as partly outside and not counted. Error cases are in the denominator and never count. Register: `oracle/outside_register_e_a.json`.", "",
         "| Suite | Outside-oracle cases | Cases | Share |", "|---|---|---|---|"]
    L += [f"| `{s}` | {a} | {b} | {100 * a / b:.0f}% |" for s, a, b in table]
    L += [f"| partly outside, not counted | {len(partial)} | | |"]
    L += [f"| **spec A total** | **{k}** | **{n}** | **{100 * k / max(n, 1):.1f}%** |", "", "Operations with no QuantLib route:", ""]
    L += [f"- `{op}`: {why}" for op, why in NO_ORACLE.items()]
    L += [""] + map_lines() + [""]
    (ROOT / "oracle" / "OUTSIDE_E_A.md").write_text("\n".join(L), encoding="utf-8", newline="\n")
    (ROOT / "oracle" / "outside_register_e_a.json").write_text(json.dumps({"rule": "plan 11.2.5", "library": CM.LIBRARY, "version": CM.VERSION, "map_review": CM.REVIEW,
                                                                         "cases": reg, "partly_outside_not_counted": partial}, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L[:len(table) + 8]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
