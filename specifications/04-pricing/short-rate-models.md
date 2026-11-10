# One-factor short-rate models: Vasicek, CIR, Hull-White

Spec version 1.0.0. Status: Specified (stage G, wave 1, slice G1). Rulings: `stage-g-rulings.md` G-1 to G-6. Suite `stage_g/shortrate_g`, written by `oracle/python/gen_stage_g_w1.py` (slice `G1`).

**Plain idea.** A short-rate model says how the overnight rate moves randomly through time. From it, the price of a zero-coupon bond and of an option on that bond follow in closed form. These three models are the base of stage G: Bermudan swaptions, callable bonds and the exposure simulation for xVA (later waves) all run on Hull-White, and the bond-option formula here is the building block of Jamshidian's swaption decomposition.

Sources:
- [V77] O. Vasicek, "An equilibrium characterization of the term structure", *Journal of Financial Economics* 5, 1977 (not opened).
- [CIR85] J. Cox, J. Ingersoll, S. Ross, "A theory of the term structure of interest rates", *Econometrica* 53(2), 1985 (not opened).
- [HW90] J. Hull, A. White, "Pricing interest-rate-derivative securities", *Review of Financial Studies* 3(4), 1990 (not opened).
- [J89] F. Jamshidian, "An exact bond option formula", *Journal of Finance* 44(1), 1989 (not opened).
- [BM] D. Brigo, F. Mercurio, *Interest Rate Models: Theory and Practice*, 2nd ed., Springer, 2006, sections 3.2.1 (Vasicek, eqs. 3.5 and 3.10), 3.2.3 (CIR, eqs. 3.24 and 3.26), 3.3 (Hull-White, eqs. 3.39 and 3.41) (not opened in this session; formulas checked against QuantLib 1.44 `Vasicek`, `CoxIngersollRoss` and `HullWhite`, which implement the same equations).

## Conventions

- Time is in years as a Real (`t_years`, `expiry_years`, `maturity_years`). There are no dates in this slice; a caller converts dates with ACT/365F (`01-core/daycount.md`).
- Risk-neutral dynamics, no market price of risk (Vasicek `lambda = 0`).
  - `VASICEK`: `dr = a (b - r) dt + sigma dW`.
  - `CIR`: `dr = a (b - r) dt + sigma sqrt(r) dW`. The Feller condition `2 a b >= sigma^2` is **not** required (ruling G-1).
  - `HULL_WHITE`: `dr = (theta(t) - a r) dt + sigma dW`, with `theta` fitted so the model reprices the input curve exactly.
- Inputs: `mean_reversion` `a` (> 0), `sigma` (> 0), `long_term_mean` `b` (`VASICEK`: any; `CIR`: > 0). `HULL_WHITE` takes `curve` instead of `b`.
- `curve` (`HULL_WHITE` only): `{times, discount_factors}`, pillar times strictly increasing and > 0 (else `E_INPUT`), discount factors > 0 (else `E_DOMAIN`), at least one pillar. `P(0, 0) = 1`. Interpolation is log-linear in discount factor (piecewise flat forward), with `(0, 1)` as the first node, and flat forward beyond the last pillar. The instantaneous forward `f(0, t)` at a pillar time is the **right-hand** forward (ruling G-3).

## `rates.shortrate.zcb`

Price at time `t` of a zero-coupon bond paying 1 at `T`, given the short rate `r` at `t`.

Inputs: `model` (`VASICEK`, `CIR`, `HULL_WHITE`; else `E_INPUT`), the model's parameters, `short_rate` `r` (required for every model; `CIR` needs `r >= 0`, else `E_DOMAIN`), `t_years` (>= 0), `maturity_years` (> `t_years`).

Outputs: `discount_factor` `P(t, T) = A(t, T) exp(-B(t, T) r)` and `zero_rate` `= -ln P / (T - t)` (continuous).

With `tau = T - t`:
- Vasicek: `B = (1 - e^{-a tau}) / a`; `ln A = (B - tau)(a^2 b - sigma^2/2) / a^2 - sigma^2 B^2 / (4a)` [BM 3.10].
- CIR: `gamma = sqrt(a^2 + 2 sigma^2)`, `den = (gamma + a)(e^{gamma tau} - 1) + 2 gamma`; `B = 2 (e^{gamma tau} - 1) / den`; `ln A = (2 a b / sigma^2) ln(2 gamma e^{(a + gamma) tau / 2} / den)` [BM 3.25].
- Hull-White: `B = (1 - e^{-a tau}) / a`; `ln A = ln(P(0,T) / P(0,t)) + B f(0,t) - sigma^2/(4a) (1 - e^{-2 a t}) B^2` [BM 3.39].

Small `a` (ruling G-2): `B` and `(B - tau)/a^2` lose all their digits to cancellation when `a tau` is small (at `a = 1e-4`, `tau = 5` a direct double evaluation of Vasicek's `ln A` is off by 1e-9 relative; QuantLib 1.44 shows exactly this, and the case is not counted as outside). Evaluate `B` with `expm1` and use the series `(B - tau) = -a tau^2/2 + a^2 tau^3/6 - ...` (or an equivalent exact rearrangement) when `a tau < 1e-2`.

## `rates.shortrate.zcb_option`

European option at `T` on a zero-coupon bond maturing at `S` (`0 < T < S`, else `E_DOMAIN`), strike `K` (> 0, else `E_DOMAIN`) per unit face, scaled by `notional`.

Inputs: `model` and parameters as above; `short_rate` (`r(0)`) required for `VASICEK` and `CIR`, and **not allowed** for `HULL_WHITE` (`E_INPUT`; the curve fixes the start, ruling G-5); `option_type` (`CALL`, `PUT`; else `E_INPUT`), `strike`, `expiry_years` `T`, `maturity_years` `S`, `notional`.

Outputs: `price`, `bond_price_expiry` `P(0,T)`, `bond_price_maturity` `P(0,S)`.

- Vasicek and Hull-White [J89, BM 3.10 and 3.41]: `sigma_p = (sigma / a)(1 - e^{-a(S - T)}) sqrt((1 - e^{-2aT}) / (2a))`, `h = ln(P(0,S) / (K P(0,T))) / sigma_p + sigma_p / 2`; call `= P(0,S) N(h) - K P(0,T) N(h - sigma_p)`; put by parity, `call - P(0,S) + K P(0,T)`. `P(0, .)` is the model bond price (Vasicek) or the curve (Hull-White).
- CIR [BM 3.26]: with `rho = 2 gamma / (sigma^2 (e^{gamma T} - 1))`, `psi = (a + gamma) / sigma^2`, `rbar = ln(A(T,S)/K) / B(T,S)`, `k = 4ab/sigma^2`, and `chi2(x; k, lambda)` the noncentral chi-square CDF: call `= P(0,S) chi2(2 rbar (rho + psi + B); k, 2 rho^2 r e^{gamma T} / (rho + psi + B)) - K P(0,T) chi2(2 rbar (rho + psi); k, 2 rho^2 r e^{gamma T} / (rho + psi))`; put by parity. `A`, `B` are the CIR factors at `tau = S - T`.

## `rates.shortrate.swaption` (stage G wave 2a)

European swaption on Hull-White by Jamshidian's decomposition [J89; BM 3.11]. Suite `stage_g/swaption_g` (40 cases), generator slice `G2A`. Rulings G-12, G-13.

Inputs: `curve`, `mean_reversion`, `sigma` (Hull-White, as above; no `short_rate`, `E_INPUT` if present), `expiry_years` `T0` (> 0, else `E_DOMAIN`), `payment_times` `T1 < ... < Tn` (at least one, strictly increasing, `T1 > T0`; else `E_INPUT`), `fixed_rate` `K` (any sign), `swaption_type` (`PAYER`, `RECEIVER`; else `E_INPUT`), `notional`.

Conventions (ruling G-12): single curve; the fixed accruals are the time differences `tau_1 = T1 - T0`, `tau_i = Ti - T(i-1)` (ACT/365F year fractions, so a caller's dates fix them); the floating leg is worth `P(T0, T0) - P(T0, Tn)` at expiry (a par floater on the same curve). A payer swaption pays fixed.

Outputs: `price`; `forward_swap_rate` `F = (P(0,T0) - P(0,Tn)) / sum tau_i P(0,Ti)`; `annuity` `notional x sum tau_i P(0,Ti)`.

Method: coupons `c_i = K tau_i`, plus 1 on the last. Find `r*` with `sum c_i P(T0, Ti; r*) = 1` (the Hull-White bond formula above; the sum is strictly decreasing in `r`, so the root is unique; solve to 1e-15 relative in the sum). With `X_i = P(T0, Ti; r*)`: receiver `= notional x sum c_i ZBC(0, T0, Ti, X_i)`, payer `= notional x sum c_i ZBP(0, T0, Ti, X_i)`, with `ZBC`, `ZBP` the Hull-White bond options above. The root solve is internal; `r*` is not an output (ruling G-13).

Errors in order (after F-2): `short_rate` present `E_INPUT`; `a`, `sigma`, curve as `zcb`; `expiry_years <= 0` `E_DOMAIN`; `payment_times` rules `E_INPUT`; `swaption_type` `E_INPUT`. `E_LIMIT`: 10,000 payment times.

Validation: 33 value cases (expiries 0.5 to 10 years, 2 to 20 annual periods, strikes at the forward and 100 bp either side, both types, a semi-annual swap, high mean reversion `a = 0.5`, a zero strike on the negative-rate curve) and 7 error cases. Values: 50-digit mpmath, `r*` to 1e-45. Payer minus receiver equals `annuity (F - K)` to 1e-8 on every pair (asserted). Outside: QuantLib 1.44 `HullWhite` `discountBond` and `discountBondOption`, `r*` by QuantLib's `Brent` to 1e-15, combined by arithmetic, and `DiscountCurve` discounts: 33 of 40 count. `JamshidianSwaptionEngine` itself agrees only to about 3e-7 relative (its internal root accuracy), so the engine is not the counted check. Wrong conventions caught: Ho-Lee `sigma_p`; strike 1 on every bond option.

### Stage G wave 2f: `model` on `rates.shortrate.swaption` (Vasicek and CIR)

Suite `stage_g/swaption_affine_g` (39 cases), generator slice `G2F`. Ruling G-20.

New optional input `model` (`VASICEK`, `CIR`, `HULL_WHITE`; absent means `HULL_WHITE`, so wave 2a cases keep their meaning; another value `E_INPUT`). With `VASICEK` or `CIR` the inputs are those of `rates.shortrate.zcb_option` for that model (`mean_reversion`, `long_term_mean`, `sigma`, `short_rate` required, else `E_SCHEMA`), and no `curve`. The method is unchanged: `r*` solves `sum c_i P(T0, Ti; r*) = 1` with the model's bond formula at `tau = Ti - T0`, then the sum of the model's bond options at strikes `X_i = P(T0, Ti; r*)`. `forward_swap_rate` and `annuity` use the model's bond prices `P(0, t)` at `short_rate`.

CIR needs `r* >= 0` (the bond formula is for `r >= 0`): if `sum c_i P(T0, Ti; 0) < 1` there is no such root, and the case is `E_DOMAIN`.

Validation: two models x three expiry and tenor pairs x strikes at the forward and 100 bp either side x payer and receiver (36 cases); 3 error cases. Asserted: payer minus receiver equals `annuity (F - K)`. Outside: QuantLib 1.44 `Vasicek` and `CoxIngersollRoss` objects by the G-13 method: 36 of 39 count.

## `rates.shortrate.hw_calibrate` (stage G wave 2c)

Hull-White `sigma` fitted to a strip of European swaption prices with `a` fixed. Suite `stage_g/hwcal_g` (6 cases), generator slice `G2C`. Ruling G-17.

Inputs: `curve`, `mean_reversion` (> 0), `swaptions`: at least one (else `E_INPUT`), each `{expiry_years, payment_times, fixed_rate, swaption_type, target_price}` with the rules of `rates.shortrate.swaption` and `target_price` >= 0 per unit notional (else `E_DOMAIN`).

Objective: `F(sigma) = sum_i (model_i(sigma) - target_i)^2`, unweighted, `model_i` the Jamshidian price per unit notional. Output `sigma` = the minimiser of `F` on `[1e-4, 1]`, `fitted_prices` (model prices at `sigma`, in input order), `rmse` = `sqrt(F(sigma) / n)`. If the minimum on that interval is at an end, `E_NO_CONVERGENCE`.

Method: any solver that reaches `F'(sigma) = 0` to a relative step below 1e-12 (for example a bracketing scan, then Newton or Brent on `F'` with `model'` analytic or by central differences of the closed form). The goldens assert a unique interior minimum by a scan on `[0.001, 0.04]`, so the answer does not depend on the solver.

Validation: three ten-year co-terminal strips (expiries 1, 2, 3, 5, 7 years, strikes at the forward), targets from a known `sigma` with stated percentage perturbations (`a = 0.05`, payers; `a = 0.2`, receivers; `a = 0.01`, unperturbed, an exact fit recovering `sigma = 0.007`); 3 error cases. Values: 30-digit mpmath, `F'` root. Outside: none counted (ruling G-17); QuantLib 1.44 `HullWhite` objects reprice every fitted price at the golden `sigma` to 1e-10 relative (evidence).

## `rates.shortrate.bermudan_swaption` (stage G wave 2d)

Bermudan swaption on Hull-White by a pinned reference scheme (ruling G-18), as `exotic.american.fd` pins its scheme (E-A23). Suite `stage_g/bermudan_g` (15 cases), generator `oracle/python/gen_stage_g_berm.py`.

Inputs: `curve`, `mean_reversion`, `sigma` (Hull-White); the underlying swap `start_years` `T0` (> 0), `payment_times` (the `rates.shortrate.swaption` rules, first payment after `T0`), `fixed_rate`, `swaption_type` (`PAYER`, `RECEIVER`), `notional`; `exercise_times`: at least one, strictly increasing, each one of `T0, T1, ..., T(n-1)` (a reset date before the last payment), else `E_INPUT`; `grid` `{nx, steps_per_year, width}`: `nx` odd and at least 5 (else `E_INPUT`), at most 10,001 (`E_LIMIT`); `steps_per_year` at least 1 (else `E_INPUT`), at most 100,000 (`E_LIMIT`); `width` > 0 (else `E_DOMAIN`). Exercising at `t` enters the swap paying from `t` to `Tn` (fixed periods after `t`).

**Reference scheme.**
1. State `x = r - alpha(t)`, `alpha(t) = f(0,t) + sigma^2/(2a^2) (1 - e^{-at})^2`, `f` the curve's right-hand forward (G-3); `dx = -a x dt + sigma dW`, `x(0) = 0`.
2. Space grid: `sx = sigma sqrt((1 - e^{-2a t_m}) / (2a))` with `t_m` the last exercise time; `h = width sx`; `x_i = -h + i dx`, `dx = 2h/(nx - 1)`, `i = 0..nx-1` (the centre node is `x = 0`).
3. Time grid: knots `0, t_1, ..., t_m` (the exercise times). Interval `[t_(k-1), t_k]` gets `n = max(1, ceil(steps_per_year (t_k - t_(k-1))))` equal steps.
4. Exercise value at `t` and node `i` (per unit notional): `phi (1 - P(t, Tn) - K sum tau_j P(t, Tj))` over the payments after `t`, `tau` the time differences starting at `t`, `P(t, T)` the Hull-White bond of `rates.shortrate.zcb` with `r = x_i + alpha(t)`, `phi = +1` payer, `-1` receiver.
5. Start at `t_m` with `V = max(exercise, 0)`. Step backward fully implicitly: from `t + dt` to `t`, solve `(I - dt L(t)) V(t) = V(t + dt)` on interior nodes `1..nx-2`, where `(L V)_i = (sigma^2/2)(V_(i+1) - 2V_i + V_(i-1))/dx^2 - a x_i (V_(i+1) - V_(i-1))/(2 dx) - (x_i + alpha(t)) V_i`, coefficients at the earlier time `t`. Boundaries: `V_0 = 2V_1 - V_2` and `V_(nx-1) = 2V_(nx-2) - V_(nx-3)`, substituted into the first and last interior rows (the system stays tridiagonal), then set after the solve.
6. On arriving at an exercise time `t_k` (`k < m`), `V = max(V, exercise(t_k))`. Do not apply exercise at `t = 0`.
7. `price = notional x V` at the centre node at `t = 0`.

Output: `price`. Class `root_finding` with a limit of 1e-9 relative: the scheme is deterministic, so builds differ only by rounding in the tridiagonal solve.

## Convergence and limit cases (Bermudan scheme)

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Fully implicit FD on the Hull-White state | 1 in time (space second order, refined together) | `nx = 51, 101, 201, 401` with `steps_per_year = 25, 50, 100, 200`, width 6, one exercise date at 1y into a 5y payer at 4%: errors against Jamshidian -149.7, -52.2, -23.9, -12.9 on 1e6 notional; observed orders 1.52, 1.13, 0.89 (the last two within 0.2 of 1) | one exercise date: the European swaption (`swaption_g`, Jamshidian) | Jamshidian closed form; QuantLib 1.44 `FdHullWhiteSwaptionEngine` (400 x 400) and `TreeSwaptionEngine` (400 steps) |

At the default grid (201 nodes, 100 steps a year) the scheme sits about 0.1% to 0.2% below QuantLib's FD and tree engines on the ten value cases (`oracle/BERMUDAN_EVIDENCE_G.json`). That is the first-order time bias of the reference scheme; it is a pinned reference, not the most accurate engine. On the coarse pinned grid (51 nodes, 12 steps a year) it is about 1.2% below. No case counts as outside (G-18).

Validation: payer and receiver at the forward and 50 bp either side, annual exercise into a 1-into-5-year swap (6 cases); the European limit; two exercise dates; high mean reversion; a coarse pinned grid; 5 error cases.

## `rates.shortrate.capfloor` (stage G wave 2e)

Caps and floors under Vasicek, CIR and Hull-White as portfolios of bond options [BM 2.6 and 3.3.2]. Suite `stage_g/capfloor_g` (41 cases), generator slice `G2E`. Ruling G-19.

Inputs: `model` and its parameters as `rates.shortrate.zcb_option` (including the `short_rate` rule G-5); `period_times` `t_0 < t_1 < ... < t_m` (at least two, strictly increasing, else `E_INPUT`; `t_0 > 0`, else `E_DOMAIN`); `strike` `K` (simple rate; `1 + K tau_i > 0` for every period, else `E_DOMAIN`); `cap_floor` (`CAP`, `FLOOR`; else `E_INPUT`); `notional`.

Each period `[t_(i-1), t_i]`, `tau_i = t_i - t_(i-1)`, pays `notional tau_i max(L_i - K, 0)` (cap) or `max(K - L_i, 0)` (floor) at `t_i`, where `L_i` is the simple model rate fixed at `t_(i-1)`: `1 + tau_i L_i = 1 / P(t_(i-1), t_i)` (single curve, ruling G-19). Then caplet `= notional (1 + K tau_i) ZBP(0, t_(i-1), t_i, 1/(1 + K tau_i))` and floorlet `= notional (1 + K tau_i) ZBC(...)` with the bond options of `zcb_option`.

Outputs: `price` (the sum) and `caplet_prices` (per period, in order; floorlets for a floor).

Validation: three models x two schedules (semi-annual to 5 years, annual to 7 years) x cap and floor x strikes 3%, 4%, 5% (36 cases), 5 error cases. Values: 50-digit mpmath (CIR through the noncentral chi-square). Asserted: cap minus floor equals `notional sum (P(t_(i-1)) - (1 + K tau_i) P(t_i))` on all 18 pairs. Outside: QuantLib 1.44 `Vasicek`, `CoxIngersollRoss`, `HullWhite` `discountBondOption` per period, scaled and summed: 36 of 41 count. Wrong convention caught: a cap priced with bond calls.

## G2++: `rates.g2pp.zcb`, `rates.g2pp.zcb_option` (stage G wave 2b)

Two-factor Gaussian model [BM 4.2, eqs. 4.10, 4.14 and 4.31] (not opened; checked against QuantLib 1.44 `G2`). Suite `stage_g/g2pp_g` (38 cases), generator slice `G2B`. Ruling G-14.

`r(t) = x(t) + y(t) + phi(t)`, `dx = -a x dt + sigma dW1`, `dy = -b y dt + eta dW2`, `dW1 dW2 = rho dt`, `x(0) = y(0) = 0`, `phi` fitted to the curve (the Hull-White `curve` input and rules).

Inputs: `curve`, `a`, `sigma`, `b`, `eta` (all > 0, else `E_DOMAIN`; `a = b` is allowed), `rho` (strictly inside `(-1, 1)`, else `E_DOMAIN`).
- `rates.g2pp.zcb`: plus `x`, `y` (the factor values at `t`), `t_years` (>= 0), `maturity_years` (> `t_years`). Outputs `discount_factor`, `zero_rate` as `rates.shortrate.zcb`.
- `rates.g2pp.zcb_option`: plus `option_type`, `strike`, `expiry_years`, `maturity_years`, `notional` as `rates.shortrate.zcb_option`; `x` or `y` present is `E_INPUT` (both start at 0). Outputs `price`, `bond_price_expiry`, `bond_price_maturity`.

With `tau = T - t`:
`V(tau) = sigma^2/a^2 (tau + (2/a) e^{-a tau} - (1/(2a)) e^{-2 a tau} - 3/(2a)) + eta^2/b^2 (same in b) + (2 rho sigma eta / (a b)) (tau + (e^{-a tau} - 1)/a + (e^{-b tau} - 1)/b - (e^{-(a+b) tau} - 1)/(a + b))`;
`P(t, T) = (P(0,T) / P(0,t)) exp(0.5 (V(T - t) - V(T) + V(t)) - ((1 - e^{-a tau})/a) x - ((1 - e^{-b tau})/b) y)`.

Bond option at `T` on the bond to `S`: `Sigma^2 = sigma^2/(2a^3) (1 - e^{-a(S-T)})^2 (1 - e^{-2aT}) + eta^2/(2b^3) (1 - e^{-b(S-T)})^2 (1 - e^{-2bT}) + (2 rho sigma eta / (a b (a+b))) (1 - e^{-a(S-T)})(1 - e^{-b(S-T)})(1 - e^{-(a+b)T})`, then the Gaussian bond-option formula of `zcb_option` with `sigma_p = Sigma` and the curve's `P(0,T)`, `P(0,S)`.

Small `a` or `b`: the cancellations of ruling G-2 apply to each factor; use the same series.

Validation: three parameter sets (negative, positive and zero `rho`; fast and slow factors in both orders), 12 bond prices (`t = 0` and `t > 0` with non-zero states, a 30-year bond, a 0.01-year bond) and 18 options; a one-factor limit case (`eta = 1e-12`, equal to the Hull-White price, asserted); 7 error cases. Outside: QuantLib 1.44 `G2` `discountBond` (with the factor array) and `discountBondOption`: 30 of 38 count. Wrong conventions caught: the variance terms without the 1/2; the cross term with the wrong sign.

## Error checks for `zcb` and `zcb_option`, in order (after F-2)

`model` unknown `E_INPUT`; `a <= 0` or `sigma <= 0` `E_DOMAIN`; `CIR` with `b <= 0` or `r < 0` `E_DOMAIN`; `curve` rules (above); `short_rate` presence rule (G-5) `E_INPUT`, absence where required `E_SCHEMA`; `t_years < 0`, `maturity_years <= t_years`, `expiry_years <= 0`, `maturity_years <= expiry_years`, `strike <= 0` `E_DOMAIN`; `option_type` `E_INPUT`. `E_LIMIT`: curve pillars 10,000 (ruling G-6).

## Validation cases and oracle

`shortrate_g`, 78 cases: 38 bond prices (three models, positive, zero and negative short rates, `t > 0`, a 30-year bond, a 0.01-year bond, `a = 1e-4`, a pillar-time `t`, a negative-rate Hull-White curve), 25 options (three models, call and put, four expiry and maturity pairs, a 0.5 into 20-year option, an at-par option on a negative-rate curve) and 15 error cases. Values: 50-digit mpmath replicas; the noncentral chi-square by its Poisson series to 1e-45. Outside (rule 11.2.5): QuantLib 1.44 `Vasicek`, `CoxIngersollRoss`, `HullWhite` `discountBond` and `discountBondOption`; 61 of 78 cases count (78.2%). Not counted: the small-`a` case (QuantLib's cancellation, G-2), the pillar-time case (QuantLib's centred numerical forward, G-3) and the 15 error cases. Register: `oracle/outside_register_g.json`.

Wrong conventions the goldens catch (asserted in the generator): Vasicek without `-sigma^2 B^2 / (4a)`; CIR with `gamma = sqrt(a^2 + sigma^2)`; Hull-White without the variance term; Ho-Lee `sigma_p` (`sigma (S - T) sqrt T`) in place of Hull-White's.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Noncentral chi-square CDF by Poisson-weighted central chi-square series | Geometric: terms fall faster than `(lambda/2)^j / j!`; stop when `j > lambda/2 + 10` and the term is below 1e-17 relative | the 25 option cases, terms 10, 20, 40, 80 | `lambda -> 0`: the central chi-square CDF | `mpmath.gammainc` at 50 digits; QuantLib 1.44 `CoxIngersollRoss::discountBondOption` |
| Vasicek and Hull-White closed forms | exact | | `a -> 0`: Ho-Lee, `B = tau` | series of G-2; the small-`a` golden |

## Acceptance

All four languages pass `shortrate_g`. Property tests in each build: put-call parity to 1e-12 per unit face; `HULL_WHITE` `zcb` at `t = 0` returns the curve's `P(0, T)` to 1e-14 relative; for every model `zero_rate -> short_rate` as `T - t -> 0` (checked at `T - t = 1e-6` to 1e-6 absolute).
