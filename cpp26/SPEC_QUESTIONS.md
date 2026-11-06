# Spec questions from the C++ implementation

Written from the specs alone. Nothing here was changed to fit a golden file.

## Golden cases that disagree with the spec

### 1. `add_tenor` with `end_of_month`: 20 failing cases

`calendars.md` says the end-of-month rule applies when "`date` is the last business day of its month".
Twenty golden cases use a `date` that is not a business day at all, and still expect the rule to apply:

| Calendar | `date` | Why it is not a business day |
|---|---|---|
| `GBLO`, `EUTA` | 2024-03-29 | Good Friday |
| `GBLO`, `EUTA` | 2024-03-30, 2024-03-31 | Weekend |
| `GBLO`, `EUTA` | 2024-06-30, 2024-08-31 | Weekend |
| `GBLO`, `EUTA` | 2022-12-31 | Weekend |

Example, `calendar-0057`: `GBLO`, 2024-03-29, `1M`, `FOLLOWING`, `end_of_month` true. The spec gives
2024-04-29 (the day is clipped from 29 to 29, the rule does not apply). The golden value is 2024-04-30.

All 20 list only `quantlib-1.44` in `verified_by`. QuantLib tests "no business day remains after this date
in the month", which is wider than the spec's wording. This build follows the spec, so these cases fail.

Failing ids: calendar-0056, 0057, 0061, 0084, 0107, 0148, 0149, 0180, 0314, 0318, 0608, 0609, 0613, 0636,
0659, 0700, 0701, 0732, 0866, 0870.

Decision needed: widen the spec to QuantLib's rule, or regenerate these cases from the spec's rule.

## Golden limits that are close to the noise

### 2. `diff_linalg-0006`: limit about equal to rounding noise

`poly5` at `x = 1.3`, `h = 1e-4`, order 2, limit 1e-7. The rounding of `f` alone, divided by `h^2`, is of the
same size, so the result depends on how `x^5` is written. `x*x*x*x*x` gave an error of 1.44e-7 and failed.
`pow(x, 5)`, with one rounding, passes. This build uses `pow` because it is the more accurate form of the
registry entry, but another correct implementation could miss this limit. `test-functions.md` could fix the
form, or the limit could be raised.

## Tooling

### 3. Runner command on Windows

`conformance/runner/implementations.json` gives `cpp26/build/quantforge`. On Windows, `CreateProcess` does not
find that relative path, and the run stops with `WinError 2`. Conformance here used `--config` with the absolute
path of `quantforge.exe`. Linux should be unaffected, but that has not been run.

### 4. File name in the contract

`cli-contract.md` names `conformance/runner/implementations.yaml`. The file is `implementations.json`.

## Gaps in the specs, and the reading used

No golden case covers these. Each is a choice another language could make differently.

| Where | Gap | Reading used |
|---|---|---|
| `root-finders.md`, Newton | Only one of `a`, `b` given: no code named | `E_SCHEMA`, as an input is missing |
| `root-finders.md`, Newton | `f(a)` or `f(b)` exactly 0: do they "differ in sign"? | Not an error; a zero counts as a sign change |
| `root-finders.md`, Newton | `a >= b` with a bracket | `E_INPUT` |
| `integration.md` | `max_depth` or `max_intervals` below 1 | `E_INPUT` |
| `integration.md` | Adaptive rule evaluates to infinity, as `inv_sqrt` at 0 under `adaptive_simpson` | `E_NON_FINITE` at once |
| `differentiation-and-linalg.md` | `order` other than 1 or 2 | `E_INPUT` |
| `differentiation-and-linalg.md` | "Asymmetry above 1e-12 relative": relative to what | The largest absolute entry of `a` |
| `differentiation-and-linalg.md` | All-zero matrix in `solve`: the pivot is not "below" a threshold of 0 | `E_SINGULAR` |
| `interpolation.md`, `tension` | `tension < 0`: the code is not named | `E_DOMAIN` |
| `interpolation.md`, monotone convex | Region (iv) with `g0 = 0` gives `eta = 1`, and at `x = 1` the table's fraction is 0/0 | `g(1) = g1`, the node forward; `G` takes no term from that piece |
| `interpolation.md`, monotone convex | Bad `at` and negative `fd` together | `E_OUT_OF_RANGE` first, as listed first |
| `compounding.md` | `discount_factor` at `t = 0` with `1 + r/n <= 0` | 1, as check 3 comes before check 4 |
| `daycount.md` | `BUS_252` with `start = end` outside 2000 to 2099: "0 for every convention" against `E_DATE_RANGE` | `E_DATE_RANGE` |
| `calendars.md` | `business_days_between`: range and order both broken; is `end` itself range-checked | Both dates checked, range first |
| `timezone-and-cutoff.md` | `to_instant` on a local time in range whose instant falls outside, such as Tokyo 2007-01-01T00:00:00 | Allowed; only the input is checked |
| `statistics-and-time-series.md` | `ols` with constant `y`: `r_squared` is 0/0 | `E_NON_FINITE` through the output rule |
| `statistics-and-time-series.md` | `ar1` with zero variance in the regressor | `E_SINGULAR`, as for `ols` |
| `pde.md` | With `R = 0` the first step's old boundary: formula at `tau = 0`, or the cell average | The formula, as "boundary values ... at `tau`" says |
| `rng.md` | `skip` has no upper limit, and a very large one runs for a very long time | Accepted; negative is `E_SCHEMA` |
| `monte-carlo.md` | `stream` out of range: not listed there | `E_SCHEMA`, as in `rng.md` |
| `cli-contract.md` | Keys in `inputs` that the operation does not use | Ignored |
| `cli-contract.md` | An optional input given as `null` | Treated as absent |
| `cli-contract.md` | An integer written `2.0` or `2e0` | `E_SCHEMA`: "no fraction" is read on the spelling |
| `cli-contract.md` | A blank line in `batch` | A result with `E_PARSE`, so line counts stay in step |
