# Performance targets for batch use

Written 2026-11-07, before any of these figures was measured (plan 11.2.8). Writing the targets first means a result cannot be fitted to the number. If a target is missed, the miss is reported as it is. The target is not moved in the same change as the measurement.

These targets are for batch and end-of-day use: a desk's overnight run, a risk report, or a research loop. They are not latency or HFT targets, and the project makes no such claims.

## Conditions

- **One core.** Each run is pinned to one core where the OS allows it (`taskset -c 0` on Linux, `start /affinity 1` on Windows), with no parallelism inside the library.
- **Whole CLI path.** Timing is wall time from outside the process, through the `quantforge batch` verb (or `--batch` once `specifications/cli-contract.md` names it), the same way `cli_throughput.py` times it. Start-up is counted, except in the p99 figure.
- **Reference machines.**
  - The laptop in `README.md` (Intel Core 5 120U, Windows 11).
  - A GitHub `ubuntu-24.04` standard runner.

  A result names its machine. A runner figure counts only as a sanity check, because shared runners are noisy.
- **Inputs.** Real public data where possible: the latest US Treasury par curve and SONIA fixings from the recorder. Otherwise the synthetic book defined below. Inputs are fixed by a hash recorded with each result.
- **Repeats.** One unmeasured warm-up batch, then at least 5 repeats. The figure reported is the median, plus the p99 where a target asks for it.

## Targets

| # | Measure | Workload | Target, every language | Stretch (Rust, C++) |
|---|---|---|---:|---:|
| T1 | Single curve bootstrap, p99 latency per case within a warm batch | `rates.ois.bootstrap`, 13 SOFR OIS quotes 1W to 30Y, `LOG_LINEAR_DF`, `SEQUENTIAL`; 10,000 cases, each with quotes jittered by a seeded ±5 bp | ≤ 5 ms | ≤ 1 ms |
| T2 | 10,000-swap book PV, wall time, one core | One bootstrapped SOFR curve, then 10,000 `rates.swap.pv` cases (book below) | ≤ 60 s | ≤ 10 s |
| T3 | 10,000-swap book key-rate risk, wall time, one core | T2's book, `risk.ois.dv01` on 13 key rates (one bump per pillar, so 14 curve builds) | ≤ 15 min | ≤ 2 min |
| T4 | Batch start-up | `quantforge version`, median of 20 cold-ish runs (OS file cache warm) | ≤ 1.0 s (Python through `uv run`), ≤ 0.5 s (Java), ≤ 0.1 s (Rust, C++) | — |
| T5 | Memory | Peak RSS during T2 | ≤ 1 GiB | ≤ 256 MiB |

Why these numbers:

- **T1.** An end-of-day run builds tens of curves. Even 5 ms each is far below the time spent fetching data. The stretch figure tells us whether a curve can sit inside an intraday risk loop.
- **T2 and T3.** A small desk's swap book is in the low thousands of trades, so 10,000 is a margin above that. A full key-rate run inside 15 minutes fits a nightly batch window with room for a rerun.
- **T4.** This target exists because a JVM start per case would dominate run time, which is why `batch` exists at all (`cli-contract.md`).

## Sample swap book (T2, T3 and workflow (a))

- Built from a seeded generator (seed `20261107`), never from real positions.
- **Notionals:** 1m to 100m USD, log-uniform.
- **Maturities:** 1Y to 30Y, picked uniformly among the standard tenors.
- **Direction:** pay or receive, 50/50.
- **Fixed rate:** the par rate ±100 bp.
- **Start:** spot.
- **Conventions:** SOFR OIS, annual fixed against annual compounded SOFR.

The generator will live in `tools/workflows/sample_book.py`. Its output hash goes with every result.

## What counts as met

A target is met when the median of the repeats (or the p99 for T1) is at or under the target on the laptop, and no repeat failed. A language that misses a target gets an issue, not a footnote. A target changes only in its own commit, with the reason, before the next measurement.

## Results

None yet. Results go in `benchmarks/results/` with the machine, commit, input hash and toolchain, and in a table here that links each figure to its file.
