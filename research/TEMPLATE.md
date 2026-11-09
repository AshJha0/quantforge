# Research study template

Plan 11.3. Every QuantForge study, in R3 and stage J, reports on this template, whether its result is positive, null or negative. Null results are published with the same prominence.

**Required label on every result, table and chart:** *signal on a fitted curve; tradability not established.* Par and fitted yields are not tradable instruments. Free data has no instrument-level prices, bid/ask, repo specials or futures. Costs are a sensitivity table, never a P&L claim (plan 11.1.3).

## 1. Identity
- Study id, title, preregistration file and its commit hash (signed before any holdout data is read).
- Library version (QuantForge tag and commit), data snapshot hashes, run date.

## 2. Data
- Sources, licences, series ids, download dates, snapshot hashes (`core.snapshot.*`).
- In-sample, holdout and live forward-log periods, exactly as preregistered.
- Gaps, revisions and how each was handled.

## 3. Method
- The signal, the position rule and the rebalance frequency, as preregistered. Any change after signing is listed here as a deviation, with the reason, and the study is labelled exploratory.
- Trial count: every parameter set ever evaluated, logged automatically by the study runner, never hand-counted.

## 4. Results (in-sample, holdout and forward log, each reported separately)

| Measure | In-sample | Holdout | Forward log |
|---|---|---|---|
| Gross Sharpe (annualised), 95% CI | | | |
| Net Sharpe at 1x costs, 95% CI | | | |
| Deflated Sharpe ratio (Bailey and Lopez de Prado), given the logged trial count | | | |
| Probability of backtest overfitting (CSCV, 16 blocks) | | | |
| Turnover per year; mean holding period | | | |
| Capacity estimate, with its assumption | | | |
| Maximum drawdown; longest time under water | | | |
| Sharpe by sub-period (thirds of the period) | | | |
| Correlation with carry, momentum, and level, slope and curvature factors | | | |

Cost sensitivity: net Sharpe at 0.5x, 1x and 2x of the preregistered cost assumption.

Confidence intervals for Sharpe use the Lo (2002) standard error with the autocorrelation adjustment, or a stationary block bootstrap of 10,000 draws when returns are serially dependent. The method is stated in the prereg.

## 5. Verdict

A study **passes** only if all three hold:
1. the holdout deflated Sharpe ratio beats the preregistered threshold;
2. the holdout net Sharpe is still positive at 2x costs;
3. the sign of the holdout Sharpe is the same in every sub-period.

Otherwise it **fails**, and is reported as a null or negative result. The forward log is judged after 250 business days; the 60-day check is a pipeline check only.

## 6. Limitations
- *Signal on a fitted curve; tradability not established.*
- Every assumption about costs, financing and capacity, with its source.
- Self-assessment until the human review at the end of the project.

## 7. AI assistance
Recorded for every study and every prereg or amendment (plan 13.1 R5, A8 brought forward).
- Tool and version: product, model id, and the date used.
- What it did: drafting text, writing code, choosing parameters, signing under delegation.
- Prompts kept: where the prompts and replies are stored, or a statement that they are not.
- Claims checked by a human: which claims a person verified, by whom and when; anything not yet checked is listed as unchecked.
- Prior knowledge: whether the tool, or the person, could know the holdout period's history. A model trained on data that covers the holdout period may "know" it even though no study data was read. "Unread" means no file was opened; it does not mean "unknown".
