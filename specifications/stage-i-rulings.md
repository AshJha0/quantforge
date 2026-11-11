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

## Wave 2, credit and correlation hedges

| # | Point | Ruling |
|---|---|---|
| I-15 | CS01 definition | A central difference of the piecewise-flat hazard rates with `eps = 1e-4 / (1 - R)` (about one basis point of spread by the credit triangle), with all sections shifted (`CS01`) or one (`BUCKET_k`). It is a definition, not an approximation, so builds agree to rounding. Sections are those of the `hazard` input; the last also covers the time after the last pillar. Quote bumps with a re-bootstrap are not used (spec question Q-I5) |
| I-16 | Jump to default in the hedge | `JTD = (1 - R) - pv` per unit of bought protection, with `pv` the `credit.cds.price` value including `accrued Pcs`. This is `risk.credit.jtd` with the computed value in place of the clean market value input |
| I-17 | One spread-volatility factor | Margrabe Greeks in `vol1`, `vol2` and `rho` are all proportional to `dV/ds` with factors common to every exchange option. A correlation hedge needs single-asset vanillas, so `CALL_k` and `PUT_k` are hedge instruments. Exchange options alone against two of `VEGA_1`, `VEGA_2`, `CORRELATION` are `E_SINGULAR` |
| I-18 | Correlation sensitivity units | `CORRELATION` and `correlation01` are per 0.01 of correlation, as `risk.sens.correlation`; vegas are per unit volatility, as I-9 |
| I-19 | `E_LIMIT` sizes, wave 2 | Credit: book 1,000 trades, 50 hedges. Correlation: book 1,000 positions, 5 hedges (the number of Greeks) |

## Wave 3, cross-asset hedge (equity and rates)

| # | Point | Ruling |
|---|---|---|
| I-20 | Curve for the cross-asset hedge | Continuously compounded zero rates on ACT/365F pillar times, linear in time between pillars, flat before the first pillar, and no extrapolation after the last: a maturity there is `E_INPUT` (spec question Q-I9) |
| I-21 | Equity and key-rate risk factors | `EQ01` is half the value change between spot times 1.01 and spot times 0.99. `KR01_k` is half the change between pillar `k`'s zero rate plus and minus 1bp, other pillars fixed. Both are definitions, not derivative approximations |
| I-22 | Units of hedge instruments | The wave 1 singularity test (I-3) is relative to the largest eigenvalue, so it is not invariant to instrument units. A unit zero-coupon bond's 1bp risk (about 5e-4) next to a forward's 1% equity risk (about 40) made a regular problem look singular (ratio 6e-12, found while generating `hedgexa_i`). `ZCB` therefore takes a `notional`, and hedge instruments are expected to carry comparable risk per unit. I-3 is not changed (Q-I10) |
| I-23 | `E_LIMIT` sizes, wave 3 | Book 1,000 positions, hedges 200, curve pillars 100 |

## Wave 4a, costs, impact, liquidity and margin; frontier

| # | Point | Ruling |
|---|---|---|
| I-24 | Traded size | Costs and margin apply to `x`, the new hedge, which starts from no position. Rebalancing from existing positions is a later input (Q-I11) |
| I-25 | Order of the new checks in `hedge.qp.solve` | After wave 1 checks 1 to 3: lengths and the `margin_rates`/`margin_limit` pair (`E_INPUT`), `MIN_NORM` with any new input (`E_INPUT`), negative values (`E_DOMAIN`); then wave 1 checks 4 to 6, with the margin constraint part of feasibility |
| I-26 | Regularity with costs | The singularity test (I-3) uses `A^T W A + ridge I + cost_weight diag(impact)`. Impact counts like a ridge; a spread cost does not, because `|x|` has no curvature away from 0 |
| I-27 | Outputs with costs | `risk`, `cost` and (with margin inputs) `margin` are output only when a new input is present, so every wave 1 result keeps its exact output set; `objective = risk + cost_weight cost` |
| I-28 | Several outside solvers | An outside check may try several library solvers on the same problem and count the case if one agrees with every compared output within the case tolerance; `verified_by` names it. Goldens never depend on which solver agreed |

## Wave 4b, dynamic hedge backtest and effectiveness

| # | Point | Ruling |
|---|---|---|
| I-29 | Backtest cash account | Self-financing from zero wealth. Each step credits interest `cash (e^{r dt} - 1)` and dividends `h_i S_i (e^{q dt} - 1)` on the shares held at the step's start, then rebalances, except on the last date. Options are marked and hedged at `hedge_volatility`; at expiry the mark is the payoff |
| I-30 | Dollar offset | Cumulative: `-sum(hedge changes) / sum(item changes)`. No period-by-period ratio |
| I-31 | Effectiveness domain | `sum(item changes) = 0`, or a series with zero sample variance, is `E_DOMAIN`; a backtest with `quantity = 0` therefore fails there. Sample (co)variances use `n - 1` |
| I-32 | `E_LIMIT` sizes, wave 4b | Path and series length 100,000 |

## Wave 4c, instrument selection

| # | Point | Ruling |
|---|---|---|
| I-33 | Selection inputs | `hedge.select.solve` takes the `hedge.qp.solve` inputs without equalities or a singular policy (`E_INPUT` if present), and every bound must admit 0 (`E_DOMAIN`). The full problem must be regular (I-3) |
| I-34 | Selection rule | The least objective over all subsets of at most `K` instruments. Ties within `1e-12` relative go to the smaller subset, then to the lexicographically smaller index list. Indices are 0-based |
| I-35 | `E_LIMIT` size, wave 4c | 20 instruments |

## Wave 4d, hedge slippage

| # | Point | Ruling |
|---|---|---|
| I-36 | Slippage definition | `execution_cost = sum q (p - d)` against the decision price; `opportunity_cost = (Q - q_f)(final_price - d)`; `model_cost` is the wave 4a model on the filled size; `slippage = execution_cost - model_cost` |
| I-37 | `null` average price | `average_price` is `null` for an order with no fills; this extends I-12's list of places where `null` is legal |
| I-38 | `E_LIMIT` sizes, wave 4d | 10,000 orders; 1,000,000 fills in total |

## Wave 4e, costs in the backtest

| # | Point | Ruling |
|---|---|---|
| I-39 | Backtest costs | Optional `half_spread` and `impact` charge `half_spread |dq| + impact dq^2` on every share trade: the initial `h_0` at `t_0` (so `Pi_0 = -cost(h_0)`), and each rebalance after that date's `Pi` is recorded. No unwind at the end. Without the inputs the wave 4b result is unchanged (I-13 pattern) |
| I-40 | `trading_cost` output | The undiscounted sum of the costs paid, present only when a cost input is given |

## After the builds: the lanes' spec questions (2026-11-11)

Questions read from the lanes' notes only: Java J-I1 to J-I5, Python I-Q1 to I-Q4, C++ C-I1, C-I2 and its open note, Rust 1 to 5. Where builds read a silent point differently, one behaviour is chosen and pinned by a computed golden appended to the suite. No existing golden case changed: the five new cases come after the old ones, and a rerun leaves every earlier case byte-identical.

| # | Question | Ruling |
|---|---|---|
| I-41 | Rust 2, Python I-Q2: extra keys on `hedge.greeks.neutralise` instruments (a `quantity` on a hedge was ignored by Rust and Python) | Fixed key sets, as waves 2 and 3: a portfolio position has `instrument`, `quantity` and, for an option, `strike` and `expiry_years`; a hedge instrument has the same without `quantity`. Any other or missing key is `E_INPUT`. Pinned by `hedgegreeks_i-0020` |
| I-42 | Rust 1: unknown target names in `hedge.greeks.neutralise` and `hedge.correlation.neutralise` | `E_SCHEMA`: an enumeration value that is not listed, as the contract's error table says. `hedge.credit.cds` keeps `E_INPUT` for a target outside its list, because `BUCKET_k` depends on the data (the number of pillars). Pinned by `hedgegreeks_i-0021` |
| I-43 | Python I-Q4, Java J-I5: the zero-variance test of I-31 does not fire on a constant-spot backtest, whose hedge leg is zero only up to rounding | Relative tests replace the exact ones in `hedge.effectiveness` and `hedge.backtest.delta`. `E_DOMAIN` when `|sum(x)| <= 1e-12 sum|x|`, or `var(x) <= 1e-20 var(y)`, or `var(y) <= 1e-20 var(x)`. In binary64 the noise is about 1e-14 relative per step, a variance ratio near 1e-28, so 1e-20 leaves a margin of 1e8 on both sides; no real hedge comes near it. Pinned by `hedgebt_i-0016` (constant spot, zero rates and dividends). Every earlier golden is unchanged |
| I-44 | C++ C-I1: `hedge.minvar.ratio` check 4 on a perfect hedge depends on each build's rounding | `E_NOT_POSITIVE_DEFINITE` only when the hedged variance is below `-1e-12 S_00`. A value between that and 0 is rounding and is returned as 0 (effectiveness then 1). Pinned by `hedgemv_i-0018`, whose exact hedged variance is `-4.0e-16 S_00` |
| I-45 | Java J-I1, Python I-Q1, Rust 3: what the I-4 and I-35 limits count | Instruments are the columns of `a`. Factors are the rows of `a` and the order of `covariance` in `hedge.residual.report` (1,000). `hedge.minvar.ratio` allows 200 hedge instruments: a covariance up to 201 x 201, or up to 200 `hedge_changes` series. A `lot_sizes` list longer than the columns is `E_INPUT`, not `E_LIMIT` (Python read it as a limit). Pinned by `hedgeint_i-0019` |
| I-46 | Java J-I2, Python I-Q3: I-14's "decided exactly" cannot hold in binary64 | Amends I-14: a build may decide feasibility with a relative tolerance up to 1e-9 (phase-1 artificial sum, or a bound met within `1e-9 max(1, |x_j|)`). In the goldens, every infeasible case misses by at least 0.05 in absolute terms, and every feasible case is feasible exactly (a fixed variable sits on its bound) or with slack, so a tolerance up to 1e-9 never changes a golden's decision |
| I-47 | Java J-I3: `null` for an optional scalar or array key (for example `"ridge": null`) | `E_SCHEMA`, as any `null` outside the places a spec names (I-12, I-37). No golden yet; proposed for the next E1 pass |
| I-48 | Java J-I4, C++ open note: Java and C++ return `E_LIMIT` above 20 instruments with a sign-open cost or margin term (one QP per sign orthant); Rust and Python do not | The I-4 limit (200 instruments) is the only size limit of `hedge.qp.solve`. A method-dependent `E_LIMIT` below it is not allowed. Java and C++ replace the orthant enumeration with a split-variable or sign-state active-set method before release. No golden reaches 20 such instruments, so no golden is added tonight |
| I-49 | C++ C-I2: integer lot counts beyond `2^53` | `E_LIMIT` (key `lot_sizes`) when any lot count of the relaxed continuous solution exceeds `2^52` in absolute value: integers beyond it are not all representable, so the search is not defined in binary64. No golden yet |
| I-50 | Rust 4: one order's `fills` against the general array limit | The general limit of 100,000 entries per array (`01-core/limits.md`) still applies to each order's `fills`; I-38's 1,000,000 is a further cap on the total. One order with 200,000 fills is `E_LIMIT` |
| I-51 | Rust 5: contract version | All four CLIs report `contract_version` 1.11.0 from the stage I release; the runner's contract check (`StubTests::test_contract_mismatch_stops` covers the mechanism) stops a mismatch. The lanes move together in the integration PR |
| I-52 | Coordinator: Python import path for the tutorials | As tutorial 1: a tutorial's Python step imports the `quantforge_core` modules directly (for example `from quantforge_core import hedge_solvers`). No `quantforge.hedge` facade is added. The `python` column of `name-map.json` is a logical name, as for every earlier stage, not an import path. This amends the wave 1 to 4d follow-up note's item 2 |

## Wave 5, outside-checked value cases (2026-11-11)

| # | Point | Ruling |
|---|---|---|
| I-55 | How wave 5 adds outside-checked cases | New suites `hedgegreeks5_i`, `hedgecorr5_i`, `hedgemv5_i`, `hedgeeff5_i`, `hedgeqp5_i` of existing operations, written by `oracle/python/gen_stage_i_w5.py` from seeded draws (one seed per suite, in the generator). A draw is rejected only for reasons fixed before any outside check: a domain rule, an I-3 decision inside the factor-1e3 margin, or an infeasible QP (3 draws in all). It is never rejected because the outside check disagrees: every accepted draw is a golden, and the register counts it only if the library agrees within the case tolerance (I-2 unchanged). Earlier suites are untouched |

## Sources

- [GV13] G. H. Golub, C. F. Van Loan, *Matrix Computations*, 4th ed., 2013, section 5.5 (not opened).
- Further sources per spec page.
