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
pub fn run(
    tick_size: &str,
    lot_size: &str,
    events: &[Json],
    fee_schedule: &Json,
    session: Option<&Json>,
) -> Result<Json> {
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
    let mut ses = match session {
        Some(raw) => {
            let fee = match fee_schedule.get("auction_fee") {
                None => Dec::ZERO,
                v => dec(v, "fee_schedule/auction_fee")?,
            };
            Some(Session::new(raw, fee)?)
        }
        None => None,
    };
    for (k, e) in events.iter().enumerate() {
        let op = e.get("op").and_then(Json::as_str);
        let known = matches!(op, Some("NEW" | "CANCEL" | "MODIFY"))
            || (ses.is_some() && op == Some("PHASE"));
        if !matches!(e, Json::Obj(_)) || !known {
            return Err(at("E_SCHEMA", &format!("events/{k}"), "not an event"));
        }
        if let Some(sx) = ses.as_mut()
            && sx.event(&mut eng, e, k)?
        {
            continue;
        }
        match op {
            Some("NEW") => eng.new_order(e, k)?,
            Some("CANCEL") => eng.cancel(e, k)?,
            _ => eng.modify(e, k)?,
        }
        eng.reprice()?;
    }
    let out = eng.output()?;
    let Some(sx) = ses else {
        return Ok(out);
    };
    let Json::Obj(mut fields) = out else {
        return Err(err("E_INPUT", "engine output is not an object"));
    };
    for (key, v) in &mut fields {
        if key == "conservation"
            && let Json::Obj(cons) = v
        {
            // Still in a call book at the end: counted as resting.
            for c in &sx.call {
                if let Some((_, Json::Obj(row))) = cons.iter_mut().find(|(id, _)| *id == c.id) {
                    for (rk, rv) in row.iter_mut() {
                        if rk == "resting" {
                            *rv = s(c.qty_dec);
                        }
                    }
                }
            }
        }
    }
    fields.push(("auctions".into(), Json::Arr(sx.auctions)));
    fields.push(("phase".into(), sx.phase.into()));
    fields.sort_by(|a, b| a.0.cmp(&b.0));
    Ok(Json::Obj(fields))
}

const PHASES: [&str; 4] = ["PRE_OPEN", "CONTINUOUS", "PRE_CLOSE", "CLOSED"]; // HR-83

struct CallOrder {
    id: String,
    side: String,
    limit: Json,
    qty: i64,
    qty_dec: Dec,
    on_close: bool,
}

/// Equity session phases (asset-conventions.md 1.3, HR-83; auction.md), as the Python reference:
/// in `PRE_OPEN`, NEW LIMIT and MARKET orders collect in a call book without matching; at `CONTINUOUS`
/// the call book is uncrossed by `exec.sim.auction.uncross` (phase OPEN) and its unfilled limit
/// orders rest in allocation order. In `PRE_CLOSE` only `on_close` orders are accepted, into a
/// second call book uncrossed at `CLOSED` (phase CLOSE); unfilled on-close orders are cancelled
/// (HR-96). The continuous book does not join the closing cross. Orders in the wrong phase are
/// rejected with reason `PHASE`. Auction fills pay `auction_fee` x notional.
struct Session {
    fee: Dec,
    phase: &'static str,
    ref_price: Dec,
    tie: Json,
    call: Vec<CallOrder>,
    trader: BTreeMap<String, String>,
    auctions: Vec<Json>,
}

impl Session {
    fn new(raw: &Json, fee: Dec) -> Result<Session> {
        if !matches!(raw, Json::Obj(_)) {
            return Err(at("E_SCHEMA", "session", "not an object"));
        }
        let phase = match raw.get("phase") {
            None => "PRE_OPEN",
            Some(v) => PHASES
                .iter()
                .copied()
                .find(|p| v.as_str() == Some(p))
                .ok_or_else(|| at("E_SCHEMA", "session/phase", "not a phase"))?,
        };
        let ref_price = dec(raw.get("ref_price"), "session/ref_price")?;
        let tie = raw
            .get("tie_break")
            .cloned()
            .unwrap_or_else(|| "CBOE".into());
        Ok(Session {
            fee,
            phase,
            ref_price,
            tie,
            call: Vec::new(),
            trader: BTreeMap::new(),
            auctions: Vec::new(),
        })
    }

    /// True when the session handled the event (the engine must not).
    fn event(&mut self, eng: &mut Engine, e: &Json, k: usize) -> Result<bool> {
        let op = e.get("op").and_then(Json::as_str);
        if op == Some("PHASE") {
            self.advance(eng, e.get("phase"), k)?;
            return Ok(true);
        }
        if self.phase == "CONTINUOUS" {
            return Ok(false);
        }
        if op == Some("CANCEL") {
            let id = e.get("id").and_then(Json::as_str);
            if let Some(i) = self.call.iter().position(|c| id == Some(c.id.as_str())) {
                let c = self.call.remove(i);
                eng.cancelled
                    .push(pair(("id", c.id.clone().into()), ("qty", s(c.qty_dec))));
                eng.cons.entry(c.id).or_default().cancelled = c.qty_dec;
                return Ok(true);
            }
            return Ok(false);
        }
        if op != Some("NEW") {
            return Ok(false);
        }
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
        if !TYPES.contains(&typ) {
            return Err(at("E_SCHEMA", &path, "bad side or type"));
        }
        let on_close = match e.get("on_close") {
            None => false,
            Some(Json::Bool(b)) => *b,
            Some(_) => return Err(at("E_SCHEMA", &path, "on_close: not a boolean")),
        };
        let qty = dec(e.get("qty"), &format!("{path}/qty"))?;
        let market = typ == "MARKET";
        let limit = if market {
            None
        } else {
            Some(dec(e.get("price"), &format!("{path}/price"))?)
        };
        if eng.seen.contains(oid) {
            return Err(at("E_INPUT", &path, &format!("duplicate id {oid}")));
        }
        if qty.signum() <= 0 {
            return Err(at("E_DOMAIN", &path, "quantity must be positive"));
        }
        Engine::on_grid(qty, eng.lot, "qty")?;
        if let Some(l) = limit {
            if l.signum() <= 0 {
                return Err(at("E_DOMAIN", &path, "price must be positive"));
            }
            Engine::on_grid(l, eng.tick, "price")?;
        }
        eng.seen.insert(oid.to_string());
        eng.cons.insert(
            oid.to_string(),
            Cons {
                submitted: qty,
                ..Cons::default()
            },
        );
        let ok = matches!(typ, "LIMIT" | "MARKET")
            && (self.phase == "PRE_OPEN" || (self.phase == "PRE_CLOSE" && on_close));
        if !ok {
            eng.reject(oid, "PHASE", qty)?;
            return Ok(true);
        }
        self.trader.insert(oid.to_string(), trader.to_string());
        let lots = qty
            .div_int(eng.lot, false)?
            .to_string()
            .parse::<i64>()
            .map_err(|_| at("E_LIMIT", &path, "too many lots"))?;
        self.call.push(CallOrder {
            id: oid.to_string(),
            side: side.to_string(),
            limit: if market {
                "MARKET".into()
            } else {
                e.get("price").cloned().unwrap_or(Json::Null)
            },
            qty: lots,
            qty_dec: qty,
            on_close: self.phase == "PRE_CLOSE",
        });
        Ok(true)
    }

    fn advance(&mut self, eng: &mut Engine, to: Option<&Json>, k: usize) -> Result<()> {
        let path = format!("events/{k}");
        let want = to.and_then(Json::as_str);
        let Some(to) = PHASES.iter().position(|p| want == Some(p)) else {
            return Err(at("E_SCHEMA", &path, "phase: not a phase"));
        };
        let from = PHASES.iter().position(|p| *p == self.phase).unwrap_or(0);
        if to != from + 1 {
            return Err(at(
                "E_INPUT",
                &path,
                &format!("phase {} cannot move to {}", self.phase, PHASES[to]),
            ));
        }
        match PHASES[to] {
            "CONTINUOUS" => self.uncross(eng, "OPEN")?,
            "CLOSED" => self.uncross(eng, "CLOSE")?,
            _ => {}
        }
        self.phase = PHASES[to];
        Ok(())
    }

    fn uncross(&mut self, eng: &mut Engine, phase: &str) -> Result<()> {
        let lot = eng.lot;
        let orders: Vec<Json> = self
            .call
            .iter()
            .enumerate()
            .map(|(n, c)| {
                Json::Obj(vec![
                    ("id".into(), c.id.clone().into()),
                    ("side".into(), c.side.clone().into()),
                    ("limit".into(), c.limit.clone()),
                    ("qty".into(), Json::Int(c.qty)),
                    ("seq".into(), Json::Int(n as i64 + 1)),
                    ("on_close".into(), Json::Bool(c.on_close)),
                ])
            })
            .collect();
        let req = Json::Obj(vec![
            ("orders".into(), Json::Arr(orders)),
            ("phase".into(), phase.into()),
            ("ref_price".into(), s(self.ref_price)),
            ("tick_size".into(), s(eng.tick)),
            ("tie_break".into(), self.tie.clone()),
        ]);
        let res = crate::multiasset::auction_uncross(&req)?;
        let lots =
            |v: Option<&Json>| Dec::int(v.and_then(Json::as_int).unwrap_or(0)).checked_mul(lot);
        let list = |k: &str| res.get(k).and_then(Json::as_array).unwrap_or(&[]).to_vec();
        let text = |v: &Json, k: &str| {
            v.get(k)
                .and_then(Json::as_str)
                .unwrap_or_default()
                .to_string()
        };
        let mut fills = Vec::new();
        for f in list("fills") {
            let id = text(&f, "id");
            let q = lots(f.get("qty"))?;
            let price = dec(f.get("price"), "price")?;
            fills.push(Json::Obj(vec![
                ("id".into(), id.clone().into()),
                ("price".into(), s(price)),
                ("qty".into(), s(q)),
                ("side".into(), f.get("side").cloned().unwrap_or(Json::Null)),
            ]));
            let c = eng.cons.entry(id.clone()).or_default();
            c.filled = c.filled.checked_add(q)?;
            let t = self.trader.get(&id).cloned().unwrap_or_default();
            let add = self.fee.checked_mul(price.checked_mul(q)?)?;
            let fe = eng.fees.entry(t).or_default();
            *fe = fe.checked_add(add)?;
        }
        for r in list("residual") {
            let id = text(&r, "id");
            let q = lots(r.get("qty"))?;
            let limit = dec(r.get("limit"), "limit")?;
            let seq = eng.next_seq();
            let o = Order {
                id: id.clone(),
                trader: self.trader.get(&id).cloned().unwrap_or_default(),
                buy: r.get("side").and_then(Json::as_str) == Some("B"),
                typ: "LIMIT",
                cap: Some(limit),
                price: Some(limit),
                display: q,
                hidden: Dec::ZERO,
                slice: q,
                seq,
            };
            eng.resting.insert(id, o);
        }
        for oid in list("cancelled") {
            let oid = oid.as_str().unwrap_or_default().to_string();
            let qd = self
                .call
                .iter()
                .find(|c| c.id == oid)
                .map_or(Dec::ZERO, |c| c.qty_dec);
            let c = eng.cons.entry(oid.clone()).or_default();
            let left = qd.checked_sub(c.filled)?;
            c.cancelled = left;
            eng.cancelled
                .push(pair(("id", oid.into()), ("qty", s(left))));
        }
        let price = match res.get("price") {
            Some(p @ Json::Str(_)) => s(dec(Some(p), "price")?),
            _ => Json::Null,
        };
        self.auctions.push(Json::Obj(vec![
            ("fills".into(), Json::Arr(fills)),
            ("imbalance".into(), s(lots(res.get("imbalance"))?)),
            ("phase".into(), phase.into()),
            ("price".into(), price),
            ("volume".into(), s(lots(res.get("volume"))?)),
        ]));
        self.call.clear();
        Ok(())
    }
}
