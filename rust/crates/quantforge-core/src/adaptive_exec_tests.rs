//! Acceptance tests of `adaptive-algos.md` (1 to 4) and `tca-pretrade.md` (1, 2), seed 20261118.
//! The goldens (acceptance 5 and 3) run in the CLI golden replay.
use super::*;
use crate::execution::{TcaOrder, tca_shortfall};
use crate::json::Json;
use crate::lit_matching;
use crate::rng::Xoshiro;

const SEED: u64 = 20_261_118;

struct U(Xoshiro);

impl U {
    fn new(stream: u32) -> U {
        U(Xoshiro::seeded(SEED, stream))
    }
    fn u(&mut self, lo: f64, hi: f64) -> f64 {
        lo + (hi - lo) * self.0.next_uniform()
    }
    /// An integer in `[lo, hi]`.
    #[allow(clippy::cast_possible_truncation, clippy::cast_precision_loss)]
    fn i(&mut self, lo: i64, hi: i64) -> i64 {
        (lo + (self.0.next_uniform() * (hi - lo + 1) as f64) as i64).min(hi)
    }
    fn buy(&mut self) -> bool {
        self.0.next_uniform() < 0.5
    }
}

fn rel(a: f64, b: f64) -> bool {
    (a - b).abs() <= 1e-12 * a.abs().max(b.abs()).max(1.0)
}

fn ints(v: &[Amount]) -> Vec<i64> {
    v.iter()
        .map(|a| match a {
            Amount::Units(n) => *n,
            Amount::Real(_) => panic!("expected units"),
        })
        .collect()
}

fn sum(v: &[Amount]) -> f64 {
    v.iter().map(|a| a.value()).sum()
}

fn code<T: std::fmt::Debug>(r: Result<T>) -> &'static str {
    r.unwrap_err().code
}

#[test]
fn spec_examples_and_hr_67() {
    let ln2 = std::f64::consts::LN_2; // the spec writes 0.69314718055994531
    let a = arrival(2100.0, 3, ln2, false).unwrap();
    for (got, want) in values(&a).iter().zip([1100.0, 600.0, 400.0]) {
        assert!(rel(*got, want));
    }
    assert_eq!(ints(&arrival(1001.0, 2, ln2, true).unwrap()), [601, 400]);
    // HR-67: kappa = 0 in UNITS equals TWAP, not HR-59's [333, 334, 333]
    assert_eq!(
        ints(&arrival(1000.0, 3, 0.0, true).unwrap()),
        [334, 333, 333]
    );
    assert_eq!(code(arrival(1000.0, 4, -0.1, false)), "E_DOMAIN");
    assert_eq!(code(arrival(1000.0, 0, 0.5, false)), "E_INPUT");
    // no overflow at a large urgency
    let big = arrival(1000.0, 4, 400.0, false).unwrap();
    assert!(values(&big).iter().all(|v| v.is_finite()));
    assert!(rel(sum(&big), 1000.0));
}

#[test]
fn close_rows_and_errors() {
    let (auc, s) = close(10_002.0, 50_000.0, 0.1, &[1.0, 1.0, 1.0], true).unwrap();
    assert_eq!(
        (auc, ints(&s)),
        (Amount::Units(5000), vec![1668, 1667, 1667])
    );
    let (auc, s) = close(3000.0, 50_000.0, 0.1, &[0.0, 0.0], false).unwrap();
    assert_eq!(auc, Amount::Real(3000.0));
    assert_eq!(values(&s), [0.0, 0.0]);
    assert_eq!(code(close(1000.0, 5e4, 1.5, &[1.0], false)), "E_DOMAIN");
    assert_eq!(code(close(1e4, 5e4, 0.1, &[0.0, 0.0], false)), "E_DOMAIN");
    assert_eq!(code(close(1e4, 5e4, 0.1, &[], false)), "E_INPUT");
    assert_eq!(code(close(1e4, -1.0, 0.1, &[1.0], false)), "E_DOMAIN");
    // HR-66: structural E_INPUT (empty profile) before E_DOMAIN (p_c)
    assert_eq!(code(close(1e4, 5e4, 2.0, &[], false)), "E_INPUT");
}

#[test]
fn seek_pair_basket_errors() {
    let b = vec![vec![[100.0, 300.0]]];
    assert_eq!(code(liquidity_seek(true, 1e3, 101.0, 0.0, &b)), "E_DOMAIN");
    assert_eq!(code(liquidity_seek(true, 1e3, 0.0, 1.0, &b)), "E_DOMAIN");
    assert_eq!(code(liquidity_seek(true, 1e3, 101.0, 1.0, &[])), "E_INPUT");
    let bad = vec![vec![[100.5, 300.0], [100.0, 300.0]]];
    assert_eq!(code(liquidity_seek(true, 1e3, 101.0, 0.0, &bad)), "E_INPUT");
    let neg = vec![vec![[-1.0, 300.0]]];
    assert_eq!(
        code(liquidity_seek(true, 1e3, 101.0, 1.0, &neg)),
        "E_DOMAIN"
    );
    let zero = vec![vec![[1.0, 0.0]]];
    assert_eq!(
        code(liquidity_seek(true, 1e3, 101.0, 1.0, &zero)),
        "E_INPUT"
    );
    let leg = |buy, quantity, price| Leg {
        buy,
        quantity,
        price,
    };
    let (a, b) = (leg(true, 1000.0, 50.0), leg(true, 0.0, 25.0));
    assert_eq!(code(pair(a, b, false, None, 2, false)), "E_INPUT");
    let b = leg(false, 0.0, 25.0);
    assert_eq!(code(pair(a, b, true, Some(0.0), 2, false)), "E_DOMAIN");
    assert_eq!(code(pair(a, b, true, None, 2, false)), "E_INPUT");
    assert_eq!(
        code(pair(a, leg(false, 0.0, 0.0), false, None, 2, false)),
        "E_DOMAIN"
    );
    assert_eq!(code(basket(&[], 2, false)), "E_INPUT");
    assert_eq!(code(basket(&[leg(true, 1.0, 0.0)], 2, false)), "E_DOMAIN");
    let r = basket(&[leg(true, 3.0, 10.0), leg(false, 1.0, 30.0)], 2, true).unwrap();
    assert_eq!(r.cash_imbalance, [-10.0, 0.0]);
}

#[test]
fn pretrade_errors() {
    let k = IstarParams {
        a1: 700.0,
        a2: 1.0,
        a3: 1.0,
        a4: 0.5,
        b1: 1.0,
    };
    let ok = pretrade(1e5, 1e6, 0.02, 0.04, 0.0, k, None).unwrap();
    assert!(rel(ok.timing_risk_bps, 182.574_185_835_055_37));
    assert!(ok.expected_cost.is_none());
    assert_eq!(
        code(pretrade(1e5, 1e6, 0.02, 1.0, 0.0, k, None)),
        "E_DOMAIN"
    );
    assert_eq!(code(pretrade(0.0, 1e6, 0.02, 0.5, 0.0, k, None)), "E_INPUT");
    let b = IstarParams { b1: 1.2, ..k };
    assert_eq!(
        code(pretrade(1e5, 1e6, 0.02, 0.5, 0.0, b, None)),
        "E_DOMAIN"
    );
    let z = IstarParams { a3: 0.0, ..k };
    assert_eq!(code(pretrade(1e5, 1e6, 0.0, 0.5, 0.0, z, None)), "E_DOMAIN");
    assert_eq!(
        code(pretrade(1e5, 1e6, 0.02, 0.5, 0.0, k, Some(0.0))),
        "E_DOMAIN"
    );
}

/// Acceptance 1 and 2 (adaptive-algos.md): schedule identities on 1,000 random inputs per
/// operation; arrival kappa = 0 is TWAP and kappa > 0 is strictly decreasing.
#[test]
fn schedule_identities() {
    let mut r = U::new(0);
    for _ in 0..1000 {
        let units = r.buy();
        let x = if units {
            r.i(1, 1_000_000) as f64
        } else {
            r.u(0.5, 1e6)
        };
        let n = r.i(1, 60);
        let k = if r.buy() { 0.0 } else { r.u(0.001, 3.0) };
        let a = arrival(x, n, k, units).unwrap();
        if units {
            assert_eq!(ints(&a).iter().sum::<i64>() as f64, x);
        } else {
            assert!(rel(sum(&a), x));
        }
        if k == 0.0 {
            assert_eq!(a, schedule_twap(x, n, units).unwrap());
        } else if !units {
            let v = values(&a);
            assert!(v.windows(2).all(|w| w[0] > w[1]), "{v:?}");
        } else {
            let cont = values(&arrival(x, n, k, false).unwrap());
            assert!(
                values(&a)
                    .iter()
                    .zip(&cont)
                    .all(|(u, c)| (u - c).abs() < 1.0)
            );
        }

        let m = usize::try_from(r.i(1, 12)).unwrap();
        let w: Vec<f64> = (0..m).map(|_| r.u(0.0, 5.0)).collect();
        let (auc, s) = close(x, r.u(0.0, 2e6), r.u(0.0, 1.0), &w, units).unwrap();
        if units {
            assert_eq!(ints(&s).iter().sum::<i64>() + ints(&[auc])[0], x as i64);
        } else {
            assert!(rel(auc.value() + sum(&s), x));
        }

        let leg_a = Leg {
            buy: r.buy(),
            quantity: x,
            price: r.u(1.0, 1000.0),
        };
        let leg_b = Leg {
            buy: !leg_a.buy,
            quantity: 0.0,
            price: r.u(1.0, 1000.0),
        };
        let p = pair(leg_a, leg_b, false, None, n, units).unwrap();
        if units {
            assert_eq!(ints(&p.slices_a).iter().sum::<i64>() as f64, x);
            assert_eq!(
                ints(&p.slices_b).iter().sum::<i64>(),
                ints(&[p.quantity_b])[0]
            );
        } else {
            assert!(rel(sum(&p.slices_a), x));
            assert!(rel(sum(&p.slices_b), p.quantity_b.value()));
        }

        let legs: Vec<Leg> = (0..r.i(1, 6))
            .map(|_| Leg {
                buy: r.buy(),
                quantity: if units {
                    r.i(1, 100_000) as f64
                } else {
                    r.u(0.5, 1e5)
                },
                price: r.u(1.0, 1000.0),
            })
            .collect();
        let b = basket(&legs, n, units).unwrap();
        for (l, s) in legs.iter().zip(&b.slices) {
            if units {
                assert_eq!(ints(s).iter().sum::<i64>() as f64, l.quantity);
            } else {
                assert!(rel(sum(s), l.quantity));
            }
        }
        if !units {
            let last = *b.cash_imbalance.last().unwrap();
            for (j, c) in b.cash_imbalance.iter().enumerate() {
                let want = (j + 1) as f64 / n as f64 * last;
                assert!((c - want).abs() <= 1e-9 * b.gross_notional);
            }
        }

        let books = vec![vec![[r.u(1.0, 100.0), r.u(1.0, 1e5)]]; 3];
        let s = liquidity_seek(true, x, 200.0, r.u(0.01, 1.0), &books).unwrap();
        assert!(rel(s.filled + s.residual, x));
    }
}

/// Acceptance 3 (adaptive-algos.md): pair cash-imbalance bounds and the HEDGED quantity.
#[test]
fn pair_bounds() {
    let mut r = U::new(1);
    for _ in 0..1000 {
        let n = r.i(1, 40);
        let (pa, pb) = (r.u(1.0, 1000.0), r.u(1.0, 1000.0));
        let buy = r.buy();
        let a = |q| Leg {
            buy,
            quantity: q,
            price: pa,
        };
        let b = Leg {
            buy: !buy,
            quantity: 0.0,
            price: pb,
        };
        let xc = r.u(1.0, 1e6);
        let c = pair(a(xc), b, false, None, n, false).unwrap();
        let scale = xc * pa;
        assert!(c.cash_imbalance.iter().all(|v| v.abs() <= 1e-12 * scale));
        let xu = r.i(1, 1_000_000) as f64;
        let u = pair(a(xu), b, false, None, n, true).unwrap();
        assert!(
            u.cash_imbalance
                .iter()
                .all(|v| v.abs() <= pb / 2.0 + 1e-9 * xu * pa)
        );
        assert_eq!(u.quantity_b, Amount::Units(half_up(xu * pa / pb)));
        let h = r.u(0.01, 5.0);
        let hd = pair(a(xc), Leg { buy: r.buy(), ..b }, true, Some(h), n, false).unwrap();
        assert!(rel(hd.quantity_b.value(), h * xc));
    }
}

/// Rests the planted book (ticks of 0.01, whole sizes) on the lit engine and sends the child as
/// an IOC at L; returns the recovered quantity and notional and checks no fill lies outside L.
fn lit_fills(buy: bool, book: &[(i64, i64)], limit: i64, child: f64) -> (f64, f64) {
    let px = |t: i64| format!("{}.{:02}", t / 100, t % 100);
    let ev = |id: String, trader: &str, side: &str, typ: &str, price: String, qty: String| {
        Json::Obj(
            [
                ("op", "NEW".to_string()),
                ("id", id),
                ("trader", trader.to_string()),
                ("side", side.to_string()),
                ("type", typ.to_string()),
                ("price", price),
                ("qty", qty),
            ]
            .into_iter()
            .map(|(k, v)| (k.to_string(), Json::Str(v)))
            .collect(),
        )
    };
    let opp = if buy { "SELL" } else { "BUY" };
    let mut events: Vec<Json> = book
        .iter()
        .enumerate()
        .map(|(k, &(t, q))| ev(format!("M{k}"), "MM", opp, "LIMIT", px(t), q.to_string()))
        .collect();
    if child > 0.0 {
        let side = if buy { "BUY" } else { "SELL" };
        events.push(ev(
            "C".into(),
            "US",
            side,
            "IOC",
            px(limit),
            format!("{child}"),
        ));
    }
    let fees = Json::Obj(vec![
        ("taker_fee".into(), Json::Str("0".into())),
        ("maker_rebate".into(), Json::Str("0".into())),
    ]);
    let out = lit_matching::run("0.01", "0.125", &events, &fees).unwrap();
    let lim = limit as f64 / 100.0;
    let (mut q, mut notional) = (0.0, 0.0);
    for f in out.get("fills").and_then(Json::as_array).unwrap() {
        if f.get("taker_id").and_then(Json::as_str) != Some("C") {
            continue;
        }
        let num = |k| {
            f.get(k)
                .and_then(Json::as_str)
                .unwrap()
                .parse::<f64>()
                .unwrap()
        };
        let (fq, fp) = (num("qty"), num("price"));
        assert!(if buy { fp <= lim } else { fp >= lim }, "fill outside L");
        q += fq;
        notional += fq * fp;
    }
    (q, notional)
}

/// Acceptance 4 (adaptive-algos.md): 200 planted books (seed 20261118, 5 to 20 levels, tick
/// 0.01) with known depth inside L, run through the lit matching engine.
#[test]
fn liquidity_seek_simulated_book() {
    let mut r = U::new(2);
    for _ in 0..200 {
        let buy = r.buy();
        let kb = usize::try_from(r.i(1, 5)).unwrap();
        let x = r.i(1, 20_000) as f64;
        let alpha = r.i(1, 8) as f64 / 8.0; // dyadic: alpha A and the remainders are exact
        let limit = r.i(9_000, 11_000);
        let dir = if buy { 1 } else { -1 };
        let mut planted: Vec<Vec<(i64, i64)>> = Vec::new();
        for _ in 0..kb {
            let nl = r.i(5, 20);
            let mut tick = limit - dir * r.i(0, 40);
            let mut lv = Vec::new();
            for _ in 0..nl {
                lv.push((tick, r.i(1, 2_000)));
                tick += dir * r.i(1, 5);
            }
            planted.push(lv);
        }
        let books: Vec<Vec<[f64; 2]>> = planted
            .iter()
            .map(|b| {
                b.iter()
                    .map(|&(t, q)| [t as f64 / 100.0, q as f64])
                    .collect()
            })
            .collect();
        let lim = limit as f64 / 100.0;
        let res = liquidity_seek(buy, x, lim, alpha, &books).unwrap();
        let mut remaining = x;
        for (b, book) in planted.iter().enumerate() {
            let known: i64 = book
                .iter()
                .filter(|&&(t, _)| if buy { t <= limit } else { t >= limit })
                .map(|&(_, q)| q)
                .sum();
            let want = remaining.min(alpha * known as f64);
            let c = res.slices[b];
            assert!(rel(c, want));
            let (q, notional) = lit_fills(buy, book, limit, c);
            assert!(rel(q, want)); // recovered fills equal min(R, alpha A_i)
            match res.avg_prices[b] {
                Some(avg) => {
                    assert!(c > 0.0);
                    assert!(rel(avg, notional / q));
                    let best = books[b][0][0];
                    let (lo, hi) = if buy { (best, lim) } else { (lim, best) };
                    assert!(lo - 1e-12 <= avg && avg <= hi + 1e-12);
                }
                None => assert_eq!(c, 0.0),
            }
            remaining -= c;
        }
        assert!(rel(res.filled + res.residual, x));
    }
}

/// Acceptance 1 (tca-pretrade.md): attribution identity and agreement with `exec.tca.shortfall`
/// on 1,000 random inputs (1 to 50 fills, prices in [1, 1000]).
#[test]
fn attribution_identity_and_shortfall() {
    let mut r = U::new(3);
    for _ in 0..1000 {
        let buy = r.buy();
        let s = if buy { 1.0 } else { -1.0 };
        let nf = r.i(1, 50);
        let fills: Vec<Fill> = (0..nf)
            .map(|_| Fill {
                quantity: r.u(1.0, 1000.0),
                price: r.u(1.0, 1000.0),
                mid: r.u(1.0, 1000.0),
            })
            .collect();
        let q: f64 = fills.iter().map(|f| f.quantity).sum();
        let x = q * r.u(1.0, 2.0);
        let (pd, m0, pc, fees) = (r.u(1.0, 1e3), r.u(1.0, 1e3), r.u(1.0, 1e3), r.u(0.0, 50.0));
        let a = attribution(buy, pd, m0, pc, x, &fills, fees).unwrap();
        let bound = 1e-10 * a.total.abs().max(1.0);
        let paper: f64 = s * fills
            .iter()
            .map(|f| f.quantity * (f.price - pd))
            .sum::<f64>();
        assert!((a.delay + a.impact + a.spread - paper).abs() <= bound);
        let sf = tca_shortfall(&TcaOrder {
            buy,
            decision_price: pd,
            arrival_price: m0,
            end_price: pc,
            order_quantity: x,
            fills: fills.iter().map(|f| (f.quantity, f.price)).collect(),
            fees,
            benchmark_vwap: None,
        })
        .unwrap();
        assert!((sf.total - a.total).abs() <= bound);
    }
    let none = attribution(true, 100.0, 100.5, 101.0, 100.0, &[], 0.0).unwrap();
    assert_eq!(
        (none.delay, none.opportunity, none.total_bps),
        (0.0, 100.0, 100.0)
    );
    let f = |quantity, mid| Fill {
        quantity,
        price: 100.2,
        mid,
    };
    assert_eq!(
        code(attribution(
            true,
            100.0,
            100.1,
            101.0,
            1e3,
            &[f(1200.0, 100.15)],
            5.0
        )),
        "E_INPUT"
    );
    assert_eq!(
        code(attribution(
            true,
            100.0,
            100.1,
            101.0,
            1e3,
            &[f(600.0, 0.0)],
            5.0
        )),
        "E_DOMAIN"
    );
    assert_eq!(
        code(attribution(
            true,
            100.0,
            100.1,
            101.0,
            1e3,
            &[f(0.0, 1.0)],
            5.0
        )),
        "E_INPUT"
    );
    assert_eq!(
        code(attribution(true, 100.0, 100.1, 101.0, 0.0, &[], 5.0)),
        "E_INPUT"
    );
}

/// Acceptance 2 (tca-pretrade.md): impact non-decreasing in X (a2 >= 0) and in p (a4 >= 0);
/// timing risk non-increasing in p.
#[test]
fn pretrade_monotonicity() {
    let mut r = U::new(4);
    for _ in 0..1000 {
        let k = IstarParams {
            a1: r.u(1.0, 1000.0),
            a2: r.u(0.0, 1.5),
            a3: r.u(0.1, 1.5),
            a4: r.u(0.0, 1.5),
            b1: r.u(0.0, 1.0),
        };
        let (adv, sig, hs) = (r.u(1e4, 1e8), r.u(0.001, 0.1), r.u(0.0, 10.0));
        let (x1, x2) = (r.u(1.0, 1e6), r.u(1.0, 1e6));
        let (x1, x2) = (x1.min(x2), x1.max(x2));
        let (p1, p2) = (r.u(0.001, 0.999), r.u(0.001, 0.999));
        let (p1, p2) = (p1.min(p2), p1.max(p2));
        let at = |x, p| pretrade(x, adv, sig, p, hs, k, Some(10.0)).unwrap();
        let tol = |v: f64| 1e-12 * v.abs().max(1e-300);
        assert!(at(x1, p1).impact_bps <= at(x2, p1).impact_bps + tol(at(x2, p1).impact_bps));
        assert!(at(x1, p1).impact_bps <= at(x1, p2).impact_bps + tol(at(x1, p2).impact_bps));
        assert!(
            at(x1, p1).timing_risk_bps + tol(at(x1, p1).timing_risk_bps)
                >= at(x1, p2).timing_risk_bps
        );
    }
}

/// A bad leg quantity names `quantity` as its field in all four builds (`adaptive-algos.md`).
#[test]
fn leg_quantity_error_names_quantity() {
    let a = Leg {
        buy: true,
        quantity: 0.0,
        price: 50.0,
    };
    let b = Leg {
        buy: false,
        quantity: 0.0,
        price: 25.0,
    };
    let e = pair(a, b, false, None, 2, false).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_INPUT", Some("quantity")));
    let legs = [Leg {
        buy: true,
        quantity: 2.5,
        price: 10.0,
    }];
    let e = basket(&legs, 2, true).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_INPUT", Some("quantity")));
}
