# Microstructure estimators with planted truth

Spec version 0.1.0 (stage H wave 2, H-4b; written 2026-11-18). Status: Specified, not implemented. Rulings HR-70, HR-71, HR-74. Plan item 14.7 H-4: the estimator recovers the planted parameter within 3 SE on a simulated book with known truth; no claim on real markets.

Sources: textbook maximum likelihood and ordinary least squares; no number comes from a paper. Evidence class: derivation. Goldens are hand calculations checked with mpmath (30 digits) by the spec lane; not yet blind re-derived.

All functions take plain lists of decimals; outputs are binary64, compared to 1e-12 relative (an expected 0 is compared absolutely to 1e-15).

## Common estimator: OLS through the origin
For pairs (x_i, y_i), i = 1..n: `beta = sum x y / sum x^2`, `s2 = sum (y - beta x)^2 / (n - 1)`, `SE = sqrt(s2 / sum x^2)`. n < 2 or `sum x^2 = 0`: `E_INPUT`.

## `micro.est.arrival_rate`
Order arrivals as a Poisson process. Inputs: event count N >= 0, window T. `lambda = N / T`, `SE = sqrt(lambda / T)`. T <= 0: `E_DOMAIN`.

## `micro.est.cancel_rate`
Resting orders cancelled at exponential rate theta; fills censor the lifetime. Inputs: list of (lifetime L_i > 0, outcome cancel or fill). `theta = C / sum L_i` with C the cancel count, `SE = theta / sqrt(C)`. C = 0: `E_INPUT`.

## `micro.est.resilience`
Spread after a shock: `S_t - S_inf = (S_0 - S_inf) exp(-kappa t)`. Inputs: S_inf (known), list of (t_i, S_i). Every S_i must exceed S_inf, else `E_DOMAIN` (checked after the count, HR-75a). OLS with intercept of `ln(S_i - S_inf)` on t_i; `kappa = -slope`, SE the OLS slope SE with n - 2 degrees of freedom. n < 3: `E_INPUT`.

## `micro.est.liquidity_decay`
Depth against distance from the touch: `D_k = D_0 exp(-alpha k)`. Same estimator as resilience with k for t and S_inf = 0.

## `micro.est.adverse_selection`
Planted model `dm_i = lambda_as * s_i q_i + e_i` (mid change after trade i against its signed size). OLS through the origin with x = s q, y = dm.

## `micro.est.regime_impact`
As adverse selection, fitted separately per regime label; outputs (beta, SE) per label and the ratio stressed / calm. A label with fewer than 2 rows: `E_INPUT`.

## `micro.est.passive_vs_aggressive`
Inputs: implementation cost in bp per fill, labelled passive or aggressive. `delta = mean(aggressive) - mean(passive)`, Welch `SE = sqrt(v_a/n_a + v_p/n_p)` with sample variances (divisor n - 1). A class with fewer than 2 fills: `E_INPUT`.

## Operation inputs and outputs (names fixed 2026-11-18 by the implementation lane, before generating goldens)
Every number is a JSON Real; `count` is an Integer. Every output standard error is named `se`. The adverse-selection slope is `lambda_as` in both slope operations (the blind lane wrote `beta`; one name now).

| Operation | Inputs | Outputs |
|---|---|---|
| `micro.est.arrival_rate` | `count` (N, Integer; < 0 `E_DOMAIN`), `window` (T) | `lambda`, `se` |
| `micro.est.cancel_rate` | `orders`: array of `{lifetime, outcome}`, outcome `CANCEL` or `FILL`; lifetime <= 0 `E_DOMAIN` | `theta`, `se` |
| `micro.est.resilience` | `s_inf`, `points`: array of `{t, s}` | `kappa`, `se` |
| `micro.est.liquidity_decay` | `levels`: array of `{k, depth}`; depth <= 0 `E_DOMAIN` (it must exceed S_inf = 0) | `alpha`, `se` |
| `micro.est.adverse_selection` | `x` (signed size s q), `y` (mid change dm), equal lengths, else `E_INPUT` | `lambda_as`, `se` |
| `micro.est.regime_impact` | `regimes`: object, label to `{x, y}`; must hold `calm` and `stressed` (else `E_INPUT`) | `regimes`: label to `{lambda_as, se}`; `ratio` = stressed / calm `lambda_as`; a calm `lambda_as` of 0 is `E_DOMAIN`, checked after the fits |
| `micro.est.passive_vs_aggressive` | `passive`, `aggressive`: arrays of costs in bp | `delta`, `se` |

In the OLS with intercept (resilience, liquidity decay), all t (or k) equal gives `sum (t - mean t)^2 = 0`: `E_INPUT`. Errors follow HR-75a: structural `E_INPUT` checks (list lengths, n below the minimum, a missing regime label, enum) come first, then `E_DOMAIN`, then the value-dependent `E_INPUT` checks (no cancel, sum x^2 = 0, all t equal).

## Golden cases
| Case | Input | Expected | Derivation |
|---|---|---|---|
| mest_h-0001 | arrival N = 12, T = 4 | lambda 3; SE 0.866025403784439 | sqrt(3/4) |
| mest_h-0002 | arrival N = 12, T = 0 | `E_DOMAIN` | T <= 0 |
| mest_h-0003 | cancel (2, cancel), (3, fill), (5, cancel) | theta 0.2; SE 0.141421356237310 | 2/10; 0.2/sqrt 2 |
| mest_h-0004 | cancel (3, fill) only | `E_INPUT` | no cancel |
| mest_h-0005 | resilience S_inf 1; (0, 5), (1, 3), (2, 2) | kappa 0.693147180559945; SE 0 | ln 4, ln 2, ln 1 lie on a line of slope -ln 2 |
| mest_h-0006 | resilience S_inf 1; (0, 5), (1, 0.5) | `E_INPUT` | n = 2 < 3, a structural check, before 0.5 <= S_inf (HR-75a; was `E_DOMAIN` under HR-75, changed 2026-11-18, hand re-derivation, not blind-checked under the new order) |
| mest_h-0007 | liquidity decay D = 800, 400, 200, 100 at k = 0..3 | alpha 0.693147180559945; SE 0 | depth halves each tick |
| mest_h-0008 | adverse selection x = (1, -1, 2), y = (0.02, -0.01, 0.05) | lambda_as 0.0216666666666667; SE 0.00390867979985286 | 0.13/6 = 13/600; residuals (-1, 7, 4)/600; s2 = 66/360000/2; SE = sqrt(s2/6) |
| mest_h-0009 | regime calm x = (1, 2), y = (0.01, 0.02); stressed x = (1, -1, 1), y = (0.05, -0.03, 0.04) | calm lambda_as 0.01, SE 0; stressed lambda_as 0.04, SE 0.00577350269189626; ratio 4 | stressed 0.12/3; residuals (0.01, 0.01, 0); s2 = 0.0001; SE = sqrt(0.0001/3) |
| mest_h-0010 | passive (-1, -0.5, 0) bp, aggressive (1, 1.5, 2) bp | delta 2; SE 0.408248290463863 | 1.5 - (-0.5); variances 0.25; sqrt(0.25/3 + 0.25/3) |
| mest_h-0011 | passive (-1) only, aggressive (1, 2) | `E_INPUT` | one passive fill |

## Recovery tests (planted truth; seeds fixed 2026-11-18 before any run)
Each test draws with `numpy.random.default_rng(seed)` in the order listed (HR-71) and passes when the estimate is within 3 SE of the planted value (HR-70). Single-seed run: seed 20261118 + j for test j. Coverage run: seeds 70000..70199 per test, at most 4 misses each.

| j | Estimator | Planted truth and simulation |
|---|---|---|
| 1 | arrival_rate | lambda = 2.5 per s, T = 3,600 s; N = `poisson(lambda T)` |
| 2 | cancel_rate | theta = 0.4, fill rate 0.1, 5,000 orders drawn order by order: L = `exponential(1/(theta + 0.1))`, then cancel if `random() < theta/(theta + 0.1)` |
| 3 | resilience | kappa = 0.3, S_0 = 5, S_inf = 1, t = 0..20; S_t = S_inf + (S_0 - S_inf) e^{-kappa t} exp(`normal(0, 0.05)`) |
| 4 | liquidity_decay | alpha = 0.15, D_0 = 1,000, k = 0..30; D_k = D_0 e^{-alpha k} exp(`normal(0, 0.1)`) |
| 5 | adverse_selection | lambda_as = 0.002, 2,000 trades drawn trade by trade: s = `choice([-1, 1])`, q = `integers(1, 101)`, e = `normal(0, 0.05)` |
| 6 | regime_impact | calm 0.001 then stressed 0.004, 1,000 trades each, drawn as test 5; passes when both betas pass |
| 7 | passive_vs_aggressive | 1,000 passive costs `normal(-1, 2)` bp, then 1,000 aggressive `normal(1.5, 2)` bp; planted delta 2.5 |

## Limitations
Method tests on simulated data with known truth only; no claim on real markets (14.7 H-4). Each model is the simplest of its family (Poisson arrivals, exponential cancels, exponential recovery, linear impact); Hawkes arrivals, queue-position cancels and nonlinear impact are not covered. The resilience and liquidity-decay goldens are exact fits (HR-74).
