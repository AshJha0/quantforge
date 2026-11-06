# Statistics and time series

Spec version 1.0.0. Status: Specified.

Input arrays must be finite unless an operation allows `null`. Use a stable method: two-pass or
Welford, never `sum(x^2) - n mean^2`.

## Distributions

`core.stats.normal`. Inputs: `x` (array). Outputs: `pdf`, `cdf`, arrays.

`n(x) = exp(-x^2/2)/sqrt(2 pi)`, `N(x) = erfc(-x/sqrt 2)/2`. Relative accuracy of `N` must be 1e-14 or
better down to `x = -37`, so the left tail must not be computed as `1 - N(-x)`. Java and Rust have no
standard `erfc`. Use Cody's rational approximations or a proven library.

The quantile is `core.rng.inverse_normal`.

## Moments

`core.stats.summary`. Input: `x`, at least 2 values, else `E_INPUT`. Outputs:

| Key | Definition |
|---|---|
| `count` | `n` |
| `mean` | `m = sum x / n` |
| `variance` | `sum (x - m)^2 / (n - 1)` |
| `stdev` | square root of `variance` |
| `skewness` | `m3 / m2^1.5`, with `m_k = sum (x - m)^k / n` |
| `excess_kurtosis` | `m4 / m2^2 - 3` |
| `min`, `max` | Extremes |

Zero variance: `skewness` and `excess_kurtosis` are `null`, and the rest stand.

`core.stats.quantile`. Inputs: `x` (at least 1), `p` (array in `[0, 1]`, else `E_DOMAIN`). Output: `values`.
Hyndman-Fan type 7: sort `x`; `h = (n - 1) p`; `k = floor(h)`; `x[k] + (h - k)(x[k+1] - x[k])`, indices from 0,
and `x[n-1]` at `p = 1`.

`core.stats.covariance`. Inputs: `x`, `y`, equal length of at least 2, else `E_INPUT`. Outputs: `covariance`
(divisor `n - 1`) and `correlation`. Zero variance in either: `correlation` is `null`.

`core.stats.ols`. Inputs: `x`, `y`, equal length of at least 3, else `E_INPUT`. Fits `y = alpha + beta x + e`.
Outputs: `alpha`, `beta`, `r_squared`, `se_alpha`, `se_beta`. Residual variance has divisor `n - 2`. Zero
variance in `x`: `E_SINGULAR`.

## Time series

Series are in time order.

`core.ts.returns`. Inputs: `prices`, at least 2, `kind` (`SIMPLE`: `p_t/p_{t-1} - 1`, or `LOG`: `ln(p_t/p_{t-1})`).
Output: `returns`, length `n - 1`. Any price `<= 0`: `E_DOMAIN`.

`core.ts.rolling`. Inputs: `x`, `window` (at least 2, at most `n`, else `E_INPUT`), `statistic` (`MEAN` or
`STDEV`, the latter with divisor `window - 1`). Output: `values`, length `n`; the first `window - 1` are `null`.
Compute each window afresh or stably, so that an early large value leaves no residue.

`core.ts.ewma_variance`. Inputs: `returns`, at least 1, `lambda` in `(0, 1)` (else `E_DOMAIN`). Output:
`variance`, same length: `v_0 = r_0^2`, `v_t = lambda v_{t-1} + (1 - lambda) r_t^2`. Zero mean is assumed.

`core.ts.autocorrelation`. Inputs: `x`, `max_lag` (at least 1, below `n`, else `E_INPUT`). Output: `acf`,
lags 1 to `max_lag`: `sum_{t=k}^{n-1} (x_t - m)(x_{t-k} - m) / sum (x_t - m)^2`. Zero variance: `E_DOMAIN`.

`core.ts.ljung_box`. Same inputs. Output: `statistic`, `Q = n (n + 2) sum_{k=1}^{L} acf_k^2 / (n - k)`.

`core.ts.ar1`. Input: `x`, at least 4. OLS of `x_t` on `x_{t-1}`. Outputs: `constant`, `phi`, `sigma` (residual
standard deviation, divisor `n - 3`, with `n - 1` pairs).

`core.ts.resample_last`. Inputs: `dates` (strictly increasing, else `E_INPUT`), `values` (`null` allowed),
`frequency` (`WEEK` or `MONTH`). Outputs: `dates`, `values`: the last non-null observation in each ISO week
(Monday to Sunday) or calendar month, carrying its own date. A bucket with no non-null value is left out.

`core.ts.forward_fill`. Inputs: `values` (`null` allowed), `limit` (integer, at least 1). Output: `values`.
A `null` takes the last non-null value if it is no more than `limit` steps back. Leading `null`s stay.

## Acceptance

Class `statistics`. Oracles: exact `Fraction` arithmetic where rational, otherwise mpmath at 50 digits, with NumPy
and SciPy as second checks for quantile, OLS and ACF. Ljung-Box has one source. Normal: class `statistics`
against mpmath, including `x = -37`.
