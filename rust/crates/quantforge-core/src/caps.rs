//! Caps, floors and swaptions (`caps-and-swaptions.md`).
use crate::black::{bachelier, black};
use crate::calendar::{Bdc, Calendar};
use crate::curve::Curve;
use crate::dates::Date;
use crate::daycount::{DayCountInputs, year_fraction};
use crate::error::{Result, fail};
use crate::schedule::{Period, add_months, generate};

fn usgs() -> Calendar {
    Calendar::parse("USGS").expect("registry calendars exist")
}

/// `adjust(spot + months)` with spot two USGS business days after `as_of`.
pub(crate) fn forward_start(as_of: Date, months: i64) -> Result<Date> {
    let cal = usgs();
    let spot = cal.add_business_days(as_of, 2)?;
    cal.adjust(add_months(spot, months), Bdc::ModifiedFollowing)
}

pub(crate) fn periods(start: Date, months: i64, every: i64) -> Result<Vec<Period>> {
    if months <= 0 || months > 1200 {
        return fail("E_INPUT", "tenor_months must be 1 to 1200");
    }
    generate(start, add_months(start, months), every, &usgs(), false, 0)
}

pub(crate) fn years(as_of: Date, d: Date) -> f64 {
    (d.serial() - as_of.serial()) as f64 / 365.0
}

/// Undiscounted option on a forward.
pub(crate) fn option(normal: bool, call: bool, f: f64, k: f64, v: f64, t: f64) -> Result<f64> {
    if normal {
        return Ok(bachelier(call, f, k, v, t, 1.0));
    }
    if k <= 0.0 || f <= 0.0 {
        return fail("E_DOMAIN", "BLACK_76 needs a positive strike and forward");
    }
    Ok(black(call, f, k, v, t, 1.0))
}

#[derive(Debug, Clone, Copy)]
pub struct CapTrade {
    pub cap: bool,
    pub start_months: i64,
    pub tenor_months: i64,
    pub strike: f64,
    pub notional: f64,
}

/// `rates.cap.price`: the caplets in order. `vols` has one entry (flat) or one per caplet.
pub fn cap_price(
    discount: &Curve,
    projection: &Curve,
    normal: bool,
    vols: &[f64],
    t: &CapTrade,
) -> Result<Vec<f64>> {
    if t.start_months < 1 {
        return fail("E_INPUT", "start_months must be at least 1");
    }
    let as_of = discount.as_of;
    let ps = periods(forward_start(as_of, t.start_months)?, t.tenor_months, 3)?;
    if vols.len() != 1 && vols.len() != ps.len() {
        return fail("E_INPUT", "one vol, or one per caplet");
    }
    if vols.iter().any(|v| *v < 0.0) {
        return fail("E_DOMAIN", "a vol is negative");
    }
    let none = DayCountInputs::default();
    ps.iter()
        .enumerate()
        .map(|(i, p)| {
            let alpha = year_fraction("ACT_360", p.start, p.end, &none)?;
            let f = (projection.discount(p.start)? / projection.discount(p.end)? - 1.0) / alpha;
            let v = if vols.len() == 1 { vols[0] } else { vols[i] };
            let o = option(normal, t.cap, f, t.strike, v, years(as_of, p.start))?;
            Ok(t.notional * alpha * discount.discount(p.end)? * o)
        })
        .collect()
}

#[derive(Debug, Clone, Copy)]
pub struct SwaptionTrade {
    pub payer: bool,
    pub expiry_months: i64,
    pub tenor_months: i64,
    pub strike: f64,
    pub notional: f64,
}

/// `rates.swaption.price`: `(price, forward_rate, annuity)`.
pub fn swaption_price(
    discount: &Curve,
    projection: &Curve,
    normal: bool,
    vol: f64,
    t: &SwaptionTrade,
) -> Result<(f64, f64, f64)> {
    if t.expiry_months < 1 {
        return fail("E_INPUT", "expiry_months must be at least 1");
    }
    if vol < 0.0 {
        return fail("E_DOMAIN", "vol is negative");
    }
    let as_of = discount.as_of;
    let (s, f, a) = swap_forward(discount, projection, t.expiry_months, t.tenor_months)?;
    let o = option(normal, t.payer, f, t.strike, vol, years(as_of, s))?;
    Ok((t.notional * a * o, f, a))
}

/// Swap start (and exercise) date, forward swap rate and annuity of the D7 swaption.
pub(crate) fn swap_forward(
    discount: &Curve,
    projection: &Curve,
    expiry_months: i64,
    tenor_months: i64,
) -> Result<(Date, f64, f64)> {
    let s = forward_start(discount.as_of, expiry_months)?;
    let fixed = periods(s, tenor_months, 12)?;
    let floating = periods(s, tenor_months, 3)?;
    let none = DayCountInputs::default();
    let mut a = 0.0;
    for p in &fixed {
        a += year_fraction("THIRTY_360_BOND", p.start, p.end, &none)? * discount.discount(p.end)?;
    }
    let mut fl = 0.0;
    for p in &floating {
        fl += (projection.discount(p.start)? / projection.discount(p.end)? - 1.0)
            * discount.discount(p.end)?;
    }
    Ok((s, fl / a, a))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::curve::{Interpolation, curve_time};

    fn d(s: &str) -> Date {
        Date::parse(s).unwrap()
    }

    fn flat(r: f64) -> Curve {
        let as_of = d("2026-11-06");
        let p = d("2056-11-06");
        Curve::from_logs(
            as_of,
            Interpolation::LogLinearDf,
            &[p],
            &[-r * curve_time(as_of, p)],
        )
    }

    #[test]
    fn cap_floor_parity_and_checks() {
        let c = flat(0.04);
        let t = CapTrade {
            cap: true,
            start_months: 3,
            tenor_months: 12,
            strike: 0.04,
            notional: 1e6,
        };
        let cap = cap_price(&c, &c, false, &[0.2], &t).unwrap();
        let floor = cap_price(&c, &c, false, &[0.2], &CapTrade { cap: false, ..t }).unwrap();
        assert_eq!(cap.len(), 4);
        let swap = cap_price(&c, &c, false, &[0.0], &t).unwrap();
        let nfloor = cap_price(&c, &c, false, &[0.0], &CapTrade { cap: false, ..t }).unwrap();
        let s1: f64 = cap.iter().zip(&floor).map(|(a, b)| a - b).sum();
        let s0: f64 = swap.iter().zip(&nfloor).map(|(a, b)| a - b).sum();
        assert!((s1 - s0).abs() < 1e-8);
        assert!(cap_price(&c, &c, true, &[0.01, 0.01, 0.01, 0.01], &t).is_ok());
        assert_eq!(
            cap_price(&c, &c, false, &[0.2, 0.2], &t).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(
            cap_price(&c, &c, false, &[-0.1], &t).unwrap_err().code,
            "E_DOMAIN"
        );
        let s0 = CapTrade {
            start_months: 0,
            ..t
        };
        assert_eq!(
            cap_price(&c, &c, false, &[0.2], &s0).unwrap_err().code,
            "E_INPUT"
        );
        let neg = CapTrade { strike: -0.01, ..t };
        assert_eq!(
            cap_price(&c, &c, false, &[0.2], &neg).unwrap_err().code,
            "E_DOMAIN"
        );
        assert!(cap_price(&c, &c, true, &[0.01], &neg).is_ok());
    }

    #[test]
    fn swaption_parity() {
        let c = flat(0.04);
        let t = SwaptionTrade {
            payer: true,
            expiry_months: 12,
            tenor_months: 60,
            strike: 0.04,
            notional: 1e6,
        };
        let (p, f, a) = swaption_price(&c, &c, false, 0.2, &t).unwrap();
        let (r, _, _) =
            swaption_price(&c, &c, false, 0.2, &SwaptionTrade { payer: false, ..t }).unwrap();
        assert!((p - r - 1e6 * a * (f - 0.04)).abs() < 1e-6);
        let e = SwaptionTrade {
            expiry_months: 0,
            ..t
        };
        assert_eq!(
            swaption_price(&c, &c, false, 0.2, &e).unwrap_err().code,
            "E_INPUT"
        );
    }
}
