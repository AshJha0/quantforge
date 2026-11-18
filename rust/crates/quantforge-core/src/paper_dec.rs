//! Decimal arithmetic as the Python reference does it for paper trading: Python `decimal` with
//! its default context (28 significant digits, `ROUND_HALF_EVEN`). Inputs are held exactly; every
//! sum, difference, product and quotient is the exact result rounded to 28 significant digits, so
//! an average cost such as 301/3 carries the same last digit as the Python build
//! (`specifications/10-execution/paper-trading.md`, HR-44). Digits are kept in a little-endian
//! base-10 vector: the values are small and the code stays obviously right.
// Value-returning arithmetic, as the operators of Python `decimal`.
#![allow(clippy::return_self_not_must_use)]
use crate::error::{Result, err};
use std::cmp::Ordering;

/// Python's default context precision.
pub const PREC: usize = 28;
/// Largest input exponent accepted (Python has none; this bounds the digit vectors).
const MAX_EXP: i64 = 4000;

/// `(-1)^neg * mag * 10^exp`, normalised: no zero digit at either end of `mag`, zero is
/// `mag` empty with `neg` false and `exp` 0. Equal values are equal structurally.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PyDec {
    neg: bool,
    mag: Vec<u8>,
    exp: i64,
}

fn trim_hi(v: &mut Vec<u8>) {
    while v.last() == Some(&0) {
        v.pop();
    }
}

fn mag_cmp(a: &[u8], b: &[u8]) -> Ordering {
    a.len()
        .cmp(&b.len())
        .then_with(|| a.iter().rev().cmp(b.iter().rev()))
}

fn mag_add(a: &[u8], b: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(a.len().max(b.len()) + 1);
    let mut carry = 0u8;
    for k in 0..a.len().max(b.len()) {
        let t = a.get(k).copied().unwrap_or(0) + b.get(k).copied().unwrap_or(0) + carry;
        out.push(t % 10);
        carry = t / 10;
    }
    if carry > 0 {
        out.push(carry);
    }
    out
}

/// `a - b` for `a >= b`.
fn mag_sub(a: &[u8], b: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(a.len());
    let mut borrow = 0i8;
    for (k, &x) in a.iter().enumerate() {
        let mut t = x as i8 - b.get(k).copied().unwrap_or(0) as i8 - borrow;
        borrow = 0;
        if t < 0 {
            t += 10;
            borrow = 1;
        }
        out.push(t as u8);
    }
    trim_hi(&mut out);
    out
}

fn mag_mul(a: &[u8], b: &[u8]) -> Vec<u8> {
    if a.is_empty() || b.is_empty() {
        return Vec::new();
    }
    let mut acc = vec![0u64; a.len() + b.len()];
    for (i, &x) in a.iter().enumerate() {
        for (j, &y) in b.iter().enumerate() {
            acc[i + j] += u64::from(x) * u64::from(y);
        }
    }
    let mut out = Vec::with_capacity(acc.len());
    let mut carry = 0u64;
    for t in acc {
        let t = t + carry;
        out.push((t % 10) as u8);
        carry = t / 10;
    }
    while carry > 0 {
        out.push((carry % 10) as u8);
        carry /= 10;
    }
    trim_hi(&mut out);
    out
}

fn shifted(v: &[u8], k: usize) -> Vec<u8> {
    let mut out = vec![0u8; k];
    out.extend_from_slice(v);
    out
}

impl PyDec {
    pub fn zero() -> PyDec {
        PyDec {
            neg: false,
            mag: Vec::new(),
            exp: 0,
        }
    }

    fn make(neg: bool, mut mag: Vec<u8>, mut exp: i64) -> PyDec {
        trim_hi(&mut mag);
        if mag.is_empty() {
            return PyDec::zero();
        }
        let low = mag.iter().take_while(|&&d| d == 0).count();
        mag.drain(..low);
        exp += low as i64;
        PyDec { neg, mag, exp }
    }

    /// Drops the `drop` lowest digits, rounding half-even; `sticky` marks a non-zero tail below.
    fn round_at(neg: bool, mut mag: Vec<u8>, exp: i64, drop: usize, sticky: bool) -> PyDec {
        if drop == 0 {
            return PyDec::make(neg, mag, exp);
        }
        if mag.len() < drop + 1 {
            mag.resize(drop + 1, 0);
        }
        let rd = mag[drop - 1];
        let below = sticky || mag[..drop - 1].iter().any(|&d| d != 0);
        let mut kept = mag[drop..].to_vec();
        let odd = kept.first().is_some_and(|d| d % 2 == 1);
        if rd > 5 || (rd == 5 && (below || odd)) {
            let mut k = 0;
            loop {
                if k == kept.len() {
                    kept.push(1);
                    break;
                }
                if kept[k] == 9 {
                    kept[k] = 0;
                    k += 1;
                } else {
                    kept[k] += 1;
                    break;
                }
            }
        }
        PyDec::make(neg, kept, exp + drop as i64)
    }

    fn rounded(neg: bool, mut mag: Vec<u8>, exp: i64, sticky: bool) -> PyDec {
        trim_hi(&mut mag);
        let drop = mag.len().saturating_sub(PREC);
        PyDec::round_at(neg, mag, exp, drop, sticky)
    }

    pub fn int(n: i64) -> PyDec {
        let mut mag = Vec::new();
        let mut u = n.unsigned_abs();
        while u > 0 {
            mag.push((u % 10) as u8);
            u /= 10;
        }
        PyDec::make(n < 0, mag, 0)
    }

    /// Python `Decimal(text)`: `None` when the text is not a decimal (`E_PARSE` for the caller),
    /// `Some(Err(E_SCHEMA))` for a non-finite token (HR-12, ruling F-2a).
    pub fn parse(text: &str) -> Option<Result<PyDec>> {
        let t = text.trim();
        let (neg, body) = match t.as_bytes().first() {
            Some(b'-') => (true, &t[1..]),
            Some(b'+') => (false, &t[1..]),
            _ => (false, t),
        };
        let low = body.to_ascii_lowercase();
        let nan_tail = |p: &str| {
            low.strip_prefix(p)
                .is_some_and(|r| r.bytes().all(|b| b.is_ascii_digit()))
        };
        if low == "inf" || low == "infinity" || nan_tail("nan") || nan_tail("snan") {
            return Some(Err(err(
                "E_SCHEMA",
                format!("{text:?} is not a finite decimal"),
            )));
        }
        let (num, e) = match low.find('e') {
            Some(k) => (&low[..k], Some(&low[k + 1..])),
            None => (low.as_str(), None),
        };
        let (ip, fp) = num.split_once('.').unwrap_or((num, ""));
        let digits = |x: &str| x.bytes().all(|b| b.is_ascii_digit());
        if ip.len() + fp.len() == 0 || !digits(ip) || !digits(fp) {
            return None;
        }
        let mut exp: i64 = 0;
        if let Some(e) = e {
            let es = e.strip_prefix(['+', '-']).unwrap_or(e);
            if es.is_empty() || !digits(es) {
                return None;
            }
            let v: i64 = es.parse().unwrap_or(i64::MAX);
            if v > MAX_EXP {
                return Some(Err(err("E_LIMIT", "decimal exponent out of range")));
            }
            exp = if e.starts_with('-') { -v } else { v };
        }
        let mag: Vec<u8> = ip
            .bytes()
            .chain(fp.bytes())
            .rev()
            .map(|b| b - b'0')
            .collect();
        Some(Ok(PyDec::make(neg, mag, exp - fp.len() as i64)))
    }

    pub fn is_zero(&self) -> bool {
        self.mag.is_empty()
    }

    pub fn is_neg(&self) -> bool {
        self.neg
    }

    pub fn is_pos(&self) -> bool {
        !self.neg && !self.mag.is_empty()
    }

    /// Python `+x`: the value rounded to the context.
    pub fn plus(&self) -> PyDec {
        PyDec::rounded(self.neg, self.mag.clone(), self.exp, false)
    }

    pub fn neg(&self) -> PyDec {
        let mut r = self.plus();
        if !r.is_zero() {
            r.neg = !r.neg;
        }
        r
    }

    pub fn abs(&self) -> PyDec {
        let mut r = self.plus();
        r.neg = false;
        r
    }

    pub fn add(&self, o: &PyDec) -> PyDec {
        let e = self.exp.min(o.exp);
        let a = shifted(&self.mag, (self.exp - e) as usize);
        let b = shifted(&o.mag, (o.exp - e) as usize);
        if self.neg == o.neg {
            return PyDec::rounded(self.neg, mag_add(&a, &b), e, false);
        }
        let (mut a, mut b) = (a, b);
        trim_hi(&mut a);
        trim_hi(&mut b);
        match mag_cmp(&a, &b) {
            Ordering::Equal => PyDec::zero(),
            Ordering::Greater => PyDec::rounded(self.neg, mag_sub(&a, &b), e, false),
            Ordering::Less => PyDec::rounded(o.neg, mag_sub(&b, &a), e, false),
        }
    }

    pub fn sub(&self, o: &PyDec) -> PyDec {
        let mut m = o.clone();
        if !m.is_zero() {
            m.neg = !m.neg;
        }
        self.add(&m)
    }

    pub fn mul(&self, o: &PyDec) -> PyDec {
        PyDec::rounded(
            self.neg != o.neg,
            mag_mul(&self.mag, &o.mag),
            self.exp + o.exp,
            false,
        )
    }

    pub fn div(&self, o: &PyDec) -> Result<PyDec> {
        if o.is_zero() {
            return Err(err("E_DOMAIN", "division by zero"));
        }
        if self.is_zero() {
            return Ok(PyDec::zero());
        }
        let k = (PREC + 3 + o.mag.len()).saturating_sub(self.mag.len());
        let a = shifted(&self.mag, k);
        let mut q: Vec<u8> = Vec::with_capacity(a.len());
        let mut rem: Vec<u8> = Vec::new();
        for &d in a.iter().rev() {
            rem.insert(0, d);
            trim_hi(&mut rem);
            let mut c = 0u8;
            while mag_cmp(&rem, &o.mag) != Ordering::Less {
                rem = mag_sub(&rem, &o.mag);
                c += 1;
            }
            q.push(c);
        }
        q.reverse();
        let exp = self.exp - o.exp - k as i64;
        Ok(PyDec::rounded(self.neg != o.neg, q, exp, !rem.is_empty()))
    }

    /// Python `quantize(Decimal(10) ** places_exp, ROUND_HALF_EVEN)`.
    pub fn quantize(&self, exp: i64) -> PyDec {
        if self.exp >= exp {
            return self.clone();
        }
        PyDec::round_at(
            self.neg,
            self.mag.clone(),
            self.exp,
            (exp - self.exp) as usize,
            false,
        )
    }

    /// The exact value as plain text: no exponent, no trailing zeros, "0" for zero.
    pub fn plain(&self) -> String {
        if self.is_zero() {
            return "0".into();
        }
        let mut digits: String = self
            .mag
            .iter()
            .rev()
            .map(|d| char::from(b'0' + d))
            .collect();
        if self.exp >= 0 {
            digits.push_str(&"0".repeat(self.exp as usize));
        } else {
            let f = (-self.exp) as usize;
            if digits.len() <= f {
                digits = format!("{}{digits}", "0".repeat(f + 1 - digits.len()));
            }
            digits.insert(digits.len() - f, '.');
        }
        if self.neg {
            format!("-{digits}")
        } else {
            digits
        }
    }

    /// The reference `fmt`: `normalize()` (rounds to 28 digits) written without exponent (HR-12).
    pub fn fmt(&self) -> String {
        self.plus().plain()
    }

    /// The nearest binary64 (Python `float(Decimal)`).
    pub fn to_f64(&self) -> f64 {
        self.plain().parse().unwrap_or(f64::NAN)
    }
}

impl Ord for PyDec {
    fn cmp(&self, o: &PyDec) -> Ordering {
        let d = self.sub(o);
        if d.is_zero() {
            Ordering::Equal
        } else if d.neg {
            Ordering::Less
        } else {
            Ordering::Greater
        }
    }
}

impl PartialOrd for PyDec {
    fn partial_cmp(&self, o: &PyDec) -> Option<Ordering> {
        Some(self.cmp(o))
    }
}

#[cfg(test)]
mod tests {
    use super::PyDec;

    fn d(t: &str) -> PyDec {
        PyDec::parse(t).and_then(Result::ok).expect("decimal")
    }

    #[test]
    fn exact_and_context_rounding() {
        assert_eq!(d("100.500").fmt(), "100.5");
        assert_eq!(d("-0.00").fmt(), "0");
        assert_eq!(d("1E+2").fmt(), "100");
        assert_eq!(d(".5").fmt(), "0.5");
        assert!(PyDec::parse("abc").is_none() && PyDec::parse("").is_none());
        for t in ["NaN", "Infinity", "-Infinity", "inf", "sNaN"] {
            assert!(PyDec::parse(t).is_some_and(|r| r.is_err_and(|e| e.code == "E_SCHEMA")));
        }
        assert_eq!(d("0.1").add(&d("0.2")), d("0.3"));
        assert_eq!(d("1").sub(&d("1.5")).fmt(), "-0.5");
        assert_eq!(d("1.5").mul(&d("-0.2")).fmt(), "-0.3");
        // Python: Decimal(301) / 3 and Decimal(2) / 3 (28 digits, half-even).
        assert_eq!(
            d("301").div(&d("3")).expect("div").fmt(),
            "100.3333333333333333333333333"
        );
        assert_eq!(
            d("2").div(&d("3")).expect("div").fmt(),
            "0.6666666666666666666666666667"
        );
        assert_eq!(d("201").div(&d("2")).expect("div").fmt(), "100.5");
        // Python: Decimal("1234567890123456789012345678.5") + 0 rounds half-even to ...678
        assert_eq!(
            d("1234567890123456789012345678.5").plus().fmt(),
            "1234567890123456789012345678"
        );
        assert_eq!(
            d("1234567890123456789012345677.5").plus().fmt(),
            "1234567890123456789012345678"
        );
        assert_eq!(d("0.990969").quantize(-2).fmt(), "0.99");
        assert_eq!(d("0.005").quantize(-2).fmt(), "0");
        assert_eq!(d("0.015").quantize(-2).fmt(), "0.02");
        assert_eq!(d("-0.6").quantize(-2).fmt(), "-0.6");
        assert!(d("2") > d("1.99") && d("-1") < d("0"));
        assert_eq!(d("0.30000000000000004").to_f64(), 0.1 + 0.2);
        assert_eq!(PyDec::int(-365).fmt(), "-365");
    }
}
