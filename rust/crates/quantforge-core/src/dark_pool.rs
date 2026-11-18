//! `exec.sim.dark.run` and `exec.sim.dark.markouts`: a simulated midpoint dark pool.
//!
//! Spec: `specifications/10-execution/dark-pool.md` (rulings HR-32 to HR-36). Simulated venue;
//! not a real dark pool. The reference price is the mid of a lit book supplied per event; prices
//! and quantities are exact decimals (HR-12, HR-57/58), shared with the lit engine.
//!
//! Crossing (HR-32, HR-33): after every event, while a mid exists, scan buys by `seq` and for each
//! buy the sells by `seq`; the first pair within both limits whose fill `min(open_buy, open_sell)`
//! meets both `min_qty` fills at the mid. A pair with a `CONDITIONAL` side first sends an
//! invitation (HR-34): the owner firms up with probability `p_firm` (a `core.rng` draw only when
//! `0 < p_firm < 1`). With `firm_delay` d > 0 both orders are held until event `event + d`, when the
//! firm-up is decided and the pair fills at that event's mid if still eligible. A decline suspends
//! the conditional for events `event + 1` to `event + penalty_events`.
//!
//! Also here: the Kaplan-Meier tail of censored per-venue fills ([GKNV09]) with its Greenwood
//! standard error, used by the planted-recovery tests.
use crate::decimal::Dec;
use crate::error::{QfError, Result, err};
use crate::json::Json;
use crate::order_book::dec;
use crate::rng::Xoshiro;
use crate::sor::Q;
use std::collections::HashMap;

pub const LABEL: &str = "simulated venue; not a real dark pool";
pub const MAX_EVENTS: usize = 10_000_000;

fn at(code: &'static str, path: &str, what: &str) -> QfError {
    let mut e = err(code, format!("{path}: {what}"));
    e.field = Some(path.to_string());
    e
}

struct Order {
    id: String,
    buy: bool,
    open: Dec,
    limit: Option<Dec>,
    min_qty: Dec,
    conditional: bool,
    seq: i64,
    suspended_to: i64,
    held_to: i64,
}

fn on_grid(x: Dec, step: Dec, path: &str) -> Result<()> {
    if x.on_grid(step)? {
        Ok(())
    } else {
        Err(at("E_DOMAIN", path, &format!("not on the grid {step}")))
    }
}

fn non_neg(v: Option<&Json>, default: i64, path: &str) -> Result<i64> {
    match v {
        None | Some(Json::Null) => Ok(default),
        Some(Json::Int(n)) if *n >= 0 => Ok(*n),
        Some(_) => Err(at("E_DOMAIN", path, "not a non-negative integer")),
    }
}

fn opt_dec(v: Option<&Json>, path: &str) -> Result<Option<Dec>> {
    match v {
        None | Some(Json::Null) => Ok(None),
        Some(x) => dec(Some(x), path).map(Some),
    }
}

fn s(d: Dec) -> Json {
    d.to_string().into()
}

fn ob(pairs: Vec<(&str, Json)>) -> Json {
    Json::Obj(pairs.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
}

struct Pool {
    tick: Dec,
    lot: Dec,
    p_firm: Dec,
    delay: i64,
    penalty: i64,
    rng: Xoshiro,
    mid: Option<Dec>,
    orders: Vec<Order>,
    index: HashMap<String, usize>,
    fills: Vec<Json>,
    invitations: Vec<Json>,
    suspensions: Vec<Json>,
    pending: Vec<(i64, usize, usize)>,
}

impl Pool {
    fn new(cfg: &Json) -> Result<Pool> {
        let tick = dec(cfg.get("tick_size"), "config/tick_size")?;
        let lot = dec(cfg.get("lot_size"), "config/lot_size")?;
        if tick.signum() <= 0 || lot.signum() <= 0 {
            return Err(at(
                "E_DOMAIN",
                "config/tick_size",
                "tick_size and lot_size must be positive",
            ));
        }
        let p_firm = match cfg.get("p_firm") {
            None | Some(Json::Null) => Dec::parse("0.8").expect("literal")?,
            v => dec(v, "config/p_firm")?,
        };
        if p_firm.signum() < 0 || p_firm > Dec::int(1) {
            return Err(at("E_DOMAIN", "config/p_firm", "p_firm outside [0, 1]"));
        }
        let delay = non_neg(cfg.get("firm_delay"), 0, "config/firm_delay")?;
        let penalty = non_neg(cfg.get("penalty_events"), 0, "config/penalty_events")?;
        let seed = non_neg(cfg.get("seed"), 0, "config/seed")?;
        Ok(Pool {
            tick,
            lot,
            p_firm,
            delay,
            penalty,
            rng: Xoshiro::seeded(seed as u64, 0),
            mid: None,
            orders: Vec::new(),
            index: HashMap::new(),
            fills: Vec::new(),
            invitations: Vec::new(),
            suspensions: Vec::new(),
            pending: Vec::new(),
        })
    }

    fn book(&mut self, e: &Json, k: usize) -> Result<()> {
        let bid = opt_dec(e.get("bid"), &format!("events/{k}/bid"))?;
        let ask = opt_dec(e.get("ask"), &format!("events/{k}/ask"))?;
        for (v, name) in [(bid, "bid"), (ask, "ask")] {
            if let Some(v) = v {
                on_grid(v, self.tick, &format!("events/{k}/{name}"))?;
            }
        }
        self.mid = match (bid, ask) {
            (Some(b), Some(a)) if b < a => Some(
                b.checked_add(a)?
                    .checked_mul(Dec::parse("0.5").expect("literal")?)?,
            ),
            _ => None,
        };
        Ok(())
    }

    fn new_order(&mut self, e: &Json, k: usize) -> Result<()> {
        let Some(oid) = e.get("id").and_then(Json::as_str) else {
            return Err(at(
                "E_SCHEMA",
                "events",
                &format!("events/{k}/id: not a string"),
            ));
        };
        if self.index.contains_key(oid) {
            return Err(at(
                "E_INPUT",
                "events",
                &format!("events/{k}: duplicate id {oid}"),
            ));
        }
        let side = e.get("side").and_then(Json::as_str);
        let kind = e.get("kind").and_then(Json::as_str);
        if !matches!(side, Some("BUY" | "SELL")) || !matches!(kind, Some("FIRM" | "CONDITIONAL")) {
            return Err(at(
                "E_SCHEMA",
                "events",
                &format!("events/{k}: side or kind"),
            ));
        }
        let qty = dec(e.get("qty"), &format!("events/{k}/qty"))?;
        let mq = match e.get("min_qty") {
            None | Some(Json::Null) => self.lot,
            v => dec(v, &format!("events/{k}/min_qty"))?,
        };
        if qty.signum() <= 0 || mq.signum() <= 0 || mq > qty {
            return Err(at(
                "E_DOMAIN",
                "events",
                &format!("events/{k}: qty must be positive and min_qty <= qty"),
            ));
        }
        on_grid(qty, self.lot, &format!("events/{k}/qty"))?;
        let limit = opt_dec(e.get("limit"), &format!("events/{k}/limit"))?;
        let seq = self.orders.len() as i64 + 1;
        self.index.insert(oid.to_string(), self.orders.len());
        self.orders.push(Order {
            id: oid.to_string(),
            buy: side == Some("BUY"),
            open: qty,
            limit,
            min_qty: mq,
            conditional: kind == Some("CONDITIONAL"),
            seq,
            suspended_to: 0,
            held_to: 0,
        });
        Ok(())
    }

    fn cancel(&mut self, e: &Json, k: usize) -> Result<()> {
        let idx = e
            .get("id")
            .and_then(Json::as_str)
            .and_then(|id| self.index.get(id).copied());
        match idx {
            Some(i) => {
                self.orders[i].open = Dec::ZERO;
                Ok(())
            }
            None => Err(at("E_INPUT", "events", &format!("events/{k}: unknown id"))),
        }
    }

    fn eligible(&self, i: usize, n: i64) -> bool {
        let o = &self.orders[i];
        let Some(mid) = self.mid else { return false };
        if o.open.signum() <= 0 || n <= o.suspended_to || n < o.held_to {
            return false;
        }
        o.limit
            .is_none_or(|l| if o.buy { l >= mid } else { l <= mid })
    }

    fn pair_ok(&self, b: usize, s: usize) -> bool {
        let (b, s) = (&self.orders[b], &self.orders[s]);
        let q = b.open.min(s.open);
        q >= b.min_qty && q >= s.min_qty
    }

    fn firm(&mut self) -> bool {
        if self.p_firm == Dec::int(1) {
            return true;
        }
        if self.p_firm.is_zero() {
            return false;
        }
        let u = self.rng.next_uniform();
        // The Python build compares Decimal(repr(u)): the shortest round-trip text of u.
        match Dec::parse(&u.to_string()) {
            Some(Ok(d)) => d < self.p_firm,
            _ => u < self.p_firm.to_string().parse::<f64>().unwrap_or(0.0),
        }
    }

    fn fill(&mut self, b: usize, s: usize) -> Result<()> {
        let mid = self
            .mid
            .ok_or_else(|| err("E_INTERNAL", "fill without a mid"))?;
        let q = self.orders[b].open.min(self.orders[s].open);
        self.orders[b].open = self.orders[b].open.checked_sub(q)?;
        self.orders[s].open = self.orders[s].open.checked_sub(q)?;
        let seq = self.fills.len() as i64 + 1;
        self.fills.push(ob(vec![
            ("buy_id", self.orders[b].id.clone().into()),
            ("price", s_(mid)),
            ("qty", s_(q)),
            ("sell_id", self.orders[s].id.clone().into()),
            ("seq", Json::Int(seq)),
        ]));
        Ok(())
    }

    /// Invitations for the conditional side(s); true when every one firms up.
    fn invite(&mut self, b: usize, s: usize, n: i64) -> bool {
        let mut ok = true;
        for (o, c) in [(b, s), (s, b)] {
            if !self.orders[o].conditional {
                continue;
            }
            let firmed = self.firm();
            self.invitations.push(ob(vec![
                ("contra_id", self.orders[c].id.clone().into()),
                ("event", Json::Int(n)),
                ("id", self.orders[o].id.clone().into()),
                ("result", if firmed { "FIRMED" } else { "DECLINED" }.into()),
            ]));
            if !firmed {
                ok = false;
                self.orders[o].suspended_to = n + self.penalty;
                if self.penalty > 0 {
                    self.suspensions.push(ob(vec![
                        ("from_event", Json::Int(n + 1)),
                        ("id", self.orders[o].id.clone().into()),
                        ("to_event", Json::Int(n + self.penalty)),
                    ]));
                }
            }
        }
        ok
    }

    fn settle(&mut self, n: i64) -> Result<()> {
        let (due, rest): (Vec<_>, Vec<_>) = self.pending.iter().partition(|p| p.0 == n);
        self.pending = rest;
        for (_, b, s) in due {
            self.orders[b].held_to = 0;
            self.orders[s].held_to = 0;
            if self.invite(b, s, n)
                && self.eligible(b, n)
                && self.eligible(s, n)
                && self.pair_ok(b, s)
            {
                self.fill(b, s)?;
            }
        }
        Ok(())
    }

    fn cross(&mut self, n: i64) -> Result<()> {
        while self.mid.is_some() {
            // Orders are stored in `seq` order.
            let live: Vec<usize> = (0..self.orders.len())
                .filter(|&i| self.eligible(i, n))
                .collect();
            let pair = live.iter().filter(|&&b| self.orders[b].buy).find_map(|&b| {
                live.iter()
                    .find(|&&s| !self.orders[s].buy && self.pair_ok(b, s))
                    .map(|&s| (b, s))
            });
            let Some((b, s)) = pair else { return Ok(()) };
            if !(self.orders[b].conditional || self.orders[s].conditional) {
                self.fill(b, s)?;
            } else if self.delay > 0 {
                self.orders[b].held_to = n + self.delay;
                self.orders[s].held_to = n + self.delay;
                self.pending.push((n + self.delay, b, s));
            } else if self.invite(b, s, n) {
                self.fill(b, s)?;
            }
        }
        Ok(())
    }

    fn output(self) -> Json {
        let resting = self
            .orders
            .iter()
            .filter(|o| o.open.signum() > 0)
            .map(|o| {
                ob(vec![
                    ("id", o.id.clone().into()),
                    ("open_qty", s(o.open)),
                    ("seq", Json::Int(o.seq)),
                    ("side", if o.buy { "BUY" } else { "SELL" }.into()),
                ])
            })
            .collect();
        ob(vec![
            ("fills", Json::Arr(self.fills)),
            ("invitations", Json::Arr(self.invitations)),
            ("label", LABEL.into()),
            ("resting", Json::Arr(resting)),
            ("suspensions", Json::Arr(self.suspensions)),
        ])
    }
}

fn s_(d: Dec) -> Json {
    s(d)
}

/// One pool run over `events` (BOOK, NEW, CANCEL), numbered from 1. `config` is an object.
/// HR-93, HR-113: `asset_class` (default EQUITY; `null` counts as absent); a dark venue of another
/// class is an invalid input combination, `E_INPUT` (structural cross-field check, HR-66).
pub fn asset_class(v: Option<&Json>, path: &str, dark: bool) -> Result<&'static str> {
    let c = match v {
        None | Some(Json::Null) => "EQUITY",
        Some(x) => match x.as_str() {
            Some("EQUITY") => "EQUITY",
            Some("FX") => "FX",
            Some("RATES") => "RATES",
            _ => return Err(at("E_SCHEMA", path, "not EQUITY, FX or RATES")),
        },
    };
    if dark && c != "EQUITY" {
        return Err(at(
            "E_INPUT",
            path,
            "dark pool is equities only (HR-93, HR-113)",
        ));
    }
    Ok(c)
}

pub fn run(config: &Json, events: &[Json]) -> Result<Json> {
    asset_class(config.get("asset_class"), "config/asset_class", true)?;
    if events.len() > MAX_EVENTS {
        return Err(at("E_LIMIT", "events", "more than 10,000,000 events"));
    }
    let mut pool = Pool::new(config)?;
    for (k, e) in events.iter().enumerate() {
        let n = k as i64 + 1;
        match e.get("op").and_then(Json::as_str) {
            Some("BOOK") => pool.book(e, k)?,
            Some("NEW") => pool.new_order(e, k)?,
            Some("CANCEL") => pool.cancel(e, k)?,
            _ => {
                return Err(at(
                    "E_SCHEMA",
                    "events",
                    &format!("events/{k}: not an event"),
                ));
            }
        }
        pool.settle(n)?;
        pool.cross(n)?;
    }
    Ok(pool.output())
}

/// Markout in bp per horizon: `side_sign * (mid - fill_price) / fill_price * 10000`, exact, rounded
/// half-even to 6 decimals (positive is good for the order's owner).
pub fn markouts(fills: &[Json]) -> Result<Json> {
    let mut out = Vec::with_capacity(fills.len());
    for (k, f) in fills.iter().enumerate() {
        let side = f.get("side").and_then(Json::as_str);
        if !matches!(f, Json::Obj(_)) || !matches!(side, Some("BUY" | "SELL")) {
            return Err(at("E_SCHEMA", "fills", &format!("fills/{k}: side")));
        }
        let px = dec(f.get("fill_price"), &format!("fills/{k}/fill_price"))?;
        if px.signum() <= 0 {
            return Err(at(
                "E_DOMAIN",
                "fills",
                &format!("fills/{k}/fill_price: not positive"),
            ));
        }
        let Some(Json::Obj(mids)) = f.get("mid_at") else {
            return Err(at(
                "E_SCHEMA",
                "fills",
                &format!("fills/{k}/mid_at: not an object"),
            ));
        };
        let mut bp = Vec::with_capacity(mids.len());
        for (h, m) in mids {
            let m = dec(Some(m), &format!("fills/{k}/mid_at/{h}"))?;
            let mut diff = m.checked_sub(px)?;
            if side == Some("SELL") {
                diff = Dec::ZERO.checked_sub(diff)?;
            }
            let v = Q::from_dec(diff)?
                .times(Q::int(10_000))?
                .over(Q::from_dec(px)?)?;
            bp.push((h.clone(), Json::Str(v.round6()?)));
        }
        out.push(ob(vec![
            ("label", LABEL.into()),
            ("markouts_bp", Json::Obj(bp)),
        ]));
    }
    Ok(ob(vec![("fills", Json::Arr(out))]))
}

/// Kaplan-Meier tail `T(s) = P(liquidity >= s)`, `s = 1..s_max`, from (v, r) observations ([GKNV09]
/// section 2: r < v observes s = r; r = v is censored, s >= v). Returns (estimate, Greenwood
/// standard error) per s; plain KM, no optimistic modification.
pub fn km_tail(obs: &[(i64, i64)], s_max: i64) -> Vec<(f64, f64)> {
    let (mut t, mut gw) = (1.0f64, 0.0f64);
    let mut out = Vec::new();
    for s in 1..=s_max {
        let j = s - 1;
        let at_risk = obs
            .iter()
            .filter(|&&(v, r)| (r < v && r >= j) || (r == v && v > j))
            .count() as f64;
        let d = obs.iter().filter(|&&(v, r)| r < v && r == j).count() as f64;
        if at_risk > 0.0 && d > 0.0 {
            t *= 1.0 - d / at_risk;
            if at_risk > d {
                gw += d / (at_risk * (at_risk - d));
            }
        }
        out.push((t, t * gw.sqrt()));
    }
    out
}
