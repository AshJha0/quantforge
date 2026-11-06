# Cross-language conformance

The plain idea: every language gets the same cases with the answers removed, and a runner that knows no finance compares what comes back.

## Contract
All four implementations consume the same golden cases and answer under the same specification. No language is a reference; expected values come only from `oracle/`.

## Golden case record
Each file has `suite`, `spec`, `spec_version`, `generator` and `reviewer`. Each case has:
- `case_id`, `operation`, `inputs`
- `expected`: the status, and the outputs or error code
- `tolerance_class`: a class in `tolerances/policy.yaml`, which has no global default
- `verified_by`: the sources that agreed
- `tags`, and optional `extra_checks`

## Comparison
For a scalar in a class with limits:
`abs(actual - expected) <= absolute + relative * max(abs(actual), abs(expected))`

Exact classes allow no difference. Never silently ignore missing outputs.

## Independence
Passing means a build matches the oracle within tolerance. Agreement between languages proves nothing alone. Where a case has only hand or replay sources, one author wrote both the spec and the check, so this is self-assessment until the human review after the project.

## Report
Each run writes `conformance/reports/NAME.json`, which git ignores, and prints pass, fail and not-implemented counts per suite.

Stage B result (observed, local, Windows, 2026-11-06, at commit `13d9871`): Java, C++, Python and Rust each passed 4,731 of 4,731 cases in 39 suites. CI has not run stage B, as the branch is not pushed. Stage A's cases passed in CI on pull request #1.

## Running

The CLI contract is `specifications/cli-contract.md`. Golden cases are `datasets/golden/**/*.json`, written only by `oracle/`.

```bash
python conformance/runner/runner.py --impl rust
```

Commands per language are in `conformance/runner/implementations.json`. Build the CLI first; `docs/developer-guides/test-infrastructure.md` gives the commands. The runner uses only the Python standard library and holds no financial logic. It strips expected values before sending a case. `python conformance/runner/test_runner.py` tests it against `stub_cli.py`, which replays golden values and injects faults. A case an implementation does not support is reported as not implemented, and the run does not pass.

## Fuzzing

`conformance/fuzz/fuzz_cli.py --impl NAME --seconds 60` damages golden inputs and raw bytes, and sends them through the same CLI each language ships. It checks for a clean exit, one result per input, the result shape and a known error code. It takes the same `--impl` names as the runner, so each language gets the same checks. A failing batch is replayed one input at a time, and each finding is written with its input to `conformance/reports/fuzz/NAME.jsonl`. Rerun with the same `--seed` to get the same inputs.

## Mutation

`conformance/mutation/cpp_mutants.py` is the C++ harness. It swaps operators in a private copy of `cpp26/` and uses the golden cases as the test. Java uses PIT. Python and Rust use mutmut and cargo-mutants, and `golden_mutants.py` scores a sample of their mutants against the golden cases too. The guide above has commands and measured scores.
