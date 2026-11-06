//! Snapshot hash (`snapshot-hash.md`).
use crate::error::{Result, fail};
use crate::json::{Json, parse};
use crate::sha256::sha256_hex;

fn string(s: &str, out: &mut Vec<u8>) {
    out.push(b'"');
    for &b in s.as_bytes() {
        match b {
            b'"' => out.extend_from_slice(b"\\\""),
            b'\\' => out.extend_from_slice(b"\\\\"),
            0..=0x1f => out.extend_from_slice(format!("\\u{b:04x}").as_bytes()),
            _ => out.push(b),
        }
    }
    out.push(b'"');
}

fn number(v: f64, out: &mut Vec<u8>) {
    let v = if v == 0.0 { 0.0 } else { v };
    out.extend_from_slice(format!("#{:016x}", v.to_bits()).as_bytes());
}

fn canonical(v: &Json, out: &mut Vec<u8>) {
    match v {
        Json::Null => out.extend_from_slice(b"null"),
        Json::Bool(true) => out.extend_from_slice(b"true"),
        Json::Bool(false) => out.extend_from_slice(b"false"),
        Json::Int(n) => number(*n as f64, out),
        Json::Num(x) => number(*x, out),
        Json::Str(s) => string(s, out),
        Json::Arr(a) => {
            out.push(b'[');
            for (i, e) in a.iter().enumerate() {
                if i > 0 {
                    out.push(b',');
                }
                canonical(e, out);
            }
            out.push(b']');
        }
        Json::Obj(o) => {
            let mut keys: Vec<&(String, Json)> = o.iter().collect();
            keys.sort_by(|a, b| a.0.as_bytes().cmp(b.0.as_bytes()));
            out.push(b'{');
            for (i, (k, e)) in keys.into_iter().enumerate() {
                if i > 0 {
                    out.push(b',');
                }
                string(k, out);
                out.push(b':');
                canonical(e, out);
            }
            out.push(b'}');
        }
    }
}

/// Returns the canonical text and the snapshot id.
pub fn hash(document: &str) -> Result<(String, String)> {
    let (doc, flags) = parse(document)?;
    if flags.overflow {
        return fail("E_SCHEMA", "a number overflows binary64");
    }
    if flags.lone_surrogate {
        return fail("E_SCHEMA", "lone surrogate escape");
    }
    let Json::Obj(mut top) = doc else {
        return fail("E_SCHEMA", "top level is not an object");
    };
    top.retain(|(k, _)| k != "snapshot_id");
    let mut bytes = Vec::new();
    canonical(&Json::Obj(top), &mut bytes);
    let id = format!("sha256:{}", sha256_hex(&bytes));
    let text = String::from_utf8(bytes).expect("canonical form is UTF-8");
    Ok((text, id))
}
