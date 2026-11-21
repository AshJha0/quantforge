# STOP NOTE, lane k-v1-aad (K-8 AAD of the valuation adjustments, now also holding k-xva-spec)

## Update 2026-11-21 (branch-update lane, session 5)

Branch `k-v1-aad` now holds `k-xva-spec` (c7a036cc, merge 1st) and local `k-v1` (47072365, merge 2nd); `k-xva-spec` itself is unchanged. Local laptop, not the acceptance machine.

**Merges.** `git merge k-xva-spec`: one conflict, `docs/model-inventory.md` (both entries kept: MK-12 and MKX-1..9). `git merge k-v1`: conflicts in hand docs (CHANGELOG, LEARN, README, ROADMAP, known-issues, results, release notes v0.10.1), code counts (C++ `test_cli.cpp` operations 387 + 1 = 388; Rust `golden_replay.rs` stage K minimum, set to the 580 cases found after the first run failed on a guessed 601), `specifications/cli-contract.md` (both sections kept), `tools/results_verdicts.json` (both rows kept) and generated files (taken from `k-v1`, then regenerated with `gen_name_map.py`, `build_references.py`, `build_checklists.py`, `case_figures.py --write`, `outside_shares.py`, `model_reports.py`, `status_ladder.py`, `results_page.py`). `program/R6_HANDOVER.md` has a new TOTALS line.

**Content.** KR-296 and KR-297 marked CONFIRMED (coordinator, 2026-11-21) in `specifications/stage-k-rulings-xva.md`, the three K-8b specs, the oracle comments (the candidate files and MANIFEST are unchanged, they already use the bucket start), CHANGELOG, model inventory and known-issues. New known-issues row "K-8 AAD = bump (plan 14.8)" (K-9 part 2, Major 3): the 1e-8 clause is delivered for `xva.adjustments.value` only (13 value goldens, tolerance fixed failing-first in 7ea4d91f, passing in all four builds below) and NOT delivered for the other six KR-162 operations; generated into `docs/results.md`.

**Second merge (19:00 UTC, coordinator request):** `origin/k-v1` 5e4facc9 merged into `k-v1-aad` (merge 490b9b59): conflicts only in count lines and generated files (taken from `k-v1`, regenerated); a new `TOTALS:` line in `program/R6_HANDOVER.md`. The Rust replay minimum stays 580 (a floor; more cases exist now).

**Merged head counts** (generated): 388 operations, 16,646 cases (8,155 value-checked, 5,937 error, 2,554 invariance).

Verification at the final merged head (490b9b59; later commits touch only this note), 2026-11-21, local laptop, not the acceptance machine:

| Language | Command | Result |
|---|---|---|
| Python (Windows) | `uv run ruff check .`, `ruff format --check .`, `mypy .` | rc 0, rc 0, rc 0 |
| Python | `coverage run -m pytest -q` + per-file coverage gate | 4,478 passed, 2 skipped; gate: 8 modules at 85%, 0 below |
| Python | conformance runner, full tree | 16,646 of 16,646 (aadadj_k 37 of 37) |
| Java (Windows, mvn lock) | `mvn -B -Pcoverage verify` + coverage gate; package | 1,102 tests, 0 failures, 1 skipped; 8 modules at 85%, 0 below; rc 0 |
| Java | conformance runner; `check_tutorial.py --lang java` | 16,646 of 16,646; rc 0 |
| Rust (WSL) | `cargo fmt --check`, `clippy -D warnings`, `cargo test --workspace` | rc 0, rc 0, 801 passed in 39 binaries |
| Rust | release CLI conformance | 16,646 of 16,646 |
| C++ (WSL) | Release `-Werror` build, ctest, conformance | rc 0; 6 of 6; 16,646 of 16,646 |
| C++ | ASan/UBSan build; `quantforge_core_tests` in 6 Catch2 shards (`--shard-count 6`), each under the lock and the 10-minute cap | build rc 0; 711 test cases, all pass, no sanitizer report. The single `ctest` run of `asan2` exceeds the 10-minute cap (TIMEOUT, as on k-v1-fix, k-v1-rev1, m5), hence the shards (`_h4ci/kv1/k-v1-aad/asan_shards.sh`). The five small ASan ctest tests (snapshot, k5a) passed at the pre-merge head only |
| Repo | `python -m pytest -q tools`; `check_case_total.py`; `research/test_preregs.py` | 118 passed, 4 skipped; rc 0 (16,646 / 8,155 / 5,937 / 2,554 equal to the handover line); OK |
| Repo | the 18 gates of `_h4ci/kv1/gates.sh` | 17 rc 0; `outside_shares.py --check` rc 1 (open item 1) |

Before the second merge (head e5c4a21d) the same set was run and passed (Python 4,419 passed, 3 skipped; Java 1,095 tests; Rust 801; C++ 6/6; conformance 16,600 of 16,600 in all four builds; ASan shards 711 test cases). The first Rust run failed only on the stage K replay minimum (a guessed 601 against 580 found), fixed in f830637f.

**Open.**
1. `outside_shares.py --check` is red: K-8 AAD (`aadadj_k`) 0 of 13 outside-checked. The tool credits only goldens in `datasets/golden/stage_k/` whose `verified_by` records a DR-H2 MATCH on every compared output. The 41 blind v2 matches are on the K-8b candidates, which are not goldens (KR-299), and no blind packet covered the `aadadj_k` outputs (the `hazard_buckets` entries were never in a packet). Nothing was credited. Route: a blind packet over the 13 `aadadj_k` value inputs, or the K-8b build.
2. K-8b operations not implemented in any build (MVA, ColVA, funding curves, stressed exposure, MPoR close-out, WWR copula, shock library, AMC, the AAD extension). Not tractable in this session (nine operations times four builds, plus error goldens). Spec conflict to rule on first: `xva-aad-sensitivities.md` (K-8b, `aadx_k`) and `xva-aad-adjustments.md` (K-8 AAD, built) both define `xva.sens.aad`, with different `wrt` grammars (indexed paths and an `outputs` list against KR-263 keys with array values).
3. ORE runs for MVA and the shock library: not run, not claimed. WWR SciPy checks are not counted as outside checks.
4. Mutation samples for the xva cells (Python and Rust) still not run (unchanged from 2026-11-20 below).

---

## Earlier note (2026-11-20)

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
