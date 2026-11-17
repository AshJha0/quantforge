//! Behavioural tests for `research_w3.rs` (rulings J-W3-1 to J-W3-14): scenario replay and
//! historical shocks, interpolation backtests, CUSUM / Page-Hinkley / PSI drift detectors and the
//! two-sample KS test. Every expected value is derived by hand in the comment beside it (exact
//! binary fractions where possible), or, for the KS exit-mass fallback, from an independent
//! closed form: two fully separated samples give `p = 2 / C(n + m, n)`.

#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
#![allow(clippy::assert_is_empty)] // `assert!(alarms.is_empty())` reads as the spec: no alarm

use quantforge_core::dates::Date;
use quantforge_core::error::Result;
use quantforge_core::interp::Method;
use quantforge_core::research_w3::{
    Direction, cusum, fsum, historical_shock, interp_loo, ks, page_hinkley, psi, replay,
    surface_holdout,
};

fn code<T: std::fmt::Debug>(r: Result<T>) -> &'static str {
    r.unwrap_err().code
}

fn close(a: f64, b: f64, tol: f64) {
    assert!((a - b).abs() <= tol, "{a} vs {b}");
}

// --- fsum ----------------------------------------------------------------------------------

#[test]
fn fsum_is_correctly_rounded() {
    assert_eq!(fsum(Vec::<f64>::new()), 0.0);
    assert_eq!(fsum([1e16, 1.0, -1e16]), 1.0);
    assert_eq!(fsum([0.1; 10]), 1.0);
    // 1e16 + 1 is a tie; the 1e-16 partial breaks it upwards (Python math.fsum gives 1e16 + 2).
    assert_eq!(fsum([1e16, 1.0, 1e-16]), 10_000_000_000_000_002.0);
    assert_eq!(fsum([1e16, -1.0, -1e-16]), 9_999_999_999_999_998.0);
    assert_eq!(fsum([1e16, 1.0]), 1e16);
    assert_eq!(fsum([3.0, -1.5, 0.25]), 1.75);
}

// --- historical shock ------------------------------------------------------------------------

fn shock_data() -> (Vec<Date>, Vec<f64>, Vec<Vec<f64>>) {
    (
        vec![
            Date::new(2024, 1, 2),
            Date::new(2024, 1, 3),
            Date::new(2024, 1, 4),
        ],
        vec![1.0, 5.0, 10.0],
        vec![
            vec![1.0, 2.0, 3.0],
            vec![1.25, 2.5, 2.75],
            vec![1.5, 2.25, 2.0],
        ],
    )
}

#[test]
fn historical_shock_values() {
    let (d, t, y) = shock_data();
    let s = historical_shock(&d, &t, &y, d[0], d[2]).unwrap();
    assert_eq!(s.start_yields, y[0]);
    assert_eq!(s.end_yields, y[2]);
    assert_eq!(s.shift_bp, vec![50.0, 25.0, -100.0]);
    assert_eq!(s.level_bp, -25.0 / 3.0);
    assert_eq!(s.slope_bp, -150.0);
    // Middle date as start: shift = [25, -25, -75], level -25, slope -100.
    let s = historical_shock(&d, &t, &y, d[1], d[2]).unwrap();
    assert_eq!(s.shift_bp, vec![25.0, -25.0, -75.0]);
    assert_eq!(s.level_bp, -25.0);
    assert_eq!(s.slope_bp, -100.0);
    let s = historical_shock(&d, &t, &y, d[0], d[1]).unwrap();
    assert_eq!(s.shift_bp, vec![25.0, 50.0, -25.0]);
    assert_eq!(s.slope_bp, -50.0);
}

#[test]
fn historical_shock_errors() {
    let (d, t, y) = shock_data();
    assert_eq!(code(historical_shock(&[], &t, &[], d[0], d[2])), "E_INPUT");
    assert_eq!(code(historical_shock(&d, &[], &y, d[0], d[2])), "E_INPUT");
    assert_eq!(
        code(historical_shock(&d, &t, &y[..2], d[0], d[2])),
        "E_INPUT"
    );
    let mut bad = y.clone();
    bad[1].pop();
    assert_eq!(code(historical_shock(&d, &t, &bad, d[0], d[2])), "E_INPUT");
    let dup = vec![d[0], d[1], d[1]];
    assert_eq!(
        code(historical_shock(&dup, &t, &y, d[0], d[1])),
        "E_DATE_ORDER"
    );
    let rev = vec![d[2], d[1], d[0]];
    assert_eq!(
        code(historical_shock(&rev, &t, &y, d[0], d[2])),
        "E_DATE_ORDER"
    );
    assert_eq!(
        code(historical_shock(&d, &t, &y, d[1], d[1])),
        "E_DATE_ORDER"
    );
    assert_eq!(
        code(historical_shock(&d, &t, &y, d[2], d[0])),
        "E_DATE_ORDER"
    );
    let missing = Date::new(2024, 1, 1);
    assert_eq!(
        code(historical_shock(&d, &t, &y, missing, d[2])),
        "E_DOMAIN"
    );
    assert_eq!(
        code(historical_shock(&d, &t, &y, d[0], Date::new(2024, 1, 9))),
        "E_DOMAIN"
    );
    assert_eq!(
        code(historical_shock(&d, &[0.0, 5.0, 10.0], &y, d[0], d[2])),
        "E_DOMAIN"
    );
    assert_eq!(
        code(historical_shock(&d, &[1.0, 5.0, 5.0], &y, d[0], d[2])),
        "E_DOMAIN"
    );
    let mut nan = y.clone();
    nan[0][0] = f64::NAN;
    assert_eq!(code(historical_shock(&d, &t, &nan, d[0], d[2])), "E_DOMAIN");
}

// --- replay --------------------------------------------------------------------------------

#[test]
fn replay_interpolates_scales_and_prices() {
    // Shock knots (1, 10bp) and (3, 30bp): t=0.5 flat 10, t=1 10, t=1.5 15, t=2 20, t=3 30, t=7 30.
    let base = [0.5, 1.0, 1.5, 2.0, 3.0, 7.0];
    let r = replay(
        &base,
        &[1.0; 6],
        &[1.0, 3.0],
        &[10.0, 30.0],
        2.0,
        Some(&[1.0, 2.0, 0.0, 3.0, 0.0, -1.0]),
    )
    .unwrap();
    assert_eq!(r.applied_bp, vec![20.0, 20.0, 30.0, 40.0, 60.0, 60.0]);
    for (s, a) in r.shocked_yields.iter().zip(&r.applied_bp) {
        close(*s, 1.0 + a / 100.0, 1e-15);
    }
    close(r.shocked_yields[3], 1.4, 1e-15);
    // pnl = -(20 + 40 + 120 - 60) = -120.
    assert_eq!(r.pnl, Some(-120.0));
    let r = replay(&[2.0], &[0.0], &[1.0, 3.0], &[10.0, 30.0], 1.0, None).unwrap();
    assert_eq!(r.applied_bp, vec![20.0]);
    close(r.shocked_yields[0], 0.2, 1e-16);
    assert_eq!(r.pnl, None);
    // Three shock knots: t = 4 sits in the second segment (3, 30) -> (5, -10): 10.
    let r = replay(
        &[4.0],
        &[0.0],
        &[1.0, 3.0, 5.0],
        &[10.0, 30.0, -10.0],
        1.0,
        None,
    )
    .unwrap();
    assert_eq!(r.applied_bp, vec![10.0]);
}

#[test]
fn replay_errors() {
    let ok = |bt: &[f64], by: &[f64], st: &[f64], sb: &[f64], dv: Option<&[f64]>| {
        replay(bt, by, st, sb, 1.0, dv)
    };
    assert_eq!(code(ok(&[], &[], &[1.0], &[1.0], None)), "E_INPUT");
    assert_eq!(
        code(ok(&[1.0], &[1.0, 2.0], &[1.0], &[1.0], None)),
        "E_INPUT"
    );
    assert_eq!(code(ok(&[1.0], &[1.0], &[], &[], None)), "E_INPUT");
    assert_eq!(
        code(ok(&[1.0], &[1.0], &[1.0], &[1.0, 2.0], None)),
        "E_INPUT"
    );
    assert_eq!(
        code(ok(&[1.0], &[1.0], &[1.0], &[1.0], Some(&[1.0, 2.0]))),
        "E_INPUT"
    );
    assert_eq!(code(ok(&[0.0], &[1.0], &[1.0], &[1.0], None)), "E_DOMAIN");
    assert_eq!(
        code(ok(&[2.0, 1.0], &[1.0, 1.0], &[1.0], &[1.0], None)),
        "E_DOMAIN"
    );
    assert_eq!(code(ok(&[1.0], &[1.0], &[-1.0], &[1.0], None)), "E_DOMAIN");
    assert_eq!(
        code(ok(&[1.0], &[1.0], &[1.0, 1.0], &[1.0, 1.0], None)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(replay(&[1.0], &[1.0], &[1.0], &[1.0], f64::NAN, None)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(ok(&[1.0], &[1.0], &[1.0], &[1.0], Some(&[f64::INFINITY]))),
        "E_DOMAIN"
    );
}

// --- interpolation backtests -----------------------------------------------------------------

#[test]
fn interp_loo_linear_values() {
    // Leave out x=1: line (0,0)-(2,4) gives 2, error 1. Leave out x=2: (1,1)-(3,10) gives 5.5, error 1.5.
    let b = interp_loo(
        Method::Linear,
        &[0.0, 1.0, 2.0, 3.0],
        &[0.0, 1.0, 4.0, 10.0],
    )
    .unwrap();
    assert_eq!(b.errors, vec![1.0, 1.5]);
    assert_eq!(b.max_abs_error, 1.5);
    close(b.rmse, (3.25f64 / 2.0).sqrt(), 1e-15);
    // A negative error: the max uses |e|. Leave out x=1 of y=(0,-3,0): error 3.
    let b = interp_loo(Method::Linear, &[0.0, 1.0, 2.0], &[0.0, -3.0, 0.0]).unwrap();
    assert_eq!(b.errors, vec![3.0]);
    assert_eq!(b.max_abs_error, 3.0);
    assert_eq!(b.rmse, 3.0);
    // A natural cubic reproduces a straight line exactly.
    let b = interp_loo(
        Method::CubicNatural,
        &[0.0, 1.0, 2.0, 3.0],
        &[1.0, 3.0, 5.0, 7.0],
    )
    .unwrap();
    assert!(b.max_abs_error < 1e-14);
}

#[test]
fn interp_loo_errors() {
    assert_eq!(
        code(interp_loo(Method::Linear, &[0.0, 1.0], &[0.0, 1.0])),
        "E_INPUT"
    );
    assert_eq!(
        code(interp_loo(Method::Linear, &[0.0, 1.0, 2.0], &[0.0, 1.0])),
        "E_INPUT"
    );
    assert_eq!(
        code(interp_loo(
            Method::Linear,
            &[0.0, 2.0, 1.0],
            &[0.0, 1.0, 2.0]
        )),
        "E_INPUT"
    );
    assert_eq!(
        code(interp_loo(
            Method::Linear,
            &[0.0, 1.0, 1.0],
            &[0.0, 1.0, 2.0]
        )),
        "E_INPUT"
    );
    assert_eq!(
        code(interp_loo(
            Method::CubicNatural,
            &[0.0, 1.0, 2.0],
            &[0.0, 1.0, 2.0]
        )),
        "E_INPUT"
    );
    assert_eq!(
        code(interp_loo(
            Method::Tension(1.0),
            &[0.0, 1.0, 2.0],
            &[0.0, 1.0, 2.0]
        )),
        "E_INPUT"
    );
    let x4 = [0.0, 1.0, 2.0, 3.0];
    assert_eq!(code(interp_loo(Method::CubicNotAKnot, &x4, &x4)), "E_INPUT");
    assert!(interp_loo(Method::CubicNotAKnot, &[0.0, 1.0, 2.0, 3.0, 4.0], &[0.0; 5]).is_ok());
    assert!(interp_loo(Method::Pchip, &[0.0, 1.0, 2.0], &[0.0, 1.0, 2.0]).is_ok());
    assert_eq!(
        code(interp_loo(Method::Linear, &[0.0, 1.0, f64::NAN], &[0.0; 3])),
        "E_DOMAIN"
    );
}

#[test]
fn surface_holdout_values() {
    // Kept total variance 0.01 and 0.09 at K=1,3: linear midpoint 0.05; error sqrt(0.05) - 0.2.
    let b = surface_holdout(
        Method::Linear,
        &[1.0, 4.0],
        &[1.0, 2.0, 3.0],
        &[vec![0.1, 0.2, 0.3], vec![0.1, 0.25, 0.3]],
        &[1],
    )
    .unwrap();
    let e = 0.05f64.sqrt();
    close(b.errors[0][0], e - 0.2, 1e-15);
    close(b.errors[1][0], e - 0.25, 1e-15);
    close(b.max_abs_error, 0.25 - e, 1e-15);
    close(
        b.rmse,
        (((e - 0.2).powi(2) + (e - 0.25).powi(2)) / 2.0).sqrt(),
        1e-15,
    );
    // Two held strikes on a flat smile: zero error.
    let b = surface_holdout(
        Method::Linear,
        &[2.0],
        &[1.0, 2.0, 3.0, 4.0],
        &[vec![0.2; 4]],
        &[1, 2],
    )
    .unwrap();
    assert_eq!(b.errors.len(), 1);
    assert_eq!(b.errors[0].len(), 2);
    assert!(b.max_abs_error < 1e-15);
}

#[test]
fn surface_holdout_errors() {
    let k = [1.0, 2.0, 3.0, 4.0];
    let v = vec![vec![0.2; 4]];
    let sh = |e: &[f64], k: &[f64], v: &[Vec<f64>], h: &[i64]| {
        surface_holdout(Method::Linear, e, k, v, h)
    };
    assert_eq!(code(sh(&[], &k, &[], &[1])), "E_INPUT");
    assert_eq!(code(sh(&[1.0, 2.0], &k, &v, &[1])), "E_INPUT");
    assert_eq!(code(sh(&[1.0], &k, &[vec![0.2; 3]], &[1])), "E_INPUT");
    assert_eq!(code(sh(&[1.0], &[1.0, 3.0, 2.0, 4.0], &v, &[1])), "E_INPUT");
    assert_eq!(code(sh(&[1.0], &k, &v, &[])), "E_INPUT");
    assert_eq!(code(sh(&[1.0], &k, &v, &[0])), "E_INPUT");
    assert_eq!(code(sh(&[1.0], &k, &v, &[3])), "E_INPUT");
    assert_eq!(code(sh(&[1.0], &k, &v, &[2, 1])), "E_INPUT");
    assert_eq!(code(sh(&[1.0], &k, &v, &[1, 1])), "E_INPUT");
    assert!(sh(&[1.0], &k, &v, &[2]).is_ok());
    assert_eq!(
        code(surface_holdout(
            Method::CubicNatural,
            &[1.0],
            &k,
            &v,
            &[1, 2]
        )),
        "E_INPUT"
    );
    assert_eq!(code(sh(&[0.0], &k, &v, &[1])), "E_DOMAIN");
    assert_eq!(
        code(sh(&[1.0], &k, &[vec![0.2, 0.2, 0.0, 0.2]], &[1])),
        "E_DOMAIN"
    );
    assert_eq!(
        code(sh(&[1.0], &k, &[vec![0.2, f64::NAN, 0.2, 0.2]], &[1])),
        "E_DOMAIN"
    );
}

// --- CUSUM ---------------------------------------------------------------------------------

#[test]
fn cusum_values() {
    // z = 0, 3, 3 with k=0.5: S+ = 0, 2.5, 5 -> alarm at 2 (up), then reset.
    let (a, sp, sm) = cusum(&[10.0, 16.0, 16.0], 0.5, 4.0, 10.0, 2.0, true).unwrap();
    assert_eq!(
        (a.alarms, a.directions, sp, sm),
        (vec![2], vec![1], 0.0, 0.0)
    );
    let (a, _, _) = cusum(&[0.0, -3.0, -3.0], 0.5, 4.0, 0.0, 1.0, true).unwrap();
    assert_eq!((a.alarms, a.directions), (vec![2], vec![-1]));
    // Repeated alarms with reset; a single one without.
    let x = [3.0; 6];
    let (a, sp, _) = cusum(&x, 0.5, 4.0, 0.0, 1.0, true).unwrap();
    assert_eq!(a.alarms, vec![1, 3, 5]);
    assert_eq!(sp, 0.0);
    let (a, sp, sm) = cusum(&x, 0.5, 4.0, 0.0, 1.0, false).unwrap();
    assert_eq!(
        (a.alarms, a.directions, sp, sm),
        (vec![1], vec![1], 5.0, 0.0)
    );
    // S+ equal to h is not an alarm; the sums carry and floor at zero.
    let (a, sp, sm) = cusum(&[4.5, -1.0], 0.5, 4.0, 0.0, 1.0, true).unwrap();
    assert!(a.alarms.is_empty());
    assert_eq!((sp, sm), (2.5, 0.5));
}

#[test]
fn cusum_errors() {
    assert_eq!(code(cusum(&[], 0.5, 4.0, 0.0, 1.0, true)), "E_INPUT");
    assert_eq!(code(cusum(&[1.0], 0.0, 4.0, 0.0, 1.0, true)), "E_DOMAIN");
    assert_eq!(code(cusum(&[1.0], 0.5, 0.0, 0.0, 1.0, true)), "E_DOMAIN");
    assert_eq!(code(cusum(&[1.0], 0.5, 4.0, 0.0, 0.0, true)), "E_DOMAIN");
    assert_eq!(
        code(cusum(&[1.0], 0.5, f64::NAN, 0.0, 1.0, true)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(cusum(&[1.0], 0.5, 4.0, f64::INFINITY, 1.0, true)),
        "E_DOMAIN"
    );
}

// --- Page-Hinkley --------------------------------------------------------------------------

#[test]
fn page_hinkley_values() {
    // At t=3 the running mean is 2.5: up = 7.5 above its minimum 0 -> alarm (lambda 5).
    let up = [0.0, 0.0, 0.0, 10.0];
    let a = page_hinkley(&up, 0.0, 5.0, Direction::Both, true).unwrap();
    assert_eq!((a.alarms, a.directions), (vec![3], vec![1]));
    let dn = [0.0, 0.0, 0.0, -10.0];
    let a = page_hinkley(&dn, 0.0, 5.0, Direction::Both, true).unwrap();
    assert_eq!((a.alarms, a.directions), (vec![3], vec![-1]));
    assert_eq!(
        page_hinkley(&dn, 0.0, 5.0, Direction::Down, true)
            .unwrap()
            .directions,
        vec![-1]
    );
    assert_eq!(
        page_hinkley(&up, 0.0, 5.0, Direction::Up, true)
            .unwrap()
            .alarms,
        vec![3]
    );
    assert!(
        page_hinkley(&dn, 0.0, 5.0, Direction::Up, true)
            .unwrap()
            .alarms
            .is_empty()
    );
    assert!(
        page_hinkley(&up, 0.0, 5.0, Direction::Down, true)
            .unwrap()
            .alarms
            .is_empty()
    );
    // lambda equal to the excursion: no alarm.
    assert!(
        page_hinkley(&up, 0.0, 7.5, Direction::Both, true)
            .unwrap()
            .alarms
            .is_empty()
    );
    // delta 1: up = -1, -2, -3, 3.5; excursion 6.5 > 5. delta 3: excursion 4.5, no alarm.
    assert_eq!(
        page_hinkley(&up, 1.0, 5.0, Direction::Up, true)
            .unwrap()
            .alarms,
        vec![3]
    );
    assert_eq!(
        page_hinkley(&up, 1.0, 6.4, Direction::Up, true)
            .unwrap()
            .alarms,
        vec![3]
    );
    assert!(
        page_hinkley(&up, 1.0, 6.5, Direction::Up, true)
            .unwrap()
            .alarms
            .is_empty()
    );
    assert!(
        page_hinkley(&up, 3.0, 5.0, Direction::Up, true)
            .unwrap()
            .alarms
            .is_empty()
    );
    // Restart after an alarm: the pattern repeats and alarms again at 7; without reset, stop at 3.
    let two = [0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0];
    assert_eq!(
        page_hinkley(&two, 0.0, 5.0, Direction::Both, true)
            .unwrap()
            .alarms,
        vec![3, 7]
    );
    assert_eq!(
        page_hinkley(&two, 0.0, 5.0, Direction::Both, false)
            .unwrap()
            .alarms,
        vec![3]
    );
    // Running mean, not the first value: a level shift at the start is absorbed (mean = 5 at t=1).
    // x = 10, 0: mean 10, 5; up = 0, -5; dn = 0, 5 -> dn excursion 5, not above lambda 5.
    assert!(
        page_hinkley(&[10.0, 0.0], 0.0, 5.0, Direction::Both, true)
            .unwrap()
            .alarms
            .is_empty()
    );
    assert_eq!(
        page_hinkley(&[10.0, 0.0], 0.0, 4.9, Direction::Both, true)
            .unwrap()
            .directions,
        vec![-1]
    );
}

#[test]
fn page_hinkley_errors() {
    assert_eq!(
        code(page_hinkley(&[], 0.0, 1.0, Direction::Both, true)),
        "E_INPUT"
    );
    assert_eq!(
        code(page_hinkley(&[1.0], -0.1, 1.0, Direction::Both, true)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(page_hinkley(&[1.0], 0.0, 0.0, Direction::Both, true)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(page_hinkley(&[f64::NAN], 0.0, 1.0, Direction::Both, true)),
        "E_DOMAIN"
    );
    assert!(page_hinkley(&[1.0], 0.0, 1.0, Direction::Both, true).is_ok());
}

// --- PSI -----------------------------------------------------------------------------------

#[test]
fn psi_values() {
    let r: Vec<f64> = (0..10).rev().map(f64::from).collect();
    // Two bins, edge r[4] = 4 (values <= 4 left). Test shares 3/4, 1/4: psi = 0.25 ln 3.
    let p = psi(&r, &[0.0, 0.0, 4.0, 9.0], 2, 0.25).unwrap();
    assert_eq!(p.reference_shares, vec![0.5, 0.5]);
    assert_eq!(p.test_shares, vec![0.75, 0.25]);
    close(p.psi, 0.25 * 3f64.ln(), 1e-15);
    assert!(p.alarm);
    assert!(!psi(&r, &[0.0, 0.0, 4.0, 9.0], 2, 0.3).unwrap().alarm);
    // The edge value goes left; the empty bin floors at 1e-4.
    let p = psi(&r, &[4.0, 4.0], 2, 0.25).unwrap();
    assert_eq!(p.test_shares, vec![1.0, 1e-4]);
    close(
        p.psi,
        0.5 * 2f64.ln() + (1e-4 - 0.5) * (2e-4f64).ln(),
        1e-14,
    );
    let p = psi(&r, &[4.5, 5.0], 2, 0.25).unwrap();
    assert_eq!(p.test_shares, vec![1e-4, 1.0]);
    // Three bins: edges r[3] = 3 and r[6] = 6 (type-1 quantiles ceil(10/3), ceil(20/3)).
    let p = psi(&r, &[3.0, 6.0, 7.0], 3, 0.25).unwrap();
    assert_eq!(p.reference_shares, vec![0.4, 0.3, 0.3]);
    let third = 1.0 / 3.0;
    assert_eq!(p.test_shares, vec![third, third, third]);
    let want = (third - 0.4) * (third / 0.4).ln() + 2.0 * (third - 0.3) * (third / 0.3).ln();
    close(p.psi, want, 1e-15);
    assert_eq!(p.alarm, want > 0.25);
}

#[test]
fn psi_errors() {
    let r: Vec<f64> = (0..10).map(f64::from).collect();
    assert_eq!(code(psi(&r, &r, 1, 0.25)), "E_INPUT");
    assert_eq!(code(psi(&r[..2], &r, 3, 0.25)), "E_INPUT");
    assert_eq!(code(psi(&r, &r[..2], 3, 0.25)), "E_INPUT");
    assert!(psi(&r[..3], &r[..3], 3, 0.25).is_ok());
    assert_eq!(code(psi(&r, &r, 2, 0.0)), "E_DOMAIN");
    assert_eq!(code(psi(&r, &r, 2, f64::NAN)), "E_DOMAIN");
    assert_eq!(code(psi(&[f64::NAN, 1.0], &r, 2, 0.25)), "E_DOMAIN");
}

// --- KS ------------------------------------------------------------------------------------

/// C(n, k) in binary64 by the product formula: independent of the crate's integer and walk paths.
fn binom_f64(n: u64, k: u64) -> f64 {
    (1..=k).fold(1.0, |c, i| c * (n - k + i) as f64 / i as f64)
}

#[test]
fn ks_exact_path() {
    // Separated samples: only the two corner paths leave the band, p = 2 / C(n + m, n).
    let (d, p, rej) = ks(&[3.0, 1.0, 2.0], &[6.0, 4.0, 5.0], 0.1).unwrap();
    assert_eq!(d, 1.0);
    close(p, 0.1, 1e-16);
    assert!(rej);
    assert!(!ks(&[1.0, 2.0, 3.0], &[4.0, 5.0, 6.0], 0.09).unwrap().2);
    // n != m: D scaled = 6 = n m, p = 2 / C(5, 2) = 0.2.
    let (d, p, _) = ks(&[1.0, 2.0], &[3.0, 4.0, 5.0], 0.05).unwrap();
    assert_eq!(d, 1.0);
    close(p, 0.2, 1e-16);
    let (d, p, _) = ks(&[5.0, 6.0, 7.0, 8.0], &[1.0, 2.0, 3.0, 4.0], 0.05).unwrap();
    assert_eq!(d, 1.0);
    close(p, 2.0 / 70.0, 1e-16);
    // Interleaved: D = 1/2 and every path reaches it, so p = 1.
    let (d, p, rej) = ks(&[1.0, 3.0], &[2.0, 4.0], 0.5).unwrap();
    assert_eq!((d, p, rej), (0.5, 1.0, false));
    // Ties step together: merged 1 | 2,2 | 3 gives |i m - j n| = 2, 2, 0 -> D = 1/2.
    assert_eq!(ks(&[1.0, 2.0], &[2.0, 3.0], 0.5).unwrap().0, 0.5);
    // Identical samples: D = 0 and p = 1.
    assert_eq!(
        ks(&[1.0, 2.0], &[1.0, 2.0], 0.5).unwrap(),
        (0.0, 1.0, false)
    );
    // n=4, m=4, a = {1,2,3,5}, b = {4,6,7,8}: D = 3/4. Paths with max |i - j| >= 3 among C(8,4)=70:
    // by reflection, #(max(i-j) >= 3) = C(8,1) = 8, same for j - i, and none reach both: p = 16/70.
    let (d, p, _) = ks(&[1.0, 2.0, 3.0, 5.0], &[4.0, 6.0, 7.0, 8.0], 0.05).unwrap();
    assert_eq!(d, 0.75);
    close(p, 16.0 / 70.0, 1e-15);
}

#[test]
fn ks_exit_mass_fallback_matches_closed_form() {
    // n + m = 140 > 124: C(140, 70) overflows 128 bits, so the binary64 exit-mass walk runs.
    for (n, m) in [(70usize, 70usize), (60, 80), (100, 30)] {
        let a: Vec<f64> = (0..n).map(|i| i as f64).collect();
        let b: Vec<f64> = (0..m).map(|i| 1000.0 + i as f64).collect();
        let (d, p, rej) = ks(&a, &b, 0.05).unwrap();
        assert_eq!(d, 1.0);
        let want = 2.0 / binom_f64((n + m) as u64, n as u64);
        assert!(((p - want) / want).abs() < 1e-11, "{n} {m}: {p} vs {want}");
        assert!(rej);
    }
    // Identical large samples: D = 0, p = 1 on the fallback path too.
    let a: Vec<f64> = (0..70).map(f64::from).collect();
    assert_eq!(ks(&a, &a, 0.05).unwrap(), (0.0, 1.0, false));
    // Interleaved large samples (a_i = 2i, b_i = 2i + 1): D = 1/70; the walk gives p = 1.
    let b: Vec<f64> = (0..70).map(|i| 2.0 * f64::from(i) + 1.0).collect();
    let a2: Vec<f64> = (0..70).map(|i| 2.0 * f64::from(i)).collect();
    let (d, p, rej) = ks(&a2, &b, 0.05).unwrap();
    close(d, 1.0 / 70.0, 1e-17);
    close(p, 1.0, 1e-12);
    assert!(!rej);
}

#[test]
fn ks_errors() {
    assert_eq!(code(ks(&[], &[1.0], 0.05)), "E_INPUT");
    assert_eq!(code(ks(&[1.0], &[], 0.05)), "E_INPUT");
    assert_eq!(code(ks(&[1.0], &[2.0], 0.0)), "E_DOMAIN");
    assert_eq!(code(ks(&[1.0], &[2.0], 1.0)), "E_DOMAIN");
    assert_eq!(code(ks(&[f64::NAN], &[2.0], 0.5)), "E_DOMAIN");
    assert_eq!(code(ks(&[1.0], &[2.0], f64::NAN)), "E_DOMAIN");
    // n = m = 1: D = 1, p = 2 / C(2, 1) = 1; level just below 1 does not reject.
    assert_eq!(ks(&[1.0], &[2.0], 0.999).unwrap(), (1.0, 1.0, false));
}
