# QuantForge

[![Python](https://github.com/AshJha0/quantforge/actions/workflows/python.yml/badge.svg)](https://github.com/AshJha0/quantforge/actions/workflows/python.yml) [![Rust](https://github.com/AshJha0/quantforge/actions/workflows/rust.yml/badge.svg)](https://github.com/AshJha0/quantforge/actions/workflows/rust.yml) [![Java 25](https://github.com/AshJha0/quantforge/actions/workflows/java25.yml/badge.svg)](https://github.com/AshJha0/quantforge/actions/workflows/java25.yml) [![C++26](https://github.com/AshJha0/quantforge/actions/workflows/cpp26.yml/badge.svg)](https://github.com/AshJha0/quantforge/actions/workflows/cpp26.yml) [![Docs](https://github.com/AshJha0/quantforge/actions/workflows/docs.yml/badge.svg)](https://ashjha0.github.io/quantforge/) [![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](https://github.com/AshJha0/quantforge/blob/main/LICENSE)

QuantForge is a quantitative finance library written four times, in Java, C++, Python and Rust, from one set of specifications, and checked against expected results that come from a separate oracle. It covers curves, pricing, volatility, risk, hedging, portfolio construction, research statistics, and execution and microstructure on simulated venues. It is a one-person, zero-spend project; validation is self-assessment.

**Quick start.** With [uv](https://docs.astral.sh/uv/) installed, from the repository root. The Python build needs Python 3.15 exactly: `python/pyproject.toml` pins `requires-python = "==3.15.*"` because the code uses `lazy import` (PEP 810, new in 3.15) and unparenthesised `except A, B:` (PEP 758, new in 3.14), so it does not run on 3.14 or earlier; uv fetches 3.15 on the first run.

<!-- quickstart:begin -->
```bash
uv run --project python quantforge batch < examples/batch.jsonl
```

```json
{"schema_version":"1.0","case_id":"example-daycount","status":"ok","outputs":{"year_fraction":0.5055555555555555},"diagnostics":{}}
{"schema_version":"1.0","case_id":"example-discount","status":"ok","outputs":{"discount_factor":0.9048374180359595},"diagnostics":{}}
{"schema_version":"1.0","case_id":"example-root","status":"ok","outputs":{"root":2.094551481542327},"diagnostics":{"iterations":7,"residual":3.552713678800501e-15,"termination":"X_TOL"}}
{"schema_version":"1.0","case_id":"example-error","status":"error","error":{"code":"E_DATE_ORDER","message":"end is before start","field":"end"},"diagnostics":{}}
```
<!-- quickstart:end -->

That is an ACT/360 year fraction, a discount factor, a root find and a refused input, printed by the Python build on Windows (*observed*, 2026-11-09). `docs.yml` runs the block on every pull request (`tools/check_quickstart.py`). Docs site: <https://ashjha0.github.io/quantforge/>. First tutorial: [price your first swap](docs/getting-started/tutorial-1-swap.md).

## Status at a glance

<!-- status-glance:begin -->

Generated from `tools/site_facts.json` and counts from the tree by `tools/status_glance.py`; do not edit by hand.

| | |
|---|---|
| **Release** | Latest release v0.10.0, stage H: microstructure and execution on simulated venues, released 2026-11-19. On main, unreleased: stage K round 1 (platform pieces with the findings of a different-model AI audit answered, intraday risk, SA-CCR, backtesting, daily jobs), merged to main by 2026-11-20 (pull requests #58 to #64: wave 1, SA-CCR, backtesting, daily jobs, wave 2 capital operations, K-3 adapters, K-5 snapshots, K-6 soak harness, K-7 release evidence), not tagged; released with v1.0.0 (owner decision 2026-11-20: there is no v0.10.1 tag). Next: the v1.0.0 release, which closes stage K (no date set; the version string is bumped then); open items in docs/known-issues.md. |
| **Built** | Stages A to J, plus R6, in Java 25, C++26, Python 3.15, Rust 2024: 387 CLI operations in the generated name map, CLI contract 1.17.0. Status rung Implemented; nothing is claimed as Validated, Benchmarked or Operationally tested. |
| **Checked** | 8,099 value-checked golden cases (4,343 without the 3,756 stage A convention sweeps), plus 5,894 error and 2,554 invariance cases (16,547 in all, docs/case-figures.md), sent to each build by the neutral runner. Stage H outside share 78.0% (160 of 205 value cases, oracle/OUTSIDE_SHARES.md), by blind re-derivation or printed paper figures, no library. |
| **Real data** | One crypto venue's public order book (Kraken L2, recorded locally, aggregates and hashes only; crypto venue; not equities or rates). Public rates and curve sources hashed daily into the forward log. US Treasury par-yield moves in the stage J shock library. Real-data studies so far: the three R3 holdout runs (null) and the H-1 crypto pilot (no conclusions). |
| **Simulated** | Every venue: the lit engine, dark pool, router, auction, FX dealer venue and Treasury futures venue. Paper trading fills come from those simulators. Golden-case inputs are synthetic, except the stage J shock-library cases (`scen_j`), which carry published US Treasury par yields. No live order is ever placed. |
| **Missed** | H-9 workload R (recorded 6-hour crypto window, 2026-11-18/19): correctness passes, timing is a recorded MISS at p99 and p99.9 in every language (local laptop, not the acceptance machine). H-9 R2 not obtained: the second recording attempt needed one unbroken 6-hour session, and all 30 sessions on 2026-11-19 and 2026-11-20 ended before hour 6 (websocket keepalive ping timeouts, with whole-connection stalls of 50 to 107 s seen before drops; cause not established: network path or machine load); the owner ended the attempt and dropped H-9 R2 on 2026-11-20; targets and rules stay as fixed before any timing (HR-130 to HR-134); the 2026-11-19 workload R result remains a recorded MISS. Stage K item K-8 misses its acceptance for lifting the R6 use restriction: the second-order Bermudan ladder method passes acceptance 1 to 3 at 201/100 only on the three cases it was developed on (in-sample), misses 1% at 101/50 on two of them, and missed its out-of-sample acceptance (KR-260, run 2026-11-20: 53 of 120 cases within 1% against 114 needed; a recorded MISS); the use restriction is kept for both methods (KR-113, KR-260), and the threshold is not loosened. K-6 flat-memory soak: the 145-minute Python soak on the local laptop (not the acceptance machine) is a recorded MISS on slope (2.32 MiB/h against 1 MiB/h); on the GitHub runner (run 44824197236, 2026-11-20/21, not the acceptance machine) C++, Rust and Python on Linux are recorded MISSes and Java passes; cause not established. K-2 (20 recorded paper-ledger trading days) is not met: at most 1 of 20 recorded trading days (one ledger row, for 2026-11-20, anchored at Bitcoin heights 976796 and 976809; the verifier's count needs those two block headers, which were not fetched, so it reports no count yet; verify_ledger.py verify --no-cli with the anchors and the forward log: ok, records 2, recorded_trading_days null; measured 2026-11-21), and v1.0.0 does not wait for it (owner decision 2026-11-20). KR-227 (pa11y AA on every page, light and dark) is not met: the every-page jobs are held on a branch until every page passes. Stage K is merged to main (2026-11-20, pull requests #58 to #64), not tagged, and is released with v1.0.0; its open items are in docs/known-issues.md. |
| **No outside check** | 45 of the 205 stage H value cases; the stage J curves-lane and hedge-fix value cases; the stage K value cases not counted in oracle/OUTSIDE_SHARES.md (ruling KR-250); DSR, PSR, PBO and the Z2 backtest (hand cases and printed examples only); every error case. Validation is self-assessment, with no second review (owner decision 2026-11-18). |

<!-- status-glance:end -->

Every stage's tests and results, misses first: [docs/results.md](docs/results.md). Open issues: [docs/known-issues.md](docs/known-issues.md). Stage history: [ROADMAP.md](ROADMAP.md#stage-history-moved-from-the-readme-on-2026-11-20) and [CHANGELOG.md](CHANGELOG.md).

## Headline figures

<!-- case-figures:begin -->

Generated by `tools/case_figures.py --write` from the golden files and `oracle/OUTSIDE_SHARES.json`; do not edit; `repo-gates` runs `--check`.

**8,099 value-checked golden cases**: each build must return the oracle's numbers within a stated tolerance. 3,756 of them are the stage A convention sweeps (generated grids of day counts, calendars and compounding), so **4,343 without those sweeps**.

Besides them, 5,910 error cases check only that a bad input is refused with the right code, and 2,554 invariance cases (1,277 pairs) check that two related inputs get the same answer, with no expected number: 16,563 cases of every class in all. The value-checked count leads because a build that refused every input would pass all the error cases and none of the value-checked ones.

**Outside-checked share per stage** (value-checked cases counted under rule D6, over the share table's value-checked cases without generated sweeps; the same figures as [docs/results.md](docs/results.md)): D 451 of 526 (85.7%), E 557 of 710 (78.5%), F 355 of 417 (85.1%), G 359 of 456 (78.7%), I 102 of 153 (66.7%), J 143 of 215 (66.5%), H 160 of 205 (78.0%), K 171 of 218 (78.4%). Stages A to C, R2 and R6 are not in the share table.

**Evidence classes of the value-checked cases**, read from their `verified_by` labels, each case in its strongest class: outside library 5,026, printed published figure 81, blind re-derivation by a second AI lane 254, own mpmath oracle 1,543, own float64 or exact oracle 884, reference-computed 134, hand-derived only 168, and 9 whose expected values are a build's own output (`sorx_h-0001`, `sorx_h-0002`, `k8_k-0001`, `k8_k-0002`, `k8_k-0003`, `k8_k-0004`, `k8_k-0005`, `k8_k-0006`, `k8_k-0007`). Per stage in [docs/case-figures.md](docs/case-figures.md#evidence-classes-per-stage).

<!-- case-figures:end -->

Stage K's share is by blind re-derivation only, with no library: <!-- generated:stage-k-total -->171 of 218 value cases (78.4%)<!-- /generated -->; per item: <!-- generated:stage-k-items -->K-4a 6 of 10 (60.0%), K-4b 4 of 6 (66.7%), K-4c 13 of 14 (92.9%), K-5a 9 of 12 (75.0%), K-8 method 7 of 7 (100.0%), K-8 guard 6 of 6 (100.0%), K-8a 15 of 18 (83.3%), K-8d SA-CCR 12 of 19 (63.2%), K-8e FRTB backtesting 23 of 28 (82.1%), K-8f 23 of 33 (69.7%), K-8g 14 of 21 (66.7%), K-8i 22 of 23 (95.7%), `tlk_k` 17 of 21 (81.0%); every item meets the 60% per-item rule<!-- /generated --> (ruling KR-250; measured by `tools/outside_shares.py`). The K-5a count excludes two recorded mismatches (idr_k-0012, idr_k-0013; `program/STAGE_K_BLIND_K5A_V2.md`).

## Words used here

Each term is defined once here and in [GLOSSARY.md](GLOSSARY.md#words-that-qualify-a-claim).

- **Value-checked case:** a golden case whose expected numbers each build must return within a stated tolerance. Error cases check only the error code; invariance cases check that two related inputs get the same answer.
- **Outside-checked:** a value-checked case whose expected values were reproduced outside the code that produced them, either by an outside library (QuantLib, Strata, ORE, NumPy, SciPy and others) or by a blind re-derivation by a second AI lane. It never means checked by a person: no person has reviewed the work (owner decision 2026-11-18). The share uses one definition everywhere (rule D6; `tools/case_figures.py outside_pair()`).
- **Blind re-derivation:** a second AI lane, run on a different model, derives the answers from the rules and inputs alone, without the expected values; a fixed script compares them (DR-H2). It catches arithmetic and convention slips, not a wrong rule, because both lanes read the same rules.
- **Audit:** a different-model AI audit: an AI model other than the one that wrote the work reads the specs and code and reports findings. Not a person, not an outside firm.
- **Self-assessment:** every check here was designed and run by the project itself (one person and AI lanes), with no second human review.
- **Sampled mutation score:** the share of injected faults (mutants) that the tests catch, on a sample of 40 mutants per module and language on pull requests, so each score carries a Wilson 95% interval. Whether a surviving mutant is equivalent (cannot change any output) is the project's own judgement.
- **Simulated:** produced by the project's own venue simulators, not by a market. Evidence classes on claims: *read*, *recalled*, *measured*, *inferred*.

## What it can and cannot show

On free public data, QuantForge can show correct pricing and risk, curve quality against published curves, and signals on fitted curves tested against preregistered pass rules (`research/preregs`, amended 2026-11-09: one-sided deflated test, 24-trial family, Holm correction; the studies are underpowered and say so).

It cannot show tradable profitability. That needs instrument-level prices, bid and ask, financing and execution data, which cost money; this is a deliberate limit of a zero-spend project. Each limit below is stated once; the open items are in [docs/known-issues.md](docs/known-issues.md).

- **Validation is self-assessment**: no second review (owner decision 2026-11-18). Many golden cases have only hand or replay sources, which can share a misreading with the spec; the evidence class of every value-checked case is counted in [docs/case-figures.md](docs/case-figures.md#evidence-classes-per-stage).
- **Design principle 5 has exceptions.** Seven Bermudan ladder cases (`k8_k`) take their expected values from the Python build under a pinned reference scheme (`oracle/python/gen_stage_k_k8.py` imports the build), and two `sorx_h` cases are the Python build's output kept as an agreement check; a further set of cases is hand-derived. All are tagged in `docs/case-figures.md`.
- **Latency: targets exist and were missed; no latency claim is made.** Stage H fixed latency targets before any timing (`specifications/09-microstructure/low-latency-targets.md`, HR-130 to HR-134). On workload R (a recorded 6-hour crypto window, 2026-11-18/19) correctness passed and timing is a recorded MISS at p99 and p99.9 in every language (H-9; local laptop, not the acceptance machine). The stage I hedge timings (target T6) and the R1 batch targets are laptop measurements too; see "Performance targets missed" below.
- **Risk is a calculator, not a bank's risk system.** VaR, ES, backtests, FRTB sensitivities-based method parts, SA-CCR and the stage K wave 2 capital operations (FRTB default risk charge and residual risk add-on, IMA, BA-CVA and SA-CVA, leverage ratio and large exposures: K-8a, K-8f, K-8g, K-8i; merged to main in pull request #63, 2026-11-20, most of their rulings still PROPOSED) run on synthetic P&L and sensitivities, with no real positions or market history. Securitisation risk weights are not built; the caller supplies them (KR-55, `specifications/06-risk/frtb-drc-rrao.md`).
- **Little market data is used.** Golden inputs are synthetic, except the stage J shock-library cases (`scen_j`, published US Treasury par yields matched to the Federal Reserve H.15 release). Recorded data from one crypto venue's book (crypto venue; not equities or rates) feeds the H-1 pilot and the H-9 timing only. A passing curve case shows the method agrees with its oracle on synthetic quotes, not that it fits a market (`datasets/data-availability.md`).
- **Trading is simulated only.** No live order is ever placed and nothing connects to a market; the venues, router and paper fills are simulated.
- **Citations are only partly opened.** Licensed books (Hull, Clark, O'Kane) are not opened; equation numbers in paywalled papers (Heston 1993, Bates 1996, Merton 1976, Dupire 1994, Carr and Madan 1999) are recalled, not verified (`specifications/stage-e-sources.md`).
- **Outside checks are partial.** Stages A to C, R2 and R6 have no share-table row. Stage E's GARCH, VIX method, Student-t copula, large-pool model, SLV and American FD scheme have no QuantLib object and rest on hand cases and high-precision replicas; stage J's DSR, PSR, PBO and Z2 backtest rest on hand cases and printed examples; every error case is self-checked. Gaps per suite: [`oracle/REPORT.md`](oracle/REPORT.md#stage-d-outside-oracle-coverage-rule-1125), `oracle/OUTSIDE_GAPS_F.md`, `oracle/OUTSIDE_SHARES.md`.

## How it is checked

- **Golden cases through a neutral runner.** `conformance/runner/runner.py` sends every golden case to each build's CLI and compares within the case's tolerance class. Expected values come from `oracle/` (with the exceptions above).
- **Continuous integration.** Each build's workflow runs its unit tests and the golden suites on pull requests and on `main`; `cross-platform.yml` runs Linux, Windows and macOS by four languages (last scheduled run on `main` passed on 2026-11-15, at `a148d0ea`; read with `gh run list`, 2026-11-20). `tools/check_scheduled_runs.py` (in `repo-gates`) fails while a scheduled workflow whose last run on `main` failed has no open row in `docs/known-issues.md`; on 2026-11-21 three are red and listed there (fuzz, stage mutation, K-6 soak); daily workflows ran green on 2026-11-20 (run 44826853145) after the red of 2026-11-19, whose cause is not confirmed, so its row stays open (read with `gh run list`, 2026-11-21).
- **Fuzzing** (`fuzz.yml`, weekly and by hand) damages golden inputs and raw bytes and checks for a clean exit and a known error code. It currently fails on `main`; see Known issues.
- **Mutation testing** (`mutation-stage.yml`, on pull requests and weekly): at least 80% of a 40-mutant sample caught per module and language, with a Wilson 95% lower bound of at least 65%. Scores are sampled and equivalence judgements are the project's own; quoted scores with their Wilson bounds are in [docs/results.md](docs/results.md#mutation-testing).
- **Unit-test line coverage** (`coverage-stage.yml`, on pull requests and weekly): gated by a whole-library floor per language (`conformance/quality/floors.json`) and a 90% per-file rule (`tools/quality_gate.py --per-file`). The figures measured in CI on 2026-11-20 are in [docs/results.md](docs/results.md#unit-test-line-coverage).
- **Documentation gates:** generated figures (`tools/case_figures.py`, `tools/results_page.py`, `tools/status_glance.py`), the known-issues register (`tools/check_known_issues.py`), links and anchors, and a static accessibility check, in `repo-gates.yml` and `docs.yml`.

### Known issues

- **Stage K is merged to main by 2026-11-20 (pull requests #58 to #64), not tagged; it is released with v1.0.0.** The last tag is v0.10.0 (owner decision 2026-11-20: no v0.10.1 tag); the build version string on main reads 0.10.1 until the v1.0.0 bump. What stays open from the audits, and every recorded miss, is in [`docs/known-issues.md`](docs/known-issues.md). Both daily jobs (paper ledger, curve run) are scheduled on main since 2026-11-20 (pull request #59); each has one row so far, for 2026-11-20 (branches `paper-ledger` and `curve-daily`, `ledger/summary.json`, read 2026-11-21). The K-2 count of recorded trading days comes from the ledger verifier, not from these files, and was not run for this page.
- **Fuzzing fails on `main` (open, K9-1a in [`docs/known-issues.md`](docs/known-issues.md)).** Every fuzz run on `main` has failed: 2026-11-09, 2026-11-13 (twice, before the v0.8.3 fixes), 2026-11-16 (scheduled, after them) and 2026-11-20 (run 44815591552, manual, on `c55a224e`). On 2026-11-16 the C++ build hit undefined behaviour at `hedging.cpp:1033` and one 20 s timeout, and the Rust build returned `E_CONVERGENCE`, an error code the contract does not list. On 2026-11-20 C++ and Rust were green and Java and Python each had one new internal-fault finding (read from `gh run view`, 2026-11-21).
- **Earlier text here said fuzzing had not run since v0.8.3; that was wrong.** A fix for the 2026-11-20 findings is in progress on another branch and is not merged; "fuzz clean" is not claimed. The three faults of 2026-11-13 are fixed in v0.8.3 (rulings J-0b.1 to J-0b.3).
- **K-6 soak misses (open, [`docs/known-issues.md`](docs/known-issues.md)).** The flat-memory rule (slope at most 1 MiB/h and range at most 5% of the median after warm-up) is missed by the local Python soak (slope 2.32 MiB/h; local laptop, not the acceptance machine) and, on the GitHub runner (run 44824197236, 2026-11-20/21, not the acceptance machine), by C++ (slope 1.41 MiB/h, SLOPE and RANGE), Rust (slope 1.04 MiB/h, SLOPE and RANGE) and Python on Linux (RANGE); Java passes. The runner's planted-leak check in Python reported `LEAK MISSED`. Cause not established; the rule is unchanged ([capacity](docs/capacity.md)).
- **Mutation gate: Rust `hedge_solvers` and C++ `hedging.cpp` are not re-measured on the fixed code.** A full `hedge_solvers.rs` run on `a148d0e` caught 908 of 990 viable mutants (91.7%, Wilson 95% lower bound 89.8%; observed 2026-11-16); a full `hedging.cpp` run caught 853 of 943 that built (90.5%, Wilson 95% lower bound 88.4%; 2026-11-18; survivors classified in `conformance/mutation/hedging-full-run-2026-11-18.md`). The degenerate-QP fixes changed the solvers after the Rust run. The scheduled stage run of 2026-11-15 was red (K9-1c). Not a required check.
- **Performance targets missed.** Benchmarks against `benchmarks/targets.md`: C++ meets every target. Python meets T3 (10,000-trade key-rate risk in 214 s against 900 s, down from about 20,900 s once curve rebuilds were cached) and misses T1 (bootstrap p99 129 ms against 5 ms; p50 14.6 ms) and T4 (start-up 1.84 s against 1.0 s).
- **More on the performance targets.** Of the Python start-up, `uv run` is about 1.1 s and QuantForge 0.1 s; `uv run` stays for reproducibility. Java misses T1 (p99 10.7 ms against 5 ms), put down to CPU contention on the test machine. Rust's T1 was measured under WSL and needs a rerun on native Linux. Hedge solver at n = 200: only Java meets T6 (3.0 to 4.9 s per case); all laptop measurements.
- **Python fuzz is slow.** About 12,800 inputs a minute in the R2 check (seed 53, 60 s per language), against a target of 50,000; Rust and C++ ran 126,600 and 92,600 (*observed* at R2, not re-measured since).
- **Clang on Windows** is blocked at times by Windows Application Control, which stops freshly built binaries; Clang conformance relies on CI.
- **Licence questions are open** on SONIA redistribution and on the Bank of England's forward and curve data. Raw data stays local (`oracle/LICENCES.md`).
- **Near-singular hedge QPs.** On one case with an active margin row the objective is off by about 1e-10 relative in Java and C++: the minimiser is exact to one ulp, and evaluating `A x + b` at it cancels terms of 3.4e6 (`CHANGELOG.md` 0.9.1).
- **Workflow (b), rich/cheap, still needs prices by hand** (ruling R2-A11): no free source gives the whole Treasury coupon universe priced on one date that automated clients may use; the manual `--data DIR` path stays.
- **The CDS index option (R7) has no outside case.** Its reference example, Pedersen (2003), is not freely available, so `cdsidx_f` (45 cases) is checked only by parity and limit cases (`docs/model-inventory.md` MF-1).
- **Stage F has open disagreements, not counted:** `risk_f4-0087` to `0095` (the spec keeps the 1996 Basel plus factors by stated vintage, ruling R6-28.1; the re-derivation used the later table), and `garch_f-0009` and `joint_f-0004`, not verified at the 1e-8 level (`oracle/OUTSIDE_GAPS_F.md`).
- **Stage G:** the G-42b ORE re-test runs as `ore-g42b.yml` (passed on `main` at `a148d0e`, 2026-11-14), but its count is an artifact not copied into the repo, so no new share is claimed.
- **Q6:** Q6-01 failed its preregistered fit-quality rule (78.4% inside the spread against 80%); the redesigned Q6-02 passed on synthetic quotes (87.4%; `research/q6/q6_02_output.json`). Real noisy option quotes are blocked by data terms; nothing was fitted on them.
- **The calendar check is amber, not red,** until 2027-01-31 while SIFMA's 2027 US holiday schedule is awaited (`datasets/calendar_provenance.json`); after that date it fails.

## Toolchains

- **Java 25:** JDK 25.0.5.
- **C++26:** GCC 16.2, and Clang.
- **Python:** 3.15.2, pinned per release (`==3.15.*`, see Quick start). The oracle runs separately on 3.12.
- **Rust:** 1.99.1, pinned per release, 2024 edition.

## Design principles

1. Mathematical specifications precede implementations.
2. Java, C++, Python and Rust are four equal implementations; none is the reference.
3. Each is written from the specification alone, with no shared code, FFI or generated maths.
4. Specifications, schemas, fixtures and conformance contracts are shared.
5. Expected results come from `oracle/`, never from an implementation. Agreement between implementations proves nothing on its own. Exceptions: the 7 `k8_k` Bermudan ladder cases (from the Python build, pinned reference scheme) and the 2 `sorx_h` agreement cases; hand-derived cases also exist. All are tagged in [docs/case-figures.md](docs/case-figures.md#evidence-classes-per-stage).
6. Correctness, numerical stability and reproducibility precede optimisation.
7. Performance claims require documented hardware, workload and methodology.

## Repository map

| Path | Purpose |
|---|---|
| `architecture/` | System architecture and ADRs |
| `specifications/` | Domain mathematics, contracts and acceptance criteria |
| `python/`, `cpp26/`, `java25/`, `rust/` | The four implementations |
| `oracle/` | Source of the golden results; tests only |
| `datasets/` | Schemas, golden files and the data-availability table |
| `conformance/` | Neutral runner, fuzz and mutation harnesses, tolerance policy |
| `tools/` | Public-data recorder, forward log, generators, gates and docs site build |
| `examples/` | Small cases to send to the CLI |
| `benchmarks/` | Benchmark harnesses and stored results |
| `program/` | Tickets, lane records and traceability |
| `docs/` | Results, known issues, guides, tutorials and diagrams |
| `.github/` | CI and issue templates |

## Start here

1. [Tutorial 1: price your first swap](docs/getting-started/tutorial-1-swap.md), about 10 minutes from clone to a priced swap and its DV01; then the [tutorial series](docs/getting-started/README.md) (63 tutorials). Then `LEARN.md` for the maths by topic and `COOKBOOK.md` for commands.
2. `ARCHITECTURE.md`, the ADRs in `architecture/decisions/`, and [determinism](docs/determinism.md) for what is bit-exact and what is within tolerance.
3. `ROADMAP.md` for the stages and their history, `GLOSSARY.md` for terms.
4. [Curves gallery](docs/curves/README.md): every implemented curve, with charts from real CLI runs on synthetic inputs.
5. [Question bank](docs/question-bank/README.md): 500 knowledge-check questions in 14 sets with worked answers and verify scripts.

### Status

Each capability moves through `Proposed → Specified → Implemented → Validated → Benchmarked → Operationally tested`. Stages A to J, R2 and R6 are at Implemented in all four languages, and stage K round 1 is on main, unreleased. Nothing is claimed as Validated, Benchmarked or Operationally tested ([status ladder](docs/validation/status-ladder.md)). What each stage built, and the figures each release published, are in [ROADMAP.md](ROADMAP.md#stage-history-moved-from-the-readme-on-2026-11-20) and [CHANGELOG.md](CHANGELOG.md).

## Licensing and market data

The project is MIT-licensed, with third-party notices in `THIRD_PARTY_NOTICES.md`. Market-data licensing and redistribution rights are separate: only commit data that you are entitled to redistribute. Prefer deterministic synthetic data for CI. Notices for each public source are in `THIRD_PARTY_NOTICES.md`.
