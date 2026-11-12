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

Inputs: `trade_date`, `discount`, `recovery`, `quotes` `[{tenor, spread}]`. Output: `pillars` `[{date, survival}]`, one per quote at its maturity (not maturity + 1, ruling D20). Each quote's `par_spread` equals its spread, solved in tenor order, below 1e-13.

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
