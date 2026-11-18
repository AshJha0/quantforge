//! Multi-asset microstructure: equities (H-22), FX spot (H-23) and rates (H-24).
//!
//! Specs: `specifications/09-microstructure/asset-conventions.md`, `specifications/10-execution/auction.md`,
//! `fx-rfq-venue.md` and `rates-futures-venue.md` (rulings HR-80 to HR-108 in
//! `specifications/stage-h-rulings-multiasset.md`, with the dated rule versions of 2026-11-18). A port
//! of `python/quantforge_core/multiasset.py`, which is the reference: every check runs in the same
//! order (HR-66: `E_SCHEMA`, then structural `E_INPUT`, then `E_DOMAIN`, then `E_LIMIT`).
//! Prices, quantities, fees and rates are exact decimals (HR-12, HR-57, HR-58); the two prices that
//! need a division that does not terminate (coupon bond, bill) are computed as exact fractions of
//! big integers and rounded once, as the 200-digit reference context does to far below the 9
//! decimals printed. Every output carries its label (HR-94). The futures venue reuses the lit
//! engine unchanged (`lit_matching::run`).
use crate::dates::Date;
use crate::decimal::Dec;
use crate::error::{QfError, Result, err};
use crate::json::Json;
use crate::lit_matching;
use crate::order_book::dec as input_dec;
use std::cmp::Ordering;
use std::collections::{BTreeMap, HashMap, HashSet};

pub const EQ_LABEL: &str = "simulated venue; not a real exchange";
pub const IEX_LABEL: &str = "IEX only; one venue";
pub const FX_LABEL: &str = "simulated venue; not a real exchange; no real FX data";
pub const RATES_LABEL: &str = "simulated venue; not a real exchange; no real rates data";

const DEFAULT_TICK_TABLE: [(&str, &str); 2] = [("0", "0.0001"), ("1.00", "0.01")]; // [REGNMS-612]
const HALF_PENNY_TABLE: [(&str, &str); 2] = [("0", "0.0001"), ("1.00", "0.005")];
/// The current Rule 612/610 text applies on and after this date (a parameter; default UNVERIFIED).
pub const RULE_2024_COMPLIANCE: &str = "2025-11-03"; // HR-110, release 34-101070
const FEE_CAP_CURRENT: (&str, &str) = ("0.001", "0.001"); // [REGNMS-610]
const FEE_CAP_OLD: (&str, &str) = ("0.003", "0.003");
const ROUND_LOTS_CURRENT: [(&str, i64); 3] = [("250", 100), ("1000", 40), ("10000", 10)];
const CCY_ORDER: [&str; 8] = ["EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY"]; // HR-88
const T1_PAIRS: [&str; 1] = ["USDCAD"]; // HR-89
const RESOLUTIONS: [i64; 3] = [32, 64, 128];
const MAX_CANDIDATES: i128 = 1_000_000;
const MAX_ORDERS: usize = 10_000_000;
const MAX_DAYS: usize = 3660;

// ------------------------------------------------------------------ parsing helpers

fn at(code: &'static str, path: &str, what: &str) -> QfError {
    let mut e = err(code, format!("{path}: {what}"));
    e.field = Some(path.to_string());
    e
}

fn d(t: &str) -> Dec {
    Dec::parse(t)
        .and_then(Result::ok)
        .expect("constant decimal")
}

fn dint(n: i128) -> Result<Dec> {
    Dec::parse(&n.to_string()).unwrap_or(Ok(Dec::ZERO))
}

/// The integer value of an integral decimal (callers pass integers below 10^36).
fn int_of(x: Dec) -> i128 {
    let (m, s) = x.parts();
    m / 10i128.pow(s)
}

fn is_obj(v: &Json) -> bool {
    matches!(v, Json::Obj(_))
}

fn need<'a>(raw: &'a Json, key: &str, path: &str) -> Result<&'a Json> {
    raw.get(key)
        .ok_or_else(|| at("E_SCHEMA", &format!("{path}{key}"), "missing"))
}

fn obj_at<'a>(v: &'a Json, path: &str) -> Result<&'a Json> {
    if is_obj(v) {
        Ok(v)
    } else {
        Err(at("E_SCHEMA", path, "not an object"))
    }
}

fn dec_of(raw: &Json, key: &str, default: Option<&str>, path: &str) -> Result<Dec> {
    let p = format!("{path}{key}");
    match (raw.get(key), default) {
        (Some(v), _) => input_dec(Some(v), &p),
        (None, Some(t)) => input_dec(Some(&Json::Str(t.into())), &p),
        (None, None) => Err(at("E_SCHEMA", &p, "missing")),
    }
}

/// HR-116: integer inputs within +-(2^53 - 1); outside is `E_LIMIT` in all four languages.
const INT_MAX: i64 = (1 << 53) - 1;

fn int_of_key(raw: &Json, key: &str, default: Option<i64>, path: &str) -> Result<i64> {
    let p = format!("{path}{key}");
    match (raw.get(key), default) {
        (Some(Json::Int(n)), _) if n.unsigned_abs() > INT_MAX.unsigned_abs() => {
            Err(at("E_LIMIT", &p, "integer outside +-(2^53 - 1)"))
        }
        (Some(Json::Int(n)), _) => Ok(*n),
        // The reader keeps integers above 2^53 as numbers (json.rs); an integral one is out of range.
        (Some(Json::Num(v)), _) if v.is_finite() && v.fract() == 0.0 && v.abs() > INT_MAX as f64 => {
            Err(at("E_LIMIT", &p, "integer outside +-(2^53 - 1)"))
        }
        (Some(_), _) => Err(at("E_SCHEMA", &p, "not an integer")),
        (None, Some(n)) => Ok(n),
        (None, None) => Err(at("E_SCHEMA", &p, "missing")),
    }
}

fn bool_of(raw: &Json, key: &str, default: bool) -> Result<bool> {
    match raw.get(key) {
        None => Ok(default),
        Some(Json::Bool(b)) => Ok(*b),
        Some(_) => Err(at("E_SCHEMA", key, "not a boolean")),
    }
}

fn str_of<'a>(raw: &'a Json, key: &str, path: &str) -> Result<&'a str> {
    need(raw, key, path)?
        .as_str()
        .ok_or_else(|| at("E_SCHEMA", &format!("{path}{key}"), "not a string"))
}

fn enum_of<'a>(raw: &'a Json, key: &str, allowed: &[&str], path: &str) -> Result<&'a str> {
    let v = str_of(raw, key, path)?;
    if allowed.contains(&v) {
        Ok(v)
    } else {
        Err(at(
            "E_SCHEMA",
            &format!("{path}{key}"),
            "not an allowed value",
        ))
    }
}

fn date_of(v: &Json, path: &str) -> Result<Date> {
    v.as_str()
        .and_then(Date::parse)
        .ok_or_else(|| at("E_SCHEMA", path, "not an ISO date"))
}

fn dates_of(v: &Json, path: &str) -> Result<HashSet<Date>> {
    let Some(list) = v.as_array() else {
        return Err(at("E_SCHEMA", path, "not an array"));
    };
    list.iter()
        .enumerate()
        .map(|(k, x)| date_of(x, &format!("{path}/{k}")))
        .collect()
}

fn list_of<'a>(raw: &'a Json, key: &str) -> Result<&'a [Json]> {
    need(raw, key, "")?
        .as_array()
        .ok_or_else(|| at("E_SCHEMA", key, "not an array"))
}

fn places(step: Dec) -> u32 {
    step.parts().1
}

/// `x` printed with exactly `places` decimals, rounding half to even if it has more (HR-100).
fn fixed_at(x: Dec, places: u32) -> String {
    if let Some(t) = x.fixed(places) {
        return t;
    }
    let (m, s) = x.parts();
    let unit = 10i128.pow(s - places);
    let (mut q, r) = (m.div_euclid(unit), m.rem_euclid(unit));
    if 2 * r > unit || (2 * r == unit && q % 2 != 0) {
        q += 1;
    }
    let mut t = q.unsigned_abs().to_string();
    let p = places as usize;
    if t.len() <= p {
        t = format!("{}{t}", "0".repeat(p + 1 - t.len()));
    }
    if p > 0 {
        t.insert(t.len() - p, '.');
    }
    if q < 0 { format!("-{t}") } else { t }
}

fn s(x: Dec) -> Json {
    Json::Str(x.to_string())
}

fn out(pairs: Vec<(&str, Json)>) -> Json {
    Json::Obj(pairs.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
}

// ------------------------------------------------------------------ equities (H-22)

/// True when the current (2024-amended) Rule 612/610 text applies at `as_of`.
fn current(raw: &Json) -> Result<bool> {
    let cd = match raw.get("compliance_date") {
        Some(v) => date_of(v, "compliance_date")?,
        None => Date::parse(RULE_2024_COMPLIANCE).expect("constant date"),
    };
    match raw.get("as_of") {
        None => Ok(true),
        Some(v) => Ok(date_of(v, "as_of")? >= cd),
    }
}

fn tick_table(raw: &Json) -> Result<Vec<(Dec, Dec)>> {
    let tier = match raw.get("tick_tier") {
        None => "PENNY",
        Some(v) => match v.as_str() {
            Some(t @ ("PENNY" | "HALF_PENNY")) => t,
            _ => return Err(at("E_SCHEMA", "tick_tier", "not PENNY or HALF_PENNY")),
        },
    };
    let cur = current(raw)?;
    let half = tier == "HALF_PENNY";
    if half && !cur {
        return Err(at(
            "E_INPUT",
            "tick_tier",
            "HALF_PENNY before the compliance date",
        ));
    }
    if half && raw.get("tick_table").is_some() {
        return Err(at(
            "E_INPUT",
            "tick_tier",
            "HALF_PENNY with an explicit tick_table",
        ));
    }
    let rows = if let Some(v) = raw.get("tick_table") {
        let Some(list) = v.as_array() else {
            return Err(at("E_SCHEMA", "tick_table", "not an array"));
        };
        let mut rows = Vec::with_capacity(list.len());
        for (k, r) in list.iter().enumerate() {
            let Some(pair) = r.as_array().filter(|a| a.len() == 2) else {
                return Err(at("E_SCHEMA", "tick_table", "not a [floor, tick] pair"));
            };
            rows.push((
                input_dec(pair.first(), &format!("tick_table/{k}/0"))?,
                input_dec(pair.get(1), &format!("tick_table/{k}/1"))?,
            ));
        }
        rows
    } else {
        let t = if half {
            HALF_PENNY_TABLE
        } else {
            DEFAULT_TICK_TABLE
        };
        t.iter().map(|(a, b)| (d(a), d(b))).collect()
    };
    if rows.first().is_none_or(|r| !r.0.is_zero()) || rows.windows(2).any(|w| w[0].0 >= w[1].0) {
        return Err(at(
            "E_INPUT",
            "tick_table",
            "floors must start at 0 and increase",
        ));
    }
    if rows.iter().any(|r| r.1.signum() <= 0) {
        return Err(at("E_DOMAIN", "tick_table", "ticks must be positive"));
    }
    Ok(rows)
}

fn tick_at(table: &[(Dec, Dec)], price: Dec) -> Dec {
    table
        .iter()
        .rfind(|r| r.0 <= price)
        .map_or(table[0].1, |r| r.1)
}

fn label_eq(raw: &Json) -> Result<&'static str> {
    match raw.get("data_source") {
        None => Ok(EQ_LABEL),
        Some(v) => match v.as_str() {
            Some("SIMULATED") => Ok(EQ_LABEL),
            Some("IEX") => Ok(IEX_LABEL),
            _ => Err(at("E_SCHEMA", "data_source", "not SIMULATED or IEX")),
        },
    }
}

fn positive_price(price: Dec) -> Result<()> {
    if price.signum() <= 0 {
        return Err(at("E_DOMAIN", "price", "price must be positive"));
    }
    Ok(())
}

/// `micro.eq.round_price` (HR-81): a buy rounds down to the grid, a sell up.
pub fn eq_round_price(raw: &Json) -> Result<Json> {
    let price = dec_of(raw, "price", None, "")?;
    let buy = enum_of(raw, "side", &["BUY", "SELL"], "")? == "BUY";
    let table = tick_table(raw)?;
    positive_price(price)?;
    let tick = tick_at(&table, price);
    let r = price.div_int(tick, !buy)?.checked_mul(tick)?;
    // A sell rounded up across a floor lands on the floor, which is on both grids (HR-81).
    let p = places(tick_at(&table, r));
    Ok(out(vec![("price", fixed_at(r, p).into())]))
}

/// `micro.eq.fee_check` (HR-85): the [REGNMS-610] access-fee cap for the price band.
pub fn eq_fee_check(raw: &Json) -> Result<Json> {
    let price = dec_of(raw, "price", None, "")?;
    let fee = dec_of(raw, "taker_fee", None, "")?;
    let check = bool_of(raw, "cap_check", true)?;
    let (per_share, frac) = if current(raw)? {
        FEE_CAP_CURRENT
    } else {
        FEE_CAP_OLD
    };
    positive_price(price)?;
    let cap = if price >= Dec::int(1) {
        d(per_share)
    } else {
        d(frac).checked_mul(price)?
    };
    if check && fee > cap {
        return Err(at("E_DOMAIN", "taker_fee", "above the Rule 610 cap"));
    }
    Ok(out(vec![("cap", s(cap)), ("taker_fee", s(fee))]))
}

/// `micro.eq.round_lot` (HR-82 as dated rule versions).
pub fn eq_round_lot(raw: &Json) -> Result<Json> {
    let price = dec_of(raw, "price", None, "")?;
    let cur = current(raw)?;
    positive_price(price)?;
    let lot = if cur {
        ROUND_LOTS_CURRENT
            .iter()
            .find(|(cap, _)| price <= d(cap))
            .map_or(1, |r| r.1)
    } else {
        100
    };
    Ok(out(vec![("round_lot", Json::Int(lot))]))
}

fn good(x: Date, hol: &HashSet<Date>) -> bool {
    !x.is_weekend() && !hol.contains(&x)
}

fn add_good(mut x: Date, n: i64, ok: &dyn Fn(Date) -> bool) -> Result<Date> {
    for _ in 0..n {
        x = x.add_days(1);
        let mut found = false;
        for _ in 0..MAX_DAYS {
            if ok(x) {
                found = true;
                break;
            }
            x = x.add_days(1);
        }
        if !found {
            return Err(at(
                "E_DOMAIN",
                "holidays",
                "no business day within ten years",
            ));
        }
    }
    Ok(x)
}

/// Equities settlement date (HR-86): `settle_lag` business days on the supplied calendar.
pub fn eq_settle_date(raw: &Json) -> Result<Json> {
    let trade = date_of(need(raw, "trade_date", "")?, "trade_date")?;
    let lag = int_of_key(raw, "settle_lag", Some(1), "")?;
    let hol = match raw.get("holidays") {
        Some(v) => dates_of(v, "holidays")?,
        None => HashSet::new(),
    };
    if !(0..=30).contains(&lag) {
        return Err(at("E_DOMAIN", "settle_lag", "outside 0..30"));
    }
    let x = add_good(trade, lag, &|x| good(x, &hol))?;
    Ok(out(vec![("settle_date", x.to_string().into())]))
}

// ------------------------------------------------------------------ equity auction

struct AucOrder {
    id: String,
    buy: bool,
    limit: Option<Dec>,
    qty: i64,
    seq: i64,
    on_close: bool,
}

/// `exec.sim.auction.uncross`: one price that trades the most shares (auction.md).
#[allow(clippy::too_many_lines)]
pub fn auction_uncross(raw: &Json) -> Result<Json> {
    let label = label_eq(raw)?;
    let tick = dec_of(raw, "tick_size", None, "")?;
    let rf = dec_of(raw, "ref_price", None, "")?;
    enum_of(raw, "phase", &["OPEN", "CLOSE"], "")?;
    let iex = match raw.get("tie_break") {
        None => false,
        Some(v) => match v.as_str() {
            Some("CBOE") => false,
            Some("IEX") => true,
            _ => return Err(at("E_SCHEMA", "tie_break", "not CBOE or IEX")),
        },
    };
    let orders = list_of(raw, "orders")?;
    if orders.len() > MAX_ORDERS {
        return Err(at("E_LIMIT", "orders", "more than 10,000,000 orders"));
    }
    let mut parsed = Vec::with_capacity(orders.len());
    let (mut nb, mut ns) = (0, 0);
    for (k, o) in orders.iter().enumerate() {
        let p = format!("orders/{k}/");
        let o = obj_at(o, &p[..p.len() - 1])?;
        let buy = enum_of(o, "side", &["BUY", "SELL"], &p)? == "BUY";
        let lim = need(o, "limit", &p)?;
        let limit = if lim.as_str() == Some("MARKET") {
            None
        } else {
            Some(input_dec(Some(lim), &format!("{p}limit"))?)
        };
        let qty = int_of_key(o, "qty", None, &p)?;
        let on_close = match o.get("on_close") {
            None => false,
            Some(Json::Bool(b)) => *b,
            Some(_) => return Err(at("E_SCHEMA", &format!("{p}on_close"), "not a boolean")),
        };
        if buy {
            nb += 1;
        } else {
            ns += 1;
        }
        let id = match o.get("id") {
            None => {
                if buy {
                    format!("b{nb}")
                } else {
                    format!("a{ns}")
                }
            }
            Some(Json::Str(t)) => t.clone(),
            Some(_) => return Err(at("E_SCHEMA", &format!("{p}id"), "not a string")),
        };
        let seq = int_of_key(o, "seq", Some(k as i64 + 1), &p)?;
        parsed.push(AucOrder {
            id,
            buy,
            limit,
            qty,
            seq,
            on_close,
        });
    }
    let ids: HashSet<&str> = parsed.iter().map(|o| o.id.as_str()).collect();
    if ids.len() != parsed.len() {
        return Err(at("E_INPUT", "orders", "duplicate order id"));
    }
    if tick.signum() <= 0 {
        return Err(at("E_DOMAIN", "tick_size", "tick_size must be positive"));
    }
    if rf.signum() <= 0 {
        return Err(at("E_DOMAIN", "ref_price", "ref_price must be positive"));
    }
    for (k, o) in parsed.iter().enumerate() {
        if o.qty <= 0 {
            return Err(at(
                "E_DOMAIN",
                "orders",
                &format!("{k}: qty must be positive"),
            ));
        }
        if let Some(l) = o.limit
            && (l.signum() <= 0 || !l.on_grid(tick)?)
        {
            return Err(at(
                "E_DOMAIN",
                "orders",
                &format!("{k}: limit not a positive tick multiple"),
            ));
        }
    }
    let pl = places(tick);
    let mut buys: Vec<&AucOrder> = parsed.iter().filter(|o| o.buy).collect();
    let mut sells: Vec<&AucOrder> = parsed.iter().filter(|o| !o.buy).collect();
    // Market orders first, then by price priority, then by sequence (stable, as Python's sort).
    buys.sort_by(|a, b| {
        (a.limit.is_some().cmp(&b.limit.is_some()))
            .then(
                b.limit
                    .unwrap_or_default()
                    .cmp(&a.limit.unwrap_or_default()),
            )
            .then(a.seq.cmp(&b.seq))
    });
    sells.sort_by(|a, b| {
        (a.limit.is_some().cmp(&b.limit.is_some()))
            .then(
                a.limit
                    .unwrap_or_default()
                    .cmp(&b.limit.unwrap_or_default()),
            )
            .then(a.seq.cmp(&b.seq))
    });
    let limits: Vec<Dec> = parsed.iter().filter_map(|o| o.limit).collect();
    let mut best: Option<(Dec, i128, i128)> = None;
    if !buys.is_empty() && !sells.is_empty() && !limits.is_empty() {
        let lo = *limits.iter().min().expect("non-empty");
        let hi = *limits.iter().max().expect("non-empty");
        let n = int_of(hi.checked_sub(lo)?.div_int(tick, false)?) + 1;
        if n > MAX_CANDIDATES {
            return Err(at(
                "E_LIMIT",
                "orders",
                "more than 1,000,000 candidate prices",
            ));
        }
        let mut cands: Vec<(Dec, i128, i128)> = Vec::with_capacity(n as usize);
        for i in 0..n {
            let px = lo.checked_add(dint(i)?.checked_mul(tick)?)?;
            let b: i128 = buys
                .iter()
                .filter(|x| x.limit.is_none_or(|l| l >= px))
                .map(|x| i128::from(x.qty))
                .sum();
            let sv: i128 = sells
                .iter()
                .filter(|x| x.limit.is_none_or(|l| l <= px))
                .map(|x| i128::from(x.qty))
                .sum();
            cands.push((px, b.min(sv), b - sv));
        }
        let vmax = cands.iter().map(|c| c.1).max().unwrap_or(0);
        if vmax > 0 {
            let mut keep: Vec<(Dec, i128, i128)> =
                cands.iter().copied().filter(|c| c.1 == vmax).collect();
            if !iex {
                let imin = keep.iter().map(|c| c.2.abs()).min().expect("non-empty");
                keep.retain(|c| c.2.abs() == imin);
                if keep.iter().all(|c| c.2 > 0) {
                    keep = vec![*keep.iter().max_by(|a, b| a.0.cmp(&b.0)).expect("non-empty")];
                } else if keep.iter().all(|c| c.2 < 0) {
                    keep = vec![*keep.iter().min_by(|a, b| a.0.cmp(&b.0)).expect("non-empty")];
                }
            }
            // Nearest the reference price, then the higher price.
            let dist = |c: &(Dec, i128, i128)| -> Result<Dec> {
                let x = c.0.checked_sub(rf)?;
                if x.signum() < 0 {
                    Dec::ZERO.checked_sub(x)
                } else {
                    Ok(x)
                }
            };
            let mut dmin: Option<Dec> = None;
            for c in &keep {
                let dd = dist(c)?;
                dmin = Some(dmin.map_or(dd, |m| m.min(dd)));
            }
            let mut chosen: Option<(Dec, i128, i128)> = None;
            for c in &keep {
                if Some(dist(c)?) == dmin && chosen.is_none_or(|b| c.0 > b.0) {
                    chosen = Some(*c);
                }
            }
            best = chosen;
        }
    }
    let mut fills = Vec::new();
    let mut residual = Vec::new();
    let mut cancelled = Vec::new();
    for side in [&buys, &sells] {
        let mut left = best.map_or(0, |b| b.1);
        for o in side {
            let q = i128::from(o.qty).min(left);
            let sd = if o.buy { "B" } else { "S" };
            if q > 0 {
                let px = best.expect("a fill has a price").0;
                fills.push(out(vec![
                    ("id", o.id.clone().into()),
                    ("price", fixed_at(px, pl).into()),
                    ("qty", Json::Int(q as i64)),
                    ("side", sd.into()),
                ]));
                left -= q;
            }
            let rest = i128::from(o.qty) - q;
            if rest > 0 {
                match o.limit {
                    Some(l) if !o.on_close => residual.push(out(vec![
                        ("id", o.id.clone().into()),
                        ("limit", fixed_at(l, pl).into()),
                        ("qty", Json::Int(rest as i64)),
                        ("side", sd.into()),
                    ])),
                    _ => cancelled.push(Json::Str(o.id.clone())),
                }
            }
        }
    }
    Ok(out(vec![
        ("cancelled", Json::Arr(cancelled)),
        ("fills", Json::Arr(fills)),
        ("imbalance", Json::Int(best.map_or(0, |b| b.2) as i64)),
        ("label", label.into()),
        (
            "price",
            best.map_or(Json::Null, |b| fixed_at(b.0, pl).into()),
        ),
        ("residual", Json::Arr(residual)),
        ("volume", Json::Int(best.map_or(0, |b| b.1) as i64)),
    ]))
}

// ------------------------------------------------------------------ FX spot (H-23)

fn pair(raw: &Json) -> Result<(&'static str, &'static str)> {
    let p = str_of(raw, "pair", "")?;
    let bad = || at("E_INPUT", "pair", "not a pair of two listed currencies");
    if p.len() != 6 || !p.is_ascii() {
        return Err(bad());
    }
    let pos = |c: &str| CCY_ORDER.iter().position(|x| *x == c);
    let (Some(b), Some(q)) = (pos(&p[..3]), pos(&p[3..])) else {
        return Err(bad());
    };
    if b == q {
        return Err(bad());
    }
    if b > q {
        return Err(at("E_INPUT", "pair", "base must rank before quote (HR-88)"));
    }
    Ok((CCY_ORDER[b], CCY_ORDER[q]))
}

fn pip(quote: &str) -> Dec {
    d(if quote == "JPY" { "0.01" } else { "0.0001" })
}

/// FX pip value in the quote currency (HR-87): notional x pip.
pub fn fx_pip_value(raw: &Json) -> Result<Json> {
    let notional = dec_of(raw, "notional", None, "")?;
    let (_, quote) = pair(raw)?;
    if notional.signum() < 0 {
        return Err(at("E_DOMAIN", "notional", "must not be negative"));
    }
    Ok(out(vec![
        ("currency", quote.into()),
        ("pip_value", s(notional.checked_mul(pip(quote))?)),
    ]))
}

/// FX spot value date (HR-89): T+2 (T+1 pairs) good days in both currencies, then a USD day.
pub fn fx_spot_date(raw: &Json) -> Result<Json> {
    let trade = date_of(need(raw, "trade_date", "")?, "trade_date")?;
    let mut hol: HashMap<String, HashSet<Date>> = HashMap::new();
    match raw.get("holidays") {
        None => {}
        Some(Json::Obj(fields)) => {
            for (c, v) in fields {
                hol.insert(c.clone(), dates_of(v, &format!("holidays/{c}"))?);
            }
        }
        Some(_) => {
            return Err(at(
                "E_SCHEMA",
                "holidays",
                "not an object of currency -> dates",
            ));
        }
    }
    let t1: Vec<&str> = match raw.get("t1_pairs") {
        None => T1_PAIRS.to_vec(),
        Some(v) => {
            let list = v
                .as_array()
                .filter(|a| a.iter().all(|x| x.as_str().is_some()));
            let Some(list) = list else {
                return Err(at("E_SCHEMA", "t1_pairs", "not an array of strings"));
            };
            list.iter().filter_map(Json::as_str).collect()
        }
    };
    let (base, quote) = pair(raw)?;
    let empty = HashSet::new();
    let h = |c: &str| hol.get(c).unwrap_or(&empty);
    let both = |x: Date| good(x, h(base)) && good(x, h(quote));
    // A USD-only holiday on T+1 does not stop the count.
    let non_usd = |x: Date| {
        [base, quote]
            .iter()
            .filter(|c| **c != "USD")
            .all(|c| good(x, h(c)))
    };
    let name = format!("{base}{quote}");
    let x = if t1.contains(&name.as_str()) {
        add_good(trade, 1, &both)?
    } else {
        add_good(add_good(trade, 1, &non_usd)?, 1, &both)?
    };
    let x = add_good(x.add_days(-1), 1, &|x| both(x) && good(x, h("USD")))?;
    Ok(out(vec![("spot_date", x.to_string().into())]))
}

/// `exec.sim.fx.stream`: bid rounded down and ask rounded up to the tick (fx-rfq-venue.md).
pub fn fx_stream(raw: &Json) -> Result<Json> {
    let path = list_of(raw, "mid_path")?;
    let hs = dec_of(raw, "half_spread_pips", None, "")?;
    let mut pts = Vec::with_capacity(path.len());
    for (k, x) in path.iter().enumerate() {
        let p = format!("mid_path/{k}");
        let x = obj_at(x, &p)?;
        let pp = format!("{p}/");
        pts.push((
            int_of_key(x, "time", None, &pp)?,
            dec_of(x, "mid", None, &pp)?,
        ));
    }
    let (_, quote) = pair(raw)?;
    let pp = pip(quote);
    let dflt = if quote == "JPY" { "0.001" } else { "0.00001" };
    let tick = dec_of(raw, "tick", Some(dflt), "")?;
    if pts.is_empty() {
        return Err(at("E_INPUT", "mid_path", "mid_path is empty"));
    }
    if tick.signum() <= 0 || hs.signum() < 0 {
        return Err(at(
            "E_DOMAIN",
            "tick",
            "tick must be positive and half_spread_pips not negative",
        ));
    }
    let pl = places(tick);
    let half = hs.checked_mul(pp)?;
    let mut quotes = Vec::with_capacity(pts.len());
    for (t, mid) in pts {
        if mid.signum() <= 0 {
            return Err(at("E_DOMAIN", "mid_path", "mid must be positive"));
        }
        let bid = mid
            .checked_sub(half)?
            .div_int(tick, false)?
            .checked_mul(tick)?;
        let ask = mid
            .checked_add(half)?
            .div_int(tick, true)?
            .checked_mul(tick)?;
        quotes.push(out(vec![
            ("ask", fixed_at(ask, pl).into()),
            ("bid", fixed_at(bid, pl).into()),
            ("mid", s(mid)),
            ("time", Json::Int(t)),
        ]));
    }
    Ok(out(vec![
        ("label", FX_LABEL.into()),
        ("quotes", Json::Arr(quotes)),
    ]))
}

/// `exec.sim.fx.request`: last look (HR-97); strict comparisons, exact decimals.
pub fn fx_request(raw: &Json) -> Result<Json> {
    let q = obj_at(need(raw, "quote", "")?, "quote")?;
    let bid = dec_of(q, "bid", None, "quote/")?;
    let ask = dec_of(q, "ask", None, "quote/")?;
    let qmid = dec_of(q, "quote_mid", None, "quote/")?;
    let buy = enum_of(raw, "side", &["BUY", "SELL"], "")? == "BUY";
    let qty = dec_of(raw, "qty", None, "")?;
    let after = dec_of(raw, "mid_after", None, "")?;
    let thr = dec_of(raw, "threshold_pips", None, "")?;
    let sym = bool_of(raw, "symmetric", true)?;
    let prr = dec_of(raw, "p_random_reject", None, "")?;
    // HR-97: without `u`, u is drawn from core.rng with stream = request_index; the draw is
    // (k + 1/2) 2^-52 = (2k + 1) / 2^53, kept exact for the comparison.
    let drawn = if raw.get("u").is_none() {
        let seed = int_of_key(raw, "seed", None, "")?;
        let idx = int_of_key(raw, "request_index", None, "")?;
        // HR-116: seed within 0..2^53 - 1, request_index within 0..2^32 - 1, outside `E_LIMIT`.
        let Ok(seed) = u64::try_from(seed) else {
            return Err(at("E_LIMIT", "seed", "seed below 0"));
        };
        let Ok(idx) = u32::try_from(idx) else {
            return Err(at(
                "E_LIMIT",
                "request_index",
                "request_index outside 0..2^32 - 1",
            ));
        };
        let x = crate::rng::Xoshiro::seeded(seed, idx).next_u64();
        Some((2 * i128::from(x >> 12) + 1, crate::rng::to_uniform(x)))
    } else {
        None
    };
    let u = match drawn {
        Some(_) => Dec::ZERO,
        None => dec_of(raw, "u", None, "")?,
    };
    let (_, quote) = pair(raw)?;
    if bid > ask {
        return Err(at("E_INPUT", "quote", "bid above ask"));
    }
    let one = Dec::int(1);
    if qty.signum() <= 0
        || thr.signum() < 0
        || prr.signum() < 0
        || prr > one
        || u.signum() < 0
        || u >= one
    {
        return Err(at(
            "E_DOMAIN",
            "u",
            "qty > 0, threshold >= 0, p in [0, 1], u in [0, 1)",
        ));
    }
    let per_pip = Dec::int(if quote == "JPY" { 100 } else { 10_000 });
    let mv = after.checked_sub(qmid)?.checked_mul(per_pip)?;
    let neg = Dec::ZERO.checked_sub(mv)?;
    let adverse = if buy { mv } else { neg };
    let test = if sym { mv.max(neg) } else { adverse };
    let outcome = if test > thr {
        "LL_PRICE"
    } else if match drawn {
        Some((odd, _)) => {
            let (pm, ps) = prr.parts();
            odd * 10i128.pow(ps) < pm * (1i128 << 53)
        }
        None => u < prr,
    } {
        "LL_RANDOM"
    } else {
        "FILL"
    };
    let price = if outcome == "FILL" {
        s(if buy { ask } else { bid })
    } else {
        Json::Null
    };
    let mut fields = vec![
        ("label", FX_LABEL.into()),
        ("move_pips", s(mv)),
        ("outcome", outcome.into()),
        ("price", price),
    ];
    if let Some((_, uf)) = drawn {
        fields.push(("u", Json::Num(uf)));
    }
    Ok(out(fields))
}

// ------------------------------------------------------------------ rates (H-24)

/// `H-FF[f]` (HR-90; `3` = 3/8 of a 32nd) to its exact value.
pub fn parse_32nds(text: &Json, path: &str) -> Result<Dec> {
    let Some(t) = text.as_str() else {
        return Err(at("E_SCHEMA", path, "not a string"));
    };
    // HR-109: CME quarter-32nds, third digit 0, 2, 5, 7 (0, 1/4, 1/2, 3/4) or "+" (1/2).
    let bad = || {
        at(
            "E_SCHEMA",
            path,
            "not H-FF[q] with q in 0, 2, 5, 7, + (HR-109)",
        )
    };
    let (h, rest) = t.split_once('-').ok_or_else(bad)?;
    let digits = |x: &str| !x.is_empty() && x.bytes().all(|b| b.is_ascii_digit());
    let ff: String = rest.chars().take(2).collect();
    let q: String = rest.chars().skip(2).collect();
    if !digits(h) || ff.len() != 2 || !digits(&ff) || q.chars().count() > 1 {
        return Err(bad());
    }
    let quarter = match q.as_str() {
        "" | "0" => 0,
        "2" => 1,
        "5" | "+" => 2,
        "7" => 3,
        _ => return Err(bad()),
    };
    let ff: i64 = ff.parse().map_err(|_| bad())?;
    if ff > 31 {
        return Err(at("E_DOMAIN", path, "32nds above 31"));
    }
    let hd = Dec::parse(h)
        .ok_or_else(bad)?
        .map_err(|_| at("E_LIMIT", path, "decimal outside the exact range"))?;
    hd.checked_add(Dec::int(4 * ff + quarter).checked_mul(d("0.0078125"))?)
        .map_err(|_| at("E_LIMIT", path, "decimal outside the exact range"))
}

fn format_32nds(x: Dec, resolution: i64) -> Result<String> {
    if !RESOLUTIONS.contains(&resolution) {
        return Err(at("E_DOMAIN", "resolution", "resolution not 32, 64 or 128"));
    }
    if x.signum() < 0 || !x.checked_mul(Dec::int(resolution))?.on_grid(Dec::int(1))? {
        return Err(at("E_DOMAIN", "value", "value not on the requested grid"));
    }
    let h = x.div_int(Dec::int(1), false)?;
    let quarters = int_of(x.checked_sub(h)?.checked_mul(Dec::int(128))?);
    let (ff, q) = (quarters / 4, quarters % 4);
    let qt = ["", "2", "+", "7"][q as usize];
    Ok(format!("{h}-{ff:02}{qt}"))
}

/// 32nds text to a decimal (HR-90).
pub fn rates_parse_32nds(raw: &Json) -> Result<Json> {
    let v = parse_32nds(need(raw, "text", "")?, "text")?;
    Ok(out(vec![("value", s(v))]))
}

/// A decimal to 32nds text at `resolution` parts per point (HR-90).
pub fn rates_format_32nds(raw: &Json) -> Result<Json> {
    let x = dec_of(raw, "value", None, "")?;
    let res = int_of_key(raw, "resolution", None, "")?;
    Ok(out(vec![("text", format_32nds(x, res)?.into())]))
}

fn contract(raw: &Json) -> Result<(Dec, Dec)> {
    let dflt = Json::Obj(vec![("symbol".into(), "ZN".into())]);
    let c = obj_at(raw.get("contract").unwrap_or(&dflt), "contract")?;
    let sym = match c.get("symbol") {
        None | Some(Json::Null) => "",
        Some(Json::Str(t)) => t.as_str(),
        Some(_) => return Err(at("E_SCHEMA", "contract/symbol", "not a string")),
    };
    let (fd, td) = match sym {
        "ZN" => (Some("100000"), Some("0.015625")), // [CME-ZN]
        "ZB" => (Some("100000"), Some("0.03125")),  // [CME-ZB]
        _ => (None, None),
    };
    let face = dec_of(c, "face", fd, "contract/")?;
    let tick = dec_of(c, "tick", td, "contract/")?;
    if face.signum() <= 0 || tick.signum() <= 0 {
        return Err(at(
            "E_DOMAIN",
            "contract",
            "contract face and tick must be positive",
        ));
    }
    Ok((face, tick))
}

fn tick_value(face: Dec, tick: Dec) -> Result<Dec> {
    face.checked_mul(tick)?.checked_mul(d("0.01"))
}

/// Futures tick value = face x tick / 100 (HR-91).
pub fn rates_tick_value(raw: &Json) -> Result<Json> {
    let face = dec_of(raw, "face", None, "")?;
    let tick = dec_of(raw, "tick", None, "")?;
    if face.signum() <= 0 || tick.signum() <= 0 {
        return Err(at("E_DOMAIN", "face", "face and tick must be positive"));
    }
    Ok(out(vec![("tick_value", s(tick_value(face, tick)?))]))
}

/// Coupon bond price on a coupon date, street convention (HR-92), 9 decimals.
pub fn rates_bond_price(raw: &Json) -> Result<Json> {
    let c = dec_of(raw, "coupon", None, "")?;
    let y = dec_of(raw, "yield", None, "")?;
    let f = int_of_key(raw, "frequency", None, "")?;
    let n = int_of_key(raw, "periods", None, "")?;
    if ![1, 2, 4, 12].contains(&f) {
        return Err(at("E_DOMAIN", "frequency", "frequency not 1, 2, 4 or 12"));
    }
    if !(1..=1200).contains(&n) {
        return Err(at("E_DOMAIN", "periods", "periods outside 1..1200"));
    }
    let (ym, ys) = y.parts();
    let dd = (f as u128) * 10u128.pow(ys); // D: g = N / D
    let nn = dd as i128 + ym;
    if nn <= 0 {
        return Err(at("E_DOMAIN", "yield", "yield at or below -frequency"));
    }
    let (bd, bn) = (Big::from(dd), Big::from(nn as u128));
    // S = sum_{i=1..n} D^i N^(n-i) (Horner), D^n and N^n.
    let (mut acc, mut dp, mut np) = (Big::from(0), Big::from(1), Big::from(1));
    for _ in 0..n {
        dp = dp.mul(&bd);
        acc = acc.mul(&bn).add(&dp);
        np = np.mul(&bn);
    }
    // P = [100 cm S + 100 f 10^cs D^n] / [f 10^cs N^n] for c = cm / 10^cs.
    let (cm, cs) = c.parts();
    let scale = (f as u128) * 10u128.pow(cs);
    let a = Big::from(100 * cm.unsigned_abs()).mul(&acc);
    let b = Big::from(100 * scale).mul(&dp);
    let (neg, num) = if cm >= 0 {
        (false, a.add(&b))
    } else if a.cmp(&b) == Ordering::Greater {
        (true, a.sub(&b))
    } else {
        (false, b.sub(&a))
    };
    let den = Big::from(scale).mul(&np);
    let limit = || {
        at(
            "E_LIMIT",
            "value",
            "decimal outside the exact range (HR-57)",
        )
    };
    if num.cmp(&den.mul(&Big::from(10u128.pow(36)))) != Ordering::Less {
        return Err(limit());
    }
    // The reference quantizes to 30 decimals, range-checks, then rounds to 9 (both half-even).
    let (ip, f30) = split(&num, &den, 30);
    if ip >= 10u128.pow(36) {
        return Err(limit());
    }
    let frac_digits = if f30 == 0 {
        0
    } else {
        30 - trailing_zeros(f30)
    };
    let sig = if ip > 0 {
        ip.to_string().len() + frac_digits
    } else if f30 == 0 {
        0
    } else {
        strip(f30).to_string().len()
    };
    if sig > 36 {
        return Err(limit());
    }
    let unit = 10u128.pow(21);
    let (mut f9, r) = (f30 / unit, f30 % unit);
    let mut ip = ip;
    if 2 * r > unit || (2 * r == unit && f9 % 2 == 1) {
        f9 += 1;
        if f9 == 10u128.pow(9) {
            (f9, ip) = (0, ip + 1);
        }
    }
    Ok(out(vec![("price", text9(neg, ip, f9).into())]))
}

/// Yield from a coupon-date price (HR-92): Brent (`core.solve`), tolerance 1e-12, binary64.
pub fn rates_bond_yield(raw: &Json) -> Result<Json> {
    let c = dec_of(raw, "coupon", None, "")?;
    let p = dec_of(raw, "price", None, "")?;
    let f = int_of_key(raw, "frequency", None, "")?;
    let n = int_of_key(raw, "periods", None, "")?;
    if ![1, 2, 4, 12].contains(&f) {
        return Err(at("E_DOMAIN", "frequency", "frequency not 1, 2, 4 or 12"));
    }
    if !(1..=1200).contains(&n) {
        return Err(at("E_DOMAIN", "periods", "periods outside 1..1200"));
    }
    if p.signum() <= 0 {
        return Err(at("E_DOMAIN", "price", "price must be positive"));
    }
    // float(100 c / f): the exact quotient, rounded once to binary64.
    let (cm, cs) = c.parts();
    let den = Big::from((f as u128) * 10u128.pow(cs));
    let (ip, frac) = split(&Big::from(100 * cm.unsigned_abs()), &den, 30);
    let mag: f64 = format!("{ip}.{frac:030}").parse().unwrap_or(0.0);
    let cf = if cm < 0 { -mag } else { mag };
    let pf: f64 = p.to_string().parse().unwrap_or(0.0);
    let ff = f as f64;
    let g = |y: f64| {
        let d = 1.0 + y / ff;
        let mut sum = 0.0;
        for i in 1..=n {
            sum += cf / d.powf(i as f64);
        }
        sum + 100.0 / d.powf(n as f64) - pf
    };
    let (lo, hi) = (-0.99 * ff, 10.0);
    if g(lo) * g(hi) > 0.0 {
        return Err(at("E_DOMAIN", "price", "no yield in (-0.99 f, 10)"));
    }
    let ctl = crate::root::Controls {
        x_tol: 1e-12,
        f_tol: 0.0,
        max_iter: 200,
    };
    let r = crate::root::brent(&g, lo, hi, &ctl)?;
    Ok(out(vec![("yield", Json::Num(r.root))]))
}

/// Bill price on the discount basis [UST-BILL]: 100 (1 - d days / 360), 9 decimals.
pub fn rates_bill_price(raw: &Json) -> Result<Json> {
    let dc = dec_of(raw, "discount", None, "")?;
    let days = int_of_key(raw, "days", None, "")?;
    if !(0..=366).contains(&days) {
        return Err(at("E_DOMAIN", "days", "days outside 0..366"));
    }
    // 100 - 5 d days / 18 = (1800 10^s - 5 dm days) / (18 10^s) for d = dm / 10^s.
    let (dm, ds) = dc.parts();
    let a = Big::from(1800 * 10u128.pow(ds));
    let b = Big::from(dm.unsigned_abs()).mul(&Big::from(5 * days as u128));
    let (neg, num) = if dm < 0 {
        (false, a.add(&b))
    } else if b.cmp(&a) == Ordering::Greater {
        (true, b.sub(&a))
    } else {
        (false, a.sub(&b))
    };
    let den = Big::from(18 * 10u128.pow(ds));
    let (ip, f9) = split(&num, &den, 9);
    Ok(out(vec![("price", text9(neg, ip, f9).into())]))
}

fn trailing_zeros(mut x: u128) -> usize {
    let mut k = 0;
    while x != 0 && x.is_multiple_of(10) {
        x /= 10;
        k += 1;
    }
    k
}

fn strip(mut x: u128) -> u128 {
    while x != 0 && x.is_multiple_of(10) {
        x /= 10;
    }
    x
}

fn text9(neg: bool, ip: u128, f9: u128) -> String {
    if ip == 0 && f9 == 0 {
        return "0".into();
    }
    let sign = if neg { "-" } else { "" };
    if f9 == 0 {
        return format!("{sign}{ip}");
    }
    let frac = format!("{f9:09}");
    format!("{sign}{ip}.{}", frac.trim_end_matches('0'))
}

/// `num / den` (`num < 2^127 den`) as an integer part and `places` decimals, half to even.
fn split(num: &Big, den: &Big, places: u32) -> (u128, u128) {
    let (mut ip, r) = num.divq(den);
    let (mut f, r2) = r.mul(&Big::from(10u128.pow(places))).divq(den);
    match r2.shl(1).cmp(den) {
        Ordering::Greater => f += 1,
        Ordering::Equal if f % 2 == 1 => f += 1,
        _ => {}
    }
    if f == 10u128.pow(places) {
        (f, ip) = (0, ip + 1);
    }
    (ip, f)
}

fn fut_ticks(v: &Json, tick: Dec, path: &str) -> Result<i128> {
    let x = match v.as_str() {
        Some(t) if t.get(1..).is_some_and(|r| r.contains('-')) => parse_32nds(v, path)?,
        _ => input_dec(Some(v), path)?,
    };
    if x.signum() < 0 || !x.on_grid(tick)? {
        return Err(at("E_DOMAIN", path, "price off the contract grid"));
    }
    Ok(int_of(x.div_int(tick, false)?))
}

/// Futures price (32nds text or decimal) to integer ticks (rates-futures-venue.md).
pub fn fut_to_ticks(raw: &Json) -> Result<Json> {
    let v = need(raw, "price", "")?;
    let (_, tick) = contract(raw)?;
    let t = fut_ticks(v, tick, "price")?;
    Ok(out(vec![
        ("label", RATES_LABEL.into()),
        ("ticks", Json::Int(t as i64)),
    ]))
}

/// Integer ticks to 32nds text at the contract resolution.
pub fn fut_to_text(raw: &Json) -> Result<Json> {
    let t = int_of_key(raw, "ticks", None, "")?;
    let (_, tick) = contract(raw)?;
    if t < 0 {
        return Err(at("E_DOMAIN", "ticks", "ticks must not be negative"));
    }
    let res = RESOLUTIONS.iter().copied().find(|r| {
        tick.checked_mul(Dec::int(*r))
            .is_ok_and(|x| x == Dec::int(1))
    });
    let Some(res) = res else {
        return Err(at(
            "E_DOMAIN",
            "contract",
            "contract tick is not 1/32, 1/64 or 1/128",
        ));
    };
    Ok(out(vec![
        ("label", RATES_LABEL.into()),
        (
            "text",
            format_32nds(Dec::int(t).checked_mul(tick)?, res)?.into(),
        ),
    ]))
}

/// One participant's round trip (HR-102): (sell - buy) ticks x qty x tick value - fees.
pub fn fut_pnl(raw: &Json) -> Result<Json> {
    let qty = int_of_key(raw, "qty", None, "")?;
    let bp = need(raw, "buy_price", "")?;
    let sp = need(raw, "sell_price", "")?;
    let fee = dec_of(raw, "fee_per_contract", Some("0"), "")?;
    let (face, tick) = contract(raw)?;
    if qty <= 0 || fee.signum() < 0 {
        return Err(at(
            "E_DOMAIN",
            "qty",
            "qty must be positive and fee not negative",
        ));
    }
    let dt = fut_ticks(sp, tick, "sell_price")? - fut_ticks(bp, tick, "buy_price")?;
    let q = Dec::int(qty);
    let fees = fee.checked_mul(Dec::int(2))?.checked_mul(q)?;
    let pnl = dint(dt)?
        .checked_mul(q)?
        .checked_mul(tick_value(face, tick)?)?
        .checked_sub(fees)?;
    Ok(out(vec![
        ("fees", s(fees)),
        ("label", RATES_LABEL.into()),
        ("pnl", s(pnl)),
    ]))
}

/// Daily variation margin (HR-92, HR-103): previous mark = fill price on the trade day.
pub fn fut_variation(raw: &Json) -> Result<Json> {
    let buy = enum_of(raw, "side", &["BUY", "SELL"], "")? == "BUY";
    let qty = int_of_key(raw, "qty", None, "")?;
    let p0 = need(raw, "price", "")?;
    let settles = list_of(raw, "settlements")?;
    let (face, tick) = contract(raw)?;
    if settles.is_empty() {
        return Err(at("E_INPUT", "settlements", "settlements is empty"));
    }
    if qty <= 0 {
        return Err(at("E_DOMAIN", "qty", "qty must be positive"));
    }
    let mut mark = fut_ticks(p0, tick, "price")?;
    let tv = tick_value(face, tick)?;
    let sign = if buy { 1 } else { -1 };
    let mut vm = Vec::with_capacity(settles.len());
    for (k, st) in settles.iter().enumerate() {
        let t = fut_ticks(st, tick, &format!("settlements/{k}"))?;
        let v = dint((t - mark) * sign)?
            .checked_mul(Dec::int(qty))?
            .checked_mul(tv)?;
        vm.push(s(v));
        mark = t;
    }
    Ok(out(vec![
        ("label", RATES_LABEL.into()),
        ("variation_margin", Json::Arr(vm)),
    ]))
}

/// `exec.sim.fut.run`: the lit engine unchanged on the contract tick grid, plus P&L per trader
/// marked at the last trade, minus `fee_per_contract` per contract per side (HR-102).
pub fn fut_run(raw: &Json) -> Result<Json> {
    let events = list_of(raw, "events")?;
    let fee = dec_of(raw, "fee_per_contract", Some("0"), "")?;
    let (face, tick) = contract(raw)?;
    if fee.signum() < 0 {
        return Err(at(
            "E_DOMAIN",
            "fee_per_contract",
            "fee_per_contract must not be negative",
        ));
    }
    let mut trader: HashMap<String, String> = HashMap::new();
    let mut buyer: HashMap<String, bool> = HashMap::new();
    let mut mapped = Vec::with_capacity(events.len());
    for (k, e) in events.iter().enumerate() {
        let Json::Obj(fields) = obj_at(e, &format!("events/{k}"))? else {
            unreachable!("checked object");
        };
        let mut fields = fields.clone();
        for (key, v) in &mut fields {
            if key == "price" && v.as_str().is_some() {
                let t = fut_ticks(v, tick, &format!("events/{k}/price"))?;
                *v = s(dint(t)?.checked_mul(tick)?);
            }
        }
        let e = Json::Obj(fields);
        if e.get("op").and_then(Json::as_str) == Some("NEW")
            && let Some(id) = e.get("id").and_then(Json::as_str)
        {
            if let Some(t) = e.get("trader").and_then(Json::as_str) {
                trader.insert(id.into(), t.into());
            }
            buyer.insert(
                id.into(),
                e.get("side").and_then(Json::as_str) == Some("BUY"),
            );
        }
        mapped.push(e);
    }
    let zero = Json::Obj(vec![
        ("maker_rebate".into(), "0".into()),
        ("taker_fee".into(), "0".into()),
    ]);
    let res = lit_matching::run(&tick.to_string(), "1", &mapped, &zero, None)?;
    let tv = tick_value(face, tick)?;
    let mut pos: BTreeMap<String, Dec> = BTreeMap::new();
    let mut cash: BTreeMap<String, Dec> = BTreeMap::new();
    let mut fees: BTreeMap<String, Dec> = BTreeMap::new();
    let mut last: Option<Dec> = None;
    let num = |v: Option<&Json>| -> Result<Dec> { input_dec(v, "fills") };
    for fl in res.get("fills").and_then(Json::as_array).unwrap_or(&[]) {
        let p = num(fl.get("price"))?;
        let q = num(fl.get("qty"))?;
        last = Some(p);
        let pt = p.div_int(tick, false)?;
        for key in ["maker_id", "taker_id"] {
            let oid = fl.get(key).and_then(Json::as_str).unwrap_or_default();
            let (Some(t), Some(b)) = (trader.get(oid), buyer.get(oid)) else {
                return Err(at(
                    "E_INPUT",
                    "events",
                    "fill for an order without a trader",
                ));
            };
            let sq = if *b { q } else { Dec::ZERO.checked_sub(q)? };
            let ps = pos.entry(t.clone()).or_default();
            *ps = ps.checked_add(sq)?;
            let cs = cash.entry(t.clone()).or_default();
            *cs = cs.checked_sub(sq.checked_mul(pt)?)?;
            let fs = fees.entry(t.clone()).or_default();
            *fs = fs.checked_add(fee.checked_mul(q)?)?;
        }
    }
    let mark = last.unwrap_or(Dec::ZERO).div_int(tick, false)?;
    let mut pnl = Vec::new();
    for (t, p) in &pos {
        let v = p
            .checked_mul(mark)?
            .checked_add(cash[t])?
            .checked_mul(tv)?
            .checked_sub(fees[t])?;
        pnl.push((t.clone(), s(v)));
    }
    let fees_j = Json::Obj(fees.iter().map(|(t, v)| (t.clone(), s(*v))).collect());
    let Json::Obj(mut fields) = res else {
        return Err(err("E_INPUT", "lit engine output is not an object"));
    };
    fields.retain(|(k, _)| k != "fees" && k != "pnl" && k != "label");
    fields.push(("fees".into(), fees_j));
    fields.push(("label".into(), RATES_LABEL.into()));
    fields.push(("pnl".into(), Json::Obj(pnl)));
    Ok(Json::Obj(fields))
}

// ------------------------------------------------------------------ big unsigned integers

/// A minimal unsigned big integer (little-endian 64-bit limbs) for the exact bond and bill prices.
#[derive(Clone, Debug)]
struct Big(Vec<u64>);

impl Big {
    fn from(n: u128) -> Big {
        Big(vec![n as u64, (n >> 64) as u64]).trim()
    }

    fn trim(mut self) -> Big {
        while self.0.last() == Some(&0) {
            self.0.pop();
        }
        self
    }

    fn mul(&self, o: &Big) -> Big {
        if self.0.is_empty() || o.0.is_empty() {
            return Big(Vec::new());
        }
        let mut r = vec![0u64; self.0.len() + o.0.len()];
        for (i, &a) in self.0.iter().enumerate() {
            let mut carry: u128 = 0;
            for (j, &b) in o.0.iter().enumerate() {
                let t = u128::from(a) * u128::from(b) + u128::from(r[i + j]) + carry;
                r[i + j] = t as u64;
                carry = t >> 64;
            }
            let mut k = i + o.0.len();
            while carry != 0 {
                let t = u128::from(r[k]) + carry;
                r[k] = t as u64;
                carry = t >> 64;
                k += 1;
            }
        }
        Big(r).trim()
    }

    fn add(&self, o: &Big) -> Big {
        let n = self.0.len().max(o.0.len());
        let mut r = Vec::with_capacity(n + 1);
        let mut carry = 0u128;
        for i in 0..n {
            let t = u128::from(*self.0.get(i).unwrap_or(&0))
                + u128::from(*o.0.get(i).unwrap_or(&0))
                + carry;
            r.push(t as u64);
            carry = t >> 64;
        }
        r.push(carry as u64);
        Big(r).trim()
    }

    /// `self - o` for `self >= o`.
    fn sub(&self, o: &Big) -> Big {
        let mut r = Vec::with_capacity(self.0.len());
        let mut borrow = 0i128;
        for i in 0..self.0.len() {
            let mut t = i128::from(self.0[i]) - i128::from(*o.0.get(i).unwrap_or(&0)) - borrow;
            borrow = 0;
            if t < 0 {
                t += 1i128 << 64;
                borrow = 1;
            }
            r.push(t as u64);
        }
        Big(r).trim()
    }

    /// `self * 2^k` for `k < 128`.
    fn shl(&self, k: u32) -> Big {
        let (w, b) = ((k / 64) as usize, k % 64);
        let mut r = vec![0u64; w];
        let mut carry = 0u64;
        for &x in &self.0 {
            r.push(if b == 0 { x } else { (x << b) | carry });
            carry = if b == 0 { 0 } else { x >> (64 - b) };
        }
        r.push(carry);
        Big(r).trim()
    }

    fn cmp(&self, o: &Big) -> Ordering {
        self.0
            .len()
            .cmp(&o.0.len())
            .then_with(|| self.0.iter().rev().cmp(o.0.iter().rev()))
    }

    /// Quotient and remainder for a quotient below 2^128 (shift-and-subtract on the quotient bits).
    fn divq(&self, den: &Big) -> (u128, Big) {
        let mut r = self.clone();
        let mut q: u128 = 0;
        for k in (0..128).rev() {
            let t = den.shl(k);
            if r.cmp(&t) != Ordering::Less {
                r = r.sub(&t);
                q |= 1u128 << k;
            }
        }
        (q, r)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json::parse;

    fn run(f: fn(&Json) -> Result<Json>, text: &str) -> Result<Json> {
        f(&parse(text).expect("json").0)
    }

    fn field(r: &Result<Json>, k: &str) -> String {
        r.as_ref().expect("ok").get(k).expect("key").to_text()
    }

    #[test]
    fn bond_and_bill_prices_are_exact() {
        let r = run(
            rates_bond_price,
            r#"{"coupon":"0.05","yield":"0.05","frequency":2,"periods":20}"#,
        );
        assert_eq!(field(&r, "price"), "\"100\"");
        let r = run(rates_bill_price, r#"{"discount":"0.05","days":91}"#);
        assert_eq!(field(&r, "price"), "\"98.736111111\"");
        let r = run(rates_bill_price, r#"{"discount":"-1","days":360}"#);
        assert_eq!(field(&r, "price"), "\"200\"");
        let r = run(rates_bill_price, r#"{"discount":"2","days":360}"#);
        assert_eq!(field(&r, "price"), "\"-100\"");
        let r = run(
            rates_bond_price,
            r#"{"coupon":"-0.5","yield":"0","frequency":1,"periods":3}"#,
        );
        assert_eq!(field(&r, "price"), "\"-50\"");
    }

    #[test]
    fn thirty_seconds_round_trip() {
        for t in ["110-16+", "0-00", "99-317", "1-012"] {
            let v = parse_32nds(&Json::Str(t.into()), "text").expect("parse");
            assert_eq!(format_32nds(v, 128).expect("format"), t);
        }
        let v = parse_32nds(&Json::Str("1-165".into()), "t").expect("parse");
        assert_eq!(format_32nds(v, 64).expect("format"), "1-16+");
        assert!(parse_32nds(&Json::Str("1-32".into()), "t").is_err_and(|e| e.code == "E_DOMAIN"));
        assert!(parse_32nds(&Json::Str("1-3".into()), "t").is_err_and(|e| e.code == "E_SCHEMA"));
        assert!(parse_32nds(&Json::Str("1-013".into()), "t").is_err_and(|e| e.code == "E_SCHEMA"));
    }

    #[test]
    fn big_division() {
        let a = Big::from(10u128.pow(30)).mul(&Big::from(7));
        let (q, r) = a.divq(&Big::from(3));
        assert_eq!(q, 7 * 10u128.pow(30) / 3);
        assert_eq!(r.cmp(&Big::from(1)), Ordering::Equal);
        assert_eq!(fixed_at(d("1.25"), 1), "1.2");
        assert_eq!(fixed_at(d("1.35"), 1), "1.4");
        assert_eq!(fixed_at(d("1"), 2), "1.00");
    }
}
