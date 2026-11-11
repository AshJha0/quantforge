# Stage I, C++ lane handover

From the C++26 session (branch `stage-i-lang-cpp`) to the spec lane and the coordinator. Append-only. Clean room: written from the specs, rulings and goldens only.

## Status at the end of session 1 (2026-11-11, 21:46)

Waves 1, 2, 3, 4a, 4b, 4c, 4d and 4e are built: 16 stage I operations, one commit per wave on `stage-i-lang-cpp` (not pushed).

- Conformance, full run on the final tree: 14,763 of 14,763, 0 failures, 0 not implemented. The 16 stage I suites: 271 of 271.
- ctest: 292 test cases, 12,574 assertions, all passed (260 before stage I; 32 stage I test cases with 5,031 assertions). WERROR (GCC 16.2, `-DQF_WERROR=ON`) clean throughout.
- Line coverage of the new code, gcov at `-O0`, unit tests plus the stage I conformance run: `hedging.cpp` 98.7% of 827 lines, `hedging_w2.cpp` 97.2% of 180, `hedging_w3.cpp` 97.7% of 86, `hedging_w4.cpp` 99.2% of 132, `ops_hedge.inc` 96.1% of 481.
- Test files define no namespace-scope static objects (fixtures are functions).

## Baseline (2026-11-11, before any change)

Main `e150116`, GCC 16.2, `-DQF_WERROR=ON`, 2 build jobs: build clean, ctest 260 test cases (7,529 assertions) passed, conformance 14,492 of 14,492.

## Wave 1, hedge solvers

Built: `hedge.qp.solve`, `hedge.integer.solve`, `hedge.minvar.ratio`, `hedge.greeks.neutralise`, `hedge.beta.futures`, `hedge.residual.report` (`cpp26/src/core/hedging.cpp`, `cpp26/src/cli/ops_hedge.inc`).

- Conformance: the six wave 1 suites 121 of 121; the full run 14,613 of 14,613, 0 failures.
- ctest: passed; 14 new test cases in `cpp26/tests/test_stage_i.cpp` (2,264 assertions), with the four property tests the spec names. WERROR clean. No namespace-scope static objects in the test file.
- Line coverage of the new code (gcov, unit tests plus the wave 1 conformance run): `hedging.cpp` 99.3% of 668 lines, `ops_hedge.inc` 90.8% of 174.
- `tests/test_cli.cpp` now expects 266 operations (the wave 1 name map).

## Wave 2, credit and correlation hedges

Built: `hedge.credit.cds`, `hedge.correlation.neutralise` (`cpp26/src/core/hedging_w2.cpp`). The CDS risks reuse the stage D `cds_price` legs on hazard curves rebuilt from the bumped piecewise-flat hazards (I-15).

- Conformance: `hedgecredit_i` 19 of 19, `hedgecorr_i` 20 of 20, on the first build. Full run on the wave 2 tree: 14,653 passed, 0 failures in the suites built so far (the 21 `hedgecost_i` failures and 52 not-implemented cases are waves 4a and 4b, not built at that point).
- ctest: 277 of 278 test cases passed; the one failure was the load-sensitive Q3b timing test (see Open), which passed when rerun. 4 new test cases (own contract hedges itself, targets zero after, bucket sum against the parallel CS01, zero risk past maturity, Margrabe delta against a price difference, the I-17 proportional rows, key sets). `tests/test_cli.cpp` expects 268 operations.

## Wave 3, cross-asset hedge

Built: `hedge.crossasset.solve` (`cpp26/src/core/hedging_w3.cpp`): the risk matrix by the I-21 half-differences on the I-20 curve, then the wave 1 `solve_qp`.

- Conformance: `hedgexa_i` 17 of 17 on the first build.
- ctest: 3 new test cases (square hedge leaves no residual, bonds have `EQ01 = 0` exactly, key-rate sharing between neighbours and before pillar 1, weight scaling, the check ladder). `tests/test_cli.cpp` expects 269 operations.

## Wave 4a, costs, impact, margin and the frontier

Built: the new optional inputs of `hedge.qp.solve` and `hedge.frontier.solve` (`cpp26/src/core/hedging.cpp`). Impact goes into `H` (I-26). With a spread or margin term the solve enumerates closed orthants: inside one, `|x_j|` is linear, so each is a strictly convex QP for the same dual active-set method, and the margin is one more linear row. The least orthant minimum is the answer; no feasible orthant is `E_INFEASIBLE`, decided exactly. Signs fixed by bounds are not enumerated.

- Conformance: `hedgecost_i` 22 of 22, `hedgefrontier_i` 10 of 10, `hedgeqp_i` still 44 of 44, on the first build. Full run: 14,701 passed, 0 failures (only the 25 wave 4b cases not implemented at that point). ctest passed.
- ctest: 4 new test cases (`cost_weight = 0` equals wave 1, no feasible perturbation does better, a costly instrument at exactly `+0.0`, an active margin equals its limit, spread against impact regularity, frontier monotonicity, the sign cap). `tests/test_cli.cpp` expects 270 operations.

## Wave 4b, dynamic delta-hedge backtest and effectiveness

Built: `hedge.backtest.delta`, `hedge.effectiveness` (`cpp26/src/core/hedging_w4.cpp`), the I-29 replay and one statistics routine for both. The hedge leg of each step is summed from its terms (`h dS`, interest, dividends), which equals `(Pi_{i+1} - Pi_i) - item_i` and is exactly 0 on a constant path without carry, so the I-31 test sees a zero variance there. The item sum for I-31 is compensated in extended precision.

- Conformance: `hedgebt_i` 15 of 15, `hedgeeff_i` 10 of 10. Full run: 14,726 of 14,726, 0 failures. ctest passed.
- ctest: 3 new test cases (perfect offset gives 1, -1, 1, 1; an exactly-zero sum that naive summation misses; the constant-path replay of the corrected property test; self-financing and the check ladder). `tests/test_cli.cpp` expects 272 operations.

## Wave 4c, instrument selection

Built: `hedge.select.solve` (`cpp26/src/core/hedging.cpp`): every subset of 1 to `K` instruments in size-then-lexicographic order, each through the wave 1 QP, and the first subset tied with the best wins (I-34). No greedy step.

- Conformance: `hedgeselect_i` 17 of 17 on the first build. Full run on the 4c and 4d tree: 14,756 passed, 0 failures outside wave 4e (`hedgebtcost_i`, not built at that point). ctest passed.
- ctest: 1 new test case (`K = n` equals the QP, the best objective never rises with `K`, the I-34 tie, the I-33 checks). `tests/test_cli.cpp` expects 273 operations at 4c.

## Wave 4d, slippage

Built: `hedge.slippage.report` (`cpp26/src/core/hedging_w4.cpp`), the I-36 arithmetic with the I-37 `null` average price.

- Conformance: `hedgeslip_i` 12 of 12 on the first build; full run as for 4c.
- ctest: 1 new test case (shortfall, slippage and totals identities, `null` price, sign of a sell's cost, the check ladder). `tests/test_cli.cpp` expects 274 operations.

## Wave 4e, costs in the backtest

Built: the optional `half_spread` and `impact` of `hedge.backtest.delta` (`cpp26/src/core/hedging_w4.cpp`, I-39, I-40). The opening purchase is a trade (`Pi_0 = -cost(h_0)`); each rebalance cost is paid after that date's `Pi` and enters the next step's hedge leg; no unwind; `trading_cost` only with a cost input.

- Conformance: `hedgebtcost_i` 8 of 8, `hedgebt_i` unchanged at 15 of 15.
- ctest: 1 new test case (zero costs equal the replay; without carry `final_pnl` falls by exactly `trading_cost`; the opening cost; the domain check).

## Example inputs (follow-up note to waves 1 to 4d)

`tests/test_stage_i.cpp` runs each of the 16 `examples/hedge_*_i.json` files (added by the spec lane at `fd3f084`) through the CLI and compares every output with its named golden case (1e-9 relative, 1e-9 absolute below 1): 16 of 16, 1,096 assertions. The test reads the files in place through `QF_REPO_DIR`, set by CMake.

## SPEC_QUESTIONS

| # | Where | Question | What the C++ build does |
|---|---|---|---|
| C-I1 | `hedge.minvar.ratio`, check 4; `hedgemv_i-0004` | A perfect hedge has a hedged variance at rounding level (golden `2.31e-18`). In binary64 the difference `S_00 - S_he' S_hh^-1 S_he` can come out a few 1e-18 below zero, which check 4 turns into `E_NOT_POSITIVE_DEFINITE`, so the case depends on the rounding of each build. Should check 4 carry a tolerance (for example `-1e-12 S_00`), as the residual report's eigenvalue check does? | Computes the Cholesky and the difference in `long double` (x87, 64-bit mantissa) and keeps the exact rule. Passes the golden; not bent to it |
| C-I2 | `hedge.integer.solve` | The spec does not say what happens when the search would need lot counts beyond `2^53` (huge `b` with small lot sizes). | `E_LIMIT` on `lot_sizes`. No golden reaches it |

## Open

- Wave 4a enumerates signs, `2^k` orthants for `k` instruments with a spread or margin term whose sign the bounds leave open. Above `k = 20` this build returns `E_LIMIT` (`max_sign_free_instruments`), while the spec allows 200 instruments. No golden reaches it. A sign-state active-set method (start from the smooth solution, flip a sign when a zero coordinate's subgradient test fails) would remove the cap.

- `Q3b AAD ladder ... costs at most 5 prices (G-9)` (stage G, `tests/test_stage_g.cpp:515`) is a wall-clock ratio. It failed once tonight at 5.09 against 5.0 while other lanes were compiling, and passed when rerun alone (2.80 earlier in the evening). Not touched by stage I.
- ASan and UBSan need WSL; not run tonight (no WSL by the coordinator's rule).
- `cpp26/tests/gen_cli_cases.py` fails on main: it reads `expected.error_code` for every non-ok case, and the stage F `e1_*` cases with `"status": "any"` have none (first: `e1_bond-0004`). `tests/cli_cases.inc` was not regenerated, so the in-process golden test has no stage I cases; conformance covers them.
