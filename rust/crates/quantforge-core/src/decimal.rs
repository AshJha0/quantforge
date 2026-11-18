//! Exact decimals for prices, quantities and fees (ruling HR-12): an `i128` coefficient and a
//! power-of-ten scale, kept normalised (no trailing zeros in the coefficient), so equal values are
//! equal structurally. HR-57: a value `c * 10^-s` is in range when `|c| < 10^36` and `s <= 36`
//! (inputs: `s <= 18`); anything else is `E_LIMIT` (HR-58), never a wrapped or rounded result.
use crate::error::{Result, err};
use std::cmp::Ordering;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Dec {
    m: i128,
    s: u32,
}

const MAX_DIGITS: u32 = 36;
const MAX_SCALE: u32 = 36;
const MAX_INPUT_SCALE: usize = 18;
const LIMIT: i128 = 10i128.pow(MAX_DIGITS);

fn overflow() -> crate::error::QfError {
    err(
        "E_LIMIT",
        "decimal outside the exact range (36 digits, 36 decimals; HR-57)",
    )
}

fn pow10(n: u32) -> Option<i128> {
    10i128.checked_pow(n)
}

/// `|num| * 10^up / (den * 10^down)` for `den > 0`, `up` or `down` zero: the quotient of the
/// magnitudes (`None` once it reaches 10^36) and whether the remainder is non-zero. Long division
/// keeps every intermediate below 10^37, so in-range operands never overflow (HR-58).
fn div_mag(num: i128, up: u32, den: i128, down: u32) -> (Option<i128>, bool) {
    let num = num.abs();
    let Some(d) = pow10(down).and_then(|p| den.checked_mul(p)) else {
        return (Some(0), num != 0); // the divisor exceeds |num|
    };
    let mut q = Some(num / d);
    let mut r = num % d;
    for _ in 0..up {
        r *= 10;
        q = q.filter(|&x| x < LIMIT).map(|x| x * 10 + r / d);
        r %= d;
    }
    (q.filter(|&x| x < LIMIT), r != 0)
}

impl Dec {
    pub const ZERO: Dec = Dec { m: 0, s: 0 };

    fn norm(mut m: i128, mut s: u32) -> Result<Dec> {
        if m == 0 {
            return Ok(Dec::ZERO);
        }
        while s > 0 && m % 10 == 0 {
            m /= 10;
            s -= 1;
        }
        if s > MAX_SCALE || m >= LIMIT || m <= -LIMIT {
            return Err(overflow());
        }
        Ok(Dec { m, s })
    }

    pub fn int(n: i64) -> Dec {
        Dec::norm(i128::from(n), 0).expect("an i64 is in range")
    }

    /// Reads `-?[0-9]+(\.[0-9]+)?` exactly; `None` for any other text, `E_LIMIT` outside HR-57.
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
        let all = format!("{ip}{frac}");
        let sig = all.trim_start_matches('0').len();
        if frac.len() > MAX_INPUT_SCALE || sig > MAX_DIGITS as usize {
            return Some(Err(err(
                "E_LIMIT",
                "decimal string outside the input range (36 digits, 18 decimals; HR-57)",
            )));
        }
        let mut m: i128 = 0;
        for b in all.bytes() {
            m = m * 10 + i128::from(b - b'0');
        }
        let m = if body.len() == t.len() { m } else { -m };
        Some(Dec::norm(m, frac.len() as u32))
    }

    /// Both coefficients at the larger scale. An overflow means the exact sum is out of range too:
    /// the side scaled up is then at least 1.7e38 at the common scale and the other below 10^36.
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
        Dec::norm(a.checked_add(b).ok_or_else(overflow)?, s)
    }

    pub fn checked_sub(self, o: Dec) -> Result<Dec> {
        let (a, b, s) = self.align(o)?;
        Dec::norm(a.checked_sub(b).ok_or_else(overflow)?, s)
    }

    pub fn checked_mul(self, o: Dec) -> Result<Dec> {
        let (mut x, mut y, mut s) = (self.m, o.m, self.s + o.s);
        // An overflowing product may be in range once its trailing zeros go: cancel factors of
        // ten (a 5 from one side with a 2 from the other) while the scale allows (HR-58).
        loop {
            if let Some(m) = x.checked_mul(y) {
                return Dec::norm(m, s);
            }
            if s == 0 {
                return Err(overflow());
            }
            if x % 10 == 0 {
                x /= 10;
            } else if y % 10 == 0 {
                y /= 10;
            } else if x % 5 == 0 && y % 2 == 0 {
                (x, y) = (x / 5, y / 2);
            } else if x % 2 == 0 && y % 5 == 0 {
                (x, y) = (x / 2, y / 5);
            } else {
                return Err(overflow());
            }
            s -= 1;
        }
    }

    /// `floor(self / o)` (or the ceiling) as an integer, for `o > 0`.
    pub fn div_int(self, o: Dec, ceil: bool) -> Result<Dec> {
        let (q, rem) = div_mag(
            self.m,
            o.s.saturating_sub(self.s),
            o.m,
            self.s.saturating_sub(o.s),
        );
        let mut q = q.ok_or_else(overflow)?;
        if self.m < 0 {
            q = -q;
        }
        if rem && ceil && self.m > 0 {
            q += 1;
        }
        if rem && !ceil && self.m < 0 {
            q -= 1;
        }
        Dec::norm(q, 0)
    }

    /// True if `self` is an integer multiple of `unit` (`unit != 0`).
    pub fn on_grid(self, unit: Dec) -> Result<bool> {
        let (_, rem) = div_mag(
            self.m,
            unit.s.saturating_sub(self.s),
            unit.m.abs(),
            self.s.saturating_sub(unit.s),
        );
        Ok(!rem)
    }

    /// The value as `(c, s)` with `self == c * 10^-s` (normalised; `s <= 36`).
    pub fn parts(self) -> (i128, u32) {
        (self.m, self.s)
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
        let mut t = self.m.unsigned_abs().to_string();
        t.push_str(&"0".repeat((places - self.s) as usize));
        let p = places as usize;
        if t.len() <= p {
            t = format!("{}{t}", "0".repeat(p + 1 - t.len()));
        }
        if p > 0 {
            t.insert(t.len() - p, '.');
        }
        Some(if self.m < 0 { format!("-{t}") } else { t })
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

    #[test]
    fn exact_range_hr57_hr58() {
        let limit = |r: crate::error::Result<Dec>| r.is_err_and(|e| e.code == "E_LIMIT");
        let big = "123456789012345678.123456789012345678";
        assert_eq!(d(big).to_string(), big);
        assert_eq!(d("1.000000000000000000000").to_string(), "1");
        assert!(limit(Dec::parse("0.0000000000000000001").expect("form")));
        assert!(limit(
            Dec::parse(&format!("1{}", "0".repeat(36))).expect("form")
        ));
        // 5^50 * 10^-18 times 2^50 * 10^-18: the coefficients overflow 128 bits, the value is 10^14.
        let p = d("88817841970012523.233890533447265625");
        assert_eq!(
            p.checked_mul(d("0.001125899906842624")).expect("mul"),
            d("100000000000000")
        );
        assert!(limit(
            d(&format!("1{}", "0".repeat(35))).checked_mul(d("10"))
        ));
        let (e30, tiny) = (
            d(&format!("1{}", "0".repeat(30))),
            d("0.000000000000000001"),
        );
        assert!(e30.on_grid(tiny).expect("grid") && !tiny.on_grid(e30).expect("grid"));
        assert!(tiny < e30);
        assert_eq!(e30.cmp(&tiny), std::cmp::Ordering::Greater);
        assert!(limit(d("1000000000000000000").div_int(tiny, false)));
        assert_eq!(
            d("7")
                .div_int(d("0.000000000000000002"), true)
                .expect("div"),
            d("3500000000000000000")
        );
        assert_eq!(
            e30.fixed(18).as_deref(),
            Some("1000000000000000000000000000000.000000000000000000")
        );
    }
}
