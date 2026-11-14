# R3-03 amendment 4: Seasonality in US breakeven inflation, open choices closed before any study run

Status: **signed**. Signed by Claude (stage J lane R3 amendment 4; signing delegated by the owner, 2026-11-07) on 2026-11-14. Second read: `program/R3_A4_REVIEW.md` (a separate Claude subagent; human check: none).
- SHA-256 of the body below the marker line: `ef1cc3f8c76bd552ccfe41d7403300bc9da336f1fa6bf7ae4e188408dfcb5934`
- SHA-256 of the amended prereg `R3-03-breakeven-seasonality.md` (whole file): `de1c6d5b5dab03924e8f0f48346976e678d687252fa6a61acc84892a41494dd2`
- SHA-256 of `R3-03-amendment-1.md` (whole file): `ed0cfc25451ee635720677b8282ee61daefeda2c06fa7d364b275c6d663f3d7a`
- SHA-256 of `R3-03-amendment-2.md` (whole file): `715ef7d0d7724d54b8c809fe0e0ffcfc3dab394f466cccfbe46d9f8e51da7db1`
- SHA-256 of `R3-03-amendment-3.md` (whole file): `b19e7967037f2156cb375725f1ac93fa55c2742466a3fe3d0fb407af99d2aa71`
- SHA-256 of the common rules (`README.md` body): `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- SHA-256 of `DEVIATION-2026-11-12.md` (whole file): `b7e9e4d33e14dc164ed2c34312bf52bb894accfa124c3c8c45400d913e67c1db`
- SHA-256 of `DEVIATION-2026-11-12-recorder-rule.md` (whole file): `8a4bdeee378644ae4389b22b81ee259b3c101d6f0dd54c9be72a170fac2e3044`
- No study signal, position or statistic has been computed on any date at signing; `research/holdout_runs.csv` has no line.
- This file is not edited after signing; a further change is a new amendment.

<!-- body -->
Amends each of `R3-01-treasury-fly.md`, `R3-02-bill-repo-spread.md` and `R3-03-breakeven-seasonality.md` (one shared text; the file header names the study it amends) and that study's amendments 1 to 3. They stand; where this amendment differs, this amendment governs. Common rules: `README.md`. Source: the open choices listed in `program/R3_NOTES.md` (stage J lane R3, 2026-11-14) and the second read `program/R3_A4_REVIEW.md`.

**How the choices were made.** Each choice below is fixed by a stated principle (no look-ahead, same sample for every trial, the more conservative of two readings) or by a published market convention, with its source. None was made by looking at data. Holdout-period values of some inputs were downloaded by the project's recorder, as listed in `DEVIATION-2026-11-12.md` (amendment 2 Change 1); no choice here used them. No study file has been downloaded or parsed by a study runner, no study signal, position or statistic has been computed on any period, `research/holdout_runs.csv` has no line, and no value in any holdout window was read to make a choice. Prior knowledge is as in amendments 1 and 2.

## Rules common to the three studies

C1. **Timing.** A signal uses only values dated on or before the decision close. A position decided at a close earns from the next price move after its execution; the per-study rules give the execution date. No value dated after a decision is used for it (principle: no look-ahead).

C2. **Window membership.** Each return is dated by the close at which it ends. A return belongs to the in-sample or holdout window that contains its end date; a return starting before a window and ending in it belongs to that window. Signals for early holdout returns may use in-sample values (they are dated before the holdout).

C3. **One continuous path.** Each trial is run as one path from the first date its windows allow; the holdout part is not restarted flat (principle: the path a trader following the rule would have; the rule is causal, so carrying state uses only earlier values).

C4. **Common sample for selection.** The in-sample Sharpe of every trial of a study, used to select the holdout trial (amendment 1) and for PBO, is computed on the same returns dates: those from the first date at which the study's longest window is full, to the in-sample end. Ties in in-sample Sharpe go to the lower trial number.

C5. **Statistics, as implemented.** The annualised Sharpe and its Lo (2002) standard error are `lo_sharpe` in `research/power/r3_power.py` at commit 09c596f (the estimator the power tables of amendments 1 and 2 used): sample Sharpe with `ddof = 1`, times `eta = q / sqrt(q + 2 sum_{k=1..min(lags, q-1)} (q - k) rho_k)`, SE `sqrt((1 + SR^2/2)/n) eta`, with `q` = 252 (daily) or 12 (monthly). The circular stationary block bootstrap SE is exactly `boot_sharpe` there, called with `x` of shape `(1, n)` (Politis and Romano 1994): 10,000 draws, mean block 3, SE the `ddof = 1` standard deviation of the bootstrap annualised Sharpes, generator `numpy.random.default_rng(20261114)` (seed fixed now, the signing date). `SR0 = SE x 1.9798`, `p = 1 - Phi((SR - SR0)/SE)`, `p2 = 1 - Phi(SR/SE)`, all on holdout net returns at 1x costs.

C6. **Pass condition (3), thirds.** The holdout returns are split into three runs of equal count by position (`n//3`, `2n//3`), as `thirds_positive` in `r3_power.py`; condition (3) holds when the mean holdout net return at 1x costs of each third is above 0. This governs over "same sign in each third" (a Sharpe's sign is its mean's sign; the overall sign required is positive by condition (1)).

C7. **Pass condition (2), 2x costs.** Every cost and charge of the study, trading and balance-sheet, is doubled.

C8. **PBO.** CSCV with 16 blocks (`research.stats.pbo`, metric Sharpe) on the in-sample net returns at 1x costs of the common sample (C4), one column per distinct trial; the earliest rows are dropped until the row count is a multiple of 16. If it cannot be computed (a block with zero variance, fewer than 2 rows a block), the result is labelled exploratory (the more conservative reading). With one distinct trial there is no selection and PBO is reported as not applicable.

C9. **Reported-only figures** (never deciding): the correlations named in each prereg, defined below per study; the dummy-controlled check of R3-02.

C10. **Data.** Each file is downloaded once into `research/r3/data/` and logged in `research/r3/data_log.csv` (source URL, UTC time, SHA-256 of the raw bytes); the runner refuses a file whose hash differs from its log line. In-sample runs download only the files for in-sample years or ranges. A business day of a study is a date on which every input value of the study is non-missing; no fill or interpolation. Funding accrual in R3-02 uses the fixing dates of the funding series.

## R3-01 Treasury fly

1. **Package and return base.** Weights in DV01 are 1 : 2 : 1 for 2Y : 5Y : 10Y (the 50:50 butterfly, net DV01 zero; Tuckman and Serrat, *Fixed Income Securities*, 3rd ed., ch. on curve trades). This governs over "duration-neutral": the 50:50 fly is DV01-neutral with equal wing risk, not duration-neutral in money. Leg DV01 per unit notional is `D = modified_duration x dirty / 10^4` from `bond.price.from_yield` (`quantforge_core.bonds.price_from_yield`) for a par bond: coupon equal to the par yield, semi-annual, maturity the tenor in years after the date, settlement on the date. For one unit of wing DV01 the gross notional is `G = 1/D2 + 2/D5 + 1/D10`. `pos_t` is the position held after close `t`, set by the rule on `z_{t-1}` (item 4). Return of day `t`: `r_t = pos_{t-1} (f_t - f_{t-1}) / G_{t-1}`, the bp P&L per unit of gross notional of the DV01-neutral package (standard practice: a return is P&L over the capital base the charges are levied on). Position `+1` is the package that gains when `f` rises; the rule's arithmetic (short the fly, `pos = -1`, when `z > k`) governs over the phrase "pay the body".
2. **Trade.** A trade is a change of position (to or from flat, or a sign flip). The daily re-weighting of an unchanged position to new DV01s is not charged (a stated limit). Cost: `0.25 bp x (1 + 2 + 1) x |pos_t - pos_{t-1}| / G_t`, so a flip costs twice an opening.
3. **DV01 date.** DV01s at the close the position is entered (`t-1` for the return of day `t`), known when the trade is made.
4. **Timing.** `z_t` uses `f` on the `L` business days ending at `t` (sample sd, `ddof = 1`); the position decided at close `t` is executed at close `t + 1` and earns from `t + 2` (`research.backtest.run`, `lag = 1`).
5. **Holdout start.** C3: carried, not flat.
6. **Financing.** None in the proxy: the package's net financing is set to zero and no carry term is added. No free GC series covers 1990 to 2012 (SOFR and TGCR start in 2018; FRED is excluded by amendment 2), so the prereg's "flat at GC" is a stated limit, not a term.
7. **Balance-sheet charge.** `0.0025 / 252 x |pos_{t-1}|` per business day, per unit of gross notional; annualisation factor 252, as for the Sharpe.
8. **Reported correlations.** Daily returns of the selected trial against the scores of the first three principal components of in-sample daily changes in 2Y, 5Y, 10Y (covariance matrix, loadings frozen at the in-sample end), and against a carry proxy, the package's yield carry `(y2/D2 - 2 y5/D5 + y10/D10) / (252 G)` signed by position.

## R3-02 bill against funding

1. **Signal date.** Entry at the close of the first business day `E` of each month. The signal uses values dated on or before the previous business day `E - 1`: the bill rate of `E - 1` and funding fixings dated through `E - 1`. Reason: the NY Fed publishes the fixing for a date at about 8:00 ET on the next business day (NY Fed, "Additional Information about Reference Rates", newyorkfed.org/markets/reference-rates/additional-information-about-reference-rates), so a fixing dated `E` is not known at the close of `E`. `s` uses the trailing mean of the last 20 fixings dated on or before each day; `z` uses the last `L` values of `s` (`ddof = 1`).
2. **Exit.** At the close of the next month's first business day, where the next position is entered. The holding period is the calendar month (19 to 23 business days), non-overlapping and contiguous; this governs over "held 21 business days" (the prereg's non-overlapping monthly entries and amendment 1's monthly Sharpe need one return a month). `F` compounds the fixings dated `E` to the day before the exit, each accruing calendar days to the next business day.
3. **Bill maturity and basis.** `t = 91` days at entry (the 13-week bill's tenor), `91 - h` at exit. `B = 366` when a 29 February falls in the year after the observation date (Treasury interpretation note: the year after issue; the observation date stands for the issue date because the rates file has none), else 365. A stated limit.
4. **Cost unit.** 0.5 bp of yield per round trip times the bill's money-market DV01 per unit price at entry, `0.5 x 10^-4 x (t/360) x P^2` (the derivative of `P = 1/(1 + y t/360)`). Each month with a non-zero position is one round trip: the bill bought at entry is sold at exit and a new 13-week bill is bought (the roll). Balance-sheet charge `0.0002 x h / 360` per month held, per unit of entry price.
5. **Flat months** enter the Sharpe as zero returns (dropping them would condition the sample on the signal).
6. **Seed:** C5, 20261114.
7. **Holdout months.** By C2: entries from 2022-12-01 to 2026-09-01 (exits 2023-01-03 to 2026-10-01), 46 months; the October 2026 entry exits after the holdout end and is not counted.
8. **Dummy-controlled check** (reported only): the same returns with the month-end, quarter-end and year-end business days removed from the funding mean `r_t` and from `F`'s fixings (accrual kept).

## R3-03 breakeven seasonality

1. **CPI arm: not run.** The archived pre-2016 BLS seasonal-factor file was not found (BLS pages refuse scripted access, HTTP 403, `program/R3_NOTES.md`). Under amendment 2 Change 3, trials T02 and T04 are reported as not run. This is decided now and final for this study: the arm is not added later even if the file is found, because adding it after the own-history result is known would be a choice made on outcomes.
2. **T01 and T03 are one strategy.** The position is the sign of the forecast, and shrinking by `lambda` = 0 or 0.5 never changes a sign, so T01 and T03 have identical positions and returns. They are merged: run once, reported as "T01 = T03". Honest count: the family has 24 ledger rows and 21 distinct strategies that are run (R3-01 8, R3-02 12, R3-03 1). The deflation keeps `N = 24`: amendments 1 and 2 fix it, `tools/quality_gate.py --check-dsr` rejects `N` below the ledger count, and 24 gives a higher benchmark than 21 (E[max] 1.9798 against 1.9221), so it is the conservative choice. The distinct count is reported beside it. The selected R3-03 trial is T01; PBO is not applicable (C8).
3. **Return base.** The package is long the TIPS leg and short the nominal leg, DV01-matched: per unit of nominal notional, TIPS notional `Dn/Dr`, where `Dn` and `Dr` are the par-bond DV01s (`price_from_yield` as in R3-01 item 1, coupon the par yield, semi-annual, 5 years) at the nominal and real par 5Y yields of the entry close. Gross notional `1 + Dn/Dr`. Monthly return `pos_{m} d_m Dn / (1 + Dn/Dr)` with `d_m` in bp. The TIPS index ratio is taken as 1 (a stated limit). Balance-sheet charge `0.0025 / 12 x |pos_m|` per month, per unit of gross notional.
4. **Round trip.** Cost `1 bp x |pos_m - pos_{m-1}| / 2 x Dn / (1 + Dn/Dr)`: opening or closing is half a round trip, a flip is one. Holding the same sign into the next month is not charged (the constant-maturity proxy needs no roll).
5. **Months.** In-sample returns Feb 2003 to Dec 2015 (155); holdout returns Jan 2016 to Oct 2026 (130), the first running from 2015-12-31 (C2). **Timing.** The position for month `m` is set at the close of the last business day of month `m - 1` from frozen in-sample means; it earns `d_m`. In-sample months use means fitted on the whole in-sample period, so the in-sample Sharpe is an in-sample fit (stated; it selects nothing, as only one distinct trial runs).
6. **Reported correlations.** Monthly returns against a roll-down proxy `(b10 - b5) / 60` (bp a month, the 5Y-10Y breakeven slope over one month) and 12-month momentum, the sign of `b5` change over the prior 12 months.

## What is unchanged

The holdout windows, the parameter grids, the cost levels, the family count `N = 24`, Holm across the three studies, the pass rule, the secondary statistic, the forward-log rules of amendments 1 and 3, and the one-shot holdout run of amendment 3 rule 1.

## Prior knowledge

Unchanged from amendment 2; holdout-period downloads by the recorder are as in `DEVIATION-2026-11-12.md`. At signing no study runner has read any study file, no signal or statistic has been computed on any date, and no line exists in `research/holdout_runs.csv`.

## AI assistance (`research/TEMPLATE.md` section 7)

- Tool and version: Claude Code, model claude-opus-5-5 (Opus 5.5), 2026-11-14.
- What it did: drafted this amendment from `program/R3_NOTES.md`, wrote the second read `program/R3_A4_REVIEW.md`, and signed under the owner's delegation.
- Claims checked by a human: none yet. The second read was by a separate Claude subagent, not a person.
