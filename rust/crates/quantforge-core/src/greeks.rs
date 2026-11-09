//! Analytic and bumped option Greeks (`vol-greeks.md`).
use crate::black::{Model, Option_, d1_d2, phi};

use crate::error::{Result, fail};
use crate::stats::{normal_cdf, normal_pdf};

#[derive(Debug, Clone, PartialEq)]
pub struct Greeks {
    pub price: f64,
    pub delta: f64,
    pub gamma: f64,
    pub vega: f64,
    pub theta: f64,
    pub rho: f64,
    pub vanna: f64,
    pub volga: f64,
}

fn check(o: &Option_, v: f64) -> Result<()> {
    o.check(Some(v))?;
    if v <= 0.0 || o.t <= 0.0 {
        return fail("E_DOMAIN", "vol and expiry_years must be above 0");
    }
    Ok(())
}

pub fn analytic(o: &Option_, v: f64) -> Result<Greeks> {
    crate::error::finite("o", &o)?;
    crate::error::finite("v", &v)?;
    check(o, v)?;
    let (f, d, k) = o.fdk();
    let (t, p) = (o.t, phi(o.call));
    let r = t.sqrt();
    let price = o.value(v);
    Ok(match o.model {
        Model::BlackScholes {
            spot,
            rate,
            dividend,
        } => {
            let q = (-dividend * t).exp();
            let (d1, d2) = d1_d2(f, k, v, t);
            let n1 = normal_pdf(d1);
            let vega = spot * q * n1 * r;
            Greeks {
                price,
                delta: q * p * normal_cdf(p * d1),
                gamma: q * n1 / (spot * v * r),
                vega,
                theta: -spot * q * n1 * v / (2.0 * r) - p * rate * k * d * normal_cdf(p * d2)
                    + p * dividend * spot * q * normal_cdf(p * d1),
                rho: p * k * t * d * normal_cdf(p * d2),
                vanna: -q * n1 * d2 / v,
                volga: vega * d1 * d2 / v,
            }
        }
        Model::Black76 { .. } => {
            let (d1, d2) = d1_d2(f, k, v, t);
            let n1 = normal_pdf(d1);
            let vega = d * f * n1 * r;
            Greeks {
                price,
                delta: d * p * normal_cdf(p * d1),
                gamma: d * n1 / (f * v * r),
                vega,
                theta: -d * f * n1 * v / (2.0 * r),
                rho: -t * price,
                vanna: -d * n1 * d2 / v,
                volga: vega * d1 * d2 / v,
            }
        }
        Model::Bachelier { .. } => {
            let x = (f - k) / (v * r);
            let n = normal_pdf(x);
            Greeks {
                price,
                delta: d * p * normal_cdf(p * x),
                gamma: d * n / (v * r),
                vega: d * r * n,
                theta: -d * v * n / (2.0 * r),
                rho: -t * price,
                vanna: -d * n * x / v,
                volga: d * r * n * x * x / v,
            }
        }
    })
}

fn moved(o: &Option_, h: f64) -> Option_ {
    let mut m = *o;
    match &mut m.model {
        Model::BlackScholes { spot, .. } => *spot += h,
        Model::Black76 { forward, .. } | Model::Bachelier { forward, .. } => *forward += h,
    }
    m
}

/// `delta`, `gamma`, `vega`, `volga`, `vanna`.
pub fn bumped(o: &Option_, v: f64) -> Result<[f64; 5]> {
    crate::error::finite("o", &o)?;
    crate::error::finite("v", &v)?;
    check(o, v)?;
    let hu = match o.model {
        Model::BlackScholes { spot, .. } => 1e-4 * spot,
        Model::Black76 { forward, shift, .. } => 1e-4 * (forward + shift),
        Model::Bachelier { forward, .. } => 1e-4 * forward.abs().max(1.0),
    };
    let hv = 1e-3 * v;
    let (up, down) = (moved(o, hu), moved(o, -hu));
    let mid = o.value(v);
    let (vu, vd) = (up.value(v), down.value(v));
    let (sp, sm) = (o.value(v + hv), o.value(v - hv));
    Ok([
        (vu - vd) / (2.0 * hu),
        (vu - 2.0 * mid + vd) / (hu * hu),
        (sp - sm) / (2.0 * hv),
        (sp - 2.0 * mid + sm) / (hv * hv),
        (up.value(v + hv) - up.value(v - hv) - down.value(v + hv) + down.value(v - hv))
            / (4.0 * hu * hv),
    ])
}

impl crate::error::Finite for Greeks {
    fn is_all_finite(&self) -> bool {
        self.price.is_all_finite()
            && self.delta.is_all_finite()
            && self.gamma.is_all_finite()
            && self.vega.is_all_finite()
            && self.theta.is_all_finite()
            && self.rho.is_all_finite()
            && self.vanna.is_all_finite()
            && self.volga.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn analytic_agrees_with_bump_on_each_model() {
        for model in [
            Model::BlackScholes {
                spot: 100.0,
                rate: 0.03,
                dividend: 0.01,
            },
            Model::Black76 {
                forward: 100.0,
                discount: 0.97,
                shift: 5.0,
            },
            Model::Bachelier {
                forward: 100.0,
                discount: 0.97,
            },
        ] {
            let v = if matches!(model, Model::Bachelier { .. }) {
                20.0
            } else {
                0.2
            };
            let o = Option_ {
                model,
                call: false,
                strike: 95.0,
                t: 1.2,
            };
            let (a, b) = (analytic(&o, v).unwrap(), bumped(&o, v).unwrap());
            let pairs = [
                (a.delta, b[0]),
                (a.gamma, b[1]),
                (a.vega, b[2]),
                (a.volga, b[3]),
                (a.vanna, b[4]),
            ];
            for (x, y) in pairs {
                assert!((x - y).abs() < 2e-4 + 1e-4 * x.abs(), "{x} {y}");
            }
        }
    }
}
