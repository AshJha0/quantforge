//! Replays the core, R2 and stage B to I goldens through `run_case` in process, judged the way
//! `conformance/runner/runner.py` judges them, with the classes of
//! `conformance/tolerances/policy.yaml`. This puts the operation adapters and the stage C modules
//! under `cargo test`, not only under the external runner.

use super::run_case;
use quantforge_core::json::{Json, obj, parse};

/// `(absolute, relative)`, or `None` for an exact class. Classes judged only by a per-case limit
/// or by extra checks (`calibration`, `monte_carlo`) have no numeric default.
#[allow(clippy::option_option)]
fn class(name: &str) -> Option<Option<(f64, f64)>> {
    Some(match name {
        "date_and_convention" | "bit_exact" => None,
        "simple_analytic" => Some((1e-12, 1e-10)),
        "interpolation" | "aad_sensitivity" => Some((1e-10, 1e-8)),
        "root_finding" => Some((1e-10, 1e-10)),
        "quadrature" | "statistics" => Some((1e-11, 1e-10)),
        "numerical_scheme" => Some((1e-8, 1e-8)),
        "fourier" | "common_rng" => Some((1e-9, 1e-9)),
        "likelihood_sum" => Some((1e-9, 1e-10)),
        "jacobian" => Some((1e-9, 1e-6)),
        "jacobian_piecewise" => Some((1e-7, 1e-5)),
        "standard_error" => Some((1e-15, 1e-5)),
        "ift_jacobian" => Some((1e-11, 1e-9)),
        "calibration" | "monte_carlo" => Some((f64::NAN, f64::NAN)),
        _ => return None,
    })
}

fn num(v: Option<&Json>) -> Option<f64> {
    v.and_then(Json::as_f64)
}

fn compare(a: &Json, e: &Json, tol: Option<(f64, f64)>, path: &str, out: &mut Vec<String>) {
    match (a, e) {
        (Json::Obj(x), Json::Obj(y)) => {
            let mut kx: Vec<&str> = x.iter().map(|p| p.0.as_str()).collect();
            let mut ky: Vec<&str> = y.iter().map(|p| p.0.as_str()).collect();
            kx.sort_unstable();
            ky.sort_unstable();
            if kx != ky {
                return out.push(format!("{path}: keys {kx:?} vs {ky:?}"));
            }
            for (k, ev) in y {
                compare(a.get(k).unwrap(), ev, tol, &format!("{path}.{k}"), out);
            }
        }
        (Json::Arr(x), Json::Arr(y)) if x.len() == y.len() => {
            for (i, (av, ev)) in x.iter().zip(y).enumerate() {
                compare(av, ev, tol, &format!("{path}[{i}]"), out);
            }
        }
        (_, Json::Int(_) | Json::Num(_)) => {
            let (Some(x), Some(y)) = (a.as_f64(), e.as_f64()) else {
                return out.push(format!("{path}: {} is not a number", a.to_text()));
            };
            let ok = match tol {
                None => x == y,
                Some((ab, re)) if ab.is_nan() || re.is_nan() => {
                    return out.push(format!("{path}: class needs a per-case limit"));
                }
                Some((ab, re)) => x.is_finite() && (x - y).abs() <= ab + re * x.abs().max(y.abs()),
            };
            if !ok {
                out.push(format!("{path}: {x:?} vs {y:?}"));
            }
        }
        _ if a == e => {}
        _ => out.push(format!("{path}: {} != {}", a.to_text(), e.to_text())),
    }
}

/// Structural zeros (rulings F-25, F-26, F-30): `name` is a dotted path to a matrix, and every
/// `[row, column]` in `positions` must be exactly 0.0 or -0.0.
fn exact_zero(chk: &Json, name: &str, outs: &Json, msgs: &mut Vec<String>) {
    let mut m = Some(outs);
    for k in name.split('.') {
        m = m.and_then(|v| v.get(k));
    }
    let Some(rows) = m.and_then(Json::as_array) else {
        msgs.push(format!("extra check {name} missing"));
        return;
    };
    for pos in chk.get("positions").and_then(Json::as_array).unwrap_or(&[]) {
        let ij: Vec<usize> = pos
            .as_array()
            .unwrap_or(&[])
            .iter()
            .filter_map(|x| x.as_f64().map(|f| f as usize))
            .collect();
        let v = rows
            .get(ij[0])
            .and_then(Json::as_array)
            .and_then(|r| r.get(ij[1]))
            .and_then(Json::as_f64);
        if v != Some(0.0) {
            msgs.push(format!(
                "extra check {name}: {v:?} at {ij:?} is not exactly zero"
            ));
        }
    }
}

/// Runs one golden case in process and returns the result document.
fn run(case: &Json) -> Json {
    let text = |k: &str| case.get(k).and_then(Json::as_str).unwrap_or_default();
    let doc = obj([
        ("schema_version", "1.0".into()),
        ("case_id", text("case_id").into()),
        ("operation", text("operation").into()),
        ("inputs", case.get("inputs").cloned().unwrap_or(Json::Null)),
    ]);
    // The parser keeps a lone surrogate escape as U+FFFD; no golden holds a real U+FFFD, so
    // writing a lone escape back restores the document the runner sends (cases store_a4-*).
    let wire = doc.to_text().replace('\u{FFFD}', "\\ud800");
    run_case(wire.as_bytes()).0
}

/// Returns the mismatches for one golden case against its result; empty means pass. `peers`
/// holds the results of the other cases of the suite, for expected status `same_as` (rule F-3).
fn judge(case: &Json, res: &Json, peers: &std::collections::HashMap<String, Json>) -> Vec<String> {
    let text = |k: &str| case.get(k).and_then(Json::as_str).unwrap_or_default();
    let mut exp = case.get("expected").unwrap().clone();
    let status = res.get("status").and_then(Json::as_str);
    if res.get("case_id").and_then(Json::as_str) != Some(text("case_id")) {
        return vec!["case_id".into()];
    }
    match exp.get("status").and_then(Json::as_str) {
        Some("any") => {
            return if matches!(status, Some("ok" | "error")) {
                Vec::new()
            } else {
                vec![format!("bad status {status:?}")]
            };
        }
        Some("same_as") => {
            let id = exp
                .get("case_id")
                .and_then(Json::as_str)
                .unwrap_or_default();
            let Some(peer) = peers.get(id) else {
                return vec![format!("peer {id} has no result")];
            };
            exp = match peer.get("status").and_then(Json::as_str) {
                Some("error") => obj([
                    ("status", "error".into()),
                    (
                        "error_code",
                        peer.get("error")
                            .and_then(|e| e.get("code"))
                            .cloned()
                            .unwrap_or(Json::Null),
                    ),
                ]),
                Some("ok") => obj([
                    ("status", "ok".into()),
                    (
                        "outputs",
                        peer.get("outputs").cloned().unwrap_or(Json::Null),
                    ),
                ]),
                _ => return vec![format!("peer {id} has no well-formed result")],
            };
        }
        _ => {}
    }
    if exp.get("status").and_then(Json::as_str) == Some("error") {
        if status != Some("error") {
            return vec![format!("expected an error, got {}", res.to_text())];
        }
        let code = res.get("error").and_then(|e| e.get("code"));
        return if code == exp.get("error_code") {
            Vec::new()
        } else {
            vec![format!("error {:?} vs {:?}", code, exp.get("error_code"))]
        };
    }
    if status != Some("ok") {
        return vec![format!("unexpected {}", res.to_text())];
    }
    let (outs, want) = (res.get("outputs").unwrap(), exp.get("outputs").unwrap());
    let base = class(text("tolerance_class")).expect("known class");
    let limit = case.get("tolerance_limit");
    let mut msgs = Vec::new();
    let Json::Obj(want_fields) = want else {
        return vec!["expected outputs is not an object".into()];
    };
    let mut ka: Vec<&str> = match outs {
        Json::Obj(f) => f.iter().map(|p| p.0.as_str()).collect(),
        _ => Vec::new(),
    };
    let mut kw: Vec<&str> = want_fields.iter().map(|p| p.0.as_str()).collect();
    ka.sort_unstable();
    kw.sort_unstable();
    if ka != kw {
        return vec![format!("output keys {ka:?} vs {kw:?}")];
    }
    for (k, e) in want_fields {
        let per = case
            .get("output_classes")
            .and_then(|c| c.get(k))
            .and_then(Json::as_str);
        let tol = match (per, base, limit) {
            (Some(p), _, _) => class(p).expect("known class"),
            (None, None, _) => None,
            (None, Some((ab, re)), Some(l)) => Some((
                num(l.get("absolute")).unwrap_or(ab),
                num(l.get("relative")).unwrap_or(if re.is_nan() { 0.0 } else { re }),
            )),
            (None, b, None) => b,
        };
        if matches!(tol, Some((ab, _)) if ab.is_nan()) {
            continue; // judged by extra checks alone, as the runner's monte_carlo cases are
        }
        compare(outs.get(k).unwrap(), e, tol, k, &mut msgs);
    }
    for chk in case
        .get("extra_checks")
        .and_then(Json::as_array)
        .unwrap_or(&[])
    {
        let name = chk.get("output").and_then(Json::as_str).unwrap();
        if chk.get("method").and_then(Json::as_str) == Some("exact_zero") {
            exact_zero(chk, name, outs, &mut msgs);
            continue;
        }
        let (Some(a), Some(e)) = (num(outs.get(name)), num(chk.get("expected"))) else {
            msgs.push(format!("extra check {name} missing"));
            continue;
        };
        let lim = if let Some("absolute") = chk.get("method").and_then(Json::as_str) {
            num(chk.get("limit")).unwrap()
        } else {
            let se_key = chk.get("stderr_output").and_then(Json::as_str).unwrap();
            num(chk.get("z")).unwrap() * num(outs.get(se_key)).unwrap_or(f64::NAN)
        };
        let within = (a - e).abs() <= lim; // false for a NaN limit
        if !within {
            msgs.push(format!("extra check {name}: {a} vs {e}, limit {lim}"));
        }
    }
    msgs
}

fn replay(stage: &str) {
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../datasets/golden")
        .join(stage);
    let mut files: Vec<_> = std::fs::read_dir(&dir)
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|x| x == "json"))
        .collect();
    files.sort();
    let (mut seen, mut failures) = (0, Vec::new());
    for f in files {
        let (doc, _) = parse(&std::fs::read_to_string(&f).unwrap()).unwrap();
        let cases = doc.get("cases").and_then(Json::as_array).unwrap();
        let results: Vec<Json> = cases.iter().map(run).collect();
        let peers: std::collections::HashMap<String, Json> = cases
            .iter()
            .zip(&results)
            .filter_map(|(c, r)| Some((c.get("case_id")?.as_str()?.to_owned(), r.clone())))
            .collect();
        for (case, res) in cases.iter().zip(&results) {
            seen += 1;
            let m = judge(case, res, &peers);
            if !m.is_empty() {
                let id = case.get("case_id").map(Json::to_text).unwrap_or_default();
                failures.push(format!("{id}: {}", m.join("; ")));
            }
        }
    }
    assert!(seen >= 40, "{stage}: only {seen} cases found");
    assert!(failures.is_empty(), "{stage}: {failures:#?}");
}

#[test]
fn stage_c_goldens() {
    replay("stage_c");
}

#[test]
fn stage_d_goldens() {
    replay("stage_d");
}

#[test]
fn stage_b_goldens() {
    replay("stage_b");
}

#[test]
fn core_goldens() {
    replay("core");
}

#[test]
fn r2_goldens() {
    replay("r2");
}

#[test]
fn stage_e_goldens() {
    replay("stage_e");
}

#[test]
fn stage_e_b_goldens() {
    replay("stage_e_b");
}

#[test]
fn stage_f_goldens() {
    replay("stage_f");
}

#[test]
fn stage_g_goldens() {
    replay("stage_g");
}

#[test]
fn stage_g_e1_goldens() {
    replay("stage_g_e1");
}

#[test]
fn stage_i_goldens() {
    replay("stage_i");
}

/// The stage I tutorial inputs under `examples/` (handover follow-up to waves 1 to 4d): each
/// file holds the inputs of one golden case, runs with status `ok`, and that case passes.
#[test]
fn stage_i_examples() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let pairs = [
        ("hedge_greeks_i", "hedgegreeks_i", "hedgegreeks_i-0003"),
        ("hedge_minvar_i", "hedgemv_i", "hedgemv_i-0006"),
        ("hedge_beta_i", "hedgebeta_i", "hedgebeta_i-0001"),
        ("hedge_qp_keyrate_i", "hedgeqp_i", "hedgeqp_i-0009"),
        ("hedge_qp_minnorm_i", "hedgeqp_i", "hedgeqp_i-0018"),
        ("hedge_integer_i", "hedgeint_i", "hedgeint_i-0010"),
        ("hedge_residual_i", "hedgeres_i", "hedgeres_i-0002"),
        ("hedge_credit_i", "hedgecredit_i", "hedgecredit_i-0004"),
        ("hedge_correlation_i", "hedgecorr_i", "hedgecorr_i-0003"),
        ("hedge_crossasset_i", "hedgexa_i", "hedgexa_i-0002"),
        ("hedge_cost_i", "hedgecost_i", "hedgecost_i-0002"),
        (
            "hedge_frontier_i",
            "hedgefrontier_i",
            "hedgefrontier_i-0001",
        ),
        ("hedge_backtest_i", "hedgebt_i", "hedgebt_i-0001"),
        ("hedge_effectiveness_i", "hedgeeff_i", "hedgeeff_i-0001"),
        ("hedge_select_i", "hedgeselect_i", "hedgeselect_i-0009"),
        ("hedge_slippage_i", "hedgeslip_i", "hedgeslip_i-0003"),
    ];
    for (file, suite, id) in pairs {
        let text = std::fs::read_to_string(root.join(format!("examples/{file}.json"))).unwrap();
        let (doc, _) = parse(&text).unwrap();
        let (_, ok) = run_case(text.as_bytes());
        assert!(ok, "{file} did not return status ok");
        let golden =
            std::fs::read_to_string(root.join(format!("datasets/golden/stage_i/{suite}.json")))
                .unwrap();
        let (g, _) = parse(&golden).unwrap();
        let case = g
            .get("cases")
            .and_then(Json::as_array)
            .unwrap()
            .iter()
            .find(|c| c.get("case_id").and_then(Json::as_str) == Some(id))
            .unwrap();
        assert_eq!(
            doc.get("inputs"),
            case.get("inputs"),
            "{file} inputs differ from {id}"
        );
        let m = judge(case, &run(case), &std::collections::HashMap::new());
        assert!(m.is_empty(), "{id}: {m:?}");
    }
}
