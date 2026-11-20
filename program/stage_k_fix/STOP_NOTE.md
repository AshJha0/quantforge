# Lane k-v1-fix: stop note (2026-11-20)

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
