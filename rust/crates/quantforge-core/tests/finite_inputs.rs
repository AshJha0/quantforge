//! E1: NaN and infinity are `E_DOMAIN` at public inputs; `-0.0` and the extreme finite values
//! are not rejected by the finiteness rule itself.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use quantforge_core::black::{Model, Option_};
use quantforge_core::compounding::{Compounding, convert, discount_factor};
use quantforge_core::interp::{Method, evaluate};
use quantforge_core::stats::{quantile, summary};

const BAD: [f64; 3] = [f64::NAN, f64::INFINITY, f64::NEG_INFINITY];

fn domain<T: std::fmt::Debug>(r: quantforge_core::error::Result<T>, field: &str) {
    let e = r.unwrap_err();
    assert_eq!(e.code, "E_DOMAIN", "{e:?}");
    assert_eq!(e.field.as_deref(), Some(field), "{e:?}");
}

fn bs(spot: f64, strike: f64, t: f64) -> Option_ {
    Option_ {
        model: Model::BlackScholes {
            spot,
            rate: 0.02,
            dividend: 0.0,
        },
        call: true,
        strike,
        t,
    }
}

#[test]
fn compounding_scalars() {
    for b in BAD {
        domain(discount_factor(b, 1.0, Compounding::Continuous), "r");
        domain(discount_factor(0.05, b, Compounding::Continuous), "t");
        domain(discount_factor(0.05, 1.0, Compounding::Periodic(b)), "c");
        domain(
            convert(b, 1.0, Compounding::Simple, Compounding::Continuous),
            "r",
        );
    }
    // -0.0 is a finite zero: it passes the finiteness rule.
    assert!(discount_factor(-0.0, 1.0, Compounding::Continuous).is_ok());
    assert!(discount_factor(0.05, -0.0, Compounding::Continuous).is_ok());
}

#[test]
fn option_struct_fields_and_vol() {
    for b in BAD {
        domain(bs(b, 100.0, 1.0).price(0.2), "self");
        domain(bs(100.0, b, 1.0).price(0.2), "self");
        domain(bs(100.0, 100.0, b).price(0.2), "self");
        domain(bs(100.0, 100.0, 1.0).price(b), "v");
    }
    assert!(bs(100.0, 100.0, 1.0).price(0.2).is_ok());
}

#[test]
fn slices_and_enum_payloads() {
    let (x, y) = ([0.0, 1.0, 2.0], [1.0, 2.0, 4.0]);
    for b in BAD {
        domain(evaluate(Method::Linear, &[0.0, b, 2.0], &y, &[0.5]), "x");
        domain(evaluate(Method::Linear, &x, &[1.0, 2.0, b], &[0.5]), "y");
        domain(evaluate(Method::Linear, &x, &y, &[b]), "at");
        domain(evaluate(Method::Tension(b), &x, &y, &[0.5]), "method");
        let clamped = Method::CubicClamped { start: 0.0, end: b };
        domain(evaluate(clamped, &x, &y, &[0.5]), "method");
        domain(summary(&[1.0, b]), "x");
        domain(quantile(&[1.0, 2.0], &[b]), "p");
    }
    assert!(evaluate(Method::Linear, &x, &y, &[-0.0]).is_ok());
    assert!(summary(&[f64::MAX, f64::MIN_POSITIVE]).is_ok());
}
