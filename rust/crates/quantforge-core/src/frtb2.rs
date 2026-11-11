//! FRTB standardised delta for FX, equity, CSR (non-securitisation) and commodity
//! (`06-risk/frtb-sa-fx-equity.md`, rulings G-48, G-49), on the MAR21.4 aggregation and the
//! MAR21.6 scenarios of `frtb-sa-girr.md`.
use crate::error::{Result, fail};
use crate::frtb::{Bucket, GirrDelta, Scenario};

/// One weighted sensitivity with the attributes its correlations need.
#[derive(Debug, Clone)]
struct Ws {
    /// Risk-factor key inside the bucket (netting for simple-sum buckets).
    key: String,
    /// Name (issuer, commodity, pair).
    name: String,
    /// Kind, tenor, curve, location (class-specific).
    a: String,
    b: String,
    value: f64,
}

fn scale(x: f64, scenario: &str) -> f64 {
    match scenario {
        "high" => (1.25 * x).min(1.0),
        "low" => (2.0 * x - 1.0).max(0.75 * x),
        _ => x,
    }
}

/// Bucket definition for the generic SBM aggregation.
struct Class<'a> {
    /// Medium intra-bucket correlation of two factors in bucket `b`.
    rho: &'a dyn Fn(i64, &Ws, &Ws) -> f64,
    /// Medium cross-bucket correlation.
    gamma: &'a dyn Fn(i64, i64) -> Result<f64>,
    /// Other-sector bucket aggregated as a simple sum of absolute netted WS.
    simple: Option<i64>,
}

/// MAR21.4 aggregation with the three MAR21.6 scenarios; buckets in the given order.
fn sbm(buckets: &[(String, i64, Vec<Ws>)], class: &Class) -> Result<GirrDelta> {
    let mut gam = vec![vec![0.0; buckets.len()]; buckets.len()];
    for (i, bi) in buckets.iter().enumerate() {
        for (j, bj) in buckets.iter().enumerate() {
            if i != j {
                gam[i][j] = (class.gamma)(bi.1, bj.1)?;
            }
        }
    }
    let mut scenarios = Vec::new();
    for name in ["high", "medium", "low"] {
        let mut out = Vec::new();
        for (label, b, items) in buckets {
            let s: f64 = items.iter().map(|x| x.value).sum();
            let k = if class.simple == Some(*b) {
                let mut net: Vec<(&str, f64)> = Vec::new();
                for w in items {
                    match net.iter_mut().find(|n| n.0 == w.key) {
                        Some(n) => n.1 += w.value,
                        None => net.push((&w.key, w.value)),
                    }
                }
                net.iter().map(|n| n.1.abs()).sum()
            } else {
                let mut sum = 0.0;
                for (i, x) in items.iter().enumerate() {
                    sum += x.value * x.value;
                    for (j, y) in items.iter().enumerate() {
                        if i != j {
                            sum += scale((class.rho)(*b, x, y), name) * x.value * y.value;
                        }
                    }
                }
                sum.max(0.0).sqrt()
            };
            out.push(Bucket {
                currency: label.clone(),
                k,
                s,
                s_used: s,
            });
        }
        let total = |o: &[Bucket]| -> f64 {
            let mut t: f64 = o.iter().map(|x| x.k * x.k).sum();
            for i in 0..o.len() {
                for j in 0..o.len() {
                    if i != j {
                        t += scale(gam[i][j], name) * o[i].s_used * o[j].s_used;
                    }
                }
            }
            t
        };
        let mut t = total(&out);
        let mut alternative = false;
        if t < 0.0 {
            alternative = true;
            for b in &mut out {
                b.s_used = b.s.min(b.k).max(-b.k);
            }
            t = total(&out).max(0.0);
        }
        scenarios.push(Scenario {
            name,
            buckets: out,
            delta: t.sqrt(),
            alternative_used: alternative,
        });
    }
    let mut best = 0;
    for i in 1..3 {
        if scenarios[i].delta > scenarios[best].delta {
            best = i;
        }
    }
    Ok(GirrDelta {
        capital: scenarios[best].delta,
        binding_scenario: scenarios[best].name,
        scenarios,
    })
}

fn group(items: Vec<(i64, String, Ws)>) -> Result<Vec<(String, i64, Vec<Ws>)>> {
    if items.is_empty() {
        return fail("E_INPUT", "no sensitivities");
    }
    let mut seen = std::collections::HashSet::new();
    for (b, _, w) in &items {
        crate::error::finite("sensitivity", &w.value)?;
        if !seen.insert((*b, w.key.clone())) {
            return fail("E_INPUT", "the same risk factor twice");
        }
    }
    let mut out: Vec<(String, i64, Vec<Ws>)> = Vec::new();
    for (b, label, w) in items {
        match out.iter_mut().find(|x| x.0 == label) {
            Some(x) => x.2.push(w),
            None => out.push((label, b, vec![w])),
        }
    }
    Ok(out)
}

fn ws(key: String, name: &str, a: &str, b: &str, ws: f64) -> Ws {
    Ws {
        key,
        name: name.into(),
        a: a.into(),
        b: b.into(),
        value: ws,
    }
}

/// `risk.frtb.fx_delta`: `(pair, sensitivity)`; pairs in `specified` get `RW / sqrt 2`.
pub fn fx_delta(sens: &[(String, f64)], specified: &[String]) -> Result<GirrDelta> {
    let items = sens
        .iter()
        .map(|(p, s)| {
            let mut rw = 0.15;
            if specified.contains(p) {
                rw /= 2f64.sqrt();
            }
            (0, p.clone(), ws(p.clone(), p, "", "", rw * s))
        })
        .collect();
    let mut g = group(items)?;
    g.sort_by(|a, b| a.0.cmp(&b.0));
    sbm(
        &g,
        &Class {
            rho: &|_, _, _| 1.0,
            gamma: &|_, _| Ok(0.6),
            simple: None,
        },
    )
}

/// An equity sensitivity: issuer, bucket 1 to 13, `SPOT` or `REPO`.
#[derive(Debug, Clone)]
pub struct EquitySens {
    /// Issuer.
    pub issuer: String,
    /// Bucket 1 to 13.
    pub bucket: i64,
    /// `SPOT` or `REPO`.
    pub kind: String,
    /// Sensitivity.
    pub sensitivity: f64,
}

/// `risk.frtb.equity_delta` (MAR21.77 to 21.80; bucket 11 by MAR21.79).
pub fn equity_delta(sens: &[EquitySens]) -> Result<GirrDelta> {
    const RW: [f64; 13] = [
        0.55, 0.60, 0.45, 0.55, 0.30, 0.35, 0.40, 0.50, 0.70, 0.50, 0.70, 0.15, 0.25,
    ];
    let mut items = Vec::new();
    for s in sens {
        if !(1..=13).contains(&s.bucket) || !matches!(s.kind.as_str(), "SPOT" | "REPO") {
            return fail(
                "E_INPUT",
                "equity bucket must be 1 to 13 and kind SPOT or REPO",
            );
        }
        #[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
        let mut rw = RW[(s.bucket - 1) as usize];
        if s.kind == "REPO" {
            rw /= 100.0;
        }
        let key = format!("{}\u{0}{}", s.issuer, s.kind);
        items.push((
            s.bucket,
            s.bucket.to_string(),
            ws(key, &s.issuer, &s.kind, "", rw * s.sensitivity),
        ));
    }
    let mut g = group(items)?;
    g.sort_by_key(|x| x.1);
    let rho = |b: i64, x: &Ws, y: &Ws| -> f64 {
        if x.name == y.name {
            return 0.999;
        }
        let base = match b {
            1..=4 => 0.15,
            5..=8 => 0.25,
            9 => 0.075,
            10 => 0.125,
            _ => 0.80,
        };
        if x.a == y.a { base } else { base * 0.999 }
    };
    let gamma = |b: i64, c: i64| -> Result<f64> {
        Ok(if b == 11 || c == 11 {
            0.0
        } else if b <= 10 && c <= 10 {
            0.15
        } else if (b, c) == (12, 13) || (b, c) == (13, 12) {
            0.75
        } else {
            0.45
        })
    };
    sbm(
        &g,
        &Class {
            rho: &rho,
            gamma: &gamma,
            simple: Some(11),
        },
    )
}

/// A CSR sensitivity: issuer, bucket 1 to 18, tenor, `BOND` or `CDS` curve.
#[derive(Debug, Clone)]
pub struct CsrSens {
    /// Issuer.
    pub issuer: String,
    /// Bucket 1 to 18.
    pub bucket: i64,
    /// `0.5Y`, `1Y`, `3Y`, `5Y` or `10Y`.
    pub tenor: String,
    /// `BOND` or `CDS`.
    pub curve: String,
    /// Sensitivity.
    pub sensitivity: f64,
}

/// Sector of a CSR bucket: 1 to 8 for buckets 1 to 15, then 16, 17, 18.
fn csr_sector(b: i64) -> i64 {
    if b <= 8 {
        b
    } else if b <= 15 {
        b - 8
    } else {
        b
    }
}

/// `risk.frtb.csr_delta` (MAR21.51 to 21.57). Cross-sector correlations between two of the
/// sectors 1 to 8 (MAR21.57 Table 5 body) are not in the spec text: such a pair is `E_INPUT`
/// until the owner confirms the table (G-49 owner item).
pub fn csr_delta(sens: &[CsrSens]) -> Result<GirrDelta> {
    const RW: [f64; 18] = [
        0.005, 0.01, 0.05, 0.03, 0.03, 0.02, 0.015, 0.025, 0.02, 0.04, 0.12, 0.07, 0.085, 0.055,
        0.05, 0.12, 0.015, 0.05,
    ];
    let mut items = Vec::new();
    for s in sens {
        if !(1..=18).contains(&s.bucket)
            || !matches!(s.tenor.as_str(), "0.5Y" | "1Y" | "3Y" | "5Y" | "10Y")
            || !matches!(s.curve.as_str(), "BOND" | "CDS")
        {
            return fail(
                "E_INPUT",
                "CSR bucket 1 to 18, tenor 0.5Y/1Y/3Y/5Y/10Y, curve BOND/CDS",
            );
        }
        #[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
        let rw = RW[(s.bucket - 1) as usize];
        let key = format!("{}\u{0}{}\u{0}{}", s.issuer, s.tenor, s.curve);
        items.push((
            s.bucket,
            s.bucket.to_string(),
            ws(key, &s.issuer, &s.tenor, &s.curve, rw * s.sensitivity),
        ));
    }
    let mut g = group(items)?;
    g.sort_by_key(|x| x.1);
    let rho = |b: i64, x: &Ws, y: &Ws| -> f64 {
        let name = if x.name == y.name {
            1.0
        } else if b >= 17 {
            0.80
        } else {
            0.35
        };
        let tenor = if x.a == y.a { 1.0 } else { 0.65 };
        let basis = if x.b == y.b { 1.0 } else { 0.999 };
        name * tenor * basis
    };
    let gamma = |b: i64, c: i64| -> Result<f64> {
        let rating = if b <= 15 && c <= 15 && ((b <= 8) != (c <= 8)) {
            0.5
        } else {
            1.0
        };
        let (sb, sc) = (csr_sector(b), csr_sector(c));
        let sector = if sb == 16 || sc == 16 {
            0.0
        } else if sb == sc {
            1.0
        } else if (sb, sc) == (17, 18) || (sb, sc) == (18, 17) {
            0.75
        } else if sb >= 17 || sc >= 17 {
            0.45
        } else {
            return fail(
                "E_INPUT",
                "CSR sector pair correlation (MAR21.57 Table 5) is not specified yet",
            );
        };
        Ok(rating * sector)
    };
    sbm(
        &g,
        &Class {
            rho: &rho,
            gamma: &gamma,
            simple: Some(16),
        },
    )
}

/// A commodity sensitivity.
#[derive(Debug, Clone)]
pub struct CommoditySens {
    /// Commodity name.
    pub commodity: String,
    /// Bucket 1 to 11.
    pub bucket: i64,
    /// Tenor label.
    pub tenor: String,
    /// Delivery location.
    pub location: String,
    /// Sensitivity.
    pub sensitivity: f64,
}

/// `risk.frtb.commodity_delta` (MAR21.82 to 21.85).
pub fn commodity_delta(sens: &[CommoditySens]) -> Result<GirrDelta> {
    const RW: [f64; 11] = [
        0.30, 0.35, 0.60, 0.80, 0.40, 0.45, 0.20, 0.35, 0.25, 0.35, 0.50,
    ];
    const CTY: [f64; 11] = [
        0.55, 0.95, 0.40, 0.80, 0.60, 0.65, 0.55, 0.45, 0.15, 0.40, 0.15,
    ];
    let mut items = Vec::new();
    for s in sens {
        if !(1..=11).contains(&s.bucket) {
            return fail("E_INPUT", "commodity bucket must be 1 to 11");
        }
        #[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
        let rw = RW[(s.bucket - 1) as usize];
        let key = format!("{}\u{0}{}\u{0}{}", s.commodity, s.tenor, s.location);
        items.push((
            s.bucket,
            s.bucket.to_string(),
            ws(key, &s.commodity, &s.tenor, &s.location, rw * s.sensitivity),
        ));
    }
    let mut g = group(items)?;
    g.sort_by_key(|x| x.1);
    let rho = |b: i64, x: &Ws, y: &Ws| -> f64 {
        #[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
        let cty = if x.name == y.name {
            1.0
        } else {
            CTY[(b - 1) as usize]
        };
        let tenor = if x.a == y.a { 1.0 } else { 0.99 };
        let loc = if x.b == y.b { 1.0 } else { 0.999 };
        cty * tenor * loc
    };
    let gamma = |b: i64, c: i64| -> Result<f64> { Ok(if b == 11 || c == 11 { 0.0 } else { 0.20 }) };
    sbm(
        &g,
        &Class {
            rho: &rho,
            gamma: &gamma,
            simple: None,
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_factor_is_rw_times_s() {
        let r = fx_delta(&[("EURUSD".into(), 1e6)], &[]).unwrap();
        assert!((r.capital - 150_000.0).abs() < 1e-9);
        let e = equity_delta(&[EquitySens {
            issuer: "A".into(),
            bucket: 5,
            kind: "SPOT".into(),
            sensitivity: 1e6,
        }])
        .unwrap();
        assert!((e.capital - 300_000.0).abs() < 1e-9);
        assert_eq!(fx_delta(&[], &[]).unwrap_err().code, "E_INPUT");
    }
}
