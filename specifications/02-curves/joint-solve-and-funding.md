# Joint multi-curve solve, calibrated turns, futures-fitted meeting steps, funding curve

Spec version 1.0.0. Status: Specified (stage F, plan items Q4 and the stage F funding curve). Rulings: `stage-f-rulings.md` F-24 to F-27. Suite `stage_f/joint_f`.

**Plain idea.** A desk does not build its curves one after another and hope. It solves them together: the OIS discount curve, the term projection curve that discounts on it, and the cross-currency curve that needs both currencies, as one system of equations with one unknown per instrument. The same solve gives the sensitivity of every curve point to every quote (the Jacobian), which risk needs. Year-end funding pressure (the turn) is solved from the quotes that span it, not typed in, and the front of the curve steps on central-bank meeting dates, fitted to SOFR futures after their convexity adjustment.

Every instrument and curve here is one that stage B or D already defines; this page only joins them. Instrument formulas are not repeated:
- OIS swaps: `ois-curves.md` (periods, legs, par rate).
- Term deposits, FRAs and swaps on `USD-TERM-3M`: `projection-and-fra.md`, discounting on the named OIS curve.
- Cross-currency basis swaps (constant notional, synthetic, ruling R1-1): `cross-currency.md`.
- Futures convexity: `futures-convexity.md` (Hull-White, QuantLib's `convexityBias`).
- Interpolations, jumps and the curve object: `curve-framework.md`, including the stage F methods.
- Step curves: `meeting-steps.md`.

## `rates.curve.joint_solve`

### Inputs

- `as_of`.
- `curves`: an array in dependency order (a curve may only name curves before it, else `E_INPUT`). Each has a unique `name` and a `type`:
  - `OIS`: `convention` (`SOFR`, `SONIA`, `ESTR`), `interpolation` (with `tension`, `step_end` when that method needs them), optional `jumps` (fixed), optional `turns` (`[{date}]`, factors solved).
  - `OIS_STEPS`: `convention`, `step_dates` (strictly increasing, after `as_of`), optional `jumps`, optional `turns`. The instantaneous forward is `base_rate` before the first step date and `step_rates[j]` from step date `j` on (`meeting-steps.md`).
  - `PROJECTION`: `index` (`USD-TERM-3M`), `discount` (the name of an `OIS` or `OIS_STEPS` curve), `interpolation` (and its options).
  - `XCCY`: `domestic` and `foreign_projection` (names of OIS curves), `domestic_convention`, `foreign_convention`, `start`, `interpolation`. The curve solved is the foreign discount curve of `cross-currency.md`.
- `instruments`: an array; each has a unique `id`, a `curve` (the name of the curve it calibrates) and the quote keys of its type:

| `type` | Curve types | Keys | Model value (residual = model minus quote) |
|---|---|---|---|
| `OIS` | `OIS`, `OIS_STEPS` | `tenor`, `rate` | par rate (`ois-curves.md`) |
| `FUTURE` | `OIS`, `OIS_STEPS` | `start`, `end`, `price`, `sigma`, `mean_reversion` | `(D(start)/D(end) - 1) / alpha` with `alpha = (end - start)/360` days, against `futures_rate - convexity` from `futures-convexity.md` with `start_years = (start - as_of)/365`, `end_years = (end - as_of)/365`, `futures_rate = (100 - price)/100` |
| `DEPOSIT`, `FRA`, `SWAP` | `PROJECTION` | as `rates.projection.bootstrap` | as there, discounting on the curve's `discount` |
| `XCCY` | `XCCY` | `months`, `spread` | the foreign leg value `L_foreign` per unit notional (quote 0 is implied: the residual is `L_foreign` itself; the quote is `spread`) |

- Instruments may carry `"turn": true` (rules below).

### Unknowns (ruling F-24)

- `OIS`, `PROJECTION`, `XCCY`: one pillar per instrument without `"turn": true`, at its last date (OIS: last payment date; projection: as stage B; xccy: the last schedule date; futures: `end`). Pillar dates must strictly increase in instrument order within a curve, else `E_INPUT`. The unknown is `ln D` at the pillar.
- `OIS_STEPS`: `base_rate` and one rate per step date; its instruments must number `1 + len(step_dates)` plus its turns, else `E_INPUT`.
- Each turn: the unknown is `ln factor` of a jump at its date (`curve-framework.md`: a factor applies to dates strictly after it). A curve with `k` turns must have exactly `k` instruments with `"turn": true`, else `E_INPUT`. A turn instrument gives no pillar; it is the quote that pins the turn (typically a short OIS or future that spans the turn date).
- A system that is not square is `E_INPUT` (it cannot be by the rules above, but a build checks it).

Unknown order (it is the row order of the Jacobian): curves in input order; within a curve, pillars (or `base_rate` then step rates) in order, then turns in date order. Labels: `<name>:pillar:<date>`, `<name>:base`, `<name>:step:<date>`, `<name>:turn:<date>`.

### Solve

All residuals together, by Newton or any proven method, until every residual is at most 1e-13 in absolute value (rates and spreads as decimals; xccy leg value per unit notional), else `E_NO_CONVERGENCE`. Starting point: flat curves at the first quote of each curve, steps at `base_rate`, turn factors 1. Because a curve's residuals depend only on its own unknowns and those of curves before it, `dR/dx` is block lower triangular, and a build may solve block by block (ruling F-25); the result is the same solution. Within a block nothing is triangular when the curve uses a non-local interpolation (`MONOTONE_CONVEX`, `MONOTONIC_LOG_CUBIC`, `TENSION_SPLINE`, `HYBRID`): a later quote moves earlier pillars, and the Jacobian has entries above its diagonal (ruling R6-1.1).

### Outputs

- `curves`: one entry per curve in input order: `{name, pillars: [{date, discount_factor}]}` (`discount_factor` the full `D`, jumps and turns included) for pillar curves; `{name, base_rate, step_rates}` for `OIS_STEPS`.
- `turn_factors`: `[{curve, date, factor}]` in unknown order.
- `jacobian`: `{unknowns: [labels], quotes: [ids], matrix}` with `matrix[i][j] = d unknown_i / d quote_j` at the solution, by the implicit function theorem: `J = -(dR/dx)^{-1} (dR/dq)`. `dR/dq` is diagonal: `-1` for rate quotes; for an `XCCY` quote (the residual is the leg value with the spread inside it) it is the spread annuity `sum alpha_i D_f(e_i)` on the solved foreign discount curve; for a `FUTURE` quoted by `price` it is `0.01 e^{-z}` (the derivative of `-(futures_rate - convexity)` in `price`, with `z` from `futures-convexity.md`). Entries for an unknown of a curve and a quote of a later curve are exactly 0 (block structure, ruling F-25).
- `turn_sensitivity`: one row per turn, in turn order: `d model_j / d ln factor` for every instrument `j` (in instrument order), at the solution with all other unknowns held. On an `OIS_STEPS` curve an instrument whose dates all lie on one side of the turn date has exactly 0; on a pillar curve it may not, because the pillar unknowns are full `ln D` (ruling F-26, amended).
- Diagnostic: `max_repricing_error`, required.

### Checks, in order

After the finite rule (F-2): a curve naming an unknown or later curve, duplicate names or ids, an instrument type not allowed for its curve type: `E_INPUT`. `step_dates` or `turns` not strictly increasing or not after `as_of`: `E_INPUT`. Count rules above: `E_INPUT`. Pillars not increasing: `E_INPUT`. Instrument checks as their own operations (`sigma < 0`, `mean_reversion < 0`: `E_DOMAIN`; `end <= start`: `E_INPUT`). A solve that does not reach 1e-13: `E_NO_CONVERGENCE`.

## `rates.funding.curve`

**Plain idea.** A bank borrows unsecured at a spread over OIS. The funding curve is the OIS curve times a spread factor, `D_f(t) = D_ois(t) exp(-integral_0^t s(u) du)`, with `s` piecewise flat between quote dates; it discounts uncollateralised cash flows and is the input stage G's FVA needs.

Inputs: `discount` (an OIS curve object, any interpolation), `quotes` `[{end, rate}]` (simple ACT/360 unsecured funding rates from `as_of` to `end`, so `P_f(end) = 1/(1 + rate (end - as_of)/360)`), optional `dates`. With `t_0 = 0` and quote times `t_i = (end_i - as_of)/365`, the spread on `(t_{i-1}, t_i]` is

```
s_i = [ ln(D_ois(end_i)/P_f(end_i)) - ln(D_ois(end_{i-1})/P_f(end_{i-1})) ] / (t_i - t_{i-1})        (the i = 1 term without the second part)
```

and `s` stays at `s_n` beyond the last quote. Outputs: `spreads` (`s_i`, continuous, may be negative), `pillars` (`[{date: end_i, discount_factor: D_f}]`), `discount_factors` at `dates` (empty array when `dates` is absent). Checks: no quotes, `end` not strictly increasing or not after `as_of`: `E_INPUT`; `1 + rate (end - as_of)/360 <= 0`: `E_DOMAIN`; a date before `as_of`: `E_OUT_OF_RANGE`.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Joint Newton | quadratic: `max |R|` at least squares per iteration once below 1e-4 | the golden systems, iterations 1 to 4 | one curve: equals `rates.ois.bootstrap`; OIS + term with log-linear: equals `rates.curve.joint_bootstrap` (stage D) | stage B and D goldens |
| IFT Jacobian | exact at the solution; the bump reference converges as `h^2` (central) and `h^4` (Richardson) | `h` = 1e-4, 5e-5, 2.5e-5 on each quote | a curve's own block equals its single-curve Jacobian (`risk.curve.jacobian`, R2) | R2 goldens |
| Turn solve | as Newton | as above | turn factor 1 when the turn instrument is quoted at the no-turn par rate | constructed case |
| Funding curve | closed form | none | all funding rates equal to the OIS simple rates: spreads 0 | hand |

## Acceptance (plan Q4)

- The joint build reprices every instrument to 1e-13 (the plan asks 1e-10); goldens compare pillars, step rates and turn factors in class `interpolation`.
- Newton stops at `max |R| < 1e-13`; a singular `dR/dx` (reciprocal condition below 1e-14) at an iterate, or 50 iterations without convergence, is `E_NO_CONVERGENCE` (ruling F-40). The four-curve case is judged in class `jacobian_piecewise`, and every F-25 zero must be exactly 0 (runner `exact_zero`).
- Cross-curve Jacobian: matches bump-and-rebuild (Richardson at `h` and `h/2` on each quote, the full joint solve rebuilt each time; `h` starts at 1e-4 and is halved until the reference is kink-free and converged, ruling F-28; the four-curve monotone convex system needs a step near 1e-6, recorded in its case's `verified_by`) to `|J - ref| <= 1e-9 + 1e-6 |ref|` (policy class `jacobian`; a build that forms `dR/dx` by central differences meets it). The structural zeros are exact.
- On `OIS_STEPS` curves a turn move affects only overlapping instruments: `turn_sensitivity` is exactly 0 for every instrument that does not span the turn and nonzero for those that do. On pillar curves the goldens hold the honest column (ruling F-26, amended).
- Outside checks (rule 11.2.5): each `OIS` and `PROJECTION` curve of a log-linear or stage F interpolation is rebuilt by QuantLib 1.44 (`PiecewiseYieldCurve` with `OISRateHelper`, `DepositRateHelper`, `FraRateHelper`, `SwapRateHelper` with the exogenous discount handle) and its pillars compared; the Jacobian is compared with bump-and-rebuild through QuantLib. Cases where every output is reproduced count; `XCCY` (constant notional, synthetic), `OIS_STEPS` with futures and turns have no QuantLib builder that reproduces them and do not count.

## Sources

- [S1] Ametrano and Bianchetti (2013), as `ois-curves.md`: multiple-curve bootstrapping and the joint solve (not opened)
- [S2] Henrard, M., *Interest Rate Modelling in the Multi-curve Framework*, Palgrave Macmillan, 2014: curve calibration with the Jacobian from the implicit function theorem; turn-of-year treatment (not opened)
- [S3] Andersen and Piterbarg (2010), as `meeting-steps.md`: turn-of-year effects and meeting-date curves (not opened)
- [S4] CME Group, *Three-Month SOFR Futures* contract specifications: final settlement price 100 minus the compounded SOFR over the reference quarter (not opened)
- [S5] Burgard, C. and Kjaer, M., "Partial differential equation representations of derivatives with bilateral counterparty risk and funding costs", *Journal of Credit Risk* 7(3), 2011, 75-93 (funding spread over OIS, for the funding curve) (not opened)
- [S6] Piterbarg (2010), as `csa-and-basis.md` (not opened)
