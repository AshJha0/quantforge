# Review request: Repo and special repo (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is filed under a labelled "AI review" section of the curve's evidence checklist and checked against the repository before anything is acted on.

Stage: D. Evidence line from the project's curve table: 4 golden cases.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.

## Spec

### `specifications/04-pricing/bonds.md`

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

Outputs: `bonds` (those four per bond, in input order), `ctd` (0-based index of the highest `implied_repo`). No golden has two implied repos within 1e-6. The stage D basis golden (`repo_d`) has a futures price far from fair, so its implied repos are near -100%; `r6/basis_r6` (ruling R6-7.2) prices the futures at the CTD's fair value less 2/32 for March 2027 delivery, giving implied repos of 0.8% to 3.6% against a 3.85% repo, each re-solved by brentq on the forward identity.

## `bond.fit.nelson_siegel`

Sovereign fit with a fixed `tau`, and relative value. Inputs: `settlement`, `tau`, `bonds` (bond objects plus `dirty_price`), optional `weights` (`>= 0`). Zero rate `z(t)` as `calib.curve.robust`, `t = (d - settlement)/365`; model dirty `sum CF exp(-z(t) t)`. Minimise `sum w (model - dirty_price)^2`. Outputs: `betas`, `residuals` (model minus market, for every bond: a bond with weight 0 shows its richness). Fewer than 3 positive weights: `E_INPUT`. `tau <= 0`: `E_DOMAIN`.

## Acceptance

Price, accrued, durations: `simple_analytic`; QuantLib within 1e-10 (convexity 1e-8 absolute). Yield and Z-spread: `root_finding`, known truth, QuantLib within 1e-10. Curve price, asset swap, FRN: `interpolation`, replay; FRN par identity. Repo and futures basis: `simple_analytic`, analytic; `ctd` and conversion factors exact. Fit: betas within 1e-8 of known truth, reached by SciPy from three starts. Suites `stage_d/bonds_d`, `repo_d`, `bondfit_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] ICMA, *Primary Market Handbook* / Rule 251 (accrued interest calculation, ACT/ACT ICMA) (not opened)
- [S2] UK Debt Management Office, *Formulae for calculating gilt prices from yields* (not opened)
- [S3] CME Group, *Calculating U.S. Treasury Futures Conversion Factors* (conversion-factor formula) and CBOT Treasury futures contract specifications. Basis of ruling R1-3 (whole months for 2Y, 3Y, 5Y; quarters otherwise; coupon to the nearest 1/8; 4 decimals) (not opened)
- [S4] Fabozzi, F. J. (ed.), *The Handbook of Fixed Income Securities*, 8th ed., McGraw-Hill, 2012 (yield, duration, convexity, repo) (not opened)
- [S5] Burghardt, G., Belton, T., Lane, M. and Papa, J., *The Treasury Bond Basis*, 3rd ed., McGraw-Hill, 2005 (gross and net basis, implied repo, CTD) (not opened)
- [S6] O'Kane, D., *Introduction to Asset Swaps*, Lehman Brothers Analytical Research Series, 2000 (par-par asset swap spread) (not opened)
- [S7] Nelson, C. R. and Siegel, A. F., "Parsimonious modeling of yield curves", *Journal of Business* 60(4), 1987, 473-489 (not opened)


## Golden cases (4 of 4 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"repo_d-0005","operation":"repo.forward","inputs":{"bond":{"maturity":"2029-11-15","coupon":0.0425,"frequency":2},"start":"2026-11-09","end":"2026-12-09","clean_price":100.42085974293727,"repo_rate":0.0385,"gc_rate":null},"expected":{"status":"ok","outputs":{"dirty":102.47656626467639,"forward_dirty":100.67489108144223,"forward_clean":100.39312312564113,"interest":0.32877898343250345,"special_spread":null,"specialness_value":null}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
{"case_id":"repo_d-0007","operation":"repo.forward","inputs":{"bond":{"maturity":"2036-08-15","coupon":0.045,"frequency":2},"start":"2026-11-09","end":"2027-02-22","clean_price":103.18692204507627,"repo_rate":0.031,"gc_rate":0.0385},"expected":{"status":"ok","outputs":{"dirty":104.23855247985888,"forward_dirty":102.9296864751976,"forward_clean":102.84266990061197,"interest":0.9424902453387239,"special_spread":0.0075,"specialness_value":0.22802183354969127}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
{"case_id":"repo_d-0009","operation":"repo.forward","inputs":{"bond":{"maturity":"2034-03-31","coupon":0.03,"frequency":1},"start":"2026-11-09","end":"2027-04-09","clean_price":93.09360797648607,"repo_rate":0.0395,"gc_rate":0.0385},"expected":{"status":"ok","outputs":{"dirty":94.92648468881484,"forward_dirty":93.49626946083272,"forward_clean":93.42249896902945,"interest":1.5727472720178781,"special_spread":-0.0010000000000000009,"specialness_value":-0.03981638663336404}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
{"case_id":"repo_d-0011","operation":"repo.forward","inputs":{"bond":{"maturity":"2031-02-28","coupon":0.0375,"frequency":2},"start":"2026-11-09","end":"2027-03-09","clean_price":98.62653398076066,"repo_rate":0.039,"gc_rate":null},"expected":{"status":"ok","outputs":{"dirty":99.35167210230762,"forward_dirty":98.7664157146376,"forward_clean":98.67470375811587,"interest":1.291571737329999,"special_spread":null,"specialness_value":null}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
```

## Outside-library evidence and limits (from the project's own page)

4 golden cases with status ok in `datasets/golden/stage_d` for `repo.forward`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| repo.forward: analytic | 4 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free general or special repo rates by term. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

None found by operation name.
