# Incremental curve update (stage K)

Spec version 1.1.0 (audit A response, 2026-11-19: KR-230, KR-231, KR-235(a) and (c); findings KA-A1, KA-A8, KA-A13 of `institutional-quant-engine-plan/STAGE_K_R1_AUDIT_A.md`): the arithmetic of the bit-for-bit cache check is the contract's (`cli-contract.md` "Numeric rules": no contraction, sums in array order), that is `acc = 0`; for each quote `P = (1 - S * acc) / (1 + S)` with a separate multiply, subtract, add and divide, then `acc = acc + P`; inc_k-0007 and 0008 use seeded quote vectors whose fused-multiply-add bootstrap differs from this one, so a build that contracts reports their cache as stale. `curve.incremental.update` applies the `par_annual` checks to both quote vectors (each quote above -1, else `E_DOMAIN`; at most 200 quotes in each list, `01-core/limits.md`, else `E_LIMIT`), and the order is KR-230: `E_SCHEMA`, `E_LIMIT`, the finite rule, the length rule (`E_INPUT`, which also catches empty lists), `E_DOMAIN`, then the stale cache (`E_INPUT`). Discount factors are returned as computed: quotes far above any market level can give a non-positive factor (quotes [1.0, 3.0] give [0.5, -0.125]), and this is not an error. The operation re-runs the full bootstrap of `previous_quotes` to check the cache, so it does at least the work of one rebuild; the saving of an incremental update is in the library entry points, which a caller may use without the check. Earlier: spec version 1.0.0. Status: **CONFIRMED** 2026-11-19, confirmed by the stage K coordinator lane (branch k-w1; was PROPOSED, version 0.1.0, stage K wave 1, plan 14.8 K-4). Rulings: `stage-k-rulings-w1.md` KR-5.

**Plain idea.** In a sequential bootstrap each discount factor depends only on the quotes up to its own maturity. When one quote ticks, the pillars before it cannot change, so only that pillar and the later ones need solving again. The test is that this shortcut gives the same curve as rebuilding everything.

**Formal statement.** Annual par swaps with accrual 1 and quotes `S_1..S_n` give `P_k = (1 - S_k sum_{i<k} P_i) / (1 + S_k)` [standard bootstrap identity; Hagan and West, "Interpolation methods for curve construction", *Applied Mathematical Finance* 13(2) 2006, section 2 (free preprint, UNVERIFIED section number)]. If quotes change only at indices `>= j` (0-based), then `P_0..P_{j-1}` are unchanged and `P_j..P_{n-1}` follow from the same recursion. The library's production bootstraps (stage B) use the same split by first changed index; this hand-sized instrument set exists so a blind lane can check the arithmetic.

## Operations

| Operation | Inputs | Outputs |
|---|---|---|
| `curve.bootstrap.par_annual` | `quotes` (decimals, 1 to 200, each > -1; else `E_DOMAIN`; more than 200 `E_LIMIT`) | `discount_factors` |
| `curve.incremental.update` | `previous_quotes`, `previous_discount_factors`, `new_quotes` (same length, else `E_INPUT`) | `discount_factors`, `first_changed_index` (`null` if none changed), `recomputed` (count) |

`curve.incremental.update` checks that `previous_discount_factors` equals `curve.bootstrap.par_annual(previous_quotes)` bit for bit; if not, `E_INPUT` (a stale cache must not be patched).

## Golden value cases (hand-derived; 30-digit check by mpmath)

Base quotes `[0.02, 0.025, 0.03]`.

Output fields compared: `curve.bootstrap.par_annual` returns `discount_factors` (array of binary64, same length as `quotes`). `curve.incremental.update` returns `discount_factors` (array of binary64, length 3 here), `first_changed_index` (0-based integer, or `null`) and `recomputed` (integer). Error cases compare `error.code` (string) only.

| Case | Operation | Input | Expected discount_factors | Expected first_changed_index | Expected recomputed |
|---|---|---|---|---|---|
| inc_k-0001 | `curve.bootstrap.par_annual` | `quotes` = base | [0.980392156862745098, 0.951697752271640363, 0.914599323034920812] | not an output | not an output |
| inc_k-0002 | `curve.incremental.update` | previous = base and its bootstrap; `new_quotes` = [0.02, 0.026, 0.03] | [0.980392156862745098 (copied), 0.949814623705232580, 0.914654171439767640] | 1 | 2 |
| inc_k-0003 | `curve.incremental.update` | previous = base and its bootstrap; `new_quotes` = [0.02, 0.025, 0.031] | [first two copied from inc_k-0001, 0.911838227756386082] | 2 | 1 |
| inc_k-0004 | `curve.incremental.update` | previous = base and its bootstrap; `new_quotes` = base | inc_k-0001 values, all copied | null | 0 |

<!-- blind:strip -->
Derivation of inc_k-0001: `P_1 = 1/1.02`; `P_2 = (1 - 0.025 P_1)/1.025 = 0.975490196.../1.025`; `P_3 = (1 - 0.03 (P_1 + P_2))/1.03`.
<!-- /blind:strip -->
Tolerance against the expected decimals: 1e-15 absolute (binary64). Between `update` and a full rebuild in the same build: equal to 1e-12 relative (K-4), expected bit-identical.

| Case | Operation | Input | Expected error.code |
|---|---|---|---|
| inc_k-0005 | `curve.incremental.update` | previous = base and its bootstrap; `new_quotes` = [0.02, 0.025] (lengths differ) | E_INPUT |
| inc_k-0006 | `curve.incremental.update` | previous = base; `previous_discount_factors` = the base bootstrap with the last element moved up by one unit in the last place (next binary64 toward +infinity); `new_quotes` = [0.02, 0.026, 0.03] | E_INPUT |

## Acceptance (fixed before any run)

- inc_k-0001..0006 in four languages.
- Property: for 10,000 random quote vectors and random single or multi-index changes, `update` equals full rebuild to 1e-12 relative, and copied pillars are bit-identical.
- The same property on the stage B production bootstrap (all instrument types it supports), which is the K-4 claim; this hand set alone does not make it.

## Acceptance evidence (2026-11-19)

- inc_k-0001..0006 and the `e2_k` cases: pass in all four builds.
- 10,000 random vectors: recomputed pillars bit-identical to a full rebuild in all 10,000 (largest relative difference 0), copied pillars bit-identical; Python and Java (`program/stage_k_w1/acceptance_python.json` and `acceptance_java.jsonl`, key `incremental_property`); C++ and Rust unit tests.
- Stage B production bootstrap: on the 10 sequential log-linear stage B bootstrap goldens, 45 single-quote moves of 1 bp; in every one the first pillar that changes is the moved quote's pillar and every earlier pillar is bit-identical (key `incremental_property_stage_b`, Python and Java). Limitation: the stage B bootstrap has no incremental entry point, so this checks the K-4 premise (earlier pillars cannot move) on the production code, not a patched curve against a rebuild; the patched-against-rebuild check is the hand instrument set above.
- Stage B production bootstrap, patched against rebuilt (added 2026-11-19, branch k-w1-fu; this closes the limitation of the line above, which stays as history). Every build now has an incremental entry point on the production sequential bootstrap, structured as `curve.incremental.update`: the cached discount factors must equal a full solve of the previous quotes bit for bit (`E_INPUT` otherwise), and the sequential solve then resumes from the previous solve's log discount factors at the first quote whose instrument or rate changed (Python `ois.bootstrap_incremental`, `projection.bootstrap_incremental` over `curves.incremental_solve`; Java `Ois.bootstrapIncremental`, `Projection.bootstrapIncremental` over `CurveSolver.incremental`; C++ `ois_bootstrap_incremental`, `projection_bootstrap_incremental` over `solve_curve_incremental`; Rust `OisCurveProblem::solve_incremental`, `projection::bootstrap_incremental` over `curve::solve_incremental`). Stage F interpolations are solved globally (ruling F-21) and give `E_INPUT`. These are library entry points, not contract operations. Test set (evidence class: measured, local laptop, not the acceptance machine): the 25 sequential stage B instrument sets (9 OIS goldens of `ois` in both stage B interpolations, with rate and with bid/ask quotes; the 6 `ois_d` sequential goldens, 2 of them with jumps; the 5 projection goldens of deposits, FRAs and swaps, each in both interpolations) and 10,000 moves: per set no change, each single pillar (the first, every middle one, the last), first and last together, and all pillars at once; then random previous quote vectors (each quote moved by up to 50 bp with probability 1/2) with 1 to n quotes moved by up to 25 bp each. Result: in all four builds, 10,000 of 10,000 moves have every pillar within 1e-12 relative of a full rebuild, and in fact bit-identical to it (largest relative difference 0), the repricing error equal, the first changed index and the count of recomputed pillars as expected, and the copied pillars bit-identical to the cache (Python `test_incremental_update_on_stage_b_bootstrap_equals_rebuild`, key `incremental_property_stage_b_patched` in `acceptance_python.json`; Java `StageKIncrementalBTest`, same key in `acceptance_java.jsonl`; C++ `test_stage_k_incremental_b.cpp`; Rust `stage_k_incremental_b_tests.rs`). The random part differs by build (Python `random.Random(20261119)`, Java `java.util.Random(20261119)`, C++ and Rust one SplitMix64 stream seeded 20261119); the fixed part (342 moves) is the same in all four. Error paths tested in all four: a cache off by one unit in the last place, unequal lengths, a stage F interpolation, a changed tenor (re-solved from its pillar). With this the third acceptance line is met as written, on the production bootstrap.
