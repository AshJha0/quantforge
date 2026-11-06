# Stage B hedges and cost

Spec version 1.0.0. Status: Specified.

## `hedge.solve`

Plan form: `min_x |A x + b|_W^2 + lambda C(x)`, with `b` the existing risk. Stage B's cost is linear in size, so that buying or selling crosses half a spread:

`C(x) = sum c_i |x_i|`

Inputs: `a` (rows are risk factors, columns instruments), `b`, `weights` (positive, one per row), `costs` (`c_i >= 0`, else `E_DOMAIN`), `lambda` (`>= 0`, else `E_DOMAIN`). Outputs: `x`, `residual` (`A x + b`), `objective`.

Length mismatch: `E_INPUT`. `A` without full column rank (a pivot of `A^T W A` at or below 1e-12 of its largest entry): `E_SINGULAR`. With full column rank the problem is strictly convex, so `x` is unique, and any exact method gives the same answer. With `lambda = 0` it is weighted least squares.

First-order conditions at the minimum, with `g = 2 A^T W (A x + b)`: `g_i + lambda c_i sign(x_i) = 0` when `x_i != 0`, and `|g_i| <= lambda c_i` when `x_i = 0`. So a costly hedge can be left out altogether.

This single form covers single-instrument, DV01, duration, key-rate and FX hedges: only `A` and `b` change. Integer lots, constraints and margin are stage I.

## `hedge.spread_cost`

The simple spread cost model. Inputs: `quantities`, `half_spreads` (`>= 0`, else `E_DOMAIN`). Output: `cost = sum |q_i| h_i`.

## Acceptance

Oracle: exact enumeration of sign patterns, checked against the first-order conditions. `x` within 1e-8.
