//! FRTB standardised vega and curvature (`06-risk/frtb-sa-vega-curvature.md`, ruling G-51),
//! for GIRR, CSR non-securitisation, equity, commodity and FX.
use crate::error::{Result, fail};
use crate::frtb::{Bucket, GirrDelta, Scenario};
use crate::frtb2::{commodity_gamma, commodity_name_rho, csr_gamma, equity_gamma, equity_name_rho};

/// Risk class of [`vega`] and [`curvature`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Class {
    /// General interest rate risk.
    Girr,
    /// Credit spread, non-securitisation.
    CsrNonsec,
    /// Equity.
    Equity,
    /// Commodity.
    Commodity,
    /// Foreign exchange.
    Fx,
}

impl Class {
    /// Parses `GIRR`, `CSR_NONSEC`, `EQUITY`, `COMMODITY`, `FX`.
    pub fn parse(s: &str) -> Option<Class> {
        Some(match s {
            "GIRR" => Class::Girr,
            "CSR_NONSEC" => Class::CsrNonsec,
            "EQUITY" => Class::Equity,
            "COMMODITY" => Class::Commodity,
            "FX" => Class::Fx,
            _ => return None,
        })
    }

    fn named(self) -> bool {
        !matches!(self, Class::Girr | Class::Fx)
    }

    /// Numeric bucket of a named class (checked range), 0 for GIRR and FX.
    fn bucket(self, label: &str) -> Result<i64> {
        if !self.named() {
            return Ok(0);
        }
        let max = match self {
            Class::CsrNonsec => 18,
            Class::Equity => 13,
            _ => 11,
        };
        match label.parse::<i64>() {
            Ok(b) if (1..=max).contains(&b) => Ok(b),
            _ => fail("E_INPUT", "unknown bucket for the risk class"),
        }
    }

    fn other_sector(self) -> Option<i64> {
        match self {
            Class::Equity => Some(11),
            Class::CsrNonsec => Some(16),
            _ => None,
        }
    }

    /// Delta correlation along the name dimension only.
    fn name_rho(self, b: i64, same: bool) -> f64 {
        if same {
            return 1.0;
        }
        match self {
            Class::CsrNonsec => {
                if b >= 17 {
                    0.80
                } else {
                    0.35
                }
            }
            Class::Equity => equity_name_rho(b),
            Class::Commodity => commodity_name_rho(b),
            Class::Girr | Class::Fx => 1.0,
        }
    }

    /// Cross-bucket delta correlation.
    fn gamma(self, b: i64, c: i64) -> Result<f64> {
        match self {
            Class::Girr => Ok(0.5),
            Class::Fx => Ok(0.6),
            Class::Equity => equity_gamma(b, c),
            Class::CsrNonsec => csr_gamma(b, c),
            Class::Commodity => commodity_gamma(b, c),
        }
    }
}

fn scale(x: f64, scenario: &str) -> f64 {
    match scenario {
        "high" => (1.25 * x).min(1.0),
        "low" => (2.0 * x - 1.0).max(0.75 * x),
        _ => x,
    }
}

/// Bucket order of G-51: by label length, then text.
fn order(a: &str, b: &str) -> std::cmp::Ordering {
    a.len().cmp(&b.len()).then_with(|| a.cmp(b))
}

/// A weighted vega sensitivity inside a bucket.
struct W {
    key: String,
    name: String,
    t: f64,
    u: f64,
    ws: f64,
}

/// Curvature rows of one bucket: `(name, CVR+, CVR-)`.
type CurvRows = Vec<(String, f64, f64)>;

/// A vega sensitivity `VR_k` (MAR21.25).
#[derive(Debug, Clone)]
pub struct VegaSens {
    /// Bucket label (currency, pair or bucket number).
    pub bucket: String,
    /// Name (issuer, commodity); `None` for GIRR and FX.
    pub name: Option<String>,
    /// Option maturity in years.
    pub option_maturity: f64,
    /// Underlying residual maturity (GIRR only).
    pub underlying_maturity: Option<f64>,
    /// Vega sensitivity.
    pub vega: f64,
}

fn mat_rho(a: f64, b: f64) -> f64 {
    (-0.01 * (a - b).abs() / a.min(b)).exp()
}

/// `risk.frtb.vega`: MAR21.92 to 21.95 on the MAR21.4 aggregation and MAR21.6 scenarios.
pub fn vega(class: Class, sens: &[VegaSens]) -> Result<GirrDelta> {
    if sens.is_empty() {
        return fail("E_INPUT", "no sensitivities");
    }
    let mut buckets: Vec<(String, i64, Vec<W>)> = Vec::new();
    for s in sens {
        crate::error::finite("vega", &[s.vega, s.option_maturity])?;
        if (class == Class::Girr) != s.underlying_maturity.is_some() {
            return fail(
                "E_INPUT",
                "underlying_maturity is required for GIRR and only there",
            );
        }
        if class.named() != s.name.is_some() {
            return fail("E_INPUT", "name is required except for GIRR and FX");
        }
        let u = s.underlying_maturity.unwrap_or(1.0);
        crate::error::finite("underlying_maturity", &u)?;
        if s.option_maturity <= 0.0 || u <= 0.0 {
            return fail("E_DOMAIN", "maturities must be positive");
        }
        let b = class.bucket(&s.bucket)?;
        let rw = if class == Class::Equity && (b <= 8 || b >= 12) {
            0.7778
        } else {
            1.0
        };
        let name = s.name.clone().unwrap_or_default();
        let key = format!(
            "{name}\u{0}{}\u{0}{:?}",
            s.option_maturity, s.underlying_maturity
        );
        let w = W {
            key,
            name,
            t: s.option_maturity,
            u,
            ws: rw * s.vega,
        };
        match buckets.iter_mut().find(|x| x.0 == s.bucket) {
            Some(x) => x.2.push(w),
            None => buckets.push((s.bucket.clone(), b, vec![w])),
        }
    }
    buckets.sort_by(|a, b| order(&a.0, &b.0));
    let n = buckets.len();
    let mut gam = vec![vec![0.0; n]; n];
    for i in 0..n {
        for j in 0..n {
            if i != j {
                gam[i][j] = class.gamma(buckets[i].1, buckets[j].1)?;
            }
        }
    }
    let mut scenarios = Vec::new();
    for sc in ["high", "medium", "low"] {
        let mut out = Vec::new();
        for (label, b, items) in &buckets {
            let s: f64 = items.iter().map(|x| x.ws).sum();
            let k = if class.other_sector() == Some(*b) {
                let mut net: Vec<(&str, f64)> = Vec::new();
                for w in items {
                    match net.iter_mut().find(|q| q.0 == w.key) {
                        Some(q) => q.1 += w.ws,
                        None => net.push((&w.key, w.ws)),
                    }
                }
                net.iter().map(|q| q.1.abs()).sum()
            } else {
                let mut sum = 0.0;
                for (i, x) in items.iter().enumerate() {
                    sum += x.ws * x.ws;
                    for (j, y) in items.iter().enumerate() {
                        if i != j {
                            let r = if class == Class::Girr {
                                (mat_rho(x.t, y.t) * mat_rho(x.u, y.u)).min(1.0)
                            } else {
                                (class.name_rho(*b, x.name == y.name) * mat_rho(x.t, y.t)).min(1.0)
                            };
                            sum += scale(r, sc) * x.ws * y.ws;
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
                        t += scale(gam[i][j], sc) * o[i].s_used * o[j].s_used;
                    }
                }
            }
            t
        };
        let mut t = total(&out);
        let mut alt = false;
        if t < 0.0 {
            alt = true;
            for b in &mut out {
                b.s_used = b.s.min(b.k).max(-b.k);
            }
            t = total(&out).max(0.0);
        }
        scenarios.push(Scenario {
            name: sc,
            buckets: out,
            delta: t.sqrt(),
            alternative_used: alt,
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

/// A curvature factor: the bank's `CVR^+`, `CVR^-` (MAR21.5(2)).
#[derive(Debug, Clone)]
pub struct CurvFactor {
    /// Bucket label.
    pub bucket: String,
    /// Name; `None` for GIRR and FX.
    pub name: Option<String>,
    /// `CVR^+`.
    pub cvr_up: f64,
    /// `CVR^-`.
    pub cvr_down: f64,
}

/// One bucket of a curvature scenario.
#[derive(Debug, Clone)]
pub struct CurvBucket {
    /// Bucket label.
    pub bucket: String,
    /// `K_b`.
    pub k: f64,
    /// `S_b` of the selected direction.
    pub s: f64,
    /// `true` for upward.
    pub up: bool,
}

/// Output of [`curvature`].
#[derive(Debug, Clone)]
pub struct Curvature {
    /// `(name, buckets, curvature)` for `high`, `medium`, `low`.
    pub scenarios: Vec<(&'static str, Vec<CurvBucket>, f64)>,
    /// Largest of the three.
    pub capital: f64,
    /// Its scenario (ties to the first).
    pub binding_scenario: &'static str,
}

fn psi(a: f64, b: f64) -> f64 {
    if a < 0.0 && b < 0.0 { 0.0 } else { 1.0 }
}

/// `risk.frtb.curvature` (MAR21.5, 21.98 to 21.101).
pub fn curvature(class: Class, factors: &[CurvFactor], fx_scalar: bool) -> Result<Curvature> {
    if fx_scalar && class != Class::Fx {
        return fail("E_INPUT", "fx_scalar applies to FX only");
    }
    if factors.is_empty() {
        return fail("E_INPUT", "no factors");
    }
    let div = if fx_scalar { 1.5 } else { 1.0 };
    let mut buckets: Vec<(String, i64, CurvRows)> = Vec::new();
    for f in factors {
        crate::error::finite("cvr", &[f.cvr_up, f.cvr_down])?;
        if class.named() != f.name.is_some() {
            return fail("E_INPUT", "name is required except for GIRR and FX");
        }
        let b = class.bucket(&f.bucket)?;
        let name = f.name.clone().unwrap_or_default();
        let row = (name, f.cvr_up / div, f.cvr_down / div);
        match buckets.iter_mut().find(|x| x.0 == f.bucket) {
            Some(x) => {
                if x.2.iter().any(|r| r.0 == row.0) {
                    return fail("E_INPUT", "the same factor twice");
                }
                x.2.push(row);
            }
            None => buckets.push((f.bucket.clone(), b, vec![row])),
        }
    }
    buckets.sort_by(|a, b| order(&a.0, &b.0));
    let n = buckets.len();
    let mut gam = vec![vec![0.0; n]; n];
    for i in 0..n {
        for j in 0..n {
            if i != j {
                let g = class.gamma(buckets[i].1, buckets[j].1)?;
                gam[i][j] = g * g;
            }
        }
    }
    let mut scenarios = Vec::new();
    for sc in ["high", "medium", "low"] {
        let mut out = Vec::new();
        for (label, b, rows) in &buckets {
            let sum_up: f64 = rows.iter().map(|r| r.1).sum();
            let sum_dn: f64 = rows.iter().map(|r| r.2).sum();
            let (ku, kd) = if class.other_sector() == Some(*b) {
                (
                    rows.iter().map(|r| r.1.max(0.0)).sum::<f64>(),
                    rows.iter().map(|r| r.2.max(0.0)).sum::<f64>(),
                )
            } else {
                let k = |pick: &dyn Fn(&(String, f64, f64)) -> f64| -> f64 {
                    let mut t = 0.0;
                    for (i, x) in rows.iter().enumerate() {
                        let cx = pick(x);
                        t += cx.max(0.0) * cx.max(0.0);
                        for (j, y) in rows.iter().enumerate() {
                            if i != j {
                                let cy = pick(y);
                                let r = class.name_rho(*b, x.0 == y.0);
                                t += scale(r * r, sc) * cx * cy * psi(cx, cy);
                            }
                        }
                    }
                    t.max(0.0).sqrt()
                };
                (k(&|r| r.1), k(&|r| r.2))
            };
            let up = ku > kd || (ku == kd && sum_up > sum_dn);
            out.push(CurvBucket {
                bucket: label.clone(),
                k: ku.max(kd),
                s: if up { sum_up } else { sum_dn },
                up,
            });
        }
        let mut t: f64 = out.iter().map(|x| x.k * x.k).sum();
        for i in 0..n {
            for j in 0..n {
                if i != j {
                    t += scale(gam[i][j], sc) * out[i].s * out[j].s * psi(out[i].s, out[j].s);
                }
            }
        }
        scenarios.push((sc, out, t.max(0.0).sqrt()));
    }
    let mut best = 0;
    for i in 1..3 {
        if scenarios[i].2 > scenarios[best].2 {
            best = i;
        }
    }
    Ok(Curvature {
        capital: scenarios[best].2,
        binding_scenario: scenarios[best].0,
        scenarios,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_factor_limits() {
        let v = vega(
            Class::Fx,
            &[VegaSens {
                bucket: "EURUSD".into(),
                name: None,
                option_maturity: 1.0,
                underlying_maturity: None,
                vega: 1e6,
            }],
        )
        .unwrap();
        assert!((v.capital - 1e6).abs() < 1e-6);
        let c = curvature(
            Class::Equity,
            &[CurvFactor {
                bucket: "5".into(),
                name: Some("A".into()),
                cvr_up: -3.0,
                cvr_down: 0.0,
            }],
            false,
        )
        .unwrap();
        assert_eq!(c.capital, 0.0);
        assert!(!c.scenarios[0].1[0].up);
        assert_eq!(order("11", "9"), std::cmp::Ordering::Greater);
    }
}
