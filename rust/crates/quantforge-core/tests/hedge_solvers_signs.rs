//! Sign-state and split-stage behaviour of the wave 4a non-smooth solver in `hedge.qp.solve`
//! (`08-hedging/hedge-costs-and-frontier.md`). Written against the surviving mutants of the full
//! cargo-mutants run on `hedge_solvers.rs` (class D of the triage, groups D1 to D8).
//!
//! Every expected value is derived by hand. Most problems use `A = I`, weights 1, so `H = I`,
//! `c = b`, the Jacobi scaling is the identity and the problem separates by coordinate:
//! minimise `sum_j (x_j + b_j)^2 + h_j |x_j|`, whose answer is the soft threshold
//! `x_j = -sign(b_j) max(|b_j| - h_j / 2 - mu m_j, 0)` (`mu` the margin multiplier, scaled as in
//! the solver: `x^T H x / 2 + c^T x`). The solver's release rule at a zero coordinate is
//! `|nu| > room + 1e-12 (1 + |nu|)`, `room = h_j / 2 + mu m_j`, `nu = (H x + c)_j`.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use quantforge_core::hedge_solvers::{Costs, QpProblem, QpSolution, Singular, qp_solve};
use quantforge_core::linalg::Matrix;

fn identity(n: usize) -> Matrix {
    (0..n)
        .map(|i| (0..n).map(|j| if i == j { 1.0 } else { 0.0 }).collect())
        .collect()
}

fn problem<'a>(a: &'a Matrix, b: &'a [f64], w: &'a [f64], costs: Costs<'a>) -> QpProblem<'a> {
    QpProblem {
        a,
        b,
        weights: w,
        ridge: 0.0,
        eq_matrix: None,
        eq_rhs: None,
        lower: None,
        upper: None,
        singular: Singular::Error,
        costs,
    }
}

fn solve(p: &QpProblem) -> QpSolution {
    match qp_solve(p) {
        Ok(s) => s,
        Err(e) => panic!("{}: {}", e.code, e.message),
    }
}

/// D8: zero is a valid cost, impact and margin rate, and a zero margin budget is valid
/// (I-25 3 says non-negative). A zero budget with positive rates allows only `x = 0`.
#[test]
fn zero_costs_and_zero_margin_budget_are_accepted() {
    let a = identity(2);
    let (b, w) = ([1.0, -2.0], [1.0, 1.0]);
    let zeros = [0.0, 0.0];
    // All three lists of zeros and a zero budget on zero rates: the constraint 0 <= 0 always
    // holds and the costs vanish, so the answer is the plain minimiser x = -b.
    let all_zero = Costs {
        half_spreads: Some(&zeros),
        impact: Some(&zeros),
        margin_rates: Some(&zeros),
        margin_limit: Some(0.0),
        ..Costs::default()
    };
    let s = solve(&problem(&a, &b, &w, all_zero));
    assert!(
        (s.x[0] + 1.0).abs() < 1e-14 && (s.x[1] - 2.0).abs() < 1e-14,
        "{:?}",
        s.x
    );
    assert_eq!((s.cost, s.margin), (Some(0.0), Some(0.0)));
    // One zero entry next to a positive one in each list on its own.
    let mixed = [0.0, 0.5];
    for which in 0..3 {
        let mut costs = Costs::default();
        match which {
            0 => costs.half_spreads = Some(&mixed),
            1 => costs.impact = Some(&mixed),
            _ => {
                costs.margin_rates = Some(&mixed);
                costs.margin_limit = Some(10.0);
            }
        }
        assert!(
            qp_solve(&problem(&a, &b, &w, costs)).is_ok(),
            "list {which}"
        );
    }
    // A zero budget with positive rates: sum |x_j| <= 0 forces x = 0 exactly.
    let rates = [1.0, 2.0];
    let budget_zero = Costs {
        margin_rates: Some(&rates),
        margin_limit: Some(0.0),
        ..Costs::default()
    };
    let s = solve(&problem(&a, &b, &w, budget_zero));
    assert_eq!(s.x, vec![0.0, 0.0]);
    assert_eq!(s.margin, Some(0.0));
}

/// D3: the bound rows of the split stage. `x_1 >= 1` wants -1.9, `x_2 <= -1` wants 2.9 and
/// `0 <= x_3 <= 2` wants 4.9 (soft thresholds of `-b` by `h / 2 = 0.1`), so each sits on a bound.
/// A split row with the wrong normal lets the split put `x_1` negative (its orthant then has no
/// point and the split answer would come back); a wrong upper right-hand side makes the split
/// stage infeasible.
#[test]
fn lower_and_upper_bounds_bind_in_the_split_stage() {
    let a = identity(3);
    let (b, w) = ([2.0, -3.0, -5.0], [1.0; 3]);
    let spreads = [0.2; 3];
    let lower = [Some(1.0), None, Some(0.0)];
    let upper = [None, Some(-1.0), Some(2.0)];
    let mut p = problem(
        &a,
        &b,
        &w,
        Costs {
            half_spreads: Some(&spreads),
            ..Costs::default()
        },
    );
    p.lower = Some(&lower);
    p.upper = Some(&upper);
    assert_eq!(solve(&p).x, vec![1.0, -1.0, 2.0]);
}

/// D4: the margin row of the split stage uses each instrument's own rate. With `x_1 + x_2 = 1`
/// and `|x_1| + 3 |x_2| <= 1.5` the feasible set is `x_1` in `[0.75, 1.125]`; the objective
/// `(x_1 + 2)^2 + (x_2 - 3)^2 = 2 (x_1 + 2)^2` on that line wants `x_1 = -2`, so the answer is
/// `(0.75, 0.25)` with the margin binding. Rates mixed across instruments in the split make it
/// cheap to hold `x_2 > 1`, the split then picks the sign state `(-, +)`, which has no feasible
/// point, and the split answer would come back.
#[test]
fn split_margin_row_uses_each_instruments_rate() {
    let a = identity(2);
    let (b, w) = ([2.0, -3.0], [1.0, 1.0]);
    let eq = vec![vec![1.0, 1.0]];
    let rates = [1.0, 3.0];
    let mut p = problem(
        &a,
        &b,
        &w,
        Costs {
            margin_rates: Some(&rates),
            margin_limit: Some(1.5),
            ..Costs::default()
        },
    );
    p.eq_matrix = Some(&eq);
    p.eq_rhs = Some(&[1.0]);
    let s = solve(&p);
    assert!((s.x[0] - 0.75).abs() < 1e-13, "{:?}", s.x);
    assert!((s.x[1] - 0.25).abs() < 1e-13, "{:?}", s.x);
    assert!((s.margin.unwrap() - 1.5).abs() < 1e-13);
}

/// D6: the release rule at a zero coordinate, `h / 2 = 1` for all three instruments.
/// - `x_1 = 1001 - 1 = 1000` sets the kink tolerance to `1e-11 * 1000 = 1e-8`.
/// - `x_2`: `|b_2| - 1 = 1e-9`, below the tolerance, so the sign state starts at 0; `nu = b_2`
///   exceeds the room 1 by `1e-9`, far above `1e-12 (1 + |nu|)`, so it is released towards
///   `-sign(nu) = +` and ends at `1e-9`.
/// - `x_3`: `|b_3| - 1 = 1.5e-12`, inside the window `2e-12 = 1e-12 (1 + 1)`: the rule keeps it
///   at exactly 0 (the true minimiser `1.5e-12` is below the rule's resolution). Any narrower
///   window (`room - ...`, `1e-12 / (1 + |nu|)`, `1e-12 (1 - |nu|)`, `1e-12 |nu|`) releases it.
#[test]
fn zero_coordinate_release_rule() {
    let a = identity(3);
    let b = [-1001.0, -(1.0 + 1e-9), -(1.0 + 1.5e-12)];
    let w = [1.0; 3];
    let spreads = [2.0; 3];
    let s = solve(&problem(
        &a,
        &b,
        &w,
        Costs {
            half_spreads: Some(&spreads),
            ..Costs::default()
        },
    ));
    assert!((s.x[0] - 1000.0).abs() < 1e-12, "{:?}", s.x);
    assert!((s.x[1] - 1e-9).abs() < 1e-15, "{:?}", s.x);
    assert_eq!(s.x[2], 0.0, "{:?}", s.x);
    // The mirror image releases towards the negative side.
    let bm: Vec<f64> = b.iter().map(|v| -v).collect();
    let s = solve(&problem(
        &a,
        &bm,
        &w,
        Costs {
            half_spreads: Some(&spreads),
            ..Costs::default()
        },
    ));
    assert!((s.x[0] + 1000.0).abs() < 1e-12, "{:?}", s.x);
    assert!((s.x[1] + 1e-9).abs() < 1e-15, "{:?}", s.x);
    assert_eq!(s.x[2], 0.0, "{:?}", s.x);
}

/// D6 with an active margin: `h / 2 = 0.5`, rates `(1, 1, 2)`, budget 3.5. With `x_3 = 0`,
/// `|x_1| + |x_2| = (3 - 0.5 - mu) + (2 - 0.5 - mu) = 3.5` gives `mu = 0.25`, so
/// `x = (2.25, -1.25, 0)`; `x_3 = 0` holds because `|b_3| = 0.9 <= 0.5 + 0.25 * 2 = 1`.
#[test]
fn margin_multiplier_widens_the_room_at_zero() {
    let a = identity(3);
    let (b, w) = ([-3.0, 2.0, 0.9], [1.0; 3]);
    let spreads = [1.0; 3];
    let rates = [1.0, 1.0, 2.0];
    let s = solve(&problem(
        &a,
        &b,
        &w,
        Costs {
            half_spreads: Some(&spreads),
            margin_rates: Some(&rates),
            margin_limit: Some(3.5),
            ..Costs::default()
        },
    ));
    assert!((s.x[0] - 2.25).abs() < 1e-13, "{:?}", s.x);
    assert!((s.x[1] + 1.25).abs() < 1e-13, "{:?}", s.x);
    assert_eq!(s.x[2], 0.0, "{:?}", s.x);
}

/// D5: the sign seed `x0 = p - n` and its zero rule. With `h / 2 = 100` the release window is
/// `1e-12 (1 + 100) ~ 1.01e-10`, wider than the kink tolerance `1e-11` (every `|x| < 1`, so the
/// tolerance is absolute). Each coordinate's true minimiser is `5e-11` in size: the split sees it
/// above the tolerance and seeds its sign, and the exact orthant solve returns it. A seed of 0
/// for any of them would keep it at exactly 0, because `5e-11` is inside the release window.
#[test]
fn tiny_coordinates_keep_the_split_sign() {
    let t = 5e-11;
    let a = identity(4);
    let b = [100.0 + t, 100.0 + t, 100.0 + t, -(100.0 + t)];
    let w = [1.0; 4];
    let spreads = [200.0; 4];
    let s = solve(&problem(
        &a,
        &b,
        &w,
        Costs {
            half_spreads: Some(&spreads),
            ..Costs::default()
        },
    ));
    for (j, want) in [-t, -t, -t, t].iter().enumerate() {
        assert!((s.x[j] - want).abs() < 1e-13, "{j}: {:?}", s.x);
    }
}

/// D7: a coordinate pinned at 0 by a wrong sign seed is fixed at 0 and then released. With
/// `A = [[1, -0.6], [0, 0.8]]`, `H = [[1, -0.6], [-0.6, 1]]`, `h / 2 = (1, 0)`, the orthant
/// `(+, +)` gives `x = -H^{-1} (A^T b + (1, 0)) = (1000, 1e-8)` exactly in rationals for
/// `b = (-1000.999999994, -0.750000008)`. With no kink on `x_2` the split has no dead zone there. The split's regularisation `delta ~ 1e-6` shifts
/// `x_2` by about `-delta (H^{-1} x)_2 = -1e-6 * 937.5`, so the split seeds `x_2 < 0`; the
/// orthant solve pins it at 0 with a positive multiplier, the rule fixes it at 0, and the zero
/// test then releases it to `+` (its push `1e-8 * 0.64` is far outside the window).
#[test]
fn pinned_coordinate_is_fixed_then_released() {
    let a: Matrix = vec![vec![1.0, -0.6], vec![0.0, 0.8]];
    let (b, w) = ([-1000.999999994, -0.750000008], [1.0, 1.0]);
    let spreads = [2.0, 0.0];
    let s = solve(&problem(
        &a,
        &b,
        &w,
        Costs {
            half_spreads: Some(&spreads),
            ..Costs::default()
        },
    ));
    assert!((s.x[0] - 1000.0).abs() < 1e-9, "{:?}", s.x);
    assert!((s.x[1] - 1e-8).abs() < 1e-12, "{:?}", s.x);
}
