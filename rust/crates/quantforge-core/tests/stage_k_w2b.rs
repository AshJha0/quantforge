//! Stage K wave 2b (K-8g CVA capital, K-8i leverage ratio and large exposures): hand cases from
//! `cva-capital.md` and `leverage-large-exposures.md`, the errors in KR-67 order, and property
//! tests mirroring `python/tests/test_stage_k_w2b.py`.
use proptest::prelude::*;
use quantforge_core::cva::{
    self, Constituent, Counterparty, CreditFactor, Factor, IndexHedge, NettingSet, Sensitivity,
    SingleNameHedge,
};
use quantforge_core::json::{Json, parse};
use quantforge_core::leverage::{
    self as lev, BankingBookExposure, DerivativeSet, LeCounterparty, OffBalance,
    OffBalanceExposure, Protection, Sft, TradingPosition, WrittenCreditDerivative,
};

fn close(a: f64, b: f64) -> bool {
    (a - b).abs() <= 1e-12 * b.abs().max(1.0)
}

fn cp(id: &str, sector: &str, quality: &str, sets: &[(f64, f64)]) -> Counterparty {
    Counterparty {
        id: id.into(),
        sector: sector.into(),
        quality: quality.into(),
        netting_sets: sets
            .iter()
            .map(|&(ead, m)| NettingSet { ead, m, imm: false })
            .collect(),
    }
}

fn hedge(c: &str, relation: &str, m: f64, notional: f64) -> SingleNameHedge {
    SingleNameHedge {
        counterparty: c.into(),
        relation: relation.into(),
        sector: "financials".into(),
        quality: "IG".into(),
        m,
        notional,
    }
}

fn index_hedge(m: f64, notional: f64, weights: &[f64]) -> IndexHedge {
    IndexHedge {
        m,
        notional,
        constituents: weights
            .iter()
            .map(|&weight| Constituent {
                sector: "financials".into(),
                quality: "IG".into(),
                weight,
            })
            .collect(),
    }
}

fn code<T: std::fmt::Debug>(r: quantforge_core::error::Result<T>) -> &'static str {
    r.expect_err("an error").code
}

// --- tables (KR-50) ------------------------------------------------------------------------------

fn table(name: &str) -> Vec<(String, Json)> {
    let path = format!(
        "{}/../../../specifications/tables/stage_k/{name}",
        env!("CARGO_MANIFEST_DIR")
    );
    let text = std::fs::read_to_string(path).expect("table file");
    let (doc, _) = parse(&text).expect("valid JSON");
    doc.get("entries")
        .and_then(Json::as_array)
        .expect("entries")
        .iter()
        .map(|e| {
            (
                e.get("key")
                    .and_then(Json::as_str)
                    .expect("key")
                    .to_string(),
                e.get("value").expect("value").clone(),
            )
        })
        .collect()
}

fn value(t: &[(String, Json)], key: &str) -> f64 {
    let v = &t.iter().find(|(k, _)| k == key).expect("key").1;
    v.as_str()
        .and_then(|s| s.parse().ok())
        .or_else(|| v.as_f64())
        .expect("number")
}

#[test]
fn parameters_match_tables() {
    let m = table("mar50_cva.json");
    // The worked example of cva-capital.md: RW 5%, EAD 1,000,000, M 5, DF(5), alpha 1.4.
    let df = cva::discount_factor(5.0, false).expect("df");
    let r = cva::ba_cva(
        &[cp("C1", "financials", "IG", &[(1e6, 5.0)])],
        "REDUCED",
        &[],
        &[],
    )
    .expect("ba");
    let rw = 0.05;
    let scva = rw * 5.0 * 1e6 * df / value(&m, "ba.alpha");
    assert!(close(r.counterparties[0].scva, scva));
    assert!(close(r.capital, value(&m, "ba.ds") * scva));
    assert!(close(r.rwa, value(&m, "rwa_multiplier") * r.capital));
    let l = table("lev_leverage.json");
    let x = lev::leverage(1.0, &[100.0], &[], &[], &[], &[]).expect("lev");
    assert_eq!(
        x.meets_minimum,
        1.0 >= value(&l, "min_leverage_ratio") * 100.0
    );
    let lx = table("lex_large_exposures.json");
    assert_eq!(value(&lx, "report.top_n"), 20.0);
    assert_eq!(cva::sectors().len(), 8);
    assert_eq!(cva::class_keys()[0], "IR.DELTA");
}

// --- BA-CVA --------------------------------------------------------------------------------------

#[test]
fn discount_factor_cases() {
    // df_k-0001: DF(5) = (1 - exp(-0.25)) / 0.25 in the expm1 form (KR-64).
    assert!(close(
        cva::discount_factor(5.0, false).expect("df"),
        0.8847968677143805
    ));
    assert_eq!(cva::discount_factor(5.0, true).expect("df"), 1.0);
    assert_eq!(code(cva::discount_factor(0.0, false)), "E_DOMAIN");
    assert_eq!(code(cva::discount_factor(f64::NAN, true)), "E_DOMAIN");
    // Small M: DF tends to 1 without cancellation.
    assert!(close(
        cva::discount_factor(1e-12, false).expect("df"),
        1.0 - 0.025e-12
    ));
}

#[test]
fn ba_reduced_worked_example() {
    // cva_k-0001.
    let r = cva::ba_cva(
        &[cp("C1", "financials", "IG", &[(1e6, 5.0)])],
        "REDUCED",
        &[],
        &[],
    )
    .expect("ba");
    assert!(close(r.k_reduced, 157999.44066328224));
    assert!(close(r.capital, 102699.63643113345));
    assert!(r.ih.is_none() && r.k_hedged.is_none() && r.k_full.is_none());
    assert!(r.counterparties[0].snh.is_none());
}

#[test]
fn ba_full_direct_hedge() {
    let cps = [cp("C1", "financials", "IG", &[(1e6, 5.0)])];
    let r = cva::ba_cva(
        &cps,
        "FULL",
        &[hedge("C1", "DIRECT", 5.0, 1e6)],
        &[index_hedge(5.0, 0.0, &[0.5, 0.5])],
    )
    .expect("ba");
    // A direct hedge of the same size removes the whole SCVA: r = 1, HMA = 0.
    let row = &r.counterparties[0];
    let snh = row.snh.expect("snh");
    assert!(close(snh, 1.4 * row.scva));
    assert_eq!(row.hma, Some(0.0));
    assert_eq!(r.ih, Some(0.0));
    let k_hedged = r.k_hedged.expect("hedged");
    let net = row.scva - snh;
    assert!(close(k_hedged, net.abs()));
    assert!(close(
        r.k_full.expect("full"),
        0.25 * r.k_reduced + 0.75 * k_hedged
    ));
    // Other relations and an index hedge.
    for rel in ["LEGAL", "SECTOR_REGION"] {
        let r = cva::ba_cva(
            &cps,
            "FULL",
            &[hedge("C1", rel, 5.0, 1e5)],
            &[index_hedge(3.0, 1e5, &[0.25, 0.75])],
        )
        .expect("ba");
        assert!(r.counterparties[0].hma.expect("hma") > 0.0);
        assert!(r.ih.expect("ih") > 0.0);
    }
}

#[test]
fn ba_errors_in_order() {
    let ok = [cp("C1", "financials", "IG", &[(1.0, 1.0)])];
    let bad_sector = [cp("C1", "SPACE", "IG", &[(1.0, 1.0)])];
    let bad_quality = [cp("C1", "financials", "AA", &[(1.0, 1.0)])];
    assert_eq!(code(cva::ba_cva(&ok, "BASIC", &[], &[])), "E_SCHEMA");
    assert_eq!(
        code(cva::ba_cva(&bad_sector, "REDUCED", &[], &[])),
        "E_SCHEMA"
    );
    assert_eq!(
        code(cva::ba_cva(&bad_quality, "REDUCED", &[], &[])),
        "E_SCHEMA"
    );
    let mut h = hedge("C1", "COUSIN", 1.0, 1.0);
    assert_eq!(
        code(cva::ba_cva(&ok, "FULL", &[h.clone()], &[])),
        "E_SCHEMA"
    );
    h.relation = "DIRECT".into();
    h.sector = "SPACE".into();
    assert_eq!(
        code(cva::ba_cva(&ok, "FULL", &[h.clone()], &[])),
        "E_SCHEMA"
    );
    h.sector = "financials".into();
    h.quality = "AA".into();
    assert_eq!(code(cva::ba_cva(&ok, "FULL", &[h], &[])), "E_SCHEMA");
    let mut ih = index_hedge(1.0, 1.0, &[1.0]);
    ih.constituents[0].sector = "SPACE".into();
    assert_eq!(
        code(cva::ba_cva(&ok, "FULL", &[], &[ih.clone()])),
        "E_SCHEMA"
    );
    ih.constituents[0].sector = "financials".into();
    ih.constituents[0].quality = "AA".into();
    assert_eq!(code(cva::ba_cva(&ok, "FULL", &[], &[ih])), "E_SCHEMA");
    // Structure before domain: a duplicate id with a negative EAD is E_INPUT.
    let dup = [
        cp("C1", "financials", "IG", &[(-1.0, 1.0)]),
        cp("C1", "financials", "IG", &[(1.0, 1.0)]),
    ];
    assert_eq!(code(cva::ba_cva(&dup, "REDUCED", &[], &[])), "E_INPUT");
    let h = hedge("C1", "DIRECT", 1.0, 1.0);
    assert_eq!(
        code(cva::ba_cva(&ok, "REDUCED", std::slice::from_ref(&h), &[])),
        "E_INPUT"
    );
    let ih = index_hedge(1.0, 1.0, &[1.0]);
    assert_eq!(code(cva::ba_cva(&ok, "REDUCED", &[], &[ih])), "E_INPUT");
    assert_eq!(
        code(cva::ba_cva(
            &ok,
            "FULL",
            &[hedge("C9", "DIRECT", 1.0, 1.0)],
            &[]
        )),
        "E_INPUT"
    );
    // Domain.
    let neg = [cp("C1", "financials", "IG", &[(-1.0, 1.0)])];
    assert_eq!(code(cva::ba_cva(&neg, "REDUCED", &[], &[])), "E_DOMAIN");
    let m0 = [cp("C1", "financials", "IG", &[(1.0, 0.0)])];
    assert_eq!(code(cva::ba_cva(&m0, "REDUCED", &[], &[])), "E_DOMAIN");
    for (m, n) in [(0.0, 1.0), (1.0, -1.0)] {
        assert_eq!(
            code(cva::ba_cva(
                &ok,
                "FULL",
                &[hedge("C1", "DIRECT", m, n)],
                &[]
            )),
            "E_DOMAIN"
        );
        assert_eq!(
            code(cva::ba_cva(&ok, "FULL", &[], &[index_hedge(m, n, &[1.0])])),
            "E_DOMAIN"
        );
    }
    for w in [&[-0.5, 1.5][..], &[0.5, 0.4][..]] {
        assert_eq!(
            code(cva::ba_cva(&ok, "FULL", &[], &[index_hedge(1.0, 1.0, w)])),
            "E_DOMAIN"
        );
    }
}

fn cps_strategy() -> impl Strategy<Value = Vec<Counterparty>> {
    let sectors = cva::sectors();
    prop::collection::vec(
        (
            prop::sample::select(sectors),
            prop::sample::select(vec!["IG", "HY_NR"]),
            prop::collection::vec((0.0..1e7_f64, 0.05..30.0_f64), 0..3),
        ),
        1..5,
    )
    .prop_map(|v| {
        v.into_iter()
            .enumerate()
            .map(|(n, (s, q, sets))| cp(&format!("C{n}"), &s, q, &sets))
            .collect()
    })
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(300))]

    #[test]
    fn ba_monotone_in_exposure(cps in cps_strategy(), who in 0usize..4, f in 1.0..10.0_f64) {
        let base = cva::ba_cva(&cps, "REDUCED", &[], &[]).expect("ba");
        let mut up = cps.clone();
        let k = who % up.len();
        for ns in &mut up[k].netting_sets {
            ns.ead *= f;
        }
        let bumped = cva::ba_cva(&up, "REDUCED", &[], &[]).expect("ba");
        prop_assert!(bumped.k_reduced >= base.k_reduced * (1.0 - 1e-12));
    }

    #[test]
    fn reduced_equals_full_without_hedges(cps in cps_strategy()) {
        let r = cva::ba_cva(&cps, "REDUCED", &[], &[]).expect("ba");
        let f = cva::ba_cva(&cps, "FULL", &[], &[]).expect("ba");
        prop_assert!(close(f.k_full.expect("full"), r.k_reduced));
        prop_assert!(close(f.capital, r.capital));
    }

    #[test]
    fn full_never_below_beta_floor(
        cps in cps_strategy(),
        hs in prop::collection::vec((0.1..10.0_f64, 0.0..1e7_f64), 0..3),
    ) {
        let hedges: Vec<_> = hs.iter().map(|&(m, n)| hedge("C0", "DIRECT", m, n)).collect();
        let f = cva::ba_cva(&cps, "FULL", &hedges, &[]).expect("ba");
        prop_assert!(f.k_full.expect("full") >= 0.25 * f.k_reduced * (1.0 - 1e-12));
    }
}

// --- SA-CVA --------------------------------------------------------------------------------------

fn s(bucket: &str, factor: &str, s_cva: f64, s_hdg: f64) -> Sensitivity {
    Sensitivity {
        bucket: bucket.into(),
        factor: Factor::Name(factor.into()),
        s_cva,
        s_hdg,
    }
}

fn credit(bucket: &str, name: &str, tenor: &str, quality: &str, s_cva: f64) -> Sensitivity {
    Sensitivity {
        bucket: bucket.into(),
        factor: Factor::Credit(CreditFactor {
            name: name.into(),
            tenor: tenor.into(),
            quality: quality.into(),
            legal_group: None,
            index: None,
            series: None,
        }),
        s_cva,
        s_hdg: 0.0,
    }
}

fn sa(classes: Vec<(&str, Vec<Sensitivity>)>) -> quantforge_core::error::Result<cva::SaResult> {
    let c: Vec<(String, Vec<Sensitivity>)> = classes
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect();
    cva::sa_cva(&c, "USD", 1.0)
}

#[test]
fn sa_ir_hand_case() {
    // sacva_k-0001: WS = 0.0111 x 1e6 and -0.0074 x 2e6, rho(1Y, 5Y) = 0.72.
    let r = sa(vec![(
        "IR.DELTA",
        vec![s("USD", "1Y", 1e6, 0.0), s("USD", "5Y", -2e6, 0.0)],
    )])
    .expect("sa");
    let (a, b): (f64, f64) = (0.0111 * 1e6, -0.0074 * 2e6);
    let k = (a * a + b * b + 2.0 * 0.72 * a * b).sqrt();
    let bucket = &r.classes[0].1.buckets[0];
    assert!(close(bucket.k_b, k));
    assert!(close(bucket.sum_ws, a + b));
    assert!(close(bucket.s_b, a + b));
    assert!(close(r.total, k));
    assert!(close(r.rwa, 12.5 * k));
    // The hedge term R sum WSH^2 sits under the root.
    let h = sa(vec![("IR.DELTA", vec![s("USD", "1Y", 0.0, 1e6)])]).expect("sa");
    let w: f64 = 0.0111 * 1e6;
    assert!(close(h.total, (w * w + 0.01 * w * w).sqrt()));
}

#[test]
fn sa_every_class() {
    let r = cva::sa_cva(
        &[
            (
                "IR.DELTA".into(),
                vec![
                    s("NOK", "CURVE", 2e5, 0.0),
                    s("NOK", "inflation", -1e5, 0.0),
                    s("EUR", "inflation", 1e5, 0.0),
                    s("EUR", "2Y", 1e5, 0.0),
                ],
            ),
            (
                "IR.VEGA".into(),
                vec![
                    s("EUR", "IR_VOL", 1e3, 0.0),
                    s("EUR", "INFLATION_VOL", 2e3, 0.0),
                ],
            ),
            (
                "FX.DELTA".into(),
                vec![s("GBP", "GBP", 2e5, 0.0), s("JPY", "JPY", -1e5, 0.0)],
            ),
            ("FX.VEGA".into(), vec![s("JPY", "JPY", 1e3, 0.0)]),
            (
                "CCS.DELTA".into(),
                vec![
                    credit("1a", "S1", "1Y", "IG", 2e5),
                    credit("1b", "M1", "1Y", "HY_NR", 1e5),
                    credit("7", "O1", "5Y", "IG", 1e5),
                    Sensitivity {
                        bucket: "8".into(),
                        factor: Factor::Credit(CreditFactor {
                            name: "IX".into(),
                            tenor: "1Y".into(),
                            quality: "IG".into(),
                            legal_group: None,
                            index: Some("CDX".into()),
                            series: Some("41".into()),
                        }),
                        s_cva: 5e4,
                        s_hdg: 0.0,
                    },
                ],
            ),
            (
                "RCS.DELTA".into(),
                vec![
                    s("3", "R3", 1e5, 0.0),
                    s("10", "R10", 4e4, 0.0),
                    s("15", "R15", 1e4, 0.0),
                ],
            ),
            ("RCS.VEGA".into(), vec![s("3", "R3", 1e3, 0.0)]),
            (
                "EQ.DELTA".into(),
                vec![
                    s("1", "E1", 1e5, 0.0),
                    s("12", "E12", 1e5, 0.0),
                    s("13", "E13", 1e5, 0.0),
                ],
            ),
            (
                "EQ.VEGA".into(),
                vec![s("1", "E1", 1e3, 0.0), s("9", "E9", 1e3, 0.0)],
            ),
            (
                "COM.DELTA".into(),
                vec![s("1", "C1", 1e5, 0.0), s("11", "C11", 1e5, 0.0)],
            ),
            ("COM.VEGA".into(), vec![s("2", "C2", 1e3, 0.0)]),
        ],
        "EUR",
        1.25,
    )
    .expect("sa");
    let keys: Vec<&str> = r.classes.iter().map(|(k, _)| k.as_str()).collect();
    assert_eq!(keys, cva::class_keys());
    // CCS 1a and 1b aggregate as bucket 1 (KR-312), buckets ordered by length then text.
    let ccs = &r.classes[4].1;
    let names: Vec<&str> = ccs.buckets.iter().map(|b| b.bucket.as_str()).collect();
    assert_eq!(names, ["1", "7", "8"]);
    let rcs: Vec<&str> = r.classes[5]
        .1
        .buckets
        .iter()
        .map(|b| b.bucket.as_str())
        .collect();
    assert_eq!(rcs, ["3", "10", "15"]);
    // EQ vega: bucket 1 is large cap (0.78), bucket 9 is not (KR-315).
    let eqv = &r.classes[8].1.buckets;
    assert!(close(eqv[0].k_b, 780.0));
    assert!(close(eqv[1].k_b, 1000.0));
    assert!(r.total > 0.0 && r.m_cva == 1.25);
    let sum: f64 = r.classes.iter().map(|(_, c)| c.k).sum();
    assert!(close(r.total, sum));
}

#[test]
fn sa_floored_flag() {
    // Two IR curve and inflation factors of an unspecified currency with opposite WS cannot go
    // below 0; a hedge-free case is never floored. An empty book has no capital.
    let r = sa(vec![]).expect("sa");
    assert_eq!(r.total, 0.0);
    assert_eq!(r.classes.len(), 0);
    let r = sa(vec![("FX.DELTA", vec![s("EUR", "EUR", -1e5, 0.0)])]).expect("sa");
    let b = &r.classes[0].1.buckets[0];
    assert!(!b.floored);
    assert!(close(b.s_b, -b.k_b));
}

#[test]
fn sa_errors_in_order() {
    let one = |k: &str, v: Sensitivity| sa(vec![(k, vec![v])]);
    assert_eq!(code(one("IR.GAMMA", s("USD", "1Y", 1.0, 0.0))), "E_SCHEMA");
    assert_eq!(code(one("XX.DELTA", s("USD", "1Y", 1.0, 0.0))), "E_SCHEMA");
    assert_eq!(code(one("IR.DELTA", s("USD", "7Y", 1.0, 0.0))), "E_SCHEMA");
    assert_eq!(code(one("IR.VEGA", s("USD", "1Y", 1.0, 0.0))), "E_SCHEMA");
    assert_eq!(code(one("CCS.DELTA", s("2", "X", 1.0, 0.0))), "E_SCHEMA");
    assert_eq!(
        code(one("CCS.DELTA", credit("2", "X", "2Y", "IG", 1.0))),
        "E_SCHEMA"
    );
    assert_eq!(
        code(one("CCS.DELTA", credit("2", "X", "1Y", "AAA", 1.0))),
        "E_SCHEMA"
    );
    assert_eq!(
        code(one("EQ.DELTA", credit("2", "X", "1Y", "IG", 1.0))),
        "E_SCHEMA"
    );
    // Schema outranks the CCS.VEGA structural error.
    assert_eq!(
        code(sa(vec![
            ("IR.DELTA", vec![s("USD", "7Y", 1.0, 0.0)]),
            ("CCS.VEGA", vec![credit("2", "X", "1Y", "IG", 1.0)]),
        ])),
        "E_SCHEMA"
    );
    assert_eq!(
        code(one("CCS.VEGA", credit("2", "X", "1Y", "IG", 1.0))),
        "E_INPUT"
    );
    let c = vec![("IR.DELTA".to_string(), vec![s("USD", "1Y", 1.0, 0.0)])];
    assert_eq!(code(cva::sa_cva(&c, "usd", 1.0)), "E_INPUT");
    // Structure before domain: CCS.VEGA with m_cva below 1 is E_INPUT.
    let v = vec![(
        "CCS.VEGA".to_string(),
        vec![credit("2", "X", "1Y", "IG", 1.0)],
    )];
    assert_eq!(code(cva::sa_cva(&v, "USD", 0.9)), "E_INPUT");
    assert_eq!(code(cva::sa_cva(&c, "USD", 0.9)), "E_DOMAIN");
    for (k, v) in [
        ("IR.DELTA", s("5", "1Y", 1.0, 0.0)),
        ("FX.DELTA", s("USD", "USD", 1.0, 0.0)),
        ("IR.DELTA", s("USD", "CURVE", 1.0, 0.0)),
        ("IR.DELTA", s("NOK", "5Y", 1.0, 0.0)),
        ("CCS.DELTA", credit("9", "X", "1Y", "IG", 1.0)),
        ("CCS.DELTA", credit("8", "X", "1Y", "IG", 1.0)),
        ("RCS.DELTA", s("18", "R", 1.0, 0.0)),
        ("COM.VEGA", s("USD", "R", 1.0, 0.0)),
    ] {
        assert_eq!(code(one(k, v)), "E_INPUT", "{k}");
    }
    assert_eq!(
        code(sa(vec![(
            "IR.DELTA",
            vec![s("USD", "1Y", 1.0, 0.0), s("USD", "1Y", 1.0, 0.0)]
        )])),
        "E_INPUT"
    );
    assert_eq!(
        code(sa(vec![(
            "EQ.DELTA",
            vec![s("1", "A", 1.0, 0.0), s("1", "B", 1.0, 0.0)]
        )])),
        "E_INPUT"
    );
    assert_eq!(
        code(sa(vec![(
            "CCS.DELTA",
            vec![
                credit("1a", "X", "1Y", "IG", 1.0),
                credit("1b", "X", "1Y", "IG", 1.0)
            ]
        )])),
        "E_INPUT"
    );
    assert_eq!(
        code(sa(vec![(
            "CCS.DELTA",
            vec![
                credit("2", "X", "1Y", "IG", 1.0),
                credit("2", "X", "5Y", "HY_NR", 1.0)
            ]
        )])),
        "E_INPUT"
    );
}

fn ir_book() -> impl Strategy<Value = Vec<Sensitivity>> {
    prop::collection::vec(
        (
            prop::sample::select(vec!["USD", "EUR", "GBP"]),
            prop::sample::select(vec!["1Y", "2Y", "5Y", "10Y", "30Y", "inflation"]),
            -1e6..1e6_f64,
            -1e6..1e6_f64,
        ),
        1..8,
    )
    .prop_map(|v| {
        let mut seen = std::collections::HashSet::new();
        v.into_iter()
            .filter(|(b, f, _, _)| seen.insert((*b, *f)))
            .map(|(b, f, x, h)| s(b, f, x, h))
            .collect()
    })
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(300))]

    #[test]
    fn sa_bucket_bounds_and_scaling(book in ir_book(), c in 0.001..5.0_f64, neg in any::<bool>()) {
        let c = if neg { -c } else { c };
        let r = sa(vec![("IR.DELTA", book.clone())]).expect("sa");
        for b in &r.classes[0].1.buckets {
            prop_assert!(b.k_b >= 0.0 && b.s_b.abs() <= b.k_b);
        }
        let scaled: Vec<_> = book
            .iter()
            .map(|x| s(&x.bucket, match &x.factor { Factor::Name(n) => n, Factor::Credit(_) => "" },
                       c * x.s_cva, c * x.s_hdg))
            .collect();
        let r2 = sa(vec![("IR.DELTA", scaled)]).expect("sa");
        let want = c.abs() * r.total;
        prop_assert!((r2.total - want).abs() <= 1e-9 * want.max(1.0));
    }

    #[test]
    fn sa_order_invariance(book in ir_book()) {
        let r = sa(vec![("IR.DELTA", book.clone())]).expect("sa");
        let mut rev = book;
        rev.reverse();
        let r2 = sa(vec![("IR.DELTA", rev)]).expect("sa");
        prop_assert!((r2.total - r.total).abs() <= 1e-9 * r.total.max(1.0));
    }
}

#[test]
fn radicands_follow_the_reference_order() {
    assert_eq!(cva::bucket_radicand(&[3.0, 4.0], |_, _| 0.5), 25.0 + 12.0);
    assert_eq!(
        cva::cross_radicand(&[1.0, 2.0], &[1.0, -1.0], |_, _| 1.0),
        3.0
    );
}

// --- leverage ratio ------------------------------------------------------------------------------

#[test]
fn leverage_cre99_example() {
    // lev_k-0001: CRE99 Example 1, alpha (RC + PFE) = 1.4 (60 + 347).
    let d = DerivativeSet {
        v: 60.0,
        pfe: 347.0,
        cvm_received: 0.0,
        cvm_provided: 0.0,
    };
    let r = lev::leverage(100.0, &[], &[d], &[], &[], &[]).expect("lev");
    assert!(close(r.exposure, 569.8));
    assert!(close(r.ratio, 100.0 / 569.8));
    assert!(r.meets_minimum);
}

#[test]
fn leverage_parts() {
    // lev_k-0004/0005: footnote 384 (100 - 10 = 90; a positive fair value does not reduce).
    let w = |fv: f64, off: f64| WrittenCreditDerivative {
        notional: 100.0,
        fair_value: fv,
        purchased_offset: off,
    };
    assert_eq!(lev::written_cd_effective_notional(&w(-10.0, 0.0)), 90.0);
    assert_eq!(lev::written_cd_effective_notional(&w(10.0, 0.0)), 100.0);
    assert_eq!(lev::written_cd_effective_notional(&w(-10.0, 200.0)), 0.0);
    let sft = |mna: bool| Sft {
        gross_assets: 10.0,
        mna,
        exposures: vec![5.0, 1.0],
        collateral: vec![2.0, 3.0],
    };
    assert_eq!(lev::sft_exposure(&sft(true)), 11.0);
    assert_eq!(lev::sft_exposure(&sft(false)), 13.0);
    let ob = |c: &str| OffBalance {
        notional: 100.0,
        ccf_category: c.into(),
    };
    let r = lev::leverage(
        3.0,
        &[50.0],
        &[],
        &[w(-10.0, 0.0)],
        &[sft(true)],
        &[ob("COMMITMENT"), ob("NIF_RUF")],
    )
    .expect("lev");
    assert_eq!(r.off_balance, 90.0);
    assert_eq!(r.derivatives, 90.0);
    assert_eq!(r.written_credit_derivatives, 90.0);
    assert_eq!(r.exposure, 50.0 + 90.0 + 11.0 + 90.0);
    // Binary64 boundary of LEV20.7: 3 against 0.03 x 100.
    let b = lev::leverage(3.0, &[100.0], &[], &[], &[], &[]).expect("lev");
    assert_eq!(b.meets_minimum, 3.0 >= 0.03 * 100.0);
}

#[test]
fn leverage_errors_in_order() {
    let ob = |n: f64, c: &str| OffBalance {
        notional: n,
        ccf_category: c.into(),
    };
    assert_eq!(
        code(lev::leverage(
            10.0,
            &[100.0],
            &[],
            &[],
            &[],
            &[ob(-1.0, "GUARANTEE")]
        )),
        "E_SCHEMA"
    );
    let bad_sft = Sft {
        gross_assets: 1.0,
        mna: true,
        exposures: vec![1.0, 2.0],
        collateral: vec![1.0],
    };
    assert_eq!(
        code(lev::leverage(0.0, &[100.0], &[], &[], &[bad_sft], &[])),
        "E_INPUT"
    );
    assert_eq!(
        code(lev::leverage(0.0, &[100.0], &[], &[], &[], &[])),
        "E_DOMAIN"
    );
    assert_eq!(
        code(lev::leverage(1.0, &[], &[], &[], &[], &[])),
        "E_DOMAIN"
    );
    assert_eq!(
        code(lev::leverage(1.0, &[-1.0], &[], &[], &[], &[])),
        "E_DOMAIN"
    );
    let d = |r: f64, p: f64, pfe: f64| DerivativeSet {
        v: 1.0,
        pfe,
        cvm_received: r,
        cvm_provided: p,
    };
    for x in [d(-1.0, 0.0, 1.0), d(0.0, -1.0, 1.0), d(0.0, 0.0, -1.0)] {
        assert_eq!(
            code(lev::leverage(1.0, &[1.0], &[x], &[], &[], &[])),
            "E_DOMAIN"
        );
    }
    let w = |n: f64, o: f64| WrittenCreditDerivative {
        notional: n,
        fair_value: 0.0,
        purchased_offset: o,
    };
    for x in [w(-1.0, 0.0), w(1.0, -1.0)] {
        assert_eq!(
            code(lev::leverage(1.0, &[1.0], &[], &[x], &[], &[])),
            "E_DOMAIN"
        );
    }
    let s = |g: f64, e: f64, c: f64| Sft {
        gross_assets: g,
        mna: false,
        exposures: vec![e],
        collateral: vec![c],
    };
    for x in [s(-1.0, 1.0, 1.0), s(1.0, -1.0, 1.0), s(1.0, 1.0, -1.0)] {
        assert_eq!(
            code(lev::leverage(1.0, &[1.0], &[], &[], &[x], &[])),
            "E_DOMAIN"
        );
    }
    assert_eq!(
        code(lev::leverage(
            1.0,
            &[1.0],
            &[],
            &[],
            &[],
            &[ob(-1.0, "COMMITMENT")]
        )),
        "E_DOMAIN"
    );
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(300))]

    #[test]
    fn leverage_monotone(on in prop::collection::vec(0.0..1e6_f64, 1..4), bump in 0.0..1e6_f64) {
        let r = lev::leverage(10.0, &on, &[], &[], &[], &[]).expect("lev");
        prop_assert!(r.exposure >= 0.0 && r.ratio > 0.0);
        let mut more = on.clone();
        more.push(bump);
        let r2 = lev::leverage(10.0, &more, &[], &[], &[], &[]).expect("lev");
        prop_assert!(r2.exposure >= r.exposure);
        prop_assert!(r2.ratio <= r.ratio);
    }
}

// --- large exposures -----------------------------------------------------------------------------

fn lc(id: &str, group: Option<&str>, gsib: bool, exempt: bool) -> LeCounterparty {
    LeCounterparty {
        id: id.into(),
        group: group.map(Into::into),
        gsib,
        exempt,
    }
}

fn bb(c: &str, v: f64) -> BankingBookExposure {
    BankingBookExposure {
        counterparty: c.into(),
        value: v,
    }
}

fn tp(id: &str, c: &str, sen: &str, n: f64, mv: f64) -> TradingPosition {
    TradingPosition {
        id: id.into(),
        counterparty: c.into(),
        seniority: sen.into(),
        notional: n,
        market_value: mv,
    }
}

#[test]
fn large_exposures_mixed_gsib_group() {
    // lex_k-0010: GM has one G-SIB member and takes 15% (KR-324, any member).
    let cps = [
        lc("M1", Some("GM"), true, false),
        lc("M2", Some("GM"), false, false),
        lc("N1", Some("GN"), false, false),
        lc("N2", Some("GN"), false, false),
    ];
    let book: Vec<_> = ["M1", "M2", "N1", "N2"]
        .iter()
        .map(|c| bb(c, 100.0))
        .collect();
    let r = lev::large_exposures(1000.0, &cps, &book, &[], &[], &[], true).expect("lex");
    assert_eq!(r.groups[0].limit, 150.0);
    assert!(r.groups[0].breach);
    assert_eq!(r.groups[1].limit, 250.0);
    assert!(!r.groups[1].breach);
    assert_eq!(r.report, ["GM", "GN"]);
    // Without the bank flag both groups take 25%.
    let r = lev::large_exposures(1000.0, &cps, &book, &[], &[], &[], false).expect("lex");
    assert_eq!(r.groups[0].limit, 250.0);
}

#[test]
fn large_exposures_parts() {
    let cps = [
        lc("A", None, false, false),
        lc("B", None, false, true),
        lc("C", Some("G"), false, false),
    ];
    let obs = [OffBalanceExposure {
        counterparty: "A".into(),
        notional: 100.0,
        ccf: 0.0,
    }];
    let crm = [Protection {
        counterparty: "A".into(),
        provider: "B".into(),
        protected: 5.0,
    }];
    let tb = [
        tp("p1", "A", "SENIOR", 10.0, 9.0),
        tp("p2", "A", "SENIOR", -10.0, -4.0),
        tp("p3", "C", "EQUITY", -10.0, -4.0),
    ];
    let r =
        lev::large_exposures(100.0, &cps, &[bb("A", 10.0)], &obs, &crm, &tb, false).expect("lex");
    let a = &r.counterparties[0];
    assert_eq!(a.off_balance, 10.0); // CCF floored at 10% (LEX30.6)
    assert_eq!(a.trading_book_net_long, 5.0);
    assert_eq!(a.exposure, 10.0 + 10.0 + 5.0 - 5.0);
    assert_eq!(r.counterparties[1].received, 5.0);
    assert_eq!(r.counterparties[2].trading_book_net_short, -4.0);
    // B is exempt: counted 0, so no breach even when large.
    let b = r.groups.iter().find(|g| g.group == "B").expect("B");
    assert!(b.exempt && !b.breach);
    assert_eq!(r.groups.len(), 3);
}

#[test]
fn large_exposures_report_top_n() {
    let cps: Vec<_> = (0..25)
        .map(|n| lc(&format!("C{n:02}"), None, false, false))
        .collect();
    let book: Vec<_> = (0..25)
        .map(|n| bb(&format!("C{n:02}"), f64::from(n)))
        .collect();
    let r = lev::large_exposures(1e6, &cps, &book, &[], &[], &[], false).expect("lex");
    assert_eq!(r.report.len(), 20);
    assert_eq!(r.report[0], "C24");
}

#[test]
fn large_exposures_errors_in_order() {
    let two = [lc("A", None, false, false), lc("B", None, false, false)];
    let le = |cps: &[LeCounterparty],
              b: &[BankingBookExposure],
              o: &[OffBalanceExposure],
              c: &[Protection],
              t: &[TradingPosition],
              tier1: f64| lev::large_exposures(tier1, cps, b, o, c, t, false);
    assert_eq!(
        code(le(
            &two,
            &[],
            &[],
            &[],
            &[tp("p", "A", "SUPER", 1.0, 1.0)],
            1.0
        )),
        "E_SCHEMA"
    );
    let dup = [
        lc("A", Some("G1"), false, false),
        lc("A", Some("G2"), false, false),
    ];
    assert_eq!(code(le(&dup, &[], &[], &[], &[], 1.0)), "E_INPUT");
    let clash = [
        lc("A", Some("B"), false, false),
        lc("B", None, false, false),
    ];
    assert_eq!(code(le(&clash, &[], &[], &[], &[], 1.0)), "E_INPUT");
    assert_eq!(
        code(le(&two, &[bb("Q", 1.0)], &[], &[], &[], 0.0)),
        "E_INPUT"
    );
    let p = |c: &str, pr: &str, x: f64| Protection {
        counterparty: c.into(),
        provider: pr.into(),
        protected: x,
    };
    assert_eq!(
        code(le(&two, &[], &[], &[p("A", "A", 1.0)], &[], 1.0)),
        "E_INPUT"
    );
    let tb = [
        tp("p", "A", "SENIOR", 1.0, 1.0),
        tp("p", "B", "SENIOR", 1.0, 1.0),
    ];
    assert_eq!(code(le(&two, &[], &[], &[], &tb, 1.0)), "E_INPUT");
    assert_eq!(code(le(&two, &[], &[], &[], &[], 0.0)), "E_DOMAIN");
    assert_eq!(
        code(le(&two, &[bb("A", -1.0)], &[], &[], &[], 1.0)),
        "E_DOMAIN"
    );
    let o = |n: f64, ccf: f64| OffBalanceExposure {
        counterparty: "A".into(),
        notional: n,
        ccf,
    };
    for x in [o(-1.0, 0.5), o(1.0, -0.1), o(1.0, 1.5)] {
        assert_eq!(code(le(&two, &[], &[x], &[], &[], 1.0)), "E_DOMAIN");
    }
    assert_eq!(
        code(le(&two, &[], &[], &[p("A", "B", -1.0)], &[], 1.0)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(le(
            &two,
            &[bb("A", 10.0)],
            &[],
            &[p("A", "B", 11.0)],
            &[],
            1.0
        )),
        "E_DOMAIN"
    );
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(300))]

    #[test]
    fn group_is_sum_of_members(values in prop::collection::vec((0usize..3, 0.0..1e6_f64), 1..8)) {
        let cps: Vec<_> = values
            .iter()
            .enumerate()
            .map(|(n, (g, _))| lc(&format!("C{n}"), Some(&format!("G{g}")), false, false))
            .collect();
        let book: Vec<_> = values
            .iter()
            .enumerate()
            .map(|(n, (_, v))| bb(&format!("C{n}"), *v))
            .collect();
        let r = lev::large_exposures(1e6, &cps, &book, &[], &[], &[], false).expect("lex");
        for g in &r.groups {
            let sum: f64 = r
                .counterparties
                .iter()
                .filter(|c| g.members.contains(&c.id))
                .map(|c| c.exposure)
                .sum();
            prop_assert!((g.exposure - sum).abs() <= 1e-9 * sum.max(1.0));
        }
    }

    #[test]
    fn protection_moves_exposure(a in 1.0..1e6_f64, b in 0.0..1e6_f64, frac in 0.0..1.0_f64) {
        let cps = [lc("A", None, false, false), lc("B", None, false, false)];
        let book = [bb("A", a), bb("B", b)];
        let base = lev::large_exposures(1e6, &cps, &book, &[], &[], &[], false).expect("lex");
        let crm = [Protection { counterparty: "A".into(), provider: "B".into(), protected: frac * a }];
        let r = lev::large_exposures(1e6, &cps, &book, &[], &crm, &[], false).expect("lex");
        let total = |x: &lev::LargeExposuresResult| x.counterparties.iter().map(|c| c.exposure).sum::<f64>();
        prop_assert!((total(&r) - total(&base)).abs() <= 1e-9 * total(&base).max(1.0));
        prop_assert!(r.counterparties[0].exposure <= base.counterparties[0].exposure);
    }
}
