# Low-latency order book: H-9 targets

Spec version 0.1.0 (stage H wave 1b; confirmed 2026-11-18 by the stage H coordinator). Plan item 14.7 H-9; rulings HR-18 to HR-24 (`stage-h-rulings-w1b.md`); method, workloads R and S, warm-up, repeats and allocation counting are in `low-latency-book.md` and are not repeated here.

**Fixed as of 2026-11-18, before any H-9 timing run (R1 rule, [TGT]).** No H-9 code exists on this date. The first measurement is published as it is; a missed target is reported as a miss and is not retuned in the change that measures. A target changes only in its own later commit with a reason, before the next measurement.

## How the numbers were chosen

The targets come from first principles, not from a published order-book benchmark: we found no public, reproducible per-message latency figure for an L2 book at 100 levels that we could read and cite, so none is quoted. The reasoning:

1. A Kraken L2 update is one or a few price levels (HR-19). With the book held in an array indexed by tick distance from the touch (or a sorted array of 100 levels), one level change is a few cache-resident loads and stores. Two 100-level sides at 16 bytes a level are about 3.2 KB, well inside a 32 KB L1 data cache. Main-memory access is of order 100 ns and an L1 hit a few cycles, so a warm update that stays in cache should cost tens of nanoseconds, and one that misses to memory a few hundred. Evidence class: textbook hardware orders of magnitude, recalled, not measured on the reference machine; the figures are used only to set ceilings with margin.
2. The timer read itself costs of order 20 to 30 ns with a vDSO `clock_gettime` (recalled, to be measured and published per HR-21). A p50 target below about twice the clock cost cannot be resolved per message; HR-21's batch timing then becomes the headline for p50 and the report says so.
3. Workload S has deep sweeps of up to 100 levels and 1% of messages at just-truncated prices, so its tail is set wider than R's (a 100-level sweep at ~10 ns a level is about 1 us).
4. Java: same algorithm, JIT-compiled, bounds checks and no value types; allowed 2x the C++/Rust figures. Safepoints and JIT recompilation can appear in p99.9, so Java's p99.9 is allowed 2.5x.
5. Shared GitHub Actions runners are noisy and unpinned ([PERF]); their figures are sanity checks at 3x the headline targets and the source of the CI baseline, not the headline.

Evidence classes: [PERF] `architecture/performance-standards.md` and [TGT] `benchmarks/targets.md`, project rules, read 2026-11-17 (as recorded in `low-latency-book.md`). Points 1 and 2 are recalled engineering orders of magnitude, labelled as such; no outside citation is claimed for any number below.

## Targets (headline: pinned local Linux run, one core; median of 5 runs)

The local Linux run is WSL 2 on the reference laptop unless a native Linux machine is available; the report names which ([PERF]). All figures in-process, pre-decoded messages, no I/O (H-9(a)).

### (a) Per-message update latency (`apply`, all kinds pooled; per-kind tables reported as well)

| # | Language | Workload | p50 | p99 | p99.9 |
|---|---|---|---:|---:|---:|
| L1 | C++ | R (recorded window of at least 6 h, form B, 100 levels; amended 2026-11-19 by owner decision, targets unchanged) | <= 100 ns | <= 500 ns | <= 2 us |
| L1 | C++ | S (synthetic stress) | <= 150 ns | <= 1 us | <= 5 us |
| L2 | Rust | R | <= 100 ns | <= 500 ns | <= 2 us |
| L2 | Rust | S | <= 150 ns | <= 1 us | <= 5 us |
| L3 | Java | R | <= 200 ns | <= 1 us | <= 5 us |
| L3 | Java | S | <= 300 ns | <= 2 us | <= 12.5 us |
| - | Python | R, S | reported only, no target (H-9 reference) | | |

The R-raw 14-minute demonstration (HR-11) is reported against the R targets for information; it is not the R result.

### (b) Allocation after warm-up (HR-22)

| # | Language | Target |
|---|---|---|
| L4 | C++, Rust | exactly 0 heap allocations over the measured region, both workloads (counting allocator) |
| L4 | Java | no GC event and an allocation-sample total of 0 for the book's classes in the measured region; if missed, the miss is published with bytes per message |
| - | Python | `tracemalloc` peak reported, no target |

### (c) Query latency (p99; measured every 1,000th message, HR-19 complexity)

| # | Query | C++, Rust | Java |
|---|---|---:|---:|
| L5 | `best_bid`, `best_ask` | <= 50 ns | <= 100 ns |
| L5 | `qty_at` (present and absent price) | <= 100 ns | <= 200 ns |
| L5 | `top(10)` into a caller buffer | <= 200 ns | <= 400 ns |
| L5 | `top(100)` into a caller buffer | <= 1 us | <= 2 us |

Most single queries sit near the clock cost; each query p99 is reported with the clock overhead next to it, and batch timing is added under HR-21 where that overhead exceeds half the p50.

### (d) Correctness on the same replay (H-9(d), HR-18)

| # | Target |
|---|---|
| L6 | Zero mismatches: on R, every snapshot row reached by the differenced stream equals our book and the recomputed top-10 checksum ([KR-CRC]); on the raw demonstration, every form A checkpoint of `order-book.md`; the property test of `low-latency-book.md` (1,000 seeded streams, `top(100)` equal to `micro.book.rebuild` after every message). One mismatch fails the run whatever its latency. Same rule for every language, Python included |

### (e) CI regression thresholds (HR-24)

- Runner sanity ceiling: on the Actions Linux runner (unpinned, labelled) a run fails outright if any L1 to L3 p99 exceeds 3x its target above, or L4 is non-zero for C++ or Rust.
- Regression gate: after the first runner baseline, 10 runs of S on `main`; p99 threshold = max(20%, 3 x coefficient of variation of p99 across the 10 runs), raw values published; a PR whose median p99 over 3 runs exceeds the baseline by more than the threshold fails. The threshold number itself is computed from the baseline and committed with it; it is not chosen here.
- Allocation gate exact (0) for C++ and Rust in CI. Java allocation is reported in CI, not gated.
- Baseline refreshed only by its own commit with the reason.

### (f) Publication fields (H-9(f))

Every result carries: CPU model, cores, frequency governor, RAM; OS, kernel, WSL or native; compiler or runtime and version; flags (for example `-O3 -march=x86-64-v3`; `--release`, `lto`, `codegen-units = 1`; JVM flags); commit; workload file hashes; warm-up; repeats; clock overhead; the hash of the commit that added this file. Every table states "in-process, simulated feed; no network or venue latency", and for R also "crypto venue; not equities or rates" and "snapshot-differenced stream". No claim is made about network, kernel-bypass or venue round-trip latency.

## Workload R result (2026-11-19): MISS

Run on the laptop under WSL (not the acceptance machine), on the recorded window of the amended workload R (Kraken 2026-11-18 21:49:17 to 2026-11-19 03:49:17 UTC, the 6-hour gap-free window; the 16:00 to 02:00 window first named had gap rows and was not used. Form B, 100 levels; a message is a book update or a trade fill: BTC/USD 63,195 messages (31,287 book, 31,908 fills), ETH/USD 42,426 (31,287 book, 11,139 fills); input hashes in `benchmarks/results/h9/README.md`; raw files `benchmarks/results/h9/*_R_*.json`). **Correctness L6 passes: 0 mismatches in C++, Rust and Java.** **Timing L1 to L3 is a MISS**: p99 and p99.9 miss in every language and symbol, and ETH/USD p50 misses too. The targets stay as fixed on 2026-11-18 (overnight decision 2026-11-19); this result is recorded as a miss, not a pass.

| Language (target p50 / p99 / p99.9) | BTC/USD p50 / p99 / p99.9 (ns) | ETH/USD p50 / p99 / p99.9 (ns) | Verdict |
|---|---|---|---|
| C++ (100 / 500 / 2,000) | 39 / 9,223 / 21,471 | 784 / 9,631 / 23,087 | MISS (p99, p99.9; ETH p50) |
| Rust (100 / 500 / 2,000) | 47 / 8,927 / 19,695 | 755 / 8,703 / 21,151 | MISS (p99, p99.9; ETH p50) |
| Java (200 / 1,000 / 5,000) | 100 / 17,407 / 31,503 | 1,300 / 17,407 / 27,407 | MISS (p99, p99.9; ETH p50) |

The figures are the median of 5 runs, pooled over message kinds, as the headline rule requires (corrected 2026-11-19, audit HA-28: this table first showed run 1 of 5; the medians were already in `benchmarks/results/h9/README.md`, and the verdict is the same). C++ and Rust: WSL 2, pinned with `taskset -c 2`; Java: native Windows, not pinned. Clock p50 21 ns in WSL; Java `nanoTime` steps 100 ns on this machine.

Context only, not a reason to pass: a form B update applies about 58 level changes on average (one per changed level in a one-second snapshot difference), at roughly 40 ns per level, so a per-update cost of a few microseconds is what the per-level speed implies. The targets were written for one or a few levels per update (HR-19, "How the numbers were chosen" item 1). Owner decision 2026-11-19: the per-update targets stay the acceptance test and the miss stays recorded. The per-level figure (about 40 ns) is descriptive only and has no target. A per-level target, if one is wanted, is committed before a fresh recorded window is measured (v0.10.1 or later); the window already seen is never judged against it.

## Workload R2 and the per-level rows (added 2026-11-19, before any R2 timing; rulings HR-130, HR-131)

**Fixed on 2026-11-19 while the R2 window was still being recorded.** No raw file of the window had been read and no timing had been run when this section was committed; the commit hash is quoted in the results. Owner decision 2026-11-19 (stage K start file): measure the workload the R targets were written for, against unchanged targets, and set a per-level target for the one-second stream at the same time.

### (g) R2: per-message update latency on raw venue messages

The R figures of table (a) apply to R2 without change, because "How the numbers were chosen" item 1 reasons about a venue update of one or a few levels, which is what R2 replays.

| # | Language | Workload | p50 | p99 | p99.9 |
|---|---|---|---:|---:|---:|
| L1-R2 | C++ | R2 (raw venue messages, window of 6 to 8 h, 100 levels) | <= 100 ns | <= 500 ns | <= 2 us |
| L2-R2 | Rust | R2 | <= 100 ns | <= 500 ns | <= 2 us |
| L3-R2 | Java | R2 | <= 200 ns | <= 1 us | <= 5 us |

Headline as in (a): all message kinds pooled, median of 5 runs, per symbol; a row passes only if both symbols pass all three percentiles. HR-21 decides between per-message and batch timing exactly as for R and S. L4 (allocation) and L5 (queries) are measured on R2 as well and reported against their existing targets.

Correctness on R2 (L6, form A): after every message, the CRC32 of our top 10 equals the venue's `checksum` field; and for every per-second recorder row in the window, the full 100 levels a side equal our book as it stood at the last raw message received before the row's `t`. Zero top-10 checksum mismatches in each language, or the R2 run fails whatever its latency. Mismatches below level 10 (`order-book.md`: a truncated level the venue does not resend) are counted separately and published; they fail the run too, unless `order-book.md` as it stood before this change already classes that case as the venue's, in which case the count is published and the row is marked "passes with N venue-side holes".

### (h) L7: per-level cost on the one-second differenced stream

| # | Language | Sample (`low-latency-book.md` item 2b) | p50 | p99 | p99.9 |
|---|---|---|---:|---:|---:|
| L7 | C++, Rust | `apply` time / levels in the message, form B stream of the R2 window | <= 100 ns | <= 500 ns | <= 2 us |
| L7 | Java | same | <= 200 ns | <= 1 us | <= 5 us |

How the numbers were chosen, and what was already known. The figures are the R per-message targets carried over unchanged per level: item 1 above budgets one level change at tens of nanoseconds warm and a few hundred on a miss to memory, and that budget is per level, not per message. They were not fitted to a measurement. It must be said plainly that this row was written after the 2026-11-19 R run, whose descriptive mean was about 40 ns a level in C++ and Rust: the p50 is therefore expected to pass, and only the tail is an open question. For that reason L7 is a secondary row. It does not replace, soften or re-judge L1 to L3 on R, which stay a recorded MISS for the 2026-11-18/19 window, and the release notes, this file and tutorial 48 keep saying so. The headline H-9 result after this change is R2 (table g).

### Order of work (owner decision 2026-11-19)

1. Record the window, build and hash the R2 input and the form B input of the same window, run correctness, then timing; publish the first measurement as it is.
2. Only if an R2 or L7 tail still misses: a single-pass batch apply for a one-second difference may be built, as a later change with its own measurement on the same hashed inputs; the first measurement stays published next to it.
3. No target in this file changes in a change that measures.

## Mirror

Rows L1 to L7 (with L1-R2 to L3-R2) are mirrored, with a pointer to this file, in `benchmarks/targets.md` (HR-23).
