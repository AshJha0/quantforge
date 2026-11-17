//! Ruling J-I.1 (goldens `stage_j/hedgecut_j`): a bounded `hedge.qp.solve` keeps a column that is
//! small only in the caller's units. Python's active-set step cut ranks unscaled and returned
//! x = (0, 0), objective 1; this crate solves in Jacobi-scaled variables (R6-6.2) and pins the hand
//! optimum x1 = -1e7, objective 0, with and without a spread on x2.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use quantforge_core::hedge_solvers::{Costs, QpProblem, Singular, qp_solve};

#[test]
fn bounded_solve_keeps_a_small_column() {
    let a = vec![vec![1e-7, 0.0], vec![0.0, 1.0]];
    let (b, w) = ([1.0, 0.0], [1.0, 1.0]);
    let (lo, hi) = ([None, Some(0.0)], [None, Some(0.0)]);
    let spread = [0.0, 0.1];
    for costed in [false, true] {
        let p = QpProblem {
            a: &a,
            b: &b,
            weights: &w,
            ridge: 0.0,
            eq_matrix: None,
            eq_rhs: None,
            lower: Some(&lo),
            upper: Some(&hi),
            singular: Singular::Error,
            costs: Costs {
                half_spreads: costed.then_some(&spread[..]),
                ..Costs::default()
            },
        };
        let s = qp_solve(&p).unwrap();
        assert!((s.x[0] + 1e7).abs() <= 1e-12 * 1e7, "{:?}", s.x);
        assert_eq!(s.x[1], 0.0);
        assert!(s.objective.abs() <= 1e-12);
    }
}
