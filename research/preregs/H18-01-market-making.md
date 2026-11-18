# H18-01: inventory-aware market making (Avellaneda-Stoikov, GLFT) on a simulated lit book replaying recorded Kraken L2 data

Status: **UNSIGNED DRAFT**. Drafted 2026-11-18 by the QuantForge stage H research lane (Claude, claude-opus-5-5), writing only. The owner signs before any recorded data file is opened for this study. Until signed, no simulation on recorded data is run, no parameter is tried on recorded data, and the hashes below are blank.
- SHA-256 of the body below the marker line: `(set at signing)`
- Library commit of the simulator and quoting code at signing: `(set at signing)`
- This file is not edited after signing; a change is an amendment file.

<!-- body -->
Plan items: 15.1 "Research: a market-making strategy study under a signed prereg, reusing the quoting and order-book work"; STAGE_H_START.md item H-18 (proposed ID). It uses H-4a (Avellaneda-Stoikov quotes, [AS08]), the GLFT closed-form asymptotic quotes ([GLFT13]), H-2 (book rebuilt from the feed) and H-11 (simulated lit matching engine). Stage J supplies the deflated Sharpe ratio and PBO tooling.

**Required label on every result, table and chart:** *crypto venue; not equities or rates. Simulated fills on a replayed public book; no live orders; profitability not established.* Aggregates only: no individual order, trade or book row is published.

## 1. Data

- Source: Kraken public WebSocket L2 book feed, BTC-USD and ETH-USD, depth 100, recorded by the QuantForge recorder (`qf-crypto-data`, hourly `jsonl.gz` files named by UTC hour). The recorder is not changed for this study.
- Qualifying day: a UTC calendar day with all 24 hourly files present, total recorded coverage at least 23.5 hours, no single gap above 10 minutes, and the H-2 check (rebuilt book equals the venue checksum or snapshot at every checkpoint) passing on at least 99.9% of checkpoints. Both symbols must qualify on the same day. Qualification is decided from file names, sizes, timestamps and the H-2 checker's pass counts only, never from prices or P&L.
- Days before 2026-11-19 are excluded (no day up to 2026-11-18 qualifies; the recorder stopped overnight on every day so far).

## 2. Samples and holdout (rule 14.10.6)

- Selection sample: the first 20 qualifying days on or after 2026-11-19.
- Holdout: the next 10 qualifying days after the selection sample. If the recorder runs without a break, selection is 2026-11-19..2026-12-08 and holdout 2026-12-09..2026-12-18; the actual dates are whatever days qualify and are listed in the report.
- Forward log: every qualifying day after the holdout, judged after 60 qualifying days (pipeline check at 10).
- The holdout files are not opened by any study, page or check other than the one holdout run below. Any H-1 result or docs page built from the recorded data checks its dates against this window before it is committed.
- One holdout run only. A rerun after a code fix needs an amendment stating the fix, filed before the rerun.

## 3. Strategies and grid

Quotes are posted to the simulated lit engine (H-11) at the touch-rounded prices from the closed forms, one bid and one ask, size `q0`, refreshed on every book change or every 1 s, whichever comes first, with queue position assumed last at the price level (H-1 fill simulator bounds apply).

- S1 Avellaneda-Stoikov finite horizon [AS08], horizon `T` = 1 hour rolling: reservation price `r = s - q gamma sigma^2 (T - t)`, total spread `gamma sigma^2 (T - t) + (2/gamma) ln(1 + gamma/k)`.
- S2 GLFT asymptotic quotes [GLFT13] with inventory limit `Q`.
- Baseline B0: symmetric quotes at the touch, no inventory skew, same limit `Q`.
- `sigma` (mid volatility) and `k`, `A` (fill intensity `A exp(-k delta)`) are estimated on the previous 24 hours of the same symbol only (no look-ahead).
- Grid: `gamma` in {0.01, 0.1, 1} (per unit of base asset, scaled by `1/mid`), `Q` in {1, 5} lots, `q0` = 1 lot (lot = 0.01 BTC, 0.1 ETH). 6 parameter sets per strategy, 12 for S1 and S2, plus B0 (2 sets). Total 14 trials per symbol, 28 trials; every trial is logged by the runner. No value outside the grid without an amendment.
- Costs: Kraken published maker fee for the lowest volume tier on the signing date, recorded in the report; sensitivity at 0x, 1x, 2x. Inventory is marked to mid at each UTC day end and carried; no funding cost (spot).

## 4. Metrics

Per strategy and symbol, daily P&L series:
- Net daily Sharpe (annualised by sqrt(365)), 95% CI by stationary block bootstrap, 10,000 draws, mean block 5 days.
- Deflated Sharpe ratio (stage J implementation, Bailey and Lopez de Prado), with the logged trial count (28).
- PBO by CSCV (stage J), 10 blocks over the selection sample (S = 10, since 20 days is too short for 16).
- P&L decomposition: spread capture, inventory P&L, fees; fill rate; adverse-selection markout at 1 s, 10 s, 60 s; inventory distribution (mean absolute, time at limit); max drawdown.
- Fill-simulator sensitivity: results at the lower and upper fill bounds from H-1 (c).

## 5. Selection and hypotheses

- Selection: on the selection sample, for each of S1 and S2 the parameter set with the highest net Sharpe at 1x fees is chosen. One set per strategy goes to the holdout. B0 goes as well.
- H1 (primary): the chosen S1 or S2 has holdout net Sharpe above B0 by a one-sided paired block-bootstrap test at 5%, Holm-adjusted over the 2 strategies x 2 symbols (4 tests).
- H2: the inventory skew reduces mean absolute inventory against B0 on the holdout (paired, Holm over 4). This is a mechanism check; it can pass while H1 fails.

## 6. Pass and failure

A strategy-symbol pair **passes** only if all hold on the holdout:
1. DSR above 0.95 with 28 trials;
2. net Sharpe positive at 2x fees, and positive at the lower fill bound;
3. H1 rejects after Holm;
4. selection-sample PBO below 0.5;
5. the sign of the net Sharpe is the same in both halves of the holdout.

Anything else is a **failure** and is published with the same prominence as a pass, including a pass at the upper fill bound only (reported as "depends on the fill assumption"). A pass is a statement about a simulator replaying a public book; it is not evidence of live profitability.

## 7. Stopping rules

- The study stops, and is reported as failed without a holdout run, if the selection sample shows every S1/S2 set with net Sharpe below B0 at 1x fees, or if PBO is at least 0.5.
- If fewer than 30 qualifying days exist by 2027-01-10 (the v1.0.0 window), the study is reported as "not run: data not accrued"; the window is not shortened and the qualifying rule is not relaxed.
- No tuning after the holdout run. A failed holdout ends the study; a new idea is a new prereg on forward-log days only.
- If the H-2 check fails on more than 0.1% of checkpoints on a selection or holdout day, that day is dropped and replaced by the next qualifying day, logged; more than 3 drops stops the study for a recorder/book fix.

## 8. Limitations

- One lit venue, two symbols, public L2 (no queue or order IDs): queue position is assumed, so fills are bounded, not observed.
- No market impact of our own quotes on others; no latency model beyond the 1 s refresh.
- Self-assessment; no second review (owner decision 2026-11-18).

## 9. AI assistance

Drafted by Claude (claude-opus-5-5) on 2026-11-18; no recorded data row was opened (file names, sizes and timestamps only). The model may know 2026 crypto price history up to its training cutoff (June 2026); the holdout window (December 2026) is after that cutoff. Owner review and signature pending.

## References

[AS08] Avellaneda, M. and Stoikov, S. (2008), High-frequency trading in a limit order book, Quantitative Finance 8(3).
[GLFT13] Gueant, O., Lehalle, C.-A. and Fernandez-Tapia, J. (2013), Dealing with the inventory risk, Mathematics and Financial Economics 7(4) (arXiv v5).
