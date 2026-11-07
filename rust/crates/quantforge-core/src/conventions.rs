//! Convention registry (`conventions.md`). Market conventions are data, kept here only.
use crate::json::{Json, obj};

/// An overnight index.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Overnight {
    pub id: &'static str,
    pub currency: &'static str,
    pub day_count: &'static str,
    pub calendar: &'static str,
    pub spot_lag: i64,
    pub payment_lag: i64,
    pub fixed_months: i64,
    pub fixed_day_count: &'static str,
}

const SONIA: Overnight = Overnight {
    id: "SONIA",
    currency: "GBP",
    day_count: "ACT_365F",
    calendar: "GBLO",
    spot_lag: 0,
    payment_lag: 0,
    fixed_months: 12,
    fixed_day_count: "ACT_365F",
};

const SOFR: Overnight = Overnight {
    id: "SOFR",
    currency: "USD",
    day_count: "ACT_360",
    calendar: "USGS",
    spot_lag: 2,
    payment_lag: 2,
    fixed_months: 12,
    fixed_day_count: "ACT_360",
};

/// Stage D: Strata 2.12.78 `EUR-FIXED-1Y-ESTR-OIS` (ruling D1).
const ESTR: Overnight = Overnight {
    id: "ESTR",
    currency: "EUR",
    day_count: "ACT_360",
    calendar: "EUTA",
    spot_lag: 2,
    payment_lag: 2,
    fixed_months: 12,
    fixed_day_count: "ACT_360",
};

pub fn overnight(id: &str) -> Option<Overnight> {
    match id {
        "SONIA" => Some(SONIA),
        "SOFR" => Some(SOFR),
        "ESTR" => Some(ESTR),
        _ => None,
    }
}

/// The synthetic term index.
pub const TERM_INDEX: &str = "USD-TERM-3M";
pub const TERM_CURRENCY: &str = "USD";
pub const TERM_CALENDAR: &str = "USGS";
pub const TERM_DAY_COUNT: &str = "ACT_360";
pub const TERM_SPOT_LAG: i64 = 2;
pub const TERM_MONTHS: i64 = 3;
pub const TERM_FIXED_MONTHS: i64 = 12;
pub const TERM_FIXED_DAY_COUNT: &str = "THIRTY_360_BOND";

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FxPair {
    pub id: &'static str,
    pub base: &'static str,
    pub quote: &'static str,
    pub spot_lag: i64,
    pub calendars: [&'static str; 2],
    pub pip: f64,
}

pub fn fx_pair(id: &str) -> Option<FxPair> {
    match id {
        "GBPUSD" => Some(FxPair {
            id: "GBPUSD",
            base: "GBP",
            quote: "USD",
            spot_lag: 2,
            calendars: ["GBLO", "USGS"],
            pip: 0.0001,
        }),
        "EURUSD" => Some(FxPair {
            id: "EURUSD",
            base: "EUR",
            quote: "USD",
            spot_lag: 2,
            calendars: ["EUTA", "USGS"],
            pip: 0.0001,
        }),
        _ => None,
    }
}

const MF: &str = "MODIFIED_FOLLOWING";

/// The published record for an id.
pub fn lookup(id: &str) -> Option<Json> {
    if let Some(c) = overnight(id) {
        return Some(obj([
            ("kind", "OVERNIGHT".into()),
            ("currency", c.currency.into()),
            ("day_count", c.day_count.into()),
            ("calendar", c.calendar.into()),
            ("spot_lag", c.spot_lag.into()),
            ("payment_lag", c.payment_lag.into()),
            ("fixed_months", c.fixed_months.into()),
            ("fixed_day_count", c.fixed_day_count.into()),
            ("business_day_convention", MF.into()),
        ]));
    }
    if id == TERM_INDEX {
        return Some(obj([
            ("kind", "TERM".into()),
            ("currency", TERM_CURRENCY.into()),
            ("day_count", TERM_DAY_COUNT.into()),
            ("calendar", TERM_CALENDAR.into()),
            ("spot_lag", TERM_SPOT_LAG.into()),
            ("months", TERM_MONTHS.into()),
            ("fixed_months", TERM_FIXED_MONTHS.into()),
            ("fixed_day_count", TERM_FIXED_DAY_COUNT.into()),
            ("business_day_convention", MF.into()),
        ]));
    }
    fx_pair(id).map(|p| {
        obj([
            ("kind", "FX".into()),
            ("base", p.base.into()),
            ("quote", p.quote.into()),
            ("spot_lag", p.spot_lag.into()),
            ("calendars", p.calendars.to_vec().into()),
            ("pip", p.pip.into()),
        ])
    })
}
