# Delta, smile, SVI, SSVI, surface

Spec version 1.0.0. Status: Specified. Stage C.

Log-moneyness is `k = ln(K/F)`, with `F` the forward of that expiry. Total variance is `w = v^2 T`. Times are years, as `expiry_years`.

## Delta conventions

`Delta = phi s N(phi d1)`, lognormal, `delta` signed: a put's is negative.

| `convention` | `s` | Meaning |
|---|---|---|
| `FORWARD` | 1 | `scale` must be `null`, else `E_INPUT` |
| `SPOT` | `scale`, given | `dV/dS`. On an equity, `D(T)/C(T)`. `null`: `E_INPUT`. Must be above 0, else `E_DOMAIN` |

`vol.delta.to_strike`. Inputs: `forward`, `vol`, `expiry_years`, `option_type`, `delta`, `convention`, `scale`. With `d1 = phi Ninv(phi delta/s)`, output `strike = F exp(-d1 v sqrt T + v^2 T/2)`. `phi delta/s` outside the open interval `(0, 1)`: `E_DOMAIN`. `forward`, `vol`, `expiry_years` must be above 0, else `E_DOMAIN`. `Ninv` must be good to 1e-12.

`vol.delta.from_strike`. Same, with `strike` (above 0) for `delta`. Output: `delta`.

`vol.smile.rr_bf`. Inputs: `forward`, `expiry_years`, `atm_vol`, `atm_convention`, `rr`, `bf`, `delta` (positive, such as 0.25), `convention`, `scale`. `call_vol = atm + bf + rr/2`, `put_vol = atm + bf - rr/2`. `bf` here is the smile strangle: no broker-strangle iteration. `atm_strike`: `F` for `ATM_FORWARD`, `F exp(atm^2 T/2)` for `DELTA_NEUTRAL`. Outputs: `atm_strike`, `call_vol`, `put_vol`, `call_strike`, `put_strike`, the last two from `vol.delta.to_strike` with `delta` and `-delta`, each at its own vol. A vol `<= 0`: `E_DOMAIN`.

## SVI

Raw form, at one expiry: `w(k) = a + b (rho (k-m) + R)`, `R = sqrt((k-m)^2 + sigma^2)`.

Parameter object `svi`: `{a, b, rho, m, sigma}`. `b < 0`, `|rho| >= 1`, `sigma <= 0`, or `a + b sigma sqrt(1-rho^2) <= 0`: `E_DOMAIN`.

`w' = b (rho + (k-m)/R)`, `w'' = b sigma^2/R^3`.

Gatheral density function: `g = (1 - k w'/(2w))^2 - (w'^2/4)(1/w + 1/4) + w''/2`. `g < 0` at any `k` is butterfly arbitrage.

`vol.svi.evaluate`. Inputs: `svi`, `log_moneyness`, `expiry_years` (above 0, else `E_DOMAIN`). Outputs: `total_variance`, `implied_vol`, `g`, arrays; `min_g`; `butterfly_free`, `min_g >= 0` on the given points.

`vol.svi.calibrate`. Inputs: `log_moneyness` (strictly increasing, else `E_INPUT`), `total_variance`, optional `weights`. Minimise `sum weight (w_model - w)^2`, inside the domain above. Fewer than 5 points, or lengths that differ: `E_INPUT`. A `total_variance <= 0`, or non-positive weight: `E_DOMAIN`. Outputs: `svi`, `rmse`, the root of `sum weight e^2 / sum weight`. Any solver. Use several starts: a single one can stop in a local minimum. A build must find the global one on the golden cases.

## SSVI

`w(k, theta) = theta/2 (1 + rho phi k + sqrt((phi k + rho)^2 + 1 - rho^2))`, with the power law `phi(theta) = eta theta^-gamma (1+theta)^(gamma-1)`. `theta` is ATM total variance.

`|rho| >= 1`, `eta <= 0`, `gamma` outside `(0, 1]`, `theta <= 0`: `E_DOMAIN`. `thetas` not strictly increasing: `E_INPUT`.

`vol.ssvi.evaluate`. Inputs: `rho`, `eta`, `gamma`, `thetas`, `log_moneyness`. Outputs: `total_variance`, one row per theta; `butterfly_free`; `calendar_free`.

- `butterfly_free`: at every theta, `theta phi (1+|rho|) < 4` and `theta phi^2 (1+|rho|) <= 4`.
- `calendar_free`: at every theta, `rho^2 (1-gamma)/(1+theta) <= 1 + sqrt(1-rho^2)`. This is the Gatheral-Jacquier bound with the power-law derivative `d(theta phi)/d theta = phi (1-gamma)/(1+theta)`. The lower bound holds by `gamma <= 1`.

`vol.ssvi.calibrate`. Inputs: `thetas`, `log_moneyness`, `total_variance` (rows per theta). Outputs: `rho`, `eta`, `gamma`, `rmse`. Unweighted. Fewer than 3 points in all, or ragged rows: `E_INPUT`.

## Surface

Object `surface`: `{expiry_years, log_moneyness, vols}`, `vols` one row per expiry. Grids strictly increasing and shape matching, else `E_INPUT`. A grid time or vol `<= 0`: `E_DOMAIN`. Each grid at most 100 long, else `E_LIMIT`. Nodes hold at fixed log-moneyness, so a surface is in forward-moneyness terms.

`vol.surface.query`. Inputs: `surface`, `points`, array of `{expiry_years, log_moneyness}`. Outputs: `total_variance`, `vols`.

Rule: on each slice, `w` is linear in `k`, with `k` clamped to the grid. Between slices, `w` is linear in `T`. Before the first slice `w = w_1(k) T/T_1`, and after the last `w = w_n(k) T/T_n`, so flat vol in both directions. `expiry_years <= 0`: `E_DOMAIN`.

`vol.surface.check`. Input: `surface`. Outputs: `calendar_violations`, `butterfly_violations`, `arbitrage_free`. Lists are in row order, 0-based. All compare with a tolerance of `1e-12`.

- Calendar: `{expiry_index, k_index}` where `w[j][i] < w[j-1][i] - 1e-12`, `expiry_index` being `j`.
- Butterfly: per slice, undiscounted Black call `c_i` with `F = 1`, `K_i = exp(k_i)`, slopes `s_i = (c_{i+1}-c_i)/(K_{i+1}-K_i)`. `{expiry_index, k_index, kind}`: `SLOPE` at `i` if `s_i < -1 - 1e-12` or `s_i > 1e-12`; `CONVEXITY` at `i+1` if `s_{i+1} < s_i - 1e-12`. Within a slice, slope entries come first, then convexity.

## Limits of this stage

Linear surface interpolation can create butterfly arbitrage between nodes: the check covers nodes only. Stage E adds arbitrage-free interpolation and local vol.

## Acceptance

Targets in `stage-c-targets.md`. Suites `smile`, `surface`.
