# R3 studies: in-sample, freeze and one-shot holdout results (2026-11-14)

Preregs `research/preregs/R3-0{1,2,3}*.md` with amendments 1 to 4 (R3-01 also amendment 5). Freeze commit `faadaa4`; run log `research/holdout_runs.csv` (runner SHA-256 `f45ce97f…`), committed before the run; each holdout run once by `research/r3_holdout.py`. Raw numbers: `research/r3/in_sample.json`, `research/r3/holdout.json`. Data: free public US Treasury and NY Fed files, provenance in `research/r3/data_log.csv`.

**Verdict: all three studies fail the preregistered rule and are published as null results.** No Holm rejection; no secondary evidence below its Holm level.

| | R3-01 Treasury fly | R3-02 bill against funding | R3-03 breakeven seasonality |
|---|---|---|---|
| In-sample selection | T08 (L 500, k 1.5), net Sharpe 0.05 (best of 8; all negative at 2x) | T02 (SOFR, L 60, k 2.0), net Sharpe -0.56 (best of 12, all negative) | T01 (= T03), 0.44 (in-sample fit; T02/T04 CPI arm not run) |
| In-sample PBO | 0.15 | not computable: **exploratory** | not applicable (one distinct trial) |
| Holdout returns | 3,459 daily (2013 to Oct 2026) | 46 monthly (exits Jan 2023 to Oct 2026) | 130 monthly (Jan 2016 to Oct 2026) |
| Holdout net Sharpe, 1x | -0.61 (SE 0.34, Lo 20 lags) | -1.09 (bootstrap SE undefined, below) | 0.33 (SE 0.35, Lo 3 lags) |
| DSR (N = 24), `1 - p` | 0.0001 (p 0.9999) | undefined; p > 0.5 for any SE | 0.15 (p 0.849) |
| Holm-adjusted p | 1.0 | 1.0 | 1.0 |
| (2) net Sharpe at 2x > 0 | no (-1.15) | no (-1.19) | yes (0.07) |
| (3) each third positive | no | no | yes |
| Secondary p2 | 0.963, not below | undefined, not below | 0.172, not below |
| Power at the MDS (amendments 1 and 2): pass rule / p2 at 0.05 | 0.126 / 0.80 | 0.152 / 0.80 | 0.127 / 0.80 |
| Result | **fail** | **fail** (exploratory) | **fail** (conditions 2 and 3 hold, 1 does not) |

Family: 24 ledger trials, 21 distinct strategies run, deflation at N = 24 (E[max] 1.9798).

## Notes, stated after the run

- **R3-02 bootstrap SE is NaN.** The selected trial is flat in most holdout months; some of the 10,000 circular block resamples (seed 20261114, `boot_sharpe` exactly as amendment 4 C5 pins it) have zero variance, so the SE, `p` and `p2` are undefined. The holdout Sharpe is negative (-1.09) and `SR0 > 0`, so `p > 0.5` for every positive SE: condition (1) fails whatever the SE, and conditions (2) and (3) fail independently. The study was not re-run.
- **Holm ordering (post-hoc erratum, 2026-11-14).** `research/r3/holdout.json` sorts R3-02's NaN p arbitrarily, so its `holm_level` fields for R3-01 and R3-02 mean nothing; the file is a frozen output and is not edited. R3-02's p is above 0.5 for any SE, and R3-03's is 0.849, so the family's smallest p is above 0.5 against a first Holm level of 0.05/3 = 0.0167: Holm stops at step 1 and rejects nothing under any order, and every Holm-adjusted p is 1.0. Verdicts unchanged. Detail: `research/DEVIATION-2026-11-14-holm-display.md`.
- **Reported only** (never deciding). R3-01: correlation of holdout daily returns with in-sample PC scores 0.13 (PC1), -0.06 (PC2), 0.20 (PC3); with the carry proxy -0.01. R3-03: with the roll-down proxy -0.09, with 12-month momentum 0.04. R3-02's dummy-controlled check: see below.
- R3-03's CPI arm is not run (amendment 4 item 1), final.

## R3-02 dummy-controlled check (post-hoc, report-only)

*Plain idea.* Funding rates jump at month ends, quarter ends and year ends, when banks shrink their balance sheets for reporting dates. If the bill-against-funding signal were only picking up those dates, removing them should change the result a lot.

*Formal statement* (amendment 4, R3-02 item 8; C9 makes it reported only). The frozen trial (SOFR, `L` 60, `k` 2.0) is recomputed with every month-end business day (each quarter end and year end is also a month end) removed from the funding inputs: the trailing mean `r_t` averages the last 20 fixings that are not month-end days, and in the realised funding `F` a removed day's fixing is replaced by the last kept fixing, so its calendar days still accrue ("accrual kept"; this reading of the phrase is ours, stated here). Bill rates, entry dates, costs and windows are unchanged. Computed on 2026-11-14, after the holdout run, by `research/r3_02_dummy.py`, reading holdout files only through the same guard; raw output `research/r3/dummy_check.json`. It decides nothing.

| | in-sample (52 months, 5 in position) | holdout (46 months, 7 in position) |
|---|---|---|
| as run, net Sharpe 1x (plain monthly, no bootstrap) | -0.51 | -1.09 |
| month ends removed | -0.53 | -1.09 |

*Worked reading.* The trial trades in the same months either way and the holdout mean return moves from -1.751e-5 to -1.748e-5 per month: the loss does not come from reporting-date spikes. The in-sample figure here (-0.51) differs from the selection Sharpe (-0.56) because it uses every in-sample exit, not the common sample of C4.

## Forward-log back-fill (amendment 3 rule 4): due, not done

Amendment 3 makes the back-fill due once a study's line is in `research/holdout_runs.csv`; all three lines are dated 2026-11-14, so rows from the forward log's start to 2026-11-13 are now due. It is not done, because its own rules cannot yet be followed: rule 4 requires the back-fill to be written "by the same script", the one named in the run line (`research/r3_runner.py`, SHA-256 `f45ce97f…`), and that script has no forward-log writer and cannot be changed without breaking its logged hash; rule 5 also requires a `holdout_scan.py` check to exist before the first non-null signal row. No study row has been touched. The back-fill needs a new signed amendment naming a back-fill script (and its hash), plus the rule-5 scan check; until then every `study/R3-0*` row stays `"signal": null`.

## Honest ceiling

These are signals on fitted par curves and published reference rates, with stylised costs. Even a pass would not have shown a tradable profit: no bid/ask, repo specials, on/off-the-run effects or balance-sheet modelling. Every study is underpowered under the pass rule (pass probability 13 % to 15 % at the MDS), so a null says little about a true Sharpe near the MDS; it does say the in-sample choices did not carry into the holdout.
