# Exotic options

Spec version 1.0.0. Status: Specified. Stage E, slice E5 (spec A). `specifications/stage-e-rulings.md` is normative.

Common inputs, unless an operation says otherwise: `spot` `S` (> 0), `strike` `K` (> 0), `expiry_years` `T` (> 0), `rate` `r`, `dividend_yield` `q` (flat continuous, any sign), `vol` `v` (> 0), `option_type` (`CALL`, `PUT`). Cost of carry `b = r - q`. A value outside its range: `E_DOMAIN`; an array or shape rule: `E_INPUT`; all checks in input order, whatever their code (ruling E-A38). Lists are capped at 100 (stage C ruling C10), `E_LIMIT` at the gate. Prices are per unit of underlying.

`GBS(type, S, K, T, r, b, v)` is generalised Black-Scholes: `d1 = (ln(S/K) + (b + v^2/2)T)/(v sqrt T)`, `d2 = d1 - v sqrt T`; call `S e^{(b-r)T} N(d1) - K e^{-rT} N(d2)`, put `K e^{-rT} N(-d2) - S e^{(b-r)T} N(-d1)`.

Sources:
- [Haug] E. G. Haug, *The Complete Guide to Option Pricing Formulas*, 2nd ed., McGraw-Hill, 2007: chapter 4 (barriers: Reiner-Rubinstein table; lookbacks: Goldman-Sosin-Gatto; chooser: Rubinstein; Asians: Kemna-Vorst), chapter 5 (Kirk; quanto), chapter 3 (Barone-Adesi-Whaley) (not opened in this session; formulas checked against QuantLib 1.44 engines, which implement the same papers).
- [RR91] E. Reiner, M. Rubinstein, "Breaking down the barriers", *Risk* 4(8), 1991 (not opened).
- [BAW87] G. Barone-Adesi, R. Whaley, "Efficient analytic approximation of American option values", *Journal of Finance* 42(2), 1987 (not opened).
- [CRR79] J. Cox, S. Ross, M. Rubinstein, "Option pricing: a simplified approach", *Journal of Financial Economics* 7, 1979 (not opened).
- [Hull] J. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Binomial Trees in Practice" (tree probability with a dividend yield) (not opened).
- [Kirk95] E. Kirk, "Correlation in the energy markets", in *Managing Energy Price Risk*, Risk Publications, 1995 (not opened).
- [Levy92] E. Levy, "Pricing European average rate currency options", *Journal of International Money and Finance* 11, 1992 (moment matching) (not opened).

## `exotic.digital.price`

Inputs: common, `payoff` (`CASH_OR_NOTHING`, `ASSET_OR_NOTHING`), `cash` (> 0; required for both, unused for asset). With `d1`, `d2` at `b = r - q` and `phi = +1` call, `-1` put: cash-or-nothing `cash e^{-rT} N(phi d2)`; asset-or-nothing `S e^{-qT} N(phi d1)`. Output `price`.

## `exotic.barrier.price`

Inputs: common, `barrier` `H` (> 0), `rebate` `R` (>= 0), `barrier_type` (`DOWN_IN`, `DOWN_OUT`, `UP_IN`, `UP_OUT`). Continuous monitoring. Spot on or beyond the barrier (`S <= H` for down, `S >= H` for up): `E_DOMAIN` (ruling E-A19). Output `price`.

With `sd = v sqrt T`, `mu = (b - v^2/2)/v^2`, `lambda = sqrt(mu^2 + 2r/v^2)`, `phi` as above, `eta = +1` down, `-1` up:

`x1 = ln(S/K)/sd + (1+mu) sd`, `x2 = ln(S/H)/sd + (1+mu) sd`, `y1 = ln(H^2/(S K))/sd + (1+mu) sd`, `y2 = ln(H/S)/sd + (1+mu) sd`, `z = ln(H/S)/sd + lambda sd`;

- `A = phi S e^{(b-r)T} N(phi x1) - phi K e^{-rT} N(phi x1 - phi sd)`; `B` the same with `x2`;
- `C = phi S e^{(b-r)T} (H/S)^{2(mu+1)} N(eta y1) - phi K e^{-rT} (H/S)^{2 mu} N(eta y1 - eta sd)`; `D` the same with `y2`;
- `E = R e^{-rT} (N(eta x2 - eta sd) - (H/S)^{2 mu} N(eta y2 - eta sd))` (knock-in rebate, paid at expiry if never hit);
- `F = R ((H/S)^{mu+lambda} N(eta z) + (H/S)^{mu-lambda} N(eta z - 2 eta lambda sd))` (knock-out rebate, paid at the hit).

| Type | `K > H` | `K <= H` |
|---|---|---|
| down-in call | `C + E` | `A - B + D + E` |
| up-in call | `A + E` | `B - C + D + E` |
| down-in put | `B - C + D + E` | `A + E` |
| up-in put | `A - B + D + E` | `C + E` |
| down-out call | `A - C + F` | `B - D + F` |
| up-out call | `F` | `A - B + C - D + F` |
| down-out put | `A - B + C - D + F` | `F` |
| up-out put | `B - D + F` | `A - C + F` |

[RR91], [Haug] chapter 4. With no rebate, in plus out equals the vanilla (checked in the generator).

## `exotic.asian.geometric`

Inputs: common, `averaging` (`CONTINUOUS`, `DISCRETE`), `fixing_years` (for `DISCRETE`: strictly increasing, each in `(0, T]`, at least 1, else `E_INPUT`; for `CONTINUOUS` must be `[]`, else `E_INPUT`). Average-price, fixed strike, fixings from today (no past fixings).

- Continuous (Kemna-Vorst): `GBS(type, S, K, T, r, b_A, v/sqrt 3)` with `b_A = (b - v^2/6)/2`.
- Discrete, `n` fixings at `t_i`: `m = ln S + (b - v^2/2) mean(t_i)`, `V = v^2 sum_i sum_j min(t_i, t_j)/n^2`, `d1 = (m - ln K + V)/sqrt V`, `d2 = d1 - sqrt V`; call `e^{-rT}(e^{m + V/2} N(d1) - K N(d2))`, put `e^{-rT}(K N(-d2) - e^{m+V/2} N(-d1))`.

Output `price`. Arithmetic Asians are not in stage E (they need Monte Carlo or an approximation; register row EA16).

## `exotic.lookback.floating`

Inputs: common less `strike`, `running_extreme`: the minimum so far for a call (`<= S`), the maximum so far for a put (`>= S`), else `E_DOMAIN`. Continuous monitoring. `|b| <= 1e-8 v^2`: `E_DOMAIN` (the formula divides by `b`; rulings E-A20, E-A28). Near that bound binary64 loses digits: at `b = 1e-5` the golden is judged to 1e-8. Goldman-Sosin-Gatto [Haug ch. 4]: with `m` the minimum,

call `= S e^{(b-r)T} N(a1) - m e^{-rT} N(a2) + S e^{-rT} (v^2/(2b)) ((S/m)^{-2b/v^2} N(-a1 + 2b sqrt T/v) - e^{bT} N(-a1))`, `a1 = (ln(S/m) + (b + v^2/2)T)/(v sqrt T)`, `a2 = a1 - v sqrt T`;

put, with `M` the maximum, `= -S e^{(b-r)T} N(-b1) + M e^{-rT} N(-b2) + S e^{-rT} (v^2/(2b)) (-(S/M)^{-2b/v^2} N(b1 - 2b sqrt T/v) + e^{bT} N(b1))`, `b1`, `b2` as `a1`, `a2` with `M`.

## `exotic.quanto.price`

Inputs: `spot` (foreign asset), `strike`, `expiry_years`, `domestic_rate` `rd`, `foreign_rate` `rf`, `dividend_yield` `q`, `vol`, `fx_vol` (> 0), `correlation` `rho` (in `[-1, 1]`, else `E_DOMAIN`) between the asset and the FX rate quoted domestic per foreign, `option_type`. Payoff `(S_T - K)^+` (or put) in domestic currency at a fixed rate of 1. Price `GBS(type, S, K, T, rd, rf - q - rho v fx_vol, v)` [Haug ch. 5]. Output `price`.

## `exotic.chooser.price`

Inputs: common, `choose_years` `t` (in `(0, T]`, else `E_INPUT`). Simple chooser, same strike and expiry [Haug ch. 4]: with `d = (ln(S/K) + (b + v^2/2)T)/(v sqrt T)`, `y = (ln(S/K) + bT + v^2 t/2)/(v sqrt t)`,

`price = S e^{(b-r)T} N(d) - K e^{-rT} N(d - v sqrt T) - S e^{(b-r)T} N(-y) + K e^{-rT} N(-y + v sqrt t)`.

## `exotic.spread.kirk`

Inputs: `forward_1`, `forward_2` (> 0), `strike` (any sign, with `forward_2 + strike > 0`, else `E_DOMAIN`), `expiry_years`, `rate`, `vol_1`, `vol_2` (> 0), `correlation` (in `[-1, 1]`), else `E_DOMAIN` (ruling E-A39). Call on `F1 - F2 - K` [Kirk95]: `f = F2/(F2 + K)`, `s = sqrt(v1^2 - 2 rho v1 v2 f + v2^2 f^2)`, `d1 = (ln(F1/(F2 + K)) + s^2 T/2)/(s sqrt T)`, price `e^{-rT}(F1 N(d1) - (F2 + K) N(d1 - s sqrt T))`. At `K = 0` this is Margrabe's exchange option. Output `price`.

## `exotic.basket.moment`

Inputs: `forwards`, `weights` (same length as `forwards`, else `E_INPUT`; each >= 0, not all 0, else `E_DOMAIN`), `vols`, `correlation` (square, symmetric, unit diagonal, entries in `[-1, 1]`, else `E_INPUT`), `strike`, `expiry_years`, `rate`, `option_type`. Lognormal moment matching [Levy92]: `M1 = sum w_i F_i`, `M2 = sum_i sum_j w_i w_j F_i F_j e^{rho_ij v_i v_j T}`, `v_B = sqrt(ln(M2/M1^2)/T)`, price `GBS(type, M1, K, T, r, 0, v_B)`. Outputs `price`, `basket_forward` (`M1`), `basket_vol` (`v_B`). Negative weights (spreads) are refused: use Kirk (ruling E-A21).

## American options

### `exotic.american.crr`

Inputs: common, `steps` `n` (1 to 20,000, else `E_INPUT` / `E_LIMIT`). Cox-Ross-Rubinstein [CRR79] with Hull's dividend-yield probability [Hull]: `dt = T/n`, `u = e^{v sqrt dt}`, `d = 1/u`, `p = (e^{(r-q)dt} - d)/(u - d)`; `p` outside `(0, 1)`: `E_DOMAIN`. Node `(i, j)` (`j` down moves) has `S u^{i-2j}`. Backward induction with `e^{-r dt}`; the American value takes the larger of continuation and intrinsic at every node, including `i = 0`. Outputs `american`, `european` (same tree, no exercise), `early_exercise_premium` (their difference).

### `exotic.american.baw`

Inputs: common. Barone-Adesi-Whaley [BAW87], [Haug ch. 3]: `M = 2r/v^2`, `N = 2b/v^2`, `K_T = 1 - e^{-rT}`. `r <= 0`: `E_DOMAIN` (rulings E-A22, E-A30). A call with `b >= r` is European (`GBS`).

- Call: `q2 = (-(N-1) + sqrt((N-1)^2 + 4M/K_T))/2`; critical price `S*` solves `S* - K = GBS(call, S*) + (1 - e^{(b-r)T} N(d1(S*))) S*/q2`; `A2 = (S*/q2)(1 - e^{(b-r)T} N(d1(S*)))`; price `GBS(call, S) + A2 (S/S*)^{q2}` if `S < S*`, else `S - K`.
- Put: `q1 = (-(N-1) - sqrt((N-1)^2 + 4M/K_T))/2`; `S**` solves `K - S** = GBS(put, S**) - (1 - e^{(b-r)T} N(-d1(S**))) S**/q1`; `A1 = -(S**/q1)(1 - e^{(b-r)T} N(-d1(S**)))`; price `GBS(put, S) + A1 (S/S**)^{q1}` if `S > S**`, else `K - S`.

Any root finder; output `price`, judged to 1e-5 per unit (ruling E-A22).

### `exotic.american.fd`

Inputs: common, `exercise` (`AMERICAN`, `EUROPEAN`), `grid` `{nx, nt, width}`: `nx` odd, at least 5, else `E_INPUT`; at most 1001, else `E_LIMIT`; `nt` at least 1, else `E_INPUT`, at most 10,000, else `E_LIMIT`; `width` > 0, else `E_DOMAIN` (ruling E-A40).

Reference scheme (ruling E-A23): `x = ln S`; `x_i = ln S - h + i dx`, `h = width v sqrt T`, `dx = 2h/(nx-1)` (so `x_{(nx-1)/2} = ln S`); `dt = T/nt`. Backward Euler in time-to-expiry on `V_tau = (v^2/2) V_xx + (r - q - v^2/2) V_x - r V`, central differences: row `i` (interior) `V_{i-1}: -dt(v^2/(2dx^2) - mu/(2dx))`, `V_i: 1 + dt(v^2/dx^2 + r)`, `V_{i+1}: -dt(v^2/(2dx^2) + mu/(2dx))`, `mu = r - q - v^2/2`. Start at the payoff. Boundary rows: American, the intrinsic value; European, `max(phi(e^{x} e^{-q tau} - K e^{-r tau}), 0)` at `tau = (n+1)dt`. American: after each solve, `V = max(V, payoff)`. Outputs at the centre node `i`: `price = V_i`, `delta = (V_{i+1} - V_{i-1})/(2 dx S)`, `gamma = ((V_{i+1} - 2V_i + V_{i-1})/dx^2 - (V_{i+1} - V_{i-1})/(2dx))/S^2`.

## Wrong conventions the goldens catch

Cash digital on `N(d1)`; barrier `mu` with `r` for `b`; knock-in rebate dropped; continuous geometric vol `v/2`; lookback without the reflection term; quanto adjustment sign; chooser as call plus put; Kirk without the `F2/(F2+K)` weight; basket vol from weighted vols; tree probability without `q`; BAW put with the call root; FD without the exercise projection.

## Stage G addition: discrete barrier monitoring (plan 13.3 R9)

Rulings `stage-g-rulings.md` G-7, G-8. Suite `stage_g/barrier_g` (32 cases), written by `oracle/python/gen_stage_g_w1.py` (slice `R9`). Source: [BGK97] M. Broadie, P. Glasserman, S. Kou, "A continuity correction for discrete barrier options", *Mathematical Finance* 7(4), 1997 (not opened; the constant is `-zeta(1/2)/sqrt(2 pi) = 0.5825971579...`).

`exotic.barrier.price` gains two optional inputs:
- `monitoring`: `CONTINUOUS` (the default when absent; stage E behaviour unchanged) or `DISCRETE`; another value is `E_INPUT`.
- `monitoring_per_year` `m`: an Integer, required with `DISCRETE` and not allowed with `CONTINUOUS` (both `E_INPUT`); `m >= 1`, else `E_DOMAIN`. The barrier is observed at `T/n, 2T/n, ..., T` with `n = floor(m T + 0.5)` (ties round up, the same in every language; ruling G-30); `n = 0` is `E_DOMAIN`. The correction uses `dt = T/n`, the actual observation spacing (amended by R5 M3; for integer `m T` this equals `1/m`, so the original goldens are unchanged).

With `DISCRETE`, the price is the continuous-monitoring price of this page with the barrier replaced by `H' = H exp(-beta v sqrt(dt))` for `DOWN_*` and `H' = H exp(+beta v sqrt(dt))` for `UP_*`, `beta = 0.5826` exactly (ruling G-7). The rebate is unchanged and is paid as in the continuous case. The rebate leg is a convention, not a BGK approximation: BGK corrects the barrier-crossing probability of the option leg only [BGK97], so rebate rows are not expected to match a discretely monitored Monte Carlo. The domain check (ruling E-A19) uses the **unshifted** `H`, then the shifted price is computed (ruling G-8).

Wrong conventions caught: the shift with the opposite sign; the continuous price for a daily barrier.

**Acceptance (R9).** A daily-monitored (`m = 252`, `T = 1`) down-and-out call and put (`S = K = 100`, `H = 90`, `r = 0.05`, `q = 0.02`, `v = 0.25`) match an exact-date Monte Carlo (GBM sampled exactly at the 252 dates, knocked out if `S <= H` at any date, 40,000 paths, `core.rng` seed 20261109, inverse normal) within 3 SE. Oracle run 2026-11-10: call BGK 8.51904 against MC 8.45109 +- 0.08496 (z = +0.80); put 0.118543 against 0.125394 +- 0.003990 (z = -1.72). The continuous price (8.13881) is 3.7 SE from the MC call value, so the check discriminates. Stored in `oracle/R9_ACCEPTANCE.json`. Each language adds the same check as a property test (its own MC, same seed and path count; pass at 3 SE).

Outside: none counted. QuantLib's `AnalyticBarrierEngine` at the shifted barrier would only check the stage E formula, which is already counted; the shift is the point under test, and its evidence is the MC acceptance.
