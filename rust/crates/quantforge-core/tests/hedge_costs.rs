//! Stage I wave 4a costs, impact, margin and the risk-against-cost frontier
//! (`08-hedging/hedge-costs-and-frontier.md`): unit tests and the property tests the spec names.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use proptest::prelude::*;
use quantforge_core::hedge_solvers::{Costs, QpProblem, Singular, frontier_solve, qp_solve};
use quantforge_core::linalg::Matrix;

fn code<T: std::fmt::Debug>(r: quantforge_core::error::Result<T>) -> &'static str {
    r.unwrap_err().code
}

fn base() -> (Matrix, Vec<f64>, Vec<f64>) {
    (
        vec![
            vec![1.0, 0.5, 0.2],
            vec![0.3, 1.2, 0.4],
            vec![0.1, 0.6, 1.5],
            vec![0.8, 0.2, 0.9],
            vec![0.4, 0.9, 0.3],
        ],
        vec![-2.0, 1.5, -0.7, 0.9, -1.1],
        vec![1.0, 2.0, 0.5, 1.5, 1.0],
    )
}

fn problem<'a>(a: &'a Matrix, b: &'a [f64], w: &'a [f64], costs: Costs<'a>) -> QpProblem<'a> {
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
        costs,
    }
}

#[test]
fn a_costly_instrument_is_left_out_exactly() {
    let (a, b, w) = base();
    let spreads = [0.01, 50.0, 0.01];
    let costs = Costs {
        half_spreads: Some(&spreads),
        ..Costs::default()
    };
    let s = qp_solve(&problem(&a, &b, &w, costs)).unwrap();
    assert_eq!(s.x[1], 0.0);
    let cost = 0.01 * (s.x[0].abs() + s.x[2].abs());
    assert!((s.cost.unwrap() - cost).abs() < 1e-15);
    assert!((s.objective - s.risk.unwrap() - cost).abs() < 1e-14);
    assert_eq!(s.margin, None);
    // Without new inputs the wave 1 output set is unchanged.
    let plain = qp_solve(&problem(&a, &b, &w, Costs::default())).unwrap();
    assert_eq!((plain.risk, plain.cost, plain.margin), (None, None, None));
}

#[test]
fn impact_regularises_but_a_spread_does_not() {
    let a = vec![vec![1.0, 1.0], vec![0.5, 0.5]];
    let (b, w) = ([-1.0, 0.5], [1.0, 1.0]);
    let spreads = [0.1, 0.1];
    let impact = [0.01, 0.02];
    let spread_only = Costs {
        half_spreads: Some(&spreads),
        ..Costs::default()
    };
    assert_eq!(
        code(qp_solve(&problem(&a, &b, &w, spread_only))),
        "E_SINGULAR"
    );
    let with_impact = Costs {
        impact: Some(&impact),
        ..spread_only
    };
    let s = qp_solve(&problem(&a, &b, &w, with_impact)).unwrap();
    assert_eq!(s.rank, 2);
    // A cost weight of zero switches impact off again.
    let off = Costs {
        cost_weight: Some(0.0),
        ..with_impact
    };
    assert_eq!(code(qp_solve(&problem(&a, &b, &w, off))), "E_SINGULAR");
}

#[test]
fn cost_checks_in_order() {
    let (a, b, w) = base();
    let short = [0.1, 0.1];
    let ok = [0.1, 0.1, 0.1];
    let neg = [0.1, -0.1, 0.1];
    let c = |costs: Costs| code(qp_solve(&problem(&a, &b, &w, costs)));
    let d = Costs::default();
    assert_eq!(
        c(Costs {
            half_spreads: Some(&short),
            ..d
        }),
        "E_INPUT"
    );
    assert_eq!(
        c(Costs {
            margin_rates: Some(&ok),
            ..d
        }),
        "E_INPUT"
    );
    assert_eq!(
        c(Costs {
            margin_limit: Some(1.0),
            ..d
        }),
        "E_INPUT"
    );
    let mut p = problem(
        &a,
        &b,
        &w,
        Costs {
            impact: Some(&ok),
            ..d
        },
    );
    p.singular = Singular::MinNorm;
    assert_eq!(code(qp_solve(&p)), "E_INPUT");
    assert_eq!(
        c(Costs {
            impact: Some(&neg),
            ..d
        }),
        "E_DOMAIN"
    );
    assert_eq!(
        c(Costs {
            half_spreads: Some(&ok),
            cost_weight: Some(-1.0),
            ..d
        }),
        "E_DOMAIN"
    );
    let margin = Costs {
        margin_rates: Some(&ok),
        margin_limit: Some(-0.1),
        ..d
    };
    assert_eq!(c(margin), "E_DOMAIN");
    let nan = [0.1, f64::NAN, 0.1];
    assert_eq!(
        c(Costs {
            half_spreads: Some(&nan),
            ..d
        }),
        "E_DOMAIN"
    );
    // A bound that needs more margin than the limit allows.
    let lower = [Some(1.0), None, None];
    let tight = Costs {
        margin_rates: Some(&ok),
        margin_limit: Some(0.05),
        ..d
    };
    let mut p = problem(&a, &b, &w, tight);
    p.lower = Some(&lower);
    assert_eq!(code(qp_solve(&p)), "E_INFEASIBLE");
    // Every variable fixed by equalities: margin feasibility is checked on the one point.
    let e = vec![
        vec![1.0, 0.0, 0.0],
        vec![0.0, 1.0, 0.0],
        vec![0.0, 0.0, 1.0],
    ];
    let mut p = problem(&a, &b, &w, tight);
    p.eq_matrix = Some(&e);
    p.eq_rhs = Some(&[0.2, 0.2, 0.2]);
    assert_eq!(code(qp_solve(&p)), "E_INFEASIBLE");
    p.eq_rhs = Some(&[0.1, 0.1, -0.1]);
    assert!((qp_solve(&p).unwrap().margin.unwrap() - 0.03).abs() < 1e-16);
}

#[test]
fn frontier_checks() {
    let (a, b, w) = base();
    let s = [0.05, 0.1, 0.02];
    let p = problem(
        &a,
        &b,
        &w,
        Costs {
            half_spreads: Some(&s),
            ..Costs::default()
        },
    );
    assert_eq!(code(frontier_solve(&p, &[])), "E_INPUT");
    assert_eq!(code(frontier_solve(&p, &[1.0, 1.0])), "E_INPUT");
    assert_eq!(code(frontier_solve(&p, &[-1.0, 1.0])), "E_DOMAIN");
    assert_eq!(code(frontier_solve(&p, &[1.0, f64::INFINITY])), "E_DOMAIN");
    let none = problem(&a, &b, &w, Costs::default());
    assert_eq!(code(frontier_solve(&none, &[1.0])), "E_INPUT");
    let weighted = problem(
        &a,
        &b,
        &w,
        Costs {
            half_spreads: Some(&s),
            cost_weight: Some(1.0),
            ..Costs::default()
        },
    );
    assert_eq!(code(frontier_solve(&weighted, &[1.0])), "E_INPUT");
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(96))]

    #[test]
    fn zero_cost_weight_is_wave_one_and_the_frontier_is_monotone(
        spreads in prop::collection::vec(0.0..0.5_f64, 3),
        impact in prop::collection::vec(0.0..0.2_f64, 3),
        bounded in any::<bool>(),
    ) {
        let (a, b, w) = base();
        let lower = [Some(-0.5), None, Some(-2.0)];
        let mut base_p = problem(&a, &b, &w, Costs::default());
        if bounded {
            base_p.lower = Some(&lower);
        }
        let wave1 = qp_solve(&base_p).unwrap();
        let mut p = base_p.clone();
        p.costs = Costs { half_spreads: Some(&spreads), impact: Some(&impact), cost_weight: Some(0.0), ..Costs::default() };
        let zero = qp_solve(&p).unwrap();
        for (u, v) in wave1.x.iter().zip(&zero.x) {
            prop_assert!((u - v).abs() < 1e-12 * u.abs().max(1.0));
        }
        p.costs.cost_weight = None;
        let points = frontier_solve(&p, &[0.0, 0.5, 1.0, 2.0, 5.0, 20.0]).unwrap();
        for pair in points.windows(2) {
            prop_assert!(pair[1].risk >= pair[0].risk * (1.0 - 1e-10) - 1e-12);
            prop_assert!(pair[1].cost <= pair[0].cost * (1.0 + 1e-10) + 1e-12);
        }
    }

    #[test]
    fn an_active_margin_equals_its_limit(limit in 0.01..0.4_f64, rates in prop::collection::vec(0.05..0.3_f64, 3)) {
        let (a, b, w) = base();
        let costs = Costs { margin_rates: Some(&rates), margin_limit: Some(limit), ..Costs::default() };
        let s = qp_solve(&problem(&a, &b, &w, costs)).unwrap();
        let free = qp_solve(&problem(&a, &b, &w, Costs::default())).unwrap();
        let free_margin: f64 = rates.iter().zip(&free.x).map(|(m, x)| m * x.abs()).sum();
        let m = s.margin.unwrap();
        prop_assert!(m <= limit * (1.0 + 1e-12));
        if free_margin > limit {
            prop_assert!((m - limit).abs() < 1e-12 * limit.max(1.0), "{m} {limit}");
        }
    }
}
