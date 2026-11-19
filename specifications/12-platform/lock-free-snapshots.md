# Lock-free snapshots, low-latency risk and real-time hedge (K-5b)

Spec version 0.1.0-proposed (stage K wave 3, lane k-w3-spec, 2026-11-19). Status: PROPOSED; nothing here is built or run. Rulings KR-190 to KR-199 (`stage-k-rulings-w3.md`). Plan items: 14.8 K-5 (the race-test and label parts; the error-bound part is K-5a, `06-risk/intraday-risk-bounds.md`, confirmed); 14.10 rule 1. House method for targets: `09-microstructure/low-latency-targets.md` (H-9).

**Every output, table and page of this item says "latency-aware analytics on simulated data".** The market moves are generated from `core.rng`; no feed, venue or network is involved, and no claim is made about network, kernel or venue latency.

**Plain idea.** One thread (the writer) owns the market state. When the state changes it builds a new, complete, read-only copy (a snapshot), then makes it visible with one atomic pointer store. Many threads (the readers) price and hedge from whatever snapshot is current. Because a snapshot is never changed after it is published, a reader can never see half of an update. The hard part is not publishing; it is knowing when an old snapshot can be reused, because a slow reader may still be looking at it. Java leaves that to the garbage collector. C++ and Rust use hazard pointers: each reader announces which snapshot it is holding, and the writer reuses a slot only when no reader has announced it.

## Sources

| Ref | What | Evidence class |
|---|---|---|
| [HP] | M. M. Michael, "Hazard pointers: safe memory reclamation for lock-free objects", *IEEE Transactions on Parallel and Distributed Systems* 15(6), 2004 | recalled (not opened tonight); algorithm restated below and checked by the race tests, not by the citation |
| [ACQ] | C++ `std::atomic<std::shared_ptr>`, `https://en.cppreference.com/w/cpp/memory/shared_ptr/atomic2`, read 2026-11-19: `is_always_lock_free` is "implementation-defined"; the type is not required to be lock-free. This is why C++ does not use it here | read |
| [ARC] | `arc-swap` 1.9.5 docs, `https://docs.rs/arc-swap/latest/arc_swap/` and its performance and limitations pages, read 2026-11-19: reads "always lock-free", "Most of the time ... wait-free"; mentions "debt storage/stripped down hazard pointers"; MIT OR Apache-2.0. Used only as a design comparison (KR-191) | read |
| [EBR] | `crossbeam-epoch` 0.9.21 docs, read 2026-11-19: epoch-based reclamation; garbage freed once no pinned thread can reach it. Considered and not chosen (KR-191) | read |
| [TSAN] | `https://clang.llvm.org/docs/ThreadSanitizer.html`, read 2026-11-19: detects data races; "about 5x-15x" slowdown; status beta; code not built with `-fsanitize=thread` "may fail to detect races" | read |
| [JCS] | `https://github.com/openjdk/jcstress`, read 2026-11-19: harness for JVM concurrency correctness; tests are probabilistic; outcomes graded acceptable, forbidden or special (interesting); GPL-2.0 (a test tool, not linked into the library) | read |
| [LOOM] | `https://github.com/tokio-rs/loom`, read 2026-11-19: permutes executions under the C11 memory model; treats SeqCst loads and stores as AcqRel (false alarms possible); does not explore load-buffering executions, so not sound; MIT | read |
| [MIRI] | `https://github.com/rust-lang/miri`, read 2026-11-19 (page truncated): detects data races, emulates some weak-memory effects, one execution per seed, `-Zmiri-many-seeds` | read (partly) |
| [VH] | Java `VarHandle` acquire/release modes: the Oracle API page could not be fetched on 2026-11-19 | recalled |
| [H9] | `09-microstructure/low-latency-targets.md`: targets fixed before measurement, first measurement published as it is, a miss recorded as a miss, figures from first principles labelled as recalled | read (repository) |

## 1. The snapshot

A snapshot is an immutable value: `version` (u64, strictly increasing), `as_of` (logical event number, not wall time), the market state (the zero-rate pillars of the stage F golden 12-pillar SOFR curve, as binary64), and the derived numbers the writer computes once per publish (§3). Fixed size: at most 4 KiB, no pointers to mutable data. In C++ and Rust the snapshot lives in a slot of a fixed pool allocated at start-up; in Java it is a record whose fields are final.

## 2. Algorithm (KR-190, KR-191)

**Java.** One `volatile` field (or a `VarHandle` with `setRelease` / `getAcquire` [VH]) holds the current record. Writer: build the record, then one release store. Reader: one acquire load, then read the record's final fields. Reclamation: the garbage collector. Progress: publish and read are each a single access, wait-free on the JVM's own terms (inferred; a JVM safepoint can still pause any thread, which is reported in the p99.9 as in H-9).

**C++ and Rust: single-writer hazard pointers over a fixed pool [HP].** `R` registered readers (fixed at start-up, at most 64), pool of `R + 2` slots, `current` an atomic slot index, `hp[0..R)` atomic slot indices with `NONE`.

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
f = any slot that is not current and not in {hp[0..R)}  # scan R hazards (seq_cst loads)
build the new snapshot in slot[f]                         # plain writes; no reader can hold f
current.store(f, seq_cst)
```
Why a free slot always exists: at most `R` slots are announced and one is current, so of `R + 2` slots at least one is free (pigeonhole). Why a reader never sees a slot being written: the writer only writes a slot no reader has announced at scan time; a reader that announces it afterwards re-checks `current`, which no longer names that slot, and retries.

Progress claimed (KR-192): **writer wait-free** (one scan of `R` hazards, bounded); **reader lock-free, not wait-free**: a reader retries only when a publish happened between its two loads of `current`, so some thread always makes progress, but a reader can in principle be starved by a writer publishing continuously. No heap allocation after start-up. Memory bound: `(R + 2) x 4 KiB`.

Not chosen (KR-191): `std::atomic<std::shared_ptr>` (not required lock-free [ACQ]); epoch-based reclamation [EBR] (a stalled reader holds back all reclamation, which an unbounded pool would need); `arc-swap` [ARC] as a library dependency (a third-party crate in the numerical library; it stays a reference for a comparison benchmark in tests only, if wanted); a seqlock (a writer stalled mid-write blocks every reader, so readers are not lock-free).

## 3. What "low-latency risk" and "real-time hedge" compute (KR-193)

Only existing library operations; no new maths and no new goldens for numbers.

| Where | Operation | Computes |
|---|---|---|
| writer, per publish | `risk.curve.key_rate` | key-rate DV01s of the book on the snapshot curve |
| writer, per publish | `hedge.greeks.neutralise` (or `hedge.solve` where the book needs the general form) | hedge ratios that neutralise the key-rate exposure with the stage F instrument set |
| reader, per simulated move | `risk.intraday.delta_gamma_bound` | estimate of the book P&L for a parallel shift and its Taylor bound (K-5a, confirmed) |

**Exactness rule (KR-194).** A number read through a snapshot is bit-identical to calling the same operation directly with the same inputs: the snapshot stores results, it does no arithmetic of its own. Tested on 1,000 publishes per language.

## 4. Race tests (KR-195)

| Language | Tool | Scenarios |
|---|---|---|
| C++ | ThreadSanitizer [TSAN] (clang, `-fsanitize=thread`, CI job beside `sanitizers.yml`; WSL locally) | 1 writer, R = 1, 4, 16 readers; 1,000,000 publishes; every reader checks the invariant `field_k == f(version, k)` for all fields of the slot it holds, and that `version` never decreases for that reader |
| Rust | loom [LOOM] on the pool with R = 2 and 3 publishes (the state space must stay small); Miri [MIRI] with `-Zmiri-many-seeds=0..64` on the same small test; TSan (nightly `-Zsanitizer=thread`) on the 1,000,000-publish stress test if the toolchain supports it on the runner, else reported as not run | same invariants |
| Java | jcstress [JCS] | Actor writer publishes version v with fields derived from v; actor reader reads; outcome "fields from two versions" FORBIDDEN, "initial or any whole version" ACCEPTABLE |

**Clean** means: TSan reports 0 races; loom finds no failing interleaving; Miri reports no undefined behaviour; jcstress reports no FORBIDDEN outcome in its default mode.

**Planted faults (plan 14.10 rule 1).** A race test counts as built only when each of these is shown failing, with the run recorded:
1. C++ and Rust: `current.store` and `load` changed to relaxed: TSan and loom must report it.
2. C++ and Rust: writer skips the hazard scan and reuses the oldest slot: TSan (stress) and loom must report the race on slot contents.
3. Java: a mutable snapshot updated in place instead of published: jcstress must show the FORBIDDEN mixed outcome.
4. All: invariant checker fed a slot with one field corrupted: the reader check must fail (proves the checker runs).
loom's own limits [LOOM] mean a loom pass is evidence, not proof; TSan's [TSAN] mean only code built with the sanitizer is covered. Both are stated with the results.

## 5. Targets (fixed before any timing run; H-9 method, KR-196)

**Fixed in the commit that confirms this spec, before any K-5b code exists.** The first measurement is published as it is; a missed target is a miss and is not retuned in the change that measures; a target changes only in its own later commit with a reason, before the next measurement [H9].

How the numbers were chosen (first principles, recalled orders of magnitude, no outside benchmark cited): an acquire is two loads of one cache line and one store to the reader's own line; with no publish in between that is tens of nanoseconds, near the clock cost (about 21 ns in WSL, H-9). A publish scans R hazard lines (R = 4: four cache lines) and stores one; building the snapshot is excluded because it is the library's own time. `risk.intraday.delta_gamma_bound` on 100 positions is 100 `exp` calls and a sum: about 2 us. Java allowed 2x, its p99.9 2.5x, as in H-9.

| # | Measure (median of 5 runs, pinned core, R = 4 readers on 4 cores, 1,000,000 publishes) | C++, Rust p50 / p99 / p99.9 | Java p50 / p99 / p99.9 |
|---|---|---|---|
| S1 | reader acquire + release, no concurrent publish | <= 50 ns / 200 ns / 1 us | <= 100 ns / 400 ns / 2.5 us |
| S2 | reader acquire + release, writer publishing every 1 us | <= 100 ns / 1 us / 5 us | <= 200 ns / 2 us / 12.5 us |
| S3 | writer publish (scan + store; build excluded) | <= 100 ns / 500 ns / 2 us | <= 200 ns / 1 us / 5 us |
| S4 | tick to estimate: acquire, `risk.intraday.delta_gamma_bound` on a 100-position book, release | <= 5 us / 10 us / 25 us | <= 10 us / 20 us / 62.5 us |
| S5 | heap allocation after warm-up | exactly 0 (C++, Rust) | reported, no target |

Workload: shifts drawn from `core.rng` seed 20261109, N(0, 5 bp), book of 100 zero positions from seed 20261110. HR-21's rule applies: where a p50 is below twice the clock cost, batch timing is the headline and the report says so. Publication fields as H-9 (f): CPU, OS, WSL or native, compiler and flags, commit, workload hashes, clock overhead, "local laptop, not the acceptance machine", and the label above. Python: reported only.

## Acceptance tests (PROPOSED)

| ID | Plan | Test |
|---|---|---|
| LF1 | K-5 | §4 race tests clean in C++ (TSan), Rust (loom and Miri; TSan if available) and Java (jcstress) |
| LF2 | 14.10 rule 1 | each §4 planted fault shown failing, run recorded |
| LF3 | K-5 | §3 exactness on 1,000 publishes per language |
| LF4 | K-5 | label present on every output and results table |
| LF5 | H-9 method | S1 to S5 measured after this file's targets are committed; result published with PASS or MISS per row |

## Out of scope

- Any claim about end-to-end trading latency, network, kernel bypass or venue round trip.
- Multiple writers; NUMA placement; real-time OS scheduling.
- New risk or hedge maths; any operation not already in the libraries.
- Python race tests (Python has no K-5b implementation; it stays the reference for numbers only).

## Limits

- Reader progress is lock-free, not wait-free (§2); a starvation scenario is possible in principle and is not tested for.
- A jcstress or loom pass is probabilistic or bounded evidence; neither proves the absence of races.
- Targets are first-principles ceilings, not measured; the laptop is not the acceptance machine.
