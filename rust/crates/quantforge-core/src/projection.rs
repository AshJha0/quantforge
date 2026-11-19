//! Projection curves, FRAs, swaps and basis (`projection-and-fra.md`).
use crate::calendar::{Bdc, Calendar};
use crate::conventions::{
    TERM_CALENDAR, TERM_CURRENCY, TERM_DAY_COUNT, TERM_FIXED_DAY_COUNT, TERM_FIXED_MONTHS,
    TERM_INDEX, TERM_MONTHS, TERM_SPOT_LAG,
};
use crate::curve::{
    Curve, Discount, Incremental, Interpolation, SequentialProblem, SolveMethod, Solved,
    solve_curve, solve_incremental,
};
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
    pub fn legs<D: Discount + ?Sized, P: Discount + ?Sized>(
        &self,
        discount: &D,
        projection: &P,
    ) -> Result<(f64, f64)> {
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

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ProjectionQuote {
    Deposit { months: i64, rate: f64 },
    Fra { start_months: i64, rate: f64 },
    Swap { months: i64, rate: f64 },
}

/// A projection instrument with its dates fixed.
#[derive(Debug, Clone)]
pub enum Instrument {
    Simple(Date, Date),
    Swap(SwapLegs),
}

fn simple_rate<P: Discount + ?Sized>(p: &P, s: Date, e: Date) -> Result<f64> {
    Ok((p.discount(s)? / p.discount(e)? - 1.0) / alpha(TERM_DAY_COUNT, s, e)?)
}

impl Instrument {
    /// `(instrument, quoted rate, pillar date)`, with the quote's own checks.
    pub fn new(as_of: Date, q: &ProjectionQuote) -> Result<(Instrument, f64, Date)> {
        let s = spot(as_of)?;
        Ok(match *q {
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
        })
    }

    /// The model rate, projecting on `projection` and discounting swaps on `discount`.
    pub fn model<D: Discount + ?Sized, P: Discount + ?Sized>(
        &self,
        discount: &D,
        projection: &P,
    ) -> Result<f64> {
        match self {
            Instrument::Simple(s, e) => simple_rate(projection, *s, *e),
            Instrument::Swap(legs) => {
                let (f, a) = legs.legs(discount, projection)?;
                Ok(f / a)
            }
        }
    }
}

type Instruments = (Vec<Instrument>, Vec<f64>, Vec<Date>);

fn instruments(as_of: Date, quotes: &[ProjectionQuote]) -> Result<Instruments> {
    crate::error::finite("quotes", &quotes)?;
    if quotes.is_empty() {
        return fail("E_INPUT", "no quotes");
    }
    let mut items = Vec::new();
    let mut rates = Vec::new();
    let mut dates = Vec::new();
    for q in quotes {
        let (item, rate, date) = Instrument::new(as_of, q)?;
        items.push(item);
        rates.push(rate);
        dates.push(date);
    }
    if dates[0] <= as_of || dates.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "quotes are not in pillar order");
    }
    Ok((items, rates, dates))
}

/// K-4b on the stage B projection bootstrap (deposits, FRAs, swaps; the discount curve held
/// fixed): the bootstrap of `next`, solving only the pillars at and after the first quote that
/// differs from `previous` (type, months or rate); see `curve::solve_incremental`.
pub fn bootstrap_incremental(
    discount: &Curve,
    as_of: Date,
    previous: &[ProjectionQuote],
    previous_factors: &[f64],
    next: &[ProjectionQuote],
    interpolation: Interpolation,
) -> Result<Incremental> {
    let (old_items, old_rates, old_dates) = instruments(as_of, previous)?;
    let (new_items, new_rates, new_dates) = instruments(as_of, next)?;
    let key = |q: &ProjectionQuote| match *q {
        ProjectionQuote::Deposit { months, rate } => (0, months, rate.to_bits()),
        ProjectionQuote::Fra { start_months, rate } => (1, start_months, rate.to_bits()),
        ProjectionQuote::Swap { months, rate } => (2, months, rate.to_bits()),
    };
    let (old_keys, new_keys): (Vec<_>, Vec<_>) = (
        previous.iter().map(key).collect(),
        next.iter().map(key).collect(),
    );
    let old_model = |c: &Curve, j: usize| old_items[j].model(discount, c);
    let new_model = |c: &Curve, j: usize| new_items[j].model(discount, c);
    solve_incremental(
        as_of,
        interpolation,
        &[],
        &SequentialProblem {
            dates: &old_dates,
            quotes: &old_rates,
            model: &old_model,
            keys: &old_keys,
        },
        previous_factors,
        &SequentialProblem {
            dates: &new_dates,
            quotes: &new_rates,
            model: &new_model,
            keys: &new_keys,
        },
    )
}

pub fn bootstrap(
    discount: &Curve,
    as_of: Date,
    quotes: &[ProjectionQuote],
    interpolation: Interpolation,
) -> Result<Solved> {
    let (items, rates, dates) = instruments(as_of, quotes)?;
    let model = |c: &Curve, j: usize| items[j].model(discount, c);
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
    crate::error::finite("fixed_rate", &fixed_rate)?;
    crate::error::finite("notional", &notional)?;
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
    crate::error::finite("fixed_rate", &fixed_rate)?;
    crate::error::finite("notional", &notional)?;
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

impl crate::error::Finite for ProjectionQuote {
    #[allow(clippy::match_same_arms)]
    fn is_all_finite(&self) -> bool {
        match self {
            Self::Deposit { rate, .. } => rate.is_all_finite(),
            Self::Fra { rate, .. } => rate.is_all_finite(),
            Self::Swap { rate, .. } => rate.is_all_finite(),
        }
    }
}
