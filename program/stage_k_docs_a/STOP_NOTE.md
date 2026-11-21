# Stage K docs lane A: stop note

Branch `k-v1-docs-a` (cut from main 11ba1b40). Files owned: COOKBOOK.md, docs/getting-started/ (tutorials), docs/developer-guides/.

## Done
- Tutorial 59, FRTB IMA from PLA to capital (`docs/getting-started/tutorial-59-frtb-ima-pla-to-capital.md`), indexed in `docs/getting-started/README.md`; `tools/check_tutorial.py --lang python` passes on it (12 lines).

## Next, in order
1. Cookbook recipes for wave 2 operations with no recipe: RRAO, DRC CTP and securitisation, SA-CVA, large exposures, RFET.
2. Wrong-way-risk CVA (`xva.wwr.cva_hw`) recipe.
3. K-6 end-of-day rehearsal and capacity tools; K-5 snapshots; K-3 adapters and simulated feed codecs (developer guides).

## How to resume
Python build on Windows: Smart App Control blocks the `quantforge` exe, so use `uv run --locked --project python python -m quantforge_core.cli.main batch`. No WSL.
