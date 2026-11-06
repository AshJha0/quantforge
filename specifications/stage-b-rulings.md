# Stage B rulings and oracle coverage

Spec version 1.0.0. Normative: this page is part of every stage B spec, and wins where it is more exact. Cases are in `datasets/golden/stage_b/rulings_b.json`.

## Rulings

| # | Point | Ruling | Case |
|---|---|---|---|
| B0 | `spot` when `as_of` is not a business day | `add_business_days(as_of, lag)`, in all rates specs. The first version of `ois-curves.md` adjusted first; that was wrong, by QuantLib's `MakeOIS` | `ois_deep` |
| B1 | Every schedule date dropped | Empty `periods`, not an error | Yes |
| B2 | `payment_lag` | Negative: `E_INPUT`. Above 30,000: `E_LIMIT` | Yes |
| B3 | Empty `pillars` | `E_INPUT`, like empty quotes. The schema no longer sets a minimum. With one pillar, extrapolation uses the node at `as_of` as the previous one | Yes |
| B4 | `rates.curve.forward` with a `day_count` needing conditional inputs | `E_SCHEMA`, as they cannot be given | Yes |
| B5 | The 100 quote and pillar limit | Applies to every curve and quote list in any operation, `fx.*` and `calib.curve_report` included | Yes |
| B6 | `rates.ois.compound` | Empty arrays: `E_INPUT`. `denominator` other than 360 or 365: `E_SCHEMA`, as G5 | Yes |
| B7 | `fx.curve.implied` tenors | `M` and `Y` only, else `E_SCHEMA`. Out of order: `E_INPUT` | Yes |
| B8 | `fx.*` with a curve whose `as_of` differs | `E_INPUT`. A silent mismatch misprices | Yes |
| B9 | Value date before spot in any `fx.*`; `near_date >= far_date` | `E_DATE_ORDER` | Yes |
| B10 | `snapshot_id` | Optional on every operation that returns a `valuation` | Yes |
| B11 | `calib.fit` | `max_iter < 1`, `lower` above `upper`, wrong length of `prior`, `weights` or bounds: `E_INPUT`. All length checks come before domain checks. A `start` outside the bounds is projected on the box | Yes |
| B12 | `calib.fit` model and method | `ROSENBROCK` and `NELSON_SIEGEL` run with any method; "not used" in the spec describes the cases only. `x`, `y` may be left out for `ROSENBROCK`, and `weights` do not apply to it | Yes |
| B13 | `hedge.solve` | Order: lengths and shape (ragged or empty `a`: `E_INPUT`), then domain (non-positive weight: `E_DOMAIN`), then `E_SINGULAR`. Any exact method. An iterative one that fails: `E_NO_CONVERGENCE` | Yes |
| B14 | `usecase.rates_hedge` | Above 20 `hedge_tenors`: `E_LIMIT`. Dependent hedges: `E_SINGULAR`. Bumped curves may be shared | Yes |
| B15 | `add_money` with a 19-digit sum | Written in full. The digit limit is on inputs | Yes |
| B16 | Solve method where no `method` input exists | Either: both give one curve | No |
| B17 | `curve_report` diagnostics | `inputs` lists tenors, as stage B quotes carry no timestamps. `tolerance_breaches` is an array. `condition_number` must hold to 1e-4 relative: eigenvalues of `J^T J` serve only below about 1e7 | No |
| B18 | Order in `rates.ois.bootstrap` checks | All are `E_INPUT`, so order cannot be seen | No |
| B19 | FRA `start_months` | Integer from 0 to 1200, else `E_INPUT`. 0 is a spot-starting FRA. Within range, a date past the calendar is `E_DATE_RANGE`, as for `months` and `tenor_months` | Yes |
| B20 | Order of checks in `fx.*` | After `E_SCHEMA` and `E_LIMIT`: `spot`, each curve's own checks, the `as_of` match, then value dates | Yes |
| B21 | `fx.curve.implied` `points` | A quote list, so the limit of 100 applies | Yes |
| B22 | A non-finite objective in `calib.fit` | See below | Yes |
| B23 | `newton` bracket when `f(a)` or `f(b)` is exactly 0 (completes R3) | An end point with `f` exactly 0 stays in the bracket: the bracket shrinks from the other end, by the sign of that end's `f` | Yes |
| B24 | `E_LIMIT` and work already done | The array limit must be checked before an operation does work beyond one linear pass. Running the operation and dropping its result is not allowed: an oversized `rolling` costs `n` x `window`, and the input size has no bound. A build needs a schema pass, then the limit, then the work. Not visible in a result, only in time, so no golden case | No |

## Non-finite values in `calib.fit`

After input checks, project `start` on any bounds, then evaluate the objective there. If it is NaN or infinite, or an intermediate value overflows: `E_NON_FINITE`, at once, with no iteration. So BFGS, or any method, from `[-1.2e300, 1.0]` on `ROSENBROCK` is `E_NON_FINITE`. A language whose power operator raises on overflow must turn that into this code, not a crash.

From a finite start, a trial point with a non-finite objective is a failed step: it is rejected and the step shortened. A non-finite gradient at an accepted point is `E_NON_FINITE`. If no acceptable step can be found: `E_NO_CONVERGENCE`. Which of these a run meets depends on its path, so golden cases cover only the non-finite start.

## Oracle coverage

"Outside" means a library not written here. Replay and hand sources share an author with the spec, so can share a misreading.

| Suite | Outside oracle | Hand or self-consistency only |
|---|---|---|
| `units` | Python `decimal`; Strata source for SONIA, SOFR | FX and `USD-TERM-3M` records |
| `schedule`, `schedule_deep` | QuantLib; Strata where equal (see `verified_by`) | Payment dates |
| `curve`, `curve_deep` | QuantLib, except `LINEAR_ZERO` extrapolation | Forward |
| `ois`, `ois_deep` | QuantLib curves and PVs; Strata pricer on PVs | Bid/ask mid, compounding (exact rationals) |
| `projection`, `projection_deep` | QuantLib pillars, swaps, FRAs | Tenor basis. FRA in the first suite. Dates from a non-business `as_of` |
| `risk`, `risk_deep` | QuantLib with bumped quotes (`risk_deep`) | `risk.cashflows`; `risk` |
| `fx`, `fx_deep` | QuantLib calendars; `FxSwapRateHelper` for implied ratios | Forward, PV, delta, basis: analytic formulas |
| `hedge`, `hedge_deep` | SciPy L-BFGS-B (`hedge_deep`) | Enumeration and first-order conditions |
| `calibration` | SciPy, NumPy | Closed forms, known truth |
| `usecases` | None directly | Replay of parts checked elsewhere |
| `rulings_b` | None | Hand, by nature |

`oracle/MUTANTS.md` lists the deliberate convention errors. `gen_stage_b_deep.py` stops if a suite's tolerance would let one through. That proves each named error is caught, not that every plausible one is. `calibration`, `units`, `usecases` and `rulings_b` have no mutants. Stage B quotes are synthetic throughout, so an outside oracle here means agreement on method, not fit to a market.
