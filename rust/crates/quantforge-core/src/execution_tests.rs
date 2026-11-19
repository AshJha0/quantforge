//! Every golden row of the stage H wave 1 specs, plus their property tests.
use super::*;
use proptest::prelude::*;

fn close(a: f64, b: f64, rel: f64) -> bool {
    (a - b).abs() <= rel * b.abs().max(1e-300)
}

fn units(v: &[Amount]) -> Vec<i64> {
    v.iter()
        .map(|a| match a {
            Amount::Units(n) => *n,
            Amount::Real(_) => panic!("expected units"),
        })
        .collect()
}

fn code<T: std::fmt::Debug>(r: Result<T>) -> &'static str {
    r.unwrap_err().code
}

const P: AcParams = AcParams {
    quantity: 1e6,
    horizon: 5.0,
    n_steps: 5,
    sigma: 0.95,
    epsilon: 0.0625,
    eta: 2.5e-6,
    gamma: 2.5e-7,
};

fn with_n(n: i64) -> AcParams {
    AcParams { n_steps: n, ..P }
}

#[test]
fn sched_h_goldens() {
    assert_eq!(
        units(&schedule_twap(1000.0, 3, true).unwrap()),
        [334, 333, 333]
    );
    assert_eq!(
        schedule_twap(1000.0, 4, false).unwrap(),
        vec![Amount::Real(250.0); 4]
    );
    let v = schedule_vwap(1000.0, &[1.0, 2.0, 3.0, 4.0], false).unwrap();
    for (a, b) in v.iter().zip([100.0, 200.0, 300.0, 400.0]) {
        assert!(close(a.value(), b, 1e-15));
    }
    assert_eq!(
        units(&schedule_vwap(10.0, &[1.0, 1.0, 1.0], true).unwrap()),
        [4, 3, 3]
    );
    let r = schedule_pov(1000.0, 0.2, &[1000.0, 2000.0, 4000.0], true).unwrap();
    assert_eq!(units(&r.slices), [250, 500, 250]);
    assert_eq!(
        (r.filled, r.residual),
        (Amount::Units(1000), Amount::Units(0))
    );
    let r = schedule_pov(1000.0, 0.1, &[900.0, 900.0], false).unwrap();
    assert!(r.slices.iter().all(|s| close(s.value(), 100.0, 1e-14)));
    assert!(close(r.residual.value(), 800.0, 1e-14));
    assert_eq!(code(schedule_pov(1000.0, 1.0, &[1.0], true)), "E_DOMAIN");
    assert_eq!(code(schedule_vwap(1000.0, &[0.0, 0.0], true)), "E_DOMAIN");
}

#[test]
fn schedule_rules() {
    assert_eq!(code(schedule_twap(0.0, 3, true)), "E_INPUT");
    assert_eq!(code(schedule_twap(10.5, 3, true)), "E_INPUT");
    assert_eq!(code(schedule_twap(10.0, 0, false)), "E_INPUT");
    assert_eq!(code(schedule_vwap(10.0, &[], true)), "E_INPUT");
    assert_eq!(code(schedule_vwap(10.0, &[1.0, -1.0], true)), "E_DOMAIN");
    assert_eq!(code(schedule_pov(10.0, 0.5, &[], true)), "E_INPUT");
    assert_eq!(code(schedule_pov(10.0, 0.5, &[-1.0], true)), "E_DOMAIN");
    assert_eq!(code(schedule_pov(10.0, 0.0, &[1.0], true)), "E_DOMAIN");
    assert_eq!(largest_remainder(3.0, &[2.0, 1.0, 1.0]), [2, 1, 0]);
    assert_eq!(largest_remainder(4.0, &[1.5, 1.2, 1.3]), [2, 1, 1]);
}

#[test]
fn ac_h_goldens() {
    let r = ac_trajectory(&P, 0.0).unwrap();
    assert_eq!(r.holdings, [1e6, 8e5, 6e5, 4e5, 2e5, 0.0]);
    assert!(close(r.expected_cost, 662_500.0, 1e-14) && close(r.variance, 1.083e12, 1e-14));
    let r = ac_trajectory(&P, 1e-6).unwrap();
    assert!(close(r.kappa, 0.607_076_163_2, 1e-9));
    let want = [
        1e6,
        541_955.554_4,
        289_854.219_4,
        147_897.487_8,
        62_141.801_6,
    ];
    for (a, b) in r.holdings.iter().zip(want) {
        assert!(close(*a, b, 1e-9), "{a} {b}");
    }
    assert_eq!(r.holdings[5], 0.0);
    assert!(close(r.expected_cost, 911_226.986, 1e-9));
    assert!(close(r.variance, 3.641_285_721e11, 1e-9));
    assert!(close(r.objective, 1_275_355.558, 1e-9));
    assert!((r.kappa - 0.6).abs() <= 0.05 && (r.kappa * 5.0 - 3.0).abs() <= 0.25);
    let bad = AcParams {
        gamma: 2.0 * P.eta,
        ..P
    };
    assert_eq!(code(ac_trajectory(&bad, 1e-6)), "E_DOMAIN");
    let r = ac_trajectory(&with_n(1), 1e-6).unwrap();
    assert_eq!(r.holdings, [1e6, 0.0]);
    assert!(close(r.expected_cost, 562_500.0, 1e-14));
}

#[test]
fn ac_rules_in_spec_order() {
    let e = |p: AcParams, l: f64| code(ac_trajectory(&p, l));
    assert_eq!(e(AcParams { sigma: -1.0, ..P }, 0.0), "E_DOMAIN");
    assert_eq!(e(AcParams { horizon: 0.0, ..P }, 0.0), "E_DOMAIN");
    assert_eq!(e(with_n(0), 0.0), "E_INPUT");
    assert_eq!(
        e(
            AcParams {
                sigma: -1.0,
                ..with_n(0)
            },
            0.0
        ),
        "E_INPUT" // two errors: the structural E_INPUT comes before every E_DOMAIN (HR-66, HR-122)
    );
    assert_eq!(
        code(ac_frontier(&AcParams { sigma: -1.0, ..P }, &[])),
        "E_INPUT"
    );
    assert_eq!(code(ac_frontier(&with_n(0), &[])), "E_INPUT");
    assert_eq!(code(schedule_pov(1000.0, 1.5, &[], false)), "E_INPUT");
    assert_eq!(e(AcParams { quantity: 0.0, ..P }, 0.0), "E_INPUT");
    assert_eq!(e(AcParams { epsilon: -1.0, ..P }, 0.0), "E_DOMAIN");
    assert_eq!(e(AcParams { gamma: -1.0, ..P }, 0.0), "E_DOMAIN");
    assert_eq!(e(P, -1e-6), "E_DOMAIN");
    assert_eq!(code(ac_frontier(&P, &[])), "E_INPUT");
    assert_eq!(code(ac_frontier(&P, &[1e-6, -1.0])), "E_DOMAIN");
}

#[test]
fn ac_limits() {
    let lin = ac_trajectory(&P, 0.0).unwrap();
    let tiny = ac_trajectory(&P, 1e-15).unwrap();
    for (a, b) in tiny.holdings.iter().zip(&lin.holdings) {
        // kappa^2 T^2 / 6 = 1.6e-9 at P: the model itself moves this far, so 2e-9 (spec: 1e-9)
        assert!((a - b).abs() <= 2e-9 * b.abs().max(1.0));
    }
    let limit = (1e-6 * 0.95 * 0.95 / P.eta).sqrt();
    let errs: Vec<f64> = [10, 100, 1000]
        .iter()
        .map(|&n| (ac_trajectory(&with_n(n), 1e-6).unwrap().kappa - limit).abs())
        .collect();
    assert!(errs[0] > errs[1] && errs[1] > errs[2]);
    assert!((errs[1] / errs[2] - 10.0).abs() < 2.0);
    let y = 1e-14;
    assert!(close(
        ac_kappa(2.0 * y, 1.0, 1.0, 1.0),
        (2.0 * y).sqrt(),
        1e-12
    ));
    let lam = (200f64.cosh() - 1.0) * 2.0 * 2.375e-6 / (0.95 * 0.95);
    let r = ac_trajectory(&P, lam).unwrap();
    assert!(r.holdings.iter().all(|v| v.is_finite()));
    assert!(r.holdings.windows(2).all(|w| w[1] <= w[0]));
    assert!(close(r.kappa * 5.0, 1000.0, 1e-9));
    assert!(close(sinh_ratio(800.0, 1000.0), (-200f64).exp(), 1e-12));
}

#[test]
fn imp_h_goldens() {
    assert!(close(
        impact_sqrt(1e5, 1e7, 0.02, 1.0).unwrap(),
        0.002,
        1e-15
    ));
    assert!(close(
        impact_sqrt(4e5, 1e7, 0.02, 1.0).unwrap(),
        0.004,
        1e-15
    ));
    assert_eq!(impact_ow_optimal(1000.0, 1.0, 8.0).unwrap(), (100.0, 800.0));
    let (b, r) = impact_ow_optimal(1e5, 1.0, 2.231).unwrap();
    assert!(close(b, 23_635.074_450_484_5, 1e-13) && close(r, 52_729.851_099_031_0, 1e-13));
    assert_eq!(code(impact_sqrt(-1.0, 1e7, 0.02, 1.0)), "E_DOMAIN");
    assert_eq!(code(impact_sqrt(1.0, 0.0, 0.02, 1.0)), "E_DOMAIN");
    assert_eq!(code(impact_sqrt(1.0, 1.0, -0.02, 1.0)), "E_DOMAIN");
    assert_eq!(code(impact_sqrt(1.0, 1.0, 0.02, -1.0)), "E_DOMAIN");
    assert_eq!(code(impact_ow_optimal(0.0, 1.0, 1.0)), "E_INPUT");
    assert_eq!(code(impact_ow_optimal(1.0, 0.0, 1.0)), "E_DOMAIN");
    assert_eq!(code(impact_ow_optimal(1.0, 1.0, 0.0)), "E_DOMAIN");
    assert!(close(
        impact_ow_optimal(1000.0, 1.0, 1e-12).unwrap().0,
        500.0,
        1e-11
    ));
}

fn order(buy: bool, fees: f64) -> TcaOrder {
    TcaOrder {
        buy,
        decision_price: 100.0,
        arrival_price: 100.10,
        end_price: 101.0,
        order_quantity: 1000.0,
        fills: vec![(600.0, 100.20), (200.0, 100.30)],
        fees,
        benchmark_vwap: None,
    }
}

#[test]
fn tca_h_goldens() {
    let r = tca_shortfall(&order(true, 5.0)).unwrap();
    assert!(close(r.delay, 80.0, 1e-10) && close(r.execution, 100.0, 1e-10));
    assert!(close(r.opportunity, 200.0, 1e-10) && close(r.total, 385.0, 1e-10));
    assert!(close(r.total_bps, 38.5, 1e-10) && r.vwap_slippage.is_none());
    let r = tca_shortfall(&order(false, 0.0)).unwrap();
    assert!(close(r.delay, -80.0, 1e-10) && close(r.execution, -100.0, 1e-10));
    assert!(close(r.opportunity, -200.0, 1e-10) && close(r.total, -380.0, 1e-10));
    let over = TcaOrder {
        fills: vec![(600.0, 100.2), (600.0, 100.3)],
        decision_price: -1.0,
        ..order(true, 0.0)
    };
    assert_eq!(code(tca_shortfall(&over)), "E_INPUT");
    let bad = |o: TcaOrder| code(tca_shortfall(&o));
    assert_eq!(
        bad(TcaOrder {
            decision_price: 0.0,
            ..order(true, 0.0)
        }),
        "E_DOMAIN"
    );
    assert_eq!(
        bad(TcaOrder {
            fills: vec![(1.0, -1.0)],
            ..order(true, 0.0)
        }),
        "E_DOMAIN"
    );
    assert_eq!(
        bad(TcaOrder {
            benchmark_vwap: Some(0.0),
            ..order(true, 0.0)
        }),
        "E_DOMAIN"
    );
    assert_eq!(
        bad(TcaOrder {
            fills: vec![(0.0, 1.0)],
            ..order(true, 0.0)
        }),
        "E_INPUT"
    );
    assert_eq!(
        bad(TcaOrder {
            order_quantity: 0.0,
            fills: vec![],
            ..order(true, 0.0)
        }),
        "E_INPUT"
    );
    let r = tca_shortfall(&TcaOrder {
        benchmark_vwap: Some(100.2),
        ..order(true, 0.0)
    })
    .unwrap();
    assert!(close(r.vwap_slippage.unwrap(), 20.0, 1e-9));
}

#[test]
fn as_h_goldens() {
    let q = as_quotes(100.0, 2.0, 0.1, 2.0, 1.0, 1.5).unwrap();
    assert!(close(q.reservation, 99.2, 1e-15));
    assert!((q.spread - 1.690_770_422_8).abs() <= 1e-10);
    assert!((q.bid - 98.354_614_788_6).abs() <= 1e-10);
    assert!((q.ask - 100.045_385_211_4).abs() <= 1e-10);
    let q = as_quotes(100.0, 0.0, 0.1, 2.0, 1.0, 1.5).unwrap();
    assert_eq!(q.reservation, 100.0);
    assert!((q.bid - 99.154_614_788_6).abs() <= 1e-10);
    assert!((q.ask - 100.845_385_211_4).abs() <= 1e-10);
    let q = as_quotes(100.0, 2.0, 0.1, 2.0, 0.0, 1.5).unwrap();
    assert_eq!(q.reservation, 100.0);
    assert!((q.spread - 1.290_770_422_8).abs() <= 1e-10);
    assert_eq!(code(as_quotes(100.0, 2.0, 0.0, 2.0, 1.0, 1.5)), "E_DOMAIN");
    for (g, want, printed) in [
        (0.1, 1.490_770_422_8, 1.49),
        (0.01, 1.348_908_543_7, 1.35),
        (1.0, 3.021_651_247_5, 3.02),
    ] {
        let s = as_quotes(100.0, 0.0, g, 2.0, 0.5, 1.5).unwrap().spread;
        assert!((s - want).abs() <= 1e-10 && (s - printed).abs() <= 0.005);
    }
    assert_eq!(code(as_quotes(100.0, 0.0, 0.1, 2.0, 1.0, 0.0)), "E_DOMAIN");
    assert_eq!(code(as_quotes(100.0, 0.0, 0.1, -2.0, 1.0, 1.5)), "E_DOMAIN");
    assert_eq!(code(as_quotes(100.0, 0.0, 0.1, 2.0, -1.0, 1.5)), "E_DOMAIN");
    let s = as_quotes(100.0, 0.0, 1e-12, 2.0, 1.0, 1.5).unwrap().spread;
    assert!(close(s, 2.0 / 1.5, 1e-9));
}

#[test]
fn frontier_monotone() {
    let lams = [0.0, 1e-8, 1e-7, 1e-6, 2e-6, 1e-5, 1e-4];
    let f = ac_frontier(&P, &lams).unwrap();
    assert!(
        f.windows(2)
            .all(|w| w[1].expected_cost >= w[0].expected_cost)
    );
    assert!(f.windows(2).all(|w| w[1].variance <= w[0].variance));
    assert_eq!(f[3], ac_trajectory(&P, 1e-6).unwrap());
}

proptest! {
    #[test]
    fn twap_units_sum_exactly(x in 1i64..1_000_000_000, n in 1i64..500) {
        #[allow(clippy::cast_precision_loss)]
        let s = units(&schedule_twap(x as f64, n, true).unwrap());
        prop_assert_eq!(s.iter().sum::<i64>(), x);
        prop_assert!(s.iter().max().unwrap() - s.iter().min().unwrap() <= 1);
    }

    #[test]
    fn vwap_units_sum_exactly(x in 1i64..1_000_000_000,
                              w in proptest::collection::vec(0.0f64..1e6, 1..60)) {
        prop_assume!(w.iter().sum::<f64>() > 0.0);
        #[allow(clippy::cast_precision_loss)]
        let s = units(&schedule_vwap(x as f64, &w, true).unwrap());
        prop_assert_eq!(s.iter().sum::<i64>(), x);
        prop_assert!(s.iter().all(|&v| v >= 0));
    }

    #[test]
    fn vwap_continuous_sums(x in 1e-3f64..1e9, w in proptest::collection::vec(0.0f64..1e6, 1..60)) {
        prop_assume!(w.iter().sum::<f64>() > 0.0);
        let total: f64 = schedule_vwap(x, &w, false).unwrap().iter().map(|a| a.value()).sum();
        prop_assert!(close(total, x, 1e-12));
    }

    #[test]
    fn pov_conserves_and_participates(x in 1i64..10_000_000, p in 0.01f64..0.99,
                                      v in proptest::collection::vec(0.0f64..1e7, 1..40),
                                      unit in any::<bool>()) {
        #[allow(clippy::cast_precision_loss)]
        let xf = x as f64;
        let r = schedule_pov(xf, p, &v, unit).unwrap();
        prop_assert!(close(r.filled.value() + r.residual.value(), xf, 1e-12));
        prop_assert!(r.residual.value() >= 0.0);
        let mut remaining = xf;
        for (s, vol) in r.slices.iter().zip(&v) {
            let s = s.value();
            if !unit && s > 0.0 && s < remaining {
                prop_assert!(close(s / (s + vol), p, 1e-12));
            }
            remaining -= s;
        }
    }

    #[test]
    fn ac_trades_sum_and_below_linear(n in 1i64..200, lam in 0.0f64..1e-4) {
        let r = ac_trajectory(&with_n(n), lam).unwrap();
        let total: f64 = r.trades.iter().sum();
        prop_assert!(close(total, 1e6, 1e-12));
        prop_assert!(r.holdings.windows(2).all(|w| w[1] <= w[0]));
        if lam > 1e-9 {
            for j in 1..n {
                #[allow(clippy::cast_precision_loss)]
                let lin = 1e6 * (n - j) as f64 / n as f64;
                prop_assert!(r.holdings[usize::try_from(j).unwrap()] < lin);
            }
        }
    }

    #[test]
    fn ac_frontier_monotone(mut lams in proptest::collection::vec(0.0f64..1e-3, 2..8),
                            n in 1i64..50) {
        lams.sort_by(f64::total_cmp);
        let f = ac_frontier(&with_n(n), &lams).unwrap();
        prop_assert!(f.windows(2).all(|w| w[1].expected_cost >= w[0].expected_cost * (1.0 - 1e-12)));
        prop_assert!(f.windows(2).all(|w| w[1].variance <= w[0].variance * (1.0 + 1e-12)));
    }

    #[test]
    fn ow_conserves(x in 1e-3f64..1e9, t in 1e-3f64..100.0, rho in 1e-6f64..1e3) {
        let (b, r) = impact_ow_optimal(x, t, rho).unwrap();
        prop_assert!(close(2.0 * b + r * t, x, 1e-12));
    }

    #[test]
    fn tca_decomposition_sums(buy in any::<bool>(), pd in 1.0f64..1e4, p0 in 1.0f64..1e4,
                              pc in 1.0f64..1e4,
                              fills in proptest::collection::vec((1.0f64..1e4, 1.0f64..1e4), 0..30),
                              fees in -1e3f64..1e3, full in any::<bool>()) {
        let q: f64 = fills.iter().map(|f| f.0).sum();
        let x = if full && q > 0.0 { q } else { q + 100.0 };
        let r = tca_shortfall(&TcaOrder {
            buy, decision_price: pd, arrival_price: p0, end_price: pc, order_quantity: x,
            fills, fees, benchmark_vwap: None,
        }).unwrap();
        let scale = [r.delay, r.execution, r.opportunity, fees, 1.0]
            .iter().fold(0.0f64, |m, v| m.max(v.abs()));
        prop_assert!((r.delay + r.execution + r.opportunity + fees - r.total).abs() <= 1e-10 * scale);
        if full && q > 0.0 {
            prop_assert!(r.opportunity == 0.0);
        }
    }

    #[test]
    fn as_reservation_decreasing(q1 in -50.0f64..50.0, q2 in -50.0f64..50.0) {
        let a = as_quotes(100.0, q1, 0.1, 2.0, 1.0, 1.5).unwrap();
        let b = as_quotes(100.0, q2, 0.1, 2.0, 1.0, 1.5).unwrap();
        if q1 < q2 - 1e-9 {
            prop_assert!(a.reservation > b.reservation);
        }
        prop_assert!(a.spread == b.spread);
    }
}

#[test]
fn four_build_edge_choices() {
    let r = tca_shortfall(&TcaOrder {
        order_quantity: 800.0,
        ..order(false, 0.0)
    })
    .unwrap();
    assert!(r.opportunity.is_sign_positive());
    let s = schedule_pov(1000.0, 0.2, &[999.999_999_999_999_9], true).unwrap();
    assert_eq!(units(&s.slices), [250]);
    let s = schedule_pov(1000.0, 0.2, &[999.0], true).unwrap();
    assert_eq!(units(&s.slices), [249]);
}

#[test]
fn vwap_subnormal_weight_keeps_the_order() {
    let v = schedule_vwap(1.5, &[5e-324], false).unwrap();
    assert_eq!(v[0].value(), 1.5);
    let v = schedule_vwap(3.0, &[5e-324, 5e-324], false).unwrap();
    assert_eq!(v[0].value(), 1.5);
    assert_eq!(v[1].value(), 1.5);
}
