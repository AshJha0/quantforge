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
| T1 | Single curve bootstrap, p99 latency per case within a warm batch | `rates.ois.bootstrap`, 13 SOFR OIS quotes 1W to 30Y, `LOG_LINEAR_DF`, `SEQUENTIAL`; 10,000 inputs, each with quotes jittered by a seeded ±5 bp | ≤ 5 ms | ≤ 1 ms |
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

Measured 2026-11-07, after the targets above were written and with none of them moved. The machine is the reference laptop: Rust and C++ ran inside WSL 2 (Ubuntu 26.04, GCC 15.2, pinned to one core), because Windows blocks fresh native executables; Java and Python ran on Windows, not pinned. The code is `r2-infra` at 8215371 plus the harness (c64ea97), `benchmarks/batch_targets.py`, with 5 repeats (Python 3). Raw files are in `results/2026-11-07-*-batch-*.json`.

| # | Target (stretch) | Rust | C++ | Java | Python |
|---|---|---:|---:|---:|---:|
| T1 bootstrap p99 | ≤ 5 ms (≤ 1 ms) | 16.1 ms **miss**¹ | 1.83 ms met, stretch missed | 10.7 ms **miss** | 190 ms **miss**² |
| T2 10,000 PV | ≤ 60 s (≤ 10 s) | 1.09 s stretch met | 0.81 s stretch met | 4.71 s met | 13.0 s met |
| T3 10,000 key-rate | ≤ 900 s (≤ 120 s) | 151 s met, stretch missed | 82 s stretch met | 110 s met | 12,000 s **miss** (scaled from 200 trades)³ |
| T4 start-up | ≤ 0.1 s Rust/C++, ≤ 0.5 s Java, ≤ 1.0 s Python | 0.004 s met | 0.002 s met | 0.37 s met | 1.58 s **miss**² |
| T5 peak RSS in T2 | ≤ 1 GiB (≤ 256 MiB) | 95 MiB stretch met | 97 MiB stretch met | not measured⁴ | not measured⁴ |

1. Inside WSL, the p99 of the gap between result lines is dominated by VM scheduling jitter, about 16 ms. A repeat run gave C++ 15.7 ms and Rust 16.9 ms, while the median gap was 0.54 ms (C++) and 0.88 ms (Rust), and the mean per case 1.2 and 2.2 ms. Rust's and C++'s T1 need a native Linux rerun (a post-push check) before either miss stands.
2. Python's first ~10 minutes overlapped another CPU-heavy run on the laptop, so T4 and T1 may read high. An earlier quiet smoke test gave a T4 of 3.7 s and a T1 of 119 ms, so Python misses either way. Python runs through `uv run`, which adds launcher time to T4.
3. The 10,000-trade Python figure is scaled: start-up plus (200-trade time minus start-up) × 50, because a full run takes over three hours. Python key-rate risk is about 1.2 s per trade, against 8 to 15 ms in the compiled languages. This needs an issue for the Python lane.
4. Peak RSS is read with `os.wait4`, which exists on Linux only.

Misses to raise as issues, without moving the targets: Python on T1, T3 and T4; Java on T1, where the p99 is about 10 ms against a 5 ms target. Rerun Rust and C++ T1 natively before raising those.

## R6 addition: hedge solver at size (ruling R6-6.4, written 2026-11-12 before any measurement)

Written by the R6 spec and oracle lane before any language ran the `r6/hedgeqp_large_r6` goldens. Same conditions as above (one core, whole CLI path, median of 5 after one warm-up, machine named).

| # | Measure | Workload | Target, every language | Stretch (Rust, C++) |
|---|---|---|---:|---:|
| T6 | One bounded cost QP, n = 200, wall time per case inside a warm batch | `hedge.qp.solve`, the `n = 200` cases of `r6/hedgeqp_large_r6` (250 factors, half-spreads, impact, margin, 3 equalities, bounds) | ≤ 5 s (≤ 20 s Python) | ≤ 0.5 s |
| T7 | Same at n = 50 | the `n = 50` cases | ≤ 0.5 s (≤ 2 s Python) | ≤ 0.05 s |

Why these numbers: the review measured one such solve at 46 s in Python on v0.8.0 (finding 7). A split-variable active-set method on a 200-variable QP needs a few hundred factorisation updates of a matrix this size, well under a second in a compiled language; 20 s for Python allows a pure-numpy active set without a compiled QP library. A miss is reported, not refitted.

## Stage H addition: order-book latency H-9 (written 2026-11-18 before any measurement)

Rows L1 to L6 are fixed in `specifications/09-microstructure/low-latency-targets.md` (ruling HR-23), with their reasons; summary on the pinned local Linux run, median of 5:

| # | Measure | Target |
|---|---|---|
| L1, L2 | C++, Rust update p50 / p99 / p99.9 | R: 100 ns / 500 ns / 2 us; S: 150 ns / 1 us / 5 us |
| L3 | Java update p50 / p99 / p99.9 | R: 200 ns / 1 us / 5 us; S: 300 ns / 2 us / 12.5 us |
| L4 | Allocations after warm-up | C++, Rust exactly 0; Java no GC and 0 sampled, else miss published |
| L5 | Query p99 (best, qty_at, top(10), top(100)) | C++/Rust 50 / 100 / 200 ns / 1 us; Java twice that |
| L6 | Correctness on the same replay | zero mismatches |

Added 2026-11-19 before any R2 timing (rulings HR-130, HR-131; reasons in the same file, sections g and h):

| # | Measure | Target |
|---|---|---|
| L1-R2, L2-R2 | C++, Rust update p50 / p99 / p99.9 on R2 (raw venue messages; window exactly 6 h of the first qualifying session, HR-134; first written as 6 to 8 h) | 100 ns / 500 ns / 2 us (the R figures, unchanged) |
| L3-R2 | Java, same | 200 ns / 1 us / 5 us (unchanged) |
| L7 | Per-level cost on the one-second differenced stream of the R2 window, p50 / p99 / p99.9 | C++, Rust 100 ns / 500 ns / 2 us; Java 200 ns / 1 us / 5 us. Secondary row: written after the 2026-11-19 R miss was seen (mean about 40 ns a level), so the p50 is expected to pass; it never re-judges that window. Headline as in (a), both symbols, all three percentiles; label "per level, not per message; L1-L3 on R remain a recorded MISS" (HR-135) |

Python: reported only. A miss is reported, not refitted.

## Stage H addition: R4 library interfaces H-5 (written 2026-11-18 before any measurement)

Rows E1 to E6 (execution layer) and B1 to B4 (plan H-5 set) are fixed in `specifications/10-execution/library-interfaces.md` section 4, with method and reasons. In process, p50 / p99 per call, median of 5 repeats, acceptance machine the Actions `ubuntu-24.04` runner; regression threshold max(20%, 3 x CV of p99). Java summary: E1 1/5 us, E2 20/100 us, E3 5/25 us, E4 5/25 us, E5 200 ns/1 us, E6 100/500 ns; B1 2/5 ms, B2 50/250 us, B3 5/25 us, B4 5/6 s. Python about 50x Java; Rust and C++ half of Java. A miss is reported, not refitted.
