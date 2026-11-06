//! Holiday calendars and business-day rules (`calendars.md`).
use crate::dates::{Date, days_in_month};
use crate::error::{Result, fail};
use std::cell::RefCell;
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CalendarId {
    Gblo,
    Euta,
    Usgs,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Bdc {
    Unadjusted,
    Following,
    Preceding,
    ModifiedFollowing,
    ModifiedPreceding,
}

impl Bdc {
    pub fn parse(s: &str) -> Option<Bdc> {
        Some(match s {
            "UNADJUSTED" => Bdc::Unadjusted,
            "FOLLOWING" => Bdc::Following,
            "PRECEDING" => Bdc::Preceding,
            "MODIFIED_FOLLOWING" => Bdc::ModifiedFollowing,
            "MODIFIED_PRECEDING" => Bdc::ModifiedPreceding,
            _ => return None,
        })
    }
}

/// `^[1-9][0-9]{0,3}[DWMY]$`, as a count and a unit.
pub fn parse_tenor(s: &str) -> Option<(i64, char)> {
    if !s.is_ascii() || s.is_empty() {
        return None;
    }
    let (digits, unit) = s.split_at(s.len() - 1);
    let valid = (1..=4).contains(&digits.len())
        && digits.bytes().all(|b| b.is_ascii_digit())
        && !digits.starts_with('0')
        && "DWMY".contains(unit);
    valid.then(|| {
        (
            digits.parse().unwrap_or(0),
            unit.chars().next().unwrap_or('D'),
        )
    })
}

pub fn easter_sunday(y: i32) -> Date {
    let a = y % 19;
    let b = y / 100;
    let c = y % 100;
    let d = b / 4;
    let e = b % 4;
    let f = (b + 8) / 25;
    let g = (b - f + 1) / 3;
    let h = (19 * a + b - d - g + 15) % 30;
    let i = c / 4;
    let k = c % 4;
    let l = (32 + 2 * e + 2 * i - h - k) % 7;
    let m = (a + 11 * h + 22 * l) / 451;
    let month = (h + l - 7 * m + 114) / 31;
    let day = (h + l - 7 * m + 114) % 31 + 1;
    Date::new(y, month as u32, day as u32)
}

fn nth_weekday(y: i32, m: u32, weekday: i64, n: i64) -> Date {
    let first = Date::new(y, m, 1);
    first.add_days((weekday - first.weekday()).rem_euclid(7) + 7 * (n - 1))
}

fn last_weekday(y: i32, m: u32, weekday: i64) -> Date {
    let last = Date::new(y, m, days_in_month(y, m));
    last.add_days(-(last.weekday() - weekday).rem_euclid(7))
}

/// Friday if a Saturday, Monday if a Sunday.
fn nearest_weekday(d: Date) -> Date {
    match d.weekday() {
        5 => d.add_days(-1),
        6 => d.add_days(1),
        _ => d,
    }
}

/// Monday if a Sunday; a Saturday gives no holiday in lieu.
fn sunday_to_monday(d: Date) -> Date {
    if d.weekday() == 6 { d.add_days(1) } else { d }
}

fn one_offs(y: i32, list: &[(i32, u32, u32)], out: &mut Vec<Date>) {
    out.extend(
        list.iter()
            .filter(|o| o.0 == y)
            .map(|o| Date::new(o.0, o.1, o.2)),
    );
}

fn gblo(y: i32) -> Vec<Date> {
    let easter = easter_sunday(y);
    let new_year = Date::new(y, 1, 1);
    let mut h = vec![
        match new_year.weekday() {
            5 => new_year.add_days(2),
            6 => new_year.add_days(1),
            _ => new_year,
        },
        easter.add_days(-2),
        easter.add_days(1),
        if y == 2020 {
            Date::new(2020, 5, 8)
        } else {
            nth_weekday(y, 5, 0, 1)
        },
        match y {
            2002 => Date::new(2002, 6, 4),
            2012 => Date::new(2012, 6, 4),
            2022 => Date::new(2022, 6, 2),
            _ => last_weekday(y, 5, 0),
        },
        last_weekday(y, 8, 0),
    ];
    let (first, second) = match Date::new(y, 12, 25).weekday() {
        5 => (27, 28),
        6 => (26, 27),
        4 => (25, 28),
        _ => (25, 26),
    };
    h.push(Date::new(y, 12, first));
    h.push(Date::new(y, 12, second));
    one_offs(
        y,
        &[
            (2002, 6, 3),
            (2011, 4, 29),
            (2012, 6, 5),
            (2022, 6, 3),
            (2022, 9, 19),
            (2023, 5, 8),
        ],
        &mut h,
    );
    h
}

fn euta(y: i32) -> Vec<Date> {
    let easter = easter_sunday(y);
    let mut h = vec![
        Date::new(y, 1, 1),
        easter.add_days(-2),
        easter.add_days(1),
        Date::new(y, 5, 1),
        Date::new(y, 12, 25),
        Date::new(y, 12, 26),
    ];
    one_offs(y, &[(2001, 12, 31)], &mut h);
    h
}

fn usgs(y: i32) -> Vec<Date> {
    let mut h = vec![
        sunday_to_monday(Date::new(y, 1, 1)),
        nth_weekday(y, 1, 0, 3),
        nth_weekday(y, 2, 0, 3),
        easter_sunday(y).add_days(-2),
        last_weekday(y, 5, 0),
        nearest_weekday(Date::new(y, 7, 4)),
        nth_weekday(y, 9, 0, 1),
        nth_weekday(y, 10, 0, 2),
        sunday_to_monday(Date::new(y, 11, 11)),
        nth_weekday(y, 11, 3, 4),
        nearest_weekday(Date::new(y, 12, 25)),
    ];
    if y >= 2022 {
        h.push(nearest_weekday(Date::new(y, 6, 19)));
    }
    one_offs(y, &[(2004, 6, 11), (2012, 10, 30), (2018, 12, 5)], &mut h);
    h
}

#[derive(Debug)]
pub struct Calendar {
    id: CalendarId,
    cache: RefCell<HashMap<i32, Vec<Date>>>,
}

fn check_year(y: i32) -> Result<()> {
    if y < 2000 || y > 2099 {
        return fail("E_DATE_RANGE", "calendars cover 2000 to 2099");
    }
    Ok(())
}

impl Calendar {
    pub fn new(id: CalendarId) -> Calendar {
        Calendar {
            id,
            cache: RefCell::new(HashMap::new()),
        }
    }

    pub fn parse(s: &str) -> Option<Calendar> {
        let id = match s {
            "GBLO" => CalendarId::Gblo,
            "EUTA" => CalendarId::Euta,
            "USGS" => CalendarId::Usgs,
            _ => return None,
        };
        Some(Calendar::new(id))
    }

    /// Weekday holidays of the year, ascending.
    pub fn holidays(&self, y: i32) -> Result<Vec<Date>> {
        check_year(y)?;
        if let Some(h) = self.cache.borrow().get(&y) {
            return Ok(h.clone());
        }
        let mut h = match self.id {
            CalendarId::Gblo => gblo(y),
            CalendarId::Euta => euta(y),
            CalendarId::Usgs => usgs(y),
        };
        h.retain(|d| !d.is_weekend());
        h.sort();
        h.dedup();
        self.cache.borrow_mut().insert(y, h.clone());
        Ok(h)
    }

    pub fn is_business_day(&self, d: Date) -> Result<bool> {
        check_year(d.y)?;
        if d.is_weekend() {
            return Ok(false);
        }
        Ok(!self.holidays(d.y)?.contains(&d))
    }

    fn search(&self, mut d: Date, step: i64) -> Result<Date> {
        while !self.is_business_day(d)? {
            d = d.add_days(step);
        }
        Ok(d)
    }

    pub fn adjust(&self, d: Date, convention: Bdc) -> Result<Date> {
        check_year(d.y)?;
        match convention {
            Bdc::Unadjusted => Ok(d),
            Bdc::Following => self.search(d, 1),
            Bdc::Preceding => self.search(d, -1),
            Bdc::ModifiedFollowing => {
                let r = self.search(d, 1)?;
                if r.m == d.m {
                    Ok(r)
                } else {
                    self.search(d, -1)
                }
            }
            Bdc::ModifiedPreceding => {
                let r = self.search(d, -1)?;
                if r.m == d.m { Ok(r) } else { self.search(d, 1) }
            }
        }
    }

    pub fn add_business_days(&self, d: Date, days: i64) -> Result<Date> {
        if days == 0 {
            return self.adjust(d, Bdc::Following);
        }
        check_year(d.y)?;
        let step = days.signum();
        let mut left = days.abs();
        let mut cur = d;
        while left > 0 {
            cur = cur.add_days(step);
            if self.is_business_day(cur)? {
                left -= 1;
            }
        }
        Ok(cur)
    }

    /// Business days in `[start, end)`.
    pub fn business_days_between(&self, start: Date, end: Date) -> Result<i64> {
        check_year(start.y)?;
        check_year(end.y)?;
        if end < start {
            return fail("E_DATE_ORDER", "end is before start");
        }
        let mut count = 0;
        let mut cur = start;
        while cur < end {
            if self.is_business_day(cur)? {
                count += 1;
            }
            cur = cur.add_days(1);
        }
        Ok(count)
    }

    pub fn last_business_day(&self, y: i32, m: u32) -> Result<Date> {
        self.search(Date::new(y, m, days_in_month(y, m)), -1)
    }

    /// `count` is 1 to 9999, `unit` one of D, W, M, Y.
    pub fn add_tenor(
        &self,
        d: Date,
        count: i64,
        unit: char,
        convention: Bdc,
        end_of_month: bool,
    ) -> Result<Date> {
        check_year(d.y)?;
        let result = match unit {
            'D' | 'W' => {
                let days = if unit == 'W' { 7 * count } else { count };
                let target = d.add_days(days);
                check_year(target.y)?;
                self.adjust(target, convention)?
            }
            _ => {
                let months = if unit == 'Y' { 12 * count } else { count };
                let total = i64::from(d.y) * 12 + i64::from(d.m) - 1 + months;
                let y = total.div_euclid(12) as i32;
                let m = total.rem_euclid(12) as u32 + 1;
                check_year(y)?;
                let last_day = days_in_month(y, m);
                if end_of_month && convention == Bdc::Unadjusted {
                    let at_end = d.d == days_in_month(d.y, d.m);
                    Date::new(y, m, if at_end { last_day } else { d.d.min(last_day) })
                } else if end_of_month && d >= self.last_business_day(d.y, d.m)? {
                    self.last_business_day(y, m)?
                } else {
                    self.adjust(Date::new(y, m, d.d.min(last_day)), convention)?
                }
            }
        };
        check_year(result.y)?;
        Ok(result)
    }
}
