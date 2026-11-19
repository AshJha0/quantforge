//! Regularised and outlier-robust curve fits (`curve-fits.md`).

use crate::error::{Result, fail};
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
    crate::error::finite("knots", &knots)?;
    crate::error::finite("maturities", &maturities)?;
    crate::error::finite("zero_rates", &zero_rates)?;
    crate::error::finite("lambda", &lambda)?;
    crate::error::finite("weights", &weights)?;
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
    solve3(&a, &rhs)
}

/// Gaussian elimination with partial pivoting and an exact-zero pivot test, as Python's
/// `lu_solve`. Ruling D38b has already rejected bases singular to working precision, so the
/// shared solver's relative pivot test must not reject the systems it lets through.
fn solve3(a: &[Vec<f64>], rhs: &[f64]) -> Result<[f64; 3]> {
    let mut m = [
        [a[0][0], a[0][1], a[0][2]],
        [a[1][0], a[1][1], a[1][2]],
        [a[2][0], a[2][1], a[2][2]],
    ];
    let mut x = [rhs[0], rhs[1], rhs[2]];
    for k in 0..3 {
        let mut p = k;
        for i in k + 1..3 {
            if m[i][k].abs() > m[p][k].abs() {
                p = i;
            }
        }
        if m[p][k] == 0.0 {
            return fail("E_SINGULAR", "the matrix is singular to working precision");
        }
        if p != k {
            m.swap(k, p);
            x.swap(k, p);
        }
        for i in k + 1..3 {
            let factor = m[i][k] / m[k][k];
            if factor != 0.0 {
                for j in k..3 {
                    m[i][j] -= factor * m[k][j];
                }
                x[i] -= factor * x[k];
            }
        }
    }
    for i in (0..3).rev() {
        let mut total = x[i];
        for j in i + 1..3 {
            total -= m[i][j] * x[j];
        }
        x[i] = total / m[i][i];
    }
    Ok(x)
}

fn residuals(x: &[[f64; 3]], y: &[f64], b: &[f64; 3]) -> Vec<f64> {
    x.iter()
        .zip(y)
        .map(|(r, y)| r[0] * b[0] + r[1] * b[1] + r[2] * b[2] - y)
        .collect()
}

/// Ruling D38b: below this reciprocal condition number the robust fit's basis is singular.
const RCOND_MIN: f64 = 1e-12;

/// Ruling D38b: reciprocal 1-norm condition number of `X^T X` with columns scaled to unit
/// diagonal, from the explicit 3x3 inverse (adjugate over determinant), in the same operation
/// order as the other languages. 0 when the determinant is not positive.
fn basis_rcond(x: &[[f64; 3]]) -> f64 {
    let mut g = [[0.0; 3]; 3];
    for row in x {
        for p in 0..3 {
            for q in 0..3 {
                g[p][q] += row[p] * row[q];
            }
        }
    }
    let s = [
        1.0 / g[0][0].sqrt(),
        1.0 / g[1][1].sqrt(),
        1.0 / g[2][2].sqrt(),
    ];
    let mut a = [[0.0; 3]; 3];
    for p in 0..3 {
        for q in 0..3 {
            a[p][q] = g[p][q] * s[p] * s[q];
        }
    }
    let c = [
        [
            a[1][1] * a[2][2] - a[1][2] * a[2][1],
            a[1][2] * a[2][0] - a[1][0] * a[2][2],
            a[1][0] * a[2][1] - a[1][1] * a[2][0],
        ],
        [
            a[0][2] * a[2][1] - a[0][1] * a[2][2],
            a[0][0] * a[2][2] - a[0][2] * a[2][0],
            a[0][1] * a[2][0] - a[0][0] * a[2][1],
        ],
        [
            a[0][1] * a[1][2] - a[0][2] * a[1][1],
            a[0][2] * a[1][0] - a[0][0] * a[1][2],
            a[0][0] * a[1][1] - a[0][1] * a[1][0],
        ],
    ];
    let det = a[0][0] * c[0][0] + a[0][1] * c[0][1] + a[0][2] * c[0][2];
    if det.is_nan() || det <= 0.0 {
        return 0.0;
    }
    let (mut norm_a, mut norm_inv) = (0.0_f64, 0.0_f64);
    for q in 0..3 {
        norm_a = norm_a.max(a[0][q].abs() + a[1][q].abs() + a[2][q].abs());
        norm_inv = norm_inv.max((c[q][0].abs() + c[q][1].abs() + c[q][2].abs()) / det);
    }
    1.0 / (norm_a * norm_inv)
}

/// Working-set changes allowed before `robust` gives up (never reached at full rank).
const ROBUST_ITERATIONS: usize = 1000;

/// `calib.curve.robust`: Nelson-Siegel with fixed `tau`, Huber loss. An active-set method on the
/// dual finds the outlier set and signs exactly; the betas solve the inlier/outlier normal equations.
pub fn robust(maturities: &[f64], zero_rates: &[f64], tau: f64, delta: f64) -> Result<Robust> {
    crate::error::finite("maturities", &maturities)?;
    crate::error::finite("zero_rates", &zero_rates)?;
    crate::error::finite("tau", &tau)?;
    crate::error::finite("delta", &delta)?;
    let n = maturities.len();
    if zero_rates.len() != n || n < 3 {
        return fail("E_INPUT", "need at least 3 points of equal length");
    }
    if tau <= 0.0 || delta <= 0.0 || maturities.iter().any(|m| *m <= 0.0) {
        return fail("E_DOMAIN", "tau, delta and maturities must be positive");
    }
    let x: Vec<[f64; 3]> = maturities.iter().map(|m| ns_row(*m, tau)).collect();
    let rcond = basis_rcond(&x);
    if rcond.is_nan() || rcond < RCOND_MIN {
        return fail(
            "E_SINGULAR",
            "the Nelson-Siegel basis is singular to working precision (D38b)",
        );
    }
    // Primal active-set method on the dual (Nocedal and Wright, algorithm 16.3); the Python
    // implementation carries the full derivation. theta is the dual point, bound[j] the sign
    // s_j of a theta_j held at s_j delta (0 when free); the betas solve the inlier/outlier
    // normal equations of the current working set.
    let mut theta = vec![0.0; n];
    let mut bound = vec![0_i8; n];
    let mut solved = None;
    for _ in 0..ROBUST_ITERATIONS {
        let w: Vec<f64> = bound.iter().map(|s| f64::from(*s == 0)).collect();
        let mut g = [0.0; 3];
        for (row, s) in x.iter().zip(&bound) {
            for p in 0..3 {
                g[p] += delta * f64::from(*s) * row[p];
            }
        }
        let b = normal_solve(&x, zero_rates, &w, g)?;
        let r = residuals(&x, zero_rates, &b);
        let (mut alpha, mut block) = (1.0, None);
        for j in 0..n {
            let p = r[j] - theta[j];
            if bound[j] != 0 || p == 0.0 {
                continue;
            }
            let limit = ((if p > 0.0 { delta } else { -delta }) - theta[j]) / p;
            if limit < alpha {
                alpha = limit;
                block = Some(j);
            }
        }
        if let Some(k) = block {
            for j in 0..n {
                if bound[j] == 0 {
                    theta[j] += alpha * (r[j] - theta[j]);
                }
            }
            bound[k] = if r[k] - theta[k] > 0.0 { 1 } else { -1 };
            theta[k] = f64::from(bound[k]) * delta;
            continue;
        }
        for j in 0..n {
            theta[j] = if bound[j] == 0 {
                r[j]
            } else {
                f64::from(bound[j]) * delta
            };
        }
        let (mut worst, mut leave) = (0.0, None);
        for j in 0..n {
            let m = f64::from(bound[j]) * r[j] - delta;
            if bound[j] != 0 && m < worst {
                worst = m;
                leave = Some(j);
            }
        }
        if let Some(j) = leave {
            bound[j] = 0;
        } else {
            solved = Some(b);
            break;
        }
    }
    let Some(b) = solved else {
        return fail("E_NO_CONVERGENCE", "the Huber fit did not settle");
    };
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

impl crate::error::Finite for Robust {
    fn is_all_finite(&self) -> bool {
        self.betas.is_all_finite()
            && self.residuals.is_all_finite()
            && self.objective.is_all_finite()
    }
}

impl crate::error::Finite for Smooth {
    fn is_all_finite(&self) -> bool {
        self.forwards.is_all_finite()
            && self.fitted.is_all_finite()
            && self.objective.is_all_finite()
    }
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
        assert_eq!(pure.outliers, [] as [usize; 0]);
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

    /// Valid input where the old robust fit failed: at the minimum one residual sits within 1e-7
    /// of delta (mutation re-check 2026-11-18). Not a golden, because the spec keeps golden
    /// residuals 1e-6 from delta. The same input is in the Python, Java and C++ tests.
    #[test]
    fn robust_converges_with_a_residual_near_delta() {
        let m = [
            3.8740307873000113,
            7.757472624115791,
            24.769272470090453,
            24.76936904673551,
        ];
        let y = [
            0.022406223051166397,
            0.0025821078676810487,
            0.052253746187190836,
            0.04025167916426023,
        ];
        let (tau, delta) = (2.1121330519140273, 0.0010283264459667806);
        let fit = robust(&m, &y, tau, delta).unwrap();
        let mut g = [0.0; 3];
        let mut nearest = f64::MAX;
        for (j, mj) in m.iter().enumerate() {
            let x = ns_row(*mj, tau);
            let r = fit.residuals[j];
            for p in 0..3 {
                g[p] += r.clamp(-delta, delta) * x[p];
            }
            nearest = nearest.min((r.abs() - delta).abs());
        }
        assert!(g.iter().all(|v| v.abs() < 1e-14), "{g:?}");
        assert!(nearest < 1e-7);
        assert_eq!(fit.outliers, vec![2]);
    }
}

/// Behaviour of the D38b basis condition check and the Huber active-set fit (curve-fits.md).
/// Reference reciprocal condition numbers come from numpy: 1 / (||A||_1 ||inv(A)||_1) with A the
/// Gram matrix scaled to unit diagonal; the three matrices put the largest inverse column sum in
/// columns 2, 0 and 1. The same cases are in the Java and C++ tests.
#[cfg(test)]
mod d38b_tests {
    use super::*;
    use crate::error::Finite;

    #[test]
    fn basis_rcond_matches_the_one_norm_definition() {
        let x1 = [
            [1.0, 0.5, 0.2],
            [1.0, -1.0, 3.0],
            [2.0, 0.1, -0.7],
            [0.3, 2.0, 1.0],
        ];
        let x3 = [
            [1.0, 2.0, 0.1],
            [0.2, 1.0, 3.0],
            [4.0, -0.5, 1.0],
            [1.0, 1.0, -2.0],
            [0.7, -3.0, 0.4],
        ];
        let x5 = [
            [1.0, 0.9, 0.1],
            [1.0, 1.1, 0.3],
            [1.0, 1.0, -0.2],
            [1.0, 0.95, 0.05],
        ];
        assert!((basis_rcond(&x1) - 0.462_147_929_545_812_85).abs() < 1e-13);
        assert!((basis_rcond(&x3) - 0.633_503_583_772_005_4).abs() < 1e-13);
        assert!((basis_rcond(&x5) - 0.000_993_643_936_552_422_9).abs() < 1e-15);
        let dependent = [
            [1.0, 2.0, 3.0],
            [0.0, 1.0, 1.0],
            [1.0, 0.0, 1.0],
            [2.0, 1.0, 3.0],
        ];
        assert!(basis_rcond(&dependent) < RCOND_MIN);
    }

    #[test]
    fn nearly_equal_maturities_are_singular() {
        let m = [1.0, 1.0 + 1e-7, 1.0 + 2e-7, 1.0 + 3e-7];
        let y = [0.01, 0.02, 0.03, 0.04];
        assert_eq!(robust(&m, &y, 1.0, 1e-3).unwrap_err().code, "E_SINGULAR");
    }

    const M: [f64; 9] = [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0];
    const TAU: f64 = 1.5;

    fn curve(noise: [f64; 9]) -> Vec<f64> {
        M.iter()
            .zip(noise)
            .map(|(m, e)| {
                let r = ns_row(*m, TAU);
                0.03 * r[0] - 0.01 * r[1] + 0.02 * r[2] + e
            })
            .collect()
    }

    /// First-order conditions and objective of the Huber problem, from the returned betas alone.
    fn assert_huber_optimum(y: &[f64], delta: f64, fit: &Robust) {
        let mut g = [0.0; 3];
        let mut obj = 0.0;
        for (j, mj) in M.iter().enumerate() {
            let x = ns_row(*mj, TAU);
            let b = fit.betas;
            let r = b[0] * x[0] + b[1] * x[1] + b[2] * x[2] - y[j];
            assert!((r - fit.residuals[j]).abs() < 1e-15);
            for p in 0..3 {
                g[p] += r.clamp(-delta, delta) * x[p];
            }
            obj += if r.abs() <= delta {
                r * r / 2.0
            } else {
                delta * r.abs() - delta * delta / 2.0
            };
        }
        assert!(g.iter().all(|v| v.abs() < 1e-15), "{g:?}");
        assert!((obj - fit.objective).abs() < 1e-18);
        for j in &fit.outliers {
            assert!(fit.residuals[*j].abs() > delta);
        }
    }

    const NOISE: [f64; 9] = [2e-4, -1e-4, 0.01, 1e-4, -2e-4, 1.5e-4, -0.008, 0.0, 5e-5];

    #[test]
    fn outliers_of_both_signs_are_flagged() {
        let y = curve(NOISE);
        let fit = robust(&M, &y, TAU, 5e-4).unwrap();
        assert_huber_optimum(&y, 5e-4, &fit);
        assert_eq!(fit.outliers, vec![2, 6]);
        assert!(fit.residuals[2] < -5e-4 && fit.residuals[6] > 5e-4);
    }

    #[test]
    fn outlier_set_shrinks_as_delta_grows() {
        let y = curve(NOISE);
        let small = robust(&M, &y, TAU, 1e-4).unwrap();
        assert_huber_optimum(&y, 1e-4, &small);
        assert!(small.outliers.len() > 2);
        let large = robust(&M, &y, TAU, 1.0).unwrap();
        assert_huber_optimum(&y, 1.0, &large);
        assert_eq!(large.outliers, [] as [usize; 0]);
    }

    #[test]
    fn many_outliers_still_settle() {
        let y = curve([
            0.004, -0.003, 0.002, -0.005, 0.001, -0.002, 0.006, -0.001, 0.003,
        ]);
        let fit = robust(&M, &y, TAU, 2e-4).unwrap();
        assert_huber_optimum(&y, 2e-4, &fit);
    }

    #[test]
    fn a_point_leaves_the_working_set_before_the_fit_settles() {
        let y = curve([
            0.0017, 0.0018, 0.0006, -0.0023, -0.0018, 0.0026, -0.0027, 0.0015, 0.0015,
        ]);
        assert_huber_optimum(&y, 1e-4, &robust(&M, &y, TAU, 1e-4).unwrap());
    }

    #[test]
    fn ill_conditioned_basis_above_the_threshold_is_fitted() {
        // numpy: rcond of the scaled Gram matrix is 5.24e-10, well above 1e-12.
        let m = [5.0, 5.1, 5.2, 5.3];
        let y = [0.030, 0.031, 0.0305, 0.0302];
        let fit = robust(&m, &y, 5.0, 1e-3).unwrap();
        for (j, mj) in m.iter().enumerate() {
            let x = ns_row(*mj, 5.0);
            let b = fit.betas;
            let r = b[0] * x[0] + b[1] * x[1] + b[2] * x[2] - y[j];
            assert!((r - fit.residuals[j]).abs() < 1e-15);
        }
    }

    #[test]
    fn each_positivity_rule_is_checked_alone() {
        let m = [1.0, 2.0, 5.0, 10.0];
        let y = [0.01, 0.02, 0.025, 0.03];
        assert_eq!(robust(&m, &y, -1.0, 1e-3).unwrap_err().code, "E_DOMAIN");
        assert_eq!(robust(&m, &y, 1.0, -1e-3).unwrap_err().code, "E_DOMAIN");
        assert_eq!(
            robust(&[1.0, -2.0, 5.0, 10.0], &y, 1.0, 1e-3)
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn robust_result_finiteness_needs_every_field() {
        let ok = Robust {
            betas: [0.03, -0.01, 0.02],
            residuals: vec![1e-4, -1e-4],
            outliers: vec![],
            objective: 1e-8,
        };
        assert!(ok.is_all_finite());
        let mut bad = ok.clone();
        bad.residuals[1] = f64::NAN;
        assert!(!bad.is_all_finite());
        let mut bad = ok.clone();
        bad.betas[0] = f64::INFINITY;
        assert!(!bad.is_all_finite());
        let mut bad = ok;
        bad.objective = f64::NAN;
        assert!(!bad.is_all_finite());
    }
}
