//! Value tests for the late part of `hedge_solvers.rs` (`hedge.integer.solve`,
//! `hedge.minvar.ratio`, the determined-point check of `hedge.qp.solve`), written against the
//! surviving mutants of the stage J re-score at PR #41 head. Every expected value is derived by
//! hand (or with mpmath at 40 digits, stated where used) in the comment above it.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
#![allow(clippy::excessive_precision)] // expected values keep the mpmath digits
use quantforge_core::hedge_solvers::{
    Costs, IntegerProblem, MinVarInput, QpProblem, Singular, integer_solve, minvar_ratio, qp_solve,
};
use quantforge_core::linalg::Matrix;

fn close(got: f64, want: f64, tol: f64, what: &str) {
    assert!(
        (got - want).abs() <= tol * want.abs().max(1.0),
        "{what}: got {got}, want {want}"
    );
}

fn int_problem<'a>(
    a: &'a Matrix,
    b: &'a [f64],
    w: &'a [f64],
    lots: &'a [f64],
) -> IntegerProblem<'a> {
    IntegerProblem {
        a,
        b,
        weights: w,
        ridge: 0.0,
        lot_sizes: lots,
        lower_lots: None,
        upper_lots: None,
    }
}

fn int_code(p: &IntegerProblem) -> String {
    match integer_solve(p) {
        Ok(s) => format!("Ok({:?})", s.lots),
        Err(e) => e.code.to_string(),
    }
}

// ---------------------------------------------------------------- integer_solve

/// The residual is r = A x + b (the hedge offsets b). A = [[1], [0]], b = [2.4, 1], lot 1: the
/// continuous optimum x = -2.4 leaves the second
/// residual, f* = 1. The nearest lot -2 gives f = 0.4^2 + 1 = 1.16, so `rounding_cost` = 0.16.
#[test]
fn integer_rounding_cost_is_objective_minus_continuous() {
    let a: Matrix = vec![vec![1.0], vec![0.0]];
    let b = [2.4, 1.0];
    let w = [1.0, 1.0];
    let s = integer_solve(&int_problem(&a, &b, &w, &[1.0])).unwrap();
    assert_eq!(s.lots, vec![-2]);
    close(s.continuous_objective, 1.0, 1e-14, "continuous objective");
    close(s.objective, 1.16, 1e-14, "objective");
    close(s.rounding_cost, 0.16, 1e-13, "rounding cost");
}

/// Ruling I-7 tie: b = [2.5 + 5e-8, 1000] gives f(-2) = (0.5 + 5e-8)^2 + 1e6 and
/// f(-3) = (0.5 - 5e-8)^2 + 1e6. They differ by 2 * 5e-8 = 1e-7, inside the relative tie band
/// 1e-12 * 1e6 = 1e-6, so the smaller position (-2 lots) wins although f(-3) is lower (r = A x + b).
#[test]
fn integer_relative_tie_prefers_smaller_size() {
    let a: Matrix = vec![vec![1.0], vec![0.0]];
    let b = [2.500_000_05, 1000.0];
    let w = [1.0, 1.0];
    assert_eq!(int_code(&int_problem(&a, &b, &w, &[1.0])), "Ok([-2])");
}

/// I-49 boundary: a relaxed lot of exactly 2^52 is allowed (the limit is strict).
#[test]
fn integer_relaxed_lot_exactly_two_pow_52_is_allowed() {
    let a: Matrix = vec![vec![1.0]];
    let b = [4_503_599_627_370_496.0];
    let w = [1.0];
    assert_eq!(
        int_code(&int_problem(&a, &b, &w, &[1.0])),
        "Ok([-4503599627370496])"
    );
}

/// A = R with R^T R = [[1, rho], [rho, 1]], rho = 1 - 1e-12: the Jacobi-scaled Hessian has
/// eigenvalues 1 +- rho, the smallest 1e-12 against 1e-12 * spectral scale (about 2e-12), so
/// the problem is not strictly convex (ruling I-6).
#[test]
fn integer_near_singular_relative_to_scale_is_singular() {
    let rho: f64 = 1.0 - 1e-12;
    let a: Matrix = vec![vec![1.0, rho], vec![0.0, (1.0 - rho * rho).sqrt()]];
    let b = [1.0, 0.0];
    let w = [1.0, 1.0];
    assert_eq!(
        int_code(&int_problem(&a, &b, &w, &[1.0, 1.0])),
        "E_SINGULAR"
    );
}

/// Each shape and domain guard alone (the others valid).
#[test]
fn integer_guards_each_alone() {
    let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let b = [1.0, 2.0];
    let w = [1.0, 1.0];
    let lots = [1.0, 1.0];
    let short = [None];
    let mut p = int_problem(&a, &b, &w, &lots);
    p.lower_lots = Some(&short);
    assert_eq!(int_code(&p), "E_INPUT", "short lower_lots");
    let mut p = int_problem(&a, &b, &w, &lots);
    p.upper_lots = Some(&short);
    assert_eq!(int_code(&p), "E_INPUT", "short upper_lots");
    assert_eq!(
        int_code(&int_problem(&a, &b, &w, &[1.0])),
        "E_INPUT",
        "short lot_sizes"
    );
    let mut p = int_problem(&a, &b, &w, &lots);
    p.ridge = -1.0;
    assert_eq!(int_code(&p), "E_DOMAIN", "negative ridge");
    assert_eq!(
        int_code(&int_problem(&a, &b, &[1.0, 0.0], &lots)),
        "E_DOMAIN",
        "weight 0"
    );
    assert_eq!(
        int_code(&int_problem(&a, &b, &w, &[1.0, 0.0])),
        "E_DOMAIN",
        "lot 0"
    );
    let lo = [Some(3), None];
    let hi = [Some(2), None];
    let mut p = int_problem(&a, &b, &w, &lots);
    p.lower_lots = Some(&lo);
    p.upper_lots = Some(&hi);
    assert_eq!(int_code(&p), "E_DOMAIN", "crossed bounds");
    // Control: the valid problem solves to the exact lots [-1, -2].
    assert_eq!(int_code(&int_problem(&a, &b, &w, &lots)), "Ok([-1, -2])");
}

// ---------------------------------------------------------------- minvar_ratio

fn mv_code(input: MinVarInput) -> String {
    match minvar_ratio(input) {
        Ok(m) => format!("Ok({:?})", m.hedge),
        Err(e) => e.code.to_string(),
    }
}

/// e = [1, 2, 3, 5], h = [1, 1, 2, 3]: means 2.75 and 1.75, deviations of e [-1.75, -0.75,
/// 0.25, 2.25] and of h [-0.75, -0.75, 0.25, 1.25]. With divisor T - 1 = 3: var(e) = 8.75/3,
/// cov = 4.75/3, var(h) = 2.75/3. Hedge = -cov/var(h) = -19/11; hedged variance
/// (8.75 - 4.75^2/2.75)/3 = 2/11; effectiveness 1 - (2/11)/(35/12) = 1 - 24/385.
#[test]
fn minvar_series_matches_hand_covariance() {
    let e = [1.0, 2.0, 3.0, 5.0];
    let h: Matrix = vec![vec![1.0, 1.0, 2.0, 3.0]];
    let m = minvar_ratio(MinVarInput::Series(&e, &h)).unwrap();
    close(m.hedge[0], -19.0 / 11.0, 1e-14, "hedge");
    close(m.variance_before, 8.75 / 3.0, 1e-14, "variance before");
    close(m.variance_after, 2.0 / 11.0, 1e-13, "variance after");
    close(m.effectiveness, 1.0 - 24.0 / 385.0, 1e-13, "effectiveness");
}

/// k + 2 = 3 observations with one hedge is the minimum allowed (ruling I-8).
/// e = [1, 2, 4], h = [1, 3, 4]: means 7/3 and 8/3; deviations [-4, -1, 5]/3 and [-5, 1, 4]/3;
/// cov = (20 - 1 + 20)/9/2 = 39/18, var(h) = (25 + 1 + 16)/9/2 = 42/18, hedge = -39/42.
#[test]
fn minvar_series_with_exactly_k_plus_two_observations() {
    let e = [1.0, 2.0, 4.0];
    let h: Matrix = vec![vec![1.0, 3.0, 4.0]];
    let m = minvar_ratio(MinVarInput::Series(&e, &h)).unwrap();
    close(m.hedge[0], -39.0 / 42.0, 1e-14, "hedge");
    // Two observations with one hedge are too few.
    let h2: Matrix = vec![vec![1.0, 3.0]];
    assert_eq!(mv_code(MinVarInput::Series(&e[..2], &h2)), "E_INPUT");
}

#[test]
fn minvar_series_shape_guards() {
    let e = [1.0, 2.0, 3.0, 5.0];
    let none: Matrix = vec![];
    assert_eq!(
        mv_code(MinVarInput::Series(&e, &none)),
        "E_INPUT",
        "no hedge"
    );
    let ragged: Matrix = vec![vec![1.0, 1.0, 2.0]];
    assert_eq!(
        mv_code(MinVarInput::Series(&e, &ragged)),
        "E_INPUT",
        "short hedge"
    );
}

/// Hedge block with standard deviations 1e3, 1, 1e-3 and correlations 0.3, -0.2, 0.4; the
/// exposure has variance 4 and covariances [500, -0.3, 2e-4] with the hedges. Expected hedge
/// `-S_hh^{-1} S_he` and hedged variance from mpmath (40 digits).
#[test]
fn minvar_three_hedges_badly_scaled_matches_direct_solve() {
    let s: Matrix = vec![
        vec![4.0, 500.0, -0.3, 2e-4],
        vec![500.0, 1e6, 300.0, -0.2],
        vec![-0.3, 300.0, 1.0, 4e-4],
        vec![2e-4, -0.2, 4e-4, 1e-6],
    ];
    let m = minvar_ratio(MinVarInput::Covariance(&s)).unwrap();
    close(
        m.hedge[0],
        -0.000_903_323_262_839_879_154_1,
        1e-11,
        "hedge 0",
    );
    close(m.hedge[1], 0.861_027_190_332_326_284, 1e-11, "hedge 1");
    close(m.hedge[2], -725.075_528_700_906_344_4, 1e-11, "hedge 2");
    close(
        m.variance_after,
        3.145_015_105_740_181_269,
        1e-11,
        "variance after",
    );
}

/// 2 x 2 hedge block with variances 1e6 and 1e-6: correlation 1.0001 is indefinite, and
/// correlation 1 - 1e-13 leaves a correlation-form pivot 1 - rho^2 of about 2e-13 < 1e-12.
#[test]
fn minvar_badly_scaled_block_decisions() {
    let block =
        |c: f64| -> Matrix { vec![vec![1.0, 0.1, 0.1], vec![0.1, 1e6, c], vec![0.1, c, 1e-6]] };
    assert_eq!(
        mv_code(MinVarInput::Covariance(&block(1.0001))),
        "E_NOT_POSITIVE_DEFINITE"
    );
    assert_eq!(
        mv_code(MinVarInput::Covariance(&block(1.0 - 1e-13))),
        "E_SINGULAR"
    );
}

/// A single hedge with variance 1e-13 is valid: its correlation-form pivot is 1. Hedge =
/// -1e-7/1e-13 = -1e6, hedged variance 1 - (1e-7)^2/1e-13 = 0.9.
#[test]
fn minvar_tiny_hedge_variance_is_not_singular() {
    let s: Matrix = vec![vec![1.0, 1e-7], vec![1e-7, 1e-13]];
    let m = minvar_ratio(MinVarInput::Covariance(&s)).unwrap();
    close(m.hedge[0], -1e6, 1e-12, "hedge");
    close(m.variance_after, 0.9, 1e-12, "variance after");
}

/// `check_symmetric` is relative to the largest entry: largest 1e6, asymmetry 1e-7 is inside
/// 1e-12 * 1e6 = 1e-6 and accepted; asymmetry 1e-5 is rejected.
#[test]
fn minvar_symmetry_tolerance_is_relative() {
    let s = |d: f64| -> Matrix { vec![vec![1e6, 1000.0], vec![1000.0 + d, 4.0]] };
    // The solver reads the lower triangle: hedge = -(1000 + d)/4.
    let m = minvar_ratio(MinVarInput::Covariance(&s(1e-7))).unwrap();
    close(m.hedge[0], -(1000.0 + 1e-7) / 4.0, 1e-14, "hedge");
    assert_eq!(mv_code(MinVarInput::Covariance(&s(1e-5))), "E_INPUT");
}

// ---------------------------------------------------------------- qp dim == 0

fn determined<'a>(
    a: &'a Matrix,
    rhs: &'a [f64],
    lower: Option<&'a [Option<f64>]>,
    upper: Option<&'a [Option<f64>]>,
    costs: Costs<'a>,
) -> QpProblem<'a> {
    QpProblem {
        a,
        b: &[0.0],
        weights: &[1.0],
        ridge: 0.0,
        eq_matrix: Some(a),
        eq_rhs: Some(rhs),
        lower,
        upper,
        singular: Singular::Error,
        costs,
    }
}

fn qp_code(p: &QpProblem) -> String {
    match qp_solve(p) {
        Ok(_) => "Ok".to_string(),
        Err(e) => e.code.to_string(),
    }
}

/// x = [1] x fixes the point; bound or margin limit 1e6 has tolerance 1e-12 * 1e6 = 1e-6, so a
/// point 1e-7 on the wrong side is feasible and one 1e-5 on the wrong side is infeasible.
#[test]
fn determined_point_tolerance_is_relative_to_bound() {
    let a: Matrix = vec![vec![1.0]];
    let lo = [Some(1e6)];
    let up = [Some(1e6)];
    let below = [1e6 - 1e-7];
    let above = [1e6 + 1e-7];
    let far_below = [1e6 - 1e-5];
    let far_above = [1e6 + 1e-5];
    let d = Costs::default;
    assert_eq!(qp_code(&determined(&a, &below, Some(&lo), None, d())), "Ok");
    assert_eq!(qp_code(&determined(&a, &above, None, Some(&up), d())), "Ok");
    assert_eq!(
        qp_code(&determined(&a, &far_below, Some(&lo), None, d())),
        "E_INFEASIBLE"
    );
    assert_eq!(
        qp_code(&determined(&a, &far_above, None, Some(&up), d())),
        "E_INFEASIBLE"
    );
    let rates = [1.0];
    let margin = || Costs {
        margin_rates: Some(&rates),
        margin_limit: Some(1e6),
        ..Costs::default()
    };
    assert_eq!(qp_code(&determined(&a, &above, None, None, margin())), "Ok");
    assert_eq!(
        qp_code(&determined(&a, &far_above, None, None, margin())),
        "E_INFEASIBLE"
    );
}

/// I-44: a hedged variance between -1e-12 `S_00` and 0 is rounding of a perfect hedge and comes
/// back as 0. S = [[1e6 - 1e-7, 1e3], [1e3, 1]]: hedge = -1e3 and hedged variance
/// (1e6 - 1e-7) - 1e6 = -1e-7 (up to one ulp of 1e6), inside -1e-12 * 1e6 = -1e-6.
/// With `S_00` = 1e6 - 1e-5 the hedged variance -1e-5 is beyond the band: not positive definite.
#[test]
fn minvar_negative_hedged_variance_band_is_relative() {
    let s = |v: f64| -> Matrix { vec![vec![v, 1e3], vec![1e3, 1.0]] };
    let m = minvar_ratio(MinVarInput::Covariance(&s(1e6 - 1e-7))).unwrap();
    close(m.hedge[0], -1e3, 1e-15, "hedge");
    assert_eq!(m.variance_after, 0.0);
    assert_eq!(m.effectiveness, 1.0);
    assert_eq!(
        mv_code(MinVarInput::Covariance(&s(1e6 - 1e-5))),
        "E_NOT_POSITIVE_DEFINITE"
    );
}

/// The determined point exactly on the tolerance edge, `l - tol(l)` and `u + tol(u)` computed
/// with the same float expression as the solver, is still feasible (both limits are strict).
#[test]
fn determined_point_exactly_on_tolerance_edge_is_feasible() {
    let a: Matrix = vec![vec![1.0]];
    let lo = [Some(1e6)];
    let up = [Some(1e6)];
    let tol = 1e-12 * 1e6_f64;
    let low_edge = [1e6 - tol];
    let high_edge = [1e6 + tol];
    let d = Costs::default;
    assert_eq!(
        qp_code(&determined(&a, &low_edge, Some(&lo), None, d())),
        "Ok"
    );
    assert_eq!(
        qp_code(&determined(&a, &high_edge, None, Some(&up), d())),
        "Ok"
    );
    let rates = [1.0];
    let margin = Costs {
        margin_rates: Some(&rates),
        margin_limit: Some(1e6),
        ..Costs::default()
    };
    assert_eq!(
        qp_code(&determined(&a, &high_edge, None, None, margin)),
        "Ok"
    );
}

// ---------------------------------------------------------------- refinement of the relaxation

/// Java property seed -11115467 (PR #45 CI 2026-11-17): near-collinear columns, regular after
/// the R6-6.2 scaling.
fn near_singular() -> (Matrix, [f64; 2], [f64; 2]) {
    (
        vec![
            vec![-0.04684068765297382, 0.85014589759939],
            vec![0.06966430897729968, -1.2643959406278287],
        ],
        [-18.480681166672692, -6.198617610506782],
        [1.6701886487345696, 2.992546829483374],
    )
}

/// Square and nonsingular, so the relaxed minimum is exactly 0 (exact rational arithmetic); the
/// normal-equations solve alone gave 3.3e-6, above the integer optimum. The integer objective is
/// a sum of squared residuals of size 1e-3, each the difference of terms of size 1e8 (ulp
/// 1.5e-8), so it is good to about 1e-6 relative: that rounding is what is left, not the solver.
#[test]
fn integer_near_singular_relaxation_is_refined() {
    let (a, b, w) = near_singular();
    let upper = [Some(3), Some(3)];
    let mut p = int_problem(&a, &b, &w, &[10.0, 10.0]);
    p.upper_lots = Some(&upper[..]);
    let s = integer_solve(&p).unwrap();
    assert_eq!(s.lots, vec![-8208927, -452287]);
    assert!(
        s.continuous_objective.abs() <= 1e-12,
        "relaxed {}",
        s.continuous_objective
    );
    let want = 1.5462392586798939e-06;
    assert!(
        (s.objective - want).abs() <= 1e-6 * want,
        "objective {}",
        s.objective
    );
}

/// The same data in x with bounds 10 times the lot bounds (upper 30): the exact minimiser
/// (-82091364.70172344, -4522985.411300044) is inside them, so the minimum is 0; the
/// normal-equations solve alone left 2.3e-6 in C++ and Java.
#[test]
fn qp_near_singular_reaches_exact_minimum() {
    let (a, b, w) = near_singular();
    let upper = [Some(30.0), Some(30.0)];
    for bounds in [Some(&upper[..]), None] {
        let s = qp_solve(&QpProblem {
            a: &a,
            b: &b,
            weights: &w,
            ridge: 0.0,
            eq_matrix: None,
            eq_rhs: None,
            lower: None,
            upper: bounds,
            singular: Singular::Error,
            costs: Costs::default(),
        })
        .unwrap();
        assert!(
            (0.0..=1e-10).contains(&s.objective),
            "objective {}",
            s.objective
        );
        close(s.x[0], -82091364.70172344, 1e-10, "x0");
    }
}

/// The integer ridge is on x = L n, so the relaxation can never be above the integer optimum;
/// lots [3, -12], objective 16.195 as in Python, Java and C++.
#[test]
fn integer_ridge_is_on_positions() {
    let a: Matrix = vec![vec![1.0, 0.3], vec![0.2, 1.0], vec![0.5, 0.5]];
    let b = [-7.3, 4.1, 2.2];
    let w = [1.0, 2.0, 1.0];
    let mut p = int_problem(&a, &b, &w, &[2.5, 0.5]);
    p.ridge = 0.05;
    let s = integer_solve(&p).unwrap();
    assert_eq!(s.lots, vec![3, -12]);
    close(s.objective, 16.195, 1e-12, "objective");
    assert!(s.continuous_objective <= s.objective);
}

/// Probe suite ns2 (2026-11-17): the near-singular data with equalities and on the costed path.
/// Exact minima by fraction arithmetic over every face and orthant. Before `refine_face`, Java and
/// C++ were 2.25e-6 or 2.5e-6 too high on each.
#[test]
fn qp_near_singular_equality_and_costed_paths_are_refined() {
    let (a2, b, w) = near_singular();
    // The first column times 16 keeps the free 2x2 block regular after the R6-6.2 scaling.
    let a3: Matrix = vec![
        vec![16.0 * a2[0][0], a2[0][1], 0.5],
        vec![16.0 * a2[1][0], a2[1][1], 0.375],
    ];
    let near = |got: f64, want: f64, what: &str| {
        let err = (got - want).abs();
        assert!(
            err <= 1e-10 || err <= 1e-10 * want,
            "{what}: got {got}, want {want}"
        );
    };
    let eq: Matrix = vec![vec![0.0, 0.0, 1.0]];
    let lower = [None, None, Some(3.0)];
    for bounds in [None, Some(&lower[..])] {
        // x_2 = 3 by its row, and again with the bound x_2 >= 3 active.
        let s = qp_solve(&QpProblem {
            a: &a3,
            b: &b,
            weights: &w,
            ridge: 0.0,
            eq_matrix: Some(&eq),
            eq_rhs: Some(&[3.0]),
            lower: bounds,
            upper: None,
            singular: Singular::Error,
            costs: Costs::default(),
        })
        .unwrap();
        near(s.objective, 0.0, "equality");
        assert_eq!(s.x[2], 3.0);
    }
    let costed = |a: &Matrix, b: &[f64], w: &[f64], eq: Option<&Matrix>, costs: Costs| {
        qp_solve(&QpProblem {
            a,
            b,
            weights: w,
            ridge: 0.0,
            eq_matrix: eq,
            eq_rhs: eq.map(|_| &[3.0][..]),
            lower: None,
            upper: None,
            singular: Singular::Error,
            costs,
        })
        .unwrap()
    };
    let tiny = [1e-16, 1e-16];
    let s = costed(
        &a2,
        &b,
        &w,
        None,
        Costs {
            half_spreads: Some(&tiny),
            ..Costs::default()
        },
    );
    near(s.objective, 8.661435011274932e-09, "spreads");
    let rates = [1.0, 1.0];
    let s = costed(
        &a2,
        &b,
        &w,
        None,
        Costs {
            margin_rates: Some(&rates),
            margin_limit: Some(1e9),
            ..Costs::default()
        },
    );
    near(s.objective, 0.0, "slack margin");
    let tiny3 = [1e-16, 1e-16, 1e-16];
    let s = costed(
        &a3,
        &b,
        &w,
        Some(&eq),
        Costs {
            half_spreads: Some(&tiny3),
            ..Costs::default()
        },
    );
    near(s.objective, 8.691920544150821e-10, "spreads and equality");
    // A third instrument on its own factor row held at its kink 0 by a spread of 100.
    let ak: Matrix = vec![
        vec![a3[0][0], a3[0][1], 0.0],
        vec![a3[1][0], a3[1][1], 0.0],
        vec![0.0, 0.0, 1.0],
    ];
    let spreads = [1e-16, 1e-16, 100.0];
    let s = costed(
        &ak,
        &[b[0], b[1], -0.5],
        &[w[0], w[1], 1.0],
        None,
        Costs {
            half_spreads: Some(&spreads),
            ..Costs::default()
        },
    );
    near(s.objective, 0.25000000096536956, "kink");
    assert_eq!(s.x[2], 0.0);
}
