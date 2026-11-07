# Bonds, repo and bond futures

Spec version 1.0.0. Status: Specified (stage D, D2).

## Bond object

`bond`: `{maturity, coupon, frequency}`, `frequency` in `1, 2, 4` (else `E_SCHEMA`), face 100, redeemed at 100. Coupon dates step back from `maturity` by `12/frequency` months, unadjusted, with no business-day rule (ruling D13). If `maturity` is the last day of its month, every coupon date is the last day of its month. Every period is regular: there is no odd first coupon. Coupon amount `c = 100 coupon / frequency`.

For `settlement`: `prev <= settlement < next` are the coupon dates around it; the cash flows are every coupon date after `settlement`, the last plus 100. `accrued = c (settlement - prev)/(next - prev)` in days (ACT/ACT ICMA). `w = (next - settlement)/(next - prev)`.

Common checks: `settlement >= maturity`: `E_DATE_ORDER`.

## `bond.price.from_yield`

Inputs: `bond`, `settlement`, `yield` `y` (compounded at `frequency` `f`). With `v = 1/(1 + y/f)` and cash flow `k = 0, 1, ...` at exponent `k + w`:

`dirty = sum CF_k v^(k+w)`, `clean = dirty - accrued`,
`macaulay_duration = sum ((k+w)/f) CF_k v^(k+w) / dirty`, `modified_duration = macaulay_duration * v`,
`convexity = sum ((k+w)(k+w+1)/f^2) CF_k v^(k+w+2) / dirty`.

Outputs: `dirty`, `accrued`, `clean`, `modified_duration`, `macaulay_duration`, `convexity`. `1 + y/f <= 0`: `E_DOMAIN`. This is QuantLib's `BondFunctions` with ACT/ACT ICMA and `Compounded`.

## `bond.yield.from_price`

Inputs: `bond`, `settlement`, `clean_price`. Outputs: `yield`, `dirty`, `accrued`. The `yield` with `from_yield` clean equal to `clean_price`; price is strictly decreasing in `y`, so it is unique. `clean_price <= 0` or `clean_price + accrued <= 0`: `E_DOMAIN` (ruling D43).

## `bond.price.from_curve`, `bond.spread.z`

`Ds(d) = D(d) exp(-z t(d))`, `t(d) = (d - as_of)/365`, `D` the curve. `dirty = sum CF_k Ds(d_k) / Ds(settlement)`: valued at the curve's `as_of` and carried to `settlement`.

`bond.price.from_curve`: inputs `bond`, `settlement`, `curve`; `z = 0`. Outputs `dirty`, `accrued`, `clean`.

`bond.spread.z`: inputs `bond`, `settlement`, `curve`, `clean_price`. Output `z_spread`: the `z` that gives `clean_price + accrued`. Unique, as dirty falls in `z`. QuantLib `BondFunctions.zSpread` with `Continuous` and ACT/365F is the same thing.

`settlement` before the curve's `as_of`: `E_OUT_OF_RANGE`.

## `bond.spread.asset_swap`

Par-par asset swap spread, and the bond-OIS spread when `curve` is an OIS curve. Inputs: `bond`, `settlement`, `curve`, `dirty_price`. Floating dates step back quarterly from `maturity`, unadjusted; the first period runs from `settlement`. `annuity = sum ((e_j - s_j)/360) D(e_j) / D(settlement)`. Outputs: `annuity`, `spread = (P_curve - dirty_price) / (100 annuity)`, with `P_curve` the `from_curve` dirty price. The annuity is the floating leg's, not the bond's fixed leg.

## `bond.frn.price`

A floating-rate note on a term rate. Inputs: `settlement`, `maturity`, `frequency`, `current_rate` (the fixed rate of the period holding `settlement`), `margin`, `discount_margin` `dm`, `discount`, `projection`. Dates as the bond object; accrual `alpha = days/360`. Later periods pay `(P(s)/P(e) - 1)/alpha + margin`. With `Dm(d) = D(d) exp(-dm t(d))`:

`dirty = [sum 100 (r_i + margin) alpha_i Dm(e_i) + 100 Dm(T)] / Dm(settlement)`, `accrued = 100 (current_rate + margin)(settlement - prev)/360`, `clean = dirty - accrued`.

On a coupon date, at `margin = dm = 0`, with one curve and `current_rate` its forward, `dirty = 100`.

## `repo.forward`, `repo.implied_rate`

Inputs: `bond`, `start`, `end`, `clean_price`, `repo_rate` `r` (ACT/360, simple), `gc_rate` (a number, or `null`; the key is required). `dirty` is the clean price plus accrued at `start`. Coupons with dates in `(start, end]` are paid to the seller and reinvested at `r`:

`forward_dirty = dirty (1 + r (end-start)/360) - sum c (1 + r (end-d)/360)`, `forward_clean = forward_dirty - accrued(end)`, `interest = dirty r (end-start)/360`.

Special repo: `special_spread = gc_rate - r`, `specialness_value = dirty (gc_rate - r)(end-start)/360`; both `null` when `gc_rate` is `null`.

`repo.implied_rate`: inputs as above less the rates, plus `forward_clean`; output `repo_rate`, the `r` that gives it (linear in `r`, closed form).

Checks: `end <= start`: `E_DATE_ORDER`. `end >= maturity`: `E_INPUT`.

## `bond.futures.conversion_factor`

CME Treasury futures formula, on a 6% notional coupon (`notional_coupon` must be 0.06, else `E_INPUT`). Optional input `contract` (ruling R1-3): `TWO_YEAR`, `THREE_YEAR`, `FIVE_YEAR`, `TEN_YEAR`, `ULTRA_TEN_YEAR`, `BOND`, `ULTRA_BOND`, or `null`, which means `TEN_YEAR` (the stage D behaviour); another string is `E_SCHEMA`. First the coupon is rounded to the nearest 1/8 of 1%, ties up: `c = floor(coupon x 800 + 0.5)/800`. From the first day of `delivery_month` (`YYYY-MM`) to `maturity`: `n` whole years and `z` whole months. For `TEN_YEAR`, `ULTRA_TEN_YEAR`, `BOND` and `ULTRA_BOND`, `z` is then rounded down to a multiple of 3; for `TWO_YEAR`, `THREE_YEAR` and `FIVE_YEAR` it stays whole months. `v = z` if `z < 7` else `z - 6`. `a = 1.03^(-v/6)`, `b = (c/2)(6-v)/6`, `C = 1.03^(-2n)` if `z < 7` else `1.03^(-2n-1)`. `CF = a (c/2 + (c/0.06)(1 - C) + C) - b`, rounded to 4 decimals, as CME states. CME gives no tie rule; no golden lies within 1e-6 of a rounding boundary, so none is tested. Semi-annual bonds only (`E_INPUT` otherwise). Deliverable-basket eligibility is not checked.

## `bond.futures.basis`

Inputs: `futures_price` `F`, `settlement`, `delivery`, `repo_rate` `r`, `bonds` (bond objects plus `clean_price` and `conversion_factor`). For each bond, with `T = (delivery - settlement)/360` and coupons `c` at dates `d` in `(settlement, delivery]`:

`invoice = F CF + accrued(delivery)`, `gross_basis = clean - F CF`, `net_basis = forward_dirty - invoice` (`repo.forward` at `r`), `implied_repo = (invoice + sum c - dirty) / (dirty T - sum c (delivery - d)/360)`.

Outputs: `bonds` (those four per bond, in input order), `ctd` (0-based index of the highest `implied_repo`). No golden has two implied repos within 1e-6.

## `bond.fit.nelson_siegel`

Sovereign fit with a fixed `tau`, and relative value. Inputs: `settlement`, `tau`, `bonds` (bond objects plus `dirty_price`), optional `weights` (`>= 0`). Zero rate `z(t)` as `calib.curve.robust`, `t = (d - settlement)/365`; model dirty `sum CF exp(-z(t) t)`. Minimise `sum w (model - dirty_price)^2`. Outputs: `betas`, `residuals` (model minus market, for every bond: a bond with weight 0 shows its richness). Fewer than 3 positive weights: `E_INPUT`. `tau <= 0`: `E_DOMAIN`.

## Acceptance

Price, accrued, durations: `simple_analytic`; QuantLib within 1e-10 (convexity 1e-8 absolute). Yield and Z-spread: `root_finding`, known truth, QuantLib within 1e-10. Curve price, asset swap, FRN: `interpolation`, replay; FRN par identity. Repo and futures basis: `simple_analytic`, analytic; `ctd` and conversion factors exact. Fit: betas within 1e-8 of known truth, reached by SciPy from three starts. Suites `stage_d/bonds_d`, `repo_d`, `bondfit_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] ICMA, *Primary Market Handbook* / Rule 251 (accrued interest calculation, ACT/ACT ICMA) (not opened)
- [S2] UK Debt Management Office, *Formulae for calculating gilt prices from yields* (not opened)
- [S3] CME Group, *Calculating U.S. Treasury Futures Conversion Factors* (conversion-factor formula) and CBOT Treasury futures contract specifications (not opened)
- [S4] Fabozzi, F. J. (ed.), *The Handbook of Fixed Income Securities*, 8th ed., McGraw-Hill, 2012 (yield, duration, convexity, repo) (not opened)
- [S5] Burghardt, G., Belton, T., Lane, M. and Papa, J., *The Treasury Bond Basis*, 3rd ed., McGraw-Hill, 2005 (gross and net basis, implied repo, CTD) (not opened)
- [S6] O'Kane, D., *Introduction to Asset Swaps*, Lehman Brothers Analytical Research Series, 2000 (par-par asset swap spread) (not opened)
- [S7] Nelson, C. R. and Siegel, A. F., "Parsimonious modeling of yield curves", *Journal of Business* 60(4), 1987, 473-489 (not opened)
