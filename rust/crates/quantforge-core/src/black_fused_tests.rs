//! The fused implied-vol solver against the previous one (value, then vega, then `identified`
//! recomputing every term), kept here verbatim: outputs must agree to the bit and error codes
//! must agree, on 4000 seeded cases over Black-Scholes, Black-76 (shifted) and Bachelier,
//! including deep out of the money prices and the error paths. Mirrors Java `BlackSolveFusedTest`.

use super::*;
use crate::error::Result;

fn old_vega(o: &Option_, v: f64) -> f64 {
    let (f, d, k) = o.fdk();
    let r = o.t.sqrt();
    if o.is_normal() {
        d * r * normal_pdf((f - k) / (v * r))
    } else {
        d * f * r * normal_pdf(d1_d2(f, k, v, o.t).0)
    }
}

fn old_identified(o: &Option_, v: f64, price: f64) -> Result<f64> {
    let (f, d, k) = o.fdk();
    let p = phi(o.call);
    let root = v * o.t.sqrt();
    let mag = if o.is_normal() {
        let x = (f - k) / root;
        d * ((f - k).abs() * normal_cdf(p * x) + root * normal_pdf(x))
    } else {
        let (d1, d2) = d1_d2(f, k, v, o.t);
        d * (f * normal_cdf(p * d1) + k * normal_cdf(p * d2))
    };
    let scale = v * old_vega(o, v);
    let error = (o.value(v) - price).abs()
        + f64::EPSILON * mag
        + f64::from_bits(16) * (1.0 + d * (f.abs() + k.abs() + root));
    if scale.is_nan() || scale <= 0.0 || error > 1e-10 * scale {
        return fail("E_NO_CONVERGENCE", "x");
    }
    Ok(v)
}

fn old_implied(o: &Option_, price: f64) -> Result<f64> {
    crate::error::finite("self", o)?;
    crate::error::finite("price", &price)?;
    o.check(None)?;
    if o.t == 0.0 {
        return fail("E_DOMAIN", "x");
    }
    let (f, d, k) = o.fdk();
    let intrinsic = d * (phi(o.call) * (f - k)).max(0.0);
    if price < intrinsic {
        return fail("E_DOMAIN", "x");
    }
    if !o.is_normal() && price >= if o.call { d * f } else { d * k } {
        return fail("E_DOMAIN", "x");
    }
    if price == intrinsic {
        return Ok(0.0);
    }
    let mut hi = if o.is_normal() {
        (f - k).abs().max(price).max(1e-8)
    } else {
        1.0
    };
    let mut lo = 0.0;
    let mut guard = 0;
    while o.value(hi) < price {
        lo = hi;
        hi *= 2.0;
        guard += 1;
        if guard > 1000 || !hi.is_finite() {
            return fail("E_NO_CONVERGENCE", "x");
        }
    }
    let mut v = (lo + hi) / 2.0;
    for _ in 0..300 {
        let val = o.value(v);
        let e = val - price;
        if e == 0.0 {
            return old_identified(o, v, price);
        }
        if e > 0.0 {
            hi = v;
        } else {
            lo = v;
        }
        let vega = old_vega(o, v);
        let mut next = if vega > 0.0 && val > 0.0 {
            v - (val / price).ln() * val / vega
        } else {
            f64::NAN
        };
        if !(next > lo && next < hi) {
            next = (lo + hi) / 2.0;
        }
        if (next - v).abs() <= 2e-16 * v {
            return old_identified(o, next, price);
        }
        v = next;
    }
    if (o.value(v) - price).abs() <= 1e-13 * price.max(1.0) {
        return old_identified(o, v, price);
    }
    fail("E_NO_CONVERGENCE", "x")
}

/// `SplitMix64`, so the cases are fixed by the seed.
struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
    fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }
    fn range(&mut self, a: f64, b: f64) -> f64 {
        a + (b - a) * self.unit()
    }
}

fn case(r: &mut Rng, i: usize) -> (Option_, f64) {
    let call = r.next() & 1 == 0;
    let t = if i.is_multiple_of(97) {
        0.0
    } else {
        r.range(0.01, 30.0)
    };
    let model = match i % 3 {
        0 => Model::BlackScholes {
            spot: r.range(1.0, 500.0),
            rate: r.range(-0.02, 0.1),
            dividend: r.range(0.0, 0.05),
        },
        1 => Model::Black76 {
            forward: r.range(0.001, 0.1),
            discount: r.range(0.5, 1.0),
            shift: if r.next() & 1 == 0 { 0.0 } else { 0.02 },
        },
        _ => Model::Bachelier {
            forward: r.range(-0.02, 0.08),
            discount: r.range(0.5, 1.0),
        },
    };
    let fwd = match model {
        Model::BlackScholes { spot, .. } => spot,
        Model::Black76 { forward, .. } | Model::Bachelier { forward, .. } => forward,
    };
    // Strikes from near the money to deep out of the money (x 1e-3 to x 1e3 lognormal).
    let strike = match model {
        Model::Bachelier { .. } => fwd + r.range(-0.1, 0.1),
        _ => fwd * 10f64.powf(r.range(-3.0, 3.0)),
    };
    let o = Option_ {
        model,
        call,
        strike,
        t,
    };
    let vol = match model {
        Model::Bachelier { .. } => r.range(1e-4, 0.03),
        _ => r.range(0.005, 3.0),
    };
    let price = match i % 11 {
        0 => -1.0,     // below intrinsic
        1 => 1e300,    // above the upper bound
        2 => f64::NAN, // non-finite input
        3 => 0.0,      // at intrinsic for an OTM option
        _ if t > 0.0 => o.value(vol),
        _ => 1.0,
    };
    (o, price)
}

#[test]
fn fused_solver_is_bitwise_identical_to_the_old_one() {
    let mut r = Rng(0x5EED_2026_1122);
    let (mut ok, mut errs) = (0, 0);
    for i in 0..4000 {
        let (o, price) = case(&mut r, i);
        match (o.implied(price), old_implied(&o, price)) {
            (Ok(a), Ok(b)) => {
                assert_eq!(a.to_bits(), b.to_bits(), "case {i}: {o:?} {price}");
                ok += 1;
            }
            (Err(a), Err(b)) => {
                assert_eq!(a.code, b.code, "case {i}: {o:?} {price}");
                errs += 1;
            }
            (a, b) => panic!("case {i}: {o:?} {price}: new {a:?} old {b:?}"),
        }
    }
    // Both paths are exercised in quantity.
    assert!(ok > 2000 && errs > 500, "ok {ok} errs {errs}");
}
