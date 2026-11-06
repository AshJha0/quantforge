//! Compounding (`compounding.md`).
use crate::error::{Result, fail};

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Compounding {
    Simple,
    Continuous,
    Periodic(f64),
}

fn check_rate(c: Compounding, r: f64, t: f64) -> Result<()> {
    let bad = match c {
        Compounding::Simple => 1.0 + r * t <= 0.0,
        Compounding::Periodic(n) => 1.0 + r / n <= 0.0,
        Compounding::Continuous => false,
    };
    if bad {
        return fail("E_DOMAIN", "rate gives a non-positive growth factor");
    }
    Ok(())
}

fn factor(c: Compounding, r: f64, t: f64) -> f64 {
    match c {
        Compounding::Simple => 1.0 / (1.0 + r * t),
        Compounding::Periodic(n) => (1.0 + r / n).powf(-n * t),
        Compounding::Continuous => (-r * t).exp(),
    }
}

pub fn discount_factor(r: f64, t: f64, c: Compounding) -> Result<f64> {
    if t < 0.0 {
        return fail("E_DOMAIN", "t is negative");
    }
    check_rate(c, r, t)?;
    Ok(factor(c, r, t))
}

pub fn convert(r: f64, t: f64, from: Compounding, to: Compounding) -> Result<f64> {
    if t < 0.0 {
        return fail("E_DOMAIN", "t is negative");
    }
    if t == 0.0 {
        return fail("E_DOMAIN", "rate is undefined at t = 0");
    }
    check_rate(from, r, t)?;
    let d = factor(from, r, t);
    Ok(match to {
        Compounding::Simple => (1.0 / d - 1.0) / t,
        Compounding::Periodic(n) => n * (d.powf(-1.0 / (n * t)) - 1.0),
        Compounding::Continuous => -d.ln() / t,
    })
}
