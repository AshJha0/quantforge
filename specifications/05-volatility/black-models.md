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

**Acceptance by the vol error (ruling KR-341, PROPOSED).** Plain idea: far out of the money the price is tiny, so a price residual of `1e-13 max(1, price)` says nothing about the vol; a build could stop anywhere. A returned `v` must also pass an estimate of its own relative error. With `M` the sum of the magnitudes of the two terms of `V` (lognormal `D (F N(phi d1) + K N(phi d2))`, normal `D (|F - K| N(phi d) + v sqrt T n(d))`), which bounds how much the rounding of their difference can be:

`e = (|V(v) - price| + 2^-52 M + 2^-1070 (1 + D (|F| + |K| + v sqrt T))) / (v vega(v))`

The last term covers subnormal intermediate values. If `v vega(v)` is not above 0, or `e > 1e-10`, the result is `E_NO_CONVERGENCE` (field `price`): the price does not identify the vol in binary64. Builds solve by Newton on `ln V(v) - ln price` inside the bracket (the same step as on `V - price` near the root), which keeps its size where `V` spans hundreds of decades.

Worked example (measured 2026-11-20, mpmath at 60 digits): Black-76 call, `F = 100`, `K = 300`, `T = 0.1`, `v = 0.1` has price `1.48e-265`; before this ruling Python returned 0.1234 and Java 0.1196 (both passed the price check, the residual being below `1e-12`); now every build returns 0.1. A Bachelier put at `K = 86.84`, `T = 2.91`, `v = 0.2027` has the subnormal price `1.58e-319`: `e = 3.4e-7`, so `E_NO_CONVERGENCE`. On 4,794 random deep cases (Black-76 and Bachelier, up to 40 standard deviations out) the largest error of an accepted vol was 404 times `e` (the `d^2` growth of the rounding of `N(d)`), so an accepted vol is good to about `4e-8` relative at worst; no accepted vol erred by more than `1e-8`. Goldens `ivdeep_c`.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Implied vol: Newton on `ln V - ln price` inside a bisection bracket (KR-341) | quadratic near the root, as Newton on `V - price`; the bracket halves on any rejected step | goldens `black`, `black_deep`, `e1_vol_1`, `ivdeep_c`; 4,794 random deep cases up to 40 standard deviations out (2026-11-20) | `price = I` gives `vol = 0` exactly; a price whose vol is not identified in binary64 (estimate `e > 1e-10`, for example a subnormal price) is `E_NO_CONVERGENCE` | mpmath at 60 digits (`oracle/python/gen_stage_k_rev1.py`) |

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
