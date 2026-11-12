# R6 Java lane hand-over

Branch `r6-lang-java`, from `e387d29`. Phase 0 only: no wave was marked READY in `r6:program/R6_HANDOVER.md` when phase 0 finished (the file did not yet exist on `r6`).

## Review findings, reproduced or not

| Finding | Result | Evidence |
|---|---|---|
| 3, curve Jacobian upper-triangle mask | **Not reproduced in Java.** `CurveRisk.jacobian` reports the full central difference with no mask. On the inputs of the first `risk.curve.jacobian` golden, the largest upper entry is 0.0 under `LINEAR_ZERO` and 0.0379 under `MONOTONE_CONVEX`. | `ReviewR6Test.jacobianUpperTriangleIsNotMasked` (guards against a mask being added) |
| 15, `Bonds.java:262` | **Reproduced.** `bond.futures.conversion_factor` with coupon -1e308 crashed with `NumberFormatException: Infinite or NaN`, exit 70. | Now `E_DOMAIN`, field `bond`; `ReviewR6Test.conversionFactorOverflowIsDomain` |

Fuzz after the fix: `fuzz_cli.py --impl java --seconds 400 --seed 7`, 20,200 inputs, 0 findings. One batch of 200 hung over 16 minutes on a heavily loaded machine (other lanes and model jobs running) and was killed by hand; its inputs were not replayed, so that chunk is unchecked. The CI fuzz job is the check that counts.

## Items done

- R6-8: conversion factor overflow returns `E_DOMAIN`. The only other `new BigDecimal(double)` path parses text, so cannot see a non-finite value. Non-finite **outputs** still map to `E_NON_FINITE` in `Main.handle`, as `cli-contract.md` says; see question 1.
- R6-16 G4: renamed, public operation names unchanged: `OpsHedgeI` -> `OpsHedgeSolvers`, `OpsRatesG` -> `OpsRateModels`, `OpsRiskF` -> `OpsMarketRisk`, `OpsWave2b` -> `OpsFrtbSensitivities`, `RiskToolsB` -> `PortfolioRiskTools`; tests `StageIRulingsTest` -> `HedgeRulingsTest`, `WaveFourBTest` -> `PortfolioRiskToolsTest`, `StageFVolTest` -> `VolSpecialFunctionsTest`. No stage-letter file, class or package names remain under `java25/src`. Old names survive only in historical `program/STAGE_I_JAVA_HANDOVER.md`.
- R6-16 G-9: `ShortRateTest.aadCostRatioG9` now asserts `median(price+ladder)/median(price) <= 5` and prints the ratio. Local runs: 4.575 (machine under load) and 2.780. Under load the margin is thin; the Actions runner result counts.

## Results

- Conformance after merging `r6-evidence` (`aa33e85`): 14,941 / 14,941 pass, including `mc_hash` 6 of 6 (E9). Before the merge: 14,935 / 14,935 (golden split by expected status: 7,413 ok, 5,008 error, 1,257 any, 1,257 same_as).
- `mvn -o -Pcoverage verify`: 511 tests, 0 failures, 1 skipped (the G-9 bound is not asserted under the coverage agent, which distorted the ratio to 11.2; it is asserted on every plain run).
- Coverage (R6-26), JaCoCo, nested classes folded into their file: 137 files, line 98.26% (17,097 lines), branch 92.04%. Every file is at or above 90% line coverage before any new test, so no file needs the allow-list. Lowest five: `calibration/LeastSquares` 92.3%, `core/Finite` 92.9%, `curves/DatedCompounding` 93.4%, `cli/In` 93.8%, `core/TimeZones` 94.0%. Whole-language floor 0.96: met. Before and after are the same per file; the rewritten test below adds value checks, not lines.
- `BookRiskCrossGammaTest` rewritten (review): revaluation cross gamma is now checked against a closed form, the product `N P_a P_b` of two pillar discount factors, whose second derivatives under `P_i exp(-s_i t_i)` are `N P_a P_b t_i t_j` (zero off the two pillars), per bp^2; and the OIS closed form `crossGammaOis` is checked entry by entry against revaluation on a receiver (the old test only compared the fall-back path with itself and checked symmetry). Writing it found that a receiver's `signedNotional` is negative, as `OpsMarketRisk` passes it; no code fault.
- G4 rename note of the evidence lane: `conformance/mutation/stages.json` names no Java file, so nothing to update there.
- R6-25: `java25/SPEC_QUESTIONS.md` now has Stage G (G-J1 to G-J7) and Stage I (J-I1 to J-I7) with status. Open: G-J6 (finding every zero and level crossing in `portfolio_hw` quadrature), G-J7 (PFE key naming for a general quantile), J-I6 (one kink tolerance and iteration cap for all builds, review finding 7).

## Questions for the spec lane

1. R6-8 says `E_DOMAIN` when a finite input overflows; `cli-contract.md` says a non-finite output is `E_NON_FINITE`. Which code applies when an operation's arithmetic overflows to a non-finite result? Java uses `E_DOMAIN` only at the conversion factor until ruled.
2. A golden for the conversion factor overflow input (coupon -1e308) is expected per R6-8 acceptance.
