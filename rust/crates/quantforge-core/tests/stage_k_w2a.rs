//! Stage K wave 2a (K-8a DRC and RRAO, K-8f IMA): the parameters against the shared tables
//! (KR-50), hand cases from `frtb-drc-rrao.md` and `frtb-ima.md`, the pinned KR-327 counterexample
//! and the A3 properties (proptest). Mirrors `python/tests/test_stage_k_w2a.py`.
#![allow(clippy::unwrap_used, clippy::float_cmp)]
use proptest::prelude::*;
use quantforge_core::dates::Date;
use quantforge_core::error::QfError;
use quantforge_core::frtb_drc::{self as drc, CtpPosition, Instrument, Position, SecPosition};
use quantforge_core::frtb_ima::{self as ima, CapitalInputs};
use quantforge_core::json::{Json, parse};
use std::collections::BTreeMap;

// ---- KR-50: every parameter equals the shared table ------------------------------------------------

fn table(name: &str) -> BTreeMap<String, Json> {
    let path = format!(
        "{}/../../../specifications/tables/stage_k/{name}.json",
        env!("CARGO_MANIFEST_DIR")
    );
    let (doc, _) = parse(&std::fs::read_to_string(path).unwrap()).unwrap();
    doc.get("entries")
        .and_then(Json::as_array)
        .unwrap()
        .iter()
        .map(|e| {
            (
                e.get("key").and_then(Json::as_str).unwrap().to_string(),
                e.get("value").unwrap().clone(),
            )
        })
        .collect()
}

/// A table number: a decimal string or a JSON number.
fn num(v: &Json) -> f64 {
    v.as_str()
        .map_or_else(|| v.as_f64().unwrap(), |s| s.parse().unwrap())
}

#[test]
fn parameters_match_tables() {
    let t = table("mar22_drc");
    let lgd = [
        "lgd.covered_bond",
        "lgd.senior_debt",
        "lgd.non_senior_debt",
        "lgd.equity",
    ];
    for (k, key) in lgd.iter().enumerate() {
        assert_eq!(drc::LGD[k], num(&t[*key]), "{key}");
    }
    for (k, r) in drc::RATINGS.iter().enumerate() {
        let name = match *r {
            "UNRATED" => "Unrated",
            "DEFAULTED" => "Defaulted",
            other => other,
        };
        assert_eq!(drc::RISK_WEIGHT[k], num(&t[&format!("rw.{name}")]), "{r}");
    }
    assert_eq!(drc::MATURITY_FLOOR, num(&t["maturity_weight_floor"]));
    assert_eq!(drc::CAPITAL_HORIZON, num(&t["capital_horizon_years"]));
    let choices = t["cash_equity_maturity_choices"].as_array().unwrap();
    assert_eq!(drc::CASH_EQUITY_SHORT, num(&choices[0]));
    assert_eq!(drc::CTP_CROSS_FACTOR, num(&t["ctp_cross_index_factor"]));
    let r = table("mar23_rrao");
    assert_eq!(drc::RRAO_WEIGHT[0], num(&r["rw.exotic_underlying"]));
    assert_eq!(drc::RRAO_WEIGHT[1], num(&r["rw.other_residual_risk"]));

    let f = table("mar31_rfet");
    assert_eq!(ima::RFET_MIN_DAYS as f64, num(&f["rfet.min_obs_per_year"]));
    assert_eq!(ima::RFET_WINDOW_DAYS as f64, num(&f["rfet.window_days"]));
    assert_eq!(
        ima::RFET_MIN_PER_WINDOW as f64,
        num(&f["rfet.min_obs_per_window"])
    );
    assert_eq!(ima::RFET_ALT_MIN_DAYS as f64, num(&f["rfet.alt_min_obs_12m"]));
    assert_eq!(
        ima::RFET_LOOKBACK_MONTHS as f64,
        num(&f["rfet.lookback_months"])
    );
    for (row, lows) in ima::RFET_BUCKETS {
        let printed = f[&format!("bucket.{row}")].as_array().unwrap();
        let pair = |p: &Json| p.as_array().unwrap().to_vec();
        let printed_lows: Vec<f64> = printed.iter().map(|p| num(&pair(p)[0])).collect();
        assert_eq!(lows, printed_lows.as_slice(), "row {row}");
        let highs: Vec<f64> = printed[..printed.len() - 1]
            .iter()
            .map(|p| num(&pair(p)[1]))
            .collect();
        assert_eq!(&lows[1..], highs.as_slice(), "row {row}");
        let last = pair(printed.last().unwrap())[1].as_str().unwrap().to_string();
        assert_eq!(last, if row == "D" { "1.00" } else { "inf" });
    }

    let p = table("mar32_pla");
    let mult = &p["backtest.zone_multiplier"];
    for k in 0..10 {
        assert_eq!(ima::MULTIPLIER[k], num(mult.get(&k.to_string()).unwrap()));
    }
    assert_eq!(ima::MULTIPLIER_RED, num(mult.get("10+").unwrap()));
    assert_eq!(ima::PLA_GREEN_SPEARMAN, num(&p["pla.green.spearman_above"]));
    assert_eq!(ima::PLA_RED_SPEARMAN, num(&p["pla.red.spearman_below"]));
    assert_eq!(
        ima::PLA_GREEN_KS_PERCENT as f64 / 100.0,
        num(&p["pla.green.ks_below"])
    );
    assert_eq!(
        ima::PLA_RED_KS_PERCENT as f64 / 100.0,
        num(&p["pla.red.ks_above"])
    );
    assert_eq!(ima::PLA_WINDOW as f64, num(&p["pla.window_days"]));

    let m = table("mar33_ima");
    for j in 1..=5 {
        let h = num(m["lh.j"].get(&j.to_string()).unwrap());
        assert_eq!(ima::LIQUIDITY_HORIZONS[j - 1] as f64, h);
    }
    assert_eq!(ima::ES_CONFIDENCE, num(&m["es.confidence"]));
    assert_eq!(ima::BASE_HORIZON as f64, num(&m["es.base_horizon_days"]));
    let Json::Obj(lh) = &m["lh.table"] else {
        panic!("lh.table is an object")
    };
    let printed: Vec<(String, f64)> = lh.iter().map(|(k, v)| (k.clone(), num(v))).collect();
    let ours: Vec<(String, f64)> = ima::LH_TABLE
        .iter()
        .map(|(k, v)| ((*k).to_string(), *v as f64))
        .collect();
    assert_eq!(ours, printed);
    let pairs: Vec<&str> = m["lh.specified_fx_pairs"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap())
        .collect();
    assert_eq!(ima::SPECIFIED_FX_PAIRS.as_slice(), pairs.as_slice());
    assert_eq!(ima::IMCC_RHO, num(&m["imcc.rho"]));
    assert_eq!(ima::SES_RHO, num(&m["ses.rho"]));
    // KR-57: the computed factor is one ulp from the printed constant.
    assert!((ima::normal_es_factor() - ima::NORMAL_ES_FACTOR_DOC).abs() <= 1e-15);
}

// ---- K-8a units ------------------------------------------------------------------------------------

fn pos(id: &str, ob: &str, sen: &str, n: f64, mv: f64, m: f64) -> Position {
    Position {
        id: id.to_string(),
        obligor: ob.to_string(),
        bucket: "CORPORATE".to_string(),
        seniority: sen.to_string(),
        notional: n,
        market_value: mv,
        maturity_years: m,
        cash_equity: false,
        lgd_applies: true,
    }
}

fn ratings(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
    pairs
        .iter()
        .map(|(a, b)| ((*a).to_string(), (*b).to_string()))
        .collect()
}

fn code<T: std::fmt::Debug>(r: Result<T, QfError>) -> &'static str {
    r.unwrap_err().code
}

#[test]
fn jtd_and_weight_details() {
    let mut p = pos("a", "X", "SENIOR", 100.0, 100.0, 5.0);
    p.lgd_applies = false;
    assert_eq!(drc::gross_jtd(&p), 100.0);
    assert_eq!(drc::gross_jtd(&pos("a", "X", "SENIOR", 100.0, 100.0, 5.0)), 75.0);
    assert_eq!(drc::gross_jtd(&pos("a", "X", "SENIOR", 0.0, 0.0, 5.0)), 0.0);
    assert_eq!(drc::gross_jtd(&pos("a", "X", "SENIOR", 100.0, 10.0, 5.0)), 0.0);
    assert_eq!(drc::gross_jtd(&pos("a", "X", "SENIOR", -100.0, -10.0, 5.0)), 0.0);
    assert_eq!(drc::maturity_weight(0.1), 0.25);
    assert_eq!(drc::maturity_weight(0.6), 0.6);
    assert_eq!(drc::maturity_weight(3.0), 1.0);
}

#[test]
fn offset_greedy_kr53() {
    // A junior short is served after the senior one, so the senior short gets the covered long.
    assert_eq!(
        drc::offset(&[(4, 10.0), (1, 10.0)], &[(1, -10.0), (4, -10.0)]),
        (0.0, 0.0)
    );
    assert_eq!(drc::offset(&[(1, 10.0)], &[(3, -5.0)]), (10.0, -5.0));
    assert_eq!(drc::offset(&[(3, 10.0)], &[(1, -4.0)]), (6.0, 0.0));
    assert_eq!(drc::offset(&[], &[]), (0.0, 0.0));
}

#[test]
fn nonsec_hand_case_and_buckets() {
    // drc_k-0001: one senior long of 100, BBB: JTD 75, DRC 0.06 x 75 = 4.5.
    let out = drc::drc_nonsec(
        &[pos("p1", "X", "SENIOR", 100.0, 100.0, 5.0)],
        &ratings(&[("X", "BBB")]),
    )
    .unwrap();
    assert_eq!(out.positions[0].gross_jtd, Some(75.0));
    assert_eq!(out.buckets[0].hbr, Some(1.0));
    assert!((out.drc - 4.5).abs() < 1e-15);
    // Only a short: HBR 0, DRC 0; an obligor with zero JTD only: HBR undefined (KR-54).
    let out = drc::drc_nonsec(
        &[
            pos("z", "Z", "SENIOR", 0.0, 0.0, 5.0),
            pos("s", "S", "SENIOR", -10.0, -10.0, 5.0),
        ],
        &ratings(&[("Z", "A"), ("S", "B")]),
    )
    .unwrap();
    assert_eq!(out.buckets.len(), 1);
    assert_eq!(out.buckets[0].hbr, Some(0.0));
    let out = drc::drc_nonsec(
        &[pos("z", "Z", "SENIOR", 0.0, 0.0, 5.0)],
        &ratings(&[("Z", "A")]),
    )
    .unwrap();
    assert_eq!(out.buckets[0].hbr, None);
    assert_eq!(out.buckets[0].drc, 0.0);
    // Output order: ids and obligors by code point, buckets in MAR22.22 order (KR-302).
    let mut sov = pos("b", "B", "SENIOR", 10.0, 10.0, 5.0);
    sov.bucket = "SOVEREIGN".to_string();
    let out = drc::drc_nonsec(
        &[sov, pos("a", "A", "SENIOR", 10.0, 10.0, 5.0)],
        &ratings(&[("A", "A"), ("B", "AA")]),
    )
    .unwrap();
    let ids: Vec<&str> = out.positions.iter().map(|p| p.id.as_str()).collect();
    assert_eq!(ids, ["a", "b"]);
    let buckets: Vec<&str> = out.buckets.iter().map(|b| b.bucket.as_str()).collect();
    assert_eq!(buckets, ["CORPORATE", "SOVEREIGN"]);
}

#[test]
fn nonsec_errors_in_kr67_order() {
    let r = ratings(&[("X", "A")]);
    let big: Vec<Position> = (0..=drc::MAX_POSITIONS)
        .map(|k| pos(&k.to_string(), "X", "SENIOR", 1.0, 1.0, 1.0))
        .collect();
    assert_eq!(code(drc::drc_nonsec(&big, &r)), "E_LIMIT");
    assert_eq!(code(drc::drc_nonsec(&[], &r)), "E_INPUT");
    let dup = [
        pos("a", "X", "SENIOR", 1.0, 1.0, 1.0),
        pos("a", "X", "SENIOR", 1.0, 1.0, 1.0),
    ];
    assert_eq!(code(drc::drc_nonsec(&dup, &r)), "E_INPUT");
    // Structural before domain: a missing rating on the second position wins over a bad maturity
    // on the first.
    let two = [
        pos("a", "X", "SENIOR", 1.0, 1.0, -1.0),
        pos("b", "Y", "SENIOR", 1.0, 1.0, 1.0),
    ];
    assert_eq!(code(drc::drc_nonsec(&two, &r)), "E_INPUT");
    let mut other_bucket = pos("b", "X", "SENIOR", 1.0, 1.0, 1.0);
    other_bucket.bucket = "SOVEREIGN".to_string();
    let e = drc::drc_nonsec(&[pos("a", "X", "SENIOR", 1.0, 1.0, 1.0), other_bucket], &r)
        .unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_INPUT", Some("positions/1/bucket")));
    assert_eq!(
        code(drc::drc_nonsec(&[pos("a", "X", "SENIOR", 1.0, 1.0, 0.0)], &r)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(drc::drc_nonsec(&[pos("a", "X", "SENIOR", 0.0, 1.0, 1.0)], &r)),
        "E_DOMAIN"
    );
    // Cash equity: maturity 0.25 or at least 1 (KR-52), EQUITY with notional = market value (KR-300).
    let mut eq = pos("a", "X", "EQUITY", 5.0, 5.0, 0.5);
    eq.cash_equity = true;
    assert_eq!(code(drc::drc_nonsec(std::slice::from_ref(&eq), &r)), "E_DOMAIN");
    eq.maturity_years = 0.25;
    assert!(drc::drc_nonsec(std::slice::from_ref(&eq), &r).is_ok());
    eq.seniority = "SENIOR".to_string();
    assert_eq!(code(drc::drc_nonsec(&[eq], &r)), "E_DOMAIN");
}

fn sec(id: &str, mv: f64, m: f64, rw: f64) -> SecPosition {
    SecPosition {
        id: id.to_string(),
        bucket: "B1".to_string(),
        pool: "P".to_string(),
        tranche: "T".to_string(),
        market_value: mv,
        maturity_years: m,
        rw,
    }
}

fn ctp(id: &str, index: &str, mv: f64, rw: f64) -> CtpPosition {
    CtpPosition {
        id: id.to_string(),
        index: index.to_string(),
        series: "S".to_string(),
        tranche: "T".to_string(),
        market_value: mv,
        maturity_years: 2.0,
        rw,
    }
}

#[test]
fn sec_and_ctp_details() {
    let out = drc::drc_sec_nonctp(&[sec("a", 10.0, 0.5, 0.2), sec("b", -4.0, 0.5, 0.2)]).unwrap();
    assert!((out.buckets[0].wtd_long - 0.2 * 3.0).abs() < 1e-15);
    assert_eq!(out.positions[0].gross_jtd, None);
    assert_eq!(drc::drc_sec_nonctp(&[sec("a", -4.0, 2.0, 0.2)]).unwrap().drc, 0.0);
    // One rw per netting group (KR-303), checked before the rw cap (structural first).
    assert_eq!(
        code(drc::drc_sec_nonctp(&[sec("a", 1.0, 1.0, 13.0), sec("b", 1.0, 1.0, 0.5)])),
        "E_INPUT"
    );
    assert_eq!(code(drc::drc_sec_nonctp(&[sec("a", 1.0, 1.0, 13.0)])), "E_DOMAIN");
    assert_eq!(code(drc::drc_sec_nonctp(&[sec("a", 1.0, 0.0, 0.5)])), "E_DOMAIN");

    assert_eq!(drc::drc_ctp(Some(&[]), None).unwrap().hbr_ctp, None);
    let out = drc::drc_ctp(Some(&[ctp("a", "I", 100.0, 0.1), ctp("b", "I", -40.0, 0.1)]), None)
        .unwrap();
    assert_eq!(out.hbr_ctp, Some(1.0));
    assert!((out.drc - 6.0).abs() < 1e-12);
    // Two indices, one net short: the short index's DRC_b is negative and counts half (MAR22.45).
    let out = drc::drc_ctp(Some(&[ctp("a", "I", 100.0, 0.1), ctp("b", "J", -40.0, 0.5)]), None)
        .unwrap();
    let hbr = 100.0 / 140.0;
    assert_eq!(out.buckets[1].drc, -hbr * 20.0);
    assert!((out.drc - (10.0 - 0.5 * hbr * 20.0)).abs() < 1e-12);
    assert!((drc::ctp_total(&[-5.0, 3.0]) - 0.5).abs() < 1e-15);
    assert_eq!(drc::ctp_total(&[-5.0]), 0.0);
    assert_eq!(drc::drc_ctp(None, Some(&[2.0, -1.0])).unwrap().drc, 1.5);
    assert_eq!(code(drc::drc_ctp(None, None)), "E_INPUT");
    assert_eq!(code(drc::drc_ctp(Some(&[]), Some(&[]))), "E_INPUT");
    let big = vec![0.0; drc::MAX_POSITIONS + 1];
    assert_eq!(code(drc::drc_ctp(None, Some(&big))), "E_LIMIT");
}

#[test]
fn rrao_details() {
    let x = |id: &str, kind: &str, listed: bool, b2b: bool| Instrument {
        id: id.to_string(),
        gross_notional: 100.0,
        kind: kind.to_string(),
        listed_or_clearable: listed,
        back_to_back: b2b,
    };
    let out = drc::rrao(&[
        x("a", "EXOTIC", true, false),
        x("b", "OTHER", false, true),
        x("c", "OTHER", true, false),
        x("d", "OTHER", false, false),
    ])
    .unwrap();
    let excluded: Vec<bool> = out.instruments.iter().map(|r| r.excluded).collect();
    assert_eq!(excluded, [false, true, true, false]);
    assert!((out.rrao - 1.1).abs() < 1e-15);
    let mut neg = x("a", "EXOTIC", false, false);
    neg.gross_notional = -1.0;
    assert_eq!(code(drc::rrao(&[neg])), "E_DOMAIN");
    assert_eq!(
        code(drc::rrao(&[x("a", "EXOTIC", false, false), x("a", "OTHER", false, false)])),
        "E_INPUT"
    );
}

// ---- KR-327: the pinned counterexample and the corrected A3 property -------------------------------

const PROP_RATINGS: [(&str, &str); 3] = [("A", "BBB"), ("B", "BB"), ("C", "AA")];

fn prop_bucket(ob: &str) -> &'static str {
    if ob == "C" { "SOVEREIGN" } else { "CORPORATE" }
}

fn prop_pos(id: &str, ob: &str, sen: &str, n: f64, mv: f64, m: f64) -> Position {
    let mut p = pos(id, ob, sen, n, mv, m);
    p.bucket = prop_bucket(ob).to_string();
    p
}

fn bucket_drc(out: &drc::NonsecResult, bucket: &str) -> Option<f64> {
    out.buckets.iter().find(|b| b.bucket == bucket).map(|b| b.drc)
}

/// KR-327 (CONFIRMED 2026-11-20): a covered long of 885 added to obligor A lowers CORPORATE DRC_b.
/// The long offsets A's shorts, so the bucket's net short falls and the HBR rises from 0.288 to
/// 0.395; the weight on the remaining shorts rises more than the weighted long does. The book is the
/// Java seed -24 book of `FrtbDrcTest.a3MonotonicityCounterexample`; the old A3 sentence ("adding a
/// long only to a bucket never lowers that bucket's DRC") is false on it.
#[test]
fn kr327_a3_monotonicity_counterexample() {
    let rows = [
        ("p0", "B", "COVERED", 932.0, 943.0, 0.25),
        ("p1", "B", "SENIOR", -773.0, 819.0, 3.0),
        ("p2", "B", "NON_SENIOR", 627.0, 943.0, 0.1),
        ("p3", "A", "SENIOR", -805.0, -412.0, 0.1),
        ("p4", "A", "EQUITY", -231.0, -355.0, 0.25),
        ("p5", "A", "COVERED", 368.0, 834.0, 0.25),
        ("p6", "B", "SENIOR", -663.0, -798.0, 0.5),
        ("p7", "A", "SENIOR", -684.0, 387.0, 0.1),
        ("p8", "C", "COVERED", 756.0, 381.0, 1.0),
        ("p9", "A", "EQUITY", -673.0, -326.0, 3.0),
    ];
    let book: Vec<Position> = rows
        .iter()
        .map(|(i, o, s, n, mv, m)| prop_pos(i, o, s, *n, *mv, *m))
        .collect();
    let r = ratings(&PROP_RATINGS);
    let before = drc::drc_nonsec(&book, &r).unwrap();
    let mut more = book.clone();
    more.push(prop_pos("new", "A", "COVERED", 885.0, 885.0, 2.0));
    let after = drc::drc_nonsec(&more, &r).unwrap();
    let (b, a) = (
        bucket_drc(&before, "CORPORATE").unwrap(),
        bucket_drc(&after, "CORPORATE").unwrap(),
    );
    assert!((b - 18.67915216395695).abs() <= 1e-12 * b);
    assert!((a - 17.739318324443047).abs() <= 1e-12 * a);
    assert!(a < b);
    let hbr = |o: &drc::NonsecResult| o.buckets[0].hbr.unwrap();
    assert!((hbr(&before) - 0.288).abs() < 5e-4 && (hbr(&after) - 0.395).abs() < 5e-4);
}

fn seniority() -> impl Strategy<Value = &'static str> {
    prop::sample::select(drc::SENIORITIES.to_vec())
}

fn obligor() -> impl Strategy<Value = &'static str> {
    prop::sample::select(vec!["A", "B", "C"])
}

prop_compose! {
    /// A random book of 1 to 12 positions over three obligors in two buckets, as the Python and Java
    /// properties draw it; rows with zero notional and a nonzero market value are dropped.
    fn book()(rows in prop::collection::vec(
        (obligor(), seniority(), -1000i32..=1000, -1000i32..=1000,
         prop::sample::select(vec![0.1, 0.25, 0.5, 0.9, 1.0, 3.0])),
        1..=12,
    )) -> Vec<Position> {
        let kept: Vec<Position> = rows
            .iter()
            .enumerate()
            .filter(|(_, r)| !(r.2 == 0 && r.3 != 0))
            .map(|(k, r)| prop_pos(&format!("p{k}"), r.0, r.1, f64::from(r.2), f64::from(r.3), r.4))
            .collect();
        if kept.is_empty() { vec![prop_pos("p0", "A", "SENIOR", 1.0, 1.0, 1.0)] } else { kept }
    }
}

proptest! {
    // A3 asks for 10,000 random portfolios.
    #![proptest_config(ProptestConfig::with_cases(10_000))]

    /// A3 of `frtb-drc-rrao.md` as corrected by KR-327: DRC is 0 or positive; a long added to an
    /// obligor with no net short, with risk weight at least that of every obligor with a net short in
    /// the bucket, never lowers DRC_b; permuting the input leaves every output unchanged (totals to
    /// rounding); scaling every notional and market value by c > 0 scales DRC by c.
    #[test]
    fn drc_a3_properties(
        book in book(),
        extra in 0i32..=1000,
        ob in obligor(),
        sen in seniority(),
        perm in Just(()).prop_perturb(|(), mut rng| rng.random::<u64>()),
    ) {
        let r = ratings(&PROP_RATINGS);
        let out = drc::drc_nonsec(&book, &r).unwrap();
        prop_assert!(out.drc >= 0.0);
        for b in &out.buckets {
            prop_assert!(b.drc >= 0.0);
            prop_assert!(b.hbr.is_none_or(|h| (0.0..=1.0).contains(&h)));
        }

        let bucket = prop_bucket(ob);
        let mut more = book.clone();
        more.push(prop_pos("new", ob, sen, f64::from(extra), f64::from(extra), 2.0));
        let after = drc::drc_nonsec(&more, &r).unwrap();
        let short_rw = out
            .obligors
            .iter()
            .filter(|o| prop_bucket(&o.obligor) == bucket && o.net_short != 0.0)
            .map(|o| o.rw)
            .fold(0.0, f64::max);
        let no_short = out
            .obligors
            .iter()
            .find(|o| o.obligor == ob)
            .is_none_or(|o| o.net_short == 0.0);
        let rw = drc::risk_weight(&r[ob]);
        if no_short && rw >= short_rw {
            let a = bucket_drc(&after, bucket).unwrap();
            let b = bucket_drc(&out, bucket).unwrap_or(0.0);
            prop_assert!(a >= b - 1e-9 * (1.0 + a), "{a} < {b}");
        }

        // Permutation: a deterministic shuffle from the drawn seed.
        let mut shuffled = book.clone();
        let mut s = perm | 1;
        for k in (1..shuffled.len()).rev() {
            s ^= s << 13;
            s ^= s >> 7;
            s ^= s << 17;
            shuffled.swap(k, (s % (k as u64 + 1)) as usize);
        }
        let again = drc::drc_nonsec(&shuffled, &r).unwrap();
        prop_assert_eq!(&again.positions, &out.positions);
        prop_assert!((again.drc - out.drc).abs() <= 1e-12 * (1.0 + out.drc.abs()));

        let c = 2.5;
        let scaled: Vec<Position> = book
            .iter()
            .map(|p| Position { notional: c * p.notional, market_value: c * p.market_value, ..p.clone() })
            .collect();
        let s_out = drc::drc_nonsec(&scaled, &r).unwrap();
        prop_assert!((s_out.drc - c * out.drc).abs() <= 1e-12 * (1.0 + c * out.drc.abs()));
    }
}

// ---- K-8f units ------------------------------------------------------------------------------------

#[test]
fn pla_and_pvalue_details() {
    let out = ima::pla(&[1.0, 2.0, 3.0, 4.0], &[1.0, 2.0, 3.0, 4.0]).unwrap();
    assert_eq!(out.zone, "GREEN");
    assert_eq!(out.spearman, 1.0);
    assert_eq!(out.ks_pvalue_asymptotic, 1.0);
    assert!(!out.regulatory_window);
    assert_eq!(ima::pla(&[1.0, 2.0, 3.0], &[3.0, 2.0, 1.0]).unwrap().spearman, -1.0);
    assert_eq!(ima::doubled_ranks(&[5.0, 1.0, 5.0, 5.0]), [6, 2, 6, 6]);
    assert_eq!(ima::doubled_ranks(&[0.0, -0.0]), [3, 3]);
    assert_eq!(ima::kolmogorov_q(0.0), 1.0);
    assert_eq!(ima::kolmogorov_q(0.01), 1.0);
    assert_eq!(ima::kolmogorov_q(40.0), 0.0);
    // MAR32.42 prints p-values 0.264 and 0.055 for KS 0.09 and 0.12 at 250 days (within 1e-3).
    assert!((ima::pla_ks_pvalue(0.09, 250).unwrap() - 0.264).abs() < 1e-3);
    assert!((ima::pla_ks_pvalue(0.12, 250).unwrap() - 0.055).abs() < 1e-3);
    assert_eq!(ima::pla_ks_pvalue(0.0, 250).unwrap(), 1.0);
    assert_eq!(code(ima::pla_ks_pvalue(1.5, 250)), "E_DOMAIN");
    assert_eq!(code(ima::pla_ks_pvalue(0.5, 0)), "E_DOMAIN");
    assert_eq!(code(ima::pla(&vec![0.0; ima::MAX_PNL + 1], &[0.0])), "E_LIMIT");
    assert_eq!(code(ima::pla(&[0.0], &vec![0.0; ima::MAX_PNL + 1])), "E_LIMIT");
    assert_eq!(code(ima::pla(&[1.0, 2.0, 3.0], &[1.0, 2.0])), "E_INPUT");
    assert_eq!(code(ima::pla(&[1.0, 2.0], &[1.0, 2.0])), "E_DOMAIN");
    let e = ima::pla(&[1.0, 2.0, 3.0], &[1.0, 1.0, 1.0]).unwrap_err();
    assert_eq!((e.code, e.field.as_deref()), ("E_DOMAIN", Some("rtpl")));
    let e = ima::pla(&[1.0, 1.0, 1.0], &[1.0, 2.0, 3.0]).unwrap_err();
    assert_eq!(e.field.as_deref(), Some("hpl"));
    // Zones: AMBER between the thresholds, RED below 0.70 Spearman.
    let h: Vec<f64> = (0..100).map(f64::from).collect();
    let mut r = h.clone();
    r.swap(0, 99);
    assert_eq!(ima::pla(&h, &r).unwrap().zone, "GREEN");
    let rev: Vec<f64> = h.iter().rev().copied().collect();
    assert_eq!(ima::pla(&h, &rev).unwrap().zone, "RED");
    let shifted: Vec<f64> = h.iter().map(|x| x + 10.0).collect();
    let out = ima::pla(&h, &shifted).unwrap();
    assert_eq!((out.ks_count, out.zone), (10, "AMBER"));
}

/// Kolmogorov's series at points where the two KR-305 forms meet agree, and a value printed to
/// many digits (`Q_KS(1) = 0.26999967167735456`, the alternating series, recalled from the standard
/// table of the Kolmogorov distribution) holds.
#[test]
fn kolmogorov_q_series() {
    assert!((ima::kolmogorov_q(1.0) - 0.26999967167735456).abs() < 1e-15);
    let below = ima::kolmogorov_q(1.0 - 1e-12);
    assert!((below - ima::kolmogorov_q(1.0)).abs() < 1e-11);
    for x in [0.3, 0.6, 0.9, 1.2, 2.5, 4.0] {
        let q = ima::kolmogorov_q(x);
        assert!((0.0..=1.0).contains(&q));
    }
    assert!(ima::kolmogorov_q(0.5) > ima::kolmogorov_q(0.9));
}

#[test]
fn liquidity_horizon_details() {
    assert!(ima::fx_pair_specified("EUR/USD"));
    assert!(ima::fx_pair_specified("CHF/JPY")); // cross through USD
    assert!(!ima::fx_pair_specified("ISK/PLN"));
    let lh = |c: Option<&str>, f: Option<&str>, k: Option<&[(f64, i64)]>, m: Option<f64>| {
        ima::liquidity_horizon(c, f, k, m)
    };
    assert_eq!(lh(None, Some("ISK/PLN"), None, None).unwrap().n, 20);
    let r = lh(None, Some("EUR/USD"), None, Some(5.0)).unwrap();
    assert_eq!((r.n, r.table_n, r.rule.as_str()), (10, 10, "fx_pair+maturity"));
    let r = lh(Some("EQ_large_cap"), None, None, Some(200.0)).unwrap();
    assert_eq!(r.rule, "table");
    let r = lh(Some("CS_volatility"), None, None, Some(30.0)).unwrap();
    assert_eq!((r.n, r.table_n, r.rule.as_str()), (40, 120, "table+maturity"));
    let r = lh(None, None, Some(&[(1.0, 120)]), Some(1.0)).unwrap();
    assert_eq!((r.n, r.rule.as_str()), (10, "index+maturity"));
    // FAQ5: weights 0.5 x 10 + 0.5 x 60 = 35, the next horizon is 40.
    let r = lh(None, None, Some(&[(0.5, 10), (0.5, 60)]), None).unwrap();
    assert_eq!((r.n, r.rule.as_str()), (40, "index"));
    let r = lh(None, None, Some(&[(1.0, 120)]), Some(500.0)).unwrap();
    assert_eq!(r.n, 120);
    assert_eq!(code(lh(None, None, None, None)), "E_INPUT");
    assert_eq!(code(lh(Some("IR_other"), Some("EUR/USD"), None, None)), "E_INPUT");
    assert_eq!(code(lh(None, None, Some(&[]), None)), "E_INPUT");
    let big = vec![(0.0, 10); ima::MAX_LIST + 1];
    assert_eq!(code(lh(None, None, Some(&big), None)), "E_LIMIT");
    assert_eq!(code(lh(None, Some("USD/USD"), None, None)), "E_DOMAIN");
    assert_eq!(code(lh(Some("IR_other"), None, None, Some(0.0))), "E_DOMAIN");
    assert_eq!(code(lh(None, None, Some(&[(-0.5, 10), (1.5, 10)]), None)), "E_DOMAIN");
    assert_eq!(code(lh(None, None, Some(&[(1.0, 30)]), None)), "E_DOMAIN");
    assert_eq!(code(lh(None, None, Some(&[(0.5, 10)]), None)), "E_DOMAIN");
    assert_eq!(code(lh(Some("NOT_A_CATEGORY"), None, None, None)), "E_SCHEMA");
    assert_eq!(ima::table_horizon("COM_other_types"), Some(120));
}

#[test]
fn es_details() {
    assert_eq!(ima::horizon_weights(), [1.0, 1.0, 2.0, 2.0, 6.0]);
    let out = ima::es_lh(None, None, Some(&[vec![-1.0, -2.0, -3.0], vec![], vec![], vec![], vec![]]))
        .unwrap();
    assert_eq!((out.mode, out.es), ("pnl", 3.0));
    // A single horizon: ES_1 alone (es_k hand case).
    let out = ima::es_lh(Some(&[1.0, 0.0, 0.0, 0.0, 0.0]), None, None).unwrap();
    assert_eq!((out.mode, out.es), ("es_t", 1.0));
    let out = ima::es_lh(None, Some(&[1.0, 0.0, 0.0, 0.0, 0.0]), None).unwrap();
    assert_eq!(out.mode, "sigma");
    assert_eq!(out.es, ima::normal_es_factor());
    assert_eq!(code(ima::es_lh(None, None, None)), "E_INPUT");
    assert_eq!(code(ima::es_lh(Some(&[1.0; 5]), Some(&[1.0; 5]), None)), "E_INPUT");
    assert_eq!(code(ima::es_lh(Some(&[1.0; 4]), None, None)), "E_INPUT");
    assert_eq!(code(ima::es_lh(None, Some(&[1.0, -1.0, 0.0, 0.0, 0.0]), None)), "E_DOMAIN");
    let gain = vec![vec![1.0, 2.0], vec![], vec![], vec![], vec![]];
    assert_eq!(code(ima::es_lh(None, None, Some(&gain))), "E_DOMAIN");
    let big = vec![vec![0.0; ima::MAX_PNL + 1], vec![], vec![], vec![], vec![]];
    assert_eq!(code(ima::es_lh(None, None, Some(&big))), "E_LIMIT");
    // The historical ES: 40 points at 0.975, w = 1: the largest loss.
    let pnl: Vec<f64> = (0..40).map(|k| -f64::from(k)).collect();
    assert_eq!(ima::historical_es(&pnl, 0.975), 39.0);
    // w = 0 (one point): that loss.
    assert_eq!(ima::historical_es(&[-2.0], 1.0), 2.0);
}

#[test]
fn stressed_imcc_ses_details() {
    let (ratio, floored, es) = ima::es_stressed(10.0, 6.0, 4.0).unwrap();
    assert_eq!((ratio, floored, es), (1.5, false, 15.0));
    let (_, floored, es) = ima::es_stressed(10.0, 2.0, 4.0).unwrap();
    assert_eq!((floored, es), (true, 10.0));
    assert_eq!(code(ima::es_stressed(-1.0, 1.0, 1.0)), "E_DOMAIN");
    assert_eq!(ima::es_stressed(1.0, 1.0, 0.0).unwrap_err().field.as_deref(), Some("es_rc"));

    let cls = |v: &[(&str, [f64; 3])]| -> Vec<(String, [f64; 3])> {
        v.iter().map(|(k, t)| ((*k).to_string(), *t)).collect()
    };
    let out = ima::imcc([1.0, 1.0, 1.0], &cls(&[("CS", [1.0, 1.0, 2.0]), ("IR", [1.0, 2.0, 1.0])]))
        .unwrap();
    assert_eq!(out.classes_floored, ["CS"]);
    let names: Vec<&str> = out.classes.iter().map(|c| c.0).collect();
    assert_eq!(names, ["IR", "CS"]);
    assert_eq!(out.imcc, 0.5 * 1.0 + 0.5 * (2.0 + 1.0));
    assert!(!out.portfolio_floored);
    assert_eq!(code(ima::imcc([1.0; 3], &[])), "E_INPUT");
    assert_eq!(code(ima::imcc([1.0; 3], &cls(&[("XX", [1.0; 3])]))), "E_SCHEMA");
    let e = ima::imcc([1.0; 3], &cls(&[("EQ", [1.0, 1.0, 0.0])])).unwrap_err();
    assert_eq!(e.field.as_deref(), Some("classes.EQ.es_rc"));

    let [a, b, c, total] = ima::ses(&[3.0, 4.0], &[], &[1.0, 1.0]).unwrap();
    assert_eq!((a, b), (5.0, 0.0));
    assert!((c - (1.44f64 + 0.64 * 2.0).sqrt()).abs() < 1e-15);
    assert_eq!(total, a + b + c);
    assert_eq!(code(ima::ses(&[], &[-1.0], &[])), "E_DOMAIN");
    assert_eq!(code(ima::ses(&vec![0.0; ima::MAX_LIST + 1], &[], &[])), "E_LIMIT");
}

fn capital_inputs(desks: Vec<(&str, f64)>) -> CapitalInputs {
    CapitalInputs {
        imcc_prev: 10.0,
        ses_prev: 0.0,
        imcc_avg: 10.0,
        ses_avg: 0.0,
        exceptions: 12,
        drc: 0.0,
        desks: desks.into_iter().map(|(z, s)| (z.to_string(), s)).collect(),
        c_u: 0.0,
        sa_all: 100.0,
        qualitative_addon: 0.25,
    }
}

#[test]
fn capital_details() {
    // No desks: SA_G,A 0, the MAR33.43 formula adds IMA_G,A again (KR-308).
    let out = ima::capital(&capital_inputs(vec![])).unwrap();
    assert_eq!((out.m_c, out.k, out.acr_total), (2.25, 0.0, 45.0));
    // An amber desk: k = 0.5 x amber / SA_G,A, surcharge k x max(0, SA_G,A - IMA_G,A).
    let out = ima::capital(&capital_inputs(vec![("GREEN", 60.0), ("AMBER", 40.0)])).unwrap();
    assert_eq!(out.k, 0.5 * 40.0 / 100.0);
    assert_eq!(out.surcharge, 0.2 * (100.0 - 22.5));
    assert_eq!(out.acr_total, (22.5f64 + 0.2 * 77.5).min(100.0));
    assert_eq!(ima::multiplier(0), 1.5);
    assert_eq!(ima::multiplier(9), 1.92);
    assert_eq!(ima::multiplier(10), 2.0);
    assert_eq!(code(ima::capital(&capital_inputs(vec![("AMBER", 0.0)]))), "E_DOMAIN");
    assert_eq!(code(ima::capital(&capital_inputs(vec![("GREEN", -1.0)]))), "E_DOMAIN");
    let mut x = capital_inputs(vec![]);
    x.exceptions = -1;
    assert_eq!(code(ima::capital(&x)), "E_DOMAIN");
    x.exceptions = 0;
    x.c_u = -1.0;
    assert_eq!(ima::capital(&x).unwrap_err().field.as_deref(), Some("c_u"));
    let big = capital_inputs(vec![("GREEN", 1.0); ima::MAX_LIST + 1]);
    assert_eq!(code(ima::capital(&big)), "E_LIMIT");
}

fn d(y: i32, m: u32, day: u32) -> Date {
    Date::new(y, m, day)
}

#[test]
fn rfet_details() {
    assert_eq!(ima::months_back(d(2024, 2, 29), 12), d(2023, 2, 28));
    assert_eq!(ima::months_back(d(2026, 3, 31), 1), d(2026, 2, 28));
    assert_eq!(ima::months_back(d(2026, 1, 15), 12), d(2025, 1, 15));
    let every: Vec<Date> = (0..365).map(|k| d(2025, 7, 1).add_days(k)).collect();
    let mut obs = every.clone();
    obs.extend([d(2026, 7, 1), d(2020, 1, 1)]);
    let out = ima::rfet(d(2026, 6, 30), &obs).unwrap();
    assert_eq!(out.window_start, d(2025, 7, 1));
    assert_eq!(out.distinct_days, 365);
    assert_eq!(out.first_failing_window_start, None);
    assert!(out.pass && out.crit1 && out.crit2);
    assert_eq!(out.min_window_count, Some(90));
    // 24 days, one per fortnight: every window holds 6 or 7; then nothing for 100 days.
    let sparse: Vec<Date> = (0..10).map(|k| d(2025, 7, 1).add_days(14 * k)).collect();
    let out = ima::rfet(d(2026, 6, 30), &sparse).unwrap();
    assert!(!out.crit1 && !out.crit2 && !out.pass);
    assert!(out.first_failing_window_start.is_some());
    assert!(out.first_failing_window_count.unwrap() < 4);
    let big = vec![d(2026, 1, 1); ima::MAX_LIST + 1];
    assert_eq!(code(ima::rfet(d(2026, 6, 30), &big)), "E_LIMIT");

    assert_eq!(ima::rfet_bucket("A", Some(40.0), None).unwrap(), (9, 35.0, None));
    assert_eq!(ima::rfet_bucket("D", None, Some(0.99)).unwrap(), (5, 0.95, Some(1.0)));
    assert_eq!(ima::rfet_bucket("A", Some(0.0), None).unwrap().0, 1);
    assert_eq!(ima::rfet_bucket("B", Some(4.0), None).unwrap(), (3, 4.0, Some(10.0)));
    assert_eq!(code(ima::rfet_bucket("A", None, Some(0.5))), "E_INPUT");
    assert_eq!(code(ima::rfet_bucket("D", Some(1.0), Some(0.5))), "E_INPUT");
    assert_eq!(code(ima::rfet_bucket("C", Some(-1.0), None)), "E_DOMAIN");
    assert_eq!(code(ima::rfet_bucket("D", None, Some(1.0))), "E_DOMAIN");
    assert_eq!(code(ima::rfet_bucket("E", Some(1.0), None)), "E_SCHEMA");
}

// ---- K-8f properties (A3 of frtb-ima.md, KR-310) ---------------------------------------------------

fn brute_spearman(h: &[f64], r: &[f64]) -> f64 {
    let ranks = |x: &[f64]| -> Vec<f64> {
        x.iter()
            .map(|v| {
                let below = x.iter().filter(|w| *w < v).count() as f64;
                let equal = x.iter().filter(|w| *w == v).count() as f64;
                below + (equal + 1.0) / 2.0
            })
            .collect()
    };
    let (a, b) = (ranks(h), ranks(r));
    let n = a.len() as f64;
    let (ma, mb) = (a.iter().sum::<f64>() / n, b.iter().sum::<f64>() / n);
    let sxy: f64 = a.iter().zip(&b).map(|(x, y)| (x - ma) * (y - mb)).sum();
    let sxx: f64 = a.iter().map(|x| (x - ma) * (x - ma)).sum();
    let syy: f64 = b.iter().map(|y| (y - mb) * (y - mb)).sum();
    sxy / (sxx * syy).sqrt()
}

fn brute_ks(h: &[f64], r: &[f64]) -> usize {
    h.iter()
        .chain(r)
        .map(|x| {
            let a = r.iter().filter(|v| *v <= x).count();
            let b = h.iter().filter(|v| *v <= x).count();
            a.abs_diff(b)
        })
        .max()
        .unwrap_or(0)
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(300))]

    /// Spearman is symmetric and invariant under strictly increasing transforms of either series, KS
    /// under a common one; both equal a brute-force evaluation over every point.
    #[test]
    fn pla_invariances(pairs in prop::collection::vec((-50i32..=50, -50i32..=50), 3..40)) {
        let h: Vec<f64> = pairs.iter().map(|p| f64::from(p.0)).collect();
        let r: Vec<f64> = pairs.iter().map(|p| f64::from(p.1)).collect();
        prop_assume!(h.iter().any(|x| *x != h[0]) && r.iter().any(|x| *x != r[0]));
        let base = ima::pla(&h, &r).unwrap();
        let swapped = ima::pla(&r, &h).unwrap();
        prop_assert!((swapped.spearman - base.spearman).abs() <= 1e-15);
        prop_assert_eq!(swapped.ks_count, base.ks_count);
        let g = |x: f64| (x / 10.0).exp() + 3.0 * x;
        let hg: Vec<f64> = h.iter().map(|x| g(*x)).collect();
        let rg: Vec<f64> = r.iter().map(|x| g(*x)).collect();
        let rc: Vec<f64> = r.iter().map(|x| x * x * x).collect();
        prop_assert!((ima::spearman(&hg, &r).unwrap() - base.spearman).abs() <= 1e-15);
        prop_assert!((ima::spearman(&h, &rc).unwrap() - base.spearman).abs() <= 1e-15);
        prop_assert_eq!(ima::ks_count(&hg, &rg), base.ks_count);
        prop_assert!((brute_spearman(&h, &r) - base.spearman).abs() <= 1e-12);
        prop_assert_eq!(brute_ks(&h, &r), base.ks_count);
    }

    /// KR-310: a single horizon scales by sqrt of its weight; nested horizons (every factor at LH_j)
    /// give E sqrt(LH_j / 10).
    #[test]
    fn es_cascade_scaling(j in 0usize..5, e in 0.0f64..1e6) {
        let w = ima::horizon_weights();
        let mut single = [0.0; 5];
        single[j] = e;
        let es = ima::es_lh(Some(&single), None, None).unwrap().es;
        prop_assert!((es - e * w[j].sqrt()).abs() <= 1e-14 * es.max(1e-300));
        let nested: Vec<f64> = (0..5).map(|k| if k <= j { e } else { 0.0 }).collect();
        let lh = ima::LIQUIDITY_HORIZONS[j] as f64;
        let es = ima::es_lh(Some(&nested), None, None).unwrap().es;
        prop_assert!((es - e * (lh / 10.0).sqrt()).abs() <= 1e-14 * es.max(1e-300));
    }

    /// Stressed ES is never below ES_R,S.
    #[test]
    fn es_stressed_floor(rs in 0.0f64..1e6, fc in 0.0f64..1e6, rc in 1e-6f64..1e6) {
        prop_assert!(ima::es_stressed(rs, fc, rc).unwrap().2 >= rs);
    }

    /// The SES `other` term lies between the root-sum-square and the plain sum; a single entry
    /// equals itself (from 1e-100: below about 1e-154 squares underflow).
    #[test]
    fn ses_bounds(
        a in prop::collection::vec(0.0f64..1e6, 0..20),
        b in prop::collection::vec(0.0f64..1e6, 0..20),
        c in prop::collection::vec(0.0f64..1e6, 0..20),
        x in prop_oneof![Just(0.0), 1e-100f64..1e100],
        which in 0usize..3,
    ) {
        let out = ima::ses(&a, &b, &c).unwrap();
        let rss = c.iter().map(|v| v * v).sum::<f64>().sqrt();
        let total: f64 = c.iter().sum();
        prop_assert!(rss * (1.0 - 1e-12) - 1e-9 <= out[2]);
        prop_assert!(out[2] <= total * (1.0 + 1e-12) + 1e-9);
        let sum = |v: &[f64]| v.iter().sum::<f64>();
        prop_assert!(out[3] <= sum(&a) + sum(&b) + total + 1e-6);
        let mut lists = [vec![], vec![], vec![]];
        lists[which] = vec![x];
        let one = ima::ses(&lists[0], &lists[1], &lists[2]).unwrap()[3];
        prop_assert!((one - x).abs() <= 1e-15 * x);
    }

    /// RFET counts equal a brute-force window count; duplicates count once.
    #[test]
    fn rfet_counting_windows(offsets in prop::collection::vec(-30i64..=400, 0..60)) {
        let as_of = d(2026, 6, 30);
        let obs: Vec<Date> = offsets.iter().map(|k| as_of.add_days(-k)).collect();
        let out = ima::rfet(as_of, &obs).unwrap();
        let start = d(2025, 7, 1);
        let mut inside: Vec<Date> = obs.iter().copied().filter(|x| start <= *x && *x <= as_of).collect();
        inside.sort_unstable();
        inside.dedup();
        prop_assert_eq!(out.distinct_days, inside.len());
        let twice: Vec<Date> = obs.iter().chain(&obs).copied().collect();
        prop_assert_eq!(&ima::rfet(as_of, &twice).unwrap(), &out);
        let mut counts = Vec::new();
        let mut s = start;
        while s.add_days(89) <= as_of {
            counts.push(inside.iter().filter(|x| s <= **x && **x <= s.add_days(89)).count());
            s = s.add_days(1);
        }
        let lowest = counts.iter().copied().min();
        prop_assert_eq!(out.min_window_count, lowest);
        prop_assert_eq!(out.crit1, inside.len() >= 24 && lowest.is_some_and(|l| l >= 4));
        prop_assert_eq!(out.crit2, inside.len() >= 100);
    }
}
