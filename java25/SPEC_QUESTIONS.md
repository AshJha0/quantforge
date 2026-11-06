# Spec questions from the Java stage A build

Written from the specs alone. Where a spec and a golden case disagree, this build follows the spec text.

## Resolved by the spec corrections on `stage-a` (363e5a8)

1. `add_tenor` end-of-month on a non-business date: `calendars.md` now gives the rule, and the code follows it.
2. `THIRTY_E_360_ISDA` with `start == end`: `daycount.md` confirms 0. The build already returned 0.
3. diff_linalg-0006 limit at the rounding noise: `differentiation-and-linalg.md` now sets limits that accept any
   correct form of `f`. `poly5` stays as `Math.pow`, which was changed after seeing the old failure.

## Choices made where the spec is silent

No golden case is known to decide these. Other implementations could reasonably differ.

| # | Place | Choice |
|---|---|---|
| 4 | `BUS_252` with a date outside 2000 to 2099 and `start == end` | `E_DATE_RANGE`, from `calendars.md`, ahead of the zero test, which `daycount.md` places only before day-number adjustments. `end` is range-checked too, though it is not counted |
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

| 23 | `core.ts.rolling` | `STDEV` uses the shift of `statistics-and-time-series.md`, though `rolling` is not listed there. `MEAN` is a plain sum over the window, since a shift by a large first value would add rounding |

## Small document points

- `cli-contract.md` names `conformance/runner/implementations.yaml`. The file is `implementations.json`.
- `statistics-and-time-series.md` suggests `erfc`. `Normal.java` instead works directly in `x`, because
  `x/sqrt(2)` and a rounded `x^2` alone cost about 1e-13 relative at `x = -37`, over the 1e-14 target.
