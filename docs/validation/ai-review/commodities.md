# Review request: Commodity forwards (QuantForge curve)

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

### `specifications/02-curves/commodity.md`

# Commodity forward curves, seasonality and storage carry

Spec version 1.0.0. Status: Specified (stage D, D8).

## `cmdty.curve.forward`

Inputs: `quotes` `[{month, price}]` (delivery months `YYYY-MM`, strictly increasing, else `E_INPUT`; a price `<= 0`: `E_DOMAIN`), `seasonality` (`null`, or 12 additive log terms for January to December; another length: `E_INPUT`), `months`. Output: `forwards`.

With month index `k` and `sigma(k)` the term for its calendar month (0 when `null`): `L_j = ln(price_j) - sigma(k_j)` at the quotes; `L` linear in `k` between quotes; `F(k) = exp(L(k) + sigma(k))`. Every quote reprices. A month outside the quoted range: `E_OUT_OF_RANGE` (no extrapolation, ruling D29).

## `cmdty.storage.carry`

Inputs: `funding` (curve), `forwards` `[{date, price}]` (at least two, dates strictly increasing after `as_of`, else `E_INPUT`), `storage_cost` `u` (continuous, as a fraction of value per year, `>= 0`, else `E_DOMAIN`). For consecutive forwards, `dt = (d1 - d0)/365`, `r = ln(D(d0)/D(d1))/dt`:

- `convenience_yields`: `y = r + u - ln(F1/F0)/dt`
- `carry_values`: `D(d1) F1 - D(d0) F0 exp(u dt)`, the value of buying forward at `d0`, storing and selling forward at `d1`
- `arbitrage`: `carry_values > 0` (cash and carry earns money; `y < 0`)

## Acceptance

`simple_analytic`, analytic; `arbitrage` exact, and no golden carry value is within 1e-6 of zero. Suite `stage_d/commodity_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Determination of Forward and Futures Prices" (storage costs, convenience yield, cash and carry) (not opened)
- [S2] Geman, H., *Commodities and Commodity Derivatives*, Wiley, 2005 (forward-curve seasonality) (not opened)


## Golden cases (4 of 4 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"commodity_d-0001","operation":"cmdty.curve.forward","inputs":{"quotes":[{"month":"2026-12","price":3.42},{"month":"2027-03","price":3.105},{"month":"2027-06","price":2.88},{"month":"2027-12","price":3.56},{"month":"2028-12","price":3.64},{"month":"2030-12","price":3.7}],"seasonality":[0.06,0.045,0.01,-0.03,-0.045,-0.04,-0.02,-0.015,-0.02,0.0,0.025,0.03],"months":["2026-12","2027-01","2027-02","2027-05","2027-08","2027-11","2028-07","2029-01","2030-12"]},"expected":{"status":"ok","outputs":{"forwards":[3.4200000000000004,3.4352794377512383,3.298790855644737,2.8898312263351453,3.0960085305002294,3.4594127056508226,3.430561811898926,3.7534105089980185,3.7000000000000006]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
{"case_id":"commodity_d-0002","operation":"cmdty.curve.forward","inputs":{"quotes":[{"month":"2026-12","price":3.42},{"month":"2027-03","price":3.105},{"month":"2027-06","price":2.88},{"month":"2027-12","price":3.56},{"month":"2028-12","price":3.64},{"month":"2030-12","price":3.7}],"seasonality":null,"months":["2026-12","2027-01","2027-02","2027-05","2027-08","2027-11","2028-07","2029-01","2030-12"]},"expected":{"status":"ok","outputs":{"forwards":[3.4200000000000004,3.3116004952905813,3.2066367954411756,2.95312746938569,3.0908528139066758,3.4364266595668713,3.6064504771807036,3.6424804640311597,3.7000000000000006]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
{"case_id":"commodity_d-0007","operation":"cmdty.storage.carry","inputs":{"funding":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2027-05-06","discount_factor":0.9803598150999601},{"date":"2027-11-08","discount_factor":0.9615452062959098},{"date":"2028-11-06","discount_factor":0.9267197211276171},{"date":"2031-11-06","discount_factor":0.8310200391947283}]},"forwards":[{"date":"2026-12-15","price":75.2},{"date":"2027-03-15","price":74.1},{"date":"2027-06-15","price":75.9},{"date":"2027-12-15","price":78.4},{"date":"2028-12-15","price":76.0}],"storage_cost":0.02},"expected":{"status":"ok","outputs":{"convenience_yields":[0.11976144454022078,-0.03607983964691383,-0.006819802690525706,0.087927141008683],"carry_values":[-2.189643685364544,0.6708164887620427,0.2563568923399657,-6.466559878126418],"arbitrage":[false,true,true,false]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
{"case_id":"commodity_d-0008","operation":"cmdty.storage.carry","inputs":{"funding":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2027-05-06","discount_factor":0.9803598150999601},{"date":"2027-11-08","discount_factor":0.9615452062959098},{"date":"2028-11-06","discount_factor":0.9267197211276171},{"date":"2031-11-06","discount_factor":0.8310200391947283}]},"forwards":[{"date":"2026-12-15","price":75.2},{"date":"2027-03-15","price":74.1},{"date":"2027-06-15","price":75.9},{"date":"2027-12-15","price":78.4},{"date":"2028-12-15","price":76.0}],"storage_cost":0.06},"expected":{"status":"ok","outputs":{"convenience_yields":[0.15976144454022076,0.003920160353086177,0.03318019730947429,0.127927141008683],"carry_values":[-2.9355023287745183,-0.07325390884743399,-1.2598295540913682,-9.602400110301545],"arbitrage":[false,false,false,false]}},"tolerance_class":"simple_analytic","tolerance_limit":null,"verified_by":["analytic"]}
```

## Outside-library evidence and limits (from the project's own page)

4 golden cases with status ok in `datasets/golden/stage_d` for `cmdty.curve.forward`, `cmdty.storage.carry`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| cmdty.curve.forward: analytic | 2 |
| cmdty.storage.carry: analytic | 2 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free commodity forward curves. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

- (stage-d-rulings.md) | D54 | `seasonality`; `years` | `seasonality` is a required key that may be `null` (in `infl.*` and `cmdty.curve.forward`); absent is `E_SCHEMA`. `years` at most 100, else `E_INPUT`. Cases `rulings2_d-0012` to `-0014` |
- (stage-d-rulings.md) | D58 | `cmdty.storage.carry` price `<= 0` | `E_DOMAIN`. Case `rulings2_d-0019` |
