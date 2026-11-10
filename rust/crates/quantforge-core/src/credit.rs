//! ISDA CDS, index intrinsic and composite curves (`04-pricing/credit.md`).
use crate::curve::Curve;
use crate::dates::Date;

use crate::error::{Result, err, fail};
use crate::schedule::add_months;

/// Survival curve: `-ln Q` linear in time between pillars, flat hazard after the last.
#[derive(Debug, Clone)]
pub struct Hazard {
    pub as_of: Date,
    dates: Vec<Date>,
    logs: Vec<f64>,
}

fn years(a: Date, b: Date) -> f64 {
    (b.serial() - a.serial()) as f64 / 365.0
}

impl Hazard {
    pub fn new(as_of: Date, pillars: &[(Date, f64)]) -> Result<Hazard> {
        crate::error::finite("pillars", &pillars)?;
        if pillars.is_empty()
            || pillars[0].0 <= as_of
            || pillars.windows(2).any(|w| w[1].0 <= w[0].0)
        {
            return fail("E_INPUT", "hazard pillars must increase and follow as_of");
        }
        if pillars.iter().any(|p| p.1 <= 0.0 || p.1 > 1.0) {
            return fail("E_DOMAIN", "a survival probability is outside (0, 1]");
        }
        Ok(Hazard::from_logs(
            as_of,
            &pillars.iter().map(|p| p.0).collect::<Vec<_>>(),
            &pillars.iter().map(|p| p.1.ln()).collect::<Vec<_>>(),
        ))
    }

    fn from_logs(as_of: Date, dates: &[Date], logs: &[f64]) -> Hazard {
        let mut d = vec![as_of];
        d.extend_from_slice(dates);
        let mut l = vec![0.0];
        l.extend_from_slice(logs);
        Hazard {
            as_of,
            dates: d,
            logs: l,
        }
    }

    pub fn pillars(&self) -> Vec<(Date, f64)> {
        self.dates[1..]
            .iter()
            .zip(&self.logs[1..])
            .map(|(d, l)| (*d, l.exp()))
            .collect()
    }

    pub fn survival(&self, d: Date) -> Result<f64> {
        if d < self.as_of {
            return fail("E_OUT_OF_RANGE", "date is before the hazard curve's as_of");
        }
        let n = self.dates.len() - 1;
        let i = self
            .dates
            .partition_point(|x| *x <= d)
            .saturating_sub(1)
            .min(n - 1);
        let (t0, t1) = (
            years(self.as_of, self.dates[i]),
            years(self.as_of, self.dates[i + 1]),
        );
        let t = years(self.as_of, d);
        let u = (t - t0) / (t1 - t0);
        Ok((self.logs[i] + u * (self.logs[i + 1] - self.logs[i])).exp())
    }
}

fn weekday_on_or_after(d: Date) -> Date {
    let mut x = d;
    while x.is_weekend() {
        x = x.add_days(1);
    }
    x
}

fn add_weekdays(d: Date, n: i64) -> Date {
    let mut x = d;
    for _ in 0..n {
        x = x.add_days(1);
        while x.is_weekend() {
            x = x.add_days(1);
        }
    }
    x
}

/// Roll date for standard tenors.
pub fn roll_date(t: Date) -> Date {
    let (y, md) = (t.y, (t.m, t.d));
    if md >= (9, 20) {
        Date::new(y, 12, 20)
    } else if md >= (3, 20) {
        Date::new(y, 6, 20)
    } else {
        Date::new(y - 1, 12, 20)
    }
}

pub fn tenor_maturity(t: Date, tenor: (i64, char)) -> Result<Date> {
    let months = match tenor.1 {
        'M' => tenor.0,
        'Y' => 12 * tenor.0,
        _ => return fail("E_INPUT", "CDS tenors are in months or years"),
    };
    if months <= 0 || months > 1200 {
        return fail("E_INPUT", "tenor out of range");
    }
    Ok(add_months(roll_date(t), months))
}

/// Accrual period: adjusted start, end (maturity unadjusted), payment, accrual fraction.
#[derive(Debug, Clone, Copy)]
struct Period {
    start: Date,
    payment: Date,
    alpha: f64,
}

fn last_imm_on_or_before(t: Date) -> Date {
    let m = (t.m - 1) / 3 * 3 + 3;
    let candidate = Date::new(t.y, m, 20);
    if candidate <= t {
        candidate
    } else {
        add_months(candidate, -3)
    }
}

fn periods(t: Date, maturity: Date) -> Result<Vec<Period>> {
    if maturity <= t {
        return fail("E_INPUT", "maturity is not after the trade date");
    }
    let first = last_imm_on_or_before(t);
    if weekday_on_or_after(first) == t {
        return fail("E_INPUT", "trade date is on an adjusted coupon date");
    }
    let mut raw = vec![first];
    let mut k = 1;
    loop {
        let d = add_months(first, 3 * k);
        if d >= maturity {
            raw.push(maturity);
            break;
        }
        raw.push(d);
        k += 1;
    }
    let n = raw.len() - 1;
    let mut out = Vec::new();
    for i in 0..n {
        let start = weekday_on_or_after(raw[i]);
        let end = if i + 1 == n {
            maturity
        } else {
            weekday_on_or_after(raw[i + 1])
        };
        let payment = weekday_on_or_after(raw[i + 1]);
        let extra = if i + 1 == n { 1.0 } else { 0.0 };
        let alpha = ((end.serial() - start.serial()) as f64 + extra) / 360.0;
        out.push(Period {
            start,
            payment,
            alpha,
        });
    }
    Ok(out)
}

/// `(t0, D, h, k, QP0)` for one integration piece.
type Piece = (f64, f64, f64, f64, f64);

/// A tenor quote: `(tenor, spread)`.
pub type CdsQuote = ((i64, char), f64);

struct Engine<'a> {
    t: Date,
    discount: &'a Curve,
    hazard: &'a Hazard,
    nodes: Vec<Date>,
}

/// `(1 - e^{-x})/x` and `(1 - e^{-x}(1 + x))/x^2`, with series near 0.
fn e_terms(x: f64) -> (f64, f64) {
    if x.abs() < 1e-4 {
        let a = 1.0 - x / 2.0 + x * x / 6.0 - x * x * x / 24.0 + x * x * x * x / 120.0;
        let b = 0.5 - x / 3.0 + x * x / 8.0 - x * x * x / 30.0 + x * x * x * x / 144.0;
        (a, b)
    } else {
        let e = (-x).exp();
        (-(-x).exp_m1() / x, (1.0 - e * (1.0 + x)) / (x * x))
    }
}

impl Engine<'_> {
    fn qp(&self, d: Date) -> Result<(f64, f64)> {
        Ok((self.hazard.survival(d)?, self.discount.discount(d)?))
    }

    /// Pieces of `[a, b]` split at the nodes: `(t0, D, h, k, QP0)`.
    fn pieces(&self, a: Date, b: Date) -> Result<Vec<Piece>> {
        let mut cuts = vec![a];
        cuts.extend(self.nodes.iter().copied().filter(|d| *d > a && *d < b));
        cuts.push(b);
        let mut out = Vec::new();
        for w in cuts.windows(2) {
            let (q0, p0) = self.qp(w[0])?;
            let (q1, p1) = self.qp(w[1])?;
            let (t0, t1) = (years(self.t, w[0]), years(self.t, w[1]));
            let dt = t1 - t0;
            if dt <= 0.0 {
                continue;
            }
            let h = (q0 / q1).ln() / dt;
            let f = (p0 / p1).ln() / dt;
            out.push((t0, dt, h, f + h, q0 * p0));
        }
        Ok(out)
    }

    fn protection(&self, maturity: Date) -> Result<f64> {
        let mut v = 0.0;
        for (_, dt, h, k, qp0) in self.pieces(self.t, maturity)? {
            v += h * qp0 * dt * e_terms(k * dt).0;
        }
        Ok(v)
    }

    fn rpv01(&self, periods: &[Period]) -> Result<f64> {
        let mut v = 0.0;
        for p in periods {
            let obs = p.payment.add_days(-1);
            v += p.alpha * self.hazard.survival(obs)? * self.discount.discount(p.payment)?;
            let acc_start = p.start.add_days(-1);
            let s = acc_start.max(self.t);
            let tacc = years(self.t, acc_start);
            let mut aod = 0.0;
            for (t0, dt, h, k, qp0) in self.pieces(s, obs)? {
                let (a, b) = e_terms(k * dt);
                aod += h * qp0 * ((t0 - tacc) * dt * a + dt * dt * b);
            }
            v += 365.0 / 360.0 * aod;
        }
        Ok(v)
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CdsPrice {
    pub protection_leg: f64,
    pub rpv01: f64,
    pub accrued: f64,
    pub par_spread: f64,
    pub upfront: f64,
    pub pv: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct CdsTrade {
    pub maturity: Date,
    pub coupon: f64,
    pub notional: f64,
    pub buy: bool,
}

fn check_recovery(r: f64) -> Result<()> {
    if !(0.0..1.0).contains(&r) {
        return fail("E_DOMAIN", "recovery must be in [0, 1)");
    }
    Ok(())
}

/// Ruling D36: every curve's `as_of` is the trade date.
fn check_as_of(t: Date, discount: &Curve, hazard: &Hazard) -> Result<()> {
    if discount.as_of != t || hazard.as_of != t {
        return fail("E_INPUT", "curves must have as_of = trade_date");
    }
    Ok(())
}

fn nodes(hazard: &Hazard, pillars: &[Date]) -> Vec<Date> {
    let mut n: Vec<Date> = hazard.dates[1..].to_vec();
    n.extend_from_slice(pillars);
    n.sort();
    n.dedup();
    n
}

/// `credit.cds.price`. `digital` pays 1 in place of `1 - R`.
pub fn price(
    t: Date,
    discount: &Curve,
    discount_pillars: &[Date],
    hazard: &Hazard,
    recovery: f64,
    trade: &CdsTrade,
    digital: bool,
) -> Result<CdsPrice> {
    crate::error::finite("recovery", &recovery)?;
    crate::error::finite("trade", &trade)?;
    check_recovery(recovery)?;
    check_as_of(t, discount, hazard)?;
    let ps = periods(t, trade.maturity)?;
    let e = Engine {
        t,
        discount,
        hazard,
        nodes: nodes(hazard, discount_pillars),
    };
    let lgd = if digital { 1.0 } else { 1.0 - recovery };
    let protection_leg = lgd * e.protection(trade.maturity)?;
    let rpv01 = e.rpv01(&ps)?;
    let accrued_days = (t.add_days(1).serial() - ps[0].start.serial()) as f64 / 360.0;
    let accrued = trade.coupon * accrued_days;
    let pcs = discount.discount(add_weekdays(t, 3))?;
    let par_spread = protection_leg / (rpv01 - accrued_days * pcs);
    let upfront = (protection_leg - trade.coupon * rpv01) / pcs + accrued;
    let sign = if trade.buy { 1.0 } else { -1.0 };
    let pv = sign * trade.notional * (protection_leg - trade.coupon * rpv01 + accrued * pcs);
    Ok(CdsPrice {
        protection_leg,
        rpv01,
        accrued,
        par_spread,
        upfront,
        pv,
    })
}

/// `credit.cds.bootstrap`: survival pillars at each quote's maturity.
pub fn bootstrap(
    t: Date,
    discount: &Curve,
    discount_pillars: &[Date],
    recovery: f64,
    quotes: &[((i64, char), f64)],
) -> Result<Hazard> {
    crate::error::finite("recovery", &recovery)?;
    check_recovery(recovery)?;
    if discount.as_of != t {
        return fail("E_INPUT", "discount as_of must be trade_date");
    }
    if quotes.is_empty() {
        return fail("E_INPUT", "no quotes");
    }
    let maturities = quotes
        .iter()
        .map(|q| tenor_maturity(t, q.0))
        .collect::<Result<Vec<_>>>()?;
    if maturities.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "maturities must strictly increase");
    }
    if quotes.iter().any(|q| q.1 <= 0.0) {
        return fail("E_DOMAIN", "a spread is not positive");
    }
    periods(t, maturities[0])?;
    let mut logs: Vec<f64> = Vec::new();
    let no = || err("E_NO_CONVERGENCE", "the hazard bootstrap failed");
    for (j, q) in quotes.iter().enumerate() {
        let par = |x: f64| -> Result<f64> {
            let mut l = logs.clone();
            l.push(x);
            let h = Hazard::from_logs(t, &maturities[..=j], &l);
            let trade = CdsTrade {
                maturity: maturities[j],
                coupon: q.1,
                notional: 1.0,
                buy: true,
            };
            Ok(price(t, discount, discount_pillars, &h, recovery, &trade, false)?.par_spread - q.1)
        };
        let prev = if j == 0 { t } else { maturities[j - 1] };
        let mut x = logs.last().copied().unwrap_or(0.0)
            - q.1 / (1.0 - recovery) * years(prev, maturities[j]);
        let (mut best, mut best_x) = (f64::INFINITY, x);
        for _ in 0..80 {
            let e = par(x)?;
            if !e.is_finite() {
                return Err(no());
            }
            if e.abs() < best {
                (best, best_x) = (e.abs(), x);
            }
            if e.abs() <= 1e-16 {
                break;
            }
            let hstep = 1e-7;
            let slope = (par(x + hstep)? - par(x - hstep)?) / (2.0 * hstep);
            let step = e / slope;
            if !step.is_finite() {
                return Err(no());
            }
            if step.abs() <= 1e-17 {
                break;
            }
            x -= step;
        }
        if best >= 1e-13 {
            return Err(no());
        }
        logs.push(best_x);
    }
    Ok(Hazard::from_logs(t, &maturities, &logs))
}

/// `credit.index.intrinsic`: `(name_upfronts, intrinsic_upfront)`.
pub fn index_intrinsic(
    t: Date,
    discount: &Curve,
    discount_pillars: &[Date],
    names: &[(Hazard, f64, f64)],
    maturity: Date,
    coupon: f64,
) -> Result<(Vec<f64>, f64)> {
    crate::error::finite("coupon", &coupon)?;
    if names.is_empty() {
        return fail("E_INPUT", "no names");
    }
    if names.iter().any(|n| n.2 < 0.0) || names.iter().map(|n| n.2).sum::<f64>() <= 0.0 {
        return fail("E_DOMAIN", "a weight is negative, or the weights sum to 0");
    }
    for (h, _, _) in names {
        check_as_of(t, discount, h)?;
    }
    let trade = CdsTrade {
        maturity,
        coupon,
        notional: 1.0,
        buy: true,
    };
    let mut ups = Vec::new();
    let (mut sum, mut wsum) = (0.0, 0.0);
    for (h, r, w) in names {
        let u = price(t, discount, discount_pillars, h, *r, &trade, false)?.upfront;
        ups.push(u);
        sum += w * u;
        wsum += w;
    }
    if wsum <= 0.0 {
        return fail("E_DOMAIN", "weights must sum above zero");
    }
    Ok((ups, sum / wsum))
}

/// `credit.curve.composite`: blended spreads, scaled.
pub fn composite_spreads(
    constituents: &[(Vec<CdsQuote>, f64)],
    scale: f64,
) -> Result<Vec<((i64, char), f64)>> {
    crate::error::finite("scale", &scale)?;
    if constituents.is_empty() {
        return fail("E_INPUT", "no constituents");
    }
    let tenors: Vec<(i64, char)> = constituents[0].0.iter().map(|q| q.0).collect();
    if constituents
        .iter()
        .any(|c| c.0.iter().map(|q| q.0).collect::<Vec<_>>() != tenors)
    {
        return fail("E_INPUT", "constituents are on different tenors");
    }
    if scale <= 0.0 || constituents.iter().any(|c| c.1 < 0.0) {
        return fail(
            "E_DOMAIN",
            "scale must be positive and weights not negative",
        );
    }
    let wsum: f64 = constituents.iter().map(|c| c.1).sum();
    if wsum <= 0.0 {
        return fail("E_DOMAIN", "weights must sum above zero");
    }
    Ok(tenors
        .iter()
        .enumerate()
        .map(|(k, t)| {
            let s: f64 = constituents.iter().map(|c| c.1 * c.0[k].1).sum();
            (*t, scale * s / wsum)
        })
        .collect())
}

impl crate::error::Finite for CdsPrice {
    fn is_all_finite(&self) -> bool {
        self.protection_leg.is_all_finite()
            && self.rpv01.is_all_finite()
            && self.accrued.is_all_finite()
            && self.par_spread.is_all_finite()
            && self.upfront.is_all_finite()
            && self.pv.is_all_finite()
    }
}

impl crate::error::Finite for CdsTrade {
    fn is_all_finite(&self) -> bool {
        self.coupon.is_all_finite() && self.notional.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::curve::{Interpolation, curve_time};

    fn d(s: &str) -> Date {
        Date::parse(s).unwrap()
    }

    fn flat() -> (Curve, Vec<Date>) {
        let as_of = d("2026-11-06");
        let p = d("2046-11-06");
        let c = Curve::from_logs(
            as_of,
            Interpolation::LogLinearDf,
            &[p],
            &[-0.04 * curve_time(as_of, p)],
        );
        (c, vec![p])
    }

    #[test]
    fn dates() {
        assert_eq!(roll_date(d("2026-11-06")), d("2026-12-20"));
        assert_eq!(roll_date(d("2026-03-19")), d("2025-12-20"));
        assert_eq!(roll_date(d("2026-03-20")), d("2026-06-20"));
        assert_eq!(
            tenor_maturity(d("2026-11-06"), (6, 'M')).unwrap(),
            d("2027-06-20")
        );
        let p = periods(d("2026-11-06"), d("2027-06-20")).unwrap();
        assert_eq!(p[0].start, d("2026-09-21"));
        assert_eq!(p.last().unwrap().payment, d("2027-06-21"));
        assert_eq!(
            periods(d("2026-12-21"), d("2027-06-20")).unwrap_err().code,
            "E_INPUT"
        );
    }

    #[test]
    fn bootstrap_reprices_and_price_agrees() {
        let (c, pil) = flat();
        let t = d("2026-11-06");
        let q = [((1, 'Y'), 0.006), ((5, 'Y'), 0.012)];
        let h = bootstrap(t, &c, &pil, 0.4, &q).unwrap();
        for (tenor, s) in q {
            let tr = CdsTrade {
                maturity: tenor_maturity(t, tenor).unwrap(),
                coupon: 0.01,
                notional: 1e7,
                buy: true,
            };
            let p = price(t, &c, &pil, &h, 0.4, &tr, false).unwrap();
            assert!((p.par_spread - s).abs() < 1e-13);
            let sell = price(t, &c, &pil, &h, 0.4, &CdsTrade { buy: false, ..tr }, false).unwrap();
            assert_eq!(sell.pv, -p.pv);
            let dig = price(t, &c, &pil, &h, 0.4, &tr, true).unwrap();
            assert!((dig.protection_leg - p.protection_leg / 0.6).abs() < 1e-15);
        }
        assert_eq!(
            bootstrap(t, &c, &pil, 1.0, &q).unwrap_err().code,
            "E_DOMAIN"
        );
        let rev = [q[1], q[0]];
        assert_eq!(
            bootstrap(t, &c, &pil, 0.4, &rev).unwrap_err().code,
            "E_INPUT"
        );
        let neg = [((5, 'Y'), -0.001)];
        assert_eq!(
            bootstrap(t, &c, &pil, 0.4, &neg).unwrap_err().code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn index_and_composite() {
        let (c, pil) = flat();
        let t = d("2026-11-06");
        let h = Hazard::new(t, &[(d("2031-12-20"), 0.9)]).unwrap();
        let m = d("2031-12-20");
        let (u, i) = index_intrinsic(
            t,
            &c,
            &pil,
            &[(h.clone(), 0.4, 1.0), (h, 0.4, 3.0)],
            m,
            0.01,
        )
        .unwrap();
        assert!((u[0] - i).abs() < 1e-15);
        assert_eq!(
            index_intrinsic(t, &c, &pil, &[], m, 0.01).unwrap_err().code,
            "E_INPUT"
        );
        let a = vec![((1, 'Y'), 0.01), ((5, 'Y'), 0.02)];
        let b = vec![((1, 'Y'), 0.02), ((5, 'Y'), 0.04)];
        let s = composite_spreads(&[(a.clone(), 1.0), (b, 1.0)], 2.0).unwrap();
        assert!((s[0].1 - 0.03).abs() < 1e-16);
        let short = vec![((1, 'Y'), 0.01)];
        assert_eq!(
            composite_spreads(&[(a.clone(), 1.0), (short, 1.0)], 1.0)
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        assert_eq!(
            composite_spreads(&[(a, 1.0)], 0.0).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(Hazard::new(t, &[(t, 0.9)]).unwrap_err().code, "E_INPUT");
        assert_eq!(Hazard::new(t, &[(m, 0.0)]).unwrap_err().code, "E_DOMAIN");
    }

    #[test]
    fn rulings_d36_d37() {
        let (c, pil) = flat();
        let t = d("2026-11-06");
        let m = d("2031-12-20");
        let h = Hazard::new(t, &[(m, 0.9)]).unwrap();
        let neg = [(h.clone(), 0.4, -1.0)];
        assert_eq!(
            index_intrinsic(t, &c, &pil, &neg, m, 0.01)
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        let zero = [(h, 0.4, 0.0)];
        assert_eq!(
            index_intrinsic(t, &c, &pil, &zero, m, 0.01)
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        let later = Hazard::new(d("2026-11-09"), &[(m, 0.9)]).unwrap();
        let tr = CdsTrade {
            maturity: m,
            coupon: 0.01,
            notional: 1.0,
            buy: true,
        };
        assert_eq!(
            price(t, &c, &pil, &later, 0.4, &tr, false)
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        let e = bootstrap(d("2026-11-09"), &c, &pil, 0.4, &[((5, 'Y'), 0.01)]).unwrap_err();
        assert_eq!(e.code, "E_INPUT");
    }
}
