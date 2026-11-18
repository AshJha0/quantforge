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

fn ns(t: Instant) -> u64 {
    t.elapsed().as_nanos() as u64
}

fn timed_run(msgs: &[Msg], levels: &[Level], qseed: u64) -> String {
    let mut all = Hist::new();
    let mut kinds: Vec<Hist> = (0..KINDS.len()).map(|_| Hist::new()).collect();
    let mut queries: Vec<Hist> = (0..QUERIES.len()).map(|_| Hist::new()).collect();
    let mut batch = Hist::new();
    let mut qbatch: Vec<Hist> = (0..QUERIES.len()).map(|_| Hist::new()).collect();
    let mut pres = vec![Level::default(); DEPTH];
    let mut r = Xoshiro::seeded(qseed, 0);
    let mut buf = vec![Level::default(); DEPTH];
    let mut b = Book::new(DEPTH);
    for m in &msgs[..WARMUP] {
        b.apply(m, levels);
    }
    let far0 = b.far_lookups();
    ALLOCS.store(0, Ordering::Relaxed);
    for (i, m) in msgs.iter().enumerate().skip(WARMUP) {
        let t0 = Instant::now();
        b.apply(black_box(m), levels);
        let dt = ns(t0);
        all.record(dt);
        kinds[usize::from(m.reserved)].record(dt);
        if (i - WARMUP) % 1000 == 999 {
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
            // HR-21 batch timing: each query 1,000 times in a row, total divided by 1,000; prices cycle so no
            // call repeats the previous one.
            let mut acc = 0i64;
            let a = Instant::now();
            for _ in 0..1000 {
                acc += black_box(&b).best_bid().map_or(0, |l| l.qty);
            }
            qbatch[0].record((ns(a) + 500) / 1000);
            let a = Instant::now();
            for _ in 0..1000 {
                acc += black_box(&b).best_ask().map_or(0, |l| l.qty);
            }
            qbatch[1].record((ns(a) + 500) / 1000);
            let np = b.top(bid, &mut pres).max(1);
            let a = Instant::now();
            for j in 0..1000 {
                acc += b.qty_at(bid, black_box(pres[j % np].px));
            }
            qbatch[2].record((ns(a) + 500) / 1000);
            let a = Instant::now();
            for j in 0..1000i64 {
                acc += b.qty_at(true, black_box(absent + j));
            }
            qbatch[3].record((ns(a) + 500) / 1000);
            let a = Instant::now();
            for _ in 0..1000 {
                acc += black_box(&b).top(bid, &mut buf[..10]) as i64 + buf[0].qty;
            }
            qbatch[4].record((ns(a) + 500) / 1000);
            let a = Instant::now();
            for _ in 0..1000 {
                acc += black_box(&b).top(bid, &mut buf[..100]) as i64 + buf[99].qty;
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
    for m in &msgs[..WARMUP] {
        b.apply(m, levels);
    }
    ALLOCS.store(0, Ordering::Relaxed);
    let mut i = WARMUP;
    while i + 1000 <= msgs.len() {
        let t0 = Instant::now();
        for m in &msgs[i..i + 1000] {
            b.apply(black_box(m), levels);
        }
        batch.record((ns(t0) + 500) / 1000);
        i += 1000;
    }
    let batch_allocs = ALLOCS.load(Ordering::Relaxed);
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
         \"allocations_batch\":{batch_allocs},\"far_lookups\":{far},\"buffer_grows\":{grows},\"qty_at_index_fallbacks\":{fallbacks}}}",
        all.json(),
        batch.json()
    )
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: lowlat_book <workload S file> [runs] [out.json]");
        std::process::exit(2);
    }
    let (msgs, levels) = read_stream(&args[1]);
    let runs: u64 = args.get(2).map_or(5, |s| s.parse().expect("runs"));
    let bad = verify(&msgs, &levels);
    let mut clock = Hist::new();
    for _ in 0..1_000_000 {
        let a = Instant::now();
        clock.record(ns(black_box(a)));
    }
    let runs_json = (0..runs)
        .map(|k| timed_run(&msgs, &levels, SEED + 1 + k))
        .collect::<Vec<_>>()
        .join(",");
    let out = format!(
        "{{\"workload\":\"S\",\"messages\":{},\"warmup\":{WARMUP},\"depth\":100,\"alloc_method\":\"counting #[global_allocator]\",\
         \"correctness_mismatches\":{bad},\"clock_overhead\":{},\"runs\":[{runs_json}]}}\n",
        msgs.len(),
        clock.json()
    );
    match args.get(3) {
        Some(p) => std::fs::write(p, out).expect("write results"),
        None => print!("{out}"),
    }
    std::process::exit(i32::from(bad != 0));
}
