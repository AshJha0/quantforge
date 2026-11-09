//! Dense linear algebra (`differentiation-and-linalg.md`).
use crate::error::{Result, fail};

pub type Matrix = Vec<Vec<f64>>;

fn check_square(a: &Matrix) -> Result<usize> {
    let n = a.len();
    if n == 0 || a.iter().any(|r| r.len() != n) {
        return fail("E_INPUT", "matrix must be square");
    }
    Ok(n)
}

fn largest(a: &Matrix) -> f64 {
    a.iter().flatten().fold(0.0, |m: f64, v| m.max(v.abs()))
}

fn check_symmetric(a: &Matrix) -> Result<usize> {
    let n = check_square(a)?;
    let limit = 1e-12 * largest(a);
    for i in 0..n {
        for j in 0..i {
            if (a[i][j] - a[j][i]).abs() > limit {
                return fail("E_INPUT", "matrix is not symmetric");
            }
        }
    }
    Ok(n)
}

/// LU with partial pivoting.
pub fn solve(a: &Matrix, b: &[f64]) -> Result<Vec<f64>> {
    crate::error::finite("b", &b)?;
    let n = check_square(a)?;
    if b.len() != n {
        return fail("E_INPUT", "vector length differs from the matrix");
    }
    let limit = 1e-14 * largest(a);
    let mut m = a.clone();
    let mut x = b.to_vec();
    for k in 0..n {
        let mut p = k;
        for i in k + 1..n {
            if m[i][k].abs() > m[p][k].abs() {
                p = i;
            }
        }
        if m[p][k].abs() <= limit {
            return fail("E_SINGULAR", "matrix is singular to working precision");
        }
        m.swap(k, p);
        x.swap(k, p);
        for i in k + 1..n {
            let factor = m[i][k] / m[k][k];
            for j in k..n {
                m[i][j] -= factor * m[k][j];
            }
            x[i] -= factor * x[k];
        }
    }
    for i in (0..n).rev() {
        let mut s = x[i];
        for j in i + 1..n {
            s -= m[i][j] * x[j];
        }
        x[i] = s / m[i][i];
    }
    Ok(x)
}

pub fn cholesky(a: &Matrix) -> Result<Matrix> {
    let n = check_symmetric(a)?;
    let mut l = vec![vec![0.0; n]; n];
    for i in 0..n {
        for j in 0..=i {
            let mut s = a[i][j];
            for k in 0..j {
                s -= l[i][k] * l[j][k];
            }
            if i == j {
                if s <= 0.0 {
                    return fail("E_NOT_POSITIVE_DEFINITE", "non-positive pivot");
                }
                l[i][i] = s.sqrt();
            } else {
                l[i][j] = s / l[j][j];
            }
        }
    }
    Ok(l)
}

/// Eigenvalues by cyclic Jacobi rotations, ascending.
pub fn eigen_symmetric(a: &Matrix) -> Result<Vec<f64>> {
    let n = check_symmetric(a)?;
    let mut m = a.clone();
    for i in 0..n {
        for j in 0..i {
            let v = (m[i][j] + m[j][i]) / 2.0;
            m[i][j] = v;
            m[j][i] = v;
        }
    }
    for _ in 0..100 {
        let off: f64 = (0..n)
            .flat_map(|i| (0..i).map(move |j| (i, j)))
            .map(|(i, j)| m[i][j] * m[i][j])
            .sum();
        if off == 0.0 {
            break;
        }
        for p in 0..n {
            for q in p + 1..n {
                if m[p][q] == 0.0 {
                    continue;
                }
                let theta = (m[q][q] - m[p][p]) / (2.0 * m[p][q]);
                let sign = if theta < 0.0 { -1.0 } else { 1.0 };
                let t = if theta.abs() > 1e150 {
                    0.5 / theta
                } else {
                    sign / (theta.abs() + (theta * theta + 1.0).sqrt())
                };
                let c = 1.0 / (t * t + 1.0).sqrt();
                let s = t * c;
                for k in 0..n {
                    let (kp, kq) = (m[k][p], m[k][q]);
                    m[k][p] = c * kp - s * kq;
                    m[k][q] = s * kp + c * kq;
                }
                for k in 0..n {
                    let (pk, qk) = (m[p][k], m[q][k]);
                    m[p][k] = c * pk - s * qk;
                    m[q][k] = s * pk + c * qk;
                }
                m[p][q] = 0.0;
                m[q][p] = 0.0;
            }
        }
    }
    let mut values: Vec<f64> = (0..n).map(|i| m[i][i]).collect();
    values.sort_by(f64::total_cmp);
    Ok(values)
}

/// Singular values by one-sided Jacobi rotations.
pub fn singular_values(a: &Matrix) -> Vec<f64> {
    let (rows, n) = (a.len(), a.first().map_or(0, Vec::len));
    let mut m = a.clone();
    for _ in 0..100 {
        let mut rotated = false;
        for p in 0..n {
            for q in p + 1..n {
                let (mut alpha, mut beta, mut gamma) = (0.0f64, 0.0f64, 0.0f64);
                for r in 0..rows {
                    alpha += m[r][p] * m[r][p];
                    beta += m[r][q] * m[r][q];
                    gamma += m[r][p] * m[r][q];
                }
                if gamma == 0.0 || gamma.abs() <= 1e-16 * f64::sqrt(alpha * beta) {
                    continue;
                }
                rotated = true;
                let zeta = (beta - alpha) / (2.0 * gamma);
                let sign = if zeta < 0.0 { -1.0 } else { 1.0 };
                let t = sign / (zeta.abs() + (1.0 + zeta * zeta).sqrt());
                let c = 1.0 / (1.0 + t * t).sqrt();
                let s = c * t;
                for r in 0..rows {
                    let (x, y) = (m[r][p], m[r][q]);
                    m[r][p] = c * x - s * y;
                    m[r][q] = s * x + c * y;
                }
            }
        }
        if !rotated {
            break;
        }
    }
    (0..n)
        .map(|k| (0..rows).map(|r| m[r][k] * m[r][k]).sum::<f64>().sqrt())
        .collect()
}

/// Thomas algorithm for a constant tridiagonal system. The solution replaces `rhs`.
/// Unchecked kernel (E1): inputs are not validated, and NaN or infinity in gives NaN out.
pub fn thomas(lower: f64, diag: f64, upper: f64, rhs: &mut [f64]) {
    let n = rhs.len();
    let mut c = vec![0.0; n];
    c[0] = upper / diag;
    rhs[0] /= diag;
    for i in 1..n {
        let m = diag - lower * c[i - 1];
        c[i] = upper / m;
        rhs[i] = (rhs[i] - lower * rhs[i - 1]) / m;
    }
    for i in (0..n - 1).rev() {
        rhs[i] -= c[i] * rhs[i + 1];
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn close(a: &[f64], b: &[f64], tol: f64) {
        assert_eq!(a.len(), b.len());
        for (x, y) in a.iter().zip(b) {
            assert!((x - y).abs() <= tol, "{a:?} vs {b:?}");
        }
    }

    #[test]
    fn solve_needs_pivoting_and_rejects_bad_shapes() {
        let a = vec![
            vec![0.0, 2.0, 1.0],
            vec![1.0, 1.0, 0.0],
            vec![3.0, 0.0, 1.0],
        ];
        let x = solve(&a, &[5.0, 3.0, 4.0]).unwrap();
        close(&x, &[1.0, 2.0, 1.0], 1e-12);
        assert!(solve(&vec![vec![1.0, 2.0]], &[1.0]).is_err());
        assert!(solve(&Vec::new(), &[]).is_err());
        assert!(solve(&vec![vec![1.0, 2.0], vec![2.0, 4.0]], &[1.0, 2.0]).is_err());
    }

    #[test]
    fn cholesky_reconstructs_matrix() {
        let a = vec![
            vec![4.0, 2.0, 0.4],
            vec![2.0, 5.0, 1.0],
            vec![0.4, 1.0, 3.0],
        ];
        let l = cholesky(&a).unwrap();
        for i in 0..3 {
            for j in 0..3 {
                let v: f64 = (0..3).map(|k| l[i][k] * l[j][k]).sum();
                assert!((v - a[i][j]).abs() < 1e-12);
            }
            for j in i + 1..3 {
                assert_eq!(l[i][j], 0.0);
            }
        }
        assert!(cholesky(&vec![vec![1.0, 2.0], vec![2.0, 1.0]]).is_err());
        assert!(cholesky(&vec![vec![1.0, 0.5], vec![0.4, 1.0]]).is_err());
    }

    #[test]
    fn eigenvalues_and_singular_values() {
        let mut e = eigen_symmetric(&vec![vec![2.0, 1.0], vec![1.0, 2.0]]).unwrap();
        e.sort_by(f64::total_cmp);
        close(&e, &[1.0, 3.0], 1e-12);
        let mut s = singular_values(&vec![vec![3.0, 0.0], vec![0.0, -4.0], vec![0.0, 0.0]]);
        s.sort_by(f64::total_cmp);
        close(&s, &[3.0, 4.0], 1e-12);
    }

    #[test]
    fn thomas_matches_dense_solve() {
        let (lo, d, up) = (-1.0, 4.0, -2.0);
        let rhs = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let n = rhs.len();
        let dense: Matrix = (0..n)
            .map(|i| {
                (0..n)
                    .map(|j| match j as i64 - i as i64 {
                        0 => d,
                        -1 => lo,
                        1 => up,
                        _ => 0.0,
                    })
                    .collect()
            })
            .collect();
        let want = solve(&dense, &rhs).unwrap();
        let mut got = rhs;
        thomas(lo, d, up, &mut got);
        close(&got, &want, 1e-12);
    }
}
