# R6 C++ lane hand-over (branch `r6-lang-cpp`)

Written 2026-11-12. Builds and tests ran in WSL (Ubuntu, g++ 15.2) from a `git archive` export, `-DQF_WERROR=ON`.

## Findings reproduced

| Finding | Result | Evidence |
|---|---|---|
| 3, curve Jacobian upper-triangle mask | **Reproduced** | Hidden test `[r6-repro]` in `cpp26/tests/test_risk.cpp`: under `MONOTONE_CONVEX`, `risk.curve.jacobian` reports 0 above the diagonal where a central difference of the rebuilt curve gives 0.0114 (row 0, col 1), 0.0089 (row 1, col 2), 1.06e-4 (row 0, col 2) per unit. The mask is in `cpp26/src/core/risk.cpp` (`zero_jacobian`, loop `for i = j`). `book_sensitivity.cpp` (IFT route) has no mask but its own test asserts exact zeros only for `LOG_LINEAR_DF`. Not fixed yet: waits for the spec ruling (remove the mask or reject non-local methods). |
| 15, non-finite results from a finite input that overflows | See "Fuzz" below | C++ already turns any NaN or infinite output into `E_NON_FINITE` at the JSON writer (`json.cpp`, `Writer::real`), so an overflowing result is an error, never a crash or an `inf` on the wire. |

## Items

- R6-8: no code change. The contract (`cli-contract.md` line 144 and 167) and six goldens (`rulings-*` in `core/rulings.json`, `rulings_b-0041` to `-0045` `calib.fit`) require `E_NON_FINITE` for an output that overflows; the plan says `E_DOMAIN`. Needs a ruling (question 1).
- R6-16 G4: no stage-letter names left in `cpp26/` (`risk_f3/f4` -> `book_sensitivity`, `var_frtb`; `hedging_w2/w3/w4` -> `hedging_credit_correlation`, `hedging_cross_asset`, `hedging_dynamic`; `ops_risk_gb`, `ops_frtb_gb` -> `ops_sensitivity_portfolio`, `ops_frtb_sbm`; tests `test_f_*`, `test_mut_kill_*`, `test_stage_g/i` -> domain names). Operation names unchanged. `conformance/mutation/equivalents-cpp.md` updated.
- R6-16 G-9: the C++ test already asserts ratio <= 5 (not judged under sanitizers). It now writes `{"gate":"G-9","language":"cpp","ratio":...}` to the path in `QF_G9_RECORD`. Measured in WSL: 2.33. The evidence lane should set `QF_G9_RECORD` in the Actions job and upload the file.

## Totals

- Conformance: 14,935 of 14,935 (release build, WSL).
- ctest unit tests: 303 cases, 16,118 assertions, all pass (the hidden reproducer excluded).
- Sanitizers and fuzz: see below.

## Questions for the spec lane

1. R6-8: is an overflowing output `E_DOMAIN` (plan 14.1) or `E_NON_FINITE` (contract, 6 goldens)? C++ follows whichever is ruled; changing it is one line.
2. Finding 3: remove the mask (exact central differences everywhere) or reject non-local interpolations in `risk.curve.jacobian`? Also `risk.ois.book_sensitivity` zero-Jacobian under non-local methods.
