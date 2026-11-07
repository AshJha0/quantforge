//! Equity forward from spot, carry and cash dividends (`equity-forward.md`).
use crate::curve::{Curve, CurveInput};
use crate::dates::Date;
use crate::error::{Result, fail};

#[derive(Debug, Clone, PartialEq)]
pub struct Outright {
    pub forward: f64,
    pub discount_factor: f64,
    pub carry_factor: f64,
    pub pv_dividends: f64,
}

/// `F = S/C(T) - sum A_i C(t_i)/C(T)`, with `C = D/B`. Dividends ride on `C`, never on `D`.
pub fn outright(
    spot: f64,
    as_of: Date,
    expiry: Date,
    funding: &CurveInput,
    borrow: Option<&CurveInput>,
    dividends: &[(Date, f64)],
) -> Result<Outright> {
    if spot <= 0.0 {
        return fail("E_DOMAIN", "spot must be above 0");
    }
    let d = Curve::new(funding)?;
    let b = borrow.map(Curve::new).transpose()?;
    if funding.as_of != as_of || borrow.is_some_and(|c| c.as_of != as_of) {
        return fail("E_INPUT", "a curve as_of differs");
    }
    if expiry < as_of {
        return fail("E_DATE_ORDER", "expiry is before as_of");
    }
    if dividends.iter().any(|v| v.1 < 0.0) {
        return fail("E_DOMAIN", "a dividend is negative");
    }
    if dividends.windows(2).any(|w| w[1].0 <= w[0].0) {
        return fail("E_INPUT", "ex_dates must strictly increase");
    }
    let carry = |t: Date| -> Result<f64> {
        let fee = b.as_ref().map_or(Ok(1.0), |c| c.discount(t))?;
        Ok(d.discount(t)? / fee)
    };
    let c_t = carry(expiry)?;
    let mut pv_dividends = 0.0;
    for &(date, amount) in dividends {
        if date > as_of && date <= expiry {
            pv_dividends += amount * carry(date)?;
        }
    }
    let forward = (spot - pv_dividends) / c_t;
    if forward <= 0.0 {
        return fail("E_DOMAIN", "forward is not positive");
    }
    Ok(Outright {
        forward,
        discount_factor: d.discount(expiry)?,
        carry_factor: c_t,
        pv_dividends,
    })
}

pub fn flat(spot: f64, rate: f64, borrow: f64, t: f64, dividends: &[(f64, f64)]) -> Result<f64> {
    if spot <= 0.0 || t < 0.0 || dividends.iter().any(|v| v.1 < 0.0) {
        return fail(
            "E_DOMAIN",
            "spot, expiry_years or an amount is out of domain",
        );
    }
    if dividends.windows(2).any(|w| w[1].0 <= w[0].0) {
        return fail("E_INPUT", "time_years must strictly increase");
    }
    let g = rate - borrow;
    let mut forward = spot * (g * t).exp();
    for &(ti, a) in dividends {
        if ti > 0.0 && ti <= t {
            forward -= a * (g * (t - ti)).exp();
        }
    }
    if forward <= 0.0 {
        return fail("E_DOMAIN", "forward is not positive");
    }
    Ok(forward)
}

#[derive(Debug, Clone, PartialEq)]
pub struct ParityQuote {
    pub strike: f64,
    pub call_bid: f64,
    pub call_ask: f64,
    pub put_bid: f64,
    pub put_ask: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Parity {
    pub forward: f64,
    pub discount_factor: f64,
    pub max_residual: f64,
    pub outside_spread: Vec<f64>,
}

pub fn parity(q: &[ParityQuote], given: Option<f64>) -> Result<Parity> {
    if q.is_empty() {
        return fail("E_INPUT", "quotes is empty");
    }
    let negative = |x: &ParityQuote| {
        x.call_bid < 0.0 || x.call_ask < 0.0 || x.put_bid < 0.0 || x.put_ask < 0.0
    };
    if q.iter().any(|x| x.strike <= 0.0 || negative(x)) || given.is_some_and(|d| d <= 0.0) {
        return fail(
            "E_DOMAIN",
            "a strike, quote or discount factor is out of domain",
        );
    }
    if q.windows(2).any(|w| w[1].strike <= w[0].strike)
        || q.iter()
            .any(|x| x.call_bid > x.call_ask || x.put_bid > x.put_ask)
    {
        return fail(
            "E_INPUT",
            "strikes must increase and a bid must not pass its ask",
        );
    }
    if given.is_none() && q.len() == 1 {
        return fail("E_INPUT", "one quote cannot fit a discount factor");
    }
    let n = q.len() as f64;
    let y: Vec<f64> = q
        .iter()
        .map(|x| (x.call_bid + x.call_ask) / 2.0 - (x.put_bid + x.put_ask) / 2.0)
        .collect();
    let (d, f) = match given {
        Some(d) => {
            let sum: f64 = q.iter().zip(&y).map(|(x, y)| x.strike + y / d).sum();
            (d, sum / n)
        }
        None => {
            let kbar = q.iter().map(|x| x.strike).sum::<f64>() / n;
            let ybar = y.iter().sum::<f64>() / n;
            let (mut sxy, mut sxx) = (0.0, 0.0);
            for (x, y) in q.iter().zip(&y) {
                sxy += (x.strike - kbar) * (y - ybar);
                sxx += (x.strike - kbar) * (x.strike - kbar);
            }
            let s = sxy / sxx;
            let d = -s;
            (d, (ybar - s * kbar) / d)
        }
    };
    if d <= 0.0 || f <= 0.0 {
        return fail(
            "E_DOMAIN",
            "fitted discount factor or forward is not positive",
        );
    }
    let mut max_residual: f64 = 0.0;
    let mut outside_spread = Vec::new();
    for (x, y) in q.iter().zip(&y) {
        let model = d * (f - x.strike);
        max_residual = max_residual.max((y - model).abs());
        if model < x.call_bid - x.put_ask || model > x.call_ask - x.put_bid {
            outside_spread.push(x.strike);
        }
    }
    Ok(Parity {
        forward: f,
        discount_factor: d,
        max_residual,
        outside_spread,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plan_check_case() {
        let f = flat(100.0, 0.04, 0.05, 1.0, &[(0.5, 2.0)]).unwrap();
        assert!((f - 97.0149584).abs() < 1e-7);
    }

    #[test]
    fn dividend_at_zero_ignored_and_on_expiry_counted() {
        let f = flat(100.0, 0.0, 0.0, 1.0, &[(0.0, 5.0), (1.0, 2.0)]).unwrap();
        assert_eq!(f, 98.0);
    }

    #[test]
    fn parity_recovers_d_and_f() {
        let q: Vec<ParityQuote> = [90.0, 100.0, 110.0]
            .iter()
            .map(|&k: &f64| {
                let y: f64 = 0.9 * (105.0 - k);
                let (c, p) = (y.max(0.0) + 1.0, (-y).max(0.0) + 1.0);
                ParityQuote {
                    strike: k,
                    call_bid: c,
                    call_ask: c,
                    put_bid: p,
                    put_ask: p,
                }
            })
            .collect();
        let r = parity(&q, None).unwrap();
        assert!((r.discount_factor - 0.9).abs() < 1e-12 && (r.forward - 105.0).abs() < 1e-10);
    }
}
