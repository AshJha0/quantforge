# Review request: USD-TERM-3M projection (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage B). Evidence line from the project's status table: 6 golden cases for `rates.projection.bootstrap`, 5 with an outside library in `verified_by`.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. USD-TERM-3M is a synthetic index (no live USD term IBOR); confirm the reviewer accepts a method-only test.
9. One case (`rulings_b`) has replay only.

## Spec

### `specifications/02-curves/projection-and-fra.md`

# Projection curves, FRAs, swaps and basis

Spec version 1.0.0. Status: Implemented, not Validated.

Multi-curve means forecasting a rate on one curve and discounting on another. The index is `USD-TERM-3M`, which is synthetic (see `01-core/conventions.md`).

Throughout: `spot` is `core.calendar.add_business_days(as_of, 2)` on `USGS`, as in `ois-curves.md`, and schedules and month steps use `end_of_month` false. A `FRA` end steps from its adjusted start. `months` and `tenor_months` run from 1 to 1200, and `start_months` from 0 to 1200, else `E_INPUT`. No quotes: `E_INPUT`. These operations take an optional `snapshot_id`. `alpha` is `ACT_360` unless stated. Dates use `MODIFIED_FOLLOWING`.

## `rates.projection.bootstrap`

Inputs: `discount` (curve), `index`, `as_of`, `quotes`, `interpolation`. Output: `pillars`.

| Quote `type` | Keys | Start, end, pillar | Model rate |
|---|---|---|---|
| `DEPOSIT` | `months` (3), `rate` | `spot` to `spot + 3M` | `(P(s)/P(e) - 1)/alpha` |
| `FRA` | `start_months`, `rate` | `s = spot + start_months`, `e = s + 3M` | As above |
| `SWAP` | `months`, `rate` | Fixed schedule end | Par rate below |

`P` is the projection curve. The pillar is the end date, and quotes must be in pillar order, else `E_INPUT`. Solve as in `ois-curves.md`, stopping below 1e-13.

## Swap

Fixed leg: annual, `THIRTY_360_BOND`, schedule from `spot` to `spot + months`. Floating leg: quarterly, same dates by `schedules.md`, no payment lag.

`A = sum alpha_i D(e_i)` over fixed periods. `F = sum (P(s_j)/P(e_j) - 1) D(e_j)` over floating periods. Par rate is `F/A`.

The floating forward runs on accrual dates, not on a separate index end date.

`rates.swap.pv`. Inputs: `discount`, `projection`, `trade`: `{index, tenor_months, fixed_rate, notional, side}`. Outputs: `valuation` (`model` `SWAP_DISCOUNTING`, `conventions` the index), `par_rate`. `pv = sign * notional * (F - fixed_rate * A)`, +1 for `PAY`.

## FRA

`rates.fra.pv`. Inputs: `discount`, `projection`, `trade`: `{index, start, fixed_rate, notional, side}`. `e = start + 3M`. Outputs: `valuation` (`model` `FRA_DISCOUNTING`), `forward_rate`.

`F = (P(start)/P(e) - 1)/alpha`, and it settles at `start`, discounted at the forward: `pv = sign * notional * alpha (F - K) / (1 + alpha F) * D(start)`.

`data_version` in these valuations is `null` when no `snapshot_id` is given.

## Tenor basis

`rates.basis.spread`. Inputs: `discount`, `projection`, `index`, `tenor_months`. Output: `spread`: the amount added to an overnight leg to match the term leg, on the quarterly schedule:

`sum (P(s)/P(e) - D(s)/D(e)) D(e)  /  sum alpha D(e)`

## Acceptance

Oracle: replay against QuantLib `DepositRateHelper`, `FraRateHelper`, `SwapRateHelper` with exogenous discounting, and `MakeVanillaSwap`. Measured: pillars within 1e-10; swap and FRA PVs about 1e-8 on 1e6, and the oracle asserts 1e-5. Basis spread has hand replay only. On an `as_of` that is not a business day QuantLib disagrees with itself: `DepositRateHelper` counts from `as_of`, `SwapRateHelper` adjusts first. So those dates have no outside check here.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] ISDA, *2006 ISDA Definitions*, Section 4.16 (day count) and the FRA discounting provisions (FRA Discounting) (not opened)
- [S2] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Swaps" and chapter "Interest Rates" (FRAs) (not opened)
- [S3] Ametrano, F. M. and Bianchetti, M., SSRN 2219548, 2013 (multi-curve projection and tenor basis) (not opened)


## Golden cases (6 of 6 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"projection-0001","operation":"rates.projection.bootstrap","inputs":{"discount":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-11-19","discount_factor":0.9986040008603395},{"date":"2026-12-14","discount_factor":0.9959394252774483},{"date":"2027-02-12","discount_factor":0.989673278797288},{"date":"2027-05-12","discount_factor":0.9807770908259003},{"date":"2027-11-15","discount_factor":0.9634397330592425},{"date":"2028-11-14","discount_factor":0.9318539967570951},{"date":"2029-11-15","discount_factor":0.9012037662703272},{"date":"2031-11-13","discount_factor":0.839287128565213},{"date":"2033-11-15","discount_factor":0.7766268603223262},{"date":"2036-11-13","discount_factor":0.6858387444275659},{"date":"2041-11-14","discount_factor":0.5536981725589005},{"date":"2046-11-15","discount_factor":0.449831073617216},{"date":"2056-11-14","discount_factor":0.31789224697028523}]},"index":"USD-TERM-3M","as_of":"2026-11-06","quotes":[{"type":"DEPOSIT","months":3,"rate":0.0395},{"type":"FRA","start_months":3,"rate":0.0385},{"type":"FRA","start_months":6,"rate":0.0375},{"type":"FRA","start_months":9,"rate":0.037},{"type":"SWAP","months":24,"rate":0.0355},{"type":"SWAP","months":36,"rate":0.035},{"type":"SWAP","months":60,"rate":0.0355},{"type":"SWAP","months":120,"rate":0.038}],"interpolation":"LOG_LINEAR_DF"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-02-10","discount_factor":0.9895742049842318},{"date":"2027-05-10","discount_factor":0.9802441863604426},{"date":"2027-08-10","discount_factor":0.9709393509141818},{"date":"2027-11-10","discount_factor":0.9618445760891611},{"date":"2028-11-10","discount_factor":0.9323166788327014},{"date":"2029-11-13","discount_factor":0.9014506533357646},{"date":"2031-11-10","discount_factor":0.8396105741150829},{"date":"2036-11-10","discount_factor":0.6867313481800761}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"projection_deep-0001","operation":"rates.projection.bootstrap","inputs":{"discount":{"as_of":"2026-11-09","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-11-23","discount_factor":0.9984966970659203},{"date":"2026-12-16","discount_factor":0.9960465819422889},{"date":"2027-02-17","discount_factor":0.9894673195288839},{"date":"2027-05-14","discount_factor":0.9808827523894678},{"date":"2027-11-16","discount_factor":0.9636351668637737},{"date":"2028-11-15","discount_factor":0.9320367174528353},{"date":"2029-11-15","discount_factor":0.9014676804161993},{"date":"2031-11-14","discount_factor":0.8394597075001357},{"date":"2033-11-16","discount_factor":0.7768078965804719},{"date":"2036-11-14","discount_factor":0.6859898651733682},{"date":"2041-11-14","discount_factor":0.5538733684017644},{"date":"2046-11-15","discount_factor":0.4499762959746762},{"date":"2056-11-15","discount_factor":0.317954598128479}]},"index":"USD-TERM-3M","as_of":"2026-11-09","quotes":[{"type":"DEPOSIT","months":3,"rate":0.0395},{"type":"FRA","start_months":3,"rate":0.0385},{"type":"FRA","start_months":6,"rate":0.0375},{"type":"FRA","start_months":9,"rate":0.037},{"type":"SWAP","months":24,"rate":0.0355},{"type":"SWAP","months":36,"rate":0.035},{"type":"SWAP","months":60,"rate":0.0355},{"type":"SWAP","months":120,"rate":0.038}],"interpolation":"LOG_LINEAR_DF"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-02-12","discount_factor":0.9896822448039717},{"date":"2027-05-12","discount_factor":0.9803512075465874},{"date":"2027-08-12","discount_factor":0.9710453562161823},{"date":"2027-11-12","discount_factor":0.9619495884410342},{"date":"2028-11-13","discount_factor":0.9323297785286845},{"date":"2029-11-13","discount_factor":0.9017186988741792},{"date":"2031-11-12","discount_factor":0.839702716666113},{"date":"2036-11-12","discount_factor":0.6868063385938805}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"projection_deep-0006","operation":"rates.projection.bootstrap","inputs":{"discount":{"as_of":"2026-11-25","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-12-09","discount_factor":0.9984966970659208},{"date":"2027-01-05","discount_factor":0.9956195744124056},{"date":"2027-03-02","discount_factor":0.9897762006333997},{"date":"2027-06-02","discount_factor":0.9805744845505172},{"date":"2027-12-02","discount_factor":0.9636119241412238},{"date":"2028-12-04","discount_factor":0.9317541502086786},{"date":"2029-12-04","discount_factor":0.9011932626966367},{"date":"2031-12-02","discount_factor":0.8392731225582641},{"date":"2033-12-02","discount_factor":0.7767930568668466},{"date":"2036-12-02","discount_factor":0.6858270104400138},{"date":"2041-12-03","discount_factor":0.5536882013183373},{"date":"2046-12-04","discount_factor":0.44983034658968096},{"date":"2056-12-04","discount_factor":0.31786247635226306}]},"index":"USD-TERM-3M","as_of":"2026-11-25","quotes":[{"type":"DEPOSIT","months":3,"rate":0.0395},{"type":"FRA","start_months":3,"rate":0.0385},{"type":"FRA","start_months":6,"rate":0.0375},{"type":"FRA","start_months":9,"rate":0.037},{"type":"SWAP","months":24,"rate":0.0355},{"type":"SWAP","months":36,"rate":0.035},{"type":"SWAP","months":60,"rate":0.0355},{"type":"SWAP","months":120,"rate":0.038}],"interpolation":"LOG_LINEAR_DF"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-02-26","discount_factor":0.9898961720709801},{"date":"2027-05-26","discount_factor":0.9805631178396536},{"date":"2027-08-30","discount_factor":0.9708535740087624},{"date":"2027-11-30","discount_factor":0.9617596026547711},{"date":"2028-11-30","discount_factor":0.932214296972411},{"date":"2029-11-30","discount_factor":0.9016057116090738},{"date":"2031-11-28","discount_factor":0.8396789371849023},{"date":"2036-11-28","discount_factor":0.6867990929289848}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"projection_deep-0011","operation":"rates.projection.bootstrap","inputs":{"discount":{"as_of":"2026-12-23","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2027-01-06","discount_factor":0.9984966970659208},{"date":"2027-02-01","discount_factor":0.995725986525258},{"date":"2027-03-31","discount_factor":0.9896712694819644},{"date":"2027-06-30","discount_factor":0.9805708087963789},{"date":"2027-12-30","discount_factor":0.9636119640547665},{"date":"2029-01-02","discount_factor":0.9316691617135507},{"date":"2030-01-02","discount_factor":0.9011110950096582},{"date":"2031-12-31","discount_factor":0.8392012009214792},{"date":"2033-12-30","discount_factor":0.7767920677736848},{"date":"2036-12-31","discount_factor":0.6857744173294776},{"date":"2042-01-02","discount_factor":0.5535734739235711},{"date":"2047-01-02","discount_factor":0.4497722992140453},{"date":"2057-01-02","discount_factor":0.31782882255044936}]},"index":"USD-TERM-3M","as_of":"2026-12-23","quotes":[{"type":"DEPOSIT","months":3,"rate":0.0395},{"type":"FRA","start_months":3,"rate":0.0385},{"type":"FRA","start_months":6,"rate":0.0375},{"type":"FRA","start_months":9,"rate":0.037},{"type":"SWAP","months":24,"rate":0.0355},{"type":"SWAP","months":36,"rate":0.035},{"type":"SWAP","months":60,"rate":0.0355},{"type":"SWAP","months":120,"rate":0.038}],"interpolation":"LOG_LINEAR_DF"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-03-29","discount_factor":0.9895736407080274},{"date":"2027-06-29","discount_factor":0.9799321967059924},{"date":"2027-09-28","discount_factor":0.9707336244660101},{"date":"2027-12-28","discount_factor":0.9617386961605309},{"date":"2028-12-28","discount_factor":0.9322149285074929},{"date":"2029-12-28","discount_factor":0.9016063218868864},{"date":"2031-12-29","discount_factor":0.8394396178396221},{"date":"2036-12-29","discount_factor":0.6865850660227226}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"projection_deep-0016","operation":"rates.projection.bootstrap","inputs":{"discount":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-11-19","discount_factor":1.0004623866205076},{"date":"2026-12-14","discount_factor":1.0013626578022798},{"date":"2027-02-12","discount_factor":1.003602215300708},{"date":"2027-05-12","discount_factor":1.0072112994574374},{"date":"2027-11-15","discount_factor":1.0158187454061245},{"date":"2028-11-14","discount_factor":1.034694469093977},{"date":"2029-11-15","discount_factor":1.0539461153157124},{"date":"2031-11-13","discount_factor":1.0883768016385063},{"date":"2033-11-15","discount_factor":1.1180472949073343},{"date":"2036-11-13","discount_factor":1.1552565866735067},{"date":"2041-11-14","discount_factor":1.2141600341173049},{"date":"2046-11-15","discount_factor":1.2820110896406771},{"date":"2056-11-14","discount_factor":1.489303582614119}]},"index":"USD-TERM-3M","as_of":"2026-11-06","quotes":[{"type":"DEPOSIT","months":3,"rate":-0.010500000000000002},{"type":"FRA","start_months":3,"rate":-0.011500000000000003},{"type":"FRA","start_months":6,"rate":-0.012500000000000004},{"type":"FRA","start_months":9,"rate":-0.013000000000000005},{"type":"SWAP","months":24,"rate":-0.014500000000000006},{"type":"SWAP","months":36,"rate":-0.015},{"type":"SWAP","months":60,"rate":-0.014500000000000006},{"type":"SWAP","months":120,"rate":-0.012000000000000004}],"interpolation":"LOG_LINEAR_DF"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-02-10","discount_factor":1.0028076976210978},{"date":"2027-05-10","discount_factor":1.0056668643869313},{"date":"2027-08-10","discount_factor":1.0088897065049331},{"date":"2027-11-10","discount_factor":1.0122526347024445},{"date":"2028-11-10","discount_factor":1.0297460773891323},{"date":"2029-11-13","discount_factor":1.0466084698979767},{"date":"2031-11-10","discount_factor":1.0759516506982},{"date":"2036-11-10","discount_factor":1.129567254060459}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"rulings_b-0030","operation":"rates.projection.bootstrap","inputs":{"discount":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-11-19","discount_factor":0.9986040008603395},{"date":"2026-12-14","discount_factor":0.9959394252774483},{"date":"2027-02-12","discount_factor":0.989673278797288},{"date":"2027-05-12","discount_factor":0.9807770908259003},{"date":"2027-11-15","discount_factor":0.9634397330592425},{"date":"2028-11-14","discount_factor":0.9318539967570951},{"date":"2029-11-15","discount_factor":0.9012037662703272},{"date":"2031-11-13","discount_factor":0.839287128565213},{"date":"2033-11-15","discount_factor":0.7766268603223262},{"date":"2036-11-13","discount_factor":0.6858387444275659},{"date":"2041-11-14","discount_factor":0.5536981725589005},{"date":"2046-11-15","discount_factor":0.449831073617216},{"date":"2056-11-14","discount_factor":0.31789224697028523}]},"index":"USD-TERM-3M","as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","quotes":[{"type":"FRA","start_months":0,"rate":0.0395}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-02-10","discount_factor":0.9895742049842318}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay"]}
```

## Outside-library evidence and limits (from the project's own page)

Pillars are compared with QuantLib `DepositRateHelper`, `FraRateHelper` and `SwapRateHelper` with exogenous discounting, and the oracle's measured gap is within 1e-10. The tenor basis operation has hand replay only. On an as-of date that is not a business day QuantLib disagrees with itself, so those dates have no outside check.

Golden cases for `rates.projection.bootstrap` with an `ok` result: 6, counted from `verified_by` in `datasets/golden/stage_b/`. All four builds passed them locally, which is self-assessment.

| Suite | Verified by | Cases |
|---|---|---|
| projection | independent-replay, quantlib-1.44 | 1 |
| projection_deep | independent-replay, quantlib-1.44 | 4 |
| rulings_b | independent-replay | 1 |

Limits:

- The discount curve in the example file is the stored SOFR curve, the same values as the golden SOFR case. It does not change in the +1 bp chart: only the projection quotes move.
- The curve stops at 10Y, its last quote.
- The first pillar is three months after spot, so the segment before it has no quote of its own.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free term-rate swap or FRA quotes. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

None found by operation name.
