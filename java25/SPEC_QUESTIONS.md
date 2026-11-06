# Spec questions from the Java stage A build

Written from the specs alone. Where a spec and a golden case disagree, this build follows the spec text.

## Resolved by the spec corrections on `stage-a` (363e5a8)

1. `add_tenor` end-of-month on a non-business date: `calendars.md` now gives the rule, and the code follows it.
2. `THIRTY_E_360_ISDA` with `start == end`: `daycount.md` confirms 0. The build already returned 0.
3. diff_linalg-0006 limit at the rounding noise: `differentiation-and-linalg.md` now sets limits that accept any
   correct form of `f`. `poly5` stays as `Math.pow`, which was changed after seeing the old failure.

The choices once listed here for silent points are now settled by `specifications/01-core/rulings.md`, and the
code follows those rulings.

## Closed by rulings A1 to A6 and `limits.md` (3737bb5)

| # | Point | Outcome |
|---|---|---|
| 4 | `sequence < 1` or empty `series_id` | Closed: `E_SCHEMA` (A1) |
| 5 | "Before anything else" in the store's log checks | Closed: the contract's order holds (A2), and the code changed |
| 6 | Chain keeps every record key | Closed: confirmed (A3) |
| 7 | Lone surrogate in a record | Closed: `E_SCHEMA` (A4), and the code changed. No golden case yet, so this is untested by the runner |
| 8 | `replay` `head` | Closed: confirmed (A6) |
| 9 | `skip` near 2^53 | Closed: `E_LIMIT` above 10,000,000 in `rng` and `sobol` |

## Closed by rulings B1 to B5 (bb663d6)

| # | Point | Outcome |
|---|---|---|
| 10 | Nesting beyond the parser's threshold | Closed: a lexical scan runs before parsing (B2), and the parser's own limit is gone |
| 11 | "No work is started" and the array limit | Closed: `limits.md` now allows one linear pass over input already read |
| 12 | `document_text` over the byte limit | Closed: tested first, without parsing (B1), and the code changed |
| 13 | limits-0011 depended on rounding | Closed: the case was replaced. The 10,000,000-call limit stays in the code as a backstop with no golden case |

## Open points

None.

## Stage B: choices where the spec is silent

No golden conflict was found in stage B. No golden case is known to decide these.

| # | Place | Choice |
|---|---|---|
| 14 | Swap schedules in `projection-and-fra.md`, and `rates.basis.spread` | `end_of_month` false. `ois-curves.md` sets it from `spot`, but this page does not |
| 15 | Projection `spot` | `as_of` plus 2 `USGS` business days, with no `FOLLOWING` step first, as the page says. `ois-curves.md` adjusts first, so the two differ when `as_of` is a holiday |
| 16 | `DEPOSIT`, `FRA` and `rates.fra.pv` end dates | `MODIFIED_FOLLOWING` on the unadjusted month step, with no end-of-month rule. A `FRA` end steps from its adjusted start |
| 17 | `snapshot_id` on `rates.swap.pv`, `rates.fra.pv` | Accepted as an optional input, as the text on `data_version` implies. FX valuations always give `null`, as `fx.md` lists no such input |
| 18 | `fx.forward.pv`, `fx.swap.pv` with a date before `sp` | No error, as only `fx.forward.outright` lists `E_DATE_ORDER`. A date before `as_of` is `E_OUT_OF_RANGE` from the curve |
| 19 | `fx.curve.implied` `points` out of order | `E_INPUT`. `D` and `W` tenors are accepted, though the spec says months |
| 20 | `fx.*` `as_of` differing from a curve's `as_of` | Not checked |
| 21 | `rates.curve.forward` `day_count` needing extra inputs (`BUS_252`, `ACT_365L`, `ACT_ACT_ICMA`, `THIRTY_E_360_ISDA`) | `E_SCHEMA`, as a needed input cannot be given |
| 22 | `hedge.solve` order of checks | Length, then domain (`weights`, `costs`, `lambda`), then `E_SINGULAR`. Non-positive `weights` is `E_DOMAIN`; no code is named |
| 23 | `schedule.generate`, negative `payment_lag` | `E_INPUT`. Above 30,000 is `E_LIMIT`, following `add_business_days` |
| 24 | `rates.ois.compound` with empty arrays | `E_INPUT` |
| 25 | `calib.fit`, `ROSENBROCK` with other methods, `NELSON_SIEGEL` with `GAUSS_NEWTON` | Allowed; the spec says only that they are not used. An all-empty problem has zero gradient and returns `start` |
| 26 | `calib.fit`, `lower` above `upper`, or bounds of the wrong length | `E_INPUT` |
| 27 | `calib.curve_report`, required diagnostic "inputs with their timestamps" | Reports the quote count only, as stage B quotes carry no timestamps |
| 28 | `calib.curve_report`, condition number | From the eigenvalues of `J^T J`, so it loses accuracy above about 1e8 |
| 29 | `usecase.*`, `hedge_tenors` length | Above 20 is `E_LIMIT`, following `hedge.solve` |
| 30 | `risk.ois.dv01`, `calib.curve_report` and `usecase.rates_hedge` solve method | `SEQUENTIAL`, as these operations take no `method` |

## Small document points

- `Normal.java` does not use `erfc` (ruling S5 allows this). It works directly in `x`, because
  `x/sqrt(2)` and a rounded `x^2` alone cost about 1e-13 relative at `x = -37`, over the 1e-14 target.
