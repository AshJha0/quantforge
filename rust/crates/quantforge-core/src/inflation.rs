//! Inflation curves, seasonality and linkers (`02-curves/inflation.md`).
use crate::bonds::{Bond, price_from_yield};
use crate::curve::Curve;
use crate::dates::{Date, days_in_month};
use crate::error::{Result, err, fail};
use std::collections::HashMap;

/// Month index `12 year + month - 1`.
pub fn month_index(y: i32, m: u32) -> i64 {
    12 * i64::from(y) + i64::from(m) - 1
}

#[derive(Debug, Clone)]
pub struct CpiCurve {
    base: i64,
    base_cpi: f64,
    /// `(month index, ln I)`, from the base node.
    nodes: Vec<(i64, f64)>,
    seasonality: Option<[f64; 12]>,
}

impl CpiCurve {
    pub fn new(
        base_month: i64,
        base_cpi: f64,
        quotes: &[(i64, f64)],
        seasonality: Option<&[f64]>,
    ) -> Result<CpiCurve> {
        if quotes.is_empty()
            || quotes[0].0 <= 0
            || quotes.windows(2).any(|w| w[1].0 <= w[0].0)
            || quotes.iter().any(|q| q.0 > 100)
        {
            return fail(
                "E_INPUT",
                "years must be strictly increasing positive integers",
            );
        }
        if quotes.iter().any(|q| q.1 <= -1.0) {
            return fail("E_DOMAIN", "a rate is at or below -1");
        }
        let seasonality = match seasonality {
            None => None,
            Some(s) if s.len() != 12 => {
                return fail("E_INPUT", "seasonality needs 12 factors");
            }
            Some(s) => {
                if s.iter().any(|x| *x <= 0.0) {
                    return fail("E_DOMAIN", "a seasonal factor is not positive");
                }
                let mut a = [0.0; 12];
                a.copy_from_slice(s);
                Some(a)
            }
        };
        if base_cpi <= 0.0 {
            return fail("E_DOMAIN", "base_cpi must be positive");
        }
        let l0 = base_cpi.ln();
        let mut nodes = vec![(base_month, l0)];
        for (n, k) in quotes {
            nodes.push((base_month + 12 * n, l0 + *n as f64 * k.ln_1p()));
        }
        Ok(CpiCurve {
            base: base_month,
            base_cpi,
            nodes,
            seasonality,
        })
    }

    fn factor(&self, k: i64) -> f64 {
        self.seasonality.map_or(1.0, |s| {
            s[k.rem_euclid(12) as usize] / s[self.base.rem_euclid(12) as usize]
        })
    }

    pub fn cpi(&self, k: i64) -> Result<f64> {
        if k < self.base {
            return fail("E_OUT_OF_RANGE", "month is before base_month");
        }
        let n = self.nodes.len() - 1;
        let i = self
            .nodes
            .partition_point(|x| x.0 <= k)
            .saturating_sub(1)
            .min(n - 1);
        let ((k0, l0), (k1, l1)) = (self.nodes[i], self.nodes[i + 1]);
        let u = (k - k0) as f64 / (k1 - k0) as f64;
        Ok(((1.0 - u) * l0 + u * l1).exp() * self.factor(k))
    }

    pub fn index_ratio(&self, years: i64) -> Result<f64> {
        Ok(self.cpi(self.base + 12 * years)? / self.base_cpi)
    }
}

/// US TIPS reference CPI for `d`, from a month lookup.
pub fn reference_cpi(d: Date, lookup: &dyn Fn(i64) -> Result<f64>) -> Result<f64> {
    let m = month_index(d.y, d.m);
    let (a, b) = (lookup(m - 3)?, lookup(m - 2)?);
    Ok(a + f64::from(d.d - 1) / f64::from(days_in_month(d.y, d.m)) * (b - a))
}

#[derive(Debug, Clone, Copy)]
pub struct Zcis {
    pub years: i64,
    pub fixed_rate: f64,
    pub notional: f64,
    pub receive_inflation: bool,
    pub payment_date: Date,
}

/// `(pv, index_ratio)`.
pub fn zcis_pv(c: &CpiCurve, discount: &Curve, t: &Zcis) -> Result<(f64, f64)> {
    if t.years <= 0 || t.years > 100 {
        return fail("E_INPUT", "years must be a positive integer");
    }
    let ratio = c.index_ratio(t.years)?;
    let sign = if t.receive_inflation { 1.0 } else { -1.0 };
    let fixed = (1.0 + t.fixed_rate).powf(t.years as f64);
    Ok((
        sign * t.notional * (ratio - fixed) * discount.discount(t.payment_date)?,
        ratio,
    ))
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LinkerPrice {
    pub ref_cpi: f64,
    pub index_ratio: f64,
    pub real_clean: f64,
    pub real_accrued: f64,
    pub nominal_clean: f64,
    pub nominal_accrued: f64,
}

pub fn linker_price(
    b: &Bond,
    settlement: Date,
    real_yield: f64,
    base_ref_cpi: f64,
    fixings: &[(i64, f64)],
) -> Result<LinkerPrice> {
    let mut table = HashMap::new();
    for (m, v) in fixings {
        if table.insert(*m, *v).is_some() {
            return fail("E_INPUT", "two fixings for one month");
        }
    }
    let p = price_from_yield(b, settlement, real_yield)?;
    let lookup = |m: i64| {
        table
            .get(&m)
            .copied()
            .ok_or_else(|| err("E_INPUT", "a needed CPI fixing is missing"))
    };
    let ref_cpi = reference_cpi(settlement, &lookup)?;
    if base_ref_cpi <= 0.0 {
        return fail("E_DOMAIN", "base_ref_cpi must be positive");
    }
    let r = ref_cpi / base_ref_cpi;
    Ok(LinkerPrice {
        ref_cpi,
        index_ratio: r,
        real_clean: p.clean,
        real_accrued: p.accrued,
        nominal_clean: p.clean * r,
        nominal_accrued: p.accrued * r,
    })
}

pub fn linker_price_curve(
    b: &Bond,
    settlement: Date,
    base_ref_cpi: f64,
    c: &CpiCurve,
    discount: &Curve,
) -> Result<f64> {
    if base_ref_cpi <= 0.0 {
        return fail("E_DOMAIN", "base_ref_cpi must be positive");
    }
    let flows = b.flows(settlement)?;
    let lookup = |m: i64| c.cpi(m);
    let mut sum = 0.0;
    for (d, cf) in &flows.flows {
        sum += cf * reference_cpi(*d, &lookup)? / base_ref_cpi * discount.discount(*d)?;
    }
    Ok(sum / discount.discount(settlement)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn d(s: &str) -> Date {
        Date::parse(s).unwrap()
    }

    fn curve(s: Option<&[f64]>) -> CpiCurve {
        CpiCurve::new(month_index(2026, 8), 300.0, &[(1, 0.02), (3, 0.025)], s).unwrap()
    }

    #[test]
    fn pillars_reprice_with_and_without_seasonality() {
        let s = [
            1.01, 0.99, 1.0, 1.0, 1.0, 1.0, 1.0, 1.02, 1.0, 1.0, 1.0, 0.98,
        ];
        for c in [curve(None), curve(Some(&s))] {
            assert!((c.index_ratio(3).unwrap() - 1.025f64.powi(3)).abs() < 1e-14);
            assert!((c.cpi(month_index(2027, 8)).unwrap() - 306.0).abs() < 1e-12);
        }
        let k = month_index(2027, 1);
        let plain = curve(None).cpi(k).unwrap();
        assert!((curve(Some(&s)).cpi(k).unwrap() - plain * 1.01 / 1.02).abs() < 1e-12);
        assert_eq!(
            curve(None).cpi(month_index(2026, 7)).unwrap_err().code,
            "E_OUT_OF_RANGE"
        );
    }

    #[test]
    fn curve_checks() {
        let b = month_index(2026, 8);
        let e =
            |q: &[(i64, f64)], s: Option<&[f64]>| CpiCurve::new(b, 300.0, q, s).unwrap_err().code;
        assert_eq!(e(&[(2, 0.02), (1, 0.02)], None), "E_INPUT");
        assert_eq!(e(&[], None), "E_INPUT");
        assert_eq!(e(&[(1, -1.0)], None), "E_DOMAIN");
        assert_eq!(e(&[(1, 0.02)], Some(&[1.0; 11])), "E_INPUT");
        let mut z = [1.0; 12];
        z[3] = 0.0;
        assert_eq!(e(&[(1, 0.02)], Some(&z)), "E_DOMAIN");
    }

    #[test]
    fn reference_cpi_interpolates_daily() {
        let f = |m: i64| {
            Ok(if m == month_index(2026, 8) {
                300.0
            } else {
                303.0
            })
        };
        assert_eq!(reference_cpi(d("2026-11-01"), &f).unwrap(), 300.0);
        assert!((reference_cpi(d("2026-11-16"), &f).unwrap() - 301.5).abs() < 1e-12);
    }

    #[test]
    fn linker_and_zcis() {
        let b = Bond::new(d("2029-11-15"), 0.0425, 2);
        let fx = [(month_index(2026, 8), 300.0), (month_index(2026, 9), 303.0)];
        let p = linker_price(&b, d("2026-11-16"), 0.02, 300.0, &fx).unwrap();
        assert!((p.index_ratio - 1.005).abs() < 1e-12);
        assert_eq!(p.nominal_clean, p.real_clean * p.index_ratio);
        let e = linker_price(&b, d("2027-03-09"), 0.02, 300.0, &fx).unwrap_err();
        assert_eq!(e.code, "E_INPUT");
        let as_of = d("2026-11-06");
        let i = crate::curve::Interpolation::LogLinearDf;
        let disc = Curve::from_logs(as_of, i, &[d("2040-01-01")], &[-0.5]);
        let t = Zcis {
            years: 3,
            fixed_rate: 0.025,
            notional: 1e6,
            receive_inflation: true,
            payment_date: d("2029-11-13"),
        };
        let (pv, r) = zcis_pv(&curve(None), &disc, &t).unwrap();
        assert!(pv.abs() < 1e-6 && (r - 1.025f64.powi(3)).abs() < 1e-14);
        let v = linker_price_curve(&b, d("2026-11-09"), 300.0, &curve(None), &disc).unwrap();
        assert!(v > 100.0);
    }
}
