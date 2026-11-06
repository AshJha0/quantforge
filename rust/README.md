# Rust implementation

Stage A of QuantForge in Rust 1.99.1, edition 2024, written from `specifications/01-core/` and
`specifications/cli-contract.md`. There are no third-party crates.

- `crates/quantforge-core`: the library, one module per spec.
- `crates/quantforge-cli`: the `quantforge` executable and the test function registry.

Run `cargo fmt --all -- --check`, `cargo clippy --workspace --all-targets -- -D warnings` and
`cargo test --workspace`. Build the CLI with `cargo build --release`, then run the neutral runner from the
repository root.

Open questions on the specs and golden cases are in `SPEC_QUESTIONS.md`.
