# Stage K integration lane int1: stop note

Branch `k-v1-int1`, cut from main `11ba1b40`. Merges two docs branches one at a time, each verified and reviewed before the next. Not a PR; not merged into `k-v1` or main.

## State (2026-11-21)
1. `origin/k-v1-docs-c` (25fb092d) merged with `--no-ff`, no conflicts. Checks and review in progress.
2. `origin/k-v1-docs-a` (81c6f247): not merged yet.
3. `origin/k-v1-docs-b`: out of scope (still being written).

## If stopped here
Rerun the checks (lane rules lists, tools/check_*.py, site build, a11y static, test_preregs, full Python suite with `uv run pytest` in `python/`), then continue the review of the docs-c diff (`git diff 11ba1b40 HEAD`).
