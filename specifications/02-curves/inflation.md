# Inflation curves, seasonality and linkers

Spec version 1.0.0. Status: Specified (stage D, D6).

## CPI curve

`curve`: `{base_month, base_cpi, quotes: [{years, rate}], seasonality}`. Months are `YYYY-MM`; month index `k = 12 year + month - 1`. `base_month` already carries the index lag: it is the last published month the swaps reference.

A zero-coupon inflation swap of `n` years (integer) quoting `K` exchanges `I(b + 12n)/I_0 - 1` against `(1 + K)^n - 1` on one date, so its pillar is `I(b + 12n) = I_0 (1 + K)^n` whatever the discount curve.

Smooth curve: `ln I` linear in `k` between `(b, ln I_0)` and the pillars; after the last pillar, the last segment's slope carries on. `seasonality`: `null`, or 12 positive factors `s_1 .. s_12` for January to December. Then `I(k) = I_smooth(k) s(k)/s(b)`. Pillar months fall in the base month's calendar month, so the factors cancel there and every quote reprices.

## `infl.curve.cpi`

Inputs: the curve fields, `months`. Output: `cpi`. Checks, in order: `years` not strictly increasing positive integers: `E_INPUT`. `rate <= -1`: `E_DOMAIN`. `seasonality` not 12 positive numbers: `E_INPUT` (a factor `<= 0`: `E_DOMAIN`). A month before `base_month`: `E_OUT_OF_RANGE`.

## `infl.zcis.pv`

Inputs: `curve`, `discount`, `trade` `{years, fixed_rate, notional, side, payment_date}`. Outputs: `index_ratio = I(b + 12 years)/I_0`, `pv = sign N (index_ratio - (1 + K)^years) D(payment_date)`, +1 for `RECEIVE_INFLATION`.

## Reference CPI

For a date `d` in month `m`: `ref(d) = I(m-3) + (day(d) - 1)/days_in_month(m) (I(m-2) - I(m-3))`. This is the US TIPS rule (three-month lag, daily interpolation).

## `infl.linker.price`

Inputs: `bond` (as `04-pricing/bonds.md`), `settlement`, `real_yield`, `base_ref_cpi`, `cpi_fixings` `[{month, value}]`. Outputs: `ref_cpi` (from the fixings), `index_ratio = ref_cpi/base_ref_cpi`, both rounded as Treasury does (ruling R6-7.5, 31 CFR Part 356 Appendix B, read 2026-11-12 at law.cornell.edu: truncate to six decimals, then round half up to five; the index ratio is formed from the rounded Ref CPI), `real_clean`, `real_accrued` (`bond.price.from_yield` at the real yield), `nominal_clean`, `nominal_accrued` (the real ones times `index_ratio`). A needed fixing missing: `E_INPUT`. No deflation floor in this stage.

## `infl.linker.price_curve`

Inputs: `bond`, `settlement`, `base_ref_cpi`, `curve`, `discount`. Output: `nominal_dirty = sum CF_k ref(d_k)/base_ref_cpi D(d_k) / D(settlement)`, real cash flows as the bond object, `ref` from the CPI curve. A reference month before `base_month`: `E_OUT_OF_RANGE`.

## Acceptance

`simple_analytic` for CPI and linker from yield; `interpolation` for PVs on a discount curve. Hand and exact-rational only: no outside library is run (QuantLib's inflation curves use other lag and interpolation conventions). Suite `stage_d/inflation_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] US Treasury, 31 CFR Part 356, Appendix B (index ratio and reference CPI for TIPS: three-month lag, daily interpolation) (not opened)
- [S2] UK Debt Management Office, *Formulae for calculating gilt prices from yields* (index-linked gilts, 3-month lag) (not opened)
- [S3] Kerkhof, J., *Inflation Derivatives Explained*, Lehman Brothers Fixed Income Quantitative Research, 2005 (zero-coupon inflation swaps, seasonality) (not opened)
- [S4] Brigo, D. and Mercurio, F., *Interest Rate Models: Theory and Practice*, 2nd ed., Springer, 2006, chapter on inflation derivatives (not opened)
