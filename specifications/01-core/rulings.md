# Rulings on silent spec points

Spec version 1.2.0. Normative: this page is part of every stage A spec, and wins where it is more exact.

The first clean-room builds listed places where the specs were silent. Each is settled here. Golden cases are in
`datasets/golden/core/rulings.json`, and "Case" says where one exists.

## General

| # | Point | Ruling | Case |
|---|---|---|---|
| G1 | Integer written `2.0` or `1e3` | `E_SCHEMA`. An integer has no fraction or exponent in its text. Reals may be written as integers | Yes |
| G2 | Keys in `inputs` the operation does not use | Ignored. Unknown keys in the envelope are `E_SCHEMA` | Yes |
| G3 | An optional input given as `null` | Same as absent. A required input given as `null` is `E_SCHEMA`, unless the operation allows `null` | Yes |
| G4 | A required key absent where `null` is allowed, such as `bid` | `E_SCHEMA`. Missing data is written `null`, never left out | Yes |
| G5 | An integer input not in a listed set, such as `order` or `frequency` | `E_SCHEMA`, the same as an unlisted enum | Yes |
| G6 | `frequency` given where the convention does not use it | Ignored, even if not a listed value | Yes |
| G7 | Blank line in `batch` | One result with `E_PARSE` and `case_id: "unknown"`, so that lines stay in step. The newline ending the last line is not a blank line | Runner only |
| G8 | `schema_version` | Pattern checked only | No |
| G9 | Data files such as the Sobol table | May be compiled into a build. "Reads no file" means at run time. A test must hold the copy equal to the spec file | No |
| G10 | Short arrays where no code is named (`returns`, `ewma_variance`, `quantile`) | `E_INPUT` | Yes |
| G11 | u64 strings | `^[0-9]+$`, value at most 2^64 - 1. Leading zeros are accepted | Yes |

## By operation

| # | Operation | Ruling | Case |
|---|---|---|---|
| D1 | `BUS_252` | Both dates are range-checked against the calendar, before the `start == end` zero rule. So an out-of-range equal pair is `E_DATE_RANGE` | Yes |
| D2 | `business_days_between` | Both dates range-checked first, then `E_DATE_ORDER` | Yes |
| C1 | `compounding` at `t = 0` | The checks run in order and all apply. `1 + r/n <= 0` is `E_DOMAIN` even at `t = 0`. A value of 1 is returned only if every check passes | Yes |
| R1 | `newton`, one of `a`, `b` | `E_SCHEMA` | Yes |
| R2 | `newton`, `a >= b` | `E_INPUT` | Yes |
| R3 | `newton`, `f(a)` or `f(b)` exactly 0 | Counts as bracketed. There is no early return at the end point; iteration starts from `x0` | Yes |
| R4 | `brent` acceptance | Signed, as Brent published, and corrected in `root-finders.md`. Results do not change on the stored cases | No |
| I1 | Adaptive limits | `max_depth < 1` or `max_intervals < 1`: `E_INPUT`. The first interval has depth 0. Splitting an interval at depth `max_depth` is `E_NO_CONVERGENCE` | Yes |
| I2 | A rule that evaluates a non-finite value, such as `inv_sqrt` at 0 under `adaptive_simpson` | `E_NON_FINITE` at once | Yes |
| L1 | `solve` | The test is pivot `<=` threshold, so an all-zero matrix is `E_SINGULAR` | Yes |
| L2 | "1e-12 relative" asymmetry | Relative to the largest absolute entry of `a` | Yes |
| P1 | `tension < 0` | `E_DOMAIN` | Yes |
| P2 | `monotone_pchip` | "Differ in sign" uses a three-valued sign, as SciPy does: 0 differs from a non-zero value. So `d_0 = 0` gives `m = 0` unless `m` is also 0 | Yes |
| P3 | `monotone_convex`, order of checks | `E_OUT_OF_RANGE` on `at` before `E_DOMAIN` on `positive` | Yes |
| P4 | `monotone_convex`, region (iv), `g0 = 0`, `g1 != 0` | `eta = 1` and the table is 0/0 at `x = 1`. Then `g(1) = g1`, the node forward, and `G(1) = 0`. For `g1 = 0`, `g0 != 0`, `eta = 0`, and `x > 0` always, so `g = 0` | Yes |
| S1 | Zero variance | Tested as "all values equal", not by a computed variance, so rounding cannot hide it | Yes |
| S2 | `ols`, constant `y` | `r_squared` is `null`; the rest stand. This matches `summary` and `covariance` | Yes |
| S3 | `ar1`, constant series | `E_SINGULAR` | Yes |
| S4 | `rolling` | `STDEV` shifts by the first value of each window. `MEAN` is a plain sum over the window | No |
| S5 | `normal` | Any method that meets the stated accuracy. `erfc` is a suggestion | No |
| T1 | `to_instant`, `to_local` | Only the input is range-checked. A local time in 2007 whose instant falls in 2006 is allowed | Yes |
| E1 | PDE with `R = 0` | The first step's old boundary values come from the boundary formula at `tau = 0`, not the cell averages | Yes |
| N1 | `skip` | Upper limit in `limits.md`: `E_LIMIT`. Negative: `E_SCHEMA` in `rng`, `E_INPUT` in `sobol`, as each spec's range rule says | Yes |
| M1 | `monte-carlo`, `stream` out of range | `E_SCHEMA`, as in `rng.md` | Yes |
| Q1 | `check_quotes`, order | Parameter checks first, including `outlier_min_history < 3`: `E_INPUT`. Then `event_time` after `as_of` | Yes |

## As-of store

Cases are in `datasets/golden/core/store_rulings.json`.

| # | Point | Ruling | Case |
|---|---|---|---|
| A1 | `sequence < 1`, or an empty `series_id` | `E_SCHEMA` | Yes |
| A2 | Order of checks | The contract's order holds: all `E_SCHEMA` on any input, then `E_LIMIT`, then log checks 2 and 3, then the operation's other rule checks. "Before anything else" in the first version of `asof-store.md` was wrong, and is corrected | Yes |
| A3 | Chain canonical form | Every key of the record as given, including unknown keys and a top-level `snapshot_id`: the exclusion belongs to the snapshot hash only. Instants stay as written. Unknown keys never reach `rows` | Yes |
| A4 | A lone surrogate in any string of a record | `E_SCHEMA`, as in `snapshot-hash.md`: UTF-8 cannot carry it. No golden case yet, as the runner cannot send one (see `clean-room-followups.md`) | No |
| A5 | An instant that leaves years 1 to 9999 when moved to UTC | `E_DATE_RANGE`, as `Z` form cannot show it. Checked after log checks 2 and 3, on records first and then other inputs | Yes |
| A6 | `head` in `replay` | The chain head of the whole log, whatever the checkpoints | Yes |
