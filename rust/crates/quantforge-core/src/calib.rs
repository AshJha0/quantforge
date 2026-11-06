//! Calibration core (`least-squares.md`). Every model is a residual vector, so the objective is
//! always `sum r^2`, with regularisation as further rows.
use crate::error::{Result, fail};
use crate::linalg::{Matrix, solve};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Model {
    Linear,
    Exponential,
    NelsonSiegel,
    Rosenbrock,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Method {
    GaussNewton,
    LevenbergMarquardt,
    Bfgs,
}

#[derive(Debug, Clone)]
pub struct FitInputs {
    pub model: Model,
    pub x: Vec<f64>,
    pub y: Vec<f64>,
    pub start: Vec<f64>,
    pub method: Method,
    pub weights: Option<Vec<f64>>,
    pub regularisation: f64,
    pub prior: Option<Vec<f64>>,
    pub lower: Option<Vec<f64>>,
    pub upper: Option<Vec<f64>>,
    pub max_iter: i64,
}

#[derive(Debug, Clone)]
pub struct Fit {
    pub parameters: Vec<f64>,
    pub objective: f64,
    pub iterations: i64,
    pub status: &'static str,
    pub residuals: Vec<f64>,
}

fn value(model: Model, x: f64, p: &[f64]) -> f64 {
    match model {
        Model::Linear => p[0] + p[1] * x,
        Model::Exponential => p[0] * (-p[1] * x).exp(),
        Model::NelsonSiegel => {
            let z = x / p[3];
            let e = if z == 0.0 {
                1.0
            } else {
                (1.0 - (-z).exp()) / z
            };
            p[0] + p[1] * e + p[2] * (e - (-z).exp())
        }
        Model::Rosenbrock => 0.0,
    }
}

struct Problem<'a> {
    i: &'a FitInputs,
    weights: Vec<f64>,
    prior: Vec<f64>,
}

impl Problem<'_> {
    fn residuals(&self, p: &[f64]) -> Vec<f64> {
        let i = self.i;
        let mut r: Vec<f64> = if i.model == Model::Rosenbrock {
            vec![1.0 - p[0], 10.0 * (p[1] - p[0] * p[0])]
        } else {
            (0..i.x.len())
                .map(|k| self.weights[k].sqrt() * (value(i.model, i.x[k], p) - i.y[k]))
                .collect()
        };
        if i.regularisation > 0.0 {
            let s = i.regularisation.sqrt();
            r.extend(p.iter().zip(&self.prior).map(|(a, b)| s * (a - b)));
        }
        r
    }

    fn objective(&self, p: &[f64]) -> f64 {
        self.residuals(p).iter().map(|v| v * v).sum()
    }

    /// Central differences; column `k` is `dr/dp_k`.
    fn jacobian(&self, p: &[f64]) -> Matrix {
        let m = self.residuals(p).len();
        let mut j = vec![vec![0.0; p.len()]; m];
        for k in 0..p.len() {
            let h = 1e-6 * (1.0 + p[k].abs());
            let (mut up, mut down) = (p.to_vec(), p.to_vec());
            up[k] += h;
            down[k] -= h;
            let (a, b) = (self.residuals(&up), self.residuals(&down));
            for i in 0..m {
                j[i][k] = (a[i] - b[i]) / (2.0 * h);
            }
        }
        j
    }
}

fn normal_equations(j: &Matrix, r: &[f64]) -> (Matrix, Vec<f64>) {
    let n = j.first().map_or(0, Vec::len);
    let mut h = vec![vec![0.0; n]; n];
    let mut g = vec![0.0; n];
    for (row, ri) in j.iter().zip(r) {
        for a in 0..n {
            g[a] += row[a] * ri;
            for b in 0..n {
                h[a][b] += row[a] * row[b];
            }
        }
    }
    (h, g)
}

fn norm(v: &[f64]) -> f64 {
    v.iter().map(|x| x * x).sum::<f64>().sqrt()
}

const GRADIENT_TOL: f64 = 1e-8;
const STEP_TOL: f64 = 1e-12;

fn small_step(step: &[f64], p: &[f64]) -> bool {
    norm(step) <= STEP_TOL * (1.0 + norm(p))
}

fn no_convergence<T>() -> Result<T> {
    fail("E_NO_CONVERGENCE", "max_iter reached")
}

fn gauss_newton(
    q: &Problem,
    mut p: Vec<f64>,
    max_iter: i64,
) -> Result<(Vec<f64>, i64, &'static str)> {
    for it in 1..=max_iter {
        let r = q.residuals(&p);
        let (h, g) = normal_equations(&q.jacobian(&p), &r);
        if 2.0 * norm(&g) <= GRADIENT_TOL {
            return Ok((p, it - 1, "GRADIENT"));
        }
        let step = solve(&h, &g.iter().map(|v| -v).collect::<Vec<_>>())?;
        let f0 = q.objective(&p);
        let mut scale = 1.0;
        let mut taken = None;
        for _ in 0..60 {
            let t: Vec<f64> = p.iter().zip(&step).map(|(a, s)| a + scale * s).collect();
            if q.objective(&t) < f0 {
                taken = Some(t);
                break;
            }
            scale /= 2.0;
        }
        let Some(t) = taken else {
            return Ok((p, it, "STEP"));
        };
        let moved: Vec<f64> = t.iter().zip(&p).map(|(a, b)| a - b).collect();
        p = t;
        if small_step(&moved, &p) {
            return Ok((p, it, "STEP"));
        }
    }
    no_convergence()
}

fn levenberg_marquardt(
    q: &Problem,
    p: Vec<f64>,
    lower: &[f64],
    upper: &[f64],
    max_iter: i64,
) -> Result<(Vec<f64>, i64, &'static str)> {
    let box_of = |v: &mut Vec<f64>| {
        for k in 0..v.len() {
            v[k] = v[k].max(lower[k]).min(upper[k]);
        }
    };
    let mut p = p;
    box_of(&mut p);
    let mut mu = 1e-3;
    let mut f0 = q.objective(&p);
    for it in 1..=max_iter {
        let r = q.residuals(&p);
        let (h, g) = normal_equations(&q.jacobian(&p), &r);
        // A bound with the gradient pushing outwards holds its parameter fixed.
        let free: Vec<usize> = (0..p.len())
            .filter(|&k| !((p[k] <= lower[k] && g[k] > 0.0) || (p[k] >= upper[k] && g[k] < 0.0)))
            .collect();
        let projected: Vec<f64> = free.iter().map(|&k| g[k]).collect();
        if 2.0 * norm(&projected) <= GRADIENT_TOL {
            return Ok((p, it - 1, "GRADIENT"));
        }
        let n = free.len();
        let mut a = vec![vec![0.0; n]; n];
        for (x, &i) in free.iter().enumerate() {
            for (y, &j) in free.iter().enumerate() {
                a[x][y] = h[i][j];
            }
            a[x][x] += mu * h[i][i].max(1e-12);
        }
        let rhs: Vec<f64> = projected.iter().map(|v| -v).collect();
        let Ok(step) = solve(&a, &rhs) else {
            mu *= 4.0;
            continue;
        };
        let mut t = p.clone();
        for (s, &k) in step.iter().zip(&free) {
            t[k] += s;
        }
        box_of(&mut t);
        let moved: Vec<f64> = t.iter().zip(&p).map(|(a, b)| a - b).collect();
        let f1 = q.objective(&t);
        if f1 < f0 {
            p = t;
            f0 = f1;
            mu = (mu / 3.0).max(1e-15);
            if small_step(&moved, &p) {
                return Ok((p, it, "STEP"));
            }
        } else {
            if small_step(&moved, &p) {
                return Ok((p, it, "STEP"));
            }
            mu *= 4.0;
        }
    }
    no_convergence()
}

fn bfgs(q: &Problem, mut p: Vec<f64>, max_iter: i64) -> Result<(Vec<f64>, i64, &'static str)> {
    let n = p.len();
    let identity = || -> Matrix {
        (0..n)
            .map(|i| (0..n).map(|j| f64::from(u8::from(i == j))).collect())
            .collect()
    };
    let gradient = |p: &[f64]| -> Vec<f64> {
        let (_, g) = normal_equations(&q.jacobian(p), &q.residuals(p));
        g.iter().map(|v| 2.0 * v).collect()
    };
    let mut h = identity();
    let mut g = gradient(&p);
    let mut f0 = q.objective(&p);
    for it in 1..=max_iter {
        if norm(&g) <= GRADIENT_TOL {
            return Ok((p, it - 1, "GRADIENT"));
        }
        let mut d: Vec<f64> = (0..n)
            .map(|i| -(0..n).map(|j| h[i][j] * g[j]).sum::<f64>())
            .collect();
        let mut slope: f64 = d.iter().zip(&g).map(|(a, b)| a * b).sum();
        if slope >= 0.0 {
            h = identity();
            d = g.iter().map(|v| -v).collect();
            slope = -norm(&g).powi(2);
        }
        let mut scale = 1.0;
        let mut taken = None;
        for _ in 0..80 {
            let t: Vec<f64> = p.iter().zip(&d).map(|(a, s)| a + scale * s).collect();
            let f1 = q.objective(&t);
            if f1 <= f0 + 1e-4 * scale * slope {
                taken = Some((t, f1));
                break;
            }
            scale /= 2.0;
        }
        let Some((t, f1)) = taken else {
            return Ok((p, it, "STEP"));
        };
        let g1 = gradient(&t);
        let s: Vec<f64> = t.iter().zip(&p).map(|(a, b)| a - b).collect();
        let y: Vec<f64> = g1.iter().zip(&g).map(|(a, b)| a - b).collect();
        let sy: f64 = s.iter().zip(&y).map(|(a, b)| a * b).sum();
        if sy > 1e-14 * norm(&s) * norm(&y) {
            let hy: Vec<f64> = (0..n)
                .map(|i| (0..n).map(|j| h[i][j] * y[j]).sum())
                .collect();
            let yhy: f64 = y.iter().zip(&hy).map(|(a, b)| a * b).sum();
            for i in 0..n {
                for j in 0..n {
                    h[i][j] +=
                        (1.0 + yhy / sy) * s[i] * s[j] / sy - (hy[i] * s[j] + s[i] * hy[j]) / sy;
                }
            }
        }
        p = t;
        g = g1;
        f0 = f1;
        if small_step(&s, &p) {
            return Ok((p, it, "STEP"));
        }
    }
    no_convergence()
}

fn parameter_count(m: Model) -> usize {
    match m {
        Model::Linear | Model::Exponential | Model::Rosenbrock => 2,
        Model::NelsonSiegel => 4,
    }
}

pub fn fit(i: &FitInputs) -> Result<Fit> {
    let n = parameter_count(i.model);
    let rosenbrock = i.model == Model::Rosenbrock;
    let weights = match (&i.weights, rosenbrock) {
        (Some(w), false) => w.clone(),
        _ => vec![1.0; i.x.len()],
    };
    let prior = i.prior.clone().unwrap_or_else(|| vec![0.0; n]);
    let lower = i
        .lower
        .clone()
        .unwrap_or_else(|| vec![f64::NEG_INFINITY; n]);
    let upper = i.upper.clone().unwrap_or_else(|| vec![f64::INFINITY; n]);
    if i.x.len() != i.y.len()
        || i.start.len() != n
        || weights.len() != i.x.len()
        || prior.len() != n
        || lower.len() != n
        || upper.len() != n
    {
        return fail("E_INPUT", "an input has the wrong length");
    }
    if (i.lower.is_some() || i.upper.is_some()) && i.method != Method::LevenbergMarquardt {
        return fail("E_INPUT", "bounds need LEVENBERG_MARQUARDT");
    }
    if lower.iter().zip(&upper).any(|(a, b)| a > b) {
        return fail("E_INPUT", "lower is above upper");
    }
    if i.max_iter < 1 {
        return fail("E_INPUT", "max_iter must be at least 1");
    }
    if weights.iter().any(|w| *w < 0.0) {
        return fail("E_DOMAIN", "a weight is negative");
    }
    if i.regularisation < 0.0 {
        return fail("E_DOMAIN", "regularisation is negative");
    }
    let q = Problem { i, weights, prior };
    let p = i.start.clone();
    let (parameters, iterations, status) = match i.method {
        Method::GaussNewton => gauss_newton(&q, p, i.max_iter)?,
        Method::LevenbergMarquardt => levenberg_marquardt(&q, p, &lower, &upper, i.max_iter)?,
        Method::Bfgs => bfgs(&q, p, i.max_iter)?,
    };
    Ok(Fit {
        objective: q.objective(&parameters),
        residuals: q.residuals(&parameters),
        parameters,
        iterations,
        status,
    })
}

/// Returns `(index, side, distance)` for each breach.
pub fn check_bid_ask(
    fitted: &[f64],
    bid: &[f64],
    ask: &[f64],
) -> Result<Vec<(i64, &'static str, f64)>> {
    if fitted.len() != bid.len() || fitted.len() != ask.len() {
        return fail("E_INPUT", "lengths differ");
    }
    if bid.iter().zip(ask).any(|(b, a)| b > a) {
        return fail("E_INPUT", "bid is above ask");
    }
    let mut out = Vec::new();
    for k in 0..fitted.len() {
        if fitted[k] < bid[k] {
            out.push((k as i64, "BID", bid[k] - fitted[k]));
        } else if fitted[k] > ask[k] {
            out.push((k as i64, "ASK", fitted[k] - ask[k]));
        }
    }
    Ok(out)
}
