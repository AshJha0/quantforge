//! Stage D wave 3: caps and swaptions (`caps-and-swaptions.md`), commodity curves and storage
//! (`commodity.md`), MBS (`mbs.md`).
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

/// `cmdty.curve.forward`. Quotes and months are month indices.
pub fn commodity_forwards(
    quotes: &[(i64, f64)],
    seasonality: Option<&[f64]>,
    months: &[i64],
) -> Result<Vec<f64>> {
    if quotes.is_empty() || quotes.windows(2).any(|w| w[1].0 <= w[0].0) {
        return fail("E_INPUT", "quote months must strictly increase");
    }
    if quotes.iter().any(|q| q.1 <= 0.0) {
        return fail("E_DOMAIN", "a price is not positive");
    }
    if seasonality.is_some_and(|s| s.len() != 12) {
        return fail("E_INPUT", "seasonality needs 12 terms");
    }
    let sigma = |k: i64| seasonality.map_or(0.0, |s| s[k.rem_euclid(12) as usize]);
    let l: Vec<f64> = quotes.iter().map(|(k, p)| p.ln() - sigma(*k)).collect();
    let (first, last) = (quotes[0].0, quotes[quotes.len() - 1].0);
    months
        .iter()
        .map(|k| {
            if *k < first || *k > last {
                return fail("E_OUT_OF_RANGE", "month is outside the quoted range");
            }
            let i = quotes.partition_point(|q| q.0 <= *k).saturating_sub(1);
            let lk = if i + 1 >= quotes.len() {
                l[i]
            } else {
                let u = (k - quotes[i].0) as f64 / (quotes[i + 1].0 - quotes[i].0) as f64;
                (1.0 - u) * l[i] + u * l[i + 1]
            };
            Ok((lk + sigma(*k)).exp())
        })
        .collect()
}

/// `cmdty.storage.carry`: `(convenience_yields, carry_values, arbitrage)`.
pub fn storage_carry(
    funding: &Curve,
    forwards: &[(Date, f64)],
    u: f64,
) -> Result<(Vec<f64>, Vec<f64>, Vec<bool>)> {
    if forwards.len() < 2
        || forwards[0].0 <= funding.as_of
        || forwards.windows(2).any(|w| w[1].0 <= w[0].0)
    {
        return fail(
            "E_INPUT",
            "at least two forwards, dates increasing after as_of",
        );
    }
    if u < 0.0 {
        return fail("E_DOMAIN", "storage_cost must not be negative");
    }
    if forwards.iter().any(|f| f.1 <= 0.0) {
        return fail("E_DOMAIN", "a forward price is not positive");
    }
    let (mut ys, mut cs, mut arb) = (Vec::new(), Vec::new(), Vec::new());
    for w in forwards.windows(2) {
        let ((d0, f0), (d1, f1)) = (w[0], w[1]);
        let dt = (d1.serial() - d0.serial()) as f64 / 365.0;
        let (p0, p1) = (funding.discount(d0)?, funding.discount(d1)?);
        let r = (p0 / p1).ln() / dt;
        ys.push(r + u - (f1 / f0).ln() / dt);
        let c = p1 * f1 - p0 * f0 * (u * dt).exp();
        cs.push(c);
        arb.push(c > 0.0);
    }
    Ok((ys, cs, arb))
}

#[derive(Debug, Clone, Copy)]
pub enum Prepayment {
    Cpr(f64),
    Psa(f64),
}

#[derive(Debug, Clone, Copy)]
pub struct Pool {
    pub balance: f64,
    pub wac: f64,
    pub net_coupon: f64,
    pub wam: i64,
    pub age: i64,
    pub prepayment: Prepayment,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MbsFlows {
    pub balance: Vec<f64>,
    pub interest: Vec<f64>,
    pub scheduled_principal: Vec<f64>,
    pub prepayment: Vec<f64>,
    pub wal: f64,
}

/// `mbs.cashflows`. Checks as golden `mbs_d-0011` orders them: `wac <= 0` first.
pub fn mbs_cashflows(p: &Pool) -> Result<MbsFlows> {
    if p.wac <= 0.0 {
        return fail("E_DOMAIN", "wac must be positive");
    }
    if p.wam < 1 || p.wam > 1200 || p.age < 0 || p.net_coupon > p.wac {
        return fail("E_INPUT", "wam, age or net_coupon out of range");
    }
    let bad = match p.prepayment {
        Prepayment::Cpr(r) => !(0.0..1.0).contains(&r),
        Prepayment::Psa(s) => s < 0.0,
    };
    if p.balance <= 0.0 || bad {
        return fail("E_DOMAIN", "balance or prepayment out of range");
    }
    let r = p.wac / 12.0;
    let n_total = p.wam as usize;
    let mut out = MbsFlows {
        balance: Vec::with_capacity(n_total),
        interest: Vec::with_capacity(n_total),
        scheduled_principal: Vec::with_capacity(n_total),
        prepayment: Vec::with_capacity(n_total),
        wal: 0.0,
    };
    let mut b = p.balance;
    let mut wal = 0.0;
    for k in 1..=p.wam {
        let cpr = match p.prepayment {
            Prepayment::Cpr(x) => x,
            Prepayment::Psa(s) => (((p.age + k) as f64) / 30.0).min(1.0) * 0.06 * s / 100.0,
        };
        let smm = 1.0 - (1.0 - cpr).powf(1.0 / 12.0);
        let n = (p.wam - k + 1) as f64;
        let sched = if k == p.wam {
            b
        } else {
            b * r / (1.0 - (1.0 + r).powf(-n)) - b * r
        };
        let prepay = smm * (b - sched);
        out.balance.push(b);
        out.interest.push(b * p.net_coupon / 12.0);
        out.scheduled_principal.push(sched);
        out.prepayment.push(prepay);
        wal += k as f64 / 12.0 * (sched + prepay);
        b = b - sched - prepay;
    }
    out.wal = wal / p.balance;
    Ok(out)
}

/// `mbs.price`: `(price, modified_duration, wal)`.
pub fn mbs_price(p: &Pool, y: f64, delay_days: i64) -> Result<(f64, f64, f64)> {
    if delay_days < 0 {
        return fail("E_INPUT", "delay_days must not be negative");
    }
    let f = mbs_cashflows(p)?;
    if 1.0 + y / 12.0 <= 0.0 {
        return fail("E_DOMAIN", "1 + y/12 must be positive");
    }
    let v = 1.0 / (1.0 + y / 12.0);
    let (mut pv, mut dur) = (0.0, 0.0);
    for k in 0..f.balance.len() {
        let cf = f.interest[k] + f.scheduled_principal[k] + f.prepayment[k];
        let t = (k + 1) as f64 + delay_days as f64 / 30.0;
        let x = cf * v.powf(t);
        pv += x;
        dur += t / 12.0 * x * v;
    }
    Ok((100.0 * pv / p.balance, dur / pv, f.wal))
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

    #[test]
    fn commodity_curve_and_carry() {
        let q = [(100, 3.0), (103, 3.3)];
        let s: Vec<f64> = (0..12).map(|i| f64::from(i) * 0.01).collect();
        let f = commodity_forwards(&q, Some(&s), &[100, 103]).unwrap();
        assert!((f[0] - 3.0).abs() < 1e-14 && (f[1] - 3.3).abs() < 1e-14);
        let mid = commodity_forwards(&q, None, &[101]).unwrap()[0];
        assert!((mid - (3.0f64.ln() * 2.0 / 3.0 + 3.3f64.ln() / 3.0).exp()).abs() < 1e-14);
        assert_eq!(
            commodity_forwards(&q, None, &[99]).unwrap_err().code,
            "E_OUT_OF_RANGE"
        );
        assert_eq!(
            commodity_forwards(&[q[1], q[0]], None, &[101])
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        assert_eq!(
            commodity_forwards(&[(1, 0.0)], None, &[1])
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        assert_eq!(
            commodity_forwards(&q, Some(&s[..6]), &[101])
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        let c = flat(0.04);
        let fw = [(d("2026-12-15"), 75.0), (d("2027-12-15"), 70.0)];
        let (y, v, a) = storage_carry(&c, &fw, 0.02).unwrap();
        assert!(y[0] > 0.0 && v[0] < 0.0 && !a[0]);
        let up = [(d("2026-12-15"), 70.0), (d("2027-12-15"), 80.0)];
        assert!(storage_carry(&c, &up, 0.0).unwrap().2[0]);
        assert_eq!(
            storage_carry(&c, &fw[..1], 0.02).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(storage_carry(&c, &fw, -0.01).unwrap_err().code, "E_DOMAIN");
    }

    fn pool(pre: Prepayment) -> Pool {
        Pool {
            balance: 1e6,
            wac: 0.06,
            net_coupon: 0.055,
            wam: 60,
            age: 0,
            prepayment: pre,
        }
    }

    #[test]
    fn mbs_amortises_and_prices() {
        let f = mbs_cashflows(&pool(Prepayment::Cpr(0.0))).unwrap();
        let paid: f64 = f.scheduled_principal.iter().sum();
        assert!((paid - 1e6).abs() < 1e-6);
        let f = mbs_cashflows(&pool(Prepayment::Psa(150.0))).unwrap();
        let paid: f64 = f.scheduled_principal.iter().chain(&f.prepayment).sum();
        assert!((paid - 1e6).abs() < 1e-6);
        let (p, dur, wal) = mbs_price(&pool(Prepayment::Psa(150.0)), 0.055, 0).unwrap();
        assert!((p - 100.0).abs() < 1e-9, "{p}");
        assert!(dur > 0.0 && wal == f.wal);
        let e = |q: Pool| mbs_cashflows(&q).unwrap_err().code;
        let b = pool(Prepayment::Cpr(0.05));
        assert_eq!(
            e(Pool {
                net_coupon: 0.07,
                ..b
            }),
            "E_INPUT"
        );
        assert_eq!(e(Pool { wam: 0, ..b }), "E_INPUT");
        assert_eq!(e(Pool { wac: 0.0, ..b }), "E_DOMAIN");
        assert_eq!(e(pool(Prepayment::Cpr(1.0))), "E_DOMAIN");
        assert_eq!(e(pool(Prepayment::Psa(-1.0))), "E_DOMAIN");
        assert_eq!(mbs_price(&b, 0.05, -1).unwrap_err().code, "E_INPUT");
    }
}
