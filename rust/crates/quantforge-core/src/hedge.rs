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
