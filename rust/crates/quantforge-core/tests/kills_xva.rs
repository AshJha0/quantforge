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
    set_exposure(times, &[path.to_vec()], None, 0.5).expect("valid exposure inputs")
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
    assert!(
        close(r.cva, 0.6 * -(-0.02_f64).exp_m1(), 1e-14),
        "{}",
        r.cva
    );
    assert!(
        close(r.dva, 0.5 * -(-0.01_f64).exp_m1(), 1e-14),
        "{}",
        r.dva
    );
    // Hazard 0 and recovery 0 are inside the domain; zero hazard gives zero CVA.
    let zero = Name {
        hazard_rate: 0.0,
        recovery: 0.0,
    };
    assert_eq!(adj(zero, zero).unwrap().cva, 0.0);
}

#[test]
fn adjustment_times_must_be_positive_and_increasing() {
    // G-41: buckets start at 0, so times are t_1 < ... < t_n with t_1 > 0. Either failure alone
    // is E_INPUT: a zero first time on an increasing grid, or a positive grid that decreases.
    let good = Name {
        hazard_rate: 0.02,
        recovery: 0.4,
    };
    let run = |times: Vec<f64>| {
        adjustments(&AdjInputs {
            times,
            discount_factors: vec![1.0, 1.0],
            ee: vec![1.0, 1.0],
            ene: vec![-1.0, -1.0],
            counterparty: good,
            own: good,
            borrow_spread: 0.0,
            lend_spread: 0.0,
            exclude_dva_overlap: false,
            im: None,
            capital: None,
        })
    };
    for times in [
        vec![0.0, 1.0],
        vec![-0.5, 1.0],
        vec![1.0, 0.5],
        vec![1.0, 1.0],
    ] {
        assert_eq!(run(times.clone()).unwrap_err().code, "E_INPUT", "{times:?}");
    }
    // Two buckets (0, 0.5] and (0.5, 1], D = 1, ee = 1, both hazards 0.02:
    // CVA = 0.6 sum (S_c(p) - S_c(t)) S_b(p) = 0.6 [(1 - e^-0.01) + (e^-0.01 - e^-0.02) e^-0.01].
    let r = run(vec![0.5, 1.0]).unwrap();
    let (s1, s2) = ((-0.01_f64).exp(), (-0.02_f64).exp());
    assert!(
        close(r.cva, 0.6 * ((1.0 - s1) + (s1 - s2) * s1), 1e-14),
        "{}",
        r.cva
    );
}

fn curve() -> HwCurve {
    HwCurve::new(
        &[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        &[0.985, 0.97, 0.94, 0.85, 0.70, 0.33],
    )
    .expect("valid curve")
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
        let e = portfolio_hw(
            &c,
            0.05,
            0.01,
            std::slice::from_ref(&leg),
            &[1.0],
            &[q],
            0.02,
            0.4,
        );
        assert_eq!(e.unwrap_err().code, "E_DOMAIN", "q={q}");
    }
    assert!(
        portfolio_hw(
            &c,
            0.05,
            0.01,
            std::slice::from_ref(&leg),
            &[1.0],
            &[1e-9],
            0.02,
            0.4
        )
        .is_ok()
    );
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
        portfolio_hw(
            &c,
            0.05,
            0.01,
            std::slice::from_ref(&leg),
            &ex,
            &[0.5, 0.95, 0.99],
            0.02,
            0.4,
        )
        .unwrap()
    };
    let big = run(1e7);
    for small_n in [1.0, 1e-8] {
        let small = run(small_n);
        let k = small_n / 1e7;
        for i in 0..ex.len() {
            assert!(close(
                small.discounted_ee[i],
                k * big.discounted_ee[i],
                1e-12
            ));
            assert!(close(
                small.discounted_ene[i],
                k * big.discounted_ene[i],
                1e-12
            ));
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
        // The value has a positive density, so the 99% point lies strictly above the 95% point
        // (a bisection that stops at its upper start would return the same bound for both).
        for i in 0..ex.len() {
            assert!(small.pfe[1][i] < small.pfe[2][i], "n={small_n} i={i}");
        }
        assert!(close(small.epe, k * big.epe, 1e-12));
        assert!(close(small.cva, k * big.cva, 1e-12));
    }
}

// ---- KR-257 (confirmed 2026-11-20): the wrong-way-risk root a(t) -------------------------------
// A mutation lane found the Newton iteration from ln h silently unconverged for large |b V|:
// h = 0.01, b = 1, V = 10 on every path gave a = -2.6e33 and cva = 0. Identical V on every path
// has the closed form a_i = ln h - b V_i (exp(a_i + b V_i) = h in every bucket) and
// cva = (1 - R) sum D_i max(V_i, 0) (e^(-h t_(i-1)) - e^(-h t_i)). The other expected values are
// the 50-digit oracle values of datasets/golden/stage_g/wwr_g.json (gen_stage_g_w4b.py).

fn wwr(t: &[f64], v: &[&[f64]], d: &[f64], h: f64, r: f64, b: f64) -> (f64, Vec<f64>) {
    let paths: Vec<Vec<f64>> = v.iter().map(|p| p.to_vec()).collect();
    quantforge_core::xva::wwr_cva_hw(t, &paths, d, h, r, b).expect("valid wwr inputs")
}

fn wwr_code(
    t: &[f64],
    v: &[&[f64]],
    d: &[f64],
    h: f64,
    r: f64,
    b: f64,
) -> (&'static str, Option<String>) {
    let paths: Vec<Vec<f64>> = v.iter().map(|p| p.to_vec()).collect();
    let e = quantforge_core::xva::wwr_cva_hw(t, &paths, d, h, r, b).expect_err("an error");
    (e.code, e.field)
}

fn golden_close(got: f64, want: f64) -> bool {
    (got - want).abs() <= 1e-9 + 1e-12 * want.abs()
}

#[test]
fn wwr_identical_paths_match_the_closed_form_for_large_b_v() {
    for bv in [-700.0_f64, -60.0, -10.0, 10.0, 20.0, 60.0, 700.0] {
        let (cva, a) = wwr(
            &[1.0, 2.0],
            &[&[bv, bv], &[bv, bv]],
            &[0.97, 0.94],
            0.01,
            0.4,
            1.0,
        );
        let exact = 0.01_f64.ln() - bv;
        for x in &a {
            assert!(
                (x - exact).abs() <= 1e-14 * exact.abs().max(1.0),
                "bv {bv}: a {x} vs {exact}"
            );
        }
        let want = 0.6
            * bv.max(0.0)
            * (0.97 * -(-0.01_f64).exp_m1() + 0.94 * ((-0.01_f64).exp() - (-0.02_f64).exp()));
        // The spec cva tolerance, 1e-12 relative: a + b V carries eps |b V| ~ 1.6e-13 at |b V| = 700.
        assert!(
            (cva - want).abs() <= 1e-12 * want,
            "bv {bv}: cva {cva} vs {want}"
        );
    }
}

#[test]
fn wwr_oracle_values_mixed_paths_tiny_and_large_hazards() {
    let p: [&[f64]; 4] = [
        &[30.0, 25.0, 40.0],
        &[-20.0, 5.0, -35.0],
        &[10.0, 40.0, 0.0],
        &[2.0, -8.0, 15.0],
    ];
    let (t, d) = ([0.5, 1.0, 2.0], [0.99, 0.98, 0.955]);
    let rows: [(f64, f64, f64, [f64; 3]); 4] = [
        (
            0.02,
            1.0,
            0.853870876724446,
            [-32.51048602143332, -42.520691113242584, -42.473238050471814],
        ),
        (
            0.02,
            -0.75,
            1.6546995325270438e-06,
            [-17.51048609054749, -8.520749073538585, -28.72323562116894],
        ),
        (
            2.0,
            0.1,
            7.864264489887716,
            [0.3535902179958872, 0.45596668900756426, 3.6961779146431604],
        ),
        (
            1e-10,
            0.3,
            4.351665120150955e-09,
            [-30.6422568451193, -33.65063209843197, -33.64011564101081],
        ),
    ];
    for (h, b, cva_want, a_want) in rows {
        let (cva, a) = wwr(&t, &p, &d, h, 0.4, b);
        assert!(golden_close(cva, cva_want), "h {h} b {b}: cva {cva}");
        for (x, y) in a.iter().zip(a_want) {
            assert!(golden_close(*x, y), "h {h} b {b}: a {x} vs {y}");
        }
    }
    // b V = +700 and -700 on two paths (wwr_g-0018) and hazard 40 (wwr_g-0020).
    let (cva, a) = wwr(&[1.0], &[&[10.0], &[-10.0]], &[0.97], 0.01, 0.4, 70.0);
    assert!(
        golden_close(cva, 0.057909967579841924) && golden_close(a[0], -703.9069851686718),
        "{cva} {a:?}"
    );
    let (cva, a) = wwr(&[1.0], &[&[5.0], &[-5.0], &[1.0]], &[0.97], 40.0, 0.4, 0.2);
    assert!(
        golden_close(cva, 1.164) && golden_close(a[0], 4.661029923801264),
        "{cva} {a:?}"
    );
    // h = 1e-50: a = ln h - 700 = -815.13 (wwr_g-0012).
    let (_, a) = wwr(&[1.0], &[&[10.0], &[10.0]], &[0.97], 1e-50, 0.4, 70.0);
    assert!(golden_close(a[0], -815.1292546497023), "{a:?}");
}

#[test]
fn wwr_limit_and_non_finite_errors_name_their_fields() {
    let one = [0.97];
    assert_eq!(
        wwr_code(&[1.0], &[&[1.0], &[-10.0]], &one, 0.01, 0.4, 70.01),
        ("E_DOMAIN", Some("wwr_b".to_string()))
    );
    assert_eq!(
        wwr_code(&[1.0], &[&[1.0]], &one, 709.0, 0.4, 0.0),
        ("E_NON_FINITE", Some("hazard_rate".to_string()))
    );
    assert_eq!(
        wwr_code(&[1.0], &[&[1.0]], &one, 2e-308, 0.4, 0.0),
        ("E_NON_FINITE", Some("hazard_rate".to_string()))
    );
    // Two errors at once: the domain error comes before the non-finite one (wwr_g-0025).
    assert_eq!(
        wwr_code(&[1.0], &[&[1.0]], &one, 800.0, 1.0, 0.0).0,
        "E_DOMAIN"
    );
    // Inclusive limits: |b V| = 700 and h t = 708 both run; every path defaults, cva = 0.6 0.97 10 / 2.
    let (cva, _) = wwr(&[1.0], &[&[10.0], &[-10.0]], &one, 708.0, 0.4, 70.0);
    assert!((cva - 0.6 * 0.97 * 5.0).abs() <= 1e-12 * cva, "{cva}");
}
