# Regularised and outlier-robust curve fits

Spec version 1.0.0. Status: Specified (stage D).

Both fits have one minimum, so goldens judge parameters, not only the objective.

## `calib.curve.smooth`

Piecewise-flat forwards, penalised for roughness. Inputs: `knots` `t_1 < ... < t_n` (`t_0 = 0`), `maturities` `m_j`, `zero_rates` `y_j` (continuous), `lambda >= 0`, optional `weights` `w_j >= 0` (default 1).

Forward `f_k` holds on `(t_{k-1}, t_k]`. Model zero rate: `z(m) = (1/m) sum_k f_k * length((t_{k-1}, t_k] ∩ (0, m])`, linear in `f`: `z = B f`.

Objective: `sum w_j (z(m_j) - y_j)^2 + lambda sum_{k=1}^{n-1} (f_{k+1} - f_k)^2`. Solve the normal equations `(B^T W B + lambda D^T D) f = B^T W y`, `D` the first-difference matrix.

Outputs: `forwards`, `fitted` (`z(m_j)`), `objective`.

Checks, in order: `maturities`, `zero_rates`, `weights` of unequal length, or empty: `E_INPUT`. `knots` not strictly increasing or not positive: `E_INPUT`. `lambda < 0`, a weight `< 0`, a maturity `<= 0`: `E_DOMAIN`. A maturity past `t_n`: `E_INPUT`. A singular system: `E_SINGULAR`.

## `calib.curve.robust`

Nelson-Siegel with a fixed `tau`, fitted with Huber loss. Inputs: `maturities`, `zero_rates`, `tau`, `delta`. Model: `z(m) = b0 + b1 e + b2 (e - exp(-m/tau))`, `e = (1 - exp(-m/tau))/(m/tau)`. Residual `r_j = z(m_j) - y_j`. Objective: `sum rho(r_j)`, `rho(r) = r^2/2` for `|r| <= delta`, else `delta |r| - delta^2/2`. It is convex in `b`; the goldens' minima are strict.

Outputs: `betas`, `residuals`, `outliers` (0-based indices with `|r_j| > delta`, ascending), `objective`. Any convergent method may be used (IRLS is natural).

Checks, in order: unequal lengths or fewer than 3 points: `E_INPUT`. `tau <= 0`, `delta <= 0`, a maturity `<= 0`: `E_DOMAIN`.

## Acceptance

`smooth`: within 1e-10 plus 1e-8 relative of exact-rational goldens. `robust`: `betas`, `residuals`, `objective` within 1e-9; `outliers` exact. No golden residual is within 1e-6 of `delta`. SciPy `least_squares(loss="huber")` from three starts agrees within 1e-8. Suite `stage_d/fits_d`.
