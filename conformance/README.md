# Cross-language conformance

## Contract
All language implementations consume the same versioned test vectors and produce outputs conforming to the same mathematical specification.

## Test-vector record
Each case should include:
- `case_id`, `domain`, `spec_version`, `description`
- `inputs` with explicit units and conventions
- `expected` values and units
- `tolerance` with `absolute` and `relative`
- `verification_method` and provenance
- optional `tags`: boundary, invalid, stress, regression

## Comparison
For scalar values use:
`abs(actual - expected) <= abs_tol + rel_tol * max(abs(actual), abs(expected))`

For vectors and matrices, define element-wise and aggregate error metrics. NaN/Inf handling must be explicit. Never silently ignore missing outputs.

## Independence
At least one expected-value source must be independent of the implementation under test. Use analytical cases, hand calculations, authoritative published examples or a suitable independent library/reference. Cross-language agreement is necessary but not sufficient.

## Report
Report pass/fail counts, maximum absolute/relative error, skipped cases, implementation versions and fixture/spec versions.

## Running

The CLI contract is `specifications/cli-contract.md`. Golden cases are `datasets/golden/**/*.json`, written only by `oracle/`.

```bash
python conformance/runner/runner.py --impl rust
```

Commands per language are in `conformance/runner/implementations.json`; those paths are placeholders until each CLI exists. The runner uses only the Python standard library and holds no financial logic. It strips expected values before sending a case. `python conformance/runner/test_runner.py` tests it against `stub_cli.py`, which replays golden values and injects faults. A case an implementation does not support is reported as not implemented, and the run does not pass.
