# Soak, load, end-of-day rehearsal and capacity limits (K-6)

Spec version 0.2.0 (stage K lane k-v1-k6, 2026-11-20). Status: the rulings KR-217 to KR-221 (`stage-k-rulings-k6.md`) are PROPOSED for the stage K coordinator; the acceptance rules in section 5 are frozen as of the commit that adds this version, before any run they judge. Version 0.1.0-proposed was written by lane k-w3-spec on 2026-11-19 (branch `k-w3-spec`, read); this version keeps its rule numbers and states where the build differs. Plan items: 14.8 K-6; 14.10 rules 1 and 2. Reviewer: none: self-assessment; no second review (owner decision 2026-11-18).

Every result names its host: "local laptop, not the acceptance machine" or "GitHub Actions runner (shared, unpinned)".

**Plain idea.** Three questions, each answered by a script that writes its evidence to a file. Does a long-running process keep its memory flat and its answers unchanged (soak)? How much work can it do and where does it stop (capacity)? Can the daily chain, from recorded data to the dashboard pages, run end to end from a checklist without a human filling gaps (end-of-day rehearsal)? Each check is shown catching a fault planted on purpose.

## Acceptance tests copied from the plan (14.8 K-6; not softened)

> A 2-hour soak with flat memory; a scripted end-of-day run from recorded data to dashboard with a checklist; capacity limits measured and written down.

## 1. Soak (KR-217, KR-218)

**Workload.** Per build (Python, Java, Rust, C++): one long-lived `quantforge batch` process fed every case of `datasets/golden` (files sorted, cases as listed; the count at the run commit is in each summary file) in a loop for at least 130 minutes of wall time (the rule needs at least 7,200 s; the extra time leaves room for the warm-up; the laptop Python run of 2026-11-20 is 145 minutes, see "Planted-leak result" below), with at most 32 cases in flight. Driver: `benchmarks/soak/soak.py`.

**Answers.** The first answer to each case is judged against its golden with the conformance runner's `judge` (`GOLDEN` on a failure). Every later answer to the same case must be byte-identical to the first (`DRIFT` otherwise). A process that stays small but starts giving different answers has not passed.

**Measured, every 10 s.** The driver stops sending, waits until every case in flight is answered, takes the readings, and resumes. At that idle point the process holds only what it keeps between requests, so a transient peak inside a heavy case (a 1,000,000-normal Monte Carlo case, say) is not mistaken for growth (inferred). Readings (`benchmarks/soak/procstat.py`): resident set, committed private memory, peak, handles, threads; plus cases done, errors and drift. Java, every 30 s at the idle point: `jcmd <pid> GC.run`, then `jcmd <pid> GC.heap_info`, and the heap used after that full collection.

**Judged memory series.** Linux (WSL or a runner): VmRSS. Windows: committed private bytes, because Windows trims the working set of a process on its own schedule, more so at below-normal priority, so the working set measures the memory manager as well as the program (read: Microsoft documentation of working sets; the effect is recalled, not measured here). Java: heap used after the requested full collection; RSS is reported, not judged. All figures are written to the CSV whichever is judged.

**Flat memory, defined before the run (KR-218).**

1. Warm-up: samples before max(600 s, the end of the first full pass over the golden set) are discarded, so every case has run once before memory is judged.
2. SLOPE: the least-squares slope of the judged series against time is at most **1 MiB per hour**.
3. RANGE: maximum minus minimum of the judged series is at most **5 % of its median**.
4. Enough data: at least 660 judged samples after warm-up (200 for the Java heap series, one per 30 s), and at least 7,200 s of wall time.
5. Zero `DRIFT`, zero `GOLDEN`, zero unreadable output lines (`ERRORS`), zero bytes on stderr (`STDERR`), exit code 0 when stdin closes (`EXIT`), the process alive at every sample (`DIED`), the whole golden set answered at least once (`NO_FULL_PASS`), and no 300 s stretch without a completed case (`STALL`).

All must hold; anything else is a MISS and is written down as one. The thresholds are not changed after a run. The 95 % confidence interval of the slope is reported beside the point estimate, from the means of 10-minute blocks with a Student t on blocks minus 2 degrees of freedom; it is evidence, not a pass condition. The rule lives in one place, `RULES` in `benchmarks/soak/analyse.py`.

Why these numbers (inferred, kept from 0.1.0): one leaked small object per case at hundreds to thousands of cases a second is many MiB an hour, far above 1 MiB/h; allocator and JIT noise after warm-up is expected within a few percent. They are engineering choices, not cited figures. Why 300 s for a stall: the slowest golden suite in the slowest build takes about 23 s for 102 cases (conformance log of 2026-11-19, measured), so a single case is far under 300 s, and a hung process still shows within five minutes.

**Worked example.** A Python soak with 700 judged samples after warm-up, median 450 MiB, slope 0.3 MiB/h, range 6 MiB, no drift: SLOPE holds (0.3 <= 1), RANGE holds (6 <= 22.5), PASS. The same run with a range of 30 MiB is a MISS on RANGE even with a flat slope.

**Planted fault (rule 1).** `QF_SOAK_LEAK=1` makes the Python entry point used by the harness (`benchmarks/soak/py_entry.py`, not the library) keep 1 KiB alive for every 100 cases. A 20-minute run with it, analysed with the same SLOPE rule (`analyse.py --planted`: SHORT and FEW_SAMPLES are not applied), must fire SLOPE. Deviation from 0.1.0: there the leak was a test build flag in every language; here it is in the Python harness only, and the analyser's rule is the same for every build, so one planted build shows the rule can see a leak.

**Planted-leak result, 2026-11-20 (recorded MISS of SK4 for the soak).** The 20-minute planted run with 1 KiB per 100 cases came back `LEAK MISSED` (`benchmarks/results/k6/soak-python-2026-11-20-planted-leak.verdict.json`, measured, local laptop, not the acceptance machine): slope -47 MiB/h on 43 samples after a 826 s warm-up, range 1.5 % of the median. The reason is arithmetic, not noise: the soak ran the Python build at about 23 cases a second (the summary file counts the answers over 1,282 s; the golden mix includes multi-second cases, and the driver pauses for every reading), so the planted leak grew by about 0.8 MiB an hour, under the 1 MiB/h bound the rule is meant to flag. The proposed rule assumed a rate in the thousands a second. The miss stands and the bound is not changed. Two consequences, written down before the next runs: (1) at Python's golden-mix rate the rule can only see a leak of more than about 1.2 bytes per case on average (1 MiB/h at 23 cases a second), so a smaller per-case leak in Python passes the soak unseen; (2) an added planted run, declared here before it runs, keeps 1 KiB per case (`--leak-every 1`, about 80 MiB/h at the same rate) and must fire SLOPE; it shows the rule sees a leak of that size, nothing smaller. The Python soak itself is run for 145 minutes, not 130, because the first run's spacing (about 10.7 s per sample, 826 s warm-up) would leave about 650 samples after warm-up in 130 minutes, under the 660 the rule needs; the run length is a run setting, the rule is unchanged. A 130-minute Python soak started at 18:15 UTC was stopped by the lane after about 4 minutes for this reason; it is recorded as interrupted and not scored.

**Python soak result, 2026-11-20 (recorded MISS of SK1 for Python).** 145 minutes, local laptop, not the acceptance machine, run scripts as frozen in 3361a67e (`benchmarks/results/k6/soak-python-2026-11-20.verdict.json`, measured): MISS on SLOPE. After a 2,037 s warm-up (the first full pass took that long with the reading pauses), 671 samples: slope 2.32 MiB/h (95 % CI 1.70 to 3.80), above the 1 MiB/h bound; range 13.0 MiB, 3.0 % of the 432.6 MiB median (RANGE holds); no drift, no golden failure, no error, nothing on stderr, exit 0, longest gap between completed cases 1.7 s; 12 full passes. The cause is not found: the judged series (committed private bytes) climbs slowly with a sawtooth, which could be a true leak, allocator or interpreter caches still growing after the first pass, or Windows heap behaviour; the run does not separate them (inferred). The miss stands and the bound is not changed. The summary's `commit` field is the branch head when the run ended; the runner scripts are byte-identical to the 3361a67e freeze.

**Not in this version.** The K-5b snapshot publisher with 4 readers beside the batch process (0.1.0) is not run: the soak harness drives the batch CLI only. Recorded as not done in `docs/known-issues.md`.

**Machine plan.** Python and Java soak on the laptop under Windows, one at a time, below-normal priority, each detached with a progress file and a failure watcher (LANE_RULES). C++ and Rust soaks are not run on the laptop: a 2-hour job would hold the single WSL lock that the port lanes need. All four soaks run in `.github/workflows/k6-soak.yml` (manual and weekly, about 2.5 hours per job, under the 6-hour job limit; free for a public repository, recalled).

## 2. Capacity (KR-219)

No targets: the plan asks for limits "measured and written down". Script `benchmarks/soak/capacity.py`; raw file `benchmarks/results/k6/capacity-<build>-<date>.json`; page `docs/capacity.md`.

| Row | How |
|---|---|
| `mix/<name>` | one pass of a fixed golden mix through `quantforge batch --timings`, at 1 process on the laptop and 1, 2 and 4 processes on the runner: cases per second over wall time (start-up included), p50 and p99 of the per-case `diagnostics.elapsed_ns`, peak memory. Mixes: golden (all cases), cheap (`core.daycount`, `core.calendar`, `core.compounding`), medium (`rates.ois`, `vol.option`, `risk.curve`), heavy (`rates.lmm`, `xva.exposure`, `hedge.qp`, `vol.slv`) |
| `batch/<n>` | the cheap mix repeated to 10,000, 100,000 and 1,000,000 lines: wall time, cases per second, peak memory |
| `ceiling/<op>/<size>` | one case at 10 %, 50 % and 100 % of the documented limit after a small warm-up case in a fresh process: wall time and the extra memory the case needed; `limit + 1` must return `E_LIMIT`. Limits from `01-core/limits.md`: 200 quotes for `curve.bootstrap.par_annual`, 100,000 positions for `risk.intraday.delta_gamma_bound` |

**Pass rule per row (frozen).** A row passes when it completes with every judged answer correct against its golden (mix and batch rows), status `ok` (ceiling rows up to the limit) or `E_LIMIT` (limit + 1), and exit code 0. A row with a wrong answer reports `WRONG_RESULT` and no figure counts. There is no threshold on any figure.

**Planted fault (rule 1).** `--plant-wrong` multiplies one expected number of the heavy mix by 1.5 and adds 1 after loading; the heavy row must report `WRONG_RESULT` and be the only failed row.

Deviations from 0.1.0: adapter rates (K-3) and the 250-day daily-job timings are not measured here (the K-3 lane and the daily jobs' own logs hold them); the laptop measures 1 process only, because the laptop is shared with latency-sensitive work; 2 and 4 processes are runner rows.

## 3. End-of-day rehearsal (KR-220, KR-221)

Script `tools/eod/rehearse.py --date YYYY-MM-DD --source forward-log|synthetic [--plant FAULT]`; human checklist `tools/eod/CHECKLIST.md`; evidence `benchmarks/results/k6/eod-<date>-<source>.json`. Steps E1 to E8 as in the checklist: read and verify the recorded log, holdout check, daily curve run (dry), paper ledger run (dry), intraday risk on the day's book, render the curve and paper pages into a temporary site, site checks, archive.

**Pass rule (frozen).** The run passes only when all eight checklist lines have status `pass`; a failing step stops the run and the rest are recorded as "not run". Each planted fault E1 to E7 (`GAP`, `HOLDOUT`, `HASH`, `EXPLAIN`, `DOMAIN`, `LABEL`, `WIDTH`) must make its own step fail and no earlier step fail. Recorded data only: the script reads the recorder's log with `git show`, fetches nothing, writes nothing to the ledger branches and starts no workflow. Its JSON holds hashes, counts and aggregates only, never a recorded row.

The deviations from 0.1.0 (five tenors recorded, no Federal Reserve file, E5's book is the paper positions, E6 uses the existing page renderers since there is no `tools/dashboard/render.py`, E7 is a static width check) are listed in the script's docstring and the checklist's Limits section.

Development runs: the rehearsal was run on 2026-11-20 before this acceptance was frozen (commit 0042e5b8, development only). The counted runs are the ones made after the freeze commit, written over those files.

## 4. Dashboard

"Dashboard" means the static docs-site pages the daily jobs already publish: the curve page (`tools/curve_daily/site_page.py`) and the paper-ledger page. Grafana is dropped (AGPL). No dashboard rulings are taken in this lane (the k-w3-spec dashboard rows KR-211 to KR-216 collide with confirmed rows on `k-v1` and are not copied).

## 5. Acceptance tests (frozen before the runs they judge)

| ID | Plan | Test |
|---|---|---|
| SK1 | K-6 | 2-hour soak per build: the section 1 rule gives PASS. Laptop: Python, Java. Runner: all four |
| SK2 | K-6 | `docs/capacity.md` written from measured runs; every figure with host and commit; every row passes the section 2 row rule |
| SK3 | K-6 | EOD rehearsal on one recorded date after every holdout window: all eight checklist lines pass |
| SK4 | 14.10 rule 1 | the planted soak leak flagged (SLOPE), the planted wrong result stopping its row, each EOD planted fault failing its own step; runs recorded |
| SK5 | 14.10 rule 2 | the CHANGELOG line for K-6 names `benchmarks/results/k6/` |

## Out of scope

- A soak of the adapter containers.
- Load targets or service-level objectives.
- A production scheduler; the rehearsal is a script run by hand.

## Limits

- Two hours shows the absence of a fast leak, not of a slow one: at 1 MiB/h a leak needs about 700 hours to reach 700 MiB.
- Runner figures are noisy and unpinned; laptop figures are not the acceptance machine, and the laptop is shared with other work during the runs.
- The idle-point reading pauses the workload for a moment every 10 s, so soak throughput is lower than flat-out throughput; capacity rows measure throughput, the soak does not.
