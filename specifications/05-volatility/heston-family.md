# Heston, Bates, Merton, SLV leverage

Spec version 1.0.0. Status: Specified. Stage E, slice E2 (spec A). `stage-e-rulings.md` is normative.

Common inputs: `spot` (> 0), `expiry_years` `T` (> 0), `rate` `r` and `dividend_yield` `q` (flat continuous, any sign), `option_type` (`CALL`, `PUT`). `F = S e^{(r-q)T}`. Errors in input order; `E_INPUT` for array shape before `E_DOMAIN` for values.

Sources:
- [Hes93] S. Heston, "A closed-form solution for options with stochastic volatility", *Review of Financial Studies* 6(2), 1993, pp. 327-343.
- [Alb07] H. Albrecher, P. Mayer, W. Schoutens, J. Tistaert, "The little Heston trap", *Wilmott* 2007(1), pp. 83-92: the continuous form of the characteristic function used below.
- [Lew01] A. Lewis, "A simple option formula for general jump-diffusion and other exponential Levy processes", 2001, equation (2.10): the single-integral call price.
- [Bat96] D. Bates, "Jumps and stochastic volatility", *Review of Financial Studies* 9(1), 1996, pp. 69-107.
- [Mer76] R. Merton, "Option pricing when underlying stock returns are discontinuous", *Journal of Financial Economics* 3, 1976, pp. 125-144.
- [Hull] J. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "More on Models and Numerical Procedures" (Merton mixed jump-diffusion) (not opened; edition as the stage B to D specs)
- [GHL] P. Henry-Labordere, "Calibration of local stochastic volatility models to market smiles", *Risk*, September 2009: leverage `L(t,x)^2 = sigma_LV(t,x)^2 / E[v | x_t = x]`.

## Object `heston`

`{v0, kappa, theta, xi, rho}`: `dS/S = (r-q)dt + sqrt(v) dW1`, `dv = kappa(theta - v)dt + xi sqrt(v) dW2`, `d<W1,W2> = rho dt`. `xi` is the vol of variance. Checks: `v0 <= 0`, `kappa <= 0`, `theta <= 0`, `xi <= 0`, `|rho| >= 1`: `E_DOMAIN`. The Feller condition is not required for pricing. `xi = 0` is not Heston; use Black-Scholes (ruling E-A12).

## Characteristic function, `vol.heston.cf`

For `X = ln(S_T/F)`, with `b = kappa - rho xi i u`, `d = sqrt(b^2 + xi^2 (i u + u^2))` (principal root), `g = (b - d)/(b + d)`:

`C = (kappa/xi^2) ((b - d) T - 2 ln((1 - g e^{-dT})/(1 - g)))`, `D = ((b - d)/xi^2) (1 - e^{-dT})/(1 - g e^{-dT})`, `phi(u) = exp(C theta + D v0)` [Alb07]. `phi(-i) = 1`.

`vol.heston.cf`. Inputs: `expiry_years`, `heston`, `u` (array of real `u >= 0`, at least 1, else `E_INPUT`; negative `E_DOMAIN`). Outputs `re`, `im` arrays. Given so builds can localise pricing errors.

## Pricing by Lewis's integral

For a characteristic function `phi` of `X = ln(S_T/F)`, with `k = ln(F/K)`:

`call = e^{-rT} (F - (sqrt(F K)/pi) Int_0^inf Re[e^{i u k} phi(u - i/2)] / (u^2 + 1/4) du)` [Lew01], `put = call - e^{-rT}(F - K)`.

Reference recipe (ruling E-A13): Gauss-Legendre with 256 nodes on `u` in `[0, 200]`. On every golden this is within 2.4e-11 of QuantLib's adaptive engine at relative tolerance 1e-13; a build may use any quadrature that meets the target. Near `xi = 1e-3` the `kappa/xi^2` factor cancels to about 1e-9 in binary64, which is inside the target; goldens there come from 30-digit arithmetic.

### `vol.heston.price`

Inputs: common, `strikes` (at least 1, else `E_INPUT`; each > 0, else `E_DOMAIN`), `heston`. Output `prices` (per unit of underlying, strike order).

Small vol of variance: as `xi -> 0` the price tends to Black-Scholes at the average variance `vbar = theta + (v0 - theta)(1 - e^{-kappa T})/(kappa T)`, not at `v0` or `theta` (plan section 8). Goldens test `xi = 1e-3` and `1e-2`, near zero and not at it.

### `vol.bates.price`

As `vol.heston.price` plus `jumps`: `{intensity, mean_log_jump, log_jump_vol}` (`lambda >= 0`, `mu` any, `delta >= 0`, else `E_DOMAIN`). Log-normal jumps `ln(1+J) ~ N(mu, delta^2)`, compensated so `S e^{-(r-q)t}` is a martingale [Bat96]:

`phi_Bates(u) = phi(u) exp(lambda T (e^{i u mu - delta^2 u^2/2} - 1 - i u kbar))`, `kbar = e^{mu + delta^2/2} - 1`.

### `vol.merton.price`

Inputs: common, `strikes`, `vol` (> 0), `jumps`. Merton's series [Mer76]: with `lambda' = lambda (1 + kbar)`,

`price = sum_n e^{-lambda' T} (lambda' T)^n / n! * BS(S, K, T, r_n, q, v_n)`, `v_n^2 = v^2 + n delta^2/T`, `r_n = r - lambda kbar + n ln(1 + kbar)/T`, each BS term at rate `r_n` (forward and discount) [Mer76], [Hull]. Equivalently Poisson weights at `lambda` with each term `e^{(r_n - r)T} BS_n`; mixing the two is a wrong convention the goldens catch. Stop when the Poisson weights sum to at least `1 - 1e-16`, or at 200 terms. The Lewis route with `phi(u) = e^{-v^2 T (u^2 + i u)/2} phi_jump(u)` gives the same value to 1e-9 and is accepted. `lambda = 0` is Black-Scholes.

## `vol.slv.leverage` (fixed PDE grid)

The leverage function of a Heston stochastic-local vol model `dS/S = (r-q)dt + L(t, x) sqrt(v) dW1`, `x = ln S`, calibrated so the model reprices the local vol surface: `L(t,x)^2 = sigma_LV(t,x)^2 / E[v | x_t = x]` [GHL]. `sigma_LV` is `vol.local.dupire` on `slices` at `k = x - ln F(t)` (`local-and-forward-vol.md`); any `E_ARBITRAGE` there is returned.

Inputs: `spot`, `expiry_years`, `rate`, `dividend_yield`, `heston`, `slices`, `grid`: `{nx, nv, nt, x_min, x_max, v_max}`. Checks: `nx`, `nv` at least 5, `nt` at least 2, else `E_INPUT`; `x_min < ln(spot) < x_max`, else `E_INPUT`; `v_max > 0`, else `E_DOMAIN`; `nx`, `nv` above 1000 or `nt` above 10,000: `E_LIMIT`.

**Grid.** `x_i = x_min + i dx`, `i = 0..nx-1`, `dx = (x_max - x_min)/(nx - 1)`. `v_j = (j + 1) dv`, `j = 0..nv-1`, `dv = v_max/(nv + 1)`. `dt = T/nt`, `t_n = n dt`.

**Start, `t_1 = dt`.** `L0^2 = sigma_LV(dt, 0)^2/v0` (at the forward). `p_ij` = bivariate normal density at `(x_i, v_j)` with means `ln S + (r - q - L0^2 v0/2) dt` and `v0 + kappa(theta - v0) dt`, standard deviations `max(sqrt(L0^2 v0 dt), 2 dx)` and `max(xi sqrt(v0 dt), 2 dv)`, correlation `rho`; then scaled so `sum p dx dv = 1`.

**Leverage from a density.** `m_i = sum_j p_ij`, `e_i = sum_j v_j p_ij`, `eps = 1e-10 max_i m_i`, `Ebar = sum e / sum m`, `E_i = (e_i + eps Ebar)/(m_i + eps)`, `L_i^2 = sigma_LV(t, x_i)^2 / E_i`. The `eps` term keeps the far tail finite with no branch.

**Operator rows.** For a 1-D line with node drifts `mu_k`, node diffusions `s_k`, step `h`, the rows of `(I - dt A)`, `A p = -D[mu p] + (1/2) D2[s p]`, are, for node `k`:

- diffusion: `p_k: + dt s_k/h^2`, `p_{k-1}: - dt s_{k-1}/(2h^2)`, `p_{k+1}: - dt s_{k+1}/(2h^2)`;
- drift by upwind fluxes at the faces: face `k` lies between nodes `k-1` and `k`, its drift `f_k = (mu_{k-1} + mu_k)/2`, and the outer faces take the end node's drift; with `f+ = max(f, 0)`, `f- = min(f, 0)`: `p_k: + dt (f+_{k+1} - f-_k)/h`, `p_{k+1}: + dt f-_{k+1}/h`, `p_{k-1}: - dt f+_k/h`. Terms that would reference a node beyond the line are dropped (density 0 there).
- **No-flux variant** (used for `v`): both outer face drifts are 0, and the diffusion term of the two end nodes is `+ dt s_k/(2h^2)` instead of `/h^2`. Every column then sums to 1, so the step keeps mass.

**Step `n -> n+1`, `n = 1..nt-1`** (Lie splitting; `L` from `p^n` at `t_n`):

1. Mixed term, explicit, interior nodes only: `p* = p^n + dt (f_{i+1,j+1} - f_{i+1,j-1} - f_{i-1,j+1} + f_{i-1,j-1})/(4 dx dv)`, `f_ij = rho xi L_i v_j p^n_ij`. Edge nodes copy `p^n`.
2. `x`, implicit for each `j`: operator rows with `mu_i = r - q - L_i^2 v_j/2`, `s_i = L_i^2 v_j`, `h = dx`, then rows 0 and `nx-1` replaced by `p = 0` (right-hand side 0).
3. `v`, implicit for each `i`: no-flux operator rows with `mu_j = kappa(theta - v_j)`, `s_j = xi^2 v_j`, `h = dv`.
4. Floor: `p = max(p, 0)` at every node.

Tridiagonal solves by the Thomas algorithm (no pivoting). Outputs at `T`, after the last step: `x` (the grid), `leverage` (`L_i` from `p` at `T`), `mass` (`sum p dx dv`: below 1 by what left through the `x` ends, above 1 by what the floor added).

This is a reference scheme, not a converged answer: goldens test that four builds run the same recipe (class `numerical_scheme`). Its accuracy is checked only as stated in `stage-e-targets-a.md` (ruling E-A14).

## Wrong conventions the goldens catch

- small-`xi` limit at `sqrt(v0)` or `sqrt(theta)` instead of `sqrt(vbar)`;
- `rho` sign flipped; `xi` read as variance of variance;
- jump compensator omitted; Merton drift without `-lambda kbar`;
- SLV mixed term with the wrong sign.
