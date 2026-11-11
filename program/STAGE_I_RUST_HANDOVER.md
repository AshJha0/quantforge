# Stage I, Rust lane handover

From the Rust lane (branch `stage-i-lang-rust`) to the spec lane and the coordinator. Written 2026-11-11. Nothing is pushed.

## What is built

Every stage I wave that was READY on `stage-i` at fd3f084: 1, 2, 3, 4a, 4b, 4c, 4d and 4e. All 16 stage I suites pass, 271 of 271 cases. The code follows the spec text; no golden was tuned to.

| Wave | Operations | Module (`rust/crates/quantforge-core/src/`) | Tests (`.../tests/`) |
|---|---|---|---|
| 1 | `hedge.qp.solve`, `hedge.integer.solve`, `hedge.minvar.ratio`, `hedge.greeks.neutralise`, `hedge.beta.futures`, `hedge.residual.report` | `hedge_solvers.rs` | `hedge_solvers.rs` |
| 2 | `hedge.credit.cds`, `hedge.correlation.neutralise` | `hedge_cross.rs` (plus `Hazard::with_hazard_shifts` in `credit.rs`) | `hedge_cross.rs` |
| 3 | `hedge.crossasset.solve` | `hedge_crossasset.rs` | `hedge_crossasset.rs` |
| 4a | `hedge.qp.solve` costs and margin, `hedge.frontier.solve` | `hedge_solvers.rs` | `hedge_costs.rs` |
| 4b, 4e | `hedge.backtest.delta` (with costs), `hedge.effectiveness` | `hedge_dynamic.rs` | `hedge_dynamic.rs` |
| 4c | `hedge.select.solve` | `hedge_solvers.rs` | `hedge_costs.rs` |
| 4d | `hedge.slippage.report` | `hedge_dynamic.rs` | `hedge_dynamic.rs` |

`cargo test` also replays every stage I golden in process (`golden_replay::stage_i_goldens`) and runs the 16 tutorial inputs under `examples/` against their golden cases (`golden_replay::stage_i_examples`), as the follow-up note to waves 1 to 4d asks.

### Methods

- QP: the dual active-set method of Goldfarb and Idnani on the null space of the equalities (Householder QR of `E^T`), so it starts from the unconstrained minimiser and either ends at the unique KKT point or proves infeasibility. The answer is re-solved on the final active set and active bounds are set exactly. `MIN_NORM` uses the pseudo-inverse of `Z^T H Z` with the I-3 threshold on the largest eigenvalue of `H`.
- Integer lots: branch and bound on the bounded continuous relaxation (the same QP), nearer branch first, with the I-7 tie rule.
- Costs and margin (4a): the sign state (zero, positive, negative per instrument) is found on the split problem `x = p - n`, `p, n >= 0`, with a relative regularisation of 1e-6 that makes its Hessian definite. The exact problem is then solved on that orthant, where it is smooth, so a left-out instrument comes back as exactly `0.0`. This is exact whenever the sign state is not degenerate, which spec question Q-I2 says the goldens ensure.
- Selection: every subset of size 1 to `K` in size-then-lexicographic order; a later subset replaces the best only if it is better by more than the tie margin.

## SPEC_QUESTIONS

None of these blocked a golden. In each case the code follows the reading stated, and no golden decides it.

1. **Unknown target names.** `hedge.credit.cds` makes an unknown target `E_INPUT` (stated). `hedge.greeks.neutralise` and `hedge.correlation.neutralise` only say "distinct values from ...". Rust returns `E_SCHEMA` there, as for any other unknown enumeration value. Should those two be `E_INPUT` like the credit hedge?
2. **Extra keys on wave 1 Greek instruments.** Waves 2 and 3 make any key outside the kind's set `E_INPUT`. Wave 1 does not say so. Rust ignores a `quantity` on a `hedges` entry of `hedge.greeks.neutralise` and rejects only `strike` or `expiry_years` on `UNDERLYING`. Should wave 1 adopt the fixed key sets too?
3. **What counts as an instrument for the I-4 and I-35 limits.** Rust counts the columns of `a` (`hedge.qp.solve` 200, `hedge.integer.solve` 12, `hedge.select.solve` 20). A `lot_sizes` list longer than the columns of `a` is therefore `E_INPUT`, not `E_LIMIT`. Please confirm.
4. **Fills limit against the general array limit (I-38).** I-38 allows 1,000,000 fills in total, but the general limit of 100,000 entries per array (`limits.md`) still applies to one order's `fills`. So one order with 200,000 fills is `E_LIMIT` in Rust. Is the general limit meant to be raised for `fills`, as stage F raised it for named keys?
5. **Contract version.** I-1 targets contract 1.11.0. The Rust CLI still reports `contract_version` 1.0.0, as it has since stage A. Should the lanes move it to 1.11.0 at the stage I release, and is there a check that all four agree?

## Open items

- Selection enumerates every subset (`2^20` QPs in the worst case at the I-35 limit). That is correct but slow at the limit; branch and bound on the objective, which the spec allows, would cut it.
- The 4a orthant step is exact only away from degenerate sign states (Q-I2). On a degenerate input the answer comes from the regularised split problem, within about 1e-6 relative.
- Coverage: see the lane report. Line coverage of the new core modules was measured with `-C instrument-coverage` and `llvm-cov`, because `cargo llvm-cov` is not installed.

## After the rulings (I-41 to I-52, `stage-i` aa2297e)

- I-41 changed: `hedge.greeks.neutralise` instruments now use the fixed key sets of waves 2 and 3; a hedge with `quantity`, any other key, or a position without `quantity` is `E_INPUT` (`hedgegreeks_i-0020` passes).
- I-42: no change (already `E_SCHEMA`; `hedgegreeks_i-0021` passes).
- I-43 changed: relative zero-variance tests in `hedge.effectiveness` and `hedge.backtest.delta` (`hedgebt_i-0016` passes).
- I-44 changed: `E_NOT_POSITIVE_DEFINITE` only below `-1e-12 S_00`; a hedged variance between that and 0 is returned as 0 (`hedgemv_i-0018` passes).
- I-45: no change (`hedgeint_i-0019` passes). I-46: the feasibility tolerance is 1e-12 relative, inside the allowed 1e-9. I-47: already `E_SCHEMA` for a `null` optional key (CLI test `stage_i_null_keys_and_limits`). I-48, I-50: no change.
- I-49 added: `E_LIMIT` (field `lot_sizes`) when a relaxed lot count exceeds `2^52`.
- I-51 **not applied in this branch**: `conformance/runner/runner.py` on `stage-i` still has `CONTRACT = "1.0.0"` and stops on a mismatch, so a CLI at 1.11.0 alone fails every suite. The Rust change is one line (`CONTRACT` in `rust/crates/quantforge-cli/src/main.rs`), to land with the runner in the integration PR as I-51 says.
- Each changed behaviour has a unit test (`stray_keys_are_input_errors`, `minvar_perfect_hedge_rounding_is_zero`, `huge_lot_counts_are_a_limit`, and the I-43 cases in `effectiveness_checks`).
