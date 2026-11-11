//! Monte Carlo Greeks under GBM: pathwise, likelihood ratio, smoothed digital, central bump
//! with common draws (`06-risk/mc-greeks.md`, rulings G-10, G-15).
use crate::error::{Result, fail};

/// Payoff of [`mc_greeks`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Payoff {
    /// `max(S_T - K, 0)`.
    Call,
    /// `max(K - S_T, 0)`.
    Put,
    /// `1{S_T > K}`.
    DigitalCall,
}

/// Estimator of [`mc_greeks`], with its parameter.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Method {
    /// Pathwise derivative; `Some(eps)` (the call-spread half-width) is required for a digital.
    Pathwise(Option<f64>),
    /// Likelihood ratio (score of the lognormal density).
    LikelihoodRatio,
    /// Central bump of relative size `h` on the same draws.
    Bump(f64),
}

/// Market and contract inputs.
#[derive(Debug, Clone, Copy)]
pub struct GbmOption {
    /// Spot `S`.
    pub spot: f64,
    /// Strike `K`.
    pub strike: f64,
    /// Expiry `T` in years.
    pub expiry_years: f64,
    /// Continuously compounded rate `r`.
    pub rate: f64,
    /// Dividend yield `q`.
    pub dividend_yield: f64,
    /// Volatility `v`.
    pub vol: f64,
}

/// Sample means and standard errors (divisor `n - 1`, over `sqrt n`).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Greeks {
    /// Price (always the unsmoothed payoff).
    pub price: f64,
    /// Standard error of the price.
    pub price_se: f64,
    /// Delta.
    pub delta: f64,
    /// Standard error of delta.
    pub delta_se: f64,
    /// Vega.
    pub vega: f64,
    /// Standard error of vega.
    pub vega_se: f64,
}

/// Running mean and sum of squared deviations (Welford), path order.
#[derive(Default, Clone, Copy)]
struct Acc {
    n: f64,
    mean: f64,
    m2: f64,
}

impl Acc {
    fn push(&mut self, x: f64) {
        self.n += 1.0;
        let d = x - self.mean;
        self.mean += d / self.n;
        self.m2 += d * (x - self.mean);
    }
    fn se(&self) -> f64 {
        (self.m2 / (self.n - 1.0) / self.n).sqrt()
    }
    /// Sample variance, divisor `n - 1`.
    #[cfg(test)]
    fn var(&self) -> f64 {
        self.m2 / (self.n - 1.0)
    }
}

fn payoff(p: Payoff, s: f64, k: f64) -> f64 {
    match p {
        Payoff::Call => (s - k).max(0.0),
        Payoff::Put => (k - s).max(0.0),
        Payoff::DigitalCall => {
            if s > k {
                1.0
            } else {
                0.0
            }
        }
    }
}

/// Per-path `(price, delta, vega)` terms for the normal draw `z`.
fn terms(o: &GbmOption, p: Payoff, m: Method, z: f64) -> (f64, f64, f64) {
    let (s, k, t, v) = (o.spot, o.strike, o.expiry_years, o.vol);
    let d = (-o.rate * t).exp();
    let st_at = |s0: f64, vol: f64| {
        s0 * ((o.rate - o.dividend_yield - vol * vol / 2.0) * t + vol * t.sqrt() * z).exp()
    };
    let st = st_at(s, v);
    let f = payoff(p, st, k);
    let ds_dv = st * (t.sqrt() * z - v * t);
    let (delta, vega) = match m {
        Method::Pathwise(eps) => {
            let w = match p {
                Payoff::Call => f64::from(u8::from(st > k)),
                Payoff::Put => -f64::from(u8::from(st < k)),
                Payoff::DigitalCall => {
                    let e = eps.unwrap_or(f64::NAN);
                    f64::from(u8::from((st - k).abs() < e)) / (2.0 * e)
                }
            };
            (d * w * st / s, d * w * ds_dv)
        }
        Method::LikelihoodRatio => (
            d * f * z / (s * v * t.sqrt()),
            d * f * ((z * z - 1.0) / v - z * t.sqrt()),
        ),
        Method::Bump(h) => {
            let pf = |x: f64| d * payoff(p, x, k);
            (
                (pf(st_at(s * (1.0 + h), v)) - pf(st_at(s * (1.0 - h), v))) / (2.0 * h * s),
                (pf(st_at(s, v * (1.0 + h))) - pf(st_at(s, v * (1.0 - h)))) / (2.0 * h * v),
            )
        }
    };
    (d * f, delta, vega)
}

/// Checks the inputs in the spec's order after the payoff, method and path count.
fn check(o: &GbmOption, p: Payoff, m: Method, paths: u64) -> Result<()> {
    if paths < 2 {
        return fail("E_INPUT", "paths must be at least 2");
    }
    if paths > 10_000_000 {
        return fail("E_LIMIT", "paths is at most 10,000,000");
    }
    crate::error::finite(
        "inputs",
        &[
            o.spot,
            o.strike,
            o.expiry_years,
            o.rate,
            o.dividend_yield,
            o.vol,
        ],
    )?;
    if o.spot <= 0.0 || o.strike <= 0.0 || o.expiry_years <= 0.0 || o.vol <= 0.0 {
        return fail(
            "E_DOMAIN",
            "spot, strike, expiry_years and vol must be positive",
        );
    }
    match (m, p) {
        (Method::Pathwise(None), Payoff::DigitalCall) => {
            fail("E_INPUT", "PATHWISE on a digital needs smoothing_width")
        }
        (Method::Pathwise(Some(_)), Payoff::Call | Payoff::Put) => {
            fail("E_INPUT", "smoothing_width is only for a PATHWISE digital")
        }
        (Method::Pathwise(Some(e)), _) if !(e.is_finite() && e > 0.0) => {
            fail("E_DOMAIN", "smoothing_width must be positive")
        }
        (Method::Bump(h), _) if !(h > 0.0 && h < 1.0) => {
            fail("E_DOMAIN", "bump_relative must be in (0, 1)")
        }
        _ => Ok(()),
    }
}

/// `risk.mc.greeks`: price, delta and vega with standard errors from `paths` draws of
/// `core.rng` (`seed`, stream 0, one AS 241 normal per path in path order).
pub fn mc_greeks(o: &GbmOption, p: Payoff, m: Method, paths: u64, seed: u64) -> Result<Greeks> {
    check(o, p, m, paths)?;
    let mut g = crate::rng::Xoshiro::seeded(seed, 0);
    let (mut a, mut b, mut c) = (Acc::default(), Acc::default(), Acc::default());
    for _ in 0..paths {
        let (x, y, w) = terms(o, p, m, g.next_normal());
        a.push(x);
        b.push(y);
        c.push(w);
    }
    Ok(Greeks {
        price: a.mean,
        price_se: a.se(),
        delta: b.mean,
        delta_se: b.se(),
        vega: c.mean,
        vega_se: c.se(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn digital() -> GbmOption {
        GbmOption {
            spot: 100.0,
            strike: 100.0,
            expiry_years: 1.0,
            rate: 0.03,
            dividend_yield: 0.0,
            vol: 0.2,
        }
    }

    /// Delta sample of `n` paths from `(seed, stream)`.
    fn deltas(m: Method, seed: u64, stream: u32, n: usize) -> Acc {
        let mut g = crate::rng::Xoshiro::seeded(seed, stream);
        let mut a = Acc::default();
        for _ in 0..n {
            a.push(terms(&digital(), Payoff::DigitalCall, m, g.next_normal()).1);
        }
        a
    }

    /// G-10, the likelihood-ratio half: LR delta within 3 SE of the closed form
    /// `e^{-rT} n(d2) / (S v sqrt T)` at 100,000 paths, seed 20261109.
    #[test]
    fn g10_likelihood_ratio_matches_closed_form() {
        let o = digital();
        let d2 = (o.rate - o.vol * o.vol / 2.0) / o.vol;
        let exact = (-o.rate).exp() * crate::stats::normal_pdf(d2) / (o.spot * o.vol);
        let r = mc_greeks(
            &o,
            Payoff::DigitalCall,
            Method::LikelihoodRatio,
            100_000,
            20_261_109,
        )
        .unwrap();
        assert!(
            (r.delta - exact).abs() < 3.0 * r.delta_se,
            "{} {exact}",
            r.delta
        );
    }

    /// G-10b: smoothed pathwise (`eps = 1`, stream 0) against a central bump (`h = 0.001`,
    /// stream 1), seed 20261110, 60,000 paths each; pass when `Z > 1.6449`.
    #[test]
    fn g10b_smoothed_pathwise_beats_bump() {
        let n = 60_000;
        let kurt = |m: Method, stream| {
            let a = deltas(m, 20_261_110, stream, n);
            let mut g = crate::rng::Xoshiro::seeded(20_261_110, stream);
            let mut m4 = 0.0;
            for _ in 0..n {
                let d = terms(&digital(), Payoff::DigitalCall, m, g.next_normal()).1 - a.mean;
                m4 += d * d * d * d;
            }
            #[allow(clippy::cast_precision_loss)]
            let k = m4 / n as f64 / (a.m2 / n as f64).powi(2);
            (a.var(), k)
        };
        let (s_pw, k_pw) = kurt(Method::Pathwise(Some(1.0)), 0);
        let (s_b, k_b) = kurt(Method::Bump(0.001), 1);
        #[allow(clippy::cast_precision_loss)]
        let nf = n as f64;
        let z = (s_b.ln() - s_pw.ln()) / ((k_pw - 1.0) / nf + (k_b - 1.0) / nf).sqrt();
        assert!(z > 1.6449, "Z = {z}");
    }

    #[test]
    fn errors_in_order() {
        let o = digital();
        let e = |p, m, n| mc_greeks(&o, p, m, n, 1).unwrap_err().code;
        assert_eq!(e(Payoff::Call, Method::LikelihoodRatio, 1), "E_INPUT");
        assert_eq!(
            e(Payoff::DigitalCall, Method::Pathwise(None), 10),
            "E_INPUT"
        );
        assert_eq!(e(Payoff::Call, Method::Pathwise(Some(1.0)), 10), "E_INPUT");
        assert_eq!(
            e(Payoff::DigitalCall, Method::Pathwise(Some(0.0)), 10),
            "E_DOMAIN"
        );
        assert_eq!(e(Payoff::Call, Method::Bump(1.0), 10), "E_DOMAIN");
        let bs = mc_greeks(&o, Payoff::Call, Method::Pathwise(None), 50_000, 3).unwrap();
        let bump = mc_greeks(&o, Payoff::Call, Method::Bump(1e-4), 50_000, 3).unwrap();
        // h -> 0: the bump tends to the pathwise estimator on a call.
        assert!((bs.delta - bump.delta).abs() < 1e-4 * bs.delta);
        assert!((bs.vega - bump.vega).abs() < 1e-4 * bs.vega);
    }
}
