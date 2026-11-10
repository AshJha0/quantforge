//! Cross-currency basis and NDFs (`02-curves/cross-currency.md`). Domestic USD, foreign EUR.
use crate::calendar::Calendar;
use crate::curve::{Curve, Discount, Interpolation, SolveMethod, Solved, solve_curve};
use crate::dates::Date;

use crate::error::{Result, fail};
use crate::schedule::add_months;

fn calendars() -> [Calendar; 2] {
    ["USGS", "EUTA"].map(|c| Calendar::parse(c).expect("registry calendars exist"))
}

fn joint_business_day(d: Date) -> Result<bool> {
    for c in calendars() {
        if !c.is_business_day(d)? {
            return Ok(false);
        }
    }
    Ok(true)
}

fn modified_following(d: Date) -> Result<Date> {
    let mut x = d;
    while !joint_business_day(x)? {
        x = x.add_days(1);
    }
    if x.m != d.m {
        x = d;
        while !joint_business_day(x)? {
            x = x.add_days(-1);
        }
    }
    Ok(x)
}

/// Dates `start, e_1, ..., e_n`, quarterly, `MODIFIED_FOLLOWING` on the joint calendar.
pub fn schedule(start: Date, months: i64) -> Result<Vec<Date>> {
    if months <= 0 || months % 3 != 0 || months > 1200 {
        return fail("E_INPUT", "months must be a positive multiple of 3");
    }
    if !joint_business_day(start)? {
        return fail("E_INPUT", "start is not a business day on both calendars");
    }
    let mut out = vec![start];
    for k in 1..=months / 3 {
        out.push(modified_following(add_months(start, 3 * k))?);
    }
    Ok(out)
}

/// `L / N`: a leg with notional exchanges, per unit notional.
pub fn leg<P: Discount + ?Sized, D: Discount + ?Sized>(
    dates: &[Date],
    projection: &P,
    discount: &D,
    spread: f64,
) -> Result<f64> {
    crate::error::finite("spread", &spread)?;
    let mut v = 0.0;
    for w in dates.windows(2) {
        let (s, e) = (w[0], w[1]);
        let alpha = (e.serial() - s.serial()) as f64 / 360.0;
        let growth = projection.discount(s)? / projection.discount(e)? - 1.0;
        v += (growth + spread * alpha) * discount.discount(e)?;
    }
    let last = *dates.last().expect("dates");
    Ok(v + discount.discount(last)? - discount.discount(dates[0])?)
}

/// `fx.xccy.bootstrap`: the basis-adjusted foreign discount curve.
pub fn bootstrap(
    foreign_projection: &Curve,
    start: Date,
    quotes: &[(i64, f64)],
    interpolation: Interpolation,
) -> Result<Solved> {
    crate::error::finite("quotes", &quotes)?;
    if quotes.is_empty() {
        return fail("E_INPUT", "no quotes");
    }
    if quotes.windows(2).any(|w| w[1].0 <= w[0].0) {
        return fail("E_INPUT", "months must strictly increase");
    }
    let schedules = quotes
        .iter()
        .map(|q| schedule(start, q.0))
        .collect::<Result<Vec<_>>>()?;
    let as_of = foreign_projection.as_of;
    if start < as_of {
        return fail("E_OUT_OF_RANGE", "start is before as_of");
    }
    let dates: Vec<Date> = schedules
        .iter()
        .map(|s| *s.last().expect("dates"))
        .collect();
    let model = |c: &Curve, j: usize| leg(&schedules[j], foreign_projection, c, quotes[j].1);
    let zeros = vec![0.0; quotes.len()];
    solve_curve(
        as_of,
        interpolation,
        &dates,
        &zeros,
        &model,
        SolveMethod::Sequential,
    )
}

#[derive(Debug, Clone, Copy)]
pub struct XccyTrade {
    pub start: Date,
    pub months: i64,
    pub foreign_notional: f64,
    pub spread: f64,
    pub receive_foreign: bool,
}

/// `(pv, foreign_leg, domestic_leg)`.
pub fn pv(
    domestic: &Curve,
    foreign_projection: &Curve,
    foreign_discount: &Curve,
    spot: f64,
    t: &XccyTrade,
) -> Result<(f64, f64, f64)> {
    crate::error::finite("spot", &spot)?;
    crate::error::finite("t", &t)?;
    let dates = schedule(t.start, t.months)?;
    let f = t.foreign_notional * leg(&dates, foreign_projection, foreign_discount, t.spread)?;
    let d = t.foreign_notional * spot * leg(&dates, domestic, domestic, 0.0)?;
    let sign = if t.receive_foreign { 1.0 } else { -1.0 };
    Ok((sign * (spot * f - d), f, d))
}

#[derive(Debug, Clone, Copy)]
pub struct Ndf {
    pub fixing_date: Date,
    pub payment_date: Date,
    pub strike: f64,
    pub usd_notional: f64,
    pub buy: bool,
}

/// `fx.ndf.pv`: `(pv, forward)`.
pub fn ndf_pv(
    usd: &Curve,
    offshore: &Curve,
    spot: f64,
    t: &Ndf,
    fixing: Option<f64>,
) -> Result<(f64, f64)> {
    crate::error::finite("spot", &spot)?;
    crate::error::finite("t", &t)?;
    crate::error::finite("fixing", &fixing)?;
    if t.payment_date < t.fixing_date {
        return fail("E_DATE_ORDER", "payment_date is before fixing_date");
    }
    if t.fixing_date <= usd.as_of && fixing.is_none() {
        return fail("E_INPUT", "a past fixing must be given");
    }
    if spot <= 0.0 || t.strike <= 0.0 || fixing.is_some_and(|f| f <= 0.0) {
        return fail("E_DOMAIN", "spot, fixing and strike must be positive");
    }
    let du = usd.discount(t.payment_date)?;
    let f = match fixing {
        Some(f) => f,
        None => spot * du / offshore.discount(t.payment_date)?,
    };
    let sign = if t.buy { 1.0 } else { -1.0 };
    Ok((sign * t.usd_notional * (1.0 - t.strike / f) * du, f))
}

impl crate::error::Finite for Ndf {
    fn is_all_finite(&self) -> bool {
        self.strike.is_all_finite() && self.usd_notional.is_all_finite()
    }
}

impl crate::error::Finite for XccyTrade {
    fn is_all_finite(&self) -> bool {
        self.foreign_notional.is_all_finite() && self.spread.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::curve::curve_time;

    fn d(s: &str) -> Date {
        Date::parse(s).unwrap()
    }

    fn flat(r: f64) -> Curve {
        let as_of = d("2026-11-06");
        let p = d("2046-11-06");
        Curve::from_logs(
            as_of,
            Interpolation::LogLinearDf,
            &[p],
            &[-r * curve_time(as_of, p)],
        )
    }

    #[test]
    fn schedule_rules() {
        let s = schedule(d("2026-11-10"), 12).unwrap();
        assert_eq!(s.len(), 5);
        assert_eq!(s[4], d("2027-11-10"));
        assert_eq!(schedule(d("2026-11-10"), 10).unwrap_err().code, "E_INPUT");
        assert_eq!(schedule(d("2026-11-11"), 12).unwrap_err().code, "E_INPUT");
    }

    #[test]
    fn single_curve_leg_is_par_and_bootstrap_replays() {
        let c = flat(0.03);
        let dates = schedule(d("2026-11-10"), 24).unwrap();
        assert!(leg(&dates, &c, &c, 0.0).unwrap().abs() < 1e-15);
        let q = [(12, 0.001), (36, 0.002)];
        let s = bootstrap(&c, d("2026-11-10"), &q, Interpolation::LogLinearDf).unwrap();
        for (j, (m, sp)) in q.iter().enumerate() {
            let dates = schedule(d("2026-11-10"), *m).unwrap();
            assert!(leg(&dates, &c, &s.curve, *sp).unwrap().abs() < 1e-13, "{j}");
        }
        let bad = [(36, 0.001), (12, 0.002)];
        let e = bootstrap(&c, d("2026-11-10"), &bad, Interpolation::LogLinearDf).unwrap_err();
        assert_eq!(e.code, "E_INPUT");
        assert!(bootstrap(&c, d("2026-11-10"), &[], Interpolation::LogLinearDf).is_err());
    }

    #[test]
    fn pv_sign_and_parity() {
        let c = flat(0.03);
        let t = XccyTrade {
            start: d("2026-11-10"),
            months: 24,
            foreign_notional: 1e6,
            spread: 0.001,
            receive_foreign: true,
        };
        let (p, f, dom) = pv(&c, &c, &c, 1.1, &t).unwrap();
        assert!(dom.abs() < 1e-8 && f > 0.0 && (p - 1.1 * f).abs() < 1e-8);
        let (q, _, _) = pv(
            &c,
            &c,
            &c,
            1.1,
            &XccyTrade {
                receive_foreign: false,
                ..t
            },
        )
        .unwrap();
        assert_eq!(q, -p);
    }

    #[test]
    fn ndf_cases() {
        let (u, o) = (flat(0.04), flat(0.06));
        let t = Ndf {
            fixing_date: d("2027-05-06"),
            payment_date: d("2027-05-10"),
            strike: 90.0,
            usd_notional: 1e6,
            buy: true,
        };
        let (p, f) = ndf_pv(&u, &o, 88.0, &t, None).unwrap();
        let du = u.discount(t.payment_date).unwrap();
        assert!((f - 88.0 * du / o.discount(t.payment_date).unwrap()).abs() < 1e-12);
        assert!((p - 1e6 * (1.0 - 90.0 / f) * du).abs() < 1e-8);
        let past = Ndf {
            fixing_date: d("2026-11-05"),
            payment_date: d("2026-11-09"),
            ..t
        };
        assert_eq!(
            ndf_pv(&u, &o, 88.0, &past, None).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(ndf_pv(&u, &o, 88.0, &past, Some(88.6)).unwrap().1, 88.6);
        assert_eq!(
            ndf_pv(&u, &o, 88.0, &past, Some(-1.0)).unwrap_err().code,
            "E_DOMAIN"
        );
        let swapped = Ndf {
            fixing_date: t.payment_date,
            payment_date: t.fixing_date,
            ..t
        };
        assert_eq!(
            ndf_pv(&u, &o, 88.0, &swapped, None).unwrap_err().code,
            "E_DATE_ORDER"
        );
    }

    #[test]
    fn leg_spread_is_its_annuity_and_schedule_edges() {
        let c = flat(0.03);
        let dates = schedule(d("2026-11-10"), 12).unwrap();
        let ann: f64 = dates
            .windows(2)
            .map(|w| (w[1].serial() - w[0].serial()) as f64 / 360.0 * c.discount(w[1]).unwrap())
            .sum();
        let v = leg(&dates, &c, &c, 0.002).unwrap();
        assert!((v - 0.002 * ann).abs() < 1e-15, "{v} {ann}");
        // Month end on a Sunday rolls back inside the month (modified following).
        let s = schedule(d("2026-11-30"), 3).unwrap();
        assert_eq!(s[1], d("2027-02-26"));
        // A plain weekend inside the month rolls forward.
        let s = schedule(d("2026-11-16"), 3).unwrap();
        assert_eq!(s[1], d("2027-02-16"));
        for m in [0, -3, 1203] {
            assert_eq!(schedule(d("2026-11-10"), m).unwrap_err().code, "E_INPUT");
        }
        assert_eq!(schedule(d("2026-11-10"), 600).unwrap().len(), 201);
        let e = bootstrap(
            &c,
            d("2026-11-05"),
            &[(12, 0.0)],
            Interpolation::LogLinearDf,
        )
        .unwrap_err();
        assert_eq!(e.code, "E_OUT_OF_RANGE");
    }

    #[test]
    fn pv_uses_spot_and_both_legs() {
        let (dom, fp) = (flat(0.04), flat(0.03));
        let t = XccyTrade {
            start: d("2026-11-10"),
            months: 12,
            foreign_notional: 1e6,
            spread: 0.001,
            receive_foreign: true,
        };
        let (p, f, dl) = pv(&dom, &fp, &fp, 1.25, &t).unwrap();
        let dates = schedule(t.start, 12).unwrap();
        let fe = 1e6 * leg(&dates, &fp, &fp, 0.001).unwrap();
        let de = 1e6 * 1.25 * leg(&dates, &dom, &dom, 0.0).unwrap();
        assert_eq!(f, fe);
        assert_eq!(dl, de);
        assert_eq!(p, 1.25 * fe - de);
    }

    #[test]
    fn ndf_sell_and_domain_errors() {
        let (u, o) = (flat(0.04), flat(0.06));
        let t = Ndf {
            fixing_date: d("2027-05-06"),
            payment_date: d("2027-05-06"),
            strike: 90.0,
            usd_notional: 1e6,
            buy: false,
        };
        let (p, f) = ndf_pv(&u, &o, 88.0, &t, None).unwrap();
        let du = u.discount(t.payment_date).unwrap();
        assert!((p + 1e6 * (1.0 - 90.0 / f) * du).abs() < 1e-8);
        assert!(p > 0.0);
        for (spot, k) in [(0.0, 90.0), (88.0, 0.0), (-1.0, 90.0)] {
            let t2 = Ndf { strike: k, ..t };
            assert_eq!(
                ndf_pv(&u, &o, spot, &t2, None).unwrap_err().code,
                "E_DOMAIN"
            );
        }
        let on_as_of = Ndf {
            fixing_date: u.as_of,
            payment_date: d("2026-11-12"),
            ..t
        };
        assert_eq!(
            ndf_pv(&u, &o, 88.0, &on_as_of, None).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(
            ndf_pv(&u, &o, 88.0, &on_as_of, Some(0.0)).unwrap_err().code,
            "E_DOMAIN"
        );
    }
}
