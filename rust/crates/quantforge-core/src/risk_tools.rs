//! `risk.curve.pca` and `risk.credit.jtd` (`book-sensitivities.md`).
use crate::error::{Result, fail};
use crate::linalg::eigen_pairs;

#[derive(Debug, Clone)]
pub struct Pca {
    pub eigenvalues: Vec<f64>,
    pub loadings: Vec<Vec<f64>>,
    pub explained_ratio: Vec<f64>,
}

/// `risk.curve.pca`: sample covariance (divisor `T - 1`) of demeaned columns, eigenvalues
/// descending, the first `k` loadings with their largest-absolute entry positive.
pub fn pca(changes: &[Vec<f64>], k: i64) -> Result<Pca> {
    crate::error::finite("changes", &changes)?;
    if k < 1 {
        return fail("E_DOMAIN", "components must be at least 1");
    }
    let t = changes.len();
    if t < 2 {
        return fail("E_INPUT", "at least two observations");
    }
    let n = changes[0].len();
    if n == 0 || changes.iter().any(|r| r.len() != n) {
        return fail("E_INPUT", "rows must all have the same length");
    }
    let k = k as usize;
    if k > n {
        return fail("E_INPUT", "components above the tenor count");
    }
    let means: Vec<f64> = (0..n)
        .map(|j| changes.iter().map(|r| r[j]).sum::<f64>() / t as f64)
        .collect();
    let mut cov = vec![vec![0.0; n]; n];
    for a in 0..n {
        for b in 0..=a {
            let s: f64 = changes
                .iter()
                .map(|r| (r[a] - means[a]) * (r[b] - means[b]))
                .sum::<f64>()
                / (t - 1) as f64;
            cov[a][b] = s;
            cov[b][a] = s;
        }
    }
    let (values, vectors) = eigen_pairs(&cov)?;
    let check = (k + 1).min(n);
    let tol = 1e-6 * values[0].abs();
    if (1..check).any(|i| (values[i - 1] - values[i]).abs() < tol) {
        return fail("E_DOMAIN", "repeated eigenvalue: loadings are not unique");
    }
    let total: f64 = values.iter().sum();
    let loadings = vectors[..k]
        .iter()
        .map(|v| {
            let mut big = 0;
            for (i, x) in v.iter().enumerate() {
                if x.abs() > v[big].abs() {
                    big = i;
                }
            }
            let s = if v[big] < 0.0 { -1.0 } else { 1.0 };
            v.iter().map(|x| s * x).collect()
        })
        .collect();
    Ok(Pca {
        explained_ratio: values[..k].iter().map(|l| l / total).collect(),
        eigenvalues: values,
        loadings,
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum JtdKind {
    Bond,
    ProtectionBuyer,
    ProtectionSeller,
}

#[derive(Debug, Clone)]
pub struct JtdPosition {
    pub kind: JtdKind,
    pub notional: f64,
    pub recovery: f64,
    pub market_value: f64,
}

/// `risk.credit.jtd`: `(jtd per position, total)`.
pub fn jtd(positions: &[JtdPosition]) -> Result<(Vec<f64>, f64)> {
    for p in positions {
        crate::error::finite("notional", &p.notional)?;
        crate::error::finite("recovery", &p.recovery)?;
        crate::error::finite("market_value", &p.market_value)?;
    }
    if positions.is_empty() {
        return fail("E_INPUT", "no positions");
    }
    if positions
        .iter()
        .any(|p| p.notional < 0.0 || !(0.0..=1.0).contains(&p.recovery))
    {
        return fail(
            "E_DOMAIN",
            "notional must not be negative and recovery in [0, 1]",
        );
    }
    let v: Vec<f64> = positions
        .iter()
        .map(|p| {
            let after = match p.kind {
                JtdKind::Bond => p.recovery * p.notional,
                JtdKind::ProtectionBuyer => (1.0 - p.recovery) * p.notional,
                JtdKind::ProtectionSeller => -(1.0 - p.recovery) * p.notional,
            };
            after - p.market_value
        })
        .collect();
    let total = v.iter().sum();
    Ok((v, total))
}
