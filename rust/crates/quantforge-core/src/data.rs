//! Market-data checks (`data-checks.md`).
use crate::error::{Result, fail};
use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct Quote {
    pub instrument_id: String,
    pub event_time: i64,
    pub bid: Option<f64>,
    pub ask: Option<f64>,
    pub indicative: bool,
}

#[derive(Debug, Clone)]
pub struct CheckInputs {
    pub as_of: i64,
    pub quotes: Vec<Quote>,
    pub stale_after_seconds: i64,
    pub max_relative_spread: Option<f64>,
    pub positive_only: bool,
    pub outlier_threshold: f64,
    pub outlier_min_history: i64,
    pub history: HashMap<String, Vec<f64>>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Checked {
    pub instrument_id: String,
    pub quote_status: &'static str,
    pub quality_flags: Vec<&'static str>,
}

fn median(v: &[f64]) -> f64 {
    let mut s = v.to_vec();
    s.sort_by(f64::total_cmp);
    let n = s.len();
    if n % 2 == 1 {
        s[n / 2]
    } else {
        (s[n / 2 - 1] + s[n / 2]) / 2.0
    }
}

fn is_outlier(mid: f64, history: &[f64], threshold: f64) -> bool {
    let med = median(history);
    let dev: Vec<f64> = history.iter().map(|h| (h - med).abs()).collect();
    let mad = median(&dev);
    mad != 0.0 && (mid - med).abs() / (1.4826 * mad) > threshold
}

pub fn check_quotes(i: &CheckInputs) -> Result<Vec<Checked>> {
    if i.stale_after_seconds <= 0
        || i.max_relative_spread.is_some_and(|v| v <= 0.0)
        || i.outlier_threshold <= 0.0
        || i.outlier_min_history < 3
    {
        return fail("E_INPUT", "a limit is out of range");
    }
    if i.quotes.iter().any(|q| q.event_time > i.as_of) {
        return fail("E_INPUT", "event_time is after as_of");
    }
    Ok(i.quotes.iter().map(|q| check_one(i, q)).collect())
}

fn check_one(i: &CheckInputs, q: &Quote) -> Checked {
    let mut flags = Vec::new();
    let non_positive = i.positive_only && [q.bid, q.ask].iter().flatten().any(|v| *v <= 0.0);
    let base = if q.indicative { "INDICATIVE" } else { "FIRM" };
    let status;
    if let (Some(bid), Some(ask)) = (q.bid, q.ask) {
        let crossed = bid > ask;
        let stale = i.as_of - q.event_time > i.stale_after_seconds;
        let mid = (bid + ask) / 2.0;
        if crossed {
            flags.push("CROSSED");
        }
        if bid == ask {
            flags.push("LOCKED");
        }
        if stale {
            flags.push("STALE");
        }
        if let Some(limit) = i.max_relative_spread
            && !crossed
            && mid != 0.0
            && (ask - bid) / mid.abs() > limit
        {
            flags.push("WIDE_SPREAD");
        }
        if non_positive {
            flags.push("NON_POSITIVE");
        }
        if !crossed
            && let Some(h) = i.history.get(&q.instrument_id)
            && h.len() as i64 >= i.outlier_min_history
            && is_outlier(mid, h, i.outlier_threshold)
        {
            flags.push("OUTLIER");
        }
        status = if crossed {
            "CROSSED"
        } else if stale {
            "STALE"
        } else {
            base
        };
    } else {
        if q.bid.is_none() {
            flags.push("MISSING_BID");
        }
        if q.ask.is_none() {
            flags.push("MISSING_ASK");
        }
        if non_positive {
            flags.push("NON_POSITIVE");
        }
        status = "MISSING";
    }
    Checked {
        instrument_id: q.instrument_id.clone(),
        quote_status: status,
        quality_flags: flags,
    }
}
