# Capacity and operations

**Plain idea.** How much work each build can do, where it stops, whether it stays the same size over hours, and whether one recorded day can be taken from the recorder's log to the dashboard pages by a script. There are no targets: the plan (14.8 K-6) asks for limits "measured and written down", and a soak with flat memory. Every figure below comes from a file in `benchmarks/results/k6/`, names its host and commit, and is generated into this page by `benchmarks/soak/capacity_page.py` (no figure is typed by hand).

**Formal statement.** Spec `specifications/12-platform/soak-eod-capacity.md` 0.2.0; rulings KR-217 to KR-221 (`specifications/stage-k-rulings-k6.md`, confirmed 2026-11-20). The acceptance rules (spec section 5) were committed in 1ce167bf before the runs they judge, with the sha256 of each runner script in the commit message. Operating steps: [runbook](runbooks/soak-and-eod.md).

**Hosts.** "local laptop, not the acceptance machine": one Windows 11 laptop, 15.6 GB of RAM, shared with other work during the runs (a latency-sensitive recorder ran on it until about 20:45 UTC on 2026-11-20), every run at below-normal priority, one at a time. "GitHub Actions runner (shared, unpinned)": the `k6-soak` workflow (`.github/workflows/k6-soak.yml`, manual and weekly). Laptop figures measure this laptop on that evening; they are not figures for the acceptance machine and they move with whatever else ran.

## What is measured, and how

| Measure | Method (source: `benchmarks/soak/capacity.py`, read) |
|---|---|
| Throughput | one pass of a fixed golden mix through one `quantforge batch --timings` process; cases per second over the wall time, start-up included. Mixes: golden (every golden case), cheap (`core.daycount`, `core.calendar`, `core.compounding`), medium (`rates.ois`, `vol.option`, `risk.curve`), heavy (`rates.lmm`, `xva.exposure`, `hedge.qp`, `vol.slv`) |
| Latency | p50 and p99 of the per-case `diagnostics.elapsed_ns` the CLI reports (time inside the case, no I/O) |
| Largest batch | the cheap mix repeated to 10,000, 100,000 and 1,000,000 lines in one process; the batch commands read one line at a time (`python/quantforge_core/cli/main.py`, `java25/src/main/java/org/quantforge/cli/Main.java`, read), so a batch has no size limit of its own and the peak memory column shows whether size changes it |
| Largest curve and book | `curve.bootstrap.par_annual` at 20, 100 and 200 quotes and `risk.intraday.delta_gamma_bound` at 10,000, 50,000 and 100,000 positions (the limits in `specifications/01-core/limits.md`), each after a small warm-up case in a fresh process; one over the limit must return `E_LIMIT` |
| Memory per request | for a ceiling row, the peak during the case minus the idle reading before it (committed private bytes on Windows, VmRSS on Linux; polled every 20 ms, so a peak shorter than that can be missed); for a mix row, the peak of the whole process |
| Correctness | every answer of a mix or batch row is judged against its golden with the conformance runner; a wrong answer turns the row into `WRONG_RESULT` and no figure is shown |

Worked example of the per-request figure: if the Python process holds 430 MiB idle after the warm-up case and peaks at 470 MiB during the 100,000-position case, the row shows 40 MiB of extra memory for that request.

Planted fault (rule 1): `capacity.py --plant-wrong` changes one expected number in the heavy mix; the heavy row must come back `WRONG_RESULT` and be the only failed row (`capacity-python-<date>-planted-wrong.json`).

## Soak (flat memory)

One long-lived `quantforge batch` process per build is fed every golden case in a loop for 130 minutes. Every 10 s the driver pauses sending until the cases in flight are answered and reads the process's memory; Java's reading is the heap used after a full collection the driver requests every 30 s. The first answer to each case is judged against its golden and every later answer must be byte-identical to it. Verdict rule (frozen, `RULES` in `benchmarks/soak/analyse.py`): after warm-up (600 s or the first full pass, whichever is later) the least-squares slope is at most 1 MiB per hour and the range at most 5 % of the median, with no drift, golden failure, error, stderr output, crash or 300 s stall, at least 660 samples (200 for the Java heap) and at least 7,200 s. The 95 % confidence interval of the slope is shown as evidence, not as a condition. Planted fault: a 20-minute Python soak that keeps 1 KiB per 100 cases must be flagged (`LEAK CAUGHT`).

The Java soak was not run on the laptop on 2026-11-20 (it would have ended after 22:15 UTC, and the laptop was shut down at 23:00). Native builds (C++ and Rust) are soaked only on the runner: a 2-hour job in WSL would hold the single WSL lock the other lanes need.

**First runner soak (verdicts only; not yet in the generated tables).** The first `k6-soak.yml` run on main (run 44824197236, on `11ba1b40`, 2026-11-20/21; "GitHub Actions runner (shared, unpinned)", not the acceptance machine) gave: Java PASS; C++ MISS (SLOPE and RANGE); Rust MISS (SLOPE and RANGE); Python on Linux MISS (RANGE; its slope is inside the 1 MiB/h bound); the runner's Python planted-leak run `LEAK MISSED`; ceiling cases passed. Cause not established; the rule is unchanged. Read from the job log lines on 2026-11-21 (measured on the runner); the figures are in the K-6 rows of [`docs/known-issues.md`](known-issues.md). The run's artifacts are not yet downloaded and committed to `benchmarks/results/k6/`, so the tables below, which `capacity_page.py` builds from committed files only, do not show these runs yet.

**What the soak verdicts can show (planted faults).** Only Python has ever run a planted leak (`benchmarks/soak/ci_run.sh` plants for Python only): the 1 KiB-per-100-cases plant was missed on the laptop and on the runner (run 44824197236, `LEAK MISSED`, slope -0.4248 MiB/h), and only the laptop's 1 KiB-per-case plant was caught (`LEAK CAUGHT`). Java, C++ and Rust never ran a planted fault, so plan rule 14.10-1 (a gate counts only after a run shows it failing on a planted fault) is met for none of the four soaks, and no Java, C++ or Rust verdict, PASS or MISS, is shown able to catch a leak. Java's series is the heap used after a requested full collection, a different quantity from the process memory (VmRSS, or committed private bytes on Windows) judged for the other three, so Java's PASS is not comparable with their verdicts. Bounds unchanged. Sources: `benchmarks/soak/ci_run.sh` (read), the verdict files below (measured), run 44824197236 (read).

## End-of-day rehearsal

`tools/eod/rehearse.py` takes one recorded date through eight checklist steps (`tools/eod/CHECKLIST.md`): read and verify the recorder's log, holdout check, daily curve run (dry), paper ledger run (dry), intraday risk on the day's book, render the curve and paper pages, site checks, archive. Each step writes its evidence (hashes, counts and aggregates only, never a recorded row) to `benchmarks/results/k6/eod-<date>-<source>.json`. Results after the freeze, 2026-11-20, local laptop, not the acceptance machine (measured): 2026-11-19 from the forward log, all eight steps pass; the synthetic day, all eight pass; each planted fault (`GAP`, `HOLDOUT`, `HASH`, `EXPLAIN`, `DOMAIN`, `LABEL`, `WIDTH`) fails its own step E1 to E7 and stops the run.

## Measured figures

<!-- capacity-generated: begin (benchmarks/soak/capacity_page.py) -->
### Throughput, latency and batch size

| Build | Row | Status | Cases | Processes | Cases per second | p50 (us) | p99 (us) | Peak memory (MiB) | File |
|---|---|---|---|---|---|---|---|---|---|
| java | `mix/golden` | pass | 16,258 | 1 | 124.2 | 83.9 | 90,857.7 | 424.4 | `capacity-java-2026-11-20.json` |
| java | `mix/cheap` | pass | 3,806 | 1 | 737.2 | 67.7 | 3,353.5 | 353.5 | `capacity-java-2026-11-20.json` |
| java | `mix/medium` | pass | 770 | 1 | 3.0 | 512.0 | 2,378,536.4 | 366.3 | `capacity-java-2026-11-20.json` |
| java | `mix/heavy` | pass | 750 | 1 | 10.2 | 425.3 | 1,114,992.9 | 379.0 | `capacity-java-2026-11-20.json` |
| java | `batch/10000` | pass | 10,000 | 1 | 57.8 | 52.6 | 24,644.3 | 366.5 | `capacity-java-2026-11-20.json` |
| java | `batch/100000` | pass | 100,000 | 1 | 2,506.7 | 10.5 | 291.8 | 366.6 | `capacity-java-2026-11-20.json` |
| java | `batch/1000000` | pass | 1,000,000 | 1 | 5,275.4 | 9.9 | 235.5 | 368.4 | `capacity-java-2026-11-20.json` |
| python | `mix/golden` | pass | 16,258 | 1 | 44.8 | 120.2 | 359,146.1 | 529.1 | `capacity-python-2026-11-20.json` |
| python | `mix/cheap` | pass | 3,806 | 1 | 7,420.9 | 35.5 | 550.4 | 16.8 | `capacity-python-2026-11-20.json` |
| python | `mix/medium` | pass | 770 | 1 | 43.6 | 309.8 | 323,897.9 | 410.1 | `capacity-python-2026-11-20.json` |
| python | `mix/heavy` | pass | 750 | 1 | 3.5 | 452.0 | 3,588,395.0 | 427.4 | `capacity-python-2026-11-20.json` |
| python | `batch/10000` | pass | 10,000 | 1 | 1,514.3 | 91.9 | 1,063.7 | 19.6 | `capacity-python-2026-11-20.json` |
| python | `batch/100000` | pass | 100,000 | 1 | 2,587.8 | 108.6 | 3,751.4 | 19.9 | `capacity-python-2026-11-20.json` |
| python | `batch/1000000` | pass | 1,000,000 | 1 | 1,105.4 | 112.2 | 5,032.5 | 20.3 | `capacity-python-2026-11-20.json` |

### Input-size ceilings (documented limits from `specifications/01-core/limits.md`)

| Build | Operation | Size | Limit | Status | Answer | Wall time (s) | Extra memory (MiB) | Request (bytes) |
|---|---|---|---|---|---|---|---|---|
| java | `curve.bootstrap.par_annual` | 20 | 200 | pass | ok | 0.002 | 0.00 | 268 |
| java | `curve.bootstrap.par_annual` | 100 | 200 | pass | ok | 0.005 | 0.00 | 855 |
| java | `curve.bootstrap.par_annual` | 200 | 200 | pass | ok | 0.008 | 0.00 | 1,555 |
| java | `curve.bootstrap.par_annual` | 201 | 200 | pass | E_LIMIT | 0.008 | 0.00 | 1,562 |
| java | `risk.intraday.delta_gamma_bound` | 10,000 | 100,000 | pass | ok | 0.406 | 3.27 | 620,378 |
| java | `risk.intraday.delta_gamma_bound` | 50,000 | 100,000 | pass | ok | 1.386 | 17.66 | 3,101,381 |
| java | `risk.intraday.delta_gamma_bound` | 100,000 | 100,000 | pass | ok | 1.788 | 6.59 | 6,202,628 |
| java | `risk.intraday.delta_gamma_bound` | 100,001 | 100,000 | pass | E_LIMIT | 1.224 | 9.71 | 6,202,686 |
| python | `curve.bootstrap.par_annual` | 20 | 200 | pass | ok | 0.009 | 0.00 | 268 |
| python | `curve.bootstrap.par_annual` | 100 | 200 | pass | ok | 0.004 | 0.00 | 855 |
| python | `curve.bootstrap.par_annual` | 200 | 200 | pass | ok | 0.009 | 0.00 | 1,555 |
| python | `curve.bootstrap.par_annual` | 201 | 200 | pass | E_LIMIT | 0.005 | 0.00 | 1,562 |
| python | `risk.intraday.delta_gamma_bound` | 10,000 | 100,000 | pass | ok | 0.550 | 6.95 | 620,378 |
| python | `risk.intraday.delta_gamma_bound` | 50,000 | 100,000 | pass | ok | 4.911 | 35.89 | 3,101,381 |
| python | `risk.intraday.delta_gamma_bound` | 100,000 | 100,000 | pass | ok | 8.252 | 71.30 | 6,202,628 |
| python | `risk.intraday.delta_gamma_bound` | 100,001 | 100,000 | pass | E_LIMIT | 8.396 | 72.43 | 6,202,686 |

### Hosts and commits of the capacity files

| File | Host | Commit | Platform | Logical CPUs | Memory figure | Verdict |
|---|---|---|---|---|---|---|
| `capacity-java-2026-11-20.json` | local laptop, not the acceptance machine | `55e8dd67` | win32 | 12 | private_bytes | PASS |
| `capacity-python-2026-11-20-planted-wrong.json` | local laptop, not the acceptance machine | `55e8dd67` | win32 | 12 | private_bytes | WRONG_RESULT CAUGHT |
| `capacity-python-2026-11-20.json` | local laptop, not the acceptance machine | `55e8dd67` | win32 | 12 | private_bytes | PASS |

### Soak verdicts

| File | Build | Host | Commit | Verdict | Reasons | Slope (MiB/h) | Slope 95 % CI | Range / median | Median (MiB) | Samples | Cases |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `soak-python-2026-11-20-planted-leak-every-1.verdict.json` | python | local laptop, not the acceptance machine | `d75b6d7a` | LEAK CAUGHT | SLOPE, RANGE | 171.8955 | n/a | 0.06026 | 475.613 | 61 | 48,661 |
| `soak-python-2026-11-20-planted-leak.verdict.json` | python | local laptop, not the acceptance machine | `254e61c5` | LEAK MISSED | none | -46.9742 | n/a | 0.01507 | 429.371 | 43 | 27,694 |
| `soak-python-2026-11-20.verdict.json` | python | local laptop, not the acceptance machine | `a95aa175` | MISS | SLOPE | 2.3243 | [1.696, 3.7996] | 0.03013 | 432.59 | 671 | 199,127 |
<!-- capacity-generated: end -->

## Limits of these figures

- One laptop, shared, below-normal priority: throughput here is a floor for this machine, not a property of the build (inferred).
- Python and Java on Windows only; C++ and Rust figures come from the runner workflow once it has run.
- The laptop figures of 2026-11-20 are noisy in ways not separated here (inferred): the same cheap cases ran at 737 cases per second in a short Java run and 5,275 in the 1,000,000-line run (JIT warm-up in a short run is one likely cause), and Python ran the 1,000,000-line batch at less than half the rate of the 100,000-line one (other lanes were building on the laptop at the time). Read them as orders of magnitude for this laptop, not as build properties.
- The driver parses and judges every answer in the same low-priority process that feeds the CLI, so on a busy machine the driver itself can be the bottleneck of a batch row.
- Two hours shows the absence of a fast leak, not of a slow one.
- The soak pauses briefly every 10 s to read memory at an idle point, so its case counts are not throughput figures.
