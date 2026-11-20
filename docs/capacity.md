# Capacity and operations

**Plain idea.** How much work each build can do, where it stops, whether it stays the same size over hours, and whether one recorded day can be taken from the recorder's log to the dashboard pages by a script. There are no targets: the plan (14.8 K-6) asks for limits "measured and written down", and a soak with flat memory. Every figure below comes from a file in `benchmarks/results/k6/`, names its host and commit, and is generated into this page by `benchmarks/soak/capacity_page.py` (no figure is typed by hand).

**Formal statement.** Spec `specifications/12-platform/soak-eod-capacity.md` 0.2.0; rulings KR-217 to KR-221 (`specifications/stage-k-rulings-k6.md`, PROPOSED). The acceptance rules (spec section 5) were committed in 1ce167bf before the runs they judge, with the sha256 of each runner script in the commit message. Operating steps: [runbook](runbooks/soak-and-eod.md).

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

Native builds (C++ and Rust) are soaked only on the runner: a 2-hour job in WSL would hold the single WSL lock the other lanes need. Until the first runner artifact is downloaded and committed, the native soak is "not run yet" (`docs/known-issues.md`).

## End-of-day rehearsal

`tools/eod/rehearse.py` takes one recorded date through eight checklist steps (`tools/eod/CHECKLIST.md`): read and verify the recorder's log, holdout check, daily curve run (dry), paper ledger run (dry), intraday risk on the day's book, render the curve and paper pages, site checks, archive. Each step writes its evidence (hashes, counts and aggregates only, never a recorded row) to `benchmarks/results/k6/eod-<date>-<source>.json`. Results after the freeze, 2026-11-20, local laptop, not the acceptance machine (measured): 2026-11-19 from the forward log, all eight steps pass; the synthetic day, all eight pass; each planted fault (`GAP`, `HOLDOUT`, `HASH`, `EXPLAIN`, `DOMAIN`, `LABEL`, `WIDTH`) fails its own step E1 to E7 and stops the run.

## Measured figures

<!-- capacity-generated: begin (benchmarks/soak/capacity_page.py) -->
<!-- capacity-generated: end -->

## Limits of these figures

- One laptop, shared, below-normal priority: throughput here is a floor for this machine, not a property of the build (inferred).
- Python and Java on Windows only; C++ and Rust figures come from the runner workflow once it has run.
- Two hours shows the absence of a fast leak, not of a slow one.
- The soak pauses briefly every 10 s to read memory at an idle point, so its case counts are not throughput figures.
