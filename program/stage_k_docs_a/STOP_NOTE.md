# Stage K docs lane A: stop note

Branch `k-v1-docs-a` (cut from main 11ba1b40). Files owned: COOKBOOK.md, docs/getting-started/ (tutorials), docs/developer-guides/.

## Done
- Tutorial 59, FRTB IMA from PLA to capital (`docs/getting-started/tutorial-59-frtb-ima-pla-to-capital.md`), indexed in `docs/getting-started/README.md`; `tools/check_tutorial.py --lang python` passes on it (12 lines).

- COOKBOOK section "Stage K wave 2 capital and xVA recipes": RRAO, securitisation DRC, CTP DRC, SA-CVA with hedges, large exposures, wrong-way CVA (all outputs observed 2026-11-21, Python build).
- Tutorial 60, reading a soak run (`docs/getting-started/tutorial-60-read-a-soak-run.md`): K-6 rule on the committed CSVs, MISS and planted-leak miss stated; check passes (3 lines).
- Tutorial 61, K-5 snapshots and the hedge (`docs/getting-started/tutorial-61-snapshots-and-hedge.md`); check passes (6 lines).
- RFET recipe (dates moved to 2027-2028) in the wave 2 section.
- COOKBOOK section "Stage K platform recipes": feed fixture round trip (17 of 17, 39 of 39), end-of-day rehearsal with planted EXPLAIN and HOLDOUT, soak verdict reread (recorded MISS stated).

## Next, in order
1. Optional: developer guide on writing a stage K tutorial (Step 1 stdlib, Step 2 library, tutorial:only python).
2. Gaps left: IMA DRC model not implemented, K-3 container round trips need Docker (not run).

## How to resume
Python build on Windows: Smart App Control blocks the `quantforge` exe, so use `uv run --locked --project python python -m quantforge_core.cli.main batch`. No WSL.
