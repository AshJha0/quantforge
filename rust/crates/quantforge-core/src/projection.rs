//! Projection curves, FRAs, swaps and basis (`projection-and-fra.md`).
use crate::calendar::{Bdc, Calendar};
use crate::conventions::{
    TERM_CALENDAR, TERM_CURRENCY, TERM_DAY_COUNT, TERM_FIXED_DAY_COUNT, TERM_FIXED_MONTHS,
    TERM_INDEX, TERM_MONTHS, TERM_SPOT_LAG,
};
use crate::curve::{Curve, Interpolation, SolveMethod, Solved, solve_curve};
use crate::dates::Date;
use crate::daycount::{DayCountInputs, year_fraction};
use crate::error::{Result, fail};
use crate::ois::Valuation;
use crate::schedule::{Period, add_months, generate};

fn calendar() -> Calendar {
    Calendar::parse(TERM_CALENDAR).expect("registry calendars exist")
}

fn alpha(day_count: &str, s: Date, e: Date) -> Result<f64> {
    year_fraction(day_count, s, e, &DayCountInputs::default())
}

fn check_months(months: i64) -> Result<()> {
    if !(1..=1200).contains(&months) {
        return fail("E_INPUT", "months must be 1 to 1200");
    }
    Ok(())
}

fn spot(as_of: Date) -> Result<Date> {
    calendar().add_business_days(as_of, TERM_SPOT_LAG)
}

fn plus_months(d: Date, months: i64) -> Result<Date> {
    calendar().adjust(add_months(d, months), Bdc::ModifiedFollowing)
}

/// Fixed and floating schedules of a swap.
#[derive(Debug, Clone)]
pub struct SwapLegs {
    fixed: Vec<Period>,
    floating: Vec<Period>,
}

impl SwapLegs {
    pub fn new(as_of: Date, months: i64) -> Result<SwapLegs> {
        check_months(months)?;
        let (cal, s) = (calendar(), spot(as_of)?);
        let end = add_months(s, months);
        Ok(SwapLegs {
            fixed: generate(s, end, TERM_FIXED_MONTHS, &cal, false, 0)?,
            floating: generate(s, end, TERM_MONTHS, &cal, false, 0)?,
        })
    }

    fn last_end(&self) -> Date {
        self.fixed.last().expect("at least one period").end
    }

    /// `(F, A)`.
    pub fn legs(&self, discount: &Curve, projection: &Curve) -> Result<(f64, f64)> {
        let mut a = 0.0;
        for p in &self.fixed {
            a += alpha(TERM_FIXED_DAY_COUNT, p.start, p.end)? * discount.discount(p.end)?;
        }
        let mut f = 0.0;
        for p in &self.floating {
            let growth = projection.discount(p.start)? / projection.discount(p.end)?;
            f += (growth - 1.0) * discount.discount(p.end)?;
        }
        Ok((f, a))
    }
}

#[derive(Debug, Clone, Copy)]
pub enum ProjectionQuote {
    Deposit { months: i64, rate: f64 },
    Fra { start_months: i64, rate: f64 },
    Swap { months: i64, rate: f64 },
}

enum Instrument {
    Simple(Date, Date),
    Swap(SwapLegs),
}

fn simple_rate(p: &Curve, s: Date, e: Date) -> Result<f64> {
    Ok((p.discount(s)? / p.discount(e)? - 1.0) / alpha(TERM_DAY_COUNT, s, e)?)
}

pub fn bootstrap(
    discount: &Curve,
    as_of: Date,
    quotes: &[ProjectionQuote],
    interpolation: Interpolation,
) -> Result<Solved> {
    if quotes.is_empty() {
        return fail("E_INPUT", "no quotes");
    }
    let s = spot(as_of)?;
    let mut items = Vec::new();
    let mut rates = Vec::new();
    let mut dates = Vec::new();
    for q in quotes {
        let (item, rate, date) = match *q {
            ProjectionQuote::Deposit { months, rate } => {
                check_months(months)?;
                let e = plus_months(s, months)?;
                (Instrument::Simple(s, e), rate, e)
            }
            ProjectionQuote::Fra { start_months, rate } => {
                if !(0..=1200).contains(&start_months) {
                    return fail("E_INPUT", "start_months must be 0 to 1200");
                }
                let start = plus_months(s, start_months)?;
                let e = plus_months(start, TERM_MONTHS)?;
                (Instrument::Simple(start, e), rate, e)
            }
            ProjectionQuote::Swap { months, rate } => {
                let legs = SwapLegs::new(as_of, months)?;
                let e = legs.last_end();
                (Instrument::Swap(legs), rate, e)
            }
        };
        items.push(item);
        rates.push(rate);
        dates.push(date);
    }
    if dates[0] <= as_of || dates.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "quotes are not in pillar order");
    }
    let model = |c: &Curve, j: usize| match &items[j] {
        Instrument::Simple(s, e) => simple_rate(c, *s, *e),
        Instrument::Swap(legs) => {
            let (f, a) = legs.legs(discount, c)?;
            Ok(f / a)
        }
    };
    solve_curve(
        as_of,
        interpolation,
        &dates,
        &rates,
        &model,
        SolveMethod::Sequential,
    )
}

fn sign(pay: bool) -> f64 {
    if pay { 1.0 } else { -1.0 }
}

fn valuation(pv: f64, model: &'static str, curve: &Curve, id: Option<String>) -> Valuation {
    Valuation {
        pv,
        currency: TERM_CURRENCY.to_string(),
        model,
        data_version: id,
        conventions: TERM_INDEX.to_string(),
        as_of: curve.as_of,
    }
}

/// Returns the valuation and par rate.
pub fn swap_pv(
    discount: &Curve,
    projection: &Curve,
    tenor_months: i64,
    fixed_rate: f64,
    notional: f64,
    pay: bool,
    id: Option<String>,
) -> Result<(Valuation, f64)> {
    let legs = SwapLegs::new(discount.as_of, tenor_months)?;
    let (f, a) = legs.legs(discount, projection)?;
    let pv = sign(pay) * notional * (f - fixed_rate * a);
    Ok((valuation(pv, "SWAP_DISCOUNTING", discount, id), f / a))
}

/// Returns the valuation and forward rate.
pub fn fra_pv(
    discount: &Curve,
    projection: &Curve,
    start: Date,
    fixed_rate: f64,
    notional: f64,
    pay: bool,
    id: Option<String>,
) -> Result<(Valuation, f64)> {
    let e = plus_months(start, TERM_MONTHS)?;
    let a = alpha(TERM_DAY_COUNT, start, e)?;
    let f = simple_rate(projection, start, e)?;
    let pv =
        sign(pay) * notional * a * (f - fixed_rate) / (1.0 + a * f) * discount.discount(start)?;
    Ok((valuation(pv, "FRA_DISCOUNTING", discount, id), f))
}

pub fn basis_spread(discount: &Curve, projection: &Curve, tenor_months: i64) -> Result<f64> {
    let legs = SwapLegs::new(discount.as_of, tenor_months)?;
    let (mut top, mut bottom) = (0.0, 0.0);
    for p in &legs.floating {
        let d = discount.discount(p.end)?;
        let term = projection.discount(p.start)? / projection.discount(p.end)?;
        let overnight = discount.discount(p.start)? / d;
        top += (term - overnight) * d;
        bottom += alpha(TERM_DAY_COUNT, p.start, p.end)? * d;
    }
    Ok(top / bottom)
}
