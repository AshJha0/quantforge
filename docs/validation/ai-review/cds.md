# Review request: Credit and ISDA CDS (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is filed under a labelled "AI review" section of the curve's evidence checklist and checked against the repository before anything is acted on.

Stage: D. Evidence line from the project's curve table: 6 golden cases.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.

## Spec

### `specifications/04-pricing/credit.md`

# Credit: ISDA CDS, index CDS, composite curves, digital CDS

Spec version 1.0.0. Status: Specified (stage D, D4).

The ISDA CDS standard model: piecewise-flat hazard and forward rates, exact integrals between nodes, accrual paid on default. This spec is written to agree with QuantLib's `IsdaCdsEngine` (Taylor fix, no accrual bias, piecewise forwards), which is the outside source; the ISDA C library itself is not run.

## Dates

`T` is the trade date. Business days are weekdays (no holidays, as ISDA's standard `WeekendsOnly`). Step-in is `T + 1` day; cash settlement `T + 3` business days.

Roll date: 20 December of `T`'s year if `T` is on or after 20 September; 20 June if on or after 20 March; else 20 December of the year before. Tenor `nM`/`nY` maturity: roll date plus that many months, on the 20th, unadjusted.

Accrual periods run between 20 March, June, September, December, from the last such date on or before `T` to maturity. Each start and end is moved to the next weekday if on a weekend, except maturity itself. Payment `p_i` is the adjusted end (the last: maturity adjusted). Accrual `alpha_i = (end_i - start_i)/360`, plus one day for the last period. `T` on an adjusted coupon date is priced (ruling R6-7.3, replacing D19's `E_INPUT`): the last coupon date on or before `T` is `T` itself, so the first period starts on `T`, and the accrued premium at step-in `T + 1` is one day. QuantLib 1.44 `IsdaCdsEngine` on a CDS2015 schedule agrees to 1.3e-11 per unit on four such dates (`r6/cds_imm_r6`), so the rule now has its outside check.

## Curves

`discount`: a curve object (`curve-framework.md`) with `interpolation` `LOG_LINEAR_DF`, which gives the flat forwards the ISDA model assumes. Any other interpolation is `E_INPUT`, in every `credit.*` operation, checked before any other rule check (ruling R1-4). `hazard`: `{as_of, pillars: [{date, survival}]}`, hazard flat between pillars (`-ln` of survival linear in time) and flat after the last. Time `t = (d - T)/365`. The integration nodes are the union of both curves' pillar dates.

## Legs, per unit notional

Let `QP(t) = Q(t) P(t)`. On a piece `[t0, t1]` between consecutive nodes, `h = ln(Q0/Q1)/(t1-t0)`, `f = ln(P0/P1)/(t1-t0)`, `k = f + h`.

Protection, from `T` to maturity: `(1 - R) sum (h/k)(QP(t0) - QP(t1))`.

Premium, per unit coupon, `rpv01 = sum_i alpha_i Q(p_i - 1) P(p_i) + AoD_i`. Accrual on default in period `i` runs over pieces from `s = max(start_i - 1, T)` to `p_i - 1`, with `tacc = t(start_i - 1)`:

`AoD_i = (365/360) sum h QP(t0) [ (t0 - tacc)(1 - e^{-k D})/k + (1 - e^{-k D}(1 + k D))/k^2 ]`, `D = t1 - t0`.

When `k D < 1e-4`, the Taylor series (to fourth order, QuantLib's form) may be used; the difference is below 1e-15.

`accrued = coupon (T + 1 - start_1)/360`. `Pcs = P(cash settlement)`.

## `credit.cds.price`

Inputs: `trade_date`, `discount`, `hazard`, `recovery` `R`, `trade` `{maturity, coupon, notional, side}` (`BUY_PROTECTION`, `SELL_PROTECTION`), `payout` (`STANDARD`, or `DIGITAL`, which pays 1 in place of `1 - R`). Outputs:

- `protection_leg`, `rpv01`, `accrued`
- `par_spread = protection_leg / (rpv01 - (accrued/coupon) Pcs)`, on the clean annuity
- `upfront = (protection_leg - coupon rpv01)/Pcs + accrued`: the clean upfront, paid by the buyer, per unit
- `pv = sign notional (protection_leg - coupon rpv01 + accrued Pcs)`, +1 for the buyer, valued at `T`

## `credit.cds.bootstrap`

Inputs: `trade_date`, `discount`, `recovery`, `quotes` `[{tenor, spread}]`. Output: `pillars` `[{date, survival}]`, one per quote at its maturity (not maturity + 1, ruling D20). Each quote's `par_spread` equals its spread, solved in tenor order, below 1e-13 in the oracle's own replay. Against QuantLib's `IsdaCdsEngine` the fair spreads agree to about 1e-11 (not 1e-13) where a maturity or coupon date falls on a weekend and is adjusted (R6-25; 1.3e-11 measured on the `r6/cds_imm_r6` curves).

Checks, in order: `recovery` outside `[0, 1)`: `E_DOMAIN`. Maturities not strictly increasing: `E_INPUT`. A spread `<= 0`: `E_DOMAIN`. `T` on a coupon date: `E_INPUT`.

## `credit.index.intrinsic`

Inputs: `trade_date`, `discount`, `names` `[{hazard, recovery, weight}]`, `trade` `{maturity, coupon}`, `quoted_upfront`. Outputs: `name_upfronts` (each name's `upfront`), `intrinsic_upfront = sum w u / sum w`, `basis = quoted_upfront - intrinsic_upfront`. Empty `names`: `E_INPUT`.

## `credit.curve.composite`

Sector and rating curves. Inputs: `trade_date`, `discount`, `recovery`, `constituents` `[{quotes, weight}]` (all on the same tenors, else `E_INPUT`), `scale` (`> 0`; a rating multiplier, 1 for the sector itself). Outputs: `spreads` (per tenor, `scale sum w s / sum w`), `pillars` (`credit.cds.bootstrap` of them).

## Acceptance

Survival within 1e-9; prices 1e-9 per unit notional. QuantLib `IsdaCdsEngine` NPVs agree within 7e-16 per unit, and its fair spreads reprice the bootstrapped quotes within 2e-10, on flat and multi-node discount curves. Suite `stage_d/credit_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] ISDA / Markit, *ISDA CDS Standard Model* documentation and source (cdsmodel.com), and the 2009 Big Bang Protocol conventions (fixed coupons, step-in T+1, cash settlement T+3) (cdsmodel.com opened 2026-11-07: free source confirmed; the dates were not found there)
- [S2] ISDA, *2014 ISDA Credit Derivatives Definitions* (not opened)
- [S3] O'Kane, D., *Modelling Single-name and Multi-name Credit Derivatives*, Wiley, 2008, chapters on CDS pricing and on index CDS (not opened)
- [S4] ISDA semi-annual roll for single-name CDS, effective 21 December 2015: on-the-run roll on 20 March and 20 September, maturities on 20 June and 20 December (cdsmodel.com news, opened 2026-11-07)
- [S5] ISDA CDS Standard Model, flat-forward (log-linear discount factor) interpolation of the discount curve between nodes: basis of ruling R1-4 (not opened)


## Golden cases (10 of 10 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"cds_imm_r6-0001","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2026-12-21","discount":{"as_of":"2026-12-21","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-12-21","discount_factor":0.458161174870904}]},"recovery":0.4,"quotes":[{"tenor":"6M","spread":0.0045},{"tenor":"1Y","spread":0.006},{"tenor":"3Y","spread":0.009},{"tenor":"5Y","spread":0.012},{"tenor":"7Y","spread":0.0135},{"tenor":"10Y","spread":0.015}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-06-20","survival":0.9962549909270567},{"date":"2027-12-20","survival":0.9899587627812985},{"date":"2029-12-20","survival":0.9551785099673002},{"date":"2031-12-20","survival":0.9013720971899637},{"date":"2033-12-20","survival":0.8477225487583118},{"date":"2036-12-20","survival":0.7664714098007159}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve; spreads reprice below 1e-13"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
{"case_id":"cds_imm_r6-0003","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2027-03-22","discount":{"as_of":"2027-03-22","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2047-03-22","discount_factor":0.458161174870904}]},"recovery":0.4,"quotes":[{"tenor":"6M","spread":0.0045},{"tenor":"1Y","spread":0.006},{"tenor":"3Y","spread":0.009},{"tenor":"5Y","spread":0.012},{"tenor":"7Y","spread":0.0135},{"tenor":"10Y","spread":0.015}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-12-20","survival":0.9943566814866918},{"date":"2028-06-20","survival":0.9874172612938193},{"date":"2030-06-20","survival":0.9514050892650608},{"date":"2032-06-20","survival":0.8962969031630785},{"date":"2034-06-20","survival":0.842187496669828},{"date":"2037-06-20","survival":0.7605752165959002}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve; spreads reprice below 1e-13"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
{"case_id":"cds_imm_r6-0005","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2027-06-21","discount":{"as_of":"2027-06-21","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2047-06-21","discount_factor":0.458161174870904}]},"recovery":0.4,"quotes":[{"tenor":"6M","spread":0.0045},{"tenor":"1Y","spread":0.006},{"tenor":"3Y","spread":0.009},{"tenor":"5Y","spread":0.012},{"tenor":"7Y","spread":0.0135},{"tenor":"10Y","spread":0.015}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-12-20","survival":0.9962342379039847},{"date":"2028-06-20","survival":0.989931281082762},{"date":"2030-06-20","survival":0.9551771207725038},{"date":"2032-06-20","survival":0.9013193480049309},{"date":"2034-06-20","survival":0.8477183483099291},{"date":"2037-06-20","survival":0.7664674362362506}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve; spreads reprice below 1e-13"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
{"case_id":"cds_imm_r6-0007","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2027-09-20","discount":{"as_of":"2027-09-20","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2047-09-20","discount_factor":0.458161174870904}]},"recovery":0.4,"quotes":[{"tenor":"6M","spread":0.0045},{"tenor":"1Y","spread":0.006},{"tenor":"3Y","spread":0.009},{"tenor":"5Y","spread":0.012},{"tenor":"7Y","spread":0.0135},{"tenor":"10Y","spread":0.015}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2028-06-20","survival":0.9943361689130927},{"date":"2028-12-20","survival":0.9873897616210651},{"date":"2030-12-20","survival":0.9513637631970085},{"date":"2032-12-20","survival":0.8962413737747554},{"date":"2034-12-20","survival":0.8421268759849635},{"date":"2037-12-20","survival":0.7605101499967294}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve; spreads reprice below 1e-13"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
{"case_id":"credit_d-0001","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2026-11-06","discount":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-06","discount_factor":0.458161174870904}]},"recovery":0.4,"quotes":[{"tenor":"6M","spread":0.0045},{"tenor":"1Y","spread":0.006},{"tenor":"3Y","spread":0.009},{"tenor":"5Y","spread":0.012},{"tenor":"7Y","spread":0.0135},{"tenor":"10Y","spread":0.015}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-06-20","survival":0.9953278717430543},{"date":"2027-12-20","survival":0.9887181795921078},{"date":"2029-12-20","survival":0.9533184219921649},{"date":"2031-12-20","survival":0.8988961248330224},{"date":"2033-12-20","survival":0.8449964351776124},{"date":"2036-12-20","survival":0.7635674704223004}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve; spreads reprice below 1e-13"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
{"case_id":"credit_d-0002","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2026-11-06","discount":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-06","discount_factor":0.458161174870904}]},"recovery":0.25,"quotes":[{"tenor":"6M","spread":0.018},{"tenor":"1Y","spread":0.024},{"tenor":"3Y","spread":0.036},{"tenor":"5Y","spread":0.048},{"tenor":"7Y","spread":0.054},{"tenor":"10Y","spread":0.06}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-06-20","survival":0.9851258609044374},{"date":"2027-12-20","survival":0.9642817630498415},{"date":"2029-12-20","survival":0.8571531465087603},{"date":"2031-12-20","survival":0.7044398409169544},{"date":"2033-12-20","survival":0.5702594500772052},{"date":"2036-12-20","survival":0.39704771889922247}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve; spreads reprice below 1e-13"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
{"case_id":"credit_d-0003","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2026-11-06","discount":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-06","discount_factor":0.458161174870904}]},"recovery":0.4,"quotes":[{"tenor":"1Y","spread":0.0042},{"tenor":"3Y","spread":0.006299999999999999},{"tenor":"5Y","spread":0.0084},{"tenor":"7Y","spread":0.00945},{"tenor":"10Y","spread":0.010499999999999999}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-12-20","survival":0.9921195815027349},{"date":"2029-12-20","survival":0.9671517009117284},{"date":"2031-12-20","survival":0.9283694562373445},{"date":"2033-12-20","survival":0.8893390629638799},{"date":"2036-12-20","survival":0.8291269678582948}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve; spreads reprice below 1e-13"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
{"case_id":"credit_d-0017","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2026-12-21","discount":{"as_of":"2026-12-21","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-12-21","discount_factor":0.458161174870904}]},"recovery":0.4,"quotes":[{"tenor":"6M","spread":0.0045},{"tenor":"1Y","spread":0.006},{"tenor":"3Y","spread":0.009},{"tenor":"5Y","spread":0.012},{"tenor":"7Y","spread":0.0135},{"tenor":"10Y","spread":0.015}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-06-20","survival":0.9962549909270567},{"date":"2027-12-20","survival":0.9899587627812985},{"date":"2029-12-20","survival":0.9551785099673002},{"date":"2031-12-20","survival":0.9013720971899637},{"date":"2033-12-20","survival":0.8477225487583118},{"date":"2036-12-20","survival":0.7664714098007159}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve; spreads reprice below 1e-13"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
{"case_id":"credit_d-0018","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2027-02-10","discount":{"as_of":"2027-02-10","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2028-02-10","discount_factor":0.9627129408911995},{"date":"2030-02-09","discount_factor":0.8922579558824083},{"date":"2032-02-09","discount_factor":0.8269591339433623},{"date":"2037-02-07","discount_factor":0.6838614092123558},{"date":"2042-02-06","discount_factor":0.5655254386995371}]},"recovery":0.4,"quotes":[{"tenor":"6M","spread":0.0045},{"tenor":"1Y","spread":0.006},{"tenor":"3Y","spread":0.009},{"tenor":"5Y","spread":0.012},{"tenor":"7Y","spread":0.0135},{"tenor":"10Y","spread":0.015}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-06-20","survival":0.997310139097766},{"date":"2027-12-20","survival":0.9913685455624913},{"date":"2029-12-20","survival":0.9572918319517785},{"date":"2031-12-20","survival":0.9042131958915132},{"date":"2033-12-20","survival":0.8508848976554871},{"date":"2036-12-20","survival":0.7699163098943487}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
{"case_id":"credit_d-0019","operation":"credit.cds.bootstrap","inputs":{"trade_date":"2026-11-06","discount":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-11-19","discount_factor":0.9986040008603395},{"date":"2026-12-14","discount_factor":0.9959394252774483},{"date":"2027-02-12","discount_factor":0.989673278797288},{"date":"2027-05-12","discount_factor":0.9807770908259003},{"date":"2027-11-15","discount_factor":0.9634397330592425},{"date":"2028-11-14","discount_factor":0.9318539967570951},{"date":"2029-11-15","discount_factor":0.9012037662703272},{"date":"2031-11-13","discount_factor":0.839287128565213},{"date":"2033-11-15","discount_factor":0.7766268603223262},{"date":"2036-11-13","discount_factor":0.6858387444275659},{"date":"2041-11-14","discount_factor":0.5536981725589005},{"date":"2046-11-15","discount_factor":0.449831073617216},{"date":"2056-11-14","discount_factor":0.31789224697028523}]},"recovery":0.4,"quotes":[{"tenor":"6M","spread":0.0045},{"tenor":"1Y","spread":0.006},{"tenor":"3Y","spread":0.009},{"tenor":"5Y","spread":0.012},{"tenor":"7Y","spread":0.0135},{"tenor":"10Y","spread":0.015}]},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-06-20","survival":0.995326670878391},{"date":"2027-12-20","survival":0.9887164897229775},{"date":"2029-12-20","survival":0.9533394989688196},{"date":"2031-12-20","survival":0.8990864842101756},{"date":"2033-12-20","survival":0.8453221834775759},{"date":"2036-12-20","survival":0.7639754894864467}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
```

## Outside-library evidence and limits (from the project's own page)

6 golden cases with status ok in `datasets/golden/stage_d` for `credit.cds.bootstrap`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| credit.cds.bootstrap: independent-replay, quantlib-1.44-isda-cds-engine | 6 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free CDS spreads. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

None found by operation name.
