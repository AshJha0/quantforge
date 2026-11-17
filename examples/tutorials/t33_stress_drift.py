"""Tutorial 33: stress a curve with history, backtest the interpolation, and watch for drift.

  uv run --project python python examples/tutorials/t33_stress_drift.py         # Python
  python examples/tutorials/t33_stress_drift.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-33-stress-test-and-watch-for-drift.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import json
import sys
from pathlib import Path

from qf import connect

LIBRARY = Path(__file__).resolve().parents[2] / "datasets" / "scenarios" / "us_treasury_shocks.json"


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(x, places) for x in values)


def main(cli):
    call = connect(cli)  # the Python package with no arguments, else that build's batch command
    shocks = json.loads(LIBRARY.read_text(encoding="utf-8"))["scenarios"]

    # 1. The 2013 taper tantrum, measured from the two stored Treasury par rows (percent).
    taper = next(s for s in shocks if s["name"] == "taper_2013")
    r = call("risk.scenario.historical_shock", {
        "dates": [taper["start_date"], taper["end_date"]], "tenors": taper["tenors"],
        "yields": [taper["start_yields"], taper["end_yields"]],
        "start_date": taper["start_date"], "end_date": taper["end_date"]})
    print(f"taper 2013: 2Y {num(r['shift_bp'][4], 1)} bp  10Y {num(r['shift_bp'][8], 1)} bp"
          f"  level {num(r['level_bp'], 2)} bp  slope {num(r['slope_bp'], 1)} bp")

    # 2. Replay the four library shocks on one curve, with a small DV01 ladder (per bp, positive = long).
    base_tenors = [0.5, 2.0, 5.0, 10.0, 30.0]
    base_yields = [4.30, 4.05, 4.00, 4.20, 4.45]
    dv01 = [0.0, 1200.0, 0.0, 3500.0, 0.0]  # long 2Y and 10Y
    for s in shocks:
        r = call("risk.scenario.replay", {"base_tenors": base_tenors, "base_yields": base_yields,
                                          "shock_tenors": s["tenors"], "shock_bp": s["shift_bp"],
                                          "dv01": dv01})
        print(f"{s['name']}: 10Y {num(r['shocked_yields'][3], 2)} %  P&L {num(r['pnl'], 0)}")

    # 3. Interpolation backtests: hide each inner tenor, then the 100 strike of a two-expiry smile.
    tenors = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
    par = [5.40, 5.35, 5.10, 4.70, 4.45, 4.25, 4.22, 4.20]
    for method in ("linear", "monotone_pchip", "cubic_natural"):
        r = call("research.backtest.interp_loo", {"method": method, "x": tenors, "y": par})
        print(f"leave one tenor out, {method}: max {num(100 * r['max_abs_error'], 1)} bp"
              f"  rmse {num(100 * r['rmse'], 1)} bp")
    r = call("research.backtest.surface_holdout", {
        "method": "cubic_natural", "expiries": [0.25, 1.0], "strikes": [80.0, 90.0, 100.0, 110.0, 120.0],
        "vols": [[0.28, 0.235, 0.20, 0.185, 0.19], [0.25, 0.225, 0.21, 0.20, 0.20]], "holdout": [2]})
    print(f"hide strike 100: errors {nums([100 * e[0] for e in r['errors']], 2)} vol pts")

    # 4. Drift: 60 calm days then a +1.5 shift in the mean, from a fixed pattern (no random numbers).
    pattern = [0.3, -0.5, 0.8, -0.2, 0.1, -0.9, 0.6, 0.0, -0.4, 0.2]
    x = pattern * 6 + [v + 1.5 for v in pattern] * 3
    r = call("research.drift.cusum", {"x": x, "k": 0.5, "h": 5.0})
    print(f"CUSUM: alarms {r['alarms']}  directions {r['directions']}")
    r = call("research.drift.page_hinkley", {"x": x, "delta": 0.5, "lambda": 5.0})
    print(f"Page-Hinkley: alarms {r['alarms']}  directions {r['directions']}")
    ref, after = x[:30], x[60:]
    r = call("research.drift.psi", {"reference": ref, "test": after, "bins": 5})
    print(f"PSI: {num(r['psi'], 4)}  alarm {r['alarm']}")
    r = call("research.drift.ks", {"a": ref, "b": after})
    print(f"KS: D {num(r['statistic'], 4)}  p-value {r['p_value']:.3e}  reject {r['reject']}")
    r = call("research.drift.ks", {"a": x[:30], "b": x[30:60]})
    print(f"KS before the break: D {num(r['statistic'], 4)}  p-value {num(r['p_value'], 4)}  reject {r['reject']}")


if __name__ == "__main__":
    main(sys.argv[1:])
