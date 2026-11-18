//! Property: for every order of a random event stream, submitted equals filled plus resting plus
//! cancelled plus rejected (HR-30), fills balance between takers and makers, and the label is always set.
use proptest::prelude::*;
use quantforge_core::json::{Json, obj};
use quantforge_core::lit_matching::{LABEL, run};

const TYPES: [&str; 8] = [
    "LIMIT",
    "MARKET",
    "IOC",
    "FOK",
    "ICEBERG",
    "POST_ONLY",
    "PEG_MID",
    "PEG_PRIMARY",
];

fn event(
    k: usize,
    (op, typ, buy, px, qty, disp, target): (u8, usize, bool, u32, u32, u32, usize),
) -> Json {
    let id = format!("O{k}");
    match op % 6 {
        0 => obj([("op", "CANCEL".into()), ("id", format!("O{target}").into())]),
        1 => obj([
            ("op", "MODIFY".into()),
            ("id", format!("O{target}").into()),
            ("qty", qty.to_string().into()),
        ]),
        _ => {
            let typ = TYPES[typ];
            let mut e = vec![
                ("op".to_string(), Json::from("NEW")),
                ("id".into(), id.into()),
                ("trader".into(), format!("T{}", k % 3).into()),
                ("side".into(), if buy { "BUY" } else { "SELL" }.into()),
                ("type".into(), typ.into()),
                ("qty".into(), qty.to_string().into()),
            ];
            if typ != "MARKET" {
                e.push((
                    "price".into(),
                    format!("{}.{}", 95 + px / 2, (px % 2) * 5).into(),
                ));
            }
            if typ == "ICEBERG" {
                e.push(("display_qty".into(), disp.min(qty).to_string().into()));
            }
            Json::Obj(e)
        }
    }
}

fn num(v: &Json, k: &str) -> f64 {
    v.get(k)
        .and_then(Json::as_str)
        .and_then(|s| s.parse().ok())
        .unwrap_or(f64::NAN)
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(256))]
    #[test]
    fn conservation_holds(raw in prop::collection::vec(
        (0u8..6, 0usize..8, any::<bool>(), 0u32..20, 1u32..12, 1u32..6, 0usize..40), 1..40)) {
        let events: Vec<Json> = raw.iter().enumerate().map(|(k, r)| event(k, *r)).collect();
        let fees = obj([("taker_fee", "0.0003".into()), ("maker_rebate", "0.0001".into())]);
        let out = run("0.5", "1", &events, &fees, None).expect("valid stream");
        prop_assert_eq!(out.get("label").and_then(Json::as_str), Some(LABEL));
        let Some(Json::Obj(cons)) = out.get("conservation") else { panic!("conservation") };
        for (id, c) in cons {
            let parts = num(c, "filled") + num(c, "resting") + num(c, "cancelled") + num(c, "rejected");
            prop_assert!((num(c, "submitted") - parts).abs() < 1e-9, "{id}: {c:?}");
        }
        let fills = out.get("fills").and_then(Json::as_array).expect("fills");
        let traded: f64 = fills.iter().map(|f| num(f, "qty")).sum();
        let filled: f64 = cons.iter().map(|(_, c)| num(c, "filled")).sum();
        prop_assert!((2.0 * traded - filled).abs() < 1e-9);
        // Never crossed after an event: best bid below best ask on the MBP view.
        let mbp = out.get("mbp").expect("mbp");
        let top = |k: &str| mbp.get(k).and_then(Json::as_array).and_then(|a| a.first())
            .and_then(|l| l.as_array()?.first()?.as_str()?.parse::<f64>().ok());
        if let (Some(b), Some(a)) = (top("bids"), top("asks")) {
            prop_assert!(b < a, "crossed {b} {a}");
        }
    }
}
