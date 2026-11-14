//! Every stage J `research.*` and wave 2 `risk.*` CLI handler through `run_case`, with the
//! handler-level error paths (unknown enum values and missing inputs are `E_SCHEMA`, a partial Gaussian emission is `E_INPUT`).

use super::*;

fn run(op: &str, inputs: &str) -> (bool, Json) {
    let doc =
        format!(r#"{{"schema_version":"1.0","case_id":"c","operation":"{op}","inputs":{inputs}}}"#);
    let (r, ok) = run_case(doc.as_bytes());
    (ok, r)
}

fn ok(op: &str, inputs: &str, keys: &[&str]) {
    let (good, r) = run(op, inputs);
    assert!(good, "{op}: {}", r.to_text());
    let out = r
        .get("outputs")
        .unwrap_or_else(|| panic!("{op}: no outputs {}", r.to_text()));
    for k in keys {
        assert!(
            out.get(k).is_some(),
            "{op}: missing {k} in {}",
            out.to_text()
        );
    }
}

fn err(op: &str, inputs: &str, want: &str) {
    let (good, r) = run(op, inputs);
    assert!(!good, "{op} should fail: {}", r.to_text());
    let code = r
        .get("error")
        .and_then(|e| e.get("code"))
        .and_then(Json::as_str);
    assert_eq!(code, Some(want), "{op}: {}", r.to_text());
}

const COV: &str = "[[0.04,0.01],[0.01,0.09]]";

#[test]
fn backtest_engines_and_costs() {
    let base = r#""prices":[100,101,102,101,103],"targets":[0,1,1,-1,0],"half_spread_bps":2,"commission_per_unit":0.01,"fixed_per_trade":1,"multiplier":10,"lag":1"#;
    let keys = [
        "positions",
        "pnl_net",
        "equity",
        "turnover",
        "trade_count",
        "max_drawdown",
    ];
    for engine in ["", r#","engine":"EVENT""#, r#","engine":"VECTOR""#] {
        ok(
            "research.backtest.run",
            &format!("{{{base}{engine}}}"),
            &keys,
        );
    }
    err(
        "research.backtest.run",
        &format!(r#"{{{base},"engine":"TICK"}}"#),
        "E_SCHEMA",
    );
}

#[test]
fn cross_validation_ops() {
    ok(
        "research.cv.purged_kfold",
        r#"{"t0":[0,1,2,3,4,5],"t1":[0.5,1.5,2.5,3.5,4.5,5.5],"n_splits":3,"embargo_pct":0.1}"#,
        &["folds", "embargo_count"],
    );
    ok(
        "research.cv.cpcv_paths",
        r#"{"n_groups":6,"n_test_groups":2}"#,
        &["n_splits", "n_paths"],
    );
}

#[test]
fn regime_ops_and_the_partial_gaussian_error() {
    let base = r#""initial":[0.5,0.5],"transition":[[0.9,0.1],[0.2,0.8]]"#;
    ok(
        "research.regime.viterbi",
        &format!(r#"{{{base},"emission":[[0.9,0.1],[0.8,0.2],[0.1,0.9]]}}"#),
        &["states", "log_probability"],
    );
    ok(
        "research.regime.viterbi",
        &format!(r#"{{{base},"observations":[-1.0,-0.8,1.1,0.9],"means":[-1,1],"sds":[0.5,0.5]}}"#),
        &["states", "log_probability"],
    );
    err(
        "research.regime.viterbi",
        &format!(r#"{{{base},"observations":[-1.0,1.0],"means":[-1,1]}}"#),
        "E_INPUT",
    );
    let y = "[-1.1,-0.9,-1.2,-0.8,1.0,1.2,0.9,1.1,-1.0,-0.95,1.05,0.85]";
    ok(
        "research.regime.baum_welch",
        &format!(
            r#"{{{base},"observations":{y},"means":[-0.5,0.5],"sds":[1,1],"tolerance":1e-8,"max_iterations":200}}"#
        ),
        &[
            "initial",
            "transition",
            "means",
            "sds",
            "log_likelihood",
            "iterations",
            "converged",
        ],
    );
}

#[test]
fn portfolio_and_estimation_ops() {
    ok(
        "research.portfolio.mean_variance",
        &format!(
            r#"{{"expected_returns":[0.08,0.05],"covariance":{COV},"risk_aversion":3,"lower":[0,0],"upper":[1,1]}}"#
        ),
        &[
            "weights",
            "expected_return",
            "volatility",
            "objective",
            "at_bound",
        ],
    );
    ok(
        "research.portfolio.mean_variance",
        &format!(r#"{{"expected_returns":[0.08,0.05],"covariance":{COV},"risk_aversion":3}}"#),
        &["weights"],
    );
    for budgets in ["", r#","budgets":[0.6,0.4]"#] {
        ok(
            "research.portfolio.risk_parity",
            &format!(r#"{{"covariance":{COV}{budgets}}}"#),
            &["weights", "volatility", "contributions"],
        );
    }
    ok(
        "research.estimate.ledoit_wolf",
        r#"{"returns":[[0.01,0.02],[-0.01,0.0],[0.02,0.01],[0.0,-0.02],[0.015,0.005],[-0.005,0.01]]}"#,
        &["covariance", "shrinkage", "mu"],
    );
    ok(
        "research.estimate.black_litterman",
        &format!(
            r#"{{"covariance":{COV},"prior_returns":[0.05,0.07],"pick":[[1,-1]],"views":[0.01],"view_covariance":[[0.001]],"tau":0.05}}"#
        ),
        &[
            "posterior_returns",
            "posterior_covariance",
            "predictive_covariance",
        ],
    );
}

#[test]
fn statistics_ops_and_the_unknown_metric_error() {
    ok(
        "research.stats.psr",
        r#"{"sr":0.1,"n_obs":252,"skew":-0.2,"kurtosis":4,"sr_benchmark":0.0}"#,
        &["z", "psr"],
    );
    ok(
        "research.stats.dsr",
        r#"{"sr":0.1,"n_obs":252,"n_trials":10,"sr_variance":0.01}"#,
        &["sr0", "z", "dsr"],
    );
    ok(
        "research.stats.power",
        r#"{"years":5}"#,
        &["z_sum", "mds", "se_at_zero"],
    );
    ok(
        "research.stats.power",
        r#"{"years":5,"alpha":0.05,"power":0.8,"sr_target":1.0}"#,
        &["years_required", "se_at_target"],
    );
    let perf =
        "[[0.1,0.2],[0.3,-0.1],[0.0,0.1],[0.2,0.0],[-0.1,0.3],[0.05,0.15],[0.25,-0.05],[0.1,0.1]]";
    for metric in ["", r#","metric":"SHARPE""#, r#","metric":"MEAN""#] {
        ok(
            "research.stats.pbo",
            &format!(r#"{{"performance":{perf},"n_partitions":4{metric}}}"#),
            &["pbo", "logits", "n_combinations"],
        );
    }
    err(
        "research.stats.pbo",
        &format!(r#"{{"performance":{perf},"n_partitions":4,"metric":"SORTINO"}}"#),
        "E_SCHEMA",
    );
}

#[test]
fn risk_wave2_ops_and_their_errors() {
    ok(
        "risk.contrib.euler",
        &format!(r#"{{"weights":[0.5,0.5],"covariance":{COV}}}"#),
        &["volatility", "marginal", "contributions", "shares"],
    );
    err("risk.contrib.euler", r#"{"weights":[0.5,0.5]}"#, "E_SCHEMA");
    let base = r#""losses":[1.0,3.0,0.5,4.0],"var":[2.0,2.0,2.0,2.0],"es":[2.5,2.5,2.5,2.5]"#;
    ok(
        "risk.backtest.es_z2",
        &format!(r#"{{{base},"alpha":0.025}}"#),
        &["z2", "exceptions", "expected_exceptions"],
    );
    err(
        "risk.backtest.es_z2",
        &format!(r#"{{{base},"alpha":1.5}}"#),
        "E_DOMAIN",
    );
    err("risk.backtest.es_z2", &format!("{{{base}}}"), "E_SCHEMA");
}

/// Kills `half_spread < 0.0` -> `== 0.0` in `option_hedge_lots`: a negative half-spread is a
/// domain error and zero is allowed (CI mutation sample, 2026-11-14).
#[test]
fn option_hedge_lots_rejects_a_negative_half_spread_and_accepts_zero() {
    let base = r#"{"spot":100.0,"rate":0.03,"dividend_yield":0.01,"volatility":0.22,"portfolio":[{"instrument":"CALL","strike":105.0,"expiry_years":0.5,"quantity":-1500.0}],"hedges":[{"instrument":"UNDERLYING","lot_size":100.0,"half_spread":HS}],"targets":["DELTA"],"max_lots":1000}"#;
    err(
        "usecase.option_hedge_lots",
        &base.replace("HS", "-0.01"),
        "E_DOMAIN",
    );
    let (good, r) = run("usecase.option_hedge_lots", &base.replace("HS", "0.0"));
    assert!(good, "{}", r.to_text());
}
