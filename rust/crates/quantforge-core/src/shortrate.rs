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
    /// Builds the curve from pillar times and discount factors (`(0, 1)` is prepended).
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

    /// `ln P(0, t)`, log-linear between pillars and flat-forward past the last.
    pub fn ln_discount(&self, t: f64) -> f64 {
        let i = self.seg(t);
        self.logs[i] - self.forward(t) * (t - self.times[i])
    }
}

/// A one-factor short-rate model with its parameters.
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

/// CIR `(ln A, B)` at time to maturity `tau` [BM 3.25].
fn cir_factors(a: f64, b: f64, sigma: f64, tau: f64) -> (f64, f64) {
    let g = (a * a + 2.0 * sigma * sigma).sqrt();
    let em1 = (g * tau).exp_m1();
    let den = (g + a) * em1 + 2.0 * g;
    let bb = 2.0 * em1 / den;
    let ln_a = 2.0 * a * b / (sigma * sigma) * ((2.0 * g).ln() + (a + g) * tau / 2.0 - den.ln());
    (ln_a, bb)
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
            let (ln_a, bb) = cir_factors(a, *b, sigma, tau);
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

/// `rates.shortrate.zcb_option` (Jamshidian for Vasicek and Hull-White, the noncentral
/// chi-square formula [BM 3.26] for CIR):
/// `(price, P(0, T), P(0, S))`. `r` is `r(0)` for Vasicek and CIR, ignored for Hull-White.
pub fn zcb_option(
    m: &Model,
    r: f64,
    call: bool,
    strike: f64,
    expiry: f64,
    maturity: f64,
    notional: f64,
) -> Result<(f64, f64, f64)> {
    crate::error::finite("strike", &strike)?;
    crate::error::finite("expiry_years", &expiry)?;
    crate::error::finite("notional", &notional)?;
    if !(0.0 < expiry && expiry < maturity) || strike <= 0.0 {
        return fail("E_DOMAIN", "need 0 < expiry < maturity and strike > 0");
    }
    let (a, sigma, pt, ps) = match m {
        Model::Vasicek { a, sigma, .. } => (
            *a,
            *sigma,
            zcb(m, r, 0.0, expiry)?.0,
            zcb(m, r, 0.0, maturity)?.0,
        ),
        Model::HullWhite { a, sigma, curve } => {
            zcb(m, 0.0, 0.0, maturity)?;
            (
                *a,
                *sigma,
                curve.ln_discount(expiry).exp(),
                curve.ln_discount(maturity).exp(),
            )
        }
        Model::Cir { a, b, sigma } => {
            let pt = zcb(m, r, 0.0, expiry)?.0;
            let ps = zcb(m, r, 0.0, maturity)?.0;
            let (a, b, sigma) = (*a, *b, *sigma);
            let s2 = sigma * sigma;
            let g = (a * a + 2.0 * s2).sqrt();
            let rho = 2.0 * g / (s2 * (g * expiry).exp_m1());
            let psi = (a + g) / s2;
            let (ln_a, bb) = cir_factors(a, b, sigma, maturity - expiry);
            let rbar = (ln_a - strike.ln()) / bb;
            let k = 4.0 * a * b / s2;
            let num = 2.0 * rho * rho * r * (g * expiry).exp();
            let chi = crate::stats::noncentral_chi2_cdf;
            let c = ps * chi(2.0 * rbar * (rho + psi + bb), k, num / (rho + psi + bb))
                - strike * pt * chi(2.0 * rbar * (rho + psi), k, num / (rho + psi));
            let v = if call { c } else { c - ps + strike * pt };
            return Ok((notional * v, pt, ps));
        }
    };
    let sp = sigma / a
        * -(-a * (maturity - expiry)).exp_m1()
        * (-(-2.0 * a * expiry).exp_m1() / (2.0 * a)).sqrt();
    let h = (ps / (strike * pt)).ln() / sp + sp / 2.0;
    let n = crate::stats::normal_cdf;
    let c = ps * n(h) - strike * pt * n(h - sp);
    let v = if call { c } else { c - ps + strike * pt };
    Ok((notional * v, pt, ps))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cir_put_call_parity_and_bounds() {
        let m = Model::Cir {
            a: 0.3,
            b: 0.05,
            sigma: 0.1,
        };
        for (k, te, ts) in [(0.9, 1.0, 3.0), (0.95, 0.5, 2.0), (0.7, 2.0, 10.0)] {
            let (c, pt, ps) = zcb_option(&m, 0.04, true, k, te, ts, 1.0).unwrap();
            let (p, _, _) = zcb_option(&m, 0.04, false, k, te, ts, 1.0).unwrap();
            assert!((c - p - (ps - k * pt)).abs() < 1e-12);
            assert!(c >= 0.0 && c <= ps);
        }
        // r = 0 gives zero noncentrality and must still price.
        assert!(zcb_option(&m, 0.0, true, 0.9, 1.0, 3.0, 1.0).unwrap().0 > 0.0);
    }
}
