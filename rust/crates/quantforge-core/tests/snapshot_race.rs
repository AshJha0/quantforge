//! Stage K, K-5 (PROPOSED, KR-280 to KR-288): snapshot semantics on the shared scenario
//! `datasets/scenarios/k5_snapshot.json`, and the race test. Under `ThreadSanitizer` (nightly,
//! `-Zsanitizer=thread`) this runs in CI only: the pinned 1.99.1 toolchain is stable. Latency-aware
//! analytics on simulated data; nothing here is timed.
//!
//! The planted faults (KR-288) run only with `QF_SNAPSHOT_FAULTS=1`, under `ThreadSanitizer`, where
//! each must be reported (the CI job expects the failure).

use std::sync::atomic::{AtomicUsize, Ordering};
use std::thread;

use quantforge_core::json::{Json, parse};
use quantforge_core::live_snapshot::{
    self as ls, Fault, HedgeInstrument, HedgeSnapshot, SnapshotCell,
};
use quantforge_core::stage_k::{self, ZeroPosition};

struct Scenario {
    book: Vec<ZeroPosition>,
    hedge: HedgeInstrument,
    root: Json,
}

fn num(j: &Json, k: &str) -> f64 {
    j.get(k).and_then(Json::as_f64).expect("number in scenario")
}

fn scenario() -> Scenario {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../../datasets/scenarios/k5_snapshot.json"
    );
    let text = std::fs::read_to_string(path).expect("scenario file");
    let (root, _) = parse(&text).expect("scenario parses");
    let book = root
        .get("book")
        .and_then(Json::as_array)
        .expect("book")
        .iter()
        .map(|p| ZeroPosition {
            notional: num(p, "notional"),
            maturity: num(p, "maturity"),
            yield_: num(p, "yield"),
        })
        .collect();
    let h = root.get("hedge").expect("hedge");
    let hedge = HedgeInstrument {
        maturity: num(h, "maturity"),
        yield_: num(h, "yield"),
    };
    Scenario { book, hedge, root }
}

fn build(sc: &Scenario, k: u64, shift: f64) -> HedgeSnapshot {
    ls::build(k, k, &sc.book, &sc.hedge, shift).expect("valid book")
}

fn close(a: f64, b: f64, tol: f64) -> bool {
    (a - b).abs() <= tol * b.abs()
}

#[test]
fn scenario_expected_values() {
    let sc = scenario();
    let tol = num(&sc.root, "tolerance_relative");
    for row in sc
        .root
        .get("expected")
        .and_then(Json::as_array)
        .expect("expected")
    {
        let k = num(row, "version") as u64;
        let s = build(&sc, k, ls::scenario_shift(k));
        assert!(s.intact());
        assert_eq!(s.shift, num(row, "shift"), "shift rule, version {k}");
        assert!(close(s.estimate_pnl, num(row, "estimate_pnl"), tol));
        assert!(close(s.bound, num(row, "bound"), tol));
        assert!(close(s.book_delta, num(row, "book_delta"), tol));
        assert!(close(s.hedge_unit_delta, num(row, "hedge_unit_delta"), tol));
        assert!(close(s.hedge_notional, num(row, "hedge_notional"), tol));
        let residual = s.book_delta + s.hedge_notional * s.hedge_unit_delta;
        assert!(residual.abs() <= 1e-9 * s.book_delta.abs());
    }
}

#[test]
fn checksum_pinned_values() {
    assert_eq!(ls::checksum(&[]), ls::CHECK_SEED);
    assert_eq!(ls::checksum(&[0]), 0xF6E599AEF89D022F);
    assert_eq!(ls::checksum(&[1, 2, 3]), 0x8517CC75DE438E52);
}

#[test]
fn exactness_1000_publishes() {
    // KR-284: every number read through the cell is bit-identical to the direct call.
    let sc = scenario();
    let n = num(&sc.root, "exactness_publishes") as u64;
    let cell = SnapshotCell::new(1, build(&sc, 0, 0.0)).expect("one reader");
    for k in 1..=n {
        let h = ls::scenario_shift(k);
        cell.publish(build(&sc, k, h));
        let g = cell.acquire(0).expect("reader 0");
        let risk = stage_k::delta_gamma_bound(&sc.book, h).expect("valid");
        let (d, u) = (
            ls::book_delta(&sc.book, h),
            ls::hedge_unit_delta(&sc.hedge, h),
        );
        assert_eq!(g.version, k);
        assert_eq!(g.estimate_pnl.to_bits(), risk.estimate_pnl.to_bits());
        assert_eq!(g.bound.to_bits(), risk.bound.to_bits());
        assert_eq!(g.book_delta.to_bits(), d.to_bits());
        assert_eq!(g.hedge_unit_delta.to_bits(), u.to_bits());
        assert_eq!(g.hedge_notional.to_bits(), (-d / u).to_bits());
    }
}

#[test]
fn corrupted_field_fails_the_reader_check() {
    // Planted fault 4 (KR-288).
    let sc = scenario();
    let s = build(&sc, 5, ls::scenario_shift(5));
    let mut bad = s;
    bad.bound = f64::from_bits(s.bound.to_bits() + 1);
    assert!(!bad.intact());
    let mut bad = s;
    bad.version = 6;
    assert!(!bad.intact());
}

#[test]
fn pool_and_reader_rules() {
    let sc = scenario();
    let s0 = build(&sc, 0, 0.0);
    assert!(SnapshotCell::new(0, s0).is_none());
    assert!(SnapshotCell::new(65, s0).is_none());
    let cell = SnapshotCell::new(2, s0).expect("two readers");
    assert_eq!((cell.readers(), cell.pool_size()), (2, 4));
    assert!(cell.acquire(2).is_none());
    // A held snapshot is not overwritten by later publishes (the hazard is respected).
    let held = cell.acquire(0).expect("reader 0");
    let before = held.words();
    for k in 1..=50 {
        cell.publish(build(&sc, k, ls::scenario_shift(k)));
    }
    assert_eq!(held.words(), before);
    assert!(held.intact());
    assert_eq!(cell.acquire(1).expect("reader 1").version, 50);
    drop(held);
    assert_eq!(cell.acquire(0).expect("reader 0").version, 50);
    assert!(SnapshotCell::<HedgeSnapshot>::with_fault(1, s0, Fault::RelaxedPublish).is_some());
}

#[derive(Default, Clone, Copy)]
struct Stats {
    reads: u64,
    torn: u64,
    non_monotone: u64,
    mismatched: u64,
    last: u64,
}

fn race(readers: usize, publishes: u64, fault: Fault) -> Stats {
    let sc = scenario();
    let cell = SnapshotCell::with_fault(readers, build(&sc, 0, 0.0), fault).expect("readers");
    let ready = AtomicUsize::new(0);
    let stats: Vec<Stats> = thread::scope(|s| {
        let handles: Vec<_> = (0..readers)
            .map(|i| {
                let (cell, sc, ready) = (&cell, &sc, &ready);
                s.spawn(move || {
                    let mut st = Stats::default();
                    ready.fetch_add(1, Ordering::SeqCst);
                    loop {
                        let g = cell.acquire(i).expect("reader index");
                        st.reads += 1;
                        if !g.intact() {
                            st.torn += 1;
                        }
                        if g.version < st.last {
                            st.non_monotone += 1;
                        }
                        st.last = st.last.max(g.version);
                        if st.reads % 64 == 0 && *g != build(sc, g.version, g.shift) {
                            st.mismatched += 1;
                        }
                        if g.version >= publishes {
                            return st;
                        }
                    }
                })
            })
            .collect();
        while ready.load(Ordering::SeqCst) < readers {
            thread::yield_now();
        }
        for k in 1..=publishes {
            cell.publish(build(&sc, k, ls::scenario_shift(k)));
        }
        handles
            .into_iter()
            .map(|h| h.join().expect("reader thread"))
            .collect()
    });
    let mut total = Stats {
        last: publishes,
        ..Stats::default()
    };
    for st in stats {
        total.reads += st.reads;
        total.torn += st.torn;
        total.non_monotone += st.non_monotone;
        total.mismatched += st.mismatched;
        total.last = total.last.min(st.last);
    }
    println!(
        "race: readers={readers} publishes={publishes} reads={} torn={} non_monotone={} mismatched={} final_seen={} (latency-aware analytics on simulated data; not timed)",
        total.reads,
        total.torn,
        total.non_monotone,
        total.mismatched,
        total.last == publishes
    );
    total
}

fn publishes() -> u64 {
    std::env::var("QF_SNAPSHOT_PUBLISHES")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or_else(|| {
            num(
                scenario().root.get("race").expect("race"),
                "publishes_default",
            ) as u64
        })
}

#[test]
fn race_scenario_r1_r4_r16() {
    let p = publishes();
    for r in [1, 4, 16] {
        let t = race(r, p, Fault::None);
        assert_eq!((t.torn, t.non_monotone, t.mismatched), (0, 0, 0));
        assert_eq!(t.last, p, "every reader saw the final version");
        assert!(t.reads >= r as u64);
    }
}

#[test]
fn planted_faults_under_tsan() {
    // Only meaningful under ThreadSanitizer, which must report and abort (KR-288). Without the
    // sanitizer the faulty runs may pass or fail; nothing is asserted.
    if std::env::var("QF_SNAPSHOT_FAULTS").as_deref() != Ok("1") {
        return;
    }
    let fault = match std::env::var("QF_SNAPSHOT_FAULT").as_deref() {
        Ok("skip") => Fault::SkipHazardScan,
        _ => Fault::RelaxedPublish,
    };
    let _ = race(4, 20_000, fault);
}
