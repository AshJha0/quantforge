//! Unit tests of the H-9 Rust harness on a short synthetic workload: the file reader, the correctness pass, the
//! histogram, one timed run and the whole `run` (with a short warm-up), so the harness code is checked as well as
//! timed.
use super::*;

/// A workload of `n` messages: a snapshot (bids 97..99, asks 101..103), then updates that set or clear one level
/// on alternating sides away from the touch, and a trade every 7th message. `reserved` carries the kind index.
fn stream(n: usize) -> (Vec<Msg>, Vec<Level>) {
    let mut levels = vec![
        Level { px: 99, qty: 5 },
        Level { px: 98, qty: 6 },
        Level { px: 97, qty: 7 },
        Level { px: 101, qty: 5 },
        Level { px: 102, qty: 6 },
        Level { px: 103, qty: 7 },
    ];
    let mut msgs = vec![Msg {
        kind: MsgType::Snapshot,
        flags: 0,
        n_bids: 3,
        n_asks: 3,
        reserved: 0,
        checksum: 0,
        first: 0,
    }];
    let mut r = Xoshiro::seeded(7, 0);
    for k in 1..n {
        if k % 7 == 0 {
            msgs.push(Msg {
                kind: MsgType::Trade,
                flags: 0,
                n_bids: 0,
                n_asks: 0,
                reserved: 4,
                checksum: 0,
                first: levels.len() as u32,
            });
            continue;
        }
        let bid = k % 2 == 0;
        let off = (r.next_u64() % 20) as i64;
        let qty = (r.next_u64() % 4) as i64; // 0 clears the level
        let px = if bid { 90 - off } else { 110 + off };
        let first = levels.len() as u32;
        levels.push(Level { px, qty });
        msgs.push(Msg {
            kind: MsgType::Update,
            flags: 0,
            n_bids: u16::from(bid),
            n_asks: u16::from(!bid),
            reserved: if qty == 0 { 3 } else { 1 },
            checksum: 0,
            first,
        });
    }
    (msgs, levels)
}

/// The workload S byte layout read by `read_stream`.
fn bytes(msgs: &[Msg], levels: &[Level]) -> Vec<u8> {
    let mut b = b"QFH9S001".to_vec();
    b.extend((msgs.len() as u64).to_le_bytes());
    b.extend((levels.len() as u64).to_le_bytes());
    for m in msgs {
        b.push(match m.kind {
            MsgType::Snapshot => 0,
            MsgType::Update => 1,
            MsgType::Gap => 2,
            MsgType::Trade => 3,
        });
        b.push(m.flags);
        b.extend(m.n_bids.to_le_bytes());
        b.extend(m.n_asks.to_le_bytes());
        b.extend(m.reserved.to_le_bytes());
        b.extend(m.checksum.to_le_bytes());
        b.extend(m.first.to_le_bytes());
    }
    for l in levels {
        b.extend((l.px as u64).to_le_bytes());
        b.extend((l.qty as u64).to_le_bytes());
    }
    b
}

fn temp(name: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!("qf_lowlat_{}_{name}", std::process::id()))
}

#[test]
fn read_stream_round_trips_the_file_layout() {
    let (msgs, levels) = stream(50);
    let p = temp("rt.bin");
    std::fs::write(&p, bytes(&msgs, &levels)).unwrap();
    let (m2, l2) = read_stream(p.to_str().unwrap());
    std::fs::remove_file(&p).unwrap();
    assert_eq!(m2.len(), msgs.len());
    assert_eq!(l2, levels);
    for (a, b) in msgs.iter().zip(&m2) {
        assert_eq!(
            (
                a.kind, a.flags, a.n_bids, a.n_asks, a.reserved, a.checksum, a.first
            ),
            (
                b.kind, b.flags, b.n_bids, b.n_asks, b.reserved, b.checksum, b.first
            )
        );
    }
}

#[test]
#[should_panic(expected = "not a workload S file")]
fn read_stream_rejects_a_foreign_file() {
    let p = temp("bad.bin");
    std::fs::write(&p, b"NOTAFILE0000000000000000").unwrap();
    read_stream(p.to_str().unwrap());
}

#[test]
fn verify_finds_no_mismatch_against_the_std_transcription() {
    let (msgs, levels) = stream(2_500);
    assert_eq!(verify(&msgs, &levels), 0);
}

#[test]
fn hist_buckets_percentiles_and_json() {
    let mut h = Hist::new();
    assert_eq!(h.pct(50.0), 0);
    assert_eq!(h.json(), "{\"count\":0}");
    for v in 1..=1000 {
        h.record(v);
    }
    // 3 significant digits: values below 2048 are exact.
    assert_eq!(h.pct(50.0), 500);
    assert_eq!(h.pct(99.0), 990);
    assert_eq!(h.pct(100.0), 1000);
    h.record(u64::MAX); // clamped to 10 s
    assert_eq!(h.mx, Hist::MAX);
    let j = h.json();
    assert!(j.starts_with("{\"count\":1001,\"min\":1,\"p50\":"), "{j}");
    assert!(!j.contains("p99_99"));
    // A bucket's highest value contains the value: index(v) == index(highest(index(v))).
    for v in [1u64, 2047, 2048, 4097, 1_000_003, 9_999_999_999] {
        let i = Hist::index(v);
        assert!(Hist::highest(i) >= v);
        assert_eq!(Hist::index(Hist::highest(i)), i);
    }
    let mut big = Hist::new();
    for _ in 0..1_000_000 {
        big.record(3);
    }
    assert!(big.json().contains("\"p99_99\":3,"));
}

#[test]
fn timed_run_reports_every_kind_and_query() {
    let (msgs, levels) = stream(4_000);
    let j = timed_run_with(&msgs, &levels, SEED, 1_000);
    for k in KINDS.iter().chain(QUERIES.iter()) {
        assert!(j.contains(&format!("\"{k}\":")), "{k} missing");
    }
    assert!(j.starts_with("{\"all\":{\"count\":3000,"), "{j}");
    assert!(j.contains("\"batch_per_message\":{\"count\":3,"));
    assert!(j.contains("\"queries_batch_per_call\":{"));
}

#[test]
fn run_writes_the_results_file_and_exit_code() {
    let (msgs, levels) = stream(2_200);
    let input = temp("in.bin");
    let out = temp("out.json");
    std::fs::write(&input, bytes(&msgs, &levels)).unwrap();
    let args: Vec<String> = vec![
        "lowlat_book".into(),
        input.to_str().unwrap().into(),
        "1".into(),
        out.to_str().unwrap().into(),
    ];
    assert_eq!(run(&args, 1_000, 100), 0);
    let text = std::fs::read_to_string(&out).unwrap();
    std::fs::remove_file(&input).unwrap();
    std::fs::remove_file(&out).unwrap();
    assert!(
        text.starts_with("{\"workload\":\"S\",\"messages\":2200,\"warmup\":1000,"),
        "{text}"
    );
    assert!(text.contains("\"correctness_mismatches\":0,"));
    assert!(text.contains("\"clock_overhead\":{\"count\":100,"));
    assert!(text.ends_with("]}\n"));
    assert_eq!(
        run(&args[..1], 1_000, 1),
        2,
        "no file argument is a usage error"
    );
}

// ---------------------------------------------------------------- R2 / L7 (2026-11-19, items 2a and 2b)

fn m(kind: MsgType, n_bids: u16, n_asks: u16, first: usize) -> Msg {
    Msg {
        kind,
        flags: 0,
        n_bids,
        n_asks,
        reserved: 2,
        checksum: 0,
        first: first as u32,
    }
}

#[test]
fn r2_truncation_to_100_levels_is_inside_apply() {
    // A full 100-level book on a 10-tick grid; a raw update adds a better bid, so 101 bids: the worst falls off.
    let mut lv: Vec<Level> = (0..100)
        .map(|k| Level {
            px: 10_000 - 10 * k,
            qty: 1 + k,
        })
        .chain((0..100).map(|k| Level {
            px: 10_010 + 10 * k,
            qty: 1 + k,
        }))
        .collect();
    let mut b = Book::new(100);
    b.apply(&m(MsgType::Snapshot, 100, 100, 0), &lv);
    lv.push(Level { px: 10_005, qty: 7 });
    b.apply(&m(MsgType::Update, 1, 0, 200), &lv);
    assert_eq!(b.stats().truncated_levels, 1);
    let mut top = vec![Level::default(); 100];
    assert_eq!(b.top(true, &mut top), 100);
    assert_eq!(top[0].px, 10_005);
    assert_eq!(top[99].px, 10_000 - 10 * 98);
    assert_eq!(b.qty_at(true, 9_010), 0);
    // Beyond depth on the far side: inserted and truncated in the same apply; the book is unchanged.
    let before = b.checksum();
    lv.push(Level { px: 5_000, qty: 3 });
    b.apply(&m(MsgType::Update, 1, 0, 201), &lv);
    assert_eq!(b.stats().truncated_levels, 2);
    assert_eq!(b.checksum(), before);
    assert_eq!(b.grows(), 0);
}

#[test]
fn l7_per_level_sample_rounds_up() {
    assert_eq!(per_level_ns(100, 1), 100);
    assert_eq!(per_level_ns(101, 2), 51);
    assert_eq!(per_level_ns(100, 3), 34);
    assert_eq!(per_level_ns(99, 3), 33);
    assert_eq!(per_level_ns(0, 5), 0);
    assert_eq!(per_level_ns(1, 200), 1);
}

#[test]
fn r2_form_a_counts_checksums_and_checkpoint_classes() {
    // 0 snapshot (bids 100..89, asks 101..112, qty 5), 1 bid 100 -> 6, 2 trade, 3 bid 89 -> 9 (level 12), 4 bid 100 -> 7
    let mut lv: Vec<Level> = (0..12)
        .map(|k| Level {
            px: 100 - k,
            qty: 5,
        })
        .chain((0..12).map(|k| Level {
            px: 101 + k,
            qty: 5,
        }))
        .collect();
    lv.extend([
        Level { px: 100, qty: 6 },
        Level { px: 101, qty: 1 },
        Level { px: 89, qty: 9 },
        Level { px: 100, qty: 7 },
    ]);
    let mut msgs = vec![
        m(MsgType::Snapshot, 12, 12, 0),
        m(MsgType::Update, 1, 0, 24),
        m(MsgType::Trade, 1, 0, 25),
        m(MsgType::Update, 1, 0, 26),
        m(MsgType::Update, 1, 0, 27),
    ];
    msgs[2].reserved = 4;
    let mut r = Book::new(100);
    for (i, x) in msgs.iter_mut().enumerate() {
        r.apply(x, &lv);
        if x.kind != MsgType::Trade {
            x.flags = FLAG_VENUE_CHECKSUM;
            x.checksum = if i == 3 {
                r.checksum() ^ 1
            } else {
                r.checksum()
            };
        }
    }
    let mut rows = Vec::new();
    let mut cl = Vec::new();
    let mut row = |after: usize, lo: u32, hi: u32, tweak: u8| {
        let mut b = Book::new(100);
        for x in &msgs[..=after] {
            b.apply(x, &lv);
        }
        let (mut bids, mut asks) = (vec![Level::default(); 100], vec![Level::default(); 100]);
        let nb = b.top(true, &mut bids);
        let na = b.top(false, &mut asks);
        if tweak == 1 {
            bids[11].qty += 1;
        }
        if tweak == 2 {
            asks[0].qty += 1;
        }
        rows.push(Checkpoint {
            lo,
            n_bids: nb as u16,
            n_asks: na as u16,
            first: cl.len() as u32,
            hi,
        });
        cl.extend_from_slice(&bids[..nb]);
        cl.extend_from_slice(&asks[..na]);
    };
    row(0, 0, 0, 0);
    row(1, 0, 2, 0);
    row(4, 3, 4, 0);
    row(3, 3, 3, 1);
    row(4, 4, 4, 2);
    let c = verify_form_a(&msgs, &lv, &rows, &cl);
    assert_eq!(
        c,
        FormA {
            checksum_checked: 4,
            checksum_failed: 1,
            checkpoint_checked: 5,
            failed_top10: 1,
            failed_below10: 1,
            matched_at_lo: 1,
            matched_at_hi: 3,
            matched_only_inside_tie: 0,
            rows_with_tie: 2,
        }
    );
    assert!(
        c.json()
            .starts_with("{\"checksum_checked\":4,\"checksum_failed\":1,")
    );
    // compare(): fewer row levels than the book compares only the row's levels.
    let mut b = Book::new(100);
    b.apply(&msgs[0], &lv);
    let mut scratch = vec![Level::default(); 100];
    assert_eq!(compare(&b, &lv[..5], &lv[12..14], &mut scratch), 0);
    let mut wrong = lv[..12].to_vec();
    wrong[11].px -= 1;
    assert_eq!(compare(&b, &wrong, &lv[12..24], &mut scratch), 1);
    wrong[0].qty = 99;
    assert_eq!(compare(&b, &wrong, &lv[12..24], &mut scratch), 2);
}

#[test]
fn r2_checkpoint_file_round_trips() {
    let p = temp("cps.bin");
    let mut b = b"QFH9C001".to_vec();
    b.extend(1u64.to_le_bytes());
    b.extend(3u64.to_le_bytes());
    b.extend(4u32.to_le_bytes());
    b.extend(2u16.to_le_bytes());
    b.extend(1u16.to_le_bytes());
    b.extend(0u32.to_le_bytes());
    b.extend(7u32.to_le_bytes());
    for (px, q) in [(100i64, 1i64), (99, 2), (101, 3)] {
        b.extend(px.to_le_bytes());
        b.extend(q.to_le_bytes());
    }
    std::fs::write(&p, b).unwrap();
    let (rows, cl) = read_checkpoints(p.to_str().unwrap());
    std::fs::remove_file(&p).unwrap();
    assert_eq!(
        rows,
        vec![Checkpoint {
            lo: 4,
            n_bids: 2,
            n_asks: 1,
            first: 0,
            hi: 7
        }]
    );
    assert_eq!(cl[2], Level { px: 101, qty: 3 });
}

#[test]
fn l7_timed_run_adds_the_per_level_histogram_and_load_average() {
    let (msgs, levels) = stream(4_000);
    let j = timed_run_gen::<true>(&msgs, &levels, SEED, 1_000);
    assert!(j.contains("\"per_level\":{\"count\":"), "{j}");
    assert!(j.contains("\"loadavg_1m_start\":"));
    let plain = timed_run_with(&msgs, &levels, SEED, 1_000);
    assert!(!plain.contains("\"per_level\""));
    assert!(plain.contains("\"loadavg_1m_end\":"));
}
