//! FRTB internal models approach, plan item K-8f (`specifications/06-risk/frtb-ima.md`; rulings
//! KR-50, KR-56 to KR-61, KR-67 to KR-69 and KR-305 to KR-310 in
//! `specifications/stage-k-rulings-w2.md`): the PLA test, liquidity horizons, ES with the
//! liquidity-horizon cascade, stressed ES, IMCC, the NMRF stress scenario aggregation (SES), the risk
//! factor eligibility test (RFET) and the capital aggregation. A port of
//! `python/quantforge_core/frtb_ima.py`, with the same evaluation order: every `math.fsum` of the
//! reference is the correctly rounded [`fsum`] here, and the rank statistics are exact integers.
//!
//! The parameters are copies of `specifications/tables/stage_k/mar31_rfet.json`, `mar32_pla.json`
//! and `mar33_ima.json`; a test compares every one with the table (KR-50).
#![allow(clippy::neg_cmp_op_on_partial_ord)] // NaN-safe domain checks, as the reference writes them
use crate::dates::{Date, days_in_month};
use crate::error::{QfError, Result, err};
use crate::research_w3::fsum;
use crate::rng::ppnd16;

/// KR-69.
pub const LABEL: &str = "regulatory formula on caller inputs; not a regulatory return";
/// KR-67: P&L points per list.
pub const MAX_PNL: usize = 1_000_000;
/// KR-67: positions, sensitivities, charges, dates.
pub const MAX_LIST: usize = 100_000;

/// MAR32.42 zone thresholds; the KS ones are integer tests on the count `d` (KR-56).
pub const PLA_GREEN_SPEARMAN: f64 = 0.80;
pub const PLA_RED_SPEARMAN: f64 = 0.70;
/// Green needs `100 d < 9 n` (KS below 0.09).
pub const PLA_GREEN_KS_PERCENT: i64 = 9;
/// Red if `100 d > 12 n` (KS above 0.12).
pub const PLA_RED_KS_PERCENT: i64 = 12;
/// MAR32.35.
pub const PLA_WINDOW: usize = 250;
/// KR-56.
pub const PLA_MIN_N: usize = 3;

/// MAR33.3.
pub const ES_CONFIDENCE: f64 = 0.975;
/// MAR33.4, days.
pub const BASE_HORIZON: i64 = 10;
/// MAR33.4 Table 1.
pub const LIQUIDITY_HORIZONS: [i64; 5] = [10, 20, 40, 60, 120];
/// MAR33.12 Table 2.
pub const LH_TABLE: [(&str, i64); 26] = [
    ("IR_specified_ccy", 10),
    ("IR_unspecified_ccy", 20),
    ("IR_volatility", 60),
    ("IR_other", 60),
    ("CS_sovereign_IG", 20),
    ("CS_sovereign_HY", 40),
    ("CS_corporate_IG", 40),
    ("CS_corporate_HY", 60),
    ("CS_volatility", 120),
    ("CS_other", 120),
    ("EQ_large_cap", 10),
    ("EQ_small_cap", 20),
    ("EQ_large_cap_volatility", 20),
    ("EQ_small_cap_volatility", 60),
    ("EQ_other", 60),
    ("FX_specified_pairs", 10),
    ("FX_pairs", 20),
    ("FX_volatility", 40),
    ("FX_other", 40),
    ("COM_energy_carbon", 20),
    ("COM_precious_nonferrous", 20),
    ("COM_other", 60),
    ("COM_energy_carbon_volatility", 60),
    ("COM_precious_nonferrous_volatility", 60),
    ("COM_other_volatility", 120),
    ("COM_other_types", 120),
];
/// MAR33.12 footnote 309: specified currency pairs (either order counts, KR-60).
pub const SPECIFIED_FX_PAIRS: [&str; 23] = [
    "USD/EUR", "USD/JPY", "USD/GBP", "USD/AUD", "USD/CAD", "USD/CHF", "USD/MXN", "USD/CNY",
    "USD/NZD", "USD/RUB", "USD/HKD", "USD/SGD", "USD/TRY", "USD/KRW", "USD/SEK", "USD/ZAR",
    "USD/INR", "USD/NOK", "USD/BRL", "EUR/JPY", "EUR/GBP", "EUR/CHF", "JPY/AUD",
];
/// MAR33.15(2).
pub const IMCC_RHO: f64 = 0.5;
/// MAR33.15 risk classes; output order.
pub const IMCC_CLASSES: [&str; 5] = ["IR", "EQ", "FX", "COM", "CS"];
/// MAR33.17(4).
pub const SES_RHO: f64 = 0.6;
/// MAR32.9 Table 1: the multiplier (1.5 base plus the add-on) by exceptions 0 to 9 (KR-61).
pub const MULTIPLIER: [f64; 10] = [1.50, 1.50, 1.50, 1.50, 1.50, 1.70, 1.76, 1.83, 1.88, 1.92];
/// 10 or more exceptions.
pub const MULTIPLIER_RED: f64 = 2.00;
/// MAR33.45.
pub const SURCHARGE_K: f64 = 0.5;
/// MAR31.13 counts.
pub const RFET_MIN_DAYS: usize = 24;
pub const RFET_WINDOW_DAYS: i64 = 90;
pub const RFET_MIN_PER_WINDOW: usize = 4;
pub const RFET_ALT_MIN_DAYS: usize = 100;
pub const RFET_LOOKBACK_MONTHS: i64 = 12;
/// MAR31.16 Table 1: bucket lower bounds per row (the upper bound is the next lower bound; the last
/// is open, except in row D, which ends below 1).
pub const RFET_BUCKETS: [(&str, &[f64]); 4] = [
    ("A", &[0.0, 0.75, 1.5, 4.0, 7.0, 12.0, 18.0, 25.0, 35.0]),
    ("B", &[0.0, 0.75, 4.0, 10.0, 18.0, 30.0]),
    ("C", &[0.0, 1.5, 3.5, 7.5, 15.0]),
    ("D", &[0.0, 0.05, 0.3, 0.7, 0.95]),
];
pub const RFET_D_UPPER: f64 = 1.0;

fn at(code: &'static str, message: impl Into<String>, field: impl Into<String>) -> QfError {
    let mut e = err(code, message);
    e.field = Some(field.into());
    e
}

/// Python `max(a, b)`: `a` unless `b > a`.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}

/// Python `min(a, b)`: `a` unless `b < a`.
fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

// ---- PLA test (MAR32.34 to MAR32.44, KR-56, KR-305) ----------------------------------------------

/// Twice the average rank (ties share the mean of their positions), so every value is an integer.
pub fn doubled_ranks(x: &[f64]) -> Vec<i64> {
    let mut order: Vec<usize> = (0..x.len()).collect();
    // Stable; -0.0 and 0.0 are adjacent under `total_cmp` and tie under `==`, as in Python.
    order.sort_by(|&a, &b| x[a].total_cmp(&x[b]));
    let mut out = vec![0i64; x.len()];
    let mut i = 0;
    while i < order.len() {
        let mut j = i;
        while j + 1 < order.len() && x[order[j + 1]] == x[order[i]] {
            j += 1;
        }
        let doubled = (i + j + 2) as i64; // ranks i+1 .. j+1, mean (i + j + 2) / 2
        for &k in &order[i..=j] {
            out[k] = doubled;
        }
        i = j + 1;
    }
    out
}

/// MAR32.36 to MAR32.38: Pearson correlation of the average ranks, on centred doubled ranks
/// `2r - (n + 1)` (integers in `[-(n-1), n-1]`, so the sums are exact in `i64` up to n = 1,000,000);
/// one rounding at the end, clamped to [-1, 1].
pub fn spearman(hpl: &[f64], rtpl: &[f64]) -> Result<f64> {
    let n = hpl.len() as i64;
    let a: Vec<i64> = doubled_ranks(hpl).iter().map(|r| r - (n + 1)).collect();
    let b: Vec<i64> = doubled_ranks(rtpl).iter().map(|r| r - (n + 1)).collect();
    let sxy: i64 = a.iter().zip(&b).map(|(u, v)| u * v).sum();
    let sxx: i64 = a.iter().map(|u| u * u).sum();
    let syy: i64 = b.iter().map(|v| v * v).sum();
    if sxx == 0 || syy == 0 {
        return Err(at(
            "E_DOMAIN",
            "a series is constant: its rank variance is 0",
            if sxx == 0 { "hpl" } else { "rtpl" },
        ));
    }
    let r = sxy as f64 / (sxx as f64 * syy as f64).sqrt();
    Ok(py_max(-1.0, py_min(1.0, r)))
}

/// The number of values of an ascending list at or below `x` (Python `bisect_right`).
fn at_or_below(sorted: &[f64], x: f64) -> usize {
    sorted.partition_point(|v| *v <= x)
}

/// MAR32.39 to MAR32.41 in counts: max over pooled x of `|#{rtpl <= x} - #{hpl <= x}|` (KR-56).
pub fn ks_count(hpl: &[f64], rtpl: &[f64]) -> usize {
    let mut h = hpl.to_vec();
    let mut r = rtpl.to_vec();
    h.sort_by(f64::total_cmp);
    r.sort_by(f64::total_cmp);
    h.iter()
        .chain(&r)
        .map(|&x| at_or_below(&r, x).abs_diff(at_or_below(&h, x)))
        .max()
        .unwrap_or(0)
}

/// Kolmogorov tail `Q_KS(x) = 2 sum_{k>=1} (-1)^(k-1) exp(-2 k^2 x^2)` (KR-56), evaluated as KR-305:
/// 1 at x <= 0; for 0 < x < 1 through the theta series
/// `1 - sqrt(2 pi)/x sum_{k>=1} exp(-(2k-1)^2 pi^2 / (8 x^2))`; terms are added until one is 0.
pub fn kolmogorov_q(x: f64) -> f64 {
    if x <= 0.0 {
        return 1.0;
    }
    let mut terms = Vec::new();
    let mut k: i64 = 1;
    if x < 1.0 {
        let c = std::f64::consts::PI * std::f64::consts::PI / (8.0 * x * x);
        loop {
            let t = (-(((2 * k - 1) * (2 * k - 1)) as f64) * c).exp();
            if t == 0.0 {
                break;
            }
            terms.push(t);
            k += 1;
        }
        return py_max(
            0.0,
            1.0 - (2.0 * std::f64::consts::PI).sqrt() / x * fsum(terms),
        );
    }
    loop {
        let t = ((-2 * k * k) as f64 * x * x).exp();
        if t == 0.0 {
            break;
        }
        terms.push(if k % 2 == 1 { t } else { -t });
        k += 1;
    }
    py_min(1.0, 2.0 * fsum(terms))
}

fn pvalue(ks: f64, n: i64) -> f64 {
    kolmogorov_q(ks * (n as f64 / 2.0).sqrt())
}

/// `risk.frtb.pla`.
#[derive(Debug, Clone, PartialEq)]
pub struct PlaResult {
    pub n: usize,
    pub spearman: f64,
    pub ks: f64,
    pub ks_count: usize,
    pub zone: &'static str,
    pub ks_pvalue_asymptotic: f64,
    pub regulatory_window: bool,
}

/// P&L attribution test statistics and zone for one desk (MAR32.34 to MAR32.44).
pub fn pla(hpl: &[f64], rtpl: &[f64]) -> Result<PlaResult> {
    let n = hpl.len();
    if n > MAX_PNL || rtpl.len() > MAX_PNL {
        return Err(at(
            "E_LIMIT",
            format!("a P&L list is above its limit of {MAX_PNL}"),
            if n > MAX_PNL { "hpl" } else { "rtpl" },
        ));
    }
    if rtpl.len() != n {
        return Err(at("E_INPUT", "hpl and rtpl differ in length", "rtpl"));
    }
    if n < PLA_MIN_N {
        return Err(at(
            "E_DOMAIN",
            format!("at least {PLA_MIN_N} observations are needed"),
            "hpl",
        ));
    }
    let rs = spearman(hpl, rtpl)?;
    let d = ks_count(hpl, rtpl);
    let ks = d as f64 / n as f64;
    let (d64, n64) = (d as i64, n as i64);
    let zone = if rs > PLA_GREEN_SPEARMAN && 100 * d64 < PLA_GREEN_KS_PERCENT * n64 {
        "GREEN"
    } else if rs < PLA_RED_SPEARMAN || 100 * d64 > PLA_RED_KS_PERCENT * n64 {
        "RED"
    } else {
        "AMBER"
    };
    Ok(PlaResult {
        n,
        spearman: rs,
        ks,
        ks_count: d,
        zone,
        ks_pvalue_asymptotic: pvalue(ks, n64),
        regulatory_window: n == PLA_WINDOW,
    })
}

/// `Q_KS(ks sqrt(n/2))`, so the printed p-values of MAR32.42 can be checked (KR-305: n >= 1).
pub fn pla_ks_pvalue(ks: f64, n: i64) -> Result<f64> {
    if !(0.0 <= ks && ks <= 1.0) {
        return Err(at("E_DOMAIN", "ks must be in [0, 1]", "ks"));
    }
    if n < 1 {
        return Err(at("E_DOMAIN", "n must be at least 1", "n"));
    }
    Ok(pvalue(ks, n))
}

// ---- Liquidity horizons (MAR33.12, KR-60, KR-306) -------------------------------------------------

fn pair(text: &str) -> (&str, &str) {
    text.split_once('/').unwrap_or((text, ""))
}

fn listed(a: &str, b: &str) -> bool {
    SPECIFIED_FX_PAIRS.iter().any(|p| {
        let (x, y) = pair(p);
        (x == a && y == b) || (x == b && y == a)
    })
}

/// KR-60: listed in footnote 309 in either order, or a first-order cross of two listed pairs.
pub fn fx_pair_specified(text: &str) -> bool {
    let (a, b) = pair(text);
    if listed(a, b) {
        return true;
    }
    SPECIFIED_FX_PAIRS
        .iter()
        .flat_map(|p| {
            let (x, y) = pair(p);
            [x, y]
        })
        .any(|c| c != a && c != b && listed(a, c) && listed(b, c))
}

fn next_horizon(x: f64) -> i64 {
    LIQUIDITY_HORIZONS
        .iter()
        .copied()
        .find(|&h| h as f64 >= x)
        .unwrap_or(LIQUIDITY_HORIZONS[4])
}

/// The Table 2 horizon of a category name, `None` when it is not listed.
pub fn table_horizon(category: &str) -> Option<i64> {
    LH_TABLE.iter().find(|r| r.0 == category).map(|r| r.1)
}

/// `risk.frtb.ima.lh`.
#[derive(Debug, Clone, PartialEq)]
pub struct LhResult {
    pub n: i64,
    pub table_n: i64,
    pub rule: String,
}

/// MAR33.12 Table 2, footnote 309, FAQ4 (maturity) and FAQ5 (index constituents); KR-60, KR-306.
/// Exactly one of `category`, `fx_pair` and `constituents` ((weight, n) pairs).
pub fn liquidity_horizon(
    category: Option<&str>,
    fx_pair: Option<&str>,
    constituents: Option<&[(f64, i64)]>,
    maturity_days: Option<f64>,
) -> Result<LhResult> {
    let given = usize::from(category.is_some())
        + usize::from(fx_pair.is_some())
        + usize::from(constituents.is_some());
    if given != 1 {
        return Err(at(
            "E_INPUT",
            "give exactly one of category, fx_pair and constituents",
            "category",
        ));
    }
    if let Some(c) = constituents {
        if c.is_empty() {
            return Err(at("E_INPUT", "constituents is empty", "constituents"));
        }
        if c.len() > MAX_LIST {
            return Err(at(
                "E_LIMIT",
                format!("constituents is above its limit of {MAX_LIST}"),
                "constituents",
            ));
        }
    }
    if let Some(p) = fx_pair {
        let (a, b) = pair(p);
        if a == b {
            return Err(at(
                "E_DOMAIN",
                "an FX pair needs two different currencies",
                "fx_pair",
            ));
        }
    }
    if let Some(m) = maturity_days
        && !(m > 0.0)
    {
        return Err(at(
            "E_DOMAIN",
            "maturity_days must be above 0",
            "maturity_days",
        ));
    }
    if let Some(c) = constituents {
        for (k, &(w, h)) in c.iter().enumerate() {
            if !(w >= 0.0) {
                return Err(at(
                    "E_DOMAIN",
                    "a constituent weight is negative",
                    format!("constituents/{k}/weight"),
                ));
            }
            if !LIQUIDITY_HORIZONS.contains(&h) {
                return Err(at(
                    "E_DOMAIN",
                    "a constituent n is not 10, 20, 40, 60 or 120",
                    format!("constituents/{k}/n"),
                ));
            }
        }
        let total = fsum(c.iter().map(|x| x.0));
        if (total - 1.0).abs() > 1e-12 {
            return Err(at(
                "E_DOMAIN",
                "constituent weights must sum to 1 within 1e-12",
                "constituents",
            ));
        }
    }
    let (base, mut rule) = if let Some(cat) = category {
        let base = table_horizon(cat)
            .ok_or_else(|| at("E_SCHEMA", "category is not a Table 2 category", "category"))?;
        (base, "table".to_string())
    } else if let Some(p) = fx_pair {
        let key = if fx_pair_specified(p) {
            "FX_specified_pairs"
        } else {
            "FX_pairs"
        };
        (
            table_horizon(key).unwrap_or(LIQUIDITY_HORIZONS[1]),
            "fx_pair".to_string(),
        )
    } else {
        let c = constituents.unwrap_or_default();
        let weighted = fsum(c.iter().map(|&(w, h)| w * h as f64));
        (next_horizon(weighted), "index".to_string())
    };
    let mut n = base;
    if let Some(m) = maturity_days
        && m < base as f64
    {
        n = next_horizon(m);
        rule.push_str("+maturity");
    }
    Ok(LhResult {
        n,
        table_n: base,
        rule,
    })
}

// ---- ES with liquidity horizons, stressed ES, IMCC, SES (MAR33.4 to MAR33.17) ---------------------

/// KR-57, for documentation; the code computes the factor.
pub const NORMAL_ES_FACTOR_DOC: f64 = 2.337802792201415;

/// `phi(z) / (1 - 0.975)` with `z = Phi^-1(0.975)` (KR-57).
pub fn normal_es_factor() -> f64 {
    let z = ppnd16(ES_CONFIDENCE);
    (-z * z / 2.0).exp() / (2.0 * std::f64::consts::PI).sqrt() / (1.0 - ES_CONFIDENCE)
}

/// `(LH_j - LH_{j-1}) / T` with 1 for j = 1: (1, 1, 2, 2, 6) (MAR33.4).
pub fn horizon_weights() -> [f64; 5] {
    let mut out = [0.0; 5];
    let mut prev = 0;
    for (j, &h) in LIQUIDITY_HORIZONS.iter().enumerate() {
        out[j] = if j == 0 {
            1.0
        } else {
            (h - prev) as f64 / BASE_HORIZON as f64
        };
        prev = h;
    }
    out
}

/// MAR33.4: `sqrt(ES_1^2 + sum_{j>=2} (ES_j sqrt((LH_j - LH_{j-1}) / 10))^2)`.
pub fn es_cascade(es_by_horizon: &[f64]) -> f64 {
    fsum(
        horizon_weights()
            .iter()
            .zip(es_by_horizon)
            .map(|(w, e)| w * e * e),
    )
    .sqrt()
}

/// The historical ES at 0.975 of a P&L list (rulings F-31 and R6-3.1, the `risk.var.historical`
/// arithmetic of the Python reference: tail sum with `fsum`).
pub fn historical_es(pnl: &[f64], c: f64) -> f64 {
    let mut down: Vec<f64> = pnl.iter().map(|v| -v).collect();
    down.sort_by(|a, b| b.total_cmp(a));
    let n = down.len();
    let nf = n as f64;
    let w = nf - nf * c;
    if w <= 0.0 {
        return down[0];
    }
    let m = w.floor() as usize;
    let mut parts: Vec<f64> = down[..m.min(n)].to_vec();
    if m < n && w > m as f64 {
        parts.push((w - m as f64) * down[m]);
    }
    fsum(parts) / w
}

/// `risk.frtb.ima.es_lh`.
#[derive(Debug, Clone, PartialEq)]
pub struct EsLhResult {
    pub mode: &'static str,
    pub es_by_horizon: Vec<f64>,
    pub es: f64,
}

/// Liquidity-horizon-adjusted ES (MAR33.4, KR-57). Exactly one of the three inputs, five entries.
pub fn es_lh(
    es_t: Option<&[f64]>,
    sigma: Option<&[f64]>,
    pnl: Option<&[Vec<f64>]>,
) -> Result<EsLhResult> {
    if let Some(p) = pnl {
        for (j, lst) in p.iter().enumerate() {
            if lst.len() > MAX_PNL {
                return Err(at(
                    "E_LIMIT",
                    format!("a P&L list is above its limit of {MAX_PNL}"),
                    format!("pnl/{j}"),
                ));
            }
        }
    }
    let given =
        usize::from(es_t.is_some()) + usize::from(sigma.is_some()) + usize::from(pnl.is_some());
    if given != 1 {
        return Err(at(
            "E_INPUT",
            "give exactly one of es_t, sigma and pnl",
            "es_t",
        ));
    }
    let (field, len) = match (es_t, sigma, pnl) {
        (Some(v), _, _) => ("es_t", v.len()),
        (_, Some(v), _) => ("sigma", v.len()),
        (_, _, Some(v)) => ("pnl", v.len()),
        _ => unreachable!("exactly one input is given"),
    };
    if len != LIQUIDITY_HORIZONS.len() {
        return Err(at(
            "E_INPUT",
            format!("{field} must have exactly five entries"),
            field,
        ));
    }
    let es: Vec<f64> = if let Some(p) = pnl {
        let mut es = Vec::with_capacity(5);
        for (j, lst) in p.iter().enumerate() {
            let v = if lst.is_empty() {
                0.0
            } else {
                historical_es(lst, ES_CONFIDENCE)
            };
            if v < 0.0 {
                // KR-307
                return Err(at(
                    "E_DOMAIN",
                    "the ES of a P&L list is negative (its tail is a gain)",
                    format!("pnl/{j}"),
                ));
            }
            es.push(v);
        }
        es
    } else {
        let nums = es_t.or(sigma).unwrap_or_default();
        for (j, &v) in nums.iter().enumerate() {
            if v < 0.0 {
                return Err(at(
                    "E_DOMAIN",
                    format!("{field} entries must be 0 or above"),
                    format!("{field}/{j}"),
                ));
            }
        }
        if sigma.is_some() {
            let f = normal_es_factor();
            nums.iter().map(|s| f * s).collect()
        } else {
            nums.to_vec()
        }
    };
    Ok(EsLhResult {
        mode: field,
        es: es_cascade(&es),
        es_by_horizon: es,
    })
}

/// (ratio, floored, `ES_R,S max(1, ratio)`) of one (`es_rs`, `es_fc`, `es_rc`) triple.
fn stressed(t: [f64; 3]) -> (f64, bool, f64) {
    let [es_rs, es_fc, es_rc] = t;
    let ratio = es_fc / es_rc;
    (ratio, ratio < 1.0, es_rs * py_max(1.0, ratio))
}

fn triple_domain(t: [f64; 3], path: &str) -> Result<()> {
    let [es_rs, es_fc, es_rc] = t;
    if es_rs < 0.0 || es_fc < 0.0 {
        return Err(at("E_DOMAIN", "ES must be 0 or above", path));
    }
    if !(es_rc > 0.0) {
        return Err(at(
            "E_DOMAIN",
            "es_rc must be above 0",
            format!("{path}es_rc"),
        ));
    }
    Ok(())
}

/// `risk.frtb.ima.es_stressed`: (ratio, `ratio_floored`, es). MAR33.6 with the ratio floored at 1
/// (KR-58).
pub fn es_stressed(es_rs: f64, es_fc: f64, es_rc: f64) -> Result<(f64, bool, f64)> {
    triple_domain([es_rs, es_fc, es_rc], "")?;
    Ok(stressed([es_rs, es_fc, es_rc]))
}

/// `risk.frtb.ima.imcc`.
#[derive(Debug, Clone, PartialEq)]
pub struct ImccResult {
    pub imcc_c: f64,
    pub portfolio_floored: bool,
    /// Present classes in [`IMCC_CLASSES`] order.
    pub classes: Vec<(&'static str, f64)>,
    pub classes_floored: Vec<&'static str>,
    pub imcc: f64,
}

/// MAR33.15: `0.5 IMCC(C) + 0.5 sum_i IMCC(C_i)`, each from (`es_rs`, `es_fc`, `es_rc`) (KR-58).
/// `classes` holds (class name, triple); a name outside [`IMCC_CLASSES`] is `E_SCHEMA`.
pub fn imcc(portfolio: [f64; 3], classes: &[(String, [f64; 3])]) -> Result<ImccResult> {
    if let Some((name, _)) = classes
        .iter()
        .find(|c| !IMCC_CLASSES.contains(&c.0.as_str()))
    {
        return Err(at(
            "E_SCHEMA",
            "not a risk class (IR, EQ, FX, COM, CS)",
            format!("classes.{name}"),
        ));
    }
    if classes.is_empty() {
        return Err(at("E_INPUT", "classes is empty", "classes"));
    }
    let find = |c: &str| classes.iter().find(|x| x.0 == c).map(|x| x.1);
    triple_domain(portfolio, "portfolio.")?;
    for c in IMCC_CLASSES {
        if let Some(t) = find(c) {
            triple_domain(t, &format!("classes.{c}."))?;
        }
    }
    let (_, whole_floored, whole) = stressed(portfolio);
    let per: Vec<(&'static str, (f64, bool, f64))> = IMCC_CLASSES
        .iter()
        .filter_map(|&c| find(c).map(|t| (c, stressed(t))))
        .collect();
    let total = IMCC_RHO * whole + (1.0 - IMCC_RHO) * fsum(per.iter().map(|v| v.1.2));
    Ok(ImccResult {
        imcc_c: whole,
        portfolio_floored: whole_floored,
        classes: per.iter().map(|v| (v.0, v.1.2)).collect(),
        classes_floored: per.iter().filter(|v| v.1.1).map(|v| v.0).collect(),
        imcc: total,
    })
}

/// `risk.frtb.ima.ses`: (`idio_credit`, `idio_equity`, other, ses).
/// MAR33.17: `sqrt(sum ISES_i^2) + sqrt(sum ISES_j^2) + sqrt((0.6 sum SES_k)^2 + 0.64 sum SES_k^2)`.
pub fn ses(idio_credit: &[f64], idio_equity: &[f64], other: &[f64]) -> Result<[f64; 4]> {
    let lists = [
        ("idio_credit", idio_credit),
        ("idio_equity", idio_equity),
        ("other", other),
    ];
    for (name, lst) in lists {
        if lst.len() > MAX_LIST {
            return Err(at(
                "E_LIMIT",
                format!("{name} is above its limit of {MAX_LIST}"),
                name,
            ));
        }
    }
    for (name, lst) in lists {
        if let Some(k) = lst.iter().position(|v| *v < 0.0) {
            return Err(at(
                "E_DOMAIN",
                "a stress scenario charge is negative",
                format!("{name}/{k}"),
            ));
        }
    }
    let a = fsum(idio_credit.iter().map(|v| v * v)).sqrt();
    let b = fsum(idio_equity.iter().map(|v| v * v)).sqrt();
    let s = fsum(other.iter().copied());
    let c = ((SES_RHO * s).powi(2) + (1.0 - SES_RHO * SES_RHO) * fsum(other.iter().map(|v| v * v)))
        .sqrt();
    Ok([a, b, c, a + b + c])
}

// ---- Capital (MAR33.41 to MAR33.45, KR-61, KR-308) ------------------------------------------------

/// MAR32.9 Table 1 (KR-61).
pub fn multiplier(exceptions: i64) -> f64 {
    usize::try_from(exceptions)
        .ok()
        .and_then(|e| MULTIPLIER.get(e).copied())
        .unwrap_or(MULTIPLIER_RED)
}

/// The inputs of `risk.frtb.ima.capital`. `desks`: (zone, sa) with zone GREEN or AMBER.
#[derive(Debug, Clone, PartialEq)]
pub struct CapitalInputs {
    pub imcc_prev: f64,
    pub ses_prev: f64,
    pub imcc_avg: f64,
    pub ses_avg: f64,
    pub exceptions: i64,
    pub drc: f64,
    pub desks: Vec<(String, f64)>,
    pub c_u: f64,
    pub sa_all: f64,
    pub qualitative_addon: f64,
}

/// `risk.frtb.ima.capital`.
#[derive(Debug, Clone, PartialEq)]
pub struct CapitalResult {
    pub m_c: f64,
    pub c_a: f64,
    pub ima_ga: f64,
    pub sa_ga: f64,
    pub k: f64,
    pub surcharge: f64,
    pub acr_total: f64,
}

/// Aggregate capital requirement for market risk (MAR33.41 to MAR33.45).
pub fn capital(x: &CapitalInputs) -> Result<CapitalResult> {
    if x.desks.len() > MAX_LIST {
        return Err(at(
            "E_LIMIT",
            format!("desks is above its limit of {MAX_LIST}"),
            "desks",
        ));
    }
    for (name, v) in [
        ("imcc_prev", x.imcc_prev),
        ("ses_prev", x.ses_prev),
        ("imcc_avg", x.imcc_avg),
        ("ses_avg", x.ses_avg),
        ("drc", x.drc),
        ("c_u", x.c_u),
        ("sa_all", x.sa_all),
        ("qualitative_addon", x.qualitative_addon),
    ] {
        if v < 0.0 {
            // KR-308
            return Err(at("E_DOMAIN", format!("{name} must be 0 or above"), name));
        }
    }
    if x.exceptions < 0 {
        return Err(at(
            "E_DOMAIN",
            "exceptions must be 0 or above",
            "exceptions",
        ));
    }
    if let Some(j) = x.desks.iter().position(|d| d.1 < 0.0) {
        // KR-308
        return Err(at(
            "E_DOMAIN",
            "a desk SA must be 0 or above",
            format!("desks/{j}/sa"),
        ));
    }
    let sa_ga = fsum(x.desks.iter().map(|d| d.1));
    let amber = fsum(x.desks.iter().filter(|d| d.0 == "AMBER").map(|d| d.1));
    let has_amber = x.desks.iter().any(|d| d.0 == "AMBER");
    if has_amber && sa_ga == 0.0 {
        return Err(at(
            "E_DOMAIN",
            "SA over the green and amber desks is 0 with an amber desk",
            "desks",
        ));
    }
    let m_c = multiplier(x.exceptions) + x.qualitative_addon;
    let c_a = py_max(x.imcc_prev + x.ses_prev, m_c * x.imcc_avg + x.ses_avg);
    let ima_ga = c_a + x.drc;
    let k = if has_amber {
        SURCHARGE_K * amber / sa_ga
    } else {
        0.0
    };
    let surcharge = k * py_max(0.0, sa_ga - ima_ga);
    let acr_total = py_min(ima_ga + surcharge + x.c_u, x.sa_all) + py_max(0.0, ima_ga - sa_ga);
    Ok(CapitalResult {
        m_c,
        c_a,
        ima_ga,
        sa_ga,
        k,
        surcharge,
        acr_total,
    })
}

// ---- RFET (MAR31.12 to MAR31.16, KR-59) -----------------------------------------------------------

/// Calendar months back, the day clamped to the end of the target month (KR-59).
pub fn months_back(d: Date, months: i64) -> Date {
    let total = i64::from(d.y) * 12 + i64::from(d.m) - 1 - months;
    let (y, m) = (
        total.div_euclid(12) as i32,
        (total.rem_euclid(12) + 1) as u32,
    );
    Date::new(y, m, d.d.min(days_in_month(y, m)))
}

/// `risk.frtb.rfet`.
#[derive(Debug, Clone, PartialEq)]
pub struct RfetResult {
    pub window_start: Date,
    pub distinct_days: usize,
    pub min_window_count: Option<usize>,
    pub first_failing_window_start: Option<Date>,
    pub first_failing_window_count: Option<usize>,
    pub crit1: bool,
    pub crit2: bool,
    pub pass: bool,
}

/// Risk factor eligibility test on real-price observation dates (MAR31.13, KR-59).
pub fn rfet(as_of: Date, observations: &[Date]) -> Result<RfetResult> {
    if observations.len() > MAX_LIST {
        return Err(at(
            "E_LIMIT",
            format!("observations is above its limit of {MAX_LIST}"),
            "observations",
        ));
    }
    let start = months_back(as_of, RFET_LOOKBACK_MONTHS).add_days(1);
    let mut ordinals: Vec<i64> = observations
        .iter()
        .filter(|d| start <= **d && **d <= as_of)
        .map(|d| d.serial())
        .collect();
    ordinals.sort_unstable();
    ordinals.dedup();
    let below = |x: i64| ordinals.partition_point(|v| *v <= x);
    let (mut first_bad, mut first_bad_count, mut lowest) = (None, None, None::<usize>);
    let last = as_of.serial() - (RFET_WINDOW_DAYS - 1);
    let mut lo = start.serial();
    while lo <= last {
        let count = below(lo + RFET_WINDOW_DAYS - 1) - below(lo - 1);
        lowest = Some(lowest.map_or(count, |l| l.min(count)));
        if first_bad.is_none() && count < RFET_MIN_PER_WINDOW {
            first_bad = Some(Date::from_serial(lo));
            first_bad_count = Some(count);
        }
        lo += 1;
    }
    let distinct = ordinals.len();
    let crit1 = distinct >= RFET_MIN_DAYS && first_bad.is_none();
    let crit2 = distinct >= RFET_ALT_MIN_DAYS;
    Ok(RfetResult {
        window_start: start,
        distinct_days: distinct,
        min_window_count: lowest,
        first_failing_window_start: first_bad,
        first_failing_window_count: first_bad_count,
        crit1,
        crit2,
        pass: crit1 || crit2,
    })
}

/// `risk.frtb.rfet.bucket`: (bucket, lower, upper).
/// MAR31.16 Table 1 bucket (1-based), lower bound inclusive, upper exclusive (KR-59). Rows A to C
/// take a maturity `t` in years, row D an option `delta` (KR-309).
pub fn rfet_bucket(
    row: &str,
    t: Option<f64>,
    delta: Option<f64>,
) -> Result<(usize, f64, Option<f64>)> {
    let is_d = row == "D";
    let field = if is_d { "delta" } else { "t" };
    let (wanted, other) = if is_d { (delta, t) } else { (t, delta) };
    let Some(value) = wanted.filter(|_| other.is_none()) else {
        return Err(at(
            "E_INPUT",
            format!("row {row} takes {field} and nothing else"),
            field,
        ));
    };
    if !(value >= 0.0) {
        return Err(at("E_DOMAIN", format!("{field} must be 0 or above"), field));
    }
    if is_d && !(value < RFET_D_UPPER) {
        return Err(at("E_DOMAIN", "delta must be below 1", "delta"));
    }
    let lows = RFET_BUCKETS
        .iter()
        .find(|r| r.0 == row)
        .map(|r| r.1)
        .ok_or_else(|| at("E_SCHEMA", "row is not A, B, C or D", "row"))?;
    let b = lows.partition_point(|v| *v <= value);
    let upper = if b < lows.len() {
        Some(lows[b])
    } else {
        is_d.then_some(RFET_D_UPPER)
    };
    Ok((b, lows[b - 1], upper))
}
