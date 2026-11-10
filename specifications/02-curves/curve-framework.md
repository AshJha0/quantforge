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

Evaluate in stable forms: `sinh(sigma u)/sinh(sigma h) = e^{-sigma (h - u)} (1 - e^{-2 sigma u})/(1 - e^{-2z})`, `1/sinh(z) = 2 e^{-z}/(1 - e^{-2z})`, `coth(z) = (1 + e^{-2z})/(1 - e^{-2z})`, with `1 - e^{-x}` computed as `-expm1(-x)`. When `z < 1e-3` use the series to `O(z^4)` (ruling F-35): `alpha = h/6 (1 - 7 z^2/60)`, `beta = h/3 (1 - z^2/15)` and `R(u) = (u/h)(u^2 - h^2)/6 (1 + sigma^2 (3 u^2 - 7 h^2)/60)`; the omitted terms are below `z^4 = 1e-12` relative. Limits: `sigma -> 0` gives the natural cubic spline in `ln S` (QuantLib `NaturalLogCubicDiscountCurve`); `sigma -> infinity` gives `LOG_LINEAR_DF`. Checks: `tension` missing for `TENSION_SPLINE`: `E_INPUT`; `tension <= 0` or above 1000: `E_DOMAIN`. `tension` is ignored by the other methods.

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

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| `TENSION_SPLINE` in the tension | error `O(sigma^2)` as `sigma -> 0` | `sigma` = 0.08, 0.04, 0.02, 0.01 against `sigma = 0` | `sigma -> 0`: natural log-cubic spline; `sigma -> infinity`: log-linear | QuantLib `NaturalLogCubicDiscountCurve`; `LOG_LINEAR_DF` |
| Global bootstrap (Newton) | quadratic in the repricing error | iterations 1 to 3 on the golden quotes | one quote: one pillar, flat forward | stage B `rates.ois.bootstrap` |
| `MONOTONE_CONVEX` | closed form | none | all discrete forwards equal: a flat curve (rule (a)) | hand |

## Stage F acceptance (plan Q1, as tightened by T)

- Inputs reprice to `|PV| <= 1e-12` per unit notional with every method (the bootstrap's 1e-13 rule implies it).
- Against QuantLib 1.44 (rule 11.2.5; convention rows `CRV.MONOTONE_CONVEX` and `CRV.MONOTONIC_LOG_CUBIC` in `oracle/CONVENTION_MAP_F.md`):
  - (a) interpolation only, on the same pillars: `MONOTONIC_LOG_CUBIC` zero rates within 1e-12 absolute (`MonotonicLogCubicDiscountCurve`); `MONOTONE_CONVEX` forwards within 1e-12 (`ConvexMonotoneInterpolation(0, 1, false)` on the discrete forwards). The wheel does not expose that object's integral, so these cases count as partly outside only.
  - (b) full SOFR, SONIA and ESTR builds (`PiecewiseConvexMonotoneForward` with `ConvexMonotone(0, 1, false)`, `PiecewiseLogCubicDiscount`, `OISRateHelper`): pillars, and zero rates at 200 dates, within 1e-10 (measured 1.6e-12 and 2.7e-12; QuantLib's bootstrap accuracy is 1e-12).
- `TENSION_SPLINE` and `HYBRID` have no outside library: the limit cases above, and each part of the hybrid equals the plain method on its own nodes.

## Stage F sources

- [S2] Hagan and West (2006) as above: the monotone convex method and its regions (not opened); West, G. and Hagan, P., "Methods for constructing a yield curve", *Wilmott Magazine*, May 2008, 70-81 (not opened)
- [S3] Hyman, J. M., "Accurate monotonicity preserving cubic interpolation", *SIAM Journal on Scientific and Statistical Computing* 4(4), 1983, 645-654 (not opened)
- [S4] Schweikert, D. G., "An interpolation curve using a spline in tension", *Journal of Mathematics and Physics* 45, 1966, 312-317 (not opened)
- [S5] Andersen, L., "Discount curve construction with tension splines", *Review of Derivatives Research* 10(3), 2007, 227-267 (not opened)
- [S6] QuantLib 1.44 source at tag v1.44, `ql/math/interpolations/convexmonotoneinterpolation.hpp`, `cubicinterpolation.hpp` and `loginterpolation.hpp` (read 2026-11-09): the branch rules and the Hyman filter above; behaviour also checked through the Python wheel
