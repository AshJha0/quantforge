//! Black-Scholes, Black-76 and Bachelier prices and implied vols (`black-models.md`).
use crate::error::{Result, fail};
use crate::stats::{normal_cdf, normal_pdf};

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Model {
    BlackScholes { spot: f64, rate: f64, dividend: f64 },
    Black76 { forward: f64, discount: f64, shift: f64 },
    Bachelier { forward: f64, discount: f64 },
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Option_ {
    pub model: Model,
    pub call: bool,
    pub strike: f64,
    pub t: f64,
}

pub fn phi(call: bool) -> f64 {
    if call { 1.0 } else { -1.0 }
}

/// Lognormal price on forward `f`, strike `k`, discount `d`.
pub fn black(call: bool, f: f64, k: f64, v: f64, t: f64, d: f64) -> f64 {
    let p = phi(call);
    if t == 0.0 || v == 0.0 {
        return d * (p * (f - k)).max(0.0);
    }
    let (d1, d2) = d1_d2(f, k, v, t);
    d * p * (f * normal_cdf(p * d1) - k * normal_cdf(p * d2))
}

pub fn d1_d2(f: f64, k: f64, v: f64, t: f64) -> (f64, f64) {
    let s = v * t.sqrt();
    let d1 = ((f / k).ln() + v * v * t / 2.0) / s;
    (d1, d1 - s)
}

pub fn bachelier(call: bool, f: f64, k: f64, v: f64, t: f64, d: f64) -> f64 {
    let p = phi(call);
    if t == 0.0 || v == 0.0 {
        return d * (p * (f - k)).max(0.0);
    }
    let s = v * t.sqrt();
    let x = (f - k) / s;
    d * (p * (f - k) * normal_cdf(p * x) + s * normal_pdf(x))
}

impl Option_ {
    /// Forward, discount factor and strike, shifted where the model shifts.
    pub fn fdk(&self) -> (f64, f64, f64) {
        match self.model {
            Model::BlackScholes { spot, rate, dividend } => (
                spot * ((rate - dividend) * self.t).exp(),
                (-rate * self.t).exp(),
                self.strike,
            ),
            Model::Black76 { forward, discount, shift } => {
                (forward + shift, discount, self.strike + shift)
            }
            Model::Bachelier { forward, discount } => (forward, discount, self.strike),
        }
    }

    pub fn unshifted_forward(&self) -> f64 {
        match self.model {
            Model::Black76 { forward, .. } => forward,
            _ => self.fdk().0,
        }
    }

    pub fn is_normal(&self) -> bool {
        matches!(self.model, Model::Bachelier { .. })
    }

    /// The checks both operations share, except `vol`, in the spec's order around it.
    pub fn check(&self, vol: Option<f64>) -> Result<()> {
        if self.t < 0.0 || vol.is_some_and(|v| v < 0.0) {
            return fail("E_DOMAIN", "expiry_years or vol is negative");
        }
        match self.model {
            Model::BlackScholes { spot, .. } => {
                if spot <= 0.0 || self.strike <= 0.0 {
                    return fail("E_DOMAIN", "spot or strike is not positive");
                }
            }
            Model::Black76 { forward, discount, shift } => {
                if discount <= 0.0 || forward + shift <= 0.0 || self.strike + shift <= 0.0 {
                    return fail("E_DOMAIN", "discount, forward or strike is out of domain");
                }
            }
            Model::Bachelier { discount, .. } => {
                if discount <= 0.0 {
                    return fail("E_DOMAIN", "discount_factor is not positive");
                }
            }
        }
        Ok(())
    }

    pub fn value(&self, v: f64) -> f64 {
        let (f, d, k) = self.fdk();
        if self.is_normal() {
            bachelier(self.call, f, k, v, self.t, d)
        } else {
            black(self.call, f, k, v, self.t, d)
        }
    }

    pub fn price(&self, v: f64) -> Result<f64> {
        self.check(Some(v))?;
        Ok(self.value(v))
    }

    fn vega(&self, v: f64) -> f64 {
        let (f, d, k) = self.fdk();
        let r = self.t.sqrt();
        if self.is_normal() {
            d * r * normal_pdf((f - k) / (v * r))
        } else {
            d * f * r * normal_pdf(d1_d2(f, k, v, self.t).0)
        }
    }

    pub fn implied(&self, price: f64) -> Result<f64> {
        self.check(None)?;
        if self.t == 0.0 {
            return fail("E_DOMAIN", "expiry_years is 0");
        }
        let (f, d, k) = self.fdk();
        let intrinsic = d * (phi(self.call) * (f - k)).max(0.0);
        if price < intrinsic {
            return fail("E_DOMAIN", "price is below intrinsic");
        }
        if !self.is_normal() && price >= if self.call { d * f } else { d * k } {
            return fail("E_DOMAIN", "price is at or above the upper bound");
        }
        if price == intrinsic {
            return Ok(0.0);
        }
        // Bracket, then Newton held inside it. The result is polished to rounding, as a stop at
        // the spec's price tolerance would cost too much in vol where vega is small.
        let mut hi = if self.is_normal() {
            (f - k).abs().max(price).max(1e-8)
        } else {
            1.0
        };
        let mut lo = 0.0;
        let mut guard = 0;
        while self.value(hi) < price {
            lo = hi;
            hi *= 2.0;
            guard += 1;
            if guard > 1000 || !hi.is_finite() {
                return fail("E_NO_CONVERGENCE", "no bracket for the implied vol");
            }
        }
        let mut v = (lo + hi) / 2.0;
        for _ in 0..300 {
            let e = self.value(v) - price;
            if e == 0.0 {
                return Ok(v);
            }
            if e > 0.0 {
                hi = v;
            } else {
                lo = v;
            }
            let vega = self.vega(v);
            let mut next = v - e / vega;
            if !(next > lo && next < hi) {
                next = (lo + hi) / 2.0;
            }
            if (next - v).abs() <= 2e-16 * v {
                return Ok(next);
            }
            v = next;
        }
        if (self.value(v) - price).abs() <= 1e-13 * price.max(1.0) {
            return Ok(v);
        }
        fail("E_NO_CONVERGENCE", "implied vol did not converge")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn b76(call: bool, k: f64) -> Option_ {
        Option_ {
            model: Model::Black76 { forward: 100.0, discount: 0.97, shift: 0.0 },
            call,
            strike: k,
            t: 1.5,
        }
    }

    #[test]
    fn parity_and_round_trip() {
        let (c, p) = (b76(true, 110.0).value(0.2), b76(false, 110.0).value(0.2));
        assert!((c - p - 0.97 * (100.0 - 110.0)).abs() < 1e-12);
        assert!((b76(true, 110.0).implied(c).unwrap() - 0.2).abs() < 1e-12);
    }

    #[test]
    fn bachelier_round_trip_with_negative_forward() {
        let o = Option_ {
            model: Model::Bachelier { forward: -0.5, discount: 1.0 },
            call: false,
            strike: 0.2,
            t: 2.0,
        };
        assert!((o.implied(o.value(0.7)).unwrap() - 0.7).abs() < 1e-11);
    }

    #[test]
    fn intrinsic_gives_zero_and_below_fails() {
        let o = b76(true, 90.0);
        assert_eq!(o.implied(0.97 * 10.0).unwrap(), 0.0);
        assert_eq!(o.implied(9.0).unwrap_err().code, "E_DOMAIN");
    }
}
