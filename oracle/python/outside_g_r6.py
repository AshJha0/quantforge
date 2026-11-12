"""R6-13 oracle lane 2: per-case outside checks for the stage G suites that had none (bermudan_g, callable_g,
aadladder_g, hwcal_g). Reads the committed goldens; never writes them.

Each check uses a QuantLib 1.44 object on its own discretisation (FD or tree) or a scipy optimiser on QuantLib
pricing, never the spec's scheme. The goldens are a pinned first-order scheme, so the gap to a converged library
value is the scheme's discretisation error. The tolerance per case is fixed by the method before comparison:

  tol = 3 * e_lib_grid + 3 * e_lib_conv + 1e-6 * |value|

  e_lib_grid  QuantLib's own implicit-Euler FD at the golden's grid against QuantLib at a fine grid: the size of a
              first-order discretisation error at that grid, measured by the library (not by the spec scheme)
  e_lib_conv  QuantLib fine against QuantLib finer (or tree n against tree 2n): the library's own residual error

Writes oracle/OUTSIDE_G_R6.json (per case: library values, gap, tolerance, pass). A case counts only if every
compared output passes. Disagreements are reported, goldens are not changed.

    cd oracle/python && uv run python -W ignore outside_g_r6.py
"""
import json
import math
from pathlib import Path

import QuantLib as ql
from scipy.optimize import minimize_scalar
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GOLD = ROOT / "datasets" / "golden" / "stage_g"
TODAY = ql.Date(10, 11, 2026)
ql.Settings.instance().evaluationDate = TODAY
DC = ql.Actual365Fixed()
LIB = f"QuantLib {ql.__version__}"


def d(t):
    return TODAY + int(round(t * 365))


def curve(c, bump=None):
    dfs = list(c["discount_factors"])
    if bump is not None:
        i, h = bump
        dfs[i] += h
    h = ql.YieldTermStructureHandle(ql.DiscountCurve([TODAY] + [d(t) for t in c["times"]], [1.0] + dfs, DC))
    h.enableExtrapolation()
    return h


def cases(suite):
    g = json.loads((GOLD / f"{suite}.json").read_text(encoding="utf-8"))
    return [c for c in (g["cases"] if isinstance(g, dict) else g)]


# ------------------------------------------------------------------------------------------------ Bermudan swaption
def berm_ql(inp, t_grid, x_grid, scheme="implicit", a=None, s=None, bump=None):
    h = curve(inp["curve"], bump)
    model = ql.HullWhite(h, inp["mean_reversion"] if a is None else a, inp["sigma"] if s is None else s)
    dates = [d(inp["start_years"])] + [d(t) for t in inp["payment_times"]]
    sched = ql.Schedule(dates, ql.NullCalendar(), ql.Unadjusted)
    idx = ql.IborIndex("X", ql.Period(1, ql.Years), 0, ql.USDCurrency(), ql.NullCalendar(), ql.Unadjusted, False, DC, h)
    typ = ql.Swap.Payer if inp["swaption_type"] == "PAYER" else ql.Swap.Receiver
    sw = ql.VanillaSwap(typ, inp["notional"], sched, inp["fixed_rate"], DC, sched, idx, 0.0, DC)
    sw.setPricingEngine(ql.DiscountingSwapEngine(h))
    o = ql.Swaption(sw, ql.BermudanExercise([d(t) for t in inp["exercise_times"]]))
    sd = ql.FdmSchemeDesc.ImplicitEuler() if scheme == "implicit" else ql.FdmSchemeDesc.Douglas()
    inv_eps = float(norm.cdf(-inp["grid"]["width"]))
    o.setPricingEngine(ql.FdHullWhiteSwaptionEngine(model, t_grid, x_grid, 0, inv_eps, sd))
    return o.NPV()


def berm_values(inp, fn):
    """(value at golden grid, fine, finer) for a scalar function fn(t_grid, x_grid, scheme)."""
    g = inp["grid"]
    tg = max(1, math.ceil(g["steps_per_year"] * inp["exercise_times"][-1]))
    return fn(tg, g["nx"], "implicit"), fn(800, 801, "cn"), fn(1600, 1601, "cn")


def tol(grid_v, fine, finer, value):
    return 3 * abs(grid_v - fine) + 3 * abs(fine - finer) + 1e-6 * abs(value)


def check(name, gold, grid_v, fine, finer):
    t = tol(grid_v, fine, finer, gold)
    return {"output": name, "golden": gold, "ql_golden_grid_implicit": grid_v, "ql_fine": fine, "ql_finer": finer,
            "gap": gold - fine, "tolerance": t, "pass": abs(gold - fine) <= t}


def bermudan():
    out = []
    for c in cases("bermudan_g"):
        if c["expected"]["status"] != "ok":
            continue
        inp = c["inputs"]
        v = berm_values(inp, lambda tg, xg, sc: berm_ql(inp, tg, xg, sc))
        out.append({"case_id": c["case_id"], "checks": [check("price", c["expected"]["outputs"]["price"], *v)]})
    return out


def aadladder():
    out = []
    for c in cases("aadladder_g"):
        if c["expected"]["status"] != "ok":
            continue
        inp, o = c["inputs"], c["expected"]["outputs"]
        chk = [check("price", o["price"], *berm_values(inp, lambda tg, xg, sc: berm_ql(inp, tg, xg, sc)))]
        # central bumps on the QuantLib engine (bump-and-revalue: a different formulation from the golden's adjoint)
        ha, hs = 1e-4, 1e-5
        da = lambda tg, xg, sc: (berm_ql(inp, tg, xg, sc, a=inp["mean_reversion"] + ha) - berm_ql(inp, tg, xg, sc, a=inp["mean_reversion"] - ha)) / (2 * ha)  # noqa: E731
        ds = lambda tg, xg, sc: (berm_ql(inp, tg, xg, sc, s=inp["sigma"] + hs) - berm_ql(inp, tg, xg, sc, s=inp["sigma"] - hs)) / (2 * hs)  # noqa: E731
        chk.append(check("d_price_d_mean_reversion", o["d_price_d_mean_reversion"], *berm_values(inp, da)))
        chk.append(check("d_price_d_sigma", o["d_price_d_sigma"], *berm_values(inp, ds)))
        hd = 1e-6
        for i, gv in enumerate(o["d_price_d_discount_factors"]):
            ddf = lambda tg, xg, sc, i=i: (berm_ql(inp, tg, xg, sc, bump=(i, hd)) - berm_ql(inp, tg, xg, sc, bump=(i, -hd))) / (2 * hd)  # noqa: E731
            r = check(f"d_price_d_discount_factors[{i}]", gv, *berm_values(inp, ddf))
            # pillars beyond the last payment carry no sensitivity; bump noise there is round-off of order notional*eps/hd
            r["tolerance"] = max(r["tolerance"], 1e-9 * inp["notional"] / hd * 1e-3)
            r["pass"] = abs(r["gap"]) <= r["tolerance"]
            chk.append(r)
        out.append({"case_id": c["case_id"], "checks": chk})
    return out


# ------------------------------------------------------------------------------------------------ callable bond
def callable_tree(inp, steps):
    h = curve(inp["curve"])
    model = ql.HullWhite(h, inp["mean_reversion"], inp["sigma"])
    dates = [TODAY] + [d(t) for t in inp["payment_times"]]
    sched = ql.Schedule(dates, ql.NullCalendar(), ql.Unadjusted)
    calls = ql.CallabilitySchedule()
    for t in inp["call_times"]:
        calls.append(ql.Callability(ql.BondPrice(100.0 * inp["call_price"], ql.BondPrice.Clean), ql.Callability.Call, d(t)))
    b = ql.CallableFixedRateBond(0, 100.0, sched, [inp["coupon_rate"]], DC, ql.Unadjusted, 100.0, TODAY, calls)
    b.setPricingEngine(ql.TreeCallableFixedRateBondEngine(model, steps))
    return b.NPV() * inp["notional"] / 100.0


def callable_():
    ev = json.loads((ROOT / "oracle" / "BERMUDAN_EVIDENCE_G.json").read_text(encoding="utf-8"))
    out = []
    for c in cases("callable_g"):
        if c["expected"]["status"] != "ok":
            continue
        inp = c["inputs"]
        gold = c["expected"]["outputs"]["price"]
        t1, t2 = callable_tree(inp, 2000), callable_tree(inp, 4000)
        # golden-grid error yardstick: QuantLib has no FD callable-bond engine, so the scheme's first-order error at
        # this grid is taken from QuantLib's straight bond (the call-free limit), scaled: the golden's own
        # straight-bond limit error at 100 steps/year (BERMUDAN_EVIDENCE_G callable_straight_limit[2]), per 100 notional
        g = inp["grid"]
        lev = {25: 0, 50: 1, 100: 2, 200: 3}.get(g["steps_per_year"])
        e_grid = abs(ev["callable_straight_limit"]["errors"][lev]) * inp["notional"] / 100.0
        t = 3 * e_grid + 3 * abs(t1 - t2) + 1e-6 * abs(gold)
        out.append({"case_id": c["case_id"], "checks": [{"output": "price", "golden": gold, "ql_tree_2000": t1, "ql_tree_4000": t2,
                    "e_grid_straight_limit": e_grid, "gap": gold - t2, "tolerance": t, "pass": abs(gold - t2) <= t}]})
    return out


# ------------------------------------------------------------------------------------------------ HW calibration
def ql_jam(c, a, s, q):
    m = ql.HullWhite(curve(c), a, s)
    T0, Ts, K = q["expiry_years"], q["payment_times"], q["fixed_rate"]
    acc = [Ts[0] - T0] + [Ts[i] - Ts[i - 1] for i in range(1, len(Ts))]
    cf = [K * x for x in acc]
    cf[-1] += 1
    f = lambda r: sum(ci * m.discountBond(T0, Ti, r) for ci, Ti in zip(cf, Ts)) - 1  # noqa: E731
    rs = ql.Brent().solve(f, 1e-15, 0.0, -0.5, 0.5)
    t = ql.Option.Call if q["swaption_type"] == "RECEIVER" else ql.Option.Put
    return sum(ci * m.discountBondOption(t, m.discountBond(T0, Ti, rs), T0, Ti) for ci, Ti in zip(cf, Ts))


def hwcal():
    out = []
    for c in cases("hwcal_g"):
        if c["expected"]["status"] != "ok":
            continue
        inp, o = c["inputs"], c["expected"]["outputs"]
        obj = lambda s: sum((ql_jam(inp["curve"], inp["mean_reversion"], s, q) - q["target_price"]) ** 2 for q in inp["swaptions"])  # noqa: E731
        r = minimize_scalar(obj, bounds=(1e-3, 0.04), method="bounded", options={"xatol": 1e-14, "maxiter": 500})
        s = float(r.x)
        fitted = [ql_jam(inp["curve"], inp["mean_reversion"], s, q) for q in inp["swaptions"]]
        rmse = math.sqrt(obj(s) / len(fitted))
        # tolerance: bounded Brent stops at xatol; the objective is flat at the optimum so sigma is judged at the
        # optimiser's own resolution (sqrt(machine eps) relative on a quadratic minimum), prices at their curvature
        chk = [{"output": "sigma", "golden": o["sigma"], "outside": s, "gap": o["sigma"] - s, "tolerance": 2e-8 * s,
                "pass": abs(o["sigma"] - s) <= 2e-8 * s}]
        for i, (gv, fv) in enumerate(zip(o["fitted_prices"], fitted)):
            t = 1e-12 + 1e-7 * abs(gv)
            chk.append({"output": f"fitted_prices[{i}]", "golden": gv, "outside": fv, "gap": gv - fv, "tolerance": t, "pass": abs(gv - fv) <= t})
        t = 1e-9 if o["rmse"] < 1e-12 else 1e-6 * o["rmse"]
        chk.append({"output": "rmse", "golden": o["rmse"], "outside": rmse, "gap": o["rmse"] - rmse, "tolerance": t, "pass": abs(o["rmse"] - rmse) <= t})
        out.append({"case_id": c["case_id"], "checks": chk})
    return out


SUITES = {
    "bermudan_g": (bermudan, f"{LIB} FdHullWhiteSwaptionEngine (Crank-Nicolson/Douglas 800x801 and 1600x1601; implicit Euler at the golden grid as the error yardstick)"),
    "aadladder_g": (aadladder, f"{LIB} FdHullWhiteSwaptionEngine, central bump-and-revalue for every gradient entry"),
    "callable_g": (callable_, f"{LIB} TreeCallableFixedRateBondEngine (2000 and 4000 steps)"),
    "hwcal_g": (hwcal, f"scipy minimize_scalar (bounded Brent) on {LIB} HullWhite discountBondOption (Jamshidian)"),
}


def main():
    doc = {"rule": "per case; a case passes only if every compared output is within its stated tolerance", "suites": {}}
    for name, (fn, lib) in SUITES.items():
        rs = fn()
        for r in rs:
            r["pass"] = all(x["pass"] for x in r["checks"])
        doc["suites"][name] = {"library": lib, "cases": rs}
        bad = [r["case_id"] for r in rs if not r["pass"]]
        print(f"{name}: {sum(r['pass'] for r in rs)} of {len(rs)} ok cases pass; fail {bad}")
        for r in rs:
            for x in r["checks"]:
                if not x["pass"] or x["output"] == "price":
                    print(f"   {r['case_id']} {x['output']}: golden {x['golden']:.10g} gap {x['gap']:.3e} tol {x['tolerance']:.3e} {'ok' if x['pass'] else 'FAIL'}")
    (ROOT / "oracle" / "OUTSIDE_G_R6.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
