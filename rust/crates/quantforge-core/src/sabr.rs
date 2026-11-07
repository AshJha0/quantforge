//! Hagan SABR, its density check and fit, and the arbitrage-free recipe (`sabr.md`).
use crate::black::{Model, Option_, black};
use crate::error::{Result, fail};
use crate::svi::minimise;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Sabr {
    pub t: f64,
    pub alpha: f64,
    pub beta: f64,
    pub rho: f64,
    pub nu: f64,
    pub forward: f64,
    pub shift: f64,
}

impl Sabr {
    pub fn check(&self, strikes: &[f64]) -> Result<()> {
        if self.t <= 0.0
            || self.alpha <= 0.0
            || !(0.0..=1.0).contains(&self.beta)
            || self.rho.abs() >= 1.0
            || self.nu < 0.0
            || self.forward + self.shift <= 0.0
            || strikes.iter().any(|k| k + self.shift <= 0.0)
        {
            return fail("E_DOMAIN", "a SABR input is out of domain");
        }
        Ok(())
    }

    /// Lognormal vol at shifted strike `x`.
    fn vol_at(&self, x: f64) -> f64 {
        let Sabr { t, alpha, beta, rho, nu, .. } = *self;
        let f = self.forward + self.shift;
        let a = (f * x).powf(1.0 - beta);
        let root = a.sqrt();
        let l = (f / x).ln();
        let c = (1.0 - beta) * (1.0 - beta) * l * l;
        let z = nu / alpha * root * l;
        let m = if z.abs() < 1e-7 {
            1.0 - rho * z / 2.0 - (3.0 * rho * rho - 2.0) * z * z / 12.0
        } else {
            let chi = (((1.0 - 2.0 * rho * z + z * z).sqrt() + z - rho) / (1.0 - rho)).ln();
            z / chi
        };
        let den = root * (1.0 + c / 24.0 + c * c / 1920.0);
        let b1 = (1.0 - beta) * (1.0 - beta);
        let h = 1.0
            + t * (b1 * alpha * alpha / (24.0 * a)
                + rho * beta * nu * alpha / (4.0 * root)
                + (2.0 - 3.0 * rho * rho) * nu * nu / 24.0);
        alpha * m * h / den
    }

    pub fn hagan(&self, strikes: &[f64]) -> Result<Vec<f64>> {
        self.check(strikes)?;
        Ok(strikes.iter().map(|k| self.vol_at(k + self.shift)).collect())
    }

    /// `density`, `min_density`. The caller judges the sign.
    pub fn density(&self, strikes: &[f64], h: f64) -> Result<(Vec<f64>, f64)> {
        self.check(strikes)?;
        if h <= 0.0 {
            return fail("E_DOMAIN", "h_strike must be above 0");
        }
        if strikes.iter().any(|k| k + self.shift - h <= 0.0) {
            return fail("E_DOMAIN", "a strike less h_strike is not positive");
        }
        let f = self.forward + self.shift;
        let c = |x: f64| black(true, f, x, self.vol_at(x), self.t, 1.0);
        let d: Vec<f64> = strikes
            .iter()
            .map(|k| {
                let x = k + self.shift;
                (c(x + h) - 2.0 * c(x) + c(x - h)) / (h * h)
            })
            .collect();
        let min = d.iter().copied().fold(f64::INFINITY, f64::min);
        Ok((d, min))
    }
}

/// `alpha`, `rho`, `nu`, `rmse`.
pub fn calibrate(
    forward: f64,
    t: f64,
    beta: f64,
    shift: f64,
    k: &[f64],
    vols: &[f64],
    weights: Option<&[f64]>,
) -> Result<[f64; 4]> {
    if k.len() < 3 || k.len() != vols.len() || weights.is_some_and(|w| w.len() != k.len()) {
        return fail("E_INPUT", "needs 3 strikes and equal lengths");
    }
    if k.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "strikes must strictly increase");
    }
    if vols.iter().any(|&v| v <= 0.0) || weights.is_some_and(|w| w.iter().any(|&x| x <= 0.0)) {
        return fail("E_DOMAIN", "a vol or weight is not positive");
    }
    let model = |a: f64, r: f64, n: f64| Sabr { t, alpha: a, beta, rho: r, nu: n, forward, shift };
    model(1.0, 0.0, 0.0).check(k)?;
    let ones = vec![1.0; k.len()];
    let wt = weights.unwrap_or(&ones);
    let roots: Vec<f64> = wt.iter().map(|v| v.sqrt()).collect();
    let params = |x: &[f64]| (x[0].exp(), x[1].tanh(), x[2].exp());
    let resid = |x: &[f64]| -> Option<Vec<f64>> {
        let (a, r, n) = params(x);
        if !a.is_finite() || a <= 0.0 || !n.is_finite() || r.abs() >= 1.0 {
            return None;
        }
        let s = model(a, r, n);
        let e: Vec<f64> = k
            .iter()
            .zip(vols)
            .zip(&roots)
            .map(|((k, v), q)| q * (s.vol_at(k + shift) - v))
            .collect();
        e.iter().all(|v| v.is_finite()).then_some(e)
    };
    let f = forward + shift;
    let nearest = (0..k.len())
        .min_by(|&i, &j| (k[i] + shift - f).abs().total_cmp(&(k[j] + shift - f).abs()))
        .unwrap_or(0);
    let a0 = vols[nearest] * f.powf(1.0 - beta);
    let mut best: Option<(Vec<f64>, f64)> = None;
    for scale in [0.7f64, 1.0, 1.4] {
        for rho in [-0.7f64, -0.3, 0.0, 0.3, 0.7] {
            for nu in [0.1f64, 0.4, 1.0, 2.0] {
                let x0 = [(a0 * scale).ln(), rho.atanh(), nu.ln()];
                if let Some((x, c)) = minimise(&x0, &resid) {
                    if best.as_ref().is_none_or(|p| c < p.1) {
                        best = Some((x, c));
                    }
                }
            }
        }
    }
    let Some((x, c)) = best else {
        return fail("E_NO_CONVERGENCE", "no start reached a fit");
    };
    let (a, r, n) = params(&x);
    let _ = c;
    let s = model(a, r, n);
    let num: f64 = k
        .iter()
        .zip(vols)
        .zip(wt)
        .map(|((k, v), q)| {
            let e = s.vol_at(k + shift) - v;
            q * e * e
        })
        .sum();
    Ok([a, r, n, (num / wt.iter().sum::<f64>()).sqrt()])
}

#[derive(Debug, Clone, PartialEq)]
pub struct ArbFree {
    pub call_prices: Vec<f64>,
    pub vols: Vec<Option<f64>>,
    pub mass: f64,
    pub mean: f64,
    pub absorbed: f64,
    pub min_density: f64,
}

pub fn arbfree(s: &Sabr, cells: i64, below: i64, steps: i64, strikes: &[f64]) -> Result<ArbFree> {
    s.check(strikes)?;
    if s.beta >= 1.0 {
        return fail("E_DOMAIN", "beta must be below 1");
    }
    if below < 1 || below >= cells || steps < 1 {
        return fail("E_INPUT", "cells_below or steps is out of range");
    }
    let (n, c0) = (cells as usize, below as usize - 1);
    let Sabr { alpha, beta, rho, nu, .. } = *s;
    let f0 = s.forward + s.shift;
    let h = f0 / (below as f64 - 0.5);
    let u_max = cells as f64 * h;
    if strikes.iter().any(|k| k + s.shift >= u_max) {
        return fail("E_INPUT", "a strike is at or beyond the top of the grid");
    }
    let u: Vec<f64> = (0..n).map(|j| (j as f64 + 0.5) * h).collect();
    let half_dsq: Vec<f64> = u
        .iter()
        .map(|&x| {
            let z = (x.powf(1.0 - beta) - f0.powf(1.0 - beta)) / (1.0 - beta);
            (alpha * alpha + 2.0 * rho * alpha * nu * z + nu * nu * z * z) * x.powf(2.0 * beta) / 2.0
        })
        .collect();
    let g: Vec<f64> = (0..n)
        .map(|j| {
            if beta == 0.0 {
                0.0
            } else if j == c0 {
                beta * f0.powf(beta - 1.0)
            } else {
                (u[j].powf(beta) - f0.powf(beta)) / (u[j] - f0)
            }
        })
        .collect();
    let dt = s.t / steps as f64;
    let lambda = dt / (h * h);
    let mut q = vec![0.0; n];
    q[c0] = 1.0 / h;
    let (mut p_l, mut p_r) = (0.0, 0.0);
    let mut m = vec![0.0; n];
    let mut cp = vec![0.0; n];
    for step in 1..=steps {
        let t = step as f64 * dt;
        for j in 0..n {
            m[j] = half_dsq[j] * (rho * nu * alpha * g[j] * t).exp();
        }
        // Tridiagonal in Q: sub -l M_{j-1}, diagonal 1 + 2 l M_j (3 at the ends), super -l M_{j+1}.
        let diag = |j: usize| {
            let e = if j == 0 || j == n - 1 { 3.0 } else { 2.0 };
            1.0 + e * lambda * m[j]
        };
        let mut den = diag(0);
        cp[0] = -lambda * m[1] / den;
        q[0] /= den;
        for j in 1..n {
            let lower = -lambda * m[j - 1];
            den = diag(j) - lower * cp[j - 1];
            if j + 1 < n {
                cp[j] = -lambda * m[j + 1] / den;
            }
            q[j] = (q[j] - lower * q[j - 1]) / den;
        }
        for j in (0..n - 1).rev() {
            q[j] -= cp[j] * q[j + 1];
        }
        p_l += 2.0 * dt * m[0] * q[0] / h;
        p_r += 2.0 * dt * m[n - 1] * q[n - 1] / h;
    }
    let mut call_prices = Vec::with_capacity(strikes.len());
    let mut vols = Vec::with_capacity(strikes.len());
    for k in strikes {
        let x = k + s.shift;
        let c = ((x / h).floor() as usize).min(n - 1);
        let top = (c as f64 + 1.0) * h;
        let mut price = q[c] * (top - x) * (top - x) / 2.0;
        for j in c + 1..n {
            price += (u[j] - x) * q[j] * h;
        }
        price += (u_max - x) * p_r;
        call_prices.push(price);
        vols.push(if price > (f0 - x).max(0.0) {
            let o = Option_ {
                model: Model::Black76 { forward: f0, discount: 1.0, shift: 0.0 },
                call: true,
                strike: x,
                t: s.t,
            };
            Some(o.implied(price)?)
        } else {
            None
        });
    }
    let mut mass = 0.0;
    let mut mean = 0.0;
    for j in 0..n {
        mass += q[j] * h;
        mean += u[j] * q[j] * h;
    }
    Ok(ArbFree {
        call_prices,
        vols,
        mass: mass + p_l + p_r,
        mean: mean + u_max * p_r,
        absorbed: p_l,
        min_density: q.iter().copied().fold(f64::INFINITY, f64::min),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn s() -> Sabr {
        Sabr { t: 1.0, alpha: 0.3, beta: 0.5, rho: -0.4, nu: 0.5, forward: 1.0, shift: 0.0 }
    }

    #[test]
    fn scheme_conserves_mass_and_mean() {
        let r = arbfree(&s(), 400, 100, 100, &[0.8, 1.0, 1.2]).unwrap();
        assert!((r.mass - 1.0).abs() < 1e-11 && (r.mean - 1.0).abs() < 1e-10);
        assert!(r.min_density >= 0.0);
    }

    #[test]
    fn fit_recovers_truth() {
        let k = [0.6, 0.8, 0.9, 1.0, 1.1, 1.3, 1.6];
        let v = s().hagan(&k).unwrap();
        let r = calibrate(1.0, 1.0, 0.5, 0.0, &k, &v, None).unwrap();
        assert!((r[1] + 0.4).abs() < 1e-6 && r[3] < 1e-9);
    }
}
