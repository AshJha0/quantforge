# R6 Rust lane handover (branch `r6-lang-rust`)

All builds and tests ran in WSL (Ubuntu, toolchain 1.99.1) on a `tar` copy of this worktree, because Windows Application Control blocks fresh Rust executables. Nothing was pushed.

## Phase 0: review findings

| Finding | Result | Evidence |
|---|---|---|
| 3 Jacobian upper-triangle mask (`risk_curve.rs:404`) | **Reproduced**: monotone convex entry [0][1] was 0 against a central difference of 0.00796 | test `jacobian_matches_central_difference_for_non_local_methods` failed before the fix, passes after; mask removed (R6-1.1) |
| 15 Non-finite results, fuzz | **Partly reproduced**: no Rust panic or bad shape in 4 fuzz seeds (11 to 14, 200 s each, about 61,000 inputs), but 4 hangs (timeouts) on finite inputs that overflow: CIR `rates.shortrate.zcb_option` with `sigma` 8e298 or `mean_reversion` 2.5e5 (non-central chi-square loop of up to 1e9 steps) and `vol.garch.estimate` with a return of 1e308 (Nelder-Mead on an infinite variance) | fixed: `stats::noncentral_chi2_cdf` returns NaN for a non-finite weight and caps its downward loop; `garch_estimate::digamma` refuses non-finite arguments; `garch_estimate::estimate` returns `E_NON_FINITE` when the sample variance overflows. All four inputs now answer in under 0.4 s with `E_NON_FINITE` (R6-8.1) |
| 18 MBS PSA above about 1667% gives NaN in Rust | **Reproduced** by reading (`mbs.rs`, `(1 - cpr).powf(1/12)` with `cpr > 1`); the CLI returned `E_NON_FINITE` | R6-7.1: `E_DOMAIN` |
| 5 Rust mutation run cancelled | not in this lane's scope (evidence lane) | |

## Items done

- R6-8 / R6-8.1: overflow from finite inputs is `E_NON_FINITE` (the existing output guard plus the three fixes above).
- R6-16 G4: Rust had no stage-letter module or file names; private helpers renamed (`is_stage_f` to `is_smooth`; `stage_c_above`, `stage_f_raised`, `too_long_stage_f`, `stage_f_above`, `stage_i_above` to domain names; one test). `golden_replay.rs` still names the shared `datasets/golden/stage_*` folders, which are data paths, not modules. Public operation names unchanged.
- R6-16 G-9: test `bermudan_aad::tests::g9_ladder_cost_ratio_at_most_five` (median of 21 after 5 warm-ups, asserts at most 5, prints the ratio). The Actions runner result is the one that counts.
- R6-26: `tests/garch_mutants.rs` rewritten: the test that compared the fit with the implementation's own earlier output is gone; new tests check the spec's hand-computed worked example (loglik 5.410998350356715, variances 2.5e-4, 2.2e-4, next 2.26e-4), the closed-form forecast, and that the fit is a local maximum of a likelihood written independently in the test. New value tests also for ES (hand: 248.2 at n = 250, 497 at n = 500), `sbm_total` (hand totals) and the Jacobian (central difference).
- Coverage (R6-26): not measured locally (cargo-llvm-cov is not installed; installing it was blocked before). Per-file line coverage comes from the CI job `coverage-stage-rust` (`.github/workflows/coverage-stage.yml`, `cargo llvm-cov --workspace --lcov`, then `tools/quality_gate.py --floor`). Files below 90% are not known yet.
- Wave 1: contract 1.12.0; Jacobian mask removed, `tension`/`step_end` checked after `bump_bp`; ES by R6-3.1; `risk.frtb.sbm_total`.
- Wave 2: discrete barrier envelope (R6-2.1); `deflated_pfe_*` keys and the critical-point scan (8,001 points of the analytic slope over +-16 sd, bisection, then one root per monotone piece; R6-5.5); MBS PSA `CPR >= 1` is `E_DOMAIN`; CDS trade on an adjusted coupon date priced (D19 check removed); TIPS rounding (R6-7.5).
- Wave 3 / 3B: Jacobi scaling (QP solved in scaled variables when there is no ridge and the policy is `ERROR`, which leaves the solution unchanged; `MIN_NORM` stays unscaled; scaled rank decisions for equalities, the reduced Hessian, the integer search and `hedge.minvar.ratio`); caps `10 (n + p) + 100` for the active-set and sign-state loops and 1,000,000 nodes for the integer search, both `E_NO_CONVERGENCE`, with a planted cap-of-one property test; kink tolerance `1e-11 max(1, max|x|)`; `max_instruments` outside `1..n` is `E_INPUT` before `E_LIMIT`; minvar pivots on the correlation form (at or below -1e-12 `E_NOT_POSITIVE_DEFINITE`, absolute size below 1e-12 `E_SINGULAR`); empty `eq_matrix` is `E_INPUT`; `usecase.option_hedge_lots`.
- R6-6.1b: after the sign state is found the cost QP re-solves exactly on that orthant, with positions at a kink fixed to exactly 0 by their sign rows (snap), so it cannot stop near zero.

Not built (no goldens): R6-11.9 (negative bumped hazard `E_DOMAIN`) and R6-11.16 (degenerate spread vol `E_SINGULAR`); R6-11.3 to R6-11.5 tolerances are unchanged where the code already used them.

## Large hedge goldens (T6, T7)

`hedgeqp_large_r6`, release build in WSL: n = 50 about 0.3 s per case; n = 200 121 s (`-0004`) and 158 s (`-0005`). T6 (5 s per case at n = 200) is **not met**. The active-set solver rebuilt and inverted the active-set matrix by `q` separate eliminations at every step (O(q^4)); that is now one elimination with cached `G^-1 n` (took the n = 200 cases from over 600 s to the figures above). An incremental factor update would be the next step.

## Conformance

See the final section, written after the last run.

## Questions for the spec lane

1. R6-6.1 counts `p` as the constraints of the problem as given; in the cost QP the split form has `2n` more sign rows. Rust uses the caller's `p` (equalities, finite bounds, margin row). Confirm.
