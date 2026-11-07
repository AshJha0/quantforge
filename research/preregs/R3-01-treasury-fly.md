# R3-01: US Treasury curve butterfly mean reversion

Status: **signed**. Signed by Claude (signing delegated by the owner, 2026-11-07) on 2026-11-07.
- SHA-256 of the body below the marker line: `2b811952d283ffd7f5e626ca4b4d765d413915ed039471c461420ff1a8c336c7`
- SHA-256 of the common rules (`README.md` body): `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- Holdout data has not been read, downloaded or summarised. No study data of any period has been downloaded at signing.
- This file is not edited after signing; a change is a new prereg.

<!-- body -->
Common rules: `README.md`.

**Label:** signal on a fitted curve; tradability not established.

## Question
Does the 2s5s10s butterfly on the US Treasury par curve mean-revert enough that a z-score rule earns a positive Sharpe on a DV01-neutral, duration-neutral fly, after costs?

## Data
- US Treasury daily par yield curve rates, 1990 onward (public domain, home.treasury.gov). Tenors 2Y, 5Y, 10Y.
- In-sample: 1990-01-02 to 2012-12-31. Holdout: 2013-01-02 to 2026-10-30, unread. Forward log: from the signing date.

## Method (fixed)
- Fly level `f_t = 2 y5 - y2 - y10`, in bp.
- Signal `z_t = (f_t - mean_L) / sd_L` over a trailing window `L`. Position: short the fly (pay the body) when `z_t > k`, long when `z_t < -k`, flat when `|z_t| < 0.5`; between 0.5 and `k` the previous position is held. Rebalanced daily on the close, entered the next day.
- Return proxy: the change in the fly level times the position, in bp. Converted to a return using par-bond DV01s from `bond.price.from_yield` at each day's par yields, weights DV01-neutral and duration-neutral.
- Grid (8 trials): `L` in {60, 120, 250, 500} business days, `k` in {1.0, 1.5}.

## Costs and financing (sensitivity only)
1x = 0.25 bp of yield per leg per trade on the fly's DV01, plus a balance-sheet charge of 25 bp a year on gross notional. No repo specials are available, so financing is flat at the general-collateral rate (a stated limit).

## Statistics and pass rule
- Sharpe standard error: Lo (2002) with the autocorrelation adjustment, 20 lags.
- Holdout T = 13.83 years, MDS = 0.67. **Threshold:** holdout deflated Sharpe ratio, given the logged trial count, above 0.95, and holdout annualised net Sharpe at least 0.67.
- PBO by CSCV over 16 in-sample blocks is reported; above 0.5 makes the result exploratory.
- Correlations with level, slope and curvature (first three PCs of in-sample yield changes) and a carry proxy are reported.
- **Pass rule (all three, per `research/TEMPLATE.md` section 5):** (1) holdout deflated Sharpe ratio above 0.95 and holdout net Sharpe at least the MDS above; (2) holdout net Sharpe still above 0 at 2x costs; (3) the holdout Sharpe has the same sign in each third of the holdout. Otherwise the study fails and is published as a null result.
- **Forward log:** live paper out-of-sample from the signing date, 2026-11-07, judged on the same rule after 250 US business days.

## Known limits
Par yields are fitted, not traded. On-the-run and off-the-run effects, bid/ask and repo specials are missing.
