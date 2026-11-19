use super::*;
use proptest::prelude::*;

const DAY: i64 = 86_400;
const T0: i64 = 1_767_225_600; // 2026-01-01T00:00:00Z

fn code<T: std::fmt::Debug>(r: Result<T>) -> &'static str {
    r.unwrap_err().code
}

fn rec(
    seq: i64,
    series: &str,
    vf: i64,
    vt: Option<i64>,
    kt: i64,
    value: i64,
    del: bool,
) -> BiRecord {
    BiRecord {
        sequence: seq,
        series_id: series.to_string(),
        valid_from: vf,
        valid_to: vt,
        knowledge_time: kt,
        value: Json::Int(value),
        deleted: del,
    }
}

/// The `bt_k` golden log: two open versions, a back-dated correction of February, a withdrawal.
fn golden_log() -> Vec<BiRecord> {
    vec![
        rec(1, "A", T0, None, T0 + DAY, 100, false),
        rec(2, "A", T0 + 59 * DAY, None, T0 + 60 * DAY, 110, false),
        rec(
            3,
            "A",
            T0 + 31 * DAY,
            Some(T0 + 59 * DAY),
            T0 + 90 * DAY,
            105,
            false,
        ),
        rec(4, "A", T0 + 59 * DAY, None, T0 + 91 * DAY, 0, true),
    ]
}

#[test]
fn status_names() {
    assert_eq!(BiStatus::Found.name(), "FOUND");
    assert_eq!(BiStatus::Withdrawn.name(), "WITHDRAWN");
    assert_eq!(BiStatus::None.name(), "NONE");
}

#[test]
fn bitemporal_answers() {
    let log = golden_log();
    let q = |k: i64, v: i64| {
        let (s, r) = bitemporal_query(&log, "A", k, v).unwrap();
        (s, r.map(|r| r.sequence))
    };
    assert_eq!(q(T0 + 73 * DAY, T0 + 45 * DAY), (BiStatus::Found, Some(1)));
    assert_eq!(q(T0 + 90 * DAY, T0 + 45 * DAY), (BiStatus::Found, Some(3)));
    assert_eq!(q(T0 + 90 * DAY, T0 + 59 * DAY), (BiStatus::Found, Some(2)));
    assert_eq!(
        q(T0 + 90 * DAY, T0 + 59 * DAY - 1),
        (BiStatus::Found, Some(3))
    );
    assert_eq!(q(T0 + 94 * DAY, T0 + 68 * DAY), (BiStatus::Withdrawn, None));
    assert_eq!(q(T0 + 94 * DAY, T0 + 14 * DAY), (BiStatus::Found, Some(1)));
    assert_eq!(q(T0 + DAY / 2, T0 + 14 * DAY), (BiStatus::None, None));
    assert_eq!(q(T0 + 94 * DAY, T0 - 1), (BiStatus::None, None));
    let (s, _) = bitemporal_query(&log, "B", T0 + 94 * DAY, T0 + 14 * DAY).unwrap();
    assert_eq!(s, BiStatus::None);
    assert_eq!(
        bitemporal_query(&[], "A", T0, T0).unwrap(),
        (BiStatus::None, None)
    );
}

#[test]
fn bitemporal_log_checks_in_order() {
    let mut log = golden_log();
    log[1].sequence = 1;
    log[2].knowledge_time = T0; // also bad, but sequence is checked first
    let e = bitemporal_query(&log, "A", T0, T0).unwrap_err();
    assert_eq!(e.code, "E_INPUT");
    assert!(e.message.contains("sequence"));
    let mut log = golden_log();
    log[2].knowledge_time = T0;
    log[0].valid_to = Some(T0);
    let e = check_log(&log).unwrap_err();
    assert!(e.message.contains("knowledge_time"));
    let mut log = golden_log();
    log[0].valid_to = Some(T0);
    let e = check_log(&log).unwrap_err();
    assert_eq!(e.field.as_deref(), Some("records"));
    assert!(e.message.contains("valid_to"));
    log[0].valid_to = Some(T0 + 1);
    assert!(check_log(&log).is_ok());
}

#[test]
fn bitemporal_limit_then_finite_then_log() {
    let mut log = golden_log();
    log[0].value = Json::Num(f64::NAN);
    assert_eq!(code(bitemporal_query(&log, "A", T0, T0)), "E_DOMAIN");
    // KR-230 (HR-122): E_LIMIT outranks the finite rule, which outranks a structural E_INPUT.
    assert_eq!(code(query_within(&log, "A", T0, T0, 1)), "E_LIMIT");
    log[1].sequence = 0;
    assert_eq!(code(query_within(&log, "A", T0, T0, 4)), "E_DOMAIN");
    log[0].value = Json::Int(1);
    assert_eq!(code(query_within(&log, "A", T0, T0, 4)), "E_INPUT");
    // KR-231: the generic array cap, before log check 2 (A2)
    assert_eq!(MAX_RECORDS, 100_000);
    let same = vec![rec(1, "A", T0, None, T0, 0, false); MAX_RECORDS + 1];
    let e = bitemporal_query(&same, "A", T0, T0).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_LIMIT", Some("records")));
    let log = golden_log();
    let e = query_within(&log, "A", T0, T0, 3).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_LIMIT", Some("records")));
    assert!(query_within(&log, "A", T0, T0, 4).is_ok());
}

#[test]
fn par_annual_golden_and_errors() {
    let df = par_annual(&[0.02, 0.025, 0.03]).unwrap();
    assert_eq!(df, PD);
    assert_eq!(code(par_annual(&[])), "E_INPUT");
    assert_eq!(code(par_annual(&[0.02, f64::NAN])), "E_DOMAIN");
    let e = par_annual(&[0.02, -1.0]).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_DOMAIN", Some("quotes")));
    assert!(par_annual(&[0.01; MAX_QUOTES]).is_ok());
    assert_eq!(code(par_annual(&[0.01; MAX_QUOTES + 1])), "E_LIMIT");
    // KR-230: the size limit before the domain check and the finite rule
    let mut q = vec![0.01; MAX_QUOTES + 1];
    q[5] = -2.0;
    assert_eq!(code(par_annual(&q)), "E_LIMIT");
    q[6] = f64::NAN;
    assert_eq!(code(par_annual(&q)), "E_LIMIT");
}

const PQ: [f64; 3] = [0.02, 0.025, 0.03];
const PD: [f64; 3] = [0.9803921568627451, 0.9516977522716404, 0.9145993230349208];

#[test]
fn incremental_golden() {
    let u = incremental_update(&PQ, &PD, &[0.02, 0.026, 0.03]).unwrap();
    assert_eq!(u.first_changed_index, Some(1));
    assert_eq!(u.recomputed, 2);
    assert_eq!(
        u.discount_factors,
        [0.9803921568627451, 0.9498146237052325, 0.9146541714397676]
    );
    let u = incremental_update(&PQ, &PD, &[0.02, 0.025, 0.031]).unwrap();
    assert_eq!((u.first_changed_index, u.recomputed), (Some(2), 1));
    assert_eq!(u.discount_factors[2], 0.9118382277563861);
    let u = incremental_update(&PQ, &PD, &PQ).unwrap();
    assert_eq!(
        u,
        Update {
            discount_factors: PD.to_vec(),
            first_changed_index: None,
            recomputed: 0
        }
    );
}

#[test]
fn incremental_errors_in_order() {
    let new = [0.02, 0.026, 0.03];
    assert_eq!(code(incremental_update(&[], &[], &[])), "E_INPUT");
    assert_eq!(code(incremental_update(&PQ, &PD[..2], &new)), "E_INPUT");
    assert_eq!(code(incremental_update(&PQ, &PD, &new[..2])), "E_INPUT");
    // KR-230: the finite rule before the structural E_INPUT
    assert_eq!(code(incremental_update(&PQ, &PD, &[f64::NAN])), "E_DOMAIN");
    let nan = [0.02, f64::NAN, 0.03];
    let e = incremental_update(&nan, &PD, &new).unwrap_err();
    assert_eq!(
        (e.code, e.field.as_deref()),
        ("E_DOMAIN", Some("previous_quotes"))
    );
    let e = incremental_update(&PQ, &nan, &new).unwrap_err();
    assert_eq!(e.field.as_deref(), Some("previous_discount_factors"));
    let e = incremental_update(&PQ, &PD, &[0.02, f64::INFINITY, 0.03]).unwrap_err();
    assert_eq!(
        (e.code, e.field.as_deref()),
        ("E_DOMAIN", Some("new_quotes"))
    );
    let e = incremental_update(&[0.02, -1.5, 0.03], &PD, &new).unwrap_err();
    assert_eq!(e.field.as_deref(), Some("previous_quotes"));
    let e = incremental_update(&PQ, &PD, &[0.02, -1.0, 0.03]).unwrap_err();
    assert_eq!(
        (e.code, e.field.as_deref()),
        ("E_DOMAIN", Some("new_quotes"))
    );
    // a stale cache, one ulp off, is a value-dependent E_INPUT
    let stale = [PD[0], PD[1], 0.9145993230349209];
    let e = incremental_update(&PQ, &stale, &new).unwrap_err();
    assert_eq!(
        (e.code, e.field.as_deref()),
        ("E_INPUT", Some("previous_discount_factors"))
    );
    // the domain check comes before the stale-cache check
    assert_eq!(
        code(incremental_update(&PQ, &stale, &[0.02, -3.0, 0.03])),
        "E_DOMAIN"
    );
}

#[test]
fn incremental_sign_of_zero_and_limit() {
    // Quotes 1 and 2 make the second discount factor exactly 0.0 ((1 - 2 * 0.5) / 3): a cache
    // holding -0.0 there is stale, though -0.0 == 0.0.
    let q = [1.0, 2.0];
    let fresh = par_annual(&q).unwrap();
    assert_eq!(fresh[1].to_bits(), 0.0f64.to_bits(), "{fresh:?}");
    let negz = [fresh[0], -0.0];
    assert_eq!(code(incremental_update(&q, &negz, &q)), "E_INPUT");
    assert!(incremental_update(&q, &fresh, &q).is_ok());
    let big = vec![0.01; MAX_QUOTES + 1];
    let df = bootstrap_from(&big, &[]);
    let e = incremental_update(&big, &df, &big).unwrap_err();
    assert_eq!(
        (e.code, e.field.as_deref()),
        ("E_LIMIT", Some("previous_quotes"))
    );
    let e = incremental_update(&PQ, &PD, &big).unwrap_err();
    assert_eq!(
        (e.code, e.field.as_deref()),
        ("E_LIMIT", Some("new_quotes"))
    );
    let e = incremental_update(&PQ, &df, &PQ).unwrap_err();
    assert_eq!(e.field.as_deref(), Some("previous_discount_factors"));
    // KR-230: E_LIMIT before the stale-cache E_INPUT
    let stale = vec![0.5; MAX_QUOTES + 1];
    assert_eq!(code(incremental_update(&big, &stale, &big)), "E_LIMIT");
}

const CH: [f64; 4] = [1.0, -1.0, 1.0, -1.0];

#[test]
fn trigger_golden() {
    let t = trigger_check(&CH, 100.0, 105.0, 1.0, 3.0).unwrap();
    assert!(t.fire);
    assert_eq!(t.sigma, 1.1547005383792515);
    assert_eq!(t.threshold, 3.4641016151377544);
    assert!((t.nominal_rate - 0.002699796063260189).abs() <= 1e-10 * 0.0027);
    // KR-232: 2 t_3.sf(3), the Python reference value (class tail_probability, 1e-11 relative)
    assert!(rel(t.false_alarm_rate, 0.05766888562243732) <= 1e-11);
    assert!(!trigger_check(&CH, 100.0, 102.0, 1.0, 3.0).unwrap().fire);
    let t = trigger_check(&CH, 100.0, 105.0, 4.0, 3.0).unwrap();
    assert!(!t.fire);
    assert_eq!(t.threshold, 6.928203230275509);
    // KR-13: a move equal to the threshold does not fire; just above it does.
    let ch = [0.5, -1.0, 1.5, -0.5, 0.0, 1.0, -1.5, 0.0];
    let t = trigger_check(&ch, 0.0, 2.5, 1.0, 2.5).unwrap();
    assert_eq!((t.fire, t.sigma, t.threshold), (false, 1.0, 2.5));
    assert!((t.nominal_rate - 0.01241933065155227).abs() <= 1e-10 * 0.0125);
    assert!(rel(t.false_alarm_rate, 0.04099221858575289) <= 1e-11);
    assert!(trigger_check(&ch, 0.0, -2.5000001, 1.0, 2.5).unwrap().fire);
    // a small k takes the erf branch of the normal tail
    let t = trigger_check(&CH, 0.0, 0.0, 1.0, 0.5).unwrap();
    assert!((t.nominal_rate - 0.6170750774519739).abs() <= 1e-13);
    assert!(rel(t.false_alarm_rate, 0.651447964848151) <= 1e-11);
    // KR-6 states 2 (1 - Phi(k)) = 2 Phi(-k); at k = 30 a bare erfc(k / sqrt 2) is 1.2e-13 off
    // (trig_k-0009, mpmath 50 digits); the same formula in all four builds, within 1e-14.
    let t = trigger_check(&CH, 100.0, 105.0, 1.0, 30.0).unwrap();
    assert_eq!(t.nominal_rate, 2.0 * crate::stats::normal_cdf(-30.0));
    assert!((t.nominal_rate / 9.813427854296374e-198 - 1.0).abs() <= 1e-14);
    assert!(rel(t.false_alarm_rate, 8.13528042716396e-05) <= 1e-11);
}

#[test]
fn trigger_errors_in_order() {
    // KR-230: the finite rule before the structural E_INPUT
    assert_eq!(
        code(trigger_check(&[1.0], 100.0, f64::NAN, 1.0, 3.0)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(trigger_check(&[1.0], 100.0, 105.0, 1.0, 3.0)),
        "E_INPUT"
    );
    let e = trigger_check(&[1.0, f64::NAN], 100.0, 105.0, 1.0, 3.0).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_DOMAIN", Some("changes")));
    assert_eq!(
        code(trigger_check(&CH, 100.0, f64::NAN, 1.0, 3.0)),
        "E_DOMAIN"
    );
    let e = trigger_check(&CH, 100.0, 105.0, 1.0, 0.0).unwrap_err();
    assert_eq!(e.field.as_deref(), Some("k"));
    let e = trigger_check(&CH, 100.0, 105.0, 0.5, 3.0).unwrap_err();
    assert_eq!(
        (e.code, e.field.as_deref()),
        ("E_DOMAIN", Some("days_since"))
    );
    let e = trigger_check(&[1.0, 1.0, 1.0], 100.0, 105.0, 1.0, 3.0).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_DOMAIN", Some("changes")));
    // KR-233 (KA-A5): a constant window whose binary64 sigma is 1.7e-17, not 0
    let e = trigger_check(&[0.1, 0.1, 0.1], 0.0, 0.0, 1.0, 3.0).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_DOMAIN", Some("changes")));
    assert_eq!(
        code(trigger_within(&CH, 100.0, 105.0, 1.0, 3.0, 3)),
        "E_LIMIT"
    );
    // KR-230: E_LIMIT before E_DOMAIN and before the finite rule
    assert_eq!(
        code(trigger_within(&CH, 100.0, 105.0, 1.0, -1.0, 3)),
        "E_LIMIT"
    );
    let big: Vec<f64> = CH.iter().copied().cycle().take(MAX_CHANGES + 2).collect();
    assert_eq!(code(trigger_check(&big, 0.0, 0.0, 1.0, 3.0)), "E_LIMIT");
    let nans = vec![f64::NAN; MAX_CHANGES + 1];
    assert_eq!(code(trigger_check(&nans, 0.0, 0.0, 1.0, 3.0)), "E_LIMIT");
}

fn pos(n: f64, t: f64, y: f64) -> ZeroPosition {
    ZeroPosition {
        notional: n,
        maturity: t,
        yield_: y,
    }
}

fn rel(a: f64, b: f64) -> f64 {
    (a - b).abs() / b.abs()
}

#[test]
fn intraday_golden() {
    let book = [pos(1e6, 5.0, 0.04)];
    for (h, est, bound) in [
        // KR-234 bounds (Lagrange bound plus rounding allowance), the Python reference values
        (0.01, -39913.124212551615, 17.056890689308766),
        (-0.01, 41959.95109524657, 17.931416175710734),
        (0.0025, -10170.171073390557, 0.2665139170617964),
        (0.05, -179097.35223580853, 2132.111336141709),
    ] {
        let r = delta_gamma_bound(&book, h).unwrap();
        assert!(rel(r.estimate_pnl, est) <= 1e-12, "{h}");
        assert!(rel(r.bound, bound) <= 1e-12, "{h}");
        assert!((r.estimate_pnl - zero_revalue(&book, h)).abs() <= r.bound);
    }
    let book = [pos(1e6, 5.0, 0.04), pos(-5e5, 2.0, 0.03)];
    let r = delta_gamma_bound(&book, 0.01).unwrap();
    assert!(rel(r.estimate_pnl, -30589.655330067555) <= 1e-12);
    assert!(rel(r.bound, 17.684733711734584) <= 1e-12);
    let r = delta_gamma_bound(&[pos(1.0, 1.0, 0.0)], 0.0).unwrap();
    assert_eq!((r.estimate_pnl, r.bound), (0.0, 0.0));
}

#[test]
fn intraday_errors_in_order() {
    // KR-230: the finite rule before the structural E_INPUT
    assert_eq!(code(delta_gamma_bound(&[], f64::NAN)), "E_DOMAIN");
    assert_eq!(code(delta_gamma_bound(&[], 0.01)), "E_INPUT");
    let e = delta_gamma_bound(&[pos(1.0, f64::NAN, 0.0)], 0.01).unwrap_err();
    assert_eq!(
        (e.code, e.field.as_deref()),
        ("E_DOMAIN", Some("positions"))
    );
    let e = delta_gamma_bound(&[pos(1.0, 1.0, 0.0)], f64::NEG_INFINITY).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_DOMAIN", Some("shift")));
    let e = delta_gamma_bound(&[pos(1e6, 0.0, 0.04)], 0.01).unwrap_err();
    assert_eq!(
        (e.code, e.field.as_deref()),
        ("E_DOMAIN", Some("positions.maturity"))
    );
    let book = [pos(1.0, 1.0, 0.0), pos(1.0, 2.0, 0.0)];
    assert_eq!(code(intraday_within(&book, 0.01, 1)), "E_LIMIT");
    let bad = [pos(1.0, 1.0, 0.0), pos(1.0, -2.0, 0.0)];
    assert_eq!(code(intraday_within(&bad, 0.01, 1)), "E_LIMIT");
    assert_eq!(code(intraday_within(&bad, 0.01, 2)), "E_DOMAIN");
    let big = vec![pos(1.0, 1.0, 0.0); MAX_POSITIONS + 1];
    assert_eq!(code(delta_gamma_bound(&big, 0.01)), "E_LIMIT");
}

#[test]
fn richardson_cases() {
    let r = richardson_check(&[10.5, 10.125, 10.03125], 2.0, 2.0).unwrap();
    assert_eq!(
        (r.status, r.observed_order, r.extrapolated),
        ("OK", Some(2.0), Some(10.0))
    );
    let r = richardson_check(&[11.0, 10.5, 10.25], 2.0, 2.0).unwrap();
    assert_eq!(
        (r.status, r.observed_order, r.extrapolated),
        ("ORDER_MISMATCH", Some(1.0), None)
    );
    let r = richardson_check(&[11.0, 10.5, 10.25], 2.0, 1.0).unwrap();
    assert_eq!((r.status, r.extrapolated), ("OK", Some(10.0)));
    let r = richardson_check(&[211255.0, 220895.0, 225712.0], 2.0, 1.0).unwrap();
    assert_eq!(r.status, "OK");
    assert!(rel(r.observed_order.unwrap(), 1.0008982225303467) <= 1e-14);
    assert!(rel(r.extrapolated.unwrap(), 230529.0) <= 1e-14);
    for v in [
        [98464.0, 93700.0, 96435.0],
        [1.0, 1.0, 2.0],
        [1.0, 2.0, 2.0],
        [3.0, 2.0, 1.75],
    ] {
        let r = richardson_check(&v, 2.0, 2.0).unwrap();
        let want = if v == [3.0, 2.0, 1.75] {
            "OK"
        } else {
            "NON_MONOTONE"
        };
        assert_eq!(r.status, want, "{v:?}");
    }
    let r = richardson_check(&[1.0, 1.0, 2.0], 2.0, 2.0).unwrap();
    assert_eq!((r.observed_order, r.extrapolated), (None, None));
}

#[test]
fn richardson_errors_in_order() {
    // KR-230: the finite rule before the structural E_INPUT
    assert_eq!(
        code(richardson_check(&[1.0, f64::NAN], 0.5, 2.0)),
        "E_DOMAIN"
    );
    assert_eq!(code(richardson_check(&[1.0], 0.5, 2.0)), "E_INPUT");
    assert_eq!(
        code(richardson_check(&[1.0, 2.0, 3.0, 4.0], 2.0, 2.0)),
        "E_INPUT"
    );
    assert_eq!(
        code(richardson_check(&[1.0, f64::NAN, 3.0], 2.0, 2.0)),
        "E_DOMAIN"
    );
    let e = richardson_check(&[1.0, 2.0, 3.0], 1.0, 2.0).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_DOMAIN", Some("ratio")));
    let e = richardson_check(&[1.0, 2.0, 3.0], 2.0, 0.0).unwrap_err();
    assert_eq!(
        (e.code, e.field.as_deref()),
        ("E_DOMAIN", Some("assumed_order"))
    );
}

/// A seeded 50-position book and 1,000 moves `h ~ U[-0.02, 0.02]` (intraday-risk-bounds.md
/// acceptance): `|estimate - full revaluation| <= bound` on every move.
#[test]
fn intraday_bound_holds_on_a_seeded_book() {
    let mut s: u64 = 20261118;
    let mut u = |lo: f64, hi: f64| {
        s = s.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = s;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^= z >> 31;
        lo + (hi - lo) * ((z >> 11) as f64 / (1u64 << 53) as f64)
    };
    let book: Vec<ZeroPosition> = (0..50)
        .map(|_| pos(u(-5e6, 5e6), u(0.1, 30.0), u(-0.01, 0.08)))
        .collect();
    for _ in 0..1000 {
        let h = u(-0.02, 0.02);
        let r = delta_gamma_bound(&book, h).unwrap();
        let e = (r.estimate_pnl - zero_revalue(&book, h)).abs();
        assert!(e <= r.bound, "{h}: {e} > {}", r.bound);
    }
}

/// A random valid log over two series: increasing sequences, knowledge times that never go back,
/// open or closed valid intervals, some deletions.
fn arb_log() -> impl Strategy<Value = (Vec<BiRecord>, i64)> {
    proptest::collection::vec(
        (
            0i64..3,
            any::<bool>(),
            0i64..20,
            proptest::option::of(1i64..10),
            0i64..5,
            any::<bool>(),
        ),
        0..10,
    )
    .prop_map(|rows| {
        let mut kt = 0;
        let log = rows
            .into_iter()
            .enumerate()
            .map(|(i, (dk, b, vf, len, val, del))| {
                kt += dk * DAY;
                let vf = T0 + vf * DAY;
                rec(
                    i as i64 + 1,
                    if b { "A" } else { "B" },
                    vf,
                    len.map(|l| vf + l * DAY),
                    T0 + kt,
                    val,
                    del && i % 3 == 2,
                )
            })
            .collect();
        (log, kt)
    })
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(10_000))]

    /// KR-4 (K-4 acceptance): appending a record known after K never changes a (K, V) answer.
    #[test]
    fn kr4_correction_property(
        (log, kt) in arb_log(),
        kd in 0i64..12,
        half in any::<bool>(),
        extra_series in any::<bool>(),
        extra_vf in 0i64..20,
        extra_len in proptest::option::of(1i64..10),
        extra_del in any::<bool>(),
        gap in 0i64..3,
    ) {
        let k = T0 + kd * DAY + if half { DAY / 2 } else { 0 };
        let later = (T0 + kt).max(k + 1) + gap * DAY;
        let vf = T0 + extra_vf * DAY;
        let extra = rec(
            log.len() as i64 + 1,
            if extra_series { "A" } else { "B" },
            vf,
            extra_len.map(|l| vf + l * DAY),
            later,
            -1,
            extra_del,
        );
        let mut longer = log.clone();
        longer.push(extra);
        prop_assert!(check_log(&longer).is_ok());
        for vd in 0..25 {
            for series in ["A", "B"] {
                let v = T0 + vd * DAY;
                prop_assert_eq!(
                    bitemporal_query(&log, series, k, v).unwrap(),
                    bitemporal_query(&longer, series, k, v).unwrap()
                );
            }
        }
    }
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(10_000))]

    /// KR-5: the incremental update equals a full rebuild bit for bit, and the pillars before the
    /// first change are copied unchanged.
    #[test]
    fn incremental_equals_full_rebuild(
        old in proptest::collection::vec(-0.01f64..0.08, 1..41),
        bumps in proptest::collection::vec((0usize..40, -0.006f64..0.006), 1..5),
    ) {
        let mut new = old.clone();
        for (j, d) in bumps {
            let j = j % old.len();
            new[j] = old[j] + d;
        }
        let prev = par_annual(&old).unwrap();
        let up = incremental_update(&old, &prev, &new).unwrap();
        let full = par_annual(&new).unwrap();
        let bits = |v: &[f64]| v.iter().map(|x| x.to_bits()).collect::<Vec<_>>();
        prop_assert_eq!(bits(&up.discount_factors), bits(&full));
        let j0 = up.first_changed_index.unwrap_or(old.len());
        prop_assert_eq!(bits(&up.discount_factors[..j0]), bits(&prev[..j0]));
        prop_assert_eq!(up.recomputed, old.len() - j0);
        prop_assert!(old[..j0] == new[..j0]);
        if j0 < old.len() {
            prop_assert!(old[j0] != new[j0]);
        }
    }
}

/// KR-232: the Student-t tail against the Python reference (`stage_k.student_t_two_sided_tail`),
/// class `tail_probability` (1e-11 relative); a value that underflows to 0 there is 0 here.
#[test]
fn student_t_tail_matches_the_reference() {
    let want = [
        (1, 0.5, 0.7048327646991335),
        (1, 3.0, 0.20483276469913345),
        (1, 30.0, 0.02121280481107085),
        (1, 1e4, 6.366197702455154e-05),
        (2, 0.5, 0.6666666666666667),
        (2, 3.0, 0.09546596626670911),
        (2, 30.0, 0.0011092626819596593),
        (2, 1e4, 9.999999850000006e-09),
        (3, 0.5, 0.651447964848151),
        (3, 3.0, 0.05766888562243732),
        (3, 30.0, 8.13528042716396e-05),
        (3, 1e4, 2.2053155022958095e-12),
        (4, 0.5, 0.6433299631818632),
        (4, 3.0, 0.0399419680717188),
        (4, 30.0, 7.352856097661315e-06),
        (4, 1e4, 5.999999600000019e-16),
        (29, 0.5, 0.6208480841937815),
        (29, 3.0, 0.0054991921339034135),
        (29, 30.0, 2.1977448450987984e-23),
        (29, 1e4, 2.3537866088124234e-96),
        (249, 0.5, 0.6175166511131459),
        (249, 3.0, 0.0029737859324150294),
        (249, 30.0, 1.1828804310465052e-84),
        (249, 1e4, 0.0),
        (1000, 0.5, 0.6171850808338741),
        (1000, 3.0, 0.0027667090442382446),
        (1000, 30.0, 1.5374687444043042e-141),
        (1000, 1e4, 0.0),
    ];
    for (nu, k, w) in want {
        let got = student_t_two_sided_tail(nu, k);
        if w == 0.0 {
            assert_eq!(got, 0.0, "{nu} {k}");
        } else {
            assert!(rel(got, w) <= 1e-11, "{nu} {k}: {got} vs {w}");
        }
    }
}

/// KR-234 acceptance, binary64 half: `|estimate - V_64| <= bound` on every book of the sweep at
/// every move (`V_64` the binary64 revaluation `zero_revalue`). The books follow the Python test
/// `test_intraday_bound_small_move_sweep`: every single position of the grid, hedged books,
/// delta-neutral pairs and 300 seeded random books (here a `SplitMix64` stream, seed 20261119; the
/// Python books use `random.Random(20261119)`, so the random books differ, the rule does not).
#[test]
fn intraday_bound_small_move_sweep() {
    let mut hs = vec![0.0];
    for e in [30, 25, 20, 16, 14, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1] {
        for x in [1.0, -1.0] {
            hs.push(x * 10f64.powi(-e));
        }
    }
    hs.extend([0.5, -0.5, 1.0, -1.0, 1.0 / 3.0, -0.07]);
    let ts = [1e-6, 1e-3, 0.25, 1.0, 5.0, 30.0, 100.0];
    let ys = [-1.0, -0.01, 0.0, 0.04, 0.3, 1.0];
    let ns = [0.0, 1e-6, 1.0, 1e6, -1e6, 1e15, -1e15];
    let mut books: Vec<Vec<ZeroPosition>> = Vec::new();
    for &n in &ns {
        for &t in &ts {
            for &y in &ys {
                books.push(vec![pos(n, t, y)]);
            }
        }
    }
    for &t in &ts {
        for &y in &ys {
            books.push(vec![pos(1e6, t, y), pos(-1e6 * (1.0 + 1e-12), t, y)]);
            books.push(vec![pos(1e6, t, y), pos(-1e6, t, y)]);
            if 2.0 * t <= 100.0 {
                let n2 = -1e6 * t * (-y * t).exp() / (2.0 * t * (-y * 2.0 * t).exp());
                books.push(vec![pos(1e6, t, y), pos(n2, 2.0 * t, y)]);
            }
        }
    }
    let mut s: u64 = 20261119;
    let mut next = || {
        s = s.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = s;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^= z >> 31;
        (z >> 11) as f64 / (1u64 << 53) as f64
    };
    for _ in 0..300 {
        let size = 1 + (next() * 20.0) as usize;
        let book = (0..size)
            .map(|_| {
                let n = -1e9 + 2e9 * next();
                let t = ts[(next() * ts.len() as f64) as usize] * (0.5 + 0.5 * next());
                let y = -0.05 + 0.15 * next();
                pos(n, t, y)
            })
            .collect();
        books.push(book);
    }
    let mut cases = 0;
    for book in &books {
        for &h in &hs {
            let r = delta_gamma_bound(book, h).unwrap();
            let gap = (r.estimate_pnl - zero_revalue(book, h)).abs();
            assert!(gap <= r.bound, "{book:?} {h}: {gap} > {}", r.bound);
            cases += 1;
        }
    }
    assert!(cases > 20_000, "{cases}");
}
