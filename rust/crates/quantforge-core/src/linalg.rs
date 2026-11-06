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

/// Thomas algorithm for a constant tridiagonal system. The solution replaces `rhs`.
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
