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

## The per-session routine (ruling HR-134)

**Plain idea.** No session on 2026-11-19 reached 6 hours (four were cut by network drops, the longest 3 h 20 min), so
there is no fixed evening any more. Raw recording stays on, and the R2 window is the FIRST recorder session, on any
day, that runs 6 hours from its first raw snapshot with no gap row or restart in either symbol, taken as exactly
those 6 hours, whatever its content; no later session may be preferred (HR-134, owner decision 2026-11-19; read in
`specifications/stage-h-rulings-audit.md`). A session cut by the nightly shutdown simply does not qualify; one that
crosses midnight can.

**At each start of the laptop or of a working session**, from Git Bash at the root of a checkout:

1. `python -I benchmarks/h9/r2_status.py status C:/Work/Claude/qf-crypto-data/kraken`. Read-only and safe while the
   recorder runs: it reads the recorder log, the names, sizes and times of the data files, and the per-second files
   only for gap rows (a line is parsed only if it holds `"k":"gap"`); it never opens a raw message file. It prints
   every session since 2026-11-19 11:41:24 UTC with start, end, length and why it was rejected, then either
   `window: none yet` (exit 3; nothing to do) or the qualifying session (exit 0).
2. If a window qualified: stop the recorder cleanly, even if the status does not say `window complete at HH:MM:SS;
   stop the recorder cleanly before building`. The hour file the window ends in may still be open (a gzip member
   without its end marker), and the full gzip read of item 2a needs it closed. (a) `touch C:/Work/Claude/qf-crypto-data/kraken/STOP`;
   (b) wait until `C:/Work/Claude/qf-crypto-data/heartbeat.json` shows `"stopped": true` (a hard kill would leave a
   broken member and reject the window).
3. Confirm and build: `python -I benchmarks/h9/build_r2.py window C:/Work/Claude/qf-crypto-data/kraken` must print the
   same window as the status (it is the deciding check: it reads every hour file of every session in time order).
   If it does not, restart the recorder as it was (PowerShell `Start-ScheduledTask "QF crypto L2"`) and go back to
   step 1. If it does: `mv C:/Work/Claude/qf-crypto-data/kraken/NO_RAW.off-20261119 C:/Work/Claude/qf-crypto-data/kraken/NO_RAW`
   (the restarted recorder then writes no raw files), `Start-ScheduledTask "QF crypto L2"` (per-second recording
   resumes), and `python -I benchmarks/h9/build_r2.py auto C:/Work/Claude/qf-crypto-data/kraken C:/Work/Claude/qf-h9-r2`
   (exit 3 = no window, exit 5 = a window file is still open). No option may be given: every non-default option
   needs `--sample-only`, is stamped into `R2_window.json` and is refused by `run_r2.sh` (HR-135).
4. Commit the hashes before anything is timed: `cp C:/Work/Claude/qf-h9-r2/R2_{inputs,replay}.sha256 C:/Work/Claude/qf-h9-r2/R2_window.json benchmarks/results/h9/`
   and commit them (`R2_window.json` holds the session list with each end cause and the options; it is in
   `R2_replay.sha256`).
5. Correctness: `benchmarks/h9/run_r2.sh correct`. If it fails, including the tie guard of HR-135, no timing runs.
6. Timing: `benchmarks/h9/run_r2.sh time` (stages r2-cpp, r2-rust, r2-java, l7 in that order; a stopped run keeps
   the stages that finished, and a rerun skips them).
7. Raw off: once the inputs are built, hashed and checked, raw recording stays off (`NO_RAW` from step 3). Delete the
   window's raw files after step 5 passes; keep `C:/Work/Claude/qf-h9-r2` (the pre-decoded replay input, item 2a).
8. Cleanup: `python -I benchmarks/h9/r2_status.py cleanup C:/Work/Claude/qf-crypto-data/kraken` lists (dry run) the
   raw hour files that belong only to rejected sessions; add `--delete` to delete exactly those. It never lists the
   per-second folders, the 2026-11-17 sample (`20261117T20*`), files before 2026-11-19 11:00, or any file whose hour
   overlaps the qualifying session, an open session that could still qualify, a session not examined, or no known
   session (each widened by 5 minutes). Rejected sessions' files can also be cleaned at any earlier start: the
   helper never touches a session that could still qualify.

Without a qualifying window, only step 1 (and, if wanted, step 8) is done. Old figures measured on the 2026-11-17
sample (10-minute session on this laptop, 2026-11-19; evidence class: measured, development only): build 26 s for
both symbols, correctness 131 s, a timing pass of 1 run per stage 38 s; a 6-hour window is about 36 times the
messages (inferred).

## What is checked, and one decision for the coordinator

- Venue checksum: after every raw book message, the CRC32 of our top 10 against the `checksum` Kraken sent ([KR-CRC]).
  On the sample: 163,707 of 163,707 (BTC/USD) and 125,772 of 125,772 (ETH/USD) equal, in C++, Rust, Java and Python.
- Per-second rows: each recorder row against our full 100 levels a side "at the last raw message received before the
  row's t". The recorder stamps receive times to the millisecond and one websocket frame can carry many messages, so up
  to 39 messages share a row's millisecond on the sample; their order relative to the row is not recorded. A row is
  therefore compared after each message from "lo" (last message with t < row t, the strict reading) to "hi" (last
  with t <= row t, micro.book.rebuild's own checkpoint rule) and passes if it equals the book after at least one of
  them (HR-132 as clarified by HR-135). The
  counts at lo, at hi and only inside the tie are published with every result. On the sample: BTC/USD 846 rows, all
  equal (573 at lo, 811 at hi, 16 only inside the tie, 292 rows with a tie); ETH/USD 895 rows, all equal (722, 831, 19,
  218). Under the strict reading alone 273 and 173 rows would count as mismatches although the book is right one or
  more messages later inside the same millisecond. This reading is fixed by ruling HR-132
  (`specifications/stage-h-rulings-audit.md`, 2026-11-19, before any file of the R2 window was read); every result
  publishes `checkpoint_matched_only_inside_tie` and `checkpoint_failed_strict_reading`.
- Tie guard (HR-135): the tie reading can hide only a below-level-10 error, and only on rows with a tie; a row
  with no tie is compared exactly and catches any such error still in the book (a constructed one-message lag is
  in `python/tests/test_h9_r2_hr134.py`). Per symbol, rows without a tie must be at least 25 % of the checked rows
  and rows matched only inside the tie at most 6 %, or the correctness step fails (`r2_meta.py compare`). The
  sample's counts above pass it.
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

    python -I benchmarks/h9/build_r2.py auto C:/Work/Claude/qf-crypto-data/kraken <scratch> --sample-only \
      --after 2026-11-17T20:00:00Z --until 2026-11-17T21:00:00Z --min-hours 0.1 --tolerant
    SMOKE=1 R2DIR=<scratch> OUT=<scratch>/out benchmarks/h9/run_r2.sh all

A tolerant or sample-only build is marked `"tolerant": true` or `"sample_only": true` in its meta file, its
options are in `R2_window.json`, and `run_r2.sh` refuses it outside `SMOKE=1`: it is never a workload input. Recorded rows from these
files are never committed.

## Files

| File | What it is |
|---|---|
| `build_r2.py` | window rule (HR-134), R2 builder (QFH9S001 + checkpoints), form B by `build_r.py` |
| `r2_status.py` | read-only session status while recording; cleanup of rejected sessions' raw files |
| `check_r2.py` | Python reference for form A on `micro.book.rebuild` |
| `r2_meta.py` | compares the four sets of counts and applies the tie guard; refuses sample-only inputs; stamps the publication fields of targets (f) |
| `run_r2.sh` | build, correct, time |
| `cpp26/bench/lowlat_r2.hpp`, `rust/.../lowlat_book.rs`, `java25/.../FastBookFormA.java` | form A pass and L7 sample in each harness |
