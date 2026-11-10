//! Units and exact money (`units-and-money.md`). Amounts are 128-bit integers of 1e-8 units.
use crate::error::{Result, fail};

const SCALE_PLACES: u32 = 8;

fn per_decimal(unit: &str) -> Option<f64> {
    match unit {
        "DECIMAL" => Some(1.0),
        "PERCENT" => Some(100.0),
        "BP" => Some(10_000.0),
        _ => None,
    }
}

pub fn convert(value: f64, from: &str, to: &str) -> Result<f64> {
    crate::error::finite("value", &value)?;
    match (per_decimal(from), per_decimal(to)) {
        (Some(a), Some(b)) if a == b => Ok(value),
        (Some(a), Some(b)) => Ok(value / a * b),
        _ => fail("E_SCHEMA", "unknown unit"),
    }
}

fn minor_places(currency: &str) -> Result<u32> {
    match currency {
        "GBP" | "USD" | "EUR" => Ok(2),
        "JPY" => Ok(0),
        _ => fail("E_SCHEMA", "unknown currency"),
    }
}

/// Splits an amount into sign, whole and fraction digits. Any other form is `E_SCHEMA`.
fn split(s: &str) -> Result<(bool, &str, &str)> {
    let (negative, body) = match s.strip_prefix('-') {
        Some(b) => (true, b),
        None => (false, s),
    };
    let (whole, fraction) = body.split_once('.').unwrap_or((body, ""));
    let digits = |t: &str| t.bytes().all(|b| b.is_ascii_digit());
    if whole.is_empty() || !digits(whole) || !digits(fraction) || body.ends_with('.') {
        return fail("E_SCHEMA", "malformed amount");
    }
    Ok((negative, whole, fraction))
}

/// Parses an amount already through `split`. Too many digits is `E_LIMIT`.
fn value(s: &str) -> Result<i128> {
    let (negative, whole, fraction) = split(s)?;
    if whole.len() > 18 || fraction.len() > SCALE_PLACES as usize {
        return fail("E_LIMIT", "amount has too many digits");
    }
    let padded = format!("{whole}{fraction:0<8}");
    let v: i128 = padded.parse().expect("digits only");
    Ok(if negative { -v } else { v })
}

fn shortest(v: i128) -> String {
    let (whole, fraction) = (v.abs() / 100_000_000, v.abs() % 100_000_000);
    let sign = if v < 0 { "-" } else { "" };
    let f = format!("{fraction:08}");
    let f = f.trim_end_matches('0');
    if f.is_empty() {
        format!("{sign}{whole}")
    } else {
        format!("{sign}{whole}.{f}")
    }
}

/// Returns the amount and currency.
pub fn add_money(a: &str, ac: &str, b: &str, bc: &str) -> Result<(String, String)> {
    minor_places(ac)?;
    minor_places(bc)?;
    split(a)?;
    split(b)?;
    let (x, y) = (value(a)?, value(b)?);
    if ac != bc {
        return fail("E_CURRENCY_MISMATCH", "currencies differ");
    }
    Ok((shortest(x + y), ac.to_string()))
}

/// Half to even at the currency's minor unit.
pub fn round_money(amount: &str, currency: &str) -> Result<(String, String)> {
    let places = minor_places(currency)?;
    let v = value(amount)?;
    let unit = 10i128.pow(SCALE_PLACES - places);
    let (mut q, r) = (v.div_euclid(unit), v.rem_euclid(unit));
    if 2 * r > unit || (2 * r == unit && q % 2 != 0) {
        q += 1;
    }
    let scale = 10i128.pow(places);
    let (whole, fraction) = (q.abs() / scale, q.abs() % scale);
    let sign = if q < 0 { "-" } else { "" };
    let text = if places == 0 {
        format!("{sign}{whole}")
    } else {
        format!("{sign}{whole}.{fraction:0width$}", width = places as usize)
    };
    Ok((text, currency.to_string()))
}
