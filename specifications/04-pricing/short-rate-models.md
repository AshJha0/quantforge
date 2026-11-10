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
