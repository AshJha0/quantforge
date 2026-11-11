# Stage I handover

From the stage I spec and oracle session to the four language sessions and the lanes. Append-only. Each wave section says what a language session may read. Never read anything under `oracle/`: that is the oracle, and reading it breaks the clean room.

Stage I (v0.8): hedging (plan section 4, row I; TRACEABILITY Domain 08) plus plan item Q6 (plan 12.4). All stage I goldens are in `datasets/golden/stage_i/`, run through `conformance/runner/runner.py` (it finds them by suite name). Always read `specifications/cli-contract.md` (block "Stage I operations", and the new `E_INFEASIBLE` row of the error-code table) and `specifications/stage-i-rulings.md` with any stage I slice. The stage F rules (F-1 to F-3 finite and negative-zero inputs, F-5 names, F-6 spec template) apply to every new operation.

## Wave plan

| Wave | Content | Main outside oracle |
|---|---|---|
| 1 | Hedge solvers: constrained least squares (QP, singular handling), integer contracts, minimum variance, delta/gamma/vega and equity-beta hedges, multi-instrument hedge, residual risk | scipy 1.18 optimisers, numpy 2.5, QuantLib 1.44 Greeks |
| 2 | Credit and correlation hedges | to be named in the wave section |
| 3 | Cross-asset hedge (equity/rates) | to be named in the wave section |
| 4+ | Liquidity and margin constraints, costs and impact, instrument selection, risk-against-cost frontier, dynamic hedge backtest and hedge effectiveness | to be named |

## WAVE 1 READY (2026-11-11): hedge solvers

Read with every slice: `specifications/08-hedging/hedge-solvers.md`; `specifications/stage-i-rulings.md` I-1 to I-14; `specifications/cli-contract.md` (block "Stage I operations", error code `E_INFEASIBLE`, contract 1.11.0); `specifications/edge-case-register.md` rows I1 to I5; `specifications/name-map.json` (regenerated: 266 operations).

### Suites (121 cases)

| Suite | Operation | Cases |
|---|---|---|
| `hedgeqp_i` | `hedge.qp.solve` | 44 (27 value, 17 error) |
| `hedgeint_i` | `hedge.integer.solve` | 18 (12, 6) |
| `hedgemv_i` | `hedge.minvar.ratio` | 17 (9, 8) |
| `hedgegreeks_i` | `hedge.greeks.neutralise` | 19 (10, 9) |
| `hedgebeta_i` | `hedge.beta.futures` | 12 (8, 4) |
| `hedgeres_i` | `hedge.residual.report` | 11 (7, 4) |

### Build notes
- One QP serves the multi-instrument, key-rate and least-squares Greek hedges. Any exact method works because the goldens are strictly convex after the checks; a primal active-set method on `x'Hx + 2c'x` is the shortest path. Form `H = A^T W A + ridge I` once.
- Check order matters: shapes (`E_INPUT`), then `MIN_NORM` with a bound (`E_INPUT`), then `E_DOMAIN`, then equality rank and reduced Hessian (`E_SINGULAR`), then feasibility (`E_INFEASIBLE`, I-14). `hedgeqp_i-0044` has a zero weight and a singular `A`: `E_DOMAIN` wins.
- Singularity (I-3): compare with `1e-12` times the largest singular value or eigenvalue of the stated matrix. The goldens keep every decision a factor 1e3 or more from the threshold, so SVD, pivoted QR or eigenvalues all agree. For the reduced Hessian, compare with the largest eigenvalue of `H`, not of `Z^T H Z`.
- `MIN_NORM`: `x = E^+ e + Z y`, `y = -(Z^T H Z)^+ Z^T (H E^+ e + A^T W b)`. Without equalities it is the pseudo-inverse solution. `rank` counts eigenvalues of `Z^T H Z` above the threshold.
- Infeasibility: with full-rank equalities and bounds, a phase-1 LP or an active-set method that finds no feasible point. Without bounds nothing is infeasible.
- Integer lots: branch and bound on the strictly convex objective, or enumerate the ellipsoid box around the unconstrained minimiser. The tie rule (I-7) is pinned by `hedgeint_i-0007` to `-0009`; `-0010` defeats rounding of the relaxed solution. `continuous_objective` is the bounded QP in lot units.
- Minimum variance: `hedge` is units held, so a positively correlated hedge is short (I-8). Series use divisor `T - 1`.
- Greeks: vega per unit volatility (QuantLib's `vega()`), `e^{-qT}` in delta. The underlying has no `strike` or `expiry_years` keys. Targeted `greeks_after` entries carry an absolute tolerance in each case's `tolerance_limit`.
- Beta futures: round half away from zero (`-2.5 -> -3`, I-10). `contracts_held` is a Real.
- `null` is legal only inside `lower`, `upper`, `lower_lots`, `upper_lots` (I-12).

### Property tests (each language, own data)
- QP: KKT residual at the answer below `1e-8` of the gradient scale; bounds and equalities hold; `MIN_NORM` equals the unique solution when `rank = n - k`.
- Integer: `objective >= continuous_objective`; no neighbour (one lot up or down in one coordinate) has a lower objective.
- Minimum variance: `effectiveness` equals the `R^2` of the OLS regression with intercept on the series form.
- Residual report: `sum(contributions) = variance_after`.

### Outside-oracle status (rule 11.2.5, ruling I-2)
44 of 121 = 36.4% (`oracle/outside_register_i.json`): `hedgeqp_i` 25 of 44 (scipy BVLS, gelsd, SLSQP), `hedgemv_i` 9 of 17 (numpy), `hedgegreeks_i` 10 of 19 (QuantLib `AnalyticEuropeanEngine` plus numpy solve). Not counted: every error case, integer lots (no free library solves integer least squares), beta futures and the residual report (arithmetic only), the fixed-variable and `MIN_NORM`-with-equality QP cases. The 60% floor is measured over stage I at release (I-2); waves 2 and 3 must add QuantLib-checked suites, or the gap is reported.

### Model inventory
Row MI-1 (hedge solvers) added to `docs/model-inventory.md` with golden hashes.

## Q6 status (2026-11-11): terms checked, churn bound registered, no data, no fit

The Cboe delayed-quote pages prohibit automated download, and the Cboe website terms (section 2) and the Deribit terms of service (clause 32.3) forbid publishing derived data without written consent. Q6 waits for an owner decision on the data source (details and links in the plan folder, `STAGE_I_DATA_TERMS.md`). The churn bound is registered before any download or fit: `research/preregs/Q6-01-churn-bound.md`, hash-checked by `research/test_preregs.py`. Language sessions have nothing to build for Q6.

## WAVE 2 READY (2026-11-11): credit and correlation hedges

Read: `specifications/08-hedging/credit-and-correlation-hedges.md`; rulings I-15 to I-19 (and I-1 to I-4, I-12); `specifications/04-pricing/credit.md` (the CDS legs, normative here); `specifications/06-risk/f3-sensitivities.md` (`risk.sens.correlation`, same Margrabe formula); cli-contract block "Stage I operations"; edge-case rows I6, I7; `specifications/name-map.json` (268 operations).

### Suites (39 cases)

| Suite | Operation | Cases |
|---|---|---|
| `hedgecredit_i` | `hedge.credit.cds` | 19 (10 value, 9 error) |
| `hedgecorr_i` | `hedge.correlation.neutralise` | 20 (9, 11) |

### Build notes
- Credit: reuse your `credit.cds.price` legs. Derive hazards from the survival pillars (`h_k = ln(Q_{k-1}/Q_k)/(t_k - t_{k-1})`, `t` in ACT/365F from the trade date); bump them by `+-1e-4/(1-R)` and rebuild the survival curve from the bumped hazards; CS01 is half the difference of the two pvs (I-15), never a derivative. `JTD = (1 - R) - pv` per unit of bought protection, with pv including `accrued Pcs` (I-16).
- The discount check (`LOG_LINEAR_DF`, R1-4) comes before every other rule check, as in all `credit.*` operations.
- A bucket beyond a contract's maturity has zero risk exactly; a matrix of such rows is `E_SINGULAR` (I-3).
- Correlation: an exchange option's vega and correlation rows are proportional (I-17), so a hedge of correlation and a vega needs a vanilla (`CALL_k`, `PUT_k`). Correlation sensitivity is per 0.01 (I-18).
- Every instrument kind has a fixed key set; any other key, or a missing one, is `E_INPUT`.

### Property tests
- Credit: hedging a book with its own contract returns the book's notional with the opposite sign; `after` is zero on every target; the sum of bucket CS01s is close to the parallel CS01 (equal to first order, not exactly).
- Correlation: `correlation01` of a long exchange option is negative; a vanilla has zero correlation risk.

### Outside-oracle status
`hedgecredit_i` 10 of 19 (QuantLib `IsdaCdsEngine` on bumped hazard curves), `hedgecorr_i` 9 of 20 (QuantLib Margrabe engine and `BlackCalculator.vega`). Every value case counts; no error case does. Stage I so far: 63 of 160 = 39.4% (`oracle/outside_register_i.json`). The floor (60%, I-2) is measured at release. Error cases are 61 of the 160, so the value suites still to come must count nearly all their cases, or the stage reports a gap as G-42 did.

## WAVE 3 READY (2026-11-11): cross-asset hedge, equity and rates

Read: `specifications/08-hedging/cross-asset-hedge.md`; rulings I-20 to I-23 (and I-1 to I-5); `specifications/08-hedging/hedge-solvers.md` (the solve it reuses); cli-contract block "Stage I operations"; edge-case rows I8, I9; `specifications/name-map.json` (269 operations).

### Suite (17 cases)

`hedgexa_i`, operation `hedge.crossasset.solve`: 9 value cases, 8 error cases.

### Build notes
- Build the risk matrix by repricing, not by Greeks. `EQ01` is half of `V(1.01 S) - V(0.99 S)`, and `KR01_k` is half of `V(z_k + 1bp) - V(z_k - 1bp)` with the curve rebuilt (I-21). Then call your wave 1 `hedge.qp.solve` with the given weights and ridge.
- Curve: linear in zero rate between pillars, flat before the first, refused after the last (I-20). A maturity between pillars shares its key-rate risk between the two neighbours; before pillar 1 it all goes to pillar 1.
- `ZCB` has a `notional` (I-22). Every instrument kind has a fixed key set (`E_INPUT` otherwise).
- `residual_risk` and `objective` come from the risks and positions, as in `hedge.qp.solve`.

### Property tests
- A square, regular hedge leaves `residual_risk` at 0. A book of bonds alone has `EQ01 = 0` exactly.
- Scaling every weight by the same factor leaves `positions` unchanged when `ridge = 0`.

### Outside-oracle status
`hedgexa_i` 9 of 17 (QuantLib `ZeroCurve` and `AnalyticEuropeanEngine`, the same half-differences, numpy `lstsq`). Every value case counts; no error case does. Stage I so far: 72 of 177 = 40.7% (`oracle/outside_register_i.json`).

## WAVE 4a READY (2026-11-11): costs, impact, liquidity and margin; risk-against-cost frontier

Read: `specifications/08-hedging/hedge-costs-and-frontier.md`; rulings I-24 to I-28 (and I-13); cli-contract block "Stage I operations"; edge-case row I10; `specifications/name-map.json` (270 operations).

### Suites (32 cases)

| Suite | Operation | Cases |
|---|---|---|
| `hedgecost_i` | `hedge.qp.solve` with the new optional inputs | 22 (13 value, 9 error) |
| `hedgefrontier_i` | `hedge.frontier.solve` | 10 (4, 6) |

### Build notes
- Extend your wave 1 `hedge.qp.solve`. Without the new inputs nothing changes, and your `hedgeqp_i` results must stay the same: the generator checked that the extended reference reproduces every `hedgeqp_i` golden exactly.
- The `|x|` terms are non-smooth. Either enumerate sign states (positive, negative, zero, at a bound) with the subgradient test at zero, or solve the split QP `x = p - n`, `p, n >= 0`, where spread and margin are linear. Make sure an instrument whose cost exceeds its benefit comes out at exactly `0.0` (`hedgecost_i-0002`). Most iterative solvers return about 1e-12 there unless they snap to the kink.
- Impact enters the Hessian (`cost_weight diag(impact)`) and can make a singular problem regular; a spread cost cannot (I-26).
- Outputs `risk`, `cost` and `margin` appear only when a new input is given (I-27).
- Frontier: run the solve once per weight, in order; the first error stops it.

### Property tests
- `cost_weight = 0` gives the wave 1 answer; the frontier's risk is non-decreasing and its cost non-increasing.
- With a margin constraint active, `margin` equals `margin_limit`.

### Outside-oracle status
`hedgecost_i` 12 of 22, `hedgefrontier_i` 2 of 10 (scipy BVLS or lstsq where exact, else trust-constr or SLSQP on the split form; I-28). Stage I so far: 86 of 209 = 41.1% (`oracle/outside_register_i.json`).

## WAVE 4b READY (2026-11-11): dynamic delta-hedge backtest and hedge effectiveness

Read: `specifications/08-hedging/dynamic-hedge-and-effectiveness.md`; rulings I-29 to I-32; cli-contract block "Stage I operations"; edge-case rows I11, I12; `specifications/name-map.json` (272 operations).

### Suites (25 cases)

| Suite | Operation | Cases |
|---|---|---|
| `hedgebt_i` | `hedge.backtest.delta` | 15 (7 value, 8 error) |
| `hedgeeff_i` | `hedge.effectiveness` | 10 (5, 5) |

### Build notes
- Follow the replay order of I-29 exactly: interest on cash, then dividends on the shares held at the step's start, then the mark, then the rebalance (none on the last date). Another order changes `final_pnl` by about `q dt` per step, far above the tolerance.
- The value at `tau = 0` is the payoff; a path may stop before expiry, and then the last mark is a model value.
- Reuse one statistics routine for both operations; `quantity = 0` reaches `E_DOMAIN` through it (I-31).
- Paths are inputs with up to 64 dates; tolerance `1e-9` absolute and relative (case limit).

### Property tests
- A perfect offset gives dollar offset 1, slope -1, R² 1, variance reduction 1.
- On a path with constant spot and zero rates and dividends, the hedge leg is zero and `final_pnl` equals the option's time decay times the quantity.

### Outside-oracle status
`hedgebt_i` 7 of 15 (QuantLib `AnalyticEuropeanEngine` on each date), `hedgeeff_i` 5 of 10 (numpy). Every value case counts. Stage I so far: 98 of 234 = 41.9% (`oracle/outside_register_i.json`).

**Correction to the wave 4b property tests (2026-11-11):** on a constant-spot path the hedge leg has zero variance, so `hedge.backtest.delta` returns `E_DOMAIN` (I-31). Test the replay itself instead: on such a path, with zero rates and dividends, `portfolio_values` end at `quantity (V_last - V_0)`.

## WAVE 4c READY (2026-11-11): instrument selection

Read: `specifications/08-hedging/instrument-selection.md`; rulings I-33 to I-35; cli-contract block "Stage I operations"; edge-case row I13; `specifications/name-map.json` (273 operations).

### Suite (17 cases)

`hedgeselect_i`, operation `hedge.select.solve`: 10 value cases, 7 error cases.

### Build notes
- Enumerate subsets of size 1 to `K` and solve each with your `hedge.qp.solve` on those columns. Keep the best by the I-34 tie rule: within 1e-12 relative, the smaller subset wins, then the lexicographically smaller index list. Indices are 0-based.
- Do not select greedily: `hedgeselect_i-0009` defeats forward selection by 0.5.
- `selected` is compared exactly; `x` has zeros for instruments left out.

### Property test
- `K = n` gives the `hedge.qp.solve` answer, and the best objective never rises as `K` grows.

### Outside-oracle status
`hedgeselect_i` 10 of 17 (scipy per subset); every value case counts. Stage I so far: 108 of 251 = 43.0% (`oracle/outside_register_i.json`).
