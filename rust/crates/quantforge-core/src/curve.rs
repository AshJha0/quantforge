//! Curve object, and the solve shared by every bootstrap (`curve-framework.md`).
use crate::dates::Date;
use crate::daycount::{DayCountInputs, year_fraction};
use crate::error::{Result, err, fail};
use crate::linalg::solve;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Interpolation {
    LogLinearDf,
    LinearZero,
}

impl Interpolation {
    pub fn parse(s: &str) -> Option<Interpolation> {
        match s {
            "LOG_LINEAR_DF" => Some(Interpolation::LogLinearDf),
            "LINEAR_ZERO" => Some(Interpolation::LinearZero),
            _ => None,
        }
    }
}

/// A curve as given in a case, before its rule checks.
#[derive(Debug, Clone)]
pub struct CurveInput {
    pub as_of: Date,
    pub interpolation: Interpolation,
    pub pillars: Vec<(Date, f64)>,
    /// Stage D: `(date, factor)`, may be empty.
    pub jumps: Vec<(Date, f64)>,
}

/// Anything that gives a discount factor for a date.
pub trait Discount {
    fn discount(&self, d: Date) -> Result<f64>;
}

impl Discount for Curve {
    fn discount(&self, d: Date) -> Result<f64> {
        Curve::discount(self, d)
    }
}

/// Checks a jump list (`curve-framework.md`): dates first, then factors.
pub fn check_jumps(as_of: Date, jumps: &[(Date, f64)]) -> Result<()> {
    if jumps.first().is_some_and(|j| j.0 <= as_of) || jumps.windows(2).any(|w| w[1].0 <= w[0].0) {
        return fail("E_INPUT", "jump dates must increase and follow as_of");
    }
    if jumps.iter().any(|j| j.1.is_nan() || j.1 <= 0.0) {
        return fail("E_DOMAIN", "a jump factor is not positive");
    }
    Ok(())
}

/// `ln J(t)`: the sum of log factors whose time is strictly before `t`.
fn log_jump(jumps: &[(f64, f64)], t: f64) -> f64 {
    jumps.iter().take_while(|j| j.0 < t).map(|j| j.1).sum()
}

/// Market data: a frozen discount curve. Node 0 is the implied node at `as_of`.
#[derive(Debug, Clone)]
pub struct Curve {
    pub as_of: Date,
    interpolation: Interpolation,
    times: Vec<f64>,
    /// Logs of `S = D / J` at the nodes.
    logs: Vec<f64>,
    /// `(time, ln factor)`.
    jumps: Vec<(f64, f64)>,
}

pub fn curve_time(as_of: Date, d: Date) -> f64 {
    (d.serial() - as_of.serial()) as f64 / 365.0
}

impl Curve {
    pub fn new(c: &CurveInput) -> Result<Curve> {
        if c.pillars.is_empty()
            || c.pillars[0].0 <= c.as_of
            || c.pillars.windows(2).any(|w| w[1].0 <= w[0].0)
        {
            return fail("E_INPUT", "pillars must increase and follow as_of");
        }
        if c.pillars.iter().any(|p| p.1 <= 0.0) {
            return fail("E_DOMAIN", "a discount factor is not positive");
        }
        check_jumps(c.as_of, &c.jumps)?;
        let dates: Vec<Date> = c.pillars.iter().map(|p| p.0).collect();
        let logs: Vec<f64> = c.pillars.iter().map(|p| p.1.ln()).collect();
        Ok(Curve::from_logs_with_jumps(
            c.as_of,
            c.interpolation,
            &dates,
            &logs,
            &c.jumps,
        ))
    }

    /// From log discount factors at dates already known to be in order.
    pub fn from_logs(as_of: Date, i: Interpolation, dates: &[Date], logs: &[f64]) -> Curve {
        Curve::from_logs_with_jumps(as_of, i, dates, logs, &[])
    }

    /// From full log discount factors, with checked jumps. Nodes keep `ln S = ln D - ln J`.
    pub fn from_logs_with_jumps(
        as_of: Date,
        i: Interpolation,
        dates: &[Date],
        logs: &[f64],
        jumps: &[(Date, f64)],
    ) -> Curve {
        let jumps: Vec<(f64, f64)> = jumps
            .iter()
            .map(|j| (curve_time(as_of, j.0), j.1.ln()))
            .collect();
        let mut times = vec![0.0];
        times.extend(dates.iter().map(|d| curve_time(as_of, *d)));
        let mut l = vec![0.0];
        l.extend(
            logs.iter()
                .zip(&times[1..])
                .map(|(x, t)| x - log_jump(&jumps, *t)),
        );
        Curve {
            as_of,
            interpolation: i,
            times,
            logs: l,
            jumps,
        }
    }

    fn zero(&self, i: usize) -> f64 {
        let k = i.max(1);
        -self.logs[k] / self.times[k]
    }

    fn at_time(&self, t: f64) -> f64 {
        let n = self.times.len() - 1;
        if t == 0.0 {
            return 1.0;
        }
        if t > self.times[n] {
            let f = -(self.logs[n] - self.logs[n - 1]) / (self.times[n] - self.times[n - 1]);
            return (self.logs[n] - f * (t - self.times[n])).exp();
        }
        let i = self
            .times
            .partition_point(|x| *x <= t)
            .saturating_sub(1)
            .min(n - 1);
        let u = (t - self.times[i]) / (self.times[i + 1] - self.times[i]);
        match self.interpolation {
            Interpolation::LogLinearDf => ((1.0 - u) * self.logs[i] + u * self.logs[i + 1]).exp(),
            Interpolation::LinearZero => {
                let z = (1.0 - u) * self.zero(i) + u * self.zero(i + 1);
                (-z * t).exp()
            }
        }
    }

    pub fn discount(&self, d: Date) -> Result<f64> {
        if d < self.as_of {
            return fail("E_OUT_OF_RANGE", "date is before as_of");
        }
        let t = curve_time(self.as_of, d);
        if self.jumps.is_empty() {
            return Ok(self.at_time(t));
        }
        Ok(self.at_time(t) * log_jump(&self.jumps, t).exp())
    }

    /// Continuous zero rate; `None` at `as_of`.
    pub fn zero_rate(&self, d: Date) -> Result<Option<f64>> {
        let df = self.discount(d)?;
        Ok((d != self.as_of).then(|| -df.ln() / curve_time(self.as_of, d)))
    }

    pub fn forward(&self, start: Date, end: Date, day_count: &str) -> Result<f64> {
        let none = DayCountInputs::default();
        year_fraction(day_count, start, start, &none)?;
        if end <= start {
            return fail("E_DATE_ORDER", "end is not after start");
        }
        let alpha = year_fraction(day_count, start, end, &none)?;
        Ok((self.discount(start)? / self.discount(end)? - 1.0) / alpha)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SolveMethod {
    Sequential,
    Global,
}

/// A solved curve, with its largest repricing error in rate.
#[derive(Debug, Clone)]
pub struct Solved {
    pub curve: Curve,
    pub dates: Vec<Date>,
    pub logs: Vec<f64>,
    pub max_repricing_error: f64,
}

/// Required by the specs: every quote must reprice below this.
const REPRICING_LIMIT: f64 = 1e-13;
const RESIDUAL_GOAL: f64 = 1e-15;
const STEP_GOAL: f64 = 1e-16;
const BUMP: f64 = 1e-6;

fn no_convergence() -> crate::error::QfError {
    err("E_NO_CONVERGENCE", "the curve solve failed")
}

/// Solves `model(curve, j) = quotes[j]` for log discount factors at `dates`. The model for
/// quote `j` may only read dates on or before pillar `j`.
pub fn solve_curve(
    as_of: Date,
    interpolation: Interpolation,
    dates: &[Date],
    quotes: &[f64],
    model: &dyn Fn(&Curve, usize) -> Result<f64>,
    method: SolveMethod,
) -> Result<Solved> {
    solve_curve_with_jumps(as_of, interpolation, dates, &[], quotes, model, method)
}

/// As `solve_curve`, on a curve with checked jumps. The unknowns are full log discount factors.
pub fn solve_curve_with_jumps(
    as_of: Date,
    interpolation: Interpolation,
    dates: &[Date],
    jumps: &[(Date, f64)],
    quotes: &[f64],
    model: &dyn Fn(&Curve, usize) -> Result<f64>,
    method: SolveMethod,
) -> Result<Solved> {
    let start = |j: usize| -quotes[j] * curve_time(as_of, dates[j]);
    let mut logs: Vec<f64> = (0..dates.len()).map(start).collect();
    let build =
        |l: &[f64]| Curve::from_logs_with_jumps(as_of, interpolation, &dates[..l.len()], l, jumps);
    match method {
        SolveMethod::Sequential => {
            for j in 0..dates.len() {
                let value = |x: f64, base: &[f64]| -> Result<f64> {
                    let mut l = base[..=j].to_vec();
                    l[j] = x;
                    model(&build(&l), j)
                };
                let (mut x, mut best, mut best_x) = (logs[j], f64::INFINITY, logs[j]);
                for _ in 0..60 {
                    let r = value(x, &logs)? - quotes[j];
                    if !r.is_finite() {
                        return Err(no_convergence());
                    }
                    if r.abs() < best {
                        (best, best_x) = (r.abs(), x);
                    }
                    if r.abs() <= RESIDUAL_GOAL {
                        break;
                    }
                    let d = (value(x + BUMP, &logs)? - value(x - BUMP, &logs)?) / (2.0 * BUMP);
                    let step = r / d;
                    if !step.is_finite() {
                        return Err(no_convergence());
                    }
                    if step.abs() <= STEP_GOAL {
                        break;
                    }
                    x -= step;
                }
                logs[j] = best_x;
            }
        }
        SolveMethod::Global => {
            let n = dates.len();
            let residuals = |l: &[f64]| -> Result<Vec<f64>> {
                let c = build(l);
                (0..n).map(|j| Ok(model(&c, j)? - quotes[j])).collect()
            };
            let (mut best, mut best_logs) = (f64::INFINITY, logs.clone());
            for _ in 0..60 {
                let r = residuals(&logs)?;
                let worst = r.iter().fold(0.0f64, |m, v| m.max(v.abs()));
                if !worst.is_finite() || r.iter().any(|v| !v.is_finite()) {
                    return Err(no_convergence());
                }
                if worst < best {
                    (best, best_logs) = (worst, logs.clone());
                }
                if worst <= RESIDUAL_GOAL {
                    break;
                }
                let mut jac = vec![vec![0.0; n]; n];
                for k in 0..n {
                    let mut up = logs.clone();
                    up[k] += BUMP;
                    let mut down = logs.clone();
                    down[k] -= BUMP;
                    let (a, b) = (residuals(&up)?, residuals(&down)?);
                    for i in 0..n {
                        jac[i][k] = (a[i] - b[i]) / (2.0 * BUMP);
                    }
                }
                let step = solve(&jac, &r).map_err(|_| no_convergence())?;
                if step.iter().all(|s| s.abs() <= STEP_GOAL) {
                    break;
                }
                for (l, s) in logs.iter_mut().zip(&step) {
                    *l -= s;
                }
            }
            logs = best_logs;
        }
    }
    let curve = build(&logs);
    let mut worst = 0.0f64;
    for j in 0..dates.len() {
        let e = (model(&curve, j)? - quotes[j]).abs();
        if !e.is_finite() {
            return Err(no_convergence());
        }
        worst = worst.max(e);
    }
    if worst >= REPRICING_LIMIT {
        return Err(no_convergence());
    }
    Ok(Solved {
        curve,
        dates: dates.to_vec(),
        logs,
        max_repricing_error: worst,
    })
}
