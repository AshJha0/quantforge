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
