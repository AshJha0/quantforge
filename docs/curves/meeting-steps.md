# Central-bank meeting steps and the year-end turn

<p class="note">Hand-written page, listed under "Method pages" on the Curves index. Every number below is from the Python build in this repository, run on 2026-11-21 through <code>uv run --locked quantforge batch</code> on the golden inputs, and each agreed with its golden (largest relative difference 1.8e-14; measured, local laptop, not the acceptance machine). Inputs are synthetic; the step dates are invented, not a central bank's calendar.</p>

Back to [Curves](README.md).

**Plain idea.** The overnight rate is set by a central bank, which changes it only at its policy meetings. Between two meetings the overnight rate is, to a first approximation, flat. So the natural front end of an OIS curve is a staircase of instantaneous forwards that steps on meeting dates, not a smooth line through pillars. Around the year end, funding is often dearer for a day or two; that is a one-off jump in the discount curve (a "turn"), not a change of level.

**Formal statement** (`specifications/02-curves/meeting-steps.md` 1.0.0, read 2026-11-21).

- Step curve: `as_of`, `base_rate`, `steps [{date, rate}]`, `jumps [{date, factor}]`. The instantaneous forward is `base_rate` from `as_of` and each step's `rate` from its date on. With `t = (date - as_of) / 365`, `D(d) = exp(-integral_0^t(d) f) x J(d)`, `J(d)` the product of jump factors dated strictly before `d`.
- `rates.ois.step_curve`: discount factors and the overnight forward in force on given dates. Step dates must be strictly increasing and after `as_of` (`E_INPUT`); a date before `as_of` is `E_OUT_OF_RANGE`.
- `rates.ois.fit_steps`: solve `base_rate` and `m` step rates from `m + 1` OIS par quotes. The pillar rule `b_j < p_j <= b_(j+1)` (quote `j`'s last payment after step `j` and on or before step `j + 1`) makes quote `j` depend only on the base rate and the first `j` steps, so the system is triangular and its solution unique; every quote must reprice below 1e-13.
- In a multi-curve solve the same staircase is the curve type `OIS_STEPS` of `rates.curve.joint_solve`, which can also fit the steps to futures and solve the turn factor from the quote that spans it (`specifications/02-curves/joint-solve-and-funding.md`; see [Joint solve](joint-solve.md)).

**Worked example 1: the staircase** (`steps_d-0001`). As of 2026-11-06, base 4.25%, steps to 4.00% on 2026-12-10, 3.80% on 2027-01-28, 3.65% on 2027-03-18 and 2027-05-06, 3.50% on 2027-06-17.

| Date | Days | Overnight forward | Discount factor | By hand |
|---|---|---|---|---|
| 2026-12-09 | 33 | 4.25% | 0.9961649070718093 | `exp(-0.0425 x 33/365)` |
| 2026-12-10 | 34 | 4.00% | 0.9960489220202466 | `exp(-0.0425 x 34/365)`: the step takes effect on its date, so the integral up to that date is still all at 4.25% |
| 2026-12-11 | 35 | 4.00% | 0.9959397719549326 | `exp(-(0.0425 x 34 + 0.04 x 1)/365)` |
| 2027-06-17 | 223 | 3.50% | 0.9767445380885168 | the area under the staircase to that date |

A step with the same rate as the one before (3.65% on 2027-05-06) is allowed: a meeting at which nothing changes.

**Worked example 2: the turn** (`steps_d-0002`). The same curve with a jump factor 0.999989041155939 dated 2026-12-31. That factor is `exp(-0.004 / 365)`: one extra day of funding at 40 bp. It applies to dates strictly after its date, so `D(2026-12-31)` stays 0.9937592807153228, while `D(2027-01-01)` falls from 0.9936503815558554 to 0.9936394922962728, and every later factor is scaled by the same 0.99998904. Forwards on every other day are unchanged.

**Worked example 3: fitting the steps** (`steps_d-0007`). Six SOFR par quotes (3W 4.1969%, 2M 4.0788%, 3M 4.0182%, 5M 3.9060%, 6M 3.8687%, 1Y 3.7243%), made from the staircase above, give back `base_rate` 0.04249999999999931 and step rates 0.040000000000000806, 0.03800000000000249, 0.03649999999999632, 0.0365000000000178, 0.03499999999999531: the truth to within 3e-15 in rate. The golden's test is 1e-10.

**What goes wrong in practice.**
- A quote whose last payment falls after the next meeting as well (`steps_d-0010`) or before its own (`steps_d-0011`) breaks the triangular rule and is refused with `E_INPUT`, rather than fitted with two unknowns per quote.
- A smooth interpolation through short pillars spreads one meeting's move over weeks on either side of it; a desk reading forwards between meetings then sees moves that no policy decision caused (inferred from the construction).

**Central-bank fitted curves (H-20).** A different "central-bank curve" is the fitted government curve a central bank publishes (for example the Federal Reserve's). Stage H rebuilt such curves from their published parameters and fitted the library's Nelson-Siegel to them: a consistency check, not validation (median RMSE 3.81 bp, p95 9.21 bp, max 19.99 bp over 323 month-ends; [central-bank consistency](../validation/central-bank-consistency.md)). The daily curve run compares its own Treasury fit with the Fed's curve; on 2026-11-13 that comparison was a recorded miss (RMSE 17.36 bp against 15 bp; [Bond and sovereign fits](bond-fit.md), [LEARN](../../LEARN.md#a-daily-curve-run-and-a-consistency-check-that-missed)).

**Evidence.** `step_curve` agrees with QuantLib `ForwardCurve` (backward flat, with jumps) within 2e-15; `fit_steps` rates within 1e-10 of the truth behind QuantLib `MakeOIS` par rates (spec acceptance; suite `stage_d/steps_d`, 11 cases). The full OIS page [Full SOFR, ESTR, SONIA OIS](ois-full.md) shows the same steps inside a full curve.
