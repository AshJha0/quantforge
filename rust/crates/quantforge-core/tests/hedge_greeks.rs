//! Values of `unit_greeks` (`hedge.greeks.neutralise`, ruling I-9) against the Black-Scholes-
//! Merton closed form with a non-zero rate and dividend yield. Written against the surviving
//! d1 mutants of the stage J re-score of `hedge_solvers.rs`.
//!
//! Expected values were computed independently with mpmath at 40 digits:
//! S = 100, K = 110, r = 0.03, q = 0.01, sigma = 0.25, T = 0.5,
//! d1 = (ln(S/K) + (r - q + sigma^2/2) T) / (sigma sqrt T) = -0.394198905502735675...,
//! call delta = e^{-qT} N(d1), put delta = -e^{-qT} N(-d1),
//! gamma = e^{-qT} n(d1) / (S sigma sqrt T), vega = S e^{-qT} n(d1) sqrt T (per unit of vol).
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
#![allow(clippy::excessive_precision)] // expected values keep the mpmath digits
use quantforge_core::hedge_solvers::{GreekInstrument, GreekMarket, unit_greeks};

const CALL_DELTA: f64 = 0.344_987_838_111_096_057_6;
const PUT_DELTA: f64 = -0.650_024_641_081_586_255_8;
const GAMMA: f64 = 0.020_776_408_216_655_107_78;
const VEGA: f64 = 25.970_510_270_818_884_72;

fn market() -> GreekMarket {
    GreekMarket {
        spot: 100.0,
        rate: 0.03,
        dividend_yield: 0.01,
        volatility: 0.25,
    }
}

fn close(got: f64, want: f64, tol: f64, what: &str) {
    assert!(
        (got - want).abs() <= tol * want.abs().max(1.0),
        "{what}: got {got}, want {want}"
    );
}

#[test]
fn call_greeks_match_closed_form() {
    let g = unit_greeks(
        &market(),
        &GreekInstrument::Option {
            call: true,
            strike: 110.0,
            expiry: 0.5,
        },
    );
    close(g[0], CALL_DELTA, 1e-12, "call delta");
    close(g[1], GAMMA, 1e-12, "call gamma");
    close(g[2], VEGA, 1e-12, "call vega");
}

#[test]
fn put_greeks_match_closed_form() {
    let g = unit_greeks(
        &market(),
        &GreekInstrument::Option {
            call: false,
            strike: 110.0,
            expiry: 0.5,
        },
    );
    close(g[0], PUT_DELTA, 1e-12, "put delta");
    close(g[1], GAMMA, 1e-12, "put gamma");
    close(g[2], VEGA, 1e-12, "put vega");
    // Put-call parity of delta: call - put = e^{-qT}.
    close(
        CALL_DELTA - PUT_DELTA,
        (-0.01f64 * 0.5).exp(),
        1e-15,
        "parity",
    );
}

#[test]
fn underlying_greeks_are_unit_delta() {
    assert_eq!(
        unit_greeks(&market(), &GreekInstrument::Underlying),
        [1.0, 0.0, 0.0]
    );
}
