# Stage K docs lane A: stop note

Branch `k-v1-docs-a` (cut from main 11ba1b40). Files owned: COOKBOOK.md, docs/getting-started/ (tutorials), docs/developer-guides/.

## Done
- Tutorial 59, FRTB IMA from PLA to capital (`docs/getting-started/tutorial-59-frtb-ima-pla-to-capital.md`), indexed in `docs/getting-started/README.md`; `tools/check_tutorial.py --lang python` passes on it (12 lines).

- COOKBOOK section "Stage K wave 2 capital and xVA recipes": RRAO, securitisation DRC, CTP DRC, SA-CVA with hedges, large exposures, wrong-way CVA (all outputs observed 2026-11-21, Python build).
- Tutorial 60, reading a soak run (`docs/getting-started/tutorial-60-read-a-soak-run.md`): K-6 rule on the committed CSVs, MISS and planted-leak miss stated; check passes (3 lines).

## Next, in order
1. K-6 end-of-day rehearsal and capacity tools; K-5 snapshots; K-3 adapters and simulated feed codecs (developer guides).

## How to resume
Python build on Windows: Smart App Control blocks the `quantforge` exe, so use `uv run --locked --project python python -m quantforge_core.cli.main batch`. No WSL.
