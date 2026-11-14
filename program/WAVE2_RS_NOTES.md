# Wave 2, Rust lane: spec notes (2026-11-14)

Implementation: `rust/crates/quantforge-core/src/portfolio_opt.rs` (all seven operations and property tests), CLI in `quantforge-cli/src/ops/research.rs` and `ops/riskw2.rs`, limits in `limits.rs`.

1. Mean-variance with every weight pinned. When the bounds fix the budget (for example `sum lower = 1`), the free set is empty and `nu` is not determined. The page does not say how a build gets out of this. Rust frees index 0, which makes `nu` defined, and then runs the usual multiplier test. No golden reaches this state.
2. Mean-variance tolerances that the page does not state. The multiplier test drops a bound only when the violation is above `1e-13`. The ratio test ignores bound overshoot within `1e-14 (1 + |bound|)`. Without these the active set cycled on a random long-only problem, a degenerate case. Goldens keep a `1e-6` margin (J-W2-4), so these choices do not change any golden answer.
3. Euler with an indefinite `Sigma`: only the symmetry check runs (J-W2-6). Rust does no Cholesky, as the ruling says.
4. Ledoit-Wolf `E_LIMIT`: columns above 500 or `T N` above 10,000,000. Rows are judged at 1,000,000 by the raised-array rule. The page gives "rows 1,000,000 and cells 10,000,000" but does not state the column limit; Rust applies the 500-asset limit.
