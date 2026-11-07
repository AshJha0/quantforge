# R3-03: Seasonality in US breakeven inflation

Status: **signed**. Signed by Claude (signing delegated by the owner, 2026-11-07) on 2026-11-07.
- SHA-256 of the body below the marker line: `08537a3964958f91e1c7dafd6963612236853244e5b4bb8fd6af91ba2937646a`
- SHA-256 of the common rules (`README.md` body): `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- Holdout data has not been read, downloaded or summarised. No study data of any period has been downloaded at signing.
- This file is not edited after signing; a change is a new prereg.

<!-- body -->
Common rules: `README.md`.

**Label:** signal on a fitted curve; tradability not established.

## Question
Do month-of-year effects in headline CPI show up as a predictable seasonal pattern in monthly changes of the 5-year breakeven, beyond what is known in advance?

## Data
- FRED series T5YIE (5-year breakeven, daily, from 2003-01-02) and T10YIE as a robustness series. Breakevens are derived from Treasury nominal and TIPS yields (public data via FRED; licence terms checked at download).
- BLS CPI-U NSA, for the in-sample seasonal factors only.
- In-sample: 2003-01-02 to 2015-12-31. Holdout: 2016-01-04 to 2026-10-30, unread. Forward log: from signing.

## Method (fixed)
- Monthly change `d_m` in T5YIE, from the last business day of one month to the last of the next, in bp.
- Seasonal forecast: the in-sample mean of `d` by calendar month, shrunk toward zero by a factor `lambda`. Position: the sign of the forecast for the coming month, held one month.
- Grid (4 trials): `lambda` in {0, 0.5}, by forecast source in {own breakeven history, CPI NSA seasonal factors scaled by in-sample regression}.
- No re-estimation in the holdout: seasonal factors are frozen at the in-sample end.

## Costs and financing (sensitivity only)
1x = 1 bp of breakeven per round trip (TIPS against nominal), and 25 bp a year of balance-sheet charge. Inflation-swap quotes are not free, so the swap route is not tested (a stated limit).

## Statistics and pass rule
- 12 outcomes a year. Sharpe standard error from Lo (2002) with 3 lags.
- Holdout T = 10.83 years, MDS = 0.76. **Threshold:** holdout deflated Sharpe ratio above 0.95, and holdout net Sharpe at least 0.76.
- Sub-periods: thirds of the holdout. The 2021 to 2022 inflation shock sits in the middle third.
- Correlations with carry (the breakeven roll-down) and a 12-month momentum factor are reported.
- **Pass rule (all three, per `research/TEMPLATE.md` section 5):** (1) holdout deflated Sharpe ratio above 0.95 and holdout net Sharpe at least the MDS above; (2) holdout net Sharpe still above 0 at 2x costs; (3) the holdout Sharpe has the same sign in each third of the holdout. Otherwise the study fails and is published as a null result.
- **Forward log:** live paper out-of-sample from the signing date, 2026-11-07, judged on the same rule after 250 US business days.

## Known limits
Breakevens are fitted from par curves and include liquidity and convexity premia. The index lag (`02-curves/inflation.md`) means an announced CPI moves the breakeven before the accrual it affects.
