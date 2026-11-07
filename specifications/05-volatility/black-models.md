# Black-Scholes, Black-76, Bachelier

Spec version 1.0.0. Status: Specified. Stage C.

European options only. `N` is the standard normal distribution function, `n` its density, `phi = +1` for `CALL`, `-1` for `PUT`.

## Models

| `model` | Extra inputs | Forward `F`, discount `D` |
|---|---|---|
| `BLACK_SCHOLES` | `spot`, `rate`, `yield` | `F = S exp((r-q)T)`, `D = exp(-rT)` |
| `BLACK_76` | `forward`, `discount_factor`, optional `shift` (default 0) | As given. `F` and `K` become `F+s`, `K+s` |
| `BACHELIER` | `forward`, `discount_factor` | As given. May be negative |

An input listed for another model, or a missing one: `E_SCHEMA`.

Lognormal: `d1 = (ln(F/K) + v^2 T/2)/(v sqrt T)`, `d2 = d1 - v sqrt T`, `V = D phi (F N(phi d1) - K N(phi d2))`.

Normal: `d = (F-K)/(v sqrt T)`, `V = D (phi (F-K) N(phi d) + v sqrt T n(d))`. `vol` here is in price units per square root of year.

`T = 0` or `v = 0`: `V = D max(phi (F-K), 0)`.

`N` must be good to 1e-14 absolute. `1 - N(x)` for large `x` must not be used for a small value: use `N(-x)`.

## Operations

Common inputs: `model`, `option_type`, `strike`, `expiry_years`, and the extra inputs above.

`vol.option.price`. Adds `vol`. Outputs: `price` per unit, `forward` (unshifted).

`vol.option.implied`. Adds `price`. Output: `vol`.

Checks for both, in order, all `E_DOMAIN`: `expiry_years < 0`; `vol < 0`; `discount_factor <= 0`; lognormal `spot`, or `forward + shift`, `<= 0`; lognormal `strike + shift <= 0`. Bachelier takes any `forward`, `strike`.

Further checks for `vol.option.implied`, `E_DOMAIN`: `expiry_years = 0`; `price < I`, where `I = D max(phi (F-K), 0)`; lognormal `price >= U`, with `U = D F` for a call and `D K` for a put. `price = I` exactly gives `vol = 0`. A solve that fails is `E_NO_CONVERGENCE`, but a correct build meets none on valid inputs. Any solver: the result is judged, not the path. Stop on `|V(v) - price| <= 1e-13 max(1, price)` or better.

## Limits of this stage

No American exercise. Implied vol is ill-conditioned when vega is tiny: goldens stop at `vega >= 1e-3 max(price, 1)`.

## Acceptance

Targets in `stage-c-targets.md`. Suites `black`, `black_deep`, `strata_vol`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Black, F. and Scholes, M., "The pricing of options and corporate liabilities", *Journal of Political Economy* 81(3), 1973, 637-654 (not opened)
- [S2] Black, F., "The pricing of commodity contracts", *Journal of Financial Economics* 3, 1976, 167-179 (not opened)
- [S3] Bachelier, L., *Théorie de la spéculation*, Annales scientifiques de l'École Normale Supérieure, 1900 (not opened)
- [S4] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Futures Options and Black's Model" (not opened)
