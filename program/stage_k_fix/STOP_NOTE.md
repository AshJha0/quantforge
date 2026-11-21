# Lane k-v1-fix: stop note (2026-11-20, updated 2026-11-21)

Branch `k-v1-fix` off `k-v1` at fbf3998e. Laptop shut down at 23:00 UTC (coordinator notice); work resumes in a new session. Local laptop, not the acceptance machine.

## Item 1: KR-258 error-code parity and the xva sweep (done; see "Verification" for what ran)

- Ruling KR-258 (PROPOSED): a first time at or below 0 in `xva.wwr.cva_hw` and `xva.adjustments.value` is structural `E_INPUT` (HR-122 step 4, ordering against the implied `t_0 = 0`; precedent in `financing-term-structure.md`, `cross-asset-hedge.md`, `dynamic-hedge-and-effectiveness.md`). File `specifications/stage-k-rulings-xva-errors.md`. C++ and Java changed from `E_DOMAIN`.
- Goldens through `oracle/python/gen_stage_g_w4b.py`: 12 tag `kr258` (`wwr_g-0027` to `-0032`, `xvaadj_g-0013` to `-0018`), committed red (62a96893) before the fix (3d648db1).
- Sweep: 3,600 random malformed requests over six operations (`program/stage_k_fix/fuzz.py`, `probe.py`). Fixed: C++ read-as-you-check order in the three wave 4b handlers (2ee18e90), 11 goldens tag `hr122`, committed red first (b4e35c8a, f5a5a159). Listed, not fixed: S1 to S9 in the ruling file and known-issues row KV-XVASWEEP.

## Item 2: explicit inputs for KR-133 and KR-44 (NOT STARTED)

Not started, by the coordinator's 17:52 notice (start only if it can finish in four builds by 22:00). The WSL lock queue held eight jobs for about an hour this evening, so a four-build finish was not likely. Findings from reading, for the next session:

- KR-44 (`risk.frtb.backtest.desk`, MAR32.19 limits 12 and 30) is a constant in all four builds: Python `frtb_backtest.py` `DESK_LIMIT_99/975`, Java `FrtbBacktestTables`, C++ and Rust read `desk_limit_99/975` from the table. A plan: optional Integers `desk_limit_99` (default 12) and `desk_limit_975` (default 30), breach when the count is above the limit, `E_DOMAIN` below 0; the other reading of MAR32.19 (30 itself a breach) is `desk_limit_975 = 29`. `desk` is E1-exempt (Integer only), so no E1 golden.
- KR-133 is two different rulings. In this tree (`stage-k-rulings-sbim.md`) KR-133 is the SBIM clipped bucket sum, which has no parameter. In `program/STAGE_K_BASEL_READINGS.md` (branch `k-basel-check`, written before wave 2 numbers were settled) KR-133 is the large-exposures G-SIB group rule ("any member flagged"), which the Basel text leaves open (LEX20.1, LEX40.1, LEX10.9). That operation, `risk.capital.large_exposures`, is spec 0.1.0 PROPOSED and implemented in no build on `k-v1`, so "explicit input in four builds" cannot apply to it yet; it can only be written into the spec (`gsib_group_rule`: `ANY_MEMBER` default, `EVERY_MEMBER`). The coordinator should say which KR-133 is meant. The readings file was not brought into this branch because item 2 was not started.

## Mutation samples: not run: deferred

Coordinator rule for 2026-11-20 evening: no mutation run under the shared WSL lock before the shutdown; pull-request CI runs the mutation-report. This lane changed no mutated source of the `xva` cell (`stages.json`: Python `quantforge_core.xva*`, Rust `**/xva*.rs`, Java `org.quantforge.risk.Xva`, C++ `cpp26/src/core/exposure_lgm.cpp`); it changed only the CLI handlers `cpp26/src/cli/ops_xva.inc` and `java25/.../cli/OpsXva.java`, and added goldens to the `*_g` suite. So the content seeds are those of `k-v1` (computed with `conformance/mutation/content_seed.py` on this branch): Python 2689916947, Rust 4288426842, Java 3820012610, C++ 4020315836. Not run: deferred. The added error goldens can only kill more mutants, not fewer (inferred).

## Verification state at stop (2026-11-20, local laptop, not the acceptance machine)

- Run, green: Java `mvn verify` (twice, the second after every golden); Python ruff, ruff format, mypy; Python pytest on the 46 test files that touch xva, stage G or goldens (1,796 passed, 3 skipped, 11 min) and `test_conformance.py` for `wwr_g`, `xvaadj_g`, `collexp_g`, `sbim_g`; conformance on the xva suites in all four builds (Python and Java 642 + 11 new cases; C++ and Rust 653 of 653 after the fix); C++ release build with `-DQF_WERROR=ON` and ctest (100%); the four-build probe of all 23 new goldens; repo gates of `repo-gates.yml` run on Windows (all pass after two doc fixes), K-7 checks `model_reports --check`, `results_page --check`, `check_known_issues`; the "after any spec edit" list; `research/test_preregs.py`.
- Not run: the full Python pytest (it did not finish in 28 minutes: `test_conformance.py` replays every suite, `expsim_g` alone takes minutes in Python; no failure seen before the stop); Rust fmt, clippy and `cargo test` (no Rust source changed; Rust conformance on the xva suites passed); the C++ ASan build; the four mutation samples (above). Whole-repo conformance in four builds was not run; only the xva suites listed.

## Session of 2026-11-21: merged with `k-v1`, full verification

Merged the local `k-v1` at 47072365 (merge b7022ff4), then at 19399ec0 when the coordinator added the TOTALS commit during this session (merge da368e49). Conflicts: `CHANGELOG.md` (both "Fixed" sections kept), `docs/known-issues.md` (`k-v1` table with its new "Re-verified by" column, plus the rows KV-XVASWEEP and KV-XVAERR of this branch), `docs/results.md` and `docs/case-figures.md` (taken from `k-v1`, then regenerated). Regenerated with the tools: `build_references.py`, `tools/validation/build_checklists.py`, `gen_name_map.py`, `case_figures.py --write`, `outside_shares.py`, `tools/validation/model_reports.py`, `results_page.py`; every `--check` passes. Hand counts made true at the merged head: README and LEARN 5,933 error cases, 16,586 in all; `program/R6_HANDOVER.md` TOTALS line `16586 value 8099 error 5933 invariance 2554` (the 23 goldens of this branch). New known-issues row KV-EXPLICIT (item 2, below).

Commands and results at da368e49 (code identical to 6142d78f; the later commit changed only docs and the TOTALS line). Local laptop, not the acceptance machine. Measured.

| Language | Command | Result |
|---|---|---|
| Python | `uv run ruff check .`, `ruff format --check .`, `mypy .` | pass, pass, pass |
| Python | `uv run pytest -q` (full suite) | 4,336 passed, 3 skipped, 1 h 10 min |
| Python | `conformance/runner/runner.py --impl python` | 16,586 of 16,586 |
| Java | `mvn -B -Pcoverage verify` (mkdir lock `mvn.lock.d`) | BUILD SUCCESS, 1,090 tests, 0 failures, 1 skipped |
| Java | `quality_gate.py --lang java --floor --per-file` | 8 modules at 85%, 0 below |
| Java | `runner.py --impl java` | 16,586 of 16,586 |
| Rust | `cargo fmt --check`, `cargo clippy -D warnings`, `cargo test` | pass, pass, 795 passed 0 failed |
| Rust | release build, `runner.py --impl rust` | 16,586 of 16,586 |
| C++ | Release `-DQF_WERROR=ON` build (first part timed out at 600 s, rerun incremental), `ctest` | 6 of 6 |
| C++ | `runner.py --impl cpp` | 16,586 of 16,586 |
| C++ | ASan + UBSan build and `ctest` | ASAN_RESULT |
| repo | `python -m pytest -q tools` | 110 passed, 4 skipped |
| repo | `tools/check_case_total.py` | pass (16,586; first run failed before the TOTALS line was added) |
| repo | `research/test_preregs.py`, `check_known_issues.py`, `results_page.py --check` | pass |

Not run: the four mutation samples (as before; pull-request CI runs the mutation report).

## Item 2 status (2026-11-21): open, not started

Not done: it is a four-build change with spec edits and new goldens, not small. Listed as KV-EXPLICIT in `docs/known-issues.md`.

- KR-44: the plan above stands (optional `desk_limit_99` default 12, `desk_limit_975` default 30).
- KR-133, the two readings, for the coordinator to decide (no reading picked here):
  - Reading S (the number as it stands in this tree): KR-133 is the SBIM clipped bucket sum, `specifications/stage-k-rulings-sbim.md` line 14, cited by `specifications/06-risk/sbim-placeholder.md` line 92. It has no free choice to expose: an "explicit input" would mean an option to switch the clip off, which the ruling itself excludes ("no unclipped first attempt").
  - Reading G (what the decision text points at): the G-SIB 15% group rule of `risk.capital.large_exposures`. Evidence (read): the coordinator's stage K resume file (outside the repo), line 77 ("k-basel-check (KR-133 mixed G-SIB group and KR-44 genuinely open: plan = explicit inputs with current default)") and `program/STAGE_K_BASEL_READINGS.md` on branch `k-basel-check` (0f1eae79, 2026-11-19) items 1 and 4. On `k-v1` this rule was renumbered KR-324 (`specifications/stage-k-rulings-w2.md` line 69, CONFIRMED 2026-11-20, "any member", inferred), it is implemented in all four builds (correcting the 2026-11-20 note above, which predates the wave 2 merge), Java holds it as `Leverage.GSIB_GROUP_ANY_MEMBER` (marked open reading), and golden `lex_k-0010` pins a mixed group. Under G the work is an optional input (for example `gsib_group_rule`: `ANY_MEMBER` default, `EVERY_MEMBER`) in four builds plus goldens for both values; the defaults keep every current golden.
  - The two numbers collide, inferred, because the Basel readings file was written before the wave 2 rulings were renumbered into the KR-300 block (the KR-133 text quoted there matches KR-324); the coordinator may want the readings file's "KR-133" read as KR-324.
