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

    #[must_use]
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn leap_years_follow_gregorian_rule() {
        assert!(is_leap(2024) && is_leap(2000) && is_leap(1600));
        assert!(!is_leap(2023) && !is_leap(1900) && !is_leap(2100));
        assert_eq!(days_in_year(2000), 366);
        assert_eq!(days_in_year(1900), 365);
        assert_eq!(days_in_month(2024, 2), 29);
        assert_eq!(days_in_month(2023, 2), 28);
        assert_eq!(days_in_month(2023, 4), 30);
        assert_eq!(days_in_month(2023, 12), 31);
    }

    #[test]
    fn serial_round_trips_across_eras() {
        for n in (-800_000..800_000).step_by(997) {
            assert_eq!(Date::from_serial(n).serial(), n);
        }
        let d = Date::new(2024, 2, 28);
        assert_eq!(d.add_days(1), Date::new(2024, 2, 29));
        assert_eq!(d.add_days(2), Date::new(2024, 3, 1));
        assert_eq!(
            Date::new(2025, 1, 1).serial() - Date::new(2024, 1, 1).serial(),
            366
        );
    }

    #[test]
    fn weekdays_and_weekends() {
        // 1970-01-01 was a Thursday; 2024-06-15 a Saturday.
        assert_eq!(Date::new(1970, 1, 1).weekday(), 3);
        assert!(Date::new(2024, 6, 15).is_weekend());
        assert!(Date::new(2024, 6, 16).is_weekend());
        assert!(!Date::new(2024, 6, 17).is_weekend());
        assert!(Date::new(1600, 1, 1).weekday() < 7);
    }

    #[test]
    fn end_of_february() {
        assert!(Date::new(2024, 2, 29).is_end_of_february());
        assert!(!Date::new(2024, 2, 28).is_end_of_february());
        assert!(Date::new(2023, 2, 28).is_end_of_february());
        assert!(!Date::new(2023, 3, 31).is_end_of_february());
    }

    #[test]
    fn parse_accepts_only_valid_iso_dates() {
        assert_eq!(Date::parse("2024-02-29"), Some(Date::new(2024, 2, 29)));
        for bad in [
            "2023-02-29",
            "2024-13-01",
            "2024-00-10",
            "2024-01-00",
            "2024-1-01",
            "2024/01/01",
            "+024-01-01",
            "2024-01-011",
            "",
            "２024-01-01",
        ] {
            assert_eq!(Date::parse(bad), None, "{bad}");
        }
        assert_eq!(Date::new(7, 3, 4).to_string(), "0007-03-04");
        assert_eq!(fixed_digits("0042", 4), Some(42));
        assert_eq!(fixed_digits("42", 4), None);
        assert_eq!(fixed_digits("4a", 2), None);
    }
}
