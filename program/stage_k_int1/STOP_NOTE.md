# Stage K integration lane int1: stop note

Branch `k-v1-int1`, cut from main `11ba1b40`. Merges two docs branches one at a time, each checked and reviewed before the next. No PR; not merged into `k-v1` or main.

## State (2026-11-21)
1. `origin/k-v1-docs-c` (25fb092d) merged `--no-ff`, no conflicts. Checks: every Windows-runnable check passed except three that cannot run on this laptop (below). Review: more than 25 numbers rerun against `gh run view` (soak run 44824197236 verdict lines, race, fuzz, adapters, cross-platform runs), `gh pr list`, the ledger summaries and arithmetic; no wrong figure found.
2. `program/R6_HANDOVER.md`: new `TOTALS:` line 16547 / 8099 / 5894 / 2554 (counted; +2 from `wwr_g`, `e1g_xva`, `lex_k` in PRs #60 to #64). `check_case_total.py` is run by no workflow.
3. `origin/k-v1-docs-a` (81c6f247) merged `--no-ff`, no conflicts. `check_tutorial --lang python` passes on pages 59 to 63 (12, 3, 6, 8, 7 lines); `check_cookbook.py` 16 of 16; `test_check_cookbook.py` 9 tests OK.
4. Second check pass after the docs-a merge found three failures the branch carried: `tools/test_tools.py` (tutorial 60 had 3 expected lines, the test needs 4; fixed by printing the frozen rule from `analyse.RULES`), `tools/check_docs_status.py` (developer guide count without its classes) and `check_md_anchors.py --site` (raw-HTML link to `../capacity.md` in tutorial 60). All three pass now; site 849 pages, 0 broken links, a11y static no error-level finding; `test_preregs` OK.
5. Review fixes: tutorial index named PRs #58/#59 for pages 59 to 63 and "all four builds" for Python-only pages; tutorial 58 row said "not running"; tutorial 60 did not mention the runner soak misses; developer guide on `check_case_total`; banned word in the docs-c stop note.
6. README knowledge-check count: 470 in 14 sets is the true count on this branch (`^### Q` headings: 470; levels 156/197/117); unchanged.
7. `origin/k-v1-docs-b`: out of scope.

## Cannot run on this laptop
`tools/build_gallery.py --check` and `tools/check_quickstart.py` (they spawn the `quantforge` launcher, blocked by Smart App Control); `tools/check_site_view.py --self-test` (Playwright not installed). All three passed in the Docs run on main 44824140754.

## Python suite
`cd python && uv run pytest -q -x`: 4327 passed, 3 skipped (two opt-in long runs and one acceptance run), 17 min 51 s, Windows, after the docs-c merge; docs-a changes no file under `python/`. Java, C++ and Rust builds not run (docs-only merges; C++ and Rust need WSL, not used by this lane).

## Done
Lane work is complete; nothing pending on this branch.

## Follow-on (coordinator, 2026-11-21)
1. CI: Repo gates runs `tools/check_case_total.py`; Docs runs `tools/test_check_cookbook.py && tools/check_cookbook.py` after `uv sync` (paths filter extended). No setup-java step touched.
2. K-2 measured: one ledger row (2026-11-20), anchors at Bitcoin heights 976796 and 976809; `verify_ledger.py verify --no-cli` ok, `recorded_trading_days` null (headers not fetched: an outside download). Written as "not met: at most 1 of 20" in README status block, site_facts and ROADMAP. Note: on Windows extract the anchors with `git -c core.autocrlf=false archive`, or the OpenTimestamps proof fails ("proof is for a different file").
3. `origin/k-v1-docs-b` (cb1fdf26) merged, no conflicts. Fixes: ARCHITECTURE line 5 no longer cites ISDA; README 63 tutorials (was 50) and 500 questions (was 470); LEARN set 14 is 82 questions (said 32); Q14.32 no longer says the ledger never ran.
