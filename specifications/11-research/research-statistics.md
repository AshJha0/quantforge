# Research statistics: probabilistic and deflated Sharpe ratio, PBO by CSCV, power

Spec version 1.0.0. Status: specified, not implemented (wave 1 code lands in v0.9.0; no build implements these operations and their goldens are not in this release). Rulings: `stage-j-rulings-w1.md` J-13 to J-18. Suite: `datasets/golden/stage_j/rstats_j`, written by `oracle/python/gen_stage_j_w1.py`. Plan 11.3 (every study reports DSR and PBO), Q7, J-1.

**Plain idea.** A backtest Sharpe ratio is an estimate, and the best of many tried strategies is biased upward. The probabilistic Sharpe ratio (PSR) is the probability that the true Sharpe exceeds a benchmark, allowing for sample length, skew and fat tails. The deflated Sharpe ratio (DSR) is the PSR against the Sharpe the best of `N` useless strategies would show by luck. PBO asks a different question: how often does the in-sample winner rank in the bottom half out of sample? The power calculation says how large a Sharpe a study can detect at all.

Sources:
- [BLdP12] D. H. Bailey, M. Lopez de Prado, "The Sharpe ratio efficient frontier", *Journal of Risk* 15(2), 2012, 3-44 (PSR) (not opened in this session). Evidence class: paper, recalled.
- [BLdP14] D. H. Bailey, M. Lopez de Prado, "The deflated Sharpe ratio: correcting for selection bias, backtest overfitting and non-normality", *Journal of Portfolio Management* 40(5), 2014, 94-107 (DSR formula and the worked example: `SR = 2.5` annualised, `T = 1250` daily returns, skew `-3`, kurtosis `10`, `N = 100` trials, variance of the trials' annualised Sharpe `0.5`; printed `SR0 = 0.1132` per period and `DSR = 0.9004`) (not opened in this session; the printed values are recalled and reproduced to 4 digits by `rstats_j-0001`). Evidence class: paper, recalled; **J-1 needs the paper opened and the digits recorded before it closes**.
- [BBLdPZ17] D. H. Bailey, J. M. Borwein, M. Lopez de Prado, Q. J. Zhu, "The probability of backtest overfitting", *Journal of Computational Finance* 20(4), 2017, 39-69 (CSCV, logits, PBO) (not opened). Evidence class: paper, recalled. No printed numerical example is reproduced in wave 1; J-1's PBO half is open (handover).
- [Lo02] A. W. Lo, "The statistics of Sharpe ratios", *Financial Analysts Journal* 58(4), 2002, 36-52 (iid standard error `sqrt((1 + SR^2/2)/T)`) (not opened). Used in `research/preregs/README.md`; the MDS table there is reproduced by four goldens. Evidence class: paper, recalled; hand calculation.

## Common rules

- Sharpe ratios in `research.stats.psr` and `.dsr` are **per period** (not annualised): annualise outside. `kurtosis` is the non-excess fourth standardised moment (3 for a normal).
- Check order: `E_PARSE`, `E_SCHEMA`, `E_LIMIT`, F-2, then the checks listed. Normal quantiles and CDF to full double precision (any method with relative error below 1e-15, for example Acklam with one Halley step, or `erfc`).

## `research.stats.psr`

Inputs `sr`, `n_obs` (Integer `T >= 2`), `skew` (default 0), `kurtosis` (default 3, `>= 1`), `sr_benchmark` (default 0). With `v = 1 - skew sr + (kurtosis - 1)/4 sr^2`: `v <= 0` is `E_DOMAIN` (ruling J-14); else `z = (sr - sr_benchmark) sqrt(T - 1) / sqrt(v)` and `psr = Phi(z)`. Outputs `z`, `psr`.

## `research.stats.dsr`

Inputs as PSR without `sr_benchmark`, plus `n_trials` (Integer `N >= 1`) and `sr_variance` (`>= 0`, the variance of the per-period Sharpe ratios across the trials). Benchmark:

`SR0 = sqrt(sr_variance) ((1 - gamma) Phi^{-1}(1 - 1/N) + gamma Phi^{-1}(1 - 1/(N e)))`, `gamma` the Euler-Mascheroni constant 0.5772156649015329.

`N = 1` gives `SR0 = 0` (no selection; ruling J-13, since `Phi^{-1}(0)` is infinite). Outputs `sr0`, `z`, `dsr = Phi(z)` with `z` as PSR against `SR0`. The trial count `N` is the count logged by the trial registry (`research/trials.csv`, Q7); a study never passes a smaller `N`.

## `research.stats.pbo`

### Inputs

`performance` (`T x N`, one row per period, one column per strategy configuration, `N >= 2`), `n_partitions` (`S`, even, `2 <= S <= 16`, `T` divisible by `S` with at least 2 rows per block, ruling J-15), `metric` (`SHARPE` default: mean over sample standard deviation with divisor `n - 1`; or `MEAN`).

### Algorithm (CSCV)

1. Split rows into `S` contiguous blocks of `T/S` rows.
2. For each combination `J` of `S/2` blocks, in lexicographic order of block indices: train = rows of `J` in row order, test = the rest.
3. `n*` = the strategy with the best train metric (ties: lowest index, J-16).
4. Relative rank of `n*` out of sample: `omega = r / (N + 1)`, `r` the average rank of `n*`'s test metric among the `N` test metrics (1 = worst; ties take the average rank, J-16).
5. Logit `lambda = log(omega / (1 - omega))`.
6. `PBO = (number of lambda <= 0) / C(S, S/2)`.

A zero standard deviation in any block under `SHARPE` is `E_DOMAIN` (J-17).

### Outputs

`pbo`, `logits` (length `C(S, S/2)`, in the order of step 2), `n_combinations` (Integer).

### Worked example (`rstats_j-0025`, hand)

Rows `[1, 0], [1, 0], [0, 2], [0, 2]`, `S = 2`, `MEAN`. Combination `{0}`: train means `(1, 0)`, winner 0; test means `(0, 2)`, rank 1, `omega = 1/3`, `lambda = log(1/2) = -0.6931`. Combination `{1}`: train `(0, 2)`, winner 1; test `(1, 0)`, rank 1, same logit. `PBO = 1`.

## `research.stats.power`

Inputs `years` (`> 0`), `alpha` (default 0.05), `power` (default 0.8), both in `(0, 1)` with `alpha < power`, optional `sr_target` (`> 0`, annualised). Outputs `z_sum = Phi^{-1}(1 - alpha) + Phi^{-1}(power)`, `mds = z_sum / sqrt(years)` (the minimum detectable annualised Sharpe near zero, one-sided), `se_at_zero = 1/sqrt(years)`; with `sr_target`, `years_required = (z_sum / sr_target)^2` and `se_at_target = sqrt((1 + sr_target^2/2)/years)` [Lo02]. Example: `z_sum = 2.4865`; `years = 13.83` gives `mds = 0.6686`, the 0.67 of the R3-01 row (`rstats_j-0017`). The iid formula understates the MDS under serial correlation; studies report the simulated power of `research/power/r3_power.py` beside it.

## Limitations

PSR and DSR assume the Sharpe estimate is asymptotically normal with the [BLdP12] variance; for short or strongly autocorrelated series the stationary block bootstrap of the R3 preregs is the stated interval. PBO with `SHARPE` on short blocks is noisy; `T/S >= 2` is a floor, not a recommendation.
