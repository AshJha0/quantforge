//! Value tests for `hedge.rs` (J-0, mutation gap). The reference solution is found by
//! brute force: every sign pattern in {-1, 0, +1}^n is solved exactly on its support and
//! the one that satisfies the first-order conditions is the unique minimiser of the
//! strictly convex objective. This shares no code with the coordinate-descent solver.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use quantforge_core::hedge::{solve_hedge, spread_cost};
use quantforge_core::linalg::Matrix;

fn gauss(mut a: Vec<Vec<f64>>, mut b: Vec<f64>) -> Vec<f64> {
    let n = b.len();
    for k in 0..n {
        let p = (k..n)
            .max_by(|x, y| a[*x][k].abs().total_cmp(&a[*y][k].abs()))
            .unwrap();
        a.swap(k, p);
        b.swap(k, p);
        for i in k + 1..n {
            let f = a[i][k] / a[k][k];
            for j in k..n {
                a[i][j] -= f * a[k][j];
            }
            b[i] -= f * b[k];
        }
    }
    let mut x = vec![0.0; n];
    for k in (0..n).rev() {
        let s: f64 = (k + 1..n).map(|j| a[k][j] * x[j]).sum();
        x[k] = (b[k] - s) / a[k][k];
    }
    x
}

/// Minimiser of sum_r w_r (b_r + (A x)_r)^2 + lambda sum_i costs_i |x_i|, by enumeration.
fn reference(a: &Matrix, b: &[f64], w: &[f64], costs: &[f64], lambda: f64) -> Vec<f64> {
    let n = costs.len();
    let q: Vec<Vec<f64>> = (0..n)
        .map(|i| {
            (0..n)
                .map(|j| (0..b.len()).map(|r| a[r][i] * w[r] * a[r][j]).sum())
                .collect()
        })
        .collect();
    let c: Vec<f64> = (0..n)
        .map(|i| (0..b.len()).map(|r| a[r][i] * w[r] * b[r]).sum())
        .collect();
    let pen: Vec<f64> = costs.iter().map(|v| lambda * v / 2.0).collect();
    for code in 0..3usize.pow(n as u32) {
        let s: Vec<f64> = (0..n)
            .map(|i| [0.0, 1.0, -1.0][(code / 3usize.pow(i as u32)) % 3])
            .collect();
        let sup: Vec<usize> = (0..n).filter(|&i| s[i] != 0.0).collect();
        let xs = gauss(
            sup.iter()
                .map(|&i| sup.iter().map(|&j| q[i][j]).collect())
                .collect(),
            sup.iter().map(|&i| -c[i] - pen[i] * s[i]).collect(),
        );
        let mut x = vec![0.0; n];
        for (v, &i) in xs.iter().zip(&sup) {
            x[i] = *v;
        }
        let ok = (0..n).all(|i| {
            let g = c[i] + (0..n).map(|j| q[i][j] * x[j]).sum::<f64>();
            if s[i] == 0.0 {
                g.abs() <= pen[i] + 1e-12
            } else {
                x[i] * s[i] > 0.0
            }
        });
        if ok {
            return x;
        }
    }
    panic!("no sign pattern satisfies the conditions");
}

fn check(a: &Matrix, b: &[f64], w: &[f64], costs: &[f64], lambda: f64) -> Vec<f64> {
    let want = reference(a, b, w, costs, lambda);
    let h = solve_hedge(a, b, w, costs, lambda).unwrap();
    assert_eq!(h.x.len(), want.len());
    for (g, e) in h.x.iter().zip(&want) {
        assert!((g - e).abs() <= 1e-9 * (1.0 + e.abs()), "x {:?} vs {:?}", h.x, want);
        assert_eq!(*e == 0.0, *g == 0.0, "support {:?} vs {:?}", h.x, want);
    }
    let mut fit = 0.0;
    for r in 0..b.len() {
        let res = b[r] + (0..want.len()).map(|i| a[r][i] * want[i]).sum::<f64>();
        assert!((h.residual[r] - res).abs() <= 1e-9 * (1.0 + res.abs()));
        fit += w[r] * res * res;
    }
    let cost: f64 = costs.iter().zip(&want).map(|(k, x)| k * x.abs()).sum();
    let obj = fit + lambda * cost;
    assert!((h.objective - obj).abs() <= 1e-9 * (1.0 + obj));
    h.x
}

fn five() -> (Matrix, Vec<f64>, Vec<f64>) {
    (
        vec![
            vec![1.0, 0.5, 0.2],
            vec![0.3, 1.2, 0.4],
            vec![0.1, 0.6, 1.5],
            vec![0.8, 0.2, 0.9],
            vec![0.4, 0.9, 0.3],
        ],
        vec![-2.0, 1.5, -0.7, 0.9, -1.1],
        vec![1.0, 2.0, 0.5, 1.5, 1.0],
    )
}

#[test]
fn unconstrained_and_costly_hedges_match_enumeration() {
    let (a, b, w) = five();
    for lambda in [0.0, 0.3, 1.0, 2.5, 6.0, 40.0] {
        check(&a, &b, &w, &[1.0, 0.4, 2.0], lambda);
        check(&a, &b, &w, &[0.0, 1.0, 0.5], lambda);
    }
}

#[test]
fn mixed_signs_and_a_zero_leg() {
    let (a, b, w) = five();
    let x = check(&a, &b, &w, &[1.0, 1.0, 1.0], 2.5);
    assert!(x.iter().any(|v| *v == 0.0) || x.iter().any(|v| *v < 0.0));
    // Mixed signs on purpose: flip the target so legs go both ways.
    let b2 = vec![2.0, -1.5, 0.7, 0.9, -1.1];
    for lambda in [0.5, 1.5, 3.0] {
        check(&a, &b2, &w, &[0.3, 1.2, 0.8], lambda);
    }
}

#[test]
fn highly_correlated_instruments_need_many_sweeps() {
    let a: Matrix = vec![
        vec![1.0, 0.99, 0.98],
        vec![0.5, 0.52, 0.49],
        vec![0.2, 0.18, 0.23],
        vec![0.9, 0.91, 0.88],
    ];
    let b = vec![-1.0, -0.4, -0.3, -0.8];
    let w = vec![1.0, 1.0, 1.0, 1.0];
    for lambda in [0.0, 0.01, 0.05, 0.2, 1.0] {
        check(&a, &b, &w, &[1.0, 0.5, 2.0], lambda);
    }
}

#[test]
fn single_instrument_closed_form() {
    // q = 4, c = 6, pen = lambda*cost/2 = 1, so x = -(c - pen) / q = -1.25.
    let a: Matrix = vec![vec![2.0]];
    let h = solve_hedge(&a, &[3.0], &[1.0], &[2.0], 1.0).unwrap();
    assert!((h.x[0] + 1.25).abs() < 1e-12);
    assert!((h.residual[0] - 0.5).abs() < 1e-12);
    assert!((h.objective - (0.25 + 2.0 * 1.25)).abs() < 1e-12);
    // Threshold above |c|: the hedge is exactly zero.
    let h = solve_hedge(&a, &[3.0], &[1.0], &[2.0], 7.0).unwrap();
    assert_eq!(h.x, vec![0.0]);
    assert_eq!(h.residual, vec![3.0]);
    assert!((h.objective - 9.0).abs() < 1e-12);
}

#[test]
fn nearly_dependent_instruments_are_rejected_before_solving() {
    // det(Q) = e^2 = 9e-14: above the LU limit, below the rank-check limit.
    let e = 3e-7;
    let a: Matrix = vec![vec![1.0, 1.0], vec![1.0, 1.0 + e]];
    let r = solve_hedge(&a, &[1.0, 2.0], &[1.0, 1.0], &[0.0, 0.0], 0.0);
    assert_eq!(r.unwrap_err().code, "E_SINGULAR");
}

#[test]
fn spread_cost_allows_zero_half_spreads() {
    assert_eq!(spread_cost(&[2.0, -3.0], &[0.0, 0.5]).unwrap(), 1.5);
    assert_eq!(spread_cost(&[1.0], &[-0.0]).unwrap(), 0.0);
    assert_eq!(
        spread_cost(&[1.0], &[-1e-300]).unwrap_err().code,
        "E_DOMAIN"
    );
}
