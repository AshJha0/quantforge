//! Equity dividend, borrow and financing curves (`equity-curves.md`), index dividends,
//! rebalancing, corporate actions and TRS (`equity-index.md`).
use crate::curve::{Curve, curve_time};
use crate::dates::Date;
use crate::error::{Result, fail};
use std::collections::{BTreeMap, HashSet};

/// The carry curve `C = D / B * exp(-s t)` with flat borrow `b` and spread `s`.
pub struct Carry<'a> {
    pub funding: &'a Curve,
    pub borrow: f64,
    pub spread: f64,
}

impl Carry<'_> {
    pub fn c(&self, d: Date) -> Result<f64> {
        let t = curve_time(self.funding.as_of, d);
        Ok(self.funding.discount(d)? * ((self.borrow - self.spread) * t).exp())
    }

    /// `F(T) = [S - sum div C(t_i)] / C(T)` over ex-dates in `(as_of, T]`.
    pub fn forward(&self, spot: f64, dividends: &[(Date, f64)], t: Date) -> Result<f64> {
        let mut pv = 0.0;
        for (d, a) in dividends {
            if *d > self.funding.as_of && *d <= t {
                pv += a * self.c(*d)?;
            }
        }
        Ok((spot - pv) / self.c(t)?)
    }
}

/// Root of a decreasing or increasing function on `[lo, hi]` by bisection to adjacent floats.
fn bisect(f: &dyn Fn(f64) -> Result<f64>, lo: f64, hi: f64) -> Result<Option<f64>> {
    let (mut a, mut b) = (lo, hi);
    let (fa, fb) = (f(a)?, f(b)?);
    if fa == 0.0 {
        return Ok(Some(a));
    }
    if fb == 0.0 {
        return Ok(Some(b));
    }
    if fa.signum() == fb.signum() || !fa.is_finite() || !fb.is_finite() {
        return Ok(None);
    }
    for _ in 0..400 {
        let m = 0.5 * (a + b);
        if m <= a.min(b) || m >= a.max(b) {
            break;
        }
        let fm = f(m)?;
        if fm == 0.0 {
            return Ok(Some(m));
        }
        if fm.signum() == fa.signum() {
            a = m;
        } else {
            b = m;
        }
    }
    let (ea, eb) = (f(a)?.abs(), f(b)?.abs());
    Ok(Some(if ea <= eb { a } else { b }))
}

#[derive(Debug, Clone, PartialEq)]
pub struct ImpliedDividends {
    pub pv_dividends: Vec<f64>,
    pub period_pv_dividends: Vec<f64>,
    pub dividend_yields: Vec<f64>,
}

pub fn dividend_implied(
    spot: f64,
    funding: &Curve,
    borrow: f64,
    futures: &[(Date, f64)],
) -> Result<ImpliedDividends> {
    if futures.is_empty() {
        return fail("E_INPUT", "no futures");
    }
    if futures[0].0 <= funding.as_of || futures.windows(2).any(|w| w[1].0 <= w[0].0) {
        return fail("E_INPUT", "expiries must increase and follow as_of");
    }
    if spot <= 0.0 || futures.iter().any(|f| f.1 <= 0.0) {
        return fail("E_DOMAIN", "spot and prices must be positive");
    }
    let carry = Carry {
        funding,
        borrow,
        spread: 0.0,
    };
    let mut out = ImpliedDividends {
        pv_dividends: Vec::new(),
        period_pv_dividends: Vec::new(),
        dividend_yields: Vec::new(),
    };
    let mut prev = 0.0;
    for (t, f) in futures {
        let fc = f * carry.c(*t)?;
        let x = spot - fc;
        out.pv_dividends.push(x);
        out.period_pv_dividends.push(x - prev);
        prev = x;
        out.dividend_yields
            .push(-(fc / spot).ln() / curve_time(funding.as_of, *t));
    }
    Ok(out)
}

pub fn borrow_implied(
    spot: f64,
    funding: &Curve,
    dividends: &[(Date, f64)],
    expiry: Date,
    forward: f64,
) -> Result<f64> {
    if expiry <= funding.as_of {
        return fail("E_DATE_ORDER", "expiry is not after as_of");
    }
    let f = |b: f64| -> Result<f64> {
        let c = Carry {
            funding,
            borrow: b,
            spread: 0.0,
        };
        Ok(c.forward(spot, dividends, expiry)? - forward)
    };
    match bisect(&f, -0.5, 0.5)? {
        Some(b) => Ok(b),
        None => fail("E_NOT_BRACKETED", "no borrow rate in [-0.5, 0.5]"),
    }
}

/// `(fair_price, basis, implied_financing_spread)`.
#[allow(clippy::too_many_arguments)]
pub fn futures_basis(
    spot: f64,
    funding: &Curve,
    borrow: f64,
    spread: f64,
    dividends: &[(Date, f64)],
    expiry: Date,
    price: f64,
) -> Result<(f64, f64, f64)> {
    if expiry <= funding.as_of {
        return fail("E_DATE_ORDER", "expiry is not after as_of");
    }
    let fwd = |s: f64| -> Result<f64> {
        Carry {
            funding,
            borrow,
            spread: s,
        }
        .forward(spot, dividends, expiry)
    };
    let fair = fwd(spread)?;
    let g = |s: f64| -> Result<f64> { Ok(fwd(s)? - price) };
    match bisect(&g, -1.0, 1.0)? {
        Some(s) => Ok((fair, price - fair, s)),
        None => fail("E_NOT_BRACKETED", "no financing spread in [-1, 1]"),
    }
}

#[derive(Debug, Clone)]
pub struct Constituent {
    pub id: String,
    pub shares: f64,
    pub price: f64,
    pub dividends: Vec<(Date, f64)>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct IndexDividends {
    pub level: f64,
    pub ex_dates: Vec<Date>,
    pub points: Vec<f64>,
    pub period_points: Vec<f64>,
    pub basis: Vec<f64>,
}

fn level(divisor: f64, cs: &[Constituent]) -> f64 {
    cs.iter().map(|c| c.shares * c.price).sum::<f64>() / divisor
}

pub fn index_dividends(
    divisor: f64,
    cs: &[Constituent],
    periods: &[(Date, Date)],
    implied: &[f64],
) -> Result<IndexDividends> {
    if divisor <= 0.0 {
        return fail("E_DOMAIN", "divisor must be positive");
    }
    if periods.iter().any(|p| p.1 < p.0) {
        return fail("E_DATE_ORDER", "a period ends before it starts");
    }
    if periods.len() != implied.len() {
        return fail("E_INPUT", "periods and implied points differ in length");
    }
    let mut by_date: BTreeMap<Date, f64> = BTreeMap::new();
    for c in cs {
        for (d, a) in &c.dividends {
            *by_date.entry(*d).or_insert(0.0) += c.shares * a;
        }
    }
    let ex_dates: Vec<Date> = by_date.keys().copied().collect();
    let points: Vec<f64> = by_date.values().map(|v| v / divisor).collect();
    let period_points: Vec<f64> = periods
        .iter()
        .map(|(s, e)| {
            let sum: f64 = by_date.range(*s..=*e).map(|(_, v)| *v).sum();
            sum / divisor
        })
        .collect();
    let basis = implied
        .iter()
        .zip(&period_points)
        .map(|(a, b)| a - b)
        .collect();
    Ok(IndexDividends {
        level: level(divisor, cs),
        ex_dates,
        points,
        period_points,
        basis,
    })
}

/// `(level, new_divisor, weights)`.
pub fn rebalance(
    divisor: f64,
    old: &[Constituent],
    new: &[Constituent],
) -> Result<(f64, f64, Vec<f64>)> {
    for list in [old, new] {
        let mut seen = HashSet::new();
        if list.iter().any(|c| !seen.insert(c.id.as_str())) {
            return fail("E_INPUT", "duplicate id");
        }
    }
    if divisor <= 0.0 {
        return fail("E_DOMAIN", "divisor must be positive");
    }
    let lvl = level(divisor, old);
    let cap: f64 = new.iter().map(|c| c.shares * c.price).sum();
    let weights = new.iter().map(|c| c.shares * c.price / cap).collect();
    Ok((lvl, cap / lvl, weights))
}

#[derive(Debug, Clone, Copy)]
pub enum Action {
    Split(f64),
    Rights { m: f64, k: f64 },
    SpecialDividend(f64),
}

/// `(factor, ex_price, adjusted_shares, adjusted_strike)`.
pub fn corporate_action(
    a: Action,
    p: f64,
    shares: f64,
    strike: f64,
) -> Result<(f64, f64, f64, f64)> {
    let f = match a {
        Action::Split(r) => {
            if r <= 0.0 {
                return fail("E_DOMAIN", "ratio must be positive");
            }
            1.0 / r
        }
        Action::Rights { m, k } => {
            if m <= 0.0 || k <= 0.0 {
                return fail("E_DOMAIN", "rights terms must be positive");
            }
            (p + m * k) / (1.0 + m) / p
        }
        Action::SpecialDividend(x) => {
            if x <= 0.0 || x >= p {
                return fail("E_DOMAIN", "amount must be in (0, cum_price)");
            }
            (p - x) / p
        }
    };
    Ok((f, f * p, shares / f, f * strike))
}

#[derive(Debug, Clone, Copy)]
pub struct Trs {
    pub start: Date,
    pub end: Date,
    pub initial_price: f64,
    pub shares: f64,
    pub spread: f64,
    pub receive_equity: bool,
}

/// `(equity_leg, funding_leg, pv)`.
pub fn trs_pv(
    spot: f64,
    funding: &Curve,
    borrow: f64,
    dividends: &[(Date, f64)],
    t: &Trs,
    current_rate: Option<f64>,
) -> Result<(f64, f64, f64)> {
    if t.end <= t.start {
        return fail("E_DATE_ORDER", "end is not after start");
    }
    if t.start < funding.as_of && current_rate.is_none() {
        return fail("E_INPUT", "a started TRS needs current_rate");
    }
    let carry = Carry {
        funding,
        borrow,
        spread: 0.0,
    };
    let de = funding.discount(t.end)?;
    let divs: f64 = dividends
        .iter()
        .filter(|(d, _)| *d > funding.as_of && *d <= t.end)
        .map(|(_, a)| a)
        .sum();
    let equity = t.shares * de * (carry.forward(spot, dividends, t.end)? + divs - t.initial_price);
    let alpha = (t.end.serial() - t.start.serial()) as f64 / 360.0;
    let r = match current_rate {
        Some(r) => r,
        None => (funding.discount(t.start)? / de - 1.0) / alpha,
    };
    let fund = t.shares * t.initial_price * (r + t.spread) * alpha * de;
    let sign = if t.receive_equity { 1.0 } else { -1.0 };
    Ok((equity, fund, sign * (equity - fund)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::curve::Interpolation;

    fn d(s: &str) -> Date {
        Date::parse(s).unwrap()
    }

    fn flat() -> Curve {
        let as_of = d("2026-11-06");
        let p = d("2036-11-06");
        Curve::from_logs(
            as_of,
            Interpolation::LogLinearDf,
            &[p],
            &[-0.04 * curve_time(as_of, p)],
        )
    }

    fn divs() -> Vec<(Date, f64)> {
        vec![
            (d("2026-12-18"), 18.0),
            (d("2027-03-19"), 16.5),
            (d("2027-06-18"), 21.0),
        ]
    }

    #[test]
    fn implied_dividends_and_borrow_round_trip() {
        let c = flat();
        let carry = Carry {
            funding: &c,
            borrow: 0.003,
            spread: 0.0,
        };
        let t = [d("2026-12-18"), d("2027-06-18")];
        let fut: Vec<(Date, f64)> = t
            .iter()
            .map(|x| (*x, carry.forward(5000.0, &divs(), *x).unwrap()))
            .collect();
        let r = dividend_implied(5000.0, &c, 0.003, &fut).unwrap();
        assert!((r.pv_dividends[0] - 18.0 * carry.c(t[0]).unwrap()).abs() < 1e-9);
        assert!((r.period_pv_dividends[1] - (r.pv_dividends[1] - r.pv_dividends[0])).abs() < 1e-12);
        let b = borrow_implied(5000.0, &c, &divs(), t[1], fut[1].1).unwrap();
        assert!((b - 0.003).abs() < 1e-14);
        let rev = [fut[1], fut[0]];
        assert_eq!(
            dividend_implied(5000.0, &c, 0.003, &rev).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(
            dividend_implied(-1.0, &c, 0.003, &fut).unwrap_err().code,
            "E_DOMAIN"
        );
        let e = borrow_implied(5000.0, &c, &divs(), t[1], 1.0).unwrap_err();
        assert_eq!(e.code, "E_NOT_BRACKETED");
    }

    #[test]
    fn futures_basis_spread_reprices() {
        let c = flat();
        let x = d("2027-06-18");
        let (fair, basis, s) = futures_basis(5000.0, &c, 0.003, 0.001, &divs(), x, 5010.0).unwrap();
        assert!((basis - (5010.0 - fair)).abs() < 1e-12);
        let (again, _, _) = futures_basis(5000.0, &c, 0.003, s, &divs(), x, 5010.0).unwrap();
        assert!((again - 5010.0).abs() < 1e-9);
        let e = futures_basis(5000.0, &c, 0.003, 0.0, &[], d("2026-11-05"), 5000.0).unwrap_err();
        assert_eq!(e.code, "E_DATE_ORDER");
    }

    fn cons(id: &str, n: f64, p: f64, dv: Vec<(Date, f64)>) -> Constituent {
        Constituent {
            id: id.into(),
            shares: n,
            price: p,
            dividends: dv,
        }
    }

    #[test]
    fn index_dividends_and_rebalance() {
        let cs = vec![
            cons("A", 100.0, 10.0, vec![(d("2027-01-01"), 1.0)]),
            cons(
                "B",
                50.0,
                20.0,
                vec![(d("2027-01-01"), 2.0), (d("2027-02-01"), 1.0)],
            ),
        ];
        let p = [
            (d("2027-01-01"), d("2027-01-31")),
            (d("2027-01-02"), d("2027-02-01")),
        ];
        let r = index_dividends(10.0, &cs, &p, &[25.0, 5.0]).unwrap();
        assert_eq!(r.level, 200.0);
        assert_eq!(r.points, vec![20.0, 5.0]);
        assert_eq!(r.period_points, vec![20.0, 5.0]);
        assert_eq!(r.basis, vec![5.0, 0.0]);
        assert_eq!(
            index_dividends(0.0, &cs, &p, &[1.0, 1.0]).unwrap_err().code,
            "E_DOMAIN"
        );
        let bad = [(d("2027-02-01"), d("2027-01-01"))];
        assert_eq!(
            index_dividends(1.0, &cs, &bad, &[1.0]).unwrap_err().code,
            "E_DATE_ORDER"
        );
        assert_eq!(
            index_dividends(1.0, &cs, &p, &[1.0]).unwrap_err().code,
            "E_INPUT"
        );
        let (l, nd, w) = rebalance(10.0, &cs, &cs[..1]).unwrap();
        assert_eq!((l, nd, w), (200.0, 5.0, vec![1.0]));
        let dup = vec![cs[0].clone(), cs[0].clone()];
        assert_eq!(rebalance(10.0, &cs, &dup).unwrap_err().code, "E_INPUT");
    }

    #[test]
    fn corporate_actions() {
        assert_eq!(
            corporate_action(Action::Split(2.0), 100.0, 10.0, 90.0).unwrap(),
            (0.5, 50.0, 20.0, 45.0)
        );
        let (f, ..) =
            corporate_action(Action::Rights { m: 1.0, k: 50.0 }, 100.0, 1.0, 1.0).unwrap();
        assert_eq!(f, 0.75);
        let (f, ..) = corporate_action(Action::SpecialDividend(10.0), 100.0, 1.0, 1.0).unwrap();
        assert_eq!(f, 0.9);
        assert!(corporate_action(Action::Split(0.0), 100.0, 1.0, 1.0).is_err());
        assert!(corporate_action(Action::Rights { m: 1.0, k: 0.0 }, 100.0, 1.0, 1.0).is_err());
        assert!(corporate_action(Action::SpecialDividend(100.0), 100.0, 1.0, 1.0).is_err());
    }

    #[test]
    fn trs_cases() {
        let c = flat();
        let t = Trs {
            start: d("2026-11-06"),
            end: d("2027-11-06"),
            initial_price: 5000.0,
            shares: 1.0,
            spread: 0.0,
            receive_equity: true,
        };
        let (eq, fund, pv) = trs_pv(5000.0, &c, 0.0, &[], &t, None).unwrap();
        assert!((eq - fund).abs() < 1e-9 && pv.abs() < 1e-9);
        let started = Trs {
            start: d("2026-09-18"),
            ..t
        };
        assert_eq!(
            trs_pv(5000.0, &c, 0.0, &[], &started, None)
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        assert!(trs_pv(5000.0, &c, 0.0, &[], &started, Some(0.04)).is_ok());
    }
}
