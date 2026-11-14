//! Stage J wave 2: mean-variance, risk parity, Euler contributions (`07-portfolio/optimisation.md`),
//! Ledoit-Wolf and Black-Litterman (`07-portfolio/estimation.md`), the Acerbi-Szekely Z2 statistic
//! (`06-risk/es-backtest.md`) and Baum-Welch (`11-research/baum-welch.md`).
// Negated comparisons are deliberate: they reject NaN inputs with the domain error.
#![allow(clippy::neg_cmp_op_on_partial_ord)]
use crate::error::{Result, fail};

type Mat = Vec<Vec<f64>>;

fn square(s: &[Vec<f64>], n: usize) -> bool {
    s.len() == n && s.iter().all(|r| r.len() == n)
}

/// Ruling J-W2-3: symmetric within `1e-12 max|S|`; afterwards the upper triangle is used.
fn symmetric(s: &[Vec<f64>]) -> Result<Mat> {
    let n = s.len();
    let big = s.iter().flatten().fold(
        0.0_f64,
        |m, v| if v.is_nan() { f64::NAN } else { m.max(v.abs()) },
    );
    for i in 0..n {
        for j in 0..i {
            if !((s[i][j] - s[j][i]).abs() <= 1e-12 * big) {
                return fail("E_DOMAIN", "the matrix is not symmetric");
            }
        }
    }
    Ok((0..n)
        .map(|i| (0..n).map(|j| s[i.min(j)][i.max(j)]).collect())
        .collect())
}

/// Lower Cholesky factor; a pivot that is not positive is `E_DOMAIN` (J-W2-3).
fn cholesky(a: &[Vec<f64>]) -> Result<Mat> {
    let n = a.len();
    let mut l = vec![vec![0.0; n]; n];
    for j in 0..n {
        let mut d = a[j][j];
        for k in 0..j {
            d -= l[j][k] * l[j][k];
        }
        if !(d > 0.0) {
            return fail("E_DOMAIN", "the matrix is not positive definite");
        }
        let p = d.sqrt();
        l[j][j] = p;
        for i in j + 1..n {
            let mut s = a[i][j];
            for k in 0..j {
                s -= l[i][k] * l[j][k];
            }
            l[i][j] = s / p;
        }
    }
    Ok(l)
}

fn chol_solve(l: &[Vec<f64>], b: &[f64]) -> Vec<f64> {
    let n = l.len();
    let mut y = b.to_vec();
    for i in 0..n {
        for k in 0..i {
            y[i] -= l[i][k] * y[k];
        }
        y[i] /= l[i][i];
    }
    for i in (0..n).rev() {
        for k in i + 1..n {
            y[i] -= l[k][i] * y[k];
        }
        y[i] /= l[i][i];
    }
    y
}

fn mul(s: &[Vec<f64>], w: &[f64]) -> Vec<f64> {
    s.iter()
        .map(|r| r.iter().zip(w).map(|(a, b)| a * b).sum())
        .collect()
}

fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b).map(|(x, y)| x * y).sum()
}

pub struct MeanVariance {
    pub weights: Vec<f64>,
    pub expected_return: f64,
    pub volatility: f64,
    pub objective: f64,
    pub at_bound: Vec<i64>,
}

/// Maximise `mu'w - (gamma/2) w' Sigma w` with `sum w = 1` and bounds, by a primal active set.
pub fn mean_variance(
    mu: &[f64],
    sigma: &[Vec<f64>],
    gamma: f64,
    lower: Option<&[f64]>,
    upper: Option<&[f64]>,
) -> Result<MeanVariance> {
    let n = mu.len();
    let lo = lower.map_or_else(|| vec![0.0; n], <[f64]>::to_vec);
    let hi = upper.map_or_else(|| vec![1.0; n], <[f64]>::to_vec);
    if n == 0 || !square(sigma, n) || lo.len() != n || hi.len() != n {
        return fail(
            "E_INPUT",
            "expected_returns, covariance and bounds must agree in size",
        );
    }
    if !(gamma > 0.0) {
        return fail("E_DOMAIN", "risk_aversion must be positive");
    }
    if (0..n).any(|i| !(lo[i] <= hi[i])) {
        return fail("E_DOMAIN", "lower must not exceed upper");
    }
    let (sl, su): (f64, f64) = (lo.iter().sum(), hi.iter().sum());
    if sl > 1.0 || su < 1.0 {
        return fail("E_DOMAIN", "the bounds admit no fully invested portfolio");
    }
    let s = symmetric(sigma)?;
    cholesky(&s)?;
    // Feasible start: every weight at its lower bound, the rest filled in index order.
    let mut w = lo.clone();
    let mut state = vec![-1_i8; n];
    let mut left = 1.0 - sl;
    for i in 0..n {
        let room = hi[i] - lo[i];
        if left >= room {
            w[i] = hi[i];
            state[i] = 1;
            left -= room;
        } else if left > 0.0 {
            w[i] = lo[i] + left;
            state[i] = 0;
            left = 0.0;
        }
    }
    for _ in 0..(50 * n + 100) {
        let free: Vec<usize> = (0..n).filter(|&i| state[i] == 0).collect();
        if free.is_empty() {
            // Ruling J-W2-20: free the last asset; the budget fixes its weight and nu.
            state[n - 1] = 0;
            continue;
        }
        let fixed_sum: f64 = (0..n).filter(|&i| state[i] != 0).map(|i| w[i]).sum();
        let sff: Mat = free
            .iter()
            .map(|&i| free.iter().map(|&j| s[i][j]).collect())
            .collect();
        let r: Vec<f64> = free
            .iter()
            .map(|&i| {
                let c: f64 = (0..n)
                    .filter(|&j| state[j] != 0)
                    .map(|j| s[i][j] * w[j])
                    .sum();
                mu[i] - gamma * c
            })
            .collect();
        let l = cholesky(&sff)?;
        let a = chol_solve(&l, &r);
        let z = chol_solve(&l, &vec![1.0; free.len()]);
        let nu = (a.iter().sum::<f64>() - gamma * (1.0 - fixed_sum)) / z.iter().sum::<f64>();
        let target: Vec<f64> = a
            .iter()
            .zip(&z)
            .map(|(x, y)| (x - nu * y) / gamma)
            .collect();
        // Ratio test towards the equality-constrained optimum on the free set.
        let mut step = 1.0;
        let mut block = None;
        for (k, &i) in free.iter().enumerate() {
            let p = target[k] - w[i];
            if p < 0.0 && target[k] < lo[i] - 1e-14 * (1.0 + lo[i].abs()) {
                let t = (lo[i] - w[i]) / p;
                if t < step {
                    step = t;
                    block = Some((i, -1));
                }
            } else if p > 0.0 && target[k] > hi[i] + 1e-14 * (1.0 + hi[i].abs()) {
                let t = (hi[i] - w[i]) / p;
                if t < step {
                    step = t;
                    block = Some((i, 1));
                }
            }
        }
        if let Some((b, side)) = block {
            for (k, &i) in free.iter().enumerate() {
                w[i] += step.max(0.0) * (target[k] - w[i]);
            }
            w[b] = if side < 0 { lo[b] } else { hi[b] };
            state[b] = side;
            continue;
        }
        for (k, &i) in free.iter().enumerate() {
            w[i] = target[k].clamp(lo[i], hi[i]);
        }
        // Multipliers of the bounds: g_i = mu_i - gamma (Sigma w)_i - nu.
        let sw = mul(&s, &w);
        let mut worst = (0.0_f64, None);
        for i in 0..n {
            let g = mu[i] - gamma * sw[i] - nu;
            // Ruling J-W2-21: a fixed weight (lower = upper) never leaves the working set.
            let v = match state[i] {
                _ if lo[i] == hi[i] => 0.0,

                -1 => g,
                1 => -g,
                _ => 0.0,
            };
            if v > worst.0.max(1e-13) {
                worst = (v, Some(i));
            }
        }
        if let Some(i) = worst.1 {
            state[i] = 0;
        } else {
            {
                let sw = mul(&s, &w);
                let var = dot(&w, &sw);
                let er = dot(mu, &w);
                let at_bound = (0..n)
                    .map(|i| {
                        if w[i] == lo[i] {
                            -1
                        } else {
                            i64::from(w[i] == hi[i])
                        }
                    })
                    .collect();
                return Ok(MeanVariance {
                    expected_return: er,
                    volatility: var.sqrt(),
                    objective: er - 0.5 * gamma * var,
                    at_bound,
                    weights: w,
                });
            }
        }
    }
    fail("E_CONVERGENCE", "the active-set method did not finish")
}

/// Weights, volatility and contributions of long-only risk parity (J-W2-5).
pub fn risk_parity(
    sigma: &[Vec<f64>],
    budgets: Option<&[f64]>,
) -> Result<(Vec<f64>, f64, Vec<f64>)> {
    let n = sigma.len();
    let b0 = budgets.map_or_else(|| vec![1.0 / n as f64; n], <[f64]>::to_vec);
    if n == 0 || !square(sigma, n) || b0.len() != n {
        return fail("E_INPUT", "covariance and budgets must agree in size");
    }
    if b0.iter().any(|&b| !(b > 0.0)) {
        return fail("E_DOMAIN", "budgets must be positive");
    }
    let total: f64 = b0.iter().sum();
    // Ruling J-W2-19: only supplied budgets are sum-tested.
    if budgets.is_some() && !((total - 1.0).abs() <= 1e-12) {
        return fail("E_DOMAIN", "budgets must sum to 1");
    }
    let s = symmetric(sigma)?;
    cholesky(&s)?;
    let b: Vec<f64> = b0.iter().map(|x| x / total).collect();
    let bn = dot(&b, &b).sqrt();
    let mut y: Vec<f64> = (0..n).map(|i| (b[i] / s[i][i]).sqrt()).collect();
    for _ in 0..500 {
        let sy = mul(&s, &y);
        let f: Vec<f64> = (0..n).map(|i| sy[i] - b[i] / y[i]).collect();
        if dot(&f, &f).sqrt() < 1e-14 * bn {
            break;
        }
        let mut j = s.clone();
        for i in 0..n {
            j[i][i] += b[i] / (y[i] * y[i]);
        }
        let l = cholesky(&j)?;
        let neg: Vec<f64> = f.iter().map(|v| -v).collect();
        let d = chol_solve(&l, &neg);
        let mut t = 1.0;
        while (0..n).any(|i| y[i] + t * d[i] <= 0.0) {
            t *= 0.5;
        }
        for i in 0..n {
            y[i] += t * d[i];
        }
        if t * dot(&d, &d).sqrt() < 1e-15 {
            break;
        }
    }
    let sum: f64 = y.iter().sum();
    let w: Vec<f64> = y.iter().map(|v| v / sum).collect();
    let sw = mul(&s, &w);
    let vol = dot(&w, &sw).sqrt();
    let c = (0..n).map(|i| w[i] * sw[i] / vol).collect();
    Ok((w, vol, c))
}

pub struct Euler {
    pub volatility: f64,
    pub marginal: Vec<f64>,
    pub contributions: Vec<f64>,
    pub shares: Vec<f64>,
}

/// Euler risk contributions of volatility (J-W2-6).
pub fn euler(w: &[f64], sigma: &[Vec<f64>]) -> Result<Euler> {
    let n = w.len();
    if n == 0 || !square(sigma, n) {
        return fail("E_INPUT", "weights and covariance must agree in size");
    }
    let s = symmetric(sigma)?;
    let sw = mul(&s, w);
    let var = dot(w, &sw);
    if !(var > 0.0) {
        return fail("E_DOMAIN", "the portfolio variance is not positive");
    }
    let vol = var.sqrt();
    let marginal: Vec<f64> = sw.iter().map(|v| v / vol).collect();
    let contributions: Vec<f64> = (0..n).map(|i| w[i] * marginal[i]).collect();
    let shares = contributions.iter().map(|c| c / vol).collect();
    Ok(Euler {
        volatility: vol,
        marginal,
        contributions,
        shares,
    })
}

/// Ledoit-Wolf shrinkage to the scaled identity (J-W2-7): covariance, delta, m.
pub fn ledoit_wolf(x: &[Vec<f64>]) -> Result<(Mat, f64, f64)> {
    let t = x.len();
    let n = x.first().map_or(0, Vec::len);
    if t < 2 || n == 0 || x.iter().any(|r| r.len() != n) {
        return fail(
            "E_INPUT",
            "returns need at least two rows of equal, non-zero length",
        );
    }
    let tf = t as f64;
    let mean: Vec<f64> = (0..n)
        .map(|j| x.iter().map(|r| r[j]).sum::<f64>() / tf)
        .collect();
    let d: Mat = x
        .iter()
        .map(|r| r.iter().zip(&mean).map(|(a, m)| a - m).collect())
        .collect();
    let mut s = vec![vec![0.0; n]; n];
    for i in 0..n {
        for j in 0..n {
            s[i][j] = d.iter().map(|r| r[i] * r[j]).sum::<f64>() / tf;
        }
    }
    let nf = n as f64;
    let m = (0..n).map(|i| s[i][i]).sum::<f64>() / nf;
    let mut d2 = 0.0;
    for i in 0..n {
        for j in 0..n {
            let v = s[i][j] - if i == j { m } else { 0.0 };
            d2 += v * v;
        }
    }
    d2 /= nf;
    let mut bsum = 0.0;
    for r in &d {
        let mut e = 0.0;
        for i in 0..n {
            for j in 0..n {
                let v = r[i] * r[j] - s[i][j];
                e += v * v;
            }
        }
        bsum += e / nf;
    }
    let bbar2 = bsum / (tf * tf);
    let b2 = bbar2.min(d2);
    let delta = if b2 == 0.0 { 0.0 } else { b2 / d2 };
    let cov = (0..n)
        .map(|i| {
            (0..n)
                .map(|j| (if i == j { delta * m } else { 0.0 }) + (1.0 - delta) * s[i][j])
                .collect()
        })
        .collect();
    Ok((cov, delta, m))
}

/// Black-Litterman posterior mean, covariance of the mean and predictive covariance (J-W2-8).
pub fn black_litterman(
    sigma: &[Vec<f64>],
    pi: &[f64],
    p: &[Vec<f64>],
    q: &[f64],
    omega: &[Vec<f64>],
    tau: f64,
) -> Result<(Vec<f64>, Mat, Mat)> {
    let (n, k) = (pi.len(), q.len());
    if n == 0
        || k == 0
        || !square(sigma, n)
        || p.len() != k
        || p.iter().any(|r| r.len() != n)
        || !square(omega, k)
    {
        return fail(
            "E_INPUT",
            "covariance, prior, pick, views and view covariance disagree in size",
        );
    }
    if !(tau > 0.0) {
        return fail("E_DOMAIN", "tau must be positive");
    }
    let s = symmetric(sigma)?;
    cholesky(&s)?;
    let om = symmetric(omega)?;
    cholesky(&om)?;
    let ts: Mat = s
        .iter()
        .map(|r| r.iter().map(|v| tau * v).collect())
        .collect();
    // A = tau Sigma P' (N x K); M = P A + Omega (K x K).
    let a: Mat = (0..n)
        .map(|i| (0..k).map(|v| dot(&ts[i], &p[v])).collect())
        .collect();
    let m: Mat = (0..k)
        .map(|u| {
            (0..k)
                .map(|v| (0..n).map(|i| p[u][i] * a[i][v]).sum::<f64>() + om[u][v])
                .collect()
        })
        .collect();
    let l = cholesky(&m)?;
    let resid: Vec<f64> = (0..k).map(|v| q[v] - dot(&p[v], pi)).collect();
    let g = chol_solve(&l, &resid);
    let post: Vec<f64> = (0..n).map(|i| pi[i] + dot(&a[i], &g)).collect();
    // X = M^-1 A' (K x N), one column per asset.
    let x: Vec<Vec<f64>> = (0..n).map(|j| chol_solve(&l, &a[j])).collect();
    let pc: Mat = (0..n)
        .map(|i| (0..n).map(|j| ts[i][j] - dot(&a[i], &x[j])).collect())
        .collect();
    let pred = (0..n)
        .map(|i| (0..n).map(|j| s[i][j] + pc[i][j]).collect())
        .collect();
    Ok((post, pc, pred))
}

/// Acerbi-Szekely Z2 with positive losses (J-W2-10): `(z2, exceptions, T alpha)`.
pub fn es_z2(losses: &[f64], var: &[f64], es: &[f64], alpha: f64) -> Result<(f64, i64, f64)> {
    let t = losses.len();
    if t == 0 || var.len() != t || es.len() != t {
        return fail(
            "E_INPUT",
            "losses, var and es must have the same non-zero length",
        );
    }
    if !(alpha > 0.0 && alpha < 1.0) {
        return fail("E_DOMAIN", "alpha must lie in (0, 1)");
    }
    if es.iter().any(|&e| !(e > 0.0)) {
        return fail("E_DOMAIN", "es must be positive");
    }
    let ta = t as f64 * alpha;
    let (mut sum, mut count) = (0.0, 0_i64);
    for i in 0..t {
        if losses[i] > var[i] {
            sum += losses[i] / (ta * es[i]);
            count += 1;
        }
    }
    Ok((1.0 - sum, count, ta))
}

#[derive(Clone, Debug, PartialEq)]
pub struct Hmm {
    pub initial: Vec<f64>,
    pub transition: Mat,
    pub means: Vec<f64>,
    pub sds: Vec<f64>,
}

pub struct BaumWelch {
    pub params: Hmm,
    pub log_likelihood: f64,
    pub iterations: i64,
    pub converged: bool,
}

struct EStep {
    gamma: Mat,
    xi_sum: Mat,
    loglik: f64,
}

fn e_step(y: &[f64], h: &Hmm) -> Result<EStep> {
    let (t, k) = (y.len(), h.initial.len());
    let norm = (2.0 * std::f64::consts::PI).sqrt();
    let b: Mat = y
        .iter()
        .map(|&v| {
            (0..k)
                .map(|j| {
                    let z = (v - h.means[j]) / h.sds[j];
                    (-0.5 * z * z).exp() / (h.sds[j] * norm)
                })
                .collect()
        })
        .collect();
    let mut a = vec![vec![0.0; k]; t];
    let mut c = vec![0.0; t];
    for s in 0..t {
        for j in 0..k {
            let prior = if s == 0 {
                h.initial[j]
            } else {
                (0..k).map(|i| a[s - 1][i] * h.transition[i][j]).sum()
            };
            a[s][j] = prior * b[s][j];
        }
        c[s] = a[s].iter().sum();
        if !(c[s] > 0.0) {
            return fail(
                "E_DOMAIN",
                "an observation has zero density under every state",
            );
        }
        for j in 0..k {
            a[s][j] /= c[s];
        }
    }
    let mut beta = vec![vec![1.0; k]; t];
    for s in (0..t - 1).rev() {
        for i in 0..k {
            beta[s][i] = (0..k)
                .map(|j| h.transition[i][j] * b[s + 1][j] * beta[s + 1][j])
                .sum::<f64>()
                / c[s + 1];
        }
    }
    let gamma: Mat = (0..t)
        .map(|s| (0..k).map(|i| a[s][i] * beta[s][i]).collect())
        .collect();
    let mut xi_sum = vec![vec![0.0; k]; k];
    for s in 0..t - 1 {
        for i in 0..k {
            for j in 0..k {
                xi_sum[i][j] +=
                    a[s][i] * h.transition[i][j] * b[s + 1][j] * beta[s + 1][j] / c[s + 1];
            }
        }
    }
    let loglik = c.iter().map(|v| v.ln()).sum();
    Ok(EStep {
        gamma,
        xi_sum,
        loglik,
    })
}

fn m_step(y: &[f64], e: &EStep) -> Result<Hmm> {
    let (t, k) = (y.len(), e.gamma[0].len());
    let initial = e.gamma[0].clone();
    let mut transition = vec![vec![0.0; k]; k];
    for i in 0..k {
        let den: f64 = (0..t - 1).map(|s| e.gamma[s][i]).sum();
        if den == 0.0 {
            return fail(
                "E_DOMAIN",
                "a state has zero weight in the transition update",
            );
        }
        for j in 0..k {
            transition[i][j] = e.xi_sum[i][j] / den;
        }
    }
    let (mut means, mut sds) = (vec![0.0; k], vec![0.0; k]);
    for i in 0..k {
        let w: f64 = (0..t).map(|s| e.gamma[s][i]).sum();
        let m = (0..t).map(|s| e.gamma[s][i] * y[s]).sum::<f64>() / w;
        let v = (0..t)
            .map(|s| e.gamma[s][i] * (y[s] - m) * (y[s] - m))
            .sum::<f64>()
            / w;
        if !(v > 0.0) {
            return fail("E_DOMAIN", "a variance update is not positive");
        }
        means[i] = m;
        sds[i] = v.sqrt();
    }
    Ok(Hmm {
        initial,
        transition,
        means,
        sds,
    })
}

/// Baum-Welch for a Gaussian HMM, iteration as rulings J-W2-11 and J-W2-13.
pub fn baum_welch(y: &[f64], start: Hmm, tolerance: f64, max_iterations: i64) -> Result<BaumWelch> {
    let k = start.initial.len();
    if k < 1
        || y.len() < 2
        || max_iterations < 1
        || !square(&start.transition, k)
        || start.means.len() != k
        || start.sds.len() != k
    {
        return fail(
            "E_INPUT",
            "observations, initial, transition, means and sds disagree in size",
        );
    }
    let row_ok =
        |r: &[f64]| r.iter().all(|&p| p >= 0.0) && (r.iter().sum::<f64>() - 1.0).abs() <= 1e-9;
    if !row_ok(&start.initial) || !start.transition.iter().all(|r| row_ok(r)) {
        return fail(
            "E_DOMAIN",
            "initial and transition rows must be probabilities",
        );
    }
    if start.sds.iter().any(|&s| !(s > 0.0)) || !(tolerance > 0.0) {
        return fail("E_DOMAIN", "sds and tolerance must be positive");
    }
    let mut h = start;
    let mut e = e_step(y, &h)?;
    let mut k_iter = 0;
    loop {
        k_iter += 1;
        let next = m_step(y, &e)?;
        let e2 = e_step(y, &next)?;
        let gain = e2.loglik - e.loglik;
        h = next;
        e = e2;
        if gain < tolerance || k_iter >= max_iterations {
            return Ok(BaumWelch {
                params: h,
                log_likelihood: e.loglik,
                iterations: k_iter,
                converged: gain < tolerance,
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Lcg(u64);
    impl Lcg {
        fn next(&mut self) -> f64 {
            self.0 = self
                .0
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1_442_695_040_888_963_407);
            (self.0 >> 11) as f64 / (1u64 << 53) as f64
        }
        fn normal(&mut self) -> f64 {
            let (u, v) = (self.next().max(1e-300), self.next());
            (-2.0 * u.ln()).sqrt() * (2.0 * std::f64::consts::PI * v).cos()
        }
    }

    fn random_cov(g: &mut Lcg, n: usize) -> Mat {
        let f: Mat = (0..n)
            .map(|_| (0..n + 2).map(|_| g.normal() * 0.1).collect())
            .collect();
        (0..n)
            .map(|i| {
                (0..n)
                    .map(|j| dot(&f[i], &f[j]) + if i == j { 0.01 } else { 0.0 })
                    .collect()
            })
            .collect()
    }

    #[test]
    fn mean_variance_kkt_closed_form_and_monotone_bounds() {
        let mut g = Lcg(7);
        for n in 1..7 {
            let s = random_cov(&mut g, n);
            let mu: Vec<f64> = (0..n).map(|_| 0.05 + 0.05 * g.normal()).collect();
            // Wide bounds: closed form w = Sigma^-1 (mu - nu 1)/gamma.
            let (lo, hi) = (vec![-100.0; n], vec![100.0; n]);
            let r = mean_variance(&mu, &s, 3.0, Some(&lo), Some(&hi)).unwrap();
            let l = cholesky(&s).unwrap();
            let (a, z) = (chol_solve(&l, &mu), chol_solve(&l, &vec![1.0; n]));
            let nu = (a.iter().sum::<f64>() - 3.0) / z.iter().sum::<f64>();
            for i in 0..n {
                assert!((r.weights[i] - (a[i] - nu * z[i]) / 3.0).abs() < 1e-9);
            }
            // Long-only: KKT residual.
            let r = mean_variance(&mu, &s, 3.0, None, None).unwrap();
            let sw = mul(&s, &r.weights);
            let g_: Vec<f64> = (0..n).map(|i| mu[i] - 3.0 * sw[i]).collect();
            let free: Vec<usize> = (0..n).filter(|&i| r.at_bound[i] == 0).collect();
            let nu = free.first().map_or(0.0, |&i| g_[i]);
            for i in (0..n).filter(|_| !free.is_empty()) {
                let gi = g_[i] - nu;
                match r.at_bound[i] {
                    0 => assert!(gi.abs() < 1e-9),
                    -1 => assert!(gi < 1e-9),
                    _ => assert!(gi > -1e-9),
                }
            }
            assert!((r.weights.iter().sum::<f64>() - 1.0).abs() < 1e-12);
            // Loosening a binding upper bound never lowers the objective.
            let hi = vec![0.5; n];
            if n >= 2 {
                let tight = mean_variance(&mu, &s, 3.0, None, Some(&hi)).unwrap();
                let loose = mean_variance(&mu, &s, 3.0, None, Some(&vec![0.8; n])).unwrap();
                assert!(loose.objective >= tight.objective - 1e-15);
            }
        }
    }

    #[test]
    fn risk_parity_shares_and_euler_sum() {
        let mut g = Lcg(11);
        for n in 1..8 {
            let s = random_cov(&mut g, n);
            let raw: Vec<f64> = (0..n).map(|_| 0.1 + g.next()).collect();
            let t: f64 = raw.iter().sum();
            let b: Vec<f64> = raw.iter().map(|v| v / t).collect();
            if (b.iter().sum::<f64>() - 1.0).abs() > 1e-12 {
                continue;
            }
            let (w, vol, c) = risk_parity(&s, Some(&b)).unwrap();
            for i in 0..n {
                assert!((c[i] / vol - b[i]).abs() < 1e-10);
            }
            let s2: Mat = s
                .iter()
                .map(|r| r.iter().map(|v| 4.0 * v).collect())
                .collect();
            let (w2, _, _) = risk_parity(&s2, Some(&b)).unwrap();
            for i in 0..n {
                assert!((w[i] - w2[i]).abs() < 1e-12);
            }
            let wl: Vec<f64> = (0..n).map(|_| g.normal()).collect();
            let e = euler(&wl, &s).unwrap();
            let sum: f64 = e.contributions.iter().sum();
            assert!((sum - e.volatility).abs() < 1e-10 * e.volatility);
            let wc: Vec<f64> = wl.iter().map(|v| 2.5 * v).collect();
            let e2 = euler(&wc, &s).unwrap();
            for i in 0..n {
                assert!((e2.contributions[i] - 2.5 * e.contributions[i]).abs() < 1e-12);
            }
        }
    }

    #[test]
    fn ledoit_wolf_and_black_litterman_properties() {
        let mut g = Lcg(5);
        for n in 1..6 {
            let x: Mat = (0..30)
                .map(|_| (0..n).map(|_| g.normal()).collect())
                .collect();
            let (c, d, _) = ledoit_wolf(&x).unwrap();
            assert!((0.0..=1.0).contains(&d));
            let shifted: Mat = x
                .iter()
                .map(|r| r.iter().map(|v| v + 3.0).collect())
                .collect();
            let (c2, d2, _) = ledoit_wolf(&shifted).unwrap();
            assert!((d - d2).abs() < 1e-9);
            assert!((c[0][0] - c2[0][0]).abs() < 1e-9);
            // Black-Litterman: update form equals precision form; huge Omega gives the prior.
            let s = random_cov(&mut g, n);
            let pi: Vec<f64> = (0..n).map(|_| 0.05 * g.normal()).collect();
            let p: Mat = (0..2)
                .map(|_| (0..n).map(|_| g.normal()).collect())
                .collect();
            let q = vec![0.03, -0.01];
            let om = vec![vec![0.002, 0.0005], vec![0.0005, 0.003]];
            let (post, pc, _) = black_litterman(&s, &pi, &p, &q, &om, 0.05).unwrap();
            // Precision form check: (tau S)^-1 pc + P' Om^-1 P pc = I.
            let ts: Mat = s
                .iter()
                .map(|r| r.iter().map(|v| 0.05 * v).collect())
                .collect();
            let lt = cholesky(&ts).unwrap();
            let lo = cholesky(&om).unwrap();
            let mut prec = vec![vec![0.0; n]; n];
            for j in 0..n {
                let e: Vec<f64> = (0..n).map(|i| if i == j { 1.0 } else { 0.0 }).collect();
                let col = chol_solve(&lt, &e);
                for i in 0..n {
                    prec[i][j] = col[i];
                }
            }
            for i in 0..n {
                for j in 0..n {
                    let oi = chol_solve(&lo, &[p[0][j], p[1][j]]);
                    prec[i][j] += p[0][i] * oi[0] + p[1][i] * oi[1];
                }
            }
            let oq = chol_solve(&lo, &q);
            let rhs: Vec<f64> = (0..n)
                .map(|i| chol_solve(&lt, &pi)[i] + p[0][i] * oq[0] + p[1][i] * oq[1])
                .collect();
            let lp = cholesky(&prec).unwrap();
            let alt = chol_solve(&lp, &rhs);
            for i in 0..n {
                assert!((alt[i] - post[i]).abs() < 1e-10);
                let unit = chol_solve(
                    &lp,
                    &(0..n)
                        .map(|j| if j == i { 1.0 } else { 0.0 })
                        .collect::<Vec<_>>(),
                );
                assert!((unit[i] - pc[i][i]).abs() < 1e-10);
            }
            let big: Mat = om
                .iter()
                .map(|r| r.iter().map(|v| v * 1e12).collect())
                .collect();
            let (prior, _, _) = black_litterman(&s, &pi, &p, &q, &big, 0.05).unwrap();
            for i in 0..n {
                assert!((prior[i] - pi[i]).abs() < 1e-9);
            }
        }
    }

    #[test]
    fn z2_properties() {
        let l = [1.0, 3.0, 0.5, 4.0];
        assert_eq!(es_z2(&l, &[9.0; 4], &[10.0; 4], 0.1).unwrap().0, 1.0);
        let a = es_z2(&l, &[2.0; 4], &[2.5; 4], 0.25).unwrap().0;
        let ls: Vec<f64> = l.iter().map(|v| v * 8.0).collect();
        let b = es_z2(&ls, &[16.0; 4], &[20.0; 4], 0.25).unwrap().0;
        assert!((a - b).abs() < 1e-15 && (a + 1.8).abs() < 1e-15);
        assert!(es_z2(&l, &[2.0; 4], &[3.0; 4], 0.25).unwrap().0 > a);
    }

    fn hmm2() -> Hmm {
        Hmm {
            initial: vec![0.6, 0.4],
            transition: vec![vec![0.9, 0.1], vec![0.2, 0.8]],
            means: vec![-0.5, 1.0],
            sds: vec![0.7, 1.3],
        }
    }

    #[test]
    fn baum_welch_properties() {
        let mut g = Lcg(3);
        let y: Vec<f64> = (0..200)
            .map(|i| {
                if (i / 25) % 2 == 0 {
                    g.normal() * 0.6 - 0.4
                } else {
                    g.normal() * 1.2 + 1.1
                }
            })
            .collect();
        // Monotone likelihood.
        let mut prev = e_step(&y, &hmm2()).unwrap().loglik;
        for it in 1..30 {
            let r = baum_welch(&y, hmm2(), 1e-300, it).unwrap();
            assert!(r.log_likelihood >= prev - 1e-9 * prev.abs());
            prev = r.log_likelihood;
        }
        // Bit reproducible.
        let (a, b) = (
            baum_welch(&y, hmm2(), 1e-8, 500).unwrap(),
            baum_welch(&y, hmm2(), 1e-8, 500).unwrap(),
        );
        assert_eq!(a.params, b.params);
        assert_eq!(a.log_likelihood.to_bits(), b.log_likelihood.to_bits());
        // Permutation equivariance.
        let h = hmm2();
        let swapped = Hmm {
            initial: vec![h.initial[1], h.initial[0]],
            transition: vec![
                vec![h.transition[1][1], h.transition[1][0]],
                vec![h.transition[0][1], h.transition[0][0]],
            ],
            means: vec![h.means[1], h.means[0]],
            sds: vec![h.sds[1], h.sds[0]],
        };
        let c = baum_welch(&y, swapped, 1e-8, 500).unwrap();
        assert_eq!(a.iterations, c.iterations);
        assert!((a.params.means[0] - c.params.means[1]).abs() < 1e-9);
        assert!((a.params.sds[1] - c.params.sds[0]).abs() < 1e-9);
        // K = 1: sample mean and population sd, stop at iteration 2.
        let one = Hmm {
            initial: vec![1.0],
            transition: vec![vec![1.0]],
            means: vec![0.0],
            sds: vec![1.0],
        };
        let r = baum_welch(&y, one, 1e-10, 100).unwrap();
        let m = y.iter().sum::<f64>() / 200.0;
        let v = y.iter().map(|x| (x - m) * (x - m)).sum::<f64>() / 200.0;
        assert_eq!(r.iterations, 2);
        assert!(r.converged);
        assert!(
            (r.params.means[0] - m).abs() < 1e-12 && (r.params.sds[0] - v.sqrt()).abs() < 1e-12
        );
    }

    #[test]
    fn j_w2_19_default_budgets_are_not_sum_tested() {
        let s: Mat = (0..7)
            .map(|i| (0..7).map(|j| if i == j { 1.0 } else { 0.1 }).collect())
            .collect();
        let (w, _, _) = risk_parity(&s, None).unwrap();
        assert!(w.iter().all(|x| (x - 1.0 / 7.0).abs() < 1e-10));
    }

    #[test]
    fn j_w2_20_all_weights_at_bound_start() {
        let s = vec![
            vec![0.04, 0.01, 0.0],
            vec![0.01, 0.09, 0.02],
            vec![0.0, 0.02, 0.16],
        ];
        let r = mean_variance(&[0.3, 0.1, 0.2], &s, 2.0, Some(&[0.2, 0.3, 0.5]), None).unwrap();
        assert_eq!(r.weights, vec![0.2, 0.3, 0.5]);
        assert_eq!(r.at_bound, vec![-1, -1, -1]);
    }

    #[test]
    fn j_w2_21_degenerate_problem_terminates() {
        let eye2 = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let r = mean_variance(&[0.1, 0.1], &eye2, 1.0, None, Some(&[0.5, 0.5])).unwrap();
        assert_eq!(r.weights, vec![0.5, 0.5]);
        let eye3 = vec![
            vec![1.0, 0.0, 0.0],
            vec![0.0, 1.0, 0.0],
            vec![0.0, 0.0, 1.0],
        ];
        let r = mean_variance(
            &[0.1, 0.9, 0.1],
            &eye3,
            1.0,
            Some(&[0.0, 0.3, 0.0]),
            Some(&[1.0, 0.3, 1.0]),
        )
        .unwrap();
        assert_eq!((r.weights[1], r.at_bound[1]), (0.3, -1));
    }
}
