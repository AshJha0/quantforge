//! Par and key-rate risk (`06-risk/par-and-key-rate.md`, R2.1). Bump and revalue, no AD. Every
//! result is money per basis point, with the sign of the value change for a +1 bp move.
use crate::bonds::{Bond, dirty_on};
use crate::conventions::Overnight;
use crate::curve::{Curve, CurveInput, Discount, Interpolation, SolveMethod, curve_time};
use crate::dates::Date;
use crate::error::{Result, fail};
use crate::ois::{OisCurveProblem, OisLegs, OisQuote, OisTrade, pv_of_legs};

const BP: f64 = 1e-4;

#[derive(Debug, Clone)]
pub enum Product {
    Ois(OisTrade),
    Bond {
        bond: Bond,
        settlement: Date,
        notional: f64,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Scheme {
    Central,
    Forward,
}

/// `bump_bp` and the scheme, checked first (`E_DOMAIN`).
#[derive(Debug, Clone, Copy)]
pub struct Bump {
    pub bp: f64,
    pub scheme: Scheme,
}

impl Bump {
    pub fn new(bp: f64, scheme: Scheme) -> Result<Bump> {
        if bp == 0.0 || !(0.0..=100.0).contains(&bp) {
            return fail("E_DOMAIN", "bump_bp must be in (0, 100]");
        }
        Ok(Bump { bp, scheme })
    }

    /// Money per 1 bp from the bumped values; `down` is used only by `CENTRAL`.
    fn risk(&self, up: f64, base: f64, down: impl FnOnce() -> Result<f64>) -> Result<f64> {
        Ok(match self.scheme {
            Scheme::Central => (up - down()?) / (2.0 * self.bp),
            Scheme::Forward => (up - base) / self.bp,
        })
    }
}

/// `D(t) exp(-s(t) t)`: a continuously compounded zero shift of `s(t)` on a base curve.
struct Shifted<'a, F: Fn(f64) -> f64> {
    base: &'a Curve,
    shift: F,
}

impl<F: Fn(f64) -> f64> Discount for Shifted<'_, F> {
    fn discount(&self, d: Date) -> Result<f64> {
        let t = curve_time(self.base.as_of, d);
        Ok(self.base.discount(d)? * (-(self.shift)(t) * t).exp())
    }
}

/// A product with its dates fixed, valued on any discount function from `as_of`.
struct Priced<'a> {
    product: &'a Product,
    as_of: Date,
    legs: Option<OisLegs>,
}

impl<'a> Priced<'a> {
    fn new(product: &'a Product, as_of: Date) -> Result<Priced<'a>> {
        let legs = match product {
            Product::Ois(t) => Some(OisLegs::new(&t.convention, as_of, t.tenor)?),
            Product::Bond { .. } => None,
        };
        Ok(Priced {
            product,
            as_of,
            legs,
        })
    }

    fn value<C: Discount + ?Sized>(&self, c: &C) -> Result<f64> {
        match (self.product, &self.legs) {
            (Product::Ois(t), Some(legs)) => pv_of_legs(legs, c, t),
            (
                Product::Bond {
                    bond,
                    settlement,
                    notional,
                },
                _,
            ) => Ok(notional * dirty_on(bond, *settlement, self.as_of, c, 0.0)?.0 / 100.0),
            (Product::Ois(_), None) => unreachable!("OIS legs are built in new"),
        }
    }
}

/// `E_DOMAIN` for the notional comes before the `E_INPUT` rules, so it is checked on its own.
pub fn check_notional(product: &Product) -> Result<()> {
    match product {
        Product::Bond { notional, .. } if notional.is_nan() || *notional <= 0.0 => {
            fail("E_DOMAIN", "notional must be positive")
        }
        _ => Ok(()),
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ParRisk {
    pub value: f64,
    pub par_dv01: f64,
    pub par_buckets: Vec<f64>,
}

fn bootstrap(p: &OisCurveProblem, quotes: &[f64]) -> Result<Curve> {
    Ok(p.solve(quotes, SolveMethod::Sequential)?.curve)
}

pub fn par(
    convention: &Overnight,
    as_of: Date,
    quotes: &[OisQuote],
    interpolation: Interpolation,
    product: &Product,
    bump: Bump,
) -> Result<ParRisk> {
    check_notional(product)?;
    if let Product::Ois(t) = product
        && t.convention.id != convention.id
    {
        return fail("E_INPUT", "the trade's convention differs from the curve's");
    }
    let p = OisCurveProblem::new(convention, as_of, quotes, interpolation)?;
    let priced = Priced::new(product, as_of)?;
    let base = priced.value(&bootstrap(&p, &p.mids)?)?;
    let h = bump.bp * BP;
    let value_with = |shift: &dyn Fn(usize) -> f64| -> Result<f64> {
        let q: Vec<f64> = (0..p.mids.len()).map(|j| p.mids[j] + shift(j)).collect();
        priced.value(&bootstrap(&p, &q)?)
    };
    let par_dv01 = bump.risk(value_with(&|_| h)?, base, || value_with(&|_| -h))?;
    let mut par_buckets = Vec::with_capacity(p.mids.len());
    for k in 0..p.mids.len() {
        let one = |s: f64| move |j: usize| if j == k { s } else { 0.0 };
        par_buckets.push(bump.risk(value_with(&one(h))?, base, || value_with(&one(-h)))?);
    }
    Ok(ParRisk {
        value: base,
        par_dv01,
        par_buckets,
    })
}

#[derive(Debug, Clone, PartialEq)]
pub enum KeyMode {
    Triangular(Vec<Date>),
    Pillar,
}

#[derive(Debug, Clone, PartialEq)]
pub struct KeyRateRisk {
    pub value: f64,
    pub key_rates: Vec<f64>,
    pub zero_dv01: f64,
}

/// Triangular weight of key `i` at time `t`; the weights sum to 1 at every `t`.
fn triangle(keys: &[f64], i: usize, t: f64) -> f64 {
    let n = keys.len();
    if t <= keys[0] {
        return if i == 0 { 1.0 } else { 0.0 };
    }
    if t >= keys[n - 1] {
        return if i == n - 1 { 1.0 } else { 0.0 };
    }
    let k = keys.partition_point(|&x| x <= t); // keys[k-1] <= t < keys[k]
    let u = (t - keys[k - 1]) / (keys[k] - keys[k - 1]);
    if i == k - 1 {
        1.0 - u
    } else if i == k {
        u
    } else {
        0.0
    }
}

pub fn key_rate(
    curve: &CurveInput,
    mode: &KeyMode,
    product: &Product,
    bump: Bump,
) -> Result<KeyRateRisk> {
    check_notional(product)?;
    if let KeyMode::Triangular(keys) = mode
        && (keys.is_empty() || keys[0] <= curve.as_of || keys.windows(2).any(|w| w[1] <= w[0]))
    {
        return fail("E_INPUT", "key_dates must increase and follow as_of");
    }
    let base_curve = Curve::new(curve)?;
    let priced = Priced::new(product, curve.as_of)?;
    let base = priced.value(&base_curve)?;
    let h = bump.bp * BP;
    let shifted = |s: f64, w: &dyn Fn(f64) -> f64| -> Result<f64> {
        priced.value(&Shifted {
            base: &base_curve,
            shift: |t: f64| s * w(t),
        })
    };
    let zero_dv01 = bump.risk(shifted(h, &|_| 1.0)?, base, || shifted(-h, &|_| 1.0))?;
    let mut key_rates = Vec::new();
    match mode {
        KeyMode::Triangular(dates) => {
            let keys: Vec<f64> = dates.iter().map(|d| curve_time(curve.as_of, *d)).collect();
            for i in 0..keys.len() {
                let w = |t: f64| triangle(&keys, i, t);
                key_rates.push(bump.risk(shifted(h, &w)?, base, || shifted(-h, &w))?);
            }
        }
        KeyMode::Pillar => {
            let at = |i: usize, s: f64| -> Result<f64> {
                let mut c = curve.clone();
                let (d, df) = c.pillars[i];
                c.pillars[i].1 = df * (-s * curve_time(curve.as_of, d)).exp();
                priced.value(&Curve::new(&c)?)
            };
            for i in 0..curve.pillars.len() {
                key_rates.push(bump.risk(at(i, h)?, base, || at(i, -h))?);
            }
        }
    }
    Ok(KeyRateRisk {
        value: base,
        key_rates,
        zero_dv01,
    })
}

#[derive(Debug, Clone, PartialEq)]
pub struct Jacobian {
    pub pillar_dates: Vec<Date>,
    pub zero_rates: Vec<f64>,
    /// Rows for pillars, columns for quotes.
    pub jacobian: Vec<Vec<f64>>,
}

pub fn jacobian(
    convention: &Overnight,
    as_of: Date,
    quotes: &[OisQuote],
    interpolation: Interpolation,
    bump_bp: f64,
) -> Result<Jacobian> {
    let bump = Bump::new(bump_bp, Scheme::Central)?;
    let p = OisCurveProblem::new(convention, as_of, quotes, interpolation)?;
    let base = p.solve(&p.mids, SolveMethod::Sequential)?;
    let zeros = |c: &Curve| -> Result<Vec<f64>> {
        base.dates
            .iter()
            .map(|d| Ok(-c.discount(*d)?.ln() / curve_time(as_of, *d)))
            .collect()
    };
    let zero_rates = zeros(&base.curve)?;
    let h = bump.bp * BP;
    let n = p.mids.len();
    let mut jac = vec![vec![0.0; n]; base.dates.len()];
    for j in 0..n {
        let at = |s: f64| -> Result<Vec<f64>> {
            let mut q = p.mids.clone();
            q[j] += s;
            zeros(&bootstrap(&p, &q)?)
        };
        let (up, down) = (at(h)?, at(-h)?);
        for (i, row) in jac.iter_mut().enumerate() {
            // A pillar depends only on quotes up to its own: above the diagonal is exactly 0.
            if j <= i {
                row[j] = (up[i] - down[i]) / (2.0 * h);
            }
        }
    }
    Ok(Jacobian {
        pillar_dates: base.dates,
        zero_rates,
        jacobian: jac,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn triangle_weights_sum_to_one() {
        let keys = [1.0, 2.0, 5.0];
        for t in [0.0, 0.5, 1.0, 1.5, 2.0, 3.5, 5.0, 9.0] {
            let s: f64 = (0..3).map(|i| triangle(&keys, i, t)).sum();
            assert!((s - 1.0).abs() < 1e-15, "{t}");
        }
        assert_eq!(triangle(&keys, 1, 1.5), 0.5);
        assert_eq!(triangle(&keys, 2, 3.5), 0.5);
        assert_eq!(triangle(&keys, 0, 3.5), 0.0);
        assert_eq!(triangle(&[2.0], 0, 7.0), 1.0);
    }

    #[test]
    fn bump_bounds_and_schemes() {
        assert_eq!(
            Bump::new(0.0, Scheme::Central).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            Bump::new(100.5, Scheme::Central).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            Bump::new(f64::NAN, Scheme::Forward).unwrap_err().code,
            "E_DOMAIN"
        );
        let c = Bump::new(2.0, Scheme::Central).unwrap();
        assert_eq!(c.risk(5.0, 0.0, || Ok(-3.0)).unwrap(), 2.0);
        let f = Bump::new(2.0, Scheme::Forward).unwrap();
        assert_eq!(f.risk(5.0, 1.0, || unreachable!()).unwrap(), 2.0);
    }

    fn flat_curve() -> CurveInput {
        let as_of = Date::new(2026, 11, 6);
        let pillars = [1, 3, 10]
            .iter()
            .map(|y| {
                let d = Date::new(2026 + y, 11, 6);
                (d, (-0.04 * curve_time(as_of, d)).exp())
            })
            .collect();
        CurveInput {
            as_of,
            interpolation: Interpolation::LogLinearDf,
            pillars,
            jumps: Vec::new(),
        }
    }

    fn bond(notional: f64) -> Product {
        Product::Bond {
            bond: Bond::new(Date::new(2031, 11, 15), 0.04, 2),
            settlement: Date::new(2026, 11, 9),
            notional,
        }
    }

    #[test]
    fn key_rate_buckets_add_up_and_check_inputs() {
        let c = flat_curve();
        let b = Bump::new(1.0, Scheme::Central).unwrap();
        let keys = KeyMode::Triangular(vec![Date::new(2028, 11, 6), Date::new(2033, 11, 6)]);
        for mode in [keys, KeyMode::Pillar] {
            let r = key_rate(&c, &mode, &bond(1e6), b).unwrap();
            let sum: f64 = r.key_rates.iter().sum();
            assert!(r.zero_dv01 < 0.0, "a long bond loses when rates rise");
            assert!(
                (sum - r.zero_dv01).abs() < 1e-6 * r.zero_dv01.abs(),
                "{mode:?}"
            );
        }
        let late = KeyMode::Triangular(vec![c.as_of]);
        assert_eq!(
            key_rate(&c, &late, &bond(1e6), b).unwrap_err().code,
            "E_INPUT"
        );
        let empty = KeyMode::Triangular(Vec::new());
        assert_eq!(
            key_rate(&c, &empty, &bond(1e6), b).unwrap_err().code,
            "E_INPUT"
        );
        // E_DOMAIN for the notional outranks the E_INPUT key-date rule.
        assert_eq!(
            key_rate(&c, &late, &bond(0.0), b).unwrap_err().code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn forward_scheme_is_close_to_central() {
        let c = flat_curve();
        let central = key_rate(
            &c,
            &KeyMode::Pillar,
            &bond(1e6),
            Bump::new(1.0, Scheme::Central).unwrap(),
        );
        let forward = key_rate(
            &c,
            &KeyMode::Pillar,
            &bond(1e6),
            Bump::new(1.0, Scheme::Forward).unwrap(),
        );
        let (c0, f0) = (central.unwrap().zero_dv01, forward.unwrap().zero_dv01);
        assert!((c0 - f0).abs() < 1e-3 * c0.abs());
        assert!(c0 != f0);
    }
}
