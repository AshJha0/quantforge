//! QuantForge Rust implementation.

/// A proleptic Gregorian calendar date.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Date {
    year: i32,
    month: u32,
    day: u32,
}

impl Date {
    /// Returns an error if the month and day do not form a real date.
    pub fn new(year: i32, month: u32, day: u32) -> Result<Self, DayCountError> {
        let leap = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0;
        let last = match month {
            1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
            4 | 6 | 9 | 11 => 30,
            2 if leap => 29,
            2 => 28,
            _ => return Err(DayCountError::InvalidDate),
        };
        if day == 0 || day > last {
            return Err(DayCountError::InvalidDate);
        }
        Ok(Self { year, month, day })
    }

    /// Days since 1970-01-01.
    fn epoch_days(self) -> i64 {
        let m = i64::from(self.month);
        let y = i64::from(self.year) - i64::from(m <= 2);
        let era = y.div_euclid(400);
        let yoe = y.rem_euclid(400);
        let mp = (m + 9) % 12;
        let doy = (153 * mp + 2) / 5 + i64::from(self.day) - 1;
        let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
        era * 146_097 + doe - 719_468
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct YearFraction {
    pub value: f64,
    pub convention: &'static str,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DayCountError {
    InvalidDate,
    ReversedDates,
}

fn days(start: Date, end: Date) -> Result<i64, DayCountError> {
    let n = end.epoch_days() - start.epoch_days();
    if n < 0 {
        return Err(DayCountError::ReversedDates);
    }
    Ok(n)
}

pub fn act_360(start: Date, end: Date) -> Result<YearFraction, DayCountError> {
    Ok(YearFraction {
        value: days(start, end)? as f64 / 360.0,
        convention: "ACT/360",
    })
}

pub fn act_365f(start: Date, end: Date) -> Result<YearFraction, DayCountError> {
    Ok(YearFraction {
        value: days(start, end)? as f64 / 365.0,
        convention: "ACT/365F",
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn d(y: i32, m: u32, day: u32) -> Date {
        Date::new(y, m, day).unwrap()
    }

    #[test]
    fn act_360_example() {
        let yf = act_360(d(2025, 1, 1), d(2025, 1, 31)).unwrap();
        assert!((yf.value - 30.0 / 360.0).abs() < 1e-14);
    }

    #[test]
    fn act_365f_spans_a_leap_day() {
        let yf = act_365f(d(2024, 2, 28), d(2024, 3, 1)).unwrap();
        assert!((yf.value - 2.0 / 365.0).abs() < 1e-14);
    }

    #[test]
    fn epoch_days_match_known_dates() {
        assert_eq!(d(1970, 1, 1).epoch_days(), 0);
        assert_eq!(d(2000, 3, 1).epoch_days(), 11_017);
    }

    #[test]
    fn reversed_dates_rejected() {
        assert_eq!(
            act_360(d(2025, 1, 31), d(2025, 1, 1)),
            Err(DayCountError::ReversedDates)
        );
    }

    #[test]
    fn impossible_date_rejected() {
        assert_eq!(Date::new(2025, 2, 29), Err(DayCountError::InvalidDate));
    }
}
