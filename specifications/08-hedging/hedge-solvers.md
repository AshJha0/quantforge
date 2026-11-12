# Hedge solvers: constrained least squares, integer contracts, minimum variance, Greek and beta hedges, residual risk

Spec version 1.0.0. Status: Specified (stage I, wave 1). Rulings: `stage-i-rulings.md` I-1 to I-14. Suites in `datasets/golden/stage_i/`: `hedgeqp_i`, `hedgeint_i`, `hedgemv_i`, `hedgegreeks_i`, `hedgebeta_i`, `hedgeres_i`, all written by `oracle/python/gen_stage_i_w1.py`.

**Plain idea.** A hedge is a set of positions `x` in instruments whose sensitivities `A` (one row per risk factor, one column per instrument) offset the book's existing risk `b`. The residual risk is `A x + b`. Most hedges in this page are one problem, weighted least squares on that residual, with limits on the positions; the rest (minimum variance, Greek neutralisation, beta futures) are closed forms of the same idea. Stage B's `hedge.solve` (`stage-b-hedges.md`) is unchanged; this page adds constraints, integer lots, rank-deficient problems and reporting.

Sources:
- [NW06] J. Nocedal, S. J. Wright, *Numerical Optimization*, 2nd ed., Springer, 2006, chapter 12 (KKT conditions, theorem 12.1) and chapter 16 (equality-constrained and active-set QP) (not opened in this session; the conditions are re-derived and checked numerically by the generator).
- [GV13] G. H. Golub, C. F. Van Loan, *Matrix Computations*, 4th ed., Johns Hopkins, 2013, section 5.5 (rank-deficient least squares, minimum-norm solution by the SVD) (not opened).
- [SP95] P. B. Stark, R. L. Parker, "Bounded-variable least-squares: an algorithm and applications", *Computational Statistics* 10, 1995, 129-141 (the BVLS method that scipy's `lsq_linear(method="bvls")` implements, used as an outside check) (not opened).
- [FP85] U. Fincke, M. Pohst, "Improved methods for calculating vectors of short length in a lattice", *Mathematics of Computation* 44(170), 1985, 463-471 (ellipsoid enumeration for integer least squares) (not opened).
- [H18] J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter 3 (minimum-variance hedge ratio `h* = rho sigma_S / sigma_F`; stock-index futures `N* = beta V_A / V_F`, worked example with 30 contracts) and chapter 19 (delta, gamma and vega neutrality) (not opened; the 30-contract example is reproduced by `hedgebeta_i-0001`).

## Common rules

- Check order for every operation: `E_PARSE`, `E_SCHEMA`, `E_LIMIT` (sizes in ruling I-4), the finite rule F-2 (`E_DOMAIN`), then the operation's own checks in the order listed below. F-3 (negative zero) holds.
- Matrices are lists of rows. `null` is legal only inside `lower`, `upper`, `lower_lots`, `upper_lots` (ruling I-12).
- Every rank or singularity decision uses one relative threshold, `1e-12` (ruling I-3), **applied after scaling** (ruling R6-6.2, amending I-3): a symmetric matrix `M` (`H`, a covariance) is tested as `D M D` with `D_jj = 1/sqrt(M_jj)` (a zero or negative diagonal entry is itself singular); an equality matrix `E` is tested with each row scaled to unit Euclidean norm and its columns scaled by the same `D` as `H`; the reduced Hessian is `Z^T (D H D) Z` with `Z` a basis of the null space of `E D`, compared with the largest eigenvalue of `D H D`. Scaling never changes the solution, only the decision, so a regular problem in mixed units (basis points against currency, weights from 1e-3 to 1e3) is no longer refused (`r6/hedgescale_r6`).
- Iteration caps and the kink tolerance (ruling R6-6.1): a position is at its kink when `|x_j| <= 1e-11 max(1, max_k |x_k|)`; any active-set or sign-state loop of `hedge.qp.solve` stops after `10 (n + p) + 100` iterations (`p` constraints), and `hedge.integer.solve` after 1,000,000 lattice points or nodes, with `E_NO_CONVERGENCE`. Builds may use any rank-revealing method (SVD, pivoted QR, symmetric eigenvalues, Cholesky pivots); the goldens keep every decision at least a factor 1e3 away from the threshold, so all of them agree.
- New error code `E_INFEASIBLE` (contract 1.11.0, ruling I-1): no point satisfies the constraints.

## `hedge.qp.solve` (HEDGE-05 constrained least squares; HEDGE-04 multi-instrument)

Minimise

`f(x) = sum_i w_i (A x + b)_i^2 + ridge * sum_j x_j^2`

subject to `E x = e` (optional equalities) and `lower_j <= x_j <= upper_j` (optional bounds).

### Inputs

- `a` (`m x n`, `m, n >= 1`), `b` (length `m`), `weights` (length `m`, each `> 0`).
- `ridge` (optional, default 0, `>= 0`).
- `eq_matrix` (`k x n`) and `eq_rhs` (length `k`): optional, both or neither.
- `lower`, `upper` (optional, length `n`, entries a Real or `null` for no bound).
- `singular` (optional, `ERROR` default, or `MIN_NORM`; ruling I-5).

### Checks, in order

1. Shapes: `a` non-empty with rows of one length `n >= 1`; `b`, `weights` of length `m`; `eq_matrix` and `eq_rhs` both present or both absent, rows of length `n`, `len(eq_rhs) = k`; `lower`, `upper` of length `n`: else `E_INPUT`.
2. `singular = MIN_NORM` with any non-null bound: `E_INPUT` (I-5).
3. A weight `<= 0`, `ridge < 0`, or `lower_j > upper_j` (both non-null): `E_DOMAIN`.
4. Equality rank: `k > n`, or the smallest singular value of `E` at most `1e-12` times its largest: `E_SINGULAR`.
5. Reduced Hessian. Let `H = A^T W A + ridge I` and `Z` an orthonormal basis of the null space of `E` (`Z = I` when `k = 0`). If an eigenvalue of `Z^T H Z` is at most `1e-12` times the largest eigenvalue of `H` (in absolute value), the problem has no unique minimiser: `E_SINGULAR` under `ERROR`; under `MIN_NORM` see below. When `k = n` there is no reduced Hessian and this check passes.
6. Feasibility: no `x` with `E x = e` inside the bounds: `E_INFEASIBLE` (I-14).

### Solution

With checks 4 and 5 passed, `f` is strictly convex on the feasible set, so the minimiser is unique and every exact method (active set, BVLS, an interior point run to convergence) gives the same `x`. KKT conditions at the minimum [NW06 12.1], with `g = 2 (H x + A^T W b)`: `g + E^T lambda - mu_L + mu_U = 0`, `mu_L, mu_U >= 0`, and each `mu` is zero unless its bound is active.

**`MIN_NORM`** (no bounds, by check 2): among all minimisers of `f` on `{E x = e}`, the one of least Euclidean norm. With `x_p = E^+ e` (the minimum-norm solution of the equalities, so `x_p` is orthogonal to `Z`), `x = x_p + Z y` with `y = -(Z^T H Z)^+ Z^T (H x_p + A^T W b)`, where the pseudo-inverse drops eigenvalues at or below the check-5 threshold [GV13 5.5]. Without equalities this is `-(A^T W A + ridge I)^+ A^T W b`, the minimum-norm weighted least-squares solution. On a regular problem `MIN_NORM` returns the unique minimiser (`hedgeqp_i-0021`).

### Outputs

- `x` (length `n`), `residual` (`A x + b`, length `m`), `objective` (`f(x)`).
- `rank` (Integer): the number of eigenvalues of `Z^T H Z` above the check-5 threshold; `n - k` on a regular problem, `0` when `k = n`.

## `hedge.integer.solve` (integer contracts)

Positions come in whole lots: `x_j = lot_sizes_j * n_j`, `n_j` an integer. Minimise the same `f(x)` (with `ridge`) over integer `n`, optionally within `lower_lots_j <= n_j <= upper_lots_j`. No equalities.

### Inputs

`a`, `b`, `weights`, `ridge` as above; `lot_sizes` (length `n`, each `> 0`); `lower_lots`, `upper_lots` (optional, length `n`, entries an Integer or `null`).

### Checks, in order

1. Shapes as `hedge.qp.solve` check 1; `lot_sizes`, `lower_lots`, `upper_lots` of length `n`: else `E_INPUT`.
2. A weight `<= 0`, `ridge < 0`, a lot size `<= 0`, or `lower_lots_j > upper_lots_j`: `E_DOMAIN`.
3. The continuous problem in lot units must be strictly convex: the smallest eigenvalue of `L H L` (with `L = diag(lot_sizes)` and `H` including `ridge`) at most `1e-12` times the largest: `E_SINGULAR`, even when every lot is bounded (I-6).

A box of integers is never empty after check 2, so this operation never returns `E_INFEASIBLE`.

### Solution and ties

The minimiser over the integers exists and lies in the ellipsoid `{n : f(n) <= f(n_0)}` for any feasible `n_0`; branch and bound or ellipsoid enumeration [FP85] finds it. Rounding the continuous solution is not enough (`hedgeint_i-0010`). Ties (ruling I-7): objectives within `1e-12` relative of the best are tied; among them, the smallest `sum |n_j|`, then the lexicographically smallest `n`. The goldens hold either exact ties in binary (the tie rule is pinned by `hedgeint_i-0007` to `-0009`) or a runner-up more than `1e-9` relative above the best.

### Outputs

- `lots` (list of Integer), `x` (`lot_sizes * lots`), `residual`, `objective`.
- `continuous_objective`: `f` at the `hedge.qp.solve` solution with the lot bounds as real bounds (in lot units). `rounding_cost = objective - continuous_objective` (`>= 0`).

## `hedge.minvar.ratio` (minimum-variance hedge)

Units of each hedge instrument that minimise the variance of the hedged position's value change.

### Inputs

Exactly one of:
- `covariance`: a `(k+1) x (k+1)` covariance of value changes, index 0 the position to hedge, 1 to `k` one unit of each hedge instrument.
- `exposure_changes` (length `T`) and `hedge_changes` (`k` series, each of length `T`): the sample covariance with divisor `T - 1` is used (I-8).

### Checks, in order

1. Both forms, neither, or one series without the other: `E_INPUT`. Covariance not square or smaller than `2 x 2`; `|S_ij - S_ji| > 1e-12 max|S|`; `k < 1`; series of unequal length; `T < k + 2`: `E_INPUT`.
2. `S_00 <= 0`: `E_DOMAIN`.
3. Hedge block `S_hh`: a Cholesky pivot at or below `1e-12` times the largest diagonal entry of `S_hh` (or negative): `E_SINGULAR`.
4. Hedged variance below zero (the full matrix is not positive semi-definite): `E_NOT_POSITIVE_DEFINITE`.

### Outputs

- `hedge = -S_hh^{-1} S_he` (units held; negative is short). For one instrument this is `-rho sigma_S / sigma_F`, the negative of Hull's `h*` [H18 ch. 3], because Hull quotes the size of a short hedge (I-8).
- `variance_before = S_00`, `variance_after = S_00 + S_he^T hedge`, `effectiveness = 1 - variance_after / variance_before` (the `R^2` of the regression of the position on the hedges).

## `hedge.greeks.neutralise` (delta, gamma and vega hedges)

Black-Scholes-Merton with flat `rate`, `dividend_yield` and `volatility`. Finds the quantities of the hedge instruments that set the listed Greeks of the book to zero.

### Inputs

- `spot`, `rate`, `dividend_yield`, `volatility`.
- `portfolio`: positions `{instrument, strike, expiry_years, quantity}`; `instrument` is `CALL`, `PUT` or `UNDERLYING` (the underlying has no `strike` or `expiry_years`).
- `hedges`: instruments of the same form without `quantity`, at most 3 (I-4).
- `targets`: distinct values from `DELTA`, `GAMMA`, `VEGA`, as many as `hedges` (I-9).

### Checks, in order

1. An `UNDERLYING` with `strike` or `expiry_years`, an option without both; no hedges; `len(targets) != len(hedges)`; a repeated target: `E_INPUT`.
2. `spot <= 0`, `volatility <= 0`, an option `strike <= 0` or `expiry_years <= 0`: `E_DOMAIN`.
3. The square matrix `G` (row per target, column per hedge, each entry a per-unit Greek) has smallest singular value at most `1e-12` times its largest: `E_SINGULAR`.

### Greeks (per unit)

`d1 = (ln(S/K) + (r - q + v^2/2) T) / (v sqrt T)`. Call delta `e^{-qT} N(d1)`, put delta `-e^{-qT} N(-d1)`; gamma `e^{-qT} n(d1) / (S v sqrt T)`; vega `S e^{-qT} n(d1) sqrt T`, per unit of volatility (not per 1%; I-9). The underlying has delta 1, gamma 0, vega 0.

### Outputs

- `quantities` (solve `G q = -g_book` on the targets).
- `greeks_before`, `greeks_after`: objects with `delta`, `gamma`, `vega` of the book before and after the hedge. Targeted entries of `greeks_after` are zero up to rounding; each case carries an absolute tolerance of `1e-10 * max(1, max |greeks_before|)`.

A least-squares Greek hedge (more instruments than targets, or weights) is `hedge.qp.solve` with `A = G` and `b = g_book`.

## `hedge.beta.futures` (equity beta hedge)

### Inputs

`portfolio_value` `V`, `portfolio_beta` `beta`, `target_beta` `beta*`, `futures_price` `F`, `multiplier` `m`; `rounding` (optional, `NEAREST` default, or `NONE`).

### Checks

`V <= 0`, `F <= 0` or `m <= 0`: `E_DOMAIN`.

### Outputs

- `contracts = (beta* - beta) V / (F m)` (positive is long) [H18 ch. 3].
- `contracts_held`: `contracts` rounded half away from zero under `NEAREST` (I-10); `contracts` under `NONE`. A Real.
- `beta_after = beta + contracts_held F m / V`.

## `hedge.residual.report` (residual risk)

### Inputs

`a` (`m x n`), `b` (`m`), `x` (`n`), `covariance` (`m x m`, of the factor moves).

### Checks, in order

1. Shapes; covariance not symmetric (`|S_ij - S_ji| > 1e-12 max|S|`): `E_INPUT`.
2. Covariance with an eigenvalue below `-1e-12` times its largest absolute eigenvalue: `E_NOT_POSITIVE_DEFINITE`.
3. `b^T S b <= 0` (nothing to hedge): `E_DOMAIN`.

### Outputs

`residual r = A x + b`; `variance_before = b^T S b`; `variance_after = r^T S r`; `volatility_after = sqrt(max(variance_after, 0))`; `effectiveness = 1 - variance_after / variance_before` (below 0 for an over-hedge); `contributions_i = r_i (S r)_i`, which sum to `variance_after` (Euler allocation, not divided by the variance; I-11).

## Validation cases and oracle

Generator `oracle/python/gen_stage_i_w1.py`. Every golden, including every error code, is the output of its reference functions; an error case is kept only if the reference stops at the rule the case was written for.

| Suite | Cases (value + error) | Oracle and self-checks | Outside (I-2) |
|---|---|---|---|
| `hedgeqp_i` | 27 + 17 | Active-set enumeration at 50 digits: each active set's KKT system is solved and kept only if primal-feasible with non-negative multipliers; exactly one KKT point must be found. KKT re-checked from the double outputs. Infeasible cases confirmed by HiGHS (`scipy.optimize.linprog`) | 25 of 44: scipy 1.18 `lsq_linear` BVLS (bounds), `linalg.lstsq` gelsd (unconstrained, `MIN_NORM`), `minimize` SLSQP (equalities); every output within `root_finding` |
| `hedgeint_i` | 12 + 6 | Exhaustive search in exact rational arithmetic over a box that contains every minimiser (ellipsoid bound from the rounded relaxed solution); tie margin asserted; second method: a float search over a box of 6 lots either side of the clipped relaxed solution, with the I-7 tie rule, returns the same lots | 0 of 18 |
| `hedgemv_i` | 9 + 8 | 50-digit Cholesky and solve; Hull's `rho sigma_S / sigma_F` asserted | 9 of 17: numpy 2.5 `linalg.solve` (covariance) and `linalg.lstsq` OLS with intercept (series) |
| `hedgegreeks_i` | 10 + 9 | 50-digit Greeks and solve | 10 of 19: QuantLib 1.44 `AnalyticEuropeanEngine` Greeks, then numpy `linalg.solve` |
| `hedgebeta_i` | 8 + 4 | 50-digit arithmetic; Hull's 30-contract example | 0 of 12 |
| `hedgeres_i` | 7 + 4 | 50-digit arithmetic; contributions sum to the variance | 0 of 11 |

Wave 1: 44 of 121 = 36.4% outside (error cases in the denominator). The 60% floor is measured over stage I at release (I-2); the later waves need a higher share, or the gap is reported as for G-42.

Mutants caught by the goldens (generator log): bounds ignored (the free solution clipped instead of re-solved), weights dropped, ridge ignored, naive rounding for integer lots, population divisor for the sample variances, the `e^{-qT}` factor dropped from delta, round half to even for beta futures.

## Convergence and limit cases

| Method | Asserted behaviour | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Active-set QP | Finite termination: the unique KKT point is found among at most `3^(bounded n)` active sets; the goldens hold one KKT point each | Every `hedgeqp_i` value case (the generator asserts a single KKT point) | `ridge -> 0` on a regular problem tends to weighted least squares; `lower = upper` fixes a variable (`hedgeqp_i-0013`) | scipy BVLS and SLSQP on the same problems |
| `MIN_NORM` | Equals the unique solution on a regular problem | `hedgeqp_i-0021` against `-0001` | Duplicate instruments split evenly (`-0018`); a zero column stays at 0 (`-0019`) | scipy `lstsq` (gelsd) |
| Integer search | Finite: the box from the ellipsoid bound holds every minimiser | Box sizes 1 to 756 points in `hedgeint_i` | One lot size of 1 with a large `b` tends to the rounded continuous solution | Exact rational enumeration |

## Limitations

- Costs, liquidity and margin constraints, instrument selection and the risk-against-cost frontier are later waves (plan section 4, row I); they extend `hedge.qp.solve` with new optional inputs rather than change it.
- `MIN_NORM` with bounds and integer lots with equalities are refused, not solved (I-5, I-6).
- Greek hedges use one flat Black-Scholes-Merton market; no smile, no sticky-strike or sticky-delta choice.

## Spec questions and rulings

| # | Question | Ruling |
|---|---|---|
| Q-I1 | Should `hedge.qp.solve` carry the stage B linear cost term `lambda sum c_j |x_j|`? | Not in wave 1. The cost wave adds `costs` and `cost_weight` as new optional inputs; with them absent the result is the one defined here (I-13) |
| Q-I2 | A bound active with a zero multiplier (degenerate) makes the active set ambiguous | `x` is still unique and is the only QP output; no active-set flag or multiplier is output. The goldens avoid degenerate points so an inexact method cannot land on the wrong face |
| Q-I3 | Threshold for `MIN_NORM` relative to `H` or to `Z^T H Z`? | The largest eigenvalue of `H`, so the decision does not depend on the chosen basis `Z` (I-3) |
| Q-I4 | Integer lots with equalities (for example a zero-cost budget)? | Refused by schema in wave 1 (no such input). An integer equality can make a box problem infeasible or need lattice reduction; it waits for an owner need |

## Amendments after the builds

Rulings I-41 (fixed key sets on `hedge.greeks.neutralise` instruments), I-42 (an unknown target is `E_SCHEMA`), I-44 (`hedge.minvar.ratio` check 4 has a tolerance of `1e-12 S_00`; a hedged variance inside it is returned as 0), I-45 (what the size limits count), I-46 (feasibility tolerance up to 1e-9, amending I-14), I-48 (no method-dependent `E_LIMIT`) and I-49 (`E_LIMIT` for lot counts above `2^52`) amend this page; `stage-i-rulings.md` is normative. Cases `hedgegreeks_i-0020`, `-0021`, `hedgemv_i-0018` and `hedgeint_i-0019` pin them.

## R6 amendments (rulings `r6-rulings.md` R6-6.1, R6-6.2, R6-11)

- Scaling before every singularity decision (R6-6.2); kink tolerance, iteration caps and `E_NO_CONVERGENCE` (R6-6.1).
- Feasibility tolerance is exactly `1e-9` relative (R6-11.3). An answer is accepted when its KKT residual is at most `1e-10 max(1, max|g|)` after the exact re-solve on its state (R6-11.4).
- Integer and selection ties: within `1e-12 max(best, f(0))` (R6-11.5).
- `hedge.select.solve`: `max_instruments` outside `1..n` is `E_INPUT`, before the subset-count `E_LIMIT` (R6-11.6).
- `hedge.minvar.ratio`: a negative pivot is `E_NOT_POSITIVE_DEFINITE`; a pivot at or below `1e-12` of the scaled form is `E_SINGULAR`; the lower triangle is used (R6-11.7).
- `hedge.beta.futures`: `((target_beta - beta) * V) / (F * m)` in that order, then round half away from zero; `V <= 0` stays `E_DOMAIN` by design (R6-11.12).
- `eq_matrix: []` is `E_INPUT`; dependent but consistent equality rows are `E_SINGULAR` (R6-11.13, item 14).
- `hedge.residual.report`: `b^T S b <= 0` is an exact sign test, by design (item 15).
- An unknown `instrument` string is `E_SCHEMA` (R6-11.18).
