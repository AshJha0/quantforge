//! Variance swaps: discrete replication and realized variance (`05-volatility/variance-swaps.md`,
//! rulings E-B3, E-B4).
use crate::black::black;
use crate::dates::Date;

use crate::error::{Result, fail};

pub struct Replication<'a> {
    pub as_of: Date,
    pub maturity: Date,
    pub spot: f64,
    pub rate: f64,
    pub dividend_yield: f64,
    pub put_strikes: &'a [f64],
    pub call_strikes: &'a [f64],
    /// `(strike, vol)`, one per strike of the union of the two lists.
    pub vols: &'a [(f64, f64)],
    pub extension_step: f64,
    pub variance_strike: f64,
    pub variance_notional: f64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Fair {
    pub fair_variance: f64,
    pub fair_vol: f64,
    pub pv: f64,
}

fn has_repeat(sorted: &[f64]) -> bool {
    sorted.windows(2).any(|w| w[0] == w[1])
}

fn sorted(v: &[f64]) -> Vec<f64> {
    let mut s = v.to_vec();
    s.sort_by(f64::total_cmp);
    s
}

/// Weights `w_j = s_j - s_{j-1}` on `strikes` walked in the given order, closed by `extra`.
fn weights(strikes: &[f64], extra: f64, f: &dyn Fn(f64) -> f64) -> Vec<f64> {
    let mut walk = strikes.to_vec();
    walk.push(extra);
    let mut prev = 0.0;
    walk.windows(2)
        .map(|w| {
            let s = (f(w[1]) - f(w[0])).abs() / (w[1] - w[0]).abs();
            let wt = s - prev;
            prev = s;
            wt
        })
        .collect()
}

pub fn fair_strike(x: &Replication) -> Result<Fair> {
    if x.maturity <= x.as_of {
        return fail("E_INPUT", "maturity must be after as_of");
    }
    let (puts, calls) = (sorted(x.put_strikes), sorted(x.call_strikes));
    if puts.is_empty() || calls.is_empty() || has_repeat(&puts) || has_repeat(&calls) {
        return fail("E_INPUT", "strike lists must be non-empty with no repeats");
    }
    let s0 = x.spot;
    if puts.iter().any(|&k| k > s0) || calls.iter().any(|&k| k < s0) {
        return fail(
            "E_INPUT",
            "puts must be at or below spot and calls at or above",
        );
    }
    let mut union = puts.clone();
    union.extend(&calls);
    union = sorted(&union);
    union.dedup();
    let listed = sorted(&x.vols.iter().map(|v| v.0).collect::<Vec<_>>());
    if listed != union {
        return fail("E_INPUT", "vols must list each strike exactly once");
    }
    let dk = x.extension_step;
    if s0.is_nan() || s0 <= 0.0 || x.vols.iter().any(|v| v.1.is_nan() || v.1 <= 0.0) {
        return fail("E_DOMAIN", "spot and vols must be positive");
    }
    if dk.is_nan() || dk <= 0.0 || puts[0] - dk <= 0.0 {
        return fail(
            "E_DOMAIN",
            "extension step must be positive and keep strikes positive",
        );
    }
    let t = (x.maturity.serial() - x.as_of.serial()) as f64 / 365.0;
    let (r, q) = (x.rate, x.dividend_yield);
    let d = (-r * t).exp();
    let fwd = s0 * ((r - q) * t).exp();
    let payoff = |k: f64| 2.0 / t * ((k - s0) / s0 - (k / s0).ln());
    let vol = |k: f64| x.vols.iter().find(|v| v.0 == k).map_or(f64::NAN, |v| v.1);
    let calls_w = weights(&calls, calls[calls.len() - 1] + dk, &payoff);
    let puts_desc: Vec<f64> = puts.iter().rev().copied().collect();
    let puts_w = weights(&puts_desc, puts[0] - dk, &payoff);
    let pi: f64 = calls
        .iter()
        .zip(&calls_w)
        .map(|(&k, w)| w * black(true, fwd, k, vol(k), t, d))
        .chain(
            puts_desc
                .iter()
                .zip(&puts_w)
                .map(|(&k, w)| w * black(false, fwd, k, vol(k), t, d)),
        )
        .sum();
    let fair_variance = 2.0 / t * ((r - q) * t - (fwd / s0 - 1.0)) + pi / d;
    if fair_variance.is_nan() || fair_variance < 0.0 {
        // Ruling E-B36: checked after the replication.
        return fail("E_DOMAIN", "replicated variance is below 0");
    }
    Ok(Fair {
        fair_variance,
        fair_vol: fair_variance.sqrt(),
        pv: x.variance_notional * d * (fair_variance - x.variance_strike),
    })
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Realized {
    pub realized_variance: f64,
    pub realized_vol: f64,
    pub payoff: f64,
}

/// Divisor `m`, no mean removed (ruling E-B4); payoff undiscounted.
pub fn realized(
    prices: &[f64],
    periods_per_year: f64,
    strike: f64,
    notional: f64,
) -> Result<Realized> {
    crate::error::finite("prices", &prices)?;
    crate::error::finite("periods_per_year", &periods_per_year)?;
    crate::error::finite("strike", &strike)?;
    crate::error::finite("notional", &notional)?;
    if prices.len() < 2 {
        return fail("E_INPUT", "at least 2 prices are required");
    }
    if prices.iter().any(|p| p.is_nan() || *p <= 0.0) {
        return fail("E_DOMAIN", "prices must be positive");
    }
    let sq: f64 = prices.windows(2).map(|w| (w[1] / w[0]).ln().powi(2)).sum();
    let v = periods_per_year * sq / (prices.len() - 1) as f64;
    Ok(Realized {
        realized_variance: v,
        realized_vol: v.sqrt(),
        payoff: notional * (v - strike),
    })
}

impl crate::error::Finite for Fair {
    fn is_all_finite(&self) -> bool {
        self.fair_variance.is_all_finite()
            && self.fair_vol.is_all_finite()
            && self.pv.is_all_finite()
    }
}

impl crate::error::Finite for Realized {
    fn is_all_finite(&self) -> bool {
        self.realized_variance.is_all_finite()
            && self.realized_vol.is_all_finite()
            && self.payoff.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn realized_worked_example() {
        let r = realized(
            &[100.0, 101.0, 99.5, 100.25, 102.0, 101.5],
            252.0,
            0.04,
            1e6,
        )
        .unwrap();
        assert!((r.realized_variance - 0.0354274).abs() < 1e-6);
        assert!((r.payoff - -4572.61).abs() < 0.1);
        assert_eq!(
            realized(&[1.0], 252.0, 0.0, 1.0).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(
            realized(&[1.0, 0.0], 252.0, 0.0, 1.0).unwrap_err().code,
            "E_DOMAIN"
        );
    }

    fn case<'a>(puts: &'a [f64], calls: &'a [f64], vols: &'a [(f64, f64)]) -> Replication<'a> {
        Replication {
            as_of: Date::new(2025, 1, 1),
            maturity: Date::new(2026, 1, 1),
            spot: 100.0,
            rate: 0.03,
            dividend_yield: 0.01,
            put_strikes: puts,
            call_strikes: calls,
            vols,
            extension_step: 10.0,
            variance_strike: 0.04,
            variance_notional: 1e6,
        }
    }

    #[test]
    fn first_call_weights_match_the_spec() {
        let f = |k: f64| 2.0 * ((k - 100.0) / 100.0 - (k / 100.0).ln());
        let w = weights(&[100.0, 110.0, 120.0], 130.0, &f);
        assert!((w[0] - 9.3796e-4).abs() < 1e-8);
        assert!((w[1] - 1.6598e-3).abs() < 1e-7);
    }

    #[test]
    fn flat_smile_fine_strip_approaches_the_vol() {
        let puts: Vec<f64> = (0..=380).map(|i| 100.0 - 0.25 * f64::from(i)).collect();
        let calls: Vec<f64> = (0..=1600).map(|i| 100.0 + 0.25 * f64::from(i)).collect();
        let mut vols: Vec<(f64, f64)> = puts.iter().map(|&k| (k, 0.2)).collect();
        vols.extend(calls.iter().skip(1).map(|&k| (k, 0.2)));
        let mut c = case(&puts, &calls, &vols);
        c.extension_step = 0.25;
        let f = fair_strike(&c).unwrap();
        assert!((f.fair_vol - 0.2).abs() < 2e-3, "{}", f.fair_vol);
        let d = (-0.03f64).exp();
        assert!((f.pv - 1e6 * d * (f.fair_variance - 0.04)).abs() < 1e-6);
    }

    #[test]
    fn fair_strike_checks() {
        let v = [(90.0, 0.2), (100.0, 0.2), (110.0, 0.2)];
        let (p, c) = ([90.0, 100.0], [100.0, 110.0]);
        let code = |x: &Replication| fair_strike(x).unwrap_err().code;
        assert!(fair_strike(&case(&p, &c, &v)).is_ok());
        let mut x = case(&p, &c, &v);
        x.maturity = x.as_of;
        assert_eq!(code(&x), "E_INPUT");
        assert_eq!(code(&case(&[], &c, &v)), "E_INPUT");
        assert_eq!(code(&case(&[90.0, 90.0], &c, &v)), "E_INPUT");
        assert_eq!(code(&case(&[110.0], &c, &v)), "E_INPUT");
        assert_eq!(code(&case(&p, &[90.0], &v)), "E_INPUT");
        assert_eq!(code(&case(&p, &c, &v[..2])), "E_INPUT");
        assert_eq!(
            code(&case(&p, &c, &[(90.0, 0.2), (100.0, 0.0), (110.0, 0.2)])),
            "E_DOMAIN"
        );
        let mut x = case(&p, &c, &v);
        x.extension_step = 90.0;
        assert_eq!(code(&x), "E_DOMAIN");
        x.extension_step = 0.0;
        assert_eq!(code(&x), "E_DOMAIN");
    }
}
