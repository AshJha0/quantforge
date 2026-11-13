//! Value tests for `var.rs` (the `VaR` backtest family), written to kill cargo-mutants mutants.
//! Reference values were computed independently in Python (statistics.NormalDist, math.comb)
//! from the textbook formulas; see `program/J0_HANDOVER.md`.

use quantforge_core::var::{
    christoffersen, filtered_historical, historical, kupiec, monte_carlo, parametric, traffic_light,
};

fn close(a: f64, b: f64, tol: f64) -> bool {
    (a - b).abs() <= tol * b.abs().max(1.0)
}

#[test]
fn historical_values_and_domain() {
    let pnl = [3.0, -1.0, -5.0, 2.0, -4.0, 0.0, 1.0, -2.0, -3.0, 4.0];
    // losses sorted: -4..5; c=0.8: k=8 -> 3; w=2 -> ES=(5+4)/2, tail 2
    let r = historical(&pnl, 0.8).unwrap();
    assert_eq!((r.var, r.es, r.tail_count), (3.0, 4.5, 2));
    // c=0.75: w=2.5 -> (5+4+0.5*3)/2.5 = 4.2, tail 3; k=ceil(7.5)=8 -> 3
    let r = historical(&pnl, 0.75).unwrap();
    assert!(
        close(r.es, 4.2, 1e-12) && r.tail_count == 3 && r.var == 3.0,
        "{r:?}"
    );
    // single scenario: w=1-c<1, m=0 = n-1-m index path
    let r = historical(&[-7.0], 0.9).unwrap();
    assert_eq!(r.var, 7.0);
    assert!(close(r.es, 7.0, 1e-12) && r.tail_count == 1);
    assert_eq!(historical(&[], 0.9).unwrap_err().code, "E_INPUT");
    assert_eq!(historical(&pnl, 0.49).unwrap_err().code, "E_DOMAIN");
    assert_eq!(historical(&pnl, 1.0).unwrap_err().code, "E_DOMAIN");
    assert!(historical(&pnl, 0.5).is_ok());
}

#[test]
fn filtered_historical_matches_reference() {
    let r = [
        0.01, -0.02, 0.015, -0.03, 0.005, 0.02, -0.01, 0.0, -0.025, 0.012,
    ];
    let (v, next) = filtered_historical(&r, 1e6, 0.94, 0.9).unwrap();
    assert!(close(next, 0.017029654309905516, 1e-12), "{next}");
    assert!(close(v.var, 25509.445147505245, 1e-10), "{v:?}");
    assert!(close(v.es, 30325.91769219701, 1e-10), "{v:?}");
    assert_eq!(v.tail_count, 1);
    for bad in [0.0, 1.0, -0.5] {
        assert_eq!(
            filtered_historical(&r, 1.0, bad, 0.9).unwrap_err().code,
            "E_DOMAIN"
        );
    }
    assert_eq!(
        filtered_historical(&[], 1.0, 0.9, 0.9).unwrap_err().code,
        "E_INPUT"
    );
    assert_eq!(
        filtered_historical(&[0.0, 0.0], 1.0, 0.9, 0.9)
            .unwrap_err()
            .code,
        "E_DOMAIN"
    );
    assert_eq!(
        filtered_historical(&r, 1.0, 0.9, 0.2).unwrap_err().code,
        "E_DOMAIN"
    );
}

#[test]
fn parametric_matches_reference() {
    let v = parametric(0.1, 2.0, 0.975).unwrap();
    assert!(close(v.var, 3.819927969080107, 1e-7), "{v:?}");
    assert!(close(v.es, 4.575605584402835, 1e-7), "{v:?}");
    assert_eq!(v.tail_count, 0);
    assert_eq!(parametric(0.0, 0.0, 0.99).unwrap_err().code, "E_DOMAIN");
    assert_eq!(parametric(0.0, -1.0, 0.99).unwrap_err().code, "E_DOMAIN");
    assert_eq!(parametric(0.0, 1.0, 0.3).unwrap_err().code, "E_DOMAIN");
}

#[test]
fn monte_carlo_converges_to_analytic() {
    // portfolio sd: w' S w with S=[[4,1.2],[1.2,1]], w=[1,2] -> 4+4.8+4 = 12.8
    let cov = vec![vec![4.0, 1.2], vec![1.2, 1.0]];
    let mean = [0.3, -0.1];
    let w = [1.0, 2.0];
    let v = monte_carlo(&mean, &cov, &w, 200_000, 7, 0.95).unwrap();
    let a = parametric(0.1, 12.8_f64.sqrt(), 0.95).unwrap();
    assert!((v.var - a.var).abs() < 0.05, "{v:?} vs {a:?}");
    assert!((v.es - a.es).abs() < 0.06, "{v:?} vs {a:?}");
    assert_eq!(v.tail_count, 10_000);
    // deterministic for a seed, different for another
    let v2 = monte_carlo(&mean, &cov, &w, 1000, 7, 0.95).unwrap();
    let v3 = monte_carlo(&mean, &cov, &w, 1000, 7, 0.95).unwrap();
    let v4 = monte_carlo(&mean, &cov, &w, 1000, 8, 0.95).unwrap();
    assert_eq!(v2, v3);
    assert_ne!(v2, v4);
    let asym = vec![vec![4.0, 1.2], vec![1.0, 1.0]];
    assert_eq!(
        monte_carlo(&mean, &asym, &w, 10, 1, 0.95).unwrap_err().code,
        "E_DOMAIN"
    );
    assert!(monte_carlo(&mean, &cov, &w, 1, 1, 0.95).is_ok());
}

#[test]
fn kupiec_matches_reference() {
    let (lr, p) = kupiec(250, 7, 0.99).unwrap();
    assert!(close(lr, 5.496990447792683, 1e-10), "{lr}");
    assert!(close(p, 0.01904923089052657, 1e-7), "{p}");
    let (lr0, _) = kupiec(250, 0, 0.99).unwrap();
    assert!(close(lr0, -2.0 * 250.0 * 0.99_f64.ln(), 1e-12), "{lr0}");
    let (lrall, _) = kupiec(5, 5, 0.99).unwrap();
    assert!(close(lrall, -2.0 * 5.0 * 0.01_f64.ln(), 1e-12), "{lrall}");
    for (n, x) in [(0, 0), (10, -1), (10, 11)] {
        assert_eq!(kupiec(n, x, 0.99).unwrap_err().code, "E_DOMAIN");
    }
    assert!(kupiec(1, 1, 0.99).is_ok() && kupiec(10, 10, 0.99).is_ok());
}

#[test]
fn christoffersen_matches_reference() {
    let e = [
        false, true, true, false, false, false, true, true, false, false, false, false,
    ];
    let c = christoffersen(&e, 0.95).unwrap();
    assert_eq!(c.transitions, [5, 2, 2, 2]);
    assert!(close(c.lr_uc, 9.51021085955723, 1e-10), "{c:?}");
    assert!(close(c.lr_ind, 0.499647341157476, 1e-9), "{c:?}");
    assert!(close(c.lr_cc, 10.009858200714707, 1e-10), "{c:?}");
    assert!(close(c.p_uc, 0.0020433168178096706, 1e-6), "{c:?}");
    assert!(close(c.p_ind, 0.47965511840891595, 1e-6), "{c:?}");
    assert!(close(c.p_cc, 0.006704816700485649, 1e-9), "{c:?}");
    // no exceptions: p01=p11 guard path, all LR finite and p = 1 for ind
    let c = christoffersen(&[false; 20], 0.95).unwrap();
    assert_eq!(c.transitions, [19, 0, 0, 0]);
    assert_eq!((c.lr_ind, c.p_ind), (0.0, 1.0));
    assert!(c.lr_uc > 0.0);
    assert_eq!(christoffersen(&[true], 0.95).unwrap_err().code, "E_INPUT");
    assert_eq!(
        christoffersen(&[true, false], 0.2).unwrap_err().code,
        "E_DOMAIN"
    );
}

#[test]
fn traffic_light_zones_and_plus_factor() {
    let cases = [
        (4, 0.8921876269036233, "GREEN", 0.0),
        (5, 0.9588168159301496, "YELLOW", 0.40),
        (9, 0.9997498099312573, "YELLOW", 0.85),
        (10, 0.9999461013709507, "RED", 1.0),
    ];
    for (x, cdf, zone, plus) in cases {
        let (c, z, p) = traffic_light(250, x, 0.99).unwrap();
        assert!(close(c, cdf, 1e-10), "{x}: {c}");
        assert_eq!(z, zone);
        assert_eq!(p, Some(plus));
    }
    for (x, plus) in [(6, 0.50), (7, 0.65), (8, 0.75)] {
        assert_eq!(traffic_light(250, x, 0.99).unwrap().2, Some(plus));
    }
    let (c, z, p) = traffic_light(300, 20, 0.95).unwrap();
    assert!(close(c, 0.9223622551578784, 1e-10), "{c}");
    assert_eq!((z, p), ("GREEN", None));
    assert_eq!(traffic_light(251, 0, 0.99).unwrap().2, None);
    assert_eq!(traffic_light(250, 0, 0.98).unwrap().2, None);
    assert!(close(
        traffic_light(250, 0, 0.99).unwrap().0,
        0.99_f64.powi(250),
        1e-12
    ));
    assert!(traffic_light(10, 50, 0.99).unwrap().0 <= 1.0);
    assert_eq!(traffic_light(0, 0, 0.99).unwrap_err().code, "E_DOMAIN");
    assert_eq!(traffic_light(10, -1, 0.99).unwrap_err().code, "E_DOMAIN");
}

#[test]
fn filtered_lambda_zero_rejected_without_zero_returns() {
    // No zero return, so only the lambda check can reject lambda = 0.
    let r = [0.01, -0.02, 0.015, -0.03];
    assert_eq!(
        filtered_historical(&r, 1.0, 0.0, 0.9).unwrap_err().code,
        "E_DOMAIN"
    );
}

#[test]
fn monte_carlo_size_checks_and_pinned_path() {
    let cov = vec![vec![4.0, 1.2], vec![1.2, 1.0]];
    let mean = [0.3, -0.1];
    assert_eq!(
        monte_carlo(&mean, &cov, &[1.0], 10, 1, 0.95)
            .unwrap_err()
            .code,
        "E_INPUT"
    );
    // Seed 7 is a contract (same seed, same numbers across releases): pin one path so a sign
    // flip of the correlated shock, which leaves the distribution unchanged, is still seen.
    let v = monte_carlo(&mean, &cov, &[1.0, 2.0], 1, 7, 0.5).unwrap();
    assert!((v.var - -0.844901256880429).abs() < 1e-12, "{v:?}");
}

#[test]
fn ragged_covariance_is_an_input_error() {
    let mean = [0.3, -0.1];
    let ragged = vec![vec![4.0], vec![1.2, 1.0]];
    assert_eq!(
        monte_carlo(&mean, &ragged, &[1.0, 2.0], 10, 1, 0.95)
            .unwrap_err()
            .code,
        "E_INPUT"
    );
}

#[test]
fn rounding_noise_in_the_lr_is_floored_to_zero() {
    // x / n == 1 - c exactly in exact arithmetic; in f64 the raw statistic is 2.8e-14.
    assert_eq!(kupiec(250, 25, 0.9).unwrap(), (0.0, 1.0));
}

#[test]
fn christoffersen_all_four_transitions() {
    // Reference: independent Python evaluation of the textbook formulas.
    let e: Vec<bool> = [0, 0, 1, 1, 0, 1, 0, 0, 0, 1, 1, 1, 0, 0]
        .iter()
        .map(|v| *v == 1)
        .collect();
    let r = christoffersen(&e, 0.9).unwrap();
    assert_eq!(r.transitions, [4, 3, 3, 3]);
    assert!(close(r.lr_uc, 10.195362434840565, 1e-12), "{r:?}");
    assert!(close(r.lr_ind, 0.06634794396296151, 1e-10), "{r:?}");
    assert!(close(r.lr_cc, 10.261710378803526, 1e-12), "{r:?}");
    assert!(close(r.p_ind, 0.7967303361691838, 1e-7), "{r:?}");
    assert!(close(r.p_cc, 0.005911502856788296, 1e-10), "{r:?}");
}
