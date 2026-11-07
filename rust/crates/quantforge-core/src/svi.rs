//! SVI, SSVI (`smile-and-surface.md`), and the small least-squares solver the fits share.
use crate::error::{Result, fail};

/// Levenberg-Marquardt with a central-difference Jacobian. `resid` returns `None` outside the
/// domain, and a step that lands there is refused. Returns the point and its sum of squares.
pub fn minimise<F>(x0: &[f64], resid: &F) -> Option<(Vec<f64>, f64)>
where
    F: Fn(&[f64]) -> Option<Vec<f64>>,
{
    let cost = |r: &[f64]| r.iter().map(|e| e * e).sum::<f64>();
    let n = x0.len();
    let mut x = x0.to_vec();
    let mut r = resid(&x)?;
    let mut c = cost(&r);
    let mut lambda = 1e-3;
    for _ in 0..1000 {
        if c < 1e-30 {
            break;
        }
        let mut jac = Vec::with_capacity(n);
        for j in 0..n {
            let h = 1e-6 * (1.0 + x[j].abs());
            let (mut up, mut down) = (x.clone(), x.clone());
            up[j] += h;
            down[j] -= h;
            let col: Vec<f64> = match (resid(&up), resid(&down)) {
                (Some(a), Some(b)) => a.iter().zip(&b).map(|(p, q)| (p - q) / (2.0 * h)).collect(),
                (Some(a), None) => a.iter().zip(&r).map(|(p, q)| (p - q) / h).collect(),
                (None, Some(b)) => r.iter().zip(&b).map(|(p, q)| (p - q) / h).collect(),
                (None, None) => vec![0.0; r.len()],
            };
            jac.push(col);
        }
        let dot = |a: &[f64], b: &[f64]| a.iter().zip(b).map(|(p, q)| p * q).sum::<f64>();
        let g: Vec<f64> = jac.iter().map(|col| dot(col, &r)).collect();
        let mut improved = false;
        let mut gain = 0.0;
        while lambda < 1e14 {
            let mut a = vec![vec![0.0; n + 1]; n];
            for p in 0..n {
                for q in 0..n {
                    a[p][q] = dot(&jac[p], &jac[q]);
                }
                a[p][p] += lambda * a[p][p].max(1e-14);
                a[p][n] = -g[p];
            }
            if let Some(dx) = gauss(a) {
                let trial: Vec<f64> = x.iter().zip(&dx).map(|(p, q)| p + q).collect();
                if let Some(tr) = resid(&trial) {
                    let tc = cost(&tr);
                    if tc.is_finite() && tc < c {
                        gain = c - tc;
                        x = trial;
                        r = tr;
                        c = tc;
                        lambda = (lambda / 5.0).max(1e-15);
                        improved = true;
                        break;
                    }
                }
            }
            lambda *= 4.0;
        }
        if !improved || gain <= 1e-17 * c {
            break;
        }
    }
    Some((x, c))
}

/// Gaussian elimination with pivoting on an augmented matrix.
fn gauss(mut a: Vec<Vec<f64>>) -> Option<Vec<f64>> {
    let n = a.len();
    for c in 0..n {
        let p = (c..n).max_by(|&i, &j| a[i][c].abs().total_cmp(&a[j][c].abs()))?;
        if a[p][c] == 0.0 || !a[p][c].is_finite() {
            return None;
        }
        a.swap(c, p);
        for r in c + 1..n {
            let m = a[r][c] / a[c][c];
            for k in c..=n {
                a[r][k] -= m * a[c][k];
            }
        }
    }
    let mut x = vec![0.0; n];
    for r in (0..n).rev() {
        let s: f64 = (r + 1..n).map(|k| a[r][k] * x[k]).sum();
        x[r] = (a[r][n] - s) / a[r][r];
    }
    Some(x)
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Svi {
    pub a: f64,
    pub b: f64,
    pub rho: f64,
    pub m: f64,
    pub sigma: f64,
}

impl Svi {
    fn valid(&self) -> bool {
        !(self.b < 0.0
            || self.rho.abs() >= 1.0
            || self.sigma <= 0.0
            || self.a + self.b * self.sigma * (1.0 - self.rho * self.rho).sqrt() <= 0.0)
    }

    pub fn check(&self) -> Result<()> {
        if self.valid() {
            Ok(())
        } else {
            fail("E_DOMAIN", "svi parameters are out of domain")
        }
    }

    pub fn w(&self, k: f64) -> f64 {
        let x = k - self.m;
        self.a + self.b * (self.rho * x + (x * x + self.sigma * self.sigma).sqrt())
    }

    /// Gatheral's density function.
    pub fn g(&self, k: f64) -> f64 {
        let x = k - self.m;
        let r = (x * x + self.sigma * self.sigma).sqrt();
        let (w, w1) = (self.w(k), self.b * (self.rho + x / r));
        let w2 = self.b * self.sigma * self.sigma / (r * r * r);
        let u = 1.0 - k * w1 / (2.0 * w);
        u * u - (w1 * w1 / 4.0) * (1.0 / w + 0.25) + w2 / 2.0
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct SviFit {
    pub svi: Svi,
    pub rmse: f64,
}

fn from_x(x: &[f64]) -> Svi {
    Svi {
        a: x[0],
        b: x[1].exp(),
        rho: x[2].tanh(),
        m: x[3],
        sigma: x[4].exp(),
    }
}

/// Weights default to 1. Starts sweep `rho`, `m`, `sigma`, and solve `a`, `b` by regression.
pub fn calibrate(k: &[f64], w: &[f64], weights: Option<&[f64]>) -> Result<SviFit> {
    if k.len() < 5 || k.len() != w.len() || weights.is_some_and(|v| v.len() != k.len()) {
        return fail("E_INPUT", "needs 5 points and equal lengths");
    }
    if k.windows(2).any(|p| p[1] <= p[0]) {
        return fail("E_INPUT", "log_moneyness must strictly increase");
    }
    if w.iter().any(|&v| v <= 0.0) || weights.is_some_and(|v| v.iter().any(|&x| x <= 0.0)) {
        return fail("E_DOMAIN", "a total variance or weight is not positive");
    }
    let ones = vec![1.0; k.len()];
    let wt = weights.unwrap_or(&ones);
    let roots: Vec<f64> = wt.iter().map(|v| v.sqrt()).collect();
    let resid = |x: &[f64]| -> Option<Vec<f64>> {
        let s = from_x(x);
        if !s.valid() || !s.b.is_finite() || !s.sigma.is_finite() {
            return None;
        }
        Some(
            k.iter()
                .zip(w)
                .zip(&roots)
                .map(|((&k, &w), r)| r * (s.w(k) - w))
                .collect(),
        )
    };
    let lowest = (0..k.len())
        .min_by(|&i, &j| w[i].total_cmp(&w[j]))
        .unwrap_or(0);
    let span = k[k.len() - 1] - k[0];
    let mut best: Option<(Vec<f64>, f64)> = None;
    for dm in [-0.25, -0.1, 0.0, 0.1, 0.25] {
        for sigma in [0.03 * span, 0.12 * span, 0.4 * span] {
            for rho in [-0.7, -0.3, 0.0, 0.3, 0.7] {
                let m = k[lowest] + dm * span;
                let basis: Vec<f64> = k
                    .iter()
                    .map(|&v| rho * (v - m) + ((v - m) * (v - m) + sigma * sigma).sqrt())
                    .collect();
                let n = k.len() as f64;
                let (xb, yb) = (basis.iter().sum::<f64>() / n, w.iter().sum::<f64>() / n);
                let sxy: f64 = basis.iter().zip(w).map(|(x, y)| (x - xb) * (y - yb)).sum();
                let sxx: f64 = basis.iter().map(|x| (x - xb) * (x - xb)).sum();
                let b = (sxy / sxx).max(1e-4);
                let floor = 1e-8 - b * sigma * (1.0f64 - rho * rho).sqrt();
                let a = (yb - b * xb).max(floor);
                let x0 = [a, b.ln(), rho.atanh(), m, sigma.ln()];
                if let Some((x, c)) = minimise(&x0, &resid)
                    && best.as_ref().is_none_or(|p| c < p.1)
                {
                    best = Some((x, c));
                }
            }
        }
    }
    let Some((x, _)) = best else {
        return fail("E_NO_CONVERGENCE", "no start reached a fit");
    };
    let svi = from_x(&x);
    let num: f64 = k
        .iter()
        .zip(w)
        .zip(wt)
        .map(|((&k, &w), q)| {
            let e = svi.w(k) - w;
            q * e * e
        })
        .sum();
    Ok(SviFit {
        svi,
        rmse: (num / wt.iter().sum::<f64>()).sqrt(),
    })
}

pub fn ssvi_phi(theta: f64, eta: f64, gamma: f64) -> f64 {
    eta * theta.powf(-gamma) * (1.0 + theta).powf(gamma - 1.0)
}

pub fn ssvi_w(k: f64, theta: f64, rho: f64, eta: f64, gamma: f64) -> f64 {
    let p = ssvi_phi(theta, eta, gamma);
    let x = p * k;
    theta / 2.0 * (1.0 + rho * x + ((x + rho) * (x + rho) + 1.0 - rho * rho).sqrt())
}

fn check_thetas(thetas: &[f64]) -> Result<()> {
    if thetas.iter().any(|&t| t <= 0.0) {
        return fail("E_DOMAIN", "a theta is not positive");
    }
    if thetas.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "thetas must strictly increase");
    }
    Ok(())
}

#[derive(Debug, Clone, PartialEq)]
pub struct Ssvi {
    pub total_variance: Vec<Vec<f64>>,
    pub butterfly_free: bool,
    pub calendar_free: bool,
}

pub fn ssvi_evaluate(rho: f64, eta: f64, gamma: f64, thetas: &[f64], k: &[f64]) -> Result<Ssvi> {
    if rho.abs() >= 1.0 || eta <= 0.0 || gamma <= 0.0 || gamma > 1.0 {
        return fail("E_DOMAIN", "ssvi parameters are out of domain");
    }
    check_thetas(thetas)?;
    let a = 1.0 + rho.abs();
    let butterfly_free = thetas.iter().all(|&t| {
        let p = ssvi_phi(t, eta, gamma);
        t * p * a < 4.0 && t * p * p * a <= 4.0
    });
    let bound = 1.0 + (1.0 - rho * rho).sqrt();
    let calendar_free = thetas
        .iter()
        .all(|&t| rho * rho * (1.0 - gamma) / (1.0 + t) <= bound);
    Ok(Ssvi {
        total_variance: thetas
            .iter()
            .map(|&t| k.iter().map(|&v| ssvi_w(v, t, rho, eta, gamma)).collect())
            .collect(),
        butterfly_free,
        calendar_free,
    })
}

/// `rho`, `eta`, `gamma`, `rmse`.
pub fn ssvi_calibrate(thetas: &[f64], k: &[f64], w: &[Vec<f64>]) -> Result<[f64; 4]> {
    let count = thetas.len() * k.len();
    if count < 3 || w.len() != thetas.len() || w.iter().any(|r| r.len() != k.len()) {
        return fail("E_INPUT", "too few points, or ragged rows");
    }
    check_thetas(thetas)?;
    let params = |x: &[f64]| (x[0].tanh(), x[1].exp(), 1.0 / (1.0 + (-x[2]).exp()));
    let resid = |x: &[f64]| -> Option<Vec<f64>> {
        let (rho, eta, gamma) = params(x);
        if rho.abs() >= 1.0 || !eta.is_finite() || eta <= 0.0 || gamma <= 0.0 {
            return None;
        }
        let mut r = Vec::with_capacity(count);
        for (t, row) in thetas.iter().zip(w) {
            for (v, y) in k.iter().zip(row) {
                r.push(ssvi_w(*v, *t, rho, eta, gamma) - y);
            }
        }
        Some(r)
    };
    let mut best: Option<(Vec<f64>, f64)> = None;
    for rho in [-0.7f64, -0.3, 0.0, 0.3, 0.7] {
        for eta in [0.3f64, 1.0, 3.0] {
            for gamma in [0.2f64, 0.5, 0.8] {
                let x0 = [rho.atanh(), eta.ln(), (gamma / (1.0 - gamma)).ln()];
                if let Some((x, c)) = minimise(&x0, &resid)
                    && best.as_ref().is_none_or(|p| c < p.1)
                {
                    best = Some((x, c));
                }
            }
        }
    }
    let Some((x, c)) = best else {
        return fail("E_NO_CONVERGENCE", "no start reached a fit");
    };
    let (rho, eta, gamma) = params(&x);
    Ok([rho, eta, gamma, (c / count as f64).sqrt()])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn svi_fit_recovers_truth() {
        let t = Svi {
            a: 0.03,
            b: 0.12,
            rho: -0.35,
            m: 0.02,
            sigma: 0.15,
        };
        let k = [-0.6, -0.4, -0.25, -0.1, 0.0, 0.1, 0.25, 0.4, 0.6];
        let w: Vec<f64> = k.iter().map(|&x| t.w(x)).collect();
        let r = calibrate(&k, &w, None).unwrap();
        assert!((r.svi.rho - t.rho).abs() < 1e-6 && r.rmse < 1e-9);
    }

    #[test]
    fn ssvi_atm_is_theta() {
        assert!((ssvi_w(0.0, 0.09, -0.4, 1.0, 0.5) - 0.09).abs() < 1e-15);
    }
}
