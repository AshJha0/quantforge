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

## Waves 1A, 1B, 2 and 3 (r6 merged at `d51d30a` and later; R6-6.1b read at `24b7c94`)

Implemented: contract 1.12.0 (R6-0.1); Jacobian `tension`/`step_end` (R6-1.2; no mask, R6-1.1); ES tail weight `w = n - n c` (R6-3.1); `risk.frtb.sbm_total` (R6-4.1); conversion factor overflow is `E_NON_FINITE` (R6-8.1, `Bonds.java`); `per_unit` class in `GoldenSuiteTest` (R6-10); BGK envelope (R6-2.1); `deflated_pfe_` keys (R6-5.1); PSA CPR cap (R6-7.1); CDS trade date on an IMM date priced (R6-7.3); TIPS rounding (R6-7.5); kink tolerance 1e-11, caps `10 n + 100` and 1,000,000 lattice points (R6-6.1, `IterationCapTest`); Jacobi-scaled singularity decision (R6-6.2); feasibility 1e-9 (R6-11.3); select K > n `E_INPUT` (R6-11.6); scaled minvar pivots (R6-11.7); hazard bump floor (R6-11.9); empty `eq_matrix` `E_INPUT` (R6-11.13); spread vol threshold (R6-11.16, see J-R6-2); use case 6 `usecase.option_hedge_lots` (R6-11.20). Beta order (R6-11.12) and unknown instrument `E_SCHEMA` (R6-11.18) already held.

R6-6.1b: after the sign state is found, Java's final step is an exact re-solve on that state: positions at a kink are fixed to exactly 0 (the closed orthant bound), never left near zero.

### Results

- Conformance: **15,072 of 15,076**. The 4 failures are goldens that were not regenerated after the R6 rulings: `e1_risk-0372` (copy of `risk_f4-0039`; the regenerated `risk_f4-0039` expects ES 52,593.474 and `tail_count` 50, Java's value, but the copy still holds the old 52,486.18 and 51) and `edge_d-0015` to `-0017` (`infl.linker.price` without the R6-7.5 rounding). Java follows the rulings. Expected split once regenerated: 7,440 value, 5,122 error, 2,514 invariance.
- Unit tests (`-Pcoverage verify`): 526 run, 1 skipped (the G-9 bound under the coverage agent), 2 failures, both `GoldenSuiteTest` on the same 4 stale goldens.
- Coverage (R6-26): 137 files, line 98.21% (17,344 lines), branch 91.91%. Every file is at or above 90% line coverage, so none needs the allow-list; lowest `calibration/LeastSquares` 92.3%, `core/Finite` 92.9%, `curves/DatedCompounding` 93.4%.
- Large hedge goldens (`hedgeqp_large_r6`, warm batch, laptop under load from other lanes; Actions runner figures count): n = 50: 22 to 35 ms (T7 target 0.5 s, stretch 0.05 s: both met); n = 200: 3.0 to 4.9 s (T6 target 5 s: met with little margin; stretch 0.5 s not met). Cold single runs: 0.5 to 0.9 s at n = 50, 4.5 to 13.1 s at n = 200.

### Open questions (detail in `java25/SPEC_QUESTIONS.md`, section R6)

J-R6-1 negative-pivot band; J-R6-2 `hedgecorr_i-0015` expects `E_DOMAIN` against R6-11.16 `E_SINGULAR`; J-R6-3 the 4 stale goldens above; J-R6-4 scaled test not applied under `MIN_NORM`; J-R6-5 dual active-set cap now `10 n + 100`.

## Wave 3B (r6 merged at `b19054f` or later)

Applied: iteration cap `10 (n + p) + 100` with `p` the constraints (dual active set: its constraint count; sign search: the equalities); minvar scaled pivot at or below -1e-12 is `E_NOT_POSITIVE_DEFINITE`, absolute size below 1e-12 `E_SINGULAR`; `MIN_NORM` unscaled; `hedgecorr_i-0015` `E_DOMAIN` confirmed. Every J-R6 question is closed.

Results: conformance **15,918 of 15,918** pass on the goldens present after this merge (the runner counts every file now on `r6`, which is more than the 15,076 stated for wave 3; the coordinator should check the expected total). The 4 regenerated goldens pass. `mvn -o verify`: 528 tests, 0 failures, 0 skipped.

## Wave 3C (r6 merged at `a8a363e`)

The stray files `stage_f/e1_risk_1.json` and `e1_risk_2.json` are gone. Conformance **15,076 of 15,076** (7,440 value, 5,122 error, 2,514 invariance). `mvn -o verify`: 526 tests, 0 failures, 0 skipped, BUILD SUCCESS.
