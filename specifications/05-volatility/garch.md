# GARCH(1,1): likelihood, forecast and fit

Spec version 1.0.0. Status: Specified (stage E, E7, spec B). Rulings: `stage-e-rulings-b.md` E-B1, E-B2, E-B7, E-B14, E-B16, E-B17.

**Plain idea.** Volatility clusters: a big move today makes a big move tomorrow more likely. GARCH(1,1) says tomorrow's variance is a weighted mix of a constant, today's squared return and today's variance. Because the weights on the last two add up to less than one, variance drifts back to a long-run level.

## Model

Returns `r_1, ..., r_n` are given as they are: no mean is estimated or removed (ruling E-B1). Conditional variances:

```
sigma2_1     = initial variance (below)
sigma2_{t+1} = omega + alpha r_t^2 + beta sigma2_t,     t = 1, ..., n
```

`sigma2_{n+1}` is `next_variance`, the one-step forecast after the last return. Initial variance: `"SAMPLE"` means `(1/n) sum_{t=1..n} r_t^2` (divisor `n`, no demeaning), or a positive number given by the caller.

Gaussian log-likelihood, every term from `t = 1` (the first term is not dropped):

```
loglik = -1/2 sum_{t=1..n} [ ln(2 pi) + ln sigma2_t + r_t^2 / sigma2_t ]
```

## `vol.garch.loglik`

Inputs: `returns` (array, at least 2), `omega`, `alpha`, `beta`, `initial_variance` (`"SAMPLE"` or a number). Outputs: `loglik`, `variances` (`sigma2_1..sigma2_n`, length `n`), `next_variance`.

Checks, in order: fewer than 2 returns: `E_INPUT`. `initial_variance` a string other than `"SAMPLE"`: `E_INPUT`. `omega <= 0`, `alpha < 0`, `beta < 0`: `E_DOMAIN`. A numeric `initial_variance <= 0`, or `"SAMPLE"` on all-zero returns: `E_DOMAIN`. `alpha + beta >= 1` is allowed here (the likelihood exists); it is refused only by the forecast.

## `vol.garch.forecast`

Inputs: `omega`, `alpha`, `beta`, `next_variance` (`sigma2_{n+1}`), `horizon` `H` (integer), `periods_per_year`. With `p = alpha + beta` and `V_L = omega / (1 - p)`:

```
E[sigma2_{n+h}] = V_L + p^(h-1) (sigma2_{n+1} - V_L),   h = 1, ..., H
total_variance  = sum of the H values
annualized_vol  = sqrt(total_variance * periods_per_year / H)
```

Outputs: `variances` (length `H`), `total_variance`, `annualized_vol`, `long_run_variance` (`V_L`). Checks: `H < 1` or `periods_per_year <= 0`: `E_INPUT`; `omega <= 0`, `alpha < 0`, `beta < 0`, `next_variance <= 0`: `E_DOMAIN`; `alpha + beta >= 1`: `E_DOMAIN` (no long-run variance, ruling E-B2); the sum is taken in binary64 as written (ruling E-B17). `p^(h-1)` with `p = 0` and `h = 1` is 1.

## `vol.garch.fit`

Maximum likelihood over `(omega, alpha, beta)` with `omega > 0`, `alpha >= 0`, `beta >= 0`, `alpha + beta < 1`. Inputs: `returns` (at least 30), `initial_variance` (`"SAMPLE"` or a number, held fixed: it is not a parameter). Output: `loglik` at the optimum. Any proven optimiser may be used.

Acceptance is on the objective, not the parameters: `|loglik - golden| <= 1e-6`, written in the goldens as class `root_finding` with a `tolerance_limit` (ruling E-B16; the policy class `calibration` has no numeric tolerance). Stop the optimiser at a log-likelihood gap below 1e-8 (about 1e-4 relative on `omega`); a loose stopping rule is the usual cause of a failure. Optimising over `omega` divided by the sample variance helps conditioning. The golden maximum is interior (gradient zero to 1e-20 relative in 50-digit arithmetic, Hessian negative definite), so a correct fit reaches it; a 5% error in `omega` alone costs more than 1e-6 on both golden series (wrong-convention check). The fitted parameters are written in the case `description` for information and are not compared. Fewer than 30 returns: `E_INPUT`. An optimiser that fails to converge: `E_NO_CONVERGENCE`.

## Worked example (case `garch_e-0009`)

`r = (0.01, -0.02)`, `omega = 1e-5`, `alpha = 0.1`, `beta = 0.8`, `"SAMPLE"`.

- `sigma2_1 = (0.0001 + 0.0004)/2 = 2.5e-4`.
- `sigma2_2 = 1e-5 + 0.1 (1e-4) + 0.8 (2.5e-4) = 2.2e-4`.
- `next_variance = 1e-5 + 0.1 (4e-4) + 0.8 (2.2e-4) = 2.26e-4`.
- `loglik = -1/2 [2 ln(2 pi) + ln 2.5e-4 + ln 2.2e-4 + 0.4 + 1.818181...] = 5.410998350356715`.

Forecast from there with `H = 5` (case in `garch_e`): `V_L = 1e-5/0.1 = 1e-4`, `p = 0.9`, the five values are `1e-4 + 0.9^(h-1) (1.26e-4)`.

## Acceptance

Suite `stage_e_b/garch_e`. Log-likelihood in class `likelihood_sum` (1e-9 absolute plus 1e-10 relative) on series of 250 and 500 returns, class `statistics` on the short series, with variances under 1e-16 absolute plus 1e-11 relative (ruling E-B14) (each `ln` may differ in its last bit across libms; the sum of 500 such errors is far smaller). Forecast variances 1e-11 relative, which is under 1e-9 in annualised vol: below a hundredth of a cent of vega on a 10m vega notional. Goldens: mpmath at 50 digits; a separate float replay in `oracle/python/outside_e_b.py` agrees. QuantLib's `Garch11` is not in its Python wheel, so no case here is outside-checked.

Wrong-convention checks (each caught): initial variance `r_1^2`; the `ln(2 pi)` constant dropped; the same-day return in the recursion; forecast exponent `h` instead of `h - 1`.

## Sources

- [S1] Bollerslev, T., "Generalized autoregressive conditional heteroskedasticity", *Journal of Econometrics* 31(3), 1986, 307-327: the GARCH(p,q) recursion and Gaussian likelihood (not opened)
- [S2] Engle, R. F., "Autoregressive conditional heteroscedasticity with estimates of the variance of United Kingdom inflation", *Econometrica* 50(4), 1982, 987-1007 (not opened)
- [S3] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Estimating Volatilities and Correlations" (chapter number not checked; the edition matches the other QuantForge specs that cite Hull) (GARCH(1,1), long-run variance `omega/(1 - alpha - beta)`, the forecast `V_L + (alpha + beta)^k (sigma2 - V_L)`, maximum likelihood) (not opened)

"(not opened)" means the reference was written from memory in this session and not re-read; the formulas above are fully stated here and checked by the goldens, so no rule depends on the reference.
