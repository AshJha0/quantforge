//! Stage I wave 4b backtest and effectiveness (`08-hedging/dynamic-hedge-and-effectiveness.md`):
//! unit tests and the property tests the spec names (with the 2026-11-11 correction).
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use proptest::prelude::*;
use quantforge_core::hedge_dynamic::{
    BacktestOption, BacktestSetup, backtest_delta, effectiveness, replay,
};

fn code<T: std::fmt::Debug>(r: quantforge_core::error::Result<T>) -> &'static str {
    r.unwrap_err().code
}

const CALL: BacktestOption = BacktestOption {
    call: true,
    strike: 100.0,
    expiry: 0.25,
};

const SETUP: BacktestSetup = BacktestSetup {
    quantity: -100.0,
    rate: 0.03,
    dividend_yield: 0.01,
    hedge_volatility: 0.2,
};

#[test]
fn effectiveness_checks() {
    let x = [1.0, -2.0, 3.0];
    assert_eq!(code(effectiveness(&x, &[1.0, 2.0])), "E_INPUT");
    assert_eq!(code(effectiveness(&x[..2], &[1.0, 2.0])), "E_INPUT");
    assert_eq!(code(effectiveness(&[1.0, -1.0, 0.0], &x)), "E_DOMAIN");
    assert_eq!(code(effectiveness(&[1.0, 1.0, 1.0], &x)), "E_DOMAIN");
    assert_eq!(code(effectiveness(&x, &[2.0, 2.0, 2.0])), "E_DOMAIN");
    assert_eq!(code(effectiveness(&x, &[1.0, f64::NAN, 2.0])), "E_DOMAIN");
    // Hedging half of the item: offset 0.5, slope -0.5, R^2 1, variance reduction 0.75.
    let y: Vec<f64> = x.iter().map(|v| -0.5 * v).collect();
    let e = effectiveness(&x, &y).unwrap();
    assert!((e.dollar_offset - 0.5).abs() < 1e-15 && (e.regression_slope + 0.5).abs() < 1e-15);
    assert!((e.regression_r2 - 1.0).abs() < 1e-15 && (e.variance_reduction - 0.75).abs() < 1e-15);
}

#[test]
fn backtest_checks_and_expiry_payoff() {
    let t = [0.0, 0.1, 0.2, 0.25];
    let s = [100.0, 103.0, 98.0, 104.0];
    let r = backtest_delta(&CALL, &SETUP, &t, &s).unwrap();
    assert_eq!(r.option_values[3], 4.0);
    assert_eq!(r.portfolio_values[0], 0.0);
    assert_eq!(r.shares.len(), 3);
    assert_eq!(r.final_pnl, r.portfolio_values[3]);
    let put = BacktestOption {
        call: false,
        ..CALL
    };
    assert_eq!(
        backtest_delta(&put, &SETUP, &t, &s).unwrap().option_values[3],
        0.0
    );
    assert_eq!(
        code(backtest_delta(&CALL, &SETUP, &[0.1, 0.2, 0.3, 0.4], &s)),
        "E_INPUT"
    );
    assert_eq!(
        code(backtest_delta(&CALL, &SETUP, &[0.0, 0.2, 0.2, 0.25], &s)),
        "E_INPUT"
    );
    assert_eq!(code(backtest_delta(&CALL, &SETUP, &t, &s[..3])), "E_INPUT");
    assert_eq!(
        code(backtest_delta(&CALL, &SETUP, &t[..3], &s[..3])),
        "E_INPUT"
    );
    assert_eq!(
        code(backtest_delta(&CALL, &SETUP, &[0.0, 0.1, 0.2, 0.3], &s)),
        "E_INPUT"
    );
    assert_eq!(
        code(backtest_delta(
            &CALL,
            &SETUP,
            &t,
            &[100.0, 0.0, 98.0, 104.0]
        )),
        "E_DOMAIN"
    );
    let flat = BacktestSetup {
        hedge_volatility: 0.0,
        ..SETUP
    };
    assert_eq!(code(backtest_delta(&CALL, &flat, &t, &s)), "E_DOMAIN");
    let none = BacktestSetup {
        quantity: 0.0,
        ..SETUP
    };
    assert_eq!(code(backtest_delta(&CALL, &none, &t, &s)), "E_DOMAIN");
    let nan = BacktestSetup {
        rate: f64::NAN,
        ..SETUP
    };
    assert_eq!(code(backtest_delta(&CALL, &nan, &t, &s)), "E_DOMAIN");
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(128))]

    #[test]
    fn perfect_offset_scores_one(x in prop::collection::vec(-100.0..100.0_f64, 3..40)) {
        let y: Vec<f64> = x.iter().map(|v| -v).collect();
        if let Ok(e) = effectiveness(&x, &y) {
            prop_assert!((e.dollar_offset - 1.0).abs() < 1e-12);
            prop_assert!((e.regression_slope + 1.0).abs() < 1e-12);
            prop_assert!((e.regression_r2 - 1.0).abs() < 1e-12);
            prop_assert!((e.variance_reduction - 1.0).abs() < 1e-12);
        }
    }

    #[test]
    fn constant_spot_replay_ends_at_the_option_decay(
        spot in 60.0..140.0_f64,
        steps in 3usize..30,
        quantity in -50.0..50.0_f64,
        call in any::<bool>(),
    ) {
        #[allow(clippy::cast_precision_loss)]
        let times: Vec<f64> = (0..=steps).map(|i| 0.2 * i as f64 / steps as f64).collect();
        let spots = vec![spot; steps + 1];
        let setup = BacktestSetup { quantity, rate: 0.0, dividend_yield: 0.0, hedge_volatility: 0.25 };
        let o = BacktestOption { call, strike: 100.0, expiry: 0.3 };
        let r = replay(&o, &setup, &times, &spots).unwrap();
        let v = &r.option_values;
        let want = quantity * (v[steps] - v[0]);
        let last = r.portfolio_values[steps];
        prop_assert!((last - want).abs() < 1e-10 * want.abs().max(1.0), "{last} {want}");
        prop_assert!(r.hedge.iter().all(|h| h.abs() < 1e-9 * quantity.abs().max(1.0) * spot));
    }
}
