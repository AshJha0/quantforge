# K-5 race-test evidence (lane k-v1-k5, 2026-11-20)

Latency-aware analytics on simulated data; local laptop, not the acceptance machine. Nothing here is timed. Spec `specifications/12-platform/lock-free-snapshots.md` 0.2.0 (PROPOSED); rulings KR-280 to KR-288 (PROPOSED). Reviewer: none: self-assessment; no second review (owner decision 2026-11-18). Every figure below is measured on 2026-11-20 unless marked otherwise.

## Java (Windows 11, Temurin 25.0.5, Maven 3.9.9)

- JUnit `LiveSnapshotTest`, 8 tests, 0 failures: scenario values at 1e-9 relative, checksum pinned values, exactness on 1,000 publishes (bit for bit), corrupted field detected, writer rules, race scenario P = 20,000 with R = 1, 4, 16: reads 558,785, 3,299,302 and 16,923,345; torn 0, non-monotone 0, mismatched 0, final version seen by every reader.
- jcstress 0.16, quick mode (`mvn -Pjcstress -DskipTests package exec:exec@jcstress`), full output in `jcstress_quick_local.txt`:
  - `SnapshotPublishTest`: 53,775,386 samples; `0, 1` (initial, whole) 33,572,139; `1, 1` (published, whole) 20,203,247; FORBIDDEN 0.
  - `InPlaceMutationFault` (planted fault 3): 221,902,449 samples, of which 112,579 mixed (`0, 1`): jcstress sees the fault. Graded ACCEPTABLE_INTERESTING by design.
  - "Failed tests: No matches. Error tests: No matches."
- Default mode (the CI job `java25-jcstress`): not run locally.

## C++ (WSL Ubuntu, clang 21.1.8, `-fsanitize=thread`, RelWithDebInfo, `-DQF_WERROR=ON`)

Built with `cmake -DQF_SANITIZE=thread -DQF_WERROR=ON` (whole `quantforge_core` instrumented), target `qf_snapshot_race`; the two new files also compile clean under g++ 15.2 with `-Werror -Wconversion -Wshadow`. `TSAN_OPTIONS=halt_on_error=1`.

- `qf_snapshot_race unit`: 0 failures (scenario values, checksum pinned values, exactness on 1,000 publishes bit for bit, corrupted field detected, pool and reader-index rules, a held snapshot unchanged through 50 publishes).
- Race, P = 20,000 (default mode), ThreadSanitizer reports 0 races and exit 0 at each R:
  - R = 1: 315,329 reads; R = 4: 2,612,375 reads; R = 16: 57,114,340 reads. Torn 0, non-monotone 0, mismatched 0, final version seen by every reader.
- Planted faults (R = 4, P = 20,000; rerun with `symbolize=0` because the local `llvm-symbolizer-21` crashed with "CachedFileStream was not committed" while symbolizing, which hid the report text in the first run):
  - fault 1 `relaxed`: exit 66, "SUMMARY: ThreadSanitizer: data race" reported.
  - fault 2 `skip`: exit 66, "SUMMARY: ThreadSanitizer: data race" reported.
- Long mode not run locally: R = 16 took 26 s at P = 20,000 under ThreadSanitizer, so P = 1,000,000 was stopped after about 10 minutes to free the shared WSL lock; the long mode (1,000,000 at R = 1 and 4, 200,000 at R = 16) runs in the CI job `sanitizers-tsan`, not yet run.

## Rust

Not run under ThreadSanitizer locally: the pinned toolchain 1.99.1 is stable, and `-Zsanitizer=thread` needs nightly (KR-285). The CI job `rust-tsan` runs it on `nightly-2026-11-01` in long mode with both planted faults; it has not run yet at the time of writing. Without a sanitizer (WSL, toolchain 1.99.1): `cargo fmt --check` and `cargo clippy -p quantforge-core --all-targets -D warnings` clean; `tests/snapshot_race.rs` 7 tests pass (scenario values, checksum, exactness on 1,000 publishes, corrupted field, pool rules, race P = 20,000 with R = 1, 4, 16: reads 787,777, 3,236,364 and 9,210,504; torn 0, non-monotone 0, mismatched 0, final version seen). Without a sanitizer this shows the semantics, not the absence of data races.

## Python (Windows 11)

`python/tests/test_live_snapshot.py`, 21 tests pass: reference semantics only. Python is not lock-free.
