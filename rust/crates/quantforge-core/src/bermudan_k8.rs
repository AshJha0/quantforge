//! K-8 (stage K; rulings KR-8 and KR-18): the `CN_RANNACHER_SMOOTHED` Bermudan scheme
//! (`specifications/06-risk/bermudan-ladder-k8.md`, version 0.2.0), a line-by-line port of the Java
//! build's `BermudanK8.java`, which ports `python/quantforge_core/bermudan_k8.py`. Same state, grid,
//! knots and exercise value as the pinned G-18 scheme, with three changes: the scheme carries
//! `U = V exp(-int_0^t alpha)`, so the operator has no curve term and is constant in time;
//! Crank-Nicolson stepping with the first two steps after the maturity payoff and after each exercise
//! date each replaced by two implicit half steps; and the exercise `max` applied as a hat-weighted
//! average with an end correction.
//!
//! The ladder is the exact derivative of this discrete scheme in tangent mode: every quantity is a
//! vector whose entry 0 is the value and entries 1.. its derivatives with respect to the log discount
//! factors of the curve nodes, the mean reversion and the volatility. Divisions by 3, 6 and 12 stay
//! divisions, and adding a constant to a dual touches the value only (`program/K8_PORT_NOTE.md`).
use crate::error::Result;
use crate::shortrate::{FdGrid, HwCurve, SwapLeg, check_bermudan};

/// The `method` value of this scheme.
pub const METHOD: &str = "CN_RANNACHER_SMOOTHED";
/// Steps replaced by two implicit half steps each after every exercise date (KR-18 c).
pub const START_UP_STEPS: i64 = 2;

/// A dual number: entry 0 the value, entries 1.. the tangents.
pub type Dual = Vec<f64>;

pub fn mul(u: &[f64], v: &[f64]) -> Dual {
    let mut o = vec![0.0; u.len()];
    o[0] = u[0] * v[0];
    for c in 1..o.len() {
        o[c] = u[0] * v[c] + v[0] * u[c];
    }
    o
}

pub fn div(u: &[f64], v: &[f64]) -> Dual {
    let mut o = vec![0.0; u.len()];
    let q = u[0] / v[0];
    o[0] = q;
    for c in 1..o.len() {
        o[c] = (u[c] - q * v[c]) / v[0];
    }
    o
}

pub fn add(u: &[f64], v: &[f64]) -> Dual {
    u.iter().zip(v).map(|(a, b)| a + b).collect()
}

pub fn sub(u: &[f64], v: &[f64]) -> Dual {
    u.iter().zip(v).map(|(a, b)| a - b).collect()
}

pub fn scale(k: f64, u: &[f64]) -> Dual {
    u.iter().map(|a| k * a).collect()
}

fn func(u: &[f64], value: f64, slope: f64) -> Dual {
    let mut o: Dual = u.iter().map(|a| slope * a).collect();
    o[0] = value;
    o
}

fn dexp(u: &[f64]) -> Dual {
    let e = u[0].exp();
    func(u, e, e)
}

fn dexpm1(u: &[f64]) -> Dual {
    func(u, u[0].exp_m1(), u[0].exp())
}

fn dsqrt(u: &[f64]) -> Dual {
    let s = u[0].sqrt();
    func(u, s, 0.5 / s)
}

fn neg(u: &[f64]) -> Dual {
    scale(-1.0, u)
}

fn div_scalar(u: &[f64], den: f64) -> Dual {
    u.iter().map(|a| a / den).collect()
}

/// `u + c` for a dual `u` and a constant `c`.
fn plus(u: &[f64], c: f64) -> Dual {
    let mut o = u.to_vec();
    o[0] += c;
    o
}

/// Log-linear curve on dual logs (G-3).
struct Curve {
    nodes: Vec<f64>,
    logs: Vec<Dual>,
}

impl Curve {
    fn log_discount(&self, t: f64) -> Dual {
        let w = self.logs[0].len();
        if t <= 0.0 {
            return vec![0.0; w];
        }
        let right = self.nodes.partition_point(|n| *n <= t);
        let j = (right - 1).min(self.nodes.len() - 2);
        let wt = (t - self.nodes[j]) / (self.nodes[j + 1] - self.nodes[j]);
        (0..w)
            .map(|c| self.logs[j][c] + (self.logs[j + 1][c] - self.logs[j][c]) * wt)
            .collect()
    }
}

struct Model {
    curve: Curve,
    a: Dual,
    s2: Dual,
}

impl Model {
    fn big_b(&self, tau: f64) -> Dual {
        neg(&div(&dexpm1(&scale(tau, &neg(&self.a))), &self.a))
    }
}

/// Exercise value at `t` times `D(t) = exp(-int_0^t alpha)` (spec step 3); no forward rate.
fn exercise(m: &Model, t: f64, xs: &[Dual], times: &[f64], k: f64, phi: f64) -> Vec<Dual> {
    let after: Vec<f64> = times.iter().copied().filter(|s| *s > t).collect();
    let (n, w) = (xs.len(), xs[0].len());
    let e1 = dexpm1(&scale(t, &neg(&m.a)));
    let e2 = dexpm1(&scale(t, &scale(-2.0, &m.a)));
    let big_i = plus(
        &sub(&scale(2.0, &div(&e1, &m.a)), &div(&e2, &scale(2.0, &m.a))),
        t,
    );
    let c2 = div(&m.s2, &scale(2.0, &mul(&m.a, &m.a)));
    let c4 = div(&m.s2, &scale(4.0, &m.a));
    let lead = dexp(&sub(&m.curve.log_discount(t), &mul(&c2, &big_i)));
    let mut fixed = vec![vec![0.0; w]; n];
    let mut last = fixed.clone();
    for (q, s) in after.iter().enumerate() {
        let tau = if q == 0 { s - t } else { s - after[q - 1] };
        let b = m.big_b(s - t);
        let drift = sub(
            &mul(&c2, &add(&big_i, &mul(&b, &mul(&e1, &e1)))),
            &mul(&c4, &mul(&e2, &mul(&b, &b))),
        );
        let head = sub(&m.curve.log_discount(*s), &drift);
        let mut p = Vec::with_capacity(n);
        for i in 0..n {
            let pi = dexp(&sub(&head, &mul(&b, &xs[i])));
            fixed[i] = add(&fixed[i], &scale(tau, &pi));
            p.push(pi);
        }
        last = p;
    }
    (0..n)
        .map(|i| scale(phi, &sub(&sub(&lead, &last[i]), &scale(k, &fixed[i]))))
        .collect()
}

/// `int_0^1 (1 - u) max(p + (q - p) u, 0) du`: half of the hat-weighted average of the positive part.
pub fn hat_part(p: &[f64], q: &[f64]) -> Dual {
    let (pa, qb) = (p[0], q[0]);
    if pa >= 0.0 && qb >= 0.0 {
        return add(&div_scalar(p, 3.0), &div_scalar(q, 6.0));
    }
    if pa > 0.0 && qb < 0.0 {
        let dd = sub(p, q);
        let tt = div(&mul(p, p), &scale(2.0, &dd));
        return sub(&tt, &div_scalar(&mul(&tt, &div(p, &dd)), 3.0));
    }
    if pa < 0.0 && qb > 0.0 {
        let r = div(q, &sub(q, p));
        return div_scalar(&mul(q, &mul(&r, &r)), 6.0);
    }
    vec![0.0; p.len()]
}

/// `max(V, E)` at an exercise date as a second-order smoothing (KR-18 b, spec step 5).
pub fn smoothed_max(v: &[Dual], e: &[Dual]) -> Vec<Dual> {
    let (n, w) = (v.len(), v[0].len());
    let f: Vec<Dual> = (0..n).map(|i| sub(&v[i], &e[i])).collect();
    let mut hh = Vec::with_capacity(n);
    let mut d2 = vec![vec![0.0; w]; n];
    for i in 0..n {
        let before = if i > 0 {
            f[i - 1].clone()
        } else {
            sub(&scale(2.0, &f[0]), &f[1])
        };
        let after = if i < n - 1 {
            f[i + 1].clone()
        } else {
            sub(&scale(2.0, &f[n - 1]), &f[n - 2])
        };
        hh.push(add(&hat_part(&f[i], &before), &hat_part(&f[i], &after)));
        if i > 0 && i < n - 1 {
            d2[i] = add(&sub(&f[i - 1], &scale(2.0, &f[i])), &f[i + 1]);
        }
    }
    for j in 0..n - 1 {
        let (fa, fb) = (f[j][0], f[j + 1][0]);
        if !((fa > 0.0 && fb < 0.0) || (fa < 0.0 && fb > 0.0)) {
            continue;
        }
        let (pos, ng) = if fa > 0.0 { (j, j + 1) } else { (j + 1, j) };
        let rho = div(&f[pos], &sub(&f[pos], &f[ng])); // the part of the cell where V > E
        let rest = plus(&neg(&rho), 1.0);
        let gg = div_scalar(
            &mul(&mul(&rho, &rest), &plus(&scale(2.0, &rho), -1.0)),
            12.0,
        );
        let corr = mul(&gg, &scale(0.5, &add(&d2[j], &d2[j + 1])));
        hh[pos] = sub(&hh[pos], &mul(&rest, &corr));
        hh[ng] = sub(&hh[ng], &mul(&rho, &corr));
    }
    (0..n)
        .map(|i| {
            let mut o = hh[i].clone();
            if i > 0 && i < n - 1 {
                o = sub(
                    &o,
                    &div_scalar(&add(&sub(&hh[i - 1], &scale(2.0, &hh[i])), &hh[i + 1]), 6.0),
                );
            }
            add(&e[i], &o)
        })
        .collect()
}

/// Value-only elimination, then every column with the same multipliers and pivots.
fn solve(lower: &[Dual], diag: &[Dual], upper: &[Dual], rhs: &[Dual]) -> Vec<Dual> {
    let (n, w) = (diag.len(), rhs[0].len());
    let mut cc = vec![0.0; n];
    let mut den = vec![0.0; n];
    den[0] = diag[0][0];
    cc[0] = upper[0][0] / den[0];
    for i in 1..n {
        den[i] = diag[i][0] - lower[i][0] * cc[i - 1];
        cc[i] = upper[i][0] / den[i];
    }
    let mut y0 = vec![0.0; n];
    y0[0] = rhs[0][0] / den[0];
    for i in 1..n {
        y0[i] = (rhs[i][0] - lower[i][0] * y0[i - 1]) / den[i];
    }
    for i in (0..n - 1).rev() {
        y0[i] -= cc[i] * y0[i + 1];
    }
    let mut full = rhs.to_vec();
    for i in 0..n {
        for k in 1..w {
            full[i][k] -= diag[i][k] * y0[i];
        }
    }
    for i in 1..n {
        for k in 1..w {
            full[i][k] -= lower[i][k] * y0[i - 1];
        }
    }
    for i in 0..n - 1 {
        for k in 1..w {
            full[i][k] -= upper[i][k] * y0[i + 1];
        }
    }
    let mut out = vec![vec![0.0; w]; n];
    for k in 1..w {
        out[0][k] = full[0][k] / den[0];
    }
    for i in 1..n {
        for k in 1..w {
            out[i][k] = (full[i][k] - lower[i][0] * out[i - 1][k]) / den[i];
        }
    }
    for i in (0..n - 1).rev() {
        for k in 1..w {
            out[i][k] -= cc[i] * out[i + 1][k];
        }
    }
    for i in 0..n {
        out[i][0] = y0[i];
    }
    out
}

/// Rows of `A = -L` at the interior nodes, before the boundary substitution; constant in time (KR-18 a).
struct Operator {
    lower: Vec<Dual>,
    upper: Vec<Dual>,
    diag: Vec<Dual>,
}

impl Operator {
    fn new(m: &Model, xs: &[Dual], dx: &[f64]) -> Operator {
        let n = xs.len() - 2;
        let diff = div(&m.s2, &scale(2.0, &mul(dx, dx)));
        let two_dx = scale(2.0, dx);
        let mut op = Operator {
            lower: Vec::with_capacity(n),
            upper: Vec::with_capacity(n),
            diag: Vec::with_capacity(n),
        };
        for inner in &xs[1..=n] {
            let conv = div(&mul(&m.a, inner), &two_dx);
            op.lower.push(neg(&add(&diff, &conv)));
            op.upper.push(neg(&sub(&diff, &conv)));
            op.diag.push(add(&scale(2.0, &diff), inner));
        }
        op
    }

    /// Solves `(I + w A) y = rhs` on the interior with linear extrapolation at both ends.
    fn implicit(&self, w: f64, rhs: &[Dual]) -> Vec<Dual> {
        let n = rhs.len();
        let mut lower: Vec<Dual> = self.lower.iter().map(|r| scale(w, r)).collect();
        let mut upper: Vec<Dual> = self.upper.iter().map(|r| scale(w, r)).collect();
        let mut diag: Vec<Dual> = self.diag.iter().map(|r| plus(&scale(w, r), 1.0)).collect();
        diag[0] = add(&diag[0], &scale(2.0, &lower[0]));
        upper[0] = sub(&upper[0], &lower[0]);
        lower[n - 1] = sub(&lower[n - 1], &upper[n - 1]);
        diag[n - 1] = add(&diag[n - 1], &scale(2.0, &upper[n - 1]));
        let y = solve(&lower, &diag, &upper, rhs);
        let mut out = Vec::with_capacity(n + 2);
        out.push(sub(&scale(2.0, &y[0]), &y[1]));
        let last = sub(&scale(2.0, &y[n - 1]), &y[n - 2]);
        out.extend(y);
        out.push(last);
        out
    }

    /// `(I - w A) v` at the interior nodes.
    fn explicit(&self, w: f64, v: &[Dual]) -> Vec<Dual> {
        (0..v.len() - 2)
            .map(|i| {
                let lv = add(
                    &add(&mul(&self.lower[i], &v[i]), &mul(&self.diag[i], &v[i + 1])),
                    &mul(&self.upper[i], &v[i + 2]),
                );
                sub(&v[i + 1], &scale(w, &lv))
            })
            .collect()
    }
}

/// Price per unit notional (entry 0) and, with `tangents`, its derivatives with respect to the log
/// discount factors of the curve pillars, `a` and `sigma` (entries 1..). Inputs are not checked here.
#[allow(clippy::too_many_arguments)]
pub fn scheme(
    times: &[f64],
    dfs: &[f64],
    a: f64,
    sigma: f64,
    payment_times: &[f64],
    k: f64,
    payer: bool,
    exercise_times: &[f64],
    grid: FdGrid,
    tangents: bool,
) -> Dual {
    let n = times.len();
    let w = if tangents { n + 3 } else { 1 };
    let mut logs = vec![vec![0.0; w]; n + 1];
    for j in 0..n {
        logs[j + 1][0] = dfs[j].ln();
    }
    let mut ad = vec![0.0; w];
    let mut sd = vec![0.0; w];
    ad[0] = a;
    sd[0] = sigma;
    if tangents {
        for j in 0..n {
            logs[j + 1][j + 1] = 1.0;
        }
        ad[n + 1] = 1.0;
        sd[n + 2] = 1.0;
    }
    let mut nodes = vec![0.0];
    nodes.extend_from_slice(times);
    let s2 = mul(&sd, &sd);
    let m = Model {
        curve: Curve { nodes, logs },
        a: ad,
        s2,
    };
    let phi = if payer { 1.0 } else { -1.0 };
    let tm = exercise_times[exercise_times.len() - 1];
    let gq = neg(&div(&dexpm1(&scale(-2.0 * tm, &m.a)), &scale(2.0, &m.a)));
    let sx = mul(&sd, &dsqrt(&gq));
    let half_width = scale(grid.width, &sx);
    let nx = usize::try_from(grid.nx).unwrap_or(5);
    let dx = div_scalar(&scale(2.0, &half_width), (grid.nx - 1) as f64);
    let xs: Vec<Dual> = (0..nx)
        .map(|i| add(&neg(&half_width), &scale(i as f64, &dx)))
        .collect();
    let op = Operator::new(&m, &xs, &dx);
    let mut v = smoothed_max(
        &vec![vec![0.0; w]; nx],
        &exercise(&m, tm, &xs, payment_times, k, phi),
    );
    let mut knots = vec![0.0];
    knots.extend_from_slice(exercise_times);
    for kk in (1..knots.len()).rev() {
        let (t_hi, t_lo) = (knots[kk], knots[kk - 1]);
        let steps = ((grid.steps_per_year as f64 * (t_hi - t_lo)).ceil() as i64).max(1);
        let half = (t_hi - t_lo) / steps as f64 / 2.0;
        for j in (0..steps).rev() {
            if j >= steps - START_UP_STEPS {
                // Rannacher start-up: two implicit half steps
                v = op.implicit(half, &v[1..nx - 1]);
                v = op.implicit(half, &v[1..nx - 1]);
            } else {
                v = op.implicit(half, &op.explicit(half, &v));
            }
        }
        if kk - 1 > 0 {
            v = smoothed_max(&v, &exercise(&m, t_lo, &xs, payment_times, k, phi));
        }
    }
    v.swap_remove(nx / 2)
}

/// Ladder of `CN_RANNACHER_SMOOTHED`: the price and its derivatives, scaled by the notional.
#[derive(Debug, Clone)]
pub struct Ladder {
    pub price: f64,
    pub d_discount_factors: Vec<f64>,
    pub d_mean_reversion: f64,
    pub d_sigma: f64,
}

/// `rates.shortrate.bermudan_swaption` with `method` `CN_RANNACHER_SMOOTHED`: the G-18 checks in the
/// G-18 order (schedule before grid, HR-66), then the scheme. `curve` is built from `times`, `dfs`.
#[allow(clippy::too_many_arguments)]
pub fn price(
    curve: &HwCurve,
    times: &[f64],
    dfs: &[f64],
    a: f64,
    sigma: f64,
    swap: &SwapLeg,
    exercise: &[f64],
    grid: FdGrid,
) -> Result<f64> {
    check_bermudan(curve, a, sigma, swap, exercise, grid)?;
    let r = scheme(
        times,
        dfs,
        a,
        sigma,
        swap.pay,
        swap.fixed_rate,
        swap.payer,
        exercise,
        grid,
        false,
    );
    Ok(swap.notional * r[0])
}

/// `rates.shortrate.bermudan_ladder` with `method` `CN_RANNACHER_SMOOTHED`.
#[allow(clippy::too_many_arguments)]
pub fn ladder(
    curve: &HwCurve,
    times: &[f64],
    dfs: &[f64],
    a: f64,
    sigma: f64,
    swap: &SwapLeg,
    exercise: &[f64],
    grid: FdGrid,
) -> Result<Ladder> {
    check_bermudan(curve, a, sigma, swap, exercise, grid)?;
    let r = scheme(
        times,
        dfs,
        a,
        sigma,
        swap.pay,
        swap.fixed_rate,
        swap.payer,
        exercise,
        grid,
        true,
    );
    let n = times.len();
    let notional = swap.notional;
    Ok(Ladder {
        price: notional * r[0],
        d_discount_factors: (0..n).map(|j| notional * r[1 + j] / dfs[j]).collect(),
        d_mean_reversion: notional * r[n + 1],
        d_sigma: notional * r[n + 2],
    })
}

#[cfg(test)]
#[path = "bermudan_k8_tests.rs"]
mod tests;
