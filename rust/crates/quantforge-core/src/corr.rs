//! Correlation: validation, nearest correlation matrix, implied correlation, dispersion
//! (`06-risk/correlation.md`, rulings E-B18 to E-B21).
use crate::error::{Result, fail};
use crate::linalg::Matrix;

fn square(m: &Matrix) -> Result<usize> {
    let n = m.len();
    if n == 0 || m.iter().any(|r| r.len() != n) {
        return fail("E_INPUT", "matrix must be square and non-empty");
    }
    Ok(n)
}

/// Cyclic Jacobi eigen-decomposition of a symmetric matrix: `(values, vectors as columns)`.
pub fn jacobi(a: &Matrix) -> (Vec<f64>, Matrix) {
    let n = a.len();
    let mut a = a.clone();
    let mut v: Matrix = (0..n)
        .map(|i| (0..n).map(|j| if i == j { 1.0 } else { 0.0 }).collect())
        .collect();
    for _ in 0..100 {
        let off: f64 = (0..n)
            .flat_map(|i| (0..n).filter(move |&j| j != i).map(move |j| (i, j)))
            .map(|(i, j)| a[i][j] * a[i][j])
            .sum();
        let scale: f64 = a.iter().flatten().map(|x| x * x).sum();
        if off <= 1e-32 * scale || off == 0.0 {
            break;
        }
        for p in 0..n {
            for q in p + 1..n {
                if a[p][q] == 0.0 {
                    continue;
                }
                let theta = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
                let t = theta.signum() / (theta.abs() + (theta * theta + 1.0).sqrt());
                let t = if theta == 0.0 { 1.0 } else { t };
                let (c, s) = (1.0 / (t * t + 1.0).sqrt(), t / (t * t + 1.0).sqrt());
                for k in 0..n {
                    let (akp, akq) = (a[k][p], a[k][q]);
                    a[k][p] = c * akp - s * akq;
                    a[k][q] = s * akp + c * akq;
                }
                for k in 0..n {
                    let (apk, aqk) = (a[p][k], a[q][k]);
                    a[p][k] = c * apk - s * aqk;
                    a[q][k] = s * apk + c * aqk;
                }
                for row in &mut v {
                    let (vp, vq) = (row[p], row[q]);
                    row[p] = c * vp - s * vq;
                    row[q] = s * vp + c * vq;
                }
            }
        }
    }
    ((0..n).map(|i| a[i][i]).collect(), v)
}

// One field per output flag of the contract.
#[allow(clippy::struct_excessive_bools)]
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Validation {
    pub symmetric: bool,
    pub unit_diagonal: bool,
    pub in_range: bool,
    pub min_eigenvalue: f64,
    pub psd: bool,
}

impl Validation {
    pub fn valid(&self) -> bool {
        self.symmetric && self.unit_diagonal && self.in_range && self.psd
    }
}

fn symmetric(m: &Matrix) -> bool {
    (0..m.len()).all(|i| (0..i).all(|j| m[i][j] == m[j][i]))
}

/// Exact comparisons on the given numbers; `psd` is `min_eigenvalue >= -1e-10` (ruling E-B19).
pub fn validate(m: &Matrix) -> Result<Validation> {
    let n = square(m)?;
    let sym: Matrix = (0..n)
        .map(|i| (0..n).map(|j| (m[i][j] + m[j][i]) / 2.0).collect())
        .collect();
    let min = jacobi(&sym).0.into_iter().fold(f64::INFINITY, f64::min);
    Ok(Validation {
        symmetric: symmetric(m),
        unit_diagonal: (0..n).all(|i| m[i][i] == 1.0),
        in_range: m.iter().flatten().all(|x| (-1.0..=1.0).contains(x)),
        min_eigenvalue: min,
        psd: min >= -1e-10,
    })
}

/// `V max(w, 0) V^T`.
fn psd_projection(r: &Matrix) -> Matrix {
    let n = r.len();
    let (w, v) = jacobi(r);
    (0..n)
        .map(|i| {
            (0..n)
                .map(|j| (0..n).map(|k| v[i][k] * w[k].max(0.0) * v[j][k]).sum())
                .collect()
        })
        .collect()
}

/// Higham's alternating projections with Dykstra's correction (ruling E-B18).
/// Returns the nearest correlation matrix and its Frobenius distance from `m`.
pub fn nearest(m: &Matrix) -> Result<(Matrix, f64)> {
    let n = square(m)?;
    if !symmetric(m) {
        return fail("E_INPUT", "nearest needs a symmetric matrix");
    }
    let mut y = m.clone();
    let mut ds = vec![vec![0.0; n]; n];
    let mut converged = false;
    for _ in 0..100_000 {
        let r: Matrix = (0..n)
            .map(|i| (0..n).map(|j| y[i][j] - ds[i][j]).collect())
            .collect();
        let mut x = psd_projection(&r);
        // Keep the iterate exactly symmetric.
        for i in 0..n {
            for j in 0..i {
                let s = (x[i][j] + x[j][i]) / 2.0;
                x[i][j] = s;
                x[j][i] = s;
            }
        }
        for i in 0..n {
            for j in 0..n {
                ds[i][j] = x[i][j] - r[i][j];
            }
        }
        let mut next = x;
        for (i, row) in next.iter_mut().enumerate() {
            row[i] = 1.0;
        }
        let change = (0..n)
            .flat_map(|i| (0..n).map(move |j| (i, j)))
            .map(|(i, j)| (next[i][j] - y[i][j]).abs())
            .fold(0.0, f64::max);
        y = next;
        if change <= 1e-13 {
            converged = true;
            break;
        }
    }
    if !converged {
        return fail(
            "E_NO_CONVERGENCE",
            "alternating projections did not converge",
        );
    }
    let dist = (0..n)
        .flat_map(|i| (0..n).map(move |j| (i, j)))
        .map(|(i, j)| (y[i][j] - m[i][j]).powi(2))
        .sum::<f64>()
        .sqrt();
    Ok((y, dist))
}

fn implied_unchecked(w: &[f64], v: &[f64], index: f64) -> f64 {
    let own: f64 = w.iter().zip(v).map(|(a, b)| a * a * b * b).sum();
    let total: f64 = w.iter().zip(v).map(|(a, b)| a * b).sum();
    // sum over i != j of w_i w_j s_i s_j, each pair twice.
    (index * index - own) / (total * total - own)
}

/// Average correlation, not clipped (ruling E-B20).
pub fn implied(weights: &[f64], vols: &[f64], index_vol: f64) -> Result<f64> {
    if weights.len() < 2 || weights.len() != vols.len() {
        return fail("E_INPUT", "at least two names, one vol each");
    }
    if vols.iter().any(|v| v.is_nan() || *v <= 0.0) || index_vol.is_nan() || index_vol <= 0.0 {
        return fail("E_DOMAIN", "vols must be above 0");
    }
    // Ruling E-B33: weights >= 0 with at least two positive; a zero weight drops its name.
    if weights.iter().any(|w| w.is_nan() || *w < 0.0)
        || weights.iter().filter(|w| **w > 0.0).count() < 2
    {
        return fail(
            "E_DOMAIN",
            "weights must be at least 0 with two or more positive",
        );
    }
    Ok(implied_unchecked(weights, vols, index_vol))
}

pub struct Dispersion<'a> {
    pub weights: &'a [f64],
    pub vol_strikes: &'a [f64],
    pub index_vol_strike: f64,
    pub realized_vols: &'a [f64],
    pub index_realized_vol: f64,
    pub vega_notional: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DispersionOut {
    pub pnl: f64,
    pub implied_correlation: f64,
    pub realized_correlation: f64,
    pub constituent_variance_notionals: Vec<f64>,
    pub index_variance_notional: f64,
}

/// Variance notionals `N w_i / (2 K_i)` long and `N / (2 K_I)` short (ruling E-B21).
pub fn dispersion(x: &Dispersion) -> Result<DispersionOut> {
    let n = x.weights.len();
    if n < 2 || x.vol_strikes.len() != n || x.realized_vols.len() != n {
        return fail(
            "E_INPUT",
            "at least two names, one strike and one realised vol each",
        );
    }
    let pos = |v: f64| v > 0.0;
    let scalars = [x.index_vol_strike, x.index_realized_vol];
    if !x
        .vol_strikes
        .iter()
        .chain(x.realized_vols)
        .chain(&scalars)
        .all(|&v| pos(v))
    {
        return fail("E_DOMAIN", "strikes and realised vols must be above 0");
    }
    let nv = x.vega_notional;
    let legs: Vec<f64> = x
        .weights
        .iter()
        .zip(x.vol_strikes)
        .map(|(w, k)| nv * w / (2.0 * k))
        .collect();
    let ni = nv / (2.0 * x.index_vol_strike);
    let long: f64 = legs
        .iter()
        .zip(x.realized_vols.iter().zip(x.vol_strikes))
        .map(|(l, (s, k))| l * (s * s - k * k))
        .sum();
    let (si, ki) = (x.index_realized_vol, x.index_vol_strike);
    Ok(DispersionOut {
        pnl: long - ni * (si * si - ki * ki),
        implied_correlation: implied_unchecked(x.weights, x.vol_strikes, ki),
        realized_correlation: implied_unchecked(x.weights, x.realized_vols, si),
        constituent_variance_notionals: legs,
        index_variance_notional: ni,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn higham() -> Matrix {
        vec![
            vec![1.0, 1.0, 0.0],
            vec![1.0, 1.0, 1.0],
            vec![0.0, 1.0, 1.0],
        ]
    }

    #[test]
    fn jacobi_reconstructs() {
        let a = vec![
            vec![4.0, 1.0, 0.5],
            vec![1.0, 3.0, -0.2],
            vec![0.5, -0.2, 2.0],
        ];
        let (w, v) = jacobi(&a);
        for i in 0..3 {
            for j in 0..3 {
                let back: f64 = (0..3).map(|k| v[i][k] * w[k] * v[j][k]).sum();
                assert!((back - a[i][j]).abs() < 1e-12);
            }
        }
        assert_eq!(jacobi(&vec![vec![2.0]]).0, vec![2.0]);
    }

    #[test]
    fn validate_higham_example() {
        let v = validate(&higham()).unwrap();
        assert!((v.min_eigenvalue - (1.0 - 2f64.sqrt())).abs() < 1e-14);
        assert!(v.symmetric && v.unit_diagonal && v.in_range && !v.psd && !v.valid());
        let bad = validate(&vec![vec![1.0, 0.5], vec![0.4, 2.0]]).unwrap();
        assert!(!bad.symmetric && !bad.unit_diagonal && !bad.in_range);
        assert!(
            validate(&vec![vec![1.0, 0.3], vec![0.3, 1.0]])
                .unwrap()
                .valid()
        );
        assert_eq!(validate(&Vec::new()).unwrap_err().code, "E_INPUT");
        assert_eq!(validate(&vec![vec![1.0, 0.0]]).unwrap_err().code, "E_INPUT");
    }

    #[test]
    fn nearest_matches_higham() {
        let (x, d) = nearest(&higham()).unwrap();
        assert!((x[0][1] - 0.7606898534022837).abs() < 1e-9);
        assert!((x[0][2] - 0.15729810613837608).abs() < 1e-9);
        assert!((d - 0.5277904635818285).abs() < 1e-9);
        let ok = vec![vec![1.0, 0.3], vec![0.3, 1.0]];
        let (y, d) = nearest(&ok).unwrap();
        assert!(d < 1e-12 && (y[0][1] - 0.3).abs() < 1e-12);
        assert_eq!(
            nearest(&vec![vec![1.0, 0.3], vec![0.2, 1.0]])
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        assert_eq!(nearest(&vec![vec![5.0]]).unwrap().0, vec![vec![1.0]]);
    }

    #[test]
    fn implied_and_dispersion_examples() {
        assert!((implied(&[0.5, 0.5], &[0.2, 0.3], 0.22).unwrap() - 0.53).abs() < 1e-12);
        assert_eq!(implied(&[1.0], &[0.2], 0.2).unwrap_err().code, "E_INPUT");
        assert_eq!(
            implied(&[0.5, 0.5], &[0.2, 0.0], 0.2).unwrap_err().code,
            "E_DOMAIN"
        );
        assert!(implied(&[0.5, 0.5], &[0.2, 0.3], 0.4).unwrap() > 1.0);
        assert_eq!(
            implied(&[1.0, 0.0], &[0.2, 0.3], 0.2).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            implied(&[0.6, -0.4], &[0.2, 0.3], 0.2).unwrap_err().code,
            "E_DOMAIN"
        );
        let three = implied(&[0.5, 0.5, 0.0], &[0.2, 0.3, 0.9], 0.22).unwrap();
        assert!((three - 0.53).abs() < 1e-12);
        let x = Dispersion {
            weights: &[0.5, 0.5],
            vol_strikes: &[0.25, 0.3],
            index_vol_strike: 0.24,
            realized_vols: &[0.28, 0.35],
            index_realized_vol: 0.22,
            vega_notional: 100_000.0,
        };
        let o = dispersion(&x).unwrap();
        assert!((o.pnl - 6215.0).abs() < 1e-8);
        assert!((o.index_variance_notional - 208_333.333_333_333_34).abs() < 1e-6);
        assert!((o.realized_correlation + 0.03724489795918366).abs() < 1e-12);
        let short = Dispersion {
            vol_strikes: &[0.25],
            ..x
        };
        assert_eq!(dispersion(&short).unwrap_err().code, "E_INPUT");
        let zero = Dispersion {
            index_realized_vol: 0.0,
            ..x
        };
        assert_eq!(dispersion(&zero).unwrap_err().code, "E_DOMAIN");
    }
}
