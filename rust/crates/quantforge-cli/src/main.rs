//! The `quantforge` executable (`specifications/cli-contract.md`).

mod functions;
#[cfg(test)]
mod golden_replay;
mod input;
mod limits;
mod ops;

use input::Inputs;
use ops::{dispatch, operations};
use quantforge_core::error::{QfError, err};
use quantforge_core::json::{Flags, Json, nesting_exceeds, obj, parse};
use std::io::{BufRead, Read, Write};
use std::process::ExitCode;

const CONTRACT: &str = "1.11.0";
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
        ("diagnostics", Json::Obj(Vec::new())),
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
    if text("case_id").is_none_or(str::is_empty) {
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

/// `E_SCHEMA` outranks `E_LIMIT`, and `E_LIMIT` outranks every rule check. Every operation that
/// works on an array stops at `Inputs::gate`, after its typed reads. An oversized array in a key
/// the operation ignores reaches the end, and its small result is replaced here.
fn run_operation(op: &str, inputs: &Json) -> Result<ops::Outcome, QfError> {
    let inputs = &with_non_finite_tokens(inputs);
    let limit = operations()
        .contains(&op)
        .then(|| limits::check(op, inputs))
        .flatten();
    let result = dispatch(op, &Inputs(inputs, limit.clone()));
    match (result, limit) {
        (Err(e), _) if e.code == "E_SCHEMA" => Err(e),
        (_, Some(l)) => Err(l),
        // F-2: after E_SCHEMA and E_LIMIT, before every check of the operation's own.
        _ if inputs.has_non_finite() => Err(err("E_DOMAIN", "a Real input is NaN or infinite")),
        (r, None) => r,
    }
}

/// F-1: the strings `"NaN"`, `"Infinity"` and `"-Infinity"` are the binary64 values. They become
/// numbers here, so a Real read accepts them and an Integer, Date or Enum read is `E_SCHEMA`.
fn with_non_finite_tokens(v: &Json) -> Json {
    match v {
        Json::Str(s) if s == "NaN" => Json::Num(f64::NAN),
        Json::Str(s) if s == "Infinity" => Json::Num(f64::INFINITY),
        Json::Str(s) if s == "-Infinity" => Json::Num(f64::NEG_INFINITY),
        Json::Arr(a) => Json::Arr(a.iter().map(with_non_finite_tokens).collect()),
        Json::Obj(o) => Json::Obj(
            o.iter()
                .map(|(k, x)| (k.clone(), with_non_finite_tokens(x)))
                .collect(),
        ),
        other => other.clone(),
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

/// BT5: the longest line, in bytes after the CR of a CRLF is removed.
const MAX_LINE: usize = 16_777_216;

/// Adds `diagnostics.elapsed_ns` (the `--timings` flag), also to an error result.
fn with_elapsed(mut result: Json, start: std::time::Instant) -> Json {
    let ns = i64::try_from(start.elapsed().as_nanos()).unwrap_or(i64::MAX);
    let entry = ("elapsed_ns".to_string(), Json::Int(ns));
    if let Json::Obj(fields) = &mut result {
        match fields.iter_mut().find(|(k, _)| k == "diagnostics") {
            Some((_, Json::Obj(d))) => d.push(entry),
            Some((_, other)) => *other = Json::Obj(vec![entry]),
            None => fields.push(("diagnostics".to_string(), Json::Obj(vec![entry]))),
        }
    }
    result
}

fn timed_case(bytes: &[u8], timings: bool) -> (Json, bool) {
    let start = std::time::Instant::now();
    let (result, ok) = run_case(bytes);
    (
        if timings {
            with_elapsed(result, start)
        } else {
            result
        },
        ok,
    )
}

fn run(timings: bool) -> std::io::Result<u8> {
    let mut bytes = Vec::new();
    std::io::stdin().read_to_end(&mut bytes)?;
    let (result, ok) = timed_case(&bytes, timings);
    print(&result)?;
    Ok(if ok { 0 } else { 2 })
}

/// Reads one line into `line`, keeping at most `MAX_LINE + 1` bytes (room for a CR) and dropping
/// the rest. Returns `None` at end of input, else whether the line had more bytes than were kept.
fn read_line(input: &mut impl BufRead, line: &mut Vec<u8>) -> std::io::Result<Option<bool>> {
    line.clear();
    let (mut any, mut dropped) = (false, false);
    loop {
        let buf = input.fill_buf()?;
        if buf.is_empty() {
            return Ok(any.then_some(dropped));
        }
        any = true;
        let (chunk, done) = match buf.iter().position(|&b| b == b'\n') {
            Some(i) => (&buf[..i], i + 1),
            None => (buf, buf.len()),
        };
        let room = (MAX_LINE + 1).saturating_sub(line.len());
        if chunk.len() > room {
            dropped = true;
        }
        line.extend_from_slice(&chunk[..chunk.len().min(room)]);
        let ended = done > chunk.len();
        input.consume(done);
        if ended {
            return Ok(Some(dropped));
        }
    }
}

fn batch(timings: bool) -> std::io::Result<u8> {
    let mut stdin = std::io::stdin().lock();
    let mut line = Vec::new();
    while let Some(dropped) = read_line(&mut stdin, &mut line)? {
        if !dropped && line.last() == Some(&b'\r') {
            line.pop();
        }
        let result = if dropped || line.len() > MAX_LINE {
            let start = std::time::Instant::now();
            let r = error_result("unknown", &err("E_LIMIT", "the line is longer than 16 MiB"));
            if timings { with_elapsed(r, start) } else { r }
        } else {
            timed_case(&line, timings).0
        };
        print(&result)?;
    }
    Ok(0)
}

fn print(v: &Json) -> std::io::Result<u8> {
    let mut out = std::io::stdout().lock();
    out.write_all(v.to_text().as_bytes())?;
    out.write_all(b"\n")?;
    out.flush()?;
    Ok(0)
}

fn command(name: &str, timings: bool) -> std::io::Result<u8> {
    match name {
        "run" => run(timings),
        "batch" | "--batch" => batch(timings),
        "version" => print(&obj([
            ("language", "rust".into()),
            ("implementation_version", env!("CARGO_PKG_VERSION").into()),
            ("contract_version", CONTRACT.into()),
            ("toolchain", "rustc 1.99.1".into()),
        ])),
        _ => print(&operations().to_vec().into()),
    }
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let args: Vec<&str> = args.iter().map(String::as_str).collect();
    let (name, timings) = match args.as_slice() {
        [n @ ("run" | "batch" | "--batch" | "version" | "operations")] => (*n, false),
        [n @ ("run" | "batch" | "--batch"), "--timings"] => (*n, true),
        _ => {
            eprintln!("usage: quantforge run|batch|--batch [--timings] | version | operations");
            return ExitCode::from(64);
        }
    };
    let name = name.to_string();
    // A large stack: parsing and adaptive recursion are depth-limited but not shallow.
    let worker = std::thread::Builder::new()
        .stack_size(256 << 20)
        .spawn(move || command(&name, timings));
    match worker.map(std::thread::JoinHandle::join) {
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
        assert!(operations().windows(2).all(|w| w[0] < w[1]));
        for op in operations() {
            // Every key of `hedge.minvar.ratio` is optional, and its spec makes "neither input
            // form" an `E_INPUT` (hedge-solvers.md, check 1).
            let want = if *op == "hedge.minvar.ratio" {
                "E_INPUT"
            } else {
                "E_SCHEMA"
            };
            assert_eq!(code(&case(op, "{}")), Some(want), "{op}");
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

#[cfg(test)]
mod stage_d_tests {
    use super::*;

    fn code(op: &str, inputs: &str) -> Option<String> {
        let text = format!(
            r#"{{"schema_version":"1.0","case_id":"c","operation":"{op}","inputs":{inputs}}}"#
        );
        let r = run_case(text.as_bytes()).0;
        Some(r.get("error")?.get("code")?.as_str()?.to_string())
    }

    const CURVE: &str = r#"{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2027-11-06","discount_factor":0.96}]}"#;
    const CURVE_LATER: &str = r#"{"as_of":"2026-11-09","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2027-11-06","discount_factor":0.96}]}"#;

    #[test]
    fn jumps_null_is_schema_and_bad_jumps_are_checked() {
        let q = r#""quotes":[{"tenor":"1Y","rate":0.03}],"interpolation":"LOG_LINEAR_DF","method":"SEQUENTIAL""#;
        let b = |j: &str| {
            code(
                "rates.ois.bootstrap",
                &format!(r#"{{"convention":"ESTR","as_of":"2026-11-06",{q}{j}}}"#),
            )
        };
        assert_eq!(b(""), None);
        assert_eq!(b(r#","jumps":[]"#), None);
        assert_eq!(b(r#","jumps":null"#).as_deref(), Some("E_SCHEMA"));
        assert_eq!(
            b(r#","jumps":[{"date":"2026-12-31","factor":-1}]"#).as_deref(),
            Some("E_DOMAIN")
        );
        let c = r#"{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2027-11-06","discount_factor":0.96}],"jumps":[{"date":"2026-11-06","factor":0.99}]}"#;
        let d = code(
            "rates.curve.discount",
            &format!(r#"{{"curve":{c},"dates":["2027-01-01"]}}"#),
        );
        assert_eq!(d.as_deref(), Some("E_INPUT"));
    }

    #[test]
    fn compound_dated_convention_kinds() {
        let rest = r#""start":"2026-11-10","end":"2026-11-12","method":"NONE","shift_days":0,"fixings":[{"date":"2026-11-10","rate":0.04}]"#;
        let c = |id: &str| {
            code(
                "rates.ois.compound_dated",
                &format!(r#"{{"convention":"{id}",{rest}}}"#),
            )
        };
        assert_eq!(c("SOFR"), None);
        assert_eq!(c("USD-TERM-3M").as_deref(), Some("E_INPUT"));
        assert_eq!(c("NOPE").as_deref(), Some("E_SCHEMA"));
        let m = code(
            "rates.ois.compound_dated",
            &format!(r#"{{"convention":"SOFR",{}}}"#, rest.replace("NONE", "BAD")),
        );
        assert_eq!(m.as_deref(), Some("E_SCHEMA"));
        let f = code(
            "rates.fallback.rate",
            r#"{"ibor":"GBP-LIBOR-1M","start":"2026-11-10","end":"2026-11-12","fixings":[]}"#,
        );
        assert_eq!(f.as_deref(), Some("E_INPUT"));
    }

    #[test]
    fn csa_fx_must_be_present() {
        let base = format!(r#""curve":{CURVE},"collateral_spread":0.0,"dates":["2027-01-01"]"#);
        assert_eq!(
            code("rates.csa.discount", &format!("{{{base}}}")).as_deref(),
            Some("E_SCHEMA")
        );
        assert_eq!(
            code("rates.csa.discount", &format!(r#"{{{base},"fx":null}}"#)),
            None
        );
        let fx = r#","fx":{"spot":1.1,"forwards":[{"date":"2027-01-01","forward":1.2}]}"#;
        assert_eq!(code("rates.csa.discount", &format!("{{{base}{fx}}}")), None);
        let none = code(
            "rates.csa.discount",
            &format!(r#"{{"curve":{CURVE},"collateral_spread":0.0,"dates":[],"fx":null}}"#),
        );
        assert_eq!(none.as_deref(), Some("E_INPUT"));
    }

    #[test]
    fn basis_needs_one_as_of() {
        let s = |b: &str| {
            code(
                "rates.basis.ois_spread",
                &format!(
                    r#"{{"convention":"SOFR","tenor":"1Y","discount":{CURVE},"projection_a":{CURVE},"projection_b":{b}}}"#
                ),
            )
        };
        assert_eq!(s(CURVE), None);
        assert_eq!(s(CURVE_LATER).as_deref(), Some("E_INPUT"));
    }

    #[test]
    fn step_ops_and_fits_inputs() {
        let s = |extra: &str| {
            code(
                "rates.ois.step_curve",
                &format!(
                    r#"{{"as_of":"2026-11-06","base_rate":0.04,"steps":[{{"date":"2027-01-01","rate":0.03}}]{extra}}}"#
                ),
            )
        };
        assert_eq!(s(r#","jumps":[],"dates":["2027-02-01"]"#), None);
        assert_eq!(s(r#","dates":["2027-02-01"]"#).as_deref(), Some("E_SCHEMA"));
        assert_eq!(s(r#","jumps":[],"dates":[]"#).as_deref(), Some("E_INPUT"));
        let w = |extra: &str| {
            code(
                "calib.curve.smooth",
                &format!(
                    r#"{{"knots":[1,2],"maturities":[1,2],"zero_rates":[0.03,0.04],"lambda":0.1{extra}}}"#
                ),
            )
        };
        assert_eq!(w(""), None);
        assert_eq!(w(r#","weights":[1,1]"#), None);
        assert_eq!(w(r#","weights":null"#).as_deref(), Some("E_SCHEMA"));
        let r = code(
            "calib.curve.robust",
            r#"{"maturities":[1,2,3,5],"zero_rates":[0.03,0.032,0.033,0.04],"tau":2,"delta":0.001}"#,
        );
        assert_eq!(r, None);
        let f = code(
            "rates.futures.convexity",
            r#"{"price":96,"start_years":1,"end_years":1.25,"sigma":0.01,"mean_reversion":0}"#,
        );
        assert_eq!(f, None);
    }

    #[test]
    fn joint_quote_lists_have_the_quote_limit() {
        let q: Vec<String> = (1..=101)
            .map(|n| format!(r#"{{"tenor":"{n}Y","rate":0.03}}"#))
            .collect();
        let j = format!(
            r#"{{"convention":"SOFR","index":"USD-TERM-3M","as_of":"2026-11-06","ois_quotes":[{}],"term_quotes":[{{"type":"DEPOSIT","months":3,"rate":0.03}}],"interpolation":"LOG_LINEAR_DF","method":"GLOBAL"}}"#,
            q.join(",")
        );
        assert_eq!(
            code("rates.curve.joint_bootstrap", &j).as_deref(),
            Some("E_LIMIT")
        );
    }
}

#[cfg(test)]
mod stage_d_wave2_tests {
    use super::*;

    fn code(op: &str, inputs: &str) -> Option<String> {
        let text = format!(
            r#"{{"schema_version":"1.0","case_id":"c","operation":"{op}","inputs":{inputs}}}"#
        );
        let r = run_case(text.as_bytes()).0;
        Some(r.get("error")?.get("code")?.as_str()?.to_string())
    }

    const BOND: &str = r#"{"maturity":"2029-11-15","coupon":0.0425,"frequency":2}"#;
    const CURVE: &str = r#"{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2040-11-06","discount_factor":0.6}]}"#;

    #[test]
    fn bond_and_repo_keys() {
        let y = |b: &str| {
            code(
                "bond.price.from_yield",
                &format!(r#"{{"bond":{b},"settlement":"2026-11-09","yield":0.04}}"#),
            )
        };
        assert_eq!(y(BOND), None);
        assert_eq!(y(&BOND.replace(":2}", ":3}")).as_deref(), Some("E_SCHEMA"));
        let r = |gc: &str| {
            code(
                "repo.forward",
                &format!(
                    r#"{{"bond":{BOND},"start":"2026-11-09","end":"2026-12-09","clean_price":100,"repo_rate":0.04{gc}}}"#
                ),
            )
        };
        assert_eq!(r(r#","gc_rate":null"#), None);
        assert_eq!(r(r#","gc_rate":0.041"#), None);
        assert_eq!(r("").as_deref(), Some("E_SCHEMA"));
        let cf = code(
            "bond.futures.conversion_factor",
            &format!(r#"{{"bond":{BOND},"delivery_month":"2026-1","notional_coupon":0.06}}"#),
        );
        assert_eq!(cf.as_deref(), Some("E_SCHEMA"));
    }

    #[test]
    fn ndf_trs_and_cpi_required_nullable_keys() {
        let n = |f: &str| {
            code(
                "fx.ndf.pv",
                &format!(
                    r#"{{"usd_curve":{CURVE},"offshore_curve":{CURVE},"spot":88,"trade":{{"fixing_date":"2027-05-06","payment_date":"2027-05-10","strike":90,"usd_notional":1e6,"side":"BUY"}}{f}}}"#
                ),
            )
        };
        assert_eq!(n(r#","fixing":null"#), None);
        assert_eq!(n("").as_deref(), Some("E_SCHEMA"));
        let c = |s: &str| {
            code(
                "infl.curve.cpi",
                &format!(
                    r#"{{"base_month":"2026-08","base_cpi":300,"quotes":[{{"years":1,"rate":0.02}}]{s},"months":["2027-01"]}}"#
                ),
            )
        };
        assert_eq!(c(r#","seasonality":null"#), None);
        assert_eq!(c("").as_deref(), Some("E_SCHEMA"));
        let t = |r: &str| {
            code(
                "eq.trs.pv",
                &format!(
                    r#"{{"spot":100,"funding":{CURVE},"borrow_rate":0,"dividends":[],"trade":{{"start":"2026-11-06","end":"2027-11-06","initial_price":100,"shares":1,"spread":0,"side":"PAY_EQUITY"}}{r}}}"#
                ),
            )
        };
        assert_eq!(t(r#","current_rate":null"#), None);
        assert_eq!(t("").as_deref(), Some("E_SCHEMA"));
    }

    #[test]
    fn credit_and_index_inputs() {
        let p = code(
            "credit.cds.bootstrap",
            &format!(
                r#"{{"trade_date":"2026-11-06","discount":{CURVE},"recovery":0.4,"quotes":[{{"tenor":"5Y","spread":0.01}}]}}"#
            ),
        );
        assert_eq!(p, None);
        let ca = code(
            "eq.corporate_action.adjust",
            r#"{"action":"MERGER","cum_price":1,"shares":1,"strike":1}"#,
        );
        assert_eq!(ca.as_deref(), Some("E_SCHEMA"));
    }
}

#[cfg(test)]
mod stage_d_rulings2_tests {
    use super::*;

    fn code(op: &str, inputs: &str) -> Option<String> {
        let text = format!(
            r#"{{"schema_version":"1.0","case_id":"c","operation":"{op}","inputs":{inputs}}}"#
        );
        let r = run_case(text.as_bytes()).0;
        Some(r.get("error")?.get("code")?.as_str()?.to_string())
    }

    const CURVE: &str = r#"{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2040-11-06","discount_factor":0.6}]}"#;

    #[test]
    fn d47_estr_basis_and_d56_vol_type() {
        let b = format!(
            r#"{{"convention":"ESTR","tenor":"1Y","discount":{CURVE},"projection_a":{CURVE},"projection_b":{CURVE}}}"#
        );
        assert_eq!(code("rates.basis.ois_spread", &b), None);
        let cap = |m: &str, v: &str| {
            code(
                "rates.cap.price",
                &format!(
                    r#"{{"discount":{CURVE},"projection":{CURVE},"model":"{m}","vol":{v},"trade":{{"type":"CAP","start_months":3,"tenor_months":12,"strike":-0.01,"notional":1}}}}"#
                ),
            )
        };
        assert_eq!(cap("BACHELIER", "0.01"), None);
        assert_eq!(cap("BACHELIER", r#""0.01""#).as_deref(), Some("E_SCHEMA"));
        assert_eq!(cap("SABR", "0.01").as_deref(), Some("E_SCHEMA"));
    }

    #[test]
    fn d61_futures_basis_dates() {
        let b = |d: &str| {
            code(
                "bond.futures.basis",
                &format!(
                    r#"{{"futures_price":110,"settlement":"2026-11-09","delivery":"{d}","repo_rate":0.04,"bonds":[{{"maturity":"2027-11-15","coupon":0.04,"frequency":2,"clean_price":100,"conversion_factor":0.9}}]}}"#
                ),
            )
        };
        assert_eq!(b("2026-12-01"), None);
        assert_eq!(b("2026-11-09").as_deref(), Some("E_DATE_ORDER"));
        assert_eq!(b("2028-01-03").as_deref(), Some("E_INPUT"));
    }

    #[test]
    fn stage_i_null_keys_and_limits() {
        let qp = |extra: &str| {
            code(
                "hedge.qp.solve",
                &format!(
                    r#"{{"a":[[1.0,0.0],[0.0,1.0]],"b":[1.0,2.0],"weights":[1.0,1.0]{extra}}}"#
                ),
            )
        };
        assert_eq!(qp(""), None);
        assert_eq!(qp(r#","lower":[null,0.0],"upper":[null,null]"#), None);
        assert_eq!(qp(r#","ridge":null"#).as_deref(), Some("E_SCHEMA"));
        assert_eq!(qp(r#","lower":null"#).as_deref(), Some("E_SCHEMA"));
        assert_eq!(qp(r#","singular":"PSEUDO""#).as_deref(), Some("E_SCHEMA"));
        assert_eq!(
            qp(r#","eq_matrix":[[1.0,1.0]]"#).as_deref(),
            Some("E_INPUT")
        );
        let wide = format!("[{}]", vec!["1.0"; 201].join(","));
        let r = code(
            "hedge.qp.solve",
            &format!(r#"{{"a":[{wide}],"b":[1.0],"weights":[1.0]}}"#),
        );
        assert_eq!(r.as_deref(), Some("E_LIMIT"));
        let lots = |extra: &str| {
            code(
                "hedge.integer.solve",
                &format!(r#"{{"a":[[1.0]],"b":[-0.4],"weights":[1.0],"lot_sizes":[1.0]{extra}}}"#),
            )
        };
        assert_eq!(lots(r#","lower_lots":[null],"upper_lots":[3]"#), None);
        assert_eq!(lots(r#","upper_lots":[1.5]"#).as_deref(), Some("E_SCHEMA"));
        let beta = |extra: &str| {
            code(
                "hedge.beta.futures",
                &format!(
                    r#"{{"portfolio_value":1.0,"portfolio_beta":1.0,"target_beta":0.0,"futures_price":1.0,"multiplier":1.0{extra}}}"#
                ),
            )
        };
        assert_eq!(beta(r#","rounding":"NONE""#), None);
        assert_eq!(beta(r#","rounding":"UP""#).as_deref(), Some("E_SCHEMA"));
        let mv = |inputs: &str| code("hedge.minvar.ratio", inputs);
        assert_eq!(mv(r#"{"covariance":[[1.0,0.5],[0.5,1.0]]}"#), None);
        assert_eq!(mv("{}").as_deref(), Some("E_INPUT"));
        assert_eq!(
            mv(r#"{"exposure_changes":[1.0,2.0,3.0]}"#).as_deref(),
            Some("E_INPUT")
        );
        let leg = r#"{"instrument":"UNDERLYING"}"#;
        let greeks = |hedges: &str, targets: &str| {
            code(
                "hedge.greeks.neutralise",
                &format!(
                    r#"{{"spot":100.0,"rate":0.0,"dividend_yield":0.0,"volatility":0.2,"portfolio":[{{"instrument":"CALL","strike":100.0,"expiry_years":1.0,"quantity":1.0}}],"hedges":[{hedges}],"targets":[{targets}]}}"#
                ),
            )
        };
        assert_eq!(greeks(leg, r#""DELTA""#), None);
        assert_eq!(
            greeks(r#"{"instrument":"FUTURE"}"#, r#""DELTA""#).as_deref(),
            Some("E_SCHEMA")
        );
        assert_eq!(greeks(leg, r#""RHO""#).as_deref(), Some("E_SCHEMA"));
        let four = [leg; 4].join(",");
        assert_eq!(greeks(&four, r#""DELTA""#).as_deref(), Some("E_LIMIT"));
        // I-53: n = 20 allows K = 6 (60,459 subsets) but not K = 7 (137,979).
        let row = format!("[{}]", vec!["0.0"; 20].join(","));
        let select = |k: i64| {
            code(
                "hedge.select.solve",
                &format!(r#"{{"a":[{row}],"b":[1.0],"weights":[1.0],"max_instruments":{k}}}"#),
            )
        };
        assert_eq!(select(7).as_deref(), Some("E_LIMIT"));
        assert_ne!(select(6).as_deref(), Some("E_LIMIT"));
        let res = code(
            "hedge.residual.report",
            r#"{"a":[[1.0]],"b":[1.0],"x":[0.5],"covariance":[[2.0]]}"#,
        );
        assert_eq!(res, None);
    }
}
