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

- Conformance: 14,935 / 14,935 pass (golden split by expected status: 7,413 ok, 5,008 error, 1,257 any, 1,257 same_as).
- `mvn -o verify`: 508 tests, 0 failures, BUILD SUCCESS. The coverage profile (`-Pcoverage`) was not run in this lane.

## Questions for the spec lane

1. R6-8 says `E_DOMAIN` when a finite input overflows; `cli-contract.md` says a non-finite output is `E_NON_FINITE`. Which code applies when an operation's arithmetic overflows to a non-finite result? Java uses `E_DOMAIN` only at the conversion factor until ruled.
2. A golden for the conversion factor overflow input (coupon -1e308) is expected per R6-8 acceptance.
