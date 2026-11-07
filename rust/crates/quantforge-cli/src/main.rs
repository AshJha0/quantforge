//! The `quantforge` executable (`specifications/cli-contract.md`).

mod functions;
mod input;
mod limits;
mod ops;
mod ops_b;
mod ops_c;
mod ops_d;
mod ops_d2;

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

/// `E_SCHEMA` outranks `E_LIMIT`, and `E_LIMIT` outranks every rule check. Every operation that
/// works on an array stops at `Inputs::gate`, after its typed reads. An oversized array in a key
/// the operation ignores reaches the end, and its small result is replaced here.
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
