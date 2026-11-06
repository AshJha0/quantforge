//! A strict JSON reader and writer. The contract needs duplicate-key detection, overflow and
//! lone-surrogate reporting, which is why this is not a general library.
use crate::error::{Result, fail};
use std::fmt::Write;

#[derive(Debug, Clone, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    /// A number written without fraction or exponent, of magnitude at most 2^53.
    Int(i64),
    Num(f64),
    Str(String),
    Arr(Vec<Json>),
    Obj(Vec<(String, Json)>),
}

/// Problems that the parser records and leaves the caller to rank.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Flags {
    pub overflow: bool,
    pub lone_surrogate: bool,
}

const MAX_DEPTH: usize = 1000;

struct Parser<'a> {
    b: &'a [u8],
    i: usize,
    flags: Flags,
}

pub fn parse(text: &str) -> Result<(Json, Flags)> {
    let mut p = Parser {
        b: text.as_bytes(),
        i: 0,
        flags: Flags::default(),
    };
    p.ws();
    let v = p.value(0)?;
    p.ws();
    if p.i != p.b.len() {
        return bad("trailing text");
    }
    Ok((v, p.flags))
}

fn bad<T>(m: &str) -> Result<T> {
    fail("E_PARSE", m)
}

impl Parser<'_> {
    fn ws(&mut self) {
        while matches!(self.b.get(self.i), Some(b' ' | b'\t' | b'\n' | b'\r')) {
            self.i += 1;
        }
    }

    fn eat(&mut self, c: u8) -> bool {
        let hit = self.b.get(self.i) == Some(&c);
        if hit {
            self.i += 1;
        }
        hit
    }

    fn literal(&mut self, word: &str, v: Json) -> Result<Json> {
        if self.b[self.i..].starts_with(word.as_bytes()) {
            self.i += word.len();
            Ok(v)
        } else {
            bad("bad literal")
        }
    }

    fn value(&mut self, depth: usize) -> Result<Json> {
        if depth > MAX_DEPTH {
            return bad("nested too deeply");
        }
        match self.b.get(self.i) {
            Some(b'n') => self.literal("null", Json::Null),
            Some(b't') => self.literal("true", Json::Bool(true)),
            Some(b'f') => self.literal("false", Json::Bool(false)),
            Some(b'"') => Ok(Json::Str(self.string()?)),
            Some(b'[') => self.array(depth),
            Some(b'{') => self.object(depth),
            Some(b'-' | b'0'..=b'9') => self.number(),
            _ => bad("expected a value"),
        }
    }

    fn array(&mut self, depth: usize) -> Result<Json> {
        self.i += 1;
        let mut out = Vec::new();
        self.ws();
        if self.eat(b']') {
            return Ok(Json::Arr(out));
        }
        loop {
            self.ws();
            out.push(self.value(depth + 1)?);
            self.ws();
            if self.eat(b']') {
                return Ok(Json::Arr(out));
            }
            if !self.eat(b',') {
                return bad("expected , or ]");
            }
        }
    }

    fn object(&mut self, depth: usize) -> Result<Json> {
        self.i += 1;
        let mut out: Vec<(String, Json)> = Vec::new();
        let mut seen = std::collections::HashSet::new();
        self.ws();
        if self.eat(b'}') {
            return Ok(Json::Obj(out));
        }
        loop {
            self.ws();
            if self.b.get(self.i) != Some(&b'"') {
                return bad("expected a key");
            }
            let k = self.string()?;
            if !seen.insert(k.clone()) {
                return bad("duplicate key");
            }
            self.ws();
            if !self.eat(b':') {
                return bad("expected :");
            }
            self.ws();
            let v = self.value(depth + 1)?;
            out.push((k, v));
            self.ws();
            if self.eat(b'}') {
                return Ok(Json::Obj(out));
            }
            if !self.eat(b',') {
                return bad("expected , or }");
            }
        }
    }

    fn digits(&mut self) -> Result<()> {
        let from = self.i;
        while matches!(self.b.get(self.i), Some(b'0'..=b'9')) {
            self.i += 1;
        }
        if self.i == from {
            return bad("expected a digit");
        }
        Ok(())
    }

    fn number(&mut self) -> Result<Json> {
        let start = self.i;
        self.eat(b'-');
        if self.eat(b'0') {
            if matches!(self.b.get(self.i), Some(b'0'..=b'9')) {
                return bad("leading zero");
            }
        } else {
            self.digits()?;
        }
        let mut integer = true;
        if self.eat(b'.') {
            integer = false;
            self.digits()?;
        }
        if matches!(self.b.get(self.i), Some(b'e' | b'E')) {
            integer = false;
            self.i += 1;
            if !self.eat(b'+') {
                self.eat(b'-');
            }
            self.digits()?;
        }
        let text = std::str::from_utf8(&self.b[start..self.i]).expect("ASCII number");
        if integer
            && let Ok(n) = text.parse::<i64>()
            && n.unsigned_abs() <= 1u64 << 53
        {
            return Ok(Json::Int(n));
        }
        let v: f64 = text.parse().expect("grammar checked");
        if v.is_infinite() {
            self.flags.overflow = true;
        }
        Ok(Json::Num(v))
    }

    fn hex4(&mut self) -> Result<u32> {
        let Some(h) = self.b.get(self.i..self.i + 4) else {
            return bad("short escape");
        };
        let mut v = 0;
        for c in h {
            let Some(d) = (*c as char).to_digit(16) else {
                return bad("bad escape");
            };
            v = v * 16 + d;
        }
        self.i += 4;
        Ok(v)
    }

    fn string(&mut self) -> Result<String> {
        self.i += 1;
        let mut out: Vec<u8> = Vec::new();
        loop {
            let Some(&c) = self.b.get(self.i) else {
                return bad("unterminated string");
            };
            self.i += 1;
            match c {
                b'"' => break,
                b'\\' => {
                    let Some(&e) = self.b.get(self.i) else {
                        return bad("unterminated escape");
                    };
                    self.i += 1;
                    let ch = match e {
                        b'"' => '"',
                        b'\\' => '\\',
                        b'/' => '/',
                        b'b' => '\u{8}',
                        b'f' => '\u{c}',
                        b'n' => '\n',
                        b'r' => '\r',
                        b't' => '\t',
                        b'u' => self.unicode_escape()?,
                        _ => return bad("bad escape"),
                    };
                    out.extend_from_slice(ch.encode_utf8(&mut [0; 4]).as_bytes());
                }
                0..=0x1f => return bad("control character in string"),
                _ => out.push(c),
            }
        }
        // The input was a &str and escapes were encoded, so this cannot fail.
        Ok(String::from_utf8(out).expect("valid UTF-8"))
    }

    fn unicode_escape(&mut self) -> Result<char> {
        let u = self.hex4()?;
        let code = if (0xD800..0xDC00).contains(&u) {
            if self.b[self.i..].starts_with(b"\\u") {
                let save = self.i;
                self.i += 2;
                let low = self.hex4()?;
                if (0xDC00..0xE000).contains(&low) {
                    0x10000 + ((u - 0xD800) << 10) + (low - 0xDC00)
                } else {
                    self.i = save;
                    self.flags.lone_surrogate = true;
                    0xFFFD
                }
            } else {
                self.flags.lone_surrogate = true;
                0xFFFD
            }
        } else if (0xDC00..0xE000).contains(&u) {
            self.flags.lone_surrogate = true;
            0xFFFD
        } else {
            u
        };
        Ok(char::from_u32(code).unwrap_or('\u{FFFD}'))
    }
}

impl Json {
    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Obj(o) => o.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[Json]> {
        match self {
            Json::Arr(a) => Some(a),
            _ => None,
        }
    }

    pub fn as_int(&self) -> Option<i64> {
        match self {
            Json::Int(n) => Some(*n),
            _ => None,
        }
    }

    pub fn as_f64(&self) -> Option<f64> {
        match self {
            Json::Int(n) => Some(*n as f64),
            Json::Num(v) => Some(*v),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Json::Str(s) => Some(s),
            _ => None,
        }
    }

    /// True if any number in the value is NaN or infinite.
    pub fn has_non_finite(&self) -> bool {
        match self {
            Json::Num(v) => !v.is_finite(),
            Json::Arr(a) => a.iter().any(Json::has_non_finite),
            Json::Obj(o) => o.iter().any(|(_, v)| v.has_non_finite()),
            _ => false,
        }
    }

    pub fn write(&self, out: &mut String) {
        match self {
            Json::Null => out.push_str("null"),
            Json::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
            Json::Int(n) => {
                let _ = write!(out, "{n}");
            }
            // Debug form is the shortest text that reads back to the same binary64.
            Json::Num(v) => {
                let _ = write!(out, "{v:?}");
            }
            Json::Str(s) => write_string(s, out),
            Json::Arr(a) => {
                out.push('[');
                for (i, v) in a.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    v.write(out);
                }
                out.push(']');
            }
            Json::Obj(o) => {
                out.push('{');
                for (i, (k, v)) in o.iter().enumerate() {
                    if i > 0 {
                        out.push(',');
                    }
                    write_string(k, out);
                    out.push(':');
                    v.write(out);
                }
                out.push('}');
            }
        }
    }

    pub fn to_text(&self) -> String {
        let mut s = String::new();
        self.write(&mut s);
        s
    }
}

fn write_string(s: &str, out: &mut String) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

impl From<f64> for Json {
    fn from(v: f64) -> Json {
        Json::Num(v)
    }
}
impl From<i64> for Json {
    fn from(v: i64) -> Json {
        Json::Int(v)
    }
}
impl From<bool> for Json {
    fn from(v: bool) -> Json {
        Json::Bool(v)
    }
}
impl From<&str> for Json {
    fn from(v: &str) -> Json {
        Json::Str(v.to_string())
    }
}
impl From<String> for Json {
    fn from(v: String) -> Json {
        Json::Str(v)
    }
}
impl<T: Into<Json>> From<Option<T>> for Json {
    fn from(v: Option<T>) -> Json {
        v.map_or(Json::Null, Into::into)
    }
}
impl<T: Into<Json>> From<Vec<T>> for Json {
    fn from(v: Vec<T>) -> Json {
        Json::Arr(v.into_iter().map(Into::into).collect())
    }
}

/// Builds an object from key and value pairs.
pub fn obj<const N: usize>(pairs: [(&str, Json); N]) -> Json {
    Json::Obj(pairs.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
}
