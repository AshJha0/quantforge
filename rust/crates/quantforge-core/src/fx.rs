//! FX spot, forwards and swaps (`fx.md`).
use crate::calendar::{Bdc, Calendar};
use crate::conventions::FxPair;
use crate::curve::Curve;
use crate::dates::Date;

use crate::error::{Result, fail};
use crate::ois::Valuation;

fn calendars(p: &FxPair) -> [Calendar; 2] {
    p.calendars
        .map(|c| Calendar::parse(c).expect("registry calendars exist"))
}

fn joint(c: &[Calendar; 2], d: Date) -> Result<bool> {
    Ok(c[0].is_business_day(d)? && c[1].is_business_day(d)?)
}

pub fn spot_date(p: &FxPair, trade_date: Date) -> Result<Date> {
    crate::error::finite("p", &p)?;
    let c = calendars(p);
    let (mut d, mut left) = (trade_date, p.spot_lag);
    while left > 0 {
        d = d.add_days(1);
        if joint(&c, d)? {
            left -= 1;
        }
    }
    Ok(d)
}

/// Market data for one pair.
#[derive(Debug, Clone)]
pub struct FxMarket {
    pub pair: FxPair,
    pub spot: f64,
    pub as_of: Date,
    pub base: Curve,
    pub quote: Curve,
    pub data_version: Option<String>,
}

/// Instrument: one forward leg.
#[derive(Debug, Clone, Copy)]
pub struct FxLeg {
    pub notional_base: f64,
    pub strike: f64,
    pub value_date: Date,
    pub buy: bool,
}

impl FxMarket {
    fn spot_settlement(&self) -> Result<Date> {
        if self.spot <= 0.0 {
            return fail("E_DOMAIN", "spot must be positive");
        }
        spot_date(&self.pair, self.as_of)
    }

    fn growth(curve: &Curve, sp: Date, t: Date) -> Result<f64> {
        Ok(curve.discount(t)? / curve.discount(sp)?)
    }

    fn forward(&self, t: Date) -> Result<f64> {
        let sp = self.spot_settlement()?;
        let (a, b) = (
            Self::growth(&self.base, sp, t)?,
            Self::growth(&self.quote, sp, t)?,
        );
        Ok(self.spot * a / b)
    }

    /// Returns `(forward, points)`.
    pub fn outright(&self, value_date: Date) -> Result<(f64, f64)> {
        crate::error::finite("self", self)?;
        if value_date < self.spot_settlement()? {
            return fail("E_DATE_ORDER", "value_date is before spot");
        }
        let f = self.forward(value_date)?;
        Ok((f, (f - self.spot) / self.pair.pip))
    }

    /// Returns `(pv, fx_delta)` for one leg.
    pub fn leg(&self, l: &FxLeg) -> Result<(f64, f64)> {
        crate::error::finite("self", self)?;
        crate::error::finite("l", &l)?;
        if l.value_date < self.spot_settlement()? {
            return fail("E_DATE_ORDER", "value_date is before spot");
        }
        let f = self.forward(l.value_date)?;
        let d = self.quote.discount(l.value_date)?;
        let sign = if l.buy { 1.0 } else { -1.0 };
        Ok((
            sign * l.notional_base * (f - l.strike) * d,
            sign * l.notional_base * (f / self.spot) * d,
        ))
    }

    /// Unchecked kernel (E1): inputs are not validated, and NaN or infinity in gives NaN out.
    pub fn valuation(&self, pv: f64, model: &'static str) -> Valuation {
        Valuation {
            pv,
            currency: self.pair.quote.to_string(),
            model,
            data_version: self.data_version.clone(),
            conventions: self.pair.id.to_string(),
            as_of: self.as_of,
        }
    }

    /// Returns `(value_date, implied_ratio, basis_bp)` for each `(tenor, points)`.
    pub fn implied(&self, points: &[((i64, char), f64)]) -> Result<Vec<(Date, f64, f64)>> {
        crate::error::finite("self", self)?;
        let sp = self.spot_settlement()?;
        let c = calendars(&self.pair);
        let mut out: Vec<(Date, f64, f64)> = Vec::new();
        for ((n, unit), p) in points {
            let mut t = c[0].add_tenor(sp, *n, *unit, Bdc::ModifiedFollowing, false)?;
            while !joint(&c, t)? {
                t = t.add_days(1);
            }
            if out.last().is_some_and(|l| l.0 >= t) {
                return fail("E_INPUT", "points are not in tenor order");
            }
            let f = self.spot + p * self.pair.pip;
            let ratio = f / self.spot * Self::growth(&self.quote, sp, t)?;
            let a = Self::growth(&self.base, sp, t)?;
            let tau = (t.serial() - sp.serial()) as f64 / 365.0;
            out.push((t, ratio, 10000.0 * (-ratio.ln() / tau + a.ln() / tau)));
        }
        Ok(out)
    }
}

/// Use case 1. Returns `(pv, fx_delta, hedge_spot_base, residual_delta, hedge_cost)`.
pub fn hedge_book(m: &FxMarket, book: &[FxLeg], half_spread: f64) -> Result<[f64; 5]> {
    crate::error::finite("m", &m)?;
    crate::error::finite("book", &book)?;
    crate::error::finite("half_spread", &half_spread)?;
    if half_spread < 0.0 {
        return fail("E_DOMAIN", "half_spread is negative");
    }
    let (mut pv, mut delta) = (0.0, 0.0);
    for l in book {
        let (p, d) = m.leg(l)?;
        pv += p;
        delta += d;
    }
    let hedge = -delta;
    Ok([pv, delta, hedge, 0.0, hedge.abs() * half_spread])
}

impl crate::error::Finite for FxLeg {
    fn is_all_finite(&self) -> bool {
        self.notional_base.is_all_finite() && self.strike.is_all_finite()
    }
}

impl crate::error::Finite for FxMarket {
    fn is_all_finite(&self) -> bool {
        self.pair.is_all_finite() && self.spot.is_all_finite()
    }
}
