#[derive(Debug, Clone, PartialEq)]
pub struct YearFraction {
    pub value: f64,
    pub convention: &'static str,
}

#[derive(Debug, Clone, PartialEq)]
pub enum DayCountError {
    ReversedDates,
}

pub fn act_360(days: i64) -> Result<YearFraction, DayCountError> {
    if days < 0 { return Err(DayCountError::ReversedDates); }
    Ok(YearFraction { value: days as f64 / 360.0, convention: "ACT/360" })
}

pub fn act_365f(days: i64) -> Result<YearFraction, DayCountError> {
    if days < 0 { return Err(DayCountError::ReversedDates); }
    Ok(YearFraction { value: days as f64 / 365.0, convention: "ACT/365F" })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn act_360_example() {
        let yf = act_360(30).unwrap();
        assert!((yf.value - 30.0/360.0).abs() < 1e-14);
    }

    #[test]
    fn reversed_dates_rejected() {
        assert_eq!(act_360(-1), Err(DayCountError::ReversedDates));
    }
}
