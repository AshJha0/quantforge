# Adding an operation in four builds

**Plain idea.** An operation is a name like `risk.frtb.rrao` that takes a JSON request and returns a JSON result. It exists only when four things agree: a spec page that states the rule, a golden file whose expected values come from an independent oracle, the same handler in Python, Java, C++ and Rust, and the CLI contract that lists it. No build is the reference; the goldens are. This page follows one real operation, `risk.frtb.rrao` (stage K wave 2, merged 2026-11-20), through every file it touches, so you can copy the pattern.

**Formal statement.** The rules live in `specifications/cli-contract.md` (request and result shape, error codes, error order, limits), `conformance/tolerances/policy.yaml` (comparison classes) and the stage rulings. Every path below was read on 2026-11-21 on branch `k-v1-docs-a` (main 11ba1b40); the file list for `risk.frtb.rrao` is the output of `git grep -l 'risk.frtb.rrao'` (measured). Where this page states a rule, the source is named.

## 1. The spec page

Write `specifications/<domain>/<topic>.md` first, in the house order: plain idea, sources table with evidence classes, formal statement per operation (inputs, steps, outputs), worked examples, errors, golden case table, acceptance (fixed before any run), limits. Example: `specifications/06-risk/frtb-drc-rrao.md`, section `risk.frtb.rrao`. Parameters that come from a regulatory table go in a JSON file beside it (`specifications/tables/stage_k/mar23_rrao.json`). Rulings that settle a reading of the source go in a stage rulings file (`specifications/stage-k-rulings-w2.md`) with a status (PROPOSED or CONFIRMED). The acceptance tests are committed before the run that they judge, and a miss is recorded as a miss.

## 2. Goldens from an independent oracle

Expected values come only from `oracle/` (`conformance/README.md`). For wave 2 the generator is `oracle/python/gen_stage_k_w2a.py`, which writes `datasets/golden/stage_k/drc_k.json` using fractions and 50-digit mpmath, and stops at the first failed check. A golden file has a header (`schema_version`, `suite`, `spec`, `spec_version`, `generator`, `reviewer`) and a list of cases, each with `case_id`, `operation`, `inputs`, `expected` (`{"status": "ok", "outputs": {...}}` or `{"status": "error", "error_code": "..."}`), `tolerance_class`, `verified_by`, `tags` and `description`. The reviewer field currently reads "none: self-assessment; no second review (owner decision 2026-11-18)" (lane rules, read).

Every new operation needs, in its suite:

- **Value cases**, each worked by hand in the spec table (`rrao_k-0001` to `-0003`).
- **Error cases**, one per error the spec lists, for example `rrao_ke-0001` (`gross_notional` -1, `E_DOMAIN`).
- **An E1 case**: a Real input set to `"NaN"`, `"Infinity"` or `"-Infinity"`, expected `E_DOMAIN` (ruling F-2; `drc_ke-0017` is the one for `drc_nonsec`). `python tools/check_e1_coverage.py` fails if an operation has none, unless it is listed with a reason in `conformance/E1_EXEMPT.json` (`risk.frtb.rfet` is, because it has no Real input).
- **Two errors at once**, so the order is pinned: `drc_ke-0006` has `notional` missing and `maturity_years` 0 in one request, and expects `E_SCHEMA`.

## 3. Error order

When a request breaks more than one rule, every build must report the same code. HR-66 (`specifications/stage-h-rulings-w2-exec.md`, repo-wide since 2026-11-18) sets the order `E_SCHEMA`, then structural `E_INPUT` (missing or empty lists, lengths, ordering, cross-field consistency), then `E_DOMAIN` (one value outside its domain), then `E_LIMIT`. The contract's finite rule and HR-122 reconcile it with the contract's precedence: `E_PARSE`, `E_SCHEMA`, `E_LIMIT` for request size, the finite rule (`E_DOMAIN`), then the operation's own checks, structural `E_INPUT` before `E_DOMAIN`, and a limit that only arises after validation last (`specifications/cli-contract.md`, "Finite rule"). Each spec states its own order in its errors section; `frtb-drc-rrao.md` cites KR-67 (= HR-122). Write the checks in that order in every build. Java's typed parameter records validate on construction, so an operation whose order matters needs a raw-input entry point there (lane rules, "Lessons").

## 4. The four handlers

Each build has a library function and a thin CLI handler that reads the inputs, calls it and writes the outputs. For `risk.frtb.rrao`:

| Build | Library | CLI handler | Registration |
|---|---|---|---|
| Python | `python/quantforge_core/frtb_drc.py` (`rrao`) | `python/quantforge_core/cli/ops_k_w2a.py` (`@op("risk.frtb.rrao")`) | module listed in `python/quantforge_core/cli/operations.py`; library module in `CORE_MODULES` of `cli/registry.py`; size caps in `cli/limits.py` (or a `limits_k_w2a.py` hook when the spec's caps differ from the generic ones) |
| Java | `java25/src/main/java/org/quantforge/risk/FrtbDrc.java` (`FrtbDrc.rrao`; tables in `FrtbDrcTables.java`) | `java25/src/main/java/org/quantforge/cli/OpsStageKW2a.java` (`rrao`) | `new Registry.Module("frtb_drc_ima", OpsStageKW2a::register)` in `cli/Operations.java` |
| C++ | `cpp26/include/quantforge/core/frtb_drc.hpp` and `cpp26/src/core/frtb_drc.cpp` (namespace `quantforge::frtb_drc`, called as `drc::rrao` in the handler) | `cpp26/src/cli/ops_frtb_drc_ima.inc` (`op_frtb_rrao`) | `#include "ops_frtb_drc_ima.inc"` and `frtb_drc_ima_ops` in `cpp26/src/cli/dispatch.cpp` |
| Rust | `rust/crates/quantforge-core/src/frtb_drc.rs` | `rust/crates/quantforge-cli/src/ops/kw2a.rs` (`"risk.frtb.rrao" => rrao(i)`) | `mod kw2a;` and `("risk", kw2a::NAMES, kw2a::dispatch)` in `ops/mod.rs` |

Tests beside each: `python/tests/test_stage_k_w2a.py`, `java25/src/test/java/org/quantforge/cli/StageKW2aCliTest.java`, `cpp26/tests/test_frtb_drc_ima.cpp` with the golden lines copied into `cpp26/tests/cli_cases.inc`, and `rust/crates/quantforge-core/tests/stage_k_w2a.rs`. Two traps from the lane rules: a test that hard-codes golden counts (C++ `test_multiasset.cpp`, Rust golden replay minimum counts) fails when goldens are added; and gcc does not warn on a local that shadows a namespace constant while clang `-Wshadow` in CI does.

Every output a spec labels carries its `label` string in all four builds (here "regulatory formula on caller inputs; not a regulatory return").

## 5. The contract and the generated files

- `specifications/cli-contract.md`: a section for the operations (rulings, error order, limits, tolerance class) and one row per operation in the operations-by-spec table (inputs and outputs). The contract version is a constant in each CLI and must agree: `CONTRACT_VERSION` in `python/quantforge_core/cli/main.py`, `CONTRACT` in `java25/.../cli/Main.java` and `rust/crates/quantforge-cli/src/main.rs`, and the string in `cpp26/src/cli/dispatch.cpp` (all "1.17.0" on 2026-11-21, read).
- `specifications/name-map.json` is generated: `python tools/gen_name_map.py` writes it from the spec pages and goldens, `--check` fails if stale.
- `tools/outside_shares.py` gets the suite in `STAGE_K_ITEMS` (for stage K), and regenerates `oracle/OUTSIDE_SHARES.json` and `.md`.

## 6. Checks to rerun

On Windows with Python (all standard library unless noted):

```bash
python tools/gen_name_map.py --check
python tools/check_e1_coverage.py
python tools/check_golden_copies.py
python tools/check_tolerance_units.py
python tools/outside_shares.py
python tools/build_references.py
python tools/validation/build_checklists.py --check
python tools/case_figures.py --write
python research/test_preregs.py
uv run --locked --project python pytest python/tests/test_conformance.py -q
python conformance/runner/runner.py --impl python
```

Then the runner for each other build (`--impl java`, `--impl cpp`, `--impl rust`; commands in `conformance/runner/implementations.json`), after building each CLI (`docs/developer-guides/test-infrastructure.md`, "Build the CLIs"). On this laptop the C++ and Rust builds run in WSL, one heavy job at a time, and Java on Windows (lane rules). `python tools/check_case_total.py` compares the golden totals with the last line stated in `program/R6_HANDOVER.md`; on 2026-11-21 it exited 1 on main (16,547 cases against a stated 16,545; measured), because pull requests #60 to #64 added cases without a new line; branch `k-v1-int1` adds the line (16,547). No workflow runs this check (`grep -r check_case_total .github/workflows`: none, read 2026-11-21), so a change of totals needs a new `TOTALS:` line in that file in the same change.

## 7. Docs

A recipe in [COOKBOOK](../../COOKBOOK.md) with a hand-worked example, marked for `python tools/check_cookbook.py` (section "Check the recipes" there), and for a larger topic a tutorial in `docs/getting-started/` that CI runs (`tools/check_tutorial.py`). Every number on a page comes from running the code, or carries its source and evidence class.

## Limits of this page

It describes the pattern the stage K wave 2 operations followed; older stages used other module names (`ops_risk.py`, `ops_lmm_xva_frtb.py` and so on) and the same steps. It does not cover the fuzz, mutation and sanitizer jobs, which pick up a registered operation without further edits (inferred from `conformance/fuzz/fuzz_cli.py` taking golden inputs; not checked for this operation).
