//! Regularised and outlier-robust curve fits (`curve-fits.md`).
use crate::error::{Result, err, fail};
use crate::linalg::solve;

#[derive(Debug, Clone, PartialEq)]
pub struct Smooth {
    pub forwards: Vec<f64>,
    pub fitted: Vec<f64>,
    pub objective: f64,
}

/// `calib.curve.smooth`: piecewise-flat forwards with a first-difference penalty.
pub fn smooth(
    knots: &[f64],
    maturities: &[f64],
    zero_rates: &[f64],
    lambda: f64,
    weights: Option<&[f64]>,
) -> Result<Smooth> {
    let n_obs = maturities.len();
    if n_obs == 0 || zero_rates.len() != n_obs || weights.is_some_and(|w| w.len() != n_obs) {
        return fail(
            "E_INPUT",
            "maturities, zero_rates and weights must match and be non-empty",
        );
    }
    if knots.is_empty() || knots[0] <= 0.0 || knots.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "knots must be positive and strictly increasing");
    }
    if lambda < 0.0
        || weights.is_some_and(|w| w.iter().any(|x| *x < 0.0))
        || maturities.iter().any(|m| *m <= 0.0)
    {
        return fail(
            "E_DOMAIN",
            "lambda, weights and maturities are out of range",
        );
    }
    let last = knots[knots.len() - 1];
    if maturities.iter().any(|m| *m > last) {
        return fail("E_INPUT", "a maturity is past the last knot");
    }
    let n = knots.len();
    let row = |m: f64| -> Vec<f64> {
        (0..n)
            .map(|k| {
                let lo = if k == 0 { 0.0 } else { knots[k - 1] };
                (knots[k].min(m) - lo).max(0.0) / m
            })
            .collect()
    };
    let b: Vec<Vec<f64>> = maturities.iter().map(|m| row(*m)).collect();
    let w = |j: usize| weights.map_or(1.0, |w| w[j]);
    let mut a = vec![vec![0.0; n]; n];
    let mut rhs = vec![0.0; n];
    for j in 0..n_obs {
        for p in 0..n {
            rhs[p] += w(j) * b[j][p] * zero_rates[j];
            for q in 0..n {
                a[p][q] += w(j) * b[j][p] * b[j][q];
            }
        }
    }
    for k in 0..n.saturating_sub(1) {
        a[k][k] += lambda;
        a[k + 1][k + 1] += lambda;
        a[k][k + 1] -= lambda;
        a[k + 1][k] -= lambda;
    }
    let forwards = solve(&a, &rhs)?;
    let fitted: Vec<f64> = b
        .iter()
        .map(|r| r.iter().zip(&forwards).map(|(x, f)| x * f).sum())
        .collect();
    let fit: f64 = (0..n_obs)
        .map(|j| w(j) * (fitted[j] - zero_rates[j]).powi(2))
        .sum();
    let rough: f64 = forwards.windows(2).map(|p| (p[1] - p[0]).powi(2)).sum();
    Ok(Smooth {
        forwards,
        fitted,
        objective: fit + lambda * rough,
    })
}

#[derive(Debug, Clone, PartialEq)]
pub struct Robust {
    pub betas: [f64; 3],
    pub residuals: Vec<f64>,
    pub outliers: Vec<usize>,
    pub objective: f64,
}

fn ns_row(m: f64, tau: f64) -> [f64; 3] {
    let x = m / tau;
    let e = -(-x).exp_m1() / x;
    [1.0, e, e - (-x).exp()]
}

/// Weighted least squares with a linear shift on the right: `(X^T W X) b = X^T W y - g`.
fn normal_solve(x: &[[f64; 3]], y: &[f64], w: &[f64], g: [f64; 3]) -> Result<[f64; 3]> {
    let mut a = vec![vec![0.0; 3]; 3];
    let mut rhs = vec![0.0; 3];
    for j in 0..x.len() {
        for p in 0..3 {
            rhs[p] += w[j] * x[j][p] * y[j];
            for q in 0..3 {
                a[p][q] += w[j] * x[j][p] * x[j][q];
            }
        }
    }
    for p in 0..3 {
        rhs[p] -= g[p];
    }
    let b = solve(&a, &rhs)?;
    Ok([b[0], b[1], b[2]])
}

fn residuals(x: &[[f64; 3]], y: &[f64], b: &[f64; 3]) -> Vec<f64> {
    x.iter()
        .zip(y)
        .map(|(r, y)| r[0] * b[0] + r[1] * b[1] + r[2] * b[2] - y)
        .collect()
}

/// `calib.curve.robust`: Nelson-Siegel with fixed `tau`, Huber loss. IRLS to find the region,
/// then exact Newton steps on the inlier set and outlier signs until they stop changing.
pub fn robust(maturities: &[f64], zero_rates: &[f64], tau: f64, delta: f64) -> Result<Robust> {
    let n = maturities.len();
    if zero_rates.len() != n || n < 3 {
        return fail("E_INPUT", "need at least 3 points of equal length");
    }
    if tau <= 0.0 || delta <= 0.0 || maturities.iter().any(|m| *m <= 0.0) {
        return fail("E_DOMAIN", "tau, delta and maturities must be positive");
    }
    let x: Vec<[f64; 3]> = maturities.iter().map(|m| ns_row(*m, tau)).collect();
    let mut b = normal_solve(&x, zero_rates, &vec![1.0; n], [0.0; 3])?;
    for _ in 0..200 {
        let w: Vec<f64> = residuals(&x, zero_rates, &b)
            .iter()
            .map(|r| {
                if r.abs() <= delta {
                    1.0
                } else {
                    delta / r.abs()
                }
            })
            .collect();
        b = normal_solve(&x, zero_rates, &w, [0.0; 3])?;
    }
    let pattern = |r: &[f64]| -> Vec<i8> {
        r.iter()
            .map(|v| {
                if v.abs() <= delta {
                    0
                } else if *v > 0.0 {
                    1
                } else {
                    -1
                }
            })
            .collect()
    };
    let mut last = pattern(&residuals(&x, zero_rates, &b));
    let mut stable = false;
    for _ in 0..100 {
        let w: Vec<f64> = last.iter().map(|s| f64::from(*s == 0)).collect();
        let mut g = [0.0; 3];
        for (row, s) in x.iter().zip(&last) {
            for p in 0..3 {
                g[p] += delta * f64::from(*s) * row[p];
            }
        }
        b = normal_solve(&x, zero_rates, &w, g)
            .map_err(|_| err("E_NO_CONVERGENCE", "too few inliers to fix the betas"))?;
        let next = pattern(&residuals(&x, zero_rates, &b));
        if next == last {
            stable = true;
            break;
        }
        last = next;
    }
    if !stable || b.iter().any(|v| !v.is_finite()) {
        return fail("E_NO_CONVERGENCE", "the Huber fit did not settle");
    }
    let r = residuals(&x, zero_rates, &b);
    let objective = r
        .iter()
        .map(|v| {
            if v.abs() <= delta {
                v * v / 2.0
            } else {
                delta * v.abs() - delta * delta / 2.0
            }
        })
        .sum();
    let outliers = (0..n).filter(|j| r[*j].abs() > delta).collect();
    Ok(Robust {
        betas: b,
        residuals: r,
        outliers,
        objective,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn smooth_exact_with_no_penalty() {
        let knots = [1.0, 2.0];
        let s = smooth(&knots, &[1.0, 2.0], &[0.03, 0.04], 0.0, None).unwrap();
        assert!((s.forwards[0] - 0.03).abs() < 1e-15);
        assert!((s.forwards[1] - 0.05).abs() < 1e-15);
        assert!(s.objective < 1e-30);
    }

    #[test]
    fn smooth_large_penalty_flattens() {
        let s = smooth(&[1.0, 2.0], &[1.0, 2.0], &[0.03, 0.04], 1e9, None).unwrap();
        assert!((s.forwards[0] - s.forwards[1]).abs() < 1e-9);
        let w = smooth(
            &[1.0, 2.0],
            &[1.0, 2.0],
            &[0.03, 0.04],
            1.0,
            Some(&[1.0, 0.0]),
        )
        .unwrap();
        assert!((w.fitted[0] - 0.03).abs() < 1e-12);
    }

    #[test]
    fn smooth_errors() {
        let e = |k: &[f64], m: &[f64], y: &[f64], l: f64, w: Option<&[f64]>| {
            smooth(k, m, y, l, w).unwrap_err().code
        };
        assert_eq!(e(&[1.0], &[], &[], 0.0, None), "E_INPUT");
        assert_eq!(e(&[1.0], &[1.0], &[0.1, 0.2], 0.0, None), "E_INPUT");
        assert_eq!(e(&[1.0], &[1.0], &[0.1], 0.0, Some(&[])), "E_INPUT");
        assert_eq!(e(&[1.0, 0.5], &[0.25], &[0.04], 1.0, None), "E_INPUT");
        assert_eq!(e(&[], &[0.25], &[0.04], 1.0, None), "E_INPUT");
        assert_eq!(e(&[1.0], &[0.25], &[0.04], -1.0, None), "E_DOMAIN");
        assert_eq!(e(&[1.0], &[0.25], &[0.04], 1.0, Some(&[-1.0])), "E_DOMAIN");
        assert_eq!(e(&[1.0], &[0.0], &[0.04], 1.0, None), "E_DOMAIN");
        assert_eq!(e(&[1.0], &[2.0], &[0.04], 1.0, None), "E_INPUT");
        assert_eq!(
            e(&[0.5, 1.0, 2.0], &[0.25], &[0.04], 0.0, None),
            "E_SINGULAR"
        );
    }

    #[test]
    fn robust_flags_the_outlier() {
        let m = [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0];
        let truth = [0.04, -0.01, 0.005];
        let mut y: Vec<f64> = m
            .iter()
            .map(|v| {
                let r = ns_row(*v, 2.0);
                r[0] * truth[0] + r[1] * truth[1] + r[2] * truth[2]
            })
            .collect();
        y[3] += 0.003;
        let r = robust(&m, &y, 2.0, 0.0005).unwrap();
        assert_eq!(r.outliers, vec![3]);
        assert!(r.residuals[3] < -0.0005);
        let pure = robust(&m, &y.iter().map(|v| v + 0.0).collect::<Vec<_>>(), 2.0, 1.0).unwrap();
        assert!(pure.outliers.is_empty());
    }

    #[test]
    fn robust_errors() {
        let m = [1.0, 2.0, 3.0];
        let y = [0.01, 0.02, 0.03];
        assert_eq!(
            robust(&m[..2], &y[..2], 2.0, 0.1).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(robust(&m, &y[..2], 2.0, 0.1).unwrap_err().code, "E_INPUT");
        assert_eq!(robust(&m, &y, 0.0, 0.1).unwrap_err().code, "E_DOMAIN");
        assert_eq!(robust(&m, &y, 2.0, 0.0).unwrap_err().code, "E_DOMAIN");
        assert_eq!(
            robust(&[0.0, 1.0, 2.0], &y, 2.0, 0.1).unwrap_err().code,
            "E_DOMAIN"
        );
    }
}
