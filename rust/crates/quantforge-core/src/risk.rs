//! Rates sensitivities (`rates-sensitivities.md`), use case 2 (`use-cases.md`) and the curve
//! report (`least-squares.md`). Bump and rebuild, with no AD.
use crate::conventions::Overnight;
use crate::curve::{Curve, Interpolation, SolveMethod, curve_time};
use crate::dates::Date;

use crate::error::{Result, fail};
use crate::hedge::solve_hedge;
use crate::linalg::singular_values;
use crate::ois::{OisCurveProblem, OisLegs, OisQuote, OisTrade, pv_of_legs};

const BP: f64 = 1e-4;

/// Curves for every bump: all quotes up and down, then each quote up and down.
struct Bumped {
    parallel: (Curve, Curve),
    single: Vec<(Curve, Curve)>,
}

fn bumped(p: &OisCurveProblem) -> Result<Bumped> {
    let build = |shift: &dyn Fn(usize) -> f64| -> Result<Curve> {
        let q: Vec<f64> = (0..p.mids.len()).map(|j| p.mids[j] + shift(j)).collect();
        Ok(p.solve(&q, SolveMethod::Sequential)?.curve)
    };
    let parallel = (build(&|_| BP)?, build(&|_| -BP)?);
    let mut single = Vec::with_capacity(p.mids.len());
    for k in 0..p.mids.len() {
        let on = |sign: f64| move |j: usize| if j == k { sign * BP } else { 0.0 };
        single.push((build(&on(1.0))?, build(&on(-1.0))?));
    }
    Ok(Bumped { parallel, single })
}

/// Returns `(dv01, key_rate)` with the trade's periods held fixed.
fn sensitivities(b: &Bumped, legs: &OisLegs, trade: &OisTrade) -> Result<(f64, Vec<f64>)> {
    let diff = |pair: &(Curve, Curve)| -> Result<f64> {
        Ok((pv_of_legs(legs, &pair.0, trade)? - pv_of_legs(legs, &pair.1, trade)?) / 2.0)
    };
    let keys = b.single.iter().map(diff).collect::<Result<Vec<_>>>()?;
    Ok((diff(&b.parallel)?, keys))
}

pub fn ois_dv01(
    as_of: Date,
    quotes: &[OisQuote],
    interpolation: Interpolation,
    trade: &OisTrade,
) -> Result<(f64, Vec<f64>)> {
    crate::error::finite("quotes", &quotes)?;
    crate::error::finite("trade", &trade)?;
    let p = OisCurveProblem::new(&trade.convention, as_of, quotes, interpolation)?;
    let legs = OisLegs::new(&trade.convention, as_of, trade.tenor)?;
    sensitivities(&bumped(&p)?, &legs, trade)
}

/// Returns `(pv, duration, convexity)`.
pub fn cashflows(flows: &[(f64, f64)], y: f64) -> Result<(f64, f64, f64)> {
    crate::error::finite("flows", &flows)?;
    crate::error::finite("y", &y)?;
    if flows.is_empty() {
        return fail("E_INPUT", "no cashflows");
    }
    if flows.iter().any(|f| f.0 < 0.0) {
        return fail("E_DOMAIN", "t is negative");
    }
    let (mut pv, mut d, mut c) = (0.0, 0.0, 0.0);
    for (t, a) in flows {
        let v = a * (-y * t).exp();
        pv += v;
        d += t * v;
        c += t * t * v;
    }
    if pv == 0.0 {
        return fail("E_DOMAIN", "pv is zero");
    }
    Ok((pv, d / pv, c / pv))
}

#[derive(Debug, Clone, PartialEq)]
pub struct RatesHedge {
    pub pv: f64,
    pub dv01: f64,
    pub key_rate: Vec<f64>,
    pub hedge_units: Vec<f64>,
    pub residual_key_rate: Vec<f64>,
    pub hedge_cost: f64,
}

pub fn rates_hedge(
    as_of: Date,
    quotes: &[OisQuote],
    interpolation: Interpolation,
    trade: &OisTrade,
    hedge_tenors: &[(i64, char)],
    unit_notional: f64,
    half_spread_bp: f64,
) -> Result<RatesHedge> {
    crate::error::finite("quotes", &quotes)?;
    crate::error::finite("trade", &trade)?;
    crate::error::finite("unit_notional", &unit_notional)?;
    crate::error::finite("half_spread_bp", &half_spread_bp)?;
    if half_spread_bp < 0.0 {
        return fail("E_DOMAIN", "half_spread_bp is negative");
    }
    let c = &trade.convention;
    let p = OisCurveProblem::new(c, as_of, quotes, interpolation)?;
    let base = p.solve(&p.mids, SolveMethod::Sequential)?.curve;
    let legs = OisLegs::new(c, as_of, trade.tenor)?;
    let pv = pv_of_legs(&legs, &base, trade)?;
    let b = bumped(&p)?;
    let (dv01, key_rate) = sensitivities(&b, &legs, trade)?;
    let n = key_rate.len();
    let mut a = vec![vec![0.0; hedge_tenors.len()]; n];
    let mut sums = Vec::with_capacity(hedge_tenors.len());
    for (h, tenor) in hedge_tenors.iter().enumerate() {
        let hl = OisLegs::new(c, as_of, *tenor)?;
        let unit = OisTrade {
            convention: *c,
            tenor: *tenor,
            fixed_rate: hl.par_rate(&base)?,
            notional: unit_notional,
            pay: true,
        };
        let (_, column) = sensitivities(&b, &hl, &unit)?;
        for i in 0..n {
            a[i][h] = column[i];
        }
        sums.push(column.iter().sum::<f64>());
    }
    let zeros = vec![0.0; hedge_tenors.len()];
    let s = solve_hedge(&a, &key_rate, &vec![1.0; n], &zeros, 0.0)?;
    let hedge_cost =
        s.x.iter()
            .zip(&sums)
            .map(|(x, c)| x.abs() * c.abs() * half_spread_bp)
            .sum();
    Ok(RatesHedge {
        pv,
        dv01,
        key_rate,
        hedge_units: s.x,
        residual_key_rate: s.residual,
        hedge_cost,
    })
}

#[derive(Debug, Clone, PartialEq)]
pub struct CurveReport {
    pub jacobian: Vec<Vec<f64>>,
    pub condition_number: f64,
    pub max_repricing_error: f64,
}

const REPORT_BUMP: f64 = 1e-5;

pub fn curve_report(
    c: &Overnight,
    as_of: Date,
    quotes: &[OisQuote],
    interpolation: Interpolation,
) -> Result<CurveReport> {
    crate::error::finite("quotes", &quotes)?;
    let p = OisCurveProblem::new(c, as_of, quotes, interpolation)?;
    let base = p.solve(&p.mids, SolveMethod::Sequential)?;
    let times: Vec<f64> = base.dates.iter().map(|d| curve_time(as_of, *d)).collect();
    let n = times.len();
    let mut jacobian = vec![vec![0.0; n]; n];
    for j in 0..n {
        let solved = |sign: f64| {
            let mut q = p.mids.clone();
            q[j] += sign * REPORT_BUMP;
            p.solve(&q, SolveMethod::Sequential)
        };
        let (up, down) = (solved(1.0)?, solved(-1.0)?);
        for i in 0..n {
            jacobian[i][j] = -(up.logs[i] - down.logs[i]) / times[i] / (2.0 * REPORT_BUMP);
        }
    }
    let s = singular_values(&jacobian);
    let largest = s.iter().copied().fold(0.0, f64::max);
    let smallest = s.iter().copied().fold(f64::INFINITY, f64::min);
    Ok(CurveReport {
        jacobian,
        condition_number: largest / smallest,
        max_repricing_error: base.max_repricing_error,
    })
}

impl crate::error::Finite for CurveReport {
    fn is_all_finite(&self) -> bool {
        self.jacobian.is_all_finite()
            && self.condition_number.is_all_finite()
            && self.max_repricing_error.is_all_finite()
    }
}

impl crate::error::Finite for RatesHedge {
    fn is_all_finite(&self) -> bool {
        self.pv.is_all_finite()
            && self.dv01.is_all_finite()
            && self.key_rate.is_all_finite()
            && self.hedge_units.is_all_finite()
            && self.residual_key_rate.is_all_finite()
            && self.hedge_cost.is_all_finite()
    }
}
