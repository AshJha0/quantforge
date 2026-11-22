//! Black-Scholes, Black-76 and Bachelier prices and implied vols (`black-models.md`).

use crate::error::{Result, fail};
use crate::stats::{normal_cdf, normal_pdf};

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Model {
    BlackScholes {
        spot: f64,
        rate: f64,
        dividend: f64,
    },
    Black76 {
        forward: f64,
        discount: f64,
        shift: f64,
    },
    Bachelier {
        forward: f64,
        discount: f64,
    },
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
/// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
pub fn black(call: bool, f: f64, k: f64, v: f64, t: f64, d: f64) -> f64 {
    let p = phi(call);
    if t == 0.0 || v == 0.0 {
        return d * (p * (f - k)).max(0.0);
    }
    let (d1, d2) = d1_d2(f, k, v, t);
    d * p * (f * normal_cdf(p * d1) - k * normal_cdf(p * d2))
}

/// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
pub fn d1_d2(f: f64, k: f64, v: f64, t: f64) -> (f64, f64) {
    let s = v * t.sqrt();
    let d1 = ((f / k).ln() + v * v * t / 2.0) / s;
    (d1, d1 - s)
}

/// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
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
            Model::BlackScholes {
                spot,
                rate,
                dividend,
            } => (
                spot * ((rate - dividend) * self.t).exp(),
                (-rate * self.t).exp(),
                self.strike,
            ),
            Model::Black76 {
                forward,
                discount,
                shift,
            } => (forward + shift, discount, self.strike + shift),
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
        crate::error::finite("self", self)?;
        crate::error::finite("vol", &vol)?;
        if self.t < 0.0 || vol.is_some_and(|v| v < 0.0) {
            return fail("E_DOMAIN", "expiry_years or vol is negative");
        }
        match self.model {
            Model::BlackScholes { spot, .. } => {
                if spot <= 0.0 || self.strike <= 0.0 {
                    return fail("E_DOMAIN", "spot or strike is not positive");
                }
            }
            Model::Black76 {
                forward,
                discount,
                shift,
            } => {
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

    /// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
    pub fn value(&self, v: f64) -> f64 {
        let (f, d, k) = self.fdk();
        if self.is_normal() {
            bachelier(self.call, f, k, v, self.t, d)
        } else {
            black(self.call, f, k, v, self.t, d)
        }
    }

    pub fn price(&self, v: f64) -> Result<f64> {
        crate::error::finite("self", self)?;
        crate::error::finite("v", &v)?;
        self.check(Some(v))?;
        Ok(self.value(v))
    }

    /// Value, vega and the magnitude sum M at `v`, each term evaluated once (shared `d1`, `d2`,
    /// cdf and pdf); bitwise identical to `value`, `vega` and the M of `identified` taken apart.
    /// `lfk` is `(f / k).ln()` and `r` is `sqrt(t)`, hoisted by the caller (the same values, so
    /// the same bits).
    fn eval(&self, f: f64, d: f64, k: f64, v: f64, lfk: f64, r: f64) -> Eval {
        let p = phi(self.call);
        let s = v * r;
        if self.is_normal() {
            let x = (f - k) / s;
            let px = normal_pdf(x);
            let cx = normal_cdf(p * x);
            let value = if self.t == 0.0 || v == 0.0 {
                d * (p * (f - k)).max(0.0)
            } else {
                d * (p * (f - k) * cx + s * px)
            };
            Eval {
                value,
                vega: d * r * px,
                mag: d * ((f - k).abs() * cx + s * px),
            }
        } else {
            let d1 = (lfk + v * v * self.t / 2.0) / s;
            let d2 = d1 - s;
            let c1 = normal_cdf(p * d1);
            let c2 = normal_cdf(p * d2);
            let value = if self.t == 0.0 || v == 0.0 {
                d * (p * (f - k)).max(0.0)
            } else {
                d * p * (f * c1 - k * c2)
            };
            Eval {
                value,
                vega: d * f * r * normal_pdf(d1),
                mag: d * (f * c1 + k * c2),
            }
        }
    }

    fn value_at(&self, f: f64, d: f64, k: f64, v: f64) -> f64 {
        if self.is_normal() {
            bachelier(self.call, f, k, v, self.t, d)
        } else {
            black(self.call, f, k, v, self.t, d)
        }
    }

    pub fn implied(&self, price: f64) -> Result<f64> {
        crate::error::finite("self", self)?;
        crate::error::finite("price", &price)?;
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
        while self.value_at(f, d, k, hi) < price {
            lo = hi;
            hi *= 2.0;
            guard += 1;
            if guard > 1000 || !hi.is_finite() {
                return fail("E_NO_CONVERGENCE", "no bracket for the implied vol");
            }
        }
        let lfk = if self.is_normal() { 0.0 } else { (f / k).ln() };
        let r = self.t.sqrt();
        let mut v = (lo + hi) / 2.0;
        if !self.is_normal() {
            let g = corrado_miller(self.call, f, k, price / d) / r;
            if g > lo && g < hi {
                v = g;
            }
        }
        for _ in 0..300 {
            let ev = self.eval(f, d, k, v, lfk, r);
            let val = ev.value;
            let e = val - price;
            if e == 0.0 {
                return self.identified(f, d, k, v, price, &ev);
            }
            if e > 0.0 {
                hi = v;
            } else {
                lo = v;
            }
            let vega = ev.vega;
            // Newton on ln V - ln price (ruling KR-341): the same step near the root, and it keeps its size
            // far out of the money, where V spans hundreds of decades over the bracket.
            let mut next = if vega > 0.0 && val > 0.0 {
                v - (val / price).ln() * val / vega
            } else {
                f64::NAN
            };
            if !(next > lo && next < hi) {
                next = (lo + hi) / 2.0;
            }
            if (next - v).abs() <= 2e-16 * v {
                let en = self.eval(f, d, k, next, lfk, r);
                return self.identified(f, d, k, next, price, &en);
            }
            v = next;
        }
        let ev = self.eval(f, d, k, v, lfk, r);
        if (ev.value - price).abs() <= 1e-13 * price.max(1.0) {
            return self.identified(f, d, k, v, price, &ev);
        }
        fail("E_NO_CONVERGENCE", "implied vol did not converge")
    }

    /// Returns v if the price identifies the vol in binary64, else `E_NO_CONVERGENCE` (ruling KR-341).
    /// Estimated vol error: (|V(v) - price| + 2^-52 M + 2^-1070 (1 + D (|F| + |K| + v sqrt T)))/(v vega), M the
    /// sum of the magnitudes of the two terms of V (they cancel far from the money); above 1e-10 it is refused.
    /// `ev` is `eval` at `v` (each term computed once, not again here).
    fn identified(&self, f: f64, d: f64, k: f64, v: f64, price: f64, ev: &Eval) -> Result<f64> {
        let root = v * self.t.sqrt();
        let scale = v * ev.vega;
        let error = (ev.value - price).abs()
            + f64::EPSILON * ev.mag
            + f64::from_bits(16) * (1.0 + d * (f.abs() + k.abs() + root)); // 2^-1070
        if scale.is_nan() || scale <= 0.0 || error > 1e-10 * scale {
            return fail(
                "E_NO_CONVERGENCE",
                "the price does not identify the vol in binary64",
            );
        }
        Ok(v)
    }
}

/// Corrado-Miller start for the lognormal solve: an estimate of `v sqrt(T)` from the undiscounted
/// price `c` (a put is turned into a call by parity). Only a starting point; NaN when the formula
/// does not apply, and the caller then keeps the bracket midpoint.
fn corrado_miller(call: bool, f: f64, k: f64, c: f64) -> f64 {
    let c = if call { c } else { c + (f - k) };
    let a = c - (f - k) / 2.0;
    let q = a * a - (f - k) * (f - k) / std::f64::consts::PI;
    (2.0 * std::f64::consts::PI).sqrt() / (f + k) * (a + q.max(0.0).sqrt())
}

/// One evaluation of the price terms at a vol: value, vega and the magnitude sum M.
struct Eval {
    value: f64,
    vega: f64,
    mag: f64,
}

impl crate::error::Finite for Model {
    #[allow(clippy::match_same_arms)]
    fn is_all_finite(&self) -> bool {
        match self {
            Self::BlackScholes {
                spot,
                rate,
                dividend,
                ..
            } => spot.is_all_finite() && rate.is_all_finite() && dividend.is_all_finite(),
            Self::Black76 {
                forward,
                discount,
                shift,
                ..
            } => forward.is_all_finite() && discount.is_all_finite() && shift.is_all_finite(),
            Self::Bachelier {
                forward, discount, ..
            } => forward.is_all_finite() && discount.is_all_finite(),
        }
    }
}

impl crate::error::Finite for Option_ {
    fn is_all_finite(&self) -> bool {
        self.model.is_all_finite() && self.strike.is_all_finite() && self.t.is_all_finite()
    }
}

#[cfg(test)]
#[path = "black_fused_tests.rs"]
mod fused_tests;

#[cfg(test)]
mod tests {
    use super::*;

    fn b76(call: bool, k: f64) -> Option_ {
        Option_ {
            model: Model::Black76 {
                forward: 100.0,
                discount: 0.97,
                shift: 0.0,
            },
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
            model: Model::Bachelier {
                forward: -0.5,
                discount: 1.0,
            },
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
