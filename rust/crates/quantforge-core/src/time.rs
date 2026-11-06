//! Timezones and cut-off (`timezone-and-cutoff.md`).
use crate::calendar::{Bdc, Calendar};
use crate::dates::{Date, fixed_digits};
use crate::error::{Result, fail};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Zone {
    Utc,
    London,
    Berlin,
    NewYork,
    Tokyo,
}

impl Zone {
    pub fn parse(s: &str) -> Option<Zone> {
        Some(match s {
            "UTC" => Zone::Utc,
            "Europe/London" => Zone::London,
            "Europe/Berlin" => Zone::Berlin,
            "America/New_York" => Zone::NewYork,
            "Asia/Tokyo" => Zone::Tokyo,
            _ => return None,
        })
    }

    fn standard(self) -> i64 {
        match self {
            Zone::Utc | Zone::London => 0,
            Zone::Berlin => 3600,
            Zone::NewYork => -5 * 3600,
            Zone::Tokyo => 9 * 3600,
        }
    }

    fn has_summer(self) -> bool {
        matches!(self, Zone::London | Zone::Berlin | Zone::NewYork)
    }
}

const DAY: i64 = 86400;

/// Seconds since 1970-01-01T00:00:00 for a date and time of day.
fn seconds(d: Date, tod: i64) -> i64 {
    d.serial() * DAY + tod
}

fn split(s: i64) -> (Date, i64) {
    (Date::from_serial(s.div_euclid(DAY)), s.rem_euclid(DAY))
}

fn sunday_on_or_after(d: Date) -> Date {
    d.add_days(6 - d.weekday())
}

/// Summer time `[start, end)` in UTC seconds.
fn summer(zone: Zone, y: i32) -> (i64, i64) {
    if zone == Zone::NewYork {
        let start = sunday_on_or_after(Date::new(y, 3, 8));
        let end = sunday_on_or_after(Date::new(y, 11, 1));
        (seconds(start, 7 * 3600), seconds(end, 6 * 3600))
    } else {
        let start = sunday_on_or_after(Date::new(y, 3, 25));
        let end = sunday_on_or_after(Date::new(y, 10, 25));
        (seconds(start, 3600), seconds(end, 3600))
    }
}

fn offset_at(zone: Zone, instant: i64) -> i64 {
    let mut off = zone.standard();
    if zone.has_summer() {
        let (start, end) = summer(zone, split(instant).0.y);
        if instant >= start && instant < end {
            off += 3600;
        }
    }
    off
}

fn check_year(y: i32) -> Result<()> {
    if y < 2007 || y > 2037 {
        return fail("E_DATE_RANGE", "supported years are 2007 to 2037");
    }
    Ok(())
}

fn check_instant(instant: i64) -> Result<()> {
    check_year(split(instant).0.y)
}

fn clock(s: &str) -> Option<i64> {
    let b = s.as_bytes();
    if b.len() != 8 || b[2] != b':' || b[5] != b':' {
        return None;
    }
    let h = fixed_digits(s.get(0..2)?, 2)?;
    let m = fixed_digits(s.get(3..5)?, 2)?;
    let sec = fixed_digits(s.get(6..8)?, 2)?;
    (h < 24 && m < 60 && sec < 60).then_some(h * 3600 + m * 60 + sec)
}

/// `YYYY-MM-DDTHH:MM:SS` as seconds on the local clock.
pub fn parse_local(s: &str) -> Option<i64> {
    if s.len() != 19 || s.as_bytes()[10] != b'T' {
        return None;
    }
    Some(seconds(Date::parse(s.get(0..10)?)?, clock(s.get(11..19)?)?))
}

/// RFC 3339 with `Z` or a numeric offset, whole seconds, as UTC seconds.
pub fn parse_instant(s: &str) -> Option<i64> {
    let local = parse_local(s.get(0..19)?)?;
    let rest = s.get(19..)?;
    if rest == "Z" {
        return Some(local);
    }
    let b = rest.as_bytes();
    if b.len() != 6 || b[3] != b':' || (b[0] != b'+' && b[0] != b'-') {
        return None;
    }
    let h = fixed_digits(rest.get(1..3)?, 2)?;
    let m = fixed_digits(rest.get(4..6)?, 2)?;
    if h > 23 || m > 59 {
        return None;
    }
    let off = h * 3600 + m * 60;
    Some(if b[0] == b'+' {
        local - off
    } else {
        local + off
    })
}

/// `HH:MM` as seconds into the day.
pub fn parse_cutoff(s: &str) -> Option<i64> {
    if s.len() != 5 {
        return None;
    }
    clock(&format!("{s}:00"))
}

fn format_clock(s: i64) -> String {
    let (d, t) = split(s);
    format!("{d}T{:02}:{:02}:{:02}", t / 3600, t % 3600 / 60, t % 60)
}

pub fn utc_offset(zone: Zone, instant: i64) -> Result<i64> {
    check_instant(instant)?;
    Ok(offset_at(zone, instant))
}

pub fn to_local(zone: Zone, instant: i64) -> Result<String> {
    check_instant(instant)?;
    Ok(format_clock(instant + offset_at(zone, instant)))
}

/// `overlap` is `Some(true)` for `EARLIER`, `Some(false)` for `LATER`.
pub fn to_instant(zone: Zone, local: i64, overlap: Option<bool>) -> Result<String> {
    check_year(split(local).0.y)?;
    let std = zone.standard();
    let summer_candidate = local - (std + 3600);
    let standard_candidate = local - std;
    let summer_ok = zone.has_summer() && offset_at(zone, summer_candidate) == std + 3600;
    let standard_ok = offset_at(zone, standard_candidate) == std;
    let instant = match (summer_ok, standard_ok) {
        (false, false) => return fail("E_NONEXISTENT_LOCAL_TIME", "local time is in a gap"),
        (true, false) => summer_candidate,
        (false, true) => standard_candidate,
        (true, true) => match overlap {
            None => return fail("E_AMBIGUOUS_LOCAL_TIME", "local time is in an overlap"),
            Some(true) => summer_candidate,
            Some(false) => standard_candidate,
        },
    };
    Ok(format!("{}Z", format_clock(instant)))
}

pub fn business_date(instant: i64, zone: Zone, cutoff: i64, calendar: &Calendar) -> Result<Date> {
    check_instant(instant)?;
    let (mut d, tod) = split(instant + offset_at(zone, instant));
    if tod >= cutoff {
        d = d.add_days(1);
    }
    calendar.adjust(d, Bdc::Following)
}
