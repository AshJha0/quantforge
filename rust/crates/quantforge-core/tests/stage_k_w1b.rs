//! Stage K wave 1b (K-8d SA-CCR, K-8e FRTB IMA backtesting): the CRE99 published EADs, rules,
//! errors in HR-122 order, MAR99 Table 2, zone boundaries, and property tests.
#![allow(clippy::too_many_arguments)] // test builders mirror the spec's trade fields
use proptest::prelude::*;
use quantforge_core::frtb_backtest as fb;
use quantforge_core::json::{Json, parse};
use quantforge_core::saccr::{self, Margin, Trade};

fn ir(id: &str, n: f64, mv: f64, m: f64, pos: &str, s: f64, e: f64, ccy: &str) -> Trade {
    Trade {
        start: Some(s),
        end: Some(e),
        hedging_set: Some(ccy.to_string()),
        ..Trade::linear(id, "IR", n, mv, m, pos)
    }
}

fn fx(id: &str, n: f64, mv: f64, m: f64, pos: &str, pair: Option<&str>) -> Trade {
    Trade {
        hedging_set: pair.map(str::to_string),
        ..Trade::linear(id, "FX", n, mv, m, pos)
    }
}

fn named(id: &str, cls: &str, n: f64, mv: f64, m: f64, pos: &str, ent: &str, sub: &str) -> Trade {
    let credit = cls == "CREDIT";
    Trade {
        start: credit.then_some(0.0),
        end: credit.then_some(m),
        entity: Some(ent.to_string()),
        subclass: Some(sub.to_string()),
        ..Trade::linear(id, cls, n, mv, m, pos)
    }
}

fn ex1() -> Vec<Trade> {
    vec![
        ir("1", 10000.0, 30.0, 10.0, "LONG", 0.0, 10.0, "USD"),
        ir("2", 10000.0, -20.0, 4.0, "SHORT", 0.0, 4.0, "USD"),
        Trade {
            kind: "OPTION".to_string(),
            option_type: Some("PUT".to_string()),
            underlying_price: Some(0.06),
            strike: Some(0.05),
            exercise: Some(1.0),
            ..ir("3", 5000.0, 50.0, 11.0, "BOUGHT", 1.0, 11.0, "EUR")
        },
    ]
}

fn ex2() -> Vec<Trade> {
    vec![
        named("4", "CREDIT", 10000.0, 20.0, 3.0, "LONG", "Firm A", "AA"),
        named("5", "CREDIT", 10000.0, -40.0, 6.0, "SHORT", "Firm B", "BBB"),
        named("6", "CREDIT", 10000.0, 0.0, 5.0, "LONG", "CDX.IG", "IG"),
    ]
}

fn ex3() -> Vec<Trade> {
    vec![
        named(
            "7",
            "COMMODITY",
            10000.0,
            -50.0,
            0.75,
            "LONG",
            "CRUDE_OIL",
            "OIL_GAS",
        ),
        named(
            "8",
            "COMMODITY",
            20000.0,
            -30.0,
            2.0,
            "SHORT",
            "CRUDE_OIL",
            "OIL_GAS",
        ),
        named(
            "9",
            "COMMODITY",
            10000.0,
            100.0,
            5.0,
            "LONG",
            "SILVER",
            "METALS",
        ),
    ]
}

const WEEKLY: Margin = Margin {
    threshold: 0.0,
    mta: 5.0,
    nica: 150.0,
    remargin_days: 5,
    mpor_days: None,
    illiquid: false,
    disputes: false,
};

fn ead(t: &[Trade]) -> saccr::EadResult {
    saccr::ead(t, 0.0, None, true).expect("ok")
}

fn cat(a: Vec<Trade>, b: Vec<Trade>) -> Vec<Trade> {
    a.into_iter().chain(b).collect()
}

/// KR-30: full precision, rounded half away from zero as CRE99.20 prints.
#[test]
fn cre99_published_eads() {
    assert_eq!(ead(&ex1()).ead.round(), 569.0);
    assert_eq!(ead(&ex2()).ead.round(), 381.0);
    assert_eq!(ead(&ex3()).ead.round(), 5406.0);
    assert_eq!(ead(&cat(ex1(), ex2())).ead.round(), 936.0);
    let r5 = saccr::ead(&cat(ex1(), ex3()), 200.0, Some(&WEEKLY), true).expect("ok");
    assert_eq!(r5.ead.round(), 1879.0);
}

#[test]
fn cre99_intermediates() {
    let r1 = ead(&ex1());
    let d: Vec<f64> = r1
        .trades
        .iter()
        .map(|t| t.adjusted_notional.round())
        .collect();
    assert_eq!(d, [78694.0, 36254.0, 37428.0]);
    assert_eq!((r1.trades[2].delta * 1e4).round() / 1e4, -0.2694);
    assert_eq!(r1.trades[2].effective_notional.round(), -10083.0);
    assert_eq!(r1.hedging_sets[0].key, "EUR");
    assert_eq!((r1.hedging_sets[1].addon * 100.0).round(), 29635.0);
    assert_eq!(r1.rc, 60.0);
    let r2 = ead(&ex2());
    assert_eq!(r2.addon_aggregate.round(), 282.0);
    assert_eq!((r2.multiplier * 1000.0).round(), 965.0);
    let r3 = ead(&ex3());
    assert_eq!(r3.trades[0].effective_notional.round(), 8660.0);
    assert_eq!(r3.hedging_sets[0].key, "ENERGY");
    assert_eq!(r3.hedging_sets[0].addon.round(), 2041.0);
    let r5 = saccr::ead(&cat(ex1(), ex3()), 200.0, Some(&WEEKLY), true).expect("ok");
    assert_eq!(r5.mpor_days, Some(14));
    assert_eq!((r5.rc, r5.v), (0.0, 80.0));
    assert_eq!(r5.trades[4].effective_notional.round(), -7099.0); // KR-31: printed -7,100
    assert_eq!(r5.addon_aggregate.round(), 1401.0);
    assert_eq!((r5.multiplier * 1000.0).round(), 958.0);
    assert!(!r5.capped && r5.margined);
    assert!(r5.ead_unmargined.expect("margined") > r5.ead);
}

fn spec(name: &str) -> Json {
    let p = format!(
        "{}/../../../specifications/06-risk/{name}",
        env!("CARGO_MANIFEST_DIR")
    );
    parse(&std::fs::read_to_string(p).expect("spec file"))
        .expect("json")
        .0
}

#[test]
fn embedded_tables_parse_as_the_spec_files() {
    let doc = spec("sa-ccr-parameters.json");
    let rows = doc.get("table2").and_then(Json::as_array).expect("rows");
    let p = saccr::params();
    assert_eq!(p.table2.len(), rows.len());
    for (r, j) in p.table2.iter().zip(rows) {
        assert_eq!(
            Some(r.factor),
            j.get("supervisory_factor").and_then(Json::as_f64)
        );
        assert_eq!(r.correlation, j.get("correlation").and_then(Json::as_f64));
        assert_eq!(
            Some(r.option_volatility),
            j.get("option_volatility").and_then(Json::as_f64)
        );
    }
    assert_eq!(Some(p.alpha), doc.get("alpha").and_then(Json::as_f64));
    let f = spec("frtb-ima-backtest-tables.json");
    let t = fb::tables();
    let m: Vec<f64> = f
        .get("multiplier_250")
        .and_then(Json::as_array)
        .expect("m")
        .iter()
        .filter_map(Json::as_f64)
        .collect();
    assert_eq!(t.multiplier_250, m);
    assert_eq!(
        Some(t.max_observations),
        f.get("max_observations").and_then(Json::as_int)
    );
}

#[test]
fn multiplier_edges_and_overflow() {
    // KR-36: V - C >= 0 is exactly 1 without the exponential, which overflows for a tiny add-on.
    assert_eq!(saccr::multiplier(1e6, f64::from_bits(1)), 1.0);
    assert_eq!(saccr::multiplier(0.0, 0.0), 1.0);
    assert_eq!(saccr::multiplier(-1.0, 0.0), 0.05);
    assert_eq!(saccr::multiplier(-1e6, f64::from_bits(1)), 0.05);
    let r = ead(&[fx("a", f64::from_bits(1), 5.0, 1.0, "LONG", Some("EURUSD"))]);
    assert_eq!(r.multiplier, 1.0);
    assert!((r.ead - 7.0).abs() < 1e-12);
}

#[test]
fn rules_and_edges() {
    assert_eq!(saccr::supervisory_duration(0.0, 0.0), 10.0 / 250.0);
    assert_eq!([0.5, 1.0, 5.0, 5.0001].map(saccr::bucket), [1, 2, 2, 3]);
    let daily = Margin {
        remargin_days: 1,
        ..WEEKLY
    };
    assert_eq!(saccr::mpor_floor(&daily, 1), 10);
    assert_eq!(saccr::mpor_floor(&daily, 5001), 20);
    let hard = Margin {
        illiquid: true,
        disputes: true,
        ..daily.clone()
    };
    assert_eq!(saccr::mpor_floor(&hard, 1), 40);
    assert_eq!(saccr::mpor_floor(&WEEKLY, 5000), 14);
    let cdo = Trade {
        kind: "CDO".to_string(),
        attachment: Some(0.03),
        detachment: Some(0.07),
        ..named("c", "CREDIT", 100.0, 0.0, 1.0, "SOLD", "T", "IG")
    };
    assert!((saccr::supervisory_delta(&cdo) + 15.0 / (1.42 * 1.98)).abs() < 1e-15);
    let call = Trade {
        kind: "OPTION".to_string(),
        option_type: Some("CALL".to_string()),
        underlying_price: Some(1.1),
        strike: Some(1.0),
        exercise: Some(0.5),
        ..fx("o", 100.0, 0.0, 1.0, "SOLD", Some("EURUSD"))
    };
    let d1 = (1.1f64.ln() + 0.5 * 0.15 * 0.15 * 0.5) / (0.15 * 0.5f64.sqrt());
    let want = -quantforge_core::stats::normal_cdf(d1);
    assert!((saccr::supervisory_delta(&call) - want).abs() < 1e-15);
    let off = saccr::ead(&ex1(), 0.0, None, false).expect("ok");
    assert!(off.addon[0] > ead(&ex1()).addon[0]);
    let base = named("e", "EQUITY", 100.0, 0.0, 1.0, "LONG", "X", "SINGLE");
    let a0 = ead(std::slice::from_ref(&base)).addon_aggregate;
    for (tr, k) in [("BASIS", 0.5), ("VOLATILITY", 5.0)] {
        let t = Trade {
            treatment: tr.to_string(),
            hedging_set: Some("H".to_string()),
            ..base.clone()
        };
        assert!((ead(&[t]).addon_aggregate - k * a0).abs() < 1e-12);
    }
    let one = [fx("a", 100.0, 0.0, 1.0, "LONG", Some("EURUSD"))];
    let big = Margin {
        threshold: 1e6,
        mpor_days: Some(15),
        ..daily
    };
    let capped = saccr::ead(&one, 0.0, Some(&big), true).expect("ok");
    assert!(capped.capped);
    assert_eq!(capped.mpor_days, Some(15));
    assert_eq!(capped.ead_unmargined, Some(capped.ead));
    let unm = ead(&one);
    assert_eq!((unm.mpor_days, unm.ead_unmargined), (None, None));
    assert_eq!(unm.trades[0].supervisory_duration, None);
}

fn fails(code: &str, field: &str, t: &[Trade], m: Option<&Margin>) {
    let e = saccr::ead(t, 0.0, m, true).expect_err("an error");
    assert_eq!(
        (e.code, e.field.as_deref()),
        (code, Some(field)),
        "{}",
        e.message
    );
}

fn with(t: &Trade, kind: &str, pos: &str, a: Option<f64>, d: Option<f64>) -> Trade {
    Trade {
        kind: kind.to_string(),
        position: pos.to_string(),
        attachment: a,
        detachment: d,
        ..t.clone()
    }
}

#[test]
fn saccr_errors() {
    let ok = fx("a", 100.0, 0.0, 1.0, "LONG", Some("EURUSD"));
    fails("E_INPUT", "trades", &[], None);
    fails("E_INPUT", "id", &[ok.clone(), ok.clone()], None);
    fails(
        "E_INPUT",
        "start",
        &[Trade {
            hedging_set: Some("USD".into()),
            ..Trade::linear("a", "IR", 1.0, 0.0, 1.0, "LONG")
        }],
        None,
    );
    fails(
        "E_INPUT",
        "hedging_set",
        &[fx("a", 1.0, 0.0, 1.0, "LONG", None)],
        None,
    );
    let mut no_entity = named("a", "EQUITY", 1.0, 0.0, 1.0, "LONG", "X", "SINGLE");
    no_entity.entity = None;
    fails("E_INPUT", "entity", &[no_entity], None);
    fails(
        "E_INPUT",
        "subclass",
        &[named("a", "EQUITY", 1.0, 0.0, 1.0, "LONG", "X", "IG")],
        None,
    );
    let fx_sub = Trade {
        subclass: Some("IG".into()),
        ..ok.clone()
    };
    fails("E_INPUT", "subclass", &[fx_sub], None);
    let two = [
        named("a", "EQUITY", 1.0, 0.0, 1.0, "LONG", "X", "SINGLE"),
        named("b", "EQUITY", 1.0, 0.0, 1.0, "LONG", "X", "INDEX"),
    ];
    fails("E_INPUT", "subclass", &two, None);
    fails(
        "E_INPUT",
        "position",
        &[fx("a", 1.0, 0.0, 1.0, "BOUGHT", Some("X"))],
        None,
    );
    fails(
        "E_INPUT",
        "option_type",
        &[with(&ok, "OPTION", "BOUGHT", None, None)],
        None,
    );
    fails(
        "E_INPUT",
        "kind",
        &[with(&ok, "CDO", "BOUGHT", Some(0.1), Some(0.2))],
        None,
    );
    let credit = named("c", "CREDIT", 1.0, 0.0, 1.0, "LONG", "T", "IG");
    fails(
        "E_INPUT",
        "attachment",
        &[with(&credit, "CDO", "BOUGHT", None, Some(0.2))],
        None,
    );
    fails(
        "E_DOMAIN",
        "notional",
        &[fx("a", 0.0, 0.0, 1.0, "LONG", Some("X"))],
        None,
    );
    fails(
        "E_DOMAIN",
        "maturity",
        &[fx("a", 1.0, 0.0, -1.0, "LONG", Some("X"))],
        None,
    );
    fails(
        "E_DOMAIN",
        "start",
        &[ir("a", 1.0, 0.0, 1.0, "LONG", 2.0, 1.0, "USD")],
        None,
    );
    let opt = |p: f64, k: f64, t: f64| Trade {
        kind: "OPTION".into(),
        option_type: Some("CALL".into()),
        underlying_price: Some(p),
        strike: Some(k),
        exercise: Some(t),
        ..fx("o", 100.0, 0.0, 1.0, "BOUGHT", Some("X"))
    };
    fails("E_DOMAIN", "strike", &[opt(1.0, 0.0, 1.0)], None);
    fails("E_DOMAIN", "strike", &[opt(0.0, 1.0, 1.0)], None);
    fails("E_DOMAIN", "exercise", &[opt(1.0, 1.0, 0.0)], None);
    for (a, d) in [(0.3, 0.3), (-0.1, 0.3), (0.1, 1.3)] {
        fails(
            "E_DOMAIN",
            "attachment",
            &[with(&credit, "CDO", "BOUGHT", Some(a), Some(d))],
            None,
        );
    }
    let m = |th: f64, mta: f64, rd: i64, mp: Option<i64>| Margin {
        threshold: th,
        mta,
        remargin_days: rd,
        mpor_days: mp,
        ..WEEKLY
    };
    fails(
        "E_DOMAIN",
        "threshold",
        std::slice::from_ref(&ok),
        Some(&m(-1.0, 0.0, 1, None)),
    );
    fails(
        "E_DOMAIN",
        "mta",
        std::slice::from_ref(&ok),
        Some(&m(0.0, -1.0, 1, None)),
    );
    fails(
        "E_DOMAIN",
        "remargin_days",
        std::slice::from_ref(&ok),
        Some(&m(0.0, 0.0, 0, None)),
    );
    fails(
        "E_DOMAIN",
        "mpor_days",
        std::slice::from_ref(&ok),
        Some(&m(0.0, 0.0, 1, Some(0))),
    );
    // HR-122: a structural error on a later trade outranks a domain error on an earlier one,
    // and the finite rule outranks both.
    let bad = [
        fx("a", -5.0, 0.0, 1.0, "LONG", Some("X")),
        fx("b", 1.0, 0.0, 1.0, "LONG", None),
    ];
    fails("E_INPUT", "hedging_set", &bad, None);
    fails(
        "E_DOMAIN",
        "notional",
        &[fx("b", f64::NAN, 0.0, 1.0, "LONG", None)],
        None,
    );
    fails(
        "E_DOMAIN",
        "strike",
        &[Trade {
            strike: Some(f64::INFINITY),
            ..ok.clone()
        }],
        None,
    );
    let e = saccr::ead(std::slice::from_ref(&ok), f64::NAN, None, true).expect_err("finite");
    assert_eq!(e.field.as_deref(), Some("collateral"));
    let e = saccr::ead(
        &[ok],
        0.0,
        Some(&Margin {
            nica: f64::NAN,
            ..WEEKLY
        }),
        true,
    )
    .expect_err("finite");
    assert_eq!(e.field.as_deref(), Some("nica"));
}

/// KR-41: MAR99 Table 2 rows 0 to 10 at 250 observations.
#[test]
fn mar99_table2() {
    let doc = spec("frtb-ima-backtest-tables.json");
    let arr = |k: &str| doc.get(k).and_then(Json::as_array).expect("array").to_vec();
    let (pct, zones) = (
        arr("printed_table2_cumulative_percent"),
        arr("printed_table2_zone"),
    );
    for x in 0..=10_i64 {
        let z = fb::zone(250, x, 0).expect("ok");
        let i = x as usize;
        assert_eq!(
            Some((z.cumulative_probability * 1e4).round() / 100.0),
            pct[i].as_f64(),
            "row {x}"
        );
        assert_eq!(Some(z.zone), zones[i].as_str());
        assert_eq!((z.amber_from, z.red_from), (5, 10));
    }
    let mult: Vec<f64> = (0..=10)
        .map(|x| fb::zone(250, x, 0).expect("ok").multiplier.expect("250"))
        .collect();
    assert_eq!(
        mult,
        [1.5, 1.5, 1.5, 1.5, 1.5, 1.7, 1.76, 1.83, 1.88, 1.92, 2.0]
    );
    assert_eq!(fb::zone(260, 6, 6).expect("ok").multiplier, None);
    assert_eq!(fb::zone(1, 0, 0).expect("ok").zone, "AMBER"); // KR-42
    assert_eq!(fb::binomial_cdf(10, -1, 0.01), 0.0);
    assert_eq!(fb::binomial_cdf(10, 10, 0.01), 1.0);
    assert_eq!(fb::first_at_least(1, 0.5, 0.9999), 1);
}

#[test]
fn desk_count_and_errors() {
    let d = fb::desk(250, [12, 10, 30, 28]).expect("ok");
    assert!(d.eligible && !d.breach_99 && !d.breach_975);
    assert!(fb::desk(250, [13, 0, 0, 0]).expect("ok").breach_99);
    let d31 = fb::desk(250, [0, 0, 0, 31]).expect("ok");
    assert!(d31.breach_975 && !d31.eligible);
    let c = fb::count_exceptions(
        &[Some(1.0), Some(1.0), None, Some(2.0), Some(0.5)],
        &[Some(-1.0), Some(-1.25), Some(0.3), None, Some(0.0)],
        &[Some(-1.5), Some(0.0), Some(0.1), Some(-2.5), Some(-0.5)],
    )
    .expect("ok");
    assert_eq!(
        (c.days_actual, c.days_hypothetical, c.exceptions),
        (vec![1, 2, 3], vec![0, 2, 3], 3)
    );
    let code = |r: Result<fb::Zone, quantforge_core::error::QfError>| r.expect_err("error").code;
    assert_eq!(code(fb::zone(1_000_001, -1, 0)), "E_LIMIT");
    assert_eq!(code(fb::zone(0, 0, 0)), "E_DOMAIN");
    assert_eq!(code(fb::zone(10, 11, 0)), "E_DOMAIN");
    assert_eq!(code(fb::zone(10, 0, -1)), "E_DOMAIN");
    assert_eq!(
        fb::desk(250, [0, 0, 251, 0]).expect_err("e").code,
        "E_DOMAIN"
    );
    let none: [Option<f64>; 0] = [];
    let one = [Some(1.0)];
    assert_eq!(
        fb::count_exceptions(&none, &none, &none)
            .expect_err("e")
            .field
            .as_deref(),
        Some("var")
    );
    assert_eq!(
        fb::count_exceptions(&one, &none, &one)
            .expect_err("e")
            .field
            .as_deref(),
        Some("actual")
    );
    assert_eq!(
        fb::count_exceptions(&one, &one, &none)
            .expect_err("e")
            .field
            .as_deref(),
        Some("hypothetical")
    );
    assert_eq!(
        fb::count_exceptions(&[Some(f64::NAN)], &one, &one)
            .expect_err("e")
            .code,
        "E_DOMAIN"
    );
}

const CLASSES: [&str; 5] = ["IR", "FX", "CREDIT", "EQUITY", "COMMODITY"];
const SUBS: [&[&str]; 3] = [
    &["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "IG", "SG"],
    &["SINGLE", "INDEX"],
    &["ELECTRICITY", "OIL_GAS", "METALS", "AGRICULTURAL", "OTHER"],
];

type Draw = (usize, bool, f64, f64, f64, f64, usize, usize);

fn draw() -> impl Strategy<Value = Draw> {
    (
        0..5usize,
        any::<bool>(),
        1.0..1e7f64,
        -1e5..1e5f64,
        0.01..30.0f64,
        0.0..5.0f64,
        0..9usize,
        0..3usize,
    )
}

fn build(draws: &[Draw], scale: f64) -> Vec<Trade> {
    draws
        .iter()
        .enumerate()
        .map(|(k, &(c, long, n, v, m, s, sub, ent))| {
            let id = k.to_string();
            let pos = if long { "LONG" } else { "SHORT" };
            let n = n * scale;
            match CLASSES[c] {
                "IR" => ir(
                    &id,
                    n,
                    v,
                    m,
                    pos,
                    s,
                    s + m,
                    if ent == 0 { "USD" } else { "EUR" },
                ),
                "FX" => fx(
                    &id,
                    n,
                    v,
                    m,
                    pos,
                    Some(if ent == 0 { "EURUSD" } else { "USDJPY" }),
                ),
                cls => {
                    let subs = SUBS[c - 2];
                    let sb = subs[sub % subs.len()];
                    named(&id, cls, n, v, m, pos, &format!("{sb}-{ent}"), sb)
                }
            }
        })
        .collect()
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(150))]

    /// Spec "Acceptance": multiplier in [0.05, 1]; netting never above the stand-alone add-ons;
    /// EAD non-decreasing in notional and non-increasing in collateral.
    #[test]
    fn saccr_properties(d in prop::collection::vec(draw(), 1..7), c in -1e5..1e5f64) {
        let t = build(&d, 1.0);
        let r = saccr::ead(&t, c, None, true).expect("ok");
        prop_assert!((0.05..=1.0).contains(&r.multiplier));
        let alone: f64 = t.iter().map(|x| ead(std::slice::from_ref(x)).addon_aggregate).sum();
        prop_assert!(r.addon_aggregate <= alone * (1.0 + 1e-12) + 1e-9);
        let bigger = saccr::ead(&build(&d, 1.5), c, None, true).expect("ok");
        prop_assert!(bigger.ead >= r.ead * (1.0 - 1e-12));
        let more_c = saccr::ead(&t, c + 100.0, None, true).expect("ok");
        prop_assert!(more_c.ead <= r.ead * (1.0 + 1e-12) + 1e-9);
    }

    /// The multiplier is strictly inside (0.05, 1] wherever exp does not underflow.
    #[test]
    fn multiplier_open_floor(log_addon in -5.0..10.0f64, ratio in 0.0..30.0f64) {
        let addon = log_addon.exp();
        let m = saccr::multiplier(-addon * ratio, addon);
        prop_assert!(m > 0.05 && m <= 1.0);
    }

    /// amber_from and red_from are the first counts whose binomial CDF reaches 95% and 99.99%.
    #[test]
    fn zone_boundaries(n in 1..3000i64, frac in 0.0..1.0f64) {
        let z = fb::zone(n, 0, 0).expect("ok");
        let p = 0.01;
        prop_assert!(fb::binomial_cdf(n, z.amber_from, p) >= 0.95);
        prop_assert!(z.amber_from == 0 || fb::binomial_cdf(n, z.amber_from - 1, p) < 0.95);
        prop_assert!(fb::binomial_cdf(n, z.red_from, p) >= 0.9999);
        prop_assert!(z.red_from == 0 || fb::binomial_cdf(n, z.red_from - 1, p) < 0.9999);
        let x = ((n as f64) * frac) as i64;
        let want = if x >= z.red_from { "RED" } else if x >= z.amber_from { "AMBER" } else { "GREEN" };
        prop_assert_eq!(fb::zone(n, x, 0).expect("ok").zone, want);
    }
}
