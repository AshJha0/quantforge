//! Monte Carlo engine (`monte-carlo.md`).
use crate::error::{Result, fail};
use crate::rng::{Xoshiro, ppnd16};
use crate::sobol::Sobol;
use crate::stats::{mean, variance};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Method {
    Plain,
    Antithetic,
    ControlVariate,
    Sobol,
}

#[derive(Debug, Clone, Copy)]
pub struct McInputs {
    pub call: bool,
    pub spot: f64,
    pub strike: f64,
    pub r: f64,
    pub q: f64,
    pub sigma: f64,
    pub t: f64,
    pub paths: i64,
    pub steps: i64,
    pub seed: u64,
    pub stream: u32,
    pub method: Method,
}

enum Draws {
    Random(Xoshiro),
    Quasi(Sobol, Vec<f64>),
}

impl Draws {
    fn fill(&mut self, z: &mut [f64]) {
        match self {
            Draws::Random(g) => z.iter_mut().for_each(|v| *v = g.next_normal()),
            Draws::Quasi(s, point) => {
                s.next_point(point);
                for (v, u) in z.iter_mut().zip(point.iter()) {
                    *v = ppnd16(*u);
                }
            }
        }
    }
}

/// Returns `(price, stderr)`.
pub fn gbm_european(p: &McInputs) -> Result<(f64, f64)> {
    if p.spot <= 0.0 || p.strike <= 0.0 || p.sigma <= 0.0 || p.t <= 0.0 {
        return fail("E_DOMAIN", "spot, strike, sigma and t must be positive");
    }
    if p.paths < 2 || p.steps < 1 {
        return fail("E_INPUT", "paths or steps out of range");
    }
    if p.method == Method::Sobol && p.steps > 64 {
        return fail("E_INPUT", "SOBOL allows at most 64 steps");
    }
    let m = p.steps as usize;
    let n = p.paths as usize;
    let dt = p.t / m as f64;
    let drift = (p.r - p.q - p.sigma * p.sigma / 2.0) * dt;
    let vol = p.sigma * dt.sqrt();
    let ln_spot = p.spot.ln();
    let disc = (-p.r * p.t).exp();
    let terminal = |z: &[f64], sign: f64| {
        let mut x = ln_spot;
        for v in z {
            x += drift + vol * (sign * v);
        }
        x.exp()
    };
    let payoff = |s: f64| {
        disc * if p.call {
            (s - p.strike).max(0.0)
        } else {
            (p.strike - s).max(0.0)
        }
    };
    let mut draws = if p.method == Method::Sobol {
        Draws::Quasi(Sobol::new(m, 0), vec![0.0; m])
    } else {
        Draws::Random(Xoshiro::seeded(p.seed, p.stream))
    };
    let mut z = vec![0.0; m];
    let mut samples = Vec::with_capacity(n);
    let mut controls = Vec::new();
    for _ in 0..n {
        draws.fill(&mut z);
        let s = terminal(&z, 1.0);
        match p.method {
            Method::Antithetic => {
                samples.push((payoff(s) + payoff(terminal(&z, -1.0))) / 2.0);
            }
            Method::ControlVariate => {
                samples.push(payoff(s));
                controls.push(disc * s);
            }
            _ => samples.push(payoff(s)),
        }
    }
    if p.method == Method::ControlVariate {
        let (mp, mc) = (mean(&samples), mean(&controls));
        let cov = samples
            .iter()
            .zip(&controls)
            .map(|(a, b)| (a - mp) * (b - mc))
            .sum::<f64>()
            / (n - 1) as f64;
        let beta = cov / variance(&controls);
        let known = p.spot * (-p.q * p.t).exp();
        for (y, c) in samples.iter_mut().zip(&controls) {
            *y -= beta * (c - known);
        }
    }
    Ok((mean(&samples), (variance(&samples) / n as f64).sqrt()))
}
