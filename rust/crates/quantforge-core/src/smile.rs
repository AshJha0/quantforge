//! Delta conventions and smile quotes (`smile-and-surface.md`).
use crate::black::{d1_d2, phi};

use crate::error::{Result, fail};
use crate::rng::ppnd16;
use crate::stats::normal_cdf;

/// `None` is `FORWARD`, whose `s` is 1; `Some(scale)` is `SPOT`.
pub fn delta_scale(convention_spot: bool, scale: Option<f64>) -> Result<f64> {
    crate::error::finite("scale", &scale)?;
    match (convention_spot, scale) {
        (false, None) => Ok(1.0),
        (false, Some(_)) => fail("E_INPUT", "FORWARD takes a null scale"),
        (true, None) => fail("E_INPUT", "SPOT needs a scale"),
        (true, Some(s)) if s <= 0.0 => fail("E_DOMAIN", "scale must be above 0"),
        (true, Some(s)) => Ok(s),
    }
}

fn check(f: f64, v: f64, t: f64) -> Result<()> {
    if f <= 0.0 || v <= 0.0 || t <= 0.0 {
        return fail("E_DOMAIN", "forward, vol and expiry_years must be above 0");
    }
    Ok(())
}

pub fn to_strike(f: f64, v: f64, t: f64, call: bool, delta: f64, s: f64) -> Result<f64> {
    crate::error::finite("f", &f)?;
    crate::error::finite("v", &v)?;
    crate::error::finite("t", &t)?;
    crate::error::finite("delta", &delta)?;
    crate::error::finite("s", &s)?;
    check(f, v, t)?;
    let p = phi(call);
    let x = p * delta / s;
    if x <= 0.0 || x >= 1.0 {
        return fail("E_DOMAIN", "delta is outside its range");
    }
    let d1 = p * ppnd16(x);
    Ok(f * (-d1 * v * t.sqrt() + v * v * t / 2.0).exp())
}

pub fn from_strike(f: f64, v: f64, t: f64, call: bool, k: f64, s: f64) -> Result<f64> {
    crate::error::finite("f", &f)?;
    crate::error::finite("v", &v)?;
    crate::error::finite("t", &t)?;
    crate::error::finite("k", &k)?;
    crate::error::finite("s", &s)?;
    check(f, v, t)?;
    if k <= 0.0 {
        return fail("E_DOMAIN", "strike must be above 0");
    }
    let p = phi(call);
    Ok(p * s * normal_cdf(p * d1_d2(f, k, v, t).0))
}

#[derive(Debug, Clone, PartialEq)]
pub struct RrBf {
    pub atm_strike: f64,
    pub call_vol: f64,
    pub put_vol: f64,
    pub call_strike: f64,
    pub put_strike: f64,
}

pub fn rr_bf(
    f: f64,
    t: f64,
    atm: f64,
    delta_neutral: bool,
    rr: f64,
    bf: f64,
    delta: f64,
    s: f64,
) -> Result<RrBf> {
    crate::error::finite("f", &f)?;
    crate::error::finite("t", &t)?;
    crate::error::finite("atm", &atm)?;
    crate::error::finite("rr", &rr)?;
    crate::error::finite("bf", &bf)?;
    crate::error::finite("delta", &delta)?;
    crate::error::finite("s", &s)?;
    let (call_vol, put_vol) = (atm + bf + rr / 2.0, atm + bf - rr / 2.0);
    if atm <= 0.0 || call_vol <= 0.0 || put_vol <= 0.0 {
        return fail("E_DOMAIN", "a vol is not positive");
    }
    Ok(RrBf {
        atm_strike: if delta_neutral {
            f * (atm * atm * t / 2.0).exp()
        } else {
            f
        },
        call_vol,
        put_vol,
        call_strike: to_strike(f, call_vol, t, true, delta, s)?,
        put_strike: to_strike(f, put_vol, t, false, -delta, s)?,
    })
}

impl crate::error::Finite for RrBf {
    fn is_all_finite(&self) -> bool {
        self.atm_strike.is_all_finite()
            && self.call_vol.is_all_finite()
            && self.put_vol.is_all_finite()
            && self.call_strike.is_all_finite()
            && self.put_strike.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn delta_round_trip_both_signs() {
        for (call, d) in [(true, 0.25), (false, -0.1)] {
            let k = to_strike(100.0, 0.22, 0.75, call, d, 0.97).unwrap();
            let back = from_strike(100.0, 0.22, 0.75, call, k, 0.97).unwrap();
            assert!((back - d).abs() < 1e-12);
        }
    }

    #[test]
    fn put_delta_must_be_negative() {
        assert!(to_strike(100.0, 0.2, 1.0, false, 0.25, 1.0).is_err());
    }
}
