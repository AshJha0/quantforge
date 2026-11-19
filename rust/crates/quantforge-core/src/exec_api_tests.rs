//! H-5 typed layer (`library-interfaces.md` section 2.5): bit-equal to the kernels, invariants at
//! construction with the stated code, enum parse at the edge.
use super::*;
use proptest::prelude::*;

fn code<T: std::fmt::Debug>(r: Result<T>) -> &'static str {
    r.unwrap_err().code
}

fn bits(v: &[f64]) -> Vec<u64> {
    v.iter().map(|x| x.to_bits()).collect()
}

fn amount_bits(v: &[Amount]) -> Vec<(bool, u64)> {
    v.iter()
        .map(|a| match a {
            Amount::Units(n) => (true, *n as u64),
            Amount::Real(x) => (false, x.to_bits()),
        })
        .collect()
}

fn ac() -> AcParams {
    AcParams::new(1e6, 5.0, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7).expect("valid")
}

#[test]
fn invariants_raise_the_stated_code() {
    let mk = |q, t, n, s, e, eta, g| AcParams::new(q, t, n, s, e, eta, g);
    assert_eq!(
        code(mk(1e6, 5.0, 0, 0.95, 0.0625, 2.5e-6, 2.5e-7)),
        "E_INPUT"
    );
    assert_eq!(
        code(mk(0.0, 5.0, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7)),
        "E_INPUT"
    );
    assert_eq!(
        code(mk(1e6, 0.0, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(mk(1e6, 5.0, 5, -1.0, 0.0625, 2.5e-6, 2.5e-7)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(mk(1e6, 5.0, 5, 0.95, -1.0, 2.5e-6, 2.5e-7)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(mk(1e6, 5.0, 5, 0.95, 0.0625, 2.5e-6, -1.0)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(mk(1e6, 5.0, 5, 0.95, 0.0625, 1e-7, 2.5e-7)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(mk(f64::NAN, 5.0, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(mk(1e6, f64::INFINITY, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7)),
        "E_DOMAIN"
    );
    let p = ac();
    assert_eq!(
        (p.quantity(), p.horizon(), p.n_steps(), p.sigma()),
        (1e6, 5.0, 5, 0.95)
    );
    assert_eq!((p.epsilon(), p.eta(), p.gamma()), (0.0625, 2.5e-6, 2.5e-7));

    assert_eq!(code(Fill::new(0.0, 100.0)), "E_INPUT");
    assert_eq!(code(Fill::new(-1.0, 100.0)), "E_INPUT");
    assert_eq!(code(Fill::new(1.0, 0.0)), "E_DOMAIN");
    assert_eq!(code(Fill::new(1.0, f64::NAN)), "E_DOMAIN");
    assert_eq!(code(Fill::new(f64::INFINITY, 1.0)), "E_DOMAIN");

    assert_eq!(code(Quotes::new(100.0, -1.0, 101.0, 99.0)), "E_DOMAIN");
    assert!(Quotes::new(100.0, 0.0, 100.0, 100.0).is_ok());

    assert_eq!(code(twap(f64::NAN, 5, FillMode::Units)), "E_DOMAIN");
    assert_eq!(
        code(vwap(10.0, &[1.0, f64::INFINITY], FillMode::Units)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(as_quotes(100.0, 0.0, 0.1, f64::NAN, 1.0, 1.0)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(shortfall(
            Side::Buy,
            100.0,
            100.0,
            100.0,
            10.0,
            &[],
            0.0,
            Some(f64::INFINITY)
        )),
        "E_DOMAIN"
    );
    assert_eq!(code(twap(10.5, 5, FillMode::Units)), "E_INPUT");
    let big = [Fill::new(2.0, 100.0).expect("valid")];
    assert_eq!(
        code(shortfall(
            Side::Buy,
            100.0,
            100.0,
            100.0,
            1.0,
            &big,
            0.0,
            None
        )),
        "E_INPUT"
    );
}

#[test]
fn enums_parse_at_the_edge_and_round_trip() {
    for s in ["BUY", "SELL"] {
        assert_eq!(Side::parse(s).expect("known").as_str(), s);
    }
    for s in ["UNITS", "CONTINUOUS"] {
        assert_eq!(FillMode::parse(s).expect("known").as_str(), s);
    }
    for s in ["buy", "Buy", "", "SHORT", "BUY "] {
        assert_eq!(code(Side::parse(s)), "E_SCHEMA");
    }
    for s in ["units", "", "LOTS"] {
        assert_eq!(code(FillMode::parse(s)), "E_SCHEMA");
    }
}

#[test]
fn ow_and_frontier_match_the_kernel() {
    let o = ow_optimal(1e6, 1.0, 2.0).expect("ok");
    let (b, r) = k::impact_ow_optimal(1e6, 1.0, 2.0).expect("ok");
    assert_eq!(
        bits(&[o.initial_block(), o.rate(), o.final_block()]),
        bits(&[b, r, b])
    );
    let lams = [0.0, 1e-6, 2e-6];
    let f = ac_frontier(&ac(), &lams).expect("ok");
    let kf = k::ac_frontier(ac().kernel(), &lams).expect("ok");
    assert_eq!(bits(f.risk_aversions()), bits(&lams));
    assert_eq!(
        bits(f.expected_costs()),
        bits(&kf.iter().map(|p| p.expected_cost).collect::<Vec<_>>())
    );
    assert_eq!(
        bits(f.variances()),
        bits(&kf.iter().map(|p| p.variance).collect::<Vec<_>>())
    );
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(200))]

    #[test]
    fn typed_calls_are_bit_equal_to_the_kernels(
        x in 1u32..1_000_000,
        n in 1i64..50,
        units in any::<bool>(),
        w in prop::collection::vec(0.1f64..1.1, 50),
        mv in prop::collection::vec(1.0f64..1e5, 50),
        part in 0.05f64..0.55,
        horizon in 1.0f64..10.0,
        sigma in 0.0f64..1.0,
        lam in 0.0f64..1e-6,
        fq in prop::collection::vec((1u32..100, 99.0f64..101.0), 0..20),
        buy in any::<bool>(),
        bench in prop::option::of(99.0f64..101.0),
        inv in -10.0f64..10.0,
        g in 0.01f64..1.0,
        tl in 0.0f64..1.0,
        kk in 0.1f64..2.0,
    ) {
        let x = f64::from(x);
        let mode = if units { FillMode::Units } else { FillMode::Continuous };
        let nu = n as usize;
        let t = twap(x, n, mode).expect("ok");
        prop_assert_eq!(amount_bits(t.slices()), amount_bits(&k::schedule_twap(x, n, units).expect("ok")));
        let v = vwap(x, &w[..nu], mode).expect("ok");
        prop_assert_eq!(amount_bits(v.slices()), amount_bits(&k::schedule_vwap(x, &w[..nu], units).expect("ok")));
        let p = pov(x, part, &mv[..nu], mode).expect("ok");
        let kp = k::schedule_pov(x, part, &mv[..nu], units).expect("ok");
        prop_assert_eq!(amount_bits(p.slices()), amount_bits(&kp.slices));
        prop_assert_eq!(amount_bits(&[p.filled(), p.residual()]), amount_bits(&[kp.filled, kp.residual]));

        let params = AcParams::new(x, horizon, n, sigma, 0.0625, 2.5e-6, 2.5e-7).expect("valid");
        let a = ac_trajectory(&params, lam).expect("ok");
        let ka = k::ac_trajectory(params.kernel(), lam).expect("ok");
        prop_assert_eq!(bits(a.holdings()), bits(&ka.holdings));
        prop_assert_eq!(bits(a.trades()), bits(&ka.trades));
        prop_assert_eq!(
            bits(&[a.kappa(), a.expected_cost(), a.variance(), a.objective()]),
            bits(&[ka.kappa, ka.expected_cost, ka.variance, ka.objective])
        );

        prop_assert_eq!(
            impact_sqrt(x, 1e7, sigma, 0.5).expect("ok").to_bits(),
            k::impact_sqrt(x, 1e7, sigma, 0.5).expect("ok").to_bits()
        );

        let fills: Vec<Fill> = fq.iter().map(|&(q, pr)| Fill::new(f64::from(q), pr).expect("valid")).collect();
        let side = if buy { Side::Buy } else { Side::Sell };
        let s = shortfall(side, 100.0, 100.2, 100.5, 5000.0, &fills, 3.5, bench).expect("ok");
        let ks = k::tca_shortfall(&k::TcaOrder {
            buy,
            decision_price: 100.0,
            arrival_price: 100.2,
            end_price: 100.5,
            order_quantity: 5000.0,
            fills: fq.iter().map(|&(q, pr)| (f64::from(q), pr)).collect(),
            fees: 3.5,
            benchmark_vwap: bench,
        }).expect("ok");
        prop_assert_eq!(
            bits(&[s.delay(), s.execution(), s.opportunity(), s.total(), s.total_bps()]),
            bits(&[ks.delay, ks.execution, ks.opportunity, ks.total, ks.total_bps])
        );
        prop_assert_eq!(s.vwap_slippage().map(f64::to_bits), ks.vwap_slippage.map(f64::to_bits));

        let q = as_quotes(100.0, inv, g, sigma, tl, kk).expect("ok");
        let kq = k::as_quotes(100.0, inv, g, sigma, tl, kk).expect("ok");
        prop_assert_eq!(
            bits(&[q.reservation(), q.spread(), q.bid(), q.ask()]),
            bits(&[kq.reservation, kq.spread, kq.bid, kq.ask])
        );
    }
}
