//! As-of store and replay (`asof-store.md`). Pure functions of a log.
use crate::error::{Result, err, fail};
use crate::json::{Json, obj};
use crate::sha256::sha256_hex;
use crate::snapshot::{canonical_bytes, hash_value};
use crate::time::{format_instant, parse_instant};
use std::collections::HashMap;

#[derive(Debug, Clone)]
struct Record {
    sequence: i64,
    series_id: String,
    event_time: i64,
    knowledge_time: i64,
    value: Json,
    deleted: bool,
}

#[derive(Debug, Clone)]
pub struct Log<'a> {
    raw: &'a [Json],
    records: Vec<Record>,
}

fn schema(what: &str) -> crate::error::QfError {
    err("E_SCHEMA", format!("record: {what}"))
}

fn instant(r: &Json, k: &str) -> Result<i64> {
    r.get(k)
        .and_then(Json::as_str)
        .and_then(parse_instant)
        .ok_or_else(|| schema(k))
}

fn record(r: &Json) -> Result<Record> {
    let sequence = r.get("sequence").and_then(Json::as_int);
    let sequence = sequence
        .filter(|s| *s >= 1)
        .ok_or_else(|| schema("sequence"))?;
    let series_id = r.get("series_id").and_then(Json::as_str);
    let series_id = series_id
        .filter(|s| !s.is_empty())
        .ok_or_else(|| schema("series_id"))?;
    let deleted = match r.get("deleted") {
        None | Some(Json::Null) => false,
        Some(Json::Bool(b)) => *b,
        Some(_) => return Err(schema("deleted")),
    };
    Ok(Record {
        sequence,
        series_id: series_id.to_string(),
        event_time: instant(r, "event_time")?,
        knowledge_time: instant(r, "knowledge_time")?,
        value: r.get("value").ok_or_else(|| schema("value"))?.clone(),
        deleted,
    })
}

impl<'a> Log<'a> {
    /// Runs the log checks, in the spec's order.
    pub fn parse(raw: &'a [Json]) -> Result<Log<'a>> {
        let records = raw.iter().map(record).collect::<Result<Vec<_>>>()?;
        if records.windows(2).any(|w| w[1].sequence <= w[0].sequence) {
            return fail("E_INPUT", "sequence is not strictly increasing");
        }
        if records
            .windows(2)
            .any(|w| w[1].knowledge_time < w[0].knowledge_time)
        {
            return fail("E_INPUT", "knowledge_time runs backwards");
        }
        Ok(Log { raw, records })
    }

    fn view(&self, as_of: i64) -> Vec<&Record> {
        let mut best: HashMap<(&str, i64), &Record> = HashMap::new();
        for r in self.records.iter().filter(|r| r.knowledge_time <= as_of) {
            // The log is in sequence order, so a later record is the higher sequence.
            best.insert((r.series_id.as_str(), r.event_time), r);
        }
        let mut rows: Vec<&Record> = best.into_values().filter(|r| !r.deleted).collect();
        rows.sort_by(|a, b| {
            a.series_id
                .as_bytes()
                .cmp(b.series_id.as_bytes())
                .then(a.event_time.cmp(&b.event_time))
        });
        rows
    }

    pub fn query(
        &self,
        as_of: i64,
        series_id: Option<&str>,
        from: Option<i64>,
        to: Option<i64>,
    ) -> Result<Json> {
        if let (Some(f), Some(t)) = (from, to)
            && f > t
        {
            return fail("E_DATE_ORDER", "event_from is after event_to");
        }
        let rows: Vec<Json> = self
            .view(as_of)
            .into_iter()
            .filter(|r| series_id.is_none_or(|s| s == r.series_id))
            .filter(|r| from.is_none_or(|f| r.event_time >= f))
            .filter(|r| to.is_none_or(|t| r.event_time <= t))
            .map(row)
            .collect();
        Ok(rows.into())
    }

    pub fn latest(&self, as_of: i64, series_id: &str) -> Json {
        let view = self.view(as_of);
        let last = view.into_iter().rfind(|r| r.series_id == series_id);
        last.map_or(Json::Null, row)
    }

    fn snapshot_of(&self, as_of: i64) -> (String, String, i64) {
        let rows: Vec<Json> = self.view(as_of).into_iter().map(row).collect();
        let n = rows.len() as i64;
        let doc = obj([
            ("as_of", format_instant(as_of).into()),
            ("rows", rows.into()),
        ]);
        let (canonical, id) = hash_value(doc);
        (canonical, id, n)
    }

    /// Returns the canonical text and the snapshot id.
    pub fn snapshot(&self, as_of: i64) -> (String, String) {
        let (c, id, _) = self.snapshot_of(as_of);
        (c, id)
    }

    /// Returns the snapshots and the chain head.
    pub fn replay(&self, checkpoints: &[i64]) -> Result<(Json, String)> {
        if checkpoints.windows(2).any(|w| w[1] < w[0]) {
            return fail("E_INPUT", "checkpoints are out of order");
        }
        let snapshots: Vec<Json> = checkpoints
            .iter()
            .map(|&c| {
                let (_, id, n) = self.snapshot_of(c);
                obj([
                    ("as_of", format_instant(c).into()),
                    ("row_count", n.into()),
                    ("snapshot_id", id.into()),
                ])
            })
            .collect();
        Ok((snapshots.into(), self.chain().0))
    }

    /// Returns the head and every `h_i`.
    pub fn chain(&self) -> (String, Vec<String>) {
        let mut head = "0".repeat(64);
        let mut hashes = Vec::with_capacity(self.raw.len());
        for r in self.raw {
            let mut bytes = head.into_bytes();
            bytes.extend(canonical_bytes(r));
            head = sha256_hex(&bytes);
            hashes.push(head.clone());
        }
        (head, hashes)
    }
}

fn row(r: &Record) -> Json {
    obj([
        ("series_id", r.series_id.as_str().into()),
        ("event_time", format_instant(r.event_time).into()),
        ("knowledge_time", format_instant(r.knowledge_time).into()),
        ("sequence", r.sequence.into()),
        ("value", r.value.clone()),
    ])
}
