# SABR

Spec version 1.0.0. Status: Specified. Stage C.

`dF = a C(F) dW`, `da = nu a dZ`, `dW dZ = rho dt`, `C(F) = (F+s)^beta`, `a(0) = alpha`. Below, `f = F+s`, `x = K+s`.

Common checks, in order, `E_DOMAIN`: `expiry_years <= 0`; `alpha <= 0`; `beta` outside `[0, 1]`; `|rho| >= 1`; `nu < 0`; `f <= 0`; any `x <= 0`.

**The Hagan expansion is not arbitrage-free, and neither is its shifted form.** A shift moves the point where the density goes negative; it does not remove it. So Hagan vols are either density-checked, with rejection, or replaced by `vol.sabr.arbfree`.

## Hagan formula

`vol.sabr.hagan`. Inputs: `forward`, `strikes`, `expiry_years`, `alpha`, `beta`, `rho`, `nu`, optional `shift` (default 0). Output: `vols`, lognormal, on `f`, `x`. With `A = (f x)^(1-beta)`, `L = ln(f/x)`, `c = (1-beta)^2 L^2`:

- `z = (nu/alpha) sqrt(A) L`
- `chi = ln((sqrt(1 - 2 rho z + z^2) + z - rho)/(1 - rho))`
- `m = z/chi`, or for `|z| < 1e-7`, `m = 1 - rho z/2 - (3 rho^2 - 2) z^2/12`
- `den = sqrt(A) (1 + c/24 + c^2/1920)`
- `h = 1 + T ((1-beta)^2 alpha^2/(24 A) + rho beta nu alpha/(4 sqrt A) + (2 - 3 rho^2) nu^2/24)`
- `vol = alpha m h/den`

## Density check

`vol.sabr.density`. Adds `h_strike` (above 0, else `E_DOMAIN`) and `on_negative`, `REPORT` or `REJECT`. Any `x - h_strike <= 0`: `E_DOMAIN`.

`c(K)` is the undiscounted Black call on `f`, `x`, with the Hagan vol at `x`. `density_i = (c(K_i+h) - 2 c(K_i) + c(K_i-h))/h^2`, for each strike given.

Outputs: `density`, `min_density`, `negative_density`, true when `min_density < -1e-9`. With `REJECT` and `negative_density`: `E_ARBITRAGE`. Density is only checked on the given strikes, so a grid must reach the low wing.

## Calibration

`vol.sabr.calibrate`. Inputs: `forward`, `expiry_years`, `beta` (fixed), optional `shift`, `strikes` (strictly increasing, else `E_INPUT`), `vols`, optional `weights`. Minimise `sum weight (vol_hagan - vol)^2` over `alpha`, `rho`, `nu`, inside the domain. Fewer than 3 strikes, or lengths that differ: `E_INPUT`. Vol or weight `<= 0`: `E_DOMAIN`. Outputs: `alpha`, `rho`, `nu`, `rmse`. Any solver, several starts. `beta` and `rho` are nearly exchangeable, which is why `beta` is fixed.

## Arbitrage-free SABR

`vol.sabr.arbfree`. The method of Hagan, Kumar, Lesniewski and Woodward (2014): a one-dimensional forward equation for the density of `f`, absorbing at 0, so density cannot go negative. Fixed recipe, so all languages run the same grid.

Inputs: common SABR inputs (`beta` below 1, else `E_DOMAIN`), `shift`, `cells`, `cells_below`, `steps`, `strikes`. `cells_below < 1` or `cells_below >= cells`, `steps < 1`: `E_INPUT`. `cells` or `steps` above 20,000: `E_LIMIT`.

On the shifted axis, with `f0` the shifted forward:

- `z(u) = (u^(1-beta) - f0^(1-beta))/(1-beta)`
- `Dsq(u) = (alpha^2 + 2 rho alpha nu z + nu^2 z^2) u^(2 beta)`
- `G(u) = (u^beta - f0^beta)/(u - f0)`, and `G(f0) = beta f0^(beta-1)`. With `beta = 0`, `G = 0`
- `M(u, t) = Dsq(u) exp(rho nu alpha G(u) t)/2`

Grid: `h = f0/(cells_below - 1/2)`, centres `u_j = (j - 1/2) h`, `j = 1..J`, `J = cells`. So cell `cells_below` is centred on `f0`: use the `G(f0)` limit in that cell, by index. The top is `u_max = J h`. `dt = T/steps`, `t_n = n dt`.

Start: `Q_j = 0`, except `Q = 1/h` in cell `cells_below`. `P_L = P_R = 0`.

Step, fully implicit, for `n = 1..steps`, with `a_j = M(u_j, t_n) Q_j^n`, and `lambda = dt/h^2`:

`Q_j^n - lambda (a_{j+1} - 2 a_j + a_{j-1}) = Q_j^{n-1}`, with ghosts `a_0 = -a_1`, `a_{J+1} = -a_J`.

This is one tridiagonal solve. Then `P_L += 2 dt a_1/h`, `P_R += 2 dt a_J/h`. The scheme conserves mass and mean to rounding.

Call, undiscounted, at shifted strike `x` in `(0, u_max)`, with `Q` constant in a cell: sum over cells above the one holding `x` of `(u_j - x) Q_j h`, plus `Q_c (e_c - x)^2/2` for the holding cell with top edge `e_c`, plus `(u_max - x) P_R`. `x` at or beyond `u_max`: `E_INPUT`.

Outputs: `call_prices`; `vols`, the Black vol on `f0`, `x` of each price, or `null` where the price does not exceed intrinsic; `mass` (`sum Q h + P_L + P_R`); `mean` (`sum u Q h + u_max P_R`, on the shifted axis); `absorbed` (`P_L`); `min_density` (`min Q`).

## Limits of this stage

Backward Euler is first order in time, on purpose: it keeps `Q >= 0`. The result carries a grid error that the targets state. `beta = 1` is not offered. Heston and SLV are stage E.

## Acceptance

Targets in `stage-c-targets.md`. Suites `sabr`, `sabr_deep`, `strata_vol`.
