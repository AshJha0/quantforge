# LIBOR market model: caps, floors and swaptions (closed-form layer)

Spec version 1.0.0. Status: Specified (stage G, wave 3b). Ruling: `stage-g-rulings.md` G-22. Suites `stage_g/lmmcap_g` (26 cases) and `stage_g/lmmswn_g` (42 cases), written by `oracle/python/gen_stage_g_lmm.py`.

**Plain idea.** The LIBOR market model (LMM) does not model a short rate. It models each simple forward rate of a tenor grid directly, each one lognormal under the measure that pays at the end of its own period. Two things follow. A caplet on one forward is priced by Black's formula, with the variance being the integral of that forward's volatility up to its fixing date; this is why the market quotes caps in Black volatilities. A swaption depends on many forwards at once, so it has no exact closed form, but Rebonato's approximation, which freezes the weights that turn forwards into a swap rate, gives a Black volatility for the swap rate from the forward volatilities and their correlations. This page fixes those two closed forms. The simulated LMM (drifts under the spot or terminal measure) is a later slice, and it must reproduce these caplet values within its Monte Carlo error.

Sources:
- [BM] D. Brigo, F. Mercurio, *Interest Rate Models: Theory and Practice*, 2nd ed., Springer, 2006: section 6.4 (caplets in the LMM, Black's formula), section 6.3.2 (the abcd form, there "formulation 7"), section 6.9 (exponential correlation), section 6.13 (Rebonato's swaption approximation, eq. 6.67) (not opened in this session; the formulas are checked against QuantLib, below).
- [Reb] R. Rebonato, *Volatility and Correlation*, 2nd ed., Wiley, 2004, chapter 6 (the abcd instantaneous volatility) (not opened).
- [B76] F. Black, "The pricing of commodity contracts", *Journal of Financial Economics* 3 (1976), 167-179 (Black's formula).
- [BGM] A. Brace, D. Gatarek, M. Musiela, "The market model of interest rate dynamics", *Mathematical Finance* 7 (1997), 127-155 (the model).
- Outside oracle: QuantLib 1.44 `AbcdFunction.covariance`, `DiscountCurve.discount` and `blackFormula` (rule 11.2.5, as G-13).

## Common inputs and conventions (ruling G-22)

- `curve`: as `rates.shortrate.zcb` for Hull-White (log-linear discount factors, ACT/365F year fractions, flat forward beyond the last pillar). Single curve: the forward over `[s, t]` is `F = (P(s)/P(t) - 1)/(t - s)`.
- `abcd`: object `{a, b, c, d}`. Forward `i` with fixing time `T` has instantaneous volatility `sigma_T(t) = (a + b (T - t)) exp(-c (T - t)) + d` for `t <= T` [BM 6.3.2, Reb ch. 6]. `c > 0`, `d >= 0` and `a + d > 0` (positive at the fixing), else `E_DOMAIN`. `a = b = 0` gives a constant volatility `d`: the Black-76 limit.
- Every forward rate must be `> 0` and every strike or fixed rate `> 0` (lognormal model), else `E_DOMAIN`.
- Variance and covariance integrals `C(T_i, T_j; u) = integral_0^u sigma_(T_i)(t) sigma_(T_j)(t) dt`. Implementations may use the closed form of the integral or a quadrature that is exact to 1e-14 relative.

## `rates.lmm.capfloor`

Inputs: `curve`, `abcd`, `period_times` `t_0 < ... < t_m` (at least two, increasing, else `E_INPUT`; `t_0 > 0`, else `E_DOMAIN`), `strike` `K`, `cap_floor` (`CAP`, `FLOOR`, else `E_INPUT`), `notional`.

Formal statement [BM 6.4]. Period `i` has `tau_i = t_i - t_(i-1)`, forward `F_i` fixed at `t_(i-1)`, paid at `t_i`. With `v_i^2 = C(t_(i-1), t_(i-1); t_(i-1))`:

`caplet_i = notional tau_i P(t_i) Black(F_i, K, v_i)`, `Black = F N(d1) - K N(d2)`, `d1,2 = (ln(F/K) +- v^2/2)/v`; a floorlet uses `K N(-d2) - F N(-d1)` [B76].

Outputs: `price` (sum), `caplet_prices`, `forward_rates`, `black_vols` (`v_i / sqrt(t_(i-1))`, the flat Black volatility the market would quote for that caplet).

Worked example (case `lmmcap_g-0001`). Humped abcd `(-0.06, 0.17, 0.54, 0.17)`, semi-annual cap to 5 years at 3%, notional 1,000,000. The first caplet fixes at 0.5: `v^2 = integral_0^0.5 sigma^2 dt`, its Black volatility is 0.1547 (the next two 0.1869 and 0.2088), below the peak of the hump (about 0.26 at 1.5 years to fixing), as the abcd shape intends. Each caplet is then a Black price; the golden holds the sum and each piece.

Validation: two volatility shapes (humped, flat 20%) x two schedules x cap and floor x two strikes (16 cases) plus one low-rate curve (1), 9 error cases. Asserted: cap minus floor equals `notional sum (P(t_(i-1)) - (1 + K tau_i) P(t_i))` on all 8 pairs; with the flat shape every `black_vols` entry is 0.20 to 1e-14. Wrong convention caught: the variance integrated to the payment date instead of the fixing date (gap 595 on 1,000,000).

## `rates.lmm.swaption_rebonato`

Inputs: `curve`, `abcd`, `correlation_beta` `beta >= 0` (else `E_DOMAIN`), `expiry_years` `T_0 > 0` (else `E_DOMAIN`), `payment_times` `T_1 < ... < T_n` (at least one, `T_1 > T_0`, else `E_INPUT`), `fixed_rate` `K > 0`, `side` (`PAY`, `RECEIVE`, else `E_INPUT`), `notional`. Fixed and floating accruals both from the payment times (first period from expiry), as G-12.

Formal statement [BM 6.13, eq. 6.67]. Forwards `F_i` on `[T_(i-1), T_i]`, annuity `A = sum tau_i P(T_i)`, frozen weights `w_i = tau_i P(T_i)/A`, swap rate `S = sum w_i F_i`, correlation `rho_ij = exp(-beta |T_(i-1) - T_(j-1)|)` [BM 6.9]. Then

`v^2 = (1/S^2) sum_i sum_j w_i w_j F_i F_j rho_ij C(T_(i-1), T_(j-1); T_0)`, `price = notional A Black(S, K, v)` (call for a payer, put for a receiver).

Outputs: `price`, `swap_rate`, `annuity`, `black_vol` (`v / sqrt(T_0)`).

Worked example (case `lmmswn_g-0001`). Humped abcd, `beta = 0`, 1 year into 5 years, payer at 3.5%. With `beta = 0` every pair is perfectly correlated, so `v` is the weighted average of the forward volatilities; raising `beta` to 0.5 lowers the swaption volatility (diversification across forwards): for 5 years into 5 it falls from 0.2283 at `beta = 0` to 0.1670 at `beta = 0.5`. The cap price of the example is 42,638.43.

Validation: two shapes x three `beta` (0, 0.1, 0.5) x three swaptions (1y into 5y, 5y into 5y, 2y into 2y semi-annual) x payer and receiver (36 cases), 6 error cases. Asserted: payer minus receiver equals `notional A (S - K)` on all 18 pairs; flat shape with `beta = 0` gives `black_vol = 0.20` to 1e-14. Wrong convention caught: correlation ignored (`rho = 1`) at `beta = 0.5` (gap 7,008 on 1,000,000).

## Tolerances and outside share

Prices: `simple_analytic` with limit 1e-6 absolute plus 1e-9 relative (1e-12 per unit notional). Other outputs: 1e-12 absolute plus 1e-10 relative. Outside: every value case matches QuantLib 1.44 (17 of 26 and 36 of 42 count; the error cases are in the denominator, G-4).

## Edge cases

| Case | Behaviour |
|---|---|
| Forward rate `<= 0` (negative-rate curve) | `E_DOMAIN`: the lognormal LMM is undefined. A shifted or normal LMM is a new input, not a change of meaning (G-22) |
| `abcd` with `a = b = 0` | constant volatility `d`: caplets reduce to Black-76 at `d` |
| `beta = 0` | perfect correlation: the swaption volatility is the weighted forward volatility |

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Variance integral `C(T_i, T_j; u)` | exact (closed form) or quadrature to 1e-14 relative | every golden: 50-digit `mp.quad` agrees with QuantLib's closed-form `AbcdFunction.covariance` within the 1e-10 relative output tolerance on all 53 value cases | `a = b = 0`: `C = d^2 u`, so `black_vols = d` to 1e-14 (asserted) | QuantLib 1.44 `AbcdFunction` |
| Rebonato frozen-weight approximation | none (an approximation, not a limit) | the golden is the formula itself; its error against a simulated LMM is reported by the later simulation slice, not judged here | `beta = 0` with flat volatility: `black_vol = d` exactly (asserted) | [BM 6.13] |

## Simulated LMM (stage G wave 3c): acceptance only

**Plain idea.** The closed forms above price one caplet or approximate one swaption. Path-dependent and Bermudan LMM products need the forwards simulated jointly. The simulation has no golden of its own (its numbers depend on the random stream); it is judged by reproducing the wave 3b caplets, which are exact under the model.

Formal statement [BM 6.3, eq. 6.12; Glasserman, *Monte Carlo Methods in Financial Engineering*, Springer, 2003, section 3.7 (not opened)]. Under the measure of the last grid date `T_N`, for `t` before the fixing of `F_k`:

`d ln F_k = (mu_k - sigma_k^2/2) dt + sigma_k dW_k`, `mu_k = -sigma_k sum_(j > k) rho_kj tau_j sigma_j F_j / (1 + tau_j F_j)`, `dW_i dW_j = rho_ij dt`.

Scheme (ruling G-26): log-Euler with a predictor-corrector drift (the drift averaged at the start and at the predicted end of the step), `sigma` frozen at the step midpoint, every fixing date a step boundary, correlated normals by Cholesky of `rho`. A forward stops at its fixing. A caplet on `F_k` paid at `T_(k+1)` is `P(0, T_N) E^N[tau_k max(F_k(T_k) - K, 0) prod_(j > k) (1 + tau_j F_j(T_(k+1)))]`.

Acceptance (`oracle/python/run_lmm_mc.py`, `oracle/LMM_ACCEPTANCE.json`): humped abcd, `beta = 0.1`, annual grid to 7 years, `K = 4.5%`, 100,000 paths, 20 steps a year, numpy PCG64 seed 20261111. All six caplets must lie within 3 standard errors of `lmmcap_g` closed forms. **Pass:** `z` from -1.49 to 0.61. Each language adds this as a property test with its own stream, same parameters.

Disclosure: the first run froze `sigma` at the step start (`oracle/LMM_ACCEPTANCE_LEFTPOINT.json`); it also passed but the 1-year caplet sat at `z = 2.97`, a discretisation bias of the left-point rule on the steep part of the hump. The midpoint rule was adopted after that run was seen, so it is recorded here, not hidden.

Rebonato error, evidence only (G-25): 5 years into 5, payer at 3.5%: Rebonato exceeds the simulation by 0.41% at `beta = 0` and 0.47% at `beta = 0.5` (simulation SE about 0.6% and 0.5%), consistent with the sub-percent accuracy reported for the formula [BM 6.13].
