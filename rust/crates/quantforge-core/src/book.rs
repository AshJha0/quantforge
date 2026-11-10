//! Book lifecycle and end-of-day marks (`07-portfolio/book-lifecycle.md`, ruling F-34).
use std::collections::{BTreeMap, BTreeSet, HashSet};

use crate::dates::Date;
use crate::error::{Result, fail};

#[derive(Debug, Clone)]
pub enum Event {
    Trade {
        instrument: String,
        quantity: f64,
        price: f64,
    },
    Fixing {
        index: String,
        value: f64,
    },
    Expiry {
        instrument: String,
        price: f64,
    },
    Default {
        instrument: String,
        price: f64,
    },
    Roll {
        from: String,
        to: String,
        from_price: f64,
        to_price: f64,
    },
}

#[derive(Debug, Clone, Default)]
pub struct BookState {
    /// `instrument -> (quantity, average_cost)`, open positions only.
    pub positions: BTreeMap<String, (f64, f64)>,
    pub realized: BTreeMap<String, f64>,
    /// `(index, date) -> value`.
    pub fixings: BTreeMap<(String, Date), f64>,
}

impl BookState {
    fn trade(&mut self, closed: &BTreeSet<String>, inst: &str, dq: f64, p: f64) -> Result<()> {
        if closed.contains(inst) {
            return fail("E_INPUT", "a trade into a closed instrument");
        }
        let (q, a) = self.positions.get(inst).copied().unwrap_or((0.0, 0.0));
        if q == 0.0 || q.signum() == dq.signum() {
            let q2 = q + dq;
            self.positions
                .insert(inst.to_string(), (q2, (q * a + dq * p) / q2));
            return Ok(());
        }
        let c = dq.abs().min(q.abs());
        *self.realized.entry(inst.to_string()).or_insert(0.0) += q.signum() * c * (p - a);
        let q2 = q + dq;
        if q2 == 0.0 {
            self.positions.remove(inst);
        } else if q2.signum() == q.signum() {
            self.positions.insert(inst.to_string(), (q2, a));
        } else {
            self.positions.insert(inst.to_string(), (q2, p));
        }
        Ok(())
    }

    fn held(&self, inst: &str) -> Result<f64> {
        match self.positions.get(inst) {
            Some((q, _)) if *q != 0.0 => Ok(*q),
            _ => fail("E_INPUT", "the instrument is not held"),
        }
    }
}

/// `book.lifecycle.apply`.
pub fn apply(opening: &[(String, f64, f64)], events: &[(Date, Event)]) -> Result<BookState> {
    if events.windows(2).any(|w| w[1].0 < w[0].0) {
        return fail("E_INPUT", "events must be in date order");
    }
    for (_, e) in events {
        if let Event::Trade { quantity, .. } = e
            && *quantity == 0.0
        {
            return fail("E_DOMAIN", "a trade quantity is 0");
        }
    }
    let mut b = BookState::default();
    for (i, q, a) in opening {
        if *q != 0.0 {
            b.positions.insert(i.clone(), (*q, *a));
        }
    }
    let mut closed = BTreeSet::new();
    for (date, e) in events {
        match e {
            Event::Trade {
                instrument,
                quantity,
                price,
            } => b.trade(&closed, instrument, *quantity, *price)?,
            Event::Fixing { index, value } => {
                if b.fixings.insert((index.clone(), *date), *value).is_some() {
                    return fail("E_INPUT", "the same fixing twice");
                }
            }
            Event::Expiry { instrument, price } | Event::Default { instrument, price } => {
                let q = b.held(instrument)?;
                b.trade(&closed, instrument, -q, *price)?;
                b.positions.remove(instrument);
                closed.insert(instrument.clone());
            }
            Event::Roll {
                from,
                to,
                from_price,
                to_price,
            } => {
                let q = b.held(from)?;
                if closed.contains(to) {
                    return fail("E_INPUT", "a roll into a closed instrument");
                }
                b.trade(&closed, from, -q, *from_price)?;
                b.positions.remove(from);
                closed.insert(from.clone());
                b.trade(&closed, to, q, *to_price)?;
            }
        }
    }
    Ok(b)
}

#[derive(Debug, Clone)]
pub struct Source {
    pub name: String,
    pub quotes: Vec<(String, Date, f64)>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Mark {
    pub instrument: String,
    pub price: Option<f64>,
    pub source: Option<String>,
    pub status: &'static str,
    pub age_days: Option<i64>,
    pub ipv_diff: Option<f64>,
    pub ipv_breach: bool,
}

/// `book.marks.resolve`.
pub fn resolve(
    as_of: Date,
    instruments: &[String],
    sources: &[Source],
    max_age_days: i64,
    ipv: &[(String, f64)],
    threshold: f64,
) -> Result<Vec<Mark>> {
    let mut names = HashSet::new();
    if !sources.iter().all(|s| names.insert(s.name.as_str())) {
        return fail("E_INPUT", "source names must be unique");
    }
    if max_age_days < 0 {
        return fail("E_DOMAIN", "max_age_days must not be negative");
    }
    if ipv.iter().any(|x| x.1.is_nan() || x.1 <= 0.0) {
        return fail("E_DOMAIN", "IPV prices must be positive");
    }
    let mut out = Vec::new();
    for inst in instruments {
        let mut found: Option<(f64, &str, &'static str, i64)> = None;
        for (k, s) in sources.iter().enumerate() {
            if let Some(q) = s.quotes.iter().find(|q| &q.0 == inst && q.1 == as_of) {
                found = Some((q.2, &s.name, if k == 0 { "PRIMARY" } else { "FALLBACK" }, 0));
                break;
            }
        }
        if found.is_none() {
            let mut best: Option<(Date, f64, &str)> = None;
            for s in sources {
                for q in s.quotes.iter().filter(|q| &q.0 == inst && q.1 < as_of) {
                    let age = as_of.serial() - q.1.serial();
                    if age <= max_age_days && best.is_none_or(|b| q.1 > b.0) {
                        best = Some((q.1, q.2, &s.name));
                    }
                }
            }
            found = best.map(|(d, p, n)| (p, n, "STALE", as_of.serial() - d.serial()));
        }
        let ipv_price = ipv.iter().find(|x| &x.0 == inst).map(|x| x.1);
        let (ipv_diff, ipv_breach) = match (found, ipv_price) {
            (Some((m, ..)), Some(v)) => {
                let d = (m - v) / v;
                (Some(d), d.abs() > threshold)
            }
            _ => (None, false),
        };
        out.push(match found {
            Some((p, n, st, age)) => Mark {
                instrument: inst.clone(),
                price: Some(p),
                source: Some(n.to_string()),
                status: st,
                age_days: Some(age),
                ipv_diff,
                ipv_breach,
            },
            None => Mark {
                instrument: inst.clone(),
                price: None,
                source: None,
                status: "MISSING",
                age_days: None,
                ipv_diff,
                ipv_breach,
            },
        });
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn trade(q: f64, p: f64) -> (Date, Event) {
        (
            Date::parse("2026-11-10").unwrap(),
            Event::Trade {
                instrument: "X".into(),
                quantity: q,
                price: p,
            },
        )
    }

    #[test]
    fn close_to_zero_removes_and_reversal_opens_at_trade_price() {
        let b = apply(&[], &[trade(10.0, 100.0), trade(-10.0, 101.0)]).unwrap();
        assert!(b.positions.is_empty());
        assert_eq!(b.realized["X"], 10.0);
        let b = apply(&[], &[trade(10.0, 100.0), trade(-15.0, 102.0)]).unwrap();
        assert_eq!(b.positions["X"], (-5.0, 102.0));
        assert_eq!(b.realized["X"], 20.0);
    }
}
