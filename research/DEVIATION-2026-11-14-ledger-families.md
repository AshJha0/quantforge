# Deviation 2026-11-14: `research/trials.csv` holds two hypothesis families

Recorded by the stage J coordinator under the owner's delegation, after all R3 holdout runs (logged in `research/holdout_runs.csv`) and the single Q6-02 run.

## What happened

R3 amendments 1 and 4 fix the deflated Sharpe ratio at `N = 24`, described as "the number of rows in `research/trials.csv`". The signed Q6-02 prereg (item 5) then required its three trials, `Q6-02-T01..T03`, to be committed to the same file before its run (commit 58a5c0f). The file now has 27 rows, and the gate `tools/quality_gate.py --check-dsr` began rejecting `N = 24`.

## Reading applied

The two families test unrelated hypotheses: R3 asks whether three rates signals earn a positive net Sharpe ratio; Q6 asks whether a curve calibration method keeps quotes inside the bid-ask spread. A DSR deflates over the trials of the family it is testing, so the R3 count is the R3 rows only: 24 (R3-01 8, R3-02 12, R3-03 4), exactly the count the amendments fixed and the count every R3 result used. Q6-02 computes no DSR.

`read_ledger` and `--check-dsr` now take `--family` (study prefix), and the tests count the R3 family. Running the gate over the whole file without `--family` is rejected by test, so the families cannot be pooled by accident.

## Effect on results

None. No R3 or Q6-02 number changes; no signed or hash-pinned file is edited. Future studies that log trials in this file must name their family in the study column prefix.
