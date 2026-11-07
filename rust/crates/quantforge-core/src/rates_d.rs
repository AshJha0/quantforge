//! Stage D rates core: dated overnight compounding and fallbacks (`overnight-compounding.md`),
//! meeting-date step curves (`meeting-steps.md`), futures convexity (`futures-convexity.md`),
//! and CSA discounting and joint calibration (`csa-and-basis.md`).
use crate::calendar::Calendar;
use crate::conventions::Overnight;
use crate::curve::{Curve, Discount, Interpolation, SolveMethod, Solved, check_jumps, curve_time};
use crate::dates::Date;
use crate::error::{Result, err, fail};
use crate::ois::{OisCurveProblem, OisLegs, OisQuote};
use crate::projection::{self, ProjectionQuote};
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Shift {
    None,
    Lookback,
    ObservationShift,
    Lockout,
}

impl Shift {
    pub fn parse(s: &str) -> Option<Shift> {
        match s {
            "NONE" => Some(Shift::None),
            "LOOKBACK" => Some(Shift::Lookback),
            "OBSERVATION_SHIFT" => Some(Shift::ObservationShift),
            "LOCKOUT" => Some(Shift::Lockout),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Compounded {
    pub compounded_rate: f64,
    pub accrual: f64,
    pub interest: f64,
}

fn denominator(c: &Overnight) -> f64 {
    if c.day_count == "ACT_365F" {
        365.0
    } else {
        360.0
    }
}

/// `rates.ois.compound_dated`. The convention kind is checked by the caller.
pub fn compound_dated(
    c: &Overnight,
    start: Date,
    end: Date,
    method: Shift,
    k: i64,
    fixings: &[(Date, f64)],
) -> Result<Compounded> {
    if end <= start {
        return fail("E_DATE_ORDER", "end is not after start");
    }
    let cal = Calendar::parse(c.calendar).expect("registry calendars exist");
    let mut days = Vec::new();
    let mut d = start;
    while d <= end {
        if cal.is_business_day(d)? {
            days.push(d);
        }
        d = d.add_days(1);
    }
    let n = days.len() as i64 - 1;
    let bad_shift = match method {
        Shift::None => k != 0,
        Shift::Lockout => k < 1 || k > n - 1,
        _ => k < 0,
    };
    if bad_shift {
        return fail("E_INPUT", "shift_days is out of range for the method");
    }
    if !cal.is_business_day(start)? || !cal.is_business_day(end)? {
        return fail("E_INPUT", "start and end must be business days");
    }
    let mut table = HashMap::new();
    for (date, rate) in fixings {
        if table.insert(date.serial(), *rate).is_some() {
            return fail("E_INPUT", "two fixings on one date");
        }
    }
    let r = |x: Date| {
        table
            .get(&x.serial())
            .copied()
            .ok_or_else(|| err("E_INPUT", format!("fixing for {x} is missing")))
    };
    let back = |x: Date| cal.add_business_days(x, -k);
    let b = denominator(c);
    let (mut growth, mut total) = (1.0, 0.0);
    let n = n as usize;
    for i in 0..n {
        let (rate, w) = match method {
            Shift::None => (r(days[i])?, days[i + 1].serial() - days[i].serial()),
            Shift::Lookback => (r(back(days[i])?)?, days[i + 1].serial() - days[i].serial()),
            Shift::ObservationShift => {
                let (o, o1) = (back(days[i])?, back(days[i + 1])?);
                (r(o)?, o1.serial() - o.serial())
            }
            Shift::Lockout => {
                let cut = n - k as usize;
                let x = if i < cut { days[i] } else { days[cut] };
                (r(x)?, days[i + 1].serial() - days[i].serial())
            }
        };
        growth *= 1.0 + rate * w as f64 / b;
        total += w as f64;
    }
    let compounded_rate = (growth - 1.0) * b / total;
    let accrual = (end.serial() - start.serial()) as f64 / b;
    Ok(Compounded {
        compounded_rate,
        accrual,
        interest: compounded_rate * accrual,
    })
}

/// ISDA spread adjustments fixed on 2021-03-05 (ruling D8): `(index, spread)`.
pub fn fallback_spread(ibor: &str) -> Option<(&'static str, f64)> {
    Some(match ibor {
        "USD-LIBOR-1M" => ("SOFR", 0.0011448),
        "USD-LIBOR-3M" => ("SOFR", 0.0026161),
        "USD-LIBOR-6M" => ("SOFR", 0.0042826),
        "USD-LIBOR-12M" => ("SOFR", 0.0071513),
        "GBP-LIBOR-1M" => ("SONIA", 0.0003260),
        "GBP-LIBOR-3M" => ("SONIA", 0.0011930),
        "GBP-LIBOR-6M" => ("SONIA", 0.0027660),
        "GBP-LIBOR-12M" => ("SONIA", 0.0046440),
        _ => return None,
    })
}

/// A curve with a flat instantaneous forward between steps, and jumps.
#[derive(Debug, Clone)]
pub struct StepCurve {
    pub as_of: Date,
    pub base_rate: f64,
    pub steps: Vec<(Date, f64)>,
    pub jumps: Vec<(Date, f64)>,
}

impl StepCurve {
    /// Checks in the spec's order: steps, then jumps.
    pub fn new(
        as_of: Date,
        base_rate: f64,
        steps: Vec<(Date, f64)>,
        jumps: Vec<(Date, f64)>,
    ) -> Result<StepCurve> {
        let dates: Vec<Date> = steps.iter().map(|s| s.0).collect();
        if !dates.is_empty() {
            check_step_dates(as_of, &dates)?;
        }
        check_jumps(as_of, &jumps)?;
        Ok(StepCurve {
            as_of,
            base_rate,
            steps,
            jumps,
        })
    }

    /// The forward in force on `d`.
    pub fn forward(&self, d: Date) -> Result<f64> {
        if d < self.as_of {
            return fail("E_OUT_OF_RANGE", "date is before as_of");
        }
        Ok(self
            .steps
            .iter()
            .take_while(|s| s.0 <= d)
            .last()
            .map_or(self.base_rate, |s| s.1))
    }
}

impl Discount for StepCurve {
    fn discount(&self, d: Date) -> Result<f64> {
        if d < self.as_of {
            return fail("E_OUT_OF_RANGE", "date is before as_of");
        }
        let t = curve_time(self.as_of, d);
        let (mut integral, mut from, mut rate) = (0.0, 0.0, self.base_rate);
        for (date, r) in &self.steps {
            let ts = curve_time(self.as_of, *date);
            if ts >= t {
                break;
            }
            integral += rate * (ts - from);
            (from, rate) = (ts, *r);
        }
        integral += rate * (t - from);
        let jump: f64 = self
            .jumps
            .iter()
            .take_while(|j| j.0 < d)
            .map(|j| j.1)
            .product();
        Ok((-integral).exp() * jump)
    }
}

/// Ruling D12 and D6: non-empty, strictly increasing, after `as_of`.
fn check_step_dates(as_of: Date, dates: &[Date]) -> Result<()> {
    if dates.is_empty() || dates[0] <= as_of || dates.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "step dates must increase and follow as_of");
    }
    Ok(())
}

/// The result of `rates.ois.fit_steps`.
#[derive(Debug, Clone)]
pub struct StepFit {
    pub base_rate: f64,
    pub step_rates: Vec<f64>,
    pub max_repricing_error: f64,
}

const FIT_GOAL: f64 = 1e-15;
const REPRICING_LIMIT: f64 = 1e-13;

/// `rates.ois.fit_steps`: a triangular solve, one rate per quote.
pub fn fit_steps(
    c: &Overnight,
    as_of: Date,
    step_dates: &[Date],
    quotes: &[((i64, char), f64)],
    jumps: &[(Date, f64)],
) -> Result<StepFit> {
    let m = step_dates.len();
    if quotes.len() != m + 1 {
        return fail("E_INPUT", "need one more quote than step dates");
    }
    check_step_dates(as_of, step_dates)?;
    let swaps = quotes
        .iter()
        .map(|q| OisLegs::new(c, as_of, q.0))
        .collect::<Result<Vec<_>>>()?;
    for (j, s) in swaps.iter().enumerate() {
        let p = s.last_payment();
        let lower = if j == 0 { as_of } else { step_dates[j - 1] };
        if p <= lower || (j < m && p > step_dates[j]) {
            return fail("E_INPUT", "each quote must end between its step dates");
        }
    }
    check_jumps(as_of, jumps)?;
    let mut rates = vec![quotes[0].1; m + 1];
    let curve = |r: &[f64]| StepCurve {
        as_of,
        base_rate: r[0],
        steps: step_dates
            .iter()
            .copied()
            .zip(r[1..].iter().copied())
            .collect(),
        jumps: jumps.to_vec(),
    };
    let no = || err("E_NO_CONVERGENCE", "the step fit failed");
    for j in 0..=m {
        let value = |x: f64, r: &[f64]| -> Result<f64> {
            let mut r = r.to_vec();
            r[j] = x;
            Ok(swaps[j].par_rate(&curve(&r))? - quotes[j].1)
        };
        let mut x = if j == 0 { quotes[0].1 } else { rates[j - 1] };
        let (mut best, mut best_x) = (f64::INFINITY, x);
        for _ in 0..60 {
            let e = value(x, &rates)?;
            if !e.is_finite() {
                return Err(no());
            }
            if e.abs() < best {
                (best, best_x) = (e.abs(), x);
            }
            if e.abs() <= FIT_GOAL {
                break;
            }
            let h = 1e-6;
            let slope = (value(x + h, &rates)? - value(x - h, &rates)?) / (2.0 * h);
            let step = e / slope;
            if !step.is_finite() {
                return Err(no());
            }
            if step.abs() <= 1e-17 {
                break;
            }
            x -= step;
        }
        rates[j] = best_x;
    }
    let fitted = curve(&rates);
    let mut worst = 0.0f64;
    for (s, q) in swaps.iter().zip(quotes) {
        let e = (s.par_rate(&fitted)? - q.1).abs();
        if !e.is_finite() {
            return Err(no());
        }
        worst = worst.max(e);
    }
    if worst >= REPRICING_LIMIT {
        return Err(no());
    }
    Ok(StepFit {
        base_rate: rates[0],
        step_rates: rates[1..].to_vec(),
        max_repricing_error: worst,
    })
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Convexity {
    pub futures_rate: f64,
    pub convexity: f64,
    pub forward_rate: f64,
}

/// `(1 - e^{-a x}) / a`, with its limit `x` at `a = 0`.
fn b_factor(a: f64, x: f64) -> f64 {
    if a == 0.0 { x } else { -(-a * x).exp_m1() / a }
}

/// `rates.futures.convexity`: Hull-White, as QuantLib's `HullWhite::convexityBias`.
pub fn convexity(price: f64, t: f64, big_t: f64, sigma: f64, a: f64) -> Result<Convexity> {
    if big_t.is_nan() || t.is_nan() || big_t <= t {
        return fail("E_INPUT", "end_years must be after start_years");
    }
    if t < 0.0 || sigma.is_nan() || sigma < 0.0 || a.is_nan() || a < 0.0 {
        return fail(
            "E_DOMAIN",
            "start_years, sigma and mean_reversion must not be negative",
        );
    }
    let futures_rate = (100.0 - price) / 100.0;
    let d = big_t - t;
    let bd = b_factor(a, d);
    let l = b_factor(2.0 * a, t) * 2.0;
    let bt = b_factor(a, t);
    let z = sigma * sigma / 2.0 * (l * bd * bd + bd * bt * bt);
    let convexity = -(-z).exp_m1() * (futures_rate + 1.0 / d);
    Ok(Convexity {
        futures_rate,
        convexity,
        forward_rate: futures_rate - convexity,
    })
}

/// FX data for CSA discounting: spot and forwards, units of trade currency per collateral unit.
#[derive(Debug, Clone)]
pub struct CsaFx {
    pub spot: f64,
    pub forwards: Vec<(Date, f64)>,
}

/// `rates.csa.discount`.
pub fn csa_discount(
    curve: &Curve,
    spread: f64,
    fx: Option<&CsaFx>,
    dates: &[Date],
) -> Result<Vec<f64>> {
    if dates.is_empty() {
        return fail("E_INPUT", "no dates");
    }
    let mut table = HashMap::new();
    if let Some(fx) = fx {
        if fx.spot.is_nan()
            || fx.spot <= 0.0
            || fx.forwards.iter().any(|f| f.1.is_nan() || f.1 <= 0.0)
        {
            return fail("E_DOMAIN", "spot and forwards must be positive");
        }
        for (d, f) in &fx.forwards {
            if table.insert(d.serial(), *f).is_some() {
                return fail("E_INPUT", "two forwards on one date");
            }
        }
        if dates.iter().any(|d| !table.contains_key(&d.serial())) {
            return fail("E_INPUT", "a date has no forward");
        }
    }
    dates
        .iter()
        .map(|d| {
            let base = curve.discount(*d)? * (-spread * curve_time(curve.as_of, *d)).exp();
            Ok(match fx {
                Some(fx) => base * fx.spot / table[&d.serial()],
                None => base,
            })
        })
        .collect()
}

/// `rates.curve.joint_bootstrap`: `(discount, projection)`. The system is block triangular,
/// so the discount block is solved first by `method`, then the projection block on it.
pub fn joint_bootstrap(
    c: &Overnight,
    as_of: Date,
    ois_quotes: &[OisQuote],
    term_quotes: &[ProjectionQuote],
    interpolation: Interpolation,
    method: SolveMethod,
) -> Result<(Solved, Solved)> {
    if ois_quotes.is_empty() || term_quotes.is_empty() {
        return fail("E_INPUT", "both quote lists must be non-empty");
    }
    let p = OisCurveProblem::new(c, as_of, ois_quotes, interpolation)?;
    let discount = p.solve(&p.mids, method)?;
    let projection = projection::bootstrap(&discount.curve, as_of, term_quotes, interpolation)?;
    Ok((discount, projection))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::conventions::overnight;

    fn d(s: &str) -> Date {
        Date::parse(s).unwrap()
    }

    fn sofr() -> Overnight {
        overnight("SOFR").unwrap()
    }

    fn flat_fixings(from: &str, to: &str, r: f64) -> Vec<(Date, f64)> {
        let (mut x, end) = (d(from), d(to));
        let mut out = Vec::new();
        while x <= end {
            out.push((x, r));
            x = x.add_days(1);
        }
        out
    }

    #[test]
    fn compound_dated_flat_rate_matches_closed_form() {
        let f = flat_fixings("2026-10-01", "2027-03-01", 0.04);
        for (m, k) in [
            (Shift::None, 0),
            (Shift::Lookback, 2),
            (Shift::ObservationShift, 2),
            (Shift::Lockout, 2),
        ] {
            let r = compound_dated(&sofr(), d("2026-11-10"), d("2027-02-10"), m, k, &f).unwrap();
            assert!(
                r.compounded_rate > 0.04 && r.compounded_rate < 0.0403,
                "{m:?}"
            );
            assert_eq!(r.accrual, 92.0 / 360.0);
            assert_eq!(r.interest, r.compounded_rate * r.accrual);
        }
    }

    #[test]
    fn compound_dated_single_step_is_the_fixing() {
        let f = vec![(d("2026-11-12"), 0.05)];
        let r = compound_dated(
            &sofr(),
            d("2026-11-12"),
            d("2026-11-13"),
            Shift::None,
            0,
            &f,
        )
        .unwrap();
        assert!((r.compounded_rate - 0.05).abs() < 1e-13);
    }

    #[test]
    fn compound_dated_errors() {
        let f = flat_fixings("2026-10-01", "2027-03-01", 0.04);
        let code = |s: &str, e: &str, m: Shift, k: i64, f: &[(Date, f64)]| {
            compound_dated(&sofr(), d(s), d(e), m, k, f)
                .unwrap_err()
                .code
        };
        assert_eq!(
            code("2026-11-10", "2026-11-10", Shift::None, 0, &f),
            "E_DATE_ORDER"
        );
        assert_eq!(
            code("2026-11-10", "2027-02-10", Shift::None, 1, &f),
            "E_INPUT"
        );
        assert_eq!(
            code("2026-11-10", "2027-02-10", Shift::Lookback, -1, &f),
            "E_INPUT"
        );
        assert_eq!(
            code("2026-11-10", "2027-02-10", Shift::Lockout, 0, &f),
            "E_INPUT"
        );
        assert_eq!(
            code("2026-11-10", "2027-02-10", Shift::Lockout, 500, &f),
            "E_INPUT"
        );
        assert_eq!(
            code("2026-11-07", "2027-02-10", Shift::None, 0, &f),
            "E_INPUT"
        );
        let mut dup = f.clone();
        dup.push(f[50]);
        assert_eq!(
            code("2026-11-10", "2027-02-10", Shift::None, 0, &dup),
            "E_INPUT"
        );
        assert_eq!(
            code("2026-11-10", "2027-02-10", Shift::None, 0, &f[..40]),
            "E_INPUT"
        );
    }

    #[test]
    fn fallback_table() {
        assert_eq!(fallback_spread("USD-LIBOR-3M"), Some(("SOFR", 0.0026161)));
        assert_eq!(fallback_spread("GBP-LIBOR-12M"), Some(("SONIA", 0.0046440)));
        assert_eq!(fallback_spread("EUR-LIBOR-3M"), None);
    }

    #[test]
    fn step_curve_integrates_exactly() {
        let c = StepCurve::new(
            d("2026-11-06"),
            0.04,
            vec![(d("2027-11-06"), 0.05)],
            vec![(d("2026-12-31"), 0.99)],
        )
        .unwrap();
        let t1 = 365.0 / 365.0;
        let df = c.discount(d("2028-11-05")).unwrap();
        let t2 = curve_time(d("2026-11-06"), d("2028-11-05"));
        let want = (-(0.04 * t1 + 0.05 * (t2 - t1))).exp() * 0.99;
        assert!((df - want).abs() < 1e-15);
        assert_eq!(
            c.discount(d("2026-12-31")).unwrap(),
            (-0.04 * 55.0 / 365.0f64).exp()
        );
        assert_eq!(c.forward(d("2027-11-06")).unwrap(), 0.05);
        assert_eq!(c.forward(d("2027-11-05")).unwrap(), 0.04);
        assert_eq!(
            c.discount(d("2026-11-05")).unwrap_err().code,
            "E_OUT_OF_RANGE"
        );
        assert_eq!(
            c.forward(d("2026-11-05")).unwrap_err().code,
            "E_OUT_OF_RANGE"
        );
    }

    #[test]
    fn step_curve_errors() {
        let as_of = d("2026-11-06");
        let e = |s: Vec<(Date, f64)>, j: Vec<(Date, f64)>| {
            StepCurve::new(as_of, 0.04, s, j).unwrap_err().code
        };
        assert_eq!(e(vec![(as_of, 0.04)], vec![]), "E_INPUT");
        assert!(StepCurve::new(as_of, 0.04, vec![], vec![]).is_ok());
        let s = vec![(d("2027-01-01"), 0.04)];
        assert_eq!(e(s.clone(), vec![(as_of, 0.9)]), "E_INPUT");
        assert_eq!(e(s, vec![(d("2027-01-01"), 0.0)]), "E_DOMAIN");
    }

    #[test]
    fn fit_steps_recovers_truth() {
        let as_of = d("2026-11-06");
        let steps = [d("2026-12-10"), d("2027-03-18")];
        let truth = StepCurve::new(
            as_of,
            0.0425,
            vec![(steps[0], 0.04), (steps[1], 0.037)],
            vec![(d("2026-12-31"), 0.9999)],
        )
        .unwrap();
        let tenors = [(3, 'W'), (3, 'M'), (1, 'Y')];
        let quotes: Vec<_> = tenors
            .iter()
            .map(|t| {
                (
                    *t,
                    OisLegs::new(&sofr(), as_of, *t)
                        .unwrap()
                        .par_rate(&truth)
                        .unwrap(),
                )
            })
            .collect();
        let fit = fit_steps(&sofr(), as_of, &steps, &quotes, &truth.jumps).unwrap();
        assert!((fit.base_rate - 0.0425).abs() < 1e-12);
        assert!((fit.step_rates[0] - 0.04).abs() < 1e-12);
        assert!((fit.step_rates[1] - 0.037).abs() < 1e-12);
        assert!(fit.max_repricing_error < 1e-13);
        let e = fit_steps(&sofr(), as_of, &steps, &quotes[..2], &[]).unwrap_err();
        assert_eq!(e.code, "E_INPUT");
        let bad = [quotes[0], quotes[0], quotes[2]];
        assert_eq!(
            fit_steps(&sofr(), as_of, &steps, &bad, &[])
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        let j = [(as_of, 0.9)];
        assert_eq!(
            fit_steps(&sofr(), as_of, &steps, &quotes, &j)
                .unwrap_err()
                .code,
            "E_INPUT"
        );
    }

    #[test]
    fn convexity_limits_and_errors() {
        let c = convexity(96.0, 1.0, 1.25, 0.01, 0.0).unwrap();
        let z: f64 = 0.0001 / 2.0 * (2.0 * 0.25 * 0.25 + 0.25);
        assert!((c.convexity - (-(-z).exp_m1()) * (0.04 + 4.0)).abs() < 1e-17);
        let near = convexity(96.0, 1.0, 1.25, 0.01, 1e-12).unwrap();
        assert!((near.convexity - c.convexity).abs() < 1e-15);
        assert_eq!(c.futures_rate, 0.04);
        assert_eq!(c.forward_rate, c.futures_rate - c.convexity);
        assert_eq!(
            convexity(96.0, 1.0, 1.0, 0.01, 0.03).unwrap_err().code,
            "E_INPUT"
        );
        assert_eq!(
            convexity(96.0, -0.1, 1.0, 0.01, 0.03).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            convexity(96.0, 0.1, 1.0, -0.01, 0.03).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            convexity(96.0, 0.1, 1.0, 0.01, -0.03).unwrap_err().code,
            "E_DOMAIN"
        );
    }

    fn flat_curve() -> Curve {
        let as_of = d("2026-11-06");
        let p = d("2036-11-06");
        Curve::from_logs(
            as_of,
            Interpolation::LogLinearDf,
            &[p],
            &[-0.03 * curve_time(as_of, p)],
        )
    }

    #[test]
    fn csa_discount_cases() {
        let c = flat_curve();
        let x = d("2027-11-06");
        let base = c.discount(x).unwrap();
        let v = csa_discount(&c, 0.01, None, &[x]).unwrap();
        assert!((v[0] - base * (-0.01f64).exp()).abs() < 1e-16);
        let fx = CsaFx {
            spot: 1.1,
            forwards: vec![(x, 1.2)],
        };
        let v = csa_discount(&c, 0.0, Some(&fx), &[x]).unwrap();
        assert!((v[0] - base * 1.1 / 1.2).abs() < 1e-16);
        let e = |fx: &CsaFx, ds: &[Date]| csa_discount(&c, 0.0, Some(fx), ds).unwrap_err().code;
        assert_eq!(e(&fx, &[d("2028-01-01")]), "E_INPUT");
        let zero = CsaFx {
            spot: 0.0,
            forwards: fx.forwards.clone(),
        };
        assert_eq!(e(&zero, &[x]), "E_DOMAIN");
        let neg = CsaFx {
            spot: 1.0,
            forwards: vec![(x, -1.0)],
        };
        assert_eq!(e(&neg, &[x]), "E_DOMAIN");
        assert_eq!(
            csa_discount(&c, 0.0, None, &[]).unwrap_err().code,
            "E_INPUT"
        );
        let early = csa_discount(&c, 0.0, None, &[d("2026-11-05")]).unwrap_err();
        assert_eq!(early.code, "E_OUT_OF_RANGE");
    }

    #[test]
    fn joint_matches_two_step_and_rejects_empty() {
        let as_of = d("2026-11-06");
        let q = |t, r| OisQuote {
            tenor: t,
            bid: r,
            ask: r,
        };
        let ois = [q((1, 'Y'), 0.037), q((2, 'Y'), 0.036), q((5, 'Y'), 0.0365)];
        let term = [
            ProjectionQuote::Deposit {
                months: 3,
                rate: 0.039,
            },
            ProjectionQuote::Swap {
                months: 24,
                rate: 0.037,
            },
        ];
        let i = Interpolation::LogLinearDf;
        let (a, b) =
            joint_bootstrap(&sofr(), as_of, &ois, &term, i, SolveMethod::Sequential).unwrap();
        let (c, e) = joint_bootstrap(&sofr(), as_of, &ois, &term, i, SolveMethod::Global).unwrap();
        for (x, y) in a.logs.iter().zip(&c.logs).chain(b.logs.iter().zip(&e.logs)) {
            assert!((x - y).abs() < 1e-12);
        }
        let r = joint_bootstrap(&sofr(), as_of, &[], &term, i, SolveMethod::Global);
        assert_eq!(r.unwrap_err().code, "E_INPUT");
        let r = joint_bootstrap(&sofr(), as_of, &ois, &[], i, SolveMethod::Global);
        assert_eq!(r.unwrap_err().code, "E_INPUT");
    }
}
