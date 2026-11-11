//! Stage F GARCH(1,1): Student-t innovations, a held mean, and maximum likelihood with
//! observed-information standard errors (`05-volatility/garch.md`, "Stage F additions",
//! rulings F-11 to F-14).
use crate::error::{Result, fail};
use crate::garch::{Likelihood, Start, loglik, nelder_mead};
use std::f64::consts::PI;

/// `lnGamma` by Lanczos (g = 7, 9 terms) with reflection below 1/2.
pub fn ln_gamma(x: f64) -> Result<f64> {
    crate::error::finite("x", &x)?;
    if x <= 0.0 {
        return fail("E_DOMAIN", "ln_gamma needs x > 0");
    }
    Ok(lgamma(x))
}

pub(crate) fn lgamma(x: f64) -> f64 {
    const G: [f64; 9] = [
        0.999_999_999_999_809_9,
        676.520_368_121_885_1,
        -1_259.139_216_722_402_8,
        771.323_428_777_653_1,
        -176.615_029_162_140_6,
        12.507_343_278_686_905,
        -0.138_571_095_265_720_12,
        9.984_369_578_019_572e-6,
        1.505_632_735_149_311_6e-7,
    ];
    if x < 0.5 {
        return (PI / (PI * x).sin()).ln() - lgamma(1.0 - x);
    }
    let x = x - 1.0;
    let t = x + 7.5;
    let mut a = G[0];
    for (i, g) in G.iter().enumerate().skip(1) {
        a += g / (x + i as f64);
    }
    0.5 * (2.0 * PI).ln() + (x + 0.5) * t.ln() - t + a.ln()
}

/// Digamma by recurrence to `x >= 10` and the asymptotic series.
fn digamma(mut x: f64) -> f64 {
    let mut r = 0.0;
    while x < 10.0 {
        r -= 1.0 / x;
        x += 1.0;
    }
    let f = 1.0 / (x * x);
    r + x.ln()
        - 0.5 / x
        - f * (1.0 / 12.0 - f * (1.0 / 120.0 - f * (1.0 / 252.0 - f * (1.0 / 240.0 - f / 132.0))))
}

/// Innovation law (ruling F-14).
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Distribution {
    Normal,
    /// Student-t scaled to unit variance, with `nu` degrees of freedom.
    StudentT(f64),
}

impl crate::error::Finite for Distribution {
    fn is_all_finite(&self) -> bool {
        match self {
            Self::Normal => true,
            Self::StudentT(nu) => nu.is_finite(),
        }
    }
}

/// Log-likelihood and its exact gradient in `(omega, alpha, beta[, nu])` on demeaned returns,
/// with `sigma2_1 = s1` fixed.
fn loglik_grad(e: &[f64], p: &[f64], student: bool, s1: f64) -> (f64, Vec<f64>) {
    let (omega, alpha, beta) = (p[0], p[1], p[2]);
    let nu = if student { p[3] } else { 0.0 };
    let (mut s, mut ds) = (s1, [0.0_f64; 3]);
    let (mut l, mut g) = (0.0, vec![0.0; p.len()]);
    let (c, dc) = if student {
        (
            lgamma((nu + 1.0) / 2.0) - lgamma(nu / 2.0) - 0.5 * (PI * (nu - 2.0)).ln(),
            0.5 * digamma((nu + 1.0) / 2.0) - 0.5 * digamma(nu / 2.0) - 0.5 / (nu - 2.0),
        )
    } else {
        (-0.5 * (2.0 * PI).ln(), 0.0)
    };
    for &x in e {
        let dl_ds = if student {
            let q = x * x / ((nu - 2.0) * s);
            l += c - 0.5 * s.ln() - (nu + 1.0) / 2.0 * q.ln_1p();
            g[3] += dc - 0.5 * q.ln_1p() + (nu + 1.0) / 2.0 * q / ((nu - 2.0) * (1.0 + q));
            -0.5 / s + (nu + 1.0) / 2.0 * q / (s * (1.0 + q))
        } else {
            l += c - 0.5 * (s.ln() + x * x / s);
            -0.5 * (1.0 / s - x * x / (s * s))
        };
        for k in 0..3 {
            g[k] += dl_ds * ds[k];
        }
        let d = [1.0, x * x, s];
        for k in 0..3 {
            ds[k] = d[k] + beta * ds[k];
        }
        s = omega + alpha * x * x + beta * s;
    }
    (l, g)
}

/// Hessian by central differences of the exact gradient, relative step 1e-5, symmetrised.
fn hessian(e: &[f64], p: &[f64], student: bool, s1: f64) -> Vec<Vec<f64>> {
    let n = p.len();
    let mut h = vec![vec![0.0; n]; n];
    for j in 0..n {
        let step = 1e-5 * p[j].abs();
        let (mut up, mut dn) = (p.to_vec(), p.to_vec());
        up[j] += step;
        dn[j] -= step;
        let gu = loglik_grad(e, &up, student, s1).1;
        let gd = loglik_grad(e, &dn, student, s1).1;
        for i in 0..n {
            h[i][j] = (gu[i] - gd[i]) / (2.0 * step);
        }
    }
    for i in 0..n {
        for j in 0..i {
            let m = 0.5 * (h[i][j] + h[j][i]);
            h[i][j] = m;
            h[j][i] = m;
        }
    }
    h
}

/// Inverse by Gauss-Jordan with partial pivoting; `None` if singular.
fn invert(a: &[Vec<f64>]) -> Option<Vec<Vec<f64>>> {
    let n = a.len();
    let mut m: Vec<Vec<f64>> = a
        .iter()
        .enumerate()
        .map(|(i, r)| {
            let mut row = r.clone();
            row.extend((0..n).map(|j| if i == j { 1.0 } else { 0.0 }));
            row
        })
        .collect();
    for c in 0..n {
        let p = (c..n).max_by(|&x, &y| m[x][c].abs().total_cmp(&m[y][c].abs()))?;
        if m[p][c] == 0.0 {
            return None;
        }
        m.swap(c, p);
        let d = m[c][c];
        for v in &mut m[c] {
            *v /= d;
        }
        let pivot = m[c].clone();
        for (r, row) in m.iter_mut().enumerate() {
            if r != c {
                let f = row[c];
                for (v, pv) in row.iter_mut().zip(&pivot) {
                    *v -= f * pv;
                }
            }
        }
    }
    Some(m.into_iter().map(|r| r[n..].to_vec()).collect())
}

fn positive_definite(a: &[Vec<f64>]) -> bool {
    let n = a.len();
    let mut l = vec![vec![0.0; n]; n];
    for i in 0..n {
        for j in 0..=i {
            let s: f64 = (0..j).map(|k| l[i][k] * l[j][k]).sum();
            if i == j {
                let d = a[i][i] - s;
                if d.is_nan() || d <= 0.0 {
                    return false;
                }
                l[i][i] = d.sqrt();
            } else {
                l[i][j] = (a[i][j] - s) / l[j][j];
            }
        }
    }
    true
}

fn start_variance(e: &[f64], start: Start) -> Result<f64> {
    let v = match start {
        Start::Sample => e.iter().map(|r| r * r).sum::<f64>() / e.len() as f64,
        Start::Given(v) => v,
    };
    if v > 0.0 {
        Ok(v)
    } else {
        fail("E_DOMAIN", "initial variance must be positive")
    }
}

/// `vol.garch.loglik` with the stage F inputs: a mean and an innovation law.
pub fn loglik_with(
    returns: &[f64],
    theta: (f64, f64, f64),
    start: Start,
    dist: Distribution,
    mean: f64,
) -> Result<Likelihood> {
    crate::error::finite("returns", &returns)?;
    crate::error::finite("theta", &theta)?;
    crate::error::finite("start", &start)?;
    crate::error::finite("dist", &dist)?;
    crate::error::finite("mean", &mean)?;
    let e: Vec<f64> = returns.iter().map(|r| r - mean).collect();
    let (o, a, b) = theta;
    let mut base = loglik(&e, o, a, b, start)?;
    if let Distribution::StudentT(nu) = dist {
        if nu <= 2.0 {
            return fail("E_DOMAIN", "degrees_of_freedom must be above 2");
        }
        let s1 = start_variance(&e, start)?;
        base.loglik = loglik_grad(&e, &[o, a, b, nu], true, s1).0;
    }
    Ok(base)
}

#[derive(Debug, Clone, PartialEq)]
pub struct Estimate {
    pub omega: f64,
    pub alpha: f64,
    pub beta: f64,
    pub degrees_of_freedom: Option<f64>,
    pub mean: f64,
    pub loglik: f64,
    /// `omega`, `alpha`, `beta`, then `nu` for Student-t.
    pub std_errors: Vec<f64>,
}

fn logistic(x: f64) -> f64 {
    1.0 / (1.0 + (-x).exp())
}

/// Unconstrained search point to natural parameters.
fn natural(u: &[f64], student: bool) -> Vec<f64> {
    let (s, a) = (logistic(u[1]), logistic(u[2]));
    let mut p = vec![u[0].exp(), s * a, s * (1.0 - a)];
    if student {
        p.push(2.0 + 498.0 * logistic(u[3]));
    }
    p
}

/// Multi-start Nelder-Mead in the unconstrained parametrisation; best point found.
fn search(e: &[f64], s1: f64, var: f64, student: bool) -> Option<Vec<f64>> {
    let neg = |u: &[f64]| {
        let l = loglik_grad(e, &natural(u, student), student, s1).0;
        if l.is_finite() { -l } else { f64::INFINITY }
    };
    let nus: &[f64] = if student { &[5.0, 10.0, 30.0] } else { &[0.0] };
    let mut best: Option<(Vec<f64>, f64)> = None;
    for &persist in &[0.5_f64, 0.9, 0.98] {
        for &share in &[0.05_f64, 0.15, 0.3] {
            for &nu0 in nus {
                let mut u0 = vec![
                    (var * (1.0 - persist)).ln(),
                    (persist / (1.0 - persist)).ln(),
                    (share / (1.0 - share)).ln(),
                ];
                if student {
                    let z = (nu0 - 2.0) / 498.0;
                    u0.push((z / (1.0 - z)).ln());
                }
                let (mut x, mut v) = nelder_mead(&neg, &u0, 0.5, 4000);
                for _ in 0..20 {
                    let (x2, v2) = nelder_mead(&neg, &x, 0.05, 4000);
                    let gain = v - v2;
                    (x, v) = (x2, v2.min(v));
                    if gain <= 1e-12 {
                        break;
                    }
                }
                if v.is_finite() && best.as_ref().is_none_or(|b| v < b.1) {
                    best = Some((x, v));
                }
            }
        }
    }
    best.map(|(u, _)| natural(&u, student))
}

/// `vol.garch.estimate`: interior maximum only (F-11), Newton-polished to a relative step
/// below 1e-12, with standard errors from `(-H)^{-1}` (F-13). The mean is removed first and
/// held fixed (F-12).
pub fn estimate(returns: &[f64], start: Start, student: bool, demean: bool) -> Result<Estimate> {
    crate::error::finite("returns", &returns)?;
    crate::error::finite("start", &start)?;
    if returns.len() < 30 || (student && returns.len() < 100) {
        return fail("E_INPUT", "too few returns");
    }
    let n = returns.len() as f64;
    let mean = if demean {
        returns.iter().sum::<f64>() / n
    } else {
        0.0
    };
    let e: Vec<f64> = returns.iter().map(|r| r - mean).collect();
    let s1 = start_variance(&e, start)?;
    let var = e.iter().map(|x| x * x).sum::<f64>() / n;
    let no = || fail("E_NO_CONVERGENCE", "no interior maximum of the likelihood");
    let Some(mut p) = search(&e, s1, var, student) else {
        return no();
    };
    let interior = |p: &[f64]| {
        p[0] >= 1e-6 * var
            && p[1] >= 1e-6
            && p[2] >= 1e-6
            && 1.0 - p[1] - p[2] >= 1e-6
            && (!student || (p[3] - 2.0 >= 1e-6 && 500.0 - p[3] >= 1e-6))
    };
    let mut converged = false;
    for _ in 0..100 {
        if !interior(&p) {
            return no();
        }
        let g = loglik_grad(&e, &p, student, s1).1;
        let Some(hi) = invert(&hessian(&e, &p, student, s1)) else {
            return no();
        };
        let step: Vec<f64> = (0..p.len())
            .map(|i| -(0..p.len()).map(|j| hi[i][j] * g[j]).sum::<f64>())
            .collect();
        let rel = step
            .iter()
            .zip(&p)
            .map(|(s, x)| (s / x).abs())
            .fold(0.0, f64::max);
        for (x, s) in p.iter_mut().zip(&step) {
            *x += s;
        }
        if rel < 1e-12 {
            converged = true;
            break;
        }
    }
    if !converged || !interior(&p) {
        return no();
    }
    let neg_h: Vec<Vec<f64>> = hessian(&e, &p, student, s1)
        .iter()
        .map(|r| r.iter().map(|x| -x).collect())
        .collect();
    if !positive_definite(&neg_h) {
        return no();
    }
    let Some(cov) = invert(&neg_h) else {
        return no();
    };
    Ok(Estimate {
        omega: p[0],
        alpha: p[1],
        beta: p[2],
        degrees_of_freedom: student.then(|| p[3]),
        mean,
        loglik: loglik_grad(&e, &p, student, s1).0,
        std_errors: (0..p.len()).map(|i| cov[i][i].sqrt()).collect(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ln_gamma_values() {
        assert!((lgamma(1.0)).abs() < 1e-14);
        assert!((lgamma(2.0)).abs() < 1e-14);
        assert!((lgamma(0.5) - PI.sqrt().ln()).abs() < 1e-14);
        // ln(9!) = ln 362880
        assert!((lgamma(10.0) - 362_880.0_f64.ln()).abs() < 1e-13);
        assert_eq!(ln_gamma(0.0).unwrap_err().code, "E_DOMAIN");
        assert_eq!(ln_gamma(f64::NAN).unwrap_err().code, "E_DOMAIN");
        assert!(ln_gamma(f64::MIN_POSITIVE).is_ok());
    }

    #[test]
    fn digamma_values() {
        // psi(1) = -Euler gamma
        assert!((digamma(1.0) + std::f64::consts::EULER_GAMMA).abs() < 1e-13);
    }

    #[test]
    fn gradient_matches_differences() {
        let e: Vec<f64> = (0..200)
            .map(|i| 0.01 * ((f64::from(i) * 1.7).sin() + 0.3 * (f64::from(i) * 0.37).cos()))
            .collect();
        for (p, st) in [
            (vec![2e-5, 0.08, 0.85], false),
            (vec![2e-5, 0.08, 0.85, 6.0], true),
        ] {
            let g = loglik_grad(&e, &p, st, 1e-4).1;
            for j in 0..p.len() {
                let h = 1e-6 * p[j];
                let (mut u, mut d) = (p.clone(), p.clone());
                u[j] += h;
                d[j] -= h;
                let fd =
                    (loglik_grad(&e, &u, st, 1e-4).0 - loglik_grad(&e, &d, st, 1e-4).0) / (2.0 * h);
                assert!(
                    (fd - g[j]).abs() <= 1e-5 * g[j].abs().max(1.0),
                    "{j} {fd} {}",
                    g[j]
                );
            }
        }
    }

    #[test]
    fn edges() {
        let r: Vec<f64> = (0..99).map(|i| 0.01 * (f64::from(i) * 1.3).sin()).collect();
        let code = |x: Result<Estimate>| x.unwrap_err().code;
        assert_eq!(
            code(estimate(&r[..29], Start::Sample, false, false)),
            "E_INPUT"
        );
        assert_eq!(code(estimate(&r, Start::Sample, true, false)), "E_INPUT");
        assert_eq!(
            code(estimate(&r, Start::Given(0.0), false, false)),
            "E_DOMAIN"
        );
        assert_eq!(
            code(estimate(&[0.0; 40], Start::Sample, false, true)),
            "E_DOMAIN"
        );
        let t = Distribution::StudentT(2.0);
        let l = loglik_with(&r, (1e-5, 0.1, 0.8), Start::Sample, t, 0.0);
        assert_eq!(l.unwrap_err().code, "E_DOMAIN");
        let t = Distribution::StudentT(2.0 + 1e-9);
        assert!(loglik_with(&r, (1e-5, 0.1, 0.8), Start::Sample, t, 0.0).is_ok());
    }
}
