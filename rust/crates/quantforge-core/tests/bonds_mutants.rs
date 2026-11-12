//! Tests aimed at the `bonds.rs` mutants that survived both the unit tests and the golden cases
//! in the stage F mutation sample (PR #31 never reported: its runners were shut down).
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use quantforge_core::bonds::{Bond, conversion_factor, fit_nelson_siegel, futures_basis};
use quantforge_core::dates::Date;

fn d(s: &str) -> Date {
    Date::parse(s).unwrap()
}

#[test]
fn conversion_factor_counts_a_part_month_down() {
    // kills `bonds.rs:405`, `months -= 1` -> `months /= 1`: a delivery day after the maturity day
    // drops the part month, so 2026-12-20 to 2028-08-15 is 19 whole months, as from 2027-01-01.
    let b = Bond::new(d("2028-08-15"), 0.0425, 2);
    for whole in [true, false] {
        let late = conversion_factor(&b, d("2026-12-20"), 0.06, whole).unwrap();
        let next = conversion_factor(&b, d("2027-01-01"), 0.06, whole).unwrap();
        assert_eq!(late, next, "whole months {whole}");
    }
    // In whole months 19 and 20 months give different factors (z = 7 and z = 8).
    let late = conversion_factor(&b, d("2026-12-20"), 0.06, true).unwrap();
    let first = conversion_factor(&b, d("2026-12-01"), 0.06, true).unwrap();
    assert_eq!(first, 0.9726);
    assert_ne!(late, first);
}

#[test]
fn net_basis_vanishes_at_the_implied_repo() {
    // kills `bonds.rs:460`, `dirty * t - weighted` -> `dirty * t / weighted`: financing the bond at
    // its implied repo makes the forward equal the invoice. A coupon (2026-11-15) falls between
    // settlement and delivery, so `weighted` is not zero.
    let (s, dl) = (d("2026-11-09"), d("2026-12-01"));
    let bonds = [
        (Bond::new(d("2033-11-15"), 0.0425, 2), 100.0, 0.904),
        (Bond::new(d("2034-02-15"), 0.04, 2), 90.0, 0.887),
    ];
    let (out, _) = futures_basis(110.0, s, dl, 0.04, &bonds).unwrap();
    for (i, x) in out.iter().enumerate() {
        assert!(
            x.implied_repo.is_finite() && x.implied_repo.abs() < 10.0,
            "{x:?}"
        );
        let (at, _) = futures_basis(110.0, s, dl, x.implied_repo, &bonds).unwrap();
        assert!(
            at[i].net_basis.abs() < 1e-9,
            "bond {i}: {}",
            at[i].net_basis
        );
    }
}

fn ns_row(t: f64, tau: f64) -> [f64; 3] {
    let x = t / tau;
    let e = -(-x).exp_m1() / x;
    [1.0, e, e - (-x).exp()]
}

#[test]
fn fit_raises_the_damping_until_a_step_is_accepted() {
    // kills `bonds.rs:554`, `1.0 + mu` -> `1.0 - mu`, and `bonds.rs:567`, `mu * 10.0` -> `mu / 10.0`.
    // From the start (0.04, 0, 0) the undamped Gauss-Newton step overshoots for this curve, so
    // the fit must raise the Levenberg-Marquardt damping several times before it is accepted.
    // With either mutant the damping never grows and the fit stops about 0.4 away.
    let s = d("2026-11-09");
    let truth = [0.02, 0.08, -0.4];
    let specs = [
        ("2029-11-15", 0.0425),
        ("2031-02-28", 0.0375),
        ("2036-08-15", 0.045),
        ("2055-05-15", 0.0475),
    ];
    let bonds: Vec<(Bond, f64)> = specs
        .iter()
        .map(|(m, c)| {
            let b = Bond::new(d(m), *c, 2);
            let p = b
                .flows(s)
                .unwrap()
                .flows
                .iter()
                .map(|(x, cf)| {
                    let t = (x.serial() - s.serial()) as f64 / 365.0;
                    let r = ns_row(t, 2.5);
                    cf * (-(r[0] * truth[0] + r[1] * truth[1] + r[2] * truth[2]) * t).exp()
                })
                .sum();
            (b, p)
        })
        .collect();
    let (beta, res) = fit_nelson_siegel(s, 2.5, &bonds, None).unwrap();
    for (b, t) in beta.iter().zip(truth) {
        assert!((b - t).abs() < 1e-9, "beta {beta:?}");
    }
    assert!(res.iter().all(|r| r.abs() < 1e-8), "residuals {res:?}");
}
