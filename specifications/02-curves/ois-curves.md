# OIS curves: SONIA and minimal SOFR

Spec version 1.0.0. Status: Specified. Full SOFR and ESTR are stage D.

An overnight indexed swap exchanges a fixed rate for daily compounded overnight rates. Its quotes pin down the discount curve.

## Periods

From `as_of` and a `tenor` (as in `calendars.md`), with convention `c` from `conventions.md`:

- `spot` = `as_of` adjusted `FOLLOWING`, then `c.spot_lag` business days on.
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

Inputs: `convention`, `as_of`, `quotes`, `interpolation`, `method` (`SEQUENTIAL` or `GLOBAL`). Each quote is `{tenor, rate}` or `{tenor, bid, ask}`, which uses the mid. Output: `pillars`.

There is one pillar per quote, at the last payment date `p_n` of that swap. So a lag leaves every date the swap needs on or before its pillar.

The curve solves `K_j(curve) = quote_j` for all `j`. It is a square system with one solution in practice, so `SEQUENTIAL` (one unknown at a time, in tenor order) and the `GLOBAL` solve (Newton on all pillars together) give the same curve to solver tolerance. Both must stop with every repricing error below 1e-13. Diagnostic: `max_repricing_error`, required.

Checks, in order: no quotes, pillars not strictly increasing, or `bid > ask`: `E_INPUT`. A solve that fails: `E_NO_CONVERGENCE`, never a silently clamped curve.

Negative rates are valid, and give discount factors above 1.

## `rates.ois.compound`

Compounded in arrears, from actual fixings. Inputs: `rates`, `days` (integers at least 1, same length, else `E_INPUT`), `denominator` (360 or 365). Output: `compounded_rate`:

`(prod(1 + r_i n_i / B) - 1) * B / sum n_i`

Lookback, lockout and observation shift are stage D.

## `rates.ois.pv`

Inputs: `curve`, optional `snapshot_id`, `trade`: `{convention, tenor, fixed_rate, notional, side}`, with `side` `PAY` or `RECEIVE` for the fixed rate. Periods start from the curve's `as_of`. Outputs: `valuation` (see `04-pricing/pricing-framework.md`, `model` `OIS_DISCOUNTING`, `conventions` the convention id), `par_rate`, `annuity`.

`pv = sign * notional * (F - fixed_rate * A)`, with sign +1 for `PAY`.

## Acceptance

Targets are in `stage-b-targets.md`. Oracle: independent replay, QuantLib `OISRateHelper` and `OvernightIndexedSwap`. Measured: pillars within 5e-12 of QuantLib; swap PVs within 1e-3 on 1e6. Strata was used for conventions only, not as a second curve build.
