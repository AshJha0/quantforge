# Stage I Java handover

From the Java 25 session to the spec lane. Append-only. Written from the specifications alone.

## Wave 1: hedge solvers

Built in `java25/` (`hedging.LeastSquaresHedge`, `hedging.HedgeRatios`, `cli.OpsHedgeI`): all six wave 1 suites pass,
121 of 121 cases. Property tests named by the spec are in `HedgeSolversPropertyTest`.

## SPEC_QUESTIONS

| # | Point | Java choice, open for a ruling |
|---|---|---|
| J-I1 | Ruling I-4 names "instruments 200" and "factors 1,000" but not which keys of `hedge.minvar.ratio` and `hedge.residual.report` they bound. No golden tests them | `hedge.minvar.ratio`: at most 200 hedge instruments (`covariance` up to 201 x 201, `hedge_changes` up to 200 series). `hedge.residual.report`: rows of `a` and of `covariance` up to 1,000, columns of `a` up to 200 |
| J-I2 | I-14 says feasibility "is decided exactly (no tolerance)". A double build cannot decide it exactly when a bound is met with equality, for example `k = n` with `x_p` on a bound | With `k = n`, `x_p` counts as inside a bound within `1e-10 max(1, |x_p_j|)`. Otherwise the dual active-set method reports `E_INFEASIBLE` when a violated bound has no primal step (step part outside the active span below `1e-10` of the whole) and no active bound can be dropped. The goldens keep feasible cases clear of the boundary, so all of them pass; a ruling could state a tolerance for builds |
| J-I3 | I-12 makes `null` legal only inside the four bound arrays. An optional scalar or array key given as `null` (for example `"ridge": null`) | `E_SCHEMA`, as for any other `null`. No golden case; proposed for the next E1 pass |

## Wave 2: credit and correlation hedges

Built (`hedging.CreditHedge`, `hedging.CorrelationHedge`, `cli.OpsHedgeCreditCorr`; `pricing.Credit.Hazard.shifted`
for the I-15 hazard bumps): `hedgecredit_i` 19 of 19, `hedgecorr_i` 20 of 20. No spec question.

## Wave 3: cross-asset hedge

Built (`hedging.CrossAssetHedge`, `cli.OpsHedgeCrossAsset`, solving through the wave 1 `LeastSquaresHedge`):
`hedgexa_i` 17 of 17. No spec question.

## Wave 4a: costs, impact, margin and the frontier

Built (`LeastSquaresHedge.Costs`, the sign-orthant search in `LeastSquaresHedge`, `hedge.frontier.solve` in
`cli.OpsHedgeI`): `hedgecost_i` 22 of 22, `hedgefrontier_i` 10 of 10, `hedgeqp_i` still 44 of 44.

| # | Point | Java choice, open for a ruling |
|---|---|---|
| J-I4 | The spec allows any exact method for the `|x|` terms but names no size limit for them. Java solves one strictly convex QP per closed sign orthant of the instruments that carry a spread (with `cost_weight > 0`) or a margin rate, so the work doubles per such instrument | Above 20 such instruments `hedge.qp.solve` returns `E_LIMIT` (key `half_spreads`). No golden comes near it. A ruling could set a limit for every build, or a build could switch to a split-variable method that needs no limit |
