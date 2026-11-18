# H-9 low-latency book: first measurement (2026-11-18)

**Local WSL, laptop, not the acceptance machine.** In-process, simulated feed; no network or venue latency.
Targets: `specifications/09-microstructure/low-latency-targets.md`, fixed in commit fa020dd8 before any timing run
(HR-23); not changed here. Published as measured, met or missed.

## Setup
- Machine: Intel Core 5 120U, 12 logical CPUs, WSL 2 (kernel 6.18.58.1-microsoft-standard-WSL2), 7 GB RAM given to
  WSL, frequency governor not exposed under WSL. Other WSL jobs from parallel lanes may have run at the same time
  (the shared lock serialises builds and runs that take it, not every process).
- Pinned: `taskset -c 2`, one thread. Flags: C++ g++ 15.2.0, CMake Release (`-O3`, no `-march`), `-ffp-contract=off`;
  Rust 1.99.1, `--release` workspace default profile (no LTO, default codegen units).
- Workload S only: core.rng seed 20261117, 10,000,000 messages (10,032,349 levels), file SHA-256
  `df9aeb5c48149bf107ad913c95c6ef825bbeaf4bccb0c5cb9ca9f1dfa6cc0bf3` (written by `qf_lowlat_book gen`; both languages
  read the same file). Warm-up 1,000,000 messages; 9,000,000 measured; 5 runs; figures are the median of runs
  (min-max). Unpaced replay, so no coordinated-omission correction.
- **Workload R not run**: the first complete UTC day at 100 levels (2026-11-18 at the earliest) is not yet recorded
  in full; the R-raw 14-minute demonstration was also not run in this change. L1/L2 R rows are open.
- Correctness in the same process (L6): 10,000 checkpoints of top(100) both sides against a std transcription of
  order-book.md, 0 mismatches in both languages. Property test (1,000 streams x 10,000 messages) and the ob_h goldens
  pass in `cpp26/tests/test_fast_book.cpp` and `rust/crates/quantforge-core/tests/fast_book.rs`.

## Results, workload S (ns)

| Row | Metric | Target | C++ | Rust | Verdict |
|---|---|---:|---:|---:|---|
| L1/L2 | update p50 | <= 150 | 39 (39-39) | 47 (46-59) | met |
| L1/L2 | update p99 | <= 1,000 | 80 (80-81) | 94 (88-117) | met |
| L1/L2 | update p99.9 | <= 5,000 | 264 (259-267) | 242 (221-247) | met |
| L4 | allocations, measured region | 0 | 0 every run | 0 every run | met |
| L5 | best_bid p99 | <= 50 | 26 | 105 (99-148) | C++ met; **Rust missed** |
| L5 | best_ask p99 | <= 50 | 22 | 53 (51-78) | C++ met; **Rust missed** |
| L5 | qty_at present p99 | <= 100 | 120 (86-149) | 99 (94-147) | **C++ missed**; Rust met |
| L5 | qty_at absent p99 | <= 100 | 28 | 52 | met |
| L5 | top(10) p99 | <= 200 | 69 | 56 | met |
| L5 | top(100) p99 | <= 1,000 | 73 | 76 | met |

Clock overhead (1,000,000 empty pairs, not subtracted): C++ `clock_gettime` p50 15 ns, p99 16; Rust `Instant` p50
17 ns, p99 18. Clock p50 is below half the update p50, so per-message timing is the headline; batch timing
(1,000 messages per sample) is in the JSON: C++ p50 28, Rust 35. Query samples (9,000 per run) sit near the clock
cost and were timed singly; HR-21 batch timing for queries was not added in this run, so the L5 misses are stated
as single-sample figures and include the clock read. Lookups outside the 8-level touch window: 3.44 million per
C++ run (published share, spec "Limit cases"); buffer growths: 0.

Raw output: `cpp_S.json`, `rust_S.json` (all percentiles per op kind, per run). Java (L3) not implemented in
this change.
