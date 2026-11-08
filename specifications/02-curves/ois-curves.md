# OIS curves: SONIA, SOFR and ESTR

Spec version 1.1.0. Status: SONIA and SOFR Implemented, not Validated; ESTR and jumps Specified (stage D).

An overnight indexed swap exchanges a fixed rate for daily compounded overnight rates. Its quotes pin down the discount curve.

## Periods

From `as_of` and a `tenor` (as in `calendars.md`), with convention `c` from `conventions.md`:

- `spot` = `core.calendar.add_business_days(as_of, c.spot_lag)`. Days count from `as_of` itself, even if it is not a business day, as in QuantLib (`MakeOIS`, its issue 753). So SOFR from Saturday 2026-11-07 is Tuesday 2026-11-10. A lag of 0 gives `as_of` adjusted `FOLLOWING`.
- For `D` and `W` tenors, and for tenors of `c.fixed_months` or less: one period, ending at `add_tenor(spot, tenor)` with `MODIFIED_FOLLOWING`.
- Otherwise a schedule from `spot` to `spot + tenor` (unadjusted), at `c.fixed_months`, by `schedules.md`.
- `end_of_month` is true when `spot` is on or after the last business day of its month. For one-period swaps the `add_tenor` rule gives the same thing.
- Payment `p_i` is period end `e_i` plus `c.payment_lag` business days.

## Legs

Both legs use the same periods `(s_i, e_i, p_i)`. `alpha_i` is the `fixed_day_count` fraction of `s_i` to `e_i`.

`annuity A = sum alpha_i D(p_i)`

`floating F = sum (D(s_i)/D(e_i) - 1) D(p_i)`

Plan section 8: this is the general form. The telescoped `D(s_0) - D(e_n)` holds only at zero payment lag and unit notional, and must not be used otherwise. On SOFR 10Y it is out by about 1.1e-4 per unit notional. `D(s_i)/D(e_i)` is the expected compounded growth, so no daily loop is needed on a single curve.

Par rate: `K = F / A`.

## `rates.ois.bootstrap`

Inputs: `convention` (`SONIA`, `SOFR`, `ESTR`), `as_of`, `quotes`, `interpolation`, `method` (`SEQUENTIAL` or `GLOBAL`), optional `jumps` (stage D, as in `curve-framework.md`: the solve is on the curve with those jumps, and pillars hold the full discount factor). Each quote is `{tenor, rate}` or `{tenor, bid, ask}`, which uses the mid. Output: `pillars`.

There is one pillar per quote, at the last payment date `p_n` of that swap. So a lag leaves every date the swap needs on or before its pillar.

The curve solves `K_j(curve) = quote_j` for all `j`. It is a square system with one solution in practice, so `SEQUENTIAL` (one unknown at a time, in tenor order) and the `GLOBAL` solve (Newton on all pillars together) give the same curve to solver tolerance. Both must stop with every repricing error below 1e-13. Diagnostic: `max_repricing_error`, required.

Checks, in order: a bad jump (`E_INPUT` for dates, `E_DOMAIN` for a factor), no quotes, pillars not strictly increasing, or `bid > ask`: `E_INPUT`. A solve that fails: `E_NO_CONVERGENCE`, never a silently clamped curve.

Negative rates are valid, and give discount factors above 1.

## `rates.ois.compound`

Compounded in arrears, from actual fixings. Inputs: `rates`, `days` (integers at least 1, same length, else `E_INPUT`), `denominator` (360 or 365). Output: `compounded_rate`:

`(prod(1 + r_i n_i / B) - 1) * B / sum n_i`

Dated compounding with lookback, lockout and observation shift: `overnight-compounding.md`.

## `rates.ois.pv`

Inputs: `curve`, optional `snapshot_id`, `trade`: `{convention, tenor, fixed_rate, notional, side}`, with `side` `PAY` or `RECEIVE` for the fixed rate. Periods start from the curve's `as_of`. Outputs: `valuation` (see `04-pricing/pricing-framework.md`, `model` `OIS_DISCOUNTING`, `conventions` the convention id), `par_rate`, `annuity`.

`pv = sign * notional * (F - fixed_rate * A)`, with sign +1 for `PAY`.

## Acceptance

Stage D (ESTR, SOFR at more tenors and notionals, jumps): `stage-d-targets.md`; suite `stage_d/ois_d`.


Targets are in `stage-b-targets.md`. Oracle: independent replay, QuantLib `OISRateHelper` and `OvernightIndexedSwap`. Measured: pillars within 2e-11 of QuantLib; swap PVs within 1e-5 on 1e6 against QuantLib, and through Strata's own swap pricer on the same curve (`oracle/REPORT.md`). No curve was built by Strata's calibrator.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Bank of England, *SONIA key features and policies* (opened 2026-11-07)
- [S2] Federal Reserve Bank of New York, *Additional Information about Reference Rates Administered by the New York Fed*, section "Calculation Methodology for the TGCR, BGCR, and SOFR" (opened 2026-11-07)
- [S3] European Central Bank, *The euro short-term rate (€STR) methodology and policies* (opened 2026-11-07, title from the PDF; body not read)
- [S4] ISDA, *2021 ISDA Interest Rate Derivatives Definitions*, overnight compounding Floating Rate Options for SONIA, SOFR and €STR (not opened)
- [S5] Ametrano, F. M. and Bianchetti, M., "Everything you always wanted to know about multiple interest rate curve bootstrapping but were afraid to ask", SSRN 2219548, 2013 (not opened)
