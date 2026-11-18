# Review request: SOFR OIS (minimal) (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is filed under a labelled "AI review" section of the curve's evidence checklist and checked against the repository before anything is acted on.

Stage: B. Evidence line from the project's curve table: 16 golden cases for `rates.ois.bootstrap`, 16 with an outside library in `verified_by`.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. No free SOFR swap quotes exist, so level checks against a SOFR market curve stay open.

## Spec

### `specifications/02-curves/curve-framework.md`

# Curve framework

Spec version 1.0.0. Status: Implemented.

A discount curve says what one unit paid on a future date is worth today. Everything else in stage B is built on this.

## Curve object

`{"as_of": date, "interpolation": ..., "pillars": [{"date": ..., "discount_factor": ...}]}`. Schema: `datasets/schemas/curve-input.schema.json`.

Checks: pillar dates strictly increasing and after `as_of`, else `E_INPUT`. A discount factor `<= 0`: `E_DOMAIN`. Unknown `interpolation`: `E_SCHEMA`. An implied node at `as_of` has value 1.

Curve time is always `t = (date - as_of) / 365`, whatever the instrument's day count.

| `interpolation` | Between nodes `i`, `i+1`, with `u = (t - t_i)/(t_{i+1} - t_i)` |
|---|---|
| `LOG_LINEAR_DF` | `D = exp((1-u) ln D_i + u ln D_{i+1})` |
| `LINEAR_ZERO` | `D = exp(-z t)`, `z = (1-u) z_i + u z_{i+1}`, `z_i = -ln(D_i)/t_i`. The node at `as_of` takes `z_1`, so the first segment is flat in zero rate |

**Jumps (stage D).** The curve object may carry `jumps`: `[{"date", "factor"}]`, dates strictly increasing and after `as_of` (else `E_INPUT`), `factor > 0` (else `E_DOMAIN`). Absent means none; `null` is `E_SCHEMA`. Then `D(d) = S(d) * J(d)`, with `J(d)` the product of the factors whose date is strictly before `d`. Pillars hold the full `D`; interpolation and extrapolation act on `S = D/J`. A turn of year is a jump on the last business day of the year: `factor = exp(-s n/365)` for a spread `s` over `n` days. This is QuantLib's jump rule.

**Extrapolation.** Beyond the last pillar, the forward of the last segment carries on: `D = D_n exp(-f (t - t_n))`, with `f = -ln(D_n/D_{n-1})/(t_n - t_{n-1})`, for both methods. Before `as_of`: `E_OUT_OF_RANGE`.

## Operations

`rates.curve.discount`. Inputs: `curve`, `dates`. Outputs: `discount_factors`, `zero_rates` (`-ln(D)/t`, continuous; `null` at `as_of`).

`rates.curve.forward`. Inputs: `curve`, `start`, `end`, `day_count`. Output: `forward`, simple: `(D(start)/D(end) - 1)/alpha`. `end <= start`: `E_DATE_ORDER`.

## Dependencies

A curve may need another: a projection curve needs a discount curve. Build order is the dependency order, and a cycle is `E_INPUT`. In stage B the order is overnight curve, then projection, then FX.

## Limits of this stage

Monotone-convex and spline curves plug into the same object later. Curve serialisation beyond this object, and curve versioning, ride on `snapshot_id`.

## Acceptance

Class `interpolation`. Oracle: hand replay, and QuantLib `DiscountCurve` for `LOG_LINEAR_DF`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Interest Rates" (zero rates, discount factors, forward rates) (not opened)
- [S2] Hagan, P. S. and West, G., "Interpolation methods for curve construction", *Applied Mathematical Finance* 13(2), 2006, 89-129 (not opened)

## Stage F: pluggable interpolation (plan item Q1)

Spec version 1.1.0 for this section. Rulings: `stage-f-rulings.md` F-18 to F-22. Suite `stage_f/curve_f`. Existing curves and cases are unchanged.

Four more `interpolation` values. Each acts on the smooth curve `S = D/J` (jumps as above) at node times `t_0 = 0 < t_1 < ... < t_n` (the implied node at `as_of` with `S_0 = 1`, then the pillars), and defines `ln S(t)` and the instantaneous forward `f(t) = -d ln S/dt`. At a pillar `f` is the right-hand value. Beyond `t_n` every new method extrapolates with a flat instantaneous forward equal to the left-hand forward at the last pillar, `f(t_n-)`: `ln S(t) = ln S_n - f(t_n-) (t - t_n)` (ruling F-20; QuantLib's interpolated discount curves do the same).

### `MONOTONE_CONVEX` (Hagan-West)

The convex monotone method of Hagan and West [S2] in the form QuantLib 1.44 implements as `ConvexMonotone` with `quadraticity = 0`, `monotonicity = 1`, `forcePositive = false` (QuantLib documents that this setting reproduces the basic Hagan-West method). The data are the discrete forwards `y_i = (ln S_{i-1} - ln S_i)/(t_i - t_{i-1})`, `i = 1..n`.

1. With one pillar (`n = 1`): `f(t) = y_1` everywhere.
2. Node forwards: `f_i = (dx_i y_i + dx_{i-1} y_{i+1}) / (dx_{i-1} + dx_i)` for `i = 1..n-1`, with `dx_{i-1} = t_i - t_{i-1}` and `dx_i = t_{i+1} - t_i` (each discrete forward is weighted by the other interval's length); `f_0 = 1.5 y_1 - 0.5 f_1`; `f_n = 1.5 y_n - 0.5 f_{n-1}`. No clamping.
3. Section `i` runs from `t_{i-1}` to `t_i`. With `x = (t - t_{i-1})/(t_i - t_{i-1})` in `[0, 1]`, `g0 = f_{i-1} - y_i`, `g1 = f_i - y_i`, the first rule that applies is used:
   - (a) `|g0| < 1e-14` and `|g1| < 1e-14`: `f` linear from `f_{i-1}` to `f_i`.
   - (b) `g0 > 0` and `-2 g0 <= g1 <= -0.5 g0`, or `g0 < 0` and `-0.5 g0 <= g1 <= -2 g0`: the quadratic `f = a x^2 + b x + c`, `a = 3 f_{i-1} + 3 f_i - 6 y_i`, `b = -(4 f_{i-1} + 2 f_i - 6 y_i)`, `c = f_{i-1}`.
   - (c) `g0 < 0` and `g1 > -2 g0`, or `g0 > 0` and `g1 < -2 g0`: `eta = (g1 + 2 g0)/(g1 - g0)`. If `eta < 1`: `f = y_i + g0` for `x <= eta`, else `f = y_i + g0 + (g1 - g0) ((x - eta)/(1 - eta))^2`. If `eta >= 1`: rule (e) with `eta = 1`.
   - (d) `g0 > 0`, `g1 < 0` and `g1 > -0.5 g0`, or `g0 < 0`, `g1 > 0` and `g1 < -0.5 g0`: `eta = 3 g1/(g1 - g0)`. If `eta > 0`: `f = y_i + g1 + (g0 - g1) ((eta - x)/eta)^2` for `x <= eta`, else `f = y_i + g1`. If `eta <= 0`: rule (e) with `eta = 0`.
   - (e) otherwise: `eta = g1/(g0 + g1)` clamped to `[0, 1]`, `A = -(eta g0 + (1 - eta) g1)/2`; `f = y_i + A + (g0 - A) ((eta - x)/eta)^2` for `x <= eta`, else `f = y_i + A + (g1 - A) ((x - eta)/(1 - eta))^2`. When `eta = 0` the first piece is only the point `x = 0`, where `f = f_{i-1}` and the integral is 0 (QuantLib divides 0 by 0 there; ruling F-19).
   Every branch integrates to `y_i` over its section, so `S` returns every node exactly. `ln S(t) = -(sum of y_k (t_k - t_{k-1}) over the sections before i) - (t_i - t_{i-1}) * (integral of the bra

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

### `specifications/02-curves/ois-curves.md`

# OIS curves: SONIA, SOFR and ESTR

Spec version 1.1.0. Status: SONIA and SOFR Implemented; ESTR and jumps Specified (stage D).

An overnight indexed swap exchanges a fixed rate for daily compounded overnight rates. Its quotes pin down the discount curve.

## Periods

From `as_of` and a `tenor` (as in `calendars.md`), with convention `c` from `conventions.md`:

- `spot` = `core.calendar.add_business_days(as_of, c.spot_lag)`. Days count from `as_of` itself, even if it is not a business day, as in QuantLib (`MakeOIS`, its issue 753). So SOFR from Saturday 2026-11-07 is Tuesday 2026-11-10. A lag of 0 gives `as_of` adjusted `FOLLOWING`.
- For `D` and `W` tenors, and for tenors of `c.fixed_months` or less: one period, ending at `add_tenor(spot, tenor)` with `MODIFIED_FOLLOWING`.
- Otherwise a schedule from `spot` to `spot + tenor` (unadjusted), at `c.fixed_months`, by `schedules.md`.
- `end_of_month` is true when `spot` is on or after the last business day of its month. For one-period swaps the `add_tenor` rule gives the same thing.
- Payment `p_i` is period end `e_i` plus `c.payment_lag` business days.

## Legs

Both legs use the same periods `(s_i, e_i, p_i)`. `alpha_i` is the `fixed_day_count` fraction of `s_i` to `e_i`.

`annuity A = sum alpha_i D(p_i)`

`floating F = sum (D(s_i)/D(e_i) - 1) D(p_i)`

Plan section 8: this is the general form. The telescoped `D(s_0) - D(e_n)` holds only at zero payment lag and unit notional, and must not be used otherwise. On SOFR 10Y it is out by about 1.1e-4 per unit notional. `D(s_i)/D(e_i)` is the expected compounded growth, so no daily loop is needed on a single curve.

Par rate: `K = F / A`.

## `rates.ois.bootstrap`

Inputs: `convention` (`SONIA`, `SOFR`, `ESTR`), `as_of`, `quotes`, `interpolation`, `method` (`SEQUENTIAL` or `GLOBAL`), optional `jumps` (stage D, as in `curve-framework.md`: the solve is on the curve with those jumps, and pillars hold the full discount factor). Each quote is `{tenor, rate}` or `{tenor, bid, ask}`, which uses the mid. Output: `pillars`.

There is one pillar per quote, at the last payment date `p_n` of that swap. So a lag leaves every date the swap needs on or before its pillar.

The curve solves `K_j(curve) = quote_j` for all `j`. It is a square system with one solution in practice, so `SEQUENTIAL` (one unknown at a time, in tenor order) and the `GLOBAL` solve (Newton on all pillars together) give the same curve to solver tolerance. Both must stop with every repricing error below 1e-13. Diagnostic: `max_repricing_error`, required.

Checks, in order: a bad jump (`E_INPUT` for dates, `E_DOMAIN` for a factor), no quotes, pillars not strictly increasing, or `bid > ask`: `E_INPUT`. A solve that fails: `E_NO_CONVERGENCE`, never a silently clamped curve.

Negative rates are valid, and give discount factors above 1.

## `rates.ois.compound`

Compounded in arrears, from actual fixings. Inputs: `rates`, `days` (integers at least 1, same length, else `E_INPUT`), `denominator` (360 or 365). Output: `compounded_rate`:

`(prod(1 + r_i n_i / B) - 1) * B / sum n_i`

Dated compounding with lookback, lockout and observation shift: `overnight-compounding.md`.

## `rates.ois.pv`

Inputs: `curve`, optional `snapshot_id`, `trade`: `{convention, tenor, fixed_rate, notional, side}`, with `side` `PAY` or `RECEIVE` for the fixed rate. Periods start from the curve's `as_of`. Outputs: `valuation` (see `04-pricing/pricing-framework.md`, `model` `OIS_DISCOUNTING`, `conventions` the convention id), `par_rate`, `annuity`.

`pv = sign * notional * (F - fixed_rate * A)`, with sign +1 for `PAY`.

## Acceptance

Stage D (ESTR, SOFR at more tenors and notionals, jumps): `stage-d-targets.md`; suite `stage_d/ois_d`.


Targets are in `stage-b-targets.md`. Oracle: independent replay, QuantLib `OISRateHelper` and `OvernightIndexedSwap`. Measured: pillars within 2e-11 of QuantLib; swap PVs within 1e-5 on 1e6 against QuantLib, and through Strata's own swap pricer on the same curve (`oracle/REPORT.md`). No curve was built by Strata's calibrator.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Bank of England, *SONIA key features and policies* (opened 2026-11-07)
- [S2] Federal Reserve Bank of New York, *Additional Information about Reference Rates Administered by the New York Fed*, section "Calculation Methodology for the TGCR, BGCR, and SOFR" (opened 2026-11-07)
- [S3] European Central Bank, *The euro short-term rate (€STR) methodology and policies* (opened 2026-11-07, title from the PDF; body not read)
- [S4] ISDA, *2021 ISDA Interest Rate Derivatives Definitions*, overnight compounding Floating Rate Options for SONIA, SOFR and €STR (not opened)
- [S5] Ametrano, F. M. and Bianchetti, M., "Everything you always wanted to know about multiple interest rate curve bootstrapping but were afraid to ask", SSRN 2219548, 2013 (not opened)


## Golden cases (8 of 77 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"ois-0001","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-06","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LOG_LINEAR_DF","method":"SEQUENTIAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-11-13","discount_factor":0.9992870839543515},{"date":"2026-12-07","discount_factor":0.9968589384517443},{"date":"2027-02-08","discount_factor":0.990611714947001},{"date":"2027-05-06","discount_factor":0.9823653311701559},{"date":"2027-11-08","discount_factor":0.9660045785970438},{"date":"2028-11-06","discount_factor":0.9361852434249714},{"date":"2029-11-06","discount_factor":0.9072000992045789},{"date":"2031-11-06","discount_factor":0.8480030126521996},{"date":"2033-11-07","discount_factor":0.7879297982987687},{"date":"2036-11-06","discount_factor":0.7000251340198215},{"date":"2041-11-06","discount_factor":0.5711047135767834},{"date":"2046-11-06","discount_factor":0.4687936232412164},{"date":"2056-11-06","discount_factor":0.33728170101172816}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0002","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-06","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LOG_LINEAR_DF","method":"GLOBAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-11-13","discount_factor":0.9992870839543515},{"date":"2026-12-07","discount_factor":0.9968589384517443},{"date":"2027-02-08","discount_factor":0.990611714947001},{"date":"2027-05-06","discount_factor":0.9823653311701559},{"date":"2027-11-08","discount_factor":0.9660045785970438},{"date":"2028-11-06","discount_factor":0.9361852434249714},{"date":"2029-11-06","discount_factor":0.9072000992045789},{"date":"2031-11-06","discount_factor":0.8480030126521996},{"date":"2033-11-07","discount_factor":0.7879297982987687},{"date":"2036-11-06","discount_factor":0.7000251340198215},{"date":"2041-11-06","discount_factor":0.5711047135767834},{"date":"2046-11-06","discount_factor":0.4687936232412164},{"date":"2056-11-06","discount_factor":0.33728170101172816}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0003","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-06","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LINEAR_ZERO","method":"SEQUENTIAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-11-13","discount_factor":0.9992870839543515},{"date":"2026-12-07","discount_factor":0.9968589384517443},{"date":"2027-02-08","discount_factor":0.990611714947001},{"date":"2027-05-06","discount_factor":0.9823653311701559},{"date":"2027-11-08","discount_factor":0.9660045785970438},{"date":"2028-11-06","discount_factor":0.9361852434249714},{"date":"2029-11-06","discount_factor":0.9072000992045789},{"date":"2031-11-06","discount_factor":0.847995693755382},{"date":"2033-11-07","discount_factor":0.7879084573720267},{"date":"2036-11-06","discount_factor":0.6999509464938636},{"date":"2041-11-06","discount_factor":0.5708959617956307},{"date":"2046-11-06","discount_factor":0.46858037323623375},{"date":"2056-11-06","discount_factor":0.33747448984642}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0004","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-06","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LINEAR_ZERO","method":"GLOBAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-11-13","discount_factor":0.9992870839543515},{"date":"2026-12-07","discount_factor":0.9968589384517443},{"date":"2027-02-08","discount_factor":0.990611714947001},{"date":"2027-05-06","discount_factor":0.9823653311701559},{"date":"2027-11-08","discount_factor":0.9660045785970438},{"date":"2028-11-06","discount_factor":0.9361852434249714},{"date":"2029-11-06","discount_factor":0.9072000992045789},{"date":"2031-11-06","discount_factor":0.847995693755382},{"date":"2033-11-07","discount_factor":0.7879084573720267},{"date":"2036-11-06","discount_factor":0.6999509464938636},{"date":"2041-11-06","discount_factor":0.5708959617956307},{"date":"2046-11-06","discount_factor":0.46858037323623375},{"date":"2056-11-06","discount_factor":0.33747448984642}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0005","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-30","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LOG_LINEAR_DF","method":"SEQUENTIAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-12-07","discount_factor":0.9992870839543515},{"date":"2026-12-31","discount_factor":0.9968589384517443},{"date":"2027-02-26","discount_factor":0.9912056971787842},{"date":"2027-05-28","discount_factor":0.982556790436519},{"date":"2027-11-30","discount_factor":0.9661835748792271},{"date":"2028-11-30","discount_factor":0.936184737723126},{"date":"2029-11-30","discount_factor":0.9071996169644467},{"date":"2031-11-28","discount_factor":0.8481532478408884},{"date":"2033-11-30","discount_factor":0.788002288142405},{"date":"2036-11-28","discount_factor":0.7001603332769336},{"date":"2041-11-29","discount_factor":0.5711653644576784},{"date":"2046-11-30","discount_factor":0.46879741797306496},{"date":"2056-11-30","discount_factor":0.3372840980250744}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0006","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-30","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LOG_LINEAR_DF","method":"GLOBAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-12-07","discount_factor":0.9992870839543515},{"date":"2026-12-31","discount_factor":0.9968589384517443},{"date":"2027-02-26","discount_factor":0.9912056971787842},{"date":"2027-05-28","discount_factor":0.982556790436519},{"date":"2027-11-30","discount_factor":0.9661835748792271},{"date":"2028-11-30","discount_factor":0.936184737723126},{"date":"2029-11-30","discount_factor":0.9071996169644467},{"date":"2031-11-28","discount_factor":0.8481532478408884},{"date":"2033-11-30","discount_factor":0.788002288142405},{"date":"2036-11-28","discount_factor":0.7001603332769336},{"date":"2041-11-29","discount_factor":0.5711653644576784},{"date":"2046-11-30","discount_factor":0.46879741797306496},{"date":"2056-11-30","discount_factor":0.3372840980250744}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0007","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-30","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LINEAR_ZERO","method":"SEQUENTIAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-12-07","discount_factor":0.9992870839543515},{"date":"2026-12-31","discount_factor":0.9968589384517443},{"date":"2027-02-26","discount_factor":0.9912056971787842},{"date":"2027-05-28","discount_factor":0.982556790436519},{"date":"2027-11-30","discount_factor":0.9661835748792271},{"date":"2028-11-30","discount_factor":0.936184737723126},{"date":"2029-11-30","discount_factor":0.9071996169644467},{"date":"2031-11-28","discount_factor":0.8481459603616504},{"date":"2033-11-30","discount_factor":0.787980963679958},{"date":"2036-11-28","discount_factor":0.7000861393250918},{"date":"2041-11-29","discount_factor":0.5709564234677841},{"date":"2046-11-30","discount_factor":0.46858400139661155},{"date":"2056-11-30","discount_factor":0.3374766978131558}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0008","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-30","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LINEAR_ZERO","method":"GLOBAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-12-07","discount_factor":0.9992870839543515},{"date":"2026-12-31","discount_factor":0.9968589384517443},{"date":"2027-02-26","discount_factor":0.9912056971787842},{"date":"2027-05-28","discount_factor":0.982556790436519},{"date":"2027-11-30","discount_factor":0.9661835748792271},{"date":"2028-11-30","discount_factor":0.936184737723126},{"date":"2029-11-30","discount_factor":0.9071996169644467},{"date":"2031-11-28","discount_factor":0.8481459603616504},{"date":"2033-11-30","discount_factor":0.787980963679958},{"date":"2036-11-28","discount_factor":0.7000861393250918},{"date":"2041-11-29","discount_factor":0.5709564234677841},{"date":"2046-11-30","discount_factor":0.46858400139661155},{"date":"2056-11-30","discount_factor":0.3374766978131558}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
```

## Outside-library evidence and limits (from the project's own page)

As for SONIA: QuantLib for pillars, QuantLib and Strata's pricer for swap PVs, and Strata's calibrator not run. Target and measured gap are in `specifications/02-curves/stage-b-targets.md`.

Golden cases for `rates.ois.bootstrap` with an `ok` result and convention SOFR: 16, counted from `verified_by` in `datasets/golden/stage_b/`. All four builds passed them locally, which is self-assessment.

| Suite | Verified by | Cases |
|---|---|---|
| ois | independent-replay, quantlib-1.44 | 8 |
| ois_deep | independent-replay, quantlib-1.44 | 8 |

Limits:

- Each pillar sits at the swap's last payment date, so pillar dates fall after the plain tenor date.
- The first pillar is about two weeks out, and the segment back to the as-of date has no quote of its own.
- Log-linear interpolation gives a staircase of forwards. Exact repricing says nothing about a market.

## Real-data reconciliation

- `SOFR` (GSW (Fed staff fitted Treasury zero curve, feds200628.csv), as of 2026-11-13, 11 tenors, par rates by QuantLib 1.44 MakeOIS): **pass** at the stated 0.5 bp on all 11 pillars (0.5 bp: pass, 0.1 bp: fail, 0.01 bp: fail). Between pillars within 5 bp: no (information only).
- `SOFR-EVERY-YEAR` (GSW (Fed staff fitted Treasury zero curve, feds200628.csv), as of 2026-11-13, 34 tenors, par rates by QuantLib 1.44 MakeOIS): **pass** at the stated 0.5 bp on all 34 pillars (0.5 bp: pass, 0.1 bp: fail, 0.01 bp: fail). Between pillars within 5 bp: yes (information only).
- Method (derived): the GSW curve is a Treasury curve, not a SOFR curve, so this tests the bootstrap's mechanics on a real curve shape, not SOFR levels. The every-year set misses the 0.1 bp tier because no quote covers as_of to spot (2 business days): QuantForge interpolates that stub log-linearly from D(as_of) = 1, while the published curve has its own front-end shape. The standard set's residual comes from coupon dates between sparse pillars (7Y, 10Y, ...), where log-linear and Svensson differ.

## Rulings that name this curve's operations

- (stage-b-rulings.md) | B18 | Order in `rates.ois.bootstrap` checks | All are `E_INPUT`, so order cannot be seen | No |
