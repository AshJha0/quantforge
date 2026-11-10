//! FRTB-SA GIRR delta (`06-risk/frtb-sa-girr.md`, MAR21, ruling F-33).
use std::collections::{BTreeMap, HashSet};

use crate::error::{Result, fail};

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Factor {
    /// Tenor in years.
    Tenor(f64),
    Inflation,
    XccyBasis,
}

impl Factor {
    /// `None` for a value the spec does not list (`E_SCHEMA` at the CLI).
    pub fn parse(s: &str) -> Option<Factor> {
        Some(match s {
            "0.25Y" => Factor::Tenor(0.25),
            "0.5Y" => Factor::Tenor(0.5),
            "1Y" => Factor::Tenor(1.0),
            "2Y" => Factor::Tenor(2.0),
            "3Y" => Factor::Tenor(3.0),
            "5Y" => Factor::Tenor(5.0),
            "10Y" => Factor::Tenor(10.0),
            "15Y" => Factor::Tenor(15.0),
            "20Y" => Factor::Tenor(20.0),
            "30Y" => Factor::Tenor(30.0),
            "INFLATION" => Factor::Inflation,
            "XCCY_BASIS" => Factor::XccyBasis,
            _ => return None,
        })
    }

    fn weight(self) -> f64 {
        match self {
            Factor::Tenor(t) if t <= 0.5 => 0.017,
            Factor::Tenor(1.0) | Factor::Inflation | Factor::XccyBasis => 0.016,
            Factor::Tenor(2.0) => 0.013,
            Factor::Tenor(3.0) => 0.012,
            Factor::Tenor(_) => 0.011,
        }
    }

    fn key(self) -> String {
        match self {
            Factor::Tenor(t) => format!("T{t}"),
            Factor::Inflation => "INF".into(),
            Factor::XccyBasis => "XCCY".into(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Sensitivity {
    pub currency: String,
    pub curve: String,
    pub factor: Factor,
    pub sensitivity: f64,
}

#[derive(Debug, Clone)]
pub struct Bucket {
    pub currency: String,
    pub k: f64,
    pub s: f64,
    pub s_used: f64,
}

#[derive(Debug, Clone)]
pub struct Scenario {
    pub name: &'static str,
    pub buckets: Vec<Bucket>,
    pub delta: f64,
    pub alternative_used: bool,
}

#[derive(Debug, Clone)]
pub struct GirrDelta {
    /// `high`, `medium`, `low`.
    pub scenarios: Vec<Scenario>,
    pub capital: f64,
    pub binding_scenario: &'static str,
}

const REDUCED: [&str; 7] = ["EUR", "USD", "GBP", "AUD", "JPY", "SEK", "CAD"];

/// Medium (MAR21.45 to MAR21.49) correlation of two factors in one bucket.
fn rho(a: &Sensitivity, b: &Sensitivity) -> f64 {
    let same_curve = a.curve == b.curve;
    match (a.factor, b.factor) {
        (Factor::XccyBasis, _) | (_, Factor::XccyBasis) => 0.0,
        (Factor::Tenor(x), Factor::Tenor(y)) => {
            let r = (-0.03 * (x - y).abs() / x.min(y)).exp().max(0.4);
            if same_curve { r } else { r * 0.999 }
        }
        (Factor::Inflation, Factor::Inflation) => 0.999,
        _ => 0.4,
    }
}

fn scale(x: f64, scenario: &str) -> f64 {
    match scenario {
        "high" => (1.25 * x).min(1.0),
        "low" => (2.0 * x - 1.0).max(0.75 * x),
        _ => x,
    }
}

/// `risk.frtb.girr_delta`.
pub fn girr_delta(
    sens: &[Sensitivity],
    reduction: bool,
    reporting: Option<&str>,
) -> Result<GirrDelta> {
    for s in sens {
        crate::error::finite("sensitivity", &s.sensitivity)?;
    }
    if sens.is_empty() {
        return fail("E_INPUT", "no sensitivities");
    }
    let mut seen = HashSet::new();
    for s in sens {
        if !seen.insert((s.currency.clone(), s.curve.clone(), s.factor.key())) {
            return fail("E_INPUT", "the same risk factor twice");
        }
    }
    let mut buckets: BTreeMap<&str, Vec<(&Sensitivity, f64)>> = BTreeMap::new();
    for s in sens {
        let mut rw = s.factor.weight();
        if reduction
            && (REDUCED.contains(&s.currency.as_str()) || reporting == Some(s.currency.as_str()))
        {
            rw /= 2f64.sqrt();
        }
        buckets
            .entry(s.currency.as_str())
            .or_default()
            .push((s, rw * s.sensitivity));
    }
    let mut scenarios = Vec::new();
    for name in ["high", "medium", "low"] {
        let mut out = Vec::new();
        for (ccy, items) in &buckets {
            let mut sum = 0.0;
            for (i, (a, wa)) in items.iter().enumerate() {
                sum += wa * wa;
                for (j, (b, wb)) in items.iter().enumerate() {
                    if i != j {
                        sum += scale(rho(a, b), name) * wa * wb;
                    }
                }
            }
            let k = sum.max(0.0).sqrt();
            let s: f64 = items.iter().map(|x| x.1).sum();
            out.push(Bucket {
                currency: (*ccy).to_string(),
                k,
                s,
                s_used: s,
            });
        }
        let gamma = scale(0.5, name);
        let total = |b: &[Bucket]| -> f64 {
            let mut t: f64 = b.iter().map(|x| x.k * x.k).sum();
            for i in 0..b.len() {
                for j in 0..b.len() {
                    if i != j {
                        t += gamma * b[i].s_used * b[j].s_used;
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
