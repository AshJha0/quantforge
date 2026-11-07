# R1 docs to do

Docs owed when the other R1 lanes land. The docs pass on `r1-docs` (2026-11-07) did everything that needed only what was already on `r1`. Each item names where the text goes and what must be checked before it is written. Every number is checked against the repo or a fresh run, with its evidence class.

| Lane item | Where the docs go | What to write and check |
|---|---|---|
| Edge-case register | `ROADMAP.md` R1 table; `LEARN.md` "Validate and backtest"; `CONTRIBUTING.md` checklist | Link the register; count of entries and how many are pinned by a fixture. Contributors add an entry for every new boundary case |
| Model inventory | `README.md` Status; `ARCHITECTURE.md` R1 section; `GLOSSARY.md` | Link it; count of models by evidence class and how many have an outside oracle. Make sure README's "several suites have no outside oracle" matches the inventory |
| Calendar provenance | `LEARN.md` stage A; `THIRD_PARTY_NOTICES.md` if a source needs a notice | Source and date for each calendar; say which calendars are hand-built |
| Recorder | `README.md` "The recorder is built but not scheduled" bullet; `COOKBOOK.md` "Record public data"; `tools/README.md` is the infra lane's | Replace the bullet with what is scheduled, when it first ran, and where records live. Run the command the Cookbook shows |
| Conformance matrix | `README.md` Status; `conformance/README.md`; `docs/developer-guides/test-infrastructure.md` | Link the matrix; state which toolchains ran locally and which in CI, with dates. Drop "Clang relies on CI" if the matrix shows it ran |
| Workflows (a) and (c) | `COOKBOOK.md` new recipes; `LEARN.md` worked examples; `ROADMAP.md` | Plain idea, formal statement, worked example from a real run. Label the data observed or synthetic |
| Targets (`benchmarks/targets.md`) | `COOKBOOK.md` Batch mode; `README.md` "only benchmark" bullet; `benchmarks/README.md` | Not on `r1` at the time of this pass. Quote targets only with hardware, workload and method. The R1 line is Python fuzz at 50,000 inputs a minute or more in batch mode |
| Mutation report | `README.md` Status; `docs/developer-guides/test-infrastructure.md` | Mutation score per language, date and commit. Say what survived |
| Batch mode builds | `COOKBOOK.md`, `LEARN.md`, `README.md`, `CHANGELOG.md` | Today they say each v0.4 build passes 14 of 19 streams. When the language lanes land, rerun `batch_check.py` per language, update the counts and add a `--timings` example with real output |
| Citations lane | All top-level docs | Merge its sources in; do not overwrite them with this pass's wording |

Also at the end:
- Date the CHANGELOG 0.4.1 section and update the site note's "Version 0.4.0" in `tools/site_home.html`.
- `git grep -in interview` must return nothing.
- Rerun the relative-link check over the top-level docs, `docs/` and `program/`.
