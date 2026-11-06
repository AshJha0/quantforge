//! Proleptic Gregorian dates.
use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Date {
    pub y: i32,
    pub m: u32,
    pub d: u32,
}

pub fn is_leap(y: i32) -> bool {
    (y % 4 == 0 && y % 100 != 0) || y % 400 == 0
}

pub fn days_in_year(y: i32) -> i64 {
    if is_leap(y) { 366 } else { 365 }
}

pub fn days_in_month(y: i32, m: u32) -> u32 {
    match m {
        2 if is_leap(y) => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    }
}

/// Parses a string of ASCII digits of exactly `len` characters.
pub fn fixed_digits(s: &str, len: usize) -> Option<i64> {
    if s.len() == len && s.bytes().all(|b| b.is_ascii_digit()) {
        s.parse().ok()
    } else {
        None
    }
}

impl Date {
    pub fn new(y: i32, m: u32, d: u32) -> Date {
        Date { y, m, d }
    }

    /// Days since 1970-01-01.
    pub fn serial(self) -> i64 {
        let y = i64::from(self.y) - i64::from(self.m <= 2);
        let era = y.div_euclid(400);
        let yoe = y.rem_euclid(400);
        let mp = (i64::from(self.m) + 9) % 12;
        let doy = (153 * mp + 2) / 5 + i64::from(self.d) - 1;
        let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
        era * 146097 + doe - 719468
    }

    pub fn from_serial(n: i64) -> Date {
        let z = n + 719468;
        let era = z.div_euclid(146097);
        let doe = z.rem_euclid(146097);
        let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
        let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
        let mp = (5 * doy + 2) / 153;
        let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
        let m = (if mp < 10 { mp + 3 } else { mp - 9 }) as u32;
        let y = yoe + era * 400 + i64::from(m <= 2);
        Date::new(y as i32, m, d)
    }

    /// 0 is Monday, 6 is Sunday.
    pub fn weekday(self) -> i64 {
        (self.serial() + 3).rem_euclid(7)
    }

    pub fn is_weekend(self) -> bool {
        self.weekday() >= 5
    }

    pub fn add_days(self, n: i64) -> Date {
        Date::from_serial(self.serial() + n)
    }

    pub fn is_end_of_february(self) -> bool {
        self.m == 2 && self.d == days_in_month(self.y, 2)
    }

    pub fn parse(s: &str) -> Option<Date> {
        let b = s.as_bytes();
        if b.len() != 10 || b[4] != b'-' || b[7] != b'-' {
            return None;
        }
        let y = fixed_digits(s.get(0..4)?, 4)? as i32;
        let m = fixed_digits(s.get(5..7)?, 2)? as u32;
        let d = fixed_digits(s.get(8..10)?, 2)? as u32;
        if m < 1 || m > 12 || d < 1 || d > days_in_month(y, m) {
            return None;
        }
        Some(Date::new(y, m, d))
    }
}

impl fmt::Display for Date {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:04}-{:02}-{:02}", self.y, self.m, self.d)
    }
}
