//! Stage E8: CDS options, default copulas and the large homogeneous pool
//! (`04-pricing/credit-options-and-copulas.md`, rulings E-B22 to E-B26).
use crate::black::black;
use crate::dates::Date;

use crate::error::{Result, fail};
use crate::integrate::gauss_legendre_rule;
use crate::rng::ppnd16;
use crate::schedule::add_months;
use crate::stats::{normal_cdf, normal_pdf};
use std::f64::consts::PI;
use std::sync::OnceLock;

pub struct CdsOption {
    pub as_of: Date,
    pub expiry: Date,
    pub maturity: Date,
    pub rate: f64,
    pub hazard_rate: f64,
    pub recovery: f64,
    pub payer: bool,
    pub strike: f64,
    pub notional: f64,
    pub knock_out: bool,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CdsOptionPrice {
    pub price: f64,
    pub forward_spread: f64,
    pub risky_annuity: f64,
    pub front_end_protection: f64,
}

impl CdsOption {
    fn check(&self) -> Result<()> {
        if self.expiry <= self.as_of || self.maturity <= self.expiry {
            return fail("E_INPUT", "need as_of < expiry < maturity");
        }
        let r = self.recovery;
        if !(0.0..1.0).contains(&r)
            || self.hazard_rate.is_nan()
            || self.hazard_rate < 0.0
            || self.strike.is_nan()
            || self.strike <= 0.0
        {
            return fail(
                "E_DOMAIN",
                "recovery in [0, 1), hazard_rate >= 0 and strike > 0 required",
            );
        }
        Ok(())
    }

    fn t(&self, d: Date) -> f64 {
        (d.serial() - self.as_of.serial()) as f64 / 365.0
    }

    /// `(forward_spread, annuity, front_end_protection)` of the stylised forward CDS (E-B22).
    fn legs(&self) -> (f64, f64, f64) {
        let surv = |d: Date| (-self.hazard_rate * self.t(d)).exp();
        let disc = |d: Date| (-self.rate * self.t(d)).exp();
        let mut dates = vec![self.expiry];
        for k in 1.. {
            let d = add_months(self.expiry, 3 * k);
            if d >= self.maturity {
                break;
            }
            dates.push(d);
        }
        dates.push(self.maturity);
        let (mut prot, mut ann) = (0.0, 0.0);
        for w in dates.windows(2) {
            let (a, b) = (w[0], w[1]);
            let days = b.serial() - a.serial();
            let m = a.add_days(days / 2);
            let lost = surv(a) - surv(b);
            prot += (1.0 - self.recovery) * disc(m) * lost;
            ann += days as f64 / 360.0 * disc(b) * surv(b)
                + (m.serial() - a.serial()) as f64 / 360.0 * disc(m) * lost;
        }
        let fep =
            self.notional * (1.0 - self.recovery) * (1.0 - surv(self.expiry)) * disc(self.expiry);
        (prot / ann, ann, fep)
    }

    fn value(&self, f: f64, a: f64, fep: f64, vol: f64) -> f64 {
        let opt =
            self.notional * a * black(self.payer, f, self.strike, vol, self.t(self.expiry), 1.0);
        opt + if self.payer && !self.knock_out {
            fep
        } else {
            0.0
        }
    }
}

pub fn cds_option_price(o: &CdsOption, vol: f64) -> Result<CdsOptionPrice> {
    crate::error::finite("o", &o)?;
    crate::error::finite("vol", &vol)?;
    o.check()?;
    if vol.is_nan() || vol < 0.0 {
        return fail("E_DOMAIN", "vol must not be negative");
    }
    let (f, a, fep) = o.legs();
    Ok(CdsOptionPrice {
        price: o.value(f, a, fep, vol),
        forward_spread: f,
        risky_annuity: a,
        front_end_protection: fep,
    })
}

/// Knock-out options only (ruling E-B23).
pub fn cds_option_implied_vol(o: &CdsOption, premium: f64) -> Result<f64> {
    crate::error::finite("o", &o)?;
    crate::error::finite("premium", &premium)?;
    // Ruling E-B40: the knock-out rule comes before the dates.
    if !o.knock_out {
        return fail(
            "E_INPUT",
            "implied vol is defined for knock-out options only",
        );
    }
    o.check()?;
    let (f, a, fep) = o.legs();
    let floor = o.value(f, a, fep, 0.0);
    let cap = o.notional * a * if o.payer { f } else { o.strike };
    if premium.is_nan() || premium <= floor || premium >= cap {
        return fail(
            "E_DOMAIN",
            "premium must lie strictly between the zero-vol value and the bound",
        );
    }
    let (mut lo, mut hi) = (0.0, 1.0);
    while o.value(f, a, fep, hi) < premium {
        hi *= 2.0;
        if hi > 1e6 {
            return fail("E_NO_CONVERGENCE", "no vol reaches the premium");
        }
    }
    for _ in 0..2000 {
        let mid = 0.5 * (lo + hi);
        if mid <= lo || mid >= hi {
            break;
        }
        if o.value(f, a, fep, mid) < premium {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    Ok(0.5 * (lo + hi))
}

/// Standard normal quantile: AS241 refined by one Newton step.
/// Unchecked kernel (E1): inputs are not validated, and NaN or infinity in gives NaN out.
pub fn normal_inv(p: f64) -> f64 {
    let x = ppnd16(p);
    x - (normal_cdf(x) - p) / normal_pdf(x)
}

fn gl20() -> &'static [(f64, f64)] {
    static RULE: OnceLock<Vec<(f64, f64)>> = OnceLock::new();
    RULE.get_or_init(|| gauss_legendre_rule(20))
}

/// `int_a^b f` by 20-point Gauss-Legendre on `panels` equal panels.
fn integrate(f: &dyn Fn(f64) -> f64, a: f64, b: f64, panels: usize) -> f64 {
    let w = (b - a) / panels as f64;
    (0..panels)
        .map(|p| {
            let (l, half) = (a + p as f64 * w, w / 2.0);
            gl20()
                .iter()
                .map(|&(x, wt)| wt * f(l + half * (x + 1.0)))
                .sum::<f64>()
                * half
        })
        .sum()
}

/// Bivariate normal CDF by Drezner-Wesolowsky's `sin` substitution:
/// `Phi(h) Phi(k) + (1/2pi) int_0^{asin rho} exp(-(h^2 + k^2 - 2hk sin t)/(2 cos^2 t)) dt`.
/// Unchecked kernel (E1): inputs are not validated, and NaN or infinity in gives NaN out.
pub fn bivariate_normal(h: f64, k: f64, rho: f64) -> f64 {
    let top = rho.asin();
    let g = |t: f64| {
        let (s, c2) = (t.sin(), t.cos().powi(2));
        (-(h * h + k * k - 2.0 * h * k * s) / (2.0 * c2)).exp()
    };
    normal_cdf(h) * normal_cdf(k) + integrate(&g, 0.0, top, 16) / (2.0 * PI)
}

/// `E[f(sqrt(U))]` with `U = W/nu`, `W ~ chi^2_nu`, integrated in `s = ln U` and normalised by the
/// same rule, so the gamma constant is never needed.
fn chi_mix(nu: f64, f: &dyn Fn(f64) -> f64) -> f64 {
    let a = nu / 2.0;
    let w = |s: f64| (a * s - a * s.exp()).exp();
    let (lo, hi) = (-60.0 / a.min(1.0), 6.0);
    let num = integrate(&|s| w(s) * f((s / 2.0).exp()), lo, hi, 120);
    let den = integrate(&w, lo, hi, 120);
    num / den
}

/// Student t CDF with `nu` degrees of freedom.
/// Unchecked kernel (E1): inputs are not validated, and NaN or infinity in gives NaN out.
pub fn student_cdf(x: f64, nu: f64) -> f64 {
    chi_mix(nu, &|r| normal_cdf(x * r))
}

/// Student t quantile by bisection on [`student_cdf`].
/// Unchecked kernel (E1): inputs are not validated, and NaN or infinity in gives NaN out.
pub fn student_inv(p: f64, nu: f64) -> f64 {
    let (mut lo, mut hi) = (-1.0, 1.0);
    while student_cdf(lo, nu) > p {
        lo *= 2.0;
    }
    while student_cdf(hi, nu) < p {
        hi *= 2.0;
    }
    for _ in 0..200 {
        let mid = 0.5 * (lo + hi);
        if mid <= lo || mid >= hi {
            break;
        }
        if student_cdf(mid, nu) < p {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    0.5 * (lo + hi)
}

/// Bivariate Student t CDF, one `nu`, scale matrix with off-diagonal `rho` (ruling E-B24).
/// Unchecked kernel (E1): inputs are not validated, and NaN or infinity in gives NaN out.
pub fn bivariate_student(x: f64, y: f64, rho: f64, nu: f64) -> f64 {
    chi_mix(nu, &|r| bivariate_normal(x * r, y * r, rho))
}

/// `(joint_default_probability, default_correlation)`. `nu` is `Some` for the t copula.
pub fn joint_default(p1: f64, p2: f64, rho: f64, nu: Option<f64>) -> Result<(f64, f64)> {
    crate::error::finite("p1", &p1)?;
    crate::error::finite("p2", &p2)?;
    crate::error::finite("rho", &rho)?;
    crate::error::finite("nu", &nu)?;
    let unit = |p: f64| p > 0.0 && p < 1.0;
    let rho_ok = rho.abs() < 1.0;
    let nu_ok = nu.is_none_or(|v| v > 0.0);
    if !(unit(p1) && unit(p2) && rho_ok && nu_ok) {
        return fail("E_DOMAIN", "p in (0, 1), |rho| < 1 and nu > 0 required");
    }
    let joint = match nu {
        None => bivariate_normal(normal_inv(p1), normal_inv(p2), rho),
        Some(v) => bivariate_student(student_inv(p1, v), student_inv(p2, v), rho, v),
    };
    let dc = (joint - p1 * p2) / (p1 * (1.0 - p1) * p2 * (1.0 - p2)).sqrt();
    Ok((joint, dc))
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Pool {
    pub default_probability: f64,
    pub correlation: f64,
    pub recovery: f64,
}

impl Pool {
    fn check(&self) -> Result<()> {
        let open = |v: f64| v > 0.0 && v < 1.0;
        if open(self.default_probability)
            && open(self.correlation)
            && (0.0..1.0).contains(&self.recovery)
        {
            Ok(())
        } else {
            fail(
                "E_DOMAIN",
                "p and rho in (0, 1), recovery in [0, 1) required",
            )
        }
    }

    /// `E[min(P(M), k)]` in closed form (ruling E-B25).
    fn capped(&self, k: f64) -> f64 {
        let p = self.default_probability;
        if k >= 1.0 {
            return p;
        }
        let (c, rho) = (normal_inv(p), self.correlation);
        let m = (c - (1.0 - rho).sqrt() * normal_inv(k)) / rho.sqrt();
        p - (bivariate_normal(c, m, rho.sqrt()) - k * normal_cdf(m))
    }
}

pub fn tranche_loss(pool: &Pool, attachment: f64, detachment: f64) -> Result<f64> {
    crate::error::finite("pool", &pool)?;
    crate::error::finite("attachment", &attachment)?;
    crate::error::finite("detachment", &detachment)?;
    if detachment <= attachment || attachment < 0.0 || detachment > 1.0 {
        return fail("E_INPUT", "need 0 <= attachment < detachment <= 1");
    }
    pool.check()?;
    let lgd = 1.0 - pool.recovery;
    let k = |x: f64| (x / lgd).min(1.0);
    let low = if attachment == 0.0 {
        0.0
    } else {
        pool.capped(k(attachment))
    };
    Ok(lgd * (pool.capped(k(detachment)) - low) / (detachment - attachment))
}

pub fn loss_cdf(pool: &Pool, losses: &[f64]) -> Result<Vec<f64>> {
    crate::error::finite("pool", &pool)?;
    crate::error::finite("losses", &losses)?;
    pool.check()?;
    let lgd = 1.0 - pool.recovery;
    if losses.iter().any(|x| !(*x > 0.0 && *x < lgd)) {
        return fail("E_DOMAIN", "each loss must lie in (0, 1 - recovery)");
    }
    let (c, rho) = (normal_inv(pool.default_probability), pool.correlation);
    Ok(losses
        .iter()
        .map(|x| normal_cdf(((1.0 - rho).sqrt() * normal_inv(x / lgd) - c) / rho.sqrt()))
        .collect())
}

impl crate::error::Finite for CdsOption {
    fn is_all_finite(&self) -> bool {
        self.rate.is_all_finite()
            && self.hazard_rate.is_all_finite()
            && self.recovery.is_all_finite()
            && self.strike.is_all_finite()
            && self.notional.is_all_finite()
    }
}

impl crate::error::Finite for CdsOptionPrice {
    fn is_all_finite(&self) -> bool {
        self.price.is_all_finite()
            && self.forward_spread.is_all_finite()
            && self.risky_annuity.is_all_finite()
            && self.front_end_protection.is_all_finite()
    }
}

impl crate::error::Finite for Pool {
    fn is_all_finite(&self) -> bool {
        self.default_probability.is_all_finite()
            && self.correlation.is_all_finite()
            && self.recovery.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn opt(payer: bool, strike: f64, knock_out: bool) -> CdsOption {
        CdsOption {
            as_of: Date::new(2026, 11, 6),
            expiry: Date::new(2027, 3, 20),
            maturity: Date::new(2032, 3, 20),
            rate: 0.035,
            hazard_rate: 0.02,
            recovery: 0.4,
            payer,
            strike,
            notional: 1e7,
            knock_out,
        }
    }

    #[test]
    fn cds_option_worked_example() {
        let p = cds_option_price(&opt(true, 0.012, true), 0.5).unwrap();
        assert!((p.price - 59847.84260792966).abs() < 1e-6);
        assert!((p.forward_spread - 0.011887730437307897).abs() < 1e-14);
        assert!((p.risky_annuity - 4.328652217279409).abs() < 1e-12);
        assert!((p.front_end_protection - 43333.06144966937).abs() < 1e-6);
        let open = cds_option_price(&opt(true, 0.012, false), 0.5).unwrap();
        assert!((open.price - p.price - p.front_end_protection).abs() < 1e-6);
        let rec = cds_option_price(&opt(false, 0.0096, false), 0.4).unwrap();
        assert!((rec.price - 11581.73).abs() < 0.01);
        let v = cds_option_implied_vol(&opt(true, 0.012, true), p.price).unwrap();
        assert!((v - 0.5).abs() < 1e-12);
        let rv = cds_option_implied_vol(&opt(false, 0.0096, true), rec.price).unwrap();
        assert!((rv - 0.4).abs() < 1e-12);
    }

    #[test]
    fn cds_option_checks() {
        let code = |o: CdsOption| cds_option_price(&o, 0.5).unwrap_err().code;
        assert_eq!(
            code(CdsOption {
                expiry: Date::new(2026, 11, 6),
                ..opt(true, 0.01, true)
            }),
            "E_INPUT"
        );
        assert_eq!(
            code(CdsOption {
                maturity: Date::new(2027, 3, 20),
                ..opt(true, 0.01, true)
            }),
            "E_INPUT"
        );
        assert_eq!(
            code(CdsOption {
                recovery: 1.0,
                ..opt(true, 0.01, true)
            }),
            "E_DOMAIN"
        );
        assert_eq!(
            code(CdsOption {
                hazard_rate: -0.01,
                ..opt(true, 0.01, true)
            }),
            "E_DOMAIN"
        );
        assert_eq!(code(opt(true, 0.0, true)), "E_DOMAIN");
        assert_eq!(
            cds_option_price(&opt(true, 0.01, true), -0.1)
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        assert_eq!(
            cds_option_implied_vol(&opt(true, 0.012, false), 1e4)
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        assert_eq!(
            cds_option_implied_vol(&opt(true, 0.012, true), 0.0)
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn distributions() {
        assert!((normal_inv(0.975) - 1.959963984540054).abs() < 1e-14);
        assert!(
            (bivariate_normal(0.3, -0.2, 0.0) - normal_cdf(0.3) * normal_cdf(-0.2)).abs() < 1e-16
        );
        let b = bivariate_normal(0.0, 0.0, 0.5);
        assert!((b - (0.25 + 0.5f64.asin() / (2.0 * PI))).abs() < 1e-15);
        // t with 1 degree of freedom is Cauchy.
        assert!((student_cdf(1.0, 1.0) - 0.75).abs() < 1e-12);
        assert!((student_inv(0.75, 1.0) - 1.0).abs() < 1e-10);
        let t0 = bivariate_student(0.0, 0.0, 0.5, 4.0);
        assert!((t0 - (0.25 + 0.5f64.asin() / (2.0 * PI))).abs() < 1e-12);
    }

    #[test]
    fn copulas() {
        let (g, _) = joint_default(0.02, 0.03, 0.3, None).unwrap();
        assert!((g - 0.0022875610978654965).abs() < 1e-14);
        let (z, dc) = joint_default(0.02, 0.03, 0.0, None).unwrap();
        assert!((z - 0.0006).abs() < 1e-15 && dc.abs() < 1e-11);
        let (t, _) = joint_default(0.02, 0.03, 0.3, Some(4.0)).unwrap();
        assert!((t - 0.005102).abs() < 1e-6);
        assert_eq!(
            joint_default(0.0, 0.03, 0.3, None).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            joint_default(0.02, 0.03, 1.0, None).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            joint_default(0.02, 0.03, 0.3, Some(0.0)).unwrap_err().code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn lhp() {
        let pool = Pool {
            default_probability: 0.05,
            correlation: 0.3,
            recovery: 0.4,
        };
        assert!((tranche_loss(&pool, 0.0, 0.03).unwrap() - 0.5410575024827762).abs() < 1e-12);
        let cuts = [0.0, 0.03, 0.07, 0.1, 0.15, 0.3, 1.0];
        let total: f64 = cuts
            .windows(2)
            .map(|w| tranche_loss(&pool, w[0], w[1]).unwrap() * (w[1] - w[0]))
            .sum();
        assert!((total - 0.03).abs() < 1e-15);
        let cdf = loss_cdf(&pool, &[0.005, 0.2]).unwrap();
        assert!(
            (cdf[0] - 0.2566247049337847).abs() < 1e-12
                && (cdf[1] - 0.9904898099293576).abs() < 1e-12
        );
        assert_eq!(tranche_loss(&pool, 0.1, 0.1).unwrap_err().code, "E_INPUT");
        assert_eq!(tranche_loss(&pool, 0.0, 1.1).unwrap_err().code, "E_INPUT");
        let flat = Pool {
            correlation: 0.0,
            ..pool
        };
        assert_eq!(tranche_loss(&flat, 0.0, 0.1).unwrap_err().code, "E_DOMAIN");
        assert_eq!(loss_cdf(&pool, &[0.6]).unwrap_err().code, "E_DOMAIN");
    }
}
