# PDE engine

Spec version 1.0.0. Status: Specified.

A one-dimensional finite-difference solver for Black-Scholes with constant `r`, `q`, `sigma`. Stage A
holds the scheme and its proof on European options; products come in later stages. The recipe
below is exact, so all four languages should land on the same grid solution, not merely near the true price.

## Operation `core.pde.bs_european`

Inputs: `option` (`CALL` or `PUT`), `spot`, `strike`, `r`, `q`, `sigma`, `t`, `space_steps` `J`, `time_steps` `M`,
`width` `w` (default 6), `rannacher_steps` `R` (default 2). Outputs: `price`, `delta`, `gamma`.

Checks: `spot`, `strike`, `sigma`, `t`, `w <= 0`: `E_DOMAIN`. `J` odd or below 20, `M < 2`, `R < 0` or `R >= M`: `E_INPUT`.

**Equation.** With `x = ln S` and `tau` the time to expiry, `V_tau = a V_xx + b V_x - r V`, where
`a = sigma^2/2` and `b = r - q - a`.

**Grid.** `h = 2 w sigma sqrt(t) / J`, and `x_j = ln(spot) + (j - J/2) h`, `j = 0..J`. So spot sits on node `J/2`.
`dt = t / M`.

**Initial values.** Cell-averaged payoff, so that the strike's position on the grid does no harm:
`V_j(0) = (1/h)` times the integral of the payoff over `[x_j - h/2, x_j + h/2]`. With `k = ln K`, `L = x_j - h/2`,
`U = x_j + h/2`, for a call: 0 if `U <= k`; otherwise, with `l = max(L, k)`, `V = (exp(U) - exp(l) - K (U - l)) / h`.
For a put: 0 if `L >= k`; otherwise with `u = min(U, k)`, `V = (K (u - L) - exp(u) + exp(L)) / h`.

**Boundaries**, at time to expiry `tau`, with `S_j = exp(x_j)`:
- Call: `V_0 = 0`; `V_J = S_J exp(-q tau) - K exp(-r tau)`.
- Put: `V_0 = K exp(-r tau) - S_0 exp(-q tau)`; `V_J = 0`.

**Interior operator.** `(L V)_j = l V_{j-1} + c V_j + u V_{j+1}`, with `l = a/h^2 - b/(2h)`,
`c = -2a/h^2 - r`, `u = a/h^2 + b/(2h)`.

**Time stepping.** Theta scheme for a step of size `s`, from `tau` to `tau + s`:
`(I - theta s L) V_new = (I + (1 - theta) s L) V_old`, with boundary values at `tau + s` on the left side and
at `tau` on the right.

The first `R` steps of size `dt` are each replaced by two fully implicit half steps (`theta = 1`,
`s = dt/2`). This is Rannacher start-up. The remaining `M - R` steps are Crank-Nicolson (`theta = 1/2`, `s = dt`).
Solve each tridiagonal system with the Thomas algorithm.

**Outputs.** With `m = J/2`, `price = V_m`. In `x`, `V_x = (V_{m+1} - V_{m-1})/(2h)`,
`V_xx = (V_{m+1} - 2 V_m + V_{m-1})/h^2`. Then `delta = V_x / spot`, `gamma = (V_xx - V_x) / spot^2`.

Diagnostic: `grid_h`.

## Acceptance

Two checks per case. Grid solution: class `numerical_scheme` against the oracle's independent replay of
this recipe. True value: per-case limit against the analytic Black-Scholes price from mpmath.

Numeric targets, from the oracle run: at-the-money, `spot = strike = 100`, `r = 0.05`, `q = 0.02`, `sigma = 0.2`,
`t = 1`:
- `J = 400`, `M = 200`: price error below 1e-3, delta error below 1e-4, gamma error below 1e-4.
- Doubling both `J` and `M` cuts the price error by a factor between 3 and 5: second order. Checked in the
  oracle, and through the stored per-grid cases.

American exercise, barriers and local volatility are later stages.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Crank, J. and Nicolson, P., "A practical method for numerical evaluation of solutions of partial differential equations of the heat-conduction type", *Proc. Cambridge Philosophical Society* 43(1), 1947, 50-67 (not opened)
- [S2] Rannacher, R., "Finite element solution of diffusion problems with irregular data", *Numerische Mathematik* 43, 1984, 309-327 (not opened)
- [S3] Tavella, D. and Randall, C., *Pricing Financial Instruments: The Finite Difference Method*, Wiley, 2000 (not opened)
