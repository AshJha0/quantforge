# Tutorial 33: stress a curve with history and watch for drift (stub)

Status: **stub** (stage J wave 3, 2026-11-15). The operations exist in the Python build only; the runnable page, with Rust, Java and C++ blocks and real output, comes with the wave 3 language lanes. Nothing on this page is checked by `tools/check_tutorial.py` yet.

The plain idea: a stress test replays a past crisis on today's curve, and a drift detector tells you when today's data has stopped looking like the data a model was fitted on. This page will walk through:

1. Measuring the 2013 taper-tantrum move from the stored Treasury par rows with `risk.scenario.historical_shock`, and checking it against H.15 (`datasets/scenarios/us_treasury_shocks.json`).
2. Replaying the four library shocks (2008, 2013, 2020, 2022) on one curve with `risk.scenario.replay`, with a small DV01 ladder for the P&L.
3. Hiding one tenor at a time with `research.backtest.interp_loo`, and one strike at a time with `research.backtest.surface_holdout`, and reading the results of backtests B1 (fail) and B2 (pass) in `research/interp_backtest/RESULTS.md`.
4. Running `research.drift.cusum`, `research.drift.page_hinkley`, `research.drift.psi` and `research.drift.ks` on a series with a planted break.

Specs: [scenario stress](../../specifications/06-risk/scenario-stress.md), [interpolation backtests](../../specifications/11-research/interp-backtest.md), [drift detectors](../../specifications/11-research/drift-detectors.md).
