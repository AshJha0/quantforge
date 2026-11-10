//! G6 property suites: put-call parity, discount-factor monotonicity and the implied-vol round
//! trip, over generated inputs (proptest, a dev-dependency only).
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use proptest::prelude::*;
use quantforge_core::black::{Model, Option_};
use quantforge_core::compounding::{Compounding, discount_factor};
use quantforge_core::curve::{Curve, Interpolation};
use quantforge_core::dates::Date;

fn option(model: Model, call: bool, strike: f64, t: f64) -> Option_ {
    Option_ {
        model,
        call,
        strike,
        t,
    }
}

fn models() -> impl Strategy<Value = Model> {
    prop_oneof![
        (1.0..500.0_f64, -0.05..0.15_f64, 0.0..0.10_f64).prop_map(|(spot, rate, dividend)| {
            Model::BlackScholes {
                spot,
                rate,
                dividend,
            }
        }),
        (1.0..500.0_f64, 0.5..1.0_f64).prop_map(|(forward, discount)| Model::Black76 {
            forward,
            discount,
            shift: 0.0,
        }),
        (-50.0..500.0_f64, 0.5..1.0_f64)
            .prop_map(|(forward, discount)| Model::Bachelier { forward, discount }),
    ]
}

/// Forward and discount factor the model implies at expiry `t`.
fn forward_and_df(m: Model, t: f64) -> (f64, f64) {
    match m {
        Model::BlackScholes {
            spot,
            rate,
            dividend,
        } => (spot * ((rate - dividend) * t).exp(), (-rate * t).exp()),
        Model::Black76 {
            forward, discount, ..
        }
        | Model::Bachelier { forward, discount } => (forward, discount),
    }
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(512))]

    /// C - P = D (F - K) for every model, strike, vol and expiry.
    #[test]
    fn put_call_parity(m in models(), m_k in 0.5..1.5_f64, v in 0.01..1.0_f64, t in 0.01..10.0_f64) {
        let (f, d) = forward_and_df(m, t);
        let k = if matches!(m, Model::Bachelier { .. }) { f + (m_k - 1.0) * 100.0 } else { f * m_k };
        let v = if matches!(m, Model::Bachelier { .. }) { v * 100.0 } else { v };
        let c = option(m, true, k, t).price(v).unwrap();
        let p = option(m, false, k, t).price(v).unwrap();
        let scale = f.abs().max(k.abs()).max(1.0);
        prop_assert!((c - p - d * (f - k)).abs() <= 1e-10 * scale, "c={c} p={p} f={f} k={k} d={d}");
    }

    /// Lognormal implied vol recovers the vol that made the price, where vega is not tiny.
    #[test]
    fn implied_vol_round_trip(spot in 10.0..200.0_f64, m_k in 0.7..1.3_f64, v in 0.05..1.0_f64,
                              t in 0.1..5.0_f64, call: bool) {
        let m = Model::BlackScholes { spot, rate: 0.03, dividend: 0.01 };
        let o = option(m, call, spot * m_k, t);
        let price = o.price(v).unwrap();
        prop_assume!(bs_vega(spot, spot * m_k, v, t) > 1e-4 * spot);
        let back = o.implied(price).unwrap();
        prop_assert!((back - v).abs() <= 1e-8, "v={v} back={back}");
    }

    /// With non-negative rates the discount factor never rises with time, in every compounding.
    #[test]
    fn df_monotone_in_time(r in 0.0..0.25_f64, t1 in 0.0..30.0_f64, dt in 0.0..30.0_f64, n in 1..13_i32) {
        for c in [Compounding::Simple, Compounding::Continuous, Compounding::Periodic(f64::from(n))] {
            let a = discount_factor(r, t1, c).unwrap();
            let b = discount_factor(r, t1 + dt, c).unwrap();
            prop_assert!(b <= a && a <= 1.0, "{c:?} r={r} t1={t1} dt={dt} a={a} b={b}");
        }
    }

    /// A curve built from falling discount factors falls between and beyond its pillars.
    #[test]
    fn curve_df_monotone(steps in prop::collection::vec((1..2000_i64, 0.0..0.002_f64), 1..12),
                         linear_zero: bool, probes in prop::collection::vec(0..20_000_i64, 2..40)) {
        let as_of = Date::new(2026, 11, 9);
        let (mut dates, mut logs, mut day, mut log) = (Vec::new(), Vec::new(), 0, 0.0);
        for (gap, rate) in steps {
            day += gap;
            log -= rate * gap as f64 / 365.0 * 10.0;
            dates.push(as_of.add_days(day));
            logs.push(log);
        }
        let i = if linear_zero { Interpolation::LinearZero } else { Interpolation::LogLinearDf };
        // LinearZero keeps the discount factor monotone only when zero rates do not fall fast;
        // the log-linear rule is monotone for any falling pillars.
        prop_assume!(!linear_zero || zero_rates_rise(as_of, &dates, &logs));
        let curve = Curve::from_logs(as_of, i, &dates, &logs);
        let mut probes = probes;
        probes.sort_unstable();
        let mut last = 1.0;
        for p in probes {
            let df = curve.discount(as_of.add_days(p)).unwrap();
            prop_assert!(df <= last + 1e-15, "day {p}: {df} > {last}");
            last = df;
        }
    }
}

fn zero_rates_rise(as_of: Date, dates: &[Date], logs: &[f64]) -> bool {
    let z: Vec<f64> = dates
        .iter()
        .zip(logs)
        .map(|(d, l)| -l / ((d.serial() - as_of.serial()) as f64))
        .collect();
    z.windows(2).all(|w| w[1] >= w[0])
}

/// Black-Scholes vega with r = 0.03 and q = 0.01, written out for the test.
fn bs_vega(s: f64, k: f64, v: f64, t: f64) -> f64 {
    let d1 = ((s / k).ln() + (0.03 - 0.01 + 0.5 * v * v) * t) / (v * t.sqrt());
    s * (-0.01 * t).exp() * (-0.5 * d1 * d1).exp() / (2.0 * std::f64::consts::PI).sqrt() * t.sqrt()
}
