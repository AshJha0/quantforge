//! Typed reads of a case's `inputs`. Every failure here is `E_SCHEMA`.
use quantforge_core::calendar::{Bdc, Calendar};
use quantforge_core::dates::Date;
use quantforge_core::error::{QfError, Result, err};
use quantforge_core::json::Json;
use quantforge_core::time::{Zone, parse_instant, parse_local};

/// The inputs, and the `E_LIMIT` they break, if any.
pub struct Inputs<'a>(pub &'a Json, pub Option<QfError>);

fn schema(field: &str, what: &str) -> QfError {
    let mut e = err("E_SCHEMA", format!("{field}: {what}"));
    e.field = Some(field.to_string());
    e
}

fn real(v: &Json, k: &str) -> Result<f64> {
    v.as_f64().ok_or_else(|| schema(k, "expected a number"))
}

fn real_or_null(v: &Json, k: &str) -> Result<Option<f64>> {
    match v {
        Json::Null => Ok(None),
        _ => real(v, k).map(Some),
    }
}

pub fn parse_u64(v: &Json, k: &str) -> Result<u64> {
    let s = v
        .as_str()
        .ok_or_else(|| schema(k, "expected a u64 string"))?;
    if s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()) {
        return Err(schema(k, "expected a decimal u64 string"));
    }
    s.parse().map_err(|_| schema(k, "does not fit 64 bits"))
}

impl<'a> Inputs<'a> {
    pub fn new(v: &'a Json) -> Inputs<'a> {
        Inputs(v, None)
    }

    /// Called after the typed reads and before costly work. Reads come first, as `E_SCHEMA`
    /// outranks `E_LIMIT`.
    pub fn gate(&self) -> Result<()> {
        self.1.clone().map_or(Ok(()), Err)
    }

    /// The value of a key. A `null` counts as absent.
    pub fn opt(&self, k: &str) -> Option<&'a Json> {
        self.0.get(k).filter(|v| **v != Json::Null)
    }

    pub fn req(&self, k: &str) -> Result<&'a Json> {
        self.opt(k).ok_or_else(|| schema(k, "is required"))
    }

    pub fn f64(&self, k: &str) -> Result<f64> {
        real(self.req(k)?, k)
    }

    pub fn f64_or(&self, k: &str, default: f64) -> Result<f64> {
        self.opt(k).map_or(Ok(default), |v| real(v, k))
    }

    pub fn opt_f64(&self, k: &str) -> Result<Option<f64>> {
        self.opt(k).map(|v| real(v, k)).transpose()
    }

    pub fn int(&self, k: &str) -> Result<i64> {
        self.req(k)?
            .as_int()
            .ok_or_else(|| schema(k, "expected an integer"))
    }

    pub fn opt_int(&self, k: &str) -> Result<Option<i64>> {
        self.opt(k)
            .map(|v| v.as_int().ok_or_else(|| schema(k, "expected an integer")))
            .transpose()
    }

    pub fn int_or(&self, k: &str, default: i64) -> Result<i64> {
        Ok(self.opt_int(k)?.unwrap_or(default))
    }

    pub fn bool(&self, k: &str) -> Result<bool> {
        self.req(k)?;
        self.bool_or(k, false)
    }

    pub fn bool_or(&self, k: &str, default: bool) -> Result<bool> {
        match self.opt(k) {
            None => Ok(default),
            Some(Json::Bool(b)) => Ok(*b),
            Some(_) => Err(schema(k, "expected a boolean")),
        }
    }

    pub fn str(&self, k: &str) -> Result<&'a str> {
        self.req(k)?
            .as_str()
            .ok_or_else(|| schema(k, "expected a string"))
    }

    pub fn array(&self, k: &str) -> Result<&'a [Json]> {
        self.req(k)?
            .as_array()
            .ok_or_else(|| schema(k, "expected an array"))
    }

    pub fn reals(&self, k: &str) -> Result<Vec<f64>> {
        self.array(k)?.iter().map(|v| real(v, k)).collect()
    }

    /// An array whose items may be `null`.
    pub fn nullable_reals(&self, k: &str) -> Result<Vec<Option<f64>>> {
        self.array(k)?.iter().map(|v| real_or_null(v, k)).collect()
    }

    pub fn matrix(&self, k: &str) -> Result<Vec<Vec<f64>>> {
        self.array(k)?
            .iter()
            .map(|row| {
                row.as_array()
                    .ok_or_else(|| schema(k, "expected an array of rows"))?
                    .iter()
                    .map(|v| real(v, k))
                    .collect()
            })
            .collect()
    }

    pub fn date(&self, k: &str) -> Result<Date> {
        Date::parse(self.str(k)?).ok_or_else(|| schema(k, "expected a date"))
    }

    pub fn opt_date(&self, k: &str) -> Result<Option<Date>> {
        self.opt(k).map(|_| self.date(k)).transpose()
    }

    pub fn dates(&self, k: &str) -> Result<Vec<Date>> {
        self.array(k)?
            .iter()
            .map(|v| {
                v.as_str()
                    .and_then(Date::parse)
                    .ok_or_else(|| schema(k, "expected a date"))
            })
            .collect()
    }

    pub fn instant(&self, k: &str) -> Result<i64> {
        parse_instant(self.str(k)?).ok_or_else(|| schema(k, "expected an instant"))
    }

    pub fn local(&self, k: &str) -> Result<i64> {
        parse_local(self.str(k)?).ok_or_else(|| schema(k, "expected a local time"))
    }

    pub fn calendar(&self, k: &str) -> Result<Calendar> {
        Calendar::parse(self.str(k)?).ok_or_else(|| schema(k, "unknown calendar"))
    }

    pub fn zone(&self, k: &str) -> Result<Zone> {
        Zone::parse(self.str(k)?).ok_or_else(|| schema(k, "unknown zone"))
    }

    pub fn bdc(&self, k: &str) -> Result<Bdc> {
        Bdc::parse(self.str(k)?).ok_or_else(|| schema(k, "unknown convention"))
    }

    /// True for `CALL`, false for `PUT`.
    pub fn option(&self) -> Result<bool> {
        match self.str("option")? {
            "CALL" => Ok(true),
            "PUT" => Ok(false),
            _ => Err(schema("option", "unknown option type")),
        }
    }

    pub fn seed(&self) -> Result<u64> {
        parse_u64(self.req("seed")?, "seed")
    }

    /// `stream`, 0 to 1023, default 0.
    pub fn stream(&self) -> Result<u32> {
        let s = self.int_or("stream", 0)?;
        if !(0..=1023).contains(&s) {
            return Err(schema("stream", "out of range"));
        }
        Ok(s as u32)
    }

    // A method so call sites read `i.fail(key, why)` beside the other field accessors.
    #[allow(clippy::unused_self)]
    pub fn fail<T>(&self, k: &str, what: &str) -> Result<T> {
        Err(schema(k, what))
    }
}
