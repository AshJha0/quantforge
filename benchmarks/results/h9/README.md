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

## HR-21 query batch timing (workload S; C++/Rust WSL pinned, Java native Windows)

HR-21: when the clock's own p50 is more than half the measured p50, batch timing is also reported and the report
says which figure is the headline. Here the clock p50 (C++ 29 ns, Rust 30 ns in this session; Java 100 ns) is
at or above every query's single-sample p50, so **batch timing is the headline for L5**. At every 1,000th
measured message each query runs 1,000 times in a row and the total is divided by 1,000.

**First batch harness, withdrawn.** The first version (`*_hr21.json`) gave "<1 ns" for best_bid/best_ask. That was
a loop-invariant load the compiler hoisted, not a measurement, so it does not count toward any target.

**Corrected harness** (`*_hr21b.json`):
- Every iteration takes its side or price from a precomputed array, indexed through the previous result. This
  forms a dependency chain, so the figure is latency, not throughput.
- Each iteration's result is fed into a sink: an empty `asm volatile` barrier with a memory clobber in C++,
  `std::hint::black_box` on the book and on the accumulator in Rust, and in Java a separate method per loop
  returning its accumulator (Blackhole-style).
- Check: every per-call figure is now at least 1 ns, against a clock cost amortised to about 0.03 ns per call.
  In C++ and Rust the barrier forces the cached best to be reloaded on every iteration. In Java the JIT can still
  hoist a plain field load, and the JIT code was not inspected. Java best_* is therefore a lower bound.

This session ran on a loaded machine: the WSL load average stayed near 2, because the wait for it to fall below
0.7 timed out after 40 minutes, and the clock itself cost 29-30 ns against 15-17 ns earlier. The absent-price
loop wraps at 512 ticks.

| Row | Query | Target C++/Rust (Java) | C++ batch p50 / p99 | Rust batch p50 / p99 | Java batch p50 / p99 |
|---|---|---:|---:|---:|---:|
| L5 | best_bid | 50 (100) | 1 / 2 | 2 / 3 | 1 / 4 (lower bound) |
| L5 | best_ask | 50 (100) | 1 / 2 | 2 / 3 | 1 / 4 (lower bound) |
| L5 | qty_at present | 100 (200) | 14 / 49 | 13 / 54 | 13 / 47 |
| L5 | qty_at absent | 100 (200) | 2 / 5 | 5 / 25 | 2 / 6 |
| L5 | top(10) | 200 (400) | 11 / 51 | 27 / 109 | 26 / 80 |
| L5 | top(100) | 1,000 (2,000) | 28 / 99 | 46 / 179 | 46 / 144 |

Median of 5 runs (ns). With the batch headline every L5 row is met in all three languages. The single-sample
figures from the previous session remain published alongside (C++ qty_at present p99 103 ns, a 3 ns miss on that
basis). Java updates in this session (batch): p50 103 ns, p99 327, p99.9 1,978; the p99.9 range across runs was
320 to 12,527 ns, so one run came within 30 ns of the 12.5 us target. 0 GC events.

Before/after in brief, query p99 (ns), single sample unless marked batch:

| Query | C++ first | C++ after cache/index | C++ HR-21 batch (corrected) | Rust first | Rust after cache/index | Rust HR-21 batch (corrected) |
|---|---:|---:|---:|---:|---:|---:|
| best_bid | 26 | 45 | 2 | 105 | 43 | 3 |
| best_ask | 22 | 42 | 2 | 53 | 39 | 3 |
| qty_at present | 120 | 197 | 49 | 99 | 130 | 54 |

The GitHub-runner record (the controlled machine) comes from the manual `lowlat-book` workflow, which runs the
same three harnesses. It has not been dispatched yet, because the branch is not pushed.

Raw output: `cpp_S_hr21b.json`, `rust_S_hr21b.json`, `java_S_hr21b.json` (corrected HR-21); `*_hr21.json` (withdrawn batch figures); `cpp_S.json`, `rust_S.json` (before), `cpp_S_after.json`, `rust_S_after.json`, `java_S.json`.

## Workload R window check (2026-11-19): not run, window shorter than 6 hours

Spec amended first (owner decision 2026-11-19: R = longest unbroken recorded window of at least 6 hours, window
2026-11-18 16:00 to 2026-11-19 02:00 UTC). Every hourly file in the window passed a full `gzip` read (python -I),
both symbols, except `20261118T16.jsonl.gz`, which is empty (0 bytes of content; the hour is in `T16-1`, starting
16:00:21). But the files carry gap rows (identical times in BTC/USD and ETH/USD, so recorder reconnects):
16:13:26; 17:46:08; 18:50:14, 18:51:02; 20:07:03, 20:19:47, 20:24:36; eighteen between 21:19:28 and 21:49:16 (book
rows missing for about 31 minutes in hour 21). The longest stretch with no gap row is 21:49:16 to 02:00:00, about
4 h 11 min, below the 6-hour minimum, so under the amended spec **R is not run**; no R timing or correctness run was
made. The L1 to L3 R rows stay open. No gap row from 21:49 to 02:00, so if recording stayed clean past 02:00 a
6-hour window ending about 03:50 UTC would qualify; that needs an owner ruling (it is outside the named window).

**Coordinator decision (2026-11-19, under owner delegation, before any R timing was seen):** R window =
2026-11-18 21:49:16 to 2026-11-19 03:49:16 UTC (exactly 6 h), if the files through hour 03 pass a full gzip read
and have no gap row in the window. Recorded in `low-latency-book.md`.

**What the gap rows are.** Every one is a websocket reconnect written by the recorder (`crypto_l2.py`, "gap record on
every reconnect"), none a checksum resync: 8 x `ConnectionClosedError: sent 1011 (internal error) keepalive ping
timeout; no close frame received`, and 17 x `TimeoutError: timed out during opening handshake` (the reconnect
attempts in hour 21, about 1.5 min apart, are network loss on the laptop side or the venue's side; not
distinguished here). `recorder.log` shows a fresh 100-level snapshot after each successful reconnect. Worth
checking in the recorder: the keepalive ping interval/timeout, and backoff during the handshake timeouts.
