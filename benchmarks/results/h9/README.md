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
- **Workload R not run.** It needs the first complete UTC day at 100 levels, which is 2026-11-18 at the earliest
  (low-latency-book.md, Workloads). At the time of these runs (2026-11-18, about 16:30 UTC) that day is not over, so
  no complete day exists. R runs once 2026-11-18 is recorded in full with no gap row and its file hashes are fixed.
  The L1 to L3 R rows stay open.
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
index upkeep. An intermediate session with the same top-of-book cache and a 24-byte index slot (counts inline),
clock p50 15 ns, met every C++ L5 row (qty_at present p99 84 ns, absent 65) and Rust missed only qty_at absent
(103 ns); its JSON was overwritten by the final run and is not published as a result. qty_at present p50 is 26 ns
(C++) and 32 ns (Rust), close to the clock cost: the p99 is set by one cold cache line per query (queries run every
1,000th message), and the single-sample p99 includes the clock read. HR-21 batch timing for queries is not
implemented yet, so no batch figure is given for them.

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

Raw output: `cpp_S.json`, `rust_S.json` (before), `cpp_S_after.json`, `rust_S_after.json`, `java_S.json`.
