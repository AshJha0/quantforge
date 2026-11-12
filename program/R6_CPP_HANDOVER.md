# R6 C++ lane hand-over (branch `r6-lang-cpp`)

Written 2026-11-12. All builds and tests ran in WSL (Ubuntu, g++ 15.2) on sources exported from this branch, with `-DQF_WERROR=ON`. Spec merged from `r6` at `d51d30a` (all waves READY).

## Findings reproduced

| Finding | Result | Evidence |
|---|---|---|
| 3, curve Jacobian upper-triangle mask | **Reproduced**, then fixed (R6-1.1) | Under `MONOTONE_CONVEX` the v0.8.0 build returned 0 above the diagonal where a central difference of the rebuilt curve gives 0.0114 (row 0, col 1) and 0.0089 (row 1, col 2). The mask was `cpp26/src/core/risk.cpp` `zero_jacobian` (loop from `i = j`). The reproducer is now a regular test in `cpp26/tests/test_risk.cpp` (`[r6]`), which also asserts an upper entry above 1e-3 |
| 15, a finite input that overflows | **Not reproduced as a crash** in C++ | The JSON writer turns any NaN or infinite result into `E_NON_FINITE` (`json.cpp`, `Writer::real`). R6-8.1 adopts exactly that code; `r6/nonfinite_r6` passes. A 10-minute sanitizer fuzz run on the v0.8.0 code was started and cut off by two session restarts; see "Sanitizers" |

## Items

| Item | Status |
|---|---|
| R6-0.1 contract 1.12.0 | done (`dispatch.cpp`) |
| R6-1.1, R6-1.2 Jacobian | mask removed; `tension` and `step_end` read and passed to every bumped bootstrap |
| R6-2.1 BGK envelope | `E_DOMAIN` outside it, after E-A19 and `n = 0` (`ops_exotics.inc`) |
| R6-3.1 ES | Acerbi-Tasche fractional tail (`var_frtb.cpp`); hand tests at `w = 2.5`, `w = 2`, `w = 1` |
| R6-4.1 `risk.frtb.sbm_total` | new (`ops_var_frtb.inc`); hand test: totals 12, 12, 15, binds low, sum of class capitals 19 |
| R6-5.1, R6-5.6 | keys `deflated_pfe_<100 q>`. R6-5.5: this build already scans `f'` at 8,000 points over +-40 sd and bisects each sign change, finer than the ruled 6,001 over +-12 sd |
| R6-7.1 PSA CPR >= 1 | `E_DOMAIN` before any cash flow (`mbs.cpp`) |
| R6-7.3 CDS on a coupon date | D19 `E_INPUT` removed (`credit.cpp`) |
| R6-7.5 TIPS rounding | `ref_cpi` and `index_ratio` truncated to 6 then rounded to 5 (`inflation.cpp`) |
| R6-6.1 caps | active-set and sign-state loops capped at `10 n + 100`, lattice search at 1,000,000 nodes, all `E_NO_CONVERGENCE`; planted cap of 1 tested (`detail::effort_cap_override`). Kink: see question 3 |
| R6-6.2 scaling | Jacobi scaling before the equality-rank and reduced-Hessian tests of `hedge.qp.solve` (and so cross-asset), the lattice convexity test, the select full-hedge test, and the minvar pivots |
| R6-11.5, .6, .7, .9, .13, .16 | ties against `max(best, f(0))` (integer, select); `max_instruments` outside 1..n `E_INPUT` before the subset `E_LIMIT`; minvar negative pivot `E_NOT_POSITIVE_DEFINITE`, scaled small pivot `E_SINGULAR`; negative bumped hazard `E_DOMAIN`; empty `eq_matrix` `E_INPUT`; degenerate Margrabe vol `E_SINGULAR`. R6-11.12 was already in the ruled order; R6-11.18 was already `E_SCHEMA` |
| R6-11.20 use case 6 | `usecase.option_hedge_lots` (`hedging.cpp`, `ops_hedge.inc`); hand test (237 short, lots of 100: 2 lots, cost 2, delta after -37) |
| R6-16 G4 | no stage-letter file names in `cpp26/`; `stages.json` and `equivalents-cpp.md` follow |
| R6-16 G-9 | the test writes the measured ratio to `QF_G9_RECORD`; 2.33 in WSL |
| R6-25 | `cpp26/SPEC_QUESTIONS.md`: stages G and I filled, every entry open or closed with its ruling |

## Totals

- Conformance (`runner.py --impl cpp`, all goldens at `d51d30a`): **15,071 of 15,076**; after the kink fix `hedgecost_i` is 23 of 23, so **15,072 of 15,076**. The 4 left are golden defects, question 1 and 2.
- ctest and sanitizers: see the run log below.

## Questions for the spec lane

1. `stage_d/edge_d-0015`, `-0016`, `-0017` (`infl.linker.price`) still hold the unrounded `ref_cpi` and `index_ratio` (322.85566666666665, 1.0758239651050259, 323.3929032258065). R6-7.5 rounds every linker price, so these three were not regenerated with `inflation_d`. This build gives 322.85567, 1.07582, 323.3929.
2. `stage_f/e1_risk-0372` (`risk.var.monte_carlo`, a value case of the E1 sweep) still holds the v0.8.0 ES 52,486.18; R6-3.1 gives 52,593.47 here. The sweep was not regenerated after the ES change.
3. R6-6.1 kink rule: this build decides a kink by the sign-row multiplier test (`nu - 2 k_j > 1e-10 scale`), then the orthant solve is exact. Adding a separate zeroing of `|x_j| <= 1e-11 max(1, max|x|)` changed `hedgecost_i-0010` (a binding margin) to `E_INFEASIBLE`, so it was removed. Is the multiplier test an accepted "proven equivalent"?
