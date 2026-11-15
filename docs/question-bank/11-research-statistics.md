# Question bank 11: Research statistics and backtest honesty

This set is for anyone who wants to know whether a backtest result can be believed: a newcomer learning why a Sharpe ratio from a backtest is biased, and a practitioner checking exactly how QuantForge defines the lag, the purge, the PSR, the DSR and the PBO. Each answer gives the plain idea first, then the rule as the spec states it, then a worked example where numbers help. Every number in a worked example was produced by `quantforge_core` (the `research` and `research_w2` modules) and is re-checked by `docs/question-bank/verify/v11_research_statistics.py`. Levels: foundation, practitioner, advanced. Try each question before reading the answer.

The specs are in [`specifications/11-research`](../../specifications/11-research/README.md). Sharpe ratios in the PSR and DSR operations are per period, not annualised, and `kurtosis` is the non-excess fourth moment (3 for a normal).

## The backtester

### Q11.1 In `research.backtest.run`, which position earns bar `t`'s price move?

*Level: foundation. Evidence: spec; design. Source: [Backtester](../../specifications/11-research/backtester.md), [Stage J rulings, wave 1](../../specifications/stage-j-rulings-w1.md), [Tutorial 23](../getting-started/tutorial-23-backtest-honestly.md)*

The position held before bar `t`'s trade. A strategy decides its target at the close of bar `t` using information up to that close; it cannot also have held that target over the move into that close.

The event loop (ruling J-2), with `q_{-1} = 0`: the position after bar `t`'s close is `q_t = targets[t - lag]` for `t >= lag`, else 0; the trade is `d_t = q_t - q_{t-1}`; the holding P&L is `g_t = q_{t-1} (p_t - p_{t-1}) m`, with `g_0 = 0`. The default `lag` is 1: a target decided at close `t` is held from close `t + 1`.

The pitfall this prevents is the commonest backtest bug, letting a position earn the move that produced the signal. `lag = 0` is legal only so that a look-ahead canary can be built and caught (Q11.4); a study runner refuses `lag = 0` unless its prereg says so.

### Q11.2 Work a five-bar backtest by hand: what are the positions, trades and gross P&L?

*Level: foundation. Evidence: computed; spec. Source: [Backtester](../../specifications/11-research/backtester.md), [Tutorial 23](../getting-started/tutorial-23-backtest-honestly.md)*

Shift the targets by the lag to get positions, difference them to get trades, and multiply each bar's price change by the position held before it.

**Worked example.** Prices 100, 102, 101, 104, 103; targets 1, 1, -1, 0, 0; lag 1; multiplier 1. Positions are `[0, 1, 1, -1, 0]` and trades `[0, 1, 0, -2, 1]`. Gross P&L per bar is `[0, 0, -1, 3, 1]`: bar 1 earns nothing because the position before its trade was 0; bar 2 earns `1 x (101 - 102)`; bar 3 earns `1 x (104 - 101)`; bar 4 earns `-1 x (103 - 104)`. Total gross 3.

The short target at bar 2 only starts earning at bar 4, two bars after the signal: one bar of lag, and one because the move into a close belongs to the position held before it.

### Q11.3 How are costs charged in the backtester, and what identity must the totals satisfy?

*Level: practitioner. Evidence: computed; spec. Source: [Backtester](../../specifications/11-research/backtester.md), [Tutorial 23](../getting-started/tutorial-23-backtest-honestly.md)*

Every change in position pays three costs at that close: half the spread on the traded value, a commission per unit, and a fixed fee per trade. Formally, `s_t = |d_t| p_t (half_spread_bps / 10^4) m`, `c_t = |d_t| commission_per_unit`, `f_t = fixed_per_trade` if `d_t != 0`. Net `n_t = g_t - (s_t + c_t + f_t)`. The totals satisfy `total_gross - total_spread_cost - total_commission - total_fixed_cost = total_net`, which the generator asserts in exact arithmetic.

**Worked example.** The backtest of Q11.2 with a 10 bp half-spread, 0.05 per unit commission and 1 per trade. Bar 3 trades 2 units at 104: `2 x 104 x 0.001 + 0.10 + 1` = 1.308. Totals: gross 3.000, spread 0.413, commission 0.200, fixed 3.000 (3 trades), net -0.613. Turnover is 413.

A strategy with a positive gross and a negative net is common; the attribution shows which cost did it. Here the fixed fee alone is the whole gross.

### Q11.4 What is the look-ahead canary, and what does it show?

*Level: practitioner. Evidence: computed; spec. Source: [Backtester](../../specifications/11-research/backtester.md), [Stage J rulings, wave 1](../../specifications/stage-j-rulings-w1.md), [Tutorial 23](../getting-started/tutorial-23-backtest-honestly.md)*

A canary is a strategy that cheats on purpose, so you can check that the backtest catches it. Its target at close `t` is `sign(p_{t+1} - p_t)`, the direction of the next move, which no real strategy can know. At `lag = 0` it earns every move; at `lag = 1` the cheat is removed and it should earn nothing systematic.

**Worked example.** Prices 100, 101, 100.5, 102, 101, 101.5, 103, 102.5, with targets the sign of the next move (0 on the last bar). At `lag = 0` the gross P&L is 6.5, the sum of all the absolute moves. At `lag = 1` it is -2.5.

The property test in each language asserts that the canary is detected at `lag = 0` and absent at `lag = 1` on a driftless random walk (plan item Q7, ruling J-2). A study whose real signal looks like the `lag = 0` canary has a look-ahead bug.

### Q11.5 Why does the backtester have two engines, and how equal must they be?

*Level: foundation. Evidence: spec; design. Source: [Backtester](../../specifications/11-research/backtester.md), [Stage J rulings, wave 1](../../specifications/stage-j-rulings-w1.md)*

`EVENT` runs the loop bar by bar, which is easy to read and hard to get wrong about timing. `VECTOR` computes the same quantities as whole arrays (shifted targets, differences, products, a cumulative sum), which is fast. A vectorised backtest is where look-ahead usually creeps in, through a shift in the wrong direction. Requiring the two to agree turns that bug into a test failure.

Ruling J-3: `VECTOR` must equal `EVENT` to `1e-10` relative on every output, checked by a property test in each language on random strategies. Both follow one normative definition, so the agreement holds trivially when both are right.

The backtester has no randomness and no iteration: every output is a finite sum of products in a fixed order. Its limits are stated: one instrument per call, full fills at the close plus or minus the half-spread, no impact, borrow cost, financing or dividends.

### Q11.6 How does the backtester define maximum drawdown?

*Level: practitioner. Evidence: computed; spec. Source: [Backtester](../../specifications/11-research/backtester.md)*

Drawdown is how far equity has fallen from its best level so far. The spec takes the peak with a starting equity of 0, so a strategy that loses from the first bar has a drawdown from 0, not from its first (negative) value:

`max_drawdown = max_t (max_{u <= t} max(E_u, 0) - E_t)`.

**Worked example.** The costed backtest of Q11.3 has equity `[0.000, -1.152, -2.152, -0.460, -0.613]`. The peak stays at 0 throughout, so the maximum drawdown is 2.152, at bar 2.

Starting the peak at 0 matters for short or losing backtests: without it, the drawdown of a strategy that never made money would be measured from its first loss and would understate the damage. The spec's own ten-trade example has a drawdown of 8.87575.

## Cross-validation without leakage

### Q11.7 Why does plain k-fold cross-validation leak information in finance?

*Level: foundation. Evidence: spec; literature. Source: [Purged CV](../../specifications/11-research/purged-cv.md), [Tutorial 23](../getting-started/tutorial-23-backtest-honestly.md)*

A financial label usually spans time: a 5-day forward return labelled on Monday depends on prices up to the next Monday. If a training observation's label window overlaps the test period, the model has seen part of the test answer. Plain k-fold ignores this.

QuantForge's `research.cv.purged_kfold` gives each observation a label window `[t0_i, t1_i]`. Purging drops every training observation whose window overlaps the test span; the embargo also drops a few observations just after the test block, because serial correlation carries information forward [LdP18 7.4].

The property tests make it concrete: no training label window overlaps the test span, and a planted leak (a feature equal to the label shifted inside the label window) scores high under plain k-fold and near zero under purged k-fold. Folds are contiguous blocks in `numpy.array_split` order with no shuffling (ruling J-7).

### Q11.8 In a purged, embargoed 2-fold split, which observations end up in each training set?

*Level: practitioner. Evidence: computed; spec. Source: [Purged CV](../../specifications/11-research/purged-cv.md)*

For each test block, find its span from the first start to the last end, drop every outside observation whose window touches it, then drop the embargo after the block.

**Worked example.** `t0 = 0..7`, `t1 = t0 + 1`, `k = 2`, `embargo_pct = 0.125`, so `h = floor(0.125 x 8) = 1`. Fold 0 tests 0 to 3, span `[0, 4]`; observation 4 (window `[4, 5]`) touches it and is purged, and the embargo would drop index 4 too. Train: 5, 6, 7. Fold 1 tests 4 to 7, span `[4, 8]`; observation 3 (window `[3, 4]`) touches it and is purged; nothing follows the block. Train: 0, 1, 2. `embargo_count` = 1.

Each fold loses one training observation to purging, a quarter of the training data here. With longer labels the loss grows, which is the price of an honest score.

### Q11.9 Does a label window that only touches the test span count as an overlap?

*Level: foundation. Evidence: spec. Source: [Purged CV](../../specifications/11-research/purged-cv.md)*

Yes. The spec uses closed intervals: training observation `j` is purged when `t0_j <= hi` and `t1_j >= lo`, where `[lo, hi]` is the test span. "Touching counts as overlap."

In Q11.8, observation 3 has window `[3, 4]` and the second test span starts at 4; they share only the point 4, and observation 3 is purged. Under half-open intervals it would have been kept.

The choice errs on the side of dropping data. A label that ends at the instant the test period starts may still share that instant's price with the first test label, so closed intervals are the safe reading. With `t1 = t0` and `embargo_pct = 0` the result equals plain contiguous k-fold, which is a property test.

### Q11.10 Where is the embargo applied, and how many observations does it drop?

*Level: practitioner. Evidence: spec; design. Source: [Purged CV](../../specifications/11-research/purged-cv.md), [Stage J rulings, wave 1](../../specifications/stage-j-rulings-w1.md)*

Only after the test block. For a test block `[a, b)`, the embargo drops indices `b .. b + h - 1`, with `h = floor(embargo_pct * n)` (ruling J-8). Observations before the test block are not embargoed: information leaks forward in time through serial correlation, not backward.

`embargo_pct` must lie in `[0, 1)` (`E_DOMAIN` otherwise), and the embargo is an index count. A time-based embargo in calendar units is left to the caller, who converts it to an index count first; the spec says so in its limitations.

The embargo can overlap the purge, as in Q11.8 where index 4 was both. Each index is dropped once. The output reports `embargo_count` (`h`) so a reader can see how much was given up.

### Q11.11 How many splits and backtest paths does combinatorial purged CV give?

*Level: advanced. Evidence: computed; spec; literature. Source: [Purged CV](../../specifications/11-research/purged-cv.md)*

Combinatorial purged CV splits the data into `N` groups and tests on every combination of `k` of them. Each group then appears in several test sets, and stitching the test pieces gives several full backtest paths instead of one [LdP18 12.4].

`research.cv.cpcv_paths` returns `n_splits = C(N, k)` and `n_paths = k C(N, k) / N`, always an integer since `k C(N, k) = N C(N-1, k-1)`. `N` is limited to `2..64` (`E_LIMIT` above 64) and `1 <= k < N`.

**Worked example.** `N = 6, k = 2`: 15 splits, 5 paths, the figure in [LdP18]. `N = 10, k = 2`: 45 splits, 9 paths. `N = 10, k = 3`: 120 splits, 36 paths.

More paths give a distribution of out-of-sample Sharpe ratios rather than one number. The cost is more model fits, `C(N, k)` of them.

## Probabilistic and deflated Sharpe ratios

### Q11.12 What does the probabilistic Sharpe ratio measure?

*Level: foundation. Evidence: computed; spec; literature. Source: [Research statistics](../../specifications/11-research/research-statistics.md), [Tutorial 24](../getting-started/tutorial-24-is-the-sharpe-real.md)*

A backtest Sharpe ratio is an estimate. The PSR is the probability that the true Sharpe exceeds a benchmark, given the sample length, skew and fat tails [BLdP12].

With `v = 1 - skew sr + (kurtosis - 1)/4 sr^2`: `z = (sr - sr_benchmark) sqrt(T - 1) / sqrt(v)`, `psr = Phi(z)`. Inputs are per period.

**Worked example.** A daily Sharpe of 0.1 over 252 days, normal returns, benchmark 0: `z = 1.58035`, `psr = 0.942987`. A year of a daily Sharpe of 0.1 (about 1.6 annualised) is not yet 95% evidence that the true Sharpe is above zero.

The pitfall is treating a Sharpe ratio as a fact. The PSR says how much the sample supports it.

### Q11.13 How do negative skew and fat tails change the PSR?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Research statistics](../../specifications/11-research/research-statistics.md), [Tutorial 24](../getting-started/tutorial-24-is-the-sharpe-real.md)*

They widen the uncertainty of the Sharpe estimate, so the same Sharpe is weaker evidence. In `v = 1 - skew sr + (kurtosis - 1)/4 sr^2`, a negative skew with a positive Sharpe adds to `v`, and kurtosis above 3 adds more than a normal would.

**Worked example.** The Sharpe of Q11.12 (0.1 daily, 252 days) with skew -1 and kurtosis 6: `z = 1.50206`, `psr = 0.933459`, down from 0.942987 for normal returns.

The effect is small at a daily Sharpe of 0.1 because the `sr` and `sr^2` terms are small; it grows quickly for higher per-period Sharpe ratios. Strategies that sell insurance (short options, carry) have exactly this profile: a smooth Sharpe that overstates the evidence. `kurtosis < 1` is `E_DOMAIN`, as no distribution has it.

### Q11.14 The PSR operation takes a per-period Sharpe. How do you convert an annualised one?

*Level: foundation. Evidence: computed; spec. Source: [Research statistics](../../specifications/11-research/research-statistics.md)*

Divide by the square root of the number of periods per year. The spec says Sharpe ratios in `research.stats.psr` and `.dsr` are per period, and you annualise outside.

**Worked example.** The Bailey and Lopez de Prado example uses an annualised Sharpe of 2.5 over 250 trading days a year. Per period that is `2.5 / sqrt(250)` = 0.158114. The variance of the trials' annualised Sharpe, 0.5, becomes `0.5 / 250` per period.

Passing the annualised figure is the classic error: with `T = 1250` it makes the PSR essentially 1 for almost any strategy. The `n_obs` input is the number of periods (here 1,250 daily returns), not years.

### Q11.15 When does the PSR operation return `E_DOMAIN` rather than a probability?

*Level: advanced. Evidence: computed; spec; design. Source: [Research statistics](../../specifications/11-research/research-statistics.md), [Stage J rulings, wave 1](../../specifications/stage-j-rulings-w1.md)*

When the variance term `v = 1 - skew sr + (kurtosis - 1)/4 sr^2` is at or below zero (ruling J-14), and when `kurtosis < 1`. The spec refuses rather than clamping `v` to a small positive number, because a clamp would invent a precise-looking probability from a formula that has broken down.

**Worked example.** `sr = 1.0` per period, `T = 100`, skew 3, kurtosis 3: `v = 1 - 3 + 0.5 = -1.5`, and the library returns `E_DOMAIN`.

A per-period Sharpe of 1 with skew 3 is far outside the range where the asymptotic formula holds. The spec's limitations say what to use instead for short or strongly autocorrelated series: the stationary block bootstrap of the R3 preregs.

### Q11.16 What is the deflated Sharpe ratio, and does QuantForge reproduce the published example?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Research statistics](../../specifications/11-research/research-statistics.md), [Tutorial 24](../getting-started/tutorial-24-is-the-sharpe-real.md)*

If you try `N` strategies with no skill, the best one still shows a positive Sharpe by luck. The DSR is the PSR measured against that lucky best instead of against 0 [BLdP14]:

`SR0 = sqrt(sr_variance) ((1 - gamma) Phi^{-1}(1 - 1/N) + gamma Phi^{-1}(1 - 1/(N e)))`, with `gamma` = 0.5772156649015329 (Euler-Mascheroni), then `dsr = Phi(z)` with `z` as in the PSR against `SR0`.

**Worked example.** The paper's numbers: annualised Sharpe 2.5, `T = 1250` daily returns, skew -3, kurtosis 10, `N = 100` trials, trial variance 0.5 annualised. QuantForge gives `SR0` = 0.1132 per period and `DSR` = 0.9004, the paper's printed four digits (golden `rstats_j-0001`; the paper was read on 2026-11-13). With `N = 46` the DSR is 0.9505, also as printed.

0.9004 is below 0.95: after 100 trials, a 2.5 Sharpe is not convincing.

### Q11.17 What `N` does a study pass to the DSR, and what happens with `N = 1`?

*Level: advanced. Evidence: computed; spec; design. Source: [Research statistics](../../specifications/11-research/research-statistics.md), [Stage J rulings, wave 1](../../specifications/stage-j-rulings-w1.md), [R3 preregistrations](../../research/preregs/README.md)*

`N` is the number of trials logged in the trial registry, `research/trials.csv`, never a smaller number (ruling J-13, plan item Q7). The research package's `trials.register` appends a trial before it is run and refuses a duplicate id, so the count cannot be lowered after the fact; `trials.trial_count` returns the distinct trial ids for a study.

`N = 1` gives `SR0 = 0` (no selection), because `Phi^{-1}(1 - 1/N) = Phi^{-1}(0)` is infinite. The DSR is then the PSR against 0.

**Worked example.** The inputs of Q11.16 with `N = 1`: `SR0 = 0` and DSR 0.999997, against 0.9004 with `N = 100`. The whole difference is the selection.

The honest-research point: the DSR is only as good as the trial count. A study that reports 1 trial after trying 100 gets a near-certain result for free, which is why the count is logged before each run.

## Backtest overfitting and power

### Q11.18 How does CSCV estimate the probability of backtest overfitting?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Research statistics](../../specifications/11-research/research-statistics.md), [Tutorial 24](../getting-started/tutorial-24-is-the-sharpe-real.md)*

PBO asks how often the in-sample winner ranks in the bottom half out of sample [BBLdPZ17]. Split the periods into `S` blocks; for every way of choosing half the blocks as training, pick the best strategy on the training half and see where it ranks on the rest.

Steps (ruling J-16 for ties): `n*` = best train metric (lowest index on a tie); `omega = r / (N + 1)` with `r` its average test rank (1 = worst); logit `lambda = log(omega / (1 - omega))`; `PBO = (number of lambda <= 0) / C(S, S/2)`.

**Worked example.** The spec's hand case: rows `[1, 0], [1, 0], [0, 2], [0, 2]`, `S = 2`, metric `MEAN`. Each split's winner comes last out of sample, `omega = 1/3`, both logits are -0.693147, and `PBO = 1`. Swap the data to `[2, 0], [2, 1], [3, 0], [2, 1]` and strategy 0 wins both halves: logits 0.693147, `PBO = 0`.

A PBO near 1 means the selection process picks losers out of sample.

### Q11.19 How many combinations does PBO use, and what limits the number of blocks?

*Level: advanced. Evidence: computed; spec; design. Source: [Research statistics](../../specifications/11-research/research-statistics.md), [Stage J rulings, wave 1](../../specifications/stage-j-rulings-w1.md)*

`n_combinations = C(S, S/2)`. Ruling J-15 requires `S` even with `2 <= S <= 16`, `T` divisible by `S`, and at least 2 rows per block.

**Worked example.** `S = 16` gives `C(16, 8)` = 12870 combinations, each with its own logit in the output.

The cap of 16 keeps the work bounded while giving enough logits for a PBO to be more than a few coarse fractions. The floor of 2 rows per block is needed because the `SHARPE` metric divides by a sample standard deviation with divisor `n - 1`; a zero standard deviation in any block is `E_DOMAIN` (J-17). The spec warns that `T/S >= 2` is a floor, not a recommendation: PBO with `SHARPE` on short blocks is noisy.

### Q11.20 What is the minimum detectable Sharpe ratio of a study, and why do the R3 preregs state it?

*Level: foundation. Evidence: computed; spec; literature. Source: [Research statistics](../../specifications/11-research/research-statistics.md), [R3 preregistrations](../../research/preregs/README.md)*

It is the smallest annualised Sharpe that a study of a given length can tell apart from zero with stated error rates. A study that cannot detect the effect it hopes for is not worth running.

`research.stats.power`: `z_sum = Phi^{-1}(1 - alpha) + Phi^{-1}(power)`, `mds = z_sum / sqrt(years)` (one-sided, iid, near zero). Defaults `alpha = 0.05`, `power = 0.8`.

**Worked example.** `z_sum` = 2.4865. With a 13.83-year holdout, `mds` = 0.6686, the 0.67 of the R3-01 row in the prereg table (golden `rstats_j-0017`).

The R3 common rules never set the deflated Sharpe threshold below the MDS. The preregs also note that a 250-day forward log alone can only detect a Sharpe near 2.5: it confirms a pipeline and guards against look-ahead, but cannot establish a modest signal.

### Q11.21 How many years of data would a study need to detect an annualised Sharpe of 0.5?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Research statistics](../../specifications/11-research/research-statistics.md)*

Invert the MDS: `years_required = (z_sum / sr_target)^2`. The operation also returns the standard error at the target, `se_at_target = sqrt((1 + sr_target^2/2) / years)` [Lo02].

**Worked example.** `sr_target = 0.5`, defaults `alpha = 0.05`, `power = 0.8`, and 5 years of data. `years_required` = 24.7302; with only 5 years the MDS is 1.11199, and the standard error at 0.5 is 0.474342.

A Sharpe of 0.5 is a respectable real strategy, and it needs about 25 years of iid daily data to detect at these error rates. Short backtests mostly find either nothing or luck.

### Q11.22 Why does the spec say the iid power formula understates the MDS?

*Level: advanced. Evidence: spec. Source: [Research statistics](../../specifications/11-research/research-statistics.md), [R3 preregistrations](../../research/preregs/README.md)*

The formula assumes returns are independent from period to period. Many strategy returns are serially correlated: a mean-reversion position held for weeks produces runs of similar daily returns. Positive autocorrelation means fewer effectively independent observations, a larger standard error of the Sharpe, and a larger minimum detectable Sharpe.

The spec says so directly and states what is done about it: studies report the simulated power of `research/power/r3_power.py` beside the iid figure. The R3 common rules add that serial correlation raises the MDS and that each prereg states its holdout length and MDS.

Similarly, the PSR and DSR rest on the asymptotic normality of the Sharpe estimate; for short or strongly autocorrelated series the stationary block bootstrap of the R3 preregs gives the stated interval. Each closed form is offered alongside the check that covers its weak point.

## Preregistration as QuantForge practises it

### Q11.23 What does a preregistration fix in QuantForge, and how is it kept from being edited?

*Level: foundation. Evidence: spec; design. Source: [R3 preregistrations](../../research/preregs/README.md), [Tutorial 22](../getting-started/tutorial-22-q6-method-test.md)*

A preregistration writes down, before the data is looked at, what will be tested, on which data, with which parameter grid, and what counts as a pass. It stops the analysis being shaped by the result.

In QuantForge each prereg's header records the signer, the date and the SHA-256 of its body (the bytes after the `<!-- body -->` line) and of the common rules. A signed prereg is never edited; a change is a new amendment or a deviation note, with its own hash. Signing of the R3 preregs was delegated by the owner to Claude on 2026-11-07, and the file headers say so.

The common rules require the holdout unread until the prereg is signed and the in-sample analysis frozen by a commit, the full parameter grid fixed in the prereg, every evaluated set logged as a trial, costs reported as a sensitivity table at 0.5x, 1x and 2x, and every result labelled "signal on a fitted curve; tradability not established".

### Q11.24 What is the pass rule for an R3 study?

*Level: practitioner. Evidence: spec; design. Source: [R3 preregistrations](../../research/preregs/README.md), [Research statistics](../../specifications/11-research/research-statistics.md)*

Three conditions, all required, fixed in the common rules before any study ran: the holdout deflated Sharpe above the threshold, the strategy still positive net at 2x the stated costs, and the sign stable across thirds of the holdout.

Each part covers a different failure. The DSR, with `N` from the trial registry, covers selection among many trials. The 2x cost condition covers a cost assumption that was too kind. Sign stability across thirds covers a result carried by one episode. The DSR threshold is never set below the study's MDS, so a pass cannot come from a study too short to detect the effect.

The forward log, recorded by a scheduled job to its own branch, is the live paper out-of-sample, judged after 250 business days; the 60-day mark is a pipeline check only. Reports use `research/TEMPLATE.md`.

### Q11.25 What happens when the preregistered procedure is not followed exactly?

*Level: advanced. Evidence: spec; design. Source: [R3 preregistrations](../../research/preregs/README.md)*

It is disclosed in a signed deviation note, never fixed by editing the prereg. The R3 folder holds an example: `DEVIATION-2026-11-12.md` records that holdout-period data had been downloaded and published, contrary to a statement in the signed amendments, after an outside review found it and a scan reproduced it. The owner's decision kept the holdout dates and disclosed the breach.

The rule that makes this work is that a signed file cannot change: its body hash is recorded in later files, so a silent edit would be detectable. A deviation note states what the prereg said, what happened, and what it means for the results.

Preregistration does not make a study right. It makes departures from the plan visible, so a reader can judge how much the holdout result is still worth. Plan item Q6 (Tutorial 22) shows the same practice for a method test: the bounds were fixed in `Q6-01` before any fit, and the redesign is a new prereg, `Q6-02`.

## Regimes and the A5 surrogate

### Q11.26 What does the Viterbi path tell you, and what does it not?

*Level: foundation. Evidence: computed; spec; literature. Source: [Regimes](../../specifications/11-research/regimes.md), [Tutorial 26](../getting-started/tutorial-26-test-es-and-fit-regimes.md)*

Given a hidden Markov model with known parameters, Viterbi finds the single most likely sequence of states for the observations [Rab89 III.B]. The labels are descriptive: which regime the model thinks each day was in, not a forecast.

The recursion runs in logs, `delta_t(j) = max_i (delta_{t-1}(i) + log A_ij) + log e_t(j)`, with ties going to the smallest state index (ruling J-11).

**Worked example.** The textbook two-state case: states Healthy and Fever, initial `(0.6, 0.4)`, transitions `[[0.7, 0.3], [0.4, 0.6]]`, observations normal, cold, dizzy with emission rows `(0.5, 0.4, 0.1)` and `(0.1, 0.3, 0.6)`. The path is `[0, 0, 1]` (Healthy, Healthy, Fever) with log-probability -4.19174, i.e. joint probability 0.01512 (golden `regime_j-0001`).

The pitfall is using labels computed on the whole series as a trading signal: day `t`'s label used information after `t`.

### Q11.27 Run Baum-Welch with one state. What should it return, and after how many iterations?

*Level: practitioner. Evidence: computed; spec. Source: [Baum-Welch](../../specifications/11-research/baum-welch.md), [Tutorial 26](../getting-started/tutorial-26-test-es-and-fit-regimes.md)*

Baum-Welch is the EM algorithm for an HMM: compute how likely each day is to be in each state, re-estimate the parameters from those weights, and repeat until the log-likelihood stops improving. With one state every day has weight 1, so the first M-step gives the sample mean and the population standard deviation (divisor `T`), and the second leaves them unchanged.

Iteration (ruling J-W2-11): an E-step at the start values gives `L_0`; iteration `k` is an M-step and an E-step giving `L_k`; stop at the first `k` with gain `L_k - L_{k-1} < tolerance` (default `1e-10`).

**Worked example.** Returns 0.01, -0.02, 0.015, 0.005, 0.02, starting from mean 0 and sd 0.02. The fit gives mean 0.006 and sd 0.0139284 (the population sd; the sample sd would be 0.0155724), with `iterations` = 2 and `converged` true, as golden `baumwelch_j-0001` pins.

The variance update divides by the weight sum, not by the weight sum minus one: it is a maximum-likelihood estimate.

### Q11.28 How does QuantForge make the Baum-Welch stop iteration the same in four languages?

*Level: advanced. Evidence: spec; design. Source: [Baum-Welch](../../specifications/11-research/baum-welch.md), [Stage J rulings, wave 2](../../specifications/stage-j-rulings-w2.md)*

The stop test `gain < tolerance` is a sharp boundary. If one build's gain lands just below the tolerance and another's just above, they stop at different iterations and return different parameters. Ruling J-W2-12 requires every golden's stop tests to be decided by at least `1e-11`, and the generator asserts that margin for every gain it evaluates. `iterations` and `converged` are compared exactly.

The rest of the iteration is fixed too: sums over ascending indices, no variance floor, no relabelling, no restarts. A build may compute densities in logs and rescale to avoid underflow, as long as the iteration is the one specified. Parameters are compared with absolute `1e-12` plus relative `1e-9` (J-W2-9), and the log-likelihood in class `likelihood_sum`.

Stated limits: Gaussian emissions, one series, a local maximum from given start values. Property tests check that the log-likelihood never falls by more than `1e-9 |L|` per iteration, that two runs give identical bytes, and that permuting the start states permutes the fitted ones.

### Q11.29 What is the A5 calibration surrogate, and what must it pass before it is used?

*Level: advanced. Evidence: spec; design. Source: [A5 surrogate](../../specifications/11-research/a5-surrogate.md)*

A surrogate is a cheap function (a Chebyshev expansion or a small neural network) trained to return the implied volatility the full Heston or SABR pricer would give, so calibration runs faster. Its risk is being wrong where nobody looked, usually in the wings and at short expiries.

The acceptance rules (rulings G-11 and G-37) were fixed before any surrogate existed: a test set of 100,000 Sobol points over the parameter box plus 10,000 extra points that over-sample the wings (`|ln K/F| > 0.3`) and short expiries (`T` in `[0.02, 0.1]`). Pass requires a maximum error of at most `1e-4` (1 vol bp), a 99.9th percentile of at most `5e-5`, and, for Heston, the domain error on each of the 14 faces of the box plus NaN and infinity. If more than 1% of points are excluded as unidentifiable, the run is invalid.

The surrogate is a challenger only: it never replaces the full pricer, is Python research code with no four-language goldens, and none has been trained yet. The harness self-test shows it can fail: a pricer shifted by 2 bp fails with error `2.0e-4`.

### Q11.30 Why is White's Reality Check in the research package but not a CLI operation?

*Level: practitioner. Evidence: spec; design. Source: [Research statistics](../../specifications/11-research/research-statistics.md), [Backtester](../../specifications/11-research/backtester.md)*

White's Reality Check asks whether the best of many strategies beats a benchmark by more than the best of many useless strategies would by luck. It resamples the excess returns with the stationary bootstrap (block lengths geometric with mean `1/q`), recentres each strategy's mean, and counts how often the resampled maximum reaches the observed one.

It lives in `python/quantforge_research/snooping.py` (plan item J-4), not in the four-language CLI, because the bootstrap draws would need a shared random stream across four languages to give identical goldens (gap G14). Its size on simulated nulls is checked in the Python research tests instead.

The general rule it illustrates: an operation becomes a CLI operation with goldens only when four independent builds can be made to agree on it. Operations that depend on resampling or training stay in the Python research lane, are labelled as such, and are checked by their own tests.
