# Review request: Inflation, with seasonality (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is filed under a labelled "AI review" section of the curve's evidence checklist and checked against the repository before anything is acted on.

Stage: D. Evidence line from the project's curve table: 2 golden cases.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. Decide whether a CPI-index-only check (published index against the curve's base fixing) is worth adding.

## Spec

### `specifications/02-curves/inflation.md`

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


## Golden cases (2 of 2 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"inflation_d-0001","operation":"infl.curve.cpi","inputs":{"base_month":"2026-08","base_cpi":322.15,"quotes":[{"years":1,"rate":0.0265},{"years":2,"rate":0.0255},{"years":3,"rate":0.025},{"years":5,"rate":0.0245},{"years":7,"rate":0.0245},{"years":10,"rate":0.025},{"years":20,"rate":0.0255}],"seasonality":null,"months":["2026-08","2026-12","2027-01","2027-08","2028-03","2031-08","2036-11","2048-02"]},"expected":{"status":"ok","outputs":{"cpi":[322.1499999999999,324.97088533868157,325.6799577718831,330.686975,335.38938143637296,363.59503935374437,415.03398050181625,553.9781374577557]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
{"case_id":"inflation_d-0002","operation":"infl.curve.cpi","inputs":{"base_month":"2026-08","base_cpi":322.15,"quotes":[{"years":1,"rate":0.0265},{"years":2,"rate":0.0255},{"years":3,"rate":0.025},{"years":5,"rate":0.0245},{"years":7,"rate":0.0245},{"years":10,"rate":0.025},{"years":20,"rate":0.0255}],"seasonality":[0.9978,0.9992,1.0011,1.0018,1.0012,1.0005,0.9989,0.9994,1.0006,1.0003,0.9995,0.9997],"months":["2026-08","2026-12","2027-01","2027-08","2028-03","2031-08","2036-11","2048-02"]},"expected":{"status":"ok","outputs":{"cpi":[322.1499999999999,325.0684351341605,325.15855699898435,330.686975,335.95988568736544,363.59503935374437,415.07550881685546,553.8672753129773]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
```

## Outside-library evidence and limits (from the project's own page)

2 golden cases with status ok in `datasets/golden/stage_d` for `infl.curve.cpi`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| infl.curve.cpi: analytic | 2 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- Not run in this pack. Free data exists (UK CPI from ONS; BoE GLC inflation curves, internal use only), but no free zero-coupon inflation swap quotes, so the curve's inputs cannot be rebuilt from published data.

## Rulings that name this curve's operations

None found by operation name.
