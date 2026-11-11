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

mod selection {
    use super::{base, code, problem};
    use proptest::prelude::*;
    use quantforge_core::hedge_solvers::{Costs, qp_solve, select_solve};

    #[test]
    fn selection_checks_and_ties() {
        let (a, b, w) = base();
        let p = problem(&a, &b, &w, Costs::default());
        assert_eq!(code(select_solve(&p, 0, false)), "E_INPUT");
        assert_eq!(code(select_solve(&p, 4, false)), "E_INPUT");
        assert_eq!(code(select_solve(&p, 2, true)), "E_INPUT");
        let lower = [Some(0.5), None, None];
        let mut q = p.clone();
        q.lower = Some(&lower);
        assert_eq!(code(select_solve(&q, 2, false)), "E_DOMAIN");
        let dup = vec![vec![1.0, 1.0, 0.0], vec![0.5, 0.5, 1.0]];
        let q = problem(&dup, &[-1.0, 0.5], &[1.0, 1.0], Costs::default());
        assert_eq!(code(select_solve(&q, 1, false)), "E_SINGULAR");
        // Two identical instruments plus ridge: an exact tie goes to index 0.
        let mut q = problem(&dup, &[-1.0, 0.5], &[1.0, 1.0], Costs::default());
        q.ridge = 0.01;
        assert_eq!(select_solve(&q, 1, false).unwrap().selected, vec![0]);
    }

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(48))]

        #[test]
        fn all_instruments_give_the_qp_answer_and_more_never_hurts(
            b in prop::collection::vec(-3.0..3.0_f64, 5),
        ) {
            let (a, _, w) = base();
            let p = problem(&a, &b, &w, Costs::default());
            let full = qp_solve(&p).unwrap();
            let mut last = f64::INFINITY;
            for k in 1..=3 {
                let s = select_solve(&p, k, false).unwrap();
                prop_assert!(s.objective <= last * (1.0 + 1e-12));
                last = s.objective;
                if k == 3 {
                    for (u, v) in s.x.iter().zip(&full.x) {
                        prop_assert!((u - v).abs() < 1e-12 * u.abs().max(1.0));
                    }
                }
            }
        }
    }
}

mod switch_points {
    use super::problem;
    use proptest::prelude::*;
    use quantforge_core::hedge_solvers::{Costs, IntegerProblem, integer_solve, qp_solve};
    use quantforge_core::linalg::Matrix;

    /// Largest violation of the KKT conditions of `sum w r^2 + ridge |x|^2 + sum s |x|` (no
    /// bounds, equalities or margin), relative to the gradient scale: `g_j + s_j sign(x_j) = 0`
    /// where `x_j != 0`, and `|g_j| <= s_j` where `x_j = 0`.
    fn kkt(a: &Matrix, b: &[f64], w: &[f64], ridge: f64, s: &[f64], x: &[f64]) -> f64 {
        let r: Vec<f64> = a
            .iter()
            .zip(b)
            .map(|(row, bi)| row.iter().zip(x).map(|(p, q)| p * q).sum::<f64>() + bi)
            .collect();
        let g: Vec<f64> = (0..x.len())
            .map(|j| {
                2.0 * a
                    .iter()
                    .zip(&r)
                    .zip(w)
                    .map(|((row, ri), wi)| row[j] * wi * ri)
                    .sum::<f64>()
                    + 2.0 * ridge * x[j]
            })
            .collect();
        let scale = g.iter().chain(s).fold(1.0f64, |m, v| m.max(v.abs()));
        (0..x.len())
            .map(|j| {
                if x[j] == 0.0 {
                    (g[j].abs() - s[j]).max(0.0)
                } else {
                    (g[j] + s[j] * x[j].signum()).abs()
                }
            })
            .fold(0.0, f64::max)
            / scale
    }

    fn eye() -> Matrix {
        vec![vec![1.0, 0.0], vec![0.0, 1.0]]
    }

    #[test]
    fn exactly_on_a_switch_point_the_position_is_zero() {
        // (x2 - 0.25)^2 + 0.5 |x2|: the gradient at 0 is exactly the spread, so x2 = 0.
        let (a, w, s) = (eye(), [1.0, 1.0], [0.5, 0.5]);
        let b = [-1.0, -0.25];
        let costs = Costs {
            half_spreads: Some(&s),
            ..Costs::default()
        };
        let x = qp_solve(&problem(&a, &b, &w, costs)).unwrap().x;
        assert_eq!(x, vec![0.75, 0.0]);
        assert_eq!(kkt(&a, &b, &w, 0.0, &s, &x), 0.0);
    }

    #[test]
    fn just_past_a_switch_point_the_small_position_is_exact() {
        // 1e-9 past the switch point x2 = 1e-9; a regularised solve would pin it to 0.
        let (a, w, s) = (eye(), [1.0, 1.0], [0.5, 0.5]);
        let b = [-1.0, -(0.25 + 1e-9)];
        let costs = Costs {
            half_spreads: Some(&s),
            ..Costs::default()
        };
        let x = qp_solve(&problem(&a, &b, &w, costs)).unwrap().x;
        assert!((x[1] - 1e-9).abs() < 1e-16, "{}", x[1]);
        assert!(kkt(&a, &b, &w, 0.0, &s, &x) < 1e-15);
        // 1e-9 short of it the position is exactly zero.
        let b = [-1.0, -(0.25 - 1e-9)];
        let x = qp_solve(&problem(&a, &b, &w, costs)).unwrap().x;
        assert_eq!(x[1], 0.0);
        assert!(kkt(&a, &b, &w, 0.0, &s, &x) < 1e-15);
    }

    #[test]
    fn a_binding_margin_on_a_switch_point() {
        // x1 + |x2| <= 0.5 binds; x2 sits at its switch point and stays exactly 0.
        let (a, w, s, m) = (eye(), [1.0, 1.0], [0.5, 0.5], [1.0, 1.0]);
        let b = [-1.0, -0.25];
        let costs = Costs {
            half_spreads: Some(&s),
            margin_rates: Some(&m),
            margin_limit: Some(0.5),
            ..Costs::default()
        };
        let r = qp_solve(&problem(&a, &b, &w, costs)).unwrap();
        assert_eq!(r.x, vec![0.5, 0.0]);
        assert_eq!(r.margin, Some(0.5));
    }

    fn system() -> impl Strategy<Value = (Matrix, Vec<f64>, Vec<f64>)> {
        (2usize..6).prop_flat_map(|n| {
            (
                prop::collection::vec(prop::collection::vec(-2.0..2.0_f64, n), n + 2),
                prop::collection::vec(-3.0..3.0_f64, n + 2),
                prop::collection::vec(0.2..3.0_f64, n + 2),
            )
        })
    }

    proptest! {
        #![proptest_config(ProptestConfig::with_cases(160))]

        #[test]
        fn cost_answer_meets_the_kkt_conditions(
            (a, b, w) in system(),
            spread in prop::collection::vec(0.0..2.0_f64, 6),
            ridge in 0.0..0.3_f64,
        ) {
            let n = a[0].len();
            let mut p = problem(&a, &b, &w, Costs { half_spreads: Some(&spread[..n]), ..Costs::default() });
            p.ridge = ridge;
            if let Ok(s) = qp_solve(&p) {
                let v = kkt(&a, &b, &w, ridge, &spread[..n], &s.x);
                prop_assert!(v < 1e-9, "KKT residual {v}");
            }
        }

        #[test]
        fn instruments_can_be_reordered(
            (a, b, w) in system(),
            spread in prop::collection::vec(0.0..1.0_f64, 6),
            rot in 1usize..5,
        ) {
            let n = a[0].len();
            let perm: Vec<usize> = (0..n).map(|j| (j + rot) % n).collect();
            let ap: Matrix = a.iter().map(|r| perm.iter().map(|&j| r[j]).collect()).collect();
            let sp: Vec<f64> = perm.iter().map(|&j| spread[j]).collect();
            let lower: Vec<Option<f64>> = (0..n).map(|j| (j % 2 == 0).then_some(-0.5)).collect();
            let lp: Vec<Option<f64>> = perm.iter().map(|&j| lower[j]).collect();
            let mut p = problem(&a, &b, &w, Costs { half_spreads: Some(&spread[..n]), ..Costs::default() });
            p.lower = Some(&lower);
            let mut q = problem(&ap, &b, &w, Costs { half_spreads: Some(&sp), ..Costs::default() });
            q.lower = Some(&lp);
            if let (Ok(x), Ok(y)) = (qp_solve(&p), qp_solve(&q)) {
                for (k, &j) in perm.iter().enumerate() {
                    prop_assert!((y.x[k] - x.x[j]).abs() < 1e-10 * x.x[j].abs().max(1.0));
                }
                let lots = vec![1.0; n];
                let ip = |a: &Matrix| integer_solve(&IntegerProblem { a, b: &b, weights: &w, ridge: 0.1, lot_sizes: &lots, lower_lots: None, upper_lots: None });
                if let (Ok(i), Ok(j)) = (ip(&a), ip(&ap)) {
                    // Ties may pick different points, but never a different objective.
                    prop_assert!((i.objective - j.objective).abs() <= 1e-12 * i.objective.max(1e-300) + 1e-14);
                    prop_assert!(i.objective >= i.continuous_objective * (1.0 - 1e-12));
                }
            }
        }
    }
}
