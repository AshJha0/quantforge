# R1 docs to do

Closed in the final docs pass on `r1-docs`, after merging `r1` at `3f5d97d` (2026-11-07). Every lane item below now has its text in the docs named.

| Lane item | Where it went |
|---|---|
| Edge-case register | `README.md` R1 list, `ROADMAP.md` R1 table, `LEARN.md` "Validate and backtest", `ARCHITECTURE.md` |
| Model inventory | Same places |
| Calendar provenance, R1-6 | `LEARN.md` stage A, `README.md` and `CHANGELOG.md` known issues |
| Recorder | `COOKBOOK.md` "Record public data", `ARCHITECTURE.md`, `docs/diagrams/README.md` |
| Conformance matrix, WSL C++ | `README.md` status, `ROADMAP.md` |
| Workflows (a) and (c) | `COOKBOOK.md` "Run the daily workflows", `ARCHITECTURE.md`, diagrams |
| Targets, mutation report | `README.md`, `ROADMAP.md`, `CHANGELOG.md` |
| Coverage | `README.md`, `ROADMAP.md`, `CHANGELOG.md` |
| Batch mode builds | `LEARN.md`, `COOKBOOK.md`, `README.md` |

Left for tag time:
- Done 2026-11-07: CHANGELOG dated, "not yet tagged" removed, versions bumped to 0.4.1.
- After the push, record the first results of the cross-platform matrix, the stage D mutation report, the recorder and the daily workflows, and replace "first run after push" wherever it appears.
- Rerun Java and C++ through `runner.py` and `batch_check.py` on the tagged commit; this pass reran only Rust and Python.
