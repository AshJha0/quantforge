# Stage K integration lane int1: stop note

Branch `k-v1-int1`, cut from main `11ba1b40`. Merges two docs branches one at a time, each checked and reviewed before the next. No PR; not merged into `k-v1` or main.

## State (2026-11-21)
1. `origin/k-v1-docs-c` (25fb092d) merged `--no-ff`, no conflicts. Checks: every Windows-runnable check passed except three that cannot run on this laptop (below). Review: more than 25 numbers rerun against `gh run view` (soak run 44824197236 verdict lines, race, fuzz, adapters, cross-platform runs), `gh pr list`, the ledger summaries and arithmetic; no wrong figure found.
2. `program/R6_HANDOVER.md`: new `TOTALS:` line 16547 / 8099 / 5894 / 2554 (counted; +2 from `wwr_g`, `e1g_xva`, `lex_k` in PRs #60 to #64). `check_case_total.py` is run by no workflow.
3. `origin/k-v1-docs-a` (81c6f247) merged `--no-ff`, no conflicts. `check_tutorial --lang python` passes on pages 59 to 63 (12, 3, 6, 8, 7 lines); `check_cookbook.py` 16 of 16; `test_check_cookbook.py` 9 tests OK.
4. Review fixes: tutorial index named PRs #58/#59 for pages 59 to 63 and "all four builds" for Python-only pages; tutorial 58 row said "not running"; tutorial 60 did not mention the runner soak misses; developer guide on `check_case_total`; banned word in the docs-c stop note.
5. README knowledge-check count: 470 in 14 sets is the true count on this branch (`^### Q` headings: 470; levels 156/197/117); unchanged.
6. `origin/k-v1-docs-b`: out of scope.

## Cannot run on this laptop
`tools/build_gallery.py --check` and `tools/check_quickstart.py` (they spawn the `quantforge` launcher, blocked by Smart App Control); `tools/check_site_view.py --self-test` (Playwright not installed). All three passed in the Docs run on main 44824140754.

## If stopped here
Full Python suite: `cd python && uv run pytest -q` (log in the lane's scratchpad; it was still running).
