//! Dark pool and router: paths the goldens do not reach, properties, and the seeded
//! planted-recovery tests of `specifications/10-execution/dark-pool.md` (seeds 20261118, 20261119).
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use quantforge_core::dark_pool::{self, km_tail};
use quantforge_core::json::{Json, parse};
use quantforge_core::rng::Xoshiro;
use quantforge_core::sor::{self, Problem};

fn j(t: &str) -> Json {
    parse(t).unwrap().0
}

const CFG: &str = r#"{"firm_delay":0,"lot_size":"1","p_firm":"1","penalty_events":2,"seed":1,"tick_size":"0.01"}"#;
const BOOK: &str = r#"{"op":"BOOK","bid":"100.00","ask":"100.10"}"#;

fn new(id: &str, side: &str, qty: &str, extra: &str) -> String {
    format!(r#"{{"op":"NEW","id":"{id}","side":"{side}","qty":"{qty}","kind":"FIRM"{extra}}}"#)
}

fn run(cfg: &str, ev: &[String]) -> Json {
    dark_pool::run(
        &j(cfg),
        j(&format!("[{}]", ev.join(","))).as_array().unwrap(),
    )
    .unwrap()
}

fn code(r: quantforge_core::error::Result<Json>) -> &'static str {
    r.err().map_or("ok", |e| e.code)
}

#[test]
fn time_priority_cancel_and_locked_book() {
    let ev = [
        BOOK.to_string(),
        new("B1", "BUY", "10", ""),
        r#"{"op":"CANCEL","id":"B1"}"#.into(),
        new("B2", "BUY", "10", ""),
        new("B3", "BUY", "10", ""),
        new("S1", "SELL", "10", ""),
    ];
    let out = run(CFG, &ev);
    let f = &out.get("fills").unwrap().as_array().unwrap()[0];
    assert_eq!(f.get("buy_id").unwrap().as_str(), Some("B2"));
    let locked = [
        r#"{"op":"BOOK","bid":"100.00","ask":"100.00"}"#.to_string(),
        new("B", "BUY", "5", ""),
        new("S", "SELL", "5", ""),
    ];
    assert_eq!(run(CFG, &locked).get("fills"), Some(&Json::Arr(vec![])));
}

#[test]
fn conservation_fills_plus_resting_equal_submitted() {
    let mut g = Xoshiro::seeded(42, 0);
    for _ in 0..50 {
        let mut ev = vec![BOOK.to_string()];
        let mut total = 0i64;
        for k in 0..12 {
            let q = 1 + (g.next_uniform() * 20.0) as i64;
            total += q;
            let side = if g.next_uniform() < 0.5 {
                "BUY"
            } else {
                "SELL"
            };
            ev.push(new(&format!("O{k}"), side, &q.to_string(), ""));
        }
        let out = run(CFG, &ev);
        let num = |v: &Json, k: &str| v.get(k).unwrap().as_str().unwrap().parse::<i64>().unwrap();
        let filled: i64 = out
            .get("fills")
            .unwrap()
            .as_array()
            .unwrap()
            .iter()
            .map(|f| num(f, "qty"))
            .sum();
        let rest: i64 = out
            .get("resting")
            .unwrap()
            .as_array()
            .unwrap()
            .iter()
            .map(|r| num(r, "open_qty"))
            .sum();
        assert_eq!(2 * filled + rest, total);
    }
}

#[test]
fn conditional_firm_delay_and_seeded_draw() {
    let cfg = CFG.replace(r#""firm_delay":0"#, r#""firm_delay":2"#);
    let ev = [
        BOOK.to_string(),
        new("C", "BUY", "10", "").replace("FIRM", "CONDITIONAL"),
        new("S", "SELL", "10", ""),
        r#"{"op":"BOOK","bid":"100.10","ask":"100.20"}"#.into(),
        r#"{"op":"BOOK","bid":"100.10","ask":"100.20"}"#.into(),
    ];
    let out = run(&cfg, &ev);
    let inv = &out.get("invitations").unwrap().as_array().unwrap()[0];
    assert_eq!(inv.get("event").unwrap().as_int(), Some(5));
    let f = &out.get("fills").unwrap().as_array().unwrap()[0];
    assert_eq!(f.get("price").unwrap().as_str(), Some("100.15"));
    let half = CFG.replace(r#""p_firm":"1""#, r#""p_firm":"0.5""#);
    assert_eq!(run(&half, &ev).to_text(), run(&half, &ev).to_text());
}

#[test]
fn dark_errors() {
    let cfg = j(CFG);
    let bad = |e: &str| code(dark_pool::run(&cfg, j(e).as_array().unwrap()));
    assert_eq!(
        bad(&format!(
            "[{},{}]",
            new("A", "BUY", "1", ""),
            new("A", "BUY", "1", "")
        )),
        "E_INPUT"
    );
    assert_eq!(bad(r#"[{"op":"CANCEL","id":"X"}]"#), "E_INPUT");
    assert_eq!(bad(r#"[{"op":"FOO"}]"#), "E_SCHEMA");
    assert_eq!(
        bad(r#"[{"op":"BOOK","bid":"100.001","ask":"101"}]"#),
        "E_DOMAIN"
    );
    assert_eq!(
        bad(&format!("[{}]", new("A", "BUY", "1.5", ""))),
        "E_DOMAIN"
    );
    let m = |t: &str| code(dark_pool::markouts(j(t).as_array().unwrap()));
    assert_eq!(
        m(r#"[{"side":"X","fill_price":"1","mid_at":{}}]"#),
        "E_SCHEMA"
    );
    assert_eq!(
        m(r#"[{"side":"BUY","fill_price":"0","mid_at":{}}]"#),
        "E_DOMAIN"
    );
    assert_eq!(
        m(r#"[{"side":"BUY","fill_price":"1","mid_at":[]}]"#),
        "E_SCHEMA"
    );
}

#[test]
fn km_tail_uncensored_is_empirical_and_censored_stays_one() {
    let obs: Vec<(i64, i64)> = [0, 1, 1, 2, 3, 5].iter().map(|&s| (100, s)).collect();
    for (s, (t, _)) in km_tail(&obs, 6).iter().enumerate() {
        let emp = obs.iter().filter(|o| o.1 > s as i64).count() as f64 / 6.0;
        assert!((t - emp).abs() < 1e-12);
    }
    assert!(km_tail(&[(5, 5), (7, 7)], 4).iter().all(|t| t.0 == 1.0));
}

#[test]
fn planted_fill_probability_recovered_within_3_se() {
    let mut g = Xoshiro::seeded(20261118, 0);
    let mut obs = Vec::new();
    for _ in 0..20_000 {
        let s = ((g.next_uniform() * 10.0) as i64).min(9);
        let v = 1 + ((g.next_uniform() * 10.0) as i64).min(9);
        obs.push((v, s.min(v)));
    }
    for (k, (est, se)) in km_tail(&obs, 8).iter().enumerate() {
        let s = k as f64 + 1.0;
        assert!((est - (1.0 - 0.1 * s)).abs() <= 3.0 * se, "{s} {est} {se}");
    }
}

#[test]
fn planted_leakage_recovered_within_3_se() {
    let mut g = Xoshiro::seeded(20261119, 0);
    let (alpha, jump) = (0.3, 0.20);
    let cfg = CFG.replace(r#""seed":1"#, r#""seed":20261119"#);
    let mut adverse = Vec::new();
    for _ in 0..4_000 {
        let ours = if g.next_uniform() < 0.5 {
            "BUY"
        } else {
            "SELL"
        };
        let up = g.next_uniform() < 0.5;
        let informed = g.next_uniform() < alpha;
        let contra = if informed {
            if up { "BUY" } else { "SELL" }
        } else if g.next_uniform() < 0.5 {
            "BUY"
        } else {
            "SELL"
        };
        let out = run(
            &cfg,
            &[
                BOOK.into(),
                new("U", ours, "100", ""),
                new("X", contra, "100", ""),
            ],
        );
        let fills = out.get("fills").unwrap().as_array().unwrap();
        let Some(f) = fills.first() else { continue };
        let px = f.get("price").unwrap().as_str().unwrap().to_string();
        let pxf: f64 = px.parse().unwrap();
        let mid = format!("{:.3}", pxf + if up { jump } else { -jump });
        let m = j(&format!(
            r#"[{{"side":"{ours}","fill_price":"{px}","mid_at":{{"1":"{mid}"}}}}]"#
        ));
        let bp = dark_pool::markouts(m.as_array().unwrap()).unwrap();
        let v: f64 = bp.get("fills").unwrap().as_array().unwrap()[0]
            .get("markouts_bp")
            .unwrap()
            .get("1")
            .unwrap()
            .as_str()
            .unwrap()
            .parse()
            .unwrap();
        adverse.push(-v * pxf / 10_000.0);
    }
    let n = adverse.len() as f64;
    let mean = adverse.iter().sum::<f64>() / n;
    let se = (adverse.iter().map(|a| (a - mean).powi(2)).sum::<f64>() / (n - 1.0) / n).sqrt();
    assert!((mean - alpha * jump).abs() <= 3.0 * se, "{mean} {se} {n}");
}

fn sor_case(k: usize) -> Json {
    let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../datasets/golden/stage_h/sor_h.json");
    let doc = j(&std::fs::read_to_string(p).unwrap());
    doc.get("cases").unwrap().as_array().unwrap()[k]
        .get("inputs")
        .unwrap()
        .clone()
}

fn with(inp: &Json, extra: &[(&str, Json)]) -> Json {
    let Json::Obj(mut kv) = inp.clone() else {
        panic!()
    };
    kv.retain(|(k, _)| k != "ranking" && extra.iter().all(|e| e.0 != k));
    kv.extend(extra.iter().map(|(k, v)| (k.to_string(), v.clone())));
    Json::Obj(kv)
}

#[test]
fn closed_form_and_descent_agree_with_sample_average() {
    for k in 0..3 {
        let inp = sor_case(k);
        let cf = with(&inp, &[("method", "CLOSED_FORM".into())]);
        assert_eq!(
            sor::allocate(&cf).unwrap().to_text(),
            sor::allocate(&inp).unwrap().to_text()
        );
    }
    let p = Problem::new(&sor_case(2)).unwrap();
    assert_eq!(p.descent(None).unwrap(), p.sample_average(false).unwrap().0);
}

#[test]
fn stochastic_approx_reaches_the_sample_average_optimum_on_every_golden() {
    for k in 0..5 {
        let inp = with(&sor_case(k), &[]);
        let best = sor::allocate(&inp).unwrap().to_text();
        for n in [1_000, 10_000] {
            let sa = with(
                &inp,
                &[
                    ("method", "STOCHASTIC_APPROX".into()),
                    ("iterations", Json::Int(n)),
                    ("seed", Json::Int(3)),
                ],
            );
            assert_eq!(sor::allocate(&sa).unwrap().to_text(), best, "{k} {n}");
        }
    }
}

#[test]
fn ranking_is_sorted_and_report_se_is_labelled() {
    let inp = sor_case(2);
    let out = sor::allocate(&with(&inp, &[("report_se", Json::Bool(true))])).unwrap();
    assert_eq!(out.get("label").unwrap().as_str(), Some(sor::LABEL));
    assert!(
        out.get("expected_cost_se")
            .unwrap()
            .as_str()
            .unwrap()
            .parse::<f64>()
            .unwrap()
            > 0.0
    );
    let r = sor::allocate(&with(&inp, &[("ranking", Json::Bool(true))])).unwrap();
    let costs: Vec<f64> = r
        .get("ranking")
        .unwrap()
        .as_array()
        .unwrap()
        .iter()
        .map(|e| {
            e.get("expected_cost")
                .unwrap()
                .as_str()
                .unwrap()
                .parse()
                .unwrap()
        })
        .collect();
    assert_eq!(costs.len(), 11 * 11);
    assert!(costs.windows(2).all(|w| w[0] <= w[1]));
}

#[test]
fn sor_errors() {
    let inp = sor_case(2);
    let e = |extra: &[(&str, Json)]| code(sor::allocate(&with(&inp, extra)));
    assert_eq!(e(&[("S", "1.5".into())]), "E_DOMAIN");
    assert_eq!(e(&[("venues", j("[]"))]), "E_INPUT");
    let many = format!(
        "[{}]",
        vec![r#"{"kind":"LIT","Q":"0","r":"0","as":"0"}"#; 65].join(",")
    );
    assert_eq!(e(&[("venues", j(&many))]), "E_LIMIT");
    assert_eq!(e(&[("method", "GREEDY".into())]), "E_SCHEMA");
    assert_eq!(e(&[("lit_samples", j(r#"[["1","2"]]"#))]), "E_INPUT");
    let dark = j(r#"[{"kind":"DARK","r":"0","as":"0","tail":["0.2","0.5"]}]"#);
    assert_eq!(e(&[("venues", dark)]), "E_DOMAIN");
    let only_dark = j(r#"[{"kind":"DARK","r":"0","as":"0","tail":[]}]"#);
    assert_eq!(
        e(&[
            ("method", "CLOSED_FORM".into()),
            ("lit_samples", j("[]")),
            ("venues", only_dark)
        ]),
        "E_DOMAIN"
    );
}

#[test]
fn sor_range_check_is_e_limit() {
    // theta 10^35 times (M + L + under) leaves the HR-57 range: E_LIMIT, as in the Python build.
    let inp = j(
        r#"{"S":"10","theta":"100000000000000000000000000000000000","h":"0.5","f":"0.3",
        "lambda_u":"4","lambda_o":"1","venues":[{"kind":"LIT","Q":"0","r":"0.2","as":"0"}],
        "lit_samples":[["0"],["2"]]}"#,
    );
    assert_eq!(code(sor::allocate(&inp)), "E_LIMIT");
}

#[test]
fn sor_standard_error_matches_python() {
    // Expected text from python/quantforge_core/sor.py allocate (commit 0543de77).
    let inp = j(
        r#"{"S":"4","theta":"0.01","h":"0.5","f":"0.3","lambda_u":"4","lambda_o":"1",
        "report_se":true,"venues":[{"kind":"LIT","Q":"1","r":"0.2","as":"0.05"},
        {"kind":"DARK","r":"0.1","as":"0.3","tail":["0.7","0.33","0.1"]}],
        "lit_samples":[["0"],["2"],["5"],["3"],["7"]]}"#,
    );
    let out = sor::allocate(&inp).unwrap();
    let s = |k: &str| out.get(k).unwrap().as_str().unwrap().to_string();
    assert_eq!(s("M"), "2");
    assert_eq!(s("expected_cost"), "2.14354");
    assert_eq!(s("expected_fill"), "3.746");
    assert_eq!(s("p_underfill"), "0.194");
    assert_eq!(s("expected_cost_se"), "1.077228");
}
