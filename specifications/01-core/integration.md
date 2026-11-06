# Numerical integration

Spec version 1.0.0. Status: Specified.

Integrals of `f` from `test-functions.md` over a finite `[a, b]`. Inputs `function`, `a`, `b`. Output
`value`. `a >= b` is `E_INPUT`. Infinite ranges are not offered in stage A.

## Fixed rules: exact recipes

These give the same number in every language up to rounding, so they are held to tight tolerance.

`h = (b - a)/n`, `x_i = a + i h`. Sum in index order.

| Operation | Extra input | Value |
|---|---|---|
| `core.integrate.trapezoid` | `n >= 1` | `h (f(x_0)/2 + f(x_1) + ... + f(x_{n-1}) + f(x_n)/2)` |
| `core.integrate.simpson` | `n >= 2`, even | `(h/3) (f(x_0) + 4 f(x_1) + 2 f(x_2) + ... + 4 f(x_{n-1}) + f(x_n))` |
| `core.integrate.gauss_legendre` | `n` from 1 to 64 | `(b-a)/2 * sum w_i f((a+b)/2 + (b-a)/2 t_i)` |

An `n` outside its range, or odd for Simpson, is `E_INPUT`.

Gauss-Legendre nodes `t_i` are the roots of the Legendre polynomial `P_n`, ascending. Weights are
`w_i = 2 / ((1 - t_i^2) P_n'(t_i)^2)`. Compute them by Newton from
`t ~ cos(pi (i - 1/4) / (n + 1/2))` to machine precision, or use a table.

## Adaptive rules

Results depend on the error estimate, so they are held to the requested accuracy and not to a recipe.

`core.integrate.adaptive_simpson`. Extra inputs `tol` (> 0, default 1e-10), `max_depth` (default 50).
Recursive Simpson with Richardson correction: on `[l, r]` with whole-interval estimate `S` and
half-interval estimates `S1 + S2`, accept `S1 + S2 + (S1 + S2 - S)/15` when
`|S1 + S2 - S| <= 15 tol_here`, and otherwise split, halving `tol_here`. The call limit in `limits.md` also applies. Depth beyond `max_depth`: `E_NO_CONVERGENCE`.

`core.integrate.gauss_kronrod`. Extra inputs `tol` (> 0, default 1e-10), `max_intervals` (default 500).
Globally adaptive G7-K15. Keep a list of intervals. Each gets the 15-point Kronrod value and the
error estimate `|K15 - G7|`. While the sum of estimates exceeds `max(tol, 1e-14 |value|)`, bisect the
interval with the largest estimate. Exceeding `max_intervals`: `E_NO_CONVERGENCE`. Nodes are interior,
so `inv_sqrt` on `[0, 1]` works; evaluation never touches an end point. The diagnostic `error_estimate`
is required.

Kronrod nodes and weights, on `[-1, 1]`, symmetric, `x` listed from the outside in:

```
x:  0.991455371120812639206854697526329, 0.949107912342758524526189684047851,
    0.864864423359769072789712788640926, 0.741531185599394439863864773280788,
    0.586087235467691130294144838258730, 0.405845151377397166906606412076961,
    0.207784955007898467600689403773244, 0
wK: 0.022935322010529224963732008058970, 0.063092092629978553290700663189204,
    0.104790010322250183839876322541518, 0.140653259715525918998541745705333,
    0.169004726639267902826583426140209, 0.190350578064785409913256402421014,
    0.204432940075298892414161999234649, 0.209482141084727828012999174351914
wG (for x[1], x[3], x[5], x[7]): 0.129484966168869693270611432679082,
    0.279705391489276667901467771423780, 0.381830050505118944950369775488975,
    0.417959183673469387755102040816327
```

## Acceptance

Fixed rules: class `quadrature`, oracle replays the recipe at 50 digits. Adaptive rules: class
`quadrature` with a per-case absolute limit tied to `tol`, against the true integral from mpmath.

Numeric targets: `gauss_legendre` with `n = 16` on `exp` over `[0, 1]`: error below 1e-14.
`gauss_kronrod` with `tol = 1e-10`: error below 1e-9 on every registered function, including `inv_sqrt`.
