# Review request: Five interpolation methods (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage F). Evidence line from the project's status table: 47 golden cases for `rates.curve.inspect`, 36 reproduced by an outside library.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. Tension spline and hybrid cases have mpmath replay and properties only (oracle README).

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
   Every branch integrates to `y_i` over its section, so `S` returns every node exactly. `ln S(t) = -(sum of y_k (t_k - t_{k-1}) over the sections before i) - (t_i - t_{i-1}) * (integral of the branch polynomial from 0 to x)`, the integral in closed form.

**Why `forcePositive = false` (ruling F-19).** With `forcePositive = true` (QuantLib's default), QuantLib's positive-forcing quadratic shrinks and shifts the quadratic whenever it has real roots, even roots outside the section. The forward stays positive, but its average over the section is no longer `y_i`, so the curve does not return its own pillar discount factors: on the stage F SOFR pillars `ln S` is off by up to 0.06 at a node, and QuantLib's own bootstrap fails to bracket the 30Y pillar. The positivity collar is therefore not used. A negative forward is returned as computed; negative rates are valid curves.

### `MONOTONIC_LOG_CUBIC`

QuantLib 1.44 `MonotonicLogCubic`: a cubic spline in `ln S` through the nodes `(t_i, ln S_i)`, `i = 0..n`, with the Hyman monotonicity filter [S3]. With `h_i = t_{i+1} - t_i` and chord slopes `s_i = (ln S_{i+1} - ln S_i)/h_i`, the node slopes `m_i` solve:

```
row 0:  2 m_0 + m_1 = 3 s_0                                                   (second derivative 0 at t_0)
row i:  h_i m_{i-1} + 2 (h_{i-1} + h_i) m_i + h_{i-1} m_{i+1} = 3 (h_i s_{i-1} + h_{i-1} s_i)
row n:  m_{n-1} + 2 m_n = 3 s_{n-1}                                           (second derivative 0 at t_n)
```

Then the filter, node by node in index order (it reads only chord slopes, never another node's filtered slope):
- `i = 0`: `m_0 = sign(m_0) min(|m_0|, 3|s_0|)` if `m_0 s_0 > 0`, else `0`. `i = n`: the same with `s_{n-1}`.
- `0 < i < n`: `p = (s_{i-1} h_i + s_i h_{i-1})/(h_{i-1} + h_i)`, `M = 3 min(|s_{i-1}|, |s_i|, |p|)`. If `i > 1` and `(s_{i-1} - s_{i-2})(s_i - s_{i-1}) > 0`: `pd = (s_{i-1}(2 h_{i-1} + h_{i-2}) - s_{i-2} h_{i-1})/(h_{i-2} + h_{i-1})`, and if `p pd > 0` and `p (s_{i-1} - s_{i-2}) > 0`, then `M = max(M, 1.5 min(|p|, |pd|))`. If `i < n - 1` and `(s_i - s_{i-1})(s_{i+1} - s_i) > 0`: `pu = (s_i (2 h_i + h_{i+1}) - s_{i+1} h_i)/(h_i + h_{i+1})`, and if `p pu > 0` and `-p (s_i - s_{i-1}) > 0`, then `M = max(M, 1.5 min(|p|, |pu|))`. Finally `m_i = sign(m_i) min(|m_i|, M)` if `m_i p > 0`, else `0`.

On `[t_i, t_{i+1}]` with `d = t - t_i`: `ln S = ln S_i + d (m_i + d (b_i + d c_i))`, `b_i = (3 s_i - m_{i+1} - 2 m_i)/h_i`, `c_i = (m_{i+1} + m_i - 2 s_i)/h_i^2`, and `f = -(m_i + 2 b_i d + 3 c_i d^2)`.

### `TENSION_SPLINE`

An exponential tension spline in `ln S` [S4], [S5]: on each interval `(ln S)'' - sigma^2 ln S` is linear in `t`. Tension `sigma > 0` per year is the input `tension`; the ends are natural. With `M_i` the second derivative at node `i` (`M_0 = M_n = 0`), `a = t - t_i`, `b = t_{i+1} - t`, `h = h_i`, `z_i = sigma h_i`:

```
ln S(t) = ln S_i b/h + ln S_{i+1} a/h + M_i R(b) + M_{i+1} R(a),   R(u) = (sinh(sigma u)/sinh(sigma h) - u/h) / sigma^2
interior nodes i = 1..n-1:  alpha_{i-1} M_{i-1} + (beta_{i-1} + beta_i) M_i + alpha_i M_{i+1} = s_i - s_{i-1}
alpha_i = 1/(sigma^2 h_i) - 1/(sigma sinh(z_i)),   beta_i = coth(z_i)/sigma - 1/(sigma^2 h_i)
```

Evaluate in stable forms: `sinh(sigma u)/sinh(sigma h) = e^{-sigma (h - u)} (1 - e^{-2 sigma u})/(1 - e^{-2z})`, `1/sinh(z) = 2 e^{-z}/(1 - e^{-2z})`, `coth(z) = (1 + e^{-2z})/(1 - e^{-2z})`, with `1 - e^{-x}` computed as `-expm1(-x)`. Those forms lose about `epsilon / z^2` to cancellation for small `z` (4e-8 relative at `z = 1e-3`), so when `z < 1` use instead, with `shm(x) = sinh x - x` (a series below 0.5: `x^3/6 + x^5/120 + ...`, terms to `x^19`) and `chm(x) = cosh x - 1 = 2 sinh^2(x/2)` (ruling F-35, amended): `alpha = shm(z) / (sigma^2 h sinh z)`, `beta = (z chm(z) - shm(z)) / (sigma^2 h sinh z)`, `R(u) = (h shm(sigma u) - u shm(sigma h)) / (sigma^2 h sinh(sigma h))` and `R'(u) = (h sigma chm(sigma u) - shm(sigma h)) / (sigma^2 h sinh(sigma h))`. The linear terms of `sinh` cancel analytically, so nothing cancels in floating point; measured against 40 digits, `R` and `R'` agree to 1.2e-14 and `alpha`, `beta` to 1e-15 over `z` from 1e-7 to 1. Limits: `sigma -> 0` gives the natural cubic spline in `ln S` (QuantLib `NaturalLogCubicDiscountCurve`); `sigma -> infinity` gives `LOG_LINEAR_DF`. Checks: `tension` missing for `TENSION_SPLINE`: `E_INPUT`; `tension <= 0` or above 1000: `E_DOMAIN`. `tension` is ignored by the other methods.

### `HYBRID`

Steps up to the last policy meeting, smooth after. Input `step_end`: a date that must equal a pillar date (else `E_INPUT`; missing for `HYBRID`: `E_INPUT`). Segments ending on or before `step_end` use `LOG_LINEAR_DF` (a flat forward between pillars; with pillars on meeting dates this is a meeting-step curve). From `step_end` on, `MONOTONE_CONVEX` on the nodes from `step_end` to `t_n`, with `step_end` as its node 0 and its own `f_0` rule, so the forward may jump at `step_end`, as at any meeting. If `step_end` is the last pillar, the whole curve is `LOG_LINEAR_DF` with its stage B extrapolation.

### `rates.curve.inspect`

Inputs: `curve`, `dates`. Outputs: `discount_factors`, `zero_rates` (`null` at `as_of`), `instantaneous_forwards` (the forward of the smooth curve at each date: right-hand at a pillar and at `as_of`; at and after the last pillar, the extrapolation forward). It works for every interpolation: for `LOG_LINEAR_DF` the segment's flat forward; for `LINEAR_ZERO` `z(t) + t z'(t)` with the right-hand slope. Checks as `rates.curve.discount`.

### Bootstrap with the new methods

`rates.ois.bootstrap` and `rates.curve.joint_bootstrap` accept the new values, with `tension` and `step_end` as optional top-level inputs. These methods are not local (a pillar moves earlier sections), so `SEQUENTIAL` means "repeat the one-at-a-time solve until every quote reprices", and both methods must return the unique solution with every repricing error below 1e-13 (ruling F-21).

### Locality and smoothness (the Q1 tests)

Locality is stated on the pillar inputs, not on quotes, because a bootstrap spreads a quote move over later pillars whatever the interpolation (ruling F-22):
- `MONOTONE_CONVEX`: changing `S_j` changes `f` only on sections `j - 1` to `j + 2` (it moves `y_j` and `y_{j+1}`, hence `f_{j-1}`, `f_j` and `f_{j+1}`); elsewhere `f` is unchanged to 1e-15 absolute.
- `HYBRID`: changing a pillar after `step_end` leaves every step segment unchanged; changing one before `step_end` changes only its two adjacent step segments.
- `MONOTONE_CONVEX` and `MONOTONIC_LOG_CUBIC`: `f` continuous at every interior pillar (jump at most 1e-12). `TENSION_SPLINE`: `f` and `f'` continuous (`f'` jump at most 1e-8).
- Positivity: on the golden SOFR pillars every new method's forward is positive on a 10,000-point grid to 30 years (an oracle check).

## Convergence and limit cases

| M

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

## Golden cases (1 of 47 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"curve_f-0067","operation":"rates.curve.inspect","inputs":{"curve":{"as_of":"2026-11-09","interpolation":"MONOTONIC_LOG_CUBIC","pillars":[{"date":"2027-02-08","discount_factor":0.9876116222305686},{"date":"2027-05-10","discount_factor":0.9753767163648953},{"date":"2027-11-09","discount_factor":0.9743991575839764},{"date":"2028-05-10","discount_factor":0.9734225785487846},{"date":"2028-11-08","discount_factor":0.9724523067685741},{"date":"2029-11-08","discount_factor":0.9343219064225613},{"date":"2031-11-08","discount_factor":0.862487824605791},{"date":"2036-11-06","discount_factor":0.7061453061600895}]},"dates":["2027-01-03","2027-02-27","2027-04-22","2027-06-16","2027-08-10","2027-10-03","2027-11-27","2028-01-21","2028-03-16","2028-05-10","2028-07-03","2028-08-27","2028-10-21","2028-12-14","2029-02-07","2029-04-03","2029-05-28","2029-07-21","2029-09-14","2029-11-08","2030-01-02","2030-02-25","2030-04-21","2030-06-15","2030-08-09","2030-10-03","2030-11-26","2031-01-20","2031-03-16","2031-05-09","2031-07-03","2031-08-27","2031-10-21","2031-12-14","2032-02-07","2032-04-02","2032-05-27","2032-07-20","2032-09-13","2032-11-07","2033-01-01","2033-02-25","2033-04-20","2033-06-14","2033-08-08","2033-10-01","2033-11-25","2034-01-19","2034-03-15","2034-05-09","2034-07-02","2034-08-26","2034-10-20","2034-12-13","2035-02-06","2035-04-02","2035-05-27","2035-07-20","2035-09-13","2035-11-07","2036-01-01","2036-02-24","2036-04-19","2036-06-13","2036-08-07","2036-10-01","2036-11-24","2037-01-18","2037-03-14","2037-05-07","2036-11-06"]},"expected":{"status":"ok","outputs":{"discount_factors":[0.992713855929167,0.9845232602612206,0.9763849636721061,0.9748954538369458,0.974519307314978,0.9744072332588036,0.9743772275740405,0.9741069097368386,0.9737110673056082,0.9734225785487846,0.9733208562982969,0.97316393886709,0.9727079779080892,0.9713467633090221,0.9678409499747932,0.9625898099465011,0.9561029989916985,0.9490182683833369,0.9415569351533893,0.9343219064225613,0.9275378960797581,0.9212101579678191,0.9150709733387942,0.9092077128834875,0.9035885247339439,0.898182439544681,0.8930528054905317,0.8879806613776269,0.8830338466134057,0.8782717521778945,0.8734909538165522,0.868753563977602,0.8640332810216309,0.8593918396034912,0.8546489917760174,0.849892194487423,0.845123238774485,0.8404308658635731,0.8356429897231765,0.8308481185601323,0.82604792387773,0.8212440467013431,0.816525487487854,0.8117190409532068,0.8069136232015172,0.8021980463679856,0.7973991252753351,0.7926056707837138,0.787819110005026,0.7830408394280548,0.7783588329929204,0.773600998735536,0.7688554380831915,0.7642093350743016,0.7594918391903327,0.7547903330144343,0.7501060038831324,0.7455246758412649,0.74087778250748,0.7362514344242072,0.7316467043670715,0.7271477390935877,0.722588912233645,0.7180547372416789,0.7135461773907252,0.7090641693569657,0.7046903588116954,0.700263234388816,0.6958639227923936,0.6915714886030384,0.7061453061600895],"zero_rates":[0.048530517215490086,0.051756186084934444,0.05318837942457668,0.042375067612332666,0.03438319674855643,0.0288505333749924,0.024736853396354324,0.021861848144167268,0.01972381878477187,0.017941605839416057,0.016395588604183556,0.015112623857979273,0.014185462180860264,0.01385272904825955,0.01453220739980891,0.01588662839078716,0.017599050219282757,0.019390293504772282,0.021135065253502283,0.022644748858447476,0.023874690317648592,0.024879140977262636,0.025730804076134286,0.026439362190520257,0.0270300480626682,0.027524196117905502,0.027933012189103865,0.028286979513095906,0.02859130221691614,0.02885305449717893,0.029091920792201294,0.029311620769018505,0.029519953954028386,0.029719806903620364,0.02992093791731451,0.030119586584477366,0.030315685295085607,0.030505679245804242,0.030696551782666108,0.030884711718909674,0.031070114962783116,0.03125272164000654,0.03142925246585171,0.0316062132384228,0.03178027904786104,0.03194833707786773,0.032116587045224215,0.03228186716543713,0.03244415636496713,0.03260343526354678,0.032756872212088756,0.032910133823166765,0.033060335845347524,0.033204816618301033,0.03334891438821108,0.03348991344247893,0.033627802477995405,0.03376014854988005,0.033891843702642706,0.034020399526009576,0.03414580746437155,0.03426586496508669,0.034385011220054454,0.034500987200735675,0.03461378631262978,0.0347234023626723,0.0348279238558543,0.034931271127510224,0.03503160934678866,0.03512732103914097,0.03479342465753425],"instantaneous_forwards":[0.05022198807665531,0.06398808216170733,0.03436027949098583,0.0038190450595715214,0.001483651348203779,0.0002452745677685034,0.0008844347325500091,0.002533811522157561,0.0025963815473019495,0.0010721448079831705,0.000611058166538981,0.0018094839755916949,0.004691264097677107,0.016827634148726053,0.03060665254594595,0.041045538541822316,0.04814429213635523,0.05186438751440773,0.05234360598627809,0.049482692056804965,0.04727384638333958,0.04529852485145929,0.04348356740442781,0.04186736089734005,0.040449905330196004,0.03923120070299567,0.038228017652902894,0.03740320125213647,0.03677713579131376,0.036355816650028114,0.036123639415639314,0.03609021312119424,0.036255537766692866,0.036566515642345004,0.036884788170263964,0.03719312315118574,0.03749152058511033,0.037774824445587454,0.03805352746819035,0.038322292943796056,0.03858112087240458,0.03883001125401592,0.03906470819040367,0.03929390416069331,0.03951316258398577,0.03971876632493316,0.03991833033690392,0.040107956801877495,0.04028764571985388,0.04045739709083308,0.0406143939076911,0.04076445086734861,0.040904570280008934,0.04103247390142659,0.04115289890276522,0.041263386357106656,0.04136393626445091,0.04145298982610371,0.04153384532212627,0.04160476327115164,0.04166574367317982,0.041715947175067755,0.041757233165774246,0.04178858160948355,0.04180999250619567,0.0418214658559106,0.04182359462630868,0.04182359462630868,0.04182359462630868,0.04182359462630868,0.04182359462630868]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["independent-replay"]}
```

## Outside-library evidence and limits (from the project's own page)

47 golden cases with status ok for `rates.curve.inspect`, 36 of them reproduced by an outside library (QuantLib 1.44, with SciPy quadrature for the monotone convex integral; `oracle/outside_register_f.json`):

| Method | Cases | Outside-checked |
|---|---|---|
| HYBRID | 4 | 0 |
| LINEAR_ZERO | 1 | 0 |
| LOG_LINEAR_DF | 1 | 1 |
| MONOTONE_CONVEX | 17 | 17 |
| MONOTONIC_LOG_CUBIC | 18 | 18 |
| TENSION_SPLINE | 6 | 0 |

The tension spline and the hybrid have no outside library (`oracle/OUTSIDE_GAPS_F.md`). Limits: one synthetic pillar set, so the page shows the methods, not a market.

## Real-data reconciliation

- Not applicable: these are interpolation methods on given pillars, not a market curve.

## Rulings that name this curve's operations

- (stage-f-rulings.md) | F-18 | New interpolations (Q1) | `MONOTONE_CONVEX`, `MONOTONIC_LOG_CUBIC`, `TENSION_SPLINE` (with `tension`) and `HYBRID` (with `step_end`), all on `S = D/J`. New operation `rates.curve.inspect` reports instantaneous forwards |
