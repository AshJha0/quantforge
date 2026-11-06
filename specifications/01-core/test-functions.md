# Test function registry

Spec version 1.0.0. Status: Specified.

Conformance cases cannot send code as JSON, so they name a function here. Each implementation
hard-codes this table in its CLI layer only. An unknown name is `E_SCHEMA`.

## Root finding (`f` and derivative `df`)

| Name | `f(x)` | `df(x)` |
|---|---|---|
| `cubic_wallis` | `x^3 - 2x - 5` | `3x^2 - 2` |
| `cos_minus_x` | `cos(x) - x` | `-sin(x) - 1` |
| `exp_minus_two` | `exp(x) - 2` | `exp(x)` |
| `triple_root` | `(x - 1)^3` | `3 (x - 1)^2` |
| `square` | `x^2` | `2x` |
| `no_real_root` | `x^2 + 1` | `2x` |
| `steep_atan` | `atan(1000 (x - 0.3))` | `1000 / (1 + 10^6 (x - 0.3)^2)` |
| `bs_vol_atm` | `C(sigma) - 10`, with `C` the Black-Scholes call for `S=K=100, r=0.01, q=0, T=1`, `sigma = x` | vega at `x` |

Black-Scholes here: `C = S N(d1) - K exp(-rT) N(d2)`, `d1 = (ln(S/K) + (r + x^2/2) T) / (x sqrt T)`,
`d2 = d1 - x sqrt T`; vega `= S n(d1) sqrt T`. `N` and `n` are defined in
`statistics-and-time-series.md`. `bs_vol_atm` is only used with `x > 0`.

## Integration and differentiation

| Name | `f(x)` |
|---|---|
| `exp` | `exp(x)` |
| `sin` | `sin(x)` |
| `runge` | `1 / (1 + 25 x^2)` |
| `sqrt` | `sqrt(x)`, used on `x >= 0` |
| `inv_sqrt` | `1 / sqrt(x)`, used on `x > 0`; a singular end point, so the rule must not evaluate at 0 |
| `normal_pdf` | `exp(-x^2/2) / sqrt(2 pi)` |
| `oscillatory` | `cos(50 x) exp(-x)` |
| `poly5` | `x^5 - 3x^2 + 1` |
