//! `exec.sim.lit.run`: a simulated lit matching engine (price-time priority).
//!
//! Spec: `specifications/10-execution/lit-matching.md` (rulings HR-25 to HR-31). Simulated venue;
//! not a real exchange. Prices, quantities and fees are exact decimals (HR-12); the engine is
//! deterministic, so the same event list always gives the same output.
//!
//! Priority within a price (HR-27): displayed quantity by `seq`, then non-displayed `PEG_MID`
//! orders by `seq`. An iceberg's hidden quantity is refreshed into a new displayed slice at the
//! back of the queue (new `seq`) as soon as its shown part is filled ([CME-FIFO]). Pegs never
//! take: a peg priced at or through the opposite best is stepped one tick away from it, other
//! pegs included, so two `PEG_MID` orders on an on-grid mid never lock.
use crate::decimal::Dec;
use crate::error::{QfError, Result, err};
use crate::json::Json;
use crate::order_book::dec;
use std::collections::{BTreeMap, HashSet};

pub const LABEL: &str = "simulated venue; not a real exchange";
pub const MAX_EVENTS: usize = 10_000_000;
const TYPES: [&str; 8] = [
    "LIMIT",
    "MARKET",
    "IOC",
    "FOK",
    "ICEBERG",
    "POST_ONLY",
    "PEG_MID",
    "PEG_PRIMARY",
];

fn at(code: &'static str, path: &str, what: &str) -> QfError {
    let mut e = err(code, format!("{path}: {what}"));
    e.field = Some(path.to_string());
    e
}

#[derive(Clone, Debug)]
struct Order {
    id: String,
    trader: String,
    buy: bool,
    typ: &'static str,
    cap: Option<Dec>,
    price: Option<Dec>,
    display: Dec,
    hidden: Dec,
    slice: Dec,
    seq: i64,
}

impl Order {
    fn open(&self) -> Result<Dec> {
        self.display.checked_add(self.hidden)
    }
    fn is_mid(&self) -> bool {
        self.typ == "PEG_MID"
    }
    fn is_peg(&self) -> bool {
        self.typ == "PEG_MID" || self.typ == "PEG_PRIMARY"
    }
}

#[derive(Default, Clone, Copy)]
struct Cons {
    submitted: Dec,
    filled: Dec,
    cancelled: Dec,
    rejected: Dec,
}

struct Engine {
    tick: Dec,
    lot: Dec,
    taker_fee: Dec,
    maker_rebate: Dec,
    resting: BTreeMap<String, Order>,
    seen: HashSet<String>,
    seq: i64,
    fills: Vec<Json>,
    rejects: Vec<Json>,
    cancelled: Vec<Json>,
    fees: BTreeMap<String, Dec>,
    cons: BTreeMap<String, Cons>,
}

fn marketable(buy: bool, limit: Option<Dec>, price: Dec) -> bool {
    limit.is_none_or(|l| if buy { price <= l } else { price >= l })
}

fn pair(a: (&str, Json), b: (&str, Json)) -> Json {
    Json::Obj(vec![(a.0.into(), a.1), (b.0.into(), b.1)])
}

fn s(d: Dec) -> Json {
    d.to_string().into()
}

impl Engine {
    fn next_seq(&mut self) -> i64 {
        self.seq += 1;
        self.seq
    }

    fn on_grid(x: Dec, unit: Dec, what: &str) -> Result<()> {
        if x.on_grid(unit)? {
            Ok(())
        } else {
            Err(at(
                "E_DOMAIN",
                what,
                &format!("{x} is not a multiple of {unit}"),
            ))
        }
    }

    /// Best resting price of a side.
    fn best(&self, buy: bool, exclude_mid: bool, exclude: Option<&str>) -> Option<Dec> {
        let ps = self.resting.values().filter(|o| {
            o.buy == buy && !(exclude_mid && o.is_mid()) && Some(o.id.as_str()) != exclude
        });
        let ps = ps.filter_map(|o| o.price);
        if buy { ps.max() } else { ps.min() }
    }

    fn available(&self, buy: bool, limit: Option<Dec>) -> Result<Dec> {
        let mut t = Dec::ZERO;
        for o in self.resting.values().filter(|o| o.buy != buy) {
            if o.price.is_some_and(|p| marketable(buy, limit, p)) {
                t = t.checked_add(o.open()?)?;
            }
        }
        Ok(t)
    }

    /// The id at the front of the queue at `price` (shown orders by seq, then `PEG_MID` by seq).
    fn front(&self, buy_side: bool, price: Dec) -> Option<String> {
        self.resting
            .values()
            .filter(|o| o.buy == buy_side && o.price == Some(price))
            .min_by_key(|o| (o.is_mid(), o.seq))
            .map(|o| o.id.clone())
    }

    fn matched(&mut self, taker: &Order, limit: Option<Dec>, mut qty: Dec) -> Result<Dec> {
        while qty.signum() > 0 {
            let Some(p) = self.best(!taker.buy, false, None) else {
                break;
            };
            if !marketable(taker.buy, limit, p) {
                break;
            }
            let Some(mid) = self.front(!taker.buy, p) else {
                break;
            };
            let maker = self.resting[&mid].clone();
            let avail = if maker.is_mid() {
                maker.hidden
            } else {
                maker.display
            };
            let q = qty.min(avail);
            self.trade(taker, &maker, p, q)?;
            qty = qty.checked_sub(q)?;
            let refresh_seq = self.seq + 1;
            let Some(m) = self.resting.get_mut(&mid) else {
                break;
            };
            if m.is_mid() {
                m.hidden = m.hidden.checked_sub(q)?;
            } else {
                m.display = m.display.checked_sub(q)?;
                if m.display.is_zero() && m.hidden.signum() > 0 {
                    // iceberg refresh, back of the queue
                    m.display = m.slice.min(m.hidden);
                    m.hidden = m.hidden.checked_sub(m.display)?;
                    m.seq = refresh_seq;
                    self.seq = refresh_seq;
                }
            }
            if self.resting[&mid].open()?.is_zero() {
                self.resting.remove(&mid);
            }
        }
        Ok(qty)
    }

    fn trade(&mut self, taker: &Order, maker: &Order, price: Dec, q: Dec) -> Result<()> {
        self.fills.push(Json::Obj(vec![
            ("maker_id".into(), maker.id.clone().into()),
            ("price".into(), s(price)),
            ("qty".into(), s(q)),
            ("seq".into(), Json::Int(self.fills.len() as i64 + 1)),
            ("taker_id".into(), taker.id.clone().into()),
        ]));
        let notional = price.checked_mul(q)?;
        let fee = self.taker_fee.checked_mul(notional)?;
        let t = self.fees.entry(taker.trader.clone()).or_default();
        *t = t.checked_add(fee)?;
        let reb = self.maker_rebate.checked_mul(notional)?;
        let m = self.fees.entry(maker.trader.clone()).or_default();
        *m = m.checked_sub(reb)?;
        for id in [&taker.id, &maker.id] {
            let c = self.cons.entry(id.clone()).or_default();
            c.filled = c.filled.checked_add(q)?;
        }
        Ok(())
    }

    fn peg_price(&self, o: &Order) -> Result<Option<Dec>> {
        let mut p = if o.is_mid() {
            let (Some(bb), Some(ba)) = (self.best(true, true, None), self.best(false, true, None))
            else {
                return Ok(None);
            };
            let two_ticks = self.tick.checked_add(self.tick)?;
            bb.checked_add(ba)?
                .div_int(two_ticks, !o.buy)?
                .checked_mul(self.tick)?
        } else {
            match self.best(o.buy, true, Some(&o.id)) {
                Some(x) => x,
                None => return Ok(None),
            }
        };
        if let Some(cap) = o.cap {
            p = if o.buy { p.min(cap) } else { p.max(cap) };
        }
        // HR-28, rounded away from crossing: a peg never takes, so it stays a tick away from the
        // opposite best, other pegs included.
        if let Some(opp) = self.best(!o.buy, false, Some(&o.id))
            && ((o.buy && p >= opp) || (!o.buy && p <= opp))
        {
            p = if o.buy {
                opp.checked_sub(self.tick)?
            } else {
                opp.checked_add(self.tick)?
            };
        }
        Ok((p.signum() > 0).then_some(p))
    }

    fn reprice(&mut self) -> Result<()> {
        let mut pegs: Vec<(i64, String)> = self
            .resting
            .values()
            .filter(|o| o.is_peg())
            .map(|o| (o.seq, o.id.clone()))
            .collect();
        pegs.sort();
        for (_, id) in pegs {
            let Some(o) = self.resting.get(&id) else {
                continue;
            };
            let p = self.peg_price(o)?;
            if p != o.price {
                let seq = self.next_seq();
                if let Some(o) = self.resting.get_mut(&id) {
                    o.price = p;
                    o.seq = seq;
                }
            }
        }
        Ok(())
    }

    fn reject(&mut self, oid: &str, reason: &str, qty: Dec) -> Result<()> {
        self.rejects
            .push(pair(("id", oid.into()), ("reason", reason.into())));
        let c = self.cons.entry(oid.to_string()).or_default();
        c.rejected = c.rejected.checked_add(qty)?;
        Ok(())
    }

    fn new_order(&mut self, e: &Json, k: usize) -> Result<()> {
        let path = format!("events/{k}");
        let (Some(oid), Some(trader)) = (
            e.get("id").and_then(Json::as_str),
            e.get("trader").and_then(Json::as_str),
        ) else {
            return Err(at("E_SCHEMA", &path, "id and trader must be strings"));
        };
        let side = e.get("side").and_then(Json::as_str);
        let typ = e.get("type").and_then(Json::as_str);
        let (Some(side @ ("BUY" | "SELL")), Some(typ)) = (side, typ) else {
            return Err(at("E_SCHEMA", &path, "bad side or type"));
        };
        let Some(typ) = TYPES.iter().copied().find(|t| *t == typ) else {
            return Err(at("E_SCHEMA", &path, "bad side or type"));
        };
        let qty = dec(e.get("qty"), &format!("{path}/qty"))?;
        let has_price = !matches!(e.get("price"), None | Some(Json::Null));
        let limit = if typ == "MARKET" {
            None
        } else {
            Some(dec(e.get("price"), &format!("{path}/price"))?)
        };
        if typ == "MARKET" && has_price {
            return Err(at("E_SCHEMA", &path, "MARKET takes no price"));
        }
        if qty.signum() <= 0 {
            return Err(at("E_DOMAIN", &path, "quantity must be positive"));
        }
        Self::on_grid(qty, self.lot, "qty")?;
        if let Some(l) = limit {
            if l.signum() <= 0 {
                return Err(at("E_DOMAIN", &path, "price must be positive"));
            }
            Self::on_grid(l, self.tick, "price")?;
        }
        let mut slice = qty;
        if typ == "ICEBERG" {
            slice = dec(e.get("display_qty"), &format!("{path}/display_qty"))?;
            if slice.signum() <= 0 || slice > qty {
                return Err(at("E_DOMAIN", &path, "display_qty must be in (0, qty]"));
            }
            Self::on_grid(slice, self.lot, "display_qty")?;
        }
        if !self.seen.insert(oid.to_string()) {
            return Err(at("E_INPUT", &path, &format!("duplicate id {oid}")));
        }
        self.cons.insert(
            oid.to_string(),
            Cons {
                submitted: qty,
                ..Cons::default()
            },
        );
        let buy = side == "BUY";
        let mut o = Order {
            id: oid.to_string(),
            trader: trader.to_string(),
            buy,
            typ,
            cap: limit,
            price: limit,
            display: Dec::ZERO,
            hidden: Dec::ZERO,
            slice,
            seq: 0,
        };
        if typ == "FOK" && self.available(buy, limit)? < qty {
            return self.reject(oid, "FOK_UNFILLABLE", qty);
        }
        if typ == "POST_ONLY"
            && self
                .best(!buy, false, None)
                .is_some_and(|p| marketable(buy, limit, p))
        {
            return self.reject(oid, "POST_ONLY_WOULD_CROSS", qty);
        }
        if o.is_peg() {
            o.price = self.peg_price(&o)?;
            o.seq = self.next_seq();
            if o.is_mid() {
                o.hidden = qty;
            } else {
                o.display = qty;
            }
            self.resting.insert(o.id.clone(), o);
            return Ok(());
        }
        let rest = self.matched(&o, limit, qty)?;
        if rest.is_zero() {
            return Ok(());
        }
        if typ == "MARKET" || typ == "IOC" {
            self.cancelled
                .push(pair(("id", oid.into()), ("qty", s(rest))));
            let c = self.cons.entry(oid.to_string()).or_default();
            c.cancelled = c.cancelled.checked_add(rest)?;
            return Ok(());
        }
        o.display = slice.min(rest);
        o.hidden = rest.checked_sub(o.display)?;
        o.seq = self.next_seq();
        self.resting.insert(o.id.clone(), o);
        Ok(())
    }

    fn cancel(&mut self, e: &Json, k: usize) -> Result<()> {
        let Some(oid) = e.get("id").and_then(Json::as_str) else {
            return Err(at(
                "E_SCHEMA",
                &format!("events/{k}"),
                "id must be a string",
            ));
        };
        let Some(o) = self.resting.remove(oid) else {
            self.rejects
                .push(pair(("id", oid.into()), ("reason", "UNKNOWN_ID".into())));
            return Ok(());
        };
        let open = o.open()?;
        self.cancelled
            .push(pair(("id", oid.into()), ("qty", s(open))));
        let c = self.cons.entry(oid.to_string()).or_default();
        c.cancelled = c.cancelled.checked_add(open)?;
        Ok(())
    }

    fn modify(&mut self, e: &Json, k: usize) -> Result<()> {
        let path = format!("events/{k}");
        let Some(oid) = e.get("id").and_then(Json::as_str) else {
            return Err(at("E_SCHEMA", &path, "id must be a string"));
        };
        let qty = dec(e.get("qty"), &format!("{path}/qty"))?;
        if qty.signum() <= 0 {
            return Err(at("E_DOMAIN", &path, "quantity must be positive"));
        }
        Self::on_grid(qty, self.lot, "qty")?;
        if !matches!(e.get("price"), None | Some(Json::Null)) {
            return Err(at(
                "E_SCHEMA",
                &path,
                "MODIFY takes id and qty only (wave 1b)",
            ));
        }
        let Some(o) = self.resting.get(oid) else {
            self.rejects
                .push(pair(("id", oid.into()), ("reason", "UNKNOWN_ID".into())));
            return Ok(());
        };
        // `qty` is the new open displayed quantity; a PEG_MID's whole quantity is non-displayed.
        let mid = o.is_mid();
        let old = if mid { o.hidden } else { o.display };
        if qty == old {
            return Ok(());
        }
        let seq = if qty > old {
            Some(self.next_seq())
        } else {
            None
        };
        if let Some(o) = self.resting.get_mut(oid) {
            if mid {
                o.hidden = qty;
            } else {
                o.display = qty;
            }
            if let Some(sq) = seq {
                o.seq = sq;
            }
        }
        let c = self.cons.entry(oid.to_string()).or_default();
        if qty < old {
            c.cancelled = c.cancelled.checked_add(old.checked_sub(qty)?)?;
        } else {
            c.submitted = c.submitted.checked_add(qty.checked_sub(old)?)?;
        }
        Ok(())
    }

    fn output(self) -> Result<Json> {
        let entry = |o: &Order| {
            Json::Obj(vec![
                ("display_qty".into(), s(o.display)),
                ("hidden_qty".into(), s(o.hidden)),
                ("id".into(), o.id.clone().into()),
                ("price".into(), o.price.map_or(Json::Null, s)),
                ("seq".into(), Json::Int(o.seq)),
            ])
        };
        let mut book = Vec::new();
        let mut mbp = Vec::new();
        for (name, buy) in [("asks", false), ("bids", true)] {
            let mut priced: Vec<&Order> = self
                .resting
                .values()
                .filter(|o| o.buy == buy && o.price.is_some())
                .collect();
            priced.sort_by(|a, b| {
                let by_price = if buy {
                    b.price.cmp(&a.price)
                } else {
                    a.price.cmp(&b.price)
                };
                by_price.then(a.seq.cmp(&b.seq))
            });
            let mut unpriced: Vec<&Order> = self
                .resting
                .values()
                .filter(|o| o.buy == buy && o.price.is_none())
                .collect();
            unpriced.sort_by_key(|o| o.seq);
            book.push((
                name.to_string(),
                Json::Arr(priced.iter().chain(&unpriced).map(|o| entry(o)).collect()),
            ));
            let mut levels: BTreeMap<Dec, Dec> = BTreeMap::new();
            for o in &priced {
                if let Some(p) = o.price {
                    let l = levels.entry(p).or_default();
                    *l = l.checked_add(o.display)?;
                }
            }
            let mut rows: Vec<Json> = levels
                .into_iter()
                .filter(|(_, q)| q.signum() > 0)
                .map(|(p, q)| Json::Arr(vec![s(p), s(q)]))
                .collect();
            if buy {
                rows.reverse();
            }
            mbp.push((name.to_string(), Json::Arr(rows)));
        }
        let mut cons = Vec::new();
        for (oid, c) in &self.cons {
            let resting = match self.resting.get(oid) {
                Some(o) => o.open()?,
                None => Dec::ZERO,
            };
            cons.push((
                oid.clone(),
                Json::Obj(vec![
                    ("cancelled".into(), s(c.cancelled)),
                    ("filled".into(), s(c.filled)),
                    ("rejected".into(), s(c.rejected)),
                    ("resting".into(), s(resting)),
                    ("submitted".into(), s(c.submitted)),
                ]),
            ));
        }
        let fees = self.fees.iter().map(|(t, v)| (t.clone(), s(*v))).collect();
        // Canonical JSON (HR-29): keys in sorted order.
        Ok(Json::Obj(vec![
            ("book".into(), Json::Obj(book)),
            ("cancelled".into(), Json::Arr(self.cancelled)),
            ("conservation".into(), Json::Obj(cons)),
            ("fees".into(), Json::Obj(fees)),
            ("fills".into(), Json::Arr(self.fills)),
            ("label".into(), LABEL.into()),
            ("mbp".into(), Json::Obj(mbp)),
            ("rejects".into(), Json::Arr(self.rejects)),
        ]))
    }
}

/// Runs the event list. `fee_schedule` is the raw JSON object.
pub fn run(tick_size: &str, lot_size: &str, events: &[Json], fee_schedule: &Json) -> Result<Json> {
    let tick = dec(Some(&Json::Str(tick_size.into())), "tick_size")?;
    let lot = dec(Some(&Json::Str(lot_size.into())), "lot_size")?;
    if tick.signum() <= 0 || lot.signum() <= 0 {
        return Err(at(
            "E_DOMAIN",
            "tick_size",
            "tick_size and lot_size must be positive",
        ));
    }
    let taker_fee = dec(fee_schedule.get("taker_fee"), "fee_schedule/taker_fee")?;
    let maker_rebate = dec(
        fee_schedule.get("maker_rebate"),
        "fee_schedule/maker_rebate",
    )?;
    if events.len() > MAX_EVENTS {
        return Err(at("E_LIMIT", "events", "more than 10,000,000 events"));
    }
    let mut eng = Engine {
        tick,
        lot,
        taker_fee,
        maker_rebate,
        resting: BTreeMap::new(),
        seen: HashSet::new(),
        seq: 0,
        fills: Vec::new(),
        rejects: Vec::new(),
        cancelled: Vec::new(),
        fees: BTreeMap::new(),
        cons: BTreeMap::new(),
    };
    for (k, e) in events.iter().enumerate() {
        match e.get("op").and_then(Json::as_str) {
            Some("NEW") => eng.new_order(e, k)?,
            Some("CANCEL") => eng.cancel(e, k)?,
            Some("MODIFY") => eng.modify(e, k)?,
            _ => return Err(at("E_SCHEMA", &format!("events/{k}"), "not an event")),
        }
        eng.reprice()?;
    }
    eng.output()
}
