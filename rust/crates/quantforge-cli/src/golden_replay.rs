//! Replays the core and stage B, C and D goldens through `run_case` in process, judged the way
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
        "interpolation" => Some((1e-10, 1e-8)),
        "root_finding" => Some((1e-10, 1e-10)),
        "quadrature" | "statistics" => Some((1e-11, 1e-10)),
        "numerical_scheme" => Some((1e-8, 1e-8)),
        "fourier" | "common_rng" => Some((1e-9, 1e-9)),
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

/// Returns the mismatches for one golden case; empty means pass.
fn judge(case: &Json) -> Vec<String> {
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
    let (res, _) = run_case(wire.as_bytes());
    let exp = case.get("expected").unwrap();
    let status = res.get("status").and_then(Json::as_str);
    if res.get("case_id").and_then(Json::as_str) != Some(text("case_id")) {
        return vec!["case_id".into()];
    }
    if exp.get("status").and_then(Json::as_str) == Some("error") {
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
        for case in doc.get("cases").and_then(Json::as_array).unwrap() {
            seen += 1;
            let m = judge(case);
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
