# R6 evidence lane hand-over (branch `r6-evidence`)

Lane: evidence (R6-12 check, R6-13, R6-14, R6-15, R6-16, R6-18 hygiene). Base `e387d29` (v0.8.0). Updated 2026-11-12. Nothing is pushed. No long runs are still going.

## Review findings: reproduced or not

| Finding | Claim | Result | How |
|---|---|---|---|
| 2 | 7,413 ok, 5,008 error, 1,257 any, 1,257 same_as | **reproduced exactly** (14,935 total) | count of `expected.status` over `datasets/golden/**` |
| 5 | `plan_matrix.py --stage F` / `--stage I` return an empty matrix | **reproduced** | both printed `matrix={"include": []}`, `any=false` at e387d29 |
| 6 | Stage I: 164 of 278 counted are wave 5; 114 of 278 (41%) without | **reproduced** from `oracle/outside_register_i.json` (wave 5 counted 50+35+30+20+29 = 164; non-wave-5 counted 114 of 278) | |
| 6 | Stage F 225 of 525 (42.9%), not 51.4% | **reproduced**. `outside_f.py` prints 225 / 525 = 42.9% | local uv run |
| 6 | 134 of 225 F entries are scipy or numpy | **not reproduced as stated**: 151 of 225 carry a SCIPY or NUMPY convention row (QUAD 17, EIGH 24, QUANTILE 19, NORM 10, LSTSQ 24, BINOM 20, CHI2 37). The direction holds | `tools/outside_shares.py` |
| 6 | Stage G 57.4% | **reproduced** (338 of 589 in the register); 56.4% under D6 (exposure_g CVA reclassed as reimplementation) | |
| 15 | Required check names shared by several workflows | **reproduced**. `tools/check_job_names.py` on the v0.8.0 workflows: `java`, `cpp`, `python`, `rust` each used by 5 jobs, `plan` by 2, `test` by 3 | |
| 15 | `baseline.json` empty | **reproduced** (`"machine": "unset", "results": {}`) | |
| 15 | v0.6.0 and v0.7.0 releases have no assets | **reproduced for both** (0 assets each; v0.8.0 has 7) | `gh release view` |
| 15 | `calendar-expiry` red by design | **reproduced** (USGS confirmed only through 2027-01-01) | `check_calendar_provenance.py` |
| 15 | Fuzz failure, Java `Bonds.java:262` | not taken by this lane (language lanes) | |
| 16 | E9 not done (`determinism.md:35` says planned) | **reproduced** | |
| 16 | G4 stage-letter names remain in three languages | **reproduced**: C++, Java and Python. Rust has none. List below | `git ls-files` |
| low | tracked `tools/.coverage`; secret scanning off; numpy missing from notices; ORE and ISDA licences "not verified" | **all reproduced** (secret scanning and push protection `disabled` via the API) | |

## Items

| Item | Status | Evidence | Needs CI on a pushed branch |
|---|---|---|---|
| R6-12 check | done. `tools/check_docs_status.py` fails on a count of 1,000 or more "cases" with no class on the line (`program/` excluded). **It now flags 52 lines** (README 10, CHANGELOG 12, LEARN 5, ARCHITECTURE 5, ROADMAP 4, and others): the docs lane rewrites them. Until those rewrites merge, `repo-gates` fails on this branch alone | `python tools/check_docs_status.py` | `repo-gates` green after the docs lane merges |
| R6-13 | built. `tools/outside_shares.py` applies the D6 classes per case (D, E, F) or per suite (G, I), uses all cases as the denominator (ruling I-2), shows sweeps (F `e1_*`, I `*5_i`) separately, reports per stage and per operation, with the library named per entry. It writes `oracle/OUTSIDE_SHARES.{json,md}`; `--check` diffs them, checks each G and I register suite total against its golden, and fails a stage under 60% that has no dated plan. `oracle-coverage.yml` (job `oracle-outside-registers`) now regenerates the D, E-A, E-B and F registers and diffs every `outside_register*.json`. A local regeneration of E-A, E-B and F left the registers byte-identical (about 30 s). Planted-fault test: `tools/test_outside_shares.py` (suite missing from the register, total mismatch, floor without a plan, CHI2 classed as reimplementation) | `oracle/OUTSIDE_SHARES.md` | `Outside-oracle coverage` |
| R6-13 open | G and I registers hold suite counts only. Per-case registers and regenerators for G and I belong to the spec and oracle lane (the generators `gen_stage_g_*`, `gen_stage_i_*` write them). The suite-level rulings in `SUITE_CLASS` need a second reviewer | | |
| R6-14 | built. `stages.json` now has stages A (4 modules), F (6), G (6) and I (5), alongside D and E. Matrices: A 20 jobs, F 30, G 28, I 25; `--stage ALL` gives 189 (under the 256 matrix limit). The weekly run is `ALL`, with a fresh seed (the run number) and 40 mutants per module. `stage_report.py` reports a 95% Wilson interval and gates on a point estimate of at least 80% and a lower bound of at least 65%, with exceptions only through a countersigned `reasons.json` entry. `plan_matrix.py` exits 1 on an empty full-stage matrix. `check_stages.py` checks every target against a file and every suite against a golden. Equivalents lists exist for all four languages (`equivalents-{cpp,java,python,rust}.md`), each with a second-reviewer column. Planted-fault test: `conformance/mutation/test_gates.py` (17 checks) | `python conformance/mutation/test_gates.py` | `Mutation by stage`, dispatched with `stage=ALL` (or A, F, G, I one at a time) and `gate=true`. Stage A is re-measured by that run; no local mutation run was made |
| R6-15 job names | done. Every job is uniquely named; `.github/required-checks.json` lists 15 required checks; `tools/check_job_names.py` (in `repo-gates`) fails on 21 problems against the v0.8.0 workflows and on 0 now | `R6_OWNER_SETTINGS.md` in the plan folder | the new names must appear once on main before the owner edits the ruleset |
| R6-15 cross-platform | done. `cross-platform.yml` now also runs on PRs touching `*/src`, the goldens or the runner, over every golden | | `Cross-platform conformance` green on all 12 legs (never green for stages E to I) |
| R6-15 E9 | built. `datasets/golden/core/mc_hash.json` (6 bit-exact cases: 4,096 draws, seed 20261112, streams 0, 1, 7, integers and uniforms), `oracle/MC_HASH_E9.json`, `oracle/python/gen_mc_hash.py`, `tools/check_mc_hash.py --self-test` (catches a one-ulp change). Python conformance passes 6 of 6 locally. **Adds 6 cases: the total becomes 14,941** (value-checked 7,419) | `docs/determinism.md` | `Conformance` (Java, C++, Rust) and `Cross-platform conformance` |
| R6-15 bench | gate made live. `bench_gate.py --require-baseline` on every non-PR run; it fails while no baseline exists for the runner, which shows the gate is no longer empty. The existing job already shows an injected slowdown failing against a same-job baseline. **Still needed:** dispatch `Microbenchmarks` on the branch, download the `bench-results-*` artifacts, run `python tools/bench_gate.py --current DIR --write-baseline --machine github-ubuntu-24.04`, commit `benchmarks/micro/baseline.json`; then the stored-baseline gate runs | | `Microbenchmarks` (expected red on push and dispatch until the baseline is committed) |
| R6-15 calendar | done. `awaiting_publication_until` in `datasets/calendar_provenance.json` (USGS: 2027-01-31). Amber (exit 0, `::warning::`) until that date, red after; checked with `--today 2027-02-01` | | `Calendar expiry` |
| R6-15 releases | note written: `program/R6_RELEASE_ANNOTATIONS.md` (text and `gh release edit` steps; owner or coordinator applies) | | none |
| R6-16 | CHANGELOG "0.8.1 ... Corrections of record" for E9, G4, G2, A5 and Q3b, each delivered, partial or not delivered, with paths | `CHANGELOG.md` | none |
| R6-18 | done. `tools/.coverage` untracked and ignored; a NumPy section in `THIRD_PARTY_NOTICES.md`; the ORE `license.txt` read through the GitHub API and recorded (modified BSD 3-clause); the ISDA CDS and SIMM rows restated (not used, and why). `oracle/LICENCES.md` has no "not verified" line. Secret scanning is with the owner | `oracle/LICENCES.md` | none |

## True outside shares under D6 (all cases, error cases included, no sweeps)

| Stage | library-object | library-primitive | reimplementation | none | Share | With sweeps |
|---|---:|---:|---:|---:|---:|---:|
| D | 419 | 0 | 0 | 235 | 64.1% | 64.1% |
| E | 557 | 0 | 0 | 338 | 62.2% | 62.2% |
| F | 71 | 94 | 57 | 303 | 31.4% | 2.7% (E1 sweep, 5,535 cases) |
| G | 279 | 53 | 6 | 251 | 56.4% | 56.4% |
| I | 0 | 102 | 12 | 164 | 36.7% | 60.1% |

F, G and I are under 60%. Each has a dated plan (2027-01-31, stage J close-out J-10) recorded in `tools/outside_shares.py` `PLANS`.

## For the language lanes (G4 rename, via the coordinator)

Stage-letter or wave module names at v0.8.0: C++ `cpp26/src/core/risk_f3.cpp`, `risk_f4.cpp`, `hedging_w2.cpp`, `hedging_w3.cpp`, `hedging_w4.cpp`, with `cpp26/include/quantforge/core/risk_f3.hpp` and `risk_f4.hpp`; Java `cli/OpsHedgeI.java`, `OpsRatesG.java`, `OpsRiskF.java`, `OpsWave2b.java`; Python `quantforge_core/cli/ops_stage_g2.py`. Rust: none. **When you rename one, update `conformance/mutation/stages.json`**. `check_stages.py` (in `repo-gates`) fails on a target that matches no file. Stages F and I currently name `risk_f3.cpp`, `risk_f4.cpp` and `hedging_w2.cpp` to `hedging_w4.cpp`.

## Coordinator notes

- Merge with the docs lane before expecting `repo-gates` green (R6-12 check).
- Case totals change to 14,941 with E9. Tell the docs lane.
- `mutation-stage.yml` no longer has a PR paths filter, so its plan job runs on every PR in seconds.

## R6-26: per-file 90% coverage gate (added 2026-11-12, coordinator request)

- **Reproduced:** before R6 the only per-module coverage gate read `conformance/quality/stage_e.json`, with 8 stage E modules at 85%. Every other stage was covered only by the whole-language floors. `coverage-stage.yml` ran on PRs only when listed paths changed.
- **Built:** `tools/quality_gate.py --per-file` fails on any library source file below 90% line coverage, in any stage and any of the four report formats. Exceptions go in `conformance/quality/coverage_allow.json`; an entry counts only if it has a reason. The list is empty today: the language lanes add the two entry-point files with reasons if they need to. The whole-language floors (`floors.json`: Python 0.96, Java 0.96, Rust 0.94, C++ 0.95) are unchanged and still enforced by `--floor`. All four `coverage-stage-*` jobs now pass `--floor --per-file`. The workflow runs on every PR, and the four job names are in `.github/required-checks.json` and `R6_OWNER_SETTINGS.md`.
- **Planted fault:** `tools/test_coverage_gate.py` (in `repo-gates`, 19 checks). A planted 50% file fails in all four formats. An allow-list entry with a reason clears it; an entry without a reason does not. The end-to-end exit codes are 1 for the planted file and 0 when it is covered.
- **Files below 90% today: not measured locally.** There is no `mvn` and no `cargo-llvm-cov` on this machine. A local Python coverage run of the full suite was cut off at 18% after about 28 minutes and produced no data. The lists come from the first CI run of `Coverage by stage` on the pushed branch: jobs `coverage-stage-python`, `coverage-stage-java`, `coverage-stage-rust` and `coverage-stage-cpp` print one `BELOW <path>: covered/total` line per file. Those jobs are expected to be red until the language lanes add tests. Copy the `BELOW` lines into this section for the lanes.

## Status check 2026-11-12 (end of lane, head after b9b2b3c)

Local lightweight checks re-run on this head (no language builds, no mutation campaigns):

| Item | Status | Evidence path | Needs first CI run |
|---|---|---|---|
| R6-12 check | done; red until docs lane merges (52 lines) | `tools/check_docs_status.py` (exit 1 today, by design) | `repo-gates` after docs merge |
| R6-13 registers + floor | done; floor now on value-checked cases (owner 2026-11-12). D, E, G (71.7%), I (66.7%) pass. **Stage F 39.6% fails the floor**: `--check` exits 1. Not fixable in this lane: needs outside checks / independent re-derivation on CDS index option, FRTB SA, book lifecycle, traffic light (spec and oracle lane) | `oracle/OUTSIDE_SHARES.md`, `tools/test_outside_shares.py` (pass) | `Outside-oracle coverage` (red until stage F is raised) |
| R6-14 mutation | done; matrices non-empty: A 20, F 30, G 28, I 25, ALL 189; planted faults caught | `conformance/mutation/test_gates.py` (pass), `conformance/mutation/check_stages.py` (0 problems) | `Mutation by stage`, `stage=ALL gate=true` (fresh seed = run number, 40 per module) |
| R6-15 job names | done; 54 jobs, 0 problems; 15 required in `.github/required-checks.json` | `tools/check_job_names.py` | names must exist once on main before ruleset edit |
| R6-15 cross-platform | done | `.github/workflows/cross-platform.yml` | `Cross-platform conformance`, 12 legs |
| R6-15 bench baseline | gate live; baseline needs a runner artifact | `tools/bench_gate.py --require-baseline` | dispatch `Microbenchmarks`, then `--write-baseline`, commit |
| R6-15 E9 | done; self-test catches a one-ulp change | `tools/check_mc_hash.py --self-test`, `datasets/golden/core/mc_hash.json` | `Conformance` Java/C++/Rust |
| R6-16 | done (G4 renames with language lanes) | `CHANGELOG.md` | none |
| R6-26 | gate done; planted 50% file fails in all four formats | `tools/test_coverage_gate.py` (pass) | `Coverage by stage` x4: copy `BELOW` lines to lanes |
