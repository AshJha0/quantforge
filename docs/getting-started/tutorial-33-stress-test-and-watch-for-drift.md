# Tutorial 33: stress a curve with history and watch for drift

The plain idea: a stress test replays a past crisis on today's curve, an interpolation backtest hides a point you know and checks how well the curve recovers it, and a drift detector tells you when today's data has stopped looking like the data a model was fitted on. This page does all three with the stage J wave 3 operations, in about a second.

You need: the repository and `uv` (tutorial 1). Specs: [scenario stress](../../specifications/06-risk/scenario-stress.md), [interpolation backtests](../../specifications/11-research/interp-backtest.md), [drift detectors](../../specifications/11-research/drift-detectors.md); rulings J-W3-1 to J-W3-16 in `specifications/stage-j-rulings-w3.md`.

## Step 1: run it in Python

The script reads the shock library `datasets/scenarios/us_treasury_shocks.json` (US Treasury par yields, with the source URL, retrieval time and SHA-256 of each file; every start and end value matches the Fed's H.15 release, worst gap 0.0000 percentage points).

<!-- tutorial:source examples/tutorials/t33_stress_drift.py -->
```python
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
```

Run it:

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t33_stress_drift.py
```

Real output, 2026-11-15, Windows 11 (Python build; the Rust, Java and C++ builds printed the same fourteen lines):

<!-- tutorial:expect -->
```text
taper 2013: 2Y 32.0 bp  10Y 132.0 bp  level 64.82 bp  slope 105.0 bp
gfc_2008: 10Y 2.71 %  P&L 697900
taper_2013: 10Y 5.52 %  P&L -500400
covid_2020: 10Y 3.18 %  P&L 481800
hikes_2022: 10Y 6.89 %  P&L -1392700
leave one tenor out, linear: max 10.0 bp  rmse 6.7 bp
leave one tenor out, monotone_pchip: max 6.0 bp  rmse 3.8 bp
leave one tenor out, cubic_natural: max 7.0 bp  rmse 3.8 bp
hide strike 100: errors 0.01 -0.24 vol pts
CUSUM: alarms [64, 70, 76, 82, 88]  directions [1, 1, 1, 1, 1]
Page-Hinkley: alarms [64]  directions [1]
PSI: 7.3652  alarm True
KS: D 0.9000  p-value 5.787e-13  reject True
KS before the break: D 0.0000  p-value 1.0000  reject False
```

### Reading the numbers

- **The taper tantrum.** From 1 May to 5 September 2013 the 2-year par yield rose 32 bp and the 10-year 132 bp: `shift_bp = 100 (end - start)` per tenor (J-W3-2). The level is the plain mean of the eleven shifts, 64.82 bp; the slope is 30Y minus 1M, `105 - 0 = 105` bp. A steepener, not a parallel move.
- **Replay and P&L.** The shock is interpolated linearly in tenor onto the book's tenors and held flat outside the shock's own tenors (J-W3-4). The book is long 1,200 per bp at 2Y and 3,500 per bp at 10Y, and `pnl = -sum dv01 x applied_bp`. In 2008 rates fell about 147 bp at 2Y and 149 bp at 10Y: `-(1,200 x -147 + 3,500 x -149) = 697,900`. The 2022 hiking cycle (+376 bp, +269 bp) costs 1,392,700, twice the 2008 gain.
- **Leave one tenor out.** Each inner tenor is removed, the curve rebuilt from the rest with the same `core.interp.evaluate` code, and the hidden value compared with the truth (J-W3-8). The end tenors are never left out, since that would be extrapolation. Linear misses the 1Y point by 10 bp; pchip and the natural spline follow the curvature better.
- **Hide a strike.** The surface backtest interpolates total variance `w = sigma^2 T` across strike at each expiry separately and converts back to vol (J-W3-9). Total variance is the natural quantity for the calendar check (no calendar arbitrage needs `w` non-decreasing in `T` at each strike), but interpolating each expiry on its own does not enforce that; the backtest measures fit error only. On the 3-month smile the spline puts the 100 strike 0.01 vol points high; on the 1-year smile 0.24 low.
- **CUSUM.** The series is a fixed ten-day pattern (mean 0) and from day 60 the same pattern plus 1.5. With `k = 0.5`, `h = 5` the upper sum grows by about `1.5 - 0.5 = 1` a day after the break, so it passes 5 on day 64, a delay of 4. The sums restart after each alarm and the shift is still there, so CUSUM alarms again every six days.
- **Page-Hinkley.** Same delay here, but only one alarm: after the restart its running mean is taken over the shifted data alone, so the new level is the new normal. That is the difference between the two: CUSUM measures against a fixed `mu0`, Page-Hinkley against its own running mean (J-W3-11). `lambda = 5` is the value the A3 prereg now uses (decision record DR-A3-1); with the plan's original 50 this series would not alarm at all within its 30 shifted days.
- **PSI.** Five bins at the reference window's quintiles (type-1 quantiles, right-closed bins, J-W3-12). After the shift every test value lands in the top bin (shares 0, 0, 0, 0, 1 against 0.2 each), so the shares are far apart and PSI is 7.37, far above the usual 0.25 alarm level. Empty bins are floored at `1e-4`, otherwise the logarithm would be infinite.
- **KS.** The two-sample statistic `D` is the largest gap between the two empirical distribution functions: 0.9 here, with an exact p-value of `5.8e-13` from counting lattice paths (J-W3-13). Before the break the two windows are the same pattern, `D = 0` and `p = 1`.

### The formal statement, checked against the spec

Two-sided tabular CUSUM [PAGE54] on `z_t = (x_t - mu0) / sigma`: `S+_t = max(0, S+_{t-1} + z_t - k)`, `S-_t = max(0, S-_{t-1} - z_t - k)`, alarm when either exceeds `h` (strictly), both restart at 0. Page-Hinkley: `m_t = sum_{s <= t} (x_s - xbar_s - delta)` from the last restart, `xbar_s` the running mean at step `s`, alarm when `m_t - min(0, m_1, ..., m_t) > lambda`; the down test is the same on `-x`. PSI `= sum_b (a_b - e_b) ln(a_b / e_b)` over test shares `a_b` and reference shares `e_b`. KS: `D = max_x |F_n(x) - G_m(x)|`, p-value `P(D' >= D)` under the continuous null.

The checks behind the goldens (`scen_j` 23, `interpbt_j` 25, `drift_j` 35 cases): hand cases; exact rational re-computation in the generator; numpy `interp`, scipy `CubicSpline` and `PchipInterpolator` on every interpolation-backtest value case; scipy `ks_2samp(method="exact")` and numpy/scipy quantile, binning and `rel_entr` on the KS and PSI cases; pandas date lookup and numpy `interp` on the scenario cases (`oracle/python/outside_j.py`). No library implements CUSUM or Page-Hinkley with these conventions, so those 13 value cases are checked by hand and by the rational re-implementation only.

## Step 2: the same in Rust, Java and C++

The same script sends the same cases to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t33_stress_drift.py rust/target/release/quantforge
```

Java:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t33_stress_drift.py java -jar java25/target/quantforge-cli.jar
```

C++:

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t33_stress_drift.py cpp26/build/quantforge
```

Each prints the fourteen lines of step 1, digit for digit (checked on 2026-11-15: Java on Windows 11, Rust and C++ under WSL Ubuntu). The full checks are `python conformance/runner/runner.py --impl rust --suite scen_j`, `--suite interpbt_j` and `--suite drift_j`.

## For practitioners

- **A historical shock is one path, not a distribution.** Four crises tell you how the book did in four specific moves. Use them next to VaR and a hypothetical shock set, not in place of them.
- **Interpolating a shock is a choice.** Linear and flat outside is the simplest honest rule; a book with 50-year swaps sees the 30-year shock held flat beyond 30 years. Say so in the report.
- **Leave-one-out understates the error between knots.** The hidden knot is a quoted point; the worst error usually sits between quotes. The B1 backtest (`research/interp_backtest/RESULTS.md`) fails on the short-expiry ATM point for exactly this reason.
- **Calibrate a detector's threshold before you look at the data.** Choose `h` or `lambda` from the false-alarm rate you can live with (CUSUM `k = 0.5`, `h = 5` gives about one false alarm every 469 steps, two-sided), then measure the delay. The A3 prereg does this for simulated data.
- **PSI and KS need a window.** Both compare two samples, so a break is seen only once enough of the test window lies after it. CUSUM and Page-Hinkley alarm within a few steps of a mean shift; PSI and KS see changes in shape, such as a variance change, that a mean detector misses.

## Common mistakes

- **Yields in percent, shifts in basis points.** `historical_shock` takes percent and returns basis points; `replay` adds `applied_bp / 100` to percent yields. Mixing decimal yields with these gives shocks 100 times too large.
- **A missing date.** `start_date` and `end_date` must be rows of `dates` (`E_DOMAIN` otherwise); the operation does not pick the nearest business day for you.
- **Holding out an end strike.** `surface_holdout` refuses the first and last strikes (`E_INPUT`): there is nothing on the other side to interpolate from.
- **Reading a reset detector's alarm count as the number of breaks.** CUSUM restarted against a fixed `mu0` keeps alarming while the shift lasts, as above; count the first alarm after each break.
