# Q6-01: churn bound for calibration on real option quotes

Status: **signed**. Signed by Claude (stage I spec lane; signing delegated by the owner) on 2026-11-11.
- SHA-256 of the body below the marker line: `1c79d758e31f8e193be728ba22ee7518e2284d5d4ed446630bed561017ea2f28`
- SHA-256 of the R3 common rules (`README.md` body), for reference only: `53566e4c3060d1adfd386a543b8d789b1de0b9b53393a8ffa03e0c3f4b5d58aa`
- No option quote has been downloaded and no fit has been run at signing.
- This file is not edited after signing; a change is a new prereg.

<!-- body -->
Plan item Q6 (QUANTFORGE_PLAN.md 12.4): calibration on real noisy option quotes, with a parameter time series, a churn penalty and arbitrage repair; acceptance "no butterfly or calendar arbitrage after the fit; churn under a preregistered bound". This file fixes the churn bound, the penalty grid and the selection rule before any quote is downloaded or any fit is run. It does not depend on the data source; the source is still open (data terms: see "Data source" below). The R3 common rules in `README.md` are not part of this prereg (no trading signal is tested).

## Definitions

- Grid `G`: log-forward-moneyness `k` in {-0.20, -0.15, -0.10, -0.05, 0, 0.05, 0.10, 0.15, 0.20} times expiries {30, 60, 91, 182, 365} calendar days (45 nodes). Fitted implied volatility `s_t(k, T)` on the grid is read from the day-`t` fit by interpolation in total variance `w = s^2 T`, linear in `T` at fixed `k`. A node outside the quoted expiry range of day `t` is dropped for that day and the following one.
- Surface churn `C_t = sqrt(mean over G of (s_t - s_{t-1})^2)`, in volatility units (0.01 = 1 vol point).
- Market move `A_t = sqrt(mean over the five expiries of (a_t(T) - a_{t-1}(T))^2)`, where `a_t(T)` is the at-the-forward implied volatility of the same day's fit (so the level move is measured, and the shape change is what churn adds).
- Churn ratio `R_t = C_t / max(A_t, 0.001)`. The floor of 0.1 vol point keeps quiet days, when `A_t` is close to 0, from dividing by noise.
- Penalised fit: day `t` minimises `sum_q ((model_q - mid_q) / h_q)^2 + lambda * |G| * C_t^2 / 0.001^2`, with `h_q` the quote's half-spread in price, so both terms are dimensionless and a churn of 0.1 vol point costs `lambda` per grid node.

## Fixed choices

1. Penalty grid `lambda` in {0, 0.1, 0.3, 1, 3, 10}. No value outside the grid may be tried without a new prereg. Every evaluated `lambda` is logged as a trial.
2. Selection: the first 20% of trading days (chronological) are the selection sample. The chosen `lambda` is the smallest grid value whose selection-sample fit-quality share (rule 4) is at least 80%; `lambda = 0` is allowed if it meets the churn bound on its own. The remaining 80% is the test sample and is fitted once with the chosen `lambda`.
3. **Churn bound** (test sample, all days with a previous day): median `R_t <= 1.5` **and** 95th percentile `R_t <= 3.0`.
4. Fit quality, so that a large penalty cannot buy low churn by ignoring the quotes: at least 80% of the test-sample quotes have `|model - mid| <= h` (inside the bid-ask spread).
5. Arbitrage, the plan's other acceptance: on the grid `G` of every test day, total variance non-decreasing in `T` at each `k` (no calendar arbitrage) and the Durrleman condition `g(k) >= 0` on each expiry slice (no butterfly arbitrage), checked to 1e-10.
6. Pass: rules 3, 4 and 5 all hold. Otherwise Q6 fails and the failure is reported with the same prominence.

## Justification of the bound

- The ratio measures shape change against level change. Under a sticky-moneyness surface, a day's change is a level shift and `R_t` is about 1; a median of 1.5 allows shape moves half as large as the level move on a typical day. The 95th-percentile bound of 3 allows event days (earnings, macro releases) where skew moves more than the level. These are judgement choices fixed before any data was seen, not values fitted to data.
- The 0.1 vol point floor is an assumption, not a measured spread: it is meant to be below the quoted bid-ask half-spread of liquid index options, so a churn below it is not distinguishable from quote noise. If the data show half-spreads below 0.1 vol point at the money, that is reported as a limitation; the floor is not changed.
- A ratio bound is used rather than an absolute one (for example "below 0.5 vol point") because an absolute bound would pass or fail with the market's own volatility of volatility rather than with the fit's stability.

## Data source

Not chosen. On 2026-11-11 the public terms of both named sources were read (no account, no sign-up): the Cboe delayed-quote pages prohibit download by automated programs, and Cboe's website terms and Deribit's terms of service both forbid publishing derived data without prior written consent. The findings and links are in the plan folder (`STAGE_I_DATA_TERMS.md`). A source, or written consent, needs an owner decision; this prereg holds for whichever source is approved, and no fit is run before then.
