# R3 preregistrations

<!-- body -->
Three relative-value studies on free public daily data. Plan 11.1.1 to 11.1.3 and 11.3. Signing: delegated by the owner to Claude on 2026-11-07. Each prereg's header records the signer, the date, and the SHA-256 of its body (the bytes after the `<!-- body -->` line) and of this file's body, which holds the common rules. A signed prereg is never edited; a change is a new prereg.

## Common rules (part of each prereg)

- **Holdout unread.** No data after the in-sample end is downloaded, plotted or summarised until the prereg is signed and the in-sample analysis is frozen by a commit. The study runner refuses a date range past the in-sample end unless it is given the signed commit hash. The holdout is then run once.
- **Forward log** (branch `forward-log`, recorded by the scheduled Actions job) is the live paper out-of-sample. It is judged after 250 business days. The 60-day mark is a pipeline check only.
- **Label:** every result reads *signal on a fitted curve; tradability not established*.
- **Costs** are a sensitivity table at 0.5x, 1x and 2x of the stated assumption, never a P&L claim.
- **Multiple testing.** The full parameter grid is fixed here. Every evaluated set is logged as a trial, and the deflated Sharpe ratio uses that count. No parameter outside the grid may be tried without a new prereg.
- **Report** on `research/TEMPLATE.md`. Pass rule: holdout deflated Sharpe above the threshold, still positive net at 2x costs, and sign-stable across thirds of the holdout.

## Power calculation (shared method)

For an annualised Sharpe ratio estimated from `T` years of returns, the standard error is about `sqrt((1 + SR^2/2) / T)` (Lo 2002, iid). For a one-sided test at 5% with 80% power, the minimum detectable Sharpe near zero is

`MDS = (z_0.95 + z_0.80) / sqrt(T) = (1.6449 + 0.8416) / sqrt(T) = 2.4865 / sqrt(T)`.

Serial correlation in returns raises it. Each prereg states its holdout `T` and `MDS`, and the deflated Sharpe threshold is never set below `MDS`.

| Study | Holdout | T (years) | MDS (annualised) | Forward log, 250 days |
|---|---|---|---|---|
| 1 Treasury fly mean reversion | 2013-01-02 to 2026-10-30 | 13.83 | 0.67 | 2.49 |
| 2 Bill against repo spread | 2023-01-03 to 2026-10-30 | 3.83 | 1.27 | 2.49 |
| 3 Breakeven seasonality | 2016-01-04 to 2026-10-30 | 10.83 | 0.76 | 2.49 |

The forward log alone can only detect a Sharpe near 2.5 in a year. It confirms a pipeline and guards against look-ahead; it cannot establish a modest signal by itself.
