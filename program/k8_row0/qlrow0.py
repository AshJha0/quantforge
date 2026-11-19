import json, sys, time
R = str(__import__("pathlib").Path(__file__).resolve().parents[2])
sys.path.insert(0, R + "/oracle/python")
import k8_acceptance as ka
import QuantLib as ql
out = {"quantlib": ql.__version__, "note": "row 1 (node 0.4986y = day 182) central bump h=1e-4 relative, ka.ql_price unchanged", "rows": []}
def d(i, j, tg, xg, h=1e-4):
    dfs = list(i["curve"]["discount_factors"]); a, s = i["mean_reversion"], i["sigma"]
    up = list(dfs); up[j] *= 1 + h; dn = list(dfs); dn[j] *= 1 - h
    return (ka.ql_price(i, up, a, s, tg, xg) - ka.ql_price(i, dn, a, s, tg, xg)) / (2 * h * dfs[j])
grids = [(g, 801) for g in (1000, 2000, 4000, 8000, 16000, 1825, 3650, 7300, 14600)] + [(8000, 3201), (7300, 3201)]
if len(sys.argv) > 1: grids = grids[:1]
for c in range(3):
    i = ka.inputs(c)
    for tg, xg in grids:
        if c > 0 and (tg, xg) not in ((8000, 801), (7300, 801), (8000, 3201), (7300, 3201)): continue
        t0 = time.time(); r1 = d(i, 0, tg, xg); r2 = d(i, 1, tg, xg) if c == 0 else None
        out["rows"].append({"case": c + 1, "tGrid": tg, "xGrid": xg, "day182_on_time_grid": tg % 1825 == 0, "row1": r1, "row2": r2})
        print(c + 1, tg, xg, r1, r2, round(time.time() - t0, 1), flush=True)
        json.dump(out, open(R + "/program/k8_row0/qlrow0.json", "w"), indent=1)
# European control: one exercise date, analytic Jamshidian engine against the FD engine
i = dict(ka.inputs(0)); i["exercise_times"] = [1.0]
def jam(dfs):
    ref = ql.Date(1, 1, 2025); dc = ql.Actual365Fixed(); day = lambda t: ref + round(t * 365.0)
    ql.Settings.instance().evaluationDate = ref
    curve = ql.DiscountCurve([ref] + [day(t) for t in i["curve"]["times"]], [1.0, *dfs], dc); hd = ql.YieldTermStructureHandle(curve)
    model = ql.HullWhite(hd, i["mean_reversion"], i["sigma"])
    index = ql.IborIndex("k8", ql.Period(365, ql.Days), 0, ql.EURCurrency(), ql.NullCalendar(), ql.Unadjusted, False, dc, hd)
    sched = ql.Schedule([day(i["start_years"])] + [day(t) for t in i["payment_times"]])
    swap = ql.VanillaSwap(ql.VanillaSwap.Payer, i["notional"], sched, i["fixed_rate"], dc, sched, index, 0.0, dc)
    sw = ql.Swaption(swap, ql.EuropeanExercise(day(1.0))); sw.setPricingEngine(ql.JamshidianSwaptionEngine(model, hd)); return sw.NPV()
dfs = list(i["curve"]["discount_factors"]); h = 1e-4
eu = {}
for j in (0, 1):
    up = list(dfs); up[j] *= 1 + h; dn = list(dfs); dn[j] *= 1 - h
    eu[f"row{j+1}_jamshidian"] = (jam(up) - jam(dn)) / (2 * h * dfs[j])
    eu[f"row{j+1}_fd_8000_801"] = d(i, j, 8000, 801); eu[f"row{j+1}_fd_7300_801"] = d(i, j, 7300, 801)
out["european_one_exercise_case1"] = eu; print(eu)
json.dump(out, open(R + "/program/k8_row0/qlrow0.json", "w"), indent=1)
