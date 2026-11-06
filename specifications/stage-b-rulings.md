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

`oracle/MUTANTS.md` lists the deliberate convention errors. `gen_stage_b_deep.py` stops if a suite's tolerance would let one through. That proves each named error is caught, not that every plausible one is. `calibration`, `units`, `usecases` and `rulings_b` have no mutants.
