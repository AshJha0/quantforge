//! Rulings J-20 to J-22 (`specifications/stage-j-rulings-w1.md`) through `run_case`.

use super::*;

fn run(op: &str, inputs: &str) -> (bool, String) {
    let doc =
        format!(r#"{{"schema_version":"1.0","case_id":"c","operation":"{op}","inputs":{inputs}}}"#);
    let (r, ok) = run_case(doc.as_bytes());
    let code = r
        .get("error")
        .and_then(|e| e.get("code"))
        .and_then(Json::as_str)
        .unwrap_or_default()
        .to_owned();
    (ok, code)
}

fn backtest(n: usize) -> (bool, String) {
    let prices = vec!["100.0"; n].join(",");
    let targets = vec!["0.0"; n].join(",");
    run(
        "research.backtest.run",
        &format!(r#"{{"prices":[{prices}],"targets":[{targets}]}}"#),
    )
}

#[test]
fn j20_page_limit_replaces_general_array_limit() {
    assert_eq!(backtest(100_001), (true, String::new()));
    assert_eq!(backtest(1_000_001), (false, "E_LIMIT".to_owned()));
}

#[test]
fn j20_pbo_rows_judged_by_cell_cap() {
    let rows = vec!["[0.0,1.0]"; 100_002].join(",");
    let (_, code) = run(
        "research.stats.pbo",
        &format!(r#"{{"performance":[{rows}],"n_partitions":2}}"#),
    );
    assert_ne!(code, "E_LIMIT");
}

#[test]
fn j21_power_arguments_outside_unit_interval_are_domain() {
    for (alpha, power) in [(0.0, 0.8), (-0.1, 0.8), (0.05, 1.0), (0.05, 1.5)] {
        let (_, code) = run(
            "research.stats.power",
            &format!(r#"{{"years":5.0,"alpha":{alpha:?},"power":{power:?}}}"#),
        );
        assert_eq!(code, "E_DOMAIN", "{alpha} {power}");
    }
}

#[test]
fn j22_empty_viterbi_input_is_input_error() {
    let base = r#""initial":[0.5,0.5],"transition":[[0.9,0.1],[0.1,0.9]]"#;
    assert_eq!(
        run(
            "research.regime.viterbi",
            &format!(r#"{{{base},"emission":[]}}"#)
        )
        .1,
        "E_INPUT"
    );
    let gauss = format!(r#"{{{base},"observations":[],"means":[0.0,1.0],"sds":[1.0,1.0]}}"#);
    assert_eq!(run("research.regime.viterbi", &gauss).1, "E_INPUT");
}
