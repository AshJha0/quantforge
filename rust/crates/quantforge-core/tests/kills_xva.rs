//! Value and domain tests for `xva.rs` and `xva_port.rs`, written to kill the cargo-mutants
//! survivors of the PR #59 mutation-report sample (run 44727394791, rust xva 30 of 40).
//!
//! The file name must not start with `xva`: the pull-request sample seed hashes `**/xva*.rs`
//! (`conformance/mutation/content_seed.py`), so a test file matching it would redraw the sample.
//!
//! Every expected value is a hand calculation from `specifications/06-risk/xva-framework.md`
//! (G-40, G-41), `xva-exposure-portfolio.md` (G-42) or an exact property (linearity in the
//! notional); the derivation is in the comment next to each assertion.

use quantforge_core::shortrate::{HwCurve, SwapLeg};
use quantforge_core::xva::{AdjInputs, Name, adjustments, set_exposure};
use quantforge_core::xva_port::portfolio_hw;

fn close(a: f64, b: f64, tol: f64) -> bool {
    (a - b).abs() <= tol * b.abs().max(f64::MIN_POSITIVE)
}

fn one_path(times: &[f64], path: &[f64]) -> quantforge_core::xva::SetExposure {
    set_exposure(times, &[path.to_vec()], None, 0.5).unwrap()
}

#[test]
fn effective_epe_on_a_grid_not_starting_at_zero() {
    // G-40: effective EPE averages eee over the grid points within one year of t_0. Grid from
    // t_0 = 1: points 1.25, 1.5, 2.0 count, 2.5 does not. One path, no CSA, so ee = eee = path.
    // acc = 2 * 0.25 + 3 * 0.25 + 4 * 0.5 = 3.25 over (2.0 - 1.0) = 1 year: 3.25.
    let r = one_path(&[1.0, 1.25, 1.5, 2.0, 2.5], &[1.0, 2.0, 3.0, 4.0, 5.0]);
    assert!(close(r.effective_epe, 3.25, 1e-15), "{}", r.effective_epe);
    // epe = (3.25 + 5 * 0.5) / (2.5 - 1.0).
    assert!(close(r.epe, 5.75 / 1.5, 1e-15), "{}", r.epe);
}

#[test]
fn effective_epe_boundaries() {
    // The point exactly one year out counts: ee = (2, 6, 10), effective EPE = 6 * 1 / 1.
    let r = one_path(&[0.0, 1.0, 2.0], &[2.0, 6.0, 10.0]);
    assert_eq!(r.effective_epe, 6.0);
    assert_eq!(r.epe, 8.0); // (6 + 10) / 2
    // No point within one year: eee_0 = ee_0 = 1 (the oracle's rule, gen_stage_g_w4b.py).
    let r = one_path(&[0.0, 2.0], &[1.0, 5.0]);
    assert_eq!(r.effective_epe, 1.0);
    // Non-monotone ee (4, 1, 3, 2): eee = (4, 4, 4, 4), effective EPE 4.
    let r = one_path(&[0.0, 0.25, 0.5, 1.0], &[4.0, 1.0, 3.0, 2.0]);
    assert_eq!(r.effective_epe, 4.0);
}

fn adj(cpty: Name, own: Name) -> quantforge_core::error::Result<quantforge_core::xva::Adjustments> {
    adjustments(&AdjInputs {
        times: vec![1.0],
        discount_factors: vec![1.0],
        ee: vec![1.0],
        ene: vec![-1.0],
        counterparty: cpty,
        own,
        borrow_spread: 0.0,
        lend_spread: 0.0,
        exclude_dva_overlap: false,
        im: None,
        capital: None,
    })
}

#[test]
fn adjustment_names_need_both_hazard_and_recovery_in_domain() {
    // G-41: hazard_rate >= 0 AND recovery in [0, 1), so either one out of range is E_DOMAIN.
    let good = Name {
        hazard_rate: 0.02,
        recovery: 0.4,
    };
    let bad_h = Name {
        hazard_rate: -0.01,
        recovery: 0.4,
    };
    let bad_r = Name {
        hazard_rate: 0.02,
        recovery: 1.0,
    };
    for (c, o) in [(bad_h, good), (bad_r, good), (good, bad_h), (good, bad_r)] {
        assert_eq!(adj(c, o).unwrap_err().code, "E_DOMAIN");
    }
    // One bucket (0, 1], D = 1, ee = 1, |ene| = 1, own hazard 0.01 and recovery 0.5:
    // CVA = 0.6 (1 - e^-0.02) e^0 and DVA = 0.5 (1 - e^-0.01) e^0.
    let own = Name {
        hazard_rate: 0.01,
        recovery: 0.5,
    };
    let r = adj(good, own).unwrap();
    assert!(close(r.cva, 0.6 * -(-0.02_f64).exp_m1(), 1e-14), "{}", r.cva);
    assert!(close(r.dva, 0.5 * -(-0.01_f64).exp_m1(), 1e-14), "{}", r.dva);
    // Hazard 0 and recovery 0 are inside the domain; zero hazard gives zero CVA.
    let zero = Name {
        hazard_rate: 0.0,
        recovery: 0.0,
    };
    assert_eq!(adj(zero, zero).unwrap().cva, 0.0);
}

fn curve() -> HwCurve {
    HwCurve::new(
        &[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        &[0.985, 0.97, 0.94, 0.85, 0.70, 0.33],
    )
    .unwrap()
}

#[test]
fn pfe_quantiles_must_be_strictly_inside_zero_one() {
    // G-42: pfe_quantiles in the open interval (0, 1), else E_DOMAIN.
    let pay = [1.0, 2.0, 3.0];
    let leg = SwapLeg {
        start: 0.0,
        pay: &pay,
        fixed_rate: 0.03,
        payer: true,
        notional: 1.0,
    };
    let c = curve();
    for q in [0.0, 1.0, -0.5] {
        let e = portfolio_hw(&c, 0.05, 0.01, std::slice::from_ref(&leg), &[1.0], &[q], 0.02, 0.4);
        assert_eq!(e.unwrap_err().code, "E_DOMAIN", "q={q}");
    }
    assert!(portfolio_hw(&c, 0.05, 0.01, std::slice::from_ref(&leg), &[1.0], &[1e-9], 0.02, 0.4).is_ok());
}

#[test]
fn exposure_profiles_are_linear_in_the_notional() {
    // The deflated value is linear in the notional (each trade enters as sign x notional), so
    // EE, ENE and every PFE quantile scale by the notional ratio exactly, up to rounding and the
    // relative bisection tolerance. Checked from 1e7 down to 1e-8, where the PFE values are near
    // 1e-10 and an absolute tolerance would stop the bisection at its first step.
    let pay = [1.0, 2.0, 3.0, 4.0, 5.0];
    let ex = [1.0, 2.0, 3.0, 4.0];
    let c = curve();
    let run = |notional: f64| {
        let leg = SwapLeg {
            start: 0.0,
            pay: &pay,
            fixed_rate: 0.03,
            payer: true,
            notional,
        };
        portfolio_hw(&c, 0.05, 0.01, std::slice::from_ref(&leg), &ex, &[0.5, 0.95, 0.99], 0.02, 0.4)
            .unwrap()
    };
    let big = run(1e7);
    for small_n in [1.0, 1e-8] {
        let small = run(small_n);
        let k = small_n / 1e7;
        for i in 0..ex.len() {
            assert!(close(small.discounted_ee[i], k * big.discounted_ee[i], 1e-12));
            assert!(close(small.discounted_ene[i], k * big.discounted_ene[i], 1e-12));
            for q in 0..3 {
                assert!(
                    close(small.pfe[q][i], k * big.pfe[q][i], 1e-9),
                    "n={small_n} q={q} i={i}: {} vs {}",
                    small.pfe[q][i],
                    k * big.pfe[q][i]
                );
                if q > 0 {
                    // The 95% and 99% points sit above zero, so they come from the bisection.
                    assert!(small.pfe[q][i] > 0.0);
                }
            }
        }
        assert!(close(small.epe, k * big.epe, 1e-12));
        assert!(close(small.cva, k * big.cva, 1e-12));
    }
}
