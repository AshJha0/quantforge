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
