//! Stage E quality pass: parity, limits and domain errors checked from outside the crate.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use quantforge_core::corr::implied;
use quantforge_core::credit_e::{Pool, bivariate_normal, loss_cdf, normal_inv, tranche_loss};
use quantforge_core::heston::{Heston, Jumps, Market, heston_price, merton_price};
use quantforge_core::rates_e::{FuturesOption, futures_implied_vol, futures_option_price};

fn market(call: bool) -> Market {
    Market {
        spot: 100.0,
        expiry_years: 1.0,
        rate: 0.03,
        dividend_yield: 0.01,
        call,
    }
}

fn forward_parity(strike: f64) -> f64 {
    100.0 * (-0.01f64).exp() - strike * (-0.03f64).exp()
}

const HESTON: Heston = Heston {
    v0: 0.04,
    kappa: 1.5,
    theta: 0.05,
    xi: 0.5,
    rho: -0.7,
};

#[test]
fn heston_calls_and_puts_satisfy_put_call_parity() {
    let strikes = [80.0, 100.0, 125.0];
    let calls = heston_price(&market(true), &strikes, &HESTON).unwrap();
    let puts = heston_price(&market(false), &strikes, &HESTON).unwrap();
    for i in 0..3 {
        assert!((calls[i] - puts[i] - forward_parity(strikes[i])).abs() < 1e-8);
    }
}

#[test]
fn heston_call_prices_fall_as_the_strike_rises() {
    let strikes = [60.0, 80.0, 100.0, 120.0, 140.0];
    let calls = heston_price(&market(true), &strikes, &HESTON).unwrap();
    assert!(calls.windows(2).all(|w| w[1] < w[0]));
}

#[test]
fn merton_without_jumps_satisfies_parity_and_beats_intrinsic() {
    let none = Jumps {
        intensity: 0.0,
        mean_log_jump: 0.0,
        log_jump_vol: 0.0,
    };
    let strikes = [90.0, 110.0];
    let calls = merton_price(&market(true), &strikes, 0.2, &none).unwrap();
    let puts = merton_price(&market(false), &strikes, 0.2, &none).unwrap();
    for i in 0..2 {
        assert!((calls[i] - puts[i] - forward_parity(strikes[i])).abs() < 1e-9);
        assert!(calls[i] > forward_parity(strikes[i]).max(0.0));
    }
}

fn bond_option(call: bool) -> FuturesOption {
    FuturesOption {
        call,
        futures_price: 112.0,
        strike: 110.0,
        expiry_years: 0.5,
        discount_factor: 0.98,
    }
}

#[test]
fn bond_future_options_satisfy_parity_and_scale_by_contract_size() {
    let (c, value) = futures_option_price(&bond_option(true), 0.07, 100_000.0).unwrap();
    let (p, _) = futures_option_price(&bond_option(false), 0.07, 100_000.0).unwrap();
    assert!((c - p - 0.98 * 2.0).abs() < 1e-10);
    assert!((value - c * 1000.0).abs() < 1e-9);
}

#[test]
fn bond_future_implied_vol_recovers_the_input_vol() {
    let (c, _) = futures_option_price(&bond_option(true), 0.07, 1.0).unwrap();
    let (price_vol, yield_vol) = futures_implied_vol(&bond_option(true), c, 0.04, 7.0).unwrap();
    assert!((price_vol - 0.07).abs() < 1e-9);
    assert!((yield_vol - 0.07 / (7.0 * 0.04)).abs() < 1e-9);
}

#[test]
fn bond_future_errors_are_domain_errors() {
    let bad = FuturesOption {
        discount_factor: 0.0,
        ..bond_option(true)
    };
    assert_eq!(
        futures_option_price(&bad, 0.07, 1.0).unwrap_err().code,
        "E_DOMAIN"
    );
    assert_eq!(
        futures_option_price(&bond_option(true), -0.1, 1.0)
            .unwrap_err()
            .code,
        "E_DOMAIN"
    );
    // A premium at intrinsic has no implied vol.
    let at_intrinsic = 0.98 * 2.0;
    let err = futures_implied_vol(&bond_option(true), at_intrinsic, 0.04, 7.0).unwrap_err();
    assert_eq!(err.code, "E_DOMAIN");
}

#[test]
fn implied_correlation_limits_by_hand() {
    // Equal weights, vols 20% and 30%: an index vol of 25% means perfect correlation.
    assert!((implied(&[0.5, 0.5], &[0.2, 0.3], 0.25).unwrap() - 1.0).abs() < 1e-12);
    let independent = (0.25f64 * 0.04 + 0.25 * 0.09).sqrt();
    assert!(
        implied(&[0.5, 0.5], &[0.2, 0.3], independent)
            .unwrap()
            .abs()
            < 1e-12
    );
    assert_eq!(
        implied(&[0.5, 0.5], &[0.2, 0.3], 0.0).unwrap_err().code,
        "E_DOMAIN"
    );
    assert_eq!(
        implied(&[1.0, 0.0], &[0.2, 0.3], 0.2).unwrap_err().code,
        "E_DOMAIN"
    );
    assert_eq!(implied(&[1.0], &[0.2], 0.2).unwrap_err().code, "E_INPUT");
}

const POOL: Pool = Pool {
    default_probability: 0.05,
    correlation: 0.3,
    recovery: 0.4,
};

#[test]
fn the_whole_capital_structure_loses_the_expected_loss() {
    // Tranche [0, 1] carries all losses: lgd * p = 0.6 * 0.05.
    assert!((tranche_loss(&POOL, 0.0, 1.0).unwrap() - 0.03).abs() < 1e-12);
}

#[test]
fn senior_tranches_lose_less_than_junior_ones() {
    let equity = tranche_loss(&POOL, 0.0, 0.03).unwrap();
    let mezz = tranche_loss(&POOL, 0.03, 0.07).unwrap();
    let senior = tranche_loss(&POOL, 0.15, 0.3).unwrap();
    assert!(equity > mezz && mezz > senior && senior >= 0.0);
}

#[test]
fn tranche_and_pool_inputs_are_checked() {
    assert_eq!(tranche_loss(&POOL, 0.07, 0.03).unwrap_err().code, "E_INPUT");
    assert_eq!(tranche_loss(&POOL, 0.0, 1.5).unwrap_err().code, "E_INPUT");
    let bad = Pool {
        correlation: 1.0,
        ..POOL
    };
    assert_eq!(tranche_loss(&bad, 0.0, 0.03).unwrap_err().code, "E_DOMAIN");
}

#[test]
fn loss_cdf_rises_within_zero_and_one() {
    let cdf = loss_cdf(&POOL, &[0.001, 0.01, 0.05, 0.2, 0.59]).unwrap();
    assert!(cdf.iter().all(|c| (0.0..=1.0).contains(c)));
    assert!(cdf.windows(2).all(|w| w[0] <= w[1] + 1e-12));
}

#[test]
fn bivariate_normal_by_hand() {
    // At zero thresholds: 1/4 + asin(rho) / (2 pi).
    let rho: f64 = 0.5;
    let expected = 0.25 + rho.asin() / (2.0 * std::f64::consts::PI);
    assert!((bivariate_normal(0.0, 0.0, rho) - expected).abs() < 1e-10);
    assert!((normal_inv(0.975) - 1.959_963_984_540_054).abs() < 1e-9);
}
