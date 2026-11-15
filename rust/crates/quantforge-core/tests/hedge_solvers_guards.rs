//! Input guards and rank decisions of `hedge.qp.solve` (`08-hedging/hedge-costs-and-frontier.md`,
//! rulings R6-6.2 and R6-11.13). Written against the surviving mutants of the stage J re-score
//! of `hedge_solvers.rs` (the Jacobi-scaling guard chain and the shape checks of the unscaled
//! path). Every expected value is derived by hand in the comment above it.
//!
//! A shape error must come back as `E_INPUT` whichever path the solver takes: the Jacobi-scaled
//! path truncates lists to `n` while scaling, so a guard that lets a too-long list through turns
//! an `E_INPUT` into a silent answer.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use quantforge_core::hedge_solvers::{Costs, QpProblem, Singular, qp_solve};
use quantforge_core::linalg::Matrix;

fn identity(n: usize) -> Matrix {
    (0..n)
        .map(|i| (0..n).map(|j| if i == j { 1.0 } else { 0.0 }).collect())
        .collect()
}

fn problem<'a>(a: &'a Matrix, b: &'a [f64], w: &'a [f64]) -> QpProblem<'a> {
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
        costs: Costs::default(),
    }
}

fn code(p: &QpProblem) -> String {
    match qp_solve(p) {
        Ok(s) => format!("Ok({:?})", s.x),
        Err(e) => e.code.to_string(),
    }
}

/// Each cost list with `n + 1` entries, all else valid: `E_INPUT` (I-25 1).
#[test]
fn too_long_cost_lists_are_e_input() {
    let a = identity(2);
    let (b, w) = ([1.0, -2.0], [1.0, 1.0]);
    let long = [0.1, 0.1, 0.1];
    let p = problem(&a, &b, &w);
    let hs = QpProblem {
        costs: Costs {
            half_spreads: Some(&long),
            ..Costs::default()
        },
        ..p.clone()
    };
    assert_eq!(code(&hs), "E_INPUT");
    let im = QpProblem {
        costs: Costs {
            impact: Some(&long),
            ..Costs::default()
        },
        ..p.clone()
    };
    assert_eq!(code(&im), "E_INPUT");
    let mr = QpProblem {
        costs: Costs {
            margin_rates: Some(&long),
            margin_limit: Some(10.0),
            ..Costs::default()
        },
        ..p.clone()
    };
    assert_eq!(code(&mr), "E_INPUT");
}

/// A too-short impact list: `E_INPUT`, never an index panic in the scaling.
#[test]
fn too_short_impact_is_e_input() {
    let a = identity(2);
    let (b, w) = ([1.0, -2.0], [1.0, 1.0]);
    let short = [0.1];
    let p = QpProblem {
        costs: Costs {
            impact: Some(&short),
            ..Costs::default()
        },
        ..problem(&a, &b, &w)
    };
    assert_eq!(code(&p), "E_INPUT");
}

/// `lower` or `upper` alone with the wrong length (longer or shorter), the other valid or
/// absent: `E_INPUT`.
#[test]
fn bounds_of_the_wrong_length_are_e_input() {
    let a = identity(2);
    let (b, w) = ([1.0, -2.0], [1.0, 1.0]);
    let long = [Some(-5.0), Some(-5.0), Some(-5.0)];
    let short = [Some(-5.0)];
    let ok = [Some(5.0), Some(5.0)];
    let p = problem(&a, &b, &w);
    for bad in [&long[..], &short[..]] {
        let lo = QpProblem {
            lower: Some(bad),
            upper: Some(&ok),
            ..p.clone()
        };
        assert_eq!(code(&lo), "E_INPUT");
        let lo_only = QpProblem {
            lower: Some(bad),
            ..p.clone()
        };
        assert_eq!(code(&lo_only), "E_INPUT");
        let up: Vec<Option<f64>> = bad.iter().map(|v| v.map(|v| -v)).collect();
        let hi = QpProblem {
            upper: Some(&up),
            ..p.clone()
        };
        assert_eq!(code(&hi), "E_INPUT");
    }
}

/// An equality row with `n + 1` entries: `E_INPUT`; so is `eq_rhs` with a length other than
/// the number of rows.
#[test]
fn equality_shapes_are_e_input() {
    let a = identity(2);
    let (b, w) = ([1.0, -2.0], [1.0, 1.0]);
    let p = problem(&a, &b, &w);
    let wide = vec![vec![1.0, 1.0, 1.0]];
    let rhs1 = [1.0];
    let q = QpProblem {
        eq_matrix: Some(&wide),
        eq_rhs: Some(&rhs1),
        ..p.clone()
    };
    assert_eq!(code(&q), "E_INPUT");
    let row = vec![vec![1.0, 1.0]];
    for rhs in [&[1.0, 2.0][..], &[][..]] {
        let q = QpProblem {
            eq_matrix: Some(&row),
            eq_rhs: Some(rhs),
            ..p.clone()
        };
        assert_eq!(code(&q), "E_INPUT");
    }
}

/// R6-11.13: an empty `eq_matrix` with an empty `eq_rhs` is `E_INPUT`, not "no equalities".
#[test]
fn empty_equality_matrix_is_e_input() {
    let a = identity(2);
    let (b, w) = ([1.0, -2.0], [1.0, 1.0]);
    let empty: Matrix = Vec::new();
    let q = QpProblem {
        eq_matrix: Some(&empty),
        eq_rhs: Some(&[]),
        ..problem(&a, &b, &w)
    };
    assert_eq!(code(&q), "E_INPUT");
}

/// R6-6.2 rank test: singular values of the unit-norm scaled rows against `1e-12` times the
/// largest. With `A = I` the scaling is the identity. Rows `(1, 0)` and `(1, 1.5e-12)`
/// (normalised, the second changes by under 1e-24) have `s1 s2 = |det| = 1.5e-12` and
/// `s1^2 + s2^2 = 2`, so `s1 = sqrt 2` and `s2 = 1.5e-12 / sqrt 2 = 1.06e-12`, which is at or
/// below `1e-12 * sqrt 2 = 1.41e-12`: `E_SINGULAR`. (A limit of `1e-12 / sqrt 2 = 7.1e-13`
/// would accept the pair.) Scaling both rows by 1e6 changes nothing, the rows are normalised.
#[test]
fn nearly_dependent_equality_rows_are_e_singular() {
    let a = identity(2);
    let (b, w) = ([1.0, -2.0], [1.0, 1.0]);
    let rhs = [1.0, 1.0];
    for s in [1.0, 1e6] {
        let rows = vec![vec![s, 0.0], vec![s, s * 1.5e-12]];
        let q = QpProblem {
            eq_matrix: Some(&rows),
            eq_rhs: Some(&rhs),
            ..problem(&a, &b, &w)
        };
        assert_eq!(code(&q), "E_SINGULAR", "scale {s}");
    }
    // Independent rows well apart: the answer is the unique point x = (1, 1) of the equalities.
    let rows = vec![vec![1e6, 0.0], vec![0.0, 1e6]];
    let rhs = [1e6, 1e6];
    let q = QpProblem {
        eq_matrix: Some(&rows),
        eq_rhs: Some(&rhs),
        ..problem(&a, &b, &w)
    };
    let x = qp_solve(&q).unwrap().x;
    assert!(
        (x[0] - 1.0).abs() < 1e-12 && (x[1] - 1.0).abs() < 1e-12,
        "{x:?}"
    );
}

/// `MIN_NORM` on `A = [1 2]`, `b = -1`: every `x` with `x1 + 2 x2 = 1` fits exactly, and the
/// minimum Euclidean norm one is `(1, 2) / 5 = (0.2, 0.4)`. (In Jacobi-scaled variables
/// `D = diag(1, 1/2)` the minimum-norm `y` is `(0.5, 0.5)`, `x = D y = (0.5, 0.25)`: a
/// different point, so `MIN_NORM` must not be solved in scaled variables.)
#[test]
fn min_norm_is_the_minimum_norm_in_the_callers_units() {
    let a = vec![vec![1.0, 2.0]];
    let (b, w) = ([-1.0], [1.0]);
    let q = QpProblem {
        singular: Singular::MinNorm,
        ..problem(&a, &b, &w)
    };
    let x = qp_solve(&q).unwrap().x;
    assert!(
        (x[0] - 0.2).abs() < 1e-12 && (x[1] - 0.4).abs() < 1e-12,
        "{x:?}"
    );
}

/// `MIN_NORM` keeps only eigenvalues above `1e-12` times the spectral scale of `H`.
/// `A = [[1e4, 1e4], [0, 0.01]]`: `H = [[1e8, 1e8], [1e8, 1e8 + 1e-4]]`, eigenvalues about
/// `2e8` and `det / trace = 1e4 / 2e8 = 5e-5`, ratio `2.5e-13`, below `1e-12` (the scaled form
/// `[[1, r], [r, 1]]`, `r = 1 / sqrt(1 + 1e-12)`, has ratio `2.5e-13` too, so rank 1).
/// The small pair is dropped: with `b = (-2e4, -1)`, `c = A^T b = (-2e8, -2e8 - 0.01)`, the
/// answer is `-(c . v1 / l1) v1`, `v1 = (1, 1) / sqrt 2`, `l1 = 2e8`: `x = (1, 1)` to 1e-6.
/// Keeping the small pair would add `(c . v2 / l2) v2`, about `0.007 / 5e-5 = 141` in size.
#[test]
fn min_norm_drops_eigenvalues_below_the_relative_threshold() {
    let a = vec![vec![1e4, 1e4], vec![0.0, 0.01]];
    let (b, w) = ([-2e4, -1.0], [1.0, 1.0]);
    let q = QpProblem {
        singular: Singular::MinNorm,
        ..problem(&a, &b, &w)
    };
    let x = qp_solve(&q).unwrap().x;
    assert!(
        (x[0] - 1.0).abs() < 1e-6 && (x[1] - 1.0).abs() < 1e-6,
        "{x:?}"
    );
}

/// The release rule at a zero coordinate is strict: `|nu| > room + 1e-12 (1 + |nu|)`.
/// `A = [1]`, `b = 1`: `nu = c = 1` at `x = 0`. The half spread `h = 1.999999999996` gives
/// `room = h / 2 = 0.999999999998` and `room + 1e-12 * 2 == 1.0` exactly in binary64 (checked
/// below), a tie, so `x = 0` holds and the answer is exactly `0.0` (not the orthant answer
/// `-(1 - room) = -2e-12`).
#[test]
fn release_rule_is_strict_at_an_exact_tie() {
    let h = 1.999_999_999_996_f64;
    assert_eq!(h / 2.0 + 1e-12 * (1.0 + 1.0), 1.0);
    let a = vec![vec![1.0]];
    let (b, w) = ([1.0], [1.0]);
    let hs = [h];
    let q = QpProblem {
        costs: Costs {
            half_spreads: Some(&hs),
            ..Costs::default()
        },
        ..problem(&a, &b, &w)
    };
    let x = qp_solve(&q).unwrap().x;
    assert!(x[0] == 0.0, "{x:?}");
}
