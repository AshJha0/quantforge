# Review request: Full SOFR, ESTR, SONIA OIS (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage D). Evidence line from the project's status table: 81 golden cases.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. ESTR real-data round trip not run (open).

## Spec

### `specifications/02-curves/curve-framework.md`

# Curve framework

Spec version 1.0.0. Status: Implemented, not Validated.

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
- [S2] Hagan, P. S. and West, G.

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

### `specifications/02-curves/ois-curves.md`

# OIS curves: SONIA, SOFR and ESTR

Spec version 1.1.0. Status: SONIA and SOFR Implemented, not Validated; ESTR and jumps Specified (stage D).

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

Compounded in arrears, from actual fixings. Inputs: `rates`, `days` (integers at least 1, same length, else `E_INPUT`), `denominator

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

### `specifications/02-curves/overnight-compounding.md`

# Overnight compounding by date, and IBOR fallbacks

Spec version 1.0.0. Status: Specified (stage D).

A coupon on an overnight index compounds one published fixing per business day. Market documents move the fixing window so the amount is known before payment. This spec fixes the three standard ways.

## `rates.ois.compound_dated`

Inputs: `convention` (an `OVERNIGHT` record from `01-core/conventions.md`: `SONIA`, `SOFR`, `ESTR`), `start`, `end`, `method` (`NONE`, `LOOKBACK`, `OBSERVATION_SHIFT`, `LOCKOUT`), `shift_days` (integer), `fixings`: `[{date, rate}]`.

Let `cal` be the record's calendar, except that for `SOFR` it is `USGS` with every Good Friday a non-business day: the New York Fed publishes no SOFR on Good Friday, even in the years when the bond market had an early close (none on 2021-04-02 or 2023-04-07; ruling R1-6). Let `B` its day-count denominator (`ACT_360`: 360, `ACT_365F`: 365). `d_0 = start < d_1 < ... < d_n = end` are the business days of `cal` in `[start, end]`. `back(d, k)` is `d` moved `k` business days earlier on `cal`. `r(x)` is the fixing dated `x`.

| `method` | Rate for step `i` (`0 <= i < n`) | Weight `w_i` |
|---|---|---|
| `NONE` | `r(d_i)` | `d_{i+1} - d_i` days |
| `LOOKBACK` | `r(back(d_i, k))` | `d_{i+1} - d_i` days (interest period) |
| `OBSERVATION_SHIFT` | `r(o_i)`, `o_i = back(d_i, k)` | `o_{i+1} - o_i` days (observation period) |
| `LOCKOUT` | `r(d_i)` for `i < n-k`; `r(d_{n-k})` for `i >= n-k` | `d_{i+1} - d_i` days |

`k = shift_days`. Then `growth = prod (1 + r_i w_i / B)`, `compounded_rate = (growth - 1) B / sum w_i`, `accrual = (end - start)/B`, `interest = compounded_rate * accrual`. Outputs: `compounded_rate`, `accrual`, `interest`.

`LOCKOUT` follows the ARRC rule: the rate cut-off date is `d_{n-k}`, and its fixing applies to it and every later day. QuantLib's `lockoutDays = k` locks one day earlier; this spec's `k` is QuantLib's `k-1` (ruling D3). Run the product in day order in binary64.

Checks, in order: `convention` not `OVERNIGHT`: `E_INPUT`. `end <= start`: `E_DATE_ORDER`. `shift_days < 0`; `NONE` with `shift_days != 0`; `LOCKOUT` with `shift_days < 1` or `shift_days > n-1`: `E_INPUT`. `start` or `end` not a business day of `cal`: `E_INPUT`. Two fixings on one date, or a needed fixing missing: `E_INPUT`. Extra fixings are ignored. `fixings` is not a quote list: the general array limit applies.

## `rates.fallback.rate`

The ISDA 2020 IBOR fallback: the compounded risk-free rate over the IBOR period, observation period shifted 2 business days back, plus the spread adjustment fixed on 2021-03-05.

Inputs: `ibor`, `start`, `end` (the IBOR period's value and maturity dates), `fixings`. Outputs: `compounded_rate` (as `rates.ois.compound_dated` with `OBSERVATION_SHIFT`, `shift_days` 2), `spread_adjustment`, `fallback_rate = compounded_rate + spread_adjustment`.

| `ibor` | Index | Spread adjustment |
|---|---|---|
| `USD-LIBOR-1M`, `-3M`, `-6M`, `-12M` | `SOFR` | 0.0011448, 0.0026161, 0.0042826, 0

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

### `specifications/edge-case-register.md`

# Edge-case register

Version 1.0.0, 2026-11-07. Plan 11.2.2. Maintained every stage: a stage that adds an operation adds or updates rows here before its handover.

Each row is a real-world edge case. It is either **pinned**: named golden cases that all four languages pass, or **out of scope**: with the reason and the stage that would bring it in. "All four languages" means the stage D builds in the language worktrees, checked by the spec session on 2026-11-07. New cases are in suite `stage_d/edge_d`, written by `oracle/python/gen_r1_edge.py`.

| # | Edge case | State | Golden cases | Notes |
|---|---|---|---|---|
| E1 | Negative and zero rates | Pinned | Negative yields: the `bonds_d` price cases at -0.20% (`bonds_d-0003`, `bonds_d-0007`, ...) and the `outside_d` price cases at -0.50%; near zero, the `outside_d` cases at +0.01%. Zero yield: `edge_d-0001`, `edge_d-0002`. Negative fixings: `edge_d-0003` to `edge_d-0005`. All-zero fixings: `edge_d-0006` to `edge_d-0008`. Negative zero rates on a curve (D > 1): `edge_d-0009` | Bond, compounding and curve cases are also re-priced in QuantLib (`oracle/outside_register.json`). `E_DOMAIN` only where `1 + y/f <= 0` (`bonds_d` invalid cases) |
| E2 | Month end, leap day, stub periods | Pinned | Leap-day and end-of-month maturities: `outside_d-0001` to `outside_d-0021` (2028-02-29), the 2030-04-30, 2032-08-31 and 2045-02-28 bonds in `outside_d`. Stubs: `schedule_deep-0001` to `schedule_deep-0048`. Day counts over 29 February: `daycount-0001` onwards (stage A) | Settlement on a coupon date (accrued 0): the 2033-11-09 bond in `outside_d` |
| E3 | Holiday calendar changed after trade date | Out of scope | | Calendars are rule tables in `01-core/calendars.md`, not dated versions, so a build has one calendar at a time. A change (for example a new US federal holiday) is a spec change, with goldens regenerated. Dated calendar versions belong with the as-of data store in stage K. Calendar provenance and an expiry test are in `01-core/calendar-provenance.md` |
| E4 | Missing or republished fixings (SOFR revisions) | Pinned | Missing fixing: `compound_d-0022` (`E_INPUT`). Two values for one date: `compound_d-0029` (`E_INPUT`) | A revision is a new fixings list from the caller. The library never picks between two values. Keeping both versions, with times, is the as-of store's job (`01-core/asof-store.md`, stage A suites `store`, `store_a4` and `store_rulings`) |
| E5 | US T+1 settlement (2024-05-28) | Out of scope | | No operation derives settlement from a trade date: every bond, repo and equity operation takes the settlement date as an input. A settlement-lag convention would be added with trade capture in stage F |
| E6 | IBOR cessation dates | Pinned in part | Fallback rates after cessation: `compound_d-0031` to `compound_d-0034` | The ISDA spread adjustments fixed on 2021-03-05 are pinned. Cessation dates themselves are not modelled: the caller asks for the fallback rate. Pre-cessation IBOR projection stays the s

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

## Golden cases (7 of 148 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"ois-0001","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-06","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LOG_LINEAR_DF","method":"SEQUENTIAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-11-13","discount_factor":0.9992870839543515},{"date":"2026-12-07","discount_factor":0.9968589384517443},{"date":"2027-02-08","discount_factor":0.990611714947001},{"date":"2027-05-06","discount_factor":0.9823653311701559},{"date":"2027-11-08","discount_factor":0.9660045785970438},{"date":"2028-11-06","discount_factor":0.9361852434249714},{"date":"2029-11-06","discount_factor":0.9072000992045789},{"date":"2031-11-06","discount_factor":0.8480030126521996},{"date":"2033-11-07","discount_factor":0.7879297982987687},{"date":"2036-11-06","discount_factor":0.7000251340198215},{"date":"2041-11-06","discount_factor":0.5711047135767834},{"date":"2046-11-06","discount_factor":0.4687936232412164},{"date":"2056-11-06","discount_factor":0.33728170101172816}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0002","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-06","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LOG_LINEAR_DF","method":"GLOBAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-11-13","discount_factor":0.9992870839543515},{"date":"2026-12-07","discount_factor":0.9968589384517443},{"date":"2027-02-08","discount_factor":0.990611714947001},{"date":"2027-05-06","discount_factor":0.9823653311701559},{"date":"2027-11-08","discount_factor":0.9660045785970438},{"date":"2028-11-06","discount_factor":0.9361852434249714},{"date":"2029-11-06","discount_factor":0.9072000992045789},{"date":"2031-11-06","discount_factor":0.8480030126521996},{"date":"2033-11-07","discount_factor":0.7879297982987687},{"date":"2036-11-06","discount_factor":0.7000251340198215},{"date":"2041-11-06","discount_factor":0.5711047135767834},{"date":"2046-11-06","discount_factor":0.4687936232412164},{"date":"2056-11-06","discount_factor":0.33728170101172816}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0003","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-06","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LINEAR_ZERO","method":"SEQUENTIAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-11-13","discount_factor":0.9992870839543515},{"date":"2026-12-07","discount_factor":0.9968589384517443},{"date":"2027-02-08","discount_factor":0.990611714947001},{"date":"2027-05-06","discount_factor":0.9823653311701559},{"date":"2027-11-08","discount_factor":0.9660045785970438},{"date":"2028-11-06","discount_factor":0.9361852434249714},{"date":"2029-11-06","discount_factor":0.9072000992045789},{"date":"2031-11-06","discount_factor":0.847995693755382},{"date":"2033-11-07","discount_factor":0.7879084573720267},{"date":"2036-11-06","discount_factor":0.6999509464938636},{"date":"2041-11-06","discount_factor":0.5708959617956307},{"date":"2046-11-06","discount_factor":0.46858037323623375},{"date":"2056-11-06","discount_factor":0.33747448984642}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0004","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-06","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LINEAR_ZERO","method":"GLOBAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-11-13","discount_factor":0.9992870839543515},{"date":"2026-12-07","discount_factor":0.9968589384517443},{"date":"2027-02-08","discount_factor":0.990611714947001},{"date":"2027-05-06","discount_factor":0.9823653311701559},{"date":"2027-11-08","discount_factor":0.9660045785970438},{"date":"2028-11-06","discount_factor":0.9361852434249714},{"date":"2029-11-06","discount_factor":0.9072000992045789},{"date":"2031-11-06","discount_factor":0.847995693755382},{"date":"2033-11-07","discount_factor":0.7879084573720267},{"date":"2036-11-06","discount_factor":0.6999509464938636},{"date":"2041-11-06","discount_factor":0.5708959617956307},{"date":"2046-11-06","discount_factor":0.46858037323623375},{"date":"2056-11-06","discount_factor":0.33747448984642}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0005","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-30","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LOG_LINEAR_DF","method":"SEQUENTIAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-12-07","discount_factor":0.9992870839543515},{"date":"2026-12-31","discount_factor":0.9968589384517443},{"date":"2027-02-26","discount_factor":0.9912056971787842},{"date":"2027-05-28","discount_factor":0.982556790436519},{"date":"2027-11-30","discount_factor":0.9661835748792271},{"date":"2028-11-30","discount_factor":0.936184737723126},{"date":"2029-11-30","discount_factor":0.9071996169644467},{"date":"2031-11-28","discount_factor":0.8481532478408884},{"date":"2033-11-30","discount_factor":0.788002288142405},{"date":"2036-11-28","discount_factor":0.7001603332769336},{"date":"2041-11-29","discount_factor":0.5711653644576784},{"date":"2046-11-30","discount_factor":0.46879741797306496},{"date":"2056-11-30","discount_factor":0.3372840980250744}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0006","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-30","quotes":[{"tenor":"1W","rate":0.0372},{"tenor":"1M","rate":0.0371},{"tenor":"3M","rate":0.0368},{"tenor":"6M","rate":0.0362},{"tenor":"1Y","rate":0.035},{"tenor":"2Y","rate":0.0335},{"tenor":"3Y","rate":0.033},{"tenor":"5Y","rate":0.0335},{"tenor":"7Y","rate":0.0345},{"tenor":"10Y","rate":0.036},{"tenor":"15Y","rate":0.0375},{"tenor":"20Y","rate":0.038},{"tenor":"30Y","rate":0.037}],"interpolation":"LOG_LINEAR_DF","method":"GLOBAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-12-07","discount_factor":0.9992870839543515},{"date":"2026-12-31","discount_factor":0.9968589384517443},{"date":"2027-02-26","discount_factor":0.9912056971787842},{"date":"2027-05-28","discount_factor":0.982556790436519},{"date":"2027-11-30","discount_factor":0.9661835748792271},{"date":"2028-11-30","discount_factor":0.936184737723126},{"date":"2029-11-30","discount_factor":0.9071996169644467},{"date":"2031-11-28","discount_factor":0.8481532478408884},{"date":"2033-11-30","discount_factor":0.788002288142405},{"date":"2036-11-28","discount_factor":0.7001603332769336},{"date":"2041-11-29","discount_factor":0.5711653644576784},{"date":"2046-11-30","discount_factor":0.46879741797306496},{"date":"2056-11-30","discount_factor":0.3372840980250744}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
{"case_id":"ois-0017","operation":"rates.ois.bootstrap","inputs":{"convention":"SONIA","as_of":"2026-11-06","quotes":[{"tenor":"1W","rate":-0.012800000000000006},{"tenor":"1M","rate":-0.012900000000000002},{"tenor":"3M","rate":-0.013200000000000003},{"tenor":"6M","rate":-0.0138},{"tenor":"1Y","rate":-0.015},{"tenor":"2Y","rate":-0.0165}],"interpolation":"LOG_LINEAR_DF","method":"GLOBAL"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2026-11-13","discount_factor":1.0002455397270125},{"date":"2026-12-07","discount_factor":1.0010968181303297},{"date":"2027-02-08","discount_factor":1.0034110477480707},{"date":"2027-05-06","discount_factor":1.0068904409407724},{"date":"2027-11-08","discount_factor":1.0153131476098416},{"date":"2028-11-06","discount_factor":1.0338563562771284}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["independent-replay","quantlib-1.44"]}
```

## Outside-library evidence and limits (from the project's own page)

81 golden cases with status ok in `datasets/golden/stage_d` for `rates.ois.bootstrap`, `rates.ois.compound_dated`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| rates.ois.bootstrap: independent-replay, quantlib-1.44 | 10 |
| rates.ois.compound_dated: exact-rational, quantlib-1.44 | 71 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- `SOFR` (GSW (Fed staff fitted Treasury zero curve, feds200628.csv), as of 2026-11-13, 11 tenors, par rates by QuantLib 1.44 MakeOIS): **pass** at the stated 0.5 bp on all 11 pillars (0.5 bp: pass, 0.1 bp: fail, 0.01 bp: fail). Between pillars within 5 bp: no (information only).
- `SOFR-EVERY-YEAR` (GSW (Fed staff fitted Treasury zero curve, feds200628.csv), as of 2026-11-13, 34 tenors, par rates by QuantLib 1.44 MakeOIS): **pass** at the stated 0.5 bp on all 34 pillars (0.5 bp: pass, 0.1 bp: fail, 0.01 bp: fail). Between pillars within 5 bp: yes (information only).
- Method (derived): the GSW curve is a Treasury curve, not a SOFR curve, so this tests the bootstrap's mechanics on a real curve shape, not SOFR levels. The every-year set misses the 0.1 bp tier because no quote covers as_of to spot (2 business days): QuantForge interpolates that stub log-linearly from D(as_of) = 1, while the published curve has its own front-end shape. The standard set's residual comes from coupon dates between sparse pillars (7Y, 10Y, ...), where log-linear and Svensson differ.
- `SONIA` (Bank of England fitted OIS spot curve (latest-yield-curve-data.zip), as of 2026-11-16, 10 tenors, par rates by QuantLib 1.44 MakeOIS): **pass** at the stated 0.5 bp on all 10 pillars (0.5 bp: pass, 0.1 bp: fail, 0.01 bp: fail). Between pillars within 5 bp: no (information only).
- `SONIA-EVERY-YEAR` (Bank of England fitted OIS spot curve (latest-yield-curve-data.zip), as of 2026-11-16, 29 tenors, par rates by QuantLib 1.44 MakeOIS): **pass** at the stated 0.5 bp on all 29 pillars (0.5 bp: pass, 0.1 bp: pass, 0.01 bp: pass). Between pillars within 5 bp: yes (information only).
- Method (derived): with a pillar every year SONIA's coupon dates sit on pillars (no spot or payment lag), and the round trip closes to rounding. The standard set's residual comes from coupon dates between sparse pillars. BoE values are Bank copyright for internal use, so only pass or fail is published (tools/workflows/boe_curves.py).
- ESTR: not run in this pack. Free data exists (ECB euro area yield curves, Svensson parameters); the same round trip would apply.

## Rulings that name this curve's operations

- (stage-d-rulings.md) | D46 | Check order for curves with `jumps` | The curve's pillar checks first, then jump dates (`E_INPUT`), then jump factors (`E_DOMAIN`). In `rates.ois.bootstrap` its own list stands (jumps first) |
