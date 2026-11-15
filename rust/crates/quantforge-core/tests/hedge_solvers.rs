//! Stage I wave 1 hedge solvers (`08-hedging/hedge-solvers.md`): unit tests on hand-sized
//! problems and the property tests the spec names, on generated data.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use proptest::prelude::*;
use quantforge_core::hedge_solvers::{
    Costs, Greek, GreekInstrument, GreekMarket, IntegerProblem, Leg, LegKind, LotHedge,
    MinVarInput, QpProblem, Singular, beta_futures, greeks_neutralise, integer_solve, minvar_ratio,
    option_hedge_lots, qp_solve, residual_report, select_solve, unit_greeks,
};
use quantforge_core::linalg::{Matrix, solve};

fn code<T: std::fmt::Debug>(r: quantforge_core::error::Result<T>) -> &'static str {
    r.unwrap_err().code
}

fn problem<'a>(a: &'a Matrix, b: &'a [f64], w: &'a [f64]) -> QpProblem<'a> {
    QpProblem {
        a,
        b,
        weights: w,
        ridge: 0.0,
        eq_matrix: None,
        eq_rhs: None,
        lower: None,
        upper: None,
        singular: Singular::Error,
        costs: Costs::default(),
    }
}

fn base() -> (Matrix, Vec<f64>, Vec<f64>) {
    (
        vec![
            vec![1.0, 0.5, 0.2],
            vec![0.3, 1.2, 0.4],
            vec![0.1, 0.6, 1.5],
            vec![0.8, 0.2, 0.9],
        ],
        vec![-2.0, 1.5, -0.7, 0.9],
        vec![1.0, 2.0, 0.5, 1.5],
    )
}

/// `H = A^T W A + ridge I` and `c = A^T W b`.
fn normal(a: &Matrix, b: &[f64], w: &[f64], ridge: f64) -> (Matrix, Vec<f64>) {
    let n = a[0].len();
    let h = (0..n)
        .map(|i| {
            (0..n)
                .map(|j| {
                    a.iter().zip(w).map(|(r, w)| r[i] * w * r[j]).sum::<f64>()
                        + if i == j { ridge } else { 0.0 }
                })
                .collect()
        })
        .collect();
    let c = (0..n)
        .map(|i| {
            a.iter()
                .zip(w.iter().zip(b))
                .map(|(r, (w, b))| r[i] * w * b)
                .sum()
        })
        .collect();
    (h, c)
}

#[test]
fn unconstrained_qp_solves_the_normal_equations() {
    let (a, b, w) = base();
    let mut p = problem(&a, &b, &w);
    p.ridge = 0.25;
    let s = qp_solve(&p).unwrap();
    let (h, c) = normal(&a, &b, &w, 0.25);
    let x = solve(&h, &c.iter().map(|v| -v).collect::<Vec<_>>()).unwrap();
    for (u, v) in s.x.iter().zip(&x) {
        assert!((u - v).abs() < 1e-13, "{u} {v}");
    }
    assert_eq!(s.rank, 3);
    let f: f64 = s
        .residual
        .iter()
        .zip(&w)
        .map(|(r, w)| w * r * r)
        .sum::<f64>()
        + 0.25 * s.x.iter().map(|v| v * v).sum::<f64>();
    assert!((s.objective - f).abs() < 1e-14 * f);
}

#[test]
fn bounds_equalities_and_fixed_variables() {
    let (a, b, w) = base();
    let lower = [Some(0.0), Some(0.0), Some(0.0)];
    let upper = [None, Some(0.25), None];
    let e = vec![vec![1.0, 1.0, 1.0]];
    let mut p = problem(&a, &b, &w);
    p.lower = Some(&lower);
    p.upper = Some(&upper);
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&[1.0]);
    let s = qp_solve(&p).unwrap();
    assert!((s.x.iter().sum::<f64>() - 1.0).abs() < 1e-14);
    assert!(s.x.iter().all(|v| *v >= 0.0) && s.x[1] <= 0.25);
    assert_eq!(s.rank, 2);
    // lower = upper fixes the variable exactly.
    let fixed = [Some(0.3), None, None];
    let mut p = problem(&a, &b, &w);
    p.lower = Some(&fixed);
    p.upper = Some(&fixed);
    assert_eq!(qp_solve(&p).unwrap().x[0], 0.3);
}

#[test]
fn as_many_equalities_as_instruments() {
    let (a, b, w) = base();
    let e = vec![
        vec![1.0, 0.0, 0.0],
        vec![0.0, 2.0, 0.0],
        vec![0.0, 0.0, 4.0],
    ];
    let rhs = [1.0, 1.0, 1.0];
    let mut p = problem(&a, &b, &w);
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&rhs);
    let s = qp_solve(&p).unwrap();
    assert_eq!(s.rank, 0);
    for (u, v) in s.x.iter().zip([1.0, 0.5, 0.25]) {
        assert!((u - v).abs() < 1e-15);
    }
    let upper = [None, Some(0.4), None];
    p.upper = Some(&upper);
    assert_eq!(code(qp_solve(&p)), "E_INFEASIBLE");
}

#[test]
fn min_norm_splits_duplicates_and_leaves_zero_columns() {
    let a = vec![vec![1.0, 1.0, 0.0], vec![0.5, 0.5, 0.0]];
    let (b, w) = ([-2.0, -1.0], [1.0, 1.0]);
    let mut p = problem(&a, &b, &w);
    assert_eq!(code(qp_solve(&p)), "E_SINGULAR");
    p.singular = Singular::MinNorm;
    let s = qp_solve(&p).unwrap();
    assert_eq!(s.rank, 1);
    assert!((s.x[0] - 1.0).abs() < 1e-14 && (s.x[1] - 1.0).abs() < 1e-14);
    assert!(s.x[2].abs() < 1e-14);
    // A ridge makes the same problem regular.
    p.singular = Singular::Error;
    p.ridge = 1e-3;
    assert_eq!(qp_solve(&p).unwrap().rank, 3);
}

#[test]
fn qp_checks_come_in_the_stated_order() {
    let (a, b, w) = base();
    let short = [1.0, 2.0];
    // F-2 before shapes.
    let nan = [f64::NAN, 1.0];
    assert_eq!(code(qp_solve(&problem(&a, &nan, &short))), "E_DOMAIN");
    assert_eq!(code(qp_solve(&problem(&a, &short, &w))), "E_INPUT");
    let ragged = vec![vec![1.0, 2.0], vec![1.0]];
    assert_eq!(code(qp_solve(&problem(&ragged, &short, &short))), "E_INPUT");
    let mut p = problem(&a, &b, &w);
    p.eq_matrix = Some(&a);
    assert_eq!(code(qp_solve(&p)), "E_INPUT");
    let bound = [Some(0.0), None, None];
    let mut p = problem(&a, &b, &w);
    p.lower = Some(&bound);
    p.singular = Singular::MinNorm;
    assert_eq!(code(qp_solve(&p)), "E_INPUT");
    let zero_w = [1.0, 0.0, 1.0, 1.0];
    let dup = vec![vec![1.0, 1.0]; 4];
    // E_DOMAIN before E_SINGULAR (hedgeqp_i-0044 in miniature).
    assert_eq!(code(qp_solve(&problem(&dup, &b, &zero_w))), "E_DOMAIN");
    let mut p = problem(&a, &b, &w);
    p.ridge = -1.0;
    assert_eq!(code(qp_solve(&p)), "E_DOMAIN");
    let (lo, hi) = ([Some(1.0), None, None], [Some(0.0), None, None]);
    let mut p = problem(&a, &b, &w);
    p.lower = Some(&lo);
    p.upper = Some(&hi);
    assert_eq!(code(qp_solve(&p)), "E_DOMAIN");
    let dependent = vec![vec![1.0, 1.0, 0.0], vec![2.0, 2.0, 0.0]];
    let mut p = problem(&a, &b, &w);
    p.eq_matrix = Some(&dependent);
    p.eq_rhs = Some(&[0.0, 0.0]);
    assert_eq!(code(qp_solve(&p)), "E_SINGULAR");
    let four = vec![vec![1.0, 0.0, 0.0]; 4];
    let mut p = problem(&a, &b, &w);
    p.eq_matrix = Some(&four);
    p.eq_rhs = Some(&[0.0; 4]);
    assert_eq!(code(qp_solve(&p)), "E_SINGULAR");
    // Budget above the sum of the upper bounds.
    let e = vec![vec![1.0, 1.0, 1.0]];
    let up = [Some(1.0), Some(1.0), Some(1.0)];
    let mut p = problem(&a, &b, &w);
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&[3.5]);
    p.upper = Some(&up);
    assert_eq!(code(qp_solve(&p)), "E_INFEASIBLE");
    // Singular and infeasible: E_SINGULAR first (I-14).
    let mut p = problem(&dup, &b, &w);
    let e2 = vec![vec![1.0, 1.0]];
    let up2 = [Some(1.0), Some(1.0)];
    p.eq_matrix = Some(&e2);
    p.eq_rhs = Some(&[3.0]);
    p.upper = Some(&up2);
    assert_eq!(code(qp_solve(&p)), "E_SINGULAR");
}

fn lots_problem<'a>(a: &'a Matrix, b: &'a [f64], w: &'a [f64], s: &'a [f64]) -> IntegerProblem<'a> {
    IntegerProblem {
        a,
        b,
        weights: w,
        ridge: 0.0,
        lot_sizes: s,
        lower_lots: None,
        upper_lots: None,
    }
}

#[test]
fn integer_ties_prefer_small_then_lexicographic() {
    // (n - 0.5)^2: 0 and 1 tie exactly; the smaller |n| wins.
    let a = vec![vec![1.0]];
    let s = integer_solve(&lots_problem(&a, &[-0.5], &[1.0], &[1.0])).unwrap();
    assert_eq!(s.lots, vec![0]);
    let s = integer_solve(&lots_problem(&a, &[0.5], &[1.0], &[1.0])).unwrap();
    assert_eq!(s.lots, vec![0]);
    // (n1 + n2 - 1)^2 + ridge |n|^2: (0, 1) and (1, 0) tie; lexicographic order picks (0, 1).
    let a = vec![vec![1.0, 1.0]];
    let mut p = lots_problem(&a, &[-1.0], &[1.0], &[1.0, 1.0]);
    p.ridge = 0.125;
    let s = integer_solve(&p).unwrap();
    assert_eq!(s.lots, vec![0, 1]);
    assert!(s.rounding_cost >= 0.0);
}

#[test]
fn integer_lots_scale_and_bounds() {
    let (a, b, w) = base();
    let b: Vec<f64> = b.iter().map(|v| v * 10.0).collect();
    let sizes = [2.0, 1.0, 0.5];
    let (lo, hi) = ([Some(-3), None, Some(-1)], [Some(3), Some(2), None]);
    let mut p = lots_problem(&a, &b, &w, &sizes);
    p.lower_lots = Some(&lo);
    p.upper_lots = Some(&hi);
    let s = integer_solve(&p).unwrap();
    for (j, n) in s.lots.iter().enumerate() {
        assert!(lo[j].is_none_or(|l| *n >= l) && hi[j].is_none_or(|h| *n <= h));
        #[allow(clippy::cast_precision_loss)]
        let x = *n as f64 * sizes[j];
        assert_eq!(s.x[j], x);
    }
    assert!(s.objective >= s.continuous_objective);
}

#[test]
fn integer_checks() {
    let (a, b, w) = base();
    assert_eq!(
        code(integer_solve(&lots_problem(&a, &b, &w, &[1.0]))),
        "E_INPUT"
    );
    assert_eq!(
        code(integer_solve(&lots_problem(&a, &b, &w, &[1.0, 0.0, 1.0]))),
        "E_DOMAIN"
    );
    let (lo, hi) = ([Some(2), None, None], [Some(1), None, None]);
    let mut p = lots_problem(&a, &b, &w, &[1.0; 3]);
    p.lower_lots = Some(&lo);
    p.upper_lots = Some(&hi);
    assert_eq!(code(integer_solve(&p)), "E_DOMAIN");
    let dup = vec![vec![1.0, 1.0]; 4];
    let bounded = [Some(0), Some(0)];
    let mut p = lots_problem(&dup, &b, &w, &[1.0, 1.0]);
    p.lower_lots = Some(&bounded);
    p.upper_lots = Some(&bounded);
    // Singular in lot units even with every lot fixed (I-6).
    assert_eq!(code(integer_solve(&p)), "E_SINGULAR");
    let inf = [f64::INFINITY, 1.0, 1.0];
    assert_eq!(
        code(integer_solve(&lots_problem(&a, &b, &w, &inf))),
        "E_DOMAIN"
    );
}

#[test]
fn minvar_single_instrument_is_minus_rho_sigma_ratio() {
    let (ss, sf, rho) = (0.0263f64, 0.0313f64, 0.928f64);
    let cov = vec![vec![ss * ss, rho * ss * sf], vec![rho * ss * sf, sf * sf]];
    let r = minvar_ratio(MinVarInput::Covariance(&cov)).unwrap();
    assert!((r.hedge[0] + rho * ss / sf).abs() < 1e-15);
    assert!((r.effectiveness - rho * rho).abs() < 1e-14);
}

#[test]
fn minvar_checks() {
    let bad = vec![vec![1.0, 0.5], vec![0.4, 1.0]];
    assert_eq!(code(minvar_ratio(MinVarInput::Covariance(&bad))), "E_INPUT");
    let small = vec![vec![1.0]];
    assert_eq!(
        code(minvar_ratio(MinVarInput::Covariance(&small))),
        "E_INPUT"
    );
    let zero = vec![vec![0.0, 0.0], vec![0.0, 1.0]];
    assert_eq!(
        code(minvar_ratio(MinVarInput::Covariance(&zero))),
        "E_DOMAIN"
    );
    let flat = vec![vec![1.0, 0.0], vec![0.0, 0.0]];
    assert_eq!(
        code(minvar_ratio(MinVarInput::Covariance(&flat))),
        "E_SINGULAR"
    );
    let over = vec![vec![1.0, 1.5], vec![1.5, 1.0]];
    assert_eq!(
        code(minvar_ratio(MinVarInput::Covariance(&over))),
        "E_NOT_POSITIVE_DEFINITE"
    );
    let e = [0.1, 0.2];
    let h = vec![vec![0.1, 0.3]];
    assert_eq!(code(minvar_ratio(MinVarInput::Series(&e, &h))), "E_INPUT");
    let none: Matrix = vec![];
    assert_eq!(
        code(minvar_ratio(MinVarInput::Series(&e, &none))),
        "E_INPUT"
    );
    let nan = [0.1, f64::NAN, 0.3];
    assert_eq!(
        code(minvar_ratio(MinVarInput::Series(&nan, &h))),
        "E_DOMAIN"
    );
}

const MARKET: GreekMarket = GreekMarket {
    spot: 100.0,
    rate: 0.03,
    dividend_yield: 0.01,
    volatility: 0.25,
};

fn option(kind: LegKind, strike: f64, expiry: f64) -> Leg {
    Leg {
        kind,
        strike: Some(strike),
        expiry: Some(expiry),
        stray_keys: false,
    }
}

const UNDERLYING: Leg = Leg {
    kind: LegKind::Underlying,
    strike: None,
    expiry: None,
    stray_keys: false,
};

#[test]
fn put_call_greeks_differ_by_the_forward() {
    let leg = |call| GreekInstrument::Option {
        call,
        strike: 95.0,
        expiry: 0.7,
    };
    let (c, p) = (
        unit_greeks(&MARKET, &leg(true)),
        unit_greeks(&MARKET, &leg(false)),
    );
    assert!((c[0] - p[0] - (-0.01f64 * 0.7).exp()).abs() < 1e-15);
    assert!((c[1] - p[1]).abs() < 1e-17 && (c[2] - p[2]).abs() < 1e-12);
}

#[test]
fn delta_gamma_vega_neutral() {
    let book = [
        (option(LegKind::Call, 100.0, 0.5), -1000.0),
        (option(LegKind::Put, 90.0, 1.0), 500.0),
    ];
    let hedges = [
        UNDERLYING,
        option(LegKind::Call, 105.0, 0.75),
        option(LegKind::Put, 95.0, 1.5),
    ];
    let targets = [Greek::Vega, Greek::Delta, Greek::Gamma];
    let r = greeks_neutralise(&MARKET, &book, &hedges, &targets).unwrap();
    let scale = r.before.iter().fold(1.0f64, |m, v| m.max(v.abs()));
    assert!(r.after.iter().all(|v| v.abs() < 1e-10 * scale));
    // Delta alone with the underlying: the quantity is minus the book delta.
    let r = greeks_neutralise(&MARKET, &book, &[UNDERLYING], &[Greek::Delta]).unwrap();
    assert!((r.quantities[0] + r.before[0]).abs() < 1e-12 * scale);
    assert_eq!(r.after[1], r.before[1]);
}

#[test]
fn greek_checks() {
    let book = [(option(LegKind::Call, 100.0, 0.5), -1000.0)];
    let call = option(LegKind::Call, 100.0, 0.5);
    let g = |m: &GreekMarket, b: &[(Leg, f64)], h: &[Leg], t: &[Greek]| {
        code(greeks_neutralise(m, b, h, t))
    };
    let mut nan = MARKET;
    nan.spot = f64::NAN;
    let striked = Leg {
        strike: Some(1.0),
        ..UNDERLYING
    };
    // F-2 comes before the key checks.
    assert_eq!(g(&nan, &book, &[striked], &[Greek::Delta]), "E_DOMAIN");
    assert_eq!(g(&MARKET, &book, &[striked], &[Greek::Delta]), "E_INPUT");
    let no_expiry = Leg {
        expiry: None,
        ..call
    };
    assert_eq!(
        g(&MARKET, &[(no_expiry, 1.0)], &[UNDERLYING], &[Greek::Delta]),
        "E_INPUT"
    );
    assert_eq!(g(&MARKET, &book, &[], &[]), "E_INPUT");
    assert_eq!(
        g(&MARKET, &book, &[UNDERLYING, call], &[Greek::Delta]),
        "E_INPUT"
    );
    assert_eq!(
        g(
            &MARKET,
            &book,
            &[UNDERLYING, call],
            &[Greek::Delta, Greek::Delta]
        ),
        "E_INPUT"
    );
    let mut flat = MARKET;
    flat.volatility = 0.0;
    assert_eq!(g(&flat, &book, &[UNDERLYING], &[Greek::Delta]), "E_DOMAIN");
    let negative = option(LegKind::Put, -1.0, 1.0);
    assert_eq!(g(&MARKET, &book, &[negative], &[Greek::Delta]), "E_DOMAIN");
    assert_eq!(
        g(
            &MARKET,
            &book,
            &[UNDERLYING, UNDERLYING],
            &[Greek::Delta, Greek::Gamma]
        ),
        "E_SINGULAR"
    );
    assert_eq!(
        g(&MARKET, &book, &[call, call], &[Greek::Delta, Greek::Gamma]),
        "E_SINGULAR"
    );
}

#[test]
fn stray_keys_are_input_errors() {
    // I-41: a hedge with a `quantity`, or any key outside the fixed set.
    let book = [(option(LegKind::Call, 100.0, 0.5), -1000.0)];
    let stray = Leg {
        stray_keys: true,
        ..UNDERLYING
    };
    let r = greeks_neutralise(&MARKET, &book, &[stray], &[Greek::Delta]);
    assert_eq!(code(r), "E_INPUT");
    let r = greeks_neutralise(&MARKET, &[(stray, 1.0)], &[UNDERLYING], &[Greek::Delta]);
    assert_eq!(code(r), "E_INPUT");
}

#[test]
fn minvar_perfect_hedge_rounding_is_zero() {
    // I-44: a hedged variance a hair below 0 is rounding; well below it is not PSD.
    let cov = vec![vec![1.0, 1.0], vec![1.0, 1.0 + 1e-15]];
    let r = minvar_ratio(MinVarInput::Covariance(&cov)).unwrap();
    assert!(r.variance_after >= 0.0 && r.variance_after < 1e-14);
    let bad = vec![vec![1.0, 1.0], vec![1.0, 0.999_999]];
    assert_eq!(
        code(minvar_ratio(MinVarInput::Covariance(&bad))),
        "E_NOT_POSITIVE_DEFINITE"
    );
}

#[test]
fn huge_lot_counts_are_a_limit() {
    // I-49: a relaxed lot count above 2^52.
    let a = vec![vec![1.0]];
    let r = integer_solve(&lots_problem(&a, &[-1e17], &[1.0], &[1.0]));
    assert_eq!(code(r), "E_LIMIT");
    assert!(integer_solve(&lots_problem(&a, &[-4e15], &[1.0], &[1.0])).is_ok());
}

#[test]
fn beta_futures_hull_example_and_rounding() {
    let r = beta_futures(5_050_000.0, 1.5, 0.0, 1010.0, 250.0, true).unwrap();
    assert_eq!((r.contracts, r.contracts_held), (-30.0, -30.0));
    assert!(r.beta_after.abs() < 1e-15);
    // Exactly -2.5 contracts rounds away from zero (I-10).
    let r = beta_futures(1000.0, 1.0, 0.5, 100.0, 2.0, true).unwrap();
    assert_eq!((r.contracts, r.contracts_held), (-2.5, -3.0));
    let r = beta_futures(1000.0, 1.0, 0.5, 100.0, 2.0, false).unwrap();
    assert_eq!(r.contracts_held, -2.5);
    assert!((r.beta_after - 0.5).abs() < 1e-15);
    assert_eq!(
        code(beta_futures(0.0, 1.0, 0.5, 100.0, 2.0, true)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(beta_futures(1.0, f64::INFINITY, 0.5, 100.0, 2.0, true)),
        "E_DOMAIN"
    );
}

#[test]
fn residual_report_checks() {
    let a = vec![vec![1.0], vec![0.0]];
    let s = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let r = residual_report(&a, &[-1.0, 0.0], &[0.5], &s).unwrap();
    assert_eq!(
        (r.variance_before, r.variance_after, r.effectiveness),
        (1.0, 0.25, 0.75)
    );
    assert_eq!(r.volatility_after, 0.5);
    assert_eq!(
        code(residual_report(&a, &[-1.0, 0.0], &[0.5, 1.0], &s)),
        "E_INPUT"
    );
    let asym = vec![vec![1.0, 0.1], vec![0.0, 1.0]];
    assert_eq!(
        code(residual_report(&a, &[-1.0, 0.0], &[0.5], &asym)),
        "E_INPUT"
    );
    let indefinite = vec![vec![1.0, 0.0], vec![0.0, -1.0]];
    assert_eq!(
        code(residual_report(&a, &[-1.0, 0.0], &[0.5], &indefinite)),
        "E_NOT_POSITIVE_DEFINITE"
    );
    assert_eq!(
        code(residual_report(&a, &[0.0, 0.0], &[0.5], &s)),
        "E_DOMAIN"
    );
}

// ---- Property tests named by the spec ----

fn system() -> impl Strategy<Value = (Matrix, Vec<f64>, Vec<f64>)> {
    (2usize..5).prop_flat_map(|n| {
        (n + 1..n + 4).prop_flat_map(move |m| {
            (
                prop::collection::vec(prop::collection::vec(-2.0..2.0_f64, n), m),
                prop::collection::vec(-5.0..5.0_f64, m),
                prop::collection::vec(0.2..3.0_f64, m),
            )
        })
    })
}

/// Largest KKT violation of `x` relative to the gradient scale, with an optional budget row.
fn kkt_violation(
    h: &Matrix,
    c: &[f64],
    x: &[f64],
    lower: &[Option<f64>],
    upper: &[Option<f64>],
    budget: bool,
) -> f64 {
    let n = x.len();
    let hx: Vec<f64> = (0..n)
        .map(|i| (0..n).map(|j| h[i][j] * x[j]).sum())
        .collect();
    let g: Vec<f64> = (0..n).map(|i| 2.0 * (hx[i] + c[i])).collect();
    let scale = hx.iter().chain(c).fold(1.0f64, |m, v| m.max(2.0 * v.abs()));
    let at = |b: Option<f64>, v: f64| b.is_some_and(|b| (v - b).abs() <= 1e-12 * b.abs().max(1.0));
    let free: Vec<usize> = (0..n)
        .filter(|&j| !at(lower[j], x[j]) && !at(upper[j], x[j]))
        .collect();
    // With a budget row of ones, lambda = -mean of g over the free coordinates.
    #[allow(clippy::cast_precision_loss)]
    let lambda = if budget && !free.is_empty() {
        -free.iter().map(|&j| g[j]).sum::<f64>() / free.len() as f64
    } else {
        0.0
    };
    (0..n)
        .map(|j| {
            let gj = g[j] + lambda;
            if free.contains(&j) {
                gj.abs()
            } else if at(lower[j], x[j]) && at(upper[j], x[j]) {
                0.0
            } else if at(lower[j], x[j]) {
                (-gj).max(0.0)
            } else {
                gj.max(0.0)
            }
        })
        .fold(0.0, f64::max)
        / scale
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(200))]

    #[test]
    fn qp_answer_satisfies_kkt_bounds_and_equalities(
        (a, b, w) in system(),
        ridge in prop_oneof![Just(0.0), 0.0..0.5_f64],
        box_width in 0.05..3.0_f64,
        budget in prop::option::of(-0.2..0.2_f64),
    ) {
        let n = a[0].len();
        let lower: Vec<Option<f64>> = (0..n).map(|j| (j % 2 == 0).then_some(-box_width)).collect();
        let upper: Vec<Option<f64>> = (0..n).map(|j| (j != 1).then_some(box_width)).collect();
        let e = vec![vec![1.0; n]];
        let mut p = problem(&a, &b, &w);
        p.ridge = ridge;
        p.lower = Some(&lower);
        p.upper = Some(&upper);
        if let Some(t) = &budget {
            p.eq_matrix = Some(&e);
            p.eq_rhs = Some(std::slice::from_ref(t));
        }
        let Ok(s) = qp_solve(&p) else {
            // Only a near-singular draw may fail; it must say so.
            prop_assert_eq!(code(qp_solve(&p)), "E_SINGULAR");
            return Ok(());
        };
        for j in 0..n {
            prop_assert!(lower[j].is_none_or(|l| s.x[j] >= l) && upper[j].is_none_or(|u| s.x[j] <= u));
        }
        if let Some(t) = budget {
            prop_assert!((s.x.iter().sum::<f64>() - t).abs() < 1e-12);
        }
        let (h, c) = normal(&a, &b, &w, ridge);
        let v = kkt_violation(&h, &c, &s.x, &lower, &upper, budget.is_some());
        prop_assert!(v < 1e-8, "KKT residual {v}");
    }

    #[test]
    fn min_norm_equals_the_unique_solution_on_regular_problems((a, b, w) in system()) {
        let p = problem(&a, &b, &w);
        if let Ok(s) = qp_solve(&p) {
            let mut q = p.clone();
            q.singular = Singular::MinNorm;
            let t = qp_solve(&q).unwrap();
            prop_assert_eq!(t.rank, s.rank);
            let scale = s.x.iter().fold(1.0f64, |m, v| m.max(v.abs()));
            for (u, v) in s.x.iter().zip(&t.x) {
                prop_assert!((u - v).abs() < 1e-9 * scale);
            }
        }
    }

    #[test]
    fn integer_answer_beats_relaxation_and_neighbours(
        (a, b, w) in system(),
        ridge in 0.0..0.3_f64,
        sizes in prop::collection::vec(prop_oneof![Just(1.0), Just(0.5), Just(2.0)], 4),
        bounded in any::<bool>(),
    ) {
        let n = a[0].len();
        let b: Vec<f64> = b.iter().map(|v| v * 4.0).collect();
        let lo: Vec<Option<i64>> = (0..n).map(|j| (bounded && j == 0).then_some(-1)).collect();
        let hi: Vec<Option<i64>> = (0..n).map(|j| (bounded && j == 0).then_some(1)).collect();
        let mut p = lots_problem(&a, &b, &w, &sizes[..n]);
        p.ridge = ridge;
        p.lower_lots = Some(&lo);
        p.upper_lots = Some(&hi);
        let Ok(s) = integer_solve(&p) else {
            prop_assert_eq!(code(integer_solve(&p)), "E_SINGULAR");
            return Ok(());
        };
        prop_assert!(s.objective >= s.continuous_objective * (1.0 - 1e-12) - 1e-12);
        let value = |lots: &[i64]| {
            let x: Vec<f64> = lots.iter().zip(&sizes).map(|(l, s)| {
                #[allow(clippy::cast_precision_loss)]
                let l = *l as f64;
                l * s
            }).collect();
            let r: Vec<f64> = a.iter().zip(&b).map(|(row, bi)| row.iter().zip(&x).map(|(p, q)| p * q).sum::<f64>() + bi).collect();
            r.iter().zip(&w).map(|(r, w)| w * r * r).sum::<f64>() + ridge * x.iter().map(|v| v * v).sum::<f64>()
        };
        for j in 0..n {
            for step in [-1, 1] {
                let mut m = s.lots.clone();
                m[j] += step;
                if lo[j].is_some_and(|l| m[j] < l) || hi[j].is_some_and(|h| m[j] > h) {
                    continue;
                }
                prop_assert!(value(&m) >= s.objective * (1.0 - 1e-12));
            }
        }
    }

    #[test]
    fn minvar_effectiveness_is_the_ols_r_squared(
        k in 1usize..3,
        rows in prop::collection::vec(prop::collection::vec(-1.0..1.0_f64, 3), 8..30),
        loads in prop::collection::vec(-2.0..2.0_f64, 2),
    ) {
        let h: Matrix = (0..k).map(|j| rows.iter().map(|r| r[j]).collect()).collect();
        let e: Vec<f64> = rows.iter().map(|r| (0..k).map(|j| loads[j] * r[j]).sum::<f64>() + 0.5 * r[2]).collect();
        let Ok(r) = minvar_ratio(MinVarInput::Series(&e, &h)) else { return Ok(()); };
        // OLS with intercept: centre, solve the normal equations, R^2 = 1 - SSR / SST.
        #[allow(clippy::cast_precision_loss)]
        let mean = |v: &[f64]| v.iter().sum::<f64>() / v.len() as f64;
        let ce: Vec<f64> = e.iter().map(|v| v - mean(&e)).collect();
        let ch: Matrix = h.iter().map(|s| s.iter().map(|v| v - mean(s)).collect()).collect();
        let xtx: Matrix = (0..k).map(|i| (0..k).map(|j| ch[i].iter().zip(&ch[j]).map(|(p, q)| p * q).sum()).collect()).collect();
        let xty: Vec<f64> = (0..k).map(|i| ch[i].iter().zip(&ce).map(|(p, q)| p * q).sum()).collect();
        let beta = solve(&xtx, &xty).unwrap();
        let ssr: f64 = (0..e.len()).map(|t| { let f = ce[t] - (0..k).map(|j| beta[j] * ch[j][t]).sum::<f64>(); f * f }).sum();
        let sst: f64 = ce.iter().map(|v| v * v).sum();
        prop_assert!((r.effectiveness - (1.0 - ssr / sst)).abs() < 1e-10);
        for (h, b) in r.hedge.iter().zip(&beta) {
            prop_assert!((h + b).abs() < 1e-9 * b.abs().max(1.0));
        }
    }

    #[test]
    fn residual_contributions_sum_to_the_variance(
        (a, b, _w) in system(),
        x in prop::collection::vec(-3.0..3.0_f64, 4),
        f in prop::collection::vec(-1.0..1.0_f64, 36),
    ) {
        let (m, n) = (a.len(), a[0].len());
        // S = F F^T is positive semi-definite.
        let s: Matrix = (0..m).map(|i| (0..m).map(|j| (0..6).map(|q| f[i * 6 % 36 + q % 6] * f[j * 6 % 36 + q % 6]).sum()).collect()).collect();
        let Ok(r) = residual_report(&a, &b, &x[..n], &s) else { return Ok(()); };
        let total: f64 = r.contributions.iter().sum();
        prop_assert!((total - r.variance_after).abs() <= 1e-12 * r.variance_after.abs().max(1e-300) + 1e-15);
    }
}

#[test]
fn costs_any_is_true_when_any_single_input_is_given() {
    // I-27: `any` is an OR over the five optional inputs; each alone must switch it on.
    let v = [1.0];
    let none = Costs::default();
    assert!(!none.any());
    for c in [
        Costs {
            half_spreads: Some(&v),
            ..none
        },
        Costs {
            impact: Some(&v),
            ..none
        },
        Costs {
            cost_weight: Some(1.0),
            ..none
        },
        Costs {
            margin_rates: Some(&v),
            ..none
        },
        Costs {
            margin_limit: Some(1.0),
            ..none
        },
    ] {
        assert!(c.any(), "{c:?}");
    }
}

#[test]
fn empty_rows_are_rejected_even_with_rows_present() {
    // Check 1: n == 0 alone is an input error (one row, no columns).
    let a: Matrix = vec![vec![]];
    assert_eq!(code(qp_solve(&problem(&a, &[1.0], &[1.0]))), "E_INPUT");
}

#[test]
fn integer_sized_bound_violation_is_still_enforced() {
    // min (x + 3)^2 subject to x >= 0 (the hedge offsets b, so b = 3 gives x = -3 unconstrained): the unconstrained minimiser -3 violates the bound by an
    // exact multiple of the constraint scale (1), and the answer is the bound, x = 0.
    let a: Matrix = vec![vec![1.0]];
    let lower = [Some(0.0)];
    let mut p = problem(&a, &[3.0], &[1.0]);
    p.lower = Some(&lower);
    let s = qp_solve(&p).unwrap();
    assert!(s.x[0].abs() < 1e-12, "{s:?}");
}

// ---- J-0 hs-audit: kill tests for mutants the scoped run left open (2026-11-14) ----

#[test]
fn check_system_names_the_shape_error_for_one_row_without_columns() {
    // check_system 163:15 (`||` -> `&&`): one row and no columns must fail in check 1 itself,
    // not in a later check with another message; integer_solve has no later shape check that
    // catches n == 0 with matching lot lists.
    let a: Matrix = vec![vec![]];
    let e = qp_solve(&problem(&a, &[1.0], &[1.0])).unwrap_err();
    assert_eq!(
        (e.code, e.message.as_str()),
        (
            "E_INPUT",
            "a must be a non-empty matrix with rows of one length"
        )
    );
    let e = integer_solve(&lots_problem(&a, &[1.0], &[1.0], &[])).unwrap_err();
    assert_eq!(
        (e.code, e.message.as_str()),
        (
            "E_INPUT",
            "a must be a non-empty matrix with rows of one length"
        )
    );
}

#[test]
fn bound_violated_by_an_exact_multiple_of_its_scale_is_enforced_on_the_unscaled_path() {
    // dual_active_set 340:39 (`/` -> `%`): a ridge keeps the solve unscaled (no final clamp).
    // H = 2, c = 6, so x = -3 unconstrained; slack -3 is an exact multiple of the scale 1 and
    // `-3 % 1 == -0` would hide the violation.
    let a: Matrix = vec![vec![1.0]];
    let lower = [Some(0.0)];
    let mut p = problem(&a, &[6.0], &[1.0]);
    p.ridge = 1.0;
    p.lower = Some(&lower);
    assert_eq!(qp_solve(&p).unwrap().x, vec![0.0]);
}

#[test]
fn bound_almost_parallel_to_an_equality_is_enforced() {
    // dual_active_set 340:39 (`/` -> `*`): with x0 + 1e-7 x1 = 0 the bound x0 >= 0 has a
    // projected normal of norm 1e-7, so its scale is 1e-7. Unconstrained on the equality,
    // x1 ~ 0.5 and x0 ~ -5e-8: slack / scale ~ -0.5 (violated), slack * scale ~ -5e-15 (not).
    let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let e = vec![vec![1.0, 1e-7]];
    let lower = [Some(0.0), None];
    let mut p = problem(&a, &[0.0, -0.5], &[1.0, 1.0]);
    p.ridge = 1e-3;
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&[0.0]);
    p.lower = Some(&lower);
    let s = qp_solve(&p).unwrap();
    assert!(s.x[0] >= 0.0, "{s:?}");
}

#[test]
fn violation_exactly_at_the_threshold_is_not_enforced() {
    // dual_active_set 341:33 (`<` -> `<=`): H = 2, c = 2e-12 gives x = -1e-12 exactly, slack
    // over scale exactly -THRESHOLD; the strict test leaves the bound inactive (x unchanged).
    let a: Matrix = vec![vec![1.0]];
    let lower = [Some(0.0)];
    let mut p = problem(&a, &[2e-12], &[1.0]);
    p.ridge = 1.0;
    p.lower = Some(&lower);
    assert_eq!(qp_solve(&p).unwrap().x, vec![-1e-12]);
}

#[test]
fn active_set_on_a_stiff_unscaled_problem_is_not_singular() {
    // general_inverse 273:23 (`1e-14 * largest` -> `/`): H = 1e16 + 1 (ridge keeps it unscaled),
    // so the active-set Gram matrix is ~1e-16; a limit of 1e-14 / 1e-16 = 100 would call it
    // singular. x = -1 unconstrained, the bound holds it at 0.
    let a: Matrix = vec![vec![1e8]];
    let lower = [Some(0.0)];
    let mut p = problem(&a, &[1e8], &[1.0]);
    p.ridge = 1.0;
    p.lower = Some(&lower);
    assert_eq!(qp_solve(&p).unwrap().x, vec![0.0]);
}

#[test]
fn equality_almost_along_an_axis_keeps_its_null_space() {
    // householder_qr 189:36 / 189:44 / 193:16: a reflector built as x - sign(x0) |x| e1
    // cancels when x is almost +-|x| e1; for (+-1, 1e-8) it leaves v = (0, 1e-8), a reflector
    // that does not zero the column, and the null space is then off by 1e-8. With x1 ~ 1e6 the
    // equality would miss by 1e-2.
    for s in [1.0, -1.0] {
        let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let e = vec![vec![s, 1e-8]];
        let p = QpProblem {
            eq_matrix: Some(&e),
            eq_rhs: Some(&[0.0]),
            ..problem(&a, &[0.0, -1e6], &[1.0, 1.0])
        };
        let x = qp_solve(&p).unwrap().x;
        assert!((s * x[0] + 1e-8 * x[1]).abs() < 1e-9, "{s}: {x:?}");
        assert!((x[0] + s * 1e-2).abs() < 1e-6, "{s}: {x:?}");
    }
}

#[test]
fn dual_step_drops_the_constraint_with_the_smallest_ratio() {
    // dual_active_set 380:38 (`u / r < t1` -> `u * r` or `u % r`): the drop test must compare
    // ratios. Found by a seeded search (box bounds, ridge 0.01 keeps the solve unscaled, so no
    // final clamp hides an error): with products the step overshoots and the answer is a
    // corner with KKT residual 0.12.
    let a: Matrix = vec![
        vec![
            -0.339_357_646_379_478_5,
            -0.074_194_689_193_166_41,
            -1.797_542_653_192_188_3,
        ],
        vec![
            0.103_699_644_733_219_46,
            1.712_960_260_968_014_6,
            1.231_046_582_155_376_9,
        ],
        vec![
            -0.921_126_400_769_898_3,
            -1.936_492_988_291_374_8,
            1.180_100_057_902_588_4,
        ],
        vec![
            0.332_704_307_172_170_03,
            -1.029_228_118_995_017_6,
            -0.438_789_860_284_495_07,
        ],
    ];
    let b = [
        -3.938_971_148_748_277_3,
        -0.330_648_934_104_705_86,
        4.555_863_855_195_139,
        3.019_259_704_991_169_4,
    ];
    let w = [1.0; 4];
    let bw = 0.364_602_731_721_537_2;
    let lower = [Some(-bw); 3];
    let upper = [Some(bw); 3];
    let mut p = problem(&a, &b, &w);
    p.ridge = 0.01;
    p.lower = Some(&lower);
    p.upper = Some(&upper);
    let s = qp_solve(&p).unwrap();
    assert!(s.x.iter().all(|x| x.abs() <= bw), "{s:?}");
    let (h, c) = normal(&a, &b, &w, 0.01);
    let v = kkt_violation(&h, &c, &s.x, &lower, &upper, false);
    assert!(v < 1e-8, "KKT residual {v}: {s:?}");
}

#[test]
fn margin_held_zero_uses_the_product_of_multiplier_and_rate() {
    // min (x1 - 3)^2 + (x2 - 16)^2 subject to |x1| + 10 |x2| <= 1. Margin spent on x1 is cheaper:
    // x = (1, 0) with margin multiplier mu = 4 (full scale). At x2 = 0 the push is 2 * 16 = 32,
    // inside the kink room mu * m2 = 40, so x2 stays at 0. A room of mu + m2 = 14 would release
    // x2 and leave the sign-state loop cycling (mutant hedge_solvers.rs:769 `*` -> `+`).
    let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let (b, w, m) = ([-3.0, -16.0], [1.0, 1.0], [1.0, 10.0]);
    let mut p = problem(&a, &b, &w);
    p.costs = Costs {
        margin_rates: Some(&m),
        margin_limit: Some(1.0),
        ..Costs::default()
    };
    let s = qp_solve(&p).unwrap();
    assert!(
        (s.x[0] - 1.0).abs() < 1e-12 && s.x[1].abs() < 1e-12,
        "{:?}",
        s.x
    );
}

#[test]
fn beta_futures_rejects_each_non_positive_input_alone() {
    // Each of the three positivity conditions fails the call on its own (`||`, not `&&`).
    for (v, f, m) in [(-1.0, 100.0, 50.0), (1e6, 0.0, 50.0), (1e6, 100.0, -50.0)] {
        assert_eq!(code(beta_futures(v, 1.0, 0.0, f, m, false)), "E_DOMAIN");
    }
}

// ---- Lane J-2 (rustkill): survivors of the partial cargo-mutants run on hedge_solvers.rs ----
// Expected values are derived by hand from the optimality conditions, not pinned from output.

/// `min sum 4 (x_j + b_j)^2 + 0.5 x_j^2 + 0.1 |x_j|` with A = I: setting the derivative
/// `8 (x + b) + x + 0.1 s` to zero gives `x_j = (-8 b_j - 0.1 s) / 9`, and 0 when
/// `|8 b_j| <= 0.1`. Weights 4 and the impact make the Jacobi scale `1 / sqrt(4.5)`, not 1.
fn kinked_problem_check(lower: &[Option<f64>], upper: &[Option<f64>], e: &Matrix, rhs: &[f64]) {
    let a: Matrix = (0..4)
        .map(|i| (0..4).map(|j| f64::from(u8::from(i == j))).collect())
        .collect();
    let b = [0.3, -1.0, -0.01, 1.0];
    let w = [4.0; 4];
    let hs = [0.1; 4];
    let im = [0.5; 4];
    let mut p = problem(&a, &b, &w);
    p.eq_matrix = Some(e);
    p.eq_rhs = Some(rhs);
    p.lower = Some(lower);
    p.upper = Some(upper);
    p.costs.half_spreads = Some(&hs);
    p.costs.impact = Some(&im);
    let s = qp_solve(&p).unwrap();
    // x0 fixed by the equality; x1 = 7.9 / 9; x2 at the kink (|8 b2| = 0.08); x3 = -7.9 / 9.
    let want = [-1.0, 7.9 / 9.0, 0.0, -7.9 / 9.0];
    for (x, w) in s.x.iter().zip(want) {
        assert!((x - w).abs() <= 1e-12, "{:?}", s.x);
    }
    assert_eq!(
        s.x[2], 0.0,
        "a coordinate at the kink is exactly zero: {:?}",
        s.x
    );
}

#[test]
fn kinked_solve_with_signs_fixed_by_bounds_and_an_equality_is_exact() {
    // nonsmooth_minimiser split stage (661-722), and qp_solve 877-879 (the scaled problem must
    // carry the scaled costs: dropping them changes the answer when D != 1): the split problem only proposes the sign
    // state. Each nonzero coordinate here has a bound or equality that makes the wrong sign
    // infeasible, so a wrong proposal ends in the "no feasible sign state" return of the
    // inexact split answer (error ~1e-6 from the delta regulariser), or in E_INFEASIBLE.
    let e = vec![vec![1.0, 0.0, 0.0, 0.0]];
    kinked_problem_check(
        &[None, Some(0.5), None, None],
        &[None, None, None, Some(-0.5)],
        &e,
        &[-1.0],
    );
}

#[test]
fn ridged_mixed_unit_columns_are_full_rank() {
    // jacobi 507:23 (`>` -> `<`) and 508:21 (`/` -> `*`): a ridge keeps qp_solve on the
    // unscaled path, where only `jacobi` puts H = diag(1e12, 0.25) on a common scale. Unscaled,
    // the small eigenvalue is 2.5e-13 of the large one (below 1e-12): false E_SINGULAR. (A
    // wider ratio would trip the 1e-14 pivot limit of the unscaled active-set inverse.)
    let a: Matrix = vec![vec![1e6, 0.0], vec![0.0, 0.5]];
    let mut p = problem(&a, &[-2e6, 1.5], &[1.0, 1.0]);
    p.ridge = 1e-300;
    let s = qp_solve(&p).unwrap();
    assert_eq!(s.rank, 2);
    // x_j = -b_j / a_jj (the ridge is far below rounding).
    assert!(
        (s.x[0] - 2.0).abs() <= 1e-12 && (s.x[1] + 3.0).abs() <= 1e-12,
        "{s:?}"
    );
}

#[test]
fn equality_rows_of_very_different_norms_are_independent() {
    // scaled_rows 534:43 (`x * x` -> `x + x`, `x / x`), 535:21 (`>` -> `<`, `==`), 536:36
    // (`/` -> `*`): the rank test of the equalities runs on unit-norm rows. Unnormalised (or
    // with a NaN norm, which skips the normalisation) the rows -1e13 e0 and e1 have singular
    // values 1e13 and 1: ratio 1e-13, a false "dependent rows" E_SINGULAR.
    let a: Matrix = (0..3)
        .map(|i| (0..3).map(|j| f64::from(u8::from(i == j))).collect())
        .collect();
    let e = vec![vec![-1e13, 0.0, 0.0], vec![0.0, 1.0, 0.0]];
    let mut p = problem(&a, &[0.0, 0.0, -4.0], &[1.0; 3]);
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&[-1e13, 2.0]);
    let s = qp_solve(&p).unwrap();
    // x0 = 1 and x1 = 2 from the equalities; x2 = -b2 = 4.
    for (x, w) in s.x.iter().zip([1.0, 2.0, 4.0]) {
        assert!((x - w).abs() <= 1e-12, "{s:?}");
    }
}

#[test]
fn equality_rows_after_jacobi_scaling_are_independent() {
    // scaled_rows 533:62 (`a * b` -> `a / b`): with H = diag(1e14, 1, 1) (D = diag(1e-7, 1, 1))
    // the rows (1e7, 1, 0) and (1e7, -1, 0) become (1, 1, 0) and (1, -1, 0) under E D, which are
    // orthogonal. Under E / D they are (1e14, +-1, 0): nearly parallel, singular-value ratio
    // ~1e-14, a false E_SINGULAR. The ridge keeps the solve unscaled, so only this D acts.
    let a: Matrix = vec![
        vec![1e7, 0.0, 0.0],
        vec![0.0, 1.0, 0.0],
        vec![0.0, 0.0, 1.0],
    ];
    let e = vec![vec![1e7, 1.0, 0.0], vec![1e7, -1.0, 0.0]];
    let mut p = problem(&a, &[0.0, 0.0, -5.0], &[1.0; 3]);
    p.ridge = 1e-300;
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&[1e7 + 2.0, 1e7 - 2.0]);
    let s = qp_solve(&p).unwrap();
    // The equalities give x0 = 1, x1 = 2; x2 = 5.
    let want = [1.0, 2.0, 5.0];
    for (x, w) in s.x.iter().zip(want) {
        assert!((x - w).abs() <= 1e-9, "{s:?}");
    }
}

#[test]
fn a_zero_equality_row_is_dependent() {
    // scaled_rows 535:21 (`>` -> `>=`): a zero row normalised by its zero norm becomes NaN, and
    // a NaN singular value passes the `<=` rank test; the zero row must give E_SINGULAR.
    let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let e = vec![vec![1.0, 0.0], vec![0.0, 0.0]];
    let mut p = problem(&a, &[0.0, 0.0], &[1.0, 1.0]);
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&[1.0, 0.0]);
    assert_eq!(code(qp_solve(&p)), "E_SINGULAR");
}

#[test]
fn reduced_rank_limit_scales_with_the_largest_eigenvalue() {
    // scaled_reduced_rank 556:27 (`THRESHOLD * scale` -> `/`): two columns at angle theta with
    // 1 - cos theta = 1e-12. The scaled H has eigenvalues 2 - 1e-12 and 1e-12, below the limit
    // 1e-12 * (2 - 1e-12), so E_SINGULAR. Divided, the limit is 5e-13 and the problem passes.
    let theta = (2.0e-12f64).sqrt();
    let a: Matrix = vec![vec![1.0, theta.cos()], vec![0.0, theta.sin()]];
    let p = problem(&a, &[1.0, 1.0], &[1.0, 1.0]);
    assert_eq!(code(qp_solve(&p)), "E_SINGULAR");
}

#[test]
fn non_orthogonal_equalities_give_the_minimum_norm_point() {
    // null_space 460:45 (`*` -> `/`) and 461:24 (`-` -> `+`): with two non-orthogonal rows the
    // forward substitution uses R[0][1] != 0. min |x|^2 with x0 + x1 = 1, x1 + x2 = 1 is
    // E^T (E E^T)^{-1} (1, 1) = (1/3, 2/3, 1/3).
    let a: Matrix = (0..3)
        .map(|i| (0..3).map(|j| f64::from(u8::from(i == j))).collect())
        .collect();
    let e = vec![vec![1.0, 1.0, 0.0], vec![0.0, 1.0, 1.0]];
    let mut p = problem(&a, &[0.0; 3], &[1.0; 3]);
    p.ridge = 1.0; // unscaled path; objective 2 |x|^2, same minimiser
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&[1.0, 1.0]);
    let s = qp_solve(&p).unwrap();
    let want = [1.0 / 3.0, 2.0 / 3.0, 1.0 / 3.0];
    for (x, w) in s.x.iter().zip(want) {
        assert!((x - w).abs() <= 1e-14, "{s:?}");
    }
}

#[test]
fn tiny_violation_of_a_bound_with_a_tiny_projected_normal_is_enforced() {
    // minimise_with_multipliers 599:29 (`norm * max(|rhs|, 1)` -> `+`): x0 + 1e-7 x1 = 0 gives
    // the bound x0 >= 0 a projected normal of norm 1e-7. Unconstrained, x1 ~ 1e-8 and
    // x0 ~ -1e-15: slack / (1e-7) ~ -1e-8 is a violation; slack / (1e-7 + 1) ~ -1e-15 is not.
    // With the bound, x0 = 0 and then x1 = 0 exactly.
    let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let e = vec![vec![1.0, 1e-7]];
    let lower = [Some(0.0), None];
    let mut p = problem(&a, &[0.0, -1e-8], &[1.0, 1.0]);
    p.ridge = 1e-3;
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&[0.0]);
    p.lower = Some(&lower);
    let s = qp_solve(&p).unwrap();
    assert_eq!(s.x[0], 0.0, "{s:?}");
    assert!(s.x[1].abs() <= 1e-22, "{s:?}");
}

#[test]
fn bound_violation_within_relative_tolerance_of_a_large_bound_is_left() {
    // minimise_with_multipliers 599:29 (`norm * max(|rhs|, 1)` -> `norm / max(|rhs|, 1)`): the
    // bound x >= 1e8 at x = 1e8 - 1e-6 has slack / scale = -1e-6 / 1e8 = -1e-14, inside the
    // 1e-12 tolerance, so it stays inactive and x is the unconstrained minimiser. Divided, the
    // scale is 1e-8, the slack ratio -100, and the bound is snapped to exactly 1e8.
    let a: Matrix = vec![vec![1.0]];
    let target = 1e8 - 1e-6;
    let lower = [Some(1e8)];
    let b = [-target];
    let mut p = problem(&a, &b, &[1.0]);
    p.ridge = 1e-300;
    p.lower = Some(&lower);
    let s = qp_solve(&p).unwrap();
    assert_eq!(s.x, vec![target]);
}

#[test]
fn option_hedge_lots_neutralises_delta_with_whole_lots() {
    // option_hedge_lots 2027:29 (`lot_size <= 0` -> `>`): a valid call must not be E_DOMAIN.
    // Book: 1000 units of the underlying (delta 1000). Hedge: the underlying in lots of 100, no
    // spread. Delta-neutral is exactly -10 lots, after-delta 0.
    let hedges = [LotHedge {
        leg: UNDERLYING,
        lot_size: 100.0,
        half_spread: 0.0,
    }];
    let r = option_hedge_lots(
        &MARKET,
        &[(UNDERLYING, 1000.0)],
        &hedges,
        &[Greek::Delta],
        50,
    )
    .unwrap();
    assert_eq!(r.lots, vec![-10]);
    assert!(
        (r.before[0] - 1000.0).abs() <= 1e-9 && r.after[0].abs() <= 1e-9,
        "{r:?}"
    );
    let zero = [LotHedge {
        lot_size: 0.0,
        ..hedges[0]
    }];
    assert_eq!(
        code(option_hedge_lots(
            &MARKET,
            &[(UNDERLYING, 1000.0)],
            &zero,
            &[Greek::Delta],
            50
        )),
        "E_DOMAIN"
    );
}

#[test]
fn binding_margin_on_the_scaled_path_uses_the_caller_units() {
    // min (2x - 2)^2 subject to |x| <= 0.5 (rate 1). No ridge and H = 4, so the solve runs in
    // Jacobi-scaled y = 2x, where the rate becomes 1/2. The answer is the margin edge x = 0.5;
    // applying the unscaled rate to y would give |y| <= 0.5, that is x = 0.25.
    let a: Matrix = vec![vec![2.0]];
    let (b, w, m) = ([-2.0], [1.0], [1.0]);
    let mut p = problem(&a, &b, &w);
    p.costs = Costs {
        margin_rates: Some(&m),
        margin_limit: Some(0.5),
        ..Costs::default()
    };
    let s = qp_solve(&p).unwrap();
    assert!((s.x[0] - 0.5).abs() < 1e-12, "{:?}", s.x);
}

#[test]
fn selection_passes_each_subset_its_own_bounds() {
    // min (x1 - 3)^2 + (x2 - 1)^2 with x1 in [-10, 2], at most one instrument. {0} alone sits at
    // its bound x1 = 2 (objective 1 + 1 = 2); {1} alone gives x2 = 1 (objective 9). The bounds of
    // a one-column subset have one entry: the full two-entry lists are a shape error there.
    let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let (b, w) = ([-3.0, -1.0], [1.0, 1.0]);
    let (lo, hi) = ([Some(-10.0), None], [Some(2.0), None]);
    let mut p = problem(&a, &b, &w);
    p.lower = Some(&lo);
    p.upper = Some(&hi);
    let s = select_solve(&p, 1, false).unwrap();
    assert_eq!(s.selected, vec![0]);
    assert!((s.x[0] - 2.0).abs() < 1e-12 && s.x[1] == 0.0, "{:?}", s.x);
}

#[test]
fn margin_spent_by_an_equality_alone_is_infeasible_with_three_instruments() {
    // x3 = -2 is forced, but |x1| + |x2| + |x3| <= 1. The split stage must count the short part
    // of every instrument in the margin row (2n entries); dropping the last one would accept
    // the split point and return it although it breaks the margin.
    let a: Matrix = vec![
        vec![1.0, 0.0, 0.0],
        vec![0.0, 1.0, 0.0],
        vec![0.0, 0.0, 1.0],
    ];
    let (b, w, m) = ([0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]);
    let e: Matrix = vec![vec![0.0, 0.0, 1.0]];
    let rhs = [-2.0];
    let mut p = problem(&a, &b, &w);
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&rhs);
    p.costs = Costs {
        margin_rates: Some(&m),
        margin_limit: Some(1.0),
        ..Costs::default()
    };
    assert_eq!(code(qp_solve(&p)), "E_INFEASIBLE");
}

#[test]
fn upper_bound_of_a_later_instrument_holds_in_the_split_stage() {
    // x2 = 0 is forced but x2 <= -1, with a spread so the cost path runs: infeasible. The split
    // row of bound j must read x_j = p_j - n_j; for j = 1 of n = 2 a row on p_1 alone would be
    // met by p_2 = n_2 = 1 and the split point returned.
    let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let (b, w, hs) = ([-1.0, 0.0], [1.0, 1.0], [0.1, 0.1]);
    let e: Matrix = vec![vec![0.0, 1.0]];
    let rhs = [0.0];
    let hi = [None, Some(-1.0)];
    let mut p = problem(&a, &b, &w);
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&rhs);
    p.upper = Some(&hi);
    p.costs = Costs {
        half_spreads: Some(&hs),
        cost_weight: Some(1.0),
        ..Costs::default()
    };
    assert_eq!(code(qp_solve(&p)), "E_INFEASIBLE");
}


/// J-I.2: an equality forcing `x_0 = 1e-9` while `x_1` is near 1000 put `x_0` under the R6-6.1
/// kink tolerance (`1e-11 * 1000`), so the first orthant fixed it at 0 and had no feasible point;
/// the split point (`x_0 = 1.004e-9`, off the equality, `x_1 = 999.949`) came back. The exact
/// answer is `x = (1e-9, 999.95)` (golden `hedgesign_j-0001`).
#[test]
fn tolerance_zero_forced_nonzero_by_an_equality_is_released() {
    let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let (w, hs) = (vec![1.0, 1.0], [0.1, 0.1]);
    let e: Matrix = vec![vec![1.0, 0.0]];
    for (b1, r, x1) in [(-1000.0, 1e-9, 999.95), (1000.0, -1e-9, -999.95)] {
        let b = vec![-1.0, b1];
        let rhs = [r];
        let mut p = problem(&a, &b, &w);
        p.eq_matrix = Some(&e);
        p.eq_rhs = Some(&rhs);
        p.costs.half_spreads = Some(&hs);
        let s = qp_solve(&p).unwrap();
        assert_eq!(s.x[0], r);
        assert!((s.x[1] - x1).abs() <= 1e-12 * x1.abs(), "{:?}", s.x);
    }
}

/// J-I.3: costs or margin in the problem are refused by `select_solve`, not dropped.
#[test]
fn selection_refuses_costs_and_margin() {
    let a: Matrix = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
    let (b, w) = (vec![-1.0, -1.0], vec![1.0, 1.0]);
    let hs = [0.1, 0.1];
    let mut p = problem(&a, &b, &w);
    assert!(select_solve(&p, 1, false).is_ok());
    p.costs.half_spreads = Some(&hs);
    assert_eq!(code(select_solve(&p, 1, false)), "E_INPUT");
    let mut q = problem(&a, &b, &w);
    q.costs.cost_weight = Some(1.0);
    assert_eq!(code(select_solve(&q, 1, false)), "E_INPUT");
    let mut m = problem(&a, &b, &w);
    (m.costs.margin_rates, m.costs.margin_limit) = (Some(&hs[..]), Some(1.0));
    assert_eq!(code(select_solve(&m, 1, false)), "E_INPUT");
}
