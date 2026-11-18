//! `micro.book.rebuild`: market-by-price book rebuild from Kraken-style L2 messages.
//!
//! Spec: `specifications/09-microstructure/order-book.md` (rulings HR-11 to HR-17, HR-29, HR-41).
//! Prices and quantities are exact decimal strings (HR-12); the book keeps the strings as
//! received. Checksum failures, crossed and locked books are counted and reported, never raised.
use crate::decimal::Dec;
use crate::error::{QfError, Result, err};
use crate::json::Json;
use crate::time::parse_instant;
use std::collections::{BTreeMap, HashMap};

pub const DEPTHS: [i64; 5] = [10, 25, 100, 500, 1000];
pub const MAX_MESSAGES: usize = 50_000_000;
pub const MAX_EVENTS: usize = 10_000;
const STATS: [&str; 14] = [
    "messages",
    "snapshots",
    "updates",
    "level_changes",
    "deletes_of_absent_level",
    "truncated_levels",
    "checksum_checked",
    "checksum_failed",
    "checkpoint_checked",
    "checkpoint_failed",
    "crossed",
    "locked",
    "gaps",
    "resyncs",
];

fn at(code: &'static str, path: &str, what: &str) -> QfError {
    let mut e = err(code, format!("{path}: {what}"));
    e.field = Some(path.to_string());
    e
}

/// A decimal string, else `E_SCHEMA` (HR-12: numbers are refused).
pub fn dec(v: Option<&Json>, path: &str) -> Result<Dec> {
    match v.and_then(Json::as_str).and_then(Dec::parse) {
        Some(r) => r,
        None => Err(at("E_SCHEMA", path, "not a decimal string")),
    }
}

/// One level: price, price text, quantity, quantity text.
type Level = (Dec, String, Dec, String);

fn levels(raw: Option<&Json>, path: &str) -> Result<Vec<Level>> {
    let Some(list) = raw.map_or(Some(&[][..]), Json::as_array) else {
        return Err(at("E_SCHEMA", path, "not an array"));
    };
    let mut out = Vec::with_capacity(list.len());
    for (k, lv) in list.iter().enumerate() {
        let pair = lv.as_array().filter(|a| a.len() == 2);
        let Some(pair) = pair else {
            return Err(at("E_SCHEMA", path, "not a [price, qty] pair"));
        };
        let p = dec(pair.first(), &format!("{path}/{k}/0"))?;
        let q = dec(pair.get(1), &format!("{path}/{k}/1"))?;
        if p.signum() <= 0 {
            return Err(at("E_DOMAIN", path, "price must be positive"));
        }
        if q.signum() < 0 {
            return Err(at("E_DOMAIN", path, "negative quantity"));
        }
        let text = |i: usize| pair[i].as_str().unwrap_or_default().to_string();
        out.push((p, text(0), q, text(1)));
    }
    Ok(out)
}

/// [KR-CRC]: the value at the pair's precision, decimal point and leading zeros removed.
fn component(text: &str, places: u32) -> Result<String> {
    let v = Dec::parse(text).unwrap_or(Ok(Dec::ZERO))?;
    let fixed = v.fixed(places).ok_or_else(|| {
        err(
            "E_DOMAIN",
            format!("{text} has more than {places} decimals"),
        )
    })?;
    let s = fixed.replace('.', "");
    let s = s.trim_start_matches('0');
    Ok(if s.is_empty() { "0".into() } else { s.into() })
}

/// CRC-32 (IEEE 802.3, reflected, as zlib).
pub fn crc32(data: &[u8]) -> u32 {
    let mut c = 0xFFFF_FFFFu32;
    for &b in data {
        c ^= u32::from(b);
        for _ in 0..8 {
            c = if c & 1 == 1 {
                (c >> 1) ^ 0xEDB8_8320
            } else {
                c >> 1
            };
        }
    }
    !c
}

struct Book {
    depth: usize,
    bids: BTreeMap<Dec, String>,
    asks: BTreeMap<Dec, String>,
}

impl Book {
    fn new(depth: usize) -> Book {
        Book {
            depth,
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
        }
    }

    fn side(&mut self, bid: bool) -> &mut BTreeMap<Dec, String> {
        if bid { &mut self.bids } else { &mut self.asks }
    }

    /// Best first: bids descending, asks ascending.
    fn ordered(&self, bid: bool) -> Vec<(Dec, &String)> {
        if bid {
            self.bids.iter().rev().map(|(p, q)| (*p, q)).collect()
        } else {
            self.asks.iter().map(|(p, q)| (*p, q)).collect()
        }
    }

    fn truncate(&mut self) -> i64 {
        let mut dropped = 0;
        while self.bids.len() > self.depth {
            self.bids.pop_first();
            dropped += 1;
        }
        while self.asks.len() > self.depth {
            self.asks.pop_last();
            dropped += 1;
        }
        dropped
    }

    fn checksum_string(&self, ptext: &HashMap<Dec, String>, pd: u32, qd: u32) -> Result<String> {
        let mut out = String::new();
        for bid in [false, true] {
            for (p, q) in self.ordered(bid).into_iter().take(10) {
                out.push_str(&component(&ptext[&p], pd)?);
                out.push_str(&component(q, qd)?);
            }
        }
        Ok(out)
    }
}

struct Message {
    kind: &'static str,
    bids: Vec<Level>,
    asks: Vec<Level>,
    checksum: Option<u32>,
    resubscribe: bool,
    t: Option<i64>,
}

fn instant(v: Option<&Json>, path: &str) -> Result<i64> {
    v.and_then(Json::as_str)
        .and_then(parse_instant)
        .ok_or_else(|| at("E_SCHEMA", path, "not a timestamp"))
}

fn parse_message(m: &Json, i: usize) -> Result<Message> {
    let kind = match m.get("type").and_then(Json::as_str) {
        Some("snapshot") => "snapshot",
        Some("update") => "update",
        Some("gap") => "gap",
        _ => return Err(at("E_SCHEMA", &format!("messages/{i}"), "not a message")),
    };
    if kind == "gap" {
        return Ok(Message {
            kind,
            bids: Vec::new(),
            asks: Vec::new(),
            checksum: None,
            resubscribe: false,
            t: None,
        });
    }
    let checksum = match m.get("checksum") {
        None | Some(Json::Null) => None,
        Some(v) => Some(
            v.as_int()
                .and_then(|n| u32::try_from(n).ok())
                .ok_or_else(|| at("E_SCHEMA", &format!("messages/{i}/checksum"), "not a u32"))?,
        ),
    };
    let t = match m.get("t") {
        None | Some(Json::Null) => None,
        v => Some(instant(v, &format!("messages/{i}/t"))?),
    };
    Ok(Message {
        kind,
        bids: levels(m.get("bids"), &format!("messages/{i}/bids"))?,
        asks: levels(m.get("asks"), &format!("messages/{i}/asks"))?,
        checksum,
        resubscribe: m.get("resubscribe") == Some(&Json::Bool(true)),
        t,
    })
}

struct State {
    stats: HashMap<&'static str, i64>,
    events: Vec<Json>,
    omitted: i64,
}

impl State {
    fn bump(&mut self, k: &'static str, by: i64) {
        *self.stats.entry(k).or_insert(0) += by;
    }

    fn event(&mut self, i: i64, kind: &str) {
        if self.events.len() < MAX_EVENTS {
            self.events.push(Json::Obj(vec![
                ("i".into(), Json::Int(i)),
                ("kind".into(), kind.into()),
            ]));
        } else {
            self.omitted += 1;
        }
    }
}

type Checkpoint = (i64, Vec<Level>, Vec<Level>);

/// Compares the book's top levels with each checkpoint stamped before `upto` (all if `None`).
fn check_points(
    st: &mut State,
    book: &Book,
    cps: &[Checkpoint],
    next: &mut usize,
    i: i64,
    upto: Option<i64>,
) {
    while *next < cps.len() && upto.is_none_or(|u| cps[*next].0 < u) {
        let (_, cb, ca) = &cps[*next];
        *next += 1;
        st.bump("checkpoint_checked", 1);
        let mut ok = true;
        for (bid, lv) in [(true, cb), (false, ca)] {
            let ours: Vec<(Dec, &String)> = book.ordered(bid).into_iter().take(lv.len()).collect();
            let mut want: Vec<(Dec, Dec)> = lv.iter().map(|l| (l.0, l.2)).collect();
            want.sort();
            if bid {
                want.reverse();
            }
            if ours.len() != want.len()
                || ours
                    .iter()
                    .zip(&want)
                    .any(|(a, b)| a.0 != b.0 || Dec::parse(a.1).and_then(Result::ok) != Some(b.1))
            {
                ok = false;
            }
        }
        if !ok {
            st.bump("checkpoint_failed", 1);
            st.event(i, "CHECKPOINT_FAIL");
        }
    }
}

/// The rebuild. `messages` and `checkpoints` are the raw JSON lists.
pub fn rebuild(
    messages: &[Json],
    depth: i64,
    price_decimals: i64,
    qty_decimals: i64,
    checkpoints: Option<&[Json]>,
    emit_checksum_string: bool,
) -> Result<Json> {
    if !DEPTHS.contains(&depth) {
        return Err(at(
            "E_DOMAIN",
            "depth",
            "must be one of 10, 25, 100, 500, 1000",
        ));
    }
    if !(0..=18).contains(&price_decimals) || !(0..=18).contains(&qty_decimals) {
        return Err(at("E_DOMAIN", "price_decimals", "decimals out of range"));
    }
    if messages.len() > MAX_MESSAGES {
        return Err(at("E_LIMIT", "messages", "more than 50,000,000 messages"));
    }
    let (pd, qd) = (price_decimals as u32, qty_decimals as u32);
    // Parse everything first: schema and domain errors come before any counting.
    let parsed = messages
        .iter()
        .enumerate()
        .map(|(i, m)| parse_message(m, i))
        .collect::<Result<Vec<_>>>()?;
    let mut cps: Vec<Checkpoint> = Vec::new();
    for (k, c) in checkpoints.unwrap_or_default().iter().enumerate() {
        if !matches!(c, Json::Obj(_)) {
            return Err(at("E_SCHEMA", &format!("checkpoints/{k}"), "not an object"));
        }
        cps.push((
            instant(c.get("t"), &format!("checkpoints/{k}/t"))?,
            levels(c.get("bids"), &format!("checkpoints/{k}/bids"))?,
            levels(c.get("asks"), &format!("checkpoints/{k}/asks"))?,
        ));
    }

    let mut st = State {
        stats: HashMap::new(),
        events: Vec::new(),
        omitted: 0,
    };
    let depth = depth as usize;
    let mut book = Book::new(depth);
    let mut ptext: HashMap<Dec, String> = HashMap::new();
    let (mut live, mut pending_resync, mut cp_next) = (false, false, 0usize);

    for (i, m) in parsed.iter().enumerate() {
        let ii = i as i64;
        if m.kind == "gap" {
            st.bump("gaps", 1);
            book = Book::new(depth);
            live = false;
            st.event(ii, "GAP");
            continue;
        }
        if !cps.is_empty() && m.t.is_some() {
            check_points(&mut st, &book, &cps, &mut cp_next, ii - 1, m.t);
        }
        st.bump("messages", 1);
        if m.kind == "snapshot" {
            st.bump("snapshots", 1);
            if m.resubscribe && pending_resync {
                st.bump("resyncs", 1);
            }
            pending_resync = false;
            book = Book::new(depth);
            for (bid, lv) in [(true, &m.bids), (false, &m.asks)] {
                for (p, pt, q, qt) in lv {
                    if !q.is_zero() {
                        book.side(bid).insert(*p, qt.clone());
                        ptext.insert(*p, pt.clone());
                    }
                }
            }
            live = true;
        } else {
            st.bump("updates", 1);
            if !live {
                st.event(ii, "UPDATE_BEFORE_SNAPSHOT");
                continue;
            }
            for (bid, lv) in [(true, &m.bids), (false, &m.asks)] {
                for (p, pt, q, qt) in lv {
                    st.bump("level_changes", 1);
                    if q.is_zero() {
                        if book.side(bid).remove(p).is_none() {
                            st.bump("deletes_of_absent_level", 1);
                        }
                    } else {
                        book.side(bid).insert(*p, qt.clone());
                        ptext.insert(*p, pt.clone());
                    }
                }
            }
        }
        let dropped = book.truncate();
        st.bump("truncated_levels", dropped);
        if let Some(cs) = m.checksum {
            st.bump("checksum_checked", 1);
            if crc32(book.checksum_string(&ptext, pd, qd)?.as_bytes()) != cs {
                st.bump("checksum_failed", 1);
                pending_resync = true;
                st.event(ii, "CHECKSUM_FAIL");
            }
        }
        if let (Some((bb, _)), Some((ba, _))) =
            (book.bids.last_key_value(), book.asks.first_key_value())
        {
            if bb > ba {
                st.bump("crossed", 1);
                st.event(ii, "CROSSED");
            } else if bb == ba {
                st.bump("locked", 1);
                st.event(ii, "LOCKED");
            }
        }
    }
    if !cps.is_empty() {
        check_points(
            &mut st,
            &book,
            &cps,
            &mut cp_next,
            parsed.len() as i64 - 1,
            None,
        );
    }

    let final_string = book.checksum_string(&ptext, pd, qd)?;
    let side = |bid: bool| {
        Json::Arr(
            book.ordered(bid)
                .into_iter()
                .map(|(p, q)| Json::Arr(vec![ptext[&p].clone().into(), q.clone().into()]))
                .collect(),
        )
    };
    let mut stats: Vec<(String, Json)> = STATS
        .iter()
        .map(|k| {
            (
                (*k).to_string(),
                Json::Int(st.stats.get(k).copied().unwrap_or(0)),
            )
        })
        .collect();
    stats.sort_by(|a, b| a.0.cmp(&b.0));
    // Canonical JSON (HR-29): keys in sorted order.
    let mut out = vec![
        (
            "book".to_string(),
            Json::Obj(vec![
                ("asks".into(), side(false)),
                ("bids".into(), side(true)),
            ]),
        ),
        (
            "crc32".into(),
            Json::Int(i64::from(crc32(final_string.as_bytes()))),
        ),
    ];
    if emit_checksum_string {
        out.push(("checksum_string".into(), final_string.into()));
    }
    out.push(("events".into(), Json::Arr(st.events)));
    if st.omitted > 0 {
        out.push(("events_omitted".into(), Json::Int(st.omitted)));
    }
    out.push(("stats".into(), Json::Obj(stats)));
    Ok(Json::Obj(out))
}

#[cfg(test)]
mod tests {
    use super::crc32;

    #[test]
    fn crc32_matches_zlib() {
        assert_eq!(crc32(b""), 0);
        assert_eq!(crc32(b"123456789"), 0xCBF4_3926);
    }
}
