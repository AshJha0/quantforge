# Stage G rulings

Normative for stage G (v0.7): rates models and xVA, plus plan items Q3b, Q9, A5 and R9. Earlier rulings (`stage-f-rulings.md` F-1 to F-44, including the finite rule F-2, negative zero F-3 and the check order) still hold. Append-only; an amendment is a new row that names the row it amends.

## Wave 1, G1 short-rate models and R9 discrete barriers

| # | Point | Ruling |
|---|---|---|
| G-1 | CIR Feller condition | Not required. `2ab < sigma^2` is allowed: the bond and bond-option formulas hold whenever `r >= 0`, `a > 0`, `b > 0` [BM 3.2.3]. A later simulation scheme (exposure wave) must say how it keeps `r >= 0`; this ruling only covers the closed forms |
| G-2 | Small mean reversion | The goldens include `a = 1e-4`, `tau = 5`. Builds evaluate `B` with `expm1` and use a series for `(B - tau)/a^2` when `a tau < 1e-2`; a direct double evaluation is off by about 1e-9 relative and fails `simple_analytic`. QuantLib 1.44 has the direct form, so this case is mpmath only and not counted as outside |
| G-3 | Hull-White forward at a pillar | `f(0, t)` is the right-hand forward of the log-linear curve when `t` is a pillar time (the forward of the section that starts at `t`). Chosen because `t` is the start of the bond's life, and the bond's own discounting uses the section after `t`. QuantLib's centred numerical derivative averages the two sides, so the pillar case (`t = 2.0`) is not counted as outside; every other Hull-White case keeps `t` off the pillars and counts |
| G-4 | Outside-oracle floor for stage G | 60% over the stage G value suites, rule 11.2.5, with error cases **in** the denominator (the coordinator's stage F ruling, kept). A case counts only if every compared output is a library value from the library's own model objects, or plain arithmetic on such values (E-A17, E-B28). Each generator writes its register (`oracle/outside_register_g.json` for wave 1) |
| G-5 | `short_rate` on Hull-White options | `rates.shortrate.zcb_option` with `HULL_WHITE` does not take `short_rate` (`E_INPUT` if present): `r(0)` is fixed by the curve. `rates.shortrate.zcb` takes `short_rate` for every model, because it prices at a future `t` given the rate then |
| G-6 | `E_LIMIT` sizes, wave 1 | Curve pillars 10,000; `monitoring_per_year` 1,000,000 (larger is `E_LIMIT`, checked after `E_SCHEMA`, before F-2) |
| G-7 | BGK constant | `beta = 0.5826` exactly, as plan 13.3 R9 writes it, not `0.5825971579...`. The two differ by 3e-6 relative in the shift, about 1e-8 relative in price at daily monitoring, which is below the MC acceptance but above `simple_analytic`; one constant is pinned so the four builds agree |
| G-8 | BGK domain | The stage E domain rule (E-A19) is applied to the unshifted barrier. With the shift outward from spot (down barriers move down, up barriers move up) the shifted barrier is then always on the right side of spot |

## Wave 2a, Jamshidian swaption on Hull-White

| # | Point | Ruling |
|---|---|---|
| G-12 | Swaption conventions | Single curve, fixed accruals from the payment times (first period from expiry), floating leg a par floater at expiry. Multi-curve (projection on a separate curve, a basis spread on the floating leg) waits for the calibration wave and will be a new input, not a change of meaning |
| G-13 | Outside check of Jamshidian | QuantLib's `JamshidianSwaptionEngine` stops its critical-rate solve near 1e-8, which moves the price by about 3e-7 relative; it is not the counted check. The counted check uses QuantLib's own `HullWhite` bond and bond-option values at a critical rate solved by QuantLib's `Brent` to 1e-15. `r*` is not an output, because no library returns it |

## Wave 2b, G2++

| # | Point | Ruling |
|---|---|---|
| G-14 | G2++ operations and states | G2++ has its own operations (`rates.g2pp.*`), not a `model` value of `rates.shortrate.*`, because its state is two numbers (`x`, `y`) and `G2PP` is already pinned as an unknown `model` there (`shortrate_g` error case). `rho` must be strictly inside `(-1, 1)` (at `+-1` the model is one-factor and the swaption integral of a later wave is singular); `a = b` is allowed, since no formula divides by `a - b` |

## Wave 3a, Q9 part 1 Monte Carlo Greeks

| # | Point | Ruling |
|---|---|---|
| G-15 | MC Greeks draws and estimators | One normal per path from `core.rng` stream 0 (AS 241), path `i` the `i`-th normal; terminal value sampled exactly. Estimators, smoothing and bump exactly as `06-risk/mc-greeks.md`; standard errors with divisor `n - 1`. Goldens keep every path at least 1e-9 relative from a kink, so builds agree to `common_rng`. The G-10 variance condition passes by a ratio of 0.9985 only; that is recorded as an open item, and G-10 is not changed after the result (12.10 rule) |

## Wave 4a, closed-form swap exposure and CVA

| # | Point | Ruling |
|---|---|---|
| G-16 | Exposure dates and CVA buckets | Exposure is defined only at reset dates before the last payment, where the remaining swap is a swaption and the EE is exact; between resets the floating coupon already fixed makes the exposure path-dependent, which the simulation wave covers. CVA uses default buckets `(t_(k-1), t_k]` with the exposure at the bucket end, `t_0 = 0`, independence of default and rates. Both are stylised and stated as such; the simulation wave must reproduce these numbers on the same grid |

## Wave 2c, Hull-White calibration

| # | Point | Ruling |
|---|---|---|
| G-17 | Calibration objective and outside status | One parameter (`sigma`, `a` fixed), unweighted squared price errors per unit notional, search interval `[1e-4, 1]`, `E_NO_CONVERGENCE` at an end. Judged on `sigma` (1e-9 relative) as well as on repricing, since the optimum is unique. Not counted as outside: QuantLib's `HullWhite.calibrate` needs date-based `SwaptionHelper`s with Black or normal vols and stops at its optimiser's accuracy, so it cannot reproduce this objective to 1e-9; QuantLib's repricing of the fitted prices is recorded as evidence only. A two-parameter (`a`, `sigma`) or piecewise `sigma(t)` fit waits for a later wave |

## Wave 2d, Bermudan swaption reference scheme

| # | Point | Ruling |
|---|---|---|
| G-18 | Pinned Bermudan scheme | The golden is the reference scheme of `short-rate-models.md` in binary64 (fully implicit, linear-extrapolation boundaries, exercise at the knots), as E-A23 for American options; any build implements exactly that scheme. Accuracy is shown by convergence to Jamshidian with one exercise date and by QuantLib's FD and tree engines (evidence file), not by golden tolerance. Not counted as outside: no library implements this scheme. A higher-order engine (Crank-Nicolson with Rannacher steps) may be added later as a separate `method` value; this one keeps its meaning |

## Wave 2e, caps and floors

| # | Point | Ruling |
|---|---|---|
| G-19 | Cap rate and accrual | Single curve: the fixing is the model's simple rate over its own period, `1/P(t_(i-1), t_i) - 1` over `tau_i`, accruals are time differences, payment at period end. A projection curve, fixing lag or a day count other than the time grid waits for a multi-curve wave and will be a new input |

## Wave 2f, Jamshidian for Vasicek and CIR

| # | Point | Ruling |
|---|---|---|
| G-20 | `model` on the swaption | `rates.shortrate.swaption` gains optional `model` (default `HULL_WHITE`, a minor contract change: no existing case changes meaning). The G-5 `short_rate` rule is per model as in `zcb_option`. CIR with no non-negative critical rate is `E_DOMAIN` (checked as `sum c_i P(T0, Ti; 0) < 1`) |

## Wave 2g, callable bonds

| # | Point | Ruling |
|---|---|---|
| G-21 | Callable bond on the G-18 scheme | Issuer call on coupon dates only, at a fixed fraction of face, applied to the ex-coupon value before the coupon is added; no notice period, no accrued interest between dates, no credit spread. The golden is the scheme (G-18); QuantLib's `CallableFixedRateBond` was not compared tonight (its date and accrual setup differs), so the evidence is the straight-bond limit only |

## Fixed before later waves (plan 12.10 rule: no parameter changes after results are seen)

| # | Point | Ruling |
|---|---|---|
| G-9 | Q3b ladder cost | "Full ladder at most 5x one pricing" is measured as the median of 21 timed runs, after 5 warm-up runs, of (a) one Hull-White Bermudan swaption PV and (b) the same PV with its full ladder (every curve pillar plus `a` and `sigma`) by reverse-mode AAD, same process, same thread. Pass when `median(b) / median(a) <= 5`. "AAD equals bump to 1e-8" uses the Q3a reference (Richardson central differences, `h = 1e-4` and `5e-5`): `abs(AAD - ref) <= 1e-10 + 1e-8 abs(ref)` per unit notional |
| G-10 | Q9 variance test | "Smoothed pathwise variance below bump at equal paths": a digital call under GBM (`S = K = 100`, `T = 1`, `r = 0.03`, `v = 0.2`), delta by (i) bump-and-reprice with common draws, `h = 0.01 S`, and (ii) the pathwise estimator with the payoff smoothed by a call spread of width `2 eps`, `eps = 0.01 S`; 100,000 paths, `core.rng` seed 20261109. Pass when the sample variance of (ii) is below that of (i), and the likelihood-ratio delta is within 3 SE of the closed form |
| G-11 | A5 parameters | As the T row in plan 12.10 (domain, 110,000 Sobol points, 1 bp max, 0.5 bp at the 99.9th percentile, `E_DOMAIN` on each of the 14 faces plus NaN and infinity). Challenger only: never in goldens, never in the four-language conformance (12.8), Python research module only |

## Owner decisions, 2026-11-10 (relayed by the coordinator: "agree and go ahead")

| # | Point | Ruling |
|---|---|---|
| G-10 outcome | Q9 variance test as registered | Kept exactly as registered; parameters unchanged. **Outcome: inconclusive, low power (not a pass).** The run of 2026-11-10 gave a per-path variance ratio of 0.9985 (smoothed pathwise 0.0087549, bump 0.0087677), because at `h S = eps` the two estimators are nearly the same call spread, and a comparison of two sample variances cannot separate a 0.15% difference at 100,000 paths. Recorded in CHANGELOG known issues |
| G-10b | Q9 variance test, powered (registered 2026-11-10 before any run of it) | **Question:** does the smoothed pathwise delta of a digital have lower per-path variance than a central bump with a standard finite-difference step, at equal paths? **Setup:** digital call, `S = K = 100`, `T = 1`, `r = 0.03`, `q = 0`, `v = 0.2`; pathwise smoothing `eps = 1.0`; bump `h = 0.001` (relative, central, on `S`). **Independent draws:** `core.rng` seed 20261110, stream 0 for the pathwise estimator, stream 1 for the bump, `n = 60,000` paths each. **Statistic:** `Z = (ln s_b^2 - ln s_pw^2) / sqrt((k_pw - 1)/n + (k_b - 1)/n)`, `s^2` the sample variances (divisor `n - 1`), `k` the sample kurtoses (fourth central moment over `s^4`). **Decision:** one-sided at 5%: pass if `Z > 1.6449`; fail otherwise. Report the variance ratio `s_pw^2 / s_b^2` with its 95% interval `exp(-(ln ratio) +- 1.96 se)` inverted accordingly. **Effect that matters:** a ratio of at most 0.8 (at least a 20% variance reduction). **Power calculation (closed form, no simulation):** each per-path estimator is close to a scaled Bernoulli: pathwise nonzero when `abs(S_T - K) < eps`, `p_pw = 0.039829`; bump nonzero when `K/(1+h) < S_T < K/(1-h)`, `p_b = 0.0039844` (lognormal probabilities). A scaled Bernoulli has kurtosis `k = (1 - 3p + 3p^2)/(p(1 - p))`: `k_pw = 23.149`, `k_b = 248.98`. With `Var(ln s^2) ~ (k - 1)/n`, 80% power at ratio 0.8 and one-sided 5% needs `n = ((1.6449 + 0.8416) / ln(1.25))^2 (k_pw + k_b - 2) = 124.2 x 270.13 = 33,541` per estimator; `n = 60,000` adds a factor of about 1.8 for the Bernoulli approximation (the `S_T/S` factor and discounting are ignored). The same model implies a true ratio near 0.096, so the test is expected to pass; it is registered as a falsifiable check, not assumed |
| F-33 | (stage F, unchanged) | Stays open: only the owner can confirm the `low` scenario formula against MAR21.6 |
