# Spec questions from the Rust implementation

Each entry is a place where the specs and the golden cases disagree, or where the spec leaves a choice open.
Nothing here was tuned to fit: the code follows the spec text, and the listed golden cases stay failing until
the owner rules.

## Golden cases that contradict the spec

### 1. `add_tenor` with `end_of_month`: 20 calendar cases

`calendars.md`: "If `end_of_month` is true and `date` is the last business day of its month, the result is the
last business day of the target month".

The golden file also applies the rule when `date` is not a business day but no business day follows it in the
month. For example, `GBLO` 2024-03-29 is Good Friday, so the last business day of March 2024 is 28 March. With
`1M`, `FOLLOWING`, `end_of_month` true, the rule does not apply and the code gives 2024-04-29. The golden file
expects 2024-04-30. The same applies to 2024-03-30, 2024-03-31, 2024-06-30, 2024-08-31 and 2022-12-31, all
weekend or holiday dates. These cases name only `quantlib-1.44` in `verified_by`, and the behaviour looks like
QuantLib's own month-end test.

Cases: calendar-0056, 0057, 0061, 0084, 0107, 0148, 0149, 0180, 0314, 0318, 0608, 0609, 0613, 0636, 0659,
0700, 0701, 0732, 0866, 0870.

Question: should the spec say "on or after the last business day of its month", or should the golden cases change?

### 2. `THIRTY_E_360_ISDA` with `start == end`: 1 daycount case

`daycount.md`: "`start == end` gives 0 for every convention".

daycount-1472 has start, end and termination all 2024-02-29 and expects -1/360. That is what the adjustment table
gives without the zero rule (`D1 = 30`, `D2 = 29`). It also breaks "Year fractions here are never negative". The
code gives 0.

Question: is the golden case wrong, or does the zero rule have an exception?

## Runner configuration

### 3. `implementations.json` path on Windows

`conformance/runner/implementations.json` names `rust/target/release/quantforge`. On Windows, Python's
`subprocess` cannot start that path and the runner stops with `WinError 2`, because the file is `quantforge.exe`
and the path is relative. Results here came from a copy of the config outside the repo that gives the absolute
path with `.exe`, passed with `--config`. The file is outside `rust/`, so it was not changed.
`cli-contract.md` also calls the file `implementations.yaml`, while the file on disk is `.json`.

## Readings chosen where the spec is silent

No golden case shows these to be wrong, but the other languages may read them differently.

- `core.calendar.business_days_between`: a date outside 2000 to 2099 is checked before `E_DATE_ORDER`.
- `core.compounding.*`: `frequency` is validated only with `PERIODIC`. Check 4 still applies at `t = 0`, so
  `discount_factor` at `t = 0` with `1 + r/n <= 0` is `E_DOMAIN`, not 1.
- `core.diff.central`: an `order` other than 1 or 2 is `E_SCHEMA`.
- An integer input written as `5.0` is `E_SCHEMA`, from "no fraction" in the value encoding table.
- `core.data.check_quotes`: `outlier_min_history` below 3 is `E_INPUT`. The limit checks run before the
  `event_time` check.
- `core.interp.evaluate`: negative `tension` is `E_DOMAIN`.
- `core.interp.monotone_convex`, region (iv) with `g0 = 0` and `g1 != 0`: `eta = 1`, so the formula is 0/0 at
  `x = 1`. The code takes the node value `g1` there, by continuity.
- `core.pde.bs_european`: at `tau = 0` the right side of a step uses the boundary formulas, not the cell-averaged
  end values. This matters only when `rannacher_steps` is 0.
- `core.stats.ols`: `r_squared` with constant `y` is 0/0, so the result is `E_NON_FINITE`.
- Zero variance is tested as "all values equal", so rounding in a mean cannot hide it.
- `core.stats.summary`: central moments are taken from deviations from the first value, as the mean of data with
  a 1e9 offset rounds, and the rounding reaches skewness at 3e-8. The spec asks only for a stable method.
