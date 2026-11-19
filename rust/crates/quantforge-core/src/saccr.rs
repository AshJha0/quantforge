//! SA-CCR exposure at default of a derivatives netting set (`sa-ccr.md`, plan item K-8d, rulings
//! KR-30 to KR-39). A port of `python/quantforge_core/saccr.py`. The supervisory parameters are
//! read from `specifications/06-risk/sa-ccr-parameters.json`, embedded at build time.
#![allow(clippy::neg_cmp_op_on_partial_ord)] // NaN-safe domain checks, as the spec writes them
use crate::error::{QfError, Result, err, finite};
use crate::json::{Json, parse};
use crate::research_w3::fsum;
use crate::stats::normal_cdf;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::OnceLock;

const TABLE_TEXT: &str = include_str!("../../../../specifications/06-risk/sa-ccr-parameters.json");

/// The asset classes, in output order (CRE52.26).
pub const CLASSES: [&str; 5] = ["IR", "FX", "CREDIT", "EQUITY", "COMMODITY"];
/// The hedging-set treatments, in output order (CRE52.46, CRE52.47).
pub const TREATMENTS: [&str; 3] = ["NORMAL", "BASIS", "VOLATILITY"];

/// One CRE52.72 Table 2 row.
#[derive(Debug, Clone, PartialEq)]
pub struct Row {
    pub asset_class: String,
    /// `""` for IR and FX.
    pub subclass: String,
    pub factor: f64,
    pub correlation: Option<f64>,
    pub option_volatility: f64,
    pub hedging_set: Option<String>,
}

/// The parsed parameter file.
#[derive(Debug, Clone)]
pub struct Params {
    pub alpha: f64,
    pub floor: f64,
    pub year_days: i64,
    pub min_days: i64,
    pub sd_rate: f64,
    pub rho12: f64,
    pub rho23: f64,
    pub rho13: f64,
    pub bucket1_below: f64,
    pub bucket2_up_to: f64,
    pub margined_mf_scale: f64,
    pub mpor_daily: i64,
    pub mpor_non_daily_base: i64,
    pub mpor_large: i64,
    pub mpor_large_trades_above: i64,
    pub mpor_dispute_multiplier: i64,
    pub scale: [f64; 3],
    pub cdo_numerator: f64,
    pub cdo_slope: f64,
    pub table2: Vec<Row>,
}

fn num(doc: &Json, path: &[&str]) -> f64 {
    let mut v = doc;
    for k in path {
        v = v.get(k).expect("parameter key present");
    }
    v.as_f64().expect("parameter is a number")
}

fn int(doc: &Json, path: &[&str]) -> i64 {
    num(doc, path) as i64
}

/// The parameters of `sa-ccr-parameters.json`, parsed once.
pub fn params() -> &'static Params {
    static P: OnceLock<Params> = OnceLock::new();
    P.get_or_init(|| {
        let (doc, _) = parse(TABLE_TEXT).expect("embedded SA-CCR table is valid JSON");
        let rows = doc
            .get("table2")
            .and_then(Json::as_array)
            .expect("table2 present");
        let text = |r: &Json, k: &str| r.get(k).and_then(Json::as_str).map(str::to_string);
        let table2 = rows
            .iter()
            .map(|r| Row {
                asset_class: text(r, "asset_class").expect("asset_class"),
                subclass: text(r, "subclass").unwrap_or_default(),
                factor: num(r, &["supervisory_factor"]),
                correlation: r.get("correlation").and_then(Json::as_f64),
                option_volatility: num(r, &["option_volatility"]),
                hedging_set: text(r, "hedging_set"),
            })
            .collect();
        Params {
            alpha: num(&doc, &["alpha"]),
            floor: num(&doc, &["multiplier_floor"]),
            year_days: int(&doc, &["business_days_per_year"]),
            min_days: int(&doc, &["min_business_days"]),
            sd_rate: num(&doc, &["supervisory_duration_rate"]),
            rho12: num(&doc, &["ir_bucket_correlations", "b1_b2"]),
            rho23: num(&doc, &["ir_bucket_correlations", "b2_b3"]),
            rho13: num(&doc, &["ir_bucket_correlations", "b1_b3"]),
            bucket1_below: num(&doc, &["ir_bucket_bounds_years", "bucket1_below"]),
            bucket2_up_to: num(
                &doc,
                &["ir_bucket_bounds_years", "bucket2_up_to_and_including"],
            ),
            margined_mf_scale: num(&doc, &["margined_maturity_factor_scale"]),
            mpor_daily: int(&doc, &["mpor_floor_days", "daily_margin"]),
            mpor_non_daily_base: int(&doc, &["mpor_floor_days", "non_daily_base"]),
            mpor_large: int(&doc, &["mpor_floor_days", "large_or_illiquid"]),
            mpor_large_trades_above: int(
                &doc,
                &["mpor_floor_days", "large_netting_set_trades_above"],
            ),
            mpor_dispute_multiplier: int(&doc, &["mpor_floor_days", "dispute_multiplier"]),
            scale: [
                num(&doc, &["treatment_scale", "NORMAL"]),
                num(&doc, &["treatment_scale", "BASIS"]),
                num(&doc, &["treatment_scale", "VOLATILITY"]),
            ],
            cdo_numerator: num(&doc, &["cdo_delta", "numerator"]),
            cdo_slope: num(&doc, &["cdo_delta", "slope"]),
            table2,
        }
    })
}

fn row(class: &str, subclass: Option<&str>) -> Option<&'static Row> {
    let s = subclass.unwrap_or("");
    params()
        .table2
        .iter()
        .find(|r| r.asset_class == class && r.subclass == s)
}

fn row_of(t: &Trade) -> &'static Row {
    row(&t.asset_class, t.subclass.as_deref()).expect("structure checked the Table 2 row")
}

fn min_years() -> f64 {
    params().min_days as f64 / params().year_days as f64
}

/// One trade of the netting set. Enum-valued fields hold the contract's strings, already checked by
/// the input layer (a value outside the list is `E_SCHEMA` there, ruling KR-39).
#[derive(Debug, Clone, PartialEq)]
pub struct Trade {
    pub id: String,
    pub asset_class: String,
    pub notional: f64,
    pub market_value: f64,
    pub maturity: f64,
    pub kind: String,
    pub position: String,
    pub treatment: String,
    pub start: Option<f64>,
    pub end: Option<f64>,
    pub hedging_set: Option<String>,
    pub entity: Option<String>,
    pub subclass: Option<String>,
    pub option_type: Option<String>,
    pub underlying_price: Option<f64>,
    pub strike: Option<f64>,
    pub exercise: Option<f64>,
    pub shift: f64,
    pub attachment: Option<f64>,
    pub detachment: Option<f64>,
}

impl Trade {
    /// A linear `NORMAL` trade with every optional field absent.
    pub fn linear(
        id: &str,
        class: &str,
        notional: f64,
        mv: f64,
        maturity: f64,
        pos: &str,
    ) -> Trade {
        Trade {
            id: id.to_string(),
            asset_class: class.to_string(),
            notional,
            market_value: mv,
            maturity,
            kind: "LINEAR".to_string(),
            position: pos.to_string(),
            treatment: "NORMAL".to_string(),
            start: None,
            end: None,
            hedging_set: None,
            entity: None,
            subclass: None,
            option_type: None,
            underlying_price: None,
            strike: None,
            exercise: None,
            shift: 0.0,
            attachment: None,
            detachment: None,
        }
    }
}

/// The margin agreement of a margined netting set.
#[derive(Debug, Clone, PartialEq)]
pub struct Margin {
    pub threshold: f64,
    pub mta: f64,
    pub nica: f64,
    pub remargin_days: i64,
    pub mpor_days: Option<i64>,
    pub illiquid: bool,
    pub disputes: bool,
}

/// Per-trade figures, in input order.
#[derive(Debug, Clone, PartialEq)]
pub struct TradeRow {
    pub id: String,
    pub supervisory_duration: Option<f64>,
    pub adjusted_notional: f64,
    pub maturity_factor: f64,
    pub delta: f64,
    pub effective_notional: f64,
    pub supervisory_factor: f64,
}

/// One hedging set's add-on.
#[derive(Debug, Clone, PartialEq)]
pub struct HedgingSet {
    pub asset_class: &'static str,
    pub treatment: &'static str,
    pub key: String,
    pub addon: f64,
}

/// The result of [`ead`].
#[derive(Debug, Clone, PartialEq)]
pub struct EadResult {
    pub ead: f64,
    pub rc: f64,
    pub pfe: f64,
    pub multiplier: f64,
    pub addon_aggregate: f64,
    /// In [`CLASSES`] order.
    pub addon: [f64; 5],
    pub v: f64,
    pub c: f64,
    pub margined: bool,
    pub mpor_days: Option<i64>,
    pub ead_unmargined: Option<f64>,
    pub capped: bool,
    pub hedging_sets: Vec<HedgingSet>,
    pub trades: Vec<TradeRow>,
}

fn input(field: &str, message: String) -> QfError {
    let mut e = err("E_INPUT", message);
    e.field = Some(field.to_string());
    e
}

fn domain_err(field: &str, message: String) -> QfError {
    let mut e = err("E_DOMAIN", message);
    e.field = Some(field.to_string());
    e
}

fn need<T>(t: &Trade, v: Option<&T>, field: &str, why: &str) -> Result<()> {
    if v.is_none() {
        return Err(input(
            field,
            format!("trade {}: {field} is required {why}", t.id),
        ));
    }
    Ok(())
}

fn named_class(c: &str) -> bool {
    matches!(c, "CREDIT" | "EQUITY" | "COMMODITY")
}

/// Structural checks (`E_INPUT`), all before any domain check (HR-122 order).
pub fn structure(trades: &[Trade]) -> Result<()> {
    if trades.is_empty() {
        return Err(input("trades", "trades is empty".to_string()));
    }
    let mut seen = HashSet::new();
    for t in trades {
        if !seen.insert(t.id.as_str()) {
            return Err(input("id", format!("duplicate trade id {}", t.id)));
        }
        let c = t.asset_class.as_str();
        if matches!(c, "IR" | "CREDIT") {
            need(t, t.start.as_ref(), "start", "for IR and CREDIT trades")?;
            need(t, t.end.as_ref(), "end", "for IR and CREDIT trades")?;
        }
        if matches!(c, "IR" | "FX") || t.treatment != "NORMAL" {
            need(
                t,
                t.hedging_set.as_ref(),
                "hedging_set",
                "for IR, FX, basis and volatility trades",
            )?;
        }
        if named_class(c) {
            need(
                t,
                t.entity.as_ref(),
                "entity",
                "for CREDIT, EQUITY and COMMODITY trades",
            )?;
            need(
                t,
                t.subclass.as_ref(),
                "subclass",
                "for CREDIT, EQUITY and COMMODITY trades",
            )?;
            if row(c, t.subclass.as_deref()).is_none() {
                let s = t.subclass.as_deref().unwrap_or_default();
                return Err(input(
                    "subclass",
                    format!("trade {}: subclass {s} is not a {c} subclass", t.id),
                ));
            }
        } else if t.subclass.is_some() {
            return Err(input(
                "subclass",
                format!("trade {}: {c} trades take no subclass", t.id),
            ));
        }
        let linear = matches!(t.position.as_str(), "LONG" | "SHORT");
        if (t.kind == "LINEAR") != linear {
            return Err(input(
                "position",
                format!(
                    "trade {}: position {} does not fit kind {}",
                    t.id, t.position, t.kind
                ),
            ));
        }
        if t.kind == "OPTION" {
            need(
                t,
                t.option_type.as_ref(),
                "option_type",
                "for OPTION trades",
            )?;
            need(
                t,
                t.underlying_price.as_ref(),
                "underlying_price",
                "for OPTION trades",
            )?;
            need(t, t.strike.as_ref(), "strike", "for OPTION trades")?;
            need(t, t.exercise.as_ref(), "exercise", "for OPTION trades")?;
        }
        if t.kind == "CDO" {
            if c != "CREDIT" {
                return Err(input(
                    "kind",
                    format!("trade {}: CDO tranches are CREDIT trades", t.id),
                ));
            }
            need(t, t.attachment.as_ref(), "attachment", "for CDO trades")?;
            need(t, t.detachment.as_ref(), "detachment", "for CDO trades")?;
        }
    }
    let mut entity_sub: HashMap<(&str, &str, &str, &str), &str> = HashMap::new();
    for t in trades {
        let (Some(entity), Some(sub)) = (t.entity.as_deref(), t.subclass.as_deref()) else {
            continue;
        };
        let key = (
            t.asset_class.as_str(),
            t.treatment.as_str(),
            t.hedging_set.as_deref().unwrap_or(""),
            entity,
        );
        if *entity_sub.entry(key).or_insert(sub) != sub {
            return Err(input(
                "subclass",
                format!("entity {entity} has two subclasses"),
            ));
        }
    }
    Ok(())
}

fn or0(v: Option<f64>) -> f64 {
    v.unwrap_or(0.0)
}

fn domain(trades: &[Trade], margin: Option<&Margin>) -> Result<()> {
    for t in trades {
        let id = &t.id;
        if !(t.notional > 0.0) {
            return Err(domain_err(
                "notional",
                format!("trade {id}: notional must be positive"),
            ));
        }
        if !(t.maturity > 0.0) {
            return Err(domain_err(
                "maturity",
                format!("trade {id}: maturity must be positive"),
            ));
        }
        if let (Some(s), Some(e)) = (t.start, t.end)
            && !(0.0 <= s && s <= e)
        {
            return Err(domain_err(
                "start",
                format!("trade {id}: need 0 <= start <= end"),
            ));
        }
        if t.kind == "OPTION" {
            let p = or0(t.underlying_price) + t.shift;
            let k = or0(t.strike) + t.shift;
            if !(p > 0.0 && k > 0.0) {
                return Err(domain_err(
                    "strike",
                    format!("trade {id}: shifted price and strike must be positive"),
                ));
            }
            if !(or0(t.exercise) > 0.0) {
                return Err(domain_err(
                    "exercise",
                    format!("trade {id}: exercise must be positive"),
                ));
            }
        }
        if t.kind == "CDO" {
            let (a, d) = (or0(t.attachment), or0(t.detachment));
            if !(0.0 <= a && a < d && d <= 1.0) {
                return Err(domain_err(
                    "attachment",
                    format!("trade {id}: need 0 <= attachment < detachment <= 1"),
                ));
            }
        }
    }
    if let Some(m) = margin {
        if m.threshold < 0.0 {
            return Err(domain_err(
                "threshold",
                "threshold must not be negative".to_string(),
            ));
        }
        if m.mta < 0.0 {
            return Err(domain_err("mta", "mta must not be negative".to_string()));
        }
        if m.remargin_days < 1 {
            return Err(domain_err(
                "remargin_days",
                "remargin_days must be at least 1".to_string(),
            ));
        }
        if m.mpor_days.is_some_and(|d| d < 1) {
            return Err(domain_err(
                "mpor_days",
                "mpor_days must be at least 1".to_string(),
            ));
        }
    }
    Ok(())
}

/// CRE52.34, floored at ten business days.
pub fn supervisory_duration(start: f64, end: f64) -> f64 {
    let r = params().sd_rate;
    let sd = ((-r * start).exp() - (-r * end).exp()) / r;
    sd.max(min_years())
}

/// CRE52.50 and CRE52.51 floors, in business days (ruling KR-35).
pub fn mpor_floor(m: &Margin, trade_count: usize) -> i64 {
    let p = params();
    let mut base = if m.remargin_days == 1 {
        p.mpor_daily
    } else {
        p.mpor_non_daily_base + m.remargin_days
    };
    if trade_count as i64 > p.mpor_large_trades_above || m.illiquid {
        base = base.max(p.mpor_large);
    }
    if m.disputes {
        p.mpor_dispute_multiplier * base
    } else {
        base
    }
}

/// CRE52.39 to CRE52.41.
pub fn supervisory_delta(t: &Trade) -> f64 {
    if t.kind == "LINEAR" {
        return if t.position == "LONG" { 1.0 } else { -1.0 };
    }
    let bought = t.position == "BOUGHT";
    if t.kind == "CDO" {
        let p = params();
        let (a, d) = (or0(t.attachment), or0(t.detachment));
        let v = p.cdo_numerator / ((1.0 + p.cdo_slope * a) * (1.0 + p.cdo_slope * d));
        return if bought { v } else { -v };
    }
    let sigma = row_of(t).option_volatility;
    let tt = or0(t.exercise);
    let (pr, k) = (or0(t.underlying_price) + t.shift, or0(t.strike) + t.shift);
    let d1 = ((pr / k).ln() + 0.5 * sigma * sigma * tt) / (sigma * tt.sqrt());
    let sign = if bought { 1.0 } else { -1.0 };
    let call = t.option_type.as_deref() == Some("CALL");
    sign * if call {
        normal_cdf(d1)
    } else {
        -normal_cdf(-d1)
    }
}

fn treatment_index(t: &str) -> usize {
    TREATMENTS.iter().position(|x| *x == t).unwrap_or(0)
}

fn class_index(c: &str) -> usize {
    CLASSES.iter().position(|x| *x == c).unwrap_or(0)
}

fn factor(t: &Trade) -> f64 {
    row_of(t).factor * params().scale[treatment_index(&t.treatment)]
}

/// CRE52.57 step 3 on E (CRE52.31(3)); 1 and 5 years fall in bucket 2 (ruling KR-32).
pub fn bucket(end: f64) -> usize {
    let p = params();
    if end < p.bucket1_below {
        1
    } else if end <= p.bucket2_up_to {
        2
    } else {
        3
    }
}

/// CRE52.61 step 4, CRE52.66 step 4, CRE52.70 step 5: `(rho, add-on)` pairs.
pub fn single_factor(pairs: &[(f64, f64)]) -> f64 {
    let sys = fsum(pairs.iter().map(|(r, a)| r * a));
    let idio = fsum(pairs.iter().map(|(r, a)| (1.0 - r * r) * a * a));
    (sys * sys + idio).sqrt()
}

/// CRE52.23; with a zero aggregate add-on, the limit of the formula (ruling KR-36). `V - C >= 0`
/// gives exactly 1, without evaluating an exponential that can overflow when the add-on is tiny.
pub fn multiplier(v_minus_c: f64, addon: f64) -> f64 {
    if v_minus_c >= 0.0 {
        return 1.0;
    }
    let floor = params().floor;
    if addon == 0.0 {
        return floor;
    }
    (floor + (1.0 - floor) * (v_minus_c / (2.0 * (1.0 - floor) * addon)).exp()).min(1.0)
}

struct Netting {
    ead: f64,
    pfe: f64,
    m: f64,
    by_class: [f64; 5],
    rows: Vec<HedgingSet>,
    deltas: Vec<f64>,
    eff: Vec<f64>,
}

fn group_key(t: &Trade) -> String {
    let normal = t.treatment == "NORMAL";
    if t.asset_class == "COMMODITY" && normal {
        return row_of(t).hedging_set.clone().unwrap_or_default();
    }
    if matches!(t.asset_class.as_str(), "CREDIT" | "EQUITY") && normal {
        return String::new();
    }
    t.hedging_set.clone().unwrap_or_default()
}

fn ir_addon(
    trades: &[Trade],
    members: &[usize],
    eff: &[f64],
    treatment: usize,
    offset: bool,
) -> f64 {
    let p = params();
    let mut parts: [Vec<f64>; 3] = [Vec::new(), Vec::new(), Vec::new()];
    for &i in members {
        parts[bucket(or0(trades[i].end)) - 1].push(eff[i]);
    }
    let [b1, b2, b3] = parts.map(fsum);
    let en = if offset {
        (b1 * b1 + b2 * b2 + b3 * b3 + p.rho12 * b1 * b2 + p.rho23 * b2 * b3 + p.rho13 * b1 * b3)
            .max(0.0)
            .sqrt()
    } else {
        b1.abs() + b2.abs() + b3.abs()
    };
    let ir = row("IR", None).expect("IR row").factor;
    ir * p.scale[treatment] * en
}

fn netting(
    trades: &[Trade],
    mf: &[f64],
    d: &[f64],
    v_minus_c: f64,
    rc: f64,
    offset: bool,
) -> Netting {
    let deltas: Vec<f64> = trades.iter().map(supervisory_delta).collect();
    let eff: Vec<f64> = (0..trades.len())
        .map(|i| d[i] * mf[i] * deltas[i])
        .collect();
    // String keys order by bytes, which for UTF-8 is code-point order, as Python sorts.
    let mut groups: BTreeMap<(usize, usize, String), Vec<usize>> = BTreeMap::new();
    for (i, t) in trades.iter().enumerate() {
        let g = (
            class_index(&t.asset_class),
            treatment_index(&t.treatment),
            group_key(t),
        );
        groups.entry(g).or_default().push(i);
    }
    let mut by_class = [0.0; 5];
    let mut rows = Vec::new();
    for ((cls, treatment, key), members) in groups {
        let addon = match cls {
            0 => ir_addon(trades, &members, &eff, treatment, offset),
            1 => {
                let fx = row("FX", None).expect("FX row").factor;
                fx * params().scale[treatment] * fsum(members.iter().map(|&i| eff[i])).abs()
            }
            _ => {
                let mut entities: BTreeMap<&str, Vec<usize>> = BTreeMap::new();
                for &i in &members {
                    entities
                        .entry(trades[i].entity.as_deref().unwrap_or(""))
                        .or_default()
                        .push(i);
                }
                let pairs: Vec<(f64, f64)> = entities
                    .values()
                    .map(|idx| {
                        let first = &trades[idx[0]];
                        let rho = row_of(first).correlation.unwrap_or(0.0);
                        (rho, factor(first) * fsum(idx.iter().map(|&i| eff[i])))
                    })
                    .collect();
                single_factor(&pairs)
            }
        };
        by_class[cls] += addon;
        rows.push(HedgingSet {
            asset_class: CLASSES[cls],
            treatment: TREATMENTS[treatment],
            key,
            addon,
        });
    }
    let aggregate = fsum(by_class);
    let m = multiplier(v_minus_c, aggregate);
    let pfe = m * aggregate;
    Netting {
        ead: params().alpha * (rc + pfe),
        pfe,
        m,
        by_class,
        rows,
        deltas,
        eff,
    }
}

fn check_finite(trades: &[Trade], collateral: f64, margin: Option<&Margin>) -> Result<()> {
    for t in trades {
        finite("notional", &t.notional)?;
        finite("market_value", &t.market_value)?;
        finite("maturity", &t.maturity)?;
        finite("shift", &t.shift)?;
        for (k, v) in [
            ("start", t.start),
            ("end", t.end),
            ("underlying_price", t.underlying_price),
            ("strike", t.strike),
            ("exercise", t.exercise),
            ("attachment", t.attachment),
            ("detachment", t.detachment),
        ] {
            finite(k, &v)?;
        }
    }
    finite("collateral", &collateral)?;
    if let Some(m) = margin {
        finite("threshold", &m.threshold)?;
        finite("mta", &m.mta)?;
        finite("nica", &m.nica)?;
    }
    Ok(())
}

/// EAD of one netting set under SA-CCR (CRE52.1). `margin` `None` means unmargined. Order: the
/// finite rule (E1), structure (`E_INPUT`), then domain (`E_DOMAIN`), as HR-122.
pub fn ead(
    trades: &[Trade],
    collateral: f64,
    margin: Option<&Margin>,
    ir_offset: bool,
) -> Result<EadResult> {
    check_finite(trades, collateral, margin)?;
    structure(trades)?;
    domain(trades, margin)?;
    let v = fsum(trades.iter().map(|t| t.market_value));
    let c = collateral;
    let mut sd = Vec::with_capacity(trades.len());
    let mut d = Vec::with_capacity(trades.len());
    for t in trades {
        if matches!(t.asset_class.as_str(), "IR" | "CREDIT") {
            let s = supervisory_duration(or0(t.start), or0(t.end));
            sd.push(Some(s));
            d.push(t.notional * s);
        } else {
            sd.push(None);
            d.push(t.notional);
        }
    }
    let mf_un: Vec<f64> = trades
        .iter()
        .map(|t| t.maturity.max(min_years()).min(1.0).sqrt())
        .collect();
    let rc_un = (v - c).max(0.0);
    let un = netting(trades, &mf_un, &d, v - c, rc_un, ir_offset);
    let (result, mf, rc, mpor, ead_un, capped) = match margin {
        None => (un, mf_un, rc_un, None, None, false),
        Some(m) => {
            let mpor = mpor_floor(m, trades.len()).max(m.mpor_days.unwrap_or(0));
            let p = params();
            let mf_m = p.margined_mf_scale * (mpor as f64 / p.year_days as f64).sqrt();
            let mf = vec![mf_m; trades.len()];
            let rc = (v - c).max(m.threshold + m.mta - m.nica).max(0.0);
            let r = netting(trades, &mf, &d, v - c, rc, ir_offset);
            let capped = un.ead < r.ead;
            (r, mf, rc, Some(mpor), Some(un.ead), capped)
        }
    };
    let rows = trades
        .iter()
        .enumerate()
        .map(|(i, t)| TradeRow {
            id: t.id.clone(),
            supervisory_duration: sd[i],
            adjusted_notional: d[i],
            maturity_factor: mf[i],
            delta: result.deltas[i],
            effective_notional: result.eff[i],
            supervisory_factor: factor(t),
        })
        .collect();
    Ok(EadResult {
        ead: ead_un.map_or(result.ead, |u| result.ead.min(u)),
        rc,
        pfe: result.pfe,
        multiplier: result.m,
        addon_aggregate: fsum(result.by_class),
        addon: result.by_class,
        v,
        c,
        margined: margin.is_some(),
        mpor_days: mpor,
        ead_unmargined: ead_un,
        capped,
        hedging_sets: result.rows,
        trades: rows,
    })
}
