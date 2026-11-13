# Stage J lane J-0b hand-over (2026-11-13)

Branch `stage-j-fuzz` (worktree `C:/Work/Claude/qf-wt/j0b`), from `main` 3cca7da. Not pushed. Fuzz findings from `main` run 43390662426, seed 3.

| Fix | Ruling | Java | Python | Rust | C++ |
|---|---|---|---|---|---|
| `vol.garch.forecast` horizon 2^31 timeout | J-0b.1: horizon > 100,000 is `E_LIMIT` | already had it | added (`cli/limits.py`) | added (`cli/src/limits.rs`) | added (`cli/ops_vol.inc`) |
| `vol.garch.estimate` timeout on fuzzed `garch_f-0010` (return -2.68e297, its square overflows) | J-0b.2: `E_NON_FINITE` before any search (R6-8.1) | was `E_DOMAIN`, fixed (`GarchMle.java`) | was a 20 s all-inf search, fixed (`variance.py`) | already `E_NON_FINITE` | was `E_NO_CONVERGENCE`, fixed (`vol_stats.cpp`) |
| `exotic.basket.moment` ragged correlation crash (exit 70) | J-0b.3: every row length checked first, `E_INPUT` | fixed (`OpsExotics.java`) | already `E_INPUT` | already `E_INPUT` | already `E_INPUT` |

Rulings are in `specifications/stage-j-rulings.md` (new file); the limit row is in `specifications/01-core/limits.md`; the CHANGELOG entry is under "Unreleased (0.9.0)". The new golden suite is `datasets/golden/stage_j/fuzzfix_j.json` (6 error cases), written by `oracle/python/gen_stage_j_fuzz.py`.

## Results

- Conformance: each of the four languages passes all of fuzzfix_j 6/6, garch_e 29/29, garch_f 17/17, exotic_e 128/128, rulings_e_a 17/17 and e1_exotic 411/411. Rust and C++ ran in WSL from a `git archive` of 62577ce.
- Unit tests: Java `mvn -o test` green. Python `pytest -k "garch or limit or basket"` 70 passed. Rust `cargo test --release` all ok. C++ built with `-DQF_WERROR=ON`, and ctest passed.
- Fuzz with seed 3 for 60 s: Java (9,800 cases) and Python (3,600) gave 0 findings. Rust and C++ were not fuzzed locally.

## Follow-up (2026-11-13, commit after 9a839f8)

- Ragged-matrix audit (J-0b.3). Every Java `anyMatrix` caller (23 sites, 33 operation and key pairs with a golden case) was probed in all four languages with three ragged shapes and a short extra row: 132 probes, all `E_INPUT` in Java, Python, Rust and C++. No code or ruling change was needed. One probe per pair (first row one entry short) is now a golden case: `fuzzfix_j` has 39 cases (0007-0039 built by `gen_stage_j_fuzz.py` from named source goldens).
- Unit tests for J-0b.1..3 in each language: `python/tests/test_stage_j_fuzzfix.py`, `java25/.../cli/StageJFuzzFixTest.java`, `cpp26/tests/test_stage_j_fuzzfix.cpp` (added to CMake), module `stage_j_fuzzfix_tests` in `rust/crates/quantforge-cli/src/main.rs`.
- Counts: 15,116 golden cases (error 5,161). `TOTALS:` line in `program/R6_HANDOVER.md`, README headline and `docs/case-figures.md` updated; `check_case_total`, `case_figures --check` and `check_docs_status` pass.
- Results: Python full suite 2,005 passed, 2 skipped, mypy on tests clean; Java `mvn -o test` green; Rust `cargo test --release` ok, clippy `-D warnings` clean, rustfmt clean after one fix; C++ `-DQF_WERROR=ON` build and ctest green (WSL, `git archive`, TMPDIR moved off the full /tmp tmpfs). Conformance 39/39, 29/29, 17/17, 128/128, 17/17, 411/411 in all four.

## Left

- Not checked: `check_error_cases.py` on stage_j; the site build; CHANGELOG case count for 0.9.0.
