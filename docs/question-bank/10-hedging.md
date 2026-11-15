# Question bank 10: Hedging and hedge solvers

This set is for two readers: someone meeting hedge maths for the first time, and a practitioner who wants to check how QuantForge pins down the details (sign conventions, units, tie rules, error codes). Each answer starts with the plain idea, then gives the rule as the spec states it, then a worked example where numbers help. Every number in a worked example was produced by `quantforge_core` and is re-checked by `docs/question-bank/verify/v10_hedging.py`. Levels: foundation (the idea and the convention), practitioner (using the operation and reading its output), advanced (edge cases, rulings and why the spec chose what it chose). Try to answer before reading the answer.

All hedges here start from no hedge position, use synthetic inputs, and are calculations with no connection to a market. The specs are in [`specifications/08-hedging`](../../specifications/08-hedging/README.md).

## The common form

### Q10.1 What does QuantForge mean by the residual `A x + b`, and which way round are the signs?

*Level: foundation. Evidence: spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Stage B hedges](../../specifications/08-hedging/stage-b-hedges.md)*

A hedge adds positions whose risks cancel the book's risks. QuantForge writes the book's existing risk as a vector `b` (one entry per risk factor), the hedge instruments' risk per unit as a matrix `A` (one row per factor, one column per instrument), and the hedge positions as `x`. What is left after hedging is the residual `r = A x + b`.

So `b` enters with a plus sign: the solver looks for the `x` that drives `A x + b` towards zero, and a positive `x` is a long position. Most hedges in domain 08 are one problem, weighted least squares on that residual (`hedge.qp.solve`), with optional bounds, equalities, costs and a margin limit; the minimum-variance, Greek and beta hedges are closed forms of the same idea. Stage B's `hedge.solve` uses the same form with a linear spread cost and covers single-instrument, DV01, duration, key-rate and FX hedges by changing only `A` and `b`.

The pitfall is feeding `-b` (the risk you want to add) instead of `b` (the risk you have): the answer comes back with every sign flipped and doubles the risk.

### Q10.2 How do you delta-hedge a short call with the underlying in QuantForge, and how many shares does it take?

*Level: foundation. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Tutorial 17](../getting-started/tutorial-17-delta-hedge.md)*

A delta hedge holds enough of the underlying that a small move in spot leaves the book's value unchanged. With one target (`DELTA`) and one hedge (`UNDERLYING`, delta 1), `hedge.greeks.neutralise` solves `G q = -g_book`, a 1 x 1 system.

The Greeks are Black-Scholes-Merton with flat inputs: `d1 = (ln(S/K) + (r - q + v^2/2) T) / (v sqrt T)`, call delta `e^{-qT} N(d1)`.

**Worked example.** Spot 100, rate 3%, dividend yield 1%, volatility 25%. The book is short 100 six-month 100 calls. Book delta = -55.4846, so the hedge buys 55.4846 shares. After the hedge, delta is 0, but gamma stays at -2.2220 and vega at -2777.54 per unit of volatility, because shares carry neither.

The desk cares that a delta hedge holds only at today's spot and volatility: the short gamma means the hedge goes stale as soon as spot moves, which is why it is rebalanced (Q10.19).

### Q10.3 Why does a delta-gamma hedge need an option as well as the underlying, and how is the 2 x 2 solve read?

*Level: practitioner. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Tutorial 17](../getting-started/tutorial-17-delta-hedge.md)*

Shares have gamma 0 and vega 0, so they can fix delta and nothing else. To cancel gamma you need an instrument with gamma, an option. The spec requires as many hedges as targets (ruling I-9), at most 3 hedges (I-4), and solves the square system `G q = -g_book`, with `G` a row per target and a column per hedge.

Read it in order: the option alone must cancel the gamma, because the shares contribute none; the shares then take whatever delta is left, including the option's own delta.

**Worked example.** The book of Q10.2 (short 100 six-month 100 calls; spot 100, `r` 3%, `q` 1%, vol 25%). Hedges: the underlying and a three-month 110 call; targets `DELTA`, `GAMMA`. Result: 33.4427 shares and 86.7802 of the 110 calls. Delta and gamma after are 0; vega after is -1388.77 per unit of volatility, about half the book's, since vega was not targeted.

The pitfall is reading "gamma-neutral" as "hedged": the untargeted Greeks (here vega) are still open, and the hedge itself has to be redone as spot moves.

### Q10.4 In what unit does QuantForge quote vega in a Greek hedge?

*Level: foundation. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md)*

Vega is the value change per unit of volatility, where a unit is 1.00, i.e. 100 volatility points. The spec says so explicitly: `vega = S e^{-qT} n(d1) sqrt T`, "per unit of volatility (not per 1%; I-9)".

**Worked example.** The book of Q10.2 has vega -2777.54 per unit of volatility. Per volatility point (0.01) that is -27.7754: if implied volatility rises from 25% to 26%, the short calls lose about 27.78.

This matters when you compare with a trading screen, which usually quotes vega per point. Mixing the two is a factor-of-100 error. Gamma is per unit of spot squared and delta per unit of spot, with the underlying at delta 1, gamma 0, vega 0.

### Q10.5 What happens if two hedge instruments in a Greek hedge carry the same risks?

*Level: practitioner. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md)*

The square matrix `G` then has two equal columns, so it is singular and there is no unique answer. QuantForge refuses rather than picking one: check 3 of `hedge.greeks.neutralise` returns `E_SINGULAR` when the smallest singular value of `G` is at most `1e-12` times its largest (ruling I-3, applied after the scaling of R6-6.2).

**Worked example.** Book: short 100 six-month 100 calls. Hedges: two identical six-month 105 calls; targets `DELTA`, `GAMMA`. The library returns `E_SINGULAR`.

Other checks come first, in order: shapes and key rules (`E_INPUT`: no hedges, `len(targets) != len(hedges)`, a repeated target), then the domain (`E_DOMAIN`: spot, volatility, strike or expiry at or below 0). An unknown target string is `E_SCHEMA` (ruling I-42). For a least-squares Greek hedge with more instruments than targets, the spec points you to `hedge.qp.solve` with `A = G` and `b = g_book`.

## Least squares, bounds and singular problems

### Q10.6 What does `hedge.qp.solve` minimise, and what is its answer without constraints?

*Level: foundation. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Tutorial 18](../getting-started/tutorial-18-minvar-qp.md)*

It minimises the weighted sum of squared residual risks, plus an optional ridge penalty on position size:

`f(x) = sum_i w_i (A x + b)_i^2 + ridge * sum_j x_j^2`

subject to optional equalities `E x = e` and bounds. With no constraints and a regular problem, the minimiser is the weighted least-squares solution `x = -(A^T W A + ridge I)^{-1} A^T W b`.

**Worked example.** Two risk factors, one instrument: `A = [[2], [1]]`, `b = (-3, -1)`, weights 1 and 1. Then `x = 1.400000`, residual `(-0.2, 0.4)` and objective 0.200000. One instrument cannot cancel two risks, so the objective stays above zero; the solver splits the miss between the factors in proportion to their weights.

Outputs are `x`, `residual`, `objective` and `rank` (`n - k` on a regular problem). The weights are where a desk says which risks it cares about most.

### Q10.7 Why is clipping the unconstrained solution to its bounds not the same as solving with bounds?

*Level: practitioner. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Tutorial 18](../getting-started/tutorial-18-minvar-qp.md)*

When one position hits a bound, the other positions should move to take up part of its job. Clipping leaves them where the free solution put them. The spec defines the answer as the unique minimiser of `f` on the feasible set, characterised by the KKT conditions [NW06 12.1]; "bounds ignored (the free solution clipped instead of re-solved)" is one of the mutants the goldens catch.

**Worked example.** `A = [[1, 0.5], [0.5, 1]]`, `b = (-2, 0.5)`, weights 1. The free solution is `x = (3, -2)` with objective 0. Add long-only bounds (`lower = (0, 0)`). Clipping gives `(3, 0)` with objective 5.000000. The bounded solve gives `x = (1.4, 0)` with objective 1.800000: the first instrument shrinks because it no longer has the second to offset its effect on factor 2.

The desk lesson: a liquidity or long-only limit changes every position, not only the one at its limit.

### Q10.8 What does `E_INFEASIBLE` mean, and when does `hedge.qp.solve` return it?

*Level: foundation. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [CLI contract](../../specifications/cli-contract.md)*

It means no point satisfies all the constraints at once, so there is nothing to minimise over. The code was added in contract 1.11.0 (ruling I-1) and is check 6 of `hedge.qp.solve`, after shapes, domain, equality rank and the reduced Hessian. The feasibility tolerance is `1e-9` relative (R6-11.3); the margin limit of the cost wave is counted too.

**Worked example.** Two instruments with bounds `0 <= x_j <= 2` and the equality `x_1 + x_2 = 5`. The largest sum the box allows is 4, so the library returns `E_INFEASIBLE`.

`hedge.integer.solve` never returns it: a box of integers is never empty after its domain check. `hedge.select.solve` avoids it by refusing bounds that exclude 0 (`E_DOMAIN`), because an instrument left out sits at 0.

### Q10.9 Two hedge instruments are identical. What does QuantForge return by default, and what does `MIN_NORM` change?

*Level: advanced. Evidence: computed; spec; design. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Stage I rulings](../../specifications/stage-i-rulings.md), [Tutorial 18](../getting-started/tutorial-18-minvar-qp.md)*

Any split between two identical instruments hedges equally well, so the minimiser is not unique. The default policy `singular = ERROR` returns `E_SINGULAR` (check 5: an eigenvalue of the reduced Hessian `Z^T H Z` at most `1e-12` times the largest eigenvalue of `H`). `MIN_NORM` instead returns the minimiser of least Euclidean norm, `x = -(A^T W A + ridge I)^+ A^T W b` without equalities [GV13 5.5].

**Worked example.** `A = [[1, 1], [0.5, 0.5]]`, `b = (-2, -1)`. Default: `E_SINGULAR`. `MIN_NORM`: `x = (1, 1)`, rank 1, the even split. A ridge of 0.01 also makes the problem regular and gives 0.996016 of each, slightly short of a full hedge because size now costs something.

`ERROR` is the default by design (ruling I-5): a desk would rather learn it has a duplicate than have a solver pick a split for it. `MIN_NORM` with bounds is refused (`E_INPUT`), not solved.

### Q10.10 Why does QuantForge scale a matrix before deciding that it is singular?

*Level: advanced. Evidence: spec; design. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [R6 rulings](../../specifications/r6-rulings.md)*

A relative threshold such as `1e-12` is only meaningful if the matrix entries are on comparable scales. A hedge problem that mixes basis-point risks with currency risks, or weights from `1e-3` to `1e3`, can look singular in raw units when it is perfectly regular.

Ruling R6-6.2 (amending I-3) therefore tests a symmetric matrix `M` as `D M D` with `D_jj = 1/sqrt(M_jj)`; equality rows are scaled to unit norm with the same column scaling; and the reduced Hessian is `Z^T (D H D) Z` compared with the largest eigenvalue of `D H D`. A zero or negative diagonal entry is itself singular. Scaling never changes the solution, only the decision. Case `r6/hedgescale_r6` pins it.

One exception is recorded honestly: `hedge.crossasset.solve` keeps the wave 1 unscaled test and says it is not scale-invariant, which is why its zero-coupon bond carries a `notional` (ruling I-22). The goldens keep every decision at least a factor `1e3` from the threshold so that SVD, QR, eigenvalue and Cholesky builds all agree.

### Q10.11 What does a ridge do to a hedge, and when would you use it?

*Level: practitioner. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md)*

A ridge adds `ridge * sum_j x_j^2` to the objective, so large positions cost something. It makes `H = A^T W A + ridge I` strictly positive definite, turning a singular or near-singular problem into a regular one, and it shrinks positions towards zero.

**Worked example.** The duplicate-instrument problem of Q10.9 (`A = [[1, 1], [0.5, 0.5]]`, `b = (-2, -1)`) is `E_SINGULAR` without a ridge. With `ridge = 0.01` it solves to 0.996016 in each instrument, with objective 0.019920: a small residual risk accepted in exchange for smaller positions.

Use it when two instruments are near-duplicates (two bonds a few months apart) and the unregularised answer is long one and short the other in large size. The limit `ridge -> 0` on a regular problem tends to plain weighted least squares. The price is a residual that is no longer the smallest possible, so report the ridge with the hedge.

## Integer lots and closed-form hedges

### Q10.12 Why is rounding the continuous hedge not the best whole-lot hedge?

*Level: practitioner. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Tutorial 18](../getting-started/tutorial-18-minvar-qp.md)*

When instruments are correlated, the objective's contours are long thin ellipses tilted away from the axes. The nearest lattice point to the continuous optimum by rounding each coordinate need not be the lattice point with the lowest objective. `hedge.integer.solve` searches the integers properly (branch and bound or ellipsoid enumeration [FP85]); "naive rounding for integer lots" is a mutant the goldens catch.

**Worked example.** `A = [[1, 0.95], [0.95, 1]]`, `b = (-1.265, -1.27)`, lot sizes 1. The continuous answer is `(0.6, 0.7)` with objective 0. Rounding gives `(1, 1)` with objective 0.931625. The integer solve returns lots `[0, 1]` with objective 0.172125, so `rounding_cost = objective - continuous_objective` = 0.172125.

Outputs include `continuous_objective` (the relaxation with lot bounds as real bounds) so the cost of whole lots is visible. The search stops with `E_NO_CONVERGENCE` after 1,000,000 lattice points or nodes.

### Q10.13 How does QuantForge break ties between equally good integer hedges?

*Level: advanced. Evidence: spec; design. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Stage I rulings](../../specifications/stage-i-rulings.md)*

Four languages must return the same lots, so ties cannot be left to the search order. Ruling I-7: objectives within `1e-12` relative of the best are tied (R6-11.5 sets the scale as `1e-12 max(best, f(0))`); among tied candidates the smallest `sum |n_j|` wins, then the lexicographically smallest `n`.

The plain reading: prefer fewer contracts, then a fixed order. The goldens hold either exact ties in binary (cases `hedgeint_i-0007` to `-0009` pin the rule) or a runner-up more than `1e-9` relative above the best, so a build with slightly different rounding cannot land on the other answer. `hedge.select.solve` uses the same idea for subsets (I-34): smallest subset, then the lexicographically smallest index list.

The design point is general in QuantForge: wherever an answer could be non-unique, a ruling fixes the choice, and the goldens are built to sit well away from the boundary.

### Q10.14 What is the minimum-variance hedge ratio, and why does QuantForge report it with the opposite sign to Hull?

*Level: foundation. Evidence: computed; spec; literature. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Tutorial 18](../getting-started/tutorial-18-minvar-qp.md)*

The minimum-variance hedge holds the amount of a hedge instrument that makes the hedged position's value change as small as possible in variance. `hedge.minvar.ratio` returns `hedge = -S_hh^{-1} S_he`, the units held (negative is short). For one instrument this is `-rho sigma_S / sigma_F`. Hull writes `h* = rho sigma_S / sigma_F` because he quotes the size of a short hedge [H18 ch. 3]; QuantForge reports the position, so the sign is negative (ruling I-8).

**Worked example.** `sigma_S = 0.02`, `sigma_F = 0.019`, `rho = 0.9`, so the covariance is `[[0.0004, 0.000342], [0.000342, 0.000361]]`. The hedge is -0.947368 units, the hedged variance falls from 0.0004 to 0.000076, and the effectiveness is 0.810000, which is `rho^2` for one instrument.

The pitfall is the estimate itself: the ratio is only as good as the covariance history behind it.

### Q10.15 When `hedge.minvar.ratio` is given series rather than a covariance, which variance divisor does it use, and does it matter?

*Level: practitioner. Evidence: spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Dynamic hedge and effectiveness](../../specifications/08-hedging/dynamic-hedge-and-effectiveness.md)*

Given `exposure_changes` (length `T`) and `hedge_changes` (`k` series), it forms the sample covariance with divisor `T - 1` (ruling I-8). It needs `T >= k + 2` observations, else `E_INPUT`.

For the hedge ratio and the effectiveness the divisor cancels: both are ratios of covariances. It would matter only for an output that reports a variance in absolute terms, which is why the choice is pinned anyway: `variance_before` and `variance_after` are reported, and "population divisor for the sample variances" is a mutant the goldens catch. The same `n - 1` rule is used by `hedge.effectiveness` (Q-I16).

Other checks in order: one form or the other, never both (`E_INPUT`); `S_00 <= 0` (`E_DOMAIN`); a Cholesky pivot of the hedge block at or below `1e-12` of the scaled form (`E_SINGULAR`), a negative pivot (`E_NOT_POSITIVE_DEFINITE`, R6-11.7); a hedged variance below `-1e-12 S_00` (`E_NOT_POSITIVE_DEFINITE`), with smaller negatives returned as 0 (I-44).

### Q10.16 How many index futures does it take to hedge an equity portfolio's beta?

*Level: foundation. Evidence: computed; spec; literature. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Tutorial 18](../getting-started/tutorial-18-minvar-qp.md)*

A portfolio with beta `beta` moves about `beta` times as much as the index. Futures on the index add beta at `F m / V` per contract, so the number of contracts that moves the beta to a target is `contracts = (beta* - beta) V / (F m)`, positive long [H18 ch. 3].

**Worked example.** Hull's example: a 5,050,000 portfolio with beta 1.5, index futures at 1,010 with multiplier 250, target beta 0. `contracts = (0 - 1.5) x 5,050,000 / (1,010 x 250)` = -30, so sell 30 contracts; `beta_after` = 0.

The spec also returns `contracts_held`, rounded half away from zero under the default `NEAREST` (ruling I-10), and `beta_after` on the held number. Golden `hedgebeta_i-0001` reproduces Hull's 30 contracts.

### Q10.17 A beta hedge works out at exactly -2.5 contracts on paper. Why might QuantForge hold -2 rather than -3?

*Level: advanced. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [R6 rulings](../../specifications/r6-rulings.md)*

Because the "exact" -2.5 is not exact in binary floating point. Ruling R6-11.12 fixes the order of operations, `((target_beta - beta) * V) / (F * m)`, then rounds half away from zero. If the computed value lands a hair inside -2.5, it rounds to -2.

**Worked example.** `V = 1,000,000`, `beta = 1.2`, target 1.0, `F = 1,000`, `m = 80`. On paper `(1.0 - 1.2) x 1,000,000 / 80,000 = -2.5`. In binary64, `1.0 - 1.2` is -0.19999999999999996, so `contracts` = -2.499999999999999, `contracts_held` = -2 and `beta_after` = 1.0400.

Fixing the order of operations is what makes the four builds agree on this; without it one language could round to -3. "Round half to even" is a separate mutant the goldens catch. A desk that wants the unrounded figure asks for `rounding = NONE`.

### Q10.18 How does `hedge.residual.report` show where the risk left after a hedge sits?

*Level: practitioner. Evidence: computed; spec. Source: [Hedge solvers](../../specifications/08-hedging/hedge-solvers.md), [Tutorial 18](../getting-started/tutorial-18-minvar-qp.md)*

Given a hedge `x` and a covariance `S` of the factor moves, it reports the variance before (`b^T S b`) and after (`r^T S r`, with `r = A x + b`), the effectiveness `1 - variance_after / variance_before` (below 0 for an over-hedge), and each factor's Euler contribution `r_i (S r)_i`, which sum to `variance_after` (ruling I-11; not divided by the variance).

**Worked example.** `A = [[1], [0.5]]`, `b = (-1, -1)`, `x = 1.2`, `S = [[0.0001, 0.00005], [0.00005, 0.0004]]`. Residual `(0.2, -0.4)`; variance 0.0006 before, 0.00006 after; effectiveness 0.900000. The contributions are about 0 for factor 1 and 0.00006 for factor 2: all the remaining variance sits in factor 2.

A contribution can be zero or negative even when that factor's residual is not zero, because of the covariance term; it says where to look for a better hedge, not which residual is largest. `b^T S b <= 0` is `E_DOMAIN`, an exact sign test by design.

## Dynamic hedging and effectiveness

### Q10.19 How does `hedge.backtest.delta` replay a delta hedge, and why is the portfolio worth zero at the start?

*Level: foundation. Evidence: spec. Source: [Dynamic hedge and effectiveness](../../specifications/08-hedging/dynamic-hedge-and-effectiveness.md), [Tutorial 17](../getting-started/tutorial-17-delta-hedge.md)*

It takes a given spot path (it does not simulate), marks the option at the hedge volatility each date, holds minus the option's delta in shares, and keeps the rest in a cash account. Rebalancing is self-financing, so nothing enters or leaves after the start; what is left at the end is the hedging error.

Ruling I-29: shares over `[t_i, t_{i+1}]` are `h_i = -quantity Delta_i`. Start with `cash = -quantity V_0 - h_0 S_0`, so `Pi_0 = 0`: the option premium and the share purchase are financed through cash. Each step: `cash <- cash e^{r dt} + h_i S_i (e^{q dt} - 1)`, then `Pi_{i+1} = quantity V_{i+1} + h_i S_{i+1} + cash`, then (except on the last date) `cash <- cash - (h_{i+1} - h_i) S_{i+1}`. At expiry the option is worth its payoff.

`final_pnl` is `Pi` on the last date. Limits stated in the spec: one option, a flat hedge volatility, a continuous dividend yield, and costs only through the optional wave 4e inputs.

### Q10.20 A short call is delta-hedged daily at a 20% hedge volatility. Why does the P&L depend on the path's realised volatility?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Dynamic hedge and effectiveness](../../specifications/08-hedging/dynamic-hedge-and-effectiveness.md), [Tutorial 17](../getting-started/tutorial-17-delta-hedge.md)*

A delta-hedged short option is short gamma. Each step it earns about `-(1/2) Gamma S^2 (realised variance - hedge variance) dt` [Hull ch. 19]: it gains when the market moves less than the volatility sold and loses when it moves more.

**Worked example.** Short 10 calls, strike 100, 30 days, rate 3%, no dividends, hedge volatility 20%, daily path 100, 101, 99.5, 100.5, 101.5, 100.8 (times in days / 365). The library gives `final_pnl` = -0.0507, dollar offset 0.9775 and R² 0.9991. The path's realised volatility (root mean square daily log return, annualised over 365 days, a scratch formula, not the library) is 20.38%, just above the 20% sold, so a small loss is what the formula predicts.

The spec does not assert that more frequent rebalancing reduces the error on one path: that is a distributional statement (a research study), not a golden. One path proves nothing about frequency.

### Q10.21 What are the four effectiveness measures, and why can a good hedge fail the dollar-offset test?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Dynamic hedge and effectiveness](../../specifications/08-hedging/dynamic-hedge-and-effectiveness.md), [Tutorial 17](../getting-started/tutorial-17-delta-hedge.md)*

With `x` the hedged item's changes and `y` the hedge's, sample statistics over `n - 1` (I-30, I-31): `dollar_offset = -sum(y)/sum(x)` (cumulative), `regression_slope = cov(x, y)/var(x)` (about -1 for a good hedge), `regression_r2`, and `variance_reduction = 1 - var(x + y)/var(x)`. Under IAS 39 a hedge was highly effective with a dollar offset in `[0.80, 1.25]` (AG105).

**Worked example.** `x = (10, -8, 5, -6)`, `y = (-9, 7.5, -5.5, 6.2)`. The dollar offset is 0.8000, right on the IAS 39 edge, while the slope is -0.954394, R² 0.994837 and the variance reduction 0.993192.

The dollar offset divides two totals, and the item's total here is small (1) next to its period moves, so a small difference becomes a large ratio [FG02]. That is why the spec reports the regression measures beside it. A near-zero `sum(x)` or variance is `E_DOMAIN` by the relative tests of I-43.

### Q10.22 In the delta-hedge replay, when are interest and dividends credited, and why does the order matter?

*Level: advanced. Evidence: spec; design. Source: [Dynamic hedge and effectiveness](../../specifications/08-hedging/dynamic-hedge-and-effectiveness.md), [Stage I rulings](../../specifications/stage-i-rulings.md)*

Each step, cash first grows by `e^{r dt}`, then the shares held earn a continuous dividend yield on their value at the start of the step, `h_i S_i (e^{q dt} - 1)`; both are credited before the rebalance (ruling I-29, question Q-I14).

The order is a convention, and the spec says so. Other conventions (dividends on the end-of-step value, or reinvested in shares) change the result by about `q dt` relative per step. Four builds can only agree to rounding if they all use the same one, so the spec picks one and pins it. A mutant that drops the dividends on the hedge shares moves `final_pnl` by 13 on a golden, and the goldens catch it.

The same care applies to costs (wave 4e, rulings I-39 and I-40): the initial purchase is a trade, so `Pi_0 = -cost(h_0)`; each rebalance cost is paid after `Pi_{i+1}` is recorded, so it shows in the next step; there is no unwind at the end.

## Costs, the frontier and slippage

### Q10.23 How does a spread cost make the solver drop an instrument exactly, rather than hold a tiny amount of it?

*Level: practitioner. Evidence: computed; spec. Source: [Hedge costs and frontier](../../specifications/08-hedging/hedge-costs-and-frontier.md), [Tutorial 21](../getting-started/tutorial-21-hedge-costs.md)*

A half-spread cost `h_j |x_j|` charges the same for the first unit as for the hundredth, so a small position in an expensive instrument costs more than the little risk it removes. Because `|x|` has a kink at 0, the optimum can sit exactly at 0.

The wave 4a objective is `f(x) = sum_i w_i r_i^2 + ridge |x|^2 + cost_weight * C(x)`, `C(x) = sum_j (half_spreads_j |x_j| + impact_j x_j^2)`. At `x_j = 0` the subgradient condition is `|g_j| <= cost_weight half_spreads_j + mu margin_rates_j`.

**Worked example.** `A = [[1, 0.9], [0.5, 1]]`, `b = (-2, -1)`, half-spreads `(0.01, 0.5)`. The answer is `x = (1.996, 0)`, the second instrument exactly 0; risk 2.0e-05, cost 0.01996. With both half-spreads at 0.01 the second instrument comes back at 0.002479.

Outputs `risk`, `cost` (and `margin`) appear only when a cost input is given, so wave 1 results keep their exact output set (I-27).

### Q10.24 Market impact makes a singular hedge problem regular, but a spread cost does not. Why?

*Level: advanced. Evidence: spec; design. Source: [Hedge costs and frontier](../../specifications/08-hedging/hedge-costs-and-frontier.md), [Stage I rulings](../../specifications/stage-i-rulings.md)*

Impact is quadratic: a trade of size `x` moved wholly to a price displaced by `impact x` costs `impact x^2` (Almgren-Chriss temporary impact, R6-11.10). A quadratic term adds `cost_weight diag(impact)` to the Hessian, exactly as a ridge does, so the singularity checks use `H = A^T W A + ridge I + cost_weight diag(impact)` and a duplicate pair can become regular.

A spread cost is linear in `|x|`. It adds nothing to the Hessian, so it cannot make a flat direction curved; a problem singular without it stays singular (ruling I-26).

Limits the spec states: square-root impact (`|x|^{3/2}`), common in practice, is not a QP and is not covered; the hedge starts from no position, so there is no cost on `x - x_0`; margin is linear in `|x|` per instrument with no netting.

### Q10.25 What does the risk-against-cost frontier show, and what shape must it have?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Hedge costs and frontier](../../specifications/08-hedging/hedge-costs-and-frontier.md), [Tutorial 21](../getting-started/tutorial-21-hedge-costs.md)*

`hedge.frontier.solve` solves the costed hedge for a list of cost weights, so you can read off how much risk you give up for each saving in cost. On a convex problem, `risk` is non-decreasing and `cost` non-increasing in the weight [BV04]; the generator asserts this on every golden.

**Worked example.** `A = [[1, 0.9], [0.5, 1]]`, `b = (-2, -1)`, half-spreads 0.1 and impact 0.05 on both instruments, weights 0, 1, 4:

| cost weight | risk | cost |
|---|---|---|
| 0 | 0 | 0.400000 |
| 1 | 0.0371966 | 0.310183 |
| 4 | 0.212201 | 0.230239 |

Weight 0 is the risk-only hedge. Inputs: 1 to 50 weights, strictly increasing, and at least one of `half_spreads` or `impact` (else `E_INPUT`). The desk picks a point where the next saving in cost is not worth the extra risk.

### Q10.26 How are liquidity and margin limits expressed in a QuantForge hedge?

*Level: foundation. Evidence: spec. Source: [Hedge costs and frontier](../../specifications/08-hedging/hedge-costs-and-frontier.md)*

A liquidity limit, a cap on how much of an instrument can be traded, needs no new input: it is a bound, `lower_j <= x_j <= upper_j`, already part of `hedge.qp.solve`.

A margin limit is a new optional pair, `margin_rates` (per instrument, each `>= 0`) and `margin_limit` (`>= 0`), both or neither. It adds the constraint `sum_j margin_rates_j |x_j| <= margin_limit`, and the output `margin` reports the margin used. A margin limit that the bounds or equalities cannot meet is `E_INFEASIBLE`.

Limits stated in the spec: margin is linear in `|x|` per instrument, with no netting and no portfolio margin model. Mutants caught by the goldens include "the margin constraint ignored".

### Q10.27 After a hedge is traded, how does QuantForge measure what it really cost against the cost model?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Hedge slippage](../../specifications/08-hedging/hedge-slippage.md), [Tutorial 21](../getting-started/tutorial-21-hedge-costs.md)*

Implementation shortfall measures cost against the price when the decision was made, split into the cost of what was filled and the opportunity cost of what was not [P88]. Slippage is the realised execution cost minus the model's cost for the same filled size.

Per order (I-36, I-37): `execution_cost = sum q (p - d)`, `opportunity_cost = (Q - q_f)(final_price - d)`, `shortfall` their sum, `model_cost = half_spread |q_f| + impact q_f^2` on the filled size, `slippage = execution_cost - model_cost`. Positive is a cost for buys and sells alike.

**Worked example.** Buy 1,000 at a decision price of 50.00; fills 600 at 50.05 and 300 at 50.12; final price 50.60; half-spread 0.02, impact 0.00001. Average price 50.0733; execution cost 66.00; opportunity cost 60.00; shortfall 126.00; model cost 26.10; slippage 39.90.

A slippage persistently above zero says the wave 4a cost weights are too optimistic. No library computes this, so the suite is exact rational arithmetic with no outside check (0 of 12).

## Instrument selection and other asset classes

### Q10.28 Why can greedy forward selection miss the best hedge with at most K instruments?

*Level: advanced. Evidence: computed; spec; literature. Source: [Instrument selection](../../specifications/08-hedging/instrument-selection.md), [Tutorial 20](../getting-started/tutorial-20-cross-asset.md)*

Greedy selection takes the best single instrument, then its best partner. But the best pair need not contain the best single instrument [M02]. `hedge.select.solve` therefore defines the answer as the best over every subset of at most `K` instruments, each solved by `hedge.qp.solve`, with `n` at most 20.

**Worked example.** Three factors; instruments `c0 = (1, 1, 1)`, `c1 = (1, 0, 0)`, `c2 = (0, 1, 0)`; `b = (-1, -1, 0)`. With `K = 1` the best is instrument 0, objective 0.666667. With `K = 2` the best is `[1, 2]`, objective 0: a perfect hedge without instrument 0. Greedy would keep instrument 0 and could not reach zero.

"At most `K`" rather than "exactly `K`" (I-34), because adding an instrument never raises the least objective. Ties go to the smallest subset, then the lexicographically smallest indices. Above 100,000 candidate subsets the call is `E_LIMIT` (I-53).

### Q10.29 How does QuantForge define CS01 and jump to default in a CDS hedge?

*Level: practitioner. Evidence: computed; spec. Source: [Credit and correlation hedges](../../specifications/08-hedging/credit-and-correlation-hedges.md), [Tutorial 19](../getting-started/tutorial-19-credit-correlation.md)*

CS01 is the value change for about one basis point of spread. QuantForge bumps the hazard rates, not the spreads, by `eps = 1e-4 / (1 - R)`, which moves a flat curve's par spread by about 1 bp through the credit triangle `s ~ (1 - R) h`. Then `CS01 = (pv(h + eps) - pv(h - eps)) / 2`, every hazard shifted; `BUCKET_k` shifts one section only. Jump to default is `JTD = (1 - R) - pv`.

**Worked example.** With recovery `R = 0.4`, `eps` = 1.66667e-4, i.e. a hazard bump of 1.67 bp for a 1 bp spread move.

These are central differences fixed by the spec, not approximations of a derivative, so every build returns the same number. Risks are per unit notional of bought protection; `hedge.credit.cds` solves `G n = -book` on the chosen targets, with at most 50 hedges and the discount curve required to be `LOG_LINEAR_DF` (`E_INPUT` otherwise).

### Q10.30 Why can exchange options alone not hedge correlation separately from vega?

*Level: advanced. Evidence: spec; literature. Source: [Credit and correlation hedges](../../specifications/08-hedging/credit-and-correlation-hedges.md), [Tutorial 19](../getting-started/tutorial-19-credit-correlation.md)*

A Margrabe exchange option's price depends on `vol1`, `vol2` and `rho` only through the spread volatility `s = sqrt(vol1^2 + vol2^2 - 2 rho vol1 vol2)` [M78]. So every exchange option's `VEGA_1`, `VEGA_2` and `CORRELATION` rows are the same multiple of `dV/ds`, with common factors `(vol1 - rho vol2)/s`, `(vol2 - rho vol1)/s` and `-0.01 vol1 vol2/s` (ruling I-17).

In a hedge built only from exchange options, those rows are proportional, so the risk matrix is singular: case `hedgecorr_i` pins exchange options alone against `CORRELATION` and `VEGA_1` as `E_SINGULAR`. The hedge needs a single-asset vanilla, whose vega carries no correlation, to separate the two.

Units: `CORRELATION` is per 0.01 of correlation (the `correlation01` of `risk.sens.correlation`), vegas per unit volatility. A spread volatility of 0 with an exchange option present is `E_DOMAIN`.

### Q10.31 How does `hedge.crossasset.solve` hedge equity and rates risk together, and what risks does it use?

*Level: practitioner. Evidence: computed; spec. Source: [Cross-asset hedge](../../specifications/08-hedging/cross-asset-hedge.md), [Tutorial 20](../getting-started/tutorial-20-cross-asset.md)*

An equity forward is worth `S e^{-qT} - K P(T)`, so it carries equity and rates risk. Hedging them separately leaves each hedge's side effects behind; one weighted least-squares solve over both does not.

Risks per unit (I-21), defined as differences, not derivative approximations: `EQ01 = (V(1.01 S) - V(0.99 S)) / 2` per 1% equity move, and `KR01_k = (V(z_k + 1bp) - V(z_k - 1bp)) / 2`, moving pillar `k`'s zero rate only, with the curve linear in zero rates between pillars and flat before the first.

**Worked example.** Spot 100, `q` 1%, vol 20%, zero rates 3% at 2 and 5 years. Book: 5 long 2-year forwards struck at 100, and short 10 five-year ZCBs of notional 100. Book risk: EQ01 4.90099, KR01 at 2 years 0.0941765, at 5 years 0.430354. Hedges: the underlying and 2- and 5-year ZCBs (notional 100). Positions -4.90099, 5 and 10, residual 0.

A maturity beyond the last pillar is `E_INPUT` (I-20): nothing is defined after it.
