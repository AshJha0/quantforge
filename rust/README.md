# Rust implementation

Stages A and B of QuantForge in Rust 1.99.1, edition 2024, written from `specifications/` alone. The library and CLI use no third-party crates; `proptest` is a test-only dev-dependency for the property suites (G6).

- `crates/quantforge-core`: the library, one module per domain. Every public function that returns
  `Result` rejects NaN and infinity as `E_DOMAIN` (E1); infallible kernels such as `black()` are
  marked as unchecked.
- `crates/quantforge-cli`: the `quantforge` executable. `src/ops/` has one module per operation
  domain (`bond`, `core`, `rates`, `vol` and so on); each declares its operations once with
  `registry!`, and the verb table is generated from the registry. `clippy::unwrap_used` is denied
  outside tests.

Run `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings` and
`cargo test --workspace`. Build the CLI with `cargo build --release`, then run `python conformance/runner/runner.py --impl rust`
from the repository root.

Open questions on the specs and golden cases are in `SPEC_QUESTIONS.md`, including one known gap against ruling B24.
