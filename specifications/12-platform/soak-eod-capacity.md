# Soak, load, end-of-day rehearsal and capacity limits (K-6)

Spec version 0.1.0-proposed (stage K wave 3, lane k-w3-spec, 2026-11-19). Status: PROPOSED; nothing here is built or run. Rulings KR-217 to KR-221 (`stage-k-rulings-w3.md`). Plan items: 14.8 K-6; 14.10 rules 1 and 2. Every result names its host: "local laptop, not the acceptance machine" or "GitHub Actions runner (shared, unpinned)".

**Plain idea.** Three questions, each answered by a script that writes its evidence to a file: does a long-running process keep its memory flat (soak); how much work can it do and where does it stop (load and capacity); and can the whole daily chain, from recorded data to the dashboard, be run end to end from a checklist without a human filling gaps (end-of-day rehearsal). Each check is shown catching a fault planted on purpose before it counts.

## Acceptance tests copied from the plan (14.8 K-6; not softened)

> A 2-hour soak with flat memory; a scripted end-of-day run from recorded data to dashboard with a checklist; capacity limits measured and written down.

## 1. Soak (KR-217, KR-218)

**Workload.** For each of Python, Java, Rust and C++: one long-lived `quantforge batch` process fed the full golden case set in a loop (cases in index order, repeated) for 2 hours of wall time, plus, for C++, Rust and Java, the K-5b snapshot publisher with 4 readers running beside it in its own process. Every result is compared with its golden as it comes out; one mismatch fails the soak (`DRIFT`), because a process that stays small but starts giving wrong answers has not passed.

**Measured.** Resident set size every 10 s (`/proc/<pid>/status` VmRSS in WSL or on the runner; for Java also the heap used after each GC from `-Xlog:gc`), cases completed, and errors.

**Flat memory, defined before the run.** Discard the first 10 minutes (warm-up, JIT, caches). On the remaining samples (at least 660): the least-squares slope of RSS against time is at most **1 MiB per hour**, and the maximum minus the minimum RSS is at most **5% of the median** RSS. For Java the same two rules apply to post-GC heap used; RSS is reported only. Both rules must hold. The thresholds are not changed after a run; a miss is recorded as a miss.

Why these numbers (inferred): a leak of one small object per case at the expected rate of hundreds to thousands of cases a second is many MiB an hour, far above 1 MiB/h; allocator and JIT noise after warm-up is expected to stay within a few percent. They are engineering choices, not cited figures.

**Planted fault (rule 1).** A build flag `QF_SOAK_LEAK=1` (test builds only) keeps 1 KiB per 100 cases alive. At 1,000 cases a second that is about 35 MiB an hour; the slope rule must flag it in a 20-minute planted run. The planted run is recorded beside the real one.

**Evidence.** `benchmarks/results/k6/soak-<language>-<date>.json` (samples, slope, range, median, case count, mismatches, host, commit) and a plotted SVG for the docs.

**Machine plan.** Python and Java soak on Windows natively; Rust and C++ in WSL one at a time (machine rule: one heavy WSL job). Each run is about 2 h 15 min, so it is launched detached with a failure watcher; four languages take about 9 hours of wall time in sequence, or about 2.5 hours if run as parallel jobs on GitHub Actions (free for a public repository, recalled), which is the recommended route (KR-218).

## 2. Load and capacity (KR-219)

No targets: the plan asks for limits "measured and written down". Each figure is published as measured, in `docs/capacity.md`, with host and commit.

| Measure | How |
|---|---|
| Throughput of `quantforge batch` | cases per second per language on three fixed mixes (cheap: day count and interpolation; medium: swap PV and implied vol; heavy: 10,000-swap book, MC), at 1, 2 and 4 concurrent processes |
| Per-case latency | p50 and p99 per mix, as in H-5 (`10-execution/library-interfaces.md`) |
| Input-size ceilings | for each limit in `01-core/limits.md` and the stage K `E_LIMIT` sizes (for example 100,000 positions, 1,000,000 P&L points): wall time and peak memory at 10%, 50% and 100% of the limit, and the check that 100% + 1 returns `E_LIMIT` |
| Adapters (K-3) | rows or messages per second for the 10,000-record round trip and for 1,000,000 records, per adapter, with peak container memory |
| Daily jobs | wall time and peak memory of the paper ledger and curve runs on a 250-day synthetic history |
| Machine ceiling | the largest of the above that runs on this laptop within WSL's 7 GB, stated as such |

**Planted fault (rule 1).** The capacity script must report a failure, not a figure, when a case returns an error or a wrong result: a corrupted golden in the heavy mix must stop that row with `WRONG_RESULT`.

## 3. End-of-day rehearsal (KR-220, KR-221)

Script `tools/eod/rehearse.py --date YYYY-MM-DD` on a date with recorded data on `forward-log` after every holdout window. Each step writes a checklist line `{step, status, evidence, seconds}` to `benchmarks/results/k6/eod-<date>.json`; the run passes only if every line passes. No step is skipped by hand; a failing step stops the run.

| # | Step | Pass when | Planted fault that must make it fail |
|---|---|---|---|
| E1 | read the day's recorded rows from `forward-log` and verify the chain | chain verifies; the day's Treasury par-yield row present | a row removed from a copy of the log (`GAP`) |
| E2 | holdout check on the date | `research/holdout_scan` finds nothing | a date inside a holdout window (`HOLDOUT`) |
| E3 | daily curve run, dry run, for the date | row built, labels present, verifier passes on the extended copy | a source file with one changed byte (`HASH`) |
| E4 | paper ledger run, dry run, for the date | DAY row built, explain sums, exact replay passes | an explain term off by one cent (`EXPLAIN`) |
| E5 | intraday risk on the day's book (`risk.intraday.delta_gamma_bound`, `risk.curve.key_rate`) | results returned, label present | a position with non-finite yield (`E_DOMAIN` reported as a failed step) |
| E6 | render the dashboards into a temporary site | `dashboard.md` checks pass (labels, counter, claim lint, holdout scan) | a label removed (`LABEL`) |
| E7 | site checks on the rendered pages | link check and the G10 phone-width check pass | a page with a 600 px fixed-width element (`WIDTH`) |
| E8 | archive | the checklist JSON and the hashes of every input and output written | none (bookkeeping) |

Recorded data only: the rehearsal reads what the recorder already published and never fetches from a source itself, so it can be rerun on the same date with the same result. It writes nothing to the ledger branches (dry runs).

## Acceptance tests (PROPOSED)

| ID | Plan | Test |
|---|---|---|
| SK1 | K-6 | 2-hour soak per language: flat-memory rules of §1 hold, zero `DRIFT` |
| SK2 | K-6 | `docs/capacity.md` written from measured runs, every figure with host and commit |
| SK3 | K-6 | EOD rehearsal on one recorded date: all eight checklist lines pass |
| SK4 | 14.10 rule 1 | the soak leak, the capacity wrong-result and each EOD planted fault shown failing, runs recorded |
| SK5 | 14.10 rule 2 | the CHANGELOG line for K-6 names `benchmarks/results/k6/` |

## Out of scope

- Soak of the adapter containers for 2 hours (their round trip is K-3; a container soak is optional and reported only).
- Load targets or service-level objectives.
- A production scheduler; the rehearsal is a script run by hand or by `workflow_dispatch`.

## Limits

- Two hours shows the absence of a fast leak, not of a slow one.
- Runner figures are noisy and unpinned; laptop figures are not the acceptance machine.
