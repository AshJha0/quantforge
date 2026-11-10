# Exposure and CVA of a swap under Hull-White (closed form)

Spec version 1.0.0. Status: Specified (stage G, wave 4a, the first xVA slice). Rulings: `stage-g-rulings.md` G-16. Suite `stage_g/exposure_g` (15 cases), written by `oracle/python/gen_stage_g_w1.py` (slice `G5A`).

**Plain idea.** If a counterparty defaults at time `t`, the bank loses what the trade was worth to it then, if positive. The expected positive value, discounted to today, is the discounted expected exposure (EE). For a swap under Hull-White, at a date when the floating rate has just been reset, the positive part of the remaining swap is exactly a European swaption on it, so the EE has a closed form (Jamshidian, `04-pricing/short-rate-models.md`). Credit valuation adjustment (CVA) then weights the EE by the chance of default in each period. This page is the exact anchor for the simulated exposure engine of the next xVA wave and for the ORE comparison of the stage demo: a simulation must reproduce these numbers within its Monte Carlo error.

Sources:
- [BM] D. Brigo, F. Mercurio, *Interest Rate Models: Theory and Practice*, 2nd ed., Springer, 2006, section 21.3 (CVA of an interest-rate swap as a sum of swaptions, under independence of default and rates) (not opened in this session).
- [G15] J. Gregory, *The xVA Challenge*, 3rd ed., Wiley, 2015, chapters 7 (exposure: EE, EPE, PFE) and 14 (CVA formula with discrete default buckets) (not opened).
- The exposure values are checked against QuantLib 1.44's own `HullWhite` objects, as `swaption_g` (ruling G-13).

## `xva.exposure.swap_ee_hw`

### Inputs

- Model: `curve`, `mean_reversion`, `sigma` (Hull-White, as `short-rate-models.md`).
- Swap: `start_years` `T0` (>= 0), `payment_times` `T1 < ... < Tn` (`T1 > T0`, else `E_INPUT`), `fixed_rate` `K`, `side` (`PAY` pays fixed, `RECEIVE` receives fixed; else `E_INPUT`), `notional`. Conventions of `rates.shortrate.swaption` (ruling G-12): single curve, accruals from the times, floating leg a par floater at each reset.
- `exposure_times`: at least one, each > 0 (else `E_DOMAIN`), strictly increasing (else `E_INPUT`), and each one a reset date before the last payment, that is one of `T0, T1, ..., T(n-1)` (else `E_INPUT`; ruling G-16). Times are compared exactly as binary64 numbers.
- Optional credit: `hazard_rate` `lambda` (>= 0, else `E_DOMAIN`) and `recovery` `R` (in `[0, 1)`, else `E_DOMAIN`), both or neither (else `E_INPUT`).

### Outputs

- `discounted_ee`: one value per exposure time. At reset date `t = T_k`, the remaining swap pays at `T(k+1), ..., Tn` (from `t` when `t = T0`). `discounted_ee(t) = E[D(0,t) max(V(t), 0)]` = the price today of the European swaption expiring at `t` on the remaining swap: payer for `PAY`, receiver for `RECEIVE`, by `rates.shortrate.swaption` with the same model, `K` and notional.
- `cva` (only with credit inputs): `(1 - R) sum_k discounted_ee(t_k) (S(t_(k-1)) - S(t_k))`, `S(t) = exp(-lambda t)`, `t_0 = 0`. Default in `(t_(k-1), t_k]` takes the exposure at `t_k` (ruling G-16). Default and rates are independent (no wrong-way risk in this slice).

### Error checks, in order (after F-2)

Model checks as `rates.shortrate.swaption`; `side` `E_INPUT`; `payment_times` `E_INPUT`; `exposure_times` values `E_DOMAIN`, then order and reset-date rules `E_INPUT`; credit pair `E_INPUT`, then values `E_DOMAIN`. `E_LIMIT`: 10,000 payment times and 10,000 exposure times.

## Validation cases and oracle

`exposure_g`: four five-year spot-start swaps (pay and receive, at 3% and 4.5%) on four annual reset dates with CVA; a ten-year semi-annual pay-fixed swap on 19 reset dates with CVA; a forward-start receiver (2 into 5 years) with no credit; a high mean-reversion case with a 5% hazard; 8 error cases. Values: 50-digit Jamshidian (as `swaption_g`). Asserted: `PAY` minus `RECEIVE` EE at each date equals the deterministic forward value of the remaining swap, to 1e-6 on 1e7 notional. Outside: every EE point by QuantLib 1.44 `HullWhite` objects (G-13 method), and `cva` as arithmetic on them: 7 of 15 count (every value case). Wrong convention caught: a receiver swaption for a pay-fixed swap.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Jamshidian critical-rate solve (inside each EE point) | quadratic (Newton) to 1e-15 relative in the bond sum | the 7 value cases | `sigma -> 0`: `discounted_ee(t) = max(forward value of the remaining swap, 0)` | the deterministic forward value; QuantLib 1.44 `HullWhite` |

## Acceptance

All four languages pass `exposure_g`. Property test: `PAY` minus `RECEIVE` EE equals the forward value of the remaining swap at every date. The next xVA wave (simulated exposure, collateral, netting) must reproduce these EE points within 3 Monte Carlo standard errors at the same dates.
