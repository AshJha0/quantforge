//! Identities and examples from the stage B specs.
use quantforge_core::calendar::parse_tenor;
use quantforge_core::conventions::overnight;
use quantforge_core::curve::{Interpolation, SolveMethod};
use quantforge_core::dates::Date;
use quantforge_core::hedge::solve_hedge;
use quantforge_core::ois::{OisCurveProblem, OisQuote};
use quantforge_core::units::{add_money, round_money};

#[test]
fn money_is_exact() {
    assert_eq!(add_money("0.1", "GBP", "0.2", "GBP").unwrap().0, "0.3");
    assert_eq!(add_money("1.50", "GBP", "-1.5", "GBP").unwrap().0, "0");
    assert_eq!(round_money("2.675", "GBP").unwrap().0, "2.68");
    assert_eq!(round_money("2.665", "GBP").unwrap().0, "2.66");
    let e = add_money("1", "GBP", "1", "USD").unwrap_err();
    assert_eq!(e.code, "E_CURRENCY_MISMATCH");
    assert_eq!(round_money("1e3", "GBP").unwrap_err().code, "E_SCHEMA");
}

#[test]
fn both_solves_give_one_curve() {
    let quotes: Vec<OisQuote> = [("1M", 0.03), ("1Y", 0.032), ("5Y", 0.035), ("10Y", 0.036)]
        .iter()
        .map(|(t, r)| OisQuote {
            tenor: parse_tenor(t).unwrap(),
            bid: *r,
            ask: *r,
        })
        .collect();
    let c = overnight("SOFR").unwrap();
    let as_of = Date::new(2026, 11, 6);
    let p = OisCurveProblem::new(&c, as_of, &quotes, Interpolation::LinearZero).unwrap();
    let a = p.solve(&p.mids, SolveMethod::Sequential).unwrap();
    let b = p.solve(&p.mids, SolveMethod::Global).unwrap();
    assert!(a.max_repricing_error < 1e-13 && b.max_repricing_error < 1e-13);
    for (x, y) in a.logs.iter().zip(&b.logs) {
        assert!((x - y).abs() < 1e-12);
    }
}

#[test]
fn a_costly_hedge_is_left_out() {
    let a = vec![vec![1.0], vec![0.0]];
    let h = solve_hedge(&a, &[1.0, 0.0], &[1.0, 1.0], &[1.0], 10.0).unwrap();
    assert_eq!(h.x, vec![0.0]);
    let free = solve_hedge(&a, &[1.0, 0.0], &[1.0, 1.0], &[0.0], 0.0).unwrap();
    assert!((free.x[0] + 1.0).abs() < 1e-12);
}
