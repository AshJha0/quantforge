//! Unsecured funding curve over OIS (`02-curves/joint-solve-and-funding.md`,
//! `rates.funding.curve`): `D_f(t) = D_ois(t) exp(-integral of s)`, `s` flat between quotes.
use crate::curve::{Curve, curve_time};
use crate::dates::Date;
use crate::error::{Result, fail};

#[derive(Debug, Clone, PartialEq)]
pub struct Funding {
    /// Continuous spreads `s_i` on `(t_{i-1}, t_i]`.
    pub spreads: Vec<f64>,
    /// `(end_i, D_f(end_i))`.
    pub pillars: Vec<(Date, f64)>,
    pub discount_factors: Vec<f64>,
}

/// `quotes`: `(end, simple ACT/360 rate from as_of)`.
pub fn funding_curve(ois: &Curve, quotes: &[(Date, f64)], dates: &[Date]) -> Result<Funding> {
    crate::error::finite("quotes", &quotes)?;
    let as_of = ois.as_of;
    if quotes.is_empty() || quotes[0].0 <= as_of || quotes.windows(2).any(|w| w[1].0 <= w[0].0) {
        return fail("E_INPUT", "quote ends must increase and follow as_of");
    }
    let mut times = vec![0.0];
    let mut logs = vec![0.0]; // ln(D_ois / P_f) at the quote ends
    for &(end, rate) in quotes {
        let g = 1.0 + rate * (end.serial() - as_of.serial()) as f64 / 360.0;
        if g.is_nan() || g <= 0.0 {
            return fail("E_DOMAIN", "1 + rate * accrual must be positive");
        }
        times.push(curve_time(as_of, end));
        logs.push(ois.discount(end)?.ln() + g.ln());
    }
    let spreads: Vec<f64> = (1..times.len())
        .map(|i| (logs[i] - logs[i - 1]) / (times[i] - times[i - 1]))
        .collect();
    let integral = |t: f64| {
        let mut sum = 0.0;
        for (i, s) in spreads.iter().enumerate() {
            let (a, b) = (times[i], times[i + 1]);
            let last = i + 1 == spreads.len();
            let hi = if last { t } else { t.min(b) };
            if hi > a {
                sum += s * (hi - a);
            }
        }
        sum
    };
    let df =
        |d: Date| -> Result<f64> { Ok(ois.discount(d)? * (-integral(curve_time(as_of, d))).exp()) };
    let pillars = quotes
        .iter()
        .map(|q| Ok((q.0, df(q.0)?)))
        .collect::<Result<Vec<_>>>()?;
    let discount_factors = dates.iter().map(|d| df(*d)).collect::<Result<Vec<_>>>()?;
    Ok(Funding {
        spreads,
        pillars,
        discount_factors,
    })
}
