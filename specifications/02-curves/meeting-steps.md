# Meeting-date steps and turn of year

Spec version 1.0.0. Status: Specified (stage D).

Short overnight rates move on central-bank meeting dates and stay flat in between. A curve with a flat instantaneous forward between meetings is the natural front end. Year end adds a one-off jump.

## Step curve

`as_of`, `base_rate`, `steps` `[{date, rate}]`, `jumps` `[{date, factor}]` (required, may be empty). The continuous instantaneous forward is `base_rate` from `as_of`, and each step's `rate` from its `date` on (a step takes effect on its date). Time is `t = (date - as_of)/365`. Then

`D(d) = exp(-integral_0^t(d) f) * J(d)`, with `J(d)` the product of jump factors whose date is strictly before `d`, as in `curve-framework.md`.

## `rates.ois.step_curve`

Inputs: the step curve, `dates`. Outputs: `discount_factors`, `overnight_forwards` (the forward in force on each date: `base_rate` before the first step, else the rate of the last step dated on or before it).

`steps` may be empty: a flat curve. Checks, in order: empty `dates`: `E_INPUT`. Step dates not strictly increasing or not after `as_of`: `E_INPUT`. Bad jumps: as `curve-framework.md`. A date before `as_of`: `E_OUT_OF_RANGE`.

## `rates.ois.fit_steps`

Inputs: `convention` (`OVERNIGHT`), `as_of`, `step_dates` (`m` of them), `quotes` `[{tenor, rate}]`, `jumps`. Outputs: `base_rate`, `step_rates` (`m`). Diagnostic: `max_repricing_error`, required.

Each quote is an OIS par rate on the step curve, with periods and legs as `ois-curves.md`. Let `p_j` be quote `j`'s last payment date (quotes in tenor order), `b_0 = as_of`, `b_j` step `j`'s date, `b_{m+1}` infinite. Rule: `b_j < p_j <= b_{j+1}` for every `j`. Quote `j` then depends only on `base_rate` and the first `j` step rates, so the system is triangular and its solution unique. Solve so every quote reprices below 1e-13.

Checks, in order: `len(quotes) != m + 1`: `E_INPUT`. Step dates as above: `E_INPUT`. The pillar rule broken: `E_INPUT`. Bad jumps. A solve that fails: `E_NO_CONVERGENCE`.

## Acceptance

`step_curve`: class `simple_analytic`; QuantLib `ForwardCurve` (backward flat, with jumps) agrees within 2e-15. `fit_steps`: rates within 1e-10 of the known truth behind QuantLib `MakeOIS` par rates. Suite `stage_d/steps_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Central-bank meeting calendars, the source of step dates: Federal Reserve FOMC, Bank of England MPC, ECB Governing Council monetary-policy meetings (not opened)
- [S2] Andersen, L. B. G. and Piterbarg, V. V., *Interest Rate Modeling*, 2010, vol. 1, chapter on curve construction (turn-of-year effects) (not opened)
