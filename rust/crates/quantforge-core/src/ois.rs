//! OIS periods, legs, bootstrap and PV (`ois-curves.md`), and the valuation result
//! (`pricing-framework.md`).
use crate::calendar::{Bdc, Calendar};
use crate::conventions::Overnight;
use crate::curve::{
    Curve, Discount, Interpolation, SolveMethod, Solved, check_jumps, solve_curve_with_jumps,
};
use crate::dates::Date;
use crate::daycount::{DayCountInputs, year_fraction};

use crate::error::{Result, fail};
use crate::json::{Json, obj};
use crate::schedule::{Period, add_months, generate};

/// Valuation result. Separate from the instrument and from the market data.
#[derive(Debug, Clone, PartialEq)]
pub struct Valuation {
    pub pv: f64,
    pub currency: String,
    pub model: &'static str,
    pub data_version: Option<String>,
    pub conventions: String,
    pub as_of: Date,
}

impl Valuation {
    pub fn to_json(&self) -> Json {
        obj([
            ("pv", self.pv.into()),
            ("currency", self.currency.as_str().into()),
            ("model", self.model.into()),
            ("data_version", self.data_version.clone().into()),
            ("conventions", self.conventions.as_str().into()),
            ("as_of", self.as_of.to_string().into()),
        ])
    }
}

/// Instrument: contract terms only.
#[derive(Debug, Clone)]
pub struct OisTrade {
    pub convention: Overnight,
    pub tenor: (i64, char),
    pub fixed_rate: f64,
    pub notional: f64,
    pub pay: bool,
}

#[derive(Debug, Clone, Copy)]
pub struct OisQuote {
    pub tenor: (i64, char),
    pub bid: f64,
    pub ask: f64,
}

impl OisQuote {
    pub fn mid(&self) -> f64 {
        (self.bid + self.ask) / 2.0
    }
}

/// Product model: dated periods with their accruals.
#[derive(Debug, Clone)]
pub struct OisLegs {
    periods: Vec<(Period, f64)>,
}

fn calendar(c: &Overnight) -> Calendar {
    Calendar::parse(c.calendar).expect("registry calendars exist")
}

impl OisLegs {
    pub fn new(c: &Overnight, as_of: Date, tenor: (i64, char)) -> Result<OisLegs> {
        let cal = calendar(c);
        let spot = cal.add_business_days(as_of, c.spot_lag)?;
        let (n, unit) = tenor;
        let months = match unit {
            'M' => n,
            'Y' => 12 * n,
            _ => 0,
        };
        let eom = spot >= cal.last_business_day(spot.y, spot.m)?;
        let periods = if months <= c.fixed_months {
            let end = cal.add_tenor(spot, n, unit, Bdc::ModifiedFollowing, eom)?;
            vec![Period {
                start: spot,
                end,
                payment: cal.add_business_days(end, c.payment_lag)?,
            }]
        } else {
            let end = add_months(spot, months);
            generate(spot, end, c.fixed_months, &cal, eom, c.payment_lag)?
        };
        let none = DayCountInputs::default();
        let periods = periods
            .into_iter()
            .map(|p| Ok((p, year_fraction(c.fixed_day_count, p.start, p.end, &none)?)))
            .collect::<Result<Vec<_>>>()?;
        Ok(OisLegs { periods })
    }

    pub fn last_payment(&self) -> Date {
        self.periods.last().expect("at least one period").0.payment
    }

    /// `(F, A)`. The general floating form, never the telescoped one.
    pub fn legs<C: Discount + ?Sized>(&self, curve: &C) -> Result<(f64, f64)> {
        self.legs_on(curve, curve)
    }

    /// `(F, A)` with the floating growth read on `projection` and discounting on `discount`.
    pub fn legs_on<C: Discount + ?Sized, P: Discount + ?Sized>(
        &self,
        discount: &C,
        projection: &P,
    ) -> Result<(f64, f64)> {
        let (mut f, mut a) = (0.0, 0.0);
        for (p, alpha) in &self.periods {
            let d = discount.discount(p.payment)?;
            a += alpha * d;
            f += (projection.discount(p.start)? / projection.discount(p.end)? - 1.0) * d;
        }
        Ok((f, a))
    }

    pub fn par_rate<C: Discount + ?Sized>(&self, curve: &C) -> Result<f64> {
        let (f, a) = self.legs(curve)?;
        Ok(f / a)
    }
}

/// A set of par swaps ready to solve, for any quote levels.
#[derive(Debug, Clone)]
pub struct OisCurveProblem {
    as_of: Date,
    interpolation: Interpolation,
    swaps: Vec<OisLegs>,
    dates: Vec<Date>,
    jumps: Vec<(Date, f64)>,
    pub mids: Vec<f64>,
}

impl OisCurveProblem {
    pub fn new(
        c: &Overnight,
        as_of: Date,
        quotes: &[OisQuote],
        interpolation: Interpolation,
    ) -> Result<OisCurveProblem> {
        crate::error::finite("quotes", &quotes)?;
        OisCurveProblem::with_jumps(c, as_of, quotes, interpolation, &[])
    }

    /// Stage D: the solve is on the curve with these jumps.
    pub fn with_jumps(
        c: &Overnight,
        as_of: Date,
        quotes: &[OisQuote],
        interpolation: Interpolation,
        jumps: &[(Date, f64)],
    ) -> Result<OisCurveProblem> {
        crate::error::finite("quotes", &quotes)?;
        crate::error::finite("jumps", &jumps)?;
        check_jumps(as_of, jumps)?;
        if quotes.is_empty() {
            return fail("E_INPUT", "no quotes");
        }
        let swaps = quotes
            .iter()
            .map(|q| OisLegs::new(c, as_of, q.tenor))
            .collect::<Result<Vec<_>>>()?;
        let dates: Vec<Date> = swaps.iter().map(OisLegs::last_payment).collect();
        if dates[0] <= as_of || dates.windows(2).any(|w| w[1] <= w[0]) {
            return fail("E_INPUT", "pillars are not strictly increasing");
        }
        if quotes.iter().any(|q| q.bid > q.ask) {
            return fail("E_INPUT", "bid is above ask");
        }
        Ok(OisCurveProblem {
            as_of,
            interpolation,
            swaps,
            dates,
            jumps: jumps.to_vec(),
            mids: quotes.iter().map(OisQuote::mid).collect(),
        })
    }

    pub fn solve(&self, quotes: &[f64], method: SolveMethod) -> Result<Solved> {
        crate::error::finite("self", self)?;
        crate::error::finite("quotes", &quotes)?;
        let model = |c: &Curve, j: usize| self.swaps[j].par_rate(c);
        solve_curve_with_jumps(
            self.as_of,
            self.interpolation,
            &self.dates,
            &self.jumps,
            quotes,
            &model,
            method,
        )
    }
}

pub fn compound(rates: &[f64], days: &[i64], denominator: i64) -> Result<f64> {
    crate::error::finite("rates", &rates)?;
    if rates.len() != days.len() || rates.is_empty() || days.iter().any(|d| *d < 1) {
        return fail("E_INPUT", "rates and days do not match");
    }
    let b = denominator as f64;
    let mut product = 1.0;
    for (r, n) in rates.iter().zip(days) {
        product *= 1.0 + r * *n as f64 / b;
    }
    Ok((product - 1.0) * b / days.iter().sum::<i64>() as f64)
}

/// Pricing model. Returns `(valuation, par_rate, annuity)`.
pub fn pv(
    curve: &Curve,
    trade: &OisTrade,
    snapshot_id: Option<String>,
) -> Result<(Valuation, f64, f64)> {
    crate::error::finite("trade", &trade)?;
    let legs = OisLegs::new(&trade.convention, curve.as_of, trade.tenor)?;
    let value = pv_of_legs(&legs, curve, trade)?;
    let (f, a) = legs.legs(curve)?;
    let valuation = Valuation {
        pv: value,
        currency: trade.convention.currency.to_string(),
        model: "OIS_DISCOUNTING",
        data_version: snapshot_id,
        conventions: trade.convention.id.to_string(),
        as_of: curve.as_of,
    };
    Ok((valuation, f / a, a))
}

/// PV with the periods held fixed, as bumped risk needs.
pub fn pv_of_legs<C: Discount + ?Sized>(
    legs: &OisLegs,
    curve: &C,
    trade: &OisTrade,
) -> Result<f64> {
    crate::error::finite("trade", &trade)?;
    let (f, a) = legs.legs(curve)?;
    let sign = if trade.pay { 1.0 } else { -1.0 };
    Ok(sign * trade.notional * (f - trade.fixed_rate * a))
}

/// `rates.basis.ois_spread`: `(F_a - F_b) / A`, both legs discounted on `discount`.
pub fn ois_spread(
    c: &Overnight,
    tenor: (i64, char),
    discount: &Curve,
    a: &Curve,
    b: &Curve,
) -> Result<f64> {
    if a.as_of != discount.as_of || b.as_of != discount.as_of {
        return fail("E_INPUT", "curves have different as_of dates");
    }
    let legs = OisLegs::new(c, discount.as_of, tenor)?;
    let (fa, annuity) = legs.legs_on(discount, a)?;
    let (fb, _) = legs.legs_on(discount, b)?;
    Ok((fa - fb) / annuity)
}

impl crate::error::Finite for OisCurveProblem {
    fn is_all_finite(&self) -> bool {
        self.mids.is_all_finite()
    }
}

impl crate::error::Finite for OisQuote {
    fn is_all_finite(&self) -> bool {
        self.bid.is_all_finite() && self.ask.is_all_finite()
    }
}

impl crate::error::Finite for OisTrade {
    fn is_all_finite(&self) -> bool {
        self.fixed_rate.is_all_finite() && self.notional.is_all_finite()
    }
}

impl crate::error::Finite for Valuation {
    fn is_all_finite(&self) -> bool {
        self.pv.is_all_finite()
    }
}
