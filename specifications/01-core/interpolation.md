# Interpolation

Spec version 1.0.0. Status: Specified.

## Operation `core.interp.evaluate`

Inputs: `method`, `x` (knots), `y` (values), `at` (query points), and any method parameters.
Outputs: `values`, and `derivatives` (first derivative at `at`) for every method except `log_linear`
and `linear`, where a query on a knot has no single slope. Query points need not be sorted.

Checks, in order:
1. `x`, `y` lengths differ, or fewer knots than the method needs: `E_INPUT`.
2. `x` not strictly increasing: `E_INPUT`.
3. Method parameter checks, below.
4. Any `at` outside `[x_0, x_n]`: `E_OUT_OF_RANGE`. Extrapolation policy belongs to curves, stage B.

A query on interior knot `x_i` uses the interval to its right, `[x_i, x_{i+1}]`; on `x_n`, the last.
Throughout, `h_i = x_{i+1} - x_i`, `d_i = (y_{i+1} - y_i)/h_i`, and `u = (t - x_i)/h_i`.

| `method` | Min knots | Definition |
|---|---|---|
| `linear` | 2 | `y_i + u (y_{i+1} - y_i)` |
| `log_linear` | 2 | `exp((1-u) ln y_i + u ln y_{i+1})`. Any `y <= 0`: `E_DOMAIN` |
| `cubic_natural` | 3 | Cubic spline, `s'' = 0` at both ends |
| `cubic_clamped` | 2 | Cubic spline, `s'(x_0) = slope_start`, `s'(x_n) = slope_end` (both required) |
| `cubic_not_a_knot` | 4 | Cubic spline, `s'''` continuous at `x_1` and `x_{n-1}` |
| `monotone_pchip` | 2 | Hermite cubic with Fritsch-Butland slopes, below |
| `tension` | 3 | Exponential tension spline, below |

The three cubic splines are defined by their end conditions; any stable solve is fine.

Hermite form, slopes `m_i`: with `u` as above,
`s = (2u^3-3u^2+1) y_i + (u^3-2u^2+u) h_i m_i + (-2u^3+3u^2) y_{i+1} + (u^3-u^2) h_i m_{i+1}`.

### `monotone_pchip`

Interior slope `m_i`: 0 if `d_{i-1}` and `d_i` have opposite signs, or either is 0. Otherwise, with
`w1 = 2 h_i + h_{i-1}`, `w2 = h_i + 2 h_{i-1}`: `m_i = (w1 + w2) / (w1/d_{i-1} + w2/d_i)`.

End slope at `x_0`: `m = ((2 h_0 + h_1) d_0 - h_0 d_1) / (h_0 + h_1)`. If `m` and `d_0` differ in sign,
`m = 0`. Otherwise if `d_0`, `d_1` differ in sign and `|m| > 3 |d_0|`, `m = 3 d_0`. The other end mirrors it. With two knots,
both slopes are `d_0`.

### `tension`

Parameter `tension`, `p >= 0`. The curve solves `s'''' - p^2 s'' = 0` between knots, and so moves from a cubic
spline (`p = 0`) to straight lines (large `p`). With `M_i = s''(x_i)`, on `[x_i, x_{i+1}]`:

```
s(t) = [M_i sinh(p (x_{i+1}-t)) + M_{i+1} sinh(p (t-x_i))] / (p^2 sinh(p h_i))
     + (y_i - M_i/p^2) (x_{i+1}-t)/h_i + (y_{i+1} - M_{i+1}/p^2) (t-x_i)/h_i
```

Natural ends: `M_0 = M_n = 0`. Continuity of `s'` gives the tridiagonal system for the interior:

```
e_{i-1} M_{i-1} + (c_{i-1} + c_i) M_i + e_i M_{i+1} = p^2 (d_i - d_{i-1})
e_i = 1/h_i - p/sinh(p h_i)
c_i = p cosh(p h_i)/sinh(p h_i) - 1/h_i
```

`p = 0` means `cubic_natural`. Otherwise need `0.01 <= p h_i <= 500` for every `i`, else `E_DOMAIN`: below
it, the formula cancels badly, and above it `sinh` nears overflow. `tension` is not scaled by interval length.

## Operation `core.interp.monotone_convex`

Hagan and West (2006), the original method. It interpolates forwards, so that the zero-rate curve
reprices every input.

Inputs: `t` (times, strictly increasing, `t_1 > 0`; `t_0 = 0` is implied), `r` (continuously compounded zero
rates at `t`, at least 2), `at` (query times), `positive` (boolean, default false). Outputs: `forwards`
(instantaneous `f(s)`) and `zero_rates` at `at`.

Checks: `t` or `r` bad as for the common checks: `E_INPUT`. Any `at <= 0` or beyond `t_n`: `E_OUT_OF_RANGE`.

Discrete forwards, `i = 1..n`: `fd_i = (r_i t_i - r_{i-1} t_{i-1}) / (t_i - t_{i-1})`, with `r_0 t_0 = 0`.

Node forwards, `i = 1..n-1`:
`f_i = (t_i - t_{i-1})/(t_{i+1} - t_{i-1}) fd_{i+1} + (t_{i+1} - t_i)/(t_{i+1} - t_{i-1}) fd_i`.
Ends: `f_0 = fd_1 - (f_1 - fd_1)/2`, `f_n = fd_n - (f_{n-1} - fd_n)/2`.

If `positive`: `f_0 = clamp(f_0, 0, 2 fd_1)`; for interior `i`, `f_i = clamp(f_i, 0, 2 min(fd_i, fd_{i+1}))`;
`f_n = clamp(f_n, 0, 2 fd_n)`. All `fd_i` must be non-negative, else `E_DOMAIN`.

For `s` in `(t_{i-1}, t_i]`, let `x = (s - t_{i-1})/(t_i - t_{i-1})`, `g0 = f_{i-1} - fd_i`, `g1 = f_i - fd_i`.
Then `f(s) = fd_i + g(x)`, with `g` chosen by the first region that holds:

| Region | Condition | `g(x)` |
|---|---|---|
| Zero | `g0 = 0` and `g1 = 0` | 0 |
| (i) | `g0 < 0` and `-g0/2 <= g1 <= -2 g0`, or `g0 > 0` and `-g0/2 >= g1 >= -2 g0` | `g0 (1 - 4x + 3x^2) + g1 (-2x + 3x^2)` |
| (ii) | `g0 < 0` and `g1 > -2 g0`, or `g0 > 0` and `g1 < -2 g0` | With `eta = (g1 + 2 g0)/(g1 - g0)`: `g0` for `x <= eta`, otherwise `g0 + (g1 - g0) ((x - eta)/(1 - eta))^2` |
| (iii) | `g0 > 0` and `-g0/2 < g1 < 0`, or `g0 < 0` and `0 < g1 < -g0/2` | With `eta = 3 g1/(g1 - g0)`: `g1 + (g0 - g1) ((eta - x)/eta)^2` for `x < eta`, otherwise `g1` |
| (iv) | Otherwise (same sign, or one is zero) | With `eta = g1/(g1 + g0)`, `A = -g0 g1/(g0 + g1)`: `A + (g0 - A) ((eta - x)/eta)^2` for `x < eta`, otherwise `A + (g1 - A) ((x - eta)/(1 - eta))^2` |

Zero rate: `r(s) s = r_{i-1} t_{i-1} + (t_i - t_{i-1}) (fd_i x + G(x))`, where `G(x)` is the integral of `g` from 0 to
`x`, done in closed form. Each `g` integrates to 0 on `[0, 1]`, which is why every input zero rate reprices.

## Acceptance

Class `interpolation`. Oracles: `linear`, `log_linear`, and `cubic_*`: SciPy, and QuantLib where offered.
`monotone_pchip`: SciPy `PchipInterpolator`. `tension`: 50-digit solve of the system above, checked for
`s'` continuity and for the limits `p -> 0` and `p` large. `monotone_convex`: 50-digit evaluation, checked
for repricing, `g` integrating to 0, and forward continuity. QuantLib's `ConvexMonotone` is a later variant with
extra parameters, so it is not a second source here: this method has a single source.

Numeric targets: all methods reproduce the knots to 1e-12. `monotone_pchip` on monotone data never overshoots.
`monotone_convex` reprices each input zero rate to 1e-12.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Hagan, P. S. and West, G., "Interpolation methods for curve construction", *Applied Mathematical Finance* 13(2), 2006, 89-129 (not opened)
- [S2] Fritsch, F. N. and Butland, J., "A method for constructing local monotone piecewise cubic interpolants", *SIAM Journal on Scientific and Statistical Computing* 5(2), 1984, 300-304 (not opened)
- [S3] Hagan, P. S. and West, G., "Methods for constructing a yield curve", *Wilmott Magazine*, May 2008 (monotone convex) (not opened)
