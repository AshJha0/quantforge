# Value at risk, expected shortfall and backtests

Spec version 1.0.0. Status: Specified (stage F, slice F4, plan item Q2). Rulings: `stage-f-rulings.md` F-31 to F-32. Suite `stage_f/risk_f4`, written by `oracle/python/gen_stage_f_w2.py` (slice `F4`).

**Plain idea.** Value at risk (VaR) answers "how much could we lose on a bad day, at 99% confidence?"; expected shortfall (ES) answers "and when it is that bad, how much on average?". Both are read off a set of profit-and-loss scenarios: past days replayed (historical), past days rescaled to today's volatility (filtered historical), simulated days (Monte Carlo), or a normal distribution (parametric). A backtest then asks whether the model's losses broke VaR as often as they should (Kupiec), whether the breaks bunch together (Christoffersen), and which supervisory zone that puts the bank in (the Basel traffic light).

Losses are positive: `L = -pnl`. VaR and ES are reported as positive numbers for a loss. `confidence` `c` is in `[0.5, 1)`, else `E_DOMAIN`.

## Order statistic rule (ruling F-31)

For `n` losses sorted ascending, `L_(1) <= ... <= L_(n)`, and `k = ceil(n c)` with `n c` the binary64 product (one correctly rounded multiply, so the same in every language):

- `var = L_(k)`;
- `es = mean(L_(k), ..., L_(n))`, the `tail_count = n - k + 1` largest losses, VaR scenario included.

This is the inverted empirical distribution (Hyndman and Fan type 1 [S5]): VaR is the smallest loss whose empirical distribution reaches `c`. At `n = 250`, `c = 0.99` it is the third-largest loss and ES is the mean of the three largest. Ties need no rule: the value is the same whichever tied scenario is picked.

## `risk.var.historical`

Inputs: `pnl` (at least one, else `E_INPUT`), `confidence`. Outputs: `var`, `es`, `tail_count`. Class `simple_analytic` (`tail_count` exact).

## `risk.var.filtered_historical`

Inputs: `returns` `r_1..r_T` (at least one), `position_value` `P` (signed), `lambda` (`0 < lambda < 1`, else `E_DOMAIN`), `confidence`. All returns 0 (so every `sigma_t` is 0): `E_DOMAIN` (ruling F-39).

EWMA variance [S2, S3]: `sigma_1^2 = (1/T) sum r_t^2`; `sigma_{t+1}^2 = lambda sigma_t^2 + (1 - lambda) r_t^2` for `t = 1..T`. Rescaled scenario `t`: `pnl_t = P r_t sigma_{T+1} / sigma_t`. Then the order statistic rule. Outputs: `var`, `es`, `tail_count`, `sigma_next` (`sigma_{T+1}`). Class `interpolation`.

## `risk.var.parametric`

Inputs: `mean` `mu` and `std` `sigma > 0` (else `E_DOMAIN`) of the P&L, `confidence`. With `z = Phi^{-1}(c)`: `var = -mu + sigma z`, `es = -mu + sigma phi(z) / (1 - c)`. Class `simple_analytic`.

## `risk.var.monte_carlo`

Inputs: `mean` (`N`), `covariance` (`N x N`, symmetric; a non-positive Cholesky pivot is `E_NOT_POSITIVE_DEFINITE`, as `01-core/differentiation-and-linalg.md`), `weights` (`N` position values), `paths` (`>= 1`), `seed` (a decimal u64 string, as `core.rng`, else `E_SCHEMA`), `confidence`. Ruling F-39.

Draws: `core.rng` (`01-core/rng.md`) with `seed`, stream 0; normals by AS 241, path by path and within a path asset by asset. Returns `r = mean + L z`, `L` the lower Cholesky factor (Cholesky-Banachiewicz order). `pnl = weights . r`, then the order statistic rule. Outputs: `var`, `es`, `tail_count`. Class `common_rng`.

## `risk.backtest.kupiec`

Inputs: `observations` `n >= 1`, `exceptions` `0 <= x <= n` (else `E_DOMAIN`), `confidence`. With `p = 1 - c` and `p_hat = x/n` [S6]:

```
LR_uc = -2 [ (n - x) ln(1 - p) + x ln p ] + 2 [ (n - x) ln(1 - p_hat) + x ln p_hat ]        (0 ln 0 = 0)
```

`p_value = P(chi^2_1 > LR_uc)`. Ruling F-32: an LR below `1e-12` is exactly 0 and its p-value is 1.

## `risk.backtest.christoffersen`

Inputs: `exceptions` (booleans, length `n >= 2`, else `E_INPUT`), `confidence`. `LR_uc` as Kupiec on all `n` days. Transitions over the `n - 1` consecutive pairs: `n_ij` counts day pairs (`I_{t-1} = i`, `I_t = j`). With `pi_01 = n01/(n00 + n01)`, `pi_11 = n11/(n10 + n11)` (0 when the denominator is 0) and `pi = (n01 + n11)/(n - 1)` [S7]:

```
LR_ind = -2 [ (n00 + n10) ln(1 - pi) + (n01 + n11) ln pi
            - n00 ln(1 - pi_01) - n01 ln pi_01 - n10 ln(1 - pi_11) - n11 ln pi_11 ]           (0 ln 0 = 0)
LR_cc  = LR_uc + LR_ind
```

p-values: chi-square with 1, 1 and 2 degrees of freedom. Ruling F-32 applies to `LR_uc` and `LR_ind`. Outputs: the three LRs, the three p-values, `transitions` (exact).

## `risk.backtest.traffic_light`

Inputs: `observations` (`>= 1`), `exceptions` (`0 <= x <= n`, else `E_DOMAIN`), `confidence`. `cumulative_probability = P(X <= x)`, `X ~ Binomial(n, 1 - c)`. Zone: `GREEN` below 0.95, `YELLOW` below 0.9999, else `RED` [S8]. At `n = 250` and `c = 0.99` this gives green for 0 to 4 exceptions, yellow for 5 to 9, red from 10, as Table 2 of [S8]; `plus_factor` is that table's value (0 for 0 to 4; 0.40, 0.50, 0.65, 0.75, 0.85 for 5 to 9; 1.00 from 10). For any other `n` or `c`, `plus_factor` is `null`.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Monte Carlo VaR | the VaR order statistic converges as `n^{-1/2}` to the normal quantile | paths 1,000, 5,000, 10,000 on the one-asset case | one asset: `var -> w sigma z_c` | `risk.var.parametric` |
| FHS | `lambda -> 1` gives plain historical simulation on the rescaled-by-a-constant series | lambda 0.94, 0.97, 0.99 | all returns equal in size: every `sigma_t` equal, FHS = historical | constructed |
| Parametric | closed form | none | `c = 0.5`: `var = -mu` | hand |
| Kupiec | closed form | none | `x = n p`: `LR = 0`, `p_value = 1` (ruling F-32) | golden cases |

## Acceptance (plan Q2)

- Every case of `risk_f4` passes in all four languages.
- Outside (rule 11.2.5): Kupiec, Christoffersen, traffic light and parametric cases are recomputed by SciPy (`chi2.sf`, `binom.logpmf`, `binom.cdf`, `norm.ppf`, and ES by numerical integration of the normal tail rather than the closed form); historical cases by `numpy.quantile(method="inverted_cdf")`. FHS and Monte Carlo cases have no outside library and do not count.
- Full revaluation against sensitivity P&L is not a new operation: `risk.pnl.explain` (R2) already reports the unexplained term. Reverse stress, limits, concentration, liquidity-adjusted risk, portfolio vol by horizon and model-risk reserves are deferred to wave 2b (handover).

## Sources

- [S1] Jorion, P., *Value at Risk*, 3rd ed., McGraw-Hill, 2007 (historical, parametric and Monte Carlo VaR) (not opened)
- [S2] J.P. Morgan/Reuters, *RiskMetrics Technical Document*, 4th ed., 1996 (EWMA with lambda 0.94 for daily data) (not opened)
- [S3] Hull, J. and White, A., "Incorporating volatility updating into the historical simulation method for value-at-risk", *Journal of Risk* 1(1), 1998, 5-19 (rescaling scenarios by the ratio of current to past volatility) (not opened)
- [S4] Acerbi, C. and Tasche, D., "On the coherence of expected shortfall", *Journal of Banking and Finance* 26(7), 2002, 1487-1503 (not opened)
- [S5] Hyndman, R. J. and Fan, Y., "Sample quantiles in statistical packages", *The American Statistician* 50(4), 1996, 361-365 (type 1, the inverted empirical distribution) (not opened)
- [S6] Kupiec, P., "Techniques for verifying the accuracy of risk measurement models", *Journal of Derivatives* 3(2), 1995, 73-84 (not opened)
- [S7] Christoffersen, P., "Evaluating interval forecasts", *International Economic Review* 39(4), 1998, 841-862 (not opened)
- [S8] Basel Committee on Banking Supervision, *Supervisory framework for the use of "backtesting" in conjunction with the internal models approach to market risk capital requirements*, January 1996, Table 2 (zones and plus factors) (not opened)
