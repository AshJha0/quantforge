# Stage K docs lane A: stop note

Branch `k-v1-docs-a` (cut from main 11ba1b40). Files owned: COOKBOOK.md, docs/getting-started/ (tutorials), docs/developer-guides/.

## Done
- Tutorial 59, FRTB IMA from PLA to capital (`docs/getting-started/tutorial-59-frtb-ima-pla-to-capital.md`), indexed in `docs/getting-started/README.md`; `tools/check_tutorial.py --lang python` passes on it (12 lines).

- COOKBOOK section "Stage K wave 2 capital and xVA recipes": RRAO, securitisation DRC, CTP DRC, SA-CVA with hedges, large exposures, wrong-way CVA (all outputs observed 2026-11-21, Python build).
- Tutorial 60, reading a soak run (`docs/getting-started/tutorial-60-read-a-soak-run.md`): K-6 rule on the committed CSVs, MISS and planted-leak miss stated; check passes (3 lines).
- Tutorial 61, K-5 snapshots and the hedge (`docs/getting-started/tutorial-61-snapshots-and-hedge.md`); check passes (6 lines).
- RFET recipe (dates moved to 2027-2028) in the wave 2 section.
- COOKBOOK section "Stage K platform recipes": feed fixture round trip (17 of 17, 39 of 39), end-of-day rehearsal with planted EXPLAIN and HOLDOUT, soak verdict reread (recorded MISS stated).

## Round 2 (coordinator, 2026-11-21)
- Done: `tools/check_cookbook.py` (runs COOKBOOK bash blocks marked `cookbook:run` and checks the strings in the following `cookbook:expect` comment); 16 recipes marked. Commands: `python tools/check_cookbook.py` (16 of 16 match, about 17 s on the laptop) and `python tools/test_check_cookbook.py` (9 tests). Not wired into any workflow.

## Next, in order
1. DRC tutorial (next free number, 62), python-only.
2. Developer guide docs/developer-guides/adding-an-operation.md.
3. If time: wrong-way CVA tutorial.

## How to resume
Python build on Windows: Smart App Control blocks the `quantforge` exe, so use `uv run --locked --project python python -m quantforge_core.cli.main batch`. No WSL.
