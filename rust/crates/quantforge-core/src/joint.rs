//! `rates.curve.joint_solve` (`joint-solve-and-funding.md`, rulings F-24 to F-27): OIS,
//! step, projection and cross-currency curves solved as one block lower triangular system,
//! with calibrated turns and the implicit-function-theorem Jacobian.
use std::collections::HashMap;

use crate::conventions::Overnight;
use crate::curve::{Curve, Discount, Interpolation, check_jumps, curve_time};
use crate::dates::Date;
use crate::error::{Result, err, fail};
use crate::linalg::{Matrix, solve};
use crate::ois::OisLegs;
use crate::projection::{self, ProjectionQuote};
use crate::rates_overnight::{StepCurve, convexity};
use crate::xccy;

#[derive(Debug, Clone)]
pub enum CurveKind {
    Ois {
        convention: Overnight,
        interpolation: Interpolation,
        jumps: Vec<(Date, f64)>,
    },
    Steps {
        convention: Overnight,
        step_dates: Vec<Date>,
        jumps: Vec<(Date, f64)>,
    },
    Projection {
        discount: String,
        interpolation: Interpolation,
    },
    Xccy {
        domestic: String,
        foreign_projection: String,
        start: Date,
        interpolation: Interpolation,
    },
}

#[derive(Debug, Clone)]
pub struct CurveSpec {
    pub name: String,
    pub kind: CurveKind,
    pub turns: Vec<Date>,
}

#[derive(Debug, Clone, Copy)]
pub enum Quote {
    Ois {
        tenor: (i64, char),
        rate: f64,
    },
    Future {
        start: Date,
        end: Date,
        price: f64,
        sigma: f64,
        mean_reversion: f64,
    },
    Projection(ProjectionQuote),
    Xccy {
        months: i64,
        spread: f64,
    },
}

#[derive(Debug, Clone)]
pub struct InstrumentSpec {
    pub id: String,
    pub curve: String,
    pub quote: Quote,
    pub turn: bool,
}

/// Solved curve, as the output lists it.
#[derive(Debug, Clone)]
pub enum CurveOut {
    Pillars {
        name: String,
        pillars: Vec<(Date, f64)>,
    },
    Steps {
        name: String,
        base_rate: f64,
        step_rates: Vec<f64>,
    },
}

#[derive(Debug, Clone)]
pub struct JointResult {
    pub curves: Vec<CurveOut>,
    /// `(curve, date, factor)` in unknown order.
    pub turn_factors: Vec<(String, Date, f64)>,
    pub unknowns: Vec<String>,
    pub quotes: Vec<String>,
    pub jacobian: Matrix,
    pub turn_sensitivity: Matrix,
    pub max_repricing_error: f64,
}

/// A built curve of either shape.
enum Built {
    Pillar(Curve),
    Steps(StepCurve),
}

impl Discount for Built {
    fn discount(&self, d: Date) -> Result<f64> {
        match self {
            Built::Pillar(c) => c.discount(d),
            Built::Steps(c) => c.discount(d),
        }
    }
}

enum Model {
    Ois(OisLegs),
    /// `(start, end, alpha)`.
    Future(Date, Date, f64),
    Projection(projection::Instrument),
    Xccy(Vec<Date>),
}

struct Inst {
    curve: usize,
    model: Model,
    /// The value the model must equal (0 for xccy, whose spread sits in the leg).
    target: f64,
    /// `d residual / d quote`.
    dq: Dq,
}

enum Dq {
    Constant(f64),
    /// `d L_foreign / d spread = sum alpha D_f(e)`, read at the solution.
    XccyAnnuity,
}

enum Shape {
    Pillars {
        interpolation: Interpolation,
        dates: Vec<Date>,
    },
    Steps {
        step_dates: Vec<Date>,
    },
}

struct Block {
    shape: Shape,
    jumps: Vec<(Date, f64)>,
    turns: Vec<Date>,
    /// Curves this one reads: projection discount, or xccy foreign projection.
    deps: Vec<usize>,
    /// Offset and count of its unknowns.
    offset: usize,
    size: usize,
    instruments: Vec<usize>,
}

impl Block {
    fn build(&self, as_of: Date, x: &[f64]) -> Built {
        let x = &x[self.offset..self.offset + self.size];
        let k = self.turns.len();
        let main = &x[..self.size - k];
        let mut jumps = self.jumps.clone();
        jumps.extend(
            self.turns
                .iter()
                .zip(&x[self.size - k..])
                .map(|(d, l)| (*d, l.exp())),
        );
        jumps.sort_by_key(|j| j.0);
        match &self.shape {
            Shape::Pillars {
                interpolation,
                dates,
            } => Built::Pillar(Curve::from_logs_with_jumps(
                as_of,
                *interpolation,
                dates,
                main,
                &jumps,
            )),
            Shape::Steps { step_dates } => Built::Steps(StepCurve {
                as_of,
                base_rate: main[0],
                steps: step_dates
                    .iter()
                    .copied()
                    .zip(main[1..].iter().copied())
                    .collect(),
                jumps,
            }),
        }
    }
}

struct System {
    as_of: Date,
    blocks: Vec<Block>,
    insts: Vec<Inst>,
    n: usize,
    /// Xccy spreads by instrument index (they enter the leg, not the target).
    spreads: HashMap<usize, f64>,
}

const GOAL: f64 = 1e-13;
const RESIDUAL_GOAL: f64 = 1e-16;
const NEWTON_BUMP: f64 = 1e-7;
/// Five-point stencil step for `dR/dx` at the solution.
const IFT_BUMP: f64 = 1e-5;
/// Down to `1e-5 / 4^4`, about 4e-8.
const IFT_HALVINGS: usize = 4;

fn no_convergence() -> crate::error::QfError {
    err("E_NO_CONVERGENCE", "the joint solve failed")
}

fn input<T>(what: &str) -> Result<T> {
    fail("E_INPUT", what)
}

impl System {
    fn built(&self, x: &[f64], upto: usize) -> Vec<Built> {
        self.blocks[..=upto]
            .iter()
            .map(|b| b.build(self.as_of, x))
            .collect()
    }

    fn model(&self, curves: &[Built], j: usize) -> Result<f64> {
        let inst = &self.insts[j];
        let b = &self.blocks[inst.curve];
        let own = &curves[inst.curve];
        match &inst.model {
            Model::Ois(legs) => legs.par_rate(own),
            Model::Future(s, e, alpha) => Ok((own.discount(*s)? / own.discount(*e)? - 1.0) / alpha),
            Model::Projection(p) => p.model(&curves[b.deps[0]], own),
            Model::Xccy(dates) => {
                let spread = self.spreads.get(&j).copied().unwrap_or(0.0);
                xccy::leg(dates, &curves[b.deps[0]], own, spread)
            }
        }
    }

    /// Residuals of the instruments of block `b`.
    fn block_residuals(&self, x: &[f64], b: usize) -> Result<Vec<f64>> {
        let curves = self.built(x, b);
        self.blocks[b]
            .instruments
            .iter()
            .map(|&j| Ok(self.model(&curves, j)? - self.insts[j].target))
            .collect()
    }

    fn all_residuals(&self, x: &[f64]) -> Result<Vec<f64>> {
        let curves = self.built(x, self.blocks.len() - 1);
        (0..self.insts.len())
            .map(|j| Ok(self.model(&curves, j)? - self.insts[j].target))
            .collect()
    }

    fn solve_block(&self, x: &mut [f64], b: usize) -> Result<()> {
        let (off, n) = (self.blocks[b].offset, self.blocks[b].size);
        let worst = |r: &[f64]| r.iter().fold(0.0f64, |m, v| m.max(v.abs()));
        let mut r = self.block_residuals(x, b)?;
        let (mut best, mut best_x) = (worst(&r), x[off..off + n].to_vec());
        for _ in 0..80 {
            if !best.is_finite() {
                return Err(no_convergence());
            }
            if worst(&r) <= RESIDUAL_GOAL {
                break;
            }
            let mut jac = vec![vec![0.0; n]; n];
            for k in 0..n {
                let mut up = x.to_vec();
                up[off + k] += NEWTON_BUMP;
                let mut down = x.to_vec();
                down[off + k] -= NEWTON_BUMP;
                let (a, c) = (
                    self.block_residuals(&up, b)?,
                    self.block_residuals(&down, b)?,
                );
                for i in 0..n {
                    jac[i][k] = (a[i] - c[i]) / (2.0 * NEWTON_BUMP);
                }
            }
            let step = solve(&jac, &r).map_err(|_| no_convergence())?;
            if step.iter().any(|s| !s.is_finite()) {
                return Err(no_convergence());
            }
            // Backtracking: halve until the worst residual does not grow.
            let base = x.to_vec();
            let mut lambda = 1.0;
            let mut accepted = false;
            for _ in 0..12 {
                for k in 0..n {
                    x[off + k] = base[off + k] - lambda * step[k];
                }
                if let Ok(t) = self.block_residuals(x, b)
                    && t.iter().all(|v| v.is_finite())
                    && worst(&t) <= worst(&r).max(1e-14)
                {
                    r = t;
                    accepted = true;
                    break;
                }
                lambda /= 2.0;
            }
            if !accepted {
                x.copy_from_slice(&base);
                break;
            }
            if worst(&r) < best {
                (best, best_x) = (worst(&r), x[off..off + n].to_vec());
            }
            if step.iter().all(|s| (lambda * s).abs() <= 1e-17) {
                break;
            }
        }
        x[off..off + n].copy_from_slice(&best_x);
        Ok(())
    }

    /// `dR/dx` by a five-point stencil, column by column. The stage F interpolations are
    /// piecewise in their data, so a stencil may straddle a branch boundary near the solution:
    /// the step shrinks until two consecutive steps agree, within the roundoff of residuals
    /// (about 3e-15, so about 1e-9 at the first step) and far below a kink's jump. Entries of residuals that do not
    /// read an unknown are exactly 0, as every evaluation is identical (ruling F-25).
    fn drdx(&self, x: &[f64]) -> Result<Matrix> {
        let m = self.insts.len();
        let mut a = vec![vec![0.0; self.n]; m];
        for k in 0..self.n {
            let column = |h: f64| -> Result<Vec<f64>> {
                let at = |s: f64| -> Result<Vec<f64>> {
                    let mut y = x.to_vec();
                    y[k] += s;
                    self.all_residuals(&y)
                };
                let (p1, m1, p2, m2) = (at(h)?, at(-h)?, at(2.0 * h)?, at(-2.0 * h)?);
                Ok((0..m)
                    .map(|i| {
                        let (d1, d2) = (p1[i] - m1[i], p2[i] - m2[i]);
                        if d1 == 0.0 && d2 == 0.0 {
                            0.0
                        } else {
                            (8.0 * d1 - d2) / (12.0 * h)
                        }
                    })
                    .collect())
            };
            let mut h = IFT_BUMP;
            let mut cur = column(h)?;
            for _ in 0..IFT_HALVINGS {
                let next = column(h / 4.0)?;
                let agree = cur.iter().zip(&next).all(|(u, v)| {
                    (u - v).abs() <= 4e-9 * (IFT_BUMP / h) + 1e-6 * u.abs().max(v.abs())
                });
                if agree {
                    break;
                }

                (h, cur) = (h / 4.0, next);
            }
            for i in 0..m {
                a[i][k] = cur[i];
            }
        }
        Ok(a)
    }
}

fn check_increasing(as_of: Date, dates: &[Date], what: &str) -> Result<()> {
    if dates.first().is_some_and(|d| *d <= as_of) || dates.windows(2).any(|w| w[1] <= w[0]) {
        return input(what);
    }
    Ok(())
}

fn label_date(d: Date) -> String {
    d.to_string()
}

/// `rates.curve.joint_solve`.
pub fn joint_solve(
    as_of: Date,
    curves: &[CurveSpec],
    instruments: &[InstrumentSpec],
) -> Result<JointResult> {
    crate::error::finite("instruments", &instruments)?;
    if curves.is_empty() || instruments.is_empty() {
        return input("curves and instruments must be non-empty");
    }
    // Names and dependency order.
    let mut index: HashMap<&str, usize> = HashMap::new();
    let is_ois = |c: &CurveSpec| matches!(c.kind, CurveKind::Ois { .. } | CurveKind::Steps { .. });
    let mut deps_of = Vec::new();
    for (k, c) in curves.iter().enumerate() {
        let earlier = |name: &str, need_ois: bool| -> Result<usize> {
            match index.get(name) {
                Some(&i) if !need_ois || is_ois(&curves[i]) => Ok(i),
                _ => Err(err(
                    "E_INPUT",
                    "a curve names an unknown, later or wrong-type curve",
                )),
            }
        };
        let deps = match &c.kind {
            CurveKind::Projection { discount, .. } => vec![earlier(discount, true)?],
            CurveKind::Xccy {
                domestic,
                foreign_projection,
                ..
            } => {
                earlier(domestic, true)?;
                vec![earlier(foreign_projection, true)?]
            }
            _ => Vec::new(),
        };
        if index.insert(c.name.as_str(), k).is_some() {
            return input("duplicate curve name");
        }
        deps_of.push(deps);
    }
    // Ids, curves and allowed types.
    let mut ids = std::collections::HashSet::new();
    for inst in instruments {
        if !ids.insert(inst.id.as_str()) {
            return input("duplicate instrument id");
        }
        let Some(&k) = index.get(inst.curve.as_str()) else {
            return input("an instrument names an unknown curve");
        };
        let ok = matches!(
            (&curves[k].kind, &inst.quote),
            (
                CurveKind::Ois { .. } | CurveKind::Steps { .. },
                Quote::Ois { .. } | Quote::Future { .. },
            ) | (CurveKind::Projection { .. }, Quote::Projection(_))
                | (CurveKind::Xccy { .. }, Quote::Xccy { .. })
        );
        if !ok {
            return input("instrument type not allowed for its curve");
        }
    }
    // Step dates, turns, jumps.
    for c in curves {
        if let CurveKind::Steps { step_dates, .. } = &c.kind {
            check_increasing(
                as_of,
                step_dates,
                "step dates must increase and follow as_of",
            )?;
        }
        check_increasing(as_of, &c.turns, "turns must increase and follow as_of")?;
    }
    for c in curves {
        if let CurveKind::Ois { jumps, .. } | CurveKind::Steps { jumps, .. } = &c.kind {
            check_jumps(as_of, jumps)?;
        }
    }
    // Counts.
    let members: Vec<Vec<usize>> = (0..curves.len())
        .map(|k| {
            (0..instruments.len())
                .filter(|&j| index[instruments[j].curve.as_str()] == k)
                .collect()
        })
        .collect();
    for (k, c) in curves.iter().enumerate() {
        let turned = members[k].iter().filter(|&&j| instruments[j].turn).count();
        if turned != c.turns.len() {
            return input("a curve needs one turn instrument per turn");
        }
        let need = match &c.kind {
            CurveKind::Steps { step_dates, .. } => 1 + step_dates.len() + c.turns.len(),
            _ => members[k].len(),
        };
        if members[k].len() != need || members[k].len() <= c.turns.len() {
            return input("instrument count does not match the curve's unknowns");
        }
    }
    // Instruments: dates (pillars), then their own checks.
    let mut insts = Vec::new();
    let mut pillar_dates: Vec<Vec<Date>> = vec![Vec::new(); curves.len()];
    let mut spreads = HashMap::new();
    let mut first_rate: Vec<Option<f64>> = vec![None; curves.len()];
    let mut later_checks: Vec<Box<dyn Fn() -> Result<()>>> = Vec::new();
    for (j, s) in instruments.iter().enumerate() {
        let k = index[s.curve.as_str()];
        let (model, target, dq, pillar) = match (&curves[k].kind, s.quote) {
            (
                CurveKind::Ois { convention, .. } | CurveKind::Steps { convention, .. },
                Quote::Ois { tenor, rate },
            ) => {
                let legs = OisLegs::new(convention, as_of, tenor)?;
                let p = legs.last_payment();
                (Model::Ois(legs), rate, Dq::Constant(-1.0), p)
            }
            (
                _,
                Quote::Future {
                    start,
                    end,
                    price,
                    sigma,
                    mean_reversion,
                },
            ) => {
                let (t, big_t) = (curve_time(as_of, start), curve_time(as_of, end));
                later_checks.push(Box::new(move || {
                    convexity(price, t, big_t, sigma, mean_reversion).map(|_| ())
                }));
                let alpha = (end.serial() - start.serial()) as f64 / 360.0;
                match convexity(price, t, big_t, sigma, mean_reversion) {
                    Ok(c) => {
                        let ez = 1.0 - c.convexity / (c.futures_rate + 1.0 / (big_t - t));
                        (
                            Model::Future(start, end, alpha),
                            c.forward_rate,
                            Dq::Constant(0.01 * ez),
                            end,
                        )
                    }
                    // Placeholder; the instrument checks run after the pillar check.
                    Err(_) => (
                        Model::Future(start, end, alpha),
                        0.0,
                        Dq::Constant(0.0),
                        end,
                    ),
                }
            }
            (_, Quote::Projection(q)) => {
                let (p, rate, date) = projection::Instrument::new(as_of, &q)?;
                (Model::Projection(p), rate, Dq::Constant(-1.0), date)
            }
            (CurveKind::Xccy { start, .. }, Quote::Xccy { months, spread }) => {
                if *start < as_of {
                    return fail("E_OUT_OF_RANGE", "start is before as_of");
                }
                let dates = xccy::schedule(*start, months)?;
                let p = *dates.last().expect("dates");
                spreads.insert(j, spread);
                (Model::Xccy(dates), 0.0, Dq::XccyAnnuity, p)
            }
            _ => return input("instrument type not allowed for its curve"),
        };
        if first_rate[k].is_none() {
            first_rate[k] = Some(target);
        }
        if !s.turn {
            pillar_dates[k].push(pillar);
        }
        insts.push(Inst {
            curve: k,
            model,
            target,
            dq,
        });
    }
    for (k, c) in curves.iter().enumerate() {
        if !matches!(c.kind, CurveKind::Steps { .. }) {
            check_increasing(as_of, &pillar_dates[k], "pillars must strictly increase")?;
            if let CurveKind::Ois {
                interpolation: Interpolation::Hybrid(e),
                ..
            }
            | CurveKind::Projection {
                interpolation: Interpolation::Hybrid(e),
                ..
            }
            | CurveKind::Xccy {
                interpolation: Interpolation::Hybrid(e),
                ..
            } = &c.kind
                && !pillar_dates[k].contains(e)
            {
                return input("step_end must be a pillar date");
            }
        }
    }
    for check in &later_checks {
        check()?;
    }
    // Blocks and the starting point.
    let mut blocks = Vec::new();
    let mut offset = 0;
    let mut x0 = Vec::new();
    for (k, c) in curves.iter().enumerate() {
        let r0 = first_rate[k].unwrap_or(0.0);
        let (shape, jumps) = match &c.kind {
            CurveKind::Ois {
                interpolation,
                jumps,
                ..
            } => (
                Shape::Pillars {
                    interpolation: *interpolation,
                    dates: pillar_dates[k].clone(),
                },
                jumps.clone(),
            ),
            CurveKind::Projection { interpolation, .. } | CurveKind::Xccy { interpolation, .. } => {
                (
                    Shape::Pillars {
                        interpolation: *interpolation,
                        dates: pillar_dates[k].clone(),
                    },
                    Vec::new(),
                )
            }
            CurveKind::Steps {
                step_dates, jumps, ..
            } => (
                Shape::Steps {
                    step_dates: step_dates.clone(),
                },
                jumps.clone(),
            ),
        };
        let main = match &shape {
            Shape::Pillars { dates, .. } => {
                // Xccy starts from its foreign projection (set below); others flat.
                let r = if matches!(c.kind, CurveKind::Xccy { .. }) {
                    0.0
                } else {
                    r0
                };
                dates
                    .iter()
                    .map(|d| -r * curve_time(as_of, *d))
                    .collect::<Vec<_>>()
            }
            Shape::Steps { step_dates } => vec![r0; 1 + step_dates.len()],
        };
        let size = main.len() + c.turns.len();
        x0.extend(main);
        x0.extend(std::iter::repeat_n(0.0, c.turns.len()));
        if size != members[k].len() {
            return input("the system is not square");
        }
        blocks.push(Block {
            shape,
            jumps,
            turns: c.turns.clone(),
            deps: deps_of[k].clone(),
            offset,
            size,
            instruments: members[k].clone(),
        });
        offset += size;
    }
    let sys = System {
        as_of,
        blocks,
        insts,
        n: offset,
        spreads,
    };
    let mut x = x0;
    for b in 0..sys.blocks.len() {
        if let CurveKind::Xccy { .. } = curves[b].kind {
            let dep = sys.blocks[b].deps[0];
            let fp = sys.blocks[dep].build(as_of, &x);
            if let Shape::Pillars { dates, .. } = &sys.blocks[b].shape {
                let off = sys.blocks[b].offset;
                for (i, d) in dates.iter().enumerate() {
                    x[off + i] = fp.discount(*d)?.ln();
                }
            }
        }
        sys.solve_block(&mut x, b)?;
    }
    let r = sys.all_residuals(&x)?;
    let worst = r.iter().fold(0.0f64, |m, v| m.max(v.abs()));
    if !worst.is_finite() || worst > GOAL {
        return Err(no_convergence());
    }
    // IFT Jacobian, block by block (exact zeros across blocks, ruling F-25).
    let a = sys.drdx(&x)?;
    let m = sys.insts.len();
    let curves_built = sys.built(&x, sys.blocks.len() - 1);
    let mut dq = vec![0.0; m];
    for j in 0..m {
        dq[j] = match sys.insts[j].dq {
            Dq::Constant(v) => v,
            Dq::XccyAnnuity => {
                let Model::Xccy(dates) = &sys.insts[j].model else {
                    unreachable!()
                };
                let own = &curves_built[sys.insts[j].curve];
                let mut s = 0.0;
                for w in dates.windows(2) {
                    s += (w[1].serial() - w[0].serial()) as f64 / 360.0 * own.discount(w[1])?;
                }
                s
            }
        };
    }
    let mut jac = vec![vec![0.0; m]; sys.n];
    for b in 0..sys.blocks.len() {
        let blk = &sys.blocks[b];
        let rows = &blk.instruments;
        let a_bb: Matrix = rows
            .iter()
            .map(|&i| (0..blk.size).map(|k| a[i][blk.offset + k]).collect())
            .collect();
        for q in 0..m {
            // rhs_i = -(dR_i/dq + sum over earlier unknowns u of A[i][u] J[u][q]).
            let mut rhs = vec![0.0; rows.len()];
            let mut any = false;
            for (ri, &i) in rows.iter().enumerate() {
                let mut v = if i == q { dq[q] } else { 0.0 };
                for u in 0..blk.offset {
                    if a[i][u] != 0.0 && jac[u][q] != 0.0 {
                        v += a[i][u] * jac[u][q];
                    }
                }
                if v != 0.0 {
                    any = true;
                }
                rhs[ri] = -v;
            }
            if !any {
                continue;
            }
            let sol = solve(&a_bb, &rhs).map_err(|_| no_convergence())?;
            for k in 0..blk.size {
                jac[blk.offset + k][q] = sol[k];
            }
        }
    }
    // Labels, outputs.
    let mut unknowns = Vec::new();
    let mut outs = Vec::new();
    let mut turn_factors = Vec::new();
    let mut turn_cols = Vec::new();
    for (b, c) in curves.iter().enumerate() {
        let blk = &sys.blocks[b];
        let xs = &x[blk.offset..blk.offset + blk.size];
        match &blk.shape {
            Shape::Pillars { dates, .. } => {
                for d in dates {
                    unknowns.push(format!("{}:pillar:{}", c.name, label_date(*d)));
                }
                outs.push(CurveOut::Pillars {
                    name: c.name.clone(),
                    pillars: dates.iter().zip(xs).map(|(d, l)| (*d, l.exp())).collect(),
                });
            }
            Shape::Steps { step_dates } => {
                unknowns.push(format!("{}:base", c.name));
                for d in step_dates {
                    unknowns.push(format!("{}:step:{}", c.name, label_date(*d)));
                }
                outs.push(CurveOut::Steps {
                    name: c.name.clone(),
                    base_rate: xs[0],
                    step_rates: xs[1..=step_dates.len()].to_vec(),
                });
            }
        }
        let k = blk.turns.len();
        for (t, d) in blk.turns.iter().enumerate() {
            unknowns.push(format!("{}:turn:{}", c.name, label_date(*d)));
            let l = xs[blk.size - k + t];
            turn_factors.push((c.name.clone(), *d, l.exp()));
            turn_cols.push(blk.offset + blk.size - k + t);
        }
    }
    let turn_sensitivity = turn_cols
        .iter()
        .map(|&u| (0..m).map(|j| a[j][u]).collect())
        .collect();
    Ok(JointResult {
        curves: outs,
        turn_factors,
        unknowns,
        quotes: instruments.iter().map(|i| i.id.clone()).collect(),
        jacobian: jac,
        turn_sensitivity,
        max_repricing_error: worst,
    })
}

impl crate::error::Finite for InstrumentSpec {
    fn is_all_finite(&self) -> bool {
        match self.quote {
            Quote::Ois { rate, .. } => rate.is_finite(),
            Quote::Future {
                price,
                sigma,
                mean_reversion,
                ..
            } => price.is_finite() && sigma.is_finite() && mean_reversion.is_finite(),
            Quote::Projection(q) => q.is_all_finite(),
            Quote::Xccy { spread, .. } => spread.is_finite(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::conventions::overnight;
    use crate::curve::SolveMethod;
    use crate::ois::{OisCurveProblem, OisQuote};

    fn d(s: &str) -> Date {
        Date::parse(s).unwrap()
    }

    fn ois_curve(name: &str, turns: Vec<Date>) -> CurveSpec {
        CurveSpec {
            name: name.into(),
            kind: CurveKind::Ois {
                convention: overnight("SOFR").unwrap(),
                interpolation: Interpolation::LogLinearDf,
                jumps: Vec::new(),
            },
            turns,
        }
    }

    fn ois(id: &str, tenor: (i64, char), rate: f64, turn: bool) -> InstrumentSpec {
        InstrumentSpec {
            id: id.into(),
            curve: "USD-SOFR".into(),
            quote: Quote::Ois { tenor, rate },
            turn,
        }
    }

    const TENORS: [((i64, char), f64); 4] = [
        ((3, 'M'), 0.0425),
        ((1, 'Y'), 0.039),
        ((2, 'Y'), 0.0365),
        ((5, 'Y'), 0.0352),
    ];

    #[test]
    fn one_curve_equals_ois_bootstrap() {
        let as_of = d("2026-11-09");
        let insts: Vec<_> = TENORS
            .iter()
            .enumerate()
            .map(|(k, (t, r))| ois(&format!("Q{k}"), *t, *r, false))
            .collect();
        let r = joint_solve(as_of, &[ois_curve("USD-SOFR", Vec::new())], &insts).unwrap();
        let quotes: Vec<OisQuote> = TENORS
            .iter()
            .map(|(t, r)| OisQuote {
                tenor: *t,
                bid: *r,
                ask: *r,
            })
            .collect();
        let c = overnight("SOFR").unwrap();
        let p = OisCurveProblem::new(&c, as_of, &quotes, Interpolation::LogLinearDf).unwrap();
        let s = p.solve(&p.mids, SolveMethod::Global).unwrap();
        let CurveOut::Pillars { pillars, .. } = &r.curves[0] else {
            panic!()
        };
        for ((date, df), (d2, l)) in pillars.iter().zip(s.dates.iter().zip(&s.logs)) {
            assert_eq!(date, d2);
            assert!((df - l.exp()).abs() < 1e-13);
        }
        assert!(r.max_repricing_error <= 1e-13);
    }

    #[test]
    fn turn_quoted_at_no_turn_par_gives_factor_one_and_exact_zeros() {
        let as_of = d("2026-11-09");
        let base: Vec<_> = TENORS
            .iter()
            .enumerate()
            .map(|(k, (t, r))| ois(&format!("Q{k}"), *t, *r, false))
            .collect();
        let plain = joint_solve(as_of, &[ois_curve("USD-SOFR", Vec::new())], &base).unwrap();
        // The 2M par rate on the curve without a turn.
        let CurveOut::Pillars { pillars, .. } = &plain.curves[0] else {
            panic!()
        };
        let dates: Vec<Date> = pillars.iter().map(|p| p.0).collect();
        let logs: Vec<f64> = pillars.iter().map(|p| p.1.ln()).collect();
        let curve = Curve::from_logs(as_of, Interpolation::LogLinearDf, &dates, &logs);
        let c = overnight("SOFR").unwrap();
        let par = OisLegs::new(&c, as_of, (2, 'M'))
            .unwrap()
            .par_rate(&curve)
            .unwrap();
        let mut insts = base.clone();
        insts.insert(1, ois("TURN", (2, 'M'), par, true));
        let r = joint_solve(
            as_of,
            &[ois_curve("USD-SOFR", vec![d("2026-12-31")])],
            &insts,
        )
        .unwrap();
        assert!((r.turn_factors[0].2 - 1.0).abs() < 1e-12);
        assert_eq!(r.unknowns.last().unwrap(), "USD-SOFR:turn:2026-12-31");
        assert_eq!(r.jacobian.len(), 5);
        assert_eq!(r.turn_sensitivity[0].len(), 5);
    }

    #[test]
    fn later_curve_quotes_have_exact_zero_columns() {
        let as_of = d("2026-11-09");
        let mut insts: Vec<_> = TENORS
            .iter()
            .enumerate()
            .map(|(k, (t, r))| ois(&format!("Q{k}"), *t, *r, false))
            .collect();
        for (k, m) in [24, 60].iter().enumerate() {
            insts.push(InstrumentSpec {
                id: format!("T{k}"),
                curve: "USD-TERM-3M".into(),
                quote: Quote::Projection(ProjectionQuote::Swap {
                    months: *m,
                    rate: 0.038,
                }),
                turn: false,
            });
        }
        let term = CurveSpec {
            name: "USD-TERM-3M".into(),
            kind: CurveKind::Projection {
                discount: "USD-SOFR".into(),
                interpolation: Interpolation::LogLinearDf,
            },
            turns: Vec::new(),
        };
        let r = joint_solve(
            as_of,
            &[ois_curve("USD-SOFR", Vec::new()), term.clone()],
            &insts,
        )
        .unwrap();
        for row in &r.jacobian[..4] {
            assert!(row[4..].iter().all(|v| *v == 0.0));
        }
        assert!(r.jacobian[4][..4].iter().any(|v| *v != 0.0));
        // Order matters: a curve may not name a later one.
        let e = joint_solve(as_of, &[term, ois_curve("USD-SOFR", Vec::new())], &insts).unwrap_err();
        assert_eq!(e.code, "E_INPUT");
    }
}
