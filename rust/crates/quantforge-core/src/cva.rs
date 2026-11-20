//! CVA risk capital: BA-CVA, reduced and full, and SA-CVA (plan item K-8g, `cva-capital.md`).
//!
//! A port of `python/quantforge_core/cva.py`, rulings KR-50, KR-62 to KR-64, KR-67 to KR-69 and
//! KR-311 to KR-318 (`specifications/stage-k-rulings-w2.md`). Every parameter is read from
//! `specifications/tables/stage_k/mar50_cva.json`, embedded at build time; nothing is typed here.
//! Sums follow the reference: `math.fsum` is [`fsum`], Python's built-in `sum` of floats (Neumaier
//! compensated since Python 3.12) is [`py_sum`]. SA-CVA uses the FRTB SA bucket and cross
//! radicands in the reference's order (`frtb.bucket_radicand`, `frtb.cross_radicand`).
//!
//! Error order (KR-67): `E_SCHEMA` (unlisted enums), structural `E_INPUT` over the whole input, then
//! `E_DOMAIN`. The finite rule is applied by the CLI before any of these.
#![allow(clippy::neg_cmp_op_on_partial_ord)] // NaN-safe domain checks, as the spec writes them
use crate::error::{QfError, Result};
use crate::json::{Json, parse};
use crate::research_w3::fsum;
use std::collections::HashSet;
use std::sync::OnceLock;

/// KR-69.
pub const LABEL: &str = "regulatory formula on caller inputs; not a regulatory return";

const MAR50_TEXT: &str = include_str!("../../../../specifications/tables/stage_k/mar50_cva.json");

/// The `entries` of a stage K table file, key to value, in file order.
pub(crate) struct Table(Vec<(String, Json)>);

impl Table {
    pub(crate) fn parse(text: &str) -> Table {
        let (doc, _) = parse(text).expect("embedded stage K table is valid JSON");
        let entries = doc
            .get("entries")
            .and_then(Json::as_array)
            .expect("table has entries");
        Table(
            entries
                .iter()
                .map(|e| {
                    let key = e.get("key").and_then(Json::as_str).expect("entry key");
                    let value = e.get("value").expect("entry value").clone();
                    (key.to_string(), value)
                })
                .collect(),
        )
    }

    pub(crate) fn get(&self, key: &str) -> &Json {
        &self
            .0
            .iter()
            .find(|(k, _)| k == key)
            .unwrap_or_else(|| panic!("table key {key} present"))
            .1
    }

    pub(crate) fn num(&self, key: &str) -> f64 {
        dec(self.get(key))
    }
}

/// A table cell: a decimal string, read by its leading number (`"0.90 legally related"`), or a
/// JSON number.
pub(crate) fn dec(v: &Json) -> f64 {
    match v {
        Json::Str(s) => s
            .split_whitespace()
            .next()
            .and_then(|t| t.parse().ok())
            .expect("table cell is a decimal"),
        other => other.as_f64().expect("table cell is a number"),
    }
}

/// The member `k` of a table object.
pub(crate) fn at<'a>(v: &'a Json, k: &str) -> &'a Json {
    v.get(k)
        .unwrap_or_else(|| panic!("table member {k} present"))
}

fn idx(v: &Json, i: usize) -> &Json {
    &v.as_array().expect("table array")[i]
}

fn strings(v: &Json) -> Vec<String> {
    v.as_array()
        .expect("table array")
        .iter()
        .map(|s| s.as_str().expect("table string").to_string())
        .collect()
}

fn keys(v: &Json) -> Vec<String> {
    match v {
        Json::Obj(o) => o.iter().map(|(k, _)| k.clone()).collect(),
        _ => panic!("table object expected"),
    }
}

fn mar50() -> &'static Table {
    static T: OnceLock<Table> = OnceLock::new();
    T.get_or_init(|| Table::parse(MAR50_TEXT))
}

/// Python's built-in `sum` of floats (CPython 3.12 and later): Neumaier compensated, the
/// compensation added once at the end when it is finite and nonzero.
pub fn py_sum(v: impl IntoIterator<Item = f64>) -> f64 {
    let (mut s, mut c) = (0.0_f64, 0.0_f64);
    for x in v {
        let t = s + x;
        if s.abs() >= x.abs() {
            c += (s - t) + x;
        } else {
            c += (x - t) + s;
        }
        s = t;
    }
    if c != 0.0 && c.is_finite() {
        s += c;
    }
    s
}

pub(crate) fn qerr(code: &'static str, message: impl Into<String>, field: &str) -> QfError {
    QfError {
        code,
        message: message.into(),
        field: Some(field.to_string()),
    }
}

// --- BA-CVA ---------------------------------------------------------------------------------------

/// MAR50.16 Table 1 columns, in that order.
pub const QUALITIES: [&str; 2] = ["IG", "HY_NR"];
pub const VERSIONS: [&str; 2] = ["REDUCED", "FULL"];
/// MAR50.26 Table 2: input names (KR-64) and their table keys.
pub const RELATIONS: [(&str, &str); 3] = [
    ("DIRECT", "direct"),
    ("LEGAL", "legally_related"),
    ("SECTOR_REGION", "same_sector_region"),
];
/// The relation input names.
pub const RELATION_NAMES: [&str; 3] = ["DIRECT", "LEGAL", "SECTOR_REGION"];
const WEIGHT_TOLERANCE: f64 = 1e-12; // index weights sum to 1 (cva-capital.md, Errors)

/// The MAR50.16 sectors, in table order.
pub fn sectors() -> Vec<String> {
    keys(mar50().get("ba.rw"))
}

fn rw(sector: &str, quality: &str) -> f64 {
    let q = QUALITIES.iter().position(|x| *x == quality).unwrap_or(0);
    dec(idx(at(mar50().get("ba.rw"), sector), q))
}

#[derive(Debug, Clone, PartialEq)]
pub struct NettingSet {
    pub ead: f64,
    pub m: f64,
    pub imm: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Counterparty {
    pub id: String,
    pub sector: String,
    pub quality: String,
    pub netting_sets: Vec<NettingSet>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SingleNameHedge {
    pub counterparty: String,
    pub relation: String,
    pub sector: String,
    pub quality: String,
    pub m: f64,
    pub notional: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Constituent {
    pub sector: String,
    pub quality: String,
    pub weight: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct IndexHedge {
    pub m: f64,
    pub notional: f64,
    pub constituents: Vec<Constituent>,
}

/// One counterparty row of the BA-CVA output.
#[derive(Debug, Clone, PartialEq)]
pub struct BaRow {
    pub id: String,
    pub scva: f64,
    pub snh: Option<f64>,
    pub hma: Option<f64>,
    pub dfs: Vec<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BaResult {
    pub version: String,
    pub counterparties: Vec<BaRow>,
    pub ih: Option<f64>,
    pub k_reduced: f64,
    pub k_hedged: Option<f64>,
    pub k_full: Option<f64>,
    pub capital: f64,
    pub rwa: f64,
}

/// MAR50.15(4): 1 for IMM, else the average discount factor at 5% to M (footnote 357), computed
/// as `-expm1(-0.05 M) / (0.05 M)` (KR-64).
pub fn discount_factor(m: f64, imm: bool) -> Result<f64> {
    if !(m > 0.0) {
        return Err(qerr("E_DOMAIN", "m must be positive", "m"));
    }
    if imm {
        return Ok(1.0);
    }
    let x = mar50().num("ba.df_rate") * m;
    Ok(-(-x).exp_m1() / x)
}

fn listed(v: &str, allowed: &[String], what: &str) -> Result<()> {
    if allowed.iter().any(|a| a == v) {
        Ok(())
    } else {
        Err(qerr("E_SCHEMA", format!("{what} {v} is not listed"), what))
    }
}

fn quality_listed(q: &str) -> Result<()> {
    if QUALITIES.contains(&q) {
        Ok(())
    } else {
        Err(qerr("E_SCHEMA", format!("quality {q} is not listed"), "quality"))
    }
}

fn check_enums(
    counterparties: &[Counterparty],
    version: &str,
    single: &[SingleNameHedge],
    index: &[IndexHedge],
) -> Result<()> {
    if !VERSIONS.contains(&version) {
        return Err(qerr(
            "E_SCHEMA",
            format!("version {version} is not listed"),
            "version",
        ));
    }
    let secs = sectors();
    for c in counterparties {
        listed(&c.sector, &secs, "sector")?;
        quality_listed(&c.quality)?;
    }
    for h in single {
        if !RELATION_NAMES.contains(&h.relation.as_str()) {
            return Err(qerr(
                "E_SCHEMA",
                format!("relation {} is not listed", h.relation),
                "relation",
            ));
        }
        listed(&h.sector, &secs, "sector")?;
        quality_listed(&h.quality)?;
    }
    for ih in index {
        for k in &ih.constituents {
            listed(&k.sector, &secs, "sector")?;
            quality_listed(&k.quality)?;
        }
    }
    Ok(())
}

fn ba_structure(
    counterparties: &[Counterparty],
    version: &str,
    single: &[SingleNameHedge],
    index: &[IndexHedge],
) -> Result<()> {
    let mut ids = HashSet::new();
    for c in counterparties {
        if !ids.insert(c.id.as_str()) {
            return Err(qerr(
                "E_INPUT",
                format!("counterparty {} appears twice", c.id),
                "id",
            )); // KR-312
        }
    }
    if version == "REDUCED" && (!single.is_empty() || !index.is_empty()) {
        return Err(qerr(
            "E_INPUT",
            "hedges are recognised only in the FULL version",
            "single_name_hedges",
        ));
    }
    for h in single {
        if !ids.contains(h.counterparty.as_str()) {
            return Err(qerr(
                "E_INPUT",
                format!("hedge references unknown counterparty {}", h.counterparty),
                "counterparty",
            ));
        }
    }
    Ok(())
}

fn ba_domain(
    counterparties: &[Counterparty],
    single: &[SingleNameHedge],
    index: &[IndexHedge],
) -> Result<()> {
    for c in counterparties {
        for ns in &c.netting_sets {
            if ns.ead < 0.0 {
                return Err(qerr(
                    "E_DOMAIN",
                    format!("counterparty {}: ead must not be negative", c.id),
                    "ead",
                ));
            }
            if !(ns.m > 0.0) {
                return Err(qerr(
                    "E_DOMAIN",
                    format!("counterparty {}: m must be positive", c.id),
                    "m",
                ));
            }
        }
    }
    for h in single {
        if !(h.m > 0.0) {
            return Err(qerr("E_DOMAIN", "hedge m must be positive", "m"));
        }
        if h.notional < 0.0 {
            return Err(qerr("E_DOMAIN", "hedge notional must not be negative", "notional"));
        }
    }
    for ih in index {
        if !(ih.m > 0.0) {
            return Err(qerr("E_DOMAIN", "index hedge m must be positive", "m"));
        }
        if ih.notional < 0.0 {
            return Err(qerr(
                "E_DOMAIN",
                "index hedge notional must not be negative",
                "notional",
            ));
        }
        if ih.constituents.iter().any(|k| k.weight < 0.0) {
            return Err(qerr("E_DOMAIN", "index weights must not be negative", "weight")); // KR-313
        }
        let total = fsum(ih.constituents.iter().map(|k| k.weight));
        if !((total - 1.0).abs() <= WEIGHT_TOLERANCE) {
            return Err(qerr(
                "E_DOMAIN",
                "index weights must sum to 1 within 1e-12",
                "weight",
            ));
        }
    }
    Ok(())
}

/// MAR50.14.
fn k_reduced(scva: &[f64], rho: f64) -> f64 {
    let systematic = rho * fsum(scva.iter().copied());
    (systematic * systematic + (1.0 - rho * rho) * fsum(scva.iter().map(|s| s * s))).sqrt()
}

/// BA-CVA capital, reduced (MAR50.14) or full (MAR50.20), with its intermediates.
pub fn ba_cva(
    counterparties: &[Counterparty],
    version: &str,
    single_name_hedges: &[SingleNameHedge],
    index_hedges: &[IndexHedge],
) -> Result<BaResult> {
    check_enums(counterparties, version, single_name_hedges, index_hedges)?;
    ba_structure(counterparties, version, single_name_hedges, index_hedges)?;
    ba_domain(counterparties, single_name_hedges, index_hedges)?;
    let t = mar50();
    let (rho, alpha, beta, ds) = (
        t.num("ba.rho"),
        t.num("ba.alpha"),
        t.num("ba.beta"),
        t.num("ba.ds"),
    );
    let mut rows = Vec::with_capacity(counterparties.len());
    let mut scva = Vec::with_capacity(counterparties.len());
    for c in counterparties {
        let dfs = c
            .netting_sets
            .iter()
            .map(|ns| discount_factor(ns.m, ns.imm))
            .collect::<Result<Vec<_>>>()?;
        let s = rw(&c.sector, &c.quality)
            * fsum(c.netting_sets.iter().zip(&dfs).map(|(ns, df)| ns.m * ns.ead * df))
            / alpha; // MAR50.15
        scva.push(s);
        rows.push(BaRow {
            id: c.id.clone(),
            scva: s,
            snh: None,
            hma: None,
            dfs,
        });
    }
    let k_red = k_reduced(&scva, rho);
    let (mut ih, mut k_hedged, mut k_full) = (None, None, None);
    let capital = if version == "FULL" {
        let mut snh_parts: Vec<Vec<f64>> = vec![Vec::new(); counterparties.len()];
        let mut hma_parts: Vec<Vec<f64>> = vec![Vec::new(); counterparties.len()];
        let r_hc = t.get("ba.r_hc");
        for h in single_name_hedges {
            let key = RELATIONS
                .iter()
                .find(|(n, _)| *n == h.relation)
                .map_or("direct", |(_, k)| k);
            let r = dec(at(r_hc, key));
            let x = rw(&h.sector, &h.quality) * h.m * h.notional * discount_factor(h.m, false)?;
            let p = counterparties
                .iter()
                .position(|c| c.id == h.counterparty)
                .unwrap_or(0);
            snh_parts[p].push(r * x); // MAR50.23
            hma_parts[p].push((1.0 - r * r) * x * x); // MAR50.25
        }
        let snh: Vec<f64> = snh_parts.into_iter().map(fsum).collect();
        let hma: Vec<f64> = hma_parts.into_iter().map(fsum).collect();
        let scalar = t.num("ba.index_rw_scalar");
        let mut terms = Vec::with_capacity(index_hedges.len());
        for i in index_hedges {
            let w = fsum(
                i.constituents
                    .iter()
                    .map(|k| k.weight * rw(&k.sector, &k.quality)),
            );
            terms.push(scalar * w * i.m * i.notional * discount_factor(i.m, false)?);
        }
        let index = fsum(terms); // MAR50.24
        let net: Vec<f64> = scva.iter().zip(&snh).map(|(s, h)| s - h).collect();
        let systematic = rho * fsum(net.iter().copied()) - index;
        let hedged = (systematic * systematic
            + (1.0 - rho * rho) * fsum(net.iter().map(|x| x * x))
            + fsum(hma.iter().copied()))
        .sqrt(); // MAR50.21
        let full = beta * k_red + (1.0 - beta) * hedged; // MAR50.20
        for ((row, a), b) in rows.iter_mut().zip(snh).zip(hma) {
            row.snh = Some(a);
            row.hma = Some(b);
        }
        ih = Some(index);
        k_hedged = Some(hedged);
        k_full = Some(full);
        ds * full
    } else {
        ds * k_red
    };
    Ok(BaResult {
        version: version.to_string(),
        counterparties: rows,
        ih,
        k_reduced: k_red,
        k_hedged,
        k_full,
        capital,
        rwa: t.num("rwa_multiplier") * capital,
    })
}

// --- SA-CVA ---------------------------------------------------------------------------------------

/// MAR50.43, KR-63.
pub const RISK_CLASSES: [&str; 6] = ["IR", "FX", "CCS", "RCS", "EQ", "COM"];
pub const KINDS: [&str; 2] = ["DELTA", "VEGA"];
/// KR-311: the parallel-shift factor of an unspecified currency (MAR50.57).
pub const IR_CURVE: &str = "CURVE";
/// KR-311, MAR50.58(1).
pub const IR_VEGA_FACTORS: [&str; 2] = ["IR_VOL", "INFLATION_VOL"];

/// The class keys in output order: every class and kind except `CCS.VEGA`.
pub fn class_keys() -> Vec<String> {
    let mut out = Vec::new();
    for c in RISK_CLASSES {
        for k in KINDS {
            if (c, k) != ("CCS", "VEGA") {
                out.push(format!("{c}.{k}"));
            }
        }
    }
    out
}

/// The specified-currency tenors of MAR50.56(1), `inflation` included.
pub fn ir_tenors() -> Vec<String> {
    strings(mar50().get("ir.tenors_specified"))
}

/// The IR delta factor names: the tenors and `CURVE`.
pub fn ir_delta_factors() -> Vec<String> {
    let mut v = ir_tenors();
    v.push(IR_CURVE.to_string());
    v
}

/// MAR50.65(1).
pub fn ccs_tenors() -> Vec<String> {
    strings(mar50().get("ccs.tenors"))
}

/// A counterparty credit spread factor (KR-63).
#[derive(Debug, Clone, PartialEq)]
pub struct CreditFactor {
    pub name: String,
    pub tenor: String,
    pub quality: String,
    pub legal_group: Option<String>,
    pub index: Option<String>,
    pub series: Option<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Factor {
    Name(String),
    Credit(CreditFactor),
}

#[derive(Debug, Clone, PartialEq)]
pub struct Sensitivity {
    pub bucket: String,
    pub factor: Factor,
    pub s_cva: f64,
    pub s_hdg: f64,
}

/// One bucket of a class output.
#[derive(Debug, Clone, PartialEq)]
pub struct BucketRow {
    pub bucket: String,
    pub k_b: f64,
    pub s_b: f64,
    pub sum_ws: f64,
    pub floored: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ClassResult {
    pub buckets: Vec<BucketRow>,
    pub k: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SaResult {
    /// In the order of [`class_keys`].
    pub classes: Vec<(String, ClassResult)>,
    pub m_cva: f64,
    pub total: f64,
    pub rwa: f64,
}

struct Entry<'a> {
    bucket: String,
    key: Vec<String>,
    rw: f64,
    s: &'a Sensitivity,
}

fn is_currency(s: &str) -> bool {
    s.len() == 3 && s.bytes().all(|b| b.is_ascii_uppercase())
}

fn upper(table: &Json, a: usize, b: usize) -> f64 {
    let (i, j) = (a.min(b), a.max(b));
    dec(idx(idx(table, i), j))
}

fn ir_rho(a: &str, b: &str) -> f64 {
    let tenors = ir_tenors();
    let p = |t: &str| tenors.iter().position(|x| x == t).unwrap_or(0);
    let (x, y) = (p(a), p(b));
    let (i, j) = (x.min(y), x.max(y));
    dec(at(
        at(mar50().get("ir.rho_specified"), &tenors[i]),
        &tenors[j],
    ))
}

fn credit(f: &Factor) -> &CreditFactor {
    match f {
        Factor::Credit(c) => c,
        Factor::Name(_) => panic!("a CCS entry carries a credit factor"),
    }
}

/// MAR50.65(4)-(5): `rho_tenor x rho_name x rho_quality`.
fn ccs_rho(bucket: &str, f: &CreditFactor, g: &CreditFactor) -> f64 {
    let spec = mar50().get("ccs.rho");
    let (p, name) = if bucket == "8" {
        let p = at(spec, "bucket_8");
        let n = if (&f.index, &f.series) == (&g.index, &g.series) {
            0
        } else if f.index == g.index {
            1
        } else {
            2
        };
        (p, n)
    } else {
        let p = at(spec, "buckets_1_7");
        let n = if f.name == g.name {
            0
        } else if f.legal_group.is_some() && f.legal_group == g.legal_group {
            1
        } else {
            2
        };
        (p, n)
    };
    let name = dec(idx(at(p, "name"), name));
    let tenor = dec(idx(at(p, "tenor"), usize::from(f.tenor != g.tenor)));
    let quality = dec(idx(at(p, "quality"), usize::from(f.quality != g.quality)));
    tenor * name * quality
}

fn bucket_number(b: &str) -> usize {
    b.parse().unwrap_or(0)
}

/// MAR50.67 Table 9 rows: 1/8 .. 7/14 are rows 0..6, then 15, 16, 17 are rows 7, 8, 9 (KR-316).
fn rcs_row(b: usize) -> usize {
    if b <= 7 { b - 1 } else { b - 8 }
}

fn rcs_gamma(b: &str, c: &str) -> f64 {
    let (x, y) = (bucket_number(b), bucket_number(c));
    let mut g = upper(mar50().get("rcs.gamma_same_quality"), rcs_row(x), rcs_row(y));
    if x <= 14 && y <= 14 && (x <= 7) != (y <= 7) {
        g /= mar50().num("rcs.gamma_cross_quality_divisor"); // MAR50.67(2)
    }
    g
}

/// MAR50.71.
fn eq_gamma(b: &str, c: &str) -> f64 {
    let (x, y) = (bucket_number(b), bucket_number(c));
    let g = mar50().get("eq.gamma");
    let key = if x == 11 || y == 11 {
        "with_11"
    } else if x <= 10 && y <= 10 {
        "within_1_10"
    } else if (x, y) == (12, 13) || (x, y) == (13, 12) {
        "12_13"
    } else {
        "12_or_13_with_1_10"
    };
    dec(at(g, key))
}

/// MAR50.75.
fn com_gamma(b: &str, c: &str) -> f64 {
    let g = mar50().get("com.gamma");
    let eleven = bucket_number(b) == 11 || bucket_number(c) == 11;
    dec(at(g, if eleven { "with_11" } else { "within_1_10" }))
}

/// MAR50.64 Table 6; buckets 1a and 1b are bucket 1 (KR-312).
fn ccs_gamma(b: &str, c: &str) -> f64 {
    upper(
        mar50().get("ccs.gamma"),
        bucket_number(b) - 1,
        bucket_number(c) - 1,
    )
}

fn gamma(cls: &str, b: &str, c: &str) -> f64 {
    match cls {
        "IR" => mar50().num("ir.gamma"),
        "FX" => mar50().num("fx.gamma"),
        "CCS" => ccs_gamma(b, c),
        "RCS" => rcs_gamma(b, c),
        "EQ" => eq_gamma(b, c),
        _ => com_gamma(b, c),
    }
}

fn rho(cls: &str, kind: &str, bucket: &str, a: &Entry, b: &Entry) -> f64 {
    match (cls, kind) {
        ("IR", "VEGA") => mar50().num("ir.vega_rho"),
        ("IR", _) => {
            if a.key[0] == IR_CURVE || b.key[0] == IR_CURVE {
                mar50().num("ir.rho_other_ccy_curve_inflation")
            } else {
                ir_rho(&a.key[0], &b.key[0])
            }
        }
        ("CCS", _) => ccs_rho(bucket, credit(&a.s.factor), credit(&b.s.factor)),
        _ => 1.0, // one factor per bucket: never called with two entries
    }
}

/// `sum_k WS_k^2 + sum_{k != l} rho_kl WS_k WS_l`, not floored (MAR21.4(1)), in the order of
/// `frtb.bucket_radicand`: the squares by Python `sum`, then the cross terms one by one.
pub fn bucket_radicand(ws: &[f64], rho: impl Fn(usize, usize) -> f64) -> f64 {
    let mut total = py_sum(ws.iter().map(|w| w * w));
    for (i, wi) in ws.iter().enumerate() {
        for (j, wj) in ws.iter().enumerate() {
            if i != j {
                total += rho(i, j) * wi * wj;
            }
        }
    }
    total
}

/// `sum_b K_b^2 + sum_{b != c} gamma_bc S_b S_c`, not floored (MAR21.4(4)), in the order of
/// `frtb.cross_radicand`.
pub fn cross_radicand(ks: &[f64], s: &[f64], gamma: impl Fn(usize, usize) -> f64) -> f64 {
    let mut total = py_sum(ks.iter().map(|k| k * k));
    for b in 0..s.len() {
        for c in 0..s.len() {
            if b != c {
                total += gamma(b, c) * s[b] * s[c];
            }
        }
    }
    total
}

fn split_key(key: &str) -> Result<(&str, &str)> {
    let (cls, kind) = key.split_once('.').unwrap_or((key, ""));
    if RISK_CLASSES.contains(&cls) && KINDS.contains(&kind) {
        Ok((cls, kind))
    } else {
        Err(qerr(
            "E_SCHEMA",
            format!("class {key} is not listed"),
            "classes",
        ))
    }
}

/// The factor's type and listed values (`E_SCHEMA`).
fn check_factor_schema(cls: &str, kind: &str, s: &Sensitivity) -> Result<()> {
    match (&s.factor, cls) {
        (Factor::Credit(f), "CCS") => {
            if !ccs_tenors().contains(&f.tenor) {
                return Err(qerr(
                    "E_SCHEMA",
                    format!("tenor {} is not listed", f.tenor),
                    "tenor",
                ));
            }
            quality_listed(&f.quality)
        }
        (_, "CCS") => Err(qerr("E_SCHEMA", "a CCS factor is an object", "factor")),
        (Factor::Credit(_), _) => Err(qerr(
            "E_SCHEMA",
            "the factor is a string outside CCS",
            "factor",
        )),
        (Factor::Name(f), "IR") => {
            let ok = if kind == "DELTA" {
                ir_delta_factors().contains(f)
            } else {
                IR_VEGA_FACTORS.contains(&f.as_str())
            };
            if ok {
                Ok(())
            } else {
                Err(qerr(
                    "E_SCHEMA",
                    format!("IR factor {f} is not listed"),
                    "factor",
                ))
            }
        }
        _ => Ok(()),
    }
}

fn factor_name(f: &Factor) -> &str {
    match f {
        Factor::Name(n) => n,
        Factor::Credit(c) => &c.name,
    }
}

/// Bucket, factor key and risk weight of one sensitivity; structural checks (`E_INPUT`).
fn entry<'a>(
    cls: &str,
    kind: &str,
    s: &'a Sensitivity,
    specified: &[String],
    rep: &str,
) -> Result<Entry<'a>> {
    let t = mar50();
    let b = s.bucket.as_str();
    let make = |bucket: &str, key: Vec<String>, rw: f64| Entry {
        bucket: bucket.to_string(),
        key,
        rw,
        s,
    };
    if cls == "IR" || cls == "FX" {
        if !is_currency(b) {
            return Err(qerr(
                "E_INPUT",
                format!("{cls} bucket {b} is not a currency code"),
                "bucket",
            ));
        }
        if cls == "FX" {
            if b == rep {
                return Err(qerr(
                    "E_INPUT",
                    "the reporting currency is not an FX bucket (MAR50.59)",
                    "bucket",
                ));
            }
            let w = t.num(if kind == "DELTA" {
                "fx.delta_rw"
            } else {
                "fx.vega_rw"
            });
            return Ok(make(b, Vec::new(), w));
        }
        let f = factor_name(&s.factor).to_string();
        if kind == "VEGA" {
            return Ok(make(b, vec![f], t.num("ir.vega_rw")));
        }
        if specified.iter().any(|c| c == b) {
            if f == IR_CURVE {
                return Err(qerr(
                    "E_INPUT",
                    format!("{b} is a specified currency: tenor factors (MAR50.56)"),
                    "factor",
                ));
            }
            let w = dec(at(t.get("ir.rw_specified"), &f));
            return Ok(make(b, vec![f], w));
        }
        if f != IR_CURVE && f != "inflation" {
            return Err(qerr(
                "E_INPUT",
                format!("{b} is not a specified currency: CURVE and inflation"),
                "factor",
            ));
        }
        return Ok(make(b, vec![f], t.num("ir.rw_other_ccy")));
    }
    if cls == "CCS" {
        let table = t.get("ccs.rw");
        if !keys(table).iter().any(|k| k == b) {
            return Err(qerr(
                "E_INPUT",
                format!("CCS bucket {b} is not listed"),
                "bucket",
            ));
        }
        let f = credit(&s.factor);
        let q = QUALITIES.iter().position(|x| *x == f.quality).unwrap_or(0);
        let w = dec(idx(at(table, b), q));
        let agg = if b == "1a" || b == "1b" { "1" } else { b };
        if b == "8" {
            let (Some(index), Some(series)) = (&f.index, &f.series) else {
                return Err(qerr(
                    "E_INPUT",
                    "bucket 8 factors need index and series (KR-63)",
                    "index",
                ));
            };
            return Ok(make(
                agg,
                vec![index.clone(), series.clone(), f.tenor.clone()],
                w,
            ));
        }
        return Ok(make(agg, vec![f.name.clone(), f.tenor.clone()], w));
    }
    let lower = cls.to_ascii_lowercase();
    let rws = t.get(&format!("{lower}.rw"));
    let n = keys(rws).len();
    if !(1..=n).any(|k| k.to_string() == b) {
        return Err(qerr(
            "E_INPUT",
            format!("{cls} bucket {b} is not listed"),
            "bucket",
        ));
    }
    let w = if kind == "DELTA" {
        dec(at(rws, b))
    } else if cls == "EQ" {
        let x = bucket_number(b);
        // KR-315: Table 11 "Large" buckets 1 to 8 and the index bucket 12.
        let large = (1..=8).contains(&x) || x == 12;
        dec(at(
            t.get("eq.vega_rw"),
            if large { "large_cap" } else { "other" },
        ))
    } else {
        t.num(&format!("{lower}.vega_rw"))
    };
    Ok(make(b, Vec::new(), w))
}

/// A CCS name (bucket 8: an index series) has one quality and one legal group (KR-314).
fn check_names(entries: &[Entry]) -> Result<()> {
    type Who = (String, Vec<Option<String>>);
    let mut seen: Vec<(Who, (String, Option<String>))> = Vec::new();
    for e in entries {
        let f = credit(&e.s.factor);
        let who = if e.bucket == "8" {
            vec![f.index.clone(), f.series.clone()]
        } else {
            vec![Some(f.name.clone())]
        };
        let key = (e.bucket.clone(), who);
        let attrs = (f.quality.clone(), f.legal_group.clone());
        match seen.iter().find(|(k, _)| *k == key) {
            Some((_, a)) if *a != attrs => {
                return Err(qerr(
                    "E_INPUT",
                    format!("name {} has two qualities or legal groups", f.name),
                    "factor",
                ));
            }
            Some(_) => {}
            None => seen.push((key, attrs)),
        }
    }
    Ok(())
}

/// Bucket order: by length, then text (`5` < `9` < `11`, `EUR` < `USD`).
fn bucket_order(a: &str, b: &str) -> std::cmp::Ordering {
    a.chars()
        .count()
        .cmp(&b.chars().count())
        .then_with(|| a.cmp(b))
}

/// MAR50.53 for one risk class and kind.
fn class_capital(cls: &str, kind: &str, entries: &[Entry], m_cva: f64) -> ClassResult {
    let mut names: Vec<&str> = Vec::new();
    for e in entries {
        if !names.contains(&e.bucket.as_str()) {
            names.push(&e.bucket);
        }
    }
    names.sort_by(|a, b| bucket_order(a, b));
    let r_hedge = mar50().num("sa.R");
    let (mut ks, mut sb, mut rows) = (Vec::new(), Vec::new(), Vec::new());
    for name in &names {
        let members: Vec<&Entry> = entries.iter().filter(|e| e.bucket == *name).collect();
        let ws: Vec<f64> = members
            .iter()
            .map(|e| e.rw * e.s.s_cva - e.rw * e.s.s_hdg)
            .collect(); // MAR50.51-50.52
        let wsh: Vec<f64> = members.iter().map(|e| e.rw * e.s.s_hdg).collect();
        let radicand = bucket_radicand(&ws, |i, j| rho(cls, kind, name, members[i], members[j]))
            + r_hedge * py_sum(wsh.iter().map(|h| h * h));
        let k_b = (if radicand > 0.0 { radicand } else { 0.0 }).sqrt(); // KR-62
        let total = py_sum(ws.iter().copied());
        let low = if k_b < total { k_b } else { total };
        let s_b = if low > -k_b { low } else { -k_b }; // MAR50.53(3)
        ks.push(k_b);
        sb.push(s_b);
        rows.push(BucketRow {
            bucket: (*name).to_string(),
            k_b,
            s_b,
            sum_ws: total,
            floored: radicand < 0.0,
        });
    }
    let cross = cross_radicand(&ks, &sb, |b, c| gamma(cls, names[b], names[c]));
    let k = m_cva * (if cross > 0.0 { cross } else { 0.0 }).sqrt();
    ClassResult { buckets: rows, k }
}

/// SA-CVA capital (MAR50.42-50.53): the sum of the delta and vega capital of every class.
/// `classes` holds the class keys (`IR.DELTA` ...) in input order.
pub fn sa_cva(
    classes: &[(String, Vec<Sensitivity>)],
    reporting_currency: &str,
    m_cva: f64,
) -> Result<SaResult> {
    let mut parsed = Vec::with_capacity(classes.len());
    for (key, _) in classes {
        parsed.push(split_key(key)?);
    }
    for ((cls, kind), (_, items)) in parsed.iter().zip(classes) {
        for s in items {
            check_factor_schema(cls, kind, s)?;
        }
    }
    if parsed.contains(&("CCS", "VEGA")) {
        return Err(qerr(
            "E_INPUT",
            "counterparty credit spread has no vega (MAR50.45)",
            "classes",
        ));
    }
    if !is_currency(reporting_currency) {
        return Err(qerr(
            "E_INPUT",
            "reporting_currency is not a currency code",
            "reporting_currency",
        ));
    }
    let specified: Vec<String> = strings(mar50().get("ir.specified_currencies"))
        .into_iter()
        .map(|c| {
            if c == "reporting" {
                reporting_currency.to_string()
            } else {
                c
            }
        })
        .collect();
    let mut built = Vec::new();
    for key in class_keys() {
        let Some(n) = classes.iter().position(|(k, _)| *k == key) else {
            continue;
        };
        let (cls, kind) = parsed[n];
        let entries = classes[n]
            .1
            .iter()
            .map(|s| entry(cls, kind, s, &specified, reporting_currency))
            .collect::<Result<Vec<_>>>()?;
        let mut seen = HashSet::new();
        for e in &entries {
            if !seen.insert((e.bucket.as_str(), e.key.as_slice())) {
                return Err(qerr(
                    "E_INPUT",
                    format!("{key}: bucket {} holds one risk factor twice", e.bucket),
                    "factor",
                ));
            }
        }
        if cls == "CCS" {
            check_names(&entries)?;
        }
        built.push((key, cls, kind, entries));
    }
    if !(m_cva >= 1.0) {
        return Err(qerr("E_DOMAIN", "m_cva must be at least 1 (MAR50.41)", "m_cva"));
    }
    let mut out = Vec::with_capacity(built.len());
    for (key, cls, kind, entries) in &built {
        out.push((key.clone(), class_capital(cls, kind, entries, m_cva)));
    }
    let total = fsum(out.iter().map(|(_, c)| c.k));
    Ok(SaResult {
        classes: out,
        m_cva,
        total,
        rwa: mar50().num("rwa_multiplier") * total,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn py_sum_is_compensated() {
        assert_eq!(py_sum([1e16, 1.0, -1e16]), 1.0);
        assert_eq!(py_sum(Vec::<f64>::new()), 0.0);
        assert_eq!(py_sum([0.1, 0.2, 0.3]), 0.6);
        assert!(py_sum([f64::INFINITY, 1.0]).is_infinite());
    }

    #[test]
    fn table_cells() {
        assert_eq!(dec(&Json::Str("0.90 legally related".into())), 0.9);
        assert_eq!(dec(&Json::Int(20)), 20.0);
        assert_eq!(sectors().len(), 8);
        assert_eq!(class_keys().len(), 11);
        assert_eq!(ir_delta_factors().last().map(String::as_str), Some("CURVE"));
    }

    #[test]
    fn gammas() {
        assert_eq!(rcs_gamma("1", "8"), 0.5); // cross quality: 1 / 2
        assert_eq!(rcs_gamma("15", "16"), 0.0);
        assert_eq!(rcs_gamma("1", "15"), 0.45);
        assert_eq!(eq_gamma("12", "13"), 0.75);
        assert_eq!(eq_gamma("13", "12"), 0.75);
        assert_eq!(eq_gamma("1", "12"), 0.45);
        assert_eq!(eq_gamma("11", "2"), 0.0);
        assert_eq!(eq_gamma("1", "2"), 0.15);
        assert_eq!(com_gamma("1", "2"), 0.2);
        assert_eq!(com_gamma("11", "2"), 0.0);
        assert_eq!(ccs_gamma("8", "1"), 0.45);
        assert_eq!(ir_rho("30Y", "1Y"), 0.31);
    }

    #[test]
    fn ccs_rho_parts() {
        let f = |name: &str, tenor: &str, q: &str, idx: Option<&str>, ser: Option<&str>| {
            CreditFactor {
                name: name.into(),
                tenor: tenor.into(),
                quality: q.into(),
                legal_group: None,
                index: idx.map(Into::into),
                series: ser.map(Into::into),
            }
        };
        let a = f("X", "1Y", "IG", Some("I"), Some("1"));
        let b = f("Y", "5Y", "HY_NR", Some("I"), Some("2"));
        let c = f("Z", "1Y", "IG", Some("J"), Some("1"));
        assert!((ccs_rho("8", &a, &b) - 0.9 * 0.9 * 0.8).abs() < 1e-15);
        assert!((ccs_rho("8", &a, &c) - 0.8).abs() < 1e-15);
        assert!((ccs_rho("8", &a, &a) - 1.0).abs() < 1e-15);
        assert!((ccs_rho("2", &a, &c) - 0.5).abs() < 1e-15);
    }

    #[test]
    #[should_panic(expected = "credit factor")]
    fn credit_of_a_name_panics() {
        let _ = credit(&Factor::Name("X".into()));
    }
}
