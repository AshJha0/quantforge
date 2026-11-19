import sys
R = str(__import__("pathlib").Path(__file__).resolve().parents[2])
sys.path.insert(0, R + "/oracle/python")
import k8_acceptance as ka
import QuantLib as ql
i = dict(ka.inputs(0)); i["exercise_times"] = [1.0]
ref = ql.Date(1, 1, 2025); dc = ql.Actual365Fixed(); day = lambda t: ref + round(t * 365.0)
ql.Settings.instance().evaluationDate = ref
def jam(dfs, info=False):
    curve = ql.DiscountCurve([ref] + [day(t) for t in i["curve"]["times"]], [1.0, *dfs], dc); hd = ql.YieldTermStructureHandle(curve)
    if info:
        return [curve.forwardRate(t, t, ql.Continuous, ql.NoFrequency).rate() for t in (0.9, 1.0, 1.1)]
    model = ql.HullWhite(hd, i["mean_reversion"], i["sigma"])
    index = ql.IborIndex("k8", ql.Period(365, ql.Days), 0, ql.EURCurrency(), ql.NullCalendar(), ql.Unadjusted, False, dc, hd)
    sched = ql.Schedule([day(i["start_years"])] + [day(t) for t in i["payment_times"]])
    swap = ql.VanillaSwap(ql.VanillaSwap.Payer, i["notional"], sched, i["fixed_rate"], dc, sched, index, 0.0, dc)
    sw = ql.Swaption(swap, ql.EuropeanExercise(day(1.0))); sw.setPricingEngine(ql.JamshidianSwaptionEngine(model, hd)); return sw.NPV()
dfs = list(i["curve"]["discount_factors"])
print("fwd at 0.9,1.0,1.1:", jam(dfs, True))
up = list(dfs); up[0] *= 1.01; print("fwd, DF1 up 1%:", jam(up, True))
for h in (1e-6, 1e-5, 1e-4, 1e-3, 1e-2):
    up = list(dfs); up[0] *= 1 + h; dn = list(dfs); dn[0] *= 1 - h
    print(h, (jam(up) - jam(dn)) / (2 * h * dfs[0]))
