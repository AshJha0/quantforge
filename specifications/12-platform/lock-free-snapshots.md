# Lock-free snapshots, low-latency risk and real-time hedge (K-5)

Spec version 0.2.0-proposed (stage K, lane k-v1-k5, 2026-11-20). Status: **PROPOSED**; not normative until the stage K coordinator confirms each ruling. Rulings KR-280 to KR-288 (`stage-k-rulings-k5.md`). Built from the proposal 0.1.0 of lane k-w3-spec (branch `k-w3-spec`, rulings KR-190 to KR-196 there, renumbered here because those numbers collide on `k-v1`); section "Changes from 0.1.0" lists what differs. Plan item 14.8 K-5 (the snapshot, race-test, hedge and label parts; the error-bound part is K-5a, `06-risk/intraday-risk-bounds.md`, confirmed). Reviewer: none: self-assessment; no second review (owner decision 2026-11-18).

**Every output, table and page of this item says "latency-aware analytics on simulated data".** The market moves come from a fixed integer rule (KR-287); no feed, venue or network is involved, and no claim is made about network, kernel or venue latency. Any timing figure is from a local laptop, not the acceptance machine, and none is published by this lane (no measured file exists yet).

**Plain idea.** One thread (the writer) owns the market state. When the state changes it builds a new, complete, read-only copy (a snapshot), then makes it visible with one atomic store. Many threads (the readers) price and hedge from whatever snapshot is current. Because a snapshot is never changed after it is published, a reader can never see half of an update. The hard part is not publishing; it is knowing when an old snapshot's memory can be reused, because a slow reader may still be looking at it. Java leaves that to the garbage collector. C++ and Rust use hazard pointers over a fixed pool: each reader announces which slot it holds, and the writer reuses only a slot that no reader has announced.

## Sources

| Ref | What | Evidence class |
|---|---|---|
| [HP] | M. M. Michael, "Hazard pointers: safe memory reclamation for lock-free objects", *IEEE Transactions on Parallel and Distributed Systems* 15(6), 2004 | recalled; the algorithm is restated in section 2 and checked by the race tests, not by the citation |
| [ACQ] | C++ `std::atomic<std::shared_ptr>`, cppreference page `memory/shared_ptr/atomic2`: `is_always_lock_free` is implementation-defined | read by lane k-w3-spec on 2026-11-19 (quoted in its 0.1.0 proposal); not reopened here |
| [TSAN] | `https://clang.llvm.org/docs/ThreadSanitizer.html`: detects data races; 5x to 15x slowdown; code not built with `-fsanitize=thread` may hide races | read by lane k-w3-spec on 2026-11-19; not reopened here |
| [JCS] | `https://github.com/openjdk/jcstress`: JVM concurrency harness; tests are probabilistic; outcomes graded ACCEPTABLE, FORBIDDEN or ACCEPTABLE_INTERESTING; GPL-2.0 with the Classpath exception, a test tool not linked into the library | read by lane k-w3-spec on 2026-11-19; version 0.16 pinned here from Maven Central metadata (read 2026-11-20) |
| [JMM] | Java `VarHandle` acquire and release modes; `final` field semantics (JLS 17.5) | recalled |

## 1. The snapshot (KR-280)

A snapshot is an immutable value of fixed size (72 bytes; at most 4 KiB is the rule): `version` (u64, strictly increasing), `as_of` (u64 logical event number, not wall time), `shift` (the cumulative parallel yield move of the simulated market, binary64), five derived numbers the writer computes once per publish (section 3), and `check`, a 64-bit checksum over the other eight fields (KR-287). In C++ and Rust it lives in a slot of a fixed pool allocated at start-up; in Java it is a record whose fields are final; in Python a frozen dataclass.

**Guarantees.**
1. *No torn read.* A reader sees either the whole of one published snapshot or the whole of another; never fields from two. Tested: every read recomputes `check`.
2. *Monotone versions per reader.* Successive reads by one reader never return a smaller `version`. Tested on every read.
3. *Final version seen.* After the writer's last publish, every reader eventually reads it. Tested: readers stop only on the final version.
4. *Bounded staleness, stated not timed.* A read returns the snapshot that was current at the reader's validating load of `current` (the linearisation point); a snapshot is therefore stale by at most the publishes that happen during the reader's use of it. No bound in time is claimed (no measurement exists, section 5).
5. *Exactness (KR-284).* The snapshot stores results and does no arithmetic of its own: every number read through it is bit-identical to calling the same functions directly with the same inputs.

## 2. Algorithm (KR-280, KR-281, KR-282)

**Java.** One `AtomicReference` holds the current record. Writer: build the record, then `setRelease`. Reader: `getAcquire`, then read the record's final fields. Reclamation: the garbage collector. A second concurrent writer is refused (a `compareAndSet` on a writer flag), and a version that does not increase is refused.

**C++ and Rust: single-writer hazard pointers over a fixed pool [HP].** `R` registered readers (fixed at construction, 1 to 64), a pool of `R + 2` slots, `current` an atomic slot index, `hp[0..R)` atomic slot indices with `NONE`, each on its own cache line.

Reader `i`, acquire:
```
loop:
    s = current.load(acquire)
    hp[i].store(s, seq_cst)
    if current.load(seq_cst) == s: return slot[s]   # announced before the writer could reuse it
release: hp[i].store(NONE, release)
```
Writer, publish:
```
f = a slot that is not current and not in {hp[0..R)}  # scan R hazards (seq_cst loads)
write the new snapshot into slot[f]                    # plain writes; no reader can hold f
current.store(f, seq_cst)
```
Why a free slot always exists: at most `R` slots are announced and one is current, so of `R + 2` slots at least one is free (pigeonhole). Why a reader never reads a slot being written: the writer writes only a slot that no reader had announced at its scan; a reader that announces that slot later re-checks `current`; if the check passes, the store it read was made after the write finished, so the write happens-before the read. Why the writer never overwrites a slot a reader still holds: the reader's announcement precedes its validating load, which precedes (in the single total order of the `seq_cst` operations) the writer's next store to `current`, and so the writer's next scan sees the announcement. If a reader's slot is reused and republished between its two loads (an ABA on the slot index), the reader validates against the newer publish and reads that whole snapshot, which keeps guarantees 1 and 2.

Progress claimed (KR-282): **writer wait-free** (one scan of `R` hazards, bounded); **reader lock-free, not wait-free**: a reader retries only when a publish happened between its two loads of `current`, so some thread always makes progress, but a reader can in principle be starved by a writer publishing without pause. No heap allocation after construction. Memory: `(R + 2)` slots.

Not chosen (KR-281): `std::atomic<std::shared_ptr>` (not required to be lock-free [ACQ]; its reference count also writes to shared memory on every read); epoch-based reclamation (a stalled reader holds back all reclamation); a third-party crate such as `arc-swap` (no new dependency in the numerical library); a seqlock (a writer stalled mid-write blocks every reader, so readers are not lock-free, and a seqlock reader reads racing memory, which ThreadSanitizer and the Rust and C++ memory models count as a data race unless every field is atomic). Python is a correctness reference only and **is not lock-free**: a publish takes a `threading.Lock` (to refuse a second writer) and a read is one reference load of a frozen object.

## 3. What "low-latency risk" and "real-time hedge" compute (KR-283)

The book is the zero-coupon book of `risk.intraday.delta_gamma_bound`; the market state is one cumulative parallel shift `h`. Per publish the writer computes, in this order:

| Field | Computation |
|---|---|
| `estimate_pnl`, `bound` | `risk.intraday.delta_gamma_bound(book, h)` (K-5a, confirmed, spec 1.1.0) |
| `book_delta` | `fsum_i(-T_i * (N_i * exp(-(y_i + h) * T_i)))`, exactly rounded sum |
| `hedge_unit_delta` | `-T_H * exp(-(y_H + h) * T_H)`, one unit of the hedge zero `(T_H, y_H)` |
| `hedge_notional` | `-book_delta / hedge_unit_delta` |

**Plain idea.** The book's value moves by about `book_delta x h` for a small parallel move. A position of `q` units of the hedge zero moves by `q x hedge_unit_delta x h`. Choosing `q = -book_delta / hedge_unit_delta` makes the two cancel to first order: that `q` is the hedge recommendation. It is a number; no order is formed and no venue is involved. **Worked example** (scenario version 1, `h = 0.005`, `datasets/scenarios/k5_snapshot.json`): `book_delta = 12,740,024.149`, `hedge_unit_delta = -6.37628` (`T_H = 10`, `y_H = 0.04`: `-10 exp(-0.45)`), so `hedge_notional = 1,998,033.51` units; `estimate_pnl = 67,545.44` with `bound = 458.73`.

Changed from the 0.1.0 proposal (KR-283): the writer does not call `risk.curve.key_rate` or `hedge.greeks.neutralise`. `hedge.greeks.neutralise` hedges a Black-Scholes book of options, not the zero-coupon book whose risk the reader reports, so a snapshot holding both would hedge a different book from the one it measures. The parallel-delta hedge above is three lines of new arithmetic, stated here; it is a library function in each build (`book_delta`, `hedge_unit_delta`), **not a CLI operation**, so it has no golden and no error-order cases. Making it a CLI operation (a new name in the `hedge` namespace) needs goldens in all four builds including two-error cases; that is left (section "Not done").

## 4. Race tests and planted faults (KR-285, KR-288)

Shared scenario (KR-287): `datasets/scenarios/k5_snapshot.json`, written by `datasets/scenarios/build_k5_snapshot.py` (20-position book drawn once from `random.Random(20261120)` and written in full; hedge zero `T_H = 10`, `y_H = 0.04`; version `k` has `as_of = k` and `shift = ((k * 7919) mod 401 - 200) * 5e-5`, version 0 has shift 0; expected values at ten versions from the Python build, compared by every build at 1e-9 relative). Checksum: `c = 0x9E3779B97F4A7C15`; for each of the eight 64-bit words (`version`, `as_of`, then the IEEE bit patterns of the six numbers in the order of section 3 after `shift`) `c = rotl64(c xor w, 27) * 0x94D049BB133111EB mod 2^64`. Pinned values: no words gives the seed; `[0]` gives `0xF6E599AEF89D022F`; `[1, 2, 3]` gives `0x8517CC75DE438E52`.

Race scenario: one writer publishes versions 1 to `P`; `R` readers read until each sees version `P`, checking on every read that `check` matches (no torn read) and that `version` does not decrease; every 64th read is compared field by field with a fresh direct computation for its version (exactness under concurrency). `P` = 20,000 by default and 1,000,000 in the long mode (`QF_SNAPSHOT_PUBLISHES`); `R` in {1, 4, 16}.

| Build | Tool | Where it runs |
|---|---|---|
| C++ | ThreadSanitizer (clang, `-fsanitize=thread`), race test `cpp26/tests/test_snapshot_race.cpp` | WSL locally and the CI job `sanitizers-tsan` |
| Rust | ThreadSanitizer (nightly `-Zsanitizer=thread`, `-Zbuild-std`) on `rust/crates/quantforge-core/tests/snapshot_race.rs` | CI only (job `rust-tsan`): the pinned toolchain 1.99.1 is stable and cannot build with a sanitizer. The same test runs without the sanitizer in the normal Rust job. loom is not a dependency and Miri needs nightly; neither is used (KR-285) |
| Java | jcstress 0.16 (profile `jcstress`, `java25/src/jcstress/java`), plus a JUnit race test of the scenario | Windows locally and the CI job `java25-jcstress` |
| Python | `threading`, reference semantics only | Windows locally and the Python CI job |

**Clean** means: ThreadSanitizer reports 0 races and exits 0; jcstress reports no FORBIDDEN outcome; every reader check holds.

**Planted faults (plan 14.10 rule 1; KR-288).** A race test counts as built only when each fault it can see is shown failing, with the run recorded. The faults are selected at construction through a test-only parameter that defaults to none:
1. C++ and Rust `RelaxedPublish`: `current` stored and loaded relaxed. ThreadSanitizer must report a race on slot contents.
2. C++ and Rust `SkipHazardScan`: the writer reuses the slot after `current` without scanning hazards. ThreadSanitizer must report the race, and the reader checks may fail.
3. Java: a mutable snapshot updated in place instead of published (jcstress class `InPlaceMutationFault`): jcstress must show the mixed outcome, graded ACCEPTABLE_INTERESTING so the default run stays green, with its count recorded.
4. All builds: a snapshot with one field changed after the checksum was taken: the reader check must fail.

Limits: a jcstress pass is probabilistic evidence; ThreadSanitizer covers only executions that happened and only code built with it; neither proves the absence of races.

## 5. Targets (KR-286; fixed here, before any timing run)

Kept from the 0.1.0 proposal unchanged, H-9 method (`09-microstructure/low-latency-targets.md`): first measurement published as it is, a miss stays a miss, a target changes only in its own later commit with a reason. **No timing run exists. This lane measured nothing and claims no latency.**

| # | Measure (median of 5 runs, pinned core, R = 4 readers, 1,000,000 publishes) | C++, Rust p50 / p99 / p99.9 | Java p50 / p99 / p99.9 |
|---|---|---|---|
| S1 | reader acquire + release, no concurrent publish | <= 50 ns / 200 ns / 1 us | <= 100 ns / 400 ns / 2.5 us |
| S2 | reader acquire + release, writer publishing every 1 us | <= 100 ns / 1 us / 5 us | <= 200 ns / 2 us / 12.5 us |
| S3 | writer publish (scan + store; build excluded) | <= 100 ns / 500 ns / 2 us | <= 200 ns / 1 us / 5 us |
| S4 | tick to estimate: acquire, `risk.intraday.delta_gamma_bound` on a 100-position book, release | <= 5 us / 10 us / 25 us | <= 10 us / 20 us / 62.5 us |
| S5 | heap allocation after warm-up | exactly 0 (C++, Rust) | reported, no target |

The figures are first-principles ceilings (recalled orders of magnitude, from the 0.1.0 proposal); none is measured.

## Acceptance tests (PROPOSED)

| ID | Plan | Test |
|---|---|---|
| LF1 | K-5 | section 4 race tests clean: C++ (TSan), Rust (TSan, CI), Java (jcstress) |
| LF2 | 14.10 rule 1 | each section 4 planted fault shown failing, run recorded |
| LF3 | K-5 | section 1 exactness on 1,000 publishes per build |
| LF4 | K-5 | label present on every output and results table |
| LF5 | H-9 method | S1 to S5 measured after this file's targets are committed; PASS or MISS per row |
| LF6 | K-5 | every build reproduces the scenario's expected values at 1e-9 relative |

## Not done (stated, 2026-11-20)

- LF5: no timing harness and no measurement.
- The hedge is a library function, not a CLI operation: no goldens, no oracle check beyond the Python reference values of the scenario file.
- Rust under ThreadSanitizer runs in CI only; no local run. loom and Miri are not used.

## Out of scope

- Any claim about end-to-end trading latency, network, kernel bypass or venue round trip.
- Multiple writers; NUMA placement; real-time scheduling.
- Orders of any kind: the hedge is a recommended quantity only.

## Changes from 0.1.0 (lane k-w3-spec)

- Rulings renumbered KR-190..196 to KR-280..286; KR-287 (scenario and checksum) and KR-288 (fault parameter) are new.
- KR-283 replaces key-rate and `hedge.greeks.neutralise` with the parallel-delta zero hedge (section 3).
- KR-285: Rust loom and Miri dropped (loom is not a dependency; no new dependency); Rust TSan CI only. Java's planted fault graded ACCEPTABLE_INTERESTING, not FORBIDDEN, so the default jcstress run stays green while still recording the count.
- Python now has a reference build of the semantics (0.1.0 had none).
