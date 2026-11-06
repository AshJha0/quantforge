# Monte Carlo engine

Spec version 1.0.0. Status: Specified. Depends on `rng.md` and `sobol.md`.

Stage A holds the machinery and proves it on a European option under geometric Brownian motion. Draws
are fixed by `rng.md`, so a case has one right answer up to rounding.

## Operation `core.mc.gbm_european`

Inputs: `option` (`CALL`/`PUT`), `spot`, `strike`, `r`, `q`, `sigma`, `t`, `paths` `N`, `steps` `m` (default 1),
`seed` (u64 string), `stream` (default 0), `method`. Outputs: `price`, `stderr`.

Checks: `spot`, `strike`, `sigma`, `t <= 0`: `E_DOMAIN`. `N < 2`, `N > 10000000` or `m < 1`: `E_INPUT`. `method`
`SOBOL` with `m > 64`: `E_INPUT`.

**Path.** `dt = t/m`, `drift = (r - q - sigma^2/2) dt`, `vol = sigma sqrt(dt)`.
`ln S` starts at `ln(spot)` and adds `drift + vol z_j` for `j = 1..m`, in order. `S_T = exp` of that sum. Payoff
`P = max(S_T - K, 0)` or `max(K - S_T, 0)`, discounted by `exp(-r t)`.

**Draws.** Path-major: path 1 takes the first `m` normals of the stream, path 2 the next `m`, and so on.

**Sums** run in path order, in one sequence. A parallel build must reduce in that same order.

| `method` | Definition |
|---|---|
| `PLAIN` | `price` is the mean of the `N` discounted payoffs. `stderr = s / sqrt(N)`, `s` the sample deviation with divisor `N - 1` |
| `ANTITHETIC` | Each of `N` samples uses `z` and `-z` (one draw of `m` normals), and is the mean of the two discounted payoffs. Then as `PLAIN`. Total paths are `2N` |
| `CONTROL_VARIATE` | Control `C_i = exp(-r t) S_T,i`, with known mean `spot exp(-q t)`. `beta = cov(P, C)/var(C)`, both from the same `N` paths, divisor `N - 1`. `Y_i = P_i - beta (C_i - spot exp(-q t))`. Then as `PLAIN` on `Y` |
| `SOBOL` | Point `i` of `core.sobol.points` with `dimensions = m`, `skip = 0`, gives `z_j = PPND16(point[j])`. `seed` and `stream` are still required, and ignored. `stderr` is the `PLAIN` formula and is only indicative, as Sobol points are not independent |

A `P` here means the discounted payoff. Means and variances use two passes.

Sobol values can be exactly 0.5, which maps to `z = 0`. They never reach 0 or 1.

## Acceptance

Each case has two checks:
1. Same draws: `price`, `stderr` in class `common_rng` against the oracle's independent replay.
2. Truth: class `monte_carlo`: `|price - analytic| <= 4 stderr`, against the Black-Scholes value from mpmath. For
   `SOBOL` the limit is a per-case absolute limit, as `stderr` is not valid there.

Numeric targets: `spot = strike = 100`, `r = 0.05`, `q = 0.02`, `sigma = 0.2`, `t = 1`, `N = 100000`: `PLAIN` `stderr`
about 0.045. `ANTITHETIC` and `CONTROL_VARIATE` have lower `stderr` than `PLAIN`, and `SOBOL` with `N = 65536` has
error below 0.01. Oracle-measured values are in `oracle/REPORT.md`.
