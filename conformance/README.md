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

Commands per language are in `conformance/runner/implementations.json`. Build the CLI first; `docs/developer-guides/test-infrastructure.md` gives the commands. The runner uses only the Python standard library and holds no financial logic. It strips expected values before sending a case. `python conformance/runner/test_runner.py` tests it against `stub_cli.py`, which replays golden values and injects faults. A case an implementation does not support is reported as not implemented, and the run does not pass.

## Fuzzing

`conformance/fuzz/fuzz_cli.py --impl NAME --seconds 60` damages golden inputs and raw bytes, and sends them through the same CLI each language ships. It checks for a clean exit, one result per input, the result shape and a known error code. It takes the same `--impl` names as the runner, so each language gets the same checks. A failing batch is replayed one input at a time, and each finding is written with its input to `conformance/reports/fuzz/NAME.jsonl`. Rerun with the same `--seed` to get the same inputs.

## Mutation

`conformance/mutation/cpp_mutants.py` is the C++ harness. It swaps operators in a private copy of `cpp26/` and uses the golden cases as the test. The other languages use PIT, mutmut and cargo-mutants, as described in the guide above.
