# H-9 workload R2 and row L7: how to run

Crypto venue; not equities or rates. In-process, simulated feed; no network or venue latency. Local laptop, not the
acceptance machine.

**Plain idea.** R2 replays the venue's own book messages (one or a few levels each) instead of one-second snapshot
differences, so it measures the message the R targets were written for. L7 divides the cost of a one-second
difference by the levels it carries. Both are judged against targets that were committed before any R2 file was read
(`specifications/09-microstructure/low-latency-targets.md` (g) and (h), commit f2d90738; rulings HR-130 and HR-131).
Correctness runs first, in every language and in the Python reference; timing refuses to start unless it passed.

**Formal statement.** The window rule, the warm-up (first hour), the truncation inside the timed `apply` and the form A
correctness rule are those of `low-latency-book.md` item 2a and targets (g); the L7 sample is item 2b. Nothing here
changes a target, a threshold or a rule (evidence class: read, 2026-11-19).

## Commands, in order (coordinator, after the raw window has closed)

All from Git Bash at the root of a checkout of this branch, Python through `uv` in `python/`. Times are for the
14-minute sample's 10-minute session (BTC/USD 164,718 messages, ETH/USD 126,249; measured 2026-11-19 on this laptop)
and, in brackets, an estimate for an 8-hour window scaled by message count (about 48 times the sample; evidence class:
inferred, not measured).

1. Choose the window (the rule of item 2a; prints the attempts and `START ... END ...`; reads every hourly file of both
   symbols once, raw and per-second, in full):

   `python -I benchmarks/h9/build_r2.py window C:/Work/Claude/qf-crypto-data/kraken`

   About 3 s on the sample (about 3 min for 8 hours). Exit 3 and `NO WINDOW` if no session qualifies: then R2 is not
   run and the row stays open.
2. Build both symbols' inputs and the hash files (same rule, then the builder; also builds the form B stream of the
   same window with `build_r.py` for L7):

   `python -I benchmarks/h9/build_r2.py auto C:/Work/Claude/qf-crypto-data/kraken C:/Work/Claude/qf-h9-r2`

   About 13 s on the sample (about 10 min for 8 hours). Writes `R2_<SYM>.{bin,cps.bin,msgs.jsonl,rows.jsonl,meta.json}`,
   `L7_<SYM>.{bin,msgs.jsonl}`, `R2_window.json`, `R2_inputs.sha256` (recorder files) and `R2_replay.sha256` (built
   files).
3. Fix the inputs before any timing: copy `R2_inputs.sha256`, `R2_replay.sha256` and `R2_window.json` to
   `benchmarks/results/h9/` and commit them. The runner refuses to run without the committed `R2_replay.sha256`.
4. Build the harnesses: `benchmarks/h9/run_r2.sh build` (C++ Release and Rust `--release` in WSL under the WSL lock,
   Java with Maven on Windows; a few minutes, most of it the C++ core library on a cold build directory).
5. Correctness: `benchmarks/h9/run_r2.sh correct`. For each symbol: form A in C++, Rust and Java (harness with 0 timed
   runs), the Python reference `check_r2.py` (micro.book.rebuild, 6 worker processes), the counts compared field by
   field (`r2_meta.py compare`); the form B input dumped by each language and checked with `check_r.py`. Writes
   `benchmarks/results/h9/correct/R2_correctness.ok` only if all of it passes. Sample: about 2.5 min, nearly all of it
   the Python reference (about 1 hour for 8 hours, the reference again dominating; BTC/USD and ETH/USD run one after
   the other).
6. Timing: `benchmarks/h9/run_r2.sh time` (sets the QUIET flag while it runs; 5 runs per language, R2 then L7, both
   symbols). Refuses unless step 5's marker matches the same input hashes and the same commit. No timing figure was
   taken from the sample (smoke runs only checked that the code path works); the R2 timing for 8 hours is estimated at
   10 to 20 min in all (inferred from the R run of 2026-11-19, which took a few minutes for 63,195 messages).
7. Then `git add benchmarks/results/h9/*_R2_*.json benchmarks/results/h9/*_L7_*.json` and write up the result as the R
   section of `benchmarks/results/h9/README.md` does (median of 5 runs, min-max, met or missed).
8. Delete the raw files of the window once the replay input is built and checked (item 2a); keep `C:/Work/Claude/qf-h9-r2`.

`run_r2.sh all` is steps 5 and 6 in one go.

## What is checked, and one decision for the coordinator

- Venue checksum: after every raw book message, the CRC32 of our top 10 against the `checksum` Kraken sent ([KR-CRC]).
  On the sample: 163,707 of 163,707 (BTC/USD) and 125,772 of 125,772 (ETH/USD) equal, in C++, Rust, Java and Python.
- Per-second rows: each recorder row against our full 100 levels a side "at the last raw message received before the
  row's t". The recorder stamps receive times to the millisecond and one websocket frame can carry many messages, so up
  to 39 messages share a row's millisecond on the sample; their order relative to the row is not recorded. A row is
  therefore compared after each message from "lo" (last message with t < row t, the strict reading) to "hi" (last
  with t <= row t, micro.book.rebuild's own checkpoint rule) and passes if it equals the book at one of them. The
  counts at lo, at hi and only inside the tie are published with every result. On the sample: BTC/USD 846 rows, all
  equal (573 at lo, 811 at hi, 16 only inside the tie, 292 rows with a tie); ETH/USD 895 rows, all equal (722, 831, 19,
  218). Under the strict reading alone 273 and 173 rows would count as mismatches although the book is right one or
  more messages later inside the same millisecond. **Coordinator decision needed:** confirm that the millisecond range
  is the reading of "the last raw message received before the row's t" that targets (g) means, or say which other.
- Below-level-10 mismatches are counted apart (targets (g)); the runner stops with exit 2 when there are any and goes
  on only with `QF_R2_BELOW10_VENUE_SIDE=1`, which the coordinator sets only after deciding that `order-book.md` as it
  stood before HR-130 classes them as the venue's; the decision is written into the correctness marker. The sample
  had none.
- Window rule: a gap row in either symbol's raw or per-second file ends a session. A raw snapshot that does not follow
  a gap row (a recorder restart; a killed recorder writes no gap row) is treated the same way, ending the old session
  at its last row. The 14-minute sample holds three such sessions (restarts at 20:30:28 and 20:40:47 UTC). This
  reading is ours (evidence class: inferred from `tools/recorder/crypto_l2.py`), and the coordinator may overrule it.

## Development on the sample

`--tolerant` and `--until` exist only for the damaged 2026-11-17 sample (three gzip members cut short by restarts):

    python -I benchmarks/h9/build_r2.py auto C:/Work/Claude/qf-crypto-data/kraken <scratch> \
      --after 2026-11-17T20:00:00Z --until 2026-11-17T21:00:00Z --min-hours 0.1 --tolerant
    SMOKE=1 R2DIR=<scratch> OUT=<scratch>/out benchmarks/h9/run_r2.sh all

A tolerant build is marked `"tolerant": true` in its meta file and is never a workload input. Recorded rows from these
files are never committed.

## Files

| File | What it is |
|---|---|
| `build_r2.py` | window rule, R2 builder (QFH9S001 + checkpoints), form B by `build_r.py` |
| `check_r2.py` | Python reference for form A on `micro.book.rebuild` |
| `r2_meta.py` | compares the four sets of counts; stamps the publication fields of targets (f) |
| `run_r2.sh` | build, correct, time |
| `cpp26/bench/lowlat_r2.hpp`, `rust/.../lowlat_book.rs`, `java25/.../FastBookFormA.java` | form A pass and L7 sample in each harness |
