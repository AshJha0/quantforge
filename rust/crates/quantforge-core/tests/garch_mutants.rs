//! Tests aimed at the garch.rs mutants that survived the stage E mutation run.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
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

/// Independent GARCH(1,1) log-likelihood, written from `05-volatility/garch.md` in the test.
fn hand_loglik(r: &[f64], omega: f64, alpha: f64, beta: f64) -> f64 {
    let mut s2 = r.iter().map(|x| x * x).sum::<f64>() / r.len() as f64;
    let mut l = 0.0;
    for x in r {
        l += -0.5 * ((2.0 * std::f64::consts::PI).ln() + s2.ln() + x * x / s2);
        s2 = omega + alpha * x * x + beta * s2;
    }
    l
}

#[test]
fn loglik_matches_the_spec_worked_example() {
    // garch.md worked example, hand-computed: sigma2 = 2.5e-4, 2.2e-4, next 2.26e-4.
    let l = quantforge_core::garch::loglik(&[0.01, -0.02], 1e-5, 0.1, 0.8, Start::Sample).unwrap();
    assert!((l.loglik - 5.410_998_350_356_715).abs() < 1e-12, "{}", l.loglik);
    assert!((l.variances[0] - 2.5e-4).abs() < 1e-18 && (l.variances[1] - 2.2e-4).abs() < 1e-18);
    assert!((l.next_variance - 2.26e-4).abs() < 1e-18);
}

#[test]
fn fit_is_a_local_maximum_of_an_independent_likelihood() {
    // The fitted loglik equals the hand likelihood at the fitted point, and no nearby point
    // in the stationary region does better by more than the spec's 1e-8 stopping gap.
    for trend in [false, true] {
        let r = series(trend);
        let f = fit(&r, Start::Sample).unwrap();
        let l0 = hand_loglik(&r, f.omega, f.alpha, f.beta);
        assert!((f.loglik - l0).abs() < 1e-9, "{} vs {l0}", f.loglik);
        for (dw, da, db) in [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 1.0, -1.0)] {
            for h in [1e-3, -1e-3] {
                let (w, a, b) = (
                    f.omega * (1.0 + h * dw),
                    f.alpha + h * da * f.alpha.max(1e-3),
                    f.beta + h * db * f.beta.max(1e-3),
                );
                if w <= 0.0 || a < 0.0 || b < 0.0 || a + b >= 1.0 {
                    continue;
                }
                assert!(hand_loglik(&r, w, a, b) <= l0 + 1e-8, "trend {trend} dir {dw} {da} {db} h {h}");
            }
        }
    }
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

#[test]
fn forecast_matches_the_closed_form() {
    // V_L = 1e-5 / 0.1 = 1e-4; E[s2_{n+h}] = 1e-4 + 0.9^(h-1) (2e-4 - 1e-4), by hand.
    let f = quantforge_core::garch::forecast(1e-5, 0.1, 0.8, 2e-4, 3, 252.0).unwrap();
    let want = [2e-4, 1.9e-4, 1.81e-4];
    for (g, w) in f.variances.iter().zip(want) {
        assert!((g - w).abs() < 1e-18, "{g} vs {w}");
    }
    assert!((f.total_variance - 5.71e-4).abs() < 1e-18);
    assert!((f.annualized_vol - (5.71e-4_f64 * 252.0 / 3.0).sqrt()).abs() < 1e-15);
}
