# Monte Carlo Greeks: pathwise, likelihood ratio, smoothed digitals, bump with common draws

Spec version 1.0.0. Status: Specified (stage G, wave 3a, plan item Q9 part 1). Rulings: `stage-g-rulings.md` G-10, G-15. Suite `stage_g/mcgreeks_g` (21 cases), written by `oracle/python/gen_stage_g_q9.py`.

**Plain idea.** A Monte Carlo price has Greeks that can be estimated three ways. Bump the input and reprice on the same draws (simple, but noisy for jumps in the payoff). Differentiate each path's payoff (pathwise: low noise, but it fails for a digital, whose derivative is zero almost everywhere). Or differentiate the density instead of the payoff (likelihood ratio: works for any payoff, but noisy). A digital is handled pathwise by first smoothing its payoff into a narrow call spread. This page fixes each estimator exactly, on the shared random stream, so the four builds return the same numbers.

Sources:
- [G03] P. Glasserman, *Monte Carlo Methods in Financial Engineering*, Springer, 2003, sections 7.2 (pathwise, eqs. 7.18 and 7.21) and 7.3 (likelihood ratio, eqs. 7.37 and 7.39) (not opened in this session; the estimators are checked against their closed-form expectations).
- [BG96] M. Broadie, P. Glasserman, "Estimating security price derivatives using simulation", *Management Science* 42(2), 1996 (not opened).

Part 2 of Q9 (the model-reserve dispersion report over Heston, SLV and local vol on every exotic) is a later wave.

## `risk.mc.greeks`

### Inputs

- `spot` `S`, `strike` `K` (> 0), `expiry_years` `T` (> 0), `rate` `r`, `dividend_yield` `q` (any sign), `vol` `v` (> 0); else `E_DOMAIN`.
- `payoff`: `CALL`, `PUT`, `DIGITAL_CALL` (pays 1 if `S_T > K`); else `E_INPUT`.
- `method`: `PATHWISE`, `LIKELIHOOD_RATIO`, `BUMP`; else `E_INPUT`.
- `paths` `n` (Integer, at least 2, else `E_INPUT`, since a standard error needs two paths), `seed` (a decimal u64 string, else `E_SCHEMA`).
- `smoothing_width` `eps` (> 0, else `E_DOMAIN`): required for `PATHWISE` with `DIGITAL_CALL`, not allowed otherwise (`E_INPUT`).
- `bump_relative` `h` (in `(0, 1)`, else `E_DOMAIN`): required for `BUMP`, not allowed otherwise (`E_INPUT`).

### Draws (ruling G-15)

`core.rng` (`01-core/rng.md`) with `seed`, stream 0; one normal per path by AS 241, path `i` takes the `i`-th normal. `S_T = S exp((r - q - v^2/2) T + v sqrt(T) z)`, discount `D = e^{-rT}`.

### Per-path estimators

With `f(S_T)` the payoff and `dS_T/dv = S_T (sqrt(T) z - v T)`:

| Method | Price term | Delta term | Vega term |
|---|---|---|---|
| all | `D f(S_T)` | | |
| `PATHWISE`, `CALL` | | `D 1{S_T > K} S_T / S` | `D 1{S_T > K} dS_T/dv` |
| `PATHWISE`, `PUT` | | `-D 1{S_T < K} S_T / S` | `-D 1{S_T < K} dS_T/dv` |
| `PATHWISE`, `DIGITAL_CALL` | | `D 1{abs(S_T - K) < eps} / (2 eps) x S_T / S` | `D 1{abs(S_T - K) < eps} / (2 eps) x dS_T/dv` |
| `LIKELIHOOD_RATIO` | | `D f(S_T) z / (S v sqrt(T))` | `D f(S_T) ((z^2 - 1)/v - z sqrt(T))` |
| `BUMP` | | `(D f(S_T at S(1+h)) - D f(S_T at S(1-h))) / (2 h S)` | `(D f(S_T at v(1+h)) - D f(S_T at v(1-h))) / (2 h v)`, the drift's `v^2/2` moved with `v` |

The smoothed digital replaces the payoff by the call spread `(max(S_T - K + eps, 0) - max(S_T - K - eps, 0)) / (2 eps)` for the Greeks only; `price` is always the unsmoothed payoff.

### Outputs

`price`, `delta`, `vega`: the sample means of the per-path terms. `price_se`, `delta_se`, `vega_se`: the sample standard deviation (divisor `n - 1`) over `sqrt(n)`. Class `common_rng` (1e-9 absolute and relative). Sum in path order; a compensated sum (as the oracle's `math.fsum`) is allowed, since the class absorbs the difference.

### Error checks, in order (after F-2)

`payoff`, `method` `E_INPUT`; `paths < 2` `E_INPUT`; `seed` `E_SCHEMA` (a schema check, so it comes before F-2 in practice); `S`, `K`, `T`, `v` `E_DOMAIN`; `smoothing_width` and `bump_relative` presence `E_INPUT`, then value `E_DOMAIN`. `E_LIMIT`: paths 10,000,000 (as F-42).

## Validation cases and oracle

`mcgreeks_g`: every `payoff` x `method` pair at `S = K = 100`, `T = 1`, `r = 0.03`, `q = 0.01`, `v = 0.2`, 10,000 paths, seed 20261109 (9 cases); an out-of-the-money short-dated call (seed 7), a two-year digital (seed 42), a two-path put with a negative rate (seed 1); 9 error cases. Values: a float64 Python replica of the estimators on the `core.rng` stream. The generator asserts that no path's `S_T` (bumped `S_T` for `BUMP`) lies within 1e-9 relative of a kink (`K`, `K +- eps`), so an indicator cannot flip between builds. No outside library reproduces the `core.rng` stream, so no case counts as outside (as `risk.var.monte_carlo`, `OUTSIDE_GAPS_F.md`); the closed-form check below is the independent reference.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Each estimator | standard error falls as `N^-0.5` within 0.1 over 4 doublings | 12,500, 25,000, 50,000, 100,000 paths (first `n` of one seed-20261109 stream), `q = 0`. Measured 2026-11-10, delta SE slopes: digital LR -0.504, -0.502, -0.495; digital smoothed pathwise -0.505, -0.509, -0.511; call pathwise -0.501, -0.501, -0.499; call bump -0.501, -0.501, -0.499 | `eps -> 0`: smoothed pathwise digital delta tends to the true delta; `h -> 0`: bump tends to pathwise on a call | Black-Scholes closed-form price, delta and vega |

## Acceptance (plan 12.3 Q9 part 1, ruling G-10)

Digital call, `S = K = 100`, `T = 1`, `r = 0.03`, `q = 0`, `v = 0.2`, 100,000 paths, seed 20261109, `eps = 1`, `h = 0.01`. Oracle run 2026-11-10 (`oracle/Q9_ACCEPTANCE.json`): closed-form delta 0.0193334; smoothed pathwise 0.0187660 with per-path variance 0.0087549; bump 0.0187976 with variance 0.0087677; likelihood ratio 0.0193332 +- 0.0000896 (z = -0.002). Both conditions pass. Note that at `eps = 1` the likelihood-ratio delta has the lowest standard error of the three (9.0e-5 against 3.0e-4). **Open item:** the variance condition passes by a ratio of 0.9985 only. At these parameters a central bump of the digital with `h S = eps` is nearly the same call-spread estimator as the smoothed pathwise one, so the test has little power. The parameters were fixed before the run (12.10 rule) and are not changed here; a stronger test (for example `h = 0.001`, where the bump variance grows as `1/h`) needs an owner ruling.

Each language adds the acceptance as a property test with its own estimators (same seed and path count).

## Owner decision on the variance test (2026-11-10)

G-10 as registered is recorded as **inconclusive, low power** (not a pass). The powered test G-10b (registered with its power calculation before it ran; `stage-g-rulings.md`) compares smoothed pathwise (`eps = 1`) with a central bump at `h = 0.001` on independent `core.rng` streams, 60,000 paths each: variance ratio 0.1015, 95% interval [0.0888, 0.1161], `Z = 33.35`, **pass** (`oracle/G10B_RESULT.json`).
