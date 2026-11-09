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

## Stage F additions (plan item R8)

Spec version 1.1.0 for this section. Rulings: `stage-f-rulings.md` F-11 to F-14. Suite `stage_f/garch_f`. Everything above is unchanged; old cases send none of the new keys and get the old results.

### Student-t innovations and a mean, in `vol.garch.loglik`

New optional inputs: `distribution` (`NORMAL`, the default, or `STUDENT_T`), `degrees_of_freedom` `nu` (required for `STUDENT_T`, ignored for `NORMAL`), `mean` `mu` (a number, default 0). The recursion runs on `e_t = r_t - mu`: `sigma2_{t+1} = omega + alpha e_t^2 + beta sigma2_t`, and `"SAMPLE"` is `(1/n) sum e_t^2`. The Gaussian log-likelihood is the one above with `e_t` in place of `r_t`. The Student-t log-likelihood uses the t distribution scaled to unit variance [S4]:

```
loglik = sum_{t=1..n} [ lnGamma((nu+1)/2) - lnGamma(nu/2) - (1/2) ln(pi (nu - 2)) - (1/2) ln sigma2_t
                        - ((nu + 1)/2) ln(1 + e_t^2 / ((nu - 2) sigma2_t)) ]
```

Checks, after the existing ones: `distribution` not listed: `E_SCHEMA`; `STUDENT_T` without `degrees_of_freedom`: `E_INPUT`; `nu <= 2`: `E_DOMAIN` (the variance is not finite). `lnGamma` must be accurate to 1e-14 relative on `[1, 1000]` (Java has no library `lgamma`: a Lanczos (g = 7, 9 terms) or Stirling series with recurrence meets it).

### `vol.garch.estimate`

Maximum likelihood with parameters, standard errors and the options above (`vol.garch.fit` stays as it is, judged on the objective only).

Inputs: `returns` (at least 30, else `E_INPUT`; at least 100 for `STUDENT_T`, else `E_INPUT`), `initial_variance` (`"SAMPLE"` or a positive number, held fixed), `distribution` (`NORMAL` or `STUDENT_T`), `demean` (boolean). With `demean = true`, `mu` is the sample mean `(1/n) sum r_t`, removed first and held fixed (a two-step estimate: its error is not in the standard errors, ruling F-12); with `demean = false`, `mu = 0`.

Parameters `theta = (omega, alpha, beta)`, plus `nu` for `STUDENT_T`. Feasible set: `omega > 0`, `alpha >= 0`, `beta >= 0`, `alpha + beta < 1`, and `2 < nu <= 500`.

**Optimum (ruling F-11).** The maximum of the log-likelihood over the feasible set. A result is accepted only at an interior maximum: every parameter at least 1e-6 (relative to its scale: `omega` against the sample variance) from every bound, gradient zero and Hessian negative definite. A build may use any optimiser, but must finish with Newton steps on an analytic (or 1e-10-accurate) gradient and Hessian until the largest relative step is below 1e-12; parameters then agree to 1e-6 relative across languages (plan acceptance). If the maximum is on or near a bound, or the polished point is not a maximum: `E_NO_CONVERGENCE` (a boundary optimum has no standard errors in this sense).

**Standard errors (ruling F-13).** Observed information: `V = (-H)^{-1}`, `H` the Hessian of the log-likelihood in `theta` (and `nu`) at the optimum, `std_errors = sqrt(diag V)`. Not the sandwich (QML) form, and not the expected information. Any `H` accurate to 1e-8 relative passes (analytic recursion derivatives, or central differences of an analytic gradient with relative step 1e-5).

Outputs: `omega`, `alpha`, `beta`, `degrees_of_freedom` (`null` for `NORMAL`), `mean` (`mu`; `0.0` when `demean = false`), `loglik`, `std_errors` (object with the same parameter keys; `degrees_of_freedom` `null` for `NORMAL`), `persistence` (`alpha + beta`).

Checks, in order: `distribution` not listed, `demean` not a boolean: `E_SCHEMA`; too few returns: `E_INPUT`; `initial_variance` a string other than `"SAMPLE"`: `E_INPUT`; a numeric `initial_variance <= 0`, or `"SAMPLE"` on all-zero (demeaned) returns: `E_DOMAIN`; no interior maximum: `E_NO_CONVERGENCE`.

### Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Newton polish of the MLE | quadratic: the relative step at least squares each iteration once below 1e-3 | the golden series, 4 iterations from the optimiser's point | `nu -> infinity`: Student-t loglik tends to the Gaussian one (at `nu = 1e6` within 1e-5 on the golden series, an oracle check) | mpmath 50-digit optimum |
| Hessian by central differences of the score | 2 in the step | relative steps 1e-3, 5e-4, 2.5e-4, 1.25e-4 | the exact Hessian at 50 digits | mpmath `diff` |

### Acceptance (plan 13.2 R8)

- Parameters 1e-6 relative (with 1e-14 absolute) across languages: class `root_finding` with that `tolerance_limit`; `loglik` class `likelihood_sum`; standard errors 1e-5 relative.
- **Recovery.** In the oracle, 200 series of 2,000 returns simulated from known parameters (NORMAL: `omega = 2e-6`, `alpha = 0.08`, `beta = 0.90`; STUDENT_T: the same and `nu = 6`), seeds `20261109 + i`: the share of series whose `+-2 SE` interval holds the true value is reported for each parameter and must lie in [0.90, 0.99] (nominal 0.954; the band is 3.5 binomial SE at 200 series). The single golden series per distribution (seed 20261109) also holds every true parameter within 2 SE; this is reported, and the series was not chosen for it (it is the first seed).
- Goldens: mpmath at 50 digits, Newton to a gradient below 1e-20 relative, Hessian checked negative definite; a scipy multi-start search must not find a better point. No outside library: QuantLib's `Garch11` is not in its Python wheel and the `arch` package is not a dependency (zero new dependencies); `arch` 7.x was not used.
- Wrong conventions, each caught: unit-scale t density with `nu` in place of `nu - 2` (not variance-normalised); `demean` ignored; sandwich standard errors in place of observed information; Gaussian loglik on t data.

### Sources (this section)

- [S4] Bollerslev, T., "A conditionally heteroskedastic time series model for speculative prices and rates of return", *Review of Economics and Statistics* 69(3), 1987, 542-547: GARCH with standardised Student-t innovations (not opened)
- [S5] Bollerslev, T. and Wooldridge, J. M., "Quasi-maximum likelihood estimation and inference in dynamic models with time-varying covariances", *Econometric Reviews* 11(2), 1992, 143-172: the sandwich form, named here only as the form not used (not opened)
