# Question bank 2: Monte Carlo, QMC and AAD

This set is for readers learning how QuantForge simulates: the bit-exact random number generator, the Sobol sequence, the GBM Monte Carlo engine and its variance reduction, Monte Carlo Greeks, and the reverse-mode (AAD) ladder on the Hull-White Bermudan. Newcomers can read the plain idea at the top of each answer; practitioners and validators will want the formal rule and the closing line on what is checked. Every number in a worked example was produced by running `quantforge_core`, and `verify/v02_monte_carlo_aad.py` recomputes them all. Levels: foundation, practitioner, advanced. Seeds are given so you can reproduce each run.

## Random numbers

### Q2.1 Why does QuantForge specify its own random number generator instead of using each language's library?

*Level: foundation. Evidence: spec; design. Source: [Common random numbers](../../specifications/01-core/rng.md)*

Monte Carlo results from four language builds can only be compared tightly if all four draw exactly the same numbers. Library generators differ between languages and versions, so the generator is fixed in the specification, down to the bit.

Formal statement: "A language's own random library is not used for conformance." Seeding is SplitMix64 from `state = seed`, whose first four outputs fill the xoshiro256** state; all integer arithmetic is unsigned 64-bit with wrap-around (Java uses `long` and `>>>`, Python masks with `2^64 - 1`).

With identical draws, a Monte Carlo case has one right answer up to rounding, so the cross-language check (class `common_rng`) can be about 1e-9 rather than several standard errors. The oracle is checked against the published reference outputs carried in the `rand_xoshiro` 0.7.0 tests.

### Q2.2 How is a 64-bit generator output turned into a uniform, and why can it never be 0 or 1?

*Level: foundation. Evidence: computed; spec. Source: [Common random numbers](../../specifications/01-core/rng.md)*

The top 52 bits of the output are taken and centred in their cell by adding one half, so the result sits strictly inside `(0, 1)`. That matters because the inverse normal of 0 or 1 is infinite.

Formal statement: `u = ((x >> 12) + 0.5) * 2^-52`. "`x >> 12` has 52 bits, so the sum and the product are exact", and `u` lies in `[2^-53, 1 - 2^-53]`, bit-identical in all four languages.

**Worked example.** `core.rng` with seed 42, stream 0: first u64 = 1546998764402558742, and uniforms(seed 42) = 0.083862971060, 0.378980250663, 0.680043411028. The extremes are smallest u = 2^-53 = 1.110223e-16 and largest u = 1 - 2^-53 = 0.9999999999999999.

Uniforms are compared bit for bit (class `bit_exact`). A build that uses `x * 2^-64` instead would pass a quick visual check and fail every golden.

### Q2.3 Why does QuantForge make normals by inverse transform (AS 241) rather than Box-Muller?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Common random numbers](../../specifications/01-core/rng.md)*

Inverse transform uses exactly one uniform per normal, so draw `i` always belongs to the same path and step, and the same routine maps Sobol points to normals. Box-Muller uses two uniforms per pair and ziggurat a variable number, which breaks that alignment.

Formal statement: `z = PPND16(u)`, Wichura's AS 241, with the polynomial coefficients printed in the spec, evaluated by Horner. It uses only `log`, `sqrt` and rational functions, so languages agree to a few ulps, not to the bit; normals are compared in class `common_rng`. `inverse_normal` with `p` outside `(0, 1)` is `E_DOMAIN`.

**Worked example.** inverse_normal(0.975) = 1.959963984540; deep in the tail inverse_normal(1e-10) = -6.361340902; and inverse_normal(1.0): E_DOMAIN.

The oracle holds the constants to a relative error below 1e-15 against 50-digit `erfinv`, so the tails are as good as the centre.

### Q2.4 What is a stream, and how does QuantForge give independent streams from one seed?

*Level: practitioner. Evidence: computed; spec. Source: [Common random numbers](../../specifications/01-core/rng.md)*

A stream is a separate run of random numbers from the same seed, used, for example, to give each risk factor or each parallel worker its own draws without overlap. QuantForge makes stream `k` by jumping the generator ahead by `k` times 2^128 steps, so streams can never overlap in practice.

Formal statement: stream `k` (0 to 1023) is the seeded state advanced by `k` jumps with the xoshiro256** jump polynomial `J` listed in the spec. A stream out of range is `E_SCHEMA`.

**Worked example.** Seed 42: stream 0 starts at 0.083862971060 (Q2.2), while stream 1 first uniform = 0.312628684621.

The spec is candid that no published jump vector was found, so jump results rest on the oracle's own code. Monte Carlo Greeks always use stream 0 (ruling G-15).

### Q2.5 What does the `skip` input do, and how does it make runs reproducible in pieces?

*Level: practitioner. Evidence: computed; spec. Source: [Common random numbers](../../specifications/01-core/rng.md)*

`skip` throws away a number of draws first, so a run can start at any point in a stream. Combined with a fixed seed, any slice of a long simulation can be regenerated exactly.

Formal statement: `core.rng.next_u64`, `uniforms` and `normals` take `seed` (a decimal u64 string), `stream`, `count` (at least 1) and optional `skip` (default 0). Upper limits are in `limits.md`.

**Worked example.** With seed 42, the first 8 uniforms compared with 5 uniforms after skipping 3: skip=3 matches draws 4 to 8: True. Drawing 1,000 normals with seed 7 twice: same seed twice identical: True.

This is how a failing path in a large run is reproduced on its own: compute its offset and skip to it, rather than rerunning everything.

### Q2.6 Why are uniforms compared bit for bit but normals only to `common_rng`?

*Level: advanced. Evidence: spec; design. Source: [Common random numbers](../../specifications/01-core/rng.md), [Monte Carlo engine](../../specifications/01-core/monte-carlo.md)*

Uniforms come from integer operations and one exact floating multiply, so every correct build produces the same bits. Normals pass through `log` and `sqrt`, whose last bit may differ between language runtimes.

Formal statement: "Integers and uniforms: exact. Normals: class `common_rng`." The Monte Carlo engine's acceptance has two checks: same draws, price and stderr in class `common_rng` against the oracle's replay; and truth, `|price - analytic| <= 4 stderr` (class `monte_carlo`).

The split tells a reviewer where to look when a case fails. A uniform mismatch is a generator bug; a normal mismatch of a few ulps is expected and absorbed; a price outside `common_rng` with identical normals means the payoff, discounting or summation order differs.

## Sobol and quasi-Monte Carlo

### Q2.7 What is a Sobol sequence, and what are its first few points in two dimensions?

*Level: foundation. Evidence: computed; spec; literature. Source: [Sobol sequence](../../specifications/01-core/sobol.md)*

Sobol points fill the unit cube more evenly than random draws, so integrals often converge faster than the `1/sqrt(N)` of plain Monte Carlo. The sequence is deterministic: it is defined by direction numbers, which are data.

Formal statement: Gray-code construction; to go from index `i` to `i + 1`, find the lowest zero bit `c` of `i` and set `x[d] ^= v_d[c]`; the point is `x[d] * 2^-32`, exact in binary64.

**Worked example.** `core.sobol.points(2, 4)` gives Sobol 2-d points: (0.5, 0.5), (0.75, 0.25), (0.25, 0.75), (0.375, 0.375).

Each new point lands in the largest remaining gap. The output is compared exactly against QuantLib `SobolRsg` (JoeKuoD6) and unscrambled SciPy `qmc.Sobol`.

### Q2.8 Why does QuantForge never return Sobol point index 0?

*Level: foundation. Evidence: spec. Source: [Sobol sequence](../../specifications/01-core/sobol.md)*

Point 0 is the origin, and the inverse normal of 0 is minus infinity, so a simulation that used it would produce an infinite path.

Formal statement: "Index 0 is never returned: the first point served is index 1, `(0.5, 0.5, ...)`." `skip` throws away points after index 0, so the indices used run `skip+1 .. skip+count`. Sobol values can be exactly 0.5, which maps to `z = 0`, and never reach 0 or 1 (Monte Carlo spec).

Other libraries differ here: some return the origin first and leave it to the caller to drop. When comparing against an outside Sobol generator, align the indices before blaming the direction numbers.

### Q2.9 Where do QuantForge's Sobol direction numbers come from, and how many dimensions are supported?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Sobol sequence](../../specifications/01-core/sobol.md)*

Direction numbers decide how well the projections of the sequence fill the cube. QuantForge uses the Joe and Kuo table, which was built for good two-dimensional projections.

Formal statement: `specifications/01-core/data/sobol-joe-kuo-d6-64.json` holds the first 64 dimensions of `new-joe-kuo-6.21201`: degree `s`, coefficient word `a`, initial numbers `m[1..s]`. Dimension 1 uses `v[k] = 1 << (32 - k)`; others use `m[k] << (32 - k)` for `k <= s` and the recurrence in the spec beyond. Maximum dimension is 64.

**Worked example.** Asking for 65 dimensions: sobol dimensions 65: E_INPUT. In the Monte Carlo engine, `method` `SOBOL` uses one dimension per time step, so 65 steps fails too: SOBOL 65 steps: E_INPUT.

64 dimensions is enough for a single-asset path of up to 64 steps. Multi-asset or long-dated Sobol paths are outside the stage A engine.

### Q2.10 Is the Sobol standard error reported by the engine a valid error bar?

*Level: advanced. Evidence: computed; spec. Source: [Monte Carlo engine](../../specifications/01-core/monte-carlo.md), [Sobol sequence](../../specifications/01-core/sobol.md)*

No. A standard error assumes independent samples, and Sobol points are deliberately not independent. QuantForge applies no scrambling or digital shift, so there are no independent randomisations from which an honest error bar could be built.

Formal statement: for `SOBOL`, "`stderr` is the `PLAIN` formula and is only indicative, as Sobol points are not independent". `seed` and `stream` are still required and ignored. The truth check for `SOBOL` is a per-case absolute limit, not `4 stderr`. Target: `N = 65536` error below 0.01.

**Worked example.** ATM call, `S = K = 100`, `r = 0.05`, `q = 0.02`, `sigma = 0.2`, `t = 1`: SOBOL: price 9.225903, stderr 0.054010, error -0.001103. The reported 0.054 overstates the actual error about fifty times.

A validator who sees a Sobol "stderr" in a report should treat it as a diagnostic only. Randomised QMC (scrambled Sobol) is not implemented.

### Q2.11 Does QuantForge use a Brownian bridge with Sobol, and why does that matter for multi-step paths?

*Level: advanced. Evidence: computed; spec. Source: [Monte Carlo engine](../../specifications/01-core/monte-carlo.md), [Sobol sequence](../../specifications/01-core/sobol.md)*

No. Sobol dimension `j` drives time step `j` directly. QMC works best when the first, best-distributed dimensions carry most of the variance; with step-by-step construction every step carries the same share, so the later, weaker dimensions matter as much as the first. A Brownian bridge would put the terminal value on dimension 1; QuantForge does not implement one.

Formal statement: "Point `i` of `core.sobol.points` with `dimensions = m`, `skip = 0`, gives `z_j = PPND16(point[j])`", and the log price adds `drift + vol z_j` for `j = 1..m` in order.

**Worked example.** Same ATM call with 12 steps and 4,096 Sobol paths: SOBOL 12 steps, 4096 paths: error -0.089643, against -0.001103 for the one-step, 65,536-path run of Q2.10. Under GBM the European payoff depends only on the sum of the 12 normals, so the extra dimensions only add discrepancy.

For a European payoff use one step; GBM is sampled exactly, so steps add nothing. Path-dependent QMC with good effective dimension would need a bridge or PCA construction, which is a known gap.

## The Monte Carlo engine

### Q2.12 How does `core.mc.gbm_european` simulate a path, and is there discretisation error?

*Level: foundation. Evidence: spec; literature. Source: [Monte Carlo engine](../../specifications/01-core/monte-carlo.md)*

The engine simulates the logarithm of the price, which under geometric Brownian motion has normal increments, so each step is exact whatever its size. There is no time-discretisation bias, only sampling error.

Formal statement: `dt = t/m`, `drift = (r - q - sigma^2/2) dt`, `vol = sigma sqrt(dt)`; `ln S` starts at `ln(spot)` and adds `drift + vol z_j` for `j = 1..m`; payoff discounted by `exp(-r t)`. `spot`, `strike`, `sigma`, `t <= 0` is `E_DOMAIN`; `N < 2` or `m < 1` is `E_INPUT`.

The `- sigma^2/2` term is the Ito correction that makes the forward `spot exp((r - q) t)` come out right. Leaving it out biases every call upward; it is the first thing to check when a Monte Carlo price sits a few standard errors high on every seed.

### Q2.13 What standard error does a plain Monte Carlo ATM call give with 100,000 paths, and is the price within the acceptance limit?

*Level: foundation. Evidence: computed; spec. Source: [Monte Carlo engine](../../specifications/01-core/monte-carlo.md)*

The standard error is the sample standard deviation of the discounted payoffs divided by `sqrt(N)`. It measures how far the estimate is likely to be from the true price.

Formal statement: `PLAIN` `price` is the mean of `N` discounted payoffs, `stderr = s / sqrt(N)`, divisor `N - 1`, means and variances by two passes. Acceptance: `|price - analytic| <= 4 stderr`. Target: `PLAIN` stderr about 0.045 at these inputs.

**Worked example.** `S = K = 100`, `r = 0.05`, `q = 0.02`, `sigma = 0.2`, `t = 1`, `N = 100000`, seed 20261115: Black-Scholes = 9.227006 (scratch closed form); PLAIN: price 9.333222, stderr 0.043988, error +0.106217, so error in stderr units = +2.41.

A 2.4-sigma miss on one seed is unusual but legitimate, which is why the limit is 4 standard errors and not 2: a 2-sigma limit would fail about one honest case in twenty.

### Q2.14 How does the standard error scale with the number of paths?

*Level: foundation. Evidence: computed; spec. Source: [Monte Carlo engine](../../specifications/01-core/monte-carlo.md), [Monte Carlo Greeks](../../specifications/06-risk/mc-greeks.md)*

The standard error falls as `1/sqrt(N)`: four times the paths halves the error. Accuracy is therefore expensive, and variance reduction is usually cheaper than more paths.

Formal statement: `stderr = s / sqrt(N)`. The Monte Carlo Greeks spec asserts the `N^-0.5` order for every estimator and measured slopes between -0.495 and -0.511 over four doublings.

**Worked example.** Same ATM call, seed 20261115: N = 1000: stderr 0.4336; N = 4000: stderr 0.2252; N = 16000: stderr 0.1098.

Each quadrupling roughly halves the error. To go from the 0.044 of Q2.13 to 0.001 would take about 2,000 times as many paths.

### Q2.15 How much does antithetic sampling reduce the variance on the ATM call?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Monte Carlo engine](../../specifications/01-core/monte-carlo.md)*

Antithetic sampling pairs each draw `z` with `-z`. For a payoff that rises with `z`, the two errors tend to cancel, so the pair's average varies less than two independent paths would.

Formal statement: "Each of `N` samples uses `z` and `-z` (one draw of `m` normals), and is the mean of the two discounted payoffs. Then as `PLAIN`. Total paths are `2N`." Target: lower stderr than `PLAIN`.

**Worked example.** `N = 100000`, seed 20261115: ANTITHETIC: price 9.225117, stderr 0.023079, error -0.001889. Against plain, variance ratio antithetic/plain = 0.275.

The fair comparison counts work: antithetic uses `2N` payoffs, so the gain per payoff evaluation is a ratio of about 0.55, still a real saving. For payoffs symmetric in `z` (a straddle near the money) antithetics help little.

### Q2.16 How does the control variate work in the engine, and how much does it help?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Monte Carlo engine](../../specifications/01-core/monte-carlo.md)*

The discounted terminal stock price has a known mean. Its simulated mean errs in the same direction as the option's, so subtracting a multiple of its error corrects the option estimate.

Formal statement: control `C_i = exp(-r t) S_T,i`, known mean `spot exp(-q t)`; `beta = cov(P, C)/var(C)`, both from the same `N` paths, divisor `N - 1`; `Y_i = P_i - beta (C_i - spot exp(-q t))`; then `PLAIN` on `Y`.

**Worked example.** `N = 100000`, seed 20261115: CONTROL_VARIATE: price 9.216397, stderr 0.017963, error -0.010608, with variance ratio control/plain = 0.167, with no extra paths.

Estimating `beta` from the same paths introduces a small bias of order `1/N`, which is negligible here; the spec accepts it for simplicity. The control is strongest in the money and weakest far out of the money, where the call and the stock are less correlated.

### Q2.17 How does plain Monte Carlo with 100,000 paths compare with Sobol with 65,536 points on the same option?

*Level: practitioner. Evidence: computed; spec. Source: [Monte Carlo engine](../../specifications/01-core/monte-carlo.md)*

For a smooth, low-dimensional problem, Sobol's even coverage gives an error that falls close to `1/N` rather than `1/sqrt(N)`, so fewer points beat more random paths.

Formal statement: `SOBOL` uses `z_j = PPND16(point[j])` from `core.sobol.points`; target error below 0.01 at `N = 65536`. `PLAIN` is judged by `4 stderr`.

**Worked example.** One step, ATM call: PLAIN: price 9.333222, stderr 0.043988, error +0.106217 with 100,000 paths; SOBOL: price 9.225903, stderr 0.054010, error -0.001103 with 65,536 points.

Powers of two are the natural Sobol sample sizes, as the sequence is balanced at each one, which is why the target uses 65,536. The advantage shrinks with dimension and with payoff discontinuities (Q2.11).

### Q2.18 Why does the engine fix the order of draws and sums, and what does that mean for a parallel build?

*Level: advanced. Evidence: spec; design. Source: [Monte Carlo engine](../../specifications/01-core/monte-carlo.md)*

Floating-point addition is not associative: summing the same payoffs in a different order gives a slightly different total. To get one right answer across four languages and any thread count, both the assignment of draws to paths and the order of summation are fixed.

Formal statement: "Path-major: path 1 takes the first `m` normals of the stream, path 2 the next `m`, and so on." "Sums run in path order, in one sequence. A parallel build must reduce in that same order." Means and variances use two passes.

A parallel build may simulate paths on many threads but must hand back the payoffs in path order for the reduction, or use an exact (compensated) summation that the tolerance class absorbs. Breaking this does not usually change the price at the 4-stderr level, which is why it is easy to miss; it shows up only as a `common_rng` failure.

## Monte Carlo Greeks

### Q2.19 What are the three Monte Carlo Greek estimators in QuantForge, in one line each?

*Level: foundation. Evidence: spec; literature. Source: [Monte Carlo Greeks](../../specifications/06-risk/mc-greeks.md)*

Bump: move the input and reprice on the same draws. Pathwise: differentiate each path's payoff with respect to the input. Likelihood ratio: leave the payoff alone and differentiate the probability density, giving a weight that multiplies the payoff.

Formal statement: `risk.mc.greeks` with `method` `PATHWISE`, `LIKELIHOOD_RATIO` or `BUMP`, `payoff` `CALL`, `PUT` or `DIGITAL_CALL`. Draws: `core.rng`, seed given, stream 0, one normal per path by AS 241; `S_T = S exp((r - q - v^2/2) T + v sqrt(T) z)` (ruling G-15). Outputs `price`, `delta`, `vega` and their standard errors with divisor `n - 1`.

Pathwise is low-noise but needs a payoff that is differentiable almost everywhere. Likelihood ratio works for any payoff but is noisier. Bump is the simplest and needs a choice of bump size. Sources: Glasserman (2003), sections 7.2 and 7.3; Broadie and Glasserman (1996).

### Q2.20 What are the pathwise delta and vega of an ATM call on the golden parameters, and how close are they to Black-Scholes?

*Level: practitioner. Evidence: computed; spec; golden. Source: [Monte Carlo Greeks](../../specifications/06-risk/mc-greeks.md)*

For a call, the payoff's derivative with respect to spot is the indicator that the option finishes in the money times `S_T / S`. Averaging that over paths estimates delta.

Formal statement: `PATHWISE`, `CALL`: delta term `D 1{S_T > K} S_T / S`; vega term `D 1{S_T > K} dS_T/dv` with `dS_T/dv = S_T (sqrt(T) z - v T)`, `D = e^{-rT}`.

**Worked example.** `S = K = 100`, `T = 1`, `r = 0.03`, `q = 0.01`, `v = 0.2`, 10,000 paths, seed 20261109: call PATHWISE: delta 0.567128 (se 0.005831), vega 38.4717 (se 0.7349). The scratch closed form gives closed-form call delta = 0.573496, vega = 38.7152; both estimates are about one standard error away. The library reproduces the conformance case: golden mcgreeks_g-0001 delta 0.567128, library differs by 0e+00.

Vega here is per unit of volatility (per 1.00, that is per 100 vol points); divide by 100 for a per-vol-point figure.

### Q2.21 Why does the pathwise method fail for a digital call, and how does QuantForge fix it?

*Level: practitioner. Evidence: computed; spec. Source: [Monte Carlo Greeks](../../specifications/06-risk/mc-greeks.md)*

A digital pays 1 or 0, so its derivative along each path is zero almost everywhere: the pathwise estimate would be exactly zero. QuantForge replaces the digital by a narrow call spread for the Greeks only, which has a non-zero slope within `eps` of the strike.

Formal statement: smoothed payoff `(max(S_T - K + eps, 0) - max(S_T - K - eps, 0)) / (2 eps)`; delta term `D 1{abs(S_T - K) < eps} / (2 eps) x S_T / S`. `smoothing_width` is required for `PATHWISE` with `DIGITAL_CALL` and not allowed otherwise; `price` is always the unsmoothed payoff.

**Worked example.** Golden parameters as Q2.20, `eps = 1`: digital PATHWISE: delta 0.019883 (se 0.000962), against closed-form digital delta = 0.019358 (scratch formula). Without the width: digital PATHWISE without width: E_INPUT.

The smoothing biases the answer (the spread is not the digital), and the bias falls as `eps -> 0` while the variance grows. A desk chooses `eps` deliberately; the spec records the limit case "smoothed pathwise digital delta tends to the true delta".

### Q2.22 How does the likelihood-ratio method estimate a digital's delta, and how does its noise compare?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Monte Carlo Greeks](../../specifications/06-risk/mc-greeks.md)*

Likelihood ratio moves the dependence on spot from the payoff into the density of `S_T`. The weight `z / (S v sqrt(T))` is the derivative of the log density, and it needs no derivative of the payoff, so discontinuous payoffs are fine and no smoothing bias appears.

Formal statement: delta term `D f(S_T) z / (S v sqrt(T))`; vega term `D f(S_T) ((z^2 - 1)/v - z sqrt(T))`.

**Worked example.** Golden parameters, 10,000 paths, seed 20261109: digital LIKELIHOOD_RATIO: delta 0.019219 (se 0.000283), a third of the smoothed pathwise error bar. For the call it is the other way round: call LIKELIHOOD_RATIO: delta 0.568857 (se 0.013621), vega 38.1801 (se 2.4982), with a delta error bar more than twice the pathwise 0.005831.

The rule of thumb holds: pathwise for smooth payoffs, likelihood ratio for discontinuous ones. The spec's acceptance run also found LR delta had the lowest error of the three at `eps = 1`.

### Q2.23 How does the bump estimator stay low-noise, and how does it relate to pathwise?

*Level: practitioner. Evidence: computed; spec. Source: [Monte Carlo Greeks](../../specifications/06-risk/mc-greeks.md)*

Bumping on the same draws (common random numbers) means the up and down prices share their noise, which cancels in the difference. Without common draws the difference of two noisy prices divided by a small bump would be useless.

Formal statement: delta term `(D f(S_T at S(1+h)) - D f(S_T at S(1-h))) / (2 h S)`; vega the same in `v`, with the drift's `v^2/2` moved with `v`. `bump_relative` `h` in `(0, 1)` is required for `BUMP` and not allowed otherwise.

**Worked example.** Golden parameters, `h = 0.01`: call BUMP: delta 0.568044 (se 0.005776), vega 38.4726 (se 0.7349), next to pathwise delta 0.567128 and vega 38.4717. For the digital: digital BUMP: delta 0.019894 (se 0.000962).

As `h -> 0` the bump tends to pathwise on a call. On a digital, a central bump with `h S = eps` is nearly the same call-spread estimator as smoothed pathwise, which is why the two digital numbers above almost coincide.

### Q2.24 What input checks does `risk.mc.greeks` apply, and in what order?

*Level: foundation. Evidence: computed; spec. Source: [Monte Carlo Greeks](../../specifications/06-risk/mc-greeks.md)*

The checks are ordered so that every build reports the same error for the same bad input, which matters because error cases are part of the conformance suite.

Formal statement: `seed` `E_SCHEMA` first; then `payoff`, `method` `E_INPUT`; `paths < 2` `E_INPUT` ("since a standard error needs two paths"); `S`, `K`, `T`, `v` `E_DOMAIN`; `smoothing_width` and `bump_relative` presence `E_INPUT`, then value `E_DOMAIN`. Paths above 10,000,000 are `E_LIMIT`.

**Worked example.** One path: paths = 1: E_INPUT. A smoothed digital without a width: digital PATHWISE without width: E_INPUT.

The suite has 21 cases, 9 of them error cases, so ordering is tested, not just documented.

### Q2.25 What did the G-10 variance test find, and why was it re-run as G-10b?

*Level: advanced. Evidence: spec; design. Source: [Monte Carlo Greeks](../../specifications/06-risk/mc-greeks.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

G-10 asked whether smoothed pathwise has lower variance than bumping for a digital delta. It passed, but only by a ratio of 0.9985, because at the fixed parameters (`h S = eps`) the two estimators are almost the same thing, so the test had little power.

Formal statement: acceptance run (digital, `S = K = 100`, `T = 1`, `r = 0.03`, `q = 0`, `v = 0.2`, 100,000 paths, seed 20261109, `eps = 1`, `h = 0.01`): closed-form delta 0.0193334, smoothed pathwise 0.0187660, bump 0.0187976, LR 0.0193332. The owner recorded G-10 as "inconclusive, low power", not a pass. G-10b, registered with its power calculation before it ran, compared `eps = 1` with a bump at `h = 0.001` on independent streams, 60,000 paths each: variance ratio 0.1015, 95% interval [0.0888, 0.1161], `Z = 33.35`, pass.

The lesson is procedural: the parameters of G-10 were not changed after the result (the 12.10 rule); a new, powered test was registered instead.

## AAD and the ladder

### Q2.26 What is reverse-mode AAD, and why is QuantForge's ladder cost bounded at five pricings?

*Level: foundation. Evidence: spec; literature; design. Source: [AAD core on the rates models](../../specifications/06-risk/aad-core.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

Bumping each input costs one repricing per input. Reverse-mode automatic differentiation records one pricing and runs it backwards, accumulating the derivative of the price with respect to every input at once, so the whole ladder costs a small fixed multiple of one pricing however many inputs there are.

Formal statement (G-9): median of 21 timed runs after 5 warm-ups of (a) one Hull-White Bermudan PV and (b) PV plus full ladder by reverse-mode AAD, same process and thread; pass when `median(b)/median(a) <= 5`. Sources: Giles and Glasserman, "Smoking adjoints" (2006); Griewank and Walther (2008).

QuantForge's Python adjoint is written by hand (`aad_ladder.py`): one forward sweep stores coefficients, Thomas solutions and exercise decisions, and one backward sweep runs the transposed tridiagonal solves. The spec session had no AAD build, so no ratio is recorded in the spec; each language reports its own.

### Q2.27 What does the ladder give on golden case `aadladder_g-0001`, and how is each entry read?

*Level: practitioner. Evidence: computed; golden; spec. Source: [AAD core on the rates models](../../specifications/06-risk/aad-core.md)*

The ladder is the price of a Bermudan payer swaption together with its derivative with respect to every curve discount factor, the mean reversion `a` and the volatility `sigma`.

Formal statement: `rates.shortrate.bermudan_ladder` returns `price`, `d_price_d_discount_factors` (per unit absolute change of each pillar's discount factor, not per bp of a rate), `d_price_d_mean_reversion` and `d_price_d_sigma` (per unit change).

**Worked example.** Notional 1,000,000, `a = 0.05`, `sigma = 0.01`, `nx = 101`, 50 steps a year: price = 22,697.81; d_price_d_sigma = 2,269,595, so 1bp of sigma adds about 227; d_price_d_mean_reversion = -52,528. Per pillar (0.5y to 30y): d_price_d_discount_factors = 127, 191,964, 173,816, 147,510, -233,482, -343,473, 0, 0, 0, 0. Against the golden: largest relative gap to the golden reference = 5e-10.

A higher long discount factor lowers the forward swap rate and so cheapens a payer, hence the negative 5- and 7-year entries; pillars beyond the last payment have zero sensitivity.

### Q2.28 Why must the ladder not be used as a hedge at the default grid?

*Level: advanced. Evidence: spec; golden; design. Source: [AAD core on the rates models](../../specifications/06-risk/aad-core.md)*

AAD differentiates exactly what is computed: the discrete PDE scheme on its grid, not the continuous Hull-White model. On a coarse grid the price can be accurate while its derivatives are not.

Formal statement (the spec, citing ruling R6-27): each output is "a derivative of the discrete scheme at the case's grid, not a model sensitivity". On `aadladder_g-0001` the 1-year discount-factor entry is 191,964 at the golden grid (101 points, 50 steps a year), 220,895 at 401 and 200, and 225,712 at 801 and 400, while the price moves only from 22,697.8 to 22,751.8 (0.24%). At the default grid the entries differ from converged ones by up to about 18%.

So a converged outside library cannot check the discount-factor entries; only the price, `d_price_d_mean_reversion` and `d_price_d_sigma` can be compared that way. The fix, a second-order scheme or Richardson extrapolation, is stage K item K-8. Use a finer grid (the `r6/aadladder_r6` golden is within 2% of the 801/400 reference) or treat the ladder as a test of the AAD.

### Q2.29 How is the AAD ladder checked, and why was one candidate case dropped?

*Level: advanced. Evidence: spec; golden; design. Source: [AAD core on the rates models](../../specifications/06-risk/aad-core.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

The reference is a carefully extrapolated bump. If two independent bump pairs disagree, a bump has pushed an exercise decision across a grid node, the derivative is not defined there, and the case is not judged.

Formal statement (G-35, Q3a rule): `D(h) = (V(x(1+h)) - V(x(1-h)))/(2 h x)` with relative bumps `h = 1e-4` and `5e-5`; `ref = (4 D(h/2) - D(h))/3`, with `h^4` truncation. A second pair (`5e-5`, `2.5e-5`) must agree within 1e-9 relative, else the case is dropped. Tolerance (G-9): `abs(AAD - ref) <= 1e-10 + 1e-8 abs(ref)` per unit notional, class `aad_sensitivity`; price at 1e-9 relative.

`bermudan_g-0001` at the coarser grid was dropped with agreement 1.1e-9; the three kept cases agreed to 2.9e-10, 6.8e-10 and 9.0e-10. No outside library differentiates this scheme, so the bump reference is the only independent check (G-18).
