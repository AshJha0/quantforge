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

## Tonight's commands, in order (coordinator, 2026-11-19)

Git Bash at the root of a checkout of `k-h9` (PowerShell where marked). Window by HR-133: the session from 15:02:28
UTC, exactly 6 hours, so it ends 21:02:28 if nothing breaks. Measured times are for the old sample's 10-minute session
(BTC/USD 164,718 messages, ETH/USD 126,249) on this laptop on 2026-11-19; the bracketed 6-hour figures scale them by
message count (about 36 times; evidence class: inferred, not measured).

**Why the recorder is stopped first.** The window ends inside the hour file `20261119T21`, which the recorder keeps
open; a gzip file still being written has no end-of-stream marker, so the full gzip read of item 2a fails on it and
the window rule would count it as a gap at 21:00 (the session would be rejected). The recorder's STOP file closes
every file cleanly; a hard kill would leave a broken member and the same failure. So raw recording is switched off
before the build, not after.

| # | When (UTC) | Command | Sample | 6 h (inferred) |
|---|---|---|---|---|
| 0 | before 20:50 | `benchmarks/h9/run_r2.sh build` (C++, Rust in WSL; Java with the Maven mkdir lock) | MEASURED_BUILD | same |
| 1 | 21:03 | Raw off, recorder files closed: (a) `mv C:/Work/Claude/qf-crypto-data/kraken/NO_RAW.off-20261119 C:/Work/Claude/qf-crypto-data/kraken/NO_RAW`; (b) `touch C:/Work/Claude/qf-crypto-data/kraken/STOP`; (c) wait until `C:/Work/Claude/qf-crypto-data/heartbeat.json` shows `"stopped": true` and no python process runs `crypto_l2.py` (PowerShell: `Get-CimInstance Win32_Process -Filter "Name='python.exe'" \| ? CommandLine -like '*crypto_l2*'`); only if it is still alive after 60 s kill it (`Stop-Process -Id <pid>`), knowing the open hour file may then fail the gzip read; (d) PowerShell `Start-ScheduledTask "QF crypto L2"`; (e) after a minute, `ls -l C:/Work/Claude/qf-crypto-data/kraken/*-raw/` shows no new file and no size change | | 2 min |
| 2 | 21:06 | `python -I benchmarks/h9/build_r2.py auto C:/Work/Claude/qf-crypto-data/kraken C:/Work/Claude/qf-h9-r2` (must print `START 2026-11-19T15:02:28...` and an END 6 h later; exit 3 = no window, stop) | MEASURED_AUTO | 10 to 15 min |
| 3 | 21:20 | `cp C:/Work/Claude/qf-h9-r2/R2_{inputs,replay}.sha256 C:/Work/Claude/qf-h9-r2/R2_window.json benchmarks/results/h9/ && git add benchmarks/results/h9/R2_* && git commit -m "H-9 R2 input hashes (before any R2 timing)"` | | 1 min |
| 4 | 21:21 | `benchmarks/h9/run_r2.sh correct` (Python reference for both symbols in parallel with the harness passes; the counts compared; L7 dumps checked) | MEASURED_CORRECT | 40 to 50 min |
| 5 | after 4 passes | Delete the window's raw files: `rm C:/Work/Claude/qf-crypto-data/kraken/BTC-USD-raw/20261119T1[1-9]*.jsonl.gz C:/Work/Claude/qf-crypto-data/kraken/BTC-USD-raw/20261119T2*.jsonl.gz` and the same for `ETH-USD-raw`; only `20261119T11` onward, never the old `20261117T20` sample, never the per-second folders | | 1 min |
| 6 | about 22:10 | `benchmarks/h9/run_r2.sh time` (stages r2-cpp, r2-rust, r2-java, l7 in that order; QUIET already set by the coordinator is used as is) | code path only | MEASURED_TIME_EST |
| 7 | 22:45 at the latest | Stop timing (Ctrl-C). Stages that finished have complete files and markers; rerunning `time` later skips them. `STAGES="l7" benchmarks/h9/run_r2.sh time` runs one stage alone; `--skip-l7` leaves L7 out | | |
| 8 | then | `git add benchmarks/results/h9/*_R2_*.json benchmarks/results/h9/*_L7_*.json benchmarks/results/h9/correct` and write up as the R section of `benchmarks/results/h9/README.md` (median of 5 runs, min-max, met or missed) | | |

If step 4 fails, no timing runs. If time runs short, the order already puts R2 C++ and Rust first, then Java, then
L7. Keep `C:/Work/Claude/qf-h9-r2` (the pre-decoded replay input, item 2a).

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
  more messages later inside the same millisecond. This reading is fixed by ruling HR-132
  (`specifications/stage-h-rulings-audit.md`, 2026-11-19, before any file of the R2 window was read); every result
  publishes `checkpoint_matched_only_inside_tie` and `checkpoint_failed_strict_reading`.
- Below-level-10 mismatches are counted apart (targets (g)); the runner stops with exit 2 when there are any and goes
  on only with `QF_R2_BELOW10_VENUE_SIDE=1`, which only the coordinator sets (HR-132), after deciding that
  `order-book.md` as it stood before HR-130 classes them as the venue's; the decision is written into the correctness
  marker. The sample had none.
- Window rule: a gap row in either symbol's raw or per-second file ends a session. A raw snapshot that does not follow
  a gap row (a recorder restart; a killed recorder writes no gap row) is treated the same way, ending the old session
  at its last row (ruling HR-132; the recorder behaviour is inferred from `tools/recorder/crypto_l2.py`). The
  14-minute sample holds three such sessions (restarts at 20:30:28 and 20:40:47 UTC).

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
