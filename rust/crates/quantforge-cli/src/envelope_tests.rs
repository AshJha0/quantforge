//! The case envelope and the batch line reader: each refused envelope names `E_SCHEMA` (or
//! `E_LIMIT` for nesting) before any operation runs, and the batch reader keeps lines apart,
//! strips nothing but the newline, and flags a line longer than the 16 MiB cap.

use super::*;

fn code(bytes: &str) -> String {
    let (r, ok) = run_case(bytes.as_bytes());
    assert!(!ok, "{bytes}");
    r.get("error")
        .and_then(|e| e.get("code"))
        .and_then(Json::as_str)
        .unwrap_or_default()
        .to_owned()
}

#[test]
fn refused_envelopes() {
    let op = r#""operation":"core.daycount.year_fraction""#;
    for (doc, want) in [
        (
            format!(r#"{{"schema_version":"1.0","case_id":"c",{op},"inputs":{{}},"extra":1}}"#),
            "E_SCHEMA",
        ),
        (
            format!(r#"{{"schema_version":"one","case_id":"c",{op},"inputs":{{}}}}"#),
            "E_SCHEMA",
        ),
        (
            format!(r#"{{"schema_version":"1.0","case_id":"",{op},"inputs":{{}}}}"#),
            "E_SCHEMA",
        ),
        (
            r#"{"schema_version":"1.0","case_id":"c","operation":"Not An Op","inputs":{}}"#
                .to_owned(),
            "E_SCHEMA",
        ),
        (
            format!(r#"{{"schema_version":"1.0","case_id":"c",{op},"inputs":[]}}"#),
            "E_SCHEMA",
        ),
        ("[]".to_owned(), "E_SCHEMA"),
        (format!("{}{}", "[".repeat(200), "]".repeat(200)), "E_LIMIT"),
    ] {
        assert_eq!(code(&doc), want, "{doc}");
    }
}

#[test]
fn elapsed_goes_into_diagnostics_whatever_was_there() {
    let start = std::time::Instant::now();
    let has_elapsed = |r: &Json| {
        r.get("diagnostics")
            .and_then(|d| d.get("elapsed_ns"))
            .is_some()
    };
    let none = with_elapsed(Json::Obj(vec![]), start);
    assert!(has_elapsed(&none));
    let obj = Json::Obj(vec![(
        "diagnostics".into(),
        Json::Obj(vec![("note".into(), Json::Str("x".into()))]),
    )]);
    let kept = with_elapsed(obj, start);
    assert!(has_elapsed(&kept));
    assert!(
        kept.get("diagnostics")
            .and_then(|d| d.get("note"))
            .is_some()
    );
    let replaced = with_elapsed(Json::Obj(vec![("diagnostics".into(), Json::Int(1))]), start);
    assert!(has_elapsed(&replaced));
    let (timed, _) = timed_case(b"{}", true);
    assert!(has_elapsed(&timed));
    let (plain, _) = timed_case(b"{}", false);
    assert!(!has_elapsed(&plain));
}

#[test]
fn line_reader_splits_and_flags_long_lines() {
    let mut input = std::io::Cursor::new(b"ab\r\ncd\nlast".to_vec());
    let mut line = Vec::new();
    assert_eq!(read_line(&mut input, &mut line).unwrap(), Some(false));
    assert_eq!(line, b"ab\r"); // the caller strips the CR
    assert_eq!(read_line(&mut input, &mut line).unwrap(), Some(false));
    assert_eq!(line, b"cd");
    assert_eq!(read_line(&mut input, &mut line).unwrap(), Some(false));
    assert_eq!(line, b"last"); // a final line needs no newline
    assert_eq!(read_line(&mut input, &mut line).unwrap(), None);
    let mut long = vec![b'x'; MAX_LINE + 10];
    long.extend_from_slice(b"\nok\n");
    let mut input = std::io::BufReader::with_capacity(4096, std::io::Cursor::new(long));
    assert_eq!(read_line(&mut input, &mut line).unwrap(), Some(true));
    assert_eq!(line.len(), MAX_LINE + 1); // kept up to the cap, then dropped
    assert_eq!(read_line(&mut input, &mut line).unwrap(), Some(false));
    assert_eq!(line, b"ok"); // the next line is intact
}
