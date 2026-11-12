//! Stage I wave 3 cross-asset hedge (`08-hedging/cross-asset-hedge.md`): unit tests and the
//! property tests the spec names.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use proptest::prelude::*;
use quantforge_core::hedge_crossasset::{XaKind, XaLeg, XaMarket, ZeroCurve, crossasset_solve};

fn leg(kind: XaKind, fields: &[(&str, f64)]) -> XaLeg {
    XaLeg {
        kind,
        fields: fields.iter().map(|(k, v)| ((*k).to_string(), *v)).collect(),
    }
}

fn zcb(t: f64, notional: f64) -> XaLeg {
    leg(XaKind::Zcb, &[("expiry_years", t), ("notional", notional)])
}

fn market() -> XaMarket {
    XaMarket {
        spot: 4000.0,
        dividend_yield: 0.015,
        volatility: 0.18,
        curve: ZeroCurve {
            times: vec![1.0, 2.0, 5.0, 10.0],
            zero_rates: vec![0.03, 0.032, 0.035, 0.038],
        },
    }
}

fn book() -> Vec<(XaLeg, f64)> {
    vec![
        (
            leg(XaKind::Call, &[("strike", 4200.0), ("expiry_years", 1.5)]),
            -50.0,
        ),
        (
            leg(XaKind::Put, &[("strike", 3600.0), ("expiry_years", 3.0)]),
            30.0,
        ),
        (zcb(7.0, 2e6), 1.0),
    ]
}

fn hedges() -> Vec<XaLeg> {
    vec![
        leg(
            XaKind::Forward,
            &[("strike", 4000.0), ("expiry_years", 1.0)],
        ),
        zcb(1.0, 1e6),
        zcb(2.0, 1e6),
        zcb(5.0, 1e6),
        zcb(10.0, 1e6),
    ]
}

fn code<T: std::fmt::Debug>(r: quantforge_core::error::Result<T>) -> &'static str {
    r.unwrap_err().code
}

#[test]
fn key_rate_risk_is_shared_between_neighbouring_pillars() {
    // A 7Y bond sits between the 5Y and 10Y pillars; a 0.5Y bond is flat on pillar 1.
    let w = [1.0; 5];
    let one = [(zcb(7.0, 1e6), 1.0), (zcb(0.5, 1e6), 1.0)];
    let s = crossasset_solve(&market(), &one, &hedges(), &w, 0.0).unwrap();
    assert_eq!(s.book_risk[0], 0.0);
    assert!(s.book_risk[1] < 0.0 && s.book_risk[2] == 0.0);
    assert!(s.book_risk[3] < 0.0 && s.book_risk[4] < 0.0);
    // 7Y is 2/5 of the way from 5Y to 10Y: three fifths of the risk on 5Y, to first order.
    let ratio = s.book_risk[3] / s.book_risk[4];
    assert!((ratio - 1.5).abs() < 1e-3, "{ratio}");
}

#[test]
fn crossasset_checks_in_order() {
    let (m, b, h, w) = (market(), book(), hedges(), [1.0; 5]);
    let mut bad = market();
    bad.curve.times = vec![1.0, 1.0, 5.0, 10.0];
    assert_eq!(code(crossasset_solve(&bad, &b, &h, &w, 0.0)), "E_INPUT");
    bad.curve.times = vec![0.0, 2.0, 5.0, 10.0];
    assert_eq!(code(crossasset_solve(&bad, &b, &h, &w, 0.0)), "E_INPUT");
    let mut nan = market();
    nan.curve.zero_rates[1] = f64::NAN;
    assert_eq!(code(crossasset_solve(&nan, &b, &h, &w, 0.0)), "E_DOMAIN");
    let striked = [leg(
        XaKind::Zcb,
        &[("expiry_years", 1.0), ("notional", 1.0), ("strike", 1.0)],
    )];
    assert_eq!(
        code(crossasset_solve(&m, &b, &striked, &[1.0; 5], 0.0)),
        "E_INPUT"
    );
    assert_eq!(code(crossasset_solve(&m, &[], &h, &w, 0.0)), "E_INPUT");
    assert_eq!(
        code(crossasset_solve(&m, &b, &h, &[1.0; 4], 0.0)),
        "E_INPUT"
    );
    let late = [zcb(10.5, 1e6)];
    assert_eq!(code(crossasset_solve(&m, &b, &late, &w, 0.0)), "E_INPUT");
    let mut flat = market();
    flat.volatility = 0.0;
    assert_eq!(code(crossasset_solve(&flat, &b, &h, &w, 0.0)), "E_DOMAIN");
    assert_eq!(
        code(crossasset_solve(
            &m,
            &b,
            &h,
            &[1.0, 0.0, 1.0, 1.0, 1.0],
            0.0
        )),
        "E_DOMAIN"
    );
    assert_eq!(code(crossasset_solve(&m, &b, &h, &w, -1.0)), "E_DOMAIN");
    let twice = [leg(XaKind::Underlying, &[]), leg(XaKind::Underlying, &[])];
    assert_eq!(
        code(crossasset_solve(&m, &b, &twice, &w, 0.0)),
        "E_SINGULAR"
    );
    assert!(crossasset_solve(&m, &b, &twice, &w, 1e-3).is_ok());
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(64))]

    #[test]
    fn square_hedge_leaves_no_risk_and_weights_scale_out(
        quantities in prop::collection::vec(-100.0..100.0_f64, 3),
        strike in 3000.0..5000.0_f64,
        expiry in 0.2..9.5_f64,
        scale in 0.01..100.0_f64,
    ) {
        let m = market();
        let b = vec![
            (leg(XaKind::Call, &[("strike", strike), ("expiry_years", expiry)]), quantities[0]),
            (leg(XaKind::Put, &[("strike", strike), ("expiry_years", expiry / 2.0)]), quantities[1]),
            (zcb(expiry, 1e6), quantities[2]),
        ];
        let w = [1.0, 2.0, 0.5, 1.0, 3.0];
        let s = crossasset_solve(&m, &b, &hedges(), &w, 0.0).unwrap();
        let size = s.book_risk.iter().fold(1.0f64, |a, v| a.max(v.abs()));
        prop_assert!(s.residual_risk.iter().all(|r| r.abs() < 1e-9 * size));
        let ws: Vec<f64> = w.iter().map(|v| v * scale).collect();
        let t = crossasset_solve(&m, &b, &hedges(), &ws, 0.0).unwrap();
        for (p, q) in s.positions.iter().zip(&t.positions) {
            prop_assert!((p - q).abs() < 1e-9 * p.abs().max(1.0));
        }
        // Bonds alone carry no equity risk at all.
        let bonds = [(zcb(expiry, 1e6), quantities[2])];
        let r = crossasset_solve(&m, &bonds, &hedges(), &w, 0.0).unwrap();
        prop_assert_eq!(r.book_risk[0], 0.0);
    }
}
