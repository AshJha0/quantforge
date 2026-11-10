//! `risk.book.ois_sensitivity` (`book-sensitivities.md`, rulings F-29 and F-30): PVs, par-quote
//! sensitivities and the zero-rate Jacobian of an OIS book, by reverse-mode AAD through the
//! implicit function theorem. The tape records the pricer and the residuals at the solved curve,
//! never the Newton iterations.
use std::collections::HashSet;

use crate::aad::{Tape, Var};
use crate::conventions::Overnight;
use crate::curve::{Interpolation, SolveMethod, curve_time};
use crate::dates::Date;
use crate::error::{Result, fail};
use crate::linalg::{Matrix, solve};
use crate::ois::{OisCurveProblem, OisLegs, OisQuote};

#[derive(Debug, Clone)]
pub struct BookSwap {
    pub id: String,
    pub tenor_years: i64,
    pub fixed_rate: f64,
    pub payer: bool,
}

#[derive(Debug, Clone)]
pub struct BookRisk {
    pub pv: Vec<f64>,
    pub book_pv: f64,
    /// `d pv_i / d q_j`.
    pub quote_sensitivity: Matrix,
    pub book_sensitivity: Vec<f64>,
    pub pillars: Vec<Date>,
    /// `d z_i / d q_j`.
    pub zero_jacobian: Matrix,
}

/// The solved curve on a tape: `ln D` at the pillars are the inputs.
struct TapeCurve<'t> {
    as_of: Date,
    interpolation: Interpolation,
    times: Vec<f64>,
    /// Node 0 is the constant 0 at `as_of`.
    logs: Vec<Var<'t>>,
}

impl<'t> TapeCurve<'t> {
    fn zero(&self, i: usize) -> Var<'t> {
        let k = i.max(1);
        -self.logs[k] / self.times[k]
    }

    /// Mirrors `Curve::at_time` for the two sequential methods.
    fn discount(&self, d: Date) -> Var<'t> {
        let t = curve_time(self.as_of, d);
        let n = self.times.len() - 1;
        let tape = self.logs[0].tape();
        if t == 0.0 {
            return tape.constant(1.0);
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
            Interpolation::LinearZero => {
                let z = self.zero(i) * (1.0 - u) + self.zero(i + 1) * u;
                (-(z * t)).exp()
            }
            _ => (self.logs[i] * (1.0 - u) + self.logs[i + 1] * u).exp(),
        }
    }

    /// `(F, A)`, the general floating form of `OisLegs::legs`.
    fn legs(&self, legs: &OisLegs) -> (Var<'t>, Var<'t>) {
        let tape = self.logs[0].tape();
        let (mut f, mut a) = (tape.constant(0.0), tape.constant(0.0));
        for (p, alpha) in legs.periods() {
            let d = self.discount(p.payment);
            a = a + d * *alpha;
            f = f + (self.discount(p.start) / self.discount(p.end) - 1.0) * d;
        }
        (f, a)
    }
}

/// Solves `m x = b` by forward substitution when `m` is exactly lower triangular, so that
/// structural zeros stay exact (F-30); otherwise by the general solver.
fn solve_keeping_zeros(m: &Matrix, b: &[f64]) -> Result<Vec<f64>> {
    let n = m.len();
    let lower = (0..n).all(|i| (i + 1..n).all(|j| m[i][j] == 0.0));
    if !lower {
        return solve(m, b);
    }
    let mut x = vec![0.0; n];
    for i in 0..n {
        let mut s = b[i];
        for j in 0..i {
            if m[i][j] != 0.0 && x[j] != 0.0 {
                s -= m[i][j] * x[j];
            }
        }
        x[i] = if s == 0.0 { 0.0 } else { s / m[i][i] };
    }
    Ok(x)
}

fn transpose(m: &Matrix) -> Matrix {
    let (r, c) = (m.len(), m.first().map_or(0, Vec::len));
    (0..c).map(|j| (0..r).map(|i| m[i][j]).collect()).collect()
}

/// `risk.book.ois_sensitivity`.
pub fn ois_sensitivity(
    convention: &Overnight,
    as_of: Date,
    quotes: &[OisQuote],
    interpolation: Interpolation,
    swaps: &[BookSwap],
) -> Result<BookRisk> {
    crate::error::finite("quotes", &quotes)?;
    if swaps.iter().any(|s| !s.fixed_rate.is_finite()) {
        crate::error::finite("fixed_rate", &f64::NAN)?;
    }
    if swaps.is_empty() {
        return fail("E_INPUT", "the book has no swaps");
    }
    let mut ids = HashSet::new();
    if !swaps.iter().all(|s| ids.insert(s.id.as_str())) {
        return fail("E_INPUT", "duplicate swap id");
    }
    if swaps.iter().any(|s| s.tenor_years < 1) {
        return fail("E_DOMAIN", "tenor_years must be at least 1");
    }
    if !matches!(
        interpolation,
        Interpolation::LogLinearDf | Interpolation::LinearZero
    ) {
        return fail(
            "E_INPUT",
            "the AAD build covers LOG_LINEAR_DF and LINEAR_ZERO",
        );
    }
    let problem = OisCurveProblem::new(convention, as_of, quotes, interpolation)?;
    let solved = problem.solve(&problem.mids, SolveMethod::Sequential)?;
    let n = solved.dates.len();
    let quote_legs = quotes
        .iter()
        .map(|q| OisLegs::new(convention, as_of, q.tenor))
        .collect::<Result<Vec<_>>>()?;
    let swap_legs = swaps
        .iter()
        .map(|s| OisLegs::new(convention, as_of, (s.tenor_years, 'Y')))
        .collect::<Result<Vec<_>>>()?;

    let tape = Tape::new();
    let mut logs = vec![tape.constant(0.0)];
    logs.extend(solved.logs.iter().map(|l| tape.var(*l)));
    let inputs: Vec<usize> = logs[1..].iter().map(Var::idx).collect();
    let mut times = vec![0.0];
    times.extend(solved.dates.iter().map(|d| curve_time(as_of, *d)));
    let curve = TapeCurve {
        as_of,
        interpolation,
        times,
        logs,
    };
    let grad = |out: Var<'_>| -> Vec<f64> {
        let bar = tape.adjoints(out);
        inputs.iter().map(|&k| bar[k]).collect()
    };

    // dR/dx, one reverse sweep per residual (R_j = par_j - q_j).
    let drdx: Matrix = quote_legs
        .iter()
        .map(|l| {
            let (f, a) = curve.legs(l);
            grad(f / a)
        })
        .collect();
    let drdx_t = transpose(&drdx);

    // dx/dq = (dR/dx)^{-1}, since dR/dq = -I. Column j solves dR/dx c = e_j.
    let mut dxdq = vec![vec![0.0; n]; n];
    for j in 0..n {
        let mut e = vec![0.0; n];
        e[j] = 1.0;
        let c = solve_keeping_zeros(&drdx, &e)?;
        for i in 0..n {
            dxdq[i][j] = c[i];
        }
    }
    let zero_jacobian = (0..n)
        .map(|i| {
            let t = curve.times[i + 1];
            (0..n)
                .map(|j| {
                    if dxdq[i][j] == 0.0 {
                        0.0
                    } else {
                        -dxdq[i][j] / t
                    }
                })
                .collect()
        })
        .collect();

    // Each swap: one reverse sweep for x_bar, then q_bar = lambda with (dR/dx)^T lambda = x_bar.
    let mut pv = Vec::with_capacity(swaps.len());
    let mut sens = Vec::with_capacity(swaps.len());
    for (s, legs) in swaps.iter().zip(&swap_legs) {
        let (f, a) = curve.legs(legs);
        let sign = if s.payer { 1.0 } else { -1.0 };
        let v = (f - a * s.fixed_rate) * sign;
        pv.push(v.val);
        let x_bar = grad(v);
        sens.push(solve(&drdx_t, &x_bar)?);
    }
    let book_pv = pv.iter().sum();
    let book_sensitivity = (0..n).map(|j| sens.iter().map(|r| r[j]).sum()).collect();
    Ok(BookRisk {
        pv,
        book_pv,
        quote_sensitivity: sens,
        book_sensitivity,
        pillars: solved.dates,
        zero_jacobian,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::conventions::overnight;

    fn d(s: &str) -> Date {
        Date::parse(s).unwrap()
    }

    fn quotes(bump: Option<(usize, f64)>) -> Vec<OisQuote> {
        let base = [
            ((1, 'M'), 0.043),
            ((6, 'M'), 0.0412),
            ((1, 'Y'), 0.039),
            ((2, 'Y'), 0.0365),
            ((5, 'Y'), 0.0352),
            ((10, 'Y'), 0.0364),
        ];
        base.iter()
            .enumerate()
            .map(|(k, (t, r))| {
                let r = r + bump.filter(|b| b.0 == k).map_or(0.0, |b| b.1);
                OisQuote {
                    tenor: *t,
                    bid: r,
                    ask: r,
                }
            })
            .collect()
    }

    fn book() -> Vec<BookSwap> {
        [(3, 0.04, true), (7, 0.031, false), (12, 0.037, true)]
            .iter()
            .enumerate()
            .map(|(k, (t, r, p))| BookSwap {
                id: format!("S{k}"),
                tenor_years: *t,
                fixed_rate: *r,
                payer: *p,
            })
            .collect()
    }

    /// The unit test the spec asks for: AAD against its own Richardson bump-and-rebuild.
    #[test]
    fn aad_matches_richardson_bump_and_rebuild() {
        let c = overnight("SOFR").unwrap();
        let as_of = d("2026-11-10");
        let pv = |b: Option<(usize, f64)>| {
            ois_sensitivity(&c, as_of, &quotes(b), Interpolation::LogLinearDf, &book())
                .unwrap()
                .pv
        };
        let r = ois_sensitivity(
            &c,
            as_of,
            &quotes(None),
            Interpolation::LogLinearDf,
            &book(),
        )
        .unwrap();
        for j in 0..6 {
            let cd = |h: f64| -> Vec<f64> {
                let (u, v) = (pv(Some((j, h))), pv(Some((j, -h))));
                u.iter().zip(&v).map(|(a, b)| (a - b) / (2.0 * h)).collect()
            };
            let (a, b) = (cd(1e-4), cd(5e-5));
            for i in 0..3 {
                let reference = (4.0 * b[i] - a[i]) / 3.0;
                let got = r.quote_sensitivity[i][j];
                assert!(
                    (got - reference).abs() <= 1e-8 + 1e-6 * reference.abs(),
                    "swap {i} quote {j}: {got} vs {reference}"
                );
            }
        }
        // F-30: structural zeros above the diagonal.
        for i in 0..6 {
            for j in i + 1..6 {
                assert_eq!(r.zero_jacobian[i][j], 0.0);
            }
        }
    }

    #[test]
    fn payer_at_par_has_zero_pv_and_own_annuity() {
        let c = overnight("SOFR").unwrap();
        let as_of = d("2026-11-10");
        let q = quotes(None);
        let swap = vec![BookSwap {
            id: "P".into(),
            tenor_years: 5,
            fixed_rate: 0.0352,
            payer: true,
        }];
        let r = ois_sensitivity(&c, as_of, &q, Interpolation::LogLinearDf, &swap).unwrap();
        assert!(r.pv[0].abs() < 1e-14);
        let p = OisCurveProblem::new(&c, as_of, &q, Interpolation::LogLinearDf).unwrap();
        let s = p.solve(&p.mids, SolveMethod::Sequential).unwrap();
        let (_, a) = OisLegs::new(&c, as_of, (5, 'Y'))
            .unwrap()
            .legs(&s.curve)
            .unwrap();
        assert!((r.quote_sensitivity[0][4] - a).abs() < 1e-12);
    }
}
