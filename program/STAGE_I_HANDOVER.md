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
