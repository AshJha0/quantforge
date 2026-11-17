# Review request: Funding curve (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage F). Evidence line from the project's status table: 3 golden cases for `rates.funding.curve`, 3 with an outside library in `verified_by`.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. QuantLib has no funding-curve object. Round 2 (2026-11-18) builds it from QuantLib objects: the OIS `DiscountCurve`, `InterestRate(rate, Actual360, Simple)` for the funding discount factors, and a log-linear ratio curve P_f / D_ois whose continuous forwards are the spreads (`oracle/python/outside_f.py`, row FUND.RATIO, classed library-object by `tools/outside_shares.py`). All 3 cases agree at their own tolerance. The decomposition follows the spec's own formula, so this checks the arithmetic and the conventions (ACT/360 simple quotes, piecewise-flat spread, last spread held), not an independent model. Accept?

## Spec

### `specifications/02-curves/joint-solve-and-funding.md`

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
- Newton stops at `max |R| < 1e-13`; a singular `dR/dx` (reciprocal condition below 1e-14) at an iterate, or 50 iterations without convergence, is `E_NO_CONVERGENCE` (ruling F-40). The four-curve case (ruling F-40) and `joint_f-0004` (ruling R6-10.4) are judged in class `jacobian_piecewise`, and every F-25 zero must be exactly 0 (runner `exact_zero`).
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


## Golden cases (3 of 3 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"joint_f-0009","operation":"rates.funding.curve","inputs":{"discount":{"as_of":"2026-11-09","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-12-09","discount_factor":0.9964719915229288},{"date":"2027-02-08","discount_factor":0.9894600482880679},{"date":"2027-05-10","discount_factor":0.9796660196827617},{"date":"2027-11-09","discount_factor":0.9617507091463667},{"date":"2028-11-08","discount_factor":0.9296008300257927},{"date":"2031-11-09","discount_factor":0.8385371122969089}]},"quotes":[{"end":"2027-02-08","rate":0.0472},{"end":"2027-05-10","rate":0.0465},{"end":"2027-11-09","rate":0.0452},{"end":"2028-11-08","rate":0.0441},{"end":"2031-11-09","rate":0.0447}],"dates":["2026-11-09","2027-02-07","2027-05-08","2027-08-06","2027-11-04","2028-02-02","2028-05-02","2028-07-31","2028-10-29","2029-01-27","2029-04-27","2029-07-26","2029-10-24","2030-01-22","2030-04-22","2030-07-21","2030-10-19","2031-01-17","2031-04-17","2031-07-16","2031-10-14","2032-01-12","2032-04-11","2032-07-10","2032-10-08","2033-01-06","2033-04-06","2033-07-05","2033-10-03","2034-01-01","2034-04-01","2034-06-30","2034-09-28","2034-12-27","2035-03-27","2035-06-25","2035-09-23","2035-12-22","2036-03-21","2036-06-19","2036-09-17","2036-12-16","2037-03-16","2037-06-14","2037-09-12","2037-12-11","2038-03-11","2038-06-09","2038-09-07","2038-12-06"]},"expected":{"status":"ok","outputs":{"spreads":[0.005072321221332008,0.005728094713884744,0.006214967196705877,0.006841330425406059,0.005196674683710485],"pillars":[{"date":"2027-02-08","discount_factor":0.9882095619157212},{"date":"2027-05-10","discount_factor":0.9770316151146792},{"date":"2027-11-09","discount_factor":0.9561803781162184},{"date":"2028-11-08","discount_factor":0.9179154140945911},{"date":"2031-11-09","discount_factor":0.8151764109684703}],"discount_factors":[1.0,0.9883377028815381,0.9772759201252367,0.9669486393606708,0.9567441272900102,0.947129262340419,0.9376390956182055,0.9282440196803193,0.9189430817239777,0.9099966882366035,0.9011697484861272,0.8924284297784146,0.8837719015919977,0.8751993414614401,0.8667099348991955,0.858302875318221,0.8499773639553437,0.8417326097953682,0.8335678294959227,0.8254822473130315,0.8174750950274119,0.8095456118714843,0.8016930444570917,0.7939166467039178,0.7862156797686034,0.7785894119745465,0.7710371187423855,0.7635580825211565,0.7561515927201178,0.7488169456412352,0.741553444412325,0.7343603989208408,0.7272371257483075,0.7201829481053873,0.713197195767579,0.7062792050115375,0.6994283185520143,0.6926438854794068,0.6859252611979161,0.6792718073643023,0.6726828918272348,0.6661578885672325,0.6596961776371828,0.6532971451034414,0.6469601829875012,0.6406846892082283,0.6344700675246564,0.628315727479339,0.6222210843422479,0.6161855590552183]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["analytic","independent-replay","quantlib-1.44-funding"]}
{"case_id":"joint_f-0010","operation":"rates.funding.curve","inputs":{"discount":{"as_of":"2026-11-09","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-12-09","discount_factor":0.9964719915229288},{"date":"2027-02-08","discount_factor":0.9894600482880679},{"date":"2027-05-10","discount_factor":0.9796660196827617},{"date":"2027-11-09","discount_factor":0.9617507091463667},{"date":"2028-11-08","discount_factor":0.9296008300257927},{"date":"2031-11-09","discount_factor":0.8385371122969089}]},"quotes":[{"end":"2026-12-09","rate":0.0485},{"end":"2027-11-09","rate":0.044},{"end":"2029-11-08","rate":0.041}],"dates":["2026-11-09","2027-02-07","2027-05-08","2027-08-06","2027-11-04","2028-02-02","2028-05-02","2028-07-31","2028-10-29","2029-01-27","2029-04-27","2029-07-26","2029-10-24","2030-01-22","2030-04-22","2030-07-21","2030-10-19","2031-01-17","2031-04-17","2031-07-16","2031-10-14","2032-01-12","2032-04-11","2032-07-10","2032-10-08","2033-01-06","2033-04-06","2033-07-05","2033-10-03","2034-01-01","2034-04-01","2034-06-30","2034-09-28","2034-12-27","2035-03-27","2035-06-25","2035-09-23","2035-12-22","2036-03-21","2036-06-19","2036-09-17","2036-12-16","2037-03-16","2037-06-14","2037-09-12","2037-12-11","2038-03-11","2038-06-09","2038-09-07","2038-12-06"]},"expected":{"status":"ok","outputs":{"spreads":[0.006074506381101577,0.0045166289574181985,0.002772472509434289],"pillars":[{"date":"2026-12-09","discount_factor":0.9959746026476325},{"date":"2027-11-09","discount_factor":0.9572940488219963},{"date":"2029-11-08","discount_factor":0.8891194013262697}],"discount_factors":[1.0,0.988346573539367,0.9775749108771151,0.9676470252439346,0.95783617036981,0.9491313072122466,0.9405642562702631,0.9320745332609741,0.9236614402068362,0.9152572562372846,0.9069212379417817,0.8986611427821505,0.8904762792624809,0.8823659621848974,0.874329512592199,0.8663662577110192,0.8584755308955051,0.8506566715715084,0.8429090251812859,0.8352319431287027,0.827624782724935,0.820086907134667,0.8126176853227782,0.8052164920015163,0.7978827075781508,0.7906157181031035,0.7834149152185526,0.7762796961075022,0.769209463443319,0.7622036253397256,0.7552615953012516,0.7483827921741341,0.7415666400976673,0.7348125684559929,0.7281200118303325,0.7214884099516515,0.714917207653758,0.7084058548268249,0.7019538063713393,0.6955605221524679,0.68922546695484,0.6829481104377423,0.6767279270907204,0.670564396189586,0.6644570017528243,0.6584052324983989,0.6524085818009489,0.646466547649377,0.6405786326048241,0.6347443437590248]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["analytic","independent-replay","quantlib-1.44-funding"]}
{"case_id":"joint_f-0011","operation":"rates.funding.curve","inputs":{"discount":{"as_of":"2026-11-09","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-12-09","discount_factor":0.9964719915229288},{"date":"2027-02-08","discount_factor":0.9894600482880679},{"date":"2027-05-10","discount_factor":0.9796660196827617},{"date":"2027-11-09","discount_factor":0.9617507091463667},{"date":"2028-11-08","discount_factor":0.9296008300257927},{"date":"2031-11-09","discount_factor":0.8385371122969089}]},"quotes":[{"end":"2027-02-08","rate":0.04214067292471918},{"end":"2027-11-09","rate":0.03922568250426521},{"end":"2031-11-09","rate":0.03796226831673411}]},"expected":{"status":"ok","outputs":{"spreads":[0.0,0.0,0.0],"pillars":[{"date":"2027-02-08","discount_factor":0.9894600482880679},{"date":"2027-11-09","discount_factor":0.9617507091463667},{"date":"2031-11-09","discount_factor":0.8385371122969089}],"discount_factors":[]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["analytic","quantlib-1.44-funding"]}
```

## Outside-library evidence and limits (from the project's own page)

3 golden cases with status ok in `datasets/golden/stage_f` for `rates.funding.curve`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| rates.funding.curve: analytic, independent-replay, quantlib-1.44-funding | 2 |
| rates.funding.curve: analytic, quantlib-1.44-funding | 1 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free funding spreads. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

None found by operation name.
