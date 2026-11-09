//! Day counts (`daycount.md`).
use crate::calendar::Calendar;
use crate::dates::{Date, days_in_year, is_leap};
use crate::error::{Result, fail};

#[derive(Debug, Default)]
pub struct DayCountInputs {
    pub frequency: Option<i64>,
    pub ref_start: Option<Date>,
    pub ref_end: Option<Date>,
    pub termination: Option<Date>,
    pub calendar: Option<Calendar>,
}

const FREQUENCIES: [i64; 6] = [1, 2, 3, 4, 6, 12];

/// Counts 29 Februaries in the closed range `[from, to]`.
fn leap_days(from: Date, to: Date) -> i64 {
    (from.y..=to.y)
        .filter(|&y| is_leap(y))
        .map(|y| Date::new(y, 2, 29))
        .filter(|d| *d >= from && *d <= to)
        .count() as i64
}

fn need<T>(v: Option<T>, name: &str) -> Result<T> {
    match v {
        Some(x) => Ok(x),
        None => fail("E_SCHEMA", format!("{name} is required")),
    }
}

fn frequency(i: &DayCountInputs) -> Result<i64> {
    let f = need(i.frequency, "frequency")?;
    if !FREQUENCIES.contains(&f) {
        return fail("E_SCHEMA", "frequency is not listed");
    }
    Ok(f)
}

fn thirty(y1: i32, m1: i64, d1: i64, y2: i32, m2: i64, d2: i64) -> f64 {
    (360 * i64::from(y2 - y1) + 30 * (m2 - m1) + (d2 - d1)) as f64 / 360.0
}

fn back(end: Date, n: i32) -> Date {
    let y = end.y - n;
    if n == 0 {
        end
    } else if end.m == 2 && end.d == 28 && is_leap(y) {
        Date::new(y, 2, 29)
    } else if end.m == 2 && end.d == 29 && !is_leap(y) {
        Date::new(y, 2, 28)
    } else {
        Date::new(y, end.m, end.d)
    }
}

fn afb(start: Date, end: Date) -> f64 {
    let mut n = 0;
    while back(end, n + 1) >= start {
        n += 1;
    }
    let e = back(end, n);
    let d = if e > start && leap_days(start, e.add_days(-1)) > 0 {
        366.0
    } else {
        365.0
    };
    f64::from(n) + (e.serial() - start.serial()) as f64 / d
}

pub fn year_fraction(convention: &str, start: Date, end: Date, i: &DayCountInputs) -> Result<f64> {
    // Check 1: conditional inputs.
    let mut icma = None;
    let mut termination = None;
    let mut calendar = None;
    let mut l_frequency = 0;
    match convention {
        "ACT_360" | "ACT_365F" | "ACT_364" | "ACT_365_25" | "NL_365" | "ONE_ONE"
        | "ACT_ACT_ISDA" | "ACT_ACT_AFB" | "THIRTY_360_BOND" | "THIRTY_360_US" | "THIRTY_E_360"
        | "THIRTY_E_PLUS_360" => {}
        "ACT_365L" => l_frequency = frequency(i)?,
        "ACT_ACT_ICMA" => {
            icma = Some((
                frequency(i)?,
                need(i.ref_start, "ref_start")?,
                need(i.ref_end, "ref_end")?,
            ));
        }
        "THIRTY_E_360_ISDA" => termination = Some(need(i.termination, "termination")?),
        "BUS_252" => calendar = Some(need(i.calendar.as_ref(), "calendar")?),
        _ => return fail("E_SCHEMA", "unknown convention"),
    }
    // Check 2.
    if end < start {
        return fail("E_DATE_ORDER", "end is before start");
    }
    // Check 3.
    if let Some((_, rs, re)) = icma
        && (re <= rs || start < rs || end > re)
    {
        return fail("E_INPUT", "accrual must lie inside the reference period");
    }
    if let Some(c) = calendar {
        // A date outside the calendar is an error even for an empty range.
        let n = c.business_days_between(start, end)?;
        return Ok(n as f64 / 252.0);
    }
    if start == end {
        return Ok(0.0);
    }
    let days = (end.serial() - start.serial()) as f64;
    let (m1, mut d1) = (i64::from(start.m), i64::from(start.d));
    let (mut m2, mut d2) = (i64::from(end.m), i64::from(end.d));
    let (y1, y2) = (start.y, end.y);
    let after_start = start.add_days(1);
    Ok(match convention {
        "ACT_360" => days / 360.0,
        "ACT_365F" => days / 365.0,
        "ACT_364" => days / 364.0,
        "ACT_365_25" => days / 365.25,
        "NL_365" => (days - leap_days(after_start, end) as f64) / 365.0,
        "ONE_ONE" => 1.0,
        "ACT_365L" => {
            if l_frequency == 1 {
                days / if leap_days(after_start, end) > 0 {
                    366.0
                } else {
                    365.0
                }
            } else {
                days / days_in_year(y2) as f64
            }
        }
        "ACT_ACT_ISDA" => {
            if y1 == y2 {
                days / days_in_year(y1) as f64
            } else {
                let first = (Date::new(y1 + 1, 1, 1).serial() - start.serial()) as f64;
                let last = (end.serial() - Date::new(y2, 1, 1).serial()) as f64;
                first / days_in_year(y1) as f64
                    + f64::from(y2 - y1 - 1)
                    + last / days_in_year(y2) as f64
            }
        }
        "ACT_ACT_ICMA" => {
            let (f, rs, re) = icma.expect("checked above");
            days / (f * (re.serial() - rs.serial())) as f64
        }
        "ACT_ACT_AFB" => afb(start, end),
        "THIRTY_360_BOND" => {
            if d1 == 31 {
                d1 = 30;
            }
            if d2 == 31 && d1 == 30 {
                d2 = 30;
            }
            thirty(y1, m1, d1, y2, m2, d2)
        }
        "THIRTY_360_US" => {
            if start.is_end_of_february() && end.is_end_of_february() {
                d2 = 30;
            }
            if start.is_end_of_february() {
                d1 = 30;
            }
            if d2 == 31 && d1 >= 30 {
                d2 = 30;
            }
            if d1 == 31 {
                d1 = 30;
            }
            thirty(y1, m1, d1, y2, m2, d2)
        }
        "THIRTY_E_360" => thirty(y1, m1, d1.min(30), y2, m2, d2.min(30)),
        "THIRTY_E_360_ISDA" => {
            if d1 == 31 || start.is_end_of_february() {
                d1 = 30;
            }
            if d2 == 31 || (end.is_end_of_february() && Some(end) != termination) {
                d2 = 30;
            }
            thirty(y1, m1, d1, y2, m2, d2)
        }
        _ => {
            // THIRTY_E_PLUS_360, the only name left.
            if d2 == 31 {
                d2 = 1;
                m2 += 1;
            }
            thirty(y1, m1, d1.min(30), y2, m2, d2)
        }
    })
}
