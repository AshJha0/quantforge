//! Tests aimed at the garch.rs mutants that survived the stage E mutation run.
use quantforge_core::garch::{Start, fit, nelder_mead};
use std::cell::Cell;

/// Deterministic return series; `trend` makes the variance grow, so the fit sits near
/// the persistence boundary alpha + beta = 1.
fn series(trend: bool) -> Vec<f64> {
    (0..200_i32)
        .map(|t| {
            let tf = f64::from(t);
            let x = (tf * 0.7 + 0.3).sin() * 1.3 + (tf * 2.3).cos() * 0.4;
            if trend {
                0.01 * x * (1.0 + tf / 20.0)
            } else {
                0.01 * x
            }
        })
        .collect()
}

#[test]
fn fit_keeps_parameters_inside_the_stationary_region() {
    // kills logistic `+` -> `*`, which lets alpha + beta pass 1
    for trend in [false, true] {
        let f = fit(&series(trend), Start::Sample).unwrap();
        assert!(f.omega > 0.0 && f.alpha >= 0.0 && f.beta >= 0.0);
        assert!(f.alpha + f.beta < 1.0, "persistence {}", f.alpha + f.beta);
    }
}

#[test]
fn fit_reaches_the_known_likelihood_maximum() {
    // reference maxima from the unmutated fit; a worse start grid (212 `/` -> `*`) lands lower
    let f0 = fit(&series(false), Start::Sample).unwrap();
    assert!(f0.loglik > 644.929_310_5, "{}", f0.loglik);
    let f1 = fit(&series(true), Start::Sample).unwrap();
    assert!(
        (f1.loglik - 301.295_913_568_263).abs() < 1e-6,
        "{}",
        f1.loglik
    );
}

#[test]
fn nelder_mead_expansion_by_hand() {
    // f = (x - 10)^2 from 0, step 1: expand to 3, expand to 7, then reflect to 11 (expand 15 is worse)
    let (x, v) = nelder_mead(&|u: &[f64]| (u[0] - 10.0).powi(2), &[0.0], 1.0, 3);
    assert_eq!((x[0], v), (11.0, 1.0));
}

#[test]
fn nelder_mead_tie_between_expand_and_reflect_keeps_reflect() {
    // from 0 with step 4: reflect 8 and expand 12 both give 4; `fe < fr` keeps the reflection
    let (x, v) = nelder_mead(&|u: &[f64]| (u[0] - 10.0).powi(2), &[0.0], 4.0, 1);
    assert_eq!((x[0], v), (8.0, 4.0));
}

#[test]
fn nelder_mead_outside_contraction() {
    // f = (x + 1)^2, simplex {0, 2}: reflect -2 ties the best, fr < worst, so contract outside to -1
    let (x, v) = nelder_mead(&|u: &[f64]| (u[0] + 1.0).powi(2), &[0.0], 2.0, 1);
    assert_eq!((x[0], v), (-1.0, 0.0));
}

#[test]
fn nelder_mead_reflection_equal_to_worst_contracts_inside() {
    // f = (x^2 - 1)^2, simplex {0, 2}: reflect -2 equals the worst, so contract inside to +1
    let (x, v) = nelder_mead(&|u: &[f64]| (u[0] * u[0] - 1.0).powi(2), &[0.0], 2.0, 1);
    assert_eq!((x[0], v), (1.0, 0.0));
}

#[test]
fn nelder_mead_stops_when_the_simplex_collapses() {
    // the spread test must break early; without it all 10000 iterations run
    let calls = Cell::new(0usize);
    let f = |u: &[f64]| {
        calls.set(calls.get() + 1);
        (u[0] - 3.0).powi(2) + (u[1] + 1.0).powi(2) + 1.0
    };
    let (x, v) = nelder_mead(&f, &[0.0, 0.0], 0.5, 10_000);
    assert!(calls.get() < 3_000, "calls {}", calls.get());
    assert!((x[0] - 3.0).abs() < 1e-6 && (x[1] + 1.0).abs() < 1e-6 && (v - 1.0).abs() < 1e-12);
}

// Equivalent mutants (no observable change beyond the optimiser's flat-optimum noise):
// garch.rs:211:25 `*` -> `/` in fit: changes one start point only; loglik moves by < 1e-12.
// garch.rs:211:32 `-` -> `+` in fit: same, start point only; loglik within 1e-12.
// garch.rs:213:24 `/` -> `*` in fit: start point only (share odds); same maximum, slower locally.
// garch.rs:213:31 `-` -> `+` in fit: start point only; loglik within 1e-12.
// garch.rs:218:30 `-` -> `+` in fit: restarts run all 20 rounds; result is bit-identical.
