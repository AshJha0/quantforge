# Stage I rulings

Normative for stage I (v0.8): hedging (plan section 4, row I; TRACEABILITY Domain 08) and plan item Q6 (plan 12.4). Earlier rulings still hold, among them `stage-f-rulings.md` F-1 to F-3 (non-finite tokens, the finite rule, negative zero), F-5 (names) and F-6 (spec template), and `stage-g-rulings.md` G-50 (error-case schema self-check). Append-only; an amendment is a new row that names the row it amends. A rule fixed before a result is seen is never changed after it; a new rule is registered instead.

## Wave 1, hedge solvers

| # | Point | Ruling |
|---|---|---|
| I-1 | Operations and contract | Wave 1 adds `hedge.qp.solve`, `hedge.integer.solve`, `hedge.minvar.ratio`, `hedge.greeks.neutralise`, `hedge.beta.futures`, `hedge.residual.report` (`08-hedging/hedge-solvers.md`) and one error code, `E_INFEASIBLE` (no point satisfies the constraints). Adding a code is a minor version: target contract 1.11.0. Stage B `hedge.solve` and `hedge.spread_cost` are unchanged |
| I-2 | Outside-oracle floor for stage I | 60% over the stage I suites at release, rule 11.2.5, error cases **in** the denominator (as G-4). A case counts only if every compared output agrees, within the case's own tolerance, with a value returned by an outside library solving the same problem: an optimiser or linear solver (scipy 1.18, numpy 2.5) on the same objective and constraints, or a library model object (QuantLib 1.44), or plain arithmetic on such values. Arithmetic with no library value in it does not count. Each generator writes `oracle/outside_register_i.json` |
| I-3 | One singularity threshold | Every rank or singularity decision compares a singular value, eigenvalue or Cholesky pivot with `1e-12` times the largest one of the stated matrix. The generator asserts that each decision in the goldens is at least a factor 1e3 from the threshold, so builds may use any rank-revealing method |
| I-4 | `E_LIMIT` sizes, wave 1 | Factors (rows of `a`) 1,000; instruments 200; equality rows 200; integer instruments 12; series length 100,000; portfolio positions 1,000; Greek hedge instruments 3 (the number of Greeks). Checked after `E_SCHEMA`, before F-2 |
| I-5 | Singular least squares | `singular = ERROR` (default) returns `E_SINGULAR` when the reduced Hessian is singular, as stage B did. `MIN_NORM` returns the minimum Euclidean-norm minimiser [GV13 5.5]. `MIN_NORM` with any bound is `E_INPUT`: the least-norm point of a bounded minimiser set needs a second QP, and no wave 1 hedge needs it. `ridge > 0` is the third way out and makes every problem regular |
| I-6 | Integer lots need a strictly convex problem | `hedge.integer.solve` returns `E_SINGULAR` when the continuous problem in lot units is singular, even if every lot is bounded. With duplicate instruments the integer minimisers form a set whose choice would rest on the tie rule alone; refusing keeps the answer independent of the search method |
| I-7 | Integer ties | Objectives within `1e-12` relative of the best are tied; then the smallest `sum |n_j|` wins; then the lexicographically smallest `n`. Goldens hold exact binary ties or a runner-up more than `1e-9` relative above the best (asserted) |
| I-8 | Minimum-variance conventions | `hedge` is units held (negative is short), so the one-instrument value is `-rho sigma_S / sigma_F`, the negative of Hull's `h*` (a short-hedge size). Sample covariances use divisor `T - 1`, and at least `k + 2` observations (one degree of freedom after the mean and `k` slopes). Symmetry is checked at `1e-12` of the largest absolute entry; a negative hedged variance is `E_NOT_POSITIVE_DEFINITE` |
| I-9 | Greek hedges | Exact neutralisation only: as many hedge instruments as targets. Vega is per unit of volatility, as QuantLib's `vega()`, not per 1%. A least-squares Greek hedge is `hedge.qp.solve` with the Greek matrix as `a` |
| I-10 | Beta futures rounding | `NEAREST` rounds half away from zero (`-2.5 -> -3`, `hedgebeta_i-0006`), the rule used for lots elsewhere in this page; `contracts_held` is a Real so `NONE` and `NEAREST` share one output type |
| I-11 | Residual contributions | `contributions_i = r_i (S r)_i`, not divided by `variance_after`: an exact hedge leaves a variance of rounding size, and a ratio would be noise |
| I-12 | `null` bounds | `null` is legal inside `lower`, `upper`, `lower_lots`, `upper_lots` and means no bound on that instrument. Elsewhere `null` stays `E_SCHEMA` |
| I-13 | Costs in the QP | Not in wave 1 (spec question Q-I1). The cost wave adds new optional inputs; with them absent, `hedge.qp.solve` keeps the meaning fixed here |
| I-14 | Order of `E_SINGULAR` and `E_INFEASIBLE` | The equality-rank and reduced-Hessian checks come before feasibility, so a problem that is both singular and infeasible returns `E_SINGULAR`. Feasibility is decided exactly (no tolerance): the generator confirms each `E_INFEASIBLE` golden by HiGHS and keeps feasible cases clear of the boundary |

## Sources

- [GV13] G. H. Golub, C. F. Van Loan, *Matrix Computations*, 4th ed., 2013, section 5.5 (not opened).
- Further sources per spec page.
