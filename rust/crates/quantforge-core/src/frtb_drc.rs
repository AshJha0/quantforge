//! FRTB standardised approach: default risk charge (DRC) and residual risk add-on (RRAO), plan item
//! K-8a (`specifications/06-risk/frtb-drc-rrao.md`; rulings KR-50 to KR-55, KR-67 to KR-69 and
//! KR-300 to KR-304, KR-327 in `specifications/stage-k-rulings-w2.md`). A port of
//! `python/quantforge_core/frtb_drc.py`, with the same evaluation order: every sum the reference
//! takes with `math.fsum` is the correctly rounded [`fsum`] here.
//!
//! The parameters are copies of `specifications/tables/stage_k/mar22_drc.json` and
//! `mar23_rrao.json`; a test compares every one with the table (KR-50).
//!
//! Error order (KR-67, HR-122): `E_SCHEMA` in the input layer; `E_LIMIT`; the finite rule (applied
//! by the CLI before these functions run); structural `E_INPUT` (every position checked before any
//! domain rule); `E_DOMAIN`.
#![allow(clippy::neg_cmp_op_on_partial_ord)] // NaN-safe domain checks, as the reference writes them
use crate::error::{QfError, Result, err};
use crate::research_w3::fsum;
use std::collections::{BTreeMap, HashMap, HashSet};

/// KR-69.
pub const LABEL: &str = "regulatory formula on caller inputs; not a regulatory return";
/// KR-55.
pub const RW_SOURCE: &str =
    "securitisation risk weights supplied by the caller (CRE40-CRE44 not implemented)";
/// KR-67.
pub const MAX_POSITIONS: usize = 100_000;

/// MAR22.22 buckets, in output order (KR-302).
pub const BUCKETS: [&str; 3] = ["CORPORATE", "SOVEREIGN", "LOCAL_GOV"];
pub const SENIORITIES: [&str; 4] = ["COVERED", "SENIOR", "NON_SENIOR", "EQUITY"];
pub const RATINGS: [&str; 9] = [
    "AAA",
    "AA",
    "A",
    "BBB",
    "BB",
    "B",
    "CCC",
    "UNRATED",
    "DEFAULTED",
];
/// MAR22.12: loss given default, by seniority (order of [`SENIORITIES`]).
pub const LGD: [f64; 4] = [0.25, 0.75, 1.0, 1.0];
/// KR-53: offsetting rank (a short of rank r offsets longs of rank r or above).
pub const RANK: [i32; 4] = [4, 3, 2, 1];
/// MAR22.24 Table 2: default risk weights, by credit quality (order of [`RATINGS`]).
pub const RISK_WEIGHT: [f64; 9] = [0.005, 0.02, 0.03, 0.06, 0.15, 0.30, 0.50, 0.15, 1.0];
/// MAR22.15, years.
pub const CAPITAL_HORIZON: f64 = 1.0;
/// MAR22.18.
pub const MATURITY_FLOOR: f64 = 0.25;
/// MAR22.16: a cash equity maturity is 0.25 or at least one year.
pub const CASH_EQUITY_SHORT: f64 = 0.25;
/// MAR22.45.
pub const CTP_CROSS_FACTOR: f64 = 0.5;
/// `frtb-drc-rrao.md` Errors: a caller rw above 1250% is `E_DOMAIN`.
pub const RW_CAP: f64 = 12.5;
/// MAR23.8(2): EXOTIC, OTHER.
pub const RRAO_WEIGHT: [f64; 2] = [0.01, 0.001];
pub const KINDS: [&str; 2] = ["EXOTIC", "OTHER"];

fn index_of(list: &[&str], v: &str) -> usize {
    list.iter()
        .position(|x| *x == v)
        .expect("enum value checked by the reader")
}

/// The risk weight of a rating name (MAR22.24 Table 2).
pub fn risk_weight(rating: &str) -> f64 {
    RISK_WEIGHT[index_of(&RATINGS, rating)]
}

fn at(code: &'static str, message: impl Into<String>, field: impl Into<String>) -> QfError {
    let mut e = err(code, message);
    e.field = Some(field.into());
    e
}

/// A non-securitisation position (KR-51). `notional` and `market_value` are signed: long > 0.
#[derive(Debug, Clone, PartialEq)]
pub struct Position {
    pub id: String,
    pub obligor: String,
    pub bucket: String,
    pub seniority: String,
    pub notional: f64,
    pub market_value: f64,
    pub maturity_years: f64,
    pub cash_equity: bool,
    pub lgd_applies: bool,
}

/// A securitisation (non-CTP) position: JTD is the market value (MAR22.27); `rw` from the caller.
#[derive(Debug, Clone, PartialEq)]
pub struct SecPosition {
    pub id: String,
    pub bucket: String,
    pub pool: String,
    pub tranche: String,
    pub market_value: f64,
    pub maturity_years: f64,
    pub rw: f64,
}

/// A correlation trading position: netting key (index, series, tranche), bucket = index (MAR22.39).
#[derive(Debug, Clone, PartialEq)]
pub struct CtpPosition {
    pub id: String,
    pub index: String,
    pub series: String,
    pub tranche: String,
    pub market_value: f64,
    pub maturity_years: f64,
    pub rw: f64,
}

/// An instrument subject to the residual risk add-on (MAR23).
#[derive(Debug, Clone, PartialEq)]
pub struct Instrument {
    pub id: String,
    pub gross_notional: f64,
    pub kind: String,
    pub listed_or_clearable: bool,
    pub back_to_back: bool,
}

/// One row of the `positions` output.
#[derive(Debug, Clone, PartialEq)]
pub struct PositionRow {
    pub id: String,
    /// `None` for securitisation and CTP rows, which report no gross JTD.
    pub gross_jtd: Option<f64>,
    pub weight: f64,
    pub scaled_jtd: f64,
}

/// One row of the `obligors` output.
#[derive(Debug, Clone, PartialEq)]
pub struct ObligorRow {
    pub obligor: String,
    pub net_long: f64,
    pub net_short: f64,
    pub rw: f64,
}

/// One bucket of the non-securitisation and securitisation outputs.
#[derive(Debug, Clone, PartialEq)]
pub struct BucketRow {
    pub bucket: String,
    pub hbr: Option<f64>,
    pub wtd_long: f64,
    pub wtd_short: f64,
    pub drc: f64,
}

/// `risk.frtb.drc_nonsec`.
#[derive(Debug, Clone, PartialEq)]
pub struct NonsecResult {
    pub positions: Vec<PositionRow>,
    pub obligors: Vec<ObligorRow>,
    pub buckets: Vec<BucketRow>,
    pub drc: f64,
}

/// `risk.frtb.drc_sec_nonctp`.
#[derive(Debug, Clone, PartialEq)]
pub struct SecResult {
    pub positions: Vec<PositionRow>,
    pub buckets: Vec<BucketRow>,
    pub drc: f64,
}

/// One CTP bucket (an index): `drc` is not floored (MAR22.44).
#[derive(Debug, Clone, PartialEq)]
pub struct CtpBucket {
    pub bucket: String,
    pub wtd_long: f64,
    pub wtd_short: f64,
    pub drc: f64,
}

/// `risk.frtb.drc_ctp`. In `bucket_drc` mode only `drc` is set (`positions` is `None`).
#[derive(Debug, Clone, PartialEq)]
pub struct CtpResult {
    pub positions: Option<Vec<PositionRow>>,
    pub hbr_ctp: Option<f64>,
    pub buckets: Vec<CtpBucket>,
    pub drc: f64,
}

/// One row of the RRAO output.
#[derive(Debug, Clone, PartialEq)]
pub struct RraoRow {
    pub id: String,
    pub weight: f64,
    pub excluded: bool,
    pub addon: f64,
}

/// `risk.frtb.rrao`.
#[derive(Debug, Clone, PartialEq)]
pub struct RraoResult {
    pub instruments: Vec<RraoRow>,
    pub rrao: f64,
}

/// MAR22.15, MAR22.18, KR-52: 1 at one year or more, else the maturity floored at 0.25.
pub fn maturity_weight(maturity_years: f64) -> f64 {
    if maturity_years >= CAPITAL_HORIZON {
        1.0
    } else {
        // Python `max(m, 0.25)`: the first argument unless the second is larger.
        if MATURITY_FLOOR > maturity_years {
            MATURITY_FLOOR
        } else {
            maturity_years
        }
    }
}

/// MAR22.11, MAR22.12: LGD x notional + P&L, floored at 0 for a long and capped at 0 for a short.
pub fn gross_jtd(p: &Position) -> f64 {
    let lgd = if p.lgd_applies {
        LGD[index_of(&SENIORITIES, &p.seniority)]
    } else {
        1.0
    };
    let pnl = p.market_value - p.notional;
    let raw = lgd * p.notional + pnl;
    if p.notional > 0.0 {
        py_max(raw, 0.0)
    } else if p.notional < 0.0 {
        py_min(raw, 0.0)
    } else {
        0.0
    }
}

/// Python `max(a, b)`: `a` unless `b > a` (so `max(-0.0, 0.0)` is `-0.0`).
fn py_max(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

/// Python `min(a, b)`: `a` unless `b < a`.
fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

/// The (rank, scaled JTD) longs and shorts of one obligor.
type Legs = (Vec<(i32, f64)>, Vec<(i32, f64)>);

fn limit(n: usize, field: &str) -> Result<()> {
    if n > MAX_POSITIONS {
        return Err(at(
            "E_LIMIT",
            format!("{field} is above its limit of {MAX_POSITIONS}"),
            field,
        ));
    }
    Ok(())
}

fn unique<'a>(ids: impl Iterator<Item = &'a str>, field: &str) -> Result<()> {
    let mut seen = HashSet::new();
    for (k, i) in ids.enumerate() {
        if !seen.insert(i) {
            return Err(at(
                "E_INPUT",
                format!("duplicate id {i:?}"),
                format!("{field}/{k}/id"),
            ));
        }
    }
    Ok(())
}

fn maturity(m: f64, path: String) -> Result<()> {
    if !(m > 0.0) {
        return Err(at("E_DOMAIN", "maturity_years must be above 0", path));
    }
    Ok(())
}

/// KR-53 greedy offsetting within one obligor. `longs` and `shorts` are (rank, scaled JTD) in input
/// order (longs > 0, shorts < 0). Shorts are served in descending rank (ties: input order); each
/// consumes the eligible longs (rank at least its own) in ascending rank (ties: input order).
/// Returns (net long >= 0, net short <= 0).
pub fn offset(longs: &[(i32, f64)], shorts: &[(i32, f64)]) -> (f64, f64) {
    let mut left: Vec<(i32, f64)> = longs.to_vec();
    let mut order: Vec<usize> = (0..left.len()).collect();
    order.sort_by_key(|&k| (left[k].0, k));
    let mut short_order: Vec<usize> = (0..shorts.len()).collect();
    short_order.sort_by_key(|&k| (-shorts[k].0, k));
    let mut rest = Vec::new();
    for k in short_order {
        let (rank, mut need) = (shorts[k].0, -shorts[k].1);
        for &j in &order {
            if need <= 0.0 {
                break;
            }
            if left[j].0 < rank || left[j].1 <= 0.0 {
                continue;
            }
            let used = py_min(need, left[j].1);
            left[j].1 -= used;
            need -= used;
        }
        if need > 0.0 {
            rest.push(-need);
        }
    }
    (fsum(left.iter().map(|x| x.1)), fsum(rest))
}

/// MAR22.23, MAR22.25 and KR-54 over (rw, net long, net short) of one bucket.
fn bucket_drc(bucket: &str, pairs: &[(f64, f64, f64)]) -> BucketRow {
    let long_sum = fsum(pairs.iter().map(|p| p.1));
    let short_sum = fsum(pairs.iter().map(|p| -p.2));
    let wtd_long = fsum(pairs.iter().map(|p| p.0 * p.1));
    let wtd_short = fsum(pairs.iter().map(|p| p.0 * -p.2));
    let total = long_sum + short_sum;
    let hbr = (total > 0.0).then(|| long_sum / total);
    let drc = hbr.map_or(0.0, |h| py_max(wtd_long - h * wtd_short, 0.0));
    BucketRow {
        bucket: bucket.to_string(),
        hbr,
        wtd_long,
        wtd_short,
        drc,
    }
}

/// Default risk charge for non-securitisations (MAR22.9 to MAR22.26). `ratings` maps an obligor to
/// its rating name.
pub fn drc_nonsec(
    positions: &[Position],
    ratings: &BTreeMap<String, String>,
) -> Result<NonsecResult> {
    limit(positions.len(), "positions")?;
    if positions.is_empty() {
        return Err(at("E_INPUT", "positions is empty", "positions"));
    }
    unique(positions.iter().map(|p| p.id.as_str()), "positions")?;
    let mut bucket_of: HashMap<&str, &str> = HashMap::new();
    for (k, p) in positions.iter().enumerate() {
        if !ratings.contains_key(&p.obligor) {
            return Err(at(
                "E_INPUT",
                format!("obligor {:?} has no rating", p.obligor),
                format!("positions/{k}/obligor"),
            ));
        }
        // KR-301: one bucket per obligor.
        if *bucket_of.entry(&p.obligor).or_insert(&p.bucket) != p.bucket {
            return Err(at(
                "E_INPUT",
                format!("obligor {:?} is in two buckets", p.obligor),
                format!("positions/{k}/bucket"),
            ));
        }
    }
    for (k, p) in positions.iter().enumerate() {
        let path = format!("positions/{k}");
        maturity(p.maturity_years, format!("{path}/maturity_years"))?;
        if p.cash_equity {
            let m = p.maturity_years;
            if m != CASH_EQUITY_SHORT && m < CAPITAL_HORIZON {
                // KR-52
                return Err(at(
                    "E_DOMAIN",
                    "cash equity maturity must be 0.25 or at least 1",
                    path,
                ));
            }
            if p.seniority != "EQUITY" || p.notional != p.market_value {
                // KR-300
                return Err(at(
                    "E_DOMAIN",
                    "cash equity must be EQUITY with notional = market value",
                    path,
                ));
            }
        }
        if p.notional == 0.0 && p.market_value != 0.0 {
            return Err(at(
                "E_DOMAIN",
                "zero notional with a nonzero market value",
                format!("{path}/notional"),
            ));
        }
    }

    let mut rows = Vec::with_capacity(positions.len());
    let mut legs: BTreeMap<&str, Legs> = BTreeMap::new();
    for p in positions {
        let jtd = gross_jtd(p);
        let w = maturity_weight(p.maturity_years);
        let scaled = w * jtd;
        rows.push(PositionRow {
            id: p.id.clone(),
            gross_jtd: Some(jtd),
            weight: w,
            scaled_jtd: scaled,
        });
        let entry = legs.entry(&p.obligor).or_default();
        let rank = RANK[index_of(&SENIORITIES, &p.seniority)];
        if scaled > 0.0 {
            entry.0.push((rank, scaled));
        } else if scaled < 0.0 {
            entry.1.push((rank, scaled));
        }
    }

    let mut obligors = Vec::with_capacity(legs.len());
    let mut per_bucket: HashMap<&str, Vec<(f64, f64, f64)>> = HashMap::new();
    for (name, (longs, shorts)) in &legs {
        let (net_long, net_short) = offset(longs, shorts);
        let rw = risk_weight(&ratings[*name]);
        obligors.push(ObligorRow {
            obligor: (*name).to_string(),
            net_long,
            net_short,
            rw,
        });
        per_bucket
            .entry(bucket_of[name])
            .or_default()
            .push((rw, net_long, net_short));
    }
    let buckets: Vec<BucketRow> = BUCKETS
        .iter()
        .filter_map(|b| per_bucket.get(b).map(|pairs| bucket_drc(b, pairs)))
        .collect();
    rows.sort_by(|a, b| a.id.cmp(&b.id));
    Ok(NonsecResult {
        positions: rows,
        obligors,
        drc: fsum(buckets.iter().map(|b| b.drc)),
        buckets,
    })
}

fn caller_rw(rws: &[f64], maturities: &[f64], field: &str) -> Result<()> {
    for (k, (&rw, &m)) in rws.iter().zip(maturities).enumerate() {
        maturity(m, format!("{field}/{k}/maturity_years"))?;
        if !(0.0 <= rw && rw <= RW_CAP) {
            return Err(at(
                "E_DOMAIN",
                format!("rw must be in [0, {RW_CAP}]"),
                format!("{field}/{k}/rw"),
            ));
        }
    }
    Ok(())
}

/// Sums the scaled JTDs per netting key (MAR22.29, MAR22.39(1)); one rw per key (KR-303). The keys
/// come back in first-seen order, as a Python dict keeps them.
fn net_groups(
    keys: &[[&str; 3]],
    rws: &[f64],
    scaled: &[f64],
    field: &str,
) -> Result<Vec<([String; 3], f64, f64)>> {
    let mut slot: HashMap<[&str; 3], usize> = HashMap::new();
    let mut groups: Vec<([&str; 3], f64, Vec<f64>)> = Vec::new();
    for (k, (key, &rw)) in keys.iter().zip(rws).enumerate() {
        if let Some(&s) = slot.get(key) {
            if groups[s].1 != rw {
                return Err(at(
                    "E_INPUT",
                    "positions netted together carry different rw",
                    format!("{field}/{k}/rw"),
                ));
            }
        } else {
            slot.insert(*key, groups.len());
            groups.push((*key, rw, Vec::new()));
        }
    }
    for (key, &v) in keys.iter().zip(scaled) {
        groups[slot[key]].2.push(v);
    }
    Ok(groups
        .into_iter()
        .map(|(key, rw, vs)| (key.map(str::to_string), rw, fsum(vs)))
        .collect())
}

/// The maturity weight of a securitisation or CTP position: 0 for a maturity that is not above 0
/// (refused later as `E_DOMAIN`, after the structural checks).
fn weight_or_zero(m: f64) -> f64 {
    if m > 0.0 { maturity_weight(m) } else { 0.0 }
}

fn sorted_rows(ids: &[&str], weights: &[f64], scaled: &[f64]) -> Vec<PositionRow> {
    let mut rows: Vec<PositionRow> = ids
        .iter()
        .zip(weights.iter().zip(scaled))
        .map(|(id, (&w, &v))| PositionRow {
            id: (*id).to_string(),
            gross_jtd: None,
            weight: w,
            scaled_jtd: v,
        })
        .collect();
    rows.sort_by(|a, b| a.id.cmp(&b.id));
    rows
}

/// Default risk charge for securitisations outside the CTP (MAR22.27 to MAR22.35, KR-55).
pub fn drc_sec_nonctp(positions: &[SecPosition]) -> Result<SecResult> {
    limit(positions.len(), "positions")?;
    unique(positions.iter().map(|p| p.id.as_str()), "positions")?;
    let keys: Vec<[&str; 3]> = positions
        .iter()
        .map(|p| [p.bucket.as_str(), p.pool.as_str(), p.tranche.as_str()])
        .collect();
    let rws: Vec<f64> = positions.iter().map(|p| p.rw).collect();
    let weights: Vec<f64> = positions
        .iter()
        .map(|p| weight_or_zero(p.maturity_years))
        .collect();
    let scaled: Vec<f64> = weights
        .iter()
        .zip(positions)
        .map(|(w, p)| w * p.market_value)
        .collect();
    let nets = net_groups(&keys, &rws, &scaled, "positions")?;
    let mats: Vec<f64> = positions.iter().map(|p| p.maturity_years).collect();
    caller_rw(&rws, &mats, "positions")?;
    let mut per_bucket: BTreeMap<String, Vec<(f64, f64, f64)>> = BTreeMap::new();
    for ([bucket, _, _], rw, net) in nets {
        per_bucket
            .entry(bucket)
            .or_default()
            .push((rw, py_max(net, 0.0), py_min(net, 0.0)));
    }
    let buckets: Vec<BucketRow> = per_bucket
        .iter()
        .map(|(b, pairs)| bucket_drc(b, pairs))
        .collect();
    let ids: Vec<&str> = positions.iter().map(|p| p.id.as_str()).collect();
    Ok(SecResult {
        positions: sorted_rows(&ids, &weights, &scaled),
        drc: fsum(buckets.iter().map(|b| b.drc)),
        buckets,
    })
}

/// MAR22.45: `max(sum_b (max(DRC_b, 0) + 0.5 min(DRC_b, 0)), 0)`.
pub fn ctp_total(bucket_drc: &[f64]) -> f64 {
    py_max(
        fsum(
            bucket_drc
                .iter()
                .map(|&d| py_max(d, 0.0) + CTP_CROSS_FACTOR * py_min(d, 0.0)),
        ),
        0.0,
    )
}

/// Default risk charge for the correlation trading portfolio (MAR22.36 to MAR22.45, KR-55).
/// Exactly one of `positions` and `bucket_drc` (a list of index-level `DRC_b`).
pub fn drc_ctp(positions: Option<&[CtpPosition]>, bucket_drc: Option<&[f64]>) -> Result<CtpResult> {
    let positions = match (positions, bucket_drc) {
        (None, Some(b)) => {
            limit(b.len(), "bucket_drc")?;
            return Ok(CtpResult {
                positions: None,
                hbr_ctp: None,
                buckets: Vec::new(),
                drc: ctp_total(b),
            });
        }
        (Some(p), None) => p,
        _ => {
            return Err(at(
                "E_INPUT",
                "give exactly one of positions and bucket_drc",
                "positions",
            ));
        }
    };
    limit(positions.len(), "positions")?;
    unique(positions.iter().map(|p| p.id.as_str()), "positions")?;
    let keys: Vec<[&str; 3]> = positions
        .iter()
        .map(|p| [p.index.as_str(), p.series.as_str(), p.tranche.as_str()])
        .collect();
    let rws: Vec<f64> = positions.iter().map(|p| p.rw).collect();
    let weights: Vec<f64> = positions
        .iter()
        .map(|p| weight_or_zero(p.maturity_years))
        .collect();
    let scaled: Vec<f64> = weights
        .iter()
        .zip(positions)
        .map(|(w, p)| w * p.market_value)
        .collect();
    let nets = net_groups(&keys, &rws, &scaled, "positions")?;
    let mats: Vec<f64> = positions.iter().map(|p| p.maturity_years).collect();
    caller_rw(&rws, &mats, "positions")?;
    let long_sum = fsum(nets.iter().map(|n| py_max(n.2, 0.0)));
    let short_sum = fsum(nets.iter().map(|n| -py_min(n.2, 0.0)));
    let total = long_sum + short_sum;
    let hbr = (total > 0.0).then(|| long_sum / total); // KR-54 analogue
    let mut per_index: BTreeMap<String, Vec<(f64, f64)>> = BTreeMap::new();
    for ([index, _, _], rw, net) in nets {
        per_index.entry(index).or_default().push((rw, net));
    }
    let buckets: Vec<CtpBucket> = per_index
        .into_iter()
        .map(|(index, items)| {
            let wl = fsum(items.iter().filter(|x| x.1 > 0.0).map(|x| x.0 * x.1));
            let ws = fsum(items.iter().filter(|x| x.1 < 0.0).map(|x| x.0 * -x.1));
            let drc = wl - hbr.unwrap_or(0.0) * ws; // MAR22.44: no floor
            CtpBucket {
                bucket: index,
                wtd_long: wl,
                wtd_short: ws,
                drc,
            }
        })
        .collect();
    let ids: Vec<&str> = positions.iter().map(|p| p.id.as_str()).collect();
    let drcs: Vec<f64> = buckets.iter().map(|b| b.drc).collect();
    Ok(CtpResult {
        positions: Some(sorted_rows(&ids, &weights, &scaled)),
        hbr_ctp: hbr,
        drc: ctp_total(&drcs),
        buckets,
    })
}

/// Residual risk add-on (MAR23.7, MAR23.8).
pub fn rrao(instruments: &[Instrument]) -> Result<RraoResult> {
    limit(instruments.len(), "instruments")?;
    unique(instruments.iter().map(|x| x.id.as_str()), "instruments")?;
    for (k, x) in instruments.iter().enumerate() {
        if !(x.gross_notional >= 0.0) {
            return Err(at(
                "E_DOMAIN",
                "gross_notional must be 0 or above",
                format!("instruments/{k}/gross_notional"),
            ));
        }
    }
    let rows: Vec<RraoRow> = instruments
        .iter()
        .map(|x| {
            let excluded = x.back_to_back || (x.kind == "OTHER" && x.listed_or_clearable);
            let w = RRAO_WEIGHT[index_of(&KINDS, &x.kind)];
            RraoRow {
                id: x.id.clone(),
                weight: w,
                excluded,
                addon: if excluded { 0.0 } else { w * x.gross_notional },
            }
        })
        .collect();
    Ok(RraoResult {
        rrao: fsum(rows.iter().map(|r| r.addon)),
        instruments: rows,
    })
}
