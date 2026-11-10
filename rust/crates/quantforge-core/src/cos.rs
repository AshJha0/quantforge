//! COS Fourier pricing (`cos.md`).

use crate::error::{Result, fail};
use std::f64::consts::PI;
use std::ops::{Add, Div, Mul, Sub};

#[derive(Debug, Clone, Copy, PartialEq)]
struct Complex {
    re: f64,
    im: f64,
}

fn c(re: f64, im: f64) -> Complex {
    Complex { re, im }
}

impl Add for Complex {
    type Output = Complex;
    fn add(self, o: Complex) -> Complex {
        c(self.re + o.re, self.im + o.im)
    }
}
impl Sub for Complex {
    type Output = Complex;
    fn sub(self, o: Complex) -> Complex {
        c(self.re - o.re, self.im - o.im)
    }
}
impl Mul for Complex {
    type Output = Complex;
    fn mul(self, o: Complex) -> Complex {
        c(
            self.re * o.re - self.im * o.im,
            self.re * o.im + self.im * o.re,
        )
    }
}
impl Div for Complex {
    type Output = Complex;
    fn div(self, o: Complex) -> Complex {
        let d = o.re.hypot(o.im);
        let (ar, ai) = (self.re / d, self.im / d);
        let (br, bi) = (o.re / d, o.im / d);
        c(ar * br + ai * bi, ai * br - ar * bi)
    }
}
impl Complex {
    fn scale(self, k: f64) -> Complex {
        c(self.re * k, self.im * k)
    }
    fn exp(self) -> Complex {
        let m = self.re.exp();
        c(m * self.im.cos(), m * self.im.sin())
    }
    fn ln(self) -> Complex {
        c(self.re.hypot(self.im).ln(), self.im.atan2(self.re))
    }
    /// Principal root.
    fn sqrt(self) -> Complex {
        let m = self.re.hypot(self.im);
        if m == 0.0 {
            return c(0.0, 0.0);
        }
        let big = ((m + self.re.abs()) / 2.0).sqrt();
        let small = self.im.abs() / (2.0 * big);
        if self.re >= 0.0 {
            c(big, small.copysign(self.im))
        } else {
            c(small, big.copysign(self.im))
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub enum Model {
    BlackScholes {
        sigma: f64,
    },
    Heston {
        v0: f64,
        kappa: f64,
        theta: f64,
        sigma: f64,
        rho: f64,
    },
}

#[derive(Debug, Clone, Copy)]
pub struct CosInputs {
    pub call: bool,
    pub spot: f64,
    pub strike: f64,
    pub r: f64,
    pub q: f64,
    pub t: f64,
    pub model: Model,
    pub terms: i64,
    pub truncation: f64,
}

fn characteristic(p: &CosInputs, u: f64) -> Complex {
    if u == 0.0 {
        return c(1.0, 0.0);
    }
    let (r, q, t) = (p.r, p.q, p.t);
    match p.model {
        Model::BlackScholes { sigma } => {
            let s2 = sigma * sigma;
            c(-s2 * u * u * t / 2.0, u * (r - q - s2 / 2.0) * t).exp()
        }
        Model::Heston {
            v0,
            kappa,
            theta,
            sigma,
            rho,
        } => {
            let s2 = sigma * sigma;
            let beta = c(kappa, -rho * sigma * u);
            let d = (beta * beta + c(u * u, u).scale(s2)).sqrt();
            let g = (beta - d) / (beta + d);
            let e = (d.scale(-t)).exp();
            let one = c(1.0, 0.0);
            let log_term = ((one - g * e) / (one - g)).ln();
            let first = ((beta - d).scale(t) - log_term.scale(2.0)).scale(kappa * theta / s2);
            let second = ((beta - d) * (one - e) / (one - g * e)).scale(v0 / s2);
            (c(0.0, u * (r - q) * t) + first + second).exp()
        }
    }
}

/// Returns `(price, a, b)`.
pub fn european(p: &CosInputs) -> Result<(f64, f64, f64)> {
    crate::error::finite("p", &p)?;
    let mut positive = vec![p.spot, p.strike, p.t, p.truncation];
    match p.model {
        Model::BlackScholes { sigma } => positive.push(sigma),
        Model::Heston {
            v0,
            kappa,
            theta,
            sigma,
            ..
        } => positive.extend([sigma, v0, kappa, theta]),
    }
    if positive.iter().any(|v| *v <= 0.0) {
        return fail("E_DOMAIN", "a parameter must be positive");
    }
    if let Model::Heston { rho, .. } = p.model
        && rho.abs() >= 1.0
    {
        return fail("E_DOMAIN", "|rho| must be below 1");
    }
    if p.terms < 2 {
        return fail("E_INPUT", "terms must be at least 2");
    }
    let t = p.t;
    let w = match p.model {
        Model::BlackScholes { sigma } => sigma * sigma * t,
        Model::Heston {
            v0, kappa, theta, ..
        } => (theta + (v0 - theta) * (1.0 - (-kappa * t).exp()) / (kappa * t)) * t,
    };
    let x = (p.spot / p.strike).ln();
    let c1 = x + (p.r - p.q) * t - w / 2.0;
    let a = c1 - p.truncation * w.sqrt();
    let b = c1 + p.truncation * w.sqrt();
    if a >= 0.0 || b <= 0.0 {
        return fail("E_INPUT", "range does not hold the strike");
    }
    let mut sum = 0.0;
    for k in 0..p.terms {
        let u = k as f64 * PI / (b - a);
        let chi = ((u * -a).cos() + u * (u * -a).sin() - a.exp()) / (1.0 + u * u);
        let psi = if k == 0 { -a } else { (u * -a).sin() / u };
        let v = 2.0 / (b - a) * p.strike * (psi - chi);
        let term = (characteristic(p, u) * c(0.0, u * (x - a)).exp()).re * v;
        sum += if k == 0 { term / 2.0 } else { term };
    }
    let put = (-p.r * t).exp() * sum;
    let price = if p.call {
        put + p.spot * (-p.q * t).exp() - p.strike * (-p.r * t).exp()
    } else {
        put
    };
    Ok((price, a, b))
}

impl crate::error::Finite for CosInputs {
    fn is_all_finite(&self) -> bool {
        self.spot.is_all_finite()
            && self.strike.is_all_finite()
            && self.r.is_all_finite()
            && self.q.is_all_finite()
            && self.t.is_all_finite()
            && self.model.is_all_finite()
            && self.truncation.is_all_finite()
    }
}

impl crate::error::Finite for Model {
    #[allow(clippy::match_same_arms)]
    fn is_all_finite(&self) -> bool {
        match self {
            Self::BlackScholes { sigma, .. } => sigma.is_all_finite(),
            Self::Heston {
                v0,
                kappa,
                theta,
                sigma,
                rho,
                ..
            } => {
                v0.is_all_finite()
                    && kappa.is_all_finite()
                    && theta.is_all_finite()
                    && sigma.is_all_finite()
                    && rho.is_all_finite()
            }
        }
    }
}
