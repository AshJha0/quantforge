//! H-9 low-latency book: equivalence with `micro.book.rebuild` (`low-latency-book.md`, "Golden plan").
//! 1. Every `ob_h` golden row decoded to fixed point: book, crc32, stats and events equal the golden; error rows
//!    are rejected by the decoder with the golden's code; ob_h-0016 (36 digits) is outside the i64 fixed-point
//!    range and is rejected: the stated scope limit.
//! 2. Property test: seeded random streams of 10,000 messages; after every message top(100) on both sides equals
//!    a `BTreeMap` transcription of the normative algorithm; at the end of each stream book, crc32, stats and
//!    events equal `order_book::rebuild`. 100 streams in the default (debug) run; all 1,000 of the spec with
//!    `cargo test --release -- --ignored fast_book_property_1000`.
use quantforge_core::fast_book::{Book, FLAG_CHECKSUM, FLAG_RESUBSCRIBE, Level, Msg, MsgType};
use quantforge_core::json::{Json, parse};
use quantforge_core::order_book::rebuild;
use quantforge_core::rng::Xoshiro;
use std::collections::BTreeMap;

struct Stream {
    msgs: Vec<Msg>,
    levels: Vec<Level>,
}

fn to_fixed(v: &Json, dec: usize, is_price: bool) -> Result<i64, &'static str> {
    let s = v.as_str().ok_or("E_SCHEMA")?;
    let (neg, body) = s.strip_prefix('-').map_or((false, s), |b| (true, b));
    let (ip, fp) = body.split_once('.').unwrap_or((body, ""));
    let digit = |t: &str| t.bytes().all(|c| c.is_ascii_digit());
    if ip.is_empty() || !digit(ip) || !digit(fp) || (body.contains('.') && fp.is_empty()) {
        return Err("E_SCHEMA");
    }
    if ip.len() + fp.len() > 36 || fp.len() > 18 {
        return Err("E_LIMIT");
    }
    let zero = ip.bytes().chain(fp.bytes()).all(|c| c == b'0');
    if neg && !zero {
        return Err("E_DOMAIN");
    }
    if is_price && zero {
        return Err("E_DOMAIN");
    }
    if fp.len() > dec && fp[dec..].bytes().any(|c| c != b'0') {
        return Err("E_DOMAIN");
    }
    let mut out: i64 = 0;
    for c in ip
        .bytes()
        .chain(fp.bytes().chain(std::iter::repeat(b'0')).take(dec))
    {
        out = out
            .checked_mul(10)
            .and_then(|x| x.checked_add(i64::from(c - b'0')))
            .ok_or("E_LIMIT")?;
    }
    Ok(out)
}

fn decode(inputs: &Json) -> Result<Stream, &'static str> {
    let depth = inputs
        .get("depth")
        .and_then(Json::as_int)
        .ok_or("E_SCHEMA")?;
    if ![10, 25, 100, 500, 1000].contains(&depth) {
        return Err("E_DOMAIN");
    }
    let pd = inputs
        .get("price_decimals")
        .and_then(Json::as_int)
        .ok_or("E_SCHEMA")? as usize;
    let qd = inputs
        .get("qty_decimals")
        .and_then(Json::as_int)
        .ok_or("E_SCHEMA")? as usize;
    let mut st = Stream {
        msgs: vec![],
        levels: vec![],
    };
    for m in inputs
        .get("messages")
        .and_then(Json::as_array)
        .ok_or("E_SCHEMA")?
    {
        let mut out = Msg {
            first: st.levels.len() as u32,
            ..Msg::default()
        };
        out.kind = match m.get("type").and_then(Json::as_str) {
            Some("gap") => {
                st.msgs.push(Msg {
                    kind: MsgType::Gap,
                    ..out
                });
                continue;
            }
            Some("snapshot") => MsgType::Snapshot,
            Some("update") => MsgType::Update,
            _ => return Err("E_SCHEMA"),
        };
        for side in ["bids", "asks"] {
            let arr = m.get(side).and_then(Json::as_array).ok_or("E_SCHEMA")?;
            for l in arr {
                let pair = l.as_array().ok_or("E_SCHEMA")?;
                st.levels.push(Level {
                    px: to_fixed(&pair[0], pd, true)?,
                    qty: to_fixed(&pair[1], qd, false)?,
                });
            }
            if side == "bids" {
                out.n_bids = arr.len() as u16;
            } else {
                out.n_asks = arr.len() as u16;
            }
        }
        if let Some(c) = m.get("checksum").and_then(Json::as_int) {
            out.flags |= FLAG_CHECKSUM;
            out.checksum = c as u32;
        }
        if matches!(m.get("resubscribe"), Some(Json::Bool(true))) {
            out.flags |= FLAG_RESUBSCRIBE;
        }
        st.msgs.push(out);
    }
    Ok(st)
}

fn fixed_text(v: i64, dec: usize) -> String {
    let mut d = v.to_string();
    if dec == 0 {
        return d;
    }
    if d.len() <= dec {
        d = "0".repeat(dec + 1 - d.len()) + &d;
    }
    d.insert(d.len() - dec, '.');
    d
}

/// The comparable part of a rebuild output, as text: book, crc32, stats (14 counters), events (i, kind).
fn summary_of_json(o: &Json) -> String {
    let side = |k: &str| -> String {
        let arr = o
            .get("book")
            .and_then(|b| b.get(k))
            .and_then(Json::as_array)
            .expect("book side");
        arr.iter()
            .map(|l| {
                let p = l.as_array().expect("level");
                format!(
                    "{}:{}",
                    p[0].as_str().expect("px"),
                    p[1].as_str().expect("qty")
                )
            })
            .collect::<Vec<_>>()
            .join(",")
    };
    let mut stats = vec![];
    if let Some(Json::Obj(m)) = o.get("stats") {
        let mut m = m.clone();
        m.sort_by(|a, b| a.0.cmp(&b.0));
        for (k, v) in m {
            stats.push(format!("{k}={}", v.as_int().expect("count")));
        }
    }
    let events = o
        .get("events")
        .and_then(Json::as_array)
        .expect("events")
        .iter()
        .map(|e| {
            format!(
                "{}:{}",
                e.get("i").and_then(Json::as_int).expect("i"),
                e.get("kind").and_then(Json::as_str).expect("kind")
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "asks[{}] bids[{}] crc {} stats {} events {}",
        side("asks"),
        side("bids"),
        o.get("crc32").and_then(Json::as_int).expect("crc32"),
        stats.join(" "),
        events
    )
}

fn summary_of_book(b: &Book, pd: usize, qd: usize) -> String {
    let mut lv = vec![Level::default(); b.depth()];
    let mut side = |bid: bool| -> String {
        let n = b.top(bid, &mut lv);
        lv[..n]
            .iter()
            .map(|l| format!("{}:{}", fixed_text(l.px, pd), fixed_text(l.qty, qd)))
            .collect::<Vec<_>>()
            .join(",")
    };
    let (asks, bids) = (side(false), side(true));
    let s = b.stats();
    let mut stats = [
        ("checkpoint_checked", 0),
        ("checkpoint_failed", 0),
        ("checksum_checked", s.checksum_checked),
        ("checksum_failed", s.checksum_failed),
        ("crossed", s.crossed),
        ("deletes_of_absent_level", s.deletes_of_absent_level),
        ("gaps", s.gaps),
        ("level_changes", s.level_changes),
        ("locked", s.locked),
        ("messages", s.messages),
        ("resyncs", s.resyncs),
        ("snapshots", s.snapshots),
        ("truncated_levels", s.truncated_levels),
        ("updates", s.updates),
    ];
    stats.sort_by(|a, b| a.0.cmp(b.0));
    let stats = stats
        .iter()
        .map(|(k, v)| format!("{k}={v}"))
        .collect::<Vec<_>>()
        .join(" ");
    let events = b
        .events()
        .iter()
        .map(|(i, k)| format!("{i}:{}", k.name()))
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "asks[{asks}] bids[{bids}] crc {} stats {stats} events {events}",
        b.checksum()
    )
}

fn run(st: &Stream, depth: usize) -> Book {
    let mut b = Book::new(depth);
    for m in &st.msgs {
        b.apply(m, &st.levels);
    }
    b
}

#[test]
fn fast_book_ob_h_goldens() {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../../datasets/golden/stage_h/ob_h.json"
    );
    let text = std::fs::read_to_string(path).expect("ob_h.json");
    let (golden, _) = parse(&text).expect("json");
    let (mut ok, mut rejected) = (0, 0);
    for c in golden.get("cases").and_then(Json::as_array).expect("cases") {
        let id = c.get("case_id").and_then(Json::as_str).expect("id");
        let inp = c.get("inputs").expect("inputs");
        let exp = c.get("expected").expect("expected");
        if id == "ob_h-0016" {
            assert_eq!(
                decode(inp).err(),
                Some("E_LIMIT"),
                "{id}: stated i64 range limit"
            );
            continue;
        }
        if exp.get("status").and_then(Json::as_str) != Some("ok") {
            assert_eq!(
                decode(inp).err(),
                exp.get("error_code").and_then(Json::as_str),
                "{id}"
            );
            rejected += 1;
            continue;
        }
        let st = decode(inp).expect("decodes");
        let depth = inp.get("depth").and_then(Json::as_int).expect("depth") as usize;
        let pd = inp
            .get("price_decimals")
            .and_then(Json::as_int)
            .expect("pd") as usize;
        let qd = inp.get("qty_decimals").and_then(Json::as_int).expect("qd") as usize;
        assert_eq!(
            summary_of_book(&run(&st, depth), pd, qd),
            summary_of_json(exp.get("outputs").expect("outputs")),
            "{id}"
        );
        ok += 1;
    }
    assert_eq!((ok, rejected), (9, 7));
}

/// The C++ test's stream generator, ported draw for draw.
fn random_stream(seed: u64, depth: usize, n: usize) -> Stream {
    let mut r = Xoshiro::seeded(seed, 0);
    let mut u = |m: u64| (r.next_u64() % m) as i64;
    let mut st = Stream {
        msgs: vec![],
        levels: vec![],
    };
    let (mid, span) = (1000i64, depth as u64 + 20);
    for i in 0..n {
        let mut m = Msg {
            first: st.levels.len() as u32,
            ..Msg::default()
        };
        let roll = u(1000);
        m.kind = if roll < 3 {
            MsgType::Gap
        } else if roll < 15 || i == 1 {
            MsgType::Snapshot
        } else if roll < 40 {
            MsgType::Trade
        } else {
            MsgType::Update
        };
        if m.kind == MsgType::Trade {
            let px = mid + u(10);
            let qty = 1 + u(100);
            st.levels.push(Level { px, qty });
            m.n_bids = 1;
        } else if m.kind != MsgType::Gap {
            let snap = m.kind == MsgType::Snapshot;
            for side in 0..2 {
                let l = if snap {
                    u(depth as u64 + 15)
                } else if u(10) < 7 {
                    u(2)
                } else {
                    u(6)
                };
                for _ in 0..l {
                    let px = if side == 0 {
                        mid + 3 - u(span)
                    } else {
                        mid - 3 + u(span)
                    };
                    let zero = if snap { u(20) == 0 } else { u(10) < 3 };
                    let qty = if zero { 0 } else { 1 + u(1_000_000) };
                    st.levels.push(Level { px, qty });
                }
                if side == 0 {
                    m.n_bids = l as u16;
                } else {
                    m.n_asks = l as u16;
                }
            }
            if u(20) == 0 {
                m.flags |= FLAG_CHECKSUM;
                m.checksum = u(1 << 32) as u32;
            }
            if snap && u(3) == 0 {
                m.flags |= FLAG_RESUBSCRIBE;
            }
        }
        st.msgs.push(m);
    }
    st
}

fn to_json(st: &Stream) -> String {
    let mut parts = vec![];
    for m in st.msgs.iter().filter(|m| m.kind != MsgType::Trade) {
        if m.kind == MsgType::Gap {
            parts.push(r#"{"type":"gap"}"#.to_string());
            continue;
        }
        let f = m.first as usize;
        let side = |a: usize, n: u16| {
            st.levels[a..a + usize::from(n)]
                .iter()
                .map(|l| format!("[\"{}\",\"{}\"]", fixed_text(l.px, 1), fixed_text(l.qty, 8)))
                .collect::<Vec<_>>()
                .join(",")
        };
        parts.push(format!(
            r#"{{"type":"{}","t":"2026-01-01T00:00:00Z","checksum":{}{},"bids":[{}],"asks":[{}]}}"#,
            if m.kind == MsgType::Snapshot {
                "snapshot"
            } else {
                "update"
            },
            if m.flags & FLAG_CHECKSUM != 0 {
                m.checksum.to_string()
            } else {
                "null".into()
            },
            if m.flags & FLAG_RESUBSCRIBE != 0 {
                r#","resubscribe":true"#
            } else {
                ""
            },
            side(f, m.n_bids),
            side(f + usize::from(m.n_bids), m.n_asks)
        ));
    }
    format!("[{}]", parts.join(","))
}

fn property(streams: u64) {
    let depths = [10usize, 25, 100];
    let mut lv = vec![Level::default(); 100];
    for s in 0..streams {
        let depth = depths[(s % 3) as usize];
        let st = random_stream(20_261_117 + s, depth, 10_000);
        let mut b = Book::new(depth);
        let (mut bids, mut asks) = (BTreeMap::<i64, i64>::new(), BTreeMap::<i64, i64>::new());
        let mut live = false;
        for (i, m) in st.msgs.iter().enumerate() {
            b.apply(m, &st.levels);
            match m.kind {
                MsgType::Trade => {}
                MsgType::Gap => {
                    bids.clear();
                    asks.clear();
                    live = false;
                }
                _ if m.kind == MsgType::Update && !live => {}
                _ => {
                    if m.kind == MsgType::Snapshot {
                        bids.clear();
                        asks.clear();
                        live = true;
                    }
                    let f = m.first as usize;
                    let nb = usize::from(m.n_bids);
                    let snap = m.kind == MsgType::Snapshot;
                    for (k, l) in st.levels[f..f + nb + usize::from(m.n_asks)]
                        .iter()
                        .enumerate()
                    {
                        let side = if k < nb { &mut bids } else { &mut asks };
                        if l.qty != 0 {
                            side.insert(l.px, l.qty);
                        } else if !snap {
                            side.remove(&l.px);
                        }
                    }
                    while bids.len() > depth {
                        bids.pop_first();
                    }
                    while asks.len() > depth {
                        asks.pop_last();
                    }
                }
            }
            let n = b.top(true, &mut lv);
            let want: Vec<Level> = bids
                .iter()
                .rev()
                .take(100)
                .map(|(&px, &qty)| Level { px, qty })
                .collect();
            assert_eq!(&lv[..n], &want[..], "stream {s} bids at message {i}");
            let n = b.top(false, &mut lv);
            let want: Vec<Level> = asks
                .iter()
                .take(100)
                .map(|(&px, &qty)| Level { px, qty })
                .collect();
            assert_eq!(&lv[..n], &want[..], "stream {s} asks at message {i}");
        }
        let (msgs, _) = parse(&to_json(&st)).expect("json");
        let out = rebuild(
            msgs.as_array().expect("array"),
            depth as i64,
            1,
            8,
            None,
            false,
        )
        .expect("rebuild");
        assert_eq!(
            summary_of_book(&b, 1, 8),
            summary_of_json(&out),
            "stream {s}"
        );
    }
}

#[test]
fn fast_book_property_100() {
    property(100);
}

#[test]
#[ignore = "the spec's full 1,000 streams; run with --release"]
fn fast_book_property_1000() {
    property(1000);
}

#[test]
fn fast_book_limit_cases() {
    let mut b = Book::new(3);
    let lv = [
        Level { px: 100, qty: 1 },
        Level { px: 99, qty: 1 },
        Level { px: 98, qty: 1 },
        Level { px: 101, qty: 1 },
        Level { px: 102, qty: 1 },
        Level { px: 103, qty: 1 },
    ];
    b.apply(
        &Msg {
            kind: MsgType::Snapshot,
            n_bids: 3,
            n_asks: 3,
            ..Msg::default()
        },
        &lv,
    );
    b.apply(
        &Msg {
            kind: MsgType::Update,
            n_bids: 1,
            ..Msg::default()
        },
        &[Level { px: 50, qty: 7 }],
    );
    assert_eq!(b.stats().truncated_levels, 1);
    assert_eq!(b.qty_at(true, 50), 0);
    let sweep = [
        Level { px: 100, qty: 0 },
        Level { px: 99, qty: 0 },
        Level { px: 98, qty: 0 },
    ];
    b.apply(
        &Msg {
            kind: MsgType::Update,
            n_bids: 3,
            ..Msg::default()
        },
        &sweep,
    );
    assert_eq!(b.best_bid(), None);
    assert_eq!(b.best_ask().map(|l| l.px), Some(101));
    b.apply(
        &Msg {
            kind: MsgType::Trade,
            n_bids: 1,
            ..Msg::default()
        },
        &[Level { px: 101, qty: 1 }],
    );
    assert_eq!((b.stats().trades, b.stats().messages, b.grows()), (1, 3, 0));
    let wide: Vec<Level> = (0..400)
        .map(|k| Level {
            px: 1000 - k,
            qty: 1,
        })
        .collect();
    let mut w = Book::new(10);
    w.apply(
        &Msg {
            kind: MsgType::Snapshot,
            n_bids: 400,
            ..Msg::default()
        },
        &wide,
    );
    assert!(w.grows() >= 1);
    assert_eq!(w.best_bid().map(|l| l.px), Some(1000));
    assert_eq!(w.stats().truncated_levels, 390);
}
