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


## Wave 3b, LIBOR market model (closed-form layer)

| # | Point | Ruling |
|---|---|---|
| G-22 | LMM conventions | Lognormal forwards only (forward or strike `<= 0` is `E_DOMAIN`; a shifted or normal LMM is a future new input). Single curve, accruals from the time grid, caplet variance integrated to the fixing date (not payment). Volatility is the abcd form only [BM 6.3.2]; correlation `exp(-beta |T_i - T_j|)` on fixing times [BM 6.9]. Swaptions by Rebonato's frozen-weight formula [BM 6.13]: the golden is the formula, not the exact LMM price. Outside check: QuantLib 1.44 `AbcdFunction.covariance`, `DiscountCurve.discount` and `blackFormula`, combined by arithmetic (as G-13) |


## Coordinator decisions, 2026-11-11 (owner standing authorisation)

| # | Point | Ruling |
|---|---|---|
| G-23 | Wave 4 outside oracle | ORE (open-source build or binary, no spend, no account) is the outside oracle for wave 4 exposure, PFE and CVA. If it cannot be installed, that is documented and the lower share is accepted as a known issue. **Status 2026-11-11:** owner approved the install; Windows Application Control blocks the ORE DLL on Windows, so ORE 1.8.17.0 runs under WSL Linux (`~/ore-oracle/.venv`), driven by scripts under `oracle/` through `wsl.exe` |
| G-24 | LMM scope in stage G | G-22 stays lognormal only for stage G. A shifted or normal LMM is recorded as a later item |
| G-25 | Rebonato golden | The frozen-weight approximation is the golden (G-22). Its error against a simulated LMM is reported as evidence only, never judged |
| G-26 | Simulated LMM scheme and acceptance | Terminal measure, log-Euler, predictor-corrector drift, volatility at step midpoint, fixings as step boundaries, Cholesky correlation. Judged only by the caplet acceptance (6 caplets within 3 SE at 100,000 paths, 20 steps a year); no goldens (stream-dependent). The midpoint rule replaced a left-point rule after the left-point run was seen (both runs kept in `oracle/`) |
| G-27 | R5 H1: what counts for the Jamshidian suites (amends G-13) | `swaption_g`, `swaption_affine_g` and `exposure_g` are counted only against QuantLib 1.44's own `JamshidianSwaptionEngine` on a `VanillaSwap` (par floater on the same curve, `NullCalendar`, ACT/365F, par coupons), at 3e-7 relative, no platform root solve (`oracle/python/recount_h1.py`, `oracle/H1_RECOUNT_G.json`). Cases whose times are not whole days (semi-annual schedules) cannot be expressed as QuantLib dates and do not count. Result: 26/40, 36/39, 6/15 (were 33, 36, 7). For Vasicek and CIR the engine takes the model plus a model-sampled curve used only for time and index plumbing; the prices agree within 3e-7. Open for the owner: `lmmswn_g` (Rebonato) is a weighted sum of library covariances, with no root solve, and stays counted; under the strictest reading (only a library pricing engine counts) it would not, and stage G would stand at 214 of 405 = 52.8% instead of 250 of 405 = 61.7% |
| G-28 | R5 M1: scheme property tests (amends G-18, G-21) | Bounds on the pinned scheme compare with the scheme's own value of the bounding product on the same grid (single-date Bermudan; no-call bond), never with a closed form; the first-order bias exceeds the optionality in edge cases |
| G-29 | R5 M2: negative strikes in Jamshidian (amends G-20 for all models) | `1 + K tau_n <= 0` is `E_DOMAIN`; otherwise bracket `[-1, 1]`, and no sign change there is `E_DOMAIN`. Three cases appended to `swaption_g` (ids 0041 to 0043) |
| G-30 | R5 M3: discrete barrier dates (amends G-8) | `n = floor(m T + 0.5)`, `n >= 1` else `E_DOMAIN`, BGK step `dt = T/n`. Rebates are not BGK-corrected (a convention). Five cases appended to `barrier_g`: `T = 0.3, m = 252` (n = 76); the tie `T = 0.5, m = 3` (n = 2); `UP_OUT` and `UP_IN` with rebates at non-unit `T`; `n = 0` (`E_DOMAIN`) |
| G-31 | R5 M4: complete `E_LIMIT` table for stage G (amends G-6) | Checked after `E_SCHEMA`, before F-2. Curve pillars 10,000; payment times 10,000; exposure times 10,000; LMM period or payment times 10,000; swaptions in a calibration strip 10,000; `monitoring_per_year` 1,000,000; `paths` 10,000,000; PDE `nx` 10,001; `steps_per_year` 100,000; **combined grid work** `nx x total time steps <= 5e8`, where total steps is the sum over knot intervals of `ceil(steps_per_year x (t_k - t_(k-1)))` (applies to `bermudan_swaption`, `callable_bond`, and any later G-18 scheme). One `E_LIMIT` golden per family (tag `r5`) |
| G-32 | R5 M5: noncentral chi-square evaluation | Start the Poisson sum at the mode `j0 = floor(lambda/2)` with the log weight `-lambda/2 + j0 ln(lambda/2) - lnGamma(j0 + 1)`, then recur up and down until terms fall below 1e-17 of the sum; never form `exp(-lambda/2)` alone (it underflows for `lambda/2 > 745`). A non-positive argument (`rbar < 0`) gives CDF 0. Goldens: CIR with `sigma = 0.005` (large noncentrality) and a strike above `A(T,S)` |
| G-33 | R5 M6: G2++ small and equal mean reversions | Compute every factor `(1 - e^(-x u))/x` as `-expm1(-x u)/x`. The `V(tau)` cross term `tau + (e^(-a tau) - 1)/a + (e^(-b tau) - 1)/b - (e^(-(a+b) tau) - 1)/(a+b)` cancels to `a b tau^3/3 + O(tau^4)`: when `max(a, b) tau < 0.1` use the series `sum_(k>=3) (-1)^k tau^k/k! (a^(k-1) + b^(k-1) - (a+b)^(k-1))` until the term is below 1e-17 relative. The same rule for the single-factor terms (G-2). `a = b` needs no special case. Goldens at `a = 1e-4` and `a = b = 0.1` |
| G-34 | R5 LOW items | L1: G-10b compares variance only; the smoothed estimator is biased (0.018766 against 0.019334, 3%), but its MSE at 60,000 paths (about 4.7e-7) is still below the bump's (about 1.5e-6), so the conclusion holds. L2: the Hull-White `zcb` property "at `t = 0` returns `P(0,T)`" holds with `short_rate = f(0,0)`, the right-hand forward of the first curve section. L4: `times` and `discount_factors` of different lengths, or empty, are `E_INPUT`. L5: MC standard deviations are two-pass (mean first, divisor `n - 1`); `seed` is checked first. L6: R9 acceptance power is modest (continuous price 3.7 SE from the call MC; put z = -1.72), listed in CHANGELOG known issues with G-10. L7: the tolerance-limit reason "1e-12 per unit notional" means the effective limit 1e-6 absolute plus 1e-9 relative; new cases say "1e-9 relative". L8: the G-16 CVA buckets take exposure at bucket end and nothing after the last reset: it is not a bound in either direction. L9: Bermudan step counts in binary64 exactly as written. L10: golden `reviewer` fields stay "self-assessment" until the end-of-project human review; the MG inventory dates record the spec review, not a golden review. Citations: section and equation numbers to unopened books are pointers, not checked quotations |
| G-35 | Q3b ladder golden | `rates.shortrate.bermudan_ladder`: derivative of the discrete G-18 scheme, reference by two Richardson pairs (Q3a rule) that must agree within 1e-9 relative, else the case is dropped (bump crossed an exercise node). Goldens at `nx = 101`, 50 steps a year, to keep the reference run short. G-9 tolerance and performance test unchanged |
| G-36 | Q9 part 2 (registered 2026-11-11 before any run) | Statistic `risk.model_reserve.dispersion` (range [Cont06], reserve = max deviation from the booked model, tie by code-point order, `relative_reserve` null at a zero booked price). Report parameters as `06-risk/model-reserve.md` (Heston truth, LV and SLV with `xi x 0.5`, booked SLV, 200,000 paths, seed 20261111, six single-asset products, vanilla sanity gate within 3 SE); no pass/fail on reserve size; multi-asset exotics out of scope |
| G-38 | Language questions G-J1 to G-J3 (Java lane, 2026-11-11) | **G-J1:** negative `start_years` in `xva.exposure.swap_ee_hw` is `E_DOMAIN`, checked after `side` and before `payment_times` (Java's order adopted). **G-J2:** a 2,001-point log scan on `[1e-4, 1]` then bisection on the analytic `F'` to 1e-15 relative width is acceptable; any method that finds the interior minimiser to the 1e-9 relative judging tolerance is, and an end-point minimiser is `E_NO_CONVERGENCE` as specified. **G-J3:** `capfloor_g-0040` was wrong (`strike = -0.5`, annual, gives `1 + K tau = 0.5 > 0`); the golden now uses `strike = -1.0` (`1 + K tau = 0`, `E_DOMAIN`). Every other hard-coded error case of the stage G generators was re-read against its rule; no other mismatch found |
| G-37 | A5 test set and harness (registered 2026-11-11, before any surrogate) | Extra 10,000 points: even rows to the wing, odd rows to `T < 0.1`, as `11-research/a5-surrogate.md`. Reference Heston by Lewis quadrature (QuantLib checked); SABR by Hagan with `F = 0.03` (`beta < 1`) or 1. Points with reference OTM price below 1e-12 excluded; more than 1% excluded makes the run invalid. Harness self-test must pass the exact pricer and fail a 2 bp shift and an unguarded pricer |
| G-39 | Coordinator decision 2026-11-11 on G-27 and the floor | `lmmswn_g` (Rebonato) keeps counting under G-13: plain arithmetic on library values, applied as for the earlier suites. No known issue on the floor: G-4 applies at release, and wave 4 checked against ORE under WSL must bring stage G back to 60% or more |
| G-40 | Wave 4b scope and exposure conventions | Deterministic xVA on given paths; CSA call each grid point, MTA on the change of the target, collateral arrives `mpor_steps` later, IA added to the held amount; PFE by the inverted-CDF rule; EPE and effective EPE as `xva-framework.md`. Not counted as outside; the simulated slice (4c) carries ORE |
| G-41 | Adjustment conventions | Bucket-end exposure (as G-16), first-to-default weighting by survival of both names at the bucket start; FVA = FCA - FBA with the overlap rule `s_l -> max(s_l - h_b (1 - R_b), 0)` when `exclude_dva_overlap`; MVA and KVA as funding-style integrals of given IM and capital profiles |
| G-42 | (reserved for the simulated EE/PFE/EPE and CVA slice checked against ORE, wave 4c) | |
| G-43 | SIMM-style margin | One currency, IR delta only; risk weights, correlations and the concentration threshold are inputs (no ISDA calibration is distributed) |
| G-44 | Wrong-way risk | Hull-White (2012) hazard `exp(a(t) + b V(t))`, `a(t)` fitted bucket by bucket to the survival curve on the given paths |
| G-45 | E1 for the stage G operations | `gen_stage_f_e1.py G` writes `datasets/golden/stage_g_e1/e1g_*.json` (NaN, +inf, -inf and negative zero on every Real leaf of each operation's smallest ok case; rules F-1 to F-3). E1 suites are robustness checks and stay outside the G-4 denominator, as the stage F E1 suites stayed outside the stage F share; open for the owner to confirm |

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
| G-10b outcome | Run 2026-11-10 after registration (`oracle/python/run_g10b.py`, `oracle/G10B_RESULT.json`) | **Pass.** Per-path variance: smoothed pathwise 0.0090503, bump 0.0891291; ratio 0.1015, 95% interval [0.0888, 0.1161]; `Z = 33.35 > 1.6449`. Sample kurtoses 23.02 and 261.15 (registered predictions 23.15 and 248.98), so the power calculation's assumptions held. G-10 itself stays "inconclusive, low power" |
