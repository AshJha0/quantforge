# STOP NOTE, lane k-v1-aad (K-8 AAD of the valuation adjustments)

Written 2026-11-20 before the 23:00 UTC shutdown. Branch `k-v1-aad` (off `k-v1` at 105f7f96), pushed. Local laptop, not the acceptance machine.

## What exists

- Operation `xva.sens.aad` on `xva.adjustments.value`: spec `specifications/06-risk/xva-aad-adjustments.md` 0.1.0, rulings `specifications/stage-k-rulings-xva-aad.md` KR-262 to KR-268 (PROPOSED), contract entry in `specifications/cli-contract.md`.
- Goldens `datasets/golden/stage_k/aadadj_k.json`: 37 cases (13 value, 24 error, 9 of them two-error), oracle `oracle/python/gen_stage_k_aadadj.py` (50-digit Richardson bump, checked against a 50-digit closed-form adjoint to 1e-30). Failing-first commit 7ea4d91f.
- Registered in all four builds: Python `quantforge_core/xva_aad.py`, Java `org.quantforge.risk.XvaAad` + `OpsXva.sensAad`, Rust `quantforge_core::xva_aad` + CLI arm, C++ `include/quantforge/core/xva_aad.hpp` + `op_xva_sens_aad`.

## Builds (measured 2026-11-20)

| Build | Done | Not done |
|---|---|---|
| Python | ruff, format, mypy; full pytest 4,070 passed; coverage gate per file 90%: 0 below; conformance aadadj_k 37/37; 1,000-request A2 property: largest relative gap 2.4e-12 | none |
| Java | `mvn -Pcoverage verify` green (1,012 tests), coverage gate green, conformance 16,295/16,295, tutorials green | none |
| C++ | plain Release build with -Werror, ctest green (after operation count 369 to 370), conformance 16,295/16,295, tutorials green | ASan/UBSan build and gcovr coverage gate not run locally (too long for a locked slot); CI runs them |
| Rust | fmt, clippy `-D warnings`, `cargo test --workspace` green (35 test binaries, 6 xva_aad tests), release CLI conformance 16,295/16,295 | `cargo llvm-cov` coverage gate not run locally |

## Mutation (gate: 40 sampled per cell, at least 32 killed)

- Python cell `quantforge_core.xva*`: **mutation sample not finished: 0 of 40 scored**, seed 2297994266 (content seed of the current `xva.py` + `xva_aad.py`). The run was stopped at the coordinator's request after it held the WSL lock 55 minutes (other lanes queued; the golden_mutants.py unit pass over every xva mutant does not fit a 10-minute locked slice, so it is deferred); golden_mutants.py writes its JSON only at the end, so no per-mutant result exists. An earlier run on seed 2029832151 (before the `guard` fix) was also stopped and is void.
- Rust cell `**/xva*.rs`: **not run**. Seed = `python3 conformance/mutation/content_seed.py --lang rust --target '**/xva*.rs'` on the final sources.
- Kill tests written in advance: `python/tests/test_xva_aad_kills.py` (in the mutmut test list of `python/pyproject.toml`), Rust `aad_adjust_tests.rs` (`every_entry_against_a_binary64_bump` and identities). Never reported as a pass.

## Not met, recorded

- Outside share: plan item K-8 AAD 0 of 13 value cases outside-checked (KR-268), so `tools/outside_shares.py --check` reports the item under the 60% floor. A DR-H2 blind packet of the 13 value inputs is the route. The coordinator decides whether the branch enters a PR before that.

## Exact next step

1. Run the mutation samples in slices (a few mutants per locked job): Python `golden_mutants.py --impl python --target 'quantforge_core.xva*' --suite '*_g' --max 40 --seed <content seed>` and Rust likewise; add kill tests until each cell kills at least 32 of 40; never edit skip-equivalents.json.
2. C++ ASan and coverage, Rust llvm-cov: leave to CI or run in a quiet window.
