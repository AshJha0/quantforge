"""R6-13 oracle lane 2: discrete-monitoring barrier rows of barrier_g against QuantLib 1.44 MCBarrierEngine.

The golden prices a discretely monitored barrier by the Broadie-Glasserman-Kou continuity correction (a shifted
barrier in the continuous closed form). The outside value is QuantLib's own Monte Carlo barrier engine with one time
step per monitoring date and no Brownian-bridge correction (isBiased=True), so the barrier is checked only on the
monitoring dates: the exact discrete contract, a different formulation. Pseudo-random, antithetic, fixed seed.

Tolerance: 3 Monte Carlo standard errors (the repo's own R9 acceptance rule). BGK carries an approximation error of
o(1/sqrt(m)); rows where it exceeds 3 SE are reported as gaps of the approximation, not counted, and the golden is
not changed. Rows with a rebate are skipped (QuantLib's MC engine pays no rebate).
Merges its result into oracle/OUTSIDE_G_R6.json under "barrier_g".

    cd oracle/python && uv run python -W ignore outside_g_barrier_r6.py
"""
import json
import math
from pathlib import Path

import QuantLib as ql

ROOT = Path(__file__).resolve().parents[2]
TODAY = ql.Date(10, 11, 2026)
ql.Settings.instance().evaluationDate = TODAY
DC = ql.Actual365Fixed()
PATHS = 200_000


def mc(inp):
    n = math.floor(inp["monitoring_per_year"] * inp["expiry_years"] + 0.5)
    T = inp["expiry_years"]
    days = int(round(T * 365))
    ex = TODAY + days
    tc = DC.yearFraction(TODAY, ex)
    bt = {"DOWN_OUT": ql.Barrier.DownOut, "DOWN_IN": ql.Barrier.DownIn, "UP_OUT": ql.Barrier.UpOut, "UP_IN": ql.Barrier.UpIn}
    opt = ql.BarrierOption(bt[inp["barrier_type"]], inp["barrier"], 0.0,
                           ql.PlainVanillaPayoff(ql.Option.Call if inp["option_type"] == "CALL" else ql.Option.Put, inp["strike"]),
                           ql.EuropeanExercise(ex))
    ts = lambda r: ql.YieldTermStructureHandle(ql.FlatForward(TODAY, r, DC))  # noqa: E731
    proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(inp["spot"])), ts(inp["dividend_yield"]), ts(inp["rate"]),
                                        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(TODAY, ql.NullCalendar(), inp["vol"], DC)))
    eng = ql.MCPRBarrierEngine(proc, timeSteps=n, brownianBridge=False, antitheticVariate=True,
                               requiredSamples=PATHS, seed=20261112, isBiased=True)
    opt.setPricingEngine(eng)
    assert abs(tc - T) < 1e-12, "expiry must be a whole number of days"
    return opt.NPV(), opt.errorEstimate()


def main():
    g = json.loads((ROOT / "datasets" / "golden" / "stage_g" / "barrier_g.json").read_text(encoding="utf-8"))
    res = []
    for c in g["cases"]:
        i = c["inputs"]
        if c["expected"]["status"] != "ok":
            continue
        if i.get("monitoring", "CONTINUOUS") == "CONTINUOUS":
            from gen_stage_g_w1 import ql_barrier  # QuantLib AnalyticBarrierEngine, as counted before R6
            q, gold = ql_barrier(i), c["expected"]["outputs"]["price"]
            t = 1e-10 * abs(q) + 1e-12
            res.append({"case_id": c["case_id"], "pass": abs(q - gold) <= t, "checks": [{"output": "price", "golden": gold,
                        "ql_analytic": q, "gap": gold - q, "tolerance": t, "pass": abs(q - gold) <= t}]})
            continue
        if i["rebate"] != 0.0:
            continue
        if abs(round(i["expiry_years"] * 365) - i["expiry_years"] * 365) > 1e-9:
            continue
        v, se = mc(i)
        gold = c["expected"]["outputs"]["price"]
        t = 3 * se
        ok = abs(gold - v) <= t
        res.append({"case_id": c["case_id"], "pass": ok, "checks": [{"output": "price", "golden": gold, "ql_mc": v, "se": se,
                    "gap": gold - v, "z": (gold - v) / se, "tolerance": t, "pass": ok}]})
        print(f"{c['case_id']} {i['barrier_type']} {i['option_type']} m={i['monitoring_per_year']} T={i['expiry_years']}: "
              f"BGK {gold:.5f} MC {v:.5f} +- {se:.5f} z {(gold - v) / se:+.2f} {'ok' if ok else 'GAP'}")
    p = ROOT / "oracle" / "OUTSIDE_G_R6.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["suites"]["barrier_g"] = {"library": f"QuantLib {ql.__version__} MCPRBarrierEngine, one step per monitoring date, no bridge, "
                                  f"{PATHS} antithetic paths, seed 20261112; tolerance 3 SE", "cases": res}
    p.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"barrier_g discrete: {sum(r['pass'] for r in res)} of {len(res)} within 3 SE")


if __name__ == "__main__":
    main()
