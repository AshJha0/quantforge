//! The `quantforge` executable (`specifications/cli-contract.md`).

mod functions;
mod input;
mod limits;
mod ops;
mod ops_b;

use input::Inputs;
use ops::{OPERATIONS, dispatch};
use quantforge_core::error::{QfError, err};
use quantforge_core::json::{Flags, Json, nesting_exceeds, obj, parse};
use std::io::{BufRead, Read, Write};
use std::process::ExitCode;

const CONTRACT: &str = "1.0.0";
const SCHEMA: &str = "1.0";
const MAX_CASE_NESTING: usize = 80;

fn error_result(case_id: &str, e: &QfError) -> Json {
    let mut body = vec![
        ("code".to_string(), Json::from(e.code)),
        ("message".to_string(), Json::from(e.message.as_str())),
    ];
    if let Some(f) = &e.field {
        body.push(("field".to_string(), Json::from(f.as_str())));
    }
    obj([
        ("schema_version", SCHEMA.into()),
        ("case_id", case_id.into()),
        ("status", "error".into()),
        ("error", Json::Obj(body)),
    ])
}

fn version_like(s: &str) -> bool {
    let parts: Vec<&str> = s.split('.').collect();
    parts.len() == 2
        && parts
            .iter()
            .all(|p| !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit()))
}

fn operation_like(s: &str) -> bool {
    let parts: Vec<&str> = s.split('.').collect();
    parts.len() >= 2
        && parts.iter().all(|p| {
            !p.is_empty()
                && p.bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        })
}

fn check_envelope(doc: &Json, flags: Flags) -> Result<(&str, &Json), QfError> {
    if flags.overflow {
        return Err(err("E_SCHEMA", "a number overflows binary64"));
    }
    if flags.lone_surrogate {
        return Err(err("E_SCHEMA", "lone surrogate escape"));
    }
    let Json::Obj(fields) = doc else {
        return Err(err("E_SCHEMA", "a case is an object"));
    };
    let known = ["schema_version", "case_id", "operation", "inputs"];
    if fields.iter().any(|(k, _)| !known.contains(&k.as_str())) {
        return Err(err("E_SCHEMA", "unknown key in the envelope"));
    }
    let text = |k: &str| doc.get(k).and_then(Json::as_str);
    if !text("schema_version").is_some_and(version_like) {
        return Err(err("E_SCHEMA", "bad schema_version"));
    }
    if !text("case_id").is_some_and(|s| !s.is_empty()) {
        return Err(err("E_SCHEMA", "bad case_id"));
    }
    let Some(op) = text("operation").filter(|s| operation_like(s)) else {
        return Err(err("E_SCHEMA", "bad operation"));
    };
    match doc.get("inputs") {
        Some(inputs @ Json::Obj(_)) => Ok((op, inputs)),
        _ => Err(err("E_SCHEMA", "inputs must be an object")),
    }
}

/// `E_SCHEMA` outranks `E_LIMIT`, and `E_LIMIT` outranks every rule check. Operations with costly
/// work stop at `Inputs::gate`; the rest are cheap, so their outcome is simply replaced here.
fn run_operation(op: &str, inputs: &Json) -> Result<ops::Outcome, QfError> {
    let limit = OPERATIONS
        .contains(&op)
        .then(|| limits::check(op, inputs))
        .flatten();
    let result = dispatch(op, &Inputs(inputs, limit.clone()));
    match (result, limit) {
        (Err(e), _) if e.code == "E_SCHEMA" => Err(e),
        (_, Some(l)) => Err(l),
        (r, None) => r,
    }
}

/// Returns the result document and whether its status is `ok`.
fn run_case(bytes: &[u8]) -> (Json, bool) {
    if nesting_exceeds(bytes, MAX_CASE_NESTING) {
        let e = err("E_LIMIT", "the case is nested too deeply");
        return (error_result("unknown", &e), false);
    }
    let parsed = std::str::from_utf8(bytes)
        .map_err(|_| err("E_PARSE", "input is not UTF-8"))
        .and_then(parse);
    let (doc, flags) = match parsed {
        Ok(v) => v,
        Err(e) => return (error_result("unknown", &e), false),
    };
    let case_id = doc
        .get("case_id")
        .and_then(Json::as_str)
        .filter(|s| !s.is_empty())
        .unwrap_or("unknown");
    let outcome = check_envelope(&doc, flags).and_then(|(op, inputs)| run_operation(op, inputs));
    match outcome {
        Ok(o) if o.outputs.has_non_finite() => (
            error_result(case_id, &err("E_NON_FINITE", "a result is NaN or infinite")),
            false,
        ),
        Ok(o) => {
            let diagnostics = if o.diagnostics.has_non_finite() {
                Json::Obj(Vec::new())
            } else {
                o.diagnostics
            };
            (
                obj([
                    ("schema_version", SCHEMA.into()),
                    ("case_id", case_id.into()),
                    ("status", "ok".into()),
                    ("outputs", o.outputs),
                    ("diagnostics", diagnostics),
                ]),
                true,
            )
        }
        Err(e) => (error_result(case_id, &e), false),
    }
}

fn run() -> std::io::Result<u8> {
    let mut bytes = Vec::new();
    std::io::stdin().read_to_end(&mut bytes)?;
    let (result, ok) = run_case(&bytes);
    print(result)?;
    Ok(if ok { 0 } else { 2 })
}

fn batch() -> std::io::Result<u8> {
    let mut stdin = std::io::stdin().lock();
    let mut line = Vec::new();
    loop {
        line.clear();
        if stdin.read_until(b'\n', &mut line)? == 0 {
            return Ok(0);
        }
        while matches!(line.last(), Some(b'\n' | b'\r')) {
            line.pop();
        }
        print(run_case(&line).0)?;
    }
}

fn print(v: Json) -> std::io::Result<u8> {
    let mut out = std::io::stdout().lock();
    out.write_all(v.to_text().as_bytes())?;
    out.write_all(b"\n")?;
    out.flush()?;
    Ok(0)
}

fn command(name: &str) -> std::io::Result<u8> {
    match name {
        "run" => run(),
        "batch" => batch(),
        "version" => print(obj([
            ("language", "rust".into()),
            ("implementation_version", env!("CARGO_PKG_VERSION").into()),
            ("contract_version", CONTRACT.into()),
            ("toolchain", "rustc 1.99.1".into()),
        ])),
        _ => print(OPERATIONS.to_vec().into()),
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let [name] = args.as_slice() else {
        eprintln!("usage: quantforge run|batch|version|operations");
        return ExitCode::from(64);
    };
    if !["run", "batch", "version", "operations"].contains(&name.as_str()) {
        eprintln!("unknown command {name}");
        return ExitCode::from(64);
    }
    let name = name.clone();
    // A large stack: parsing and adaptive recursion are depth-limited but not shallow.
    let worker = std::thread::Builder::new()
        .stack_size(256 << 20)
        .spawn(move || command(&name));
    match worker.map(|h| h.join()) {
        Ok(Ok(Ok(code))) => ExitCode::from(code),
        _ => ExitCode::from(70),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn case(op: &str, inputs: &str) -> Json {
        let text = format!(
            r#"{{"schema_version":"1.0","case_id":"c","operation":"{op}","inputs":{inputs}}}"#
        );
        run_case(text.as_bytes()).0
    }

    fn code(r: &Json) -> Option<&str> {
        r.get("error")?.get("code")?.as_str()
    }

    #[test]
    fn operations_are_sorted_and_all_dispatch() {
        assert!(OPERATIONS.windows(2).all(|w| w[0] < w[1]));
        for op in OPERATIONS {
            assert_eq!(code(&case(op, "{}")), Some("E_SCHEMA"), "{op}");
        }
    }

    #[test]
    fn contract_example() {
        let r = case(
            "core.daycount.year_fraction",
            r#"{"convention":"ACT_360","start":"2024-01-01","end":"2024-07-01"}"#,
        );
        let y = r.get("outputs").and_then(|o| o.get("year_fraction"));
        assert_eq!(y.and_then(Json::as_f64), Some(182.0 / 360.0));
    }

    #[test]
    fn envelope_errors() {
        assert_eq!(code(&run_case(b"{").0), Some("E_PARSE"));
        assert_eq!(code(&run_case(br#"{"a":1,"a":2}"#).0), Some("E_PARSE"));
        assert_eq!(code(&run_case(b"[]").0), Some("E_SCHEMA"));
        let unknown = case("core.nope.nope", "{}");
        assert_eq!(code(&unknown), Some("E_UNSUPPORTED_OPERATION"));
        let big = case("core.stats.normal", r#"{"x":[1e400]}"#);
        assert_eq!(code(&big), Some("E_SCHEMA"));
    }

    #[test]
    fn non_finite_result_is_an_error() {
        let r = case(
            "core.integrate.trapezoid",
            r#"{"function":"inv_sqrt","a":0,"b":1,"n":4}"#,
        );
        assert_eq!(code(&r), Some("E_NON_FINITE"));
    }
}
