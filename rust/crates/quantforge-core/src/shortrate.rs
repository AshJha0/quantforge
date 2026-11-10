//! One-factor short-rate models: Vasicek, CIR, Hull-White (`04-pricing/short-rate-models.md`).
//! Stage G wave 1, partial: zero-coupon bond prices only.
use crate::error::{Result, fail};

/// Discount curve for Hull-White: log-linear in discount factor through `(0, 1)`,
/// flat forward past the last pillar.
#[derive(Debug, Clone)]
pub struct HwCurve {
    times: Vec<f64>,
    logs: Vec<f64>,
}

impl HwCurve {
    pub fn new(times: &[f64], dfs: &[f64]) -> Result<HwCurve> {
        crate::error::finite("times", &times)?;
        crate::error::finite("discount_factors", &dfs)?;
        if times.is_empty()
            || times.len() != dfs.len()
            || times[0] <= 0.0
            || times.windows(2).any(|w| w[1] <= w[0])
        {
            return fail(
                "E_INPUT",
                "curve times must be positive and strictly increasing",
            );
        }
        if dfs.iter().any(|d| *d <= 0.0) {
            return fail("E_DOMAIN", "discount factors must be positive");
        }
        let mut t = vec![0.0];
        t.extend_from_slice(times);
        let mut l = vec![0.0];
        l.extend(dfs.iter().map(|d| d.ln()));
        Ok(HwCurve { times: t, logs: l })
    }

    /// Segment holding `t`, right-continuous at pillars; the last segment extends.
    fn seg(&self, t: f64) -> usize {
        let n = self.times.len() - 1;
        self.times
            .partition_point(|x| *x <= t)
            .saturating_sub(1)
            .min(n - 1)
    }

    /// Right-hand instantaneous forward `f(0, t)`.
    pub fn forward(&self, t: f64) -> f64 {
        let i = self.seg(t);
        -(self.logs[i + 1] - self.logs[i]) / (self.times[i + 1] - self.times[i])
    }

    pub fn ln_discount(&self, t: f64) -> f64 {
        let i = self.seg(t);
        self.logs[i] - self.forward(t) * (t - self.times[i])
    }
}

pub enum Model<'a> {
    Vasicek {
        a: f64,
        b: f64,
        sigma: f64,
    },
    Cir {
        a: f64,
        b: f64,
        sigma: f64,
    },
    HullWhite {
        a: f64,
        sigma: f64,
        curve: &'a HwCurve,
    },
}

/// `B = (1 - e^{-a tau}) / a` and `(B - tau) / a`, the latter by series for small `a tau`.
fn b_terms(a: f64, tau: f64) -> (f64, f64) {
    let b = -(-a * tau).exp_m1() / a;
    let x = a * tau;
    let s = if x.abs() < 1e-2 {
        // (B - tau)/a = sum_{n>=2} (-1)^{n+1} a^{n-2} tau^n / n!
        let (mut s, mut term) = (0.0, -tau * tau / 2.0);
        for n in 2..30 {
            s += term;
            term *= -x / f64::from(n + 1);
        }
        s
    } else {
        (b - tau) / a
    };
    (b, s)
}

/// `rates.shortrate.zcb`: `(discount_factor, zero_rate)` for `P(t, T)` given `r(t)`.
pub fn zcb(m: &Model, r: f64, t: f64, maturity: f64) -> Result<(f64, f64)> {
    crate::error::finite("short_rate", &r)?;
    crate::error::finite("t_years", &t)?;
    crate::error::finite("maturity_years", &maturity)?;
    let (a, sigma) = match m {
        Model::Vasicek { a, sigma, .. }
        | Model::Cir { a, sigma, .. }
        | Model::HullWhite { a, sigma, .. } => (*a, *sigma),
    };
    crate::error::finite("mean_reversion", &a)?;
    crate::error::finite("sigma", &sigma)?;
    if a <= 0.0 || sigma <= 0.0 {
        return fail("E_DOMAIN", "mean_reversion and sigma must be positive");
    }
    if t < 0.0 || maturity <= t {
        return fail("E_DOMAIN", "need 0 <= t_years < maturity_years");
    }
    let tau = maturity - t;
    let ln_p = match m {
        Model::Vasicek { b, .. } => {
            crate::error::finite("long_term_mean", b)?;
            let (bb, s) = b_terms(a, tau);
            let ln_a =
                s * a * b - s / a * sigma * sigma / 2.0 - sigma * sigma * bb * bb / (4.0 * a);
            ln_a - bb * r
        }
        Model::Cir { b, .. } => {
            crate::error::finite("long_term_mean", b)?;
            if *b <= 0.0 {
                return fail("E_DOMAIN", "CIR long_term_mean must be positive");
            }
            if r < 0.0 {
                return fail("E_DOMAIN", "CIR short_rate must not be negative");
            }
            let g = (a * a + 2.0 * sigma * sigma).sqrt();
            let em1 = (g * tau).exp_m1();
            let den = (g + a) * em1 + 2.0 * g;
            let bb = 2.0 * em1 / den;
            let ln_a =
                2.0 * a * b / (sigma * sigma) * ((2.0 * g).ln() + (a + g) * tau / 2.0 - den.ln());
            ln_a - bb * r
        }
        Model::HullWhite { curve, .. } => {
            let (bb, _) = b_terms(a, tau);
            let ln_a = curve.ln_discount(maturity) - curve.ln_discount(t)
                + bb * curve.forward(t)
                + sigma * sigma / (4.0 * a) * (-2.0 * a * t).exp_m1() * bb * bb;
            ln_a - bb * r
        }
    };
    Ok((ln_p.exp(), -ln_p / tau))
}
