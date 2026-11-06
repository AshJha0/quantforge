# Spec questions from the Python implementation

Each item is a place where the spec is unclear, or where a golden case disagrees with it. Nothing here
was tuned to fit. The code follows the spec text, and the choice made is stated.

## Golden cases that disagree with the spec

These 21 cases fail in the neutral runner. `tests/test_conformance.py` lists them by id and fails if
the set changes, so `uv run pytest` passing does not mean they pass.

### Q1. `add_tenor` with `end_of_month` on a non-business month end (20 cases)

`calendars.md`: the end-of-month rule applies if "`date` is the last business day of its month".

The golden cases apply it also when `date` is a non-business day after the last business day. For
example, calendar-0056: `GBLO`, 2024-03-29 (Good Friday; the last business day is 2024-03-28), `1M`,
`MODIFIED_FOLLOWING`, `end_of_month` true. The spec gives 2024-04-29, the golden file 2024-04-30.

Cases: calendar-0056, 0057, 0061, 0084, 0107, 0148, 0149, 0180, 0314, 0318, 0608, 0609, 0613, 0636,
0659, 0700, 0701, 0732, 0866, 0870. All are `GBLO` or `EUTA`, and all have `verified_by` of
`quantlib-1.44` alone, which suggests the values follow QuantLib's end-of-month test, not the spec.
72 golden cases have such a date. The other 52 give the same date under both readings.

Needed: either the spec says "on or after the last business day", or the golden files change.

### Q2. `THIRTY_E_360_ISDA` with `start == end` on the last day of February (1 case)

`daycount.md`: "`start == end` gives 0 for every convention."

daycount-1472: start, end and termination all 2024-02-29. The golden file has -1/360, which is what
the adjustment table gives (`D1 = 30`, `D2 = 29`), and it is also negative, which the spec rules out.
The code returns 0.

The same rule matters for `THIRTY_E_PLUS_360` on a 31st, where the table would give 1/360.

## Choices where the spec is silent or unclear

No golden case decides these, unless stated.

| # | Where | Question | Choice made |
|---|---|---|---|
| Q3 | `statistics-and-time-series.md`, `summary` | Plain two-pass from a rounded `m` misses stats-0006 by 3.5e-8 on `skewness`, because `m` at 1e9 is rounded to about 1e-7. The golden value is right. | All moments are taken on differences from `x[0]`, then the mean. Same definition, and it passes. `mean` is `x[0] + sum(x - x[0])/n`, not literally `sum x / n` |
| Q4 | `interpolation.md`, monotone convex region (iv) | With `g0 = 0`, `g1 != 0`: `eta = 1`, and at `x = 1` the formula is 0/0. `g` is also 0 on `[0, 1)` and jumps at the end. With `g1 = 0`, `g0 != 0`, `g` is 0 on all of `(0, 1]` | At `x = 1`, `g = g1`, the end value. `G` is unaffected |
| Q5 | `root-finders.md`, Brent step 3 | The acceptance test is written `3 |xm q|`. Brent's published test uses signed `3 xm q`, which also rejects a step in the wrong direction | Follows the spec, with the absolute value |
| Q6 | `compounding.md` | `discount_factor` at `t = 0` with `PERIODIC` and `1 + r/n <= 0`: is check 3 a return of 1, or does check 4 still apply? | Check 4 applies: `E_DOMAIN` |
| Q7 | `compounding.md`, `daycount.md` | A `frequency` that is not listed, given where it is not needed | Compounding: `E_SCHEMA`. Day count: ignored unless the convention needs it |
| Q8 | `differentiation-and-linalg.md` | `order` other than 1 or 2 has no code | `E_SCHEMA`, as an unlisted value |
| Q9 | `interpolation.md`, `tension` | `p < 0` has no code | `E_DOMAIN` |
| Q10 | `root-finders.md`, Newton | Code for one of `a`, `b` given, and for `a >= b` | `E_INPUT` for both |
| Q11 | `root-finders.md`, Newton | `f(a)` or `f(b)` exactly 0 | Counts as bracketed. No early return, unlike bisection |
| Q12 | `rng.md`, `sobol.md` | Negative `skip` has no code. `skip` has no upper limit in `rng.md` | `rng`: `E_SCHEMA`. `sobol`: `E_INPUT`. No limit added |
| Q13 | `rng.md` | Is `"007"` a decimal u64 string? | Accepted |
| Q14 | `statistics-and-time-series.md`, `ols` | `r_squared` when `y` is constant is 0/0 | `E_NON_FINITE` |
| Q15 | `differentiation-and-linalg.md` | "Asymmetry above `1e-12` relative": relative to what? | The largest absolute entry of `a` |
| Q16 | `integration.md` | `max_depth` counting, and limits on `max_depth`, `max_intervals` | The first interval is depth 0. Splitting at depth `max_depth` fails. `max_depth < 0` and `max_intervals < 1` are `E_INPUT`. `inv_sqrt` on `[0, 1]` with `adaptive_simpson` touches the end point: `E_NON_FINITE` |
| Q17 | `calendars.md`, `daycount.md` | Range or order first in `business_days_between`. `BUS_252` with `start == end` outside the calendar's years | Range first, as `calendars.md` states range first. `BUS_252` then gives `E_DATE_RANGE`, not 0 |
| Q18 | `timezone-and-cutoff.md` | A local time in range whose instant falls outside, such as 2007-01-01T00:00:00 in Tokyo | `E_DATE_RANGE` |
| Q19 | `cli-contract.md` | Unknown keys inside `inputs`. `1.0` where an integer is expected | Unknown keys are ignored. `1.0` is `E_SCHEMA`: the contract says no fraction |
| Q20 | `cli-contract.md` | It names `conformance/runner/implementations.yaml`. The file is `implementations.json` | Used the file that exists |
| Q21 | `sobol.md`, `cli-contract.md` | "No command reads any file for its numbers", yet the direction numbers are a data file | Copied into `quantforge_core/_sobol_data.py`. A test holds it equal to the spec's file |
