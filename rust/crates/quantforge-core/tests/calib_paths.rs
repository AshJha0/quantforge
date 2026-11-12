//! Validation and stopping paths of `calib::fit` and `calib::check_bid_ask` (stage B
//! calibration spec): each refused input names its error code, and a capped search stops with
//! `E_NO_CONVERGENCE` rather than returning an unconverged fit as if it had settled.

#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use quantforge_core::calib::{Fit, FitInputs, Method, Model, check_bid_ask, fit};

fn linear(method: Method) -> FitInputs {
    FitInputs {
        model: Model::Linear,
        x: vec![1.0, 2.0, 3.0],
        y: vec![1.0, 2.0, 3.0],
        start: vec![0.0, 0.0],
        method,
        weights: None,
        regularisation: 0.0,
        prior: None,
        lower: None,
        upper: None,
        max_iter: 1000,
    }
}

fn code(r: quantforge_core::error::Result<Fit>) -> &'static str {
    r.err().map_or("ok", |e| e.code)
}

#[test]
fn refused_inputs_name_their_code() {
    let lm = Method::LevenbergMarquardt;
    let mut i = linear(Method::Bfgs);
    i.lower = Some(vec![0.0, 0.0]);
    assert_eq!(code(fit(&i)), "E_INPUT"); // bounds need Levenberg-Marquardt
    let mut i = linear(lm);
    i.lower = Some(vec![2.0, 0.0]);
    i.upper = Some(vec![1.0, 1.0]);
    assert_eq!(code(fit(&i)), "E_INPUT"); // lower above upper
    let mut i = linear(lm);
    i.max_iter = 0;
    assert_eq!(code(fit(&i)), "E_INPUT");
    let mut i = linear(lm);
    i.weights = Some(vec![1.0, -1.0, 1.0]);
    assert_eq!(code(fit(&i)), "E_DOMAIN");
    let mut i = linear(lm);
    i.regularisation = -1e-9;
    assert_eq!(code(fit(&i)), "E_DOMAIN");
    let mut i = linear(lm);
    i.prior = Some(vec![0.0]);
    assert_eq!(code(fit(&i)), "E_INPUT");
    assert_eq!(code(fit(&linear(lm))), "ok");
}

#[test]
fn capped_searches_do_not_settle_silently() {
    for method in [
        Method::GaussNewton,
        Method::LevenbergMarquardt,
        Method::Bfgs,
    ] {
        let i = FitInputs {
            model: Model::Rosenbrock,
            x: vec![],
            y: vec![],
            start: vec![-1.2, 1.0],
            max_iter: 1,
            ..linear(method)
        };
        assert_eq!(code(fit(&i)), "E_NO_CONVERGENCE", "{method:?}");
        let found = fit(&FitInputs {
            max_iter: 10_000,
            ..i
        })
        .unwrap();
        assert!(
            (found.parameters[0] - 1.0).abs() < 1e-6 && (found.parameters[1] - 1.0).abs() < 1e-6,
            "{method:?}"
        );
    }
}

#[test]
fn bid_ask_breaches_on_both_sides() {
    let out = check_bid_ask(&[0.9, 1.5, 2.6], &[1.0, 1.4, 2.4], &[1.1, 1.6, 2.5]).unwrap();
    assert_eq!(
        out.iter().map(|b| (b.0, b.1)).collect::<Vec<_>>(),
        vec![(0, "BID"), (2, "ASK")]
    );
    assert!((out[1].2 - 0.1).abs() < 1e-12);
    assert_eq!(check_bid_ask(&[1.0], &[1.0], &[1.0]).unwrap(), vec![]); // touching is no breach
    assert_eq!(
        check_bid_ask(&[1.0], &[1.0, 2.0], &[1.0]).unwrap_err().code,
        "E_INPUT"
    );
    assert_eq!(
        check_bid_ask(&[1.0], &[2.0], &[1.0]).unwrap_err().code,
        "E_INPUT"
    );
}
