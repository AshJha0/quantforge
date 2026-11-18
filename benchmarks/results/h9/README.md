# H-9 low-latency book: measurements (2026-11-18)

**Local, laptop, not the acceptance machine.** In-process, simulated feed; no network or venue latency.
Targets: `specifications/09-microstructure/low-latency-targets.md`, fixed in commit fa020dd8 before any timing run
(HR-23); not changed by any of these runs. Each figure is published as measured, met or missed.

## Setup
- Machine: Intel Core 5 120U laptop, 12 logical CPUs. C++ and Rust: WSL 2 (kernel 6.18.58.1-microsoft-standard-WSL2,
  7 GB), pinned `taskset -c 2`, one thread, frequency governor not exposed. Java: native Windows 11, unpinned, one
  thread. Other lanes' jobs share the laptop; the clock cost moved between sessions (C++ p50 15 ns, then 21 ns),
  which shows the machine state changed, so sessions are not strictly comparable.
- Flags: C++ g++ 15.2.0, CMake Release (`-O3`, no `-march`), `-ffp-contract=off`. Rust 1.99.1, `--release` workspace
  default profile (no LTO). Java Temurin 25.0.5, `-Xms2g -Xmx2g -XX:+AlwaysPreTouch`, G1, JFR `settings=profile`,
  `-Xlog:gc`.
- Workload S only: core.rng seed 20261117, 10,000,000 messages (10,032,349 levels), SHA-256
  `df9aeb5c48149bf107ad913c95c6ef825bbeaf4bccb0c5cb9ca9f1dfa6cc0bf3` (written by `qf_lowlat_book gen`; all three
  languages read the same file). Warm-up 1,000,000 messages; 9,000,000 measured; 5 runs; median of runs (min-max).
  Unpaced replay, so no coordinated-omission correction.
- **Workload R not run.** R needs one complete recorded UTC day at 100 levels with no gap row
  (low-latency-book.md, Workloads), its file hashes fixed before any timing. The recorder was being killed by its
  watchdog until a fix made on 2026-11-18, so days up to and including the fix are damaged or partial and will not
  be used. The earliest eligible day is the first full UTC day after the fix has been verified in operation. The
  L1 to L3 R rows stay open until then.
- Correctness in the same process (L6): 10,000 top(100) checkpoints against a std/TreeMap transcription, 0 mismatches
  in every language. The property test (1,000 streams x 10,000 messages; top(100), qty_at and the cached best after
  every message) and the ob_h goldens pass in all three ports.

## Change between the two C++/Rust measurements
"Before" (`cpp_S.json`, `rust_S.json`): best_* read the sorted array's top; qty_at searched the sorted array
(8-level scan from the touch, then binary search). "After" (`cpp_S_after.json`, `rust_S_after.json`): best_* read a
top-of-book cache refreshed at the end of each apply; qty_at reads a direct-mapped index on the tick grid
(price mod 1,024; counts kept in a separate 4 KB array), falling back to the sorted search only when two present
prices share a slot (0 fallbacks on S).

## Workload S, C++ and Rust (ns; L1/L2 and L4/L5)

| Row | Metric | Target | C++ before | C++ after | Rust before | Rust after |
|---|---|---:|---:|---:|---:|---:|
| L1/L2 | update p50 | <= 150 | 39 | 60 (55-66) | 47 | 57 (54-65) |
| L1/L2 | update p99 | <= 1,000 | 80 | 147 (125-172) | 94 | 121 (113-149) |
| L1/L2 | update p99.9 | <= 5,000 | 264 | 326 (318-343) | 242 | 301 (284-314) |
| L4 | allocations, measured | 0 | 0 | 0 | 0 | 0 |
| L5 | best_bid p99 | <= 50 | 26 | 45 (39-61) | **105** | 43 (37-51) |
| L5 | best_ask p99 | <= 50 | 22 | 42 (37-57) | **53** | 39 (32-42) |
| L5 | qty_at present p99 | <= 100 | **120** | **197 (150-219)** | 99 | **130 (110-153)** |
| L5 | qty_at absent p99 | <= 100 | 28 | 61 (58-63) | 52 | 65 (58-84) |
| L5 | top(10) p99 | <= 200 | 69 | 83 (71-87) | 56 | 69 (61-87) |
| L5 | top(100) p99 | <= 1,000 | 73 | 116 (95-119) | 76 | 100 (84-121) |

Bold = missed. The "after" session ran with the clock itself 40% slower (C++ p50 21 ns against 15 ns before), so
every row moved up, update rows included, although the update path itself changed only by the cache refresh and
index upkeep. Anecdotal only: an intermediate session (top-of-book cache, 24-byte index slot with counts inline, clock p50
15 ns) printed C++ qty_at present p99 84 ns and Rust qty_at absent p99 103 ns. Its JSON was overwritten and is not
a result. qty_at present p50 is 26 ns
(C++) and 32 ns (Rust), close to the clock cost: the p99 is set by one cold cache line per query (queries run every
1,000th message), and the single-sample p99 includes the clock read. HR-21 batch timing for queries came in the next
change (below).

## Workload S, Java (ns; L3 and L5; native Windows, unpinned)

`System.nanoTime` on this Windows machine ticks in 100 ns steps (clock overhead p50 100 ns, above half the update
p50), so under HR-21 **batch timing is the headline** for updates; single-sample query figures are quantised to
100 ns and cannot resolve the 100 ns targets.

| Row | Metric | Target | Java |
|---|---|---:|---:|
| L3 | update p50 (batch, headline) | <= 300 | 125 (113-131) |
| L3 | update p99 (batch) | <= 2,000 | 309 (273-319) |
| L3 | update p99.9 (batch) | <= 12,500 | 561 (472-928) |
| L3 | update p50 / p99 / p99.9 (per message, 100 ns ticks) | as above | 200 / 500 / 700 |
| L4 | GC events in measured region; JFR allocation samples in the book's classes | 0; 0 | 0 GC every run; 0 samples (book samples only in `Side` construction, before timing) |
| L5 | best_bid / best_ask p99 | <= 100 | **200 / 200** (clock-quantised) |
| L5 | qty_at present / absent p99 | <= 200 | **300** / 200 |
| L5 | top(10) p99 | <= 400 | 300 |
| L5 | top(100) p99 | <= 2,000 | 400 |

The thread's allocated bytes over each measured region were 792, the same in every run and in the batch region,
which runs no queries; JFR attributes no allocation to `FastBook`, so the 792 bytes are taken to be the
measurement calls themselves. This is not proven here. GC log: two young pauses during file load and the
correctness pass, none in any timed region.

## HR-21 query batch timing (workload S, final code; C++/Rust WSL pinned, Java native Windows)

HR-21: when the clock's own p50 is more than half the measured p50, batch timing is also reported and the report
says which figure is the headline. Here the clock p50 (C++ 16 ns, Rust 17 ns, Java 100 ns) is close to or above
every query's single-sample p50, so **batch timing is the headline for L5**. At every 1,000th measured message each
query runs 1,000 times in a row and the total is divided by 1,000. Prices cycle (present prices over the side's
levels; absent prices over best ask + 5 + j). So these are warm-cache, back-to-back figures. The single-sample p99
includes one clock read and usually a cold cache line, and is kept alongside. This C++/Rust session began with WSL
load average 3.6 from other lanes' jobs, even though the harness waited for load to fall below 0.7 before taking
the lock. The absent-price loop runs past 1,024 ticks, so it also exercises the shared-slot fallback (163,843
fallbacks per run, all from that loop).

| Row | Query | Target C++/Rust (Java) | C++ batch p50 / p99 | C++ single p99 | Rust batch p50 / p99 | Rust single p99 | Java batch p50 / p99 | Java single p99 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| L5 | best_bid | 50 (100) | 0 / 0 * | 26 | 0 / 0 * | 36 | 0 / 0 * | 200 |
| L5 | best_ask | 50 (100) | 0 / 0 * | 28 | 0 / 0 * | 34 | 0 / 1 * | 200 |
| L5 | qty_at present | 100 (200) | 2 / 3 | 103 | 2 / 4 | 91 | 8 / 26 | 300 |
| L5 | qty_at absent | 100 (200) | 1 / 2 | 30 | 2 / 3 | 60 | 4 / 10 | 200 |
| L5 | top(10) | 200 (400) | 4 / 7 | 59 | 9 / 17 | 59 | 23 / 58 | 300 |
| L5 | top(100) | 1,000 (2,000) | 11 / 30 | 62 | 17 / 44 | 80 | 41 / 149 | 400 |

Median of 5 runs (ns). * Under 1 ns per call: the cached best is a field read, and the compiler or JIT very
likely hoisted it out of the loop. These batch figures show only that the call costs less than a nanosecond;
they are not a measurement of the query.

Verdict, with the batch headline: every L5 row is met in all three languages. On the single-sample figures,
kept for comparison: C++ qty_at present p99 is 103 ns against 100, a miss by 3 ns. Rust met every single-sample
L5 row in this session. Java best_* and qty_at present miss, but the Windows clock steps in 100 ns, so those
single-sample figures cannot resolve the targets. In this session, update p50/p99/p99.9 were C++ 48/101/290 ns,
Rust 52/103/244 ns and Java (batch) 122/315/506 ns, all met; allocations were 0 (C++, Rust), and Java had 0 GC
events and 0 allocation samples in the book's classes.

Before/after in brief, query p99 (ns), single sample unless marked batch:

| Query | C++ first | C++ after cache/index | C++ HR-21 batch | Rust first | Rust after cache/index | Rust HR-21 batch |
|---|---:|---:|---:|---:|---:|---:|
| best_bid | 26 | 45 | <1 | 105 | 43 | <1 |
| best_ask | 22 | 42 | <1 | 53 | 39 | <1 |
| qty_at present | 120 | 197 | 3 | 99 | 130 | 4 |

The GitHub-runner record (the controlled machine) comes from the manual `lowlat-book` workflow, which runs the
same three harnesses. It has not been dispatched yet, because the branch is not pushed.

Raw output: `cpp_S_hr21.json`, `rust_S_hr21.json`, `java_S_hr21.json` (HR-21 session); `cpp_S.json`, `rust_S.json` (before), `cpp_S_after.json`, `rust_S_after.json`, `java_S.json`.
