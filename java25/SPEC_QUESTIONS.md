# Spec questions from the Java stage A build

Written from the specs alone. Where a spec and a golden case disagree, this build follows the spec text and
the case stays failing. Nothing here was tuned to fit, except the disclosed change in item 3.

## Golden case contradicts the spec (21 failing cases)

### 1. `add_tenor` end-of-month rule on a non-business date: 20 cases

`calendars.md`: "If `end_of_month` is true and `date` is the last business day of its month, the result is the
last business day of the target month". Otherwise `convention` applies.

All 20 cases have `end_of_month: true` and a `date` that is not a business day. For example GBLO 2024-03-29
(Good Friday; the last business day of March is 03-28), `1M`, `FOLLOWING`: the spec text gives 2024-04-29, the
golden file says 2024-04-30.

Every one has `verified_by: ["quantlib-1.44"]` only. They look like a broader rule, "no business day remains in
the month after `date`". That is an inference from the cases: the library's source was not read for this build.

Cases: calendar-0056, 0057, 0061, 0084, 0107, 0148, 0149, 0180, 0314, 0318, 0608, 0609, 0613, 0636, 0659, 0700,
0701, 0732, 0866, 0870.

Question: should the rule be widened to match, or should these cases be regenerated from the spec text?

### 2. `THIRTY_E_360_ISDA` with `start == end`: 1 case

`daycount.md`: "`start == end` gives 0 for every convention." It also says year fractions here are never negative.

daycount-1472 has start = end = termination = 2024-02-29 and expects -1/360, which is what the adjustment table
gives without the zero rule (`D1 = 30`, `D2 = 29`). This build returns 0.

`THIRTY_E_PLUS_360` on a 31st with `start == end` has the same trap: the table alone gives 1/360, not 0.

Question: confirm 0 and fix the case?

## Passes, but with little margin

### 3. diff_linalg-0006: limit sits at the rounding noise

`poly5`, `x = 1.3`, `h = 1e-4`, order 2, limit 1e-7. Rounding here is about `eps/h^2`, so the limit is the same size
as the noise. With `poly5` written as repeated multiplication the error was 1.44e-7 and the case failed. With
`Math.pow(x, 5)` it passes. That change was made after seeing the failure. It is a valid evaluation of the same
function, but the pass depends on how `f` is written, and other languages may land either side of the limit.

Question: should the limit be widened, or `h` raised?

## Choices made where the spec is silent

No golden case is known to decide these. Other implementations could reasonably differ.

| # | Place | Choice |
|---|---|---|
| 4 | `BUS_252` with a date outside 2000 to 2099 and `start == end` | `E_DATE_RANGE`, from `calendars.md`, over "0 for every convention". `end` is range-checked too, though it is not counted |
| 5 | `business_days_between`, both out of range and reversed | `E_DATE_RANGE` before `E_DATE_ORDER` |
| 6 | Integer inputs | No fraction or exponent in the text, so `2.0` and `1e3` are `E_SCHEMA` |
| 7 | Compounding `frequency` given with `SIMPLE` or `CONTINUOUS` | Ignored, even if not listed |
| 8 | `diff.central` `order` other than 1 or 2 | `E_INPUT` |
| 9 | `newton` with only one of `a`, `b` | `E_SCHEMA`, as a missing input |
| 10 | `newton` bracket where `f(a)` or `f(b)` is exactly 0 | Accepted as bracketed |
| 11 | `monotone_convex` with `positive`, a negative `fd`, and a bad `at` | `E_OUT_OF_RANGE` first, as the Checks line comes first |
| 12 | `monotone_convex` region (iv) with `g0 = 0`, `g1 != 0` at `x = 1` | The table gives 0/0 (`eta = 1`). Returns `g(1) = g1`, so `f` meets the node forward |
| 13 | `monotone_pchip` when `d_0 = 0` | Counted as differing in sign from a non-zero `m`, so `m = 0` |
| 14 | `core.stats.ols` with zero variance in `y` | `r_squared` is `null` |
| 15 | `core.ts.ar1` with a constant series | `E_SINGULAR`, as for OLS |
| 16 | Short arrays where no code is named (`returns`, `ewma_variance`, `quantile`) | `E_INPUT`, per the contract |
| 17 | `cholesky`, `eigen_symmetric` "1e-12 relative" | Relative to the largest absolute entry |
| 18 | `to_instant` for a local time in range whose instant falls just outside 2007 to 2037 | Allowed; only the local time is checked. `to_local` likewise checks only the instant |
| 19 | PDE with `rannacher_steps = 0` | Old boundary values on the first step come from the boundary formula at `tau = 0`, not the cell averages |
| 20 | `core.data.check_quotes` | `outlier_min_history` below 3 is `E_INPUT`. `bid` or `ask` absent is treated as `null` |
| 21 | Unknown keys inside `inputs` | Ignored. Unknown keys in the envelope are `E_SCHEMA`, per `case.schema.json` |
| 22 | `schema_version` | Pattern checked only; no major-version check |

## Small document points

- `cli-contract.md` names `conformance/runner/implementations.yaml`. The file is `implementations.json`.
- `statistics-and-time-series.md` suggests `erfc`. `Normal.java` instead works directly in `x`, because
  `x/sqrt(2)` and a rounded `x^2` alone cost about 1e-13 relative at `x = -37`, over the 1e-14 target.
