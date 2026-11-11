# Stage I, Python lane

Branch `stage-i-lang-python`. Append-only, one section per wave.

## Wave 1 (hedge solvers)

Built in `python/quantforge_core/hedge_solvers.py`, verbs in `cli/ops_hedging.py`, sizes (I-4) in
`cli/limits.py`. Conformance 121 of 121 (`hedgeqp_i`, `hedgeint_i`, `hedgemv_i`, `hedgegreeks_i`,
`hedgebeta_i`, `hedgeres_i`), no failures. Tests in `python/tests/test_hedge_solvers.py`, including
the four property tests the handover names.

SPEC_QUESTIONS: none blocking. Three readings of silent points (I-4 sizes for the covariance
inputs, a `quantity` on a hedge instrument, the phase-1 tolerance for `E_INFEASIBLE`) are recorded
as I-Q1 to I-Q3 in `python/SPEC_QUESTIONS.md`; a ruling either way changes no golden.

## Wave 2 (credit and correlation hedges)

Built in `python/quantforge_core/credit_correlation_hedges.py` on the stage D legs in `credit.py`
(bumped hazard curves keep every unshifted pillar's log-survival bit for bit, so a section past a
contract's maturity has zero bucket risk exactly). Conformance 39 of 39 (`hedgecredit_i`,
`hedgecorr_i`); stage I total 160 of 160. Tests in `python/tests/test_credit_correlation_hedges.py`
(own-contract notional, targets zero after, buckets against the parallel CS01, a hand-built CS01,
Margrabe Greeks against finite differences, correlation signs). SPEC_QUESTIONS: none.

## Waves 3 and 4a (cross-asset hedge; costs, margin and frontier)

Wave 3 in `python/quantforge_core/cross_asset_hedge.py` (risks by repricing, then the wave 1
solve). Wave 4a extends `hedge_solvers.qp_solve`: with no new input the wave 1 path runs unchanged
(`hedgeqp_i` still 44 of 44); with a spread cost or a margin, an orthant search solves a smooth QP
per sign orthant (linear cost term, the margin as one inequality) and flips an instrument sitting
at 0 only when the subgradient test fails, so a costly instrument comes out at exactly `0.0`. The
feasible start with a margin is the least-margin point from a two-phase simplex. Conformance:
`hedgexa_i` 17 of 17, `hedgecost_i` 22 of 22, `hedgefrontier_i` 10 of 10; stage I total 209 of 209.
Tests in `python/tests/test_hedge_costs_cross_asset.py`, including SciPy SLSQP on the split form
as a second check. One commit for both waves: they were released together and share the handler
and limits files. SPEC_QUESTIONS: none.

## Waves 4b and 4c (backtest and effectiveness; instrument selection)

Wave 4b in `python/quantforge_core/dynamic_hedge.py` (the I-29 replay order; one statistics routine
for both operations). Wave 4c is `hedge_solvers.select_solve`, every subset of 1 to K instruments
through the wave 1 solve, I-34 tie rule. Conformance: `hedgebt_i` 15 of 15, `hedgeeff_i` 10 of 10,
`hedgeselect_i` 17 of 17; stage I total 251 of 251. Tests in
`python/tests/test_dynamic_hedge_selection.py`. SPEC_QUESTIONS: I-Q4 in `python/SPEC_QUESTIONS.md`
(a constant-spot backtest is `E_DOMAIN` only if rounding happens to cancel exactly; asks for a
threshold or for the property note to go). Selection is exhaustive with no pruning: at the I-35
size of 20 instruments with K = 20 that is about a million small solves, correct but slow.

## Wave 4d (hedge slippage)

`python/quantforge_core/slippage.py`, plain arithmetic in correctly rounded sums; `average_price`
is `null` with no fills (I-37); I-38 sizes in `cli/limits.py`. Conformance `hedgeslip_i` 12 of 12;
stage I total 263 of 263. Tests in `python/tests/test_slippage.py`. SPEC_QUESTIONS: none.

## Wave 4e (costs in the backtest) and the follow-up note on tutorial inputs

`dynamic_hedge.backtest_delta` takes `half_spread` and `impact` (I-39); `trading_cost` only with a
cost input (I-40). Conformance `hedgebtcost_i` 8 of 8 with `hedgebt_i` unchanged; stage I total
271 of 271. Follow-up note: `python/tests/test_examples_stage_i.py` runs all sixteen
`examples/hedge_*_i.json` through `quantforge batch` and checks status ok, inputs equal to the
named golden case, and the golden outputs. Every stage I operation answers through `run` and
`batch`. Python API names: the functions carry the name-map names (`qp_solve`,
`greeks_neutralise`, `credit_cds`, ...) inside `quantforge_core` modules, as every earlier stage
does; there is no `quantforge.hedge` package path. Open item for the tutorial owner: whether the
Python step imports `quantforge_core.hedge_solvers` etc., or a `quantforge.hedge` facade is wanted.
