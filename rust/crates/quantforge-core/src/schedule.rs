//! Schedules (`schedules.md`).
use crate::calendar::{Bdc, Calendar};
use crate::dates::{Date, days_in_month};
use crate::error::{Result, fail};

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Period {
    pub start: Date,
    pub end: Date,
    pub payment: Date,
}

/// Adds months, clipping the day to the target month.
pub fn add_months(d: Date, months: i64) -> Date {
    let total = i64::from(d.y) * 12 + i64::from(d.m) - 1 + months;
    let y = total.div_euclid(12) as i32;
    let m = total.rem_euclid(12) as u32 + 1;
    Date::new(y, m, d.d.min(days_in_month(y, m)))
}

pub fn generate(
    start: Date,
    end: Date,
    frequency_months: i64,
    calendar: &Calendar,
    end_of_month: bool,
    payment_lag: i64,
) -> Result<Vec<Period>> {
    if end <= start {
        return fail("E_DATE_ORDER", "end is not after start");
    }
    if payment_lag < 0 {
        return fail("E_INPUT", "payment_lag is negative");
    }
    let mut unadjusted = Vec::new();
    let mut k = 0;
    loop {
        let d = add_months(end, -k * frequency_months);
        if d <= start {
            break;
        }
        unadjusted.push(d);
        k += 1;
    }
    unadjusted.reverse();
    let mut dates = vec![start];
    for d in unadjusted {
        let a = if end_of_month {
            calendar.last_business_day(d.y, d.m)?
        } else {
            calendar.adjust(d, Bdc::ModifiedFollowing)?
        };
        if a > *dates.last().expect("holds start") {
            dates.push(a);
        }
    }
    dates
        .windows(2)
        .map(|w| {
            Ok(Period {
                start: w[0],
                end: w[1],
                payment: calendar.add_business_days(w[1], payment_lag)?,
            })
        })
        .collect()
}
