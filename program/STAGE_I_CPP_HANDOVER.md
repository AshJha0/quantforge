# Stage I, C++ lane handover

From the C++26 session (branch `stage-i-lang-cpp`) to the spec lane and the coordinator. Append-only. Clean room: written from the specs, rulings and goldens only.

## Baseline (2026-11-11, before any change)

Main `e150116`, GCC 16.2, `-DQF_WERROR=ON`, 2 build jobs: build clean, ctest 260 test cases (7,529 assertions) passed, conformance 14,492 of 14,492.

## Wave 1, hedge solvers

Built: `hedge.qp.solve`, `hedge.integer.solve`, `hedge.minvar.ratio`, `hedge.greeks.neutralise`, `hedge.beta.futures`, `hedge.residual.report` (`cpp26/src/core/hedging.cpp`, `cpp26/src/cli/ops_hedge.inc`).

- Conformance: the six wave 1 suites 121 of 121; the full run 14,613 of 14,613, 0 failures.
- ctest: passed; 14 new test cases in `cpp26/tests/test_stage_i.cpp` (2,264 assertions), with the four property tests the spec names. WERROR clean. No namespace-scope static objects in the test file.
- Line coverage of the new code (gcov, unit tests plus the wave 1 conformance run): `hedging.cpp` 99.3% of 668 lines, `ops_hedge.inc` 90.8% of 174.
- `tests/test_cli.cpp` now expects 266 operations (the wave 1 name map).

## SPEC_QUESTIONS

| # | Where | Question | What the C++ build does |
|---|---|---|---|
| C-I1 | `hedge.minvar.ratio`, check 4; `hedgemv_i-0004` | A perfect hedge has a hedged variance at rounding level (golden `2.31e-18`). In binary64 the difference `S_00 - S_he' S_hh^-1 S_he` can come out a few 1e-18 below zero, which check 4 turns into `E_NOT_POSITIVE_DEFINITE`, so the case depends on the rounding of each build. Should check 4 carry a tolerance (for example `-1e-12 S_00`), as the residual report's eigenvalue check does? | Computes the Cholesky and the difference in `long double` (x87, 64-bit mantissa) and keeps the exact rule. Passes the golden; not bent to it |
| C-I2 | `hedge.integer.solve` | The spec does not say what happens when the search would need lot counts beyond `2^53` (huge `b` with small lot sizes). | `E_LIMIT` on `lot_sizes`. No golden reaches it |

## Open

- ASan and UBSan need WSL; not run tonight (no WSL by the coordinator's rule).
- `cpp26/tests/gen_cli_cases.py` fails on main: it reads `expected.error_code` for every non-ok case, and the stage F `e1_*` cases with `"status": "any"` have none (first: `e1_bond-0004`). `tests/cli_cases.inc` was not regenerated, so the in-process golden test has no stage I cases; conformance covers them.
