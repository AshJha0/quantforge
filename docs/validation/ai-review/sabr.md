# Review request: SABR (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is filed under a labelled "AI review" section of the curve's evidence checklist and checked against the repository before anything is acted on.

Stage: C. Evidence line from the project's curve table: 64 golden cases for `vol.sabr.hagan`, `vol.sabr.density`, `vol.sabr.arbfree`, 26 with an outside library in `verified_by`.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.
8. Arbitrage-free SABR at `nu > 0` has no tight outside source (oracle README).

## Spec

### `specifications/05-volatility/black-models.md`

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

**Acceptance by the vol error (ruling KR-341, CONFIRMED 2026-11-21).** Plain idea: far out of the money the price is tiny, so a price residual of `1e-13 max(1, price)` says nothing about the vol; a build could stop anywhere. A returned `v` must also pass an estimate of its own relative error. With `M` the sum of the magnitudes of the two terms of `V` (lognormal `D (F N(phi d1) + K N(phi d2))`, normal `D (|F - K| N(phi d) + v sqrt T n(d))`), which bounds how much the rounding of their difference can be:

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


### `specifications/05-volatility/sabr.md`

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

**Evaluating `chi` (ruling KR-340, CONFIRMED 2026-11-21).** Plain idea: written as above, `chi` is the log of a number close to 1 when `z` is small, so it keeps only about `16 + log10|z|` digits, and for `z` far below 0 the sum `sqrt(...) + z - rho` cancels. Every build evaluates the same value from terms of one sign. With `d = z - rho`, `q = (1 - rho)(1 + rho)`:

- `s = hypot(d, sqrt(q))` (equal to `sqrt(1 - 2 rho z + z^2)`)
- `w = s + d` if `d >= 0`, else `w = q/(s - d)` (equal to `s + z - rho`)
- `u = (z/(s + 1)) (w/(1 - rho) + 1)` (equal to `w/(1 - rho) - 1`, the argument of the log less 1)
- `chi = log1p(u)` if `|u| < 1/2`; else `chi = ln(s + d) - log1p(-rho)` if `d >= 0`; else `chi = log1p(rho) - ln(s - d)`

Worked example (measured, mpmath at 50 digits plus two per decade of `|z|`, 2026-11-20): at `z = 1.01e-7`, `rho = 0.3` the direct form gives `m` with relative error 2.7e-9; the form above gives 3 ulp or less over `1e-7 <= |z| <= 1e307` and `|rho| <= 1 - 2^-53` (about 18,000 sampled points). The series below `1e-7` has a truncation error of order `z^3`, below `1e-20`. Goldens `sabrz_c` check `|z|` from `1e-8` to `1e5`, both signs of `rho`, at relative limit `1e-12`.
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

Outputs: `call_prices`; `vols`, the Black vol on `f0`, `x` of each price, or `null` where no finite vol exists: the price does not exceed intrinsic, or is at or above `f0` (ruling C16); `mass` (`sum Q h + P_L + P_R`); `mean` (`sum u Q h + u_max P_R`, on the shifted axis); `absorbed` (`P_L`); `min_density` (`min Q`).

## Limits of this stage

Backward Euler is first order in time, on purpose: it keeps `Q >= 0`. The result carries a grid error that the targets state. `beta = 1` is not offered. Heston and SLV are stage E.

## Acceptance

Targets in `stage-c-targets.md`. Suites `sabr`, `sabr_deep`, `strata_vol`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for 

[... truncated to fit one chat; the rest of this file is not included, so answer "cannot check" for anything that depends on it]

## Golden cases (19 of 65 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"sabr-0001","operation":"vol.sabr.hagan","inputs":{"forward":0.03,"strikes":[0.018,0.024,0.028499999999999998,0.03,0.0315,0.0375,0.048],"expiry_years":2.0,"alpha":0.04,"beta":0.5,"rho":-0.3,"nu":0.4},"expected":{"status":"ok","outputs":{"vols":[0.3132312101373863,0.2658807994902696,0.24132005765247522,0.23492372627921312,0.22935760129447622,0.21449644252696756,0.20823170937759167]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["quantlib-1.44"]}
{"case_id":"sabr-0002","operation":"vol.sabr.hagan","inputs":{"forward":100.0,"strikes":[60.0,80.0,95.0,100.0,105.0,125.0,160.0],"expiry_years":1.0,"alpha":3.0,"beta":0.5,"rho":-0.4,"nu":0.6},"expected":{"status":"ok","outputs":{"vols":[0.4277311493595516,0.354442247779285,0.31493795645311107,0.30442125000000003,0.29519840099340056,0.27059495038968,0.2620746513880662]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["quantlib-1.44"]}
{"case_id":"sabr-0003","operation":"vol.sabr.hagan","inputs":{"forward":100.0,"strikes":[60.0,80.0,95.0,100.0,105.0,125.0,160.0],"expiry_years":0.5,"alpha":0.25,"beta":1.0,"rho":-0.6,"nu":0.8},"expected":{"status":"ok","outputs":{"vols":[0.38526489121109186,0.3079055333966916,0.26203593970701966,0.24931666666666666,0.23817697278909827,0.21314391052705223,0.22540875770527766]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["quantlib-1.44"]}
{"case_id":"sabr-0004","operation":"vol.sabr.hagan","inputs":{"forward":0.01,"strikes":[-0.005999999999999998,0.0020000000000000018,0.008,0.010000000000000002,0.012000000000000004,0.020000000000000004,0.034],"expiry_years":5.0,"alpha":0.02,"beta":0.3,"rho":0.2,"nu":0.35,"shift":0.03},"expected":{"status":"ok","outputs":{"vols":[0.24483129626457256,0.21442043683627077,0.20321501848226864,0.20115447715499948,0.19975541794633328,0.19885198337525423,0.20541735968672825]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["quantlib-1.44"]}
{"case_id":"sabr-0005","operation":"vol.sabr.hagan","inputs":{"forward":1.0,"strikes":[0.6,0.8,0.95,1.0,1.05,1.25,1.6],"expiry_years":10.0,"alpha":0.25,"beta":0.0,"rho":0.1,"nu":0.3},"expected":{"status":"ok","outputs":{"vols":[0.36139815841930345,0.30786592958890335,0.2817640055876211,0.27497916666666666,0.2689840745055014,0.25131838266285805,0.2357871635946757]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["quantlib-1.44"]}
{"case_id":"sabr-0013","operation":"vol.sabr.density","inputs":{"forward":0.02,"strikes":[0.0005,0.001,0.002,0.004,0.008,0.012,0.02,0.03,0.05],"expiry_years":20.0,"alpha":0.03,"beta":0.5,"rho":-0.3,"nu":0.5,"h_strike":0.0002,"on_negative":"REPORT"},"expected":{"status":"ok","outputs":{"density":[-174.57449723243258,-136.37248758805592,-95.58399617654727,-56.62522555554411,-23.73696164001404,-4.21417830336751,43.797275756487025,19.603041425254702,0.9313033021195529],"min_density":-174.57449723243258,"negative_density":true}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-05,"relative":1e-06,"reason":"second difference: rounding of 1e-16 over h squared"},"verified_by":["analytic-replay"]}
{"case_id":"sabr-0015","operation":"vol.sabr.density","inputs":{"forward":0.01,"strikes":[-0.0095,-0.009000000000000001,-0.008,-0.006,-0.002,0.002,0.01,0.019999999999999997,0.04],"expiry_years":20.0,"alpha":0.03,"beta":0.5,"rho":-0.3,"nu":0.5,"h_strike":0.0002,"on_negative":"REPORT","shift":0.01},"expected":{"status":"ok","outputs":{"density":[-174.57449723243258,-136.37248758805592,-95.58399617654727,-56.62522555554411,-23.73696164001404,-4.21417830336751,43.797275756487025,19.603041425254702,0.9313033021195529],"min_density":-174.57449723243258,"negative_density":true}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-05,"relative":1e-06,"reason":"second difference: rounding of 1e-16 over h squared"},"verified_by":["analytic-replay"]}
{"case_id":"sabr-0017","operation":"vol.sabr.density","inputs":{"forward":100.0,"strikes":[60.0,80.0,100.0,120.0,150.0],"expiry_years":1.0,"alpha":3.0,"beta":0.5,"rho":-0.4,"nu":0.6,"h_strike":0.5,"on_negative":"REJECT"},"expected":{"status":"ok","outputs":{"density":[0.004626859734599975,0.009617017639527603,0.014205247989821146,0.011470337519781992,0.002792110702618089],"min_density":0.002792110702618089,"negative_density":false}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-05,"relative":1e-06,"reason":"second difference: rounding of 1e-16 over h squared"},"verified_by":["analytic-replay"]}
{"case_id":"sabr_deep-0001","operation":"vol.sabr.arbfree","inputs":{"forward":1.0,"expiry_years":1.0,"alpha":0.3,"beta":0.5,"rho":0.0,"nu":0.0,"shift":0.0,"cells":2000,"cells_below":500,"steps":1000,"strikes":[0.7,0.85,1.0,1.2,1.5]},"expected":{"status":"ok","outputs":{"call_prices":[0.3191193591190782,0.2049215774726455,0.11932955146446021,0.04968468034566087,0.009725606790348782],"vols":[0.32791261821244505,0.31263719059456563,0.3002387135643896,0.28675338530020367,0.27086312091275716],"mass":0.9999999999999969,"mean":0.9999999999999984,"absorbed":3.274227435933977e-10,"min_density":2.690847963772687e-12}},"tolerance_class":"numerical_scheme","tolerance_limit":null,"verified_by":["quantlib-1.44-cev"]}
{"case_id":"sabr_deep-0002","operation":"vol.sabr.arbfree","inputs":{"forward":1.0,"expiry_years":1.0,"alpha":0.3,"beta":0.25,"rho":0.0,"nu":0.0,"shift":0.0,"cells":2000,"cells_below":500,"steps":1000,"strikes":[0.7,0.85,1.0,1.2,1.5]},"expected":{"status":"ok","outputs":{"call_prices":[0.32191079210823703,0.20706677698256046,0.11946849970769581,0.04746576888830472,0.007681843113825378],"vols":[0.34284581272462633,0.31937795749895276,0.300590956530308,0.2804472717313126,0.2571368121271441],"mass":1.0000000000000129,"mean":1.000000000000003,"absorbed":1.7876407604199287e-05,"min_density":2.0164220391050537e-16}},"tolerance_class":"numerical_scheme","tolerance_limit":null,"verified_by":["quantlib-1.44-cev"]}
{"case_id":"sabr_deep-0003","operation":"vol.sabr.arbfree","inputs":{"forward":1.0,"expiry_years":2.0,"alpha":0.3,"beta":0.5,"rho":-0.4,"nu":0.5,"shift":0.0,"cells":1000,"cells_below":250,"steps":800,"strikes":[0.6,0.8,1.0,1.25,1.6]},"expected":{"status":"ok","outputs":{"call_prices":[0.44487778644964326,0.2915675435934761,0.17069593723404114,0.0752371067803112,0.021680955081619505],"vols":[0.40772903650148284,0.3466275477180167,0.30489626782577756,0.2740120078076997,0.25923426886966244],"mass":0.9999999999999996,"mean":1.0000000000000002,"absorbed":0.023010749703289746,"min_density":1.4145646539815998e-06}},"tolerance_class":"numerical_scheme","tolerance_limit":null,"verified_by":["hagan-formula-near","quantlib-1.44-noarbsabr-near"]}
{"case_id":"sabr_deep-0004","operation":"vol.sabr.arbfree","inputs":{"forward":0.02,"expiry_years":20.0,"alpha":0.03,"beta":0.5,"rho":-0.3,"nu":0.5,"shift":0.0,"cells":800,"cells_below":40,"steps":400,"strikes":[0.002,0.004,0.008,0.012,0.02,0.03,0.05]},"expected":{"status":"ok","outputs":{"call_prices":[0.018676807228749457,0.017366152667486878,0.0148015733172678,0.012357860340082879,0.008227201086342745,0.005476228784603462,0.00380199130941394],"vols":[0.47860943188974747,0.41436963229750756,0.3421096448268052,0.2960328226080087,0.24185667877946926,0.22928169485695002,0.2516845437579852],"mass":0.9999999999999972,"mean":0.019999999999999924,"absorbed":0.33597563775876427,"min_density":3.87093171497667e-06}},"tolerance_class":"numerical_scheme","tolerance_limit":null,"verified_by":["mass-and-mean"]}
{"case_id":"sabr_deep-0005","operation":"vol.sabr.arbfree","inputs":{"forward":0.01,"expiry_years":20.0,"alpha":0.03,"beta":0.5,"rho":-0.3,"nu":0.5,"shift":0.01,"cells":800,"cells_below":40,"steps":400,"strikes":[-0.008,-0.006,-0.002,0.002,0.01,0.019999999999999997,0.04]},"expected":{"status":"ok","outputs":{"call_prices":[0.018676807228749457,0.017366152667486878,0.0148015733172678,0.012357860340082879,0.008227201086342745,0.005476228784603462,0.00380199130941394],"vols":[0.47860943188974747,0.41436963229750756,0.3421096448268052,0.2960328226080087,0.24185667877946926,0.22928169485695002,0.2516845437579852],"mass":0.9999999999999972,"mean":0.019999999999999924,"absorbed":0.33597563775876427,"min_density":3.87093171497667e-06}},"tolerance_class":"numerical_scheme","tolerance_limit":null,"verified_by":["mass-and-mean"]}
{"case_id":"sabr_deep-0013","operation":"vol.sabr.arbfree","inputs":{"forward":1.0,"expiry_years":1.0,"alpha":0.3,"beta":0.5,"rho":-0.4,"nu":0.5,"shift":0.0,"cells":100,"cells_below":25,"steps":50,"strikes":[1e-20,1.0]},"expected":{"status":"ok","outputs":{"call_prices":[1.0000000000000009,0.1199666077089992],"vols":[null,0.3018537698912655],"mass":1.0000000000000007,"mean":1.0000000000000009,"absorbed":0.0016164658349306204,"min_density":2.8669657257164814e-07}},"tolerance_class":"numerical_scheme","tolerance_limit":null,"verified_by":["mass-and-mean"]}
{"case_id":"sabrz_c-0001","operation":"vol.sabr.hagan","inputs":{"forward":100.0,"strikes":[99.9999995],"expiry_years":1.5,"alpha":0.2,"beta":1.0,"rho":-0.4,"nu":0.4},"expected":{"status":"ok","outputs":{"vols":[0.20064000040128002]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":0.0,"relative":1e-12,"reason":"KR-340: chi(z) evaluated without cancellation; the direct form misses by 2.7e-9 at z = 1.01e-7"},"verified_by":["mpmath 50 digits (independent oracle, gen_stage_k_rev1.py)","scipy quad of chi = int_0^z dt/sqrt(1 - 2 rho t + t^2), a different formulation (library-primitive), within 1e-14"]}
{"case_id":"sabrz_c-0002","operation":"vol.sabr.hagan","inputs":{"forward":100.0,"strikes":[99.99999495000013],"expiry_years":1.5,"alpha":0.2,"beta":1.0,"rho":-0.4,"nu":0.4},"expected":{"status":"ok","outputs":{"vols":[0.20064000405292826]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":0.0,"relative":1e-12,"reason":"KR-340: chi(z) evaluated without cancellation; the direct form misses by 2.7e-9 at z = 1.01e-7"},"verified_by":["mpmath 50 digits (independent oracle, gen_stage_k_rev1.py)","scipy quad of chi = int_0^z dt/sqrt(1 - 2 rho t + t^2), a different formulation (library-primitive), within 1e-14"]}
{"case_id":"sabrz_c-0003","operation":"vol.sabr.hagan","inputs":{"forward":100.0,"strikes":[99.9999500000125],"expiry_years":1.5,"alpha":0.2,"beta":1.0,"rho":-0.4,"nu":0.4},"expected":{"status":"ok","outputs":{"vols":[0.20064004012802542]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":0.0,"relative":1e-12,"reason":"KR-340: chi(z) evaluated without cancellation; the direct form misses by 2.7e-9 at z = 1.01e-7"},"verified_by":["mpmath 50 digits (independent oracle, gen_stage_k_rev1.py)","scipy quad of chi = int_0^z dt/sqrt(1 - 2 rho t + t^2), a different formulation (library-primitive), within 1e-14"]}
{"case_id":"sabrz_c-0004","operation":"vol.sabr.hagan","inputs":{"forward":100.0,"strikes":[99.99500012499792],"expiry_years":1.5,"alpha":0.2,"beta":1.0,"rho":-0.4,"nu":0.4},"expected":{"status":"ok","outputs":{"vols":[0.20064401305413052]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":0.0,"relative":1e-12,"reason":"KR-340: chi(z) evaluated without cancellation; the direct form misses by 2.7e-9 at z = 1.01e-7"},"verified_by":["mpmath 50 digits (independent oracle, gen_stage_k_rev1.py)","scipy quad of chi = int_0^z dt/sqrt(1 - 2 rho t + t^2), a different formulation (library-primitive), within 1e-14"]}
{"case_id":"sabrz_c-0005","operation":"vol.sabr.hagan","inputs":{"forward":100.0,"strikes":[100.0000005],"expiry_years":1.5,"alpha":0.2,"beta":1.0,"rho":-0.4,"nu":0.4},"expected":{"status":"ok","outputs":{"vols":[0.20063999959872]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":0.0,"relative":1e-12,"reason":"KR-340: chi(z) evaluated without cancellation; the direct form misses by 2.7e-9 at z = 1.01e-7"},"verified_by":["mpmath 50 digits (independent oracle, gen_stage_k_rev1.py)","scipy quad of chi = int_0^z dt/sqrt(1 - 2 rho t + t^2), a different formulation (library-primitive), within 1e-14"]}
```

## Outside-library evidence and limits (from the project's own page)

Hagan volatilities are compared with QuantLib 1.44, and with Strata 2.12.78 on 18 of the golden cases. The density has replay cases only. The arbitrage-free form is compared with QuantLib's CEV engine at `nu = 0` and, coarsely, with `NoArbSabrSmileSection`, a different model of the floor. Targets and measured gaps are in `specifications/05-volatility/stage-c-targets.md`.

Golden cases with an `ok` result for `vol.sabr.hagan`, `vol.sabr.density`, `vol.sabr.arbfree`: 64, counted from `verified_by` in `datasets/golden/stage_c/`. All four builds passed them locally, which is self-assessment.

| Verified by | Operation | Cases |
|---|---|---|
| hagan-formula-near, quantlib-1.44-noarbsabr-near | vol.sabr.arbfree | 1 |
| mass-and-mean | vol.sabr.arbfree | 3 |
| quantlib-1.44-cev | vol.sabr.arbfree | 2 |
| analytic-replay | vol.sabr.density | 3 |
| mpmath 50 digits (independent oracle, gen_stage_k_rev1.py), scipy quad of chi = int_0^z dt/sqrt(1 - 2 rho t + t^2), a different formulation (library-primitive), within 1e-14 | vol.sabr.hagan | 32 |
| quantlib-1.44 | vol.sabr.hagan | 5 |
| strata-2.12.78, quantlib-1.44 | vol.sabr.hagan | 18 |

Limits:

- The density input is the golden long-expiry case: 20 years, forward 2%. The formula gives a negative density at most of these strikes. That is the point of the chart, and it does not say how SABR behaves at market parameters.
- The arbitrage-free form has a method error against Hagan where Hagan is safe. Mass, mean and absorbed mass are reported, and it is not a fit.
- Three separate inputs with different parameters, so the charts are not comparable with each other.

Synthetic inputs, not market data.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free option quotes or vol surfaces. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

- (stage-c-rulings.md) | C4 | Shifted Hagan SABR | Keeps the negative density. It may be used only through `vol.sabr.density` with `REJECT`, or be replaced by `vol.sabr.arbfree`. Plan section 8 |
- (stage-c-rulings.md) | C13 | `E_ARBITRAGE` | New in contract 1.4.0. Only `vol.sabr.density` with `REJECT` returns it in stage C |
- (stage-c-rulings.md) | C16 | `vol.sabr.arbfree`, price with no finite vol | `null` in `vols`, never an error: at or below intrinsic, or at or above `f0`. Prices and the other outputs stand. The Black solve is skipped, so it cannot fail |
- (stage-c-rulings.md) | C17 | Empty arrays | `E_INPUT`, as B3 and B6, for every stage C list but `dividends`, which may be empty: `strikes`, `log_moneyness`, `thetas`, `points`, `positions`, `quotes`, `slices`, `k_grid`. This is the first rule check, before every `E_DOMAIN`, and applies to `vol.sabr.hagan`, `density`, `arbfree` and `vol.svi.evaluate`, `vol.ssvi.evaluate` as much as to fits |
