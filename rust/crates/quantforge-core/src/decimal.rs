//! Exact decimals for prices, quantities and fees (ruling HR-12): an `i128` coefficient and a
//! power-of-ten scale, kept normalised (no trailing zeros in the coefficient), so equal values are
//! equal structurally. Overflow is `E_LIMIT`, never a wrapped or rounded result.
use crate::error::{Result, err};
use std::cmp::Ordering;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Dec {
    m: i128,
    s: u32,
}

fn overflow() -> crate::error::QfError {
    err("E_LIMIT", "decimal value out of the exact range")
}

fn pow10(n: u32) -> Option<i128> {
    10i128.checked_pow(n)
}

impl Dec {
    pub const ZERO: Dec = Dec { m: 0, s: 0 };

    fn norm(mut m: i128, mut s: u32) -> Dec {
        if m == 0 {
            return Dec::ZERO;
        }
        while s > 0 && m % 10 == 0 {
            m /= 10;
            s -= 1;
        }
        Dec { m, s }
    }

    pub fn int(n: i64) -> Dec {
        Dec::norm(i128::from(n), 0)
    }

    /// Reads `-?[0-9]+(\.[0-9]+)?` exactly; `None` for any other text.
    pub fn parse(t: &str) -> Option<Result<Dec>> {
        let body = t.strip_prefix('-').unwrap_or(t);
        let (ip, fp) = match body.split_once('.') {
            Some((a, b)) => (a, Some(b)),
            None => (body, None),
        };
        let digits = |x: &str| !x.is_empty() && x.bytes().all(|b| b.is_ascii_digit());
        if !digits(ip) || fp.is_some_and(|f| !digits(f)) {
            return None;
        }
        let frac = fp.unwrap_or("").trim_end_matches('0');
        let ip = ip.trim_start_matches('0');
        let mut m: i128 = 0;
        for b in ip.bytes().chain(frac.bytes()) {
            let Some(v) = m
                .checked_mul(10)
                .and_then(|x| x.checked_add(i128::from(b - b'0')))
            else {
                return Some(Err(overflow()));
            };
            m = v;
        }
        let m = if body.len() == t.len() { m } else { -m };
        Some(Ok(Dec::norm(m, frac.len() as u32)))
    }

    /// Both coefficients at the larger scale.
    fn align(self, o: Dec) -> Result<(i128, i128, u32)> {
        let s = self.s.max(o.s);
        let up = |d: Dec| {
            pow10(s - d.s)
                .and_then(|p| d.m.checked_mul(p))
                .ok_or_else(overflow)
        };
        Ok((up(self)?, up(o)?, s))
    }

    pub fn checked_add(self, o: Dec) -> Result<Dec> {
        let (a, b, s) = self.align(o)?;
        Ok(Dec::norm(a.checked_add(b).ok_or_else(overflow)?, s))
    }

    pub fn checked_sub(self, o: Dec) -> Result<Dec> {
        let (a, b, s) = self.align(o)?;
        Ok(Dec::norm(a.checked_sub(b).ok_or_else(overflow)?, s))
    }

    pub fn checked_mul(self, o: Dec) -> Result<Dec> {
        let m = self.m.checked_mul(o.m).ok_or_else(overflow)?;
        Ok(Dec::norm(m, self.s + o.s))
    }

    /// `floor(self / o)` (or the ceiling) as an integer, for `o > 0`.
    pub fn div_int(self, o: Dec, ceil: bool) -> Result<Dec> {
        let (a, b, _) = self.align(o)?;
        let q = a.div_euclid(b);
        let q = if ceil && a.rem_euclid(b) != 0 {
            q + 1
        } else {
            q
        };
        Ok(Dec::norm(q, 0))
    }

    /// True if `self` is an integer multiple of `unit` (`unit > 0`).
    pub fn on_grid(self, unit: Dec) -> Result<bool> {
        let (a, b, _) = self.align(unit)?;
        Ok(a % b == 0)
    }

    pub fn is_zero(self) -> bool {
        self.m == 0
    }

    pub fn signum(self) -> i32 {
        self.m.signum() as i32
    }

    /// Fixed-point text with exactly `places` fraction digits, or `None` if the value has more.
    pub fn fixed(self, places: u32) -> Option<String> {
        if self.s > places {
            return None;
        }
        let m = self.m.checked_mul(pow10(places - self.s)?)?;
        let mut t = m.unsigned_abs().to_string();
        let p = places as usize;
        if t.len() <= p {
            t = format!("{}{t}", "0".repeat(p + 1 - t.len()));
        }
        if p > 0 {
            t.insert(t.len() - p, '.');
        }
        Some(if m < 0 { format!("-{t}") } else { t })
    }
}

impl Default for Dec {
    fn default() -> Dec {
        Dec::ZERO
    }
}

impl Ord for Dec {
    fn cmp(&self, o: &Dec) -> Ordering {
        match self.align(*o) {
            Ok((a, b, _)) => a.cmp(&b),
            // Only the side scaled up can overflow; a nonzero value that large dominates.
            Err(_) => {
                if self.s < o.s {
                    self.m.signum().cmp(&0)
                } else {
                    0.cmp(&o.m.signum())
                }
            }
        }
    }
}

impl PartialOrd for Dec {
    fn partial_cmp(&self, o: &Dec) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}

/// No exponent, no trailing zeros, "0" for zero (HR-12).
impl std::fmt::Display for Dec {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self.fixed(self.s) {
            Some(t) => f.write_str(&t),
            None => Err(std::fmt::Error),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::Dec;

    fn d(t: &str) -> Dec {
        Dec::parse(t).and_then(Result::ok).expect("decimal")
    }

    #[test]
    fn parse_format_and_arithmetic() {
        assert_eq!(d("100.500").to_string(), "100.5");
        assert_eq!(d("-0.00").to_string(), "0");
        assert_eq!(d("007").to_string(), "7");
        assert!(Dec::parse("1e3").is_none() && Dec::parse("1.").is_none());
        assert!(Dec::parse("").is_none() && Dec::parse("+1").is_none());
        assert_eq!(d("0.1").checked_add(d("0.2")).expect("add"), d("0.3"));
        assert_eq!(
            d("1.5").checked_mul(d("-0.2")).expect("mul").to_string(),
            "-0.3"
        );
        assert_eq!(d("201").div_int(d("2"), false).expect("div"), d("100"));
        assert_eq!(d("201").div_int(d("2"), true).expect("div"), d("101"));
        assert!(d("1.5").on_grid(d("0.5")).expect("grid"));
        assert!(!d("1.5").on_grid(d("1")).expect("grid"));
        assert!(d("2") > d("1.99") && d("-1") < d("0"));
        assert_eq!(d("0.000123").fixed(8).as_deref(), Some("0.00012300"));
        assert_eq!(d("0.000123").fixed(3), None);
        assert!(Dec::parse(&"9".repeat(60)).is_some_and(|r| r.is_err()));
    }
}
