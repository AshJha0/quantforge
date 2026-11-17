# Review request: Sector and rating curves (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage D). Evidence line from the project's status table: 2 golden cases for `credit.curve.composite`, 2 with an outside library in `verified_by`.

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


## Golden cases (2 of 2 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"credit_d-0011","operation":"credit.curve.composite","inputs":{"trade_date":"2026-11-06","discount":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-06","discount_factor":0.458161174870904}]},"recovery":0.4,"constituents":[{"quotes":[{"tenor":"6M","spread":0.0045},{"tenor":"1Y","spread":0.006},{"tenor":"3Y","spread":0.009},{"tenor":"5Y","spread":0.012},{"tenor":"7Y","spread":0.0135},{"tenor":"10Y","spread":0.015}],"weight":2.0},{"quotes":[{"tenor":"6M","spread":0.00585},{"tenor":"1Y","spread":0.0078000000000000005},{"tenor":"3Y","spread":0.0117},{"tenor":"5Y","spread":0.015600000000000001},{"tenor":"7Y","spread":0.01755},{"tenor":"10Y","spread":0.0195}],"weight":1.0},{"quotes":[{"tenor":"6M","spread":0.0036},{"tenor":"1Y","spread":0.0048000000000000004},{"tenor":"3Y","spread":0.0072},{"tenor":"5Y","spread":0.009600000000000001},{"tenor":"7Y","spread":0.0108},{"tenor":"10Y","spread":0.012}],"weight":1.0}],"scale":1.0},"expected":{"status":"ok","outputs":{"spreads":[0.0046125,0.00615,0.009225,0.0123,0.013837499999999999,0.015375],"pillars":[{"date":"2027-06-20","survival":0.9952113485609257},{"date":"2027-12-20","survival":0.9884375397513033},{"date":"2029-12-20","survival":0.9521758343425821},{"date":"2031-12-20","survival":0.8964761262017943},{"date":"2033-12-20","survival":0.8413849562364609},{"date":"2036-12-20","survival":0.7583012931616856}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
{"case_id":"credit_d-0012","operation":"credit.curve.composite","inputs":{"trade_date":"2026-11-06","discount":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2046-11-06","discount_factor":0.458161174870904}]},"recovery":0.4,"constituents":[{"quotes":[{"tenor":"6M","spread":0.0045},{"tenor":"1Y","spread":0.006},{"tenor":"3Y","spread":0.009},{"tenor":"5Y","spread":0.012},{"tenor":"7Y","spread":0.0135},{"tenor":"10Y","spread":0.015}],"weight":2.0},{"quotes":[{"tenor":"6M","spread":0.00585},{"tenor":"1Y","spread":0.0078000000000000005},{"tenor":"3Y","spread":0.0117},{"tenor":"5Y","spread":0.015600000000000001},{"tenor":"7Y","spread":0.01755},{"tenor":"10Y","spread":0.0195}],"weight":1.0},{"quotes":[{"tenor":"6M","spread":0.0036},{"tenor":"1Y","spread":0.0048000000000000004},{"tenor":"3Y","spread":0.0072},{"tenor":"5Y","spread":0.009600000000000001},{"tenor":"7Y","spread":0.0108},{"tenor":"10Y","spread":0.012}],"weight":1.0}],"scale":1.75},"expected":{"status":"ok","outputs":{"spreads":[0.008071875000000001,0.0107625,0.016143750000000002,0.021525,0.024215624999999998,0.02690625],"pillars":[{"date":"2027-06-20","survival":0.9916349101568664},{"date":"2027-12-20","survival":0.9798411511376999},{"date":"2029-12-20","survival":0.9176102272551174},{"date":"2031-12-20","survival":0.8245066732583233},{"date":"2033-12-20","survival":0.7361504031035453},{"date":"2036-12-20","survival":0.6099209746639757}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"curve solve"},"verified_by":["independent-replay","quantlib-1.44-isda-cds-engine"]}
```

## Outside-library evidence and limits (from the project's own page)

2 golden cases with status ok in `datasets/golden/stage_d` for `credit.curve.composite`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| credit.curve.composite: independent-replay, quantlib-1.44-isda-cds-engine | 2 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free CDS spreads by sector or rating. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

- (stage-d-rulings.md) | D37 | Weights in `credit.index.intrinsic`, `credit.curve.composite`, `bond.fit.nelson_siegel` | A negative weight, or weights summing to 0: `E_DOMAIN`. Wrong length: `E_INPUT`. Cases `rulings_d-0009` to `-0012` |
