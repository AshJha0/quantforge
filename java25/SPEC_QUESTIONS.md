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

## Stage B: closed by `stage-b-rulings.md` and the corrected specs (ddf2b18)

| # | Point | Outcome |
|---|---|---|
| 14 | `end_of_month` on projection schedules | Closed: false, as built |
| 15 | Spot on a non-business `as_of` | Closed: counts from `as_of` everywhere (B0). The OIS code changed |
| 16 | FRA and deposit end dates | Closed: as built |
| 17 | `snapshot_id` | Closed: optional wherever a `valuation` is returned (B10). The FX code changed |
| 18 | FX dates before spot | Closed: `E_DATE_ORDER`, and `near_date >= far_date` too (B9). The code changed |
| 19 | `fx.curve.implied` tenors | Closed: `M` and `Y` only (B7). The code changed |
| 20 | FX curve `as_of` | Closed: `E_INPUT` (B8). The code changed |
| 21 | `rates.curve.forward` `day_count` | Closed: `E_SCHEMA` (B4) |
| 22 | `hedge.solve` order | Closed: as built (B13). A descent that fails is now `E_NO_CONVERGENCE` |
| 23 | `payment_lag` | Closed: as built (B2) |
| 24 | Empty `compound` arrays | Closed: as built (B6) |
| 25 | `calib.fit` model and method | Closed: any pairing (B12). `x`, `y` may be left out for `ROSENBROCK`, and weights do not apply to it. The code changed |
| 26 | `calib.fit` checks | Closed (B11). Length checks now come before domain checks, and `max_iter < 1` is `E_INPUT` |
| 27 | `curve_report` inputs | Closed: tenors, and `tolerance_breaches` is an array (B17). The code changed |
| 28 | Condition number accuracy | Closed: now from singular values by one-sided Jacobi (B17) |
| 29 | `hedge_tenors` limit | Closed: as built (B14) |
| 30 | Solve method | Closed: either (B16) |

## Closed by rulings B19 to B24 (9615ef5)

| # | Point | Outcome |
|---|---|---|
| 31 | FRA `start_months` | Closed: 0 to 1200 (B19), as built |
| 32 | `fx.*` order of checks | Closed: as built (B20) |

The table in `stage-b-followups.md` marks B24 as ok for Java, but `quantile`, `interp.evaluate`, `monotone_convex` and
`check_quotes` could do more than one linear pass before the array limit was raised. They now gate first. Operations
without a gate make one linear pass at most, as `limits.md` allows.

## Open points

None.

## Small document points

- `Normal.java` does not use `erfc` (ruling S5 allows this). It works directly in `x`, because
  `x/sqrt(2)` and a rounded `x^2` alone cost about 1e-13 relative at `x = -37`, over the 1e-14 target.

## Stage C

Points the spec leaves open, with what Java does. None changes a golden.

| # | Point | Java |
|---|---|---|
| C-1 | `SPOT` convention with `scale` null | Closed: `E_INPUT` (C15) |
| C-2 | `vol.smile.rr_bf` with `delta <= 0` | `E_DOMAIN`, after the vol checks |
| C-3 | `risk.vol.surface_vega`: a position's `forward`, `strike`, `discount_factor` or `expiry_years` `<= 0` | `E_DOMAIN`, as no check is listed |
| C-4 | `usecase.vol_surface`: order of checks, and `strike` or `quantity <= 0` on `target` | Curve checks, then `E_DOMAIN` on target, then slices; a target expiry that is no slice's is `E_INPUT` after the fits |
| C-5 | `vol.ssvi.calibrate`: `thetas` checks against the point count | Point count and ragged rows first |

## Stage D wave 1 (D1 rates core)

| # | Point | Reading taken |
|---|---|---|
| D-1 | `stage_b/ois.json` case `ois-0023` expects `ESTR` bootstrap to be `E_SCHEMA`; `ois-curves.md` 1.1.0 now accepts `ESTR` | Follows the stage D spec, so the runner shows this one case failing. Skipped in `GoldenSuiteTest` as superseded. Needs the oracle to retire or update the case (Rust noted the same) |
| D-2 | Order of a curve's `jumps` checks against its pillar checks | Pillars first, then jumps. In `rates.ois.bootstrap` jumps come first, as its check list says |
| D-3 | Within `jumps`: a bad date and a bad factor in one list | All dates checked first (`E_INPUT`), then all factors (`E_DOMAIN`) |
| D-4 | `rates.ois.fit_steps` with empty `step_dates` | `E_INPUT` by ruling D12 (a date list), after the length check. `steps: []` in `rates.ois.step_curve` is allowed: it is not a date list, and gives a flat curve |
| D-5 | `rates.ois.compound_dated` with a lookback or shift that runs past 2000 to 2099 | `E_DATE_RANGE`, from the calendar range, so a huge `shift_days` cannot loop |
| D-6 | Convention that is a known non-overnight record (`USD-TERM-3M`, an FX pair) vs an unknown id, in `compound_dated` and `fit_steps` | Known non-overnight: `E_INPUT`; unknown: `E_SCHEMA` |
| D-7 | `rates.csa.discount`: two forwards on one date | `E_INPUT`, after the `E_DOMAIN` checks. A date equal to `as_of` still needs its own forward |
| D-8 | `calib.curve.robust` when the points cannot fix the three betas (e.g. one maturity repeated) | `E_SINGULAR` from the linear solve; the spec lists no code for it |
| D-9 | `rates.curve.joint_bootstrap` `GLOBAL` | Global Newton on the OIS block, then the term block on it: the system is block triangular (ruling D9), so this is the joint solution |
| D-10 | `rates.basis.ois_spread`, `rates.curve.joint_bootstrap` with `ESTR` | Accepted, as for any overnight convention |
| D-11 | `bond.spread.asset_swap` quarterly floating dates from a month-end maturity (e.g. 2031-02-28) | Plain month steps back from maturity, with no month-end rule (golden bonds_d-0041 needs this; the bond's own coupons keep the month-end rule) |
| D-12 | `bond.yield.from_price` with `clean_price <= 0` but `clean + accrued > 0` | `E_DOMAIN`, as golden bonds_d-0048; the spec text only names `clean + accrued <= 0` |
| D-13 | `bond.futures.basis` with `delivery >= maturity`, or `delivery <= settlement` | As `repo.forward`: `E_INPUT` and `E_DATE_ORDER`. Empty `bonds`: `E_INPUT` |
| D-14 | `bond.fit.nelson_siegel` `weights` of the wrong length | `E_INPUT` |
| D-15 | `credit.*` hazard `as_of` different from `trade_date` | Survival is anchored at the hazard's `as_of` (Q = 1 there); integration time counts from `trade_date`. No golden has them differ |
| D-16 | `credit.index.intrinsic`, `credit.curve.composite` weights that are negative or sum to 0 | `E_DOMAIN` for a negative weight, `E_INPUT` for a zero sum |
| D-17 | `eq.futures.basis` implied spread with no root | `E_NOT_BRACKETED` on `[-0.5, 0.5]`, as `eq.borrow.implied` |
| D-18 | `eq.trs.pv` with `end <= start`; `current_rate` given when `start >= as_of` | `E_DATE_ORDER`; a given rate is used |
