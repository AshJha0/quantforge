use crate::run_case;
use quantforge_core::json::Json;

fn run(op: &str, inputs: &str) -> Json {
    let text =
        format!(r#"{{"schema_version":"1.0","case_id":"k","operation":"{op}","inputs":{inputs}}}"#);
    run_case(text.as_bytes()).0
}

fn code(r: &Json) -> &str {
    r.get("error")
        .and_then(|e| e.get("code"))
        .and_then(Json::as_str)
        .unwrap_or("ok")
}

fn out<'a>(r: &'a Json, k: &str) -> &'a Json {
    r.get("outputs").and_then(|o| o.get(k)).unwrap()
}

const R1: &str = r#"{"sequence":1,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":100}"#;

fn bt(records: &str) -> Json {
    run(
        "core.store.bitemporal_query",
        &format!(
            r#"{{"records":[{records}],"series_id":"A","knowledge_as_of":"2026-04-01T00:00:00Z","valid_at":"2026-02-15T00:00:00Z"}}"#
        ),
    )
}

#[test]
fn bitemporal_found_and_row_shape() {
    let r = bt(R1);
    assert_eq!(out(&r, "status").as_str(), Some("FOUND"));
    let row = out(&r, "row");
    assert_eq!(
        row.to_text(),
        r#"{"sequence":1,"valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":100}"#
    );
    // an offset instant comes back in Z form, and a closed interval shows its end
    let r = bt(
        r#"{"sequence":1,"series_id":"A","valid_from":"2026-01-01T02:00:00+02:00","valid_to":"2026-03-01T00:00:00Z","knowledge_time":"2026-01-02T00:00:00Z","value":{"x":[1,"NaN"]}}"#,
    );
    let row = out(&r, "row");
    assert_eq!(
        row.get("valid_from").and_then(Json::as_str),
        Some("2026-01-01T00:00:00Z")
    );
    assert_eq!(
        row.get("valid_to").and_then(Json::as_str),
        Some("2026-03-01T00:00:00Z")
    );
    // F-38: a token nested inside a value stays a string
    assert_eq!(
        row.get("value").map(Json::to_text).as_deref(),
        Some(r#"{"x":[1,"NaN"]}"#)
    );
}

#[test]
fn bitemporal_withdrawn_and_none_have_null_row() {
    let del = r#"{"sequence":2,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-03T00:00:00Z","value":null,"deleted":true}"#;
    let r = bt(&format!("{R1},{del}"));
    assert_eq!(out(&r, "status").as_str(), Some("WITHDRAWN"));
    assert_eq!(out(&r, "row"), &Json::Null);
    let r = bt("");
    assert_eq!(out(&r, "status").as_str(), Some("NONE"));
    assert_eq!(out(&r, "row"), &Json::Null);
    // `deleted: null` is false; a token in a string field is a string, not a Real
    let r = bt(
        r#"{"sequence":1,"series_id":"NaN","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":1,"deleted":null}"#,
    );
    assert_eq!(out(&r, "status").as_str(), Some("NONE"));
}

#[test]
fn bitemporal_schema_errors() {
    for rec in [
        "1",
        r#"{"sequence":1,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z"}"#,
        r#"{"sequence":1,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","knowledge_time":"2026-01-02T00:00:00Z","value":1}"#,
        r#"{"sequence":0,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":1}"#,
        r#"{"sequence":1,"series_id":"","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":1}"#,
        r#"{"sequence":1.5,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":1}"#,
        r#"{"sequence":1,"series_id":"A","valid_from":"2026-01-01","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":1}"#,
        r#"{"sequence":1,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":"x","knowledge_time":"2026-01-02T00:00:00Z","value":1}"#,
        r#"{"sequence":1,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":null,"value":1}"#,
        r#"{"sequence":1,"series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":1,"deleted":1}"#,
        r#"{"sequence":"NaN","series_id":"A","valid_from":"2026-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2026-01-02T00:00:00Z","value":1}"#,
    ] {
        assert_eq!(code(&bt(rec)), "E_SCHEMA", "{rec}");
    }
    let base = format!(
        r#"{{"records":[{R1}],"series_id":"A","knowledge_as_of":"2026-04-01T00:00:00Z","valid_at":"2026-02-15T00:00:00Z"}}"#
    );
    for (k, bad) in [
        ("\"series_id\":\"A\"", "\"series_id\":1"),
        (
            "\"knowledge_as_of\":\"2026-04-01T00:00:00Z\"",
            "\"knowledge_as_of\":\"x\"",
        ),
        ("\"valid_at\":\"2026-02-15T00:00:00Z\"", "\"valid_at\":null"),
        (&format!("\"records\":[{R1}]"), "\"records\":{}"),
    ] {
        let inputs = base.replace(k, bad);
        assert_eq!(
            code(&run("core.store.bitemporal_query", &inputs)),
            "E_SCHEMA",
            "{bad}"
        );
    }
    // a token in a string field (here both series ids) stays a string
    let inputs = base.replace("\"series_id\":\"A\"", "\"series_id\":\"NaN\"");
    let r = run("core.store.bitemporal_query", &inputs);
    assert_eq!(out(&r, "status").as_str(), Some("FOUND"));
}

#[test]
fn bitemporal_error_order() {
    let nan = R1.replace("\"value\":100", "\"value\":\"NaN\"");
    assert_eq!(code(&bt(&nan)), "E_DOMAIN");
    // structural E_INPUT (log order) comes before the finite rule
    assert_eq!(code(&bt(&format!("{nan},{R1}"))), "E_INPUT");
    // E_SCHEMA comes before everything
    assert_eq!(code(&bt(&format!("{nan},{R1},1"))), "E_SCHEMA");
}

#[test]
fn bitemporal_winner_outside_z_range() {
    let rec = R1.replace("2026-01-01T00:00:00Z", "0001-01-01T00:00:00+01:00");
    let r = bt(&rec);
    assert_eq!(code(&r), "E_DATE_RANGE");
}

#[test]
fn curve_ops() {
    let r = run(
        "curve.bootstrap.par_annual",
        r#"{"quotes":[0.02,0.025,0.03]}"#,
    );
    assert_eq!(
        out(&r, "discount_factors").to_text(),
        "[0.9803921568627451,0.9516977522716404,0.9145993230349208]"
    );
    assert_eq!(
        code(&run("curve.bootstrap.par_annual", r#"{"quotes":[]}"#)),
        "E_INPUT"
    );
    assert_eq!(
        code(&run("curve.bootstrap.par_annual", r#"{"quotes":["NaN"]}"#)),
        "E_DOMAIN"
    );
    assert_eq!(
        code(&run("curve.bootstrap.par_annual", r#"{"quotes":["x"]}"#)),
        "E_SCHEMA"
    );
    let pq = "[0.02,0.025,0.03]";
    let pd = "[0.9803921568627451,0.9516977522716404,0.9145993230349208]";
    let r = run(
        "curve.incremental.update",
        &format!(
            r#"{{"previous_quotes":{pq},"previous_discount_factors":{pd},"new_quotes":[0.02,0.026,0.03]}}"#
        ),
    );
    assert_eq!(out(&r, "first_changed_index"), &Json::Int(1));
    assert_eq!(out(&r, "recomputed"), &Json::Int(2));
    let r = run(
        "curve.incremental.update",
        &format!(
            r#"{{"previous_quotes":{pq},"previous_discount_factors":{pd},"new_quotes":{pq}}}"#
        ),
    );
    assert_eq!(out(&r, "first_changed_index"), &Json::Null);
    assert_eq!(out(&r, "recomputed"), &Json::Int(0));
    // structural E_INPUT before the finite rule's E_DOMAIN
    let r = run(
        "curve.incremental.update",
        &format!(
            r#"{{"previous_quotes":{pq},"previous_discount_factors":{pd},"new_quotes":["NaN"]}}"#
        ),
    );
    assert_eq!(code(&r), "E_INPUT");
    let r = run(
        "curve.incremental.update",
        &format!(r#"{{"previous_quotes":{pq},"previous_discount_factors":{pd}}}"#),
    );
    assert_eq!(code(&r), "E_SCHEMA");
}

#[test]
fn quotes_above_200_are_e_limit_not_a_gate_size() {
    let q = vec!["0.01"; 201].join(",");
    let r = run(
        "curve.bootstrap.par_annual",
        &format!(r#"{{"quotes":[{q}]}}"#),
    );
    assert_eq!(code(&r), "E_LIMIT");
    // a domain error outranks the stage K size (HR-66)
    let q = format!("-2,{}", vec!["0.01"; 200].join(","));
    let r = run(
        "curve.bootstrap.par_annual",
        &format!(r#"{{"quotes":[{q}]}}"#),
    );
    assert_eq!(code(&r), "E_DOMAIN");
}

#[test]
fn trigger_op() {
    let ok =
        r#"{"changes":[1.0,-1.0,1.0,-1.0],"x_ref":100.0,"x_now":105.0,"days_since":1.0,"k":3.0}"#;
    let r = run("calib.trigger.check", ok);
    assert_eq!(out(&r, "fire"), &Json::Bool(true));
    assert_eq!(out(&r, "sigma").as_f64(), Some(1.1547005383792515));
    assert_eq!(
        code(&run(
            "calib.trigger.check",
            &ok.replace("[1.0,-1.0,1.0,-1.0]", "[1.0]")
                .replace("105.0", "\"NaN\"")
        )),
        "E_INPUT"
    );
    assert_eq!(
        code(&run("calib.trigger.check", &ok.replace("105.0", "\"NaN\""))),
        "E_DOMAIN"
    );
    assert_eq!(
        code(&run(
            "calib.trigger.check",
            &ok.replace("\"k\":3.0", "\"k\":\"3\"")
        )),
        "E_SCHEMA"
    );
    let big = vec!["1.0,-1.0"; 50_001].join(",");
    let r = run(
        "calib.trigger.check",
        &ok.replace("[1.0,-1.0,1.0,-1.0]", &format!("[{big}]")),
    );
    assert_eq!(code(&r), "E_LIMIT");
}

#[test]
fn intraday_op() {
    let p = r#"{"notional":1.0,"maturity":1.0,"yield":0.0}"#;
    let r = run(
        "risk.intraday.delta_gamma_bound",
        &format!(r#"{{"positions":[{p}],"shift":0.0}}"#),
    );
    assert_eq!(
        r.get("outputs").map(Json::to_text).as_deref(),
        Some(
            r#"{"estimate_pnl":0.0,"bound":0.0,"label":"latency-aware analytics on simulated data"}"#
        )
    );
    let r = run(
        "risk.intraday.delta_gamma_bound",
        r#"{"positions":[],"shift":"NaN"}"#,
    );
    assert_eq!(code(&r), "E_INPUT");
    let r = run(
        "risk.intraday.delta_gamma_bound",
        &format!(r#"{{"positions":[{p}],"shift":"NaN"}}"#),
    );
    assert_eq!(code(&r), "E_DOMAIN");
    let r = run(
        "risk.intraday.delta_gamma_bound",
        r#"{"positions":[1],"shift":0.0}"#,
    );
    assert_eq!(code(&r), "E_SCHEMA");
    let r = run(
        "risk.intraday.delta_gamma_bound",
        r#"{"positions":[{"notional":1.0,"maturity":1.0}],"shift":0.0}"#,
    );
    assert_eq!(code(&r), "E_SCHEMA");
    let many = vec![p; 100_001].join(",");
    let r = run(
        "risk.intraday.delta_gamma_bound",
        &format!(r#"{{"positions":[{many}],"shift":0.01}}"#),
    );
    assert_eq!(code(&r), "E_LIMIT");
}

#[test]
fn richardson_op() {
    let r = run(
        "num.richardson.check",
        r#"{"values":[10.5,10.125,10.03125],"ratio":2.0,"assumed_order":2.0}"#,
    );
    assert_eq!(
        r.get("outputs").map(Json::to_text).as_deref(),
        Some(r#"{"status":"OK","observed_order":2.0,"extrapolated":10.0}"#)
    );
    let r = run(
        "num.richardson.check",
        r#"{"values":[98464.0,93700.0,96435.0],"ratio":2.0,"assumed_order":2.0}"#,
    );
    assert_eq!(
        r.get("outputs").map(Json::to_text).as_deref(),
        Some(r#"{"status":"NON_MONOTONE","observed_order":null,"extrapolated":null}"#)
    );
    let r = run(
        "num.richardson.check",
        r#"{"values":[10.5,"NaN"],"ratio":2.0,"assumed_order":2.0}"#,
    );
    assert_eq!(code(&r), "E_INPUT");
    let r = run(
        "num.richardson.check",
        r#"{"values":[10.5,10.125,10.03125],"ratio":"Infinity","assumed_order":2.0}"#,
    );
    assert_eq!(code(&r), "E_DOMAIN");
}
