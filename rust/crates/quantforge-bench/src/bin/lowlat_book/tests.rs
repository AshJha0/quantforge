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
