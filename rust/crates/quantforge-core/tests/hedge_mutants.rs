//! Value tests for `hedge.rs` (J-0, mutation gap). The reference solution is found by
//! brute force: every sign pattern in {-1, 0, +1}^n is solved exactly on its support and
//! the one that satisfies the first-order conditions is the unique minimiser of the
//! strictly convex objective. This shares no code with the coordinate-descent solver.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
#![allow(clippy::needless_range_loop)] // index form mirrors the textbook elimination
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

/// Minimiser of `sum_r w_r (b_r + (A x)_r)^2 + lambda sum_i costs_i |x_i|`, by enumeration.
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
        assert!(
            (g - e).abs() <= 1e-9 * (1.0 + e.abs()),
            "x {:?} vs {:?}",
            h.x,
            want
        );
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
    assert!(x.contains(&0.0) || x.iter().any(|v| *v < 0.0));
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

/// Audit case A (`program/J0_EQUIVALENT_AUDIT.md`): near-collinear columns where descent alone
/// does not converge in time; the exact-support polish at sweep 63 is what succeeds. The answer
/// is checked against the brute-force enumeration.
#[test]
fn polish_is_needed_on_near_collinear_columns() {
    let a: Matrix = vec![
        vec![
            0.06452333649029651,
            0.42367816317235063,
            0.4236560454811379,
            0.42364098535829753,
        ],
        vec![
            0.2152159902079146,
            0.21521075185620386,
            0.14812324400176635,
            0.1480935238690613,
        ],
        vec![
            0.11760969739417759,
            0.11760514338479665,
            -0.3067217067624666,
            -0.306761385865427,
        ],
        vec![
            0.24936890745714102,
            -0.34829343966111903,
            -0.42467215863102337,
            -0.4247066591314843,
        ],
        vec![
            0.39511830312956386,
            0.3115634021783298,
            0.3115422984456242,
            0.3115354464695181,
        ],
    ];
    let b = [
        0.47846487040675223,
        -0.17730671622319183,
        0.2750276985583118,
        -0.30931612482738524,
        0.12307859374017927,
    ];
    let w = [
        0.5066255997901173,
        0.929824446642092,
        0.2847009500015133,
        0.274103313367548,
        0.11666851217794064,
    ];
    check(
        &a,
        &b,
        &w,
        &[0.16754907601671443, 0.0, 0.0, 0.0],
        0.007895753744258438,
    );
}

/// Audit cases B and B': identity, lambda 0, so x = -b exactly on two legs; a polish
/// candidate of the wrong length must never be accepted.
#[test]
fn identity_hedges_return_full_length_answers() {
    let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    for b in [[-1.0, 5.0], [1.0, 5.0]] {
        let x = check(&a, &b, &[1.0, 1.0], &[0.0, 0.0], 0.0);
        assert_eq!(x.len(), 2);
    }
}
