//! Paper trading (`specifications/10-execution/paper-trading.md`, rulings HR-42 to HR-55): the
//! hash-chained ledger, the book (positions, cash, financing, P&L explain), pre-trade checks and
//! the session that fills orders on the simulated lit engine, dark pool and router of this build.
//! A port of the Python reference (`quantforge_core/paper.py`, `paper_fills.py`), step for step:
//! the ledger hashes must match byte for byte across builds.
//!
//! Nothing here opens a socket or names an order-entry endpoint: no live order can be placed, and
//! an order with `mode` other than `"simulated"` is `E_UNSUPPORTED_OPERATION` (HR-42).
use crate::error::{Result, err};
use crate::execution::{TcaOrder, tca_shortfall};
use crate::json::Json;
use crate::paper_dec::PyDec;
use crate::sha256::sha256_hex;
use crate::{dark_pool, lit_matching, sor};
use std::collections::BTreeSet;
use std::fmt::Write;

pub const LABEL: &str = "crypto venue; simulated";
pub const CEILING: &str =
    "Paper trading on free data; simulated fills; no evidence of tradable profitability.";
pub const GENESIS: &str = "0000000000000000000000000000000000000000000000000000000000000000";
const KINDS: [&str; 6] = ["ORDER", "REJECT", "FILL", "CANCEL", "EOD", "TCA"];
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
const NONFINITE: [&str; 3] = ["NaN", "Infinity", "-Infinity"];
const SYM: &str = "S";

fn e(code: &'static str, m: impl Into<String>) -> crate::error::QfError {
    err(code, m)
}

fn s(v: impl Into<String>) -> Json {
    Json::Str(v.into())
}

fn ob(pairs: Vec<(&str, Json)>) -> Json {
    Json::Obj(pairs.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
}

/// Sets `k` in an object, replacing an existing member in place (Python dict update).
fn set_key(o: &mut Json, k: &str, v: Json) {
    if let Json::Obj(m) = o {
        if let Some(slot) = m.iter_mut().find(|(n, _)| n == k) {
            slot.1 = v;
        } else {
            m.push((k.to_string(), v));
        }
    }
}

fn parse_text(t: &str, name: &str) -> Result<PyDec> {
    PyDec::parse(t).unwrap_or_else(|| Err(e("E_PARSE", format!("{name} is not a decimal"))))
}

/// Python `dec`: a decimal given as a string (or integer); floats and booleans are `E_INPUT`.
fn dec(v: &Json, name: &str) -> Result<PyDec> {
    match v {
        Json::Num(x) if !x.is_finite() => {
            Err(e("E_SCHEMA", format!("{name} is not a finite decimal")))
        }
        Json::Bool(_) | Json::Num(_) => {
            Err(e("E_INPUT", format!("{name} must be a decimal string")))
        }
        Json::Int(n) => Ok(PyDec::int(*n)),
        Json::Str(t) => parse_text(t, name),
        _ => Err(e("E_PARSE", format!("{name} is not a decimal"))),
    }
}

/// A decimal input over the CLI must be a JSON string (HR-12, HR-44).
fn dstr(v: &Json, name: &str) -> Result<PyDec> {
    match v {
        Json::Str(t) => parse_text(t, name),
        _ => Err(e("E_SCHEMA", format!("{name} must be a decimal string"))),
    }
}

/// A member that is present and not null (`E_SCHEMA` otherwise).
fn req<'a>(m: &'a Json, k: &str, w: &str) -> Result<&'a Json> {
    m.get(k)
        .filter(|v| **v != Json::Null)
        .ok_or_else(|| e("E_SCHEMA", format!("{w}{k} is missing")))
}

fn side_sign(v: &Json) -> Result<i64> {
    match v.as_str() {
        Some("BUY") => Ok(1),
        Some("SELL") => Ok(-1),
        _ => Err(e("E_INPUT", "unknown side")),
    }
}

fn truthy(v: Option<&Json>, default: bool) -> bool {
    match v {
        None => default,
        Some(Json::Null) => false,
        Some(Json::Bool(b)) => *b,
        Some(Json::Int(n)) => *n != 0,
        Some(Json::Num(x)) => *x != 0.0,
        Some(Json::Str(t)) => !t.is_empty(),
        Some(Json::Arr(a)) => !a.is_empty(),
        Some(Json::Obj(o)) => !o.is_empty(),
    }
}

fn i(n: i64) -> PyDec {
    PyDec::int(n)
}

// ---------------------------------------------------------------- canonical JSON (HR-45)

/// Python `json.dumps(..., ensure_ascii=True)` string escaping.
fn write_str(t: &str, out: &mut String) {
    out.push('"');
    for c in t.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            ' '..='~' => out.push(c),
            c => {
                let mut buf = [0u16; 2];
                for u in c.encode_utf16(&mut buf) {
                    let _ = write!(out, "\\u{u:04x}");
                }
            }
        }
    }
    out.push('"');
}

/// Canonical text: keys sorted at every level, no whitespace, ASCII. Only the top-level `seq`
/// may be a number; any other number or a boolean is `E_INPUT` (HR-45).
fn write_canon(v: &Json, top_seq: bool, out: &mut String) -> Result<()> {
    match v {
        Json::Null => out.push_str("null"),
        Json::Str(t) => write_str(t, out),
        Json::Int(n) if top_seq => {
            let _ = write!(out, "{n}");
        }
        Json::Int(_) | Json::Num(_) | Json::Bool(_) => {
            return Err(e("E_INPUT", "only seq is an integer; values are strings"));
        }
        Json::Arr(a) => {
            out.push('[');
            for (k, x) in a.iter().enumerate() {
                if k > 0 {
                    out.push(',');
                }
                write_canon(x, false, out)?;
            }
            out.push(']');
        }
        Json::Obj(m) => {
            let mut keys: Vec<&(String, Json)> = m.iter().collect();
            keys.sort_by(|a, b| a.0.cmp(&b.0));
            out.push('{');
            for (k, (name, x)) in keys.into_iter().enumerate() {
                if k > 0 {
                    out.push(',');
                }
                write_str(name, out);
                out.push(':');
                write_canon(x, false, out)?;
            }
            out.push('}');
        }
    }
    Ok(())
}

/// The canonical bytes of a record without its `hash` (HR-45).
pub fn canonical(record: &Json) -> Result<String> {
    let Json::Obj(m) = record else {
        return Err(e("E_INPUT", "a record is an object"));
    };
    let mut out = String::from("{");
    let mut keys: Vec<&(String, Json)> = m.iter().filter(|(k, _)| k != "hash").collect();
    keys.sort_by(|a, b| a.0.cmp(&b.0));
    for (k, (name, x)) in keys.into_iter().enumerate() {
        if k > 0 {
            out.push(',');
        }
        write_str(name, &mut out);
        out.push(':');
        write_canon(x, name == "seq", &mut out)?;
    }
    out.push('}');
    Ok(out)
}

/// A copy with object keys sorted at every level (what Python reads back from a ledger line).
fn sorted(v: &Json) -> Json {
    match v {
        Json::Arr(a) => Json::Arr(a.iter().map(sorted).collect()),
        Json::Obj(m) => {
            let mut o: Vec<(String, Json)> =
                m.iter().map(|(k, x)| (k.clone(), sorted(x))).collect();
            o.sort_by(|a, b| a.0.cmp(&b.0));
            Json::Obj(o)
        }
        x => x.clone(),
    }
}

fn record(seq: i64, ts: &str, kind: &str, body: &Json, prev: &str) -> Json {
    ob(vec![
        ("seq", Json::Int(seq)),
        ("ts", s(ts)),
        ("kind", s(kind)),
        ("label", s(LABEL)),
        ("body", body.clone()),
        ("prev", s(prev)),
    ])
}

/// Append-only hash-chained ledger (HR-43, HR-45, HR-46).
struct Ledger {
    records: Vec<Json>,
    head: String,
}

impl Ledger {
    fn append(&mut self, kind: &str, ts: &str, body: &Json) -> Result<()> {
        let mut rec = record(self.records.len() as i64, ts, kind, body, &self.head);
        let hash = sha256_hex(canonical(&rec)?.as_bytes());
        set_key(&mut rec, "hash", s(hash.clone()));
        self.records.push(sorted(&rec));
        self.head = hash;
        Ok(())
    }
}

fn no_nonfinite(v: &Json) -> Result<()> {
    match v {
        Json::Obj(m) => m.iter().try_for_each(|(_, x)| no_nonfinite(x)),
        Json::Arr(a) => a.iter().try_for_each(no_nonfinite),
        // the CLI hands the F-1 tokens over as binary64 values
        Json::Num(x) if !x.is_finite() => {
            Err(e("E_SCHEMA", "a body value is not a finite decimal"))
        }
        Json::Str(t) if NONFINITE.contains(&t.as_str()) => {
            Err(e("E_SCHEMA", "a body value is not a finite decimal"))
        }
        _ => Ok(()),
    }
}

/// `paper.ledger.append` for one record: canonical bytes, hash and the full record.
pub fn ledger_append(seq: i64, ts: &str, kind: &str, body: &Json, prev: &str) -> Result<Json> {
    if !KINDS.contains(&kind) {
        return Err(e("E_INPUT", format!("unknown kind {kind:?}")));
    }
    if seq < 0 {
        return Err(e("E_DOMAIN", "seq must be >= 0"));
    }
    no_nonfinite(body)?;
    let mut rec = record(seq, ts, kind, body, prev);
    let raw = canonical(&rec)?;
    let hash = sha256_hex(raw.as_bytes());
    set_key(&mut rec, "hash", s(hash.clone()));
    Ok(ob(vec![
        ("canonical_bytes", s(raw)),
        ("hash", s(hash)),
        ("record", rec),
        ("label", s(LABEL)),
    ]))
}

/// Python `str.splitlines`.
fn split_lines(t: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut start = 0;
    let mut it = t.char_indices().peekable();
    while let Some((k, c)) = it.next() {
        let sep = matches!(
            c,
            '\n' | '\r'
                | '\u{b}'
                | '\u{c}'
                | '\u{1c}'
                | '\u{1d}'
                | '\u{1e}'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        );
        if sep {
            out.push(&t[start..k]);
            let mut end = k + c.len_utf8();
            if c == '\r' && it.peek().is_some_and(|(_, n)| *n == '\n') {
                it.next();
                end += 1;
            }
            start = end;
        }
    }
    if start < t.len() {
        out.push(&t[start..]);
    }
    out
}

/// `paper.ledger.verify`: never repairs; reports the first bad record.
pub fn ledger_verify(text: &str) -> Json {
    let lines = split_lines(text);
    let mut prev = GENESIS.to_string();
    for (n, line) in lines.iter().enumerate() {
        let bad = |reason: &str| {
            ob(vec![
                ("ok", Json::Bool(false)),
                ("records", Json::Int(n as i64)),
                ("first_bad_seq", Json::Int(n as i64)),
                ("reason", s(reason)),
                ("head", Json::Null),
                ("label", s(LABEL)),
            ])
        };
        let Ok((rec, _)) = crate::json::parse(line) else {
            return bad("PARSE");
        };
        if !matches!(rec, Json::Obj(_)) {
            return bad("PARSE");
        }
        let Some(stored) = rec.get("hash") else {
            return bad("PARSE");
        };
        let Ok(raw) = canonical(&rec) else {
            return bad("PARSE");
        };
        if rec.get("seq") != Some(&Json::Int(n as i64)) {
            return bad("SEQ");
        }
        let computed = sha256_hex(raw.as_bytes());
        if stored.as_str() != Some(computed.as_str()) {
            return bad("HASH");
        }
        if rec.get("prev").and_then(Json::as_str) != Some(prev.as_str()) {
            return bad("LINK");
        }
        if rec.get("label").and_then(Json::as_str) != Some(LABEL) {
            return bad("LABEL");
        }
        prev = computed;
    }
    ob(vec![
        ("ok", Json::Bool(true)),
        ("records", Json::Int(lines.len() as i64)),
        ("first_bad_seq", Json::Null),
        ("reason", Json::Null),
        ("head", s(prev)),
        ("label", s(LABEL)),
    ])
}

// ---------------------------------------------------------------- book (HR-50, HR-52, HR-53)

#[derive(Clone)]
struct Pos {
    n: PyDec,
    c: PyDec,
}

struct Book {
    cash: PyDec,
    positions: Vec<(String, Pos)>,
    realised: PyDec,
    fees: PyDec,
}

/// A fill as the ledger body holds it (decimal values already through `fmt`).
#[derive(Clone)]
struct DayFill {
    symbol: String,
    sign: i64,
    quantity: PyDec,
    price: PyDec,
    fee: PyDec,
}

impl Book {
    fn new(cash: PyDec) -> Book {
        Book {
            cash,
            positions: Vec::new(),
            realised: PyDec::zero(),
            fees: PyDec::zero(),
        }
    }

    fn pos(&mut self, sym: &str) -> &mut Pos {
        let k = if let Some(k) = self.positions.iter().position(|(n, _)| n == sym) {
            k
        } else {
            {
                self.positions.push((
                    sym.to_string(),
                    Pos {
                        n: PyDec::zero(),
                        c: PyDec::zero(),
                    },
                ));
                self.positions.len() - 1
            }
        };
        &mut self.positions[k].1
    }

    /// `paper.book.apply_fill`, average cost (HR-50).
    fn apply_fill(&mut self, sym: &str, sg: i64, q: &PyDec, p: &PyDec, f: &PyDec) -> Result<()> {
        if !q.is_pos() || !p.is_pos() {
            return Err(e("E_DOMAIN", "quantity and price must be positive"));
        }
        self.cash = self.cash.sub(&i(sg).mul(q).mul(p).add(f));
        self.fees = self.fees.add(f);
        let pos = self.pos(sym).clone();
        let mut realised = None;
        let np = if pos.n.is_zero() || pos.n.is_pos() == (sg > 0) {
            let an = pos.n.abs();
            Pos {
                c: an.mul(&pos.c).add(&q.mul(p)).div(&an.add(q))?,
                n: pos.n.add(&i(sg).mul(q)),
            }
        } else {
            let an = pos.n.abs();
            let closed = if an < *q { an } else { q.clone() };
            let sign = if pos.n.is_pos() { 1 } else { -1 };
            realised = Some(closed.mul(&p.sub(&pos.c)).mul(&i(sign)));
            let n = pos.n.add(&i(sg).mul(q));
            let c = if n.is_zero() {
                PyDec::zero()
            } else if n.is_pos() != (sign > 0) {
                p.clone()
            } else {
                pos.c.clone()
            };
            Pos { n, c }
        };
        if let Some(r) = realised {
            self.realised = self.realised.add(&r);
        }
        *self.pos(sym) = np;
        Ok(())
    }

    fn nav(&self, marks: &Json) -> Result<PyDec> {
        let mut t = PyDec::zero();
        for (sym, p) in &self.positions {
            if !p.n.is_zero() {
                t = t.add(&p.n.mul(&dec(mark(marks, sym)?, "marks")?));
            }
        }
        Ok(self.cash.add(&t))
    }
}

fn mark<'a>(marks: &'a Json, sym: &str) -> Result<&'a Json> {
    marks
        .get(sym)
        .ok_or_else(|| e("E_SCHEMA", format!("no mark for {sym}")))
}

struct Eod {
    market: PyDec,
    trading: PyDec,
    fees: PyDec,
    financing: PyDec,
    interest: PyDec,
    borrow: PyDec,
    total: PyDec,
    nav: PyDec,
}

/// `paper.book.end_of_day` with `paper.pnl.explain` (HR-51 to HR-53).
fn end_of_day(
    book: &mut Book,
    fills: &[DayFill],
    prev_marks: &Json,
    marks: &Json,
    days: i64,
    rates: [&Json; 3],
) -> Result<Eod> {
    let opening: Vec<(String, PyDec)> = book
        .positions
        .iter()
        .filter(|(_, p)| !p.n.is_zero())
        .map(|(k, p)| (k.clone(), p.n.clone()))
        .collect();
    let nav0 = if opening.is_empty() {
        book.cash.clone()
    } else {
        book.nav(prev_marks)?
    };
    // financing on the opening balances, ACT/365 (HR-52)
    if days < 0 {
        return Err(e("E_DOMAIN", "days must be >= 0"));
    }
    let cash = book.cash.clone();
    let r = if cash.is_neg() {
        dec(rates[1], "debit_rate")?
    } else {
        dec(rates[0], "cash_rate")?
    };
    let d365 = |x: PyDec| x.mul(&i(days)).div(&i(365));
    let interest = d365(cash.mul(&r))?.quantize(-2);
    let mut smv = PyDec::zero();
    for (sym, n) in &opening {
        let px = dec(mark(prev_marks, sym)?, "close")?;
        if n.is_neg() {
            smv = smv.add(&n.neg().mul(&px));
        }
    }
    let borrow = d365(smv.mul(&dec(rates[2], "borrow_rate")?))?
        .quantize(-2)
        .neg();
    let financing = interest.add(&borrow);
    let mut market = PyDec::zero();
    for (sym, n) in &opening {
        let m1 = dec(mark(marks, sym)?, "mark")?;
        let m0 = dec(mark(prev_marks, sym)?, "prev_mark")?;
        market = market.add(&n.mul(&m1.sub(&m0)));
    }
    let (mut trading, mut fees) = (PyDec::zero(), PyDec::zero());
    for f in fills {
        let m = dec(mark(marks, &f.symbol)?, "mark")?;
        trading = trading.add(&i(f.sign).mul(&f.quantity).mul(&m.sub(&f.price)));
        fees = fees.sub(&f.fee);
        book.apply_fill(&f.symbol, f.sign, &f.quantity, &f.price, &f.fee)?;
    }
    book.cash = book.cash.add(&financing);
    let total = market.add(&trading).add(&fees).add(&financing);
    let nav = book.nav(marks)?;
    if total != nav.sub(&nav0) {
        return Err(e("E_INPUT", "explain residual (HR-53)"));
    }
    Ok(Eod {
        market,
        trading,
        fees,
        financing,
        interest,
        borrow,
        total,
        nav,
    })
}

// ---------------------------------------------------------------- pre-trade (HR-42, HR-49)

fn limit_int(v: &Json) -> Result<i64> {
    match v {
        Json::Int(n) => Ok(*n),
        Json::Str(t) => t
            .trim()
            .parse()
            .map_err(|_| e("E_SCHEMA", "max_orders_per_day is not an integer")),
        _ => Err(e("E_SCHEMA", "max_orders_per_day is not an integer")),
    }
}

/// `paper.pretrade.check`: deterministic; every check runs; reasons in the HR-49 order.
fn pretrade_check(
    order: &Json,
    p_ref: &PyDec,
    position: &PyDec,
    cash: &PyDec,
    orders_today: i64,
    limits: &Json,
) -> Result<Vec<&'static str>> {
    if let Some(m) = order.get("mode")
        && m.as_str() != Some("simulated")
    {
        return Err(e(
            "E_UNSUPPORTED_OPERATION",
            "paper trading never places live orders (HR-42)",
        ));
    }
    let sg = side_sign(order.get("side").unwrap_or(&Json::Null))?;
    let otype = order.get("type").and_then(Json::as_str).unwrap_or("");
    if !TYPES.contains(&otype) {
        return Err(e("E_INPUT", "unknown type"));
    }
    let q = dec(req(order, "quantity", "order/")?, "quantity")?;
    let lim = |k: &str| {
        limits
            .get(k)
            .ok_or_else(|| e("E_SCHEMA", format!("limits/{k} is missing")))
    };
    let band = dec(lim("price_band")?, "price_band")?;
    if !q.is_pos() || !p_ref.is_pos() {
        return Err(e(
            "E_DOMAIN",
            "quantity and reference price must be positive",
        ));
    }
    let (limit, p_chk) = if otype == "MARKET" {
        (None, p_ref.mul(&i(1).add(&i(sg).mul(&band))))
    } else {
        let l = order
            .get("limit_price")
            .ok_or_else(|| e("E_SCHEMA", "limit_price is missing"))?;
        let l = dec(l, "limit_price")?;
        if !l.is_pos() {
            return Err(e("E_DOMAIN", "limit price must be positive"));
        }
        (Some(l.clone()), l)
    };
    let after = position.add(&i(sg).mul(&q));
    let mut out = Vec::new();
    if truthy(limits.get("kill_switch"), false) {
        out.push("KILL_SWITCH");
    }
    if orders_today >= limit_int(lim("max_orders_per_day")?)? {
        out.push("MAX_ORDERS");
    }
    if q > dec(lim("max_order_qty")?, "max_order_qty")? {
        out.push("MAX_QTY");
    }
    if let Some(l) = &limit
        && l.sub(p_ref).abs().div(p_ref)? > band
    {
        out.push("PRICE_BAND");
    }
    let notional = q.mul(&p_chk);
    if notional > dec(lim("max_notional")?, "max_notional")? {
        out.push("MAX_NOTIONAL");
    }
    if after.abs() > dec(lim("max_abs_position")?, "max_abs_position")? {
        out.push("MAX_POSITION");
    }
    if !truthy(limits.get("allow_short"), true) && after.is_neg() {
        out.push("NO_SHORT");
    }
    if sg > 0 && notional > *cash {
        out.push("INSUFFICIENT_CASH");
    }
    Ok(out)
}

// ---------------------------------------------------------------- CLI cases (one symbol)

fn fill_list(fills: &[Json]) -> Result<Vec<DayFill>> {
    let mut out = Vec::new();
    for (k, f) in fills.iter().enumerate() {
        let w = format!("fills/{k}/");
        if !matches!(f, Json::Obj(_)) {
            return Err(e("E_SCHEMA", format!("{w} is not an object")));
        }
        let sign = side_sign(req(f, "side", &w)?)?;
        let q = dstr(req(f, "quantity", &w)?, "quantity")?;
        let p = dstr(req(f, "price", &w)?, "price")?;
        let zero = s("0");
        let fee = dstr(f.get("fee").unwrap_or(&zero), "fee")?;
        if !q.is_pos() || !p.is_pos() {
            return Err(e("E_DOMAIN", "quantity and price must be positive"));
        }
        out.push(DayFill {
            symbol: SYM.into(),
            sign,
            quantity: q.plus(),
            price: p.plus(),
            fee: fee.plus(),
        });
    }
    Ok(out)
}

/// `paper.book.apply_fill`: fills in order on one symbol; `cash_delta` when no `cash` is given.
pub fn book_case(fills: &[Json], cash: Option<&Json>, position: &Json, avg: &Json) -> Result<Json> {
    let start = match cash {
        Some(c) => dstr(c, "cash")?,
        None => PyDec::zero(),
    };
    let mut book = Book::new(start);
    let (n, c) = (dstr(position, "position")?, dstr(avg, "avg_cost")?);
    *book.pos(SYM) = Pos { n, c };
    for f in fill_list(fills)? {
        book.apply_fill(SYM, f.sign, &f.quantity, &f.price, &f.fee)?;
    }
    let p = book.pos(SYM).clone();
    Ok(ob(vec![
        ("position", s(p.n.fmt())),
        ("avg_cost", s(p.c.fmt())),
        ("realised", s(book.realised.fmt())),
        ("fees", s(book.fees.fmt())),
        ("label", s(LABEL)),
        (
            if cash.is_some() { "cash" } else { "cash_delta" },
            s(book.cash.fmt()),
        ),
    ]))
}

/// The inputs of `paper.book.end_of_day` (one symbol).
pub struct DayInputs<'a> {
    pub cash_open: &'a Json,
    pub fills: &'a [Json],
    pub position_open: &'a Json,
    pub avg_cost_open: Option<&'a Json>,
    pub prev_close: Option<&'a Json>,
    pub close: Option<&'a Json>,
    pub days: i64,
    pub rates: [&'a Json; 3],
}

/// `paper.book.end_of_day` with `paper.pnl.explain` for one symbol (HR-51 to HR-53).
pub fn day_case(d: &DayInputs) -> Result<Json> {
    let cash = dstr(d.cash_open, "cash_open")?;
    let n = dstr(d.position_open, "position_open")?;
    let fl = fill_list(d.fills)?;
    if !n.is_zero() && d.prev_close.is_none() {
        return Err(e("E_SCHEMA", "prev_close is missing (open position)"));
    }
    if (!n.is_zero() || !fl.is_empty()) && d.close.is_none() {
        return Err(e("E_SCHEMA", "close is missing (position or fills)"));
    }
    let prev = d.prev_close.map(|v| dstr(v, "prev_close")).transpose()?;
    let px = d.close.map(|v| dstr(v, "close")).transpose()?;
    for v in [&prev, &px].into_iter().flatten() {
        if !v.is_pos() {
            return Err(e("E_DOMAIN", "prices must be positive"));
        }
    }
    let names = ["cash_rate", "debit_rate", "borrow_rate"];
    let mut rates = Vec::new();
    for (k, r) in d.rates.iter().enumerate() {
        rates.push(s(dstr(r, names[k])?.fmt()));
    }
    let mut book = Book::new(cash.clone());
    let c = match (d.avg_cost_open, &prev) {
        (Some(a), _) => dstr(a, "avg_cost_open")?,
        (None, Some(p)) => p.clone(),
        (None, None) => PyDec::zero(),
    };
    *book.pos(SYM) = Pos { n: n.clone(), c };
    let m = |v: &Option<PyDec>| match v {
        Some(x) => ob(vec![(SYM, s(x.fmt()))]),
        None => Json::Obj(Vec::new()),
    };
    let nav_open = match &prev {
        Some(p) if !n.is_zero() => cash.add(&n.mul(p)),
        _ => cash.add(&PyDec::zero()),
    };
    let x = end_of_day(
        &mut book,
        &fl,
        &m(&prev),
        &m(&px),
        d.days,
        [&rates[0], &rates[1], &rates[2]],
    )?;
    let mut out = ob(vec![
        ("market", s(x.market.fmt())),
        ("trading", s(x.trading.fmt())),
        ("fees", s(x.fees.fmt())),
        ("financing", s(x.financing.fmt())),
        ("cash_interest", s(x.interest.fmt())),
        ("short_borrow", s(x.borrow.fmt())),
        ("total", s(x.total.fmt())),
        ("position", s(book.pos(SYM).n.fmt())),
        ("cash_close", s(book.cash.fmt())),
        ("label", s(LABEL)),
    ]);
    if px.is_some() {
        set_key(&mut out, "nav_open", s(nav_open.fmt()));
        set_key(&mut out, "nav_close", s(x.nav.fmt()));
    }
    Ok(out)
}

/// `paper.pretrade.check` over the CLI: schema first, then HR-42, then the checks.
pub fn pretrade_case(
    order: &Json,
    ref_price: &Json,
    position: &Json,
    cash: &Json,
    orders_today: i64,
    limits: &Json,
) -> Result<Json> {
    for k in ["side", "type", "quantity"] {
        req(order, k, "order/")?;
    }
    dstr(req(order, "quantity", "order/")?, "order/quantity")?;
    if let Some(l) = order.get("limit_price").filter(|v| **v != Json::Null) {
        dstr(l, "order/limit_price")?;
    }
    for k in [
        "max_order_qty",
        "max_notional",
        "max_abs_position",
        "price_band",
    ] {
        dstr(req(limits, k, "limits/")?, k)?;
    }
    if !matches!(req(limits, "max_orders_per_day", "limits/")?, Json::Int(_)) {
        return Err(e(
            "E_SCHEMA",
            "limits/max_orders_per_day must be an integer",
        ));
    }
    for k in ["kill_switch", "allow_short"] {
        if limits.get(k).is_some_and(|v| !matches!(v, Json::Bool(_))) {
            return Err(e("E_SCHEMA", format!("limits/{k} must be a boolean")));
        }
    }
    let p_ref = dstr(ref_price, "ref_price")?;
    let pos = dstr(position, "position")?;
    let c = dstr(cash, "cash")?;
    let r = pretrade_check(order, &p_ref, &pos, &c, orders_today, limits)?;
    Ok(ob(vec![
        ("accepted", Json::Bool(r.is_empty())),
        ("reasons", Json::Arr(r.into_iter().map(s).collect())),
        ("label", s(LABEL)),
    ]))
}

// ---------------------------------------------------------------- session (HR-47, HR-48, HR-55)

const TRADER: &str = "PAPER";

#[derive(Clone)]
struct Fill {
    quantity: PyDec,
    price: PyDec,
    fee: PyDec,
    venue: &'static str,
    child_id: String,
}

struct Open {
    order_id: String,
    symbol: String,
    side: String,
    qty: PyDec,
    decision: PyDec,
    arrival: PyDec,
    fills: Vec<Fill>,
    resting: PyDec,
}

fn level<'a>(snap: &'a Json, side: &str, k: usize) -> Result<(&'a Json, &'a Json)> {
    let lv = snap
        .get(side)
        .and_then(Json::as_array)
        .and_then(|a| a.get(k))
        .and_then(Json::as_array)
        .ok_or_else(|| e("E_SCHEMA", format!("snapshot {side}: bad level")))?;
    match lv {
        [p, q] => Ok((p, q)),
        _ => Err(e(
            "E_SCHEMA",
            format!("snapshot {side}: a level is [price, qty]"),
        )),
    }
}

fn mid(snap: &Json) -> Result<PyDec> {
    let nonempty = |k: &str| truthy(snap.get(k), false);
    if !nonempty("bids") || !nonempty("asks") {
        return Err(e("E_INPUT", "snapshot has an empty side; no mid"));
    }
    let b = dec(level(snap, "bids", 0)?.0, "bid")?;
    let a = dec(level(snap, "asks", 0)?.0, "ask")?;
    b.add(&a).div(&i(2))
}

fn str_of<'a>(v: &'a Json, name: &str) -> Result<&'a str> {
    v.as_str()
        .ok_or_else(|| e("E_SCHEMA", format!("{name} must be a string")))
}

/// Replays one child into the lit engine seeded with the snapshot: (fills, resting quantity).
fn lit_child(
    cfg: &Json,
    snap: &Json,
    cid: &str,
    side: &str,
    otype: &str,
    qty: &PyDec,
    limit: Option<&PyDec>,
) -> Result<(Vec<Fill>, PyDec)> {
    let mut events = Vec::new();
    for (name, bs) in [("asks", "SELL"), ("bids", "BUY")] {
        let n = snap
            .get(name)
            .and_then(Json::as_array)
            .map_or(0, <[Json]>::len);
        for k in 0..n {
            let (p, q) = level(snap, name, k)?;
            events.push(ob(vec![
                ("op", s("NEW")),
                ("id", s(format!("BOOK-{name}-{k}"))),
                ("trader", s("BOOK")),
                ("side", s(bs)),
                ("type", s("LIMIT")),
                ("price", p.clone()),
                ("qty", q.clone()),
            ]));
        }
    }
    let mut ev = ob(vec![
        ("op", s("NEW")),
        ("id", s(cid)),
        ("trader", s(TRADER)),
        ("side", s(side)),
        ("type", s(otype)),
        ("qty", s(qty.fmt())),
    ]);
    if otype != "MARKET" {
        let l = limit.ok_or_else(|| e("E_SCHEMA", "limit_price is missing"))?;
        set_key(&mut ev, "price", s(l.fmt()));
    }
    events.push(ev);
    let fees = req(cfg, "fee_schedule", "lit/")?;
    let out = lit_matching::run(
        str_of(req(cfg, "tick_size", "lit/")?, "tick_size")?,
        str_of(req(cfg, "lot_size", "lit/")?, "lot_size")?,
        &events,
        fees,
    )?;
    let arr = |k: &str| out.get(k).and_then(Json::as_array).unwrap_or(&[]);
    let id_is = |v: &Json, k: &str| v.get(k).and_then(Json::as_str) == Some(cid);
    if arr("rejects").iter().any(|r| id_is(r, "id")) {
        return Ok((Vec::new(), PyDec::zero()));
    }
    let taker = dec(req(fees, "taker_fee", "fee_schedule/")?, "taker_fee")?;
    let rebate = dec(req(fees, "maker_rebate", "fee_schedule/")?, "maker_rebate")?;
    let mut fills = Vec::new();
    for f in arr("fills") {
        if id_is(f, "taker_id") || id_is(f, "maker_id") {
            let q = dec(req(f, "qty", "")?, "qty")?;
            let p = dec(req(f, "price", "")?, "price")?;
            let rate = if id_is(f, "taker_id") {
                taker.clone()
            } else {
                rebate.neg()
            };
            fills.push(Fill {
                fee: rate.mul(&q).mul(&p),
                quantity: q,
                price: p,
                venue: "LIT",
                child_id: cid.into(),
            });
        }
    }
    let rest = out
        .get("conservation")
        .and_then(|c| c.get(cid))
        .and_then(|c| c.get("resting"))
        .ok_or_else(|| e("E_INPUT", "no conservation row for the order"))?;
    Ok((fills, dec(rest, "resting")?))
}

/// Replays one child into the dark pool at the snapshot mid against synthetic contra orders.
fn dark_child(
    cfg: &Json,
    snap: &Json,
    contra: &[Json],
    cid: &str,
    side: &str,
    qty: &PyDec,
    limit: Option<&PyDec>,
) -> Result<(Vec<Fill>, PyDec)> {
    let mut events = vec![ob(vec![
        ("op", s("BOOK")),
        ("bid", level(snap, "bids", 0)?.0.clone()),
        ("ask", level(snap, "asks", 0)?.0.clone()),
    ])];
    for c in contra {
        if !matches!(c, Json::Obj(_)) {
            return Err(e("E_SCHEMA", "contra events are objects"));
        }
        events.push(c.clone());
    }
    let mut ev = ob(vec![
        ("op", s("NEW")),
        ("id", s(cid)),
        ("side", s(side)),
        ("qty", s(qty.fmt())),
        ("kind", s("FIRM")),
    ]);
    if let Some(l) = limit {
        set_key(&mut ev, "limit", s(l.fmt()));
    }
    events.push(ev);
    let out = dark_pool::run(cfg, &events)?;
    let arr = |k: &str| out.get(k).and_then(Json::as_array).unwrap_or(&[]);
    let id_is = |v: &Json, k: &str| v.get(k).and_then(Json::as_str) == Some(cid);
    let mut fills = Vec::new();
    for f in arr("fills") {
        if id_is(f, "buy_id") || id_is(f, "sell_id") {
            fills.push(Fill {
                quantity: dec(req(f, "qty", "")?, "qty")?,
                price: dec(req(f, "price", "")?, "price")?,
                fee: PyDec::zero(),
                venue: "DARK",
                child_id: cid.into(),
            });
        }
    }
    let rest = match arr("resting").iter().find(|r| id_is(r, "id")) {
        Some(r) => dec(req(r, "open_qty", "")?, "q")?,
        None => PyDec::zero(),
    };
    Ok((fills, rest))
}

struct Session<'a> {
    ledger: Ledger,
    book: Book,
    limits: &'a Json,
    lit: &'a Json,
    dark: Option<&'a Json>,
    today: Vec<Open>,
    day_fills: Vec<DayFill>,
    orders_today: i64,
}

fn tca_text(v: f64) -> Result<String> {
    if !v.is_finite() {
        return Err(e("E_DOMAIN", "TCA value is not finite"));
    }
    // Rust `{}` is the shortest round-trip decimal without exponent, as Python `repr` digits.
    Ok(parse_text(&format!("{v}"), "tca")?.fmt())
}

impl Session<'_> {
    fn position(&mut self, sym: &str) -> PyDec {
        let n = self.book.pos(sym).n.clone();
        let mut t = PyDec::zero();
        for f in self.day_fills.iter().filter(|f| f.symbol == sym) {
            t = t.add(&i(f.sign).mul(&f.quantity));
        }
        n.add(&t)
    }

    fn cash(&self) -> PyDec {
        let mut t = PyDec::zero();
        for f in &self.day_fills {
            t = t.add(&i(f.sign).mul(&f.quantity).mul(&f.price).add(&f.fee));
        }
        self.book.cash.sub(&t)
    }

    fn dark_cfg(&self) -> Result<&Json> {
        self.dark
            .ok_or_else(|| e("E_SCHEMA", "dark venue configuration is missing"))
    }

    fn submit(
        &mut self,
        order: &Json,
        ts: &str,
        snap: &Json,
        contra: &[Json],
        router: Option<&Json>,
    ) -> Result<Json> {
        let venue = match order.get("venue") {
            None => "LIT",
            Some(v) => match v.as_str() {
                Some(x @ ("LIT" | "DARK" | "SOR")) => x,
                _ => return Err(e("E_INPUT", "unknown venue")),
            },
        };
        let oid = str_of(
            &order.get("order_id").cloned().unwrap_or(Json::Null),
            "order_id",
        )?
        .to_string();
        if self.today.iter().any(|o| o.order_id == oid) {
            return Err(e("E_INPUT", "duplicate order_id"));
        }
        let p_ref = mid(snap)?;
        let sym = str_of(req(order, "symbol", "order/")?, "symbol")?.to_string();
        let pos = self.position(&sym);
        let cash = self.cash();
        let reasons = pretrade_check(order, &p_ref, &pos, &cash, self.orders_today, self.limits)?;
        self.orders_today += 1;
        let mut body = match order {
            Json::Obj(m) => Json::Obj(m.iter().filter(|(k, _)| k != "mode").cloned().collect()),
            _ => return Err(e("E_SCHEMA", "order is an object")),
        };
        if !reasons.is_empty() {
            let r = Json::Arr(reasons.iter().map(|x| s(*x)).collect());
            set_key(&mut body, "reasons", r.clone());
            self.ledger.append("REJECT", ts, &body)?;
            return Ok(ob(vec![("status", s("REJECTED")), ("reasons", r)]));
        }
        set_key(&mut body, "decision_price", s(p_ref.fmt()));
        self.ledger.append("ORDER", ts, &body)?;
        let side = str_of(req(order, "side", "order/")?, "side")?.to_string();
        let otype = str_of(req(order, "type", "order/")?, "type")?.to_string();
        let qty = dec(req(order, "quantity", "order/")?, "quantity")?;
        let limit = if otype == "MARKET" {
            None
        } else {
            let l = order
                .get("limit_price")
                .ok_or_else(|| e("E_SCHEMA", "limit_price is missing"))?;
            Some(dec(l, "limit_price")?)
        };
        let arrival = mid(snap)?;
        let (fills, resting) = match venue {
            "LIT" => lit_child(self.lit, snap, &oid, &side, &otype, &qty, limit.as_ref())?,
            "DARK" => dark_child(
                self.dark_cfg()?,
                snap,
                contra,
                &oid,
                &side,
                &qty,
                limit.as_ref(),
            )?,
            _ => (
                self.route(&oid, &side, snap, contra, router, &qty, limit.as_ref())?,
                PyDec::zero(),
            ),
        };
        for f in &fills {
            let fb = ob(vec![
                ("order_id", s(oid.clone())),
                ("child_id", s(f.child_id.clone())),
                ("venue", s(f.venue)),
                ("symbol", s(sym.clone())),
                ("side", s(side.clone())),
                ("quantity", s(f.quantity.fmt())),
                ("price", s(f.price.fmt())),
                ("fee", s(f.fee.fmt())),
            ]);
            self.ledger.append("FILL", ts, &fb)?;
            self.day_fills.push(DayFill {
                symbol: sym.clone(),
                sign: if side == "BUY" { 1 } else { -1 },
                quantity: f.quantity.plus(),
                price: f.price.plus(),
                fee: f.fee.plus(),
            });
        }
        let mut filled = PyDec::zero();
        for f in &fills {
            filled = filled.add(&f.quantity);
        }
        if resting.is_zero() && filled < qty {
            let body = ob(vec![
                ("order_id", s(oid.clone())),
                ("quantity", s(qty.sub(&filled).fmt())),
            ]);
            self.ledger.append("CANCEL", ts, &body)?;
        }
        let open = !resting.is_zero();
        self.today.push(Open {
            order_id: oid,
            symbol: sym,
            side,
            qty,
            decision: p_ref,
            arrival,
            fills,
            resting,
        });
        Ok(ob(vec![
            ("status", s(if open { "OPEN" } else { "DONE" })),
            ("filled", s(filled.fmt())),
        ]))
    }

    #[allow(clippy::too_many_arguments)]
    fn route(
        &self,
        oid: &str,
        side: &str,
        snap: &Json,
        contra: &[Json],
        router: Option<&Json>,
        qty: &PyDec,
        limit: Option<&PyDec>,
    ) -> Result<Vec<Fill>> {
        let router = router.ok_or_else(|| e("E_SCHEMA", "SOR order needs the router input"))?;
        let mut inp = match router {
            Json::Obj(_) => router.clone(),
            _ => return Err(e("E_SCHEMA", "router is an object")),
        };
        set_key(&mut inp, "S", s(qty.fmt()));
        let alloc = sor::allocate(&inp)?;
        let best = level(snap, if side == "BUY" { "bids" } else { "asks" }, 0)?.0;
        let mut children = vec![(
            "M".to_string(),
            "MARKET".to_string(),
            dec(req(&alloc, "M", "")?, "M")?,
        )];
        let venues = router.get("venues").and_then(Json::as_array).unwrap_or(&[]);
        let ls = alloc.get("L").and_then(Json::as_array).unwrap_or(&[]);
        if venues.len() != ls.len() {
            return Err(e(
                "E_INPUT",
                "router venues and allocation differ in length",
            ));
        }
        for (k, (v, lk)) in venues.iter().zip(ls).enumerate() {
            let kind = v
                .get("kind")
                .and_then(Json::as_str)
                .unwrap_or("")
                .to_string();
            children.push((format!("L{k}"), kind, dec(lk, "L")?));
        }
        let mut fills: Vec<Fill> = Vec::new();
        for (name, kind, q) in children {
            if q.is_zero() {
                continue;
            }
            let cid = format!("{oid}.{name}");
            let (got, _) = match kind.as_str() {
                "MARKET" => lit_child(self.lit, snap, &cid, side, "MARKET", &q, None)?,
                "LIT" => {
                    let b = dec(best, "best")?;
                    lit_child(self.lit, snap, &cid, side, "LIMIT", &q, Some(&b))?
                }
                _ => dark_child(self.dark_cfg()?, snap, contra, &cid, side, &q, limit)?,
            };
            for g in got {
                // the parent never overfills
                let mut done = PyDec::zero();
                for x in &fills {
                    done = done.add(&x.quantity);
                }
                let room = qty.sub(&done);
                if !room.is_pos() {
                    break;
                }
                let g = if g.quantity > room {
                    Fill {
                        fee: g.fee.mul(&room).div(&g.quantity)?,
                        quantity: room,
                        ..g
                    }
                } else {
                    g
                };
                fills.push(g);
            }
        }
        Ok(fills)
    }

    /// Cancels resting remainders (HR-48), writes one TCA per order, then the EOD record.
    fn close_day(
        &mut self,
        ts: &str,
        prev_marks: &Json,
        marks: &Json,
        days: i64,
        rates: [&Json; 3],
    ) -> Result<Json> {
        let today = std::mem::take(&mut self.today);
        for rec in &today {
            let mut filled = PyDec::zero();
            let mut fees = PyDec::zero();
            for f in &rec.fills {
                filled = filled.add(&f.quantity);
                fees = fees.add(&f.fee);
            }
            if !rec.resting.is_zero() {
                let body = ob(vec![
                    ("order_id", s(rec.order_id.clone())),
                    ("quantity", s(rec.qty.sub(&filled).fmt())),
                ]);
                self.ledger.append("CANCEL", ts, &body)?;
            }
            let end = dec(mark(marks, &rec.symbol)?, "close")?;
            let t = tca_shortfall(&TcaOrder {
                buy: rec.side == "BUY",
                decision_price: rec.decision.to_f64(),
                arrival_price: rec.arrival.to_f64(),
                end_price: end.to_f64(),
                order_quantity: rec.qty.to_f64(),
                fills: rec
                    .fills
                    .iter()
                    .map(|f| (f.quantity.to_f64(), f.price.to_f64()))
                    .collect(),
                fees: fees.to_f64(),
                benchmark_vwap: None,
            })?;
            let body = ob(vec![
                ("order_id", s(rec.order_id.clone())),
                ("delay", s(tca_text(t.delay)?)),
                ("execution", s(tca_text(t.execution)?)),
                ("opportunity", s(tca_text(t.opportunity)?)),
                ("total", s(tca_text(t.total)?)),
                ("total_bps", s(tca_text(t.total_bps)?)),
            ]);
            self.ledger.append("TCA", ts, &body)?;
        }
        let fills = std::mem::take(&mut self.day_fills);
        let x = end_of_day(&mut self.book, &fills, prev_marks, marks, days, rates)?;
        let eod = ob(vec![
            ("market", s(x.market.fmt())),
            ("trading", s(x.trading.fmt())),
            ("fees", s(x.fees.fmt())),
            ("financing", s(x.financing.fmt())),
            ("interest", s(x.interest.fmt())),
            ("borrow", s(x.borrow.fmt())),
            ("total", s(x.total.fmt())),
            ("nav", s(x.nav.fmt())),
            ("label", s(LABEL)),
            ("ceiling", s(CEILING)),
        ]);
        self.ledger.append("EOD", ts, &eod)?;
        self.orders_today = 0;
        Ok(eod)
    }
}

fn obj_or_empty(v: Option<&Json>, name: &str) -> Result<Json> {
    match v {
        None | Some(Json::Null) => Ok(Json::Obj(Vec::new())),
        Some(o @ Json::Obj(_)) => Ok(o.clone()),
        Some(_) => Err(e("E_SCHEMA", format!("{name} must be an object"))),
    }
}

/// `paper.session.run`: replays SUBMIT and CLOSE steps through one paper account and returns
/// every ledger record with its hash, the head, positions and cash. Simulated only (HR-42).
pub fn session_case(
    cash: &Json,
    limits: &Json,
    lit: &Json,
    script: &[Json],
    dark: Option<&Json>,
) -> Result<Json> {
    if !matches!(cash, Json::Str(_)) {
        return Err(e("E_SCHEMA", "cash must be a decimal string"));
    }
    for k in ["tick_size", "lot_size", "fee_schedule"] {
        req(lit, k, "lit/")?;
    }
    let mut ss = Session {
        ledger: Ledger {
            records: Vec::new(),
            head: GENESIS.into(),
        },
        book: Book::new(dec(cash, "cash")?),
        limits,
        lit,
        dark,
        today: Vec::new(),
        day_fills: Vec::new(),
        orders_today: 0,
    };
    let mut results = Vec::new();
    let mut symbols = BTreeSet::new();
    for (k, step) in script.iter().enumerate() {
        let w = format!("script/{k}/");
        let op = step.get("op").and_then(Json::as_str);
        if !matches!(step, Json::Obj(_)) || !matches!(op, Some("SUBMIT" | "CLOSE")) {
            return Err(e("E_SCHEMA", format!("{w}op must be SUBMIT or CLOSE")));
        }
        let ts = step
            .get("ts")
            .and_then(Json::as_str)
            .ok_or_else(|| e("E_SCHEMA", format!("{w}ts is missing")))?;
        if op == Some("SUBMIT") {
            let (order, snap) = (step.get("order"), step.get("snapshot"));
            let (Some(order @ Json::Obj(_)), Some(snap @ Json::Obj(_))) = (order, snap) else {
                return Err(e("E_SCHEMA", format!("{w}order and snapshot are required")));
            };
            for key in ["order_id", "symbol", "side", "type", "quantity"] {
                req(order, key, &format!("{w}order/"))?;
            }
            symbols.insert(str_of(req(order, "symbol", "")?, "symbol")?.to_string());
            let contra = match step.get("contra") {
                Some(Json::Arr(a)) => a.as_slice(),
                None | Some(Json::Null) => &[],
                Some(_) => return Err(e("E_SCHEMA", format!("{w}contra must be an array"))),
            };
            let router = step.get("router").filter(|r| **r != Json::Null);
            results.push(ss.submit(order, ts, snap, contra, router)?);
        } else {
            let days = match step.get("days") {
                None => 1,
                Some(Json::Int(n)) => *n,
                Some(_) => return Err(e("E_SCHEMA", format!("{w}days must be an integer"))),
            };
            let zero = s("0");
            let r = |k: &str| step.get(k).unwrap_or(&zero);
            let pm = obj_or_empty(step.get("prev_marks"), "prev_marks")?;
            let mk = obj_or_empty(step.get("marks"), "marks")?;
            let eod = ss.close_day(
                ts,
                &pm,
                &mk,
                days,
                [r("cash_rate"), r("debit_rate"), r("borrow_rate")],
            )?;
            results.push(ob(vec![("status", s("CLOSED")), ("eod", eod)]));
        }
    }
    let mut positions = Vec::new();
    for sym in &symbols {
        positions.push((sym.clone(), s(ss.position(sym).fmt())));
    }
    Ok(ob(vec![
        ("results", Json::Arr(results)),
        ("records", Json::Arr(ss.ledger.records.clone())),
        ("head", s(ss.ledger.head.clone())),
        ("positions", Json::Obj(positions)),
        ("cash", s(ss.cash().fmt())),
        ("label", s(LABEL)),
        ("ceiling", s(CEILING)),
    ]))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::json::parse;

    fn j(t: &str) -> Json {
        parse(t).expect("json").0
    }

    #[test]
    fn pt_h_0020_canonical_bytes_and_hash() {
        let body = j(
            r#"{"order_id":"O1","symbol":"BTC-USD","side":"BUY","type":"LIMIT","quantity":"3","limit_price":"101"}"#,
        );
        let out = ledger_append(0, "2026-11-18T00:00:01Z", "ORDER", &body, GENESIS).expect("ok");
        assert_eq!(
            out.get("hash").and_then(Json::as_str),
            Some("72c85984abb1b7c4072c65dbba0567b3de51279645b0ad63cfd242137aed7e81")
        );
    }

    #[test]
    fn escapes_as_python_ensure_ascii() {
        let mut o = String::new();
        write_str("a\"\\/\n\u{1}\u{7f}é😀", &mut o);
        let b = '\\';
        let want = format!("\"a{b}\"{b}{b}/{b}n{b}u0001{b}u007f{b}u00e9{b}ud83d{b}ude00\"");
        assert_eq!(o, want);
        assert!(canonical(&j(r#"{"seq":0,"body":{"x":1}}"#)).is_err_and(|e| e.code == "E_INPUT"));
        assert!(canonical(&j(r#"{"seq":0,"body":{"x":true}}"#)).is_err());
    }

    #[test]
    fn live_mode_is_unsupported_hr42() {
        let order =
            j(r#"{"side":"BUY","type":"LIMIT","quantity":"3","limit_price":"101","mode":"live"}"#);
        let limits = j(
            r#"{"max_order_qty":"10","max_notional":"1000","max_abs_position":"5","price_band":"0.05","max_orders_per_day":3}"#,
        );
        let r = pretrade_case(&order, &s("100"), &s("0"), &s("10000"), 0, &limits);
        assert!(r.is_err_and(|e| e.code == "E_UNSUPPORTED_OPERATION"));
    }

    #[test]
    fn verify_splits_like_python() {
        assert_eq!(split_lines("a\r\nb\rc\n"), vec!["a", "b", "c"]);
        assert_eq!(split_lines("\n"), vec![""]);
        let v = ledger_verify("");
        assert_eq!(v.get("head").and_then(Json::as_str), Some(GENESIS));
        let bad = ledger_verify("{\"seq\":0}\n");
        assert_eq!(bad.get("reason").and_then(Json::as_str), Some("PARSE"));
    }

    #[test]
    fn tca_text_has_no_exponent() {
        assert_eq!(tca_text(1e-5).expect("f"), "0.00001");
        assert_eq!(tca_text(-0.0).expect("f"), "0");
        assert_eq!(tca_text(1.5e16).expect("f"), "15000000000000000");
        assert_eq!(tca_text(0.1 + 0.2).expect("f"), "0.30000000000000004");
    }
}
