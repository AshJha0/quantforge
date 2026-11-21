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
same three harnesses. No runner record is in this file yet.

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

**Window start rounded to 21:49:17.** The last gap row is 21:49:13.802 in BTC/USD but 21:49:16.177 in ETH/USD, after
the decided start of 21:49:16, so the window used for both symbols is 2026-11-18 21:49:17 to 2026-11-19 03:49:17 UTC
(still exactly 6 h, no gap row inside). The first book row after reconnect is 21:50:25 (BTC/USD) and 21:50:27
(ETH/USD), so the first 68-70 s of the window hold trades only.

**Recorder note.** Some recorded quantities are in exponent form (`"5.5E-7"`), which `micro.book.rebuild` rejects
as not a plain decimal string (HR-12). `benchmarks/h9/build_r.py` rewrites them in plain form, value unchanged
(checked exactly). The recorder should write plain decimals.

## Workload R input (built 2026-11-19 04:03 UTC, before any R timing)

Window 2026-11-18 21:49:17 to 2026-11-19 03:49:17 UTC; every input file passed a full gzip read and no gap row lies in the window (`build_r.py` refuses one). Built by `python -I benchmarks/h9/build_r.py`; outputs kept outside the repo (scratchpad). Warm-up = the first hour (QF_H9_WARMUP). SHA-256:

```
input BTC-USD/20261118T21.jsonl.gz sha256 5608a3b30f32af46877ae352e53f2bad89e663ed08cd0535900d85b48e66be6a
input BTC-USD/20261118T22.jsonl.gz sha256 7d0372355c7d9144378125745f6f87a39dcf51139b0de81e2bcea8af2f2fa313
input BTC-USD/20261118T23.jsonl.gz sha256 f473942c4091ab054d617ac4262396728999a5436cfbfa0bba04c215ef26eebf
input BTC-USD/20261119T00.jsonl.gz sha256 ad2ca8ae634b4eb7babf071301f56d2c8d2f416494408d9c17c586e11ef7a76d
input BTC-USD/20261119T01.jsonl.gz sha256 b0ef6ffcfb7767c1b0c562937f4b7714608af526957ae4fa68ff18792903fc3a
input BTC-USD/20261119T02.jsonl.gz sha256 2ce7fc422d3b48376513b80ef962cdaf9ffff95a306903a4ca8baa3841aff797
input BTC-USD/20261119T03.jsonl.gz sha256 5f778a67cd416a9014555c3787e117972cbef6e7436f789da319c9edcea46c33
BTC-USD: 48815 rows, 63195 messages (31287 book, 31908 trade fills), 1824755 levels; warm-up (first hour) 9322 messages; span 2026-11-18T21:50:25.086000+00:00 .. 2026-11-19T03:49:16.037000+00:00
output R_BTC-USD.bin sha256 608517351830a5b0784cfe18f12d2b7eb838108c7f739ebe19c8189ad996f235
output R_BTC-USD.msgs.jsonl sha256 2cd1807e043470c41c2b24d86fa4c459c757224f5b4e090814580c32f8169c7e
input ETH-USD/20261118T21.jsonl.gz sha256 6855c1d87cb201b535322fd79d9b54f22bf229a73b6ec55c140253f82f5acb95
input ETH-USD/20261118T22.jsonl.gz sha256 f225ee4894dbc9fffcd4d8e2b293ae4862d80be35287e0ffc8ec3f08c13c3178
input ETH-USD/20261118T23.jsonl.gz sha256 a24c9d191a3565c0372d3f73406721b2005d61bb2fcdcd9b883cef2291ca3a48
input ETH-USD/20261119T00.jsonl.gz sha256 1aa48bdcb7f37ff3a88d4e20f55f1dd2155f4343fe32314251909a11bd3c5619
input ETH-USD/20261119T01.jsonl.gz sha256 5b60fb804b79a002b3d8a40d37a3143b63e35c7860c8e2ffb3086112db973f55
input ETH-USD/20261119T02.jsonl.gz sha256 0d16900eeed4dc755cbc5999540cb1d93f70647497a5f67230620534a1908f7d
input ETH-USD/20261119T03.jsonl.gz sha256 8adaa9d58637e8be99958202201799c0acd03f34d723263cf7e019137dd030e9
ETH-USD: 38721 rows, 42426 messages (31287 book, 11139 trade fills), 1831549 levels; warm-up (first hour) 6592 messages; span 2026-11-18T21:50:27.499000+00:00 .. 2026-11-19T03:49:16.037000+00:00
output R_ETH-USD.bin sha256 0ec00235f23417a33fbdc6332d981696cbfcc986ff484b7b09eef07a1e644f40
output R_ETH-USD.msgs.jsonl sha256 8575a279cf02b6fad99e95bfe6b49a0535931edf13233aa336b9a448a41909a7
```

## Workload R correctness (all three languages)

The fast book's full top(100) after every book message (31,287 per symbol) was dumped by each harness
(`QF_H9_DUMP`) and checked by `benchmarks/h9/check_r.py` against `micro.book.rebuild` (Python, exact decimals), one
checkpoint per book message: **0 failed of 31,287, BTC/USD and ETH/USD, in C++, Rust and Java**. The final book
equals rebuild's in full, every checkpoint has 100 levels a side, 0 crossed, 0 locked. The three dumps are
byte-identical. The in-harness std::map / BTreeMap / TreeMap check also shows 0 mismatches (64 and 43 checkpoints).

## Workload R timing: crypto venue; 6-hour window, not a full day; local laptop, not the acceptance machine

Run 2026-11-19 04:03 UTC, WSL load average 0.1-0.3 (below 1.5). C++/Rust: WSL 2, `taskset -c 2`. Java: native
Windows, unpinned. Same builds and flags as for S. 5 runs; median (min-max), ns. Warm-up = first hour (9,322
messages BTC/USD, 6,592 ETH/USD; JIT warm-up for Java is therefore short). Messages: BTC/USD 63,195 (31,287 form B
updates, 31,908 trade fills), ETH/USD 42,426 (31,287 updates, 11,139 trades). The pooled figure is the target
basis. Clock p50 21 ns in WSL; Java `nanoTime` steps 100 ns here.

| Row | Lang | Symbol | Target p50 / p99 / p99.9 | pooled p50 | pooled p99 | pooled p99.9 | Met? |
|---|---|---|---|---:|---:|---:|---|
| L1 | C++ | BTC | 100 / 500 / 2,000 | 39 (39-40) | **9,223** (8,735-9,343) | **21,471** (15,279-28,143) | p50 met; p99, p99.9 missed |
| L1 | C++ | ETH | 100 / 500 / 2,000 | **784** (759-813) | **9,631** | **23,087** | all missed |
| L2 | Rust | BTC | 100 / 500 / 2,000 | 47 (45-52) | **8,927** | **19,695** | p50 met; p99, p99.9 missed |
| L2 | Rust | ETH | 100 / 500 / 2,000 | **755** (751-802) | **8,703** | **21,151** | all missed |
| L3 | Java | BTC | 200 / 1,000 / 5,000 | 100 | **17,407** | **31,503** | p50 met; p99, p99.9 missed |
| L3 | Java | ETH | 200 / 1,000 / 5,000 | **1,300** | **17,407** | **27,407** | all missed |

Per kind: the form B update alone has p50 about 2.2-2.4 us (C++/Rust) and 4.0 us (Java), and p99 9-11 us
(C++/Rust) and 18-21 us (Java). A trade has p50 27-34 ns. BTC/USD's pooled p50 passes only because half its
messages are trades. Batch timing (1,000 messages, divided), p50 / p99: C++ 1,376 / 2,055 (BTC), 2,036 / 2,739
(ETH); Rust 1,281 / 1,781, 1,887 / 2,420; Java 2,271 / 3,053, 3,599 / 5,668.

**Why R misses.** The targets were set for a message that changes one or a few levels (targets point 1, HR-19).
A form B update instead carries a whole second of changes: about 58 levels on average (1.82 M levels / 31,287
updates). Per level that is about 40 ns (C++/Rust), in line with the S figures. The miss is real against the
targets as written, and the targets are not changed (HR-23). Owner decision 2026-11-19: the per-update targets stay the acceptance test and the miss stays recorded. The per-level figure (about 40 ns) is descriptive only and has no target. A per-level target, if one is wanted, is committed before a fresh recorded window is measured (after v0.10.0); the window already seen is never judged against it.

L4: C++ and Rust 0 allocations in every measured run. Java: 792 allocated bytes per run (the same as S, taken to be
the measurement calls) and 0 GC events in the timed regions (`gc_R_*.log` not kept in the repo). L5 queries on R
(batch top(100) p99): C++ 147 / 177, Rust 181 / 181, Java 164 / 180 ns, all under 1,000 (C++/Rust) and 2,000 (Java).

Raw output: `cpp_R_BTC-USD.json`, `cpp_R_ETH-USD.json`, `rust_R_*.json`, `java_R_*.json`.

## Workload R2 and row L7: not obtained (attempt ended 2026-11-20)

Targets fixed in commit f2d90738 (low-latency-targets.md (g) and (h)) before any R2 file was read. The raw window
started recording 2026-11-19 11:41:24 UTC. The builder, the Python reference, the harness support and the runner are
in `benchmarks/h9/` (`README_R2.md` keeps the commands as a record). No R2 or L7 figure exists; the 14-minute sample
was used for correctness only and gave no timing figure.

**Outcome (read from the recorder log and `benchmarks/h9/r2_status.py`, 2026-11-20).** R2 needed one unbroken 6-hour
session (HR-134). All 30 sessions on 2026-11-19 and 2026-11-20 ended before hour 6. The drops were websocket
keepalive ping timeouts; whole-connection stalls of 50 to 107 s were seen before drops. The cause is not established:
the network path or load on the laptop could explain it, and nothing recorded tells them apart. The owner ended the
attempt on 2026-11-20 and the recorder is stopped. The workload R result of 2026-11-19 stays a recorded MISS; the
targets and the 6-hour rule are unchanged. No raw recorded row is published here, only these counts.

**A note on one monitor (inferred, 2026-11-20).** Between 13:15 and 13:24 UTC on 2026-11-20 a diagnostic monitor
started by the coordinator read the recorder's heartbeat file and most likely stopped the recorder's housekeeping
task (the heartbeat writes). Recording continued, and no session was ended by it: sessions before and after that
interval broke in the same way.
