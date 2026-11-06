# Rust implementation

Stages A and B of QuantForge in Rust 1.99.1, edition 2024, written from `specifications/` alone. There are no third-party crates.

- `crates/quantforge-core`: the library, one module per spec.
- `crates/quantforge-cli`: the `quantforge` executable and the test function registry.

The other folders in `crates/` are empty placeholders for later stages.

Run `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings` and
`cargo test --workspace`. Build the CLI with `cargo build --release`, then run `python conformance/runner/runner.py --impl rust`
from the repository root.

Open questions on the specs and golden cases are in `SPEC_QUESTIONS.md`, including one known gap against ruling B24.
