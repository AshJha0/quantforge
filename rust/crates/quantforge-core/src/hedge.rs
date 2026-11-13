//! Hedge solve and cost (`stage-b-hedges.md`).

use crate::error::{Result, fail};
use crate::linalg::{Matrix, solve};

#[derive(Debug, Clone, PartialEq)]
pub struct Hedge {
    pub x: Vec<f64>,
    pub residual: Vec<f64>,
    pub objective: f64,
}

fn full_rank(q: &Matrix) -> bool {
    let n = q.len();
    let limit = 1e-12 * q.iter().flatten().fold(0.0f64, |m, v| m.max(v.abs()));
    let mut m = q.clone();
    for k in 0..n {
        let p = (k..n)
            .max_by(|a, b| m[*a][k].abs().total_cmp(&m[*b][k].abs()))
            .expect("not empty");
        if m[p][k].abs() <= limit {
            return false;
        }
        m.swap(k, p);
        for i in k + 1..n {
            let f = m[i][k] / m[k][k];
            for j in k..n {
                m[i][j] -= f * m[k][j];
            }
        }
    }
    true
}

/// `g_i` of the first-order conditions, halved: `q_i + (Q x)_i`.
fn half_gradient(q: &Matrix, c: &[f64], x: &[f64]) -> Vec<f64> {
    (0..x.len())
        .map(|i| c[i] + (0..x.len()).map(|j| q[i][j] * x[j]).sum::<f64>())
        .collect()
}

fn conditions_hold(q: &Matrix, c: &[f64], pen: &[f64], x: &[f64]) -> bool {
    let g = half_gradient(q, c, x);
    let scale = 1.0 + c.iter().fold(0.0f64, |m, v| m.max(v.abs()));
    (0..x.len()).all(|i| {
        if x[i] == 0.0 {
            g[i].abs() <= pen[i] + 1e-11 * scale
        } else {
            (g[i] + pen[i] * x[i].signum()).abs() <= 1e-9 * scale
        }
    })
}

/// Solves exactly on the support and signs of `x`.
fn polish(q: &Matrix, c: &[f64], pen: &[f64], x: &[f64]) -> Option<Vec<f64>> {
    let support: Vec<usize> = (0..x.len()).filter(|&i| x[i] != 0.0).collect();
    if support.is_empty() {
        return Some(x.to_vec());
    }
    let a: Matrix = support
        .iter()
        .map(|&i| support.iter().map(|&j| q[i][j]).collect())
        .collect();
    let b: Vec<f64> = support
        .iter()
        .map(|&i| -c[i] - pen[i] * x[i].signum())
        .collect();
    let s = solve(&a, &b).ok()?;
    let mut out = vec![0.0; x.len()];
    for (v, &i) in s.iter().zip(&support) {
        if v.signum() != x[i].signum() {
            return None;
        }
        out[i] = *v;
    }
    Some(out)
}

pub fn solve_hedge(
    a: &Matrix,
    b: &[f64],
    weights: &[f64],
    costs: &[f64],
    lambda: f64,
) -> Result<Hedge> {
    crate::error::finite("b", &b)?;
    crate::error::finite("weights", &weights)?;
    crate::error::finite("costs", &costs)?;
    crate::error::finite("lambda", &lambda)?;
    let rows = a.len();
    let n = costs.len();
    if rows == 0
        || b.len() != rows
        || weights.len() != rows
        || n == 0
        || a.iter().any(|r| r.len() != n)
    {
        return fail("E_INPUT", "lengths do not match");
    }
    if weights.iter().any(|w| *w <= 0.0) || costs.iter().any(|c| *c < 0.0) || lambda < 0.0 {
        return fail("E_DOMAIN", "weights, costs or lambda out of range");
    }
    let mut q = vec![vec![0.0; n]; n];
    let mut c = vec![0.0; n];
    for r in 0..rows {
        for i in 0..n {
            c[i] += a[r][i] * weights[r] * b[r];
            for j in 0..n {
                q[i][j] += a[r][i] * weights[r] * a[r][j];
            }
        }
    }
    if !full_rank(&q) {
        return fail("E_SINGULAR", "instruments are not independent");
    }
    // Minimise x'Qx + 2c'x + lambda sum c_i |x_i|, so each coordinate has threshold `pen`.
    let pen: Vec<f64> = costs.iter().map(|v| lambda * v / 2.0).collect();
    let neg: Vec<f64> = c.iter().map(|v| -v).collect();
    let mut x = solve(&q, &neg)?;
    for sweep in 0..2_000_000 {
        let mut moved = 0.0f64;
        for i in 0..n {
            let rest: f64 = c[i]
                + (0..n)
                    .filter(|&j| j != i)
                    .map(|j| q[i][j] * x[j])
                    .sum::<f64>();
            let v = if rest > pen[i] {
                -(rest - pen[i]) / q[i][i]
            } else if rest < -pen[i] {
                -(rest + pen[i]) / q[i][i]
            } else {
                0.0
            };
            moved = moved.max((v - x[i]).abs());
            x[i] = v;
        }
        if sweep % 64 == 63 || moved == 0.0 {
            if let Some(p) = polish(&q, &c, &pen, &x)
                && conditions_hold(&q, &c, &pen, &p)
            {
                x = p;
                break;
            }
            if moved == 0.0 {
                break;
            }
        }
    }
    if !conditions_hold(&q, &c, &pen, &x) {
        return fail("E_NO_CONVERGENCE", "first-order conditions do not hold");
    }
    let residual: Vec<f64> = (0..rows)
        .map(|r| b[r] + (0..n).map(|i| a[r][i] * x[i]).sum::<f64>())
        .collect();
    let fit: f64 = (0..rows).map(|r| weights[r] * residual[r].powi(2)).sum();
    let cost: f64 = (0..n).map(|i| costs[i] * x[i].abs()).sum();
    Ok(Hedge {
        x,
        residual,
        objective: fit + lambda * cost,
    })
}

pub fn spread_cost(quantities: &[f64], half_spreads: &[f64]) -> Result<f64> {
    crate::error::finite("quantities", &quantities)?;
    crate::error::finite("half_spreads", &half_spreads)?;
    if quantities.len() != half_spreads.len() {
        return fail("E_INPUT", "lengths differ");
    }
    if half_spreads.iter().any(|h| *h < 0.0) {
        return fail("E_DOMAIN", "a half spread is negative");
    }
    Ok(quantities
        .iter()
        .zip(half_spreads)
        .map(|(q, h)| q.abs() * h)
        .sum())
}

impl crate::error::Finite for Hedge {
    fn is_all_finite(&self) -> bool {
        self.x.is_all_finite() && self.residual.is_all_finite() && self.objective.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::error::Finite;

    fn code<T: std::fmt::Debug>(r: Result<T>) -> &'static str {
        r.unwrap_err().code
    }

    /// One instrument, one row: `x'Qx + 2c'x + lambda c |x|` with `Q = w a^2`, `c = a w b`.
    #[test]
    fn single_instrument_closed_form() {
        // No cost: x = -b / a exactly, zero residual, zero objective.
        let h = solve_hedge(&vec![vec![1.0]], &[-2.0], &[3.0], &[1.0], 0.0).unwrap();
        assert!((h.x[0] - 2.0).abs() < 1e-12, "{h:?}");
        assert!(
            h.residual[0].abs() < 1e-12 && h.objective.abs() < 1e-12,
            "{h:?}"
        );
        // Cost shrinks toward zero: 6x - 12 + lambda = 0, x = 2 - lambda / 6.
        let h = solve_hedge(&vec![vec![1.0]], &[-2.0], &[3.0], &[1.0], 1.2).unwrap();
        assert!((h.x[0] - 1.8).abs() < 1e-12, "{h:?}");
        assert!((h.residual[0] + 0.2).abs() < 1e-12, "{h:?}");
        // fit = 3 * 0.04 = 0.12, cost = 1.2 * 1.8 = 2.16.
        assert!((h.objective - 2.28).abs() < 1e-12, "{h:?}");
        // Mirror image: positive b gives a negative hedge.
        let h = solve_hedge(&vec![vec![1.0]], &[2.0], &[3.0], &[1.0], 1.2).unwrap();
        assert!((h.x[0] + 1.8).abs() < 1e-12, "{h:?}");
        assert!((h.objective - 2.28).abs() < 1e-12, "{h:?}");
        // Scaled instrument: a = 2, w = 1, b = -3: Q = 4, c = -6, x = (6 - pen) / 4, pen = 0.5.
        let h = solve_hedge(&vec![vec![2.0]], &[-3.0], &[1.0], &[1.0], 1.0).unwrap();
        assert!((h.x[0] - 1.375).abs() < 1e-12, "{h:?}");
        assert!(
            (h.objective - (0.25f64.powi(2) + 1.375)).abs() < 1e-12,
            "{h:?}"
        );
    }

    #[test]
    fn cost_at_the_threshold_gives_zero_hedge() {
        // |c| = 2 equals pen = lambda * cost / 2 = 2: the optimum sits exactly on the kink.
        let h = solve_hedge(&vec![vec![1.0]], &[-2.0], &[1.0], &[1.0], 4.0).unwrap();
        assert_eq!(h.x, vec![0.0]);
        assert_eq!(h.residual, vec![-2.0]);
        assert!((h.objective - 4.0).abs() < 1e-12, "{h:?}");
        // Above the threshold too.
        let h = solve_hedge(&vec![vec![1.0]], &[2.0], &[1.0], &[1.0], 10.0).unwrap();
        assert_eq!(h.x, vec![0.0]);
    }

    #[test]
    fn two_instruments_one_dropped_by_cost() {
        // Orthogonal instruments: each coordinate is its own one-dimensional problem.
        let a = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let h = solve_hedge(&a, &[-3.0, -0.4], &[1.0, 1.0], &[1.0, 1.0], 1.0).unwrap();
        assert!((h.x[0] - 2.5).abs() < 1e-12 && h.x[1] == 0.0, "{h:?}");
        assert!((h.residual[0] + 0.5).abs() < 1e-12 && (h.residual[1] + 0.4).abs() < 1e-12);
        // Correlated instruments: compare with the exact solution on the support.
        let a = vec![vec![1.0, 0.5], vec![0.2, 1.0], vec![0.3, 0.3]];
        let b = [-1.0, 2.0, 0.5];
        let w = [1.0, 2.0, 1.0];
        let h = solve_hedge(&a, &b, &w, &[0.1, 0.2], 0.5).unwrap();
        let mut q = vec![vec![0.0; 2]; 2];
        let mut c = [0.0; 2];
        for r in 0..3 {
            for i in 0..2 {
                c[i] += a[r][i] * w[r] * b[r];
                for j in 0..2 {
                    q[i][j] += a[r][i] * w[r] * a[r][j];
                }
            }
        }
        let pen = [0.025, 0.05];
        let rhs: Vec<f64> = (0..2).map(|i| -c[i] - pen[i] * h.x[i].signum()).collect();
        let exact = solve(&q, &rhs).unwrap();
        for i in 0..2 {
            assert!(
                h.x[i] != 0.0 && (h.x[i] - exact[i]).abs() < 1e-10,
                "{h:?} {exact:?}"
            );
        }
    }

    #[test]
    fn errors() {
        let a = vec![vec![1.0]];
        assert_eq!(code(solve_hedge(&vec![], &[], &[], &[1.0], 0.0)), "E_INPUT");
        assert_eq!(
            code(solve_hedge(&a, &[1.0, 2.0], &[1.0], &[1.0], 0.0)),
            "E_INPUT"
        );
        assert_eq!(
            code(solve_hedge(&a, &[1.0], &[1.0, 1.0], &[1.0], 0.0)),
            "E_INPUT"
        );
        assert_eq!(code(solve_hedge(&a, &[1.0], &[1.0], &[], 0.0)), "E_INPUT");
        assert_eq!(
            code(solve_hedge(&a, &[1.0], &[1.0], &[1.0, 1.0], 0.0)),
            "E_INPUT"
        );
        assert_eq!(
            code(solve_hedge(&a, &[1.0], &[0.0], &[1.0], 0.0)),
            "E_DOMAIN"
        );
        assert_eq!(
            code(solve_hedge(&a, &[1.0], &[1.0], &[-1.0], 0.0)),
            "E_DOMAIN"
        );
        assert_eq!(
            code(solve_hedge(&a, &[1.0], &[1.0], &[1.0], -1.0)),
            "E_DOMAIN"
        );
        assert_eq!(
            code(solve_hedge(&a, &[f64::NAN], &[1.0], &[1.0], 0.0)),
            "E_DOMAIN"
        );
        let dep = vec![vec![1.0, 2.0], vec![2.0, 4.0]];
        assert_eq!(
            code(solve_hedge(
                &dep,
                &[1.0, 1.0],
                &[1.0, 1.0],
                &[1.0, 1.0],
                0.0
            )),
            "E_SINGULAR"
        );
        let zero = vec![vec![0.0]];
        assert_eq!(
            code(solve_hedge(&zero, &[1.0], &[1.0], &[1.0], 0.0)),
            "E_SINGULAR"
        );
    }

    #[test]
    fn conditions_tolerance() {
        let q = vec![vec![1.0]];
        // c = 0: the tolerance keeps an absolute floor of 1e-9.
        assert!(conditions_hold(&q, &[0.0], &[0.0], &[1e-10]));
        assert!(!conditions_hold(&q, &[0.0], &[0.0], &[1e-8]));
        // At zero, |g| may equal the penalty exactly, and exceed it only by 1e-11 * scale.
        assert!(conditions_hold(&q, &[2.0], &[2.0], &[0.0]));
        assert!(conditions_hold(&q, &[2.0], &[2.0 - 2e-11], &[0.0]));
        assert!(!conditions_hold(&q, &[2.0], &[1.9], &[0.0]));
        // Away from zero the penalty enters with the sign of x.
        assert!(conditions_hold(&q, &[-2.0], &[0.5], &[1.5]));
        assert!(conditions_hold(&q, &[2.0], &[0.5], &[-1.5]));
        assert!(!conditions_hold(&q, &[-2.0], &[0.5], &[2.5]));
    }

    #[test]
    fn spread_cost_and_finite() {
        assert_eq!(spread_cost(&[2.0, -3.0], &[0.5, 0.25]).unwrap(), 1.75);
        assert_eq!(code(spread_cost(&[1.0], &[0.5, 0.5])), "E_INPUT");
        assert_eq!(code(spread_cost(&[1.0], &[-0.5])), "E_DOMAIN");
        let ok = Hedge {
            x: vec![1.0],
            residual: vec![0.0],
            objective: 1.0,
        };
        assert!(ok.is_all_finite());
        let bad_x = Hedge {
            x: vec![f64::NAN],
            ..ok.clone()
        };
        let bad_r = Hedge {
            residual: vec![f64::INFINITY],
            ..ok.clone()
        };
        let bad_o = Hedge {
            objective: f64::NAN,
            ..ok
        };
        assert!(!bad_x.is_all_finite() && !bad_r.is_all_finite() && !bad_o.is_all_finite());
    }
}
