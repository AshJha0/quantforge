# Stage J wave 1: outside-library oracle notes (2026-11-14)

Script `oracle/python/outside_j.py`, output `oracle/OUTSIDE_J.json`, pins `oracle/python/requirements-outside-j.txt`
(separate venv, not `uv.lock`). Goldens and implementation code were not changed. Each case is compared output by
output at the golden's own tolerance class; a case counts only if every compared output passes.

## Result

| Suite | Value cases | Library-checked | Class | Library |
|---|---|---|---|---|
| `regime_j` | 10 | 10 | library-object | hmmlearn 0.3.3 `decode(algorithm="viterbi")` (GaussianHMM; BaseHMM with the given emission table) |
| `purgedcv_j` | 15 | 12 | 4 object, 8 primitive | timeseriescv 0.2 `CombPurgedKFoldCV(n_test_splits=1)`, scikit-learn 1.9.1 `KFold`, skfolio 1.12.12 `CombinatorialPurgedCV` |
| `rstats_j` | 24 | 5 | library-primitive | statsmodels 0.15.0 `NormalIndPower(ratio=0)` (power cases only) |
| `backtest_j` | 14 | 14 | library-primitive | vectorbt 1.2.1 `Portfolio.from_orders` |
| Total | 63 (99 with error cases) | 41 | 14 object, 27 primitive | |

R6-13 share for wave 1: 41 of 63 value-checked cases (65.1 %); old all-case figure 41 of 99 (41.4 %).
"Primitive" here means at least one output is arithmetic on the library's result (embargo count `floor(pct n)`,
`z_sum = mds sqrt(years)`, `1/sqrt(years)`, the Lo standard error, the spread/commission split of vectorbt's fees,
the absolute drawdown of vectorbt's equity); the field `via` in the JSON marks each such output.

Not checked (22): DSR (14) and PSR (4 value cases) have no free library implementation; `scipy.stats.norm` around the
spec formula would be a reimplementation under D6, so they stay uncounted. PBO (6): no installable CSCV library
(`pypbo` is not on PyPI). `purgedcv_j-0004`, `-0010`: the spec's embargo is an index count (J-8), timeseriescv's a
time span, so the library cannot express it. `purgedcv_j-0019` (`N = 5, k = 1`): skfolio refuses `n_test_folds = 1`.

## Agreement and precision notes (no golden disagreement)

1. statsmodels `solve_power` stops at brentq's default tolerance; its raw MDS differs from the golden by up to 7.5e-7
   (outside `per_unit`). Refining with scipy `brentq` (xtol 1e-15) on the same statsmodels `power` function agrees
   within tolerance on all five cases. A solver-tolerance artefact, not a formula difference.
2. vectorbt with `init_cash = 1e9` rounds equity at about 2e-7. Equity is therefore taken as the cumulative library
   `cash_flow()` plus `asset_value()`; all 14 cases then agree within `simple_analytic`.

## Finding: timeseriescv 0.2 skips the after-block purge at the end of the data

`purgedcv_j-0004`, fold 7 (test index 7, `t1 = 9`, `n = 10`): the spec purges index 9 (`t0 = 9 <= hi = 9`, closed
interval). timeseriescv keeps it: its `embargo()` computes `min_train_index = #(pred_times <= last_eval + embargo)`
and applies the cut only `if min_train_index < n`; when the overlap reaches the last observation the condition is
false and nothing after the block is removed. This is a library edge-case defect, not a golden error (the spec and
the hand rule agree; fold 8 of the same case is fine). The case is not counted anyway (index embargo). No counted
case is affected: every counted fold passed exactly.

## Proposed J-19 amendment row (text only; the rulings file is not edited)

| J-19a | Outside check, wave 1 (amends J-19) | Outside libraries now check 41 of the 63 value-checked wave 1 goldens (41 of 99 with error cases): `regime_j` 10/10 hmmlearn 0.3.3 Viterbi (library-object); `purgedcv_j` 12/15 timeseriescv 0.2 purge, scikit-learn 1.9.1 KFold, skfolio 1.12.12 CPCV counts; `rstats_j` 5/24 statsmodels 0.15.0 one-sample power; `backtest_j` 14/14 vectorbt 1.2.1. Per case in `oracle/OUTSIDE_J.json` (`oracle/python/outside_j.py`). DSR, PSR and PBO have no free library and stay hand/paper checked; scipy around the spec formula is not counted (D6). timeseriescv's end-of-data purge defect is recorded in `program/WAVE1_ORACLE_NOTES.md`. Stage J is not yet in `tools/outside_shares.py` (`STAGE_DIRS`); wiring it in, with a per-case loader like `load_percase_g`, is the next step |
