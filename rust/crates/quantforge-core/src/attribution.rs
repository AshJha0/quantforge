//! Use case 4, `usecase.factor_attribution` (`04-pricing/use-cases.md`): OLS with an intercept
//! by Householder QR.
use crate::error::{Result, fail};
use crate::linalg::singular_values;

#[derive(Debug, Clone)]
pub struct Attribution {
    pub alpha: f64,
    pub betas: Vec<f64>,
    pub contributions: Vec<f64>,
    pub mean_return: f64,
    pub r_squared: f64,
    pub residual_vol: f64,
    pub beta_se: Vec<f64>,
}

pub fn factor_attribution(y: &[f64], f: &[Vec<f64>], names: usize) -> Result<Attribution> {
    crate::error::finite("portfolio_returns", &y)?;
    crate::error::finite("factor_returns", &f)?;
    let t = y.len();
    if f.len() != t || f.is_empty() {
        return fail("E_INPUT", "factor_returns must have one row per return");
    }
    let k = f[0].len();
    if f.iter().any(|r| r.len() != k) || names != k || k == 0 {
        return fail("E_INPUT", "factor names and columns differ");
    }
    if t < k + 2 {
        return fail("E_INPUT", "need T >= K + 2");
    }
    let p = k + 1;
    let x: Vec<Vec<f64>> = f
        .iter()
        .map(|r| std::iter::once(1.0).chain(r.iter().copied()).collect())
        .collect();
    let sv = singular_values(&x);
    let (big, small) = sv
        .iter()
        .fold((0.0f64, f64::INFINITY), |(b, s), v| (b.max(*v), s.min(*v)));
    if small < 1e-12 * big {
        return fail("E_DOMAIN", "the factors are collinear");
    }
    // Householder QR of X (T x p), applied to y as well.
    let mut a = x.clone();
    let mut b = y.to_vec();
    for j in 0..p {
        let norm = (j..t).map(|i| a[i][j] * a[i][j]).sum::<f64>().sqrt();
        let alpha = if a[j][j] > 0.0 { -norm } else { norm };
        let mut v: Vec<f64> = (j..t).map(|i| a[i][j]).collect();
        v[0] -= alpha;
        let vv: f64 = v.iter().map(|z| z * z).sum();
        if vv == 0.0 {
            continue;
        }
        for c in j..p {
            let s: f64 = (j..t).map(|i| v[i - j] * a[i][c]).sum::<f64>() * 2.0 / vv;
            for i in j..t {
                a[i][c] -= s * v[i - j];
            }
        }
        let s: f64 = (j..t).map(|i| v[i - j] * b[i]).sum::<f64>() * 2.0 / vv;
        for i in j..t {
            b[i] -= s * v[i - j];
        }
    }
    // Back substitution R c = Q'y.
    let mut coef = vec![0.0; p];
    for i in (0..p).rev() {
        let s: f64 = (i + 1..p).map(|c| a[i][c] * coef[c]).sum();
        coef[i] = (b[i] - s) / a[i][i];
    }
    let ssr: f64 = b[p..].iter().map(|z| z * z).sum();
    let mean = y.iter().sum::<f64>() / t as f64;
    let sst: f64 = y.iter().map(|v| (v - mean) * (v - mean)).sum();
    let dof = (t - k - 1) as f64;
    let s2 = ssr / dof;
    // (X'X)^-1 = R^-1 R^-T; its diagonal is the row norms squared of R^-1.
    let mut rinv = vec![vec![0.0; p]; p];
    for c in 0..p {
        for i in (0..=c).rev() {
            let e = if i == c { 1.0 } else { 0.0 };
            let s: f64 = (i + 1..=c).map(|m| a[i][m] * rinv[m][c]).sum();
            rinv[i][c] = (e - s) / a[i][i];
        }
    }
    let diag: Vec<f64> = (0..p)
        .map(|i| rinv[i].iter().map(|v| v * v).sum())
        .collect();
    let fmeans: Vec<f64> = (0..k)
        .map(|j| f.iter().map(|r| r[j]).sum::<f64>() / t as f64)
        .collect();
    let betas = coef[1..].to_vec();
    Ok(Attribution {
        alpha: coef[0],
        contributions: betas.iter().zip(&fmeans).map(|(b, m)| b * m).collect(),
        betas,
        mean_return: mean,
        r_squared: 1.0 - ssr / sst,
        residual_vol: s2.sqrt(),
        beta_se: diag[1..].iter().map(|d| (s2 * d).sqrt()).collect(),
    })
}
