//! H-9 harness, Rust (`specifications/09-microstructure/low-latency-book.md`, "Harness"; targets in
//! `low-latency-targets.md`). Reads workload S as written by the C++ `qf_lowlat_book gen` (same bytes, same hash).
//!
//! `cargo run --release -p quantforge-bench --bin lowlat_book -- <file> [runs] [out.json]`
//!
//! Same method as the C++ harness: correctness pass first (std transcription, top(100) every 1,000 messages);
//! warm-up 1,000,000 messages unmeasured, allocation counter reset; `Instant` read before and after each `apply`;
//! HDR-style histogram (3 significant digits, 1 ns to 10 s), per op kind and pooled; queries timed every 1,000th
//! measured message; clock cost on 1,000,000 empty pairs, not subtracted; batch timing (1,000 per sample).
//! Allocation (H-9(b)): a counting `#[global_allocator]`.
//!
//! Workload R2 and row L7 (2026-11-19, `low-latency-book.md` items 2a and 2b; targets (g) and (h)): `QF_H9_CHECKPOINTS`
//! names the checkpoint file of `benchmarks/h9/build_r2.py` and adds the form A pass (venue checksum after every book
//! message, every per-second row over its millisecond range), outside the timed region; `QF_H9_PER_LEVEL=1` adds the
//! L7 sample (apply time / levels, rounded up) through a separate instantiation of the timed loop, so the R and S
//! loops are unchanged. Every run records the 1-minute load average (`/proc/loadavg`) at its start and end.
use quantforge_core::fast_book::{Book, Level, Msg, MsgType};
use quantforge_core::rng::Xoshiro;
use std::alloc::{GlobalAlloc, Layout, System};
use std::collections::BTreeMap;
use std::hint::black_box;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;

struct Counting;
static ALLOCS: AtomicU64 = AtomicU64::new(0);
// SAFETY: forwards to the system allocator unchanged; only counts calls.
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1, Ordering::Relaxed);
        // SAFETY: same contract as the caller's.
        unsafe { System.alloc(l) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        // SAFETY: same contract as the caller's.
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1, Ordering::Relaxed);
        // SAFETY: same contract as the caller's.
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        ALLOCS.fetch_add(1, Ordering::Relaxed);
        // SAFETY: same contract as the caller's.
        unsafe { System.realloc(p, l, n) }
    }
}
#[global_allocator]
static GLOBAL: Counting = Counting;

const DEPTH: usize = 100;
const WARMUP: usize = 1_000_000;
const SEED: u64 = 20_261_117;
const KINDS: [&str; 8] = [
    "snapshot",
    "add",
    "modify",
    "delete",
    "trade",
    "sweep",
    "refill",
    "truncated_price",
];
const QUERIES: [&str; 6] = [
    "best_bid",
    "best_ask",
    "qty_at_present",
    "qty_at_absent",
    "top10",
    "top100",
];

/// `HdrHistogram`'s bucket rule at 3 significant digits (2048 sub-buckets, unit 1 ns, highest 10 s).
struct Hist {
    counts: Vec<u64>,
    n: u64,
    sum: u64,
    mn: u64,
    mx: u64,
}

impl Hist {
    const MAX: u64 = 10_000_000_000;
    fn index(v: u64) -> usize {
        let bucket = 64 - (v | 2047).leading_zeros() as usize - 11;
        (bucket << 10) + (v >> bucket) as usize
    }
    fn highest(i: usize) -> u64 {
        let (mut b, mut sub) = (i >> 10, i - ((i >> 10) << 10));
        if b > 0 && sub < 1024 {
            b -= 1;
            sub += 1024;
        }
        ((sub as u64 + 1) << b) - 1
    }
    fn new() -> Hist {
        Hist {
            counts: vec![0; Hist::index(Hist::MAX) + 1],
            n: 0,
            sum: 0,
            mn: u64::MAX,
            mx: 0,
        }
    }
    fn record(&mut self, v: u64) {
        let v = v.min(Hist::MAX);
        self.counts[Hist::index(v)] += 1;
        self.n += 1;
        self.sum += v;
        self.mn = self.mn.min(v);
        self.mx = self.mx.max(v);
    }
    fn pct(&self, p: f64) -> u64 {
        if self.n == 0 {
            return 0;
        }
        let rank = ((p / 100.0 * self.n as f64 + 0.5) as u64).max(1);
        let mut acc = 0;
        for (i, c) in self.counts.iter().enumerate() {
            acc += c;
            if acc >= rank {
                return Hist::highest(i).min(self.mx);
            }
        }
        self.mx
    }
    fn json(&self) -> String {
        if self.n == 0 {
            return "{\"count\":0}".into();
        }
        let p9999 = if self.n >= 1_000_000 {
            format!("\"p99_99\":{},", self.pct(99.99))
        } else {
            String::new()
        };
        format!(
            "{{\"count\":{},\"min\":{},\"p50\":{},\"p90\":{},\"p99\":{},\"p99_9\":{},{p9999}\"max\":{},\"mean\":{:.2}}}",
            self.n,
            self.mn,
            self.pct(50.0),
            self.pct(90.0),
            self.pct(99.0),
            self.pct(99.9),
            self.mx,
            self.sum as f64 / self.n as f64
        )
    }
}

fn read_stream(path: &str) -> (Vec<Msg>, Vec<Level>) {
    let b = std::fs::read(path).expect("read workload");
    assert_eq!(&b[..8], b"QFH9S001", "not a workload S file");
    let u64at = |o: usize| u64::from_le_bytes(b[o..o + 8].try_into().expect("8 bytes"));
    let u16at = |o: usize| u16::from_le_bytes(b[o..o + 2].try_into().expect("2 bytes"));
    let u32at = |o: usize| u32::from_le_bytes(b[o..o + 4].try_into().expect("4 bytes"));
    let (nm, nl) = (u64at(8) as usize, u64at(16) as usize);
    let mut msgs = Vec::with_capacity(nm);
    for k in 0..nm {
        let o = 24 + 16 * k;
        let kind = match b[o] {
            0 => MsgType::Snapshot,
            1 => MsgType::Update,
            2 => MsgType::Gap,
            3 => MsgType::Trade,
            x => panic!("bad message type {x}"),
        };
        msgs.push(Msg {
            kind,
            flags: b[o + 1],
            n_bids: u16at(o + 2),
            n_asks: u16at(o + 4),
            reserved: u16at(o + 6),
            checksum: u32at(o + 8),
            first: u32at(o + 12),
        });
    }
    let base = 24 + 16 * nm;
    let levels = (0..nl)
        .map(|k| {
            let o = base + 16 * k;
            Level {
                px: u64at(o) as i64,
                qty: u64at(o + 8) as i64,
            }
        })
        .collect();
    (msgs, levels)
}

fn verify(msgs: &[Msg], levels: &[Level]) -> u64 {
    let mut b = Book::new(DEPTH);
    let (mut bids, mut asks) = (BTreeMap::<i64, i64>::new(), BTreeMap::<i64, i64>::new());
    let mut t = vec![Level::default(); DEPTH];
    let (mut checks, mut bad) = (0u64, 0u64);
    // QF_H9_DUMP (workload R, 2026-11-19): the full top(100) after every non-trade message, for the check against
    // micro.book.rebuild in benchmarks/h9_check_r.py.
    let mut dump = std::env::var("QF_H9_DUMP")
        .ok()
        .map(|p| std::io::BufWriter::new(std::fs::File::create(p).expect("create dump")));
    for (i, m) in msgs.iter().enumerate() {
        b.apply(m, levels);
        if m.kind != MsgType::Trade {
            if m.kind == MsgType::Snapshot {
                bids.clear();
                asks.clear();
            }
            let f = m.first as usize;
            let nb = usize::from(m.n_bids);
            for (k, l) in levels[f..f + nb + usize::from(m.n_asks)].iter().enumerate() {
                let side = if k < nb { &mut bids } else { &mut asks };
                if l.qty != 0 {
                    side.insert(l.px, l.qty);
                } else {
                    side.remove(&l.px);
                }
            }
            while bids.len() > DEPTH {
                bids.pop_first();
            }
            while asks.len() > DEPTH {
                asks.pop_last();
            }
            if let Some(w) = dump.as_mut() {
                use std::fmt::Write as _;
                use std::io::Write;
                let mut line = format!("{i}");
                for (bid, c) in [(true, 'b'), (false, 'a')] {
                    let n = b.top(bid, &mut t);
                    write!(line, " {c} {n}").expect("write to a String");
                    for l in &t[..n] {
                        write!(line, " {} {}", l.px, l.qty).expect("write to a String");
                    }
                }
                writeln!(w, "{line}").expect("write dump");
            }
        }
        if i % 1000 == 999 || i + 1 == msgs.len() {
            checks += 1;
            let n = b.top(true, &mut t);
            let ok_b = t[..n]
                .iter()
                .copied()
                .eq(bids.iter().rev().map(|(&px, &qty)| Level { px, qty }));
            let n = b.top(false, &mut t);
            let ok_a = t[..n]
                .iter()
                .copied()
                .eq(asks.iter().map(|(&px, &qty)| Level { px, qty }));
            if !(ok_b && ok_a) {
                bad += 1;
            }
        }
    }
    eprintln!(
        "correctness: {checks} checkpoints, {bad} mismatches; crossed {}, grows {}",
        b.stats().crossed,
        b.grows()
    );
    bad
}

/// Venue checksum carried on a book message, checked outside the timed `apply` (not `FLAG_CHECKSUM`).
const FLAG_VENUE_CHECKSUM: u8 = 4;

/// One form A checkpoint row: compared after each message index in `lo..=hi` (the row's millisecond range); it passes
/// if it equals the book after one of them (ruling HR-132).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Checkpoint {
    lo: u32,
    n_bids: u16,
    n_asks: u16,
    first: u32,
    hi: u32,
}

/// The checkpoint file: "QFH9C001", u64 rows, u64 levels; 16-byte rows (lo, `n_bids`, `n_asks`, first, hi); levels.
fn read_checkpoints(path: &str) -> (Vec<Checkpoint>, Vec<Level>) {
    let b = std::fs::read(path).expect("read checkpoints");
    assert_eq!(&b[..8], b"QFH9C001", "not a checkpoint file");
    let u64at = |o: usize| u64::from_le_bytes(b[o..o + 8].try_into().expect("8 bytes"));
    let u32at = |o: usize| u32::from_le_bytes(b[o..o + 4].try_into().expect("4 bytes"));
    let u16at = |o: usize| u16::from_le_bytes(b[o..o + 2].try_into().expect("2 bytes"));
    let (nr, nl) = (u64at(8) as usize, u64at(16) as usize);
    let rows: Vec<Checkpoint> = (0..nr)
        .map(|k| {
            let o = 24 + 16 * k;
            Checkpoint {
                lo: u32at(o),
                n_bids: u16at(o + 4),
                n_asks: u16at(o + 6),
                first: u32at(o + 8),
                hi: u32at(o + 12),
            }
        })
        .collect();
    let base = 24 + 16 * nr;
    let levels: Vec<Level> = (0..nl)
        .map(|k| Level {
            px: u64at(base + 16 * k) as i64,
            qty: u64at(base + 16 * k + 8) as i64,
        })
        .collect();
    for r in &rows {
        assert!(
            r.lo <= r.hi && r.first as usize + usize::from(r.n_bids) + usize::from(r.n_asks) <= nl,
            "bad checkpoint row"
        );
    }
    (rows, levels)
}

/// L7 sample: apply time over levels, rounded up to a whole nanosecond (item 2b). `n >= 1`.
fn per_level_ns(dt: u64, n: u32) -> u64 {
    dt.div_ceil(u64::from(n))
}

/// 0: equal on all the row's levels; 1: the first 10 a side equal, a deeper one differs; 2: the first 10 differ.
/// Each side compares our best n levels with the row's n (`micro.book.rebuild`'s checkpoint rule).
fn compare(b: &Book, bids: &[Level], asks: &[Level], scratch: &mut [Level]) -> u8 {
    let mut worst = 0;
    for (bid, want) in [(true, bids), (false, asks)] {
        let got = b.top(bid, &mut scratch[..want.len()]);
        let k10 = want.len().min(10);
        if got < k10 || scratch[..k10] != want[..k10] {
            return 2;
        }
        if got != want.len() || scratch[k10..got] != want[k10..] {
            worst = 1;
        }
    }
    worst
}

/// Form A counts of low-latency-targets.md (g).
#[derive(Debug, Default, PartialEq, Eq)]
struct FormA {
    checksum_checked: u64,
    checksum_failed: u64,
    checkpoint_checked: u64,
    failed_top10: u64,
    failed_below10: u64,
    matched_at_lo: u64,
    matched_at_hi: u64,
    matched_only_inside_tie: u64,
    rows_with_tie: u64,
}

impl FormA {
    fn json(&self) -> String {
        format!(
            "{{\"checksum_checked\":{},\"checksum_failed\":{},\"checkpoint_checked\":{},\"checkpoint_failed_top10\":{},\
             \"checkpoint_failed_below10\":{},\"checkpoint_matched_at_lo\":{},\"checkpoint_matched_at_hi\":{},\
             \"checkpoint_matched_only_inside_tie\":{},\"checkpoint_rows_with_tie\":{},\
             \"checkpoint_failed_strict_reading\":{}}}",
            self.checksum_checked,
            self.checksum_failed,
            self.checkpoint_checked,
            self.failed_top10,
            self.failed_below10,
            self.matched_at_lo,
            self.matched_at_hi,
            self.matched_only_inside_tie,
            self.rows_with_tie,
            self.checkpoint_checked - self.matched_at_lo
        )
    }
}

/// One replay on a fresh book, outside any timing: venue checksums and every checkpoint row over its range.
fn verify_form_a(msgs: &[Msg], levels: &[Level], rows: &[Checkpoint], cl: &[Level]) -> FormA {
    let mut b = Book::new(DEPTH);
    let mut c = FormA::default();
    let mut scratch = vec![Level::default(); 1024];
    let mut best = vec![3u8; rows.len()];
    let mut at_lo = vec![false; rows.len()];
    let mut at_hi = vec![false; rows.len()];
    let mut next = 0usize;
    let mut live: Vec<usize> = Vec::new();
    for (i, m) in msgs.iter().enumerate() {
        b.apply(m, levels);
        if m.kind != MsgType::Trade && m.flags & FLAG_VENUE_CHECKSUM != 0 {
            c.checksum_checked += 1;
            if b.checksum() != m.checksum {
                c.checksum_failed += 1;
            }
        }
        while next < rows.len() && rows[next].lo as usize <= i {
            live.push(next);
            next += 1;
        }
        let mut k = 0;
        while k < live.len() {
            let j = live[k];
            let r = rows[j];
            let f = r.first as usize;
            let nb = usize::from(r.n_bids);
            let na = usize::from(r.n_asks);
            let res = compare(&b, &cl[f..f + nb], &cl[f + nb..f + nb + na], &mut scratch);
            best[j] = best[j].min(res);
            if res == 0 && i == r.lo as usize {
                at_lo[j] = true;
            }
            if res == 0 && i == r.hi as usize {
                at_hi[j] = true;
            }
            if i >= r.hi as usize {
                live.swap_remove(k);
            } else {
                k += 1;
            }
        }
    }
    for (j, r) in rows.iter().enumerate() {
        c.checkpoint_checked += 1;
        c.rows_with_tie += u64::from(r.hi > r.lo);
        match best[j] {
            0 => {
                c.matched_at_lo += u64::from(at_lo[j]);
                c.matched_at_hi += u64::from(at_hi[j]);
                c.matched_only_inside_tie += u64::from(!at_lo[j] && !at_hi[j]);
            }
            1 => c.failed_below10 += 1,
            _ => c.failed_top10 += 1,
        }
    }
    c
}

/// 1-minute load average; -1 where `/proc/loadavg` is absent.
fn loadavg_1m() -> f64 {
    std::fs::read_to_string("/proc/loadavg")
        .ok()
        .and_then(|s| s.split_whitespace().next().and_then(|v| v.parse().ok()))
        .unwrap_or(-1.0)
}

fn ns(t: Instant) -> u64 {
    t.elapsed().as_nanos() as u64
}

/// One timed run after `warmup` unmeasured messages (the harness uses `WARMUP`; tests a short stream).
#[cfg(test)]
fn timed_run_with(msgs: &[Msg], levels: &[Level], qseed: u64, warmup: usize) -> String {
    timed_run_gen::<false>(msgs, levels, qseed, warmup)
}

/// The timed run; `PER_LEVEL` adds the L7 sample after the clock read (a separate instantiation).
#[allow(clippy::too_many_lines)]
fn timed_run_gen<const PER_LEVEL: bool>(
    msgs: &[Msg],
    levels: &[Level],
    qseed: u64,
    warmup: usize,
) -> String {
    let load_start = loadavg_1m();
    let mut per_level = Hist::new();
    let mut all = Hist::new();
    let mut kinds: Vec<Hist> = (0..KINDS.len()).map(|_| Hist::new()).collect();
    let mut queries: Vec<Hist> = (0..QUERIES.len()).map(|_| Hist::new()).collect();
    let mut batch = Hist::new();
    let mut qbatch: Vec<Hist> = (0..QUERIES.len()).map(|_| Hist::new()).collect();
    let mut pres = vec![Level::default(); DEPTH];
    let mut r = Xoshiro::seeded(qseed, 0);
    let sides: Vec<bool> = (0..1024).map(|_| r.next_u64() & 1 == 1).collect();
    let mut buf = vec![Level::default(); DEPTH];
    let mut b = Book::new(DEPTH);
    for m in &msgs[..warmup] {
        b.apply(m, levels);
    }
    let far0 = b.far_lookups();
    ALLOCS.store(0, Ordering::Relaxed);
    for (i, m) in msgs.iter().enumerate().skip(warmup) {
        let t0 = Instant::now();
        b.apply(black_box(m), levels);
        let dt = ns(t0);
        all.record(dt);
        kinds[usize::from(m.reserved)].record(dt);
        if PER_LEVEL {
            let n = u32::from(m.n_bids) + u32::from(m.n_asks);
            if m.kind == MsgType::Update && n != 0 {
                per_level.record(per_level_ns(dt, n));
            }
        }
        if (i - warmup) % 1000 == 999 {
            let a = Instant::now();
            black_box(b.best_bid());
            queries[0].record(ns(a));
            let a = Instant::now();
            black_box(b.best_ask());
            queries[1].record(ns(a));
            let bid = r.next_u64() & 1 == 1;
            let n = b.top(bid, &mut buf);
            let present = if n > 0 {
                buf[(r.next_u64() % n as u64) as usize].px
            } else {
                0
            };
            let absent = b.best_ask().map_or(1, |l| l.px + 5);
            let a = Instant::now();
            black_box(b.qty_at(bid, black_box(present)));
            queries[2].record(ns(a));
            let a = Instant::now();
            black_box(b.qty_at(true, black_box(absent)));
            queries[3].record(ns(a));
            let a = Instant::now();
            black_box(b.top(bid, &mut buf[..10]));
            queries[4].record(ns(a));
            let a = Instant::now();
            black_box(b.top(bid, &mut buf[..100]));
            queries[5].record(ns(a));
            // HR-21 batch timing: each query 1,000 times in a row, total divided by 1,000. Each iteration's
            // side/price comes from precomputed arrays indexed through the previous result (a dependency chain:
            // latency, not throughput), and both the book reference and the accumulator pass `black_box`, so the
            // call can be neither hoisted nor elided.
            let mut acc = 0i64;
            let np = b.top(bid, &mut pres).max(1);
            let a = Instant::now();
            for _ in 0..1000 {
                acc += black_box(&b).best_bid().map_or(0, |l| l.qty + (acc & 1));
                acc = black_box(acc);
            }
            qbatch[0].record((ns(a) + 500) / 1000);
            let a = Instant::now();
            for _ in 0..1000 {
                acc += black_box(&b).best_ask().map_or(0, |l| l.qty + (acc & 1));
                acc = black_box(acc);
            }
            qbatch[1].record((ns(a) + 500) / 1000);
            let a = Instant::now();
            for j in 0..1000usize {
                acc += black_box(&b).qty_at(bid, pres[(j + (acc & 1) as usize) % np].px);
                acc = black_box(acc);
            }
            qbatch[2].record((ns(a) + 500) / 1000);
            let a = Instant::now();
            for j in 0..1000i64 {
                acc += black_box(&b).qty_at(true, absent + (j & 511) + (acc & 1));
                acc = black_box(acc);
            }
            qbatch[3].record((ns(a) + 500) / 1000);
            let a = Instant::now();
            for j in 0..1000usize {
                let side = sides[(j + (acc & 1) as usize) & 1023];
                acc += black_box(&b).top(side, &mut buf[..10]) as i64 + buf[0].qty;
                acc = black_box(acc);
            }
            qbatch[4].record((ns(a) + 500) / 1000);
            let a = Instant::now();
            for j in 0..1000usize {
                let side = sides[(j + (acc & 1) as usize) & 1023];
                acc += black_box(&b).top(side, &mut buf[..100]) as i64 + buf[99].qty;
                acc = black_box(acc);
            }
            qbatch[5].record((ns(a) + 500) / 1000);
            black_box(acc);
        }
    }
    let allocs = ALLOCS.load(Ordering::Relaxed);
    let far = b.far_lookups() - far0;
    let grows = b.grows();
    let fallbacks = b.index_fallbacks();
    let mut b = Book::new(DEPTH);
    for m in &msgs[..warmup] {
        b.apply(m, levels);
    }
    ALLOCS.store(0, Ordering::Relaxed);
    let mut i = warmup;
    while i + 1000 <= msgs.len() {
        let t0 = Instant::now();
        for m in &msgs[i..i + 1000] {
            b.apply(black_box(m), levels);
        }
        batch.record((ns(t0) + 500) / 1000);
        i += 1000;
    }
    let batch_allocs = ALLOCS.load(Ordering::Relaxed);
    let load_end = loadavg_1m();
    let pl = if PER_LEVEL {
        format!(",\"per_level\":{}", per_level.json())
    } else {
        String::new()
    };
    eprintln!(
        "run: p50 {} p99 {} p99.9 {} ns, allocs {allocs}",
        all.pct(50.0),
        all.pct(99.0),
        all.pct(99.9)
    );
    let kj = KINDS
        .iter()
        .zip(&kinds)
        .map(|(k, h)| format!("\"{k}\":{}", h.json()))
        .collect::<Vec<_>>()
        .join(",");
    let qbj = QUERIES
        .iter()
        .zip(&qbatch)
        .map(|(k, h)| format!("\"{k}\":{}", h.json()))
        .collect::<Vec<_>>()
        .join(",");
    let qj = QUERIES
        .iter()
        .zip(&queries)
        .map(|(k, h)| format!("\"{k}\":{}", h.json()))
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "{{\"all\":{},\"kinds\":{{{kj}}},\"queries\":{{{qj}}},\"queries_batch_per_call\":{{{qbj}}},\"batch_per_message\":{},\"allocations_measured\":{allocs},\
         \"allocations_batch\":{batch_allocs},\"far_lookups\":{far},\"buffer_grows\":{grows},\"qty_at_index_fallbacks\":{fallbacks}{pl},\
         \"loadavg_1m_start\":{load_start:.6},\"loadavg_1m_end\":{load_end:.6}}}",
        all.json(),
        batch.json()
    )
}

/// The whole harness for `args` (as `std::env::args`), with the warm-up length and the number of clock pairs as
/// parameters; returns the exit code. `main` passes the specified 1,000,000 and 1,000,000.
fn run(args: &[String], warmup: usize, clock_pairs: usize) -> i32 {
    if args.len() < 2 {
        eprintln!("usage: lowlat_book <workload S file> [runs] [out.json]");
        return 2;
    }
    let (msgs, levels) = read_stream(&args[1]);
    let runs: u64 = args.get(2).map_or(5, |s| s.parse().expect("runs"));
    let map_bad = verify(&msgs, &levels);
    let mut bad = map_bad;
    let mut form_a = String::new();
    if let Ok(cp) = std::env::var("QF_H9_CHECKPOINTS") {
        let (rows, cl) = read_checkpoints(&cp);
        let c = verify_form_a(&msgs, &levels, &rows, &cl);
        eprintln!("form A: {}", c.json());
        form_a = format!(",\"form_a\":{}", c.json());
        // A checksum or top-10 failure fails the run; below-10 failures are published and judged by the runner.
        bad += c.checksum_failed + c.failed_top10 + u64::from(c.checksum_checked == 0);
    }
    let per_level = std::env::var("QF_H9_PER_LEVEL").is_ok_and(|v| v == "1");
    let mut clock = Hist::new();
    for _ in 0..clock_pairs {
        let a = Instant::now();
        clock.record(ns(black_box(a)));
    }
    let workload = std::env::var("QF_H9_WORKLOAD").unwrap_or_else(|_| "S".to_string());
    let runs_json = (0..runs)
        .map(|k| {
            if per_level {
                timed_run_gen::<true>(&msgs, &levels, SEED + 1 + k, warmup)
            } else {
                timed_run_gen::<false>(&msgs, &levels, SEED + 1 + k, warmup)
            }
        })
        .collect::<Vec<_>>()
        .join(",");
    let out = format!(
        "{{\"workload\":\"{workload}\",\"messages\":{},\"warmup\":{warmup},\"depth\":100,\"alloc_method\":\"counting #[global_allocator]\",\
         \"correctness_mismatches\":{map_bad}{form_a},\"per_level_sampling\":{per_level},\"clock_overhead\":{},\"runs\":[{runs_json}]}}\n",
        msgs.len(),
        clock.json()
    );
    match args.get(3) {
        Some(p) => std::fs::write(p, out).expect("write results"),
        None => print!("{out}"),
    }
    i32::from(bad != 0)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    // QF_H9_WARMUP overrides the warm-up count (workload R warms up on its first hour).
    let warmup = std::env::var("QF_H9_WARMUP").map_or(WARMUP, |w| w.parse().expect("QF_H9_WARMUP"));
    std::process::exit(run(&args, warmup, 1_000_000));
}

#[cfg(test)]
#[path = "lowlat_book/tests.rs"]
mod tests;
