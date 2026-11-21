# Stop note: lane k-v1-claims (K-9 review part 1, documentation side), 2026-11-20

Branch `k-v1-claims`, off `k-v1` at 146102d2. Record of the findings: `STAGE_K_K9_REVIEW_PART1.md` in the plan repository. Evidence class of each line: read (from the repository, `gh run list` or run logs) unless stated.

| Finding | Verified? | State | What changed |
|---|---|---|---|
| 1 (wording and guard; code side is lane `k-v1-rev1`) | Holds. Fuzz on main failed on 2026-11-09, 2026-11-13 (two manual runs) and 2026-11-16 (C++ UB `hedging.cpp:1033`, a 20 s timeout, Rust `E_CONVERGENCE`) | done | README, CHANGELOG 0.9.0 and `docs/releases/v0.9.0.md` corrected; known-issues rows K9-1a (fuzz), K9-1b (`daily-workflows.yml` red 2026-11-19: NY Fed SOFR body not JSON) and K9-1c (`mutation-stage.yml` red 2026-11-15); new `tools/check_scheduled_runs.py` (self-test with planted faults) in `repo-gates` with `actions: read` |
| 2 | Holds (H-9 targets and MISS, stage I timings) | done | README latency bullet: targets exist, missed on a laptop, no latency claim |
| 3 | Holds: no current figure was published | done | CI log lines of coverage run 44791215671 (head 146102d2) stored in `benchmarks/results/coverage/coverage-ci-2026-11-20.json`; `docs/results.md` table generated from it; R1/R2 figures labelled historical in ROADMAP |
| 4 | Holds (stage A 4,223; sweeps 3,756) | done | `tools/case_figures.py`: count without sweeps (4,248), per-stage evidence-class table, README and golden README blocks under `--check` |
| 5 | Holds, and wider: 2 `sorx_h` cases are also the Python build's output | done | Exception stated at principle 5 (README) and in `datasets/golden/README.md`; the 9 cases tagged in `docs/case-figures.md` |
| 6 | Holds | done | "Outside-checked" and "audit" defined in README, `docs/results.md`, GLOSSARY ("Words that qualify a claim"); first mentions in the status block and known-issues say AI |
| 9 | Holds (62.2% counted error cases) | done | One definition `outside_pair()` used by README block, results page and site home; ARCHITECTURE, LEARN, GLOSSARY, model inventory, diagram note the old figure |
| 10 | Holds | done | README cut to current state; stage history moved unchanged to ROADMAP "Stage history"; only badges and generated rows exceed about 600 characters |
| 11 | Holds | done | Sampling, Wilson bounds and own equivalence judgements stated in README and results page |
| 14 | Holds | done | Golden README counts generated (`golden-counts` block, `--check`) |
| 15 | Holds | done | `daily-workflows.yml` stale comments fixed; `curve-daily.yml` and `paper-ledger.yml` keep the tolerance and print `::warning::`; triggers, schedules and recording logic unchanged |
| 16 | Holds | done | LEARN, tutorials 4 and 19, model inventory (and generated m11 report) say "ISDA-standard-model conventions, checked against QuantLib"; citations of the document title are unchanged |
| 17 | Holds | done | "Re-verified by" column on the Open and Closed tables of `docs/known-issues.md`; most say "not recorded" |
| 18 | Holds (`lazy import`, PEP 810) | done | Quick start states Python 3.15 exactly and why |
| 20 | Holds | done | SECURITY.md rewritten; `java25/.jqwik-database` removed and ignored (nothing referenced it) |

Untested until CI: `check_scheduled_runs.py` with the job's GITHUB_TOKEN (run locally with the `gh` token); the `::warning::` lines in the two daily workflows. Not done: diagnosing K9-1b and the four failed jobs of K9-1c; the three red workflows stay red until fixed (the guard passes because each has a row).
