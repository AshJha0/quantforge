# R3 studies: run status and open prereg choices (stage J, lane R3)

Date: 2026-11-14. Branch `stage-j-r3` from `stage-j` 13df617. Read: the three signed preregs, amendments 1 to 3 of each, `preregs/README.md` (common rules), `DEVIATION-2026-11-12.md` and its recorder-rule follow-up.

**Result: no study was run.** Each prereg, as amended, still leaves at least one choice open that can change the holdout number. The lane brief says: if a choice is open, stop that study and write the gap here. No holdout run line was written to `research/holdout_runs.csv`, no study data of any period was downloaded or parsed, and no signal was computed. The holdout windows are untouched by this lane.

## What each study needs (as preregistered)

| | R3-01 Treasury fly | R3-02 bill against funding | R3-03 breakeven seasonality |
|---|---|---|---|
| Data | Treasury par yields 2Y/5Y/10Y from 1990 | NY Fed SOFR, TGCR, BGCR from 2018-04-02; Treasury 13-week bill rate | Treasury par nominal 5Y minus par real 5Y from 2003-01-02 (am. 2); archived BLS seasonal factors published by 2015-12-31 |
| In-sample / holdout | 1990-01-02..2012-12-31 / 2013-01-02..2026-10-30 | 2018-04-02..2022-12-30 / 2023-01-03..2026-10-30 | 2003-01-02..2015-12-31 / 2016-01-04..2026-10-30 |
| Grid (trials) | L {60,120,250,500} x k {1.0,1.5} (8) | funding x L {60,250} x k {1,2} (12) | lambda {0,0.5} x source (4) |
| Metric | annualised net Sharpe, daily, SE Lo (2002) 20 lags | monthly P&L Sharpe (am. 1 Change 4), SE stationary block bootstrap, block 3, 10,000 draws | monthly Sharpe, SE Lo (2002) 3 lags |
| Decision | Holm across the 3 studies on p = 1 - Phi((SR - SE*1.9798)/SE), N = 24; net Sharpe > 0 at 2x costs; same sign in each holdout third. Secondary p2 = 1 - Phi(SR/SE), never deciding (am. 2). PBO by CSCV, 16 in-sample blocks, > 0.5 = exploratory | same | same |
| One shot | best in-sample trial (net, 1x costs) run once on the holdout, after an in-sample freeze commit and a `holdout_runs.csv` line committed first (am. 3 rule 1) | same | same |

Holm cannot be applied until all three p-values exist, so condition (1) of any one study is decided only when the family is complete.

## Data check (2026-11-14, HTTP status only, no values read)

- Treasury par yield and real yield per-year CSVs (in-sample years, e.g. 1990, 2003): reachable, 200. Public domain.
- NY Fed reference-rate API for an in-sample range: reachable, 200. Free with attribution.
- BLS seasonal-adjustment pages: 403 to scripted access. The archived pre-2016 factor file was not found; under amendment 2 Change 3 the "CPI NSA seasonal factors" arm (trials T02, T04) is reported as not run if it cannot be found by hand; the trial count stays 24.

Data is not the blocker. The open choices are.

## Open choices that stop each study

### R3-01
1. **Return base.** The bp P&L of the fly is "converted to a return using par-bond DV01s", but the denominator is not named (gross notional, body notional, or per unit of fly DV01). The balance-sheet charge is 25 bp a year of gross notional, so net Sharpe at 1x and 2x costs depends on that choice.
2. **What counts as a trade.** Costs are 0.25 bp per leg "per trade". With daily rebalancing on the close, it is open whether the daily DV01 re-weighting of an unchanged position is a trade, or only a change of sign or a move to flat.
3. **DV01 date.** DV01s "at each day's par yields": the prior close (entry) or the same close as the move.
4. **Holdout start state.** Whether the position at the in-sample end carries into 2013-01-02 or the holdout starts flat (the hysteresis band 0.5..k makes it matter).
5. **Financing.** "Flat at the general-collateral rate", but the return proxy carries no carry term, and no free GC series covers 1990 to 2012 (SOFR and TGCR start 2018; FRED is excluded by am. 2). It should be stated as a no-op or given a source.

### R3-02
1. **Signal date.** Entries are "on the first business day of each month"; it is open whether `z` uses that day's close (and the trade is at that close) or the prior close. `research/r3_02_pnl.py` enters every 21 business days, not on month starts, so it does not settle this.
2. **Exit.** "Held 21 business days" with monthly entries: exit after 21 business days or at the next month's first business day (they differ by up to two days and can overlap).
3. **Bill maturity and basis.** `t` (91 days fixed, or the actual days of the bill behind the published rate) and how the 365/366 rule is applied without issue dates in the rates file.
4. **Cost unit.** 0.5 bp "per round trip on bills": bp of yield (times the bill's DV01) or of price.
5. **Flat months.** Whether months with position 0 enter the Sharpe as zero returns or are dropped.
6. **Bootstrap seed** for the 10,000-draw SE (minor, but it is a free choice that moves the decision near the boundary).

### R3-03
1. **CPI arm regression.** "CPI NSA seasonal factors scaled by in-sample regression": the regression (d on the month's factor change? log factor? with intercept?) is not specified. This arm also lacks its data (above).
2. **Shrinkage is a no-op for the own-history arm.** The position is the sign of the forecast, so shrinking by 0 or 0.5 toward zero gives identical positions: T01 and T03 are the same strategy. This does not stop the run, but the 24-trial count overstates the family and should be stated.
3. **Return base and the balance-sheet charge.** The outcome is in bp of breakeven; 25 bp a year of gross notional needs a breakeven DV01 per notional (TIPS plus nominal legs), not given.
4. **Round trip definition.** 1 bp "per round trip" with a one-month hold: charged every month, or only when the sign changes.

## What closes the gaps

A signed amendment 4 per study (or one shared text, as amendment 3), fixing each item above before any in-sample run, plus a study runner that refuses dates past the in-sample end without the freeze commit hash (common rules). Then: in-sample run and PBO, freeze commit, `holdout_runs.csv` line committed, one holdout run per study, Holm across the three. Owner or delegated signer decides; this lane does not sign.

When: as soon as amendment 4 is signed; each study then takes about one session (fetch, in-sample, freeze, holdout). The forward log keeps `"signal": null` until each J-2 run date (am. 3 rule 2).

## Run lane, 2026-11-14 (branch `stage-j-r3run`): stopped before step 3

Done: deviation note for the amendment 4 DV01 wording (`research/DEVIATION-2026-11-14-a4-dv01-wording.md`); loader `research/r3_data.py` (100 public files fetched once, logged with URL, UTC time and SHA-256 in `research/r3/data_log.csv`; holdout files hashed, never parsed; parsing them goes through `r3_runner.holdout_guard`); in-sample runs `research/r3_in_sample.py`, results `research/r3/in_sample.json`. No freeze commit, no `holdout_runs.csv` line, no holdout value parsed.

### R3-01: stopped, a choice is open

Amendment 4 item 1 fixes the leg DV01 as `price_from_yield` (`quantforge_core.bonds`) of a par bond settled on each date. `quantforge_core` calendars cover 2000 to 2099 only (`calendars.MIN_YEAR = 2000`), so `price_from_yield` refuses every date in 1990-1999 (`E_DATE_RANGE`: "0 months from 1992-01-02 leaves the calendar's years"). The in-sample window is 1990-01-02 to 2012-12-31. Options, none chosen here: (a) closed-form par-bond DV01 for the whole sample (at a coupon date a par bond's price is 1 and its modified duration has a closed form; the same number the library gives where it can price), (b) widen the library's calendar range, (c) start the in-sample at 2000 (changes the window; not allowed by the prereg). It needs a signed amendment 5 before any R3-01 statistic is computed.

### R3-02 and R3-03: in-sample done, held before freeze on purpose

- R3-02: 1,188 aligned business days (bill 13-week CE, SOFR, TGCR, BGCR); common sample 43 monthly returns (exits 2019-06-03 to 2022-12-01). Every trial has a negative in-sample net Sharpe; the best is T02 (SOFR, L 60, k 2.0), -0.56 (4 non-zero months of 43). PBO: not computable (a CSCV block has zero standard deviation; mostly-flat trials), so the study is labelled exploratory (C8).
- R3-03: 156 month ends, 155 in-sample returns; T01 (= T03) net Sharpe 0.44 at 1x, 0.36 at 2x (an in-sample fit, as amendment 4 item 5 states); T02/T04 not run; PBO not applicable. The 5Y-pair business days equal the 5Y+10Y-pair days in-sample (3,254 each), so including the 10Y robustness pair in C10's "every input" changes nothing.

Why R3-02 and R3-03 were not frozen and run although they could be: condition (1) is Holm across all three studies, so no holdout verdict can be complete without R3-01, and R3-01 needs an amendment first. Running two one-shot holdouts now would mean the R3-01 amendment is signed after two holdout outcomes are known. Stopping all three keeps the amendment clean; resuming R3-02/R3-03 costs minutes (freeze, log line, run).

Stated overlap: R3-03's in-sample years 2013-2015 are R3-01 holdout years of the nominal 5Y and 10Y yields. The loader never gives R3-03 the 2Y column, so the R3-01 fly cannot be formed from it; no R3-01 quantity was computed.

### R3-01 in-sample after amendment 5 (2026-11-14)

5,755 aligned business days (1990-01-02 to 2012-12-31); common sample 5,256 daily returns (from the first full 500-day window). In-sample net Sharpe at 1x: T01 -0.71, T02 -0.34, T03 -0.61, T04 -0.47, T05 -0.07, T06 -0.10, T07 0.02, T08 0.05; all negative at 2x. Selected T08 (L 500, k 1.5). PBO 0.151 (below 0.5, not exploratory). R3-02 and R3-03 in-sample results unchanged by the re-run.
