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

## Wave 4b: dynamic delta-hedge backtest and effectiveness

Built (`hedging.DynamicHedge`, `cli.OpsHedgeDynamic`): `hedgebt_i` 15 of 15, `hedgeeff_i` 10 of 10.

| # | Point | Java choice, open for a ruling |
|---|---|---|
| J-I5 | The handover correction (e6605a2) says a constant-spot path with zero rates and dividends gives `E_DOMAIN`, because the hedge leg has zero variance. That holds in exact arithmetic only: in doubles each `hedge_i = (Pi_{i+1} - Pi_i) - item_i` carries rounding noise of about 1e-14, so the series is not constant and the statistics are returned (of noise). No golden has such a path | Java applies I-31 exactly as written: zero variance means every value is equal. A ruling could give the zero-variance test a relative tolerance (for example `var(y) <= 1e-24 var(x)`), or state that the rule holds only for inputs given exactly, as in `hedge.effectiveness` |

## Wave 4c: instrument selection

Built (`hedging.InstrumentSelection`, `cli.OpsHedgeSelect`; exhaustive over subsets in size then index order, each
solved by `LeastSquaresHedge`): `hedgeselect_i` 17 of 17. No spec question.

## Wave 4d: hedge slippage

Built (`hedging.Slippage`, `cli.OpsHedgeSlippage`): `hedgeslip_i` 12 of 12. No spec question.

## Wave 4e: costs in the backtest; tutorial examples

Built (`DynamicHedge.backtest` with `half_spread` and `impact`, I-39, I-40): `hedgebtcost_i` 8 of 8, `hedgebt_i` still
15 of 15. `HedgeExamplesSmokeTest` runs the 16 `examples/hedge_*_i.json` inputs through the CLI request handler
and judges each against its golden case; the same 16 return `status: ok` through `java -jar quantforge-cli.jar run`.
No spec question.

## Rulings I-41 to I-52 applied (2026-11-11)

| Ruling | Java |
|---|---|
| I-41 | Changed: `hedge.greeks.neutralise` refuses keys outside an instrument's set, a `quantity` on a hedge and a missing `quantity` on a position (`E_INPUT`); `hedgegreeks_i-0020` passes |
| I-42 | Checked: an unknown Greek or correlation target is `E_SCHEMA`; `hedgegreeks_i-0021` passes |
| I-43 | Changed: relative zero tests in `hedge.effectiveness` and the backtest; `hedgebt_i-0016` passes. Closes J-I5 |
| I-44 | Changed (the Java build also refused any negative hedged variance): `E_NOT_POSITIVE_DEFINITE` only below `-1e-12 S_00`, else 0; `hedgemv_i-0018` passes |
| I-45, I-46, I-47 | No change: Java already reads the limits, feasibility tolerance and `null` this way. Closes J-I1 to J-I3 |
| I-48 | Open, see below |
| I-49 | Added: `E_LIMIT` (key `lot_sizes`) when a relaxed lot count exceeds `2^52` |
| I-50 | Checked: one order's `fills` above 100,000 is `E_LIMIT` (unit test) |
| I-51 | Not applied in this lane: `conformance/runner/runner.py` still requires `contract_version` 1.0.0, so a lone move to 1.11.0 stops every conformance run. The change is one constant (`cli.Main.CONTRACT`), to land with the runner in the integration PR, as I-51 says |

### I-48, open in the Java lane

`hedge.qp.solve` still solves one strictly convex QP per closed sign orthant of the instruments with an `|x|` term
and returns `E_LIMIT` above 20 of them (`LeastSquaresHedge.MAX_COSTLY`), which I-48 forbids below 200 instruments.
Planned replacement, not started tonight so as not to ship a half-finished solver: a sign-state active-set method that
starts from the orthant of the cost-free solution and flips one instrument's sign when it sits at 0 and its orthant
bound's multiplier shows the subgradient condition `|g_j| <= cost_weight half_spreads_j + mu margin_rates_j` broken.
Each flip strictly lowers the convex objective, so the search ends. Test it against the current enumeration on random
problems of up to 12 such instruments, then drop `MAX_COSTLY`. No golden reaches 20, so every golden passes either way.

### I-48 done (2026-11-11, extended session)

`hedge.qp.solve` no longer enumerates the `2^k` sign orthants. `LeastSquaresHedge.costSearch` is a sign-state
active-set method: it solves one strictly convex orthant QP, flips every instrument at 0 whose orthant-bound
multiplier breaks the subgradient condition `|g_j| <= cost_weight half_spreads_j + mu margin_rates_j`, and accepts a
step only when the objective falls (else it retries with the single worst flip). With a margin limit, a phase 1
(smooth part plus a dominant margin cost) finds a feasible starting orthant, or returns `E_INFEASIBLE`. The size cap
and its `E_LIMIT` are gone. The enumeration stays only as a test oracle (`solveByEnumeration`). `SignSearchTest`
checks the KKT conditions at 21, 50 and 200 instruments (tolerance `1e-8` of the gradient scale) and agreement with
the oracle on 150 random problems with up to 12 such instruments; all 276 stage I goldens pass.
