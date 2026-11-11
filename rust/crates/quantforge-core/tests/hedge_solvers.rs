//! Stage I wave 1 hedge solvers (`08-hedging/hedge-solvers.md`): unit tests on hand-sized
//! problems and the property tests the spec names, on generated data.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use proptest::prelude::*;
use quantforge_core::hedge_solvers::{
    Costs, Greek, GreekInstrument, GreekMarket, IntegerProblem, Leg, LegKind, MinVarInput,
    QpProblem, Singular, beta_futures, greeks_neutralise, integer_solve, minvar_ratio, qp_solve,
    residual_report, unit_greeks,
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
