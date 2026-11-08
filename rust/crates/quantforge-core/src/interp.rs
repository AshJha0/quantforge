//! Interpolation (`interpolation.md`).
use crate::error::{Result, fail};
use crate::linalg::{Matrix, solve};

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Method {
    Linear,
    LogLinear,
    CubicNatural,
    CubicClamped { start: f64, end: f64 },
    CubicNotAKnot,
    Pchip,
    Tension(f64),
}

impl Method {
    fn min_knots(self) -> usize {
        match self {
            Method::Linear | Method::LogLinear | Method::CubicClamped { .. } | Method::Pchip => 2,
            Method::CubicNatural | Method::Tension(_) => 3,
            Method::CubicNotAKnot => 4,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Evaluated {
    pub values: Vec<f64>,
    /// Absent for `linear` and `log_linear`.
    pub derivatives: Option<Vec<f64>>,
}

fn increasing(x: &[f64]) -> bool {
    x.windows(2).all(|w| w[1] > w[0])
}

fn interval(x: &[f64], t: f64) -> usize {
    let n = x.len() - 1;
    x.partition_point(|k| *k <= t).saturating_sub(1).min(n - 1)
}

/// Slopes of the C2 cubic through the data, from the end conditions.
fn spline_slopes(x: &[f64], y: &[f64], method: Method) -> Result<Vec<f64>> {
    let n = x.len();
    let h: Vec<f64> = x.windows(2).map(|w| w[1] - w[0]).collect();
    let d: Vec<f64> = (0..n - 1).map(|i| (y[i + 1] - y[i]) / h[i]).collect();
    let mut a: Matrix = vec![vec![0.0; n]; n];
    let mut b = vec![0.0; n];
    for i in 1..n - 1 {
        a[i][i - 1] = h[i];
        a[i][i] = 2.0 * (h[i - 1] + h[i]);
        a[i][i + 1] = h[i - 1];
        b[i] = 3.0 * (h[i] * d[i - 1] + h[i - 1] * d[i]);
    }
    let l = n - 1;
    match method {
        Method::CubicClamped { start, end } => {
            a[0][0] = 1.0;
            b[0] = start;
            a[l][l] = 1.0;
            b[l] = end;
        }
        Method::CubicNotAKnot => {
            // s''' on interval i is 6 (m_i + m_{i+1} - 2 d_i) / h_i^2.
            let (p, q) = (1.0 / (h[0] * h[0]), 1.0 / (h[1] * h[1]));
            a[0][0] = p;
            a[0][1] = p - q;
            a[0][2] = -q;
            b[0] = 2.0 * (d[0] * p - d[1] * q);
            let (p, q) = (1.0 / (h[l - 2] * h[l - 2]), 1.0 / (h[l - 1] * h[l - 1]));
            a[l][l - 2] = p;
            a[l][l - 1] = p - q;
            a[l][l] = -q;
            b[l] = 2.0 * (d[l - 2] * p - d[l - 1] * q);
        }
        _ => {
            a[0][0] = 2.0;
            a[0][1] = 1.0;
            b[0] = 3.0 * d[0];
            a[l][l - 1] = 1.0;
            a[l][l] = 2.0;
            b[l] = 3.0 * d[l - 1];
        }
    }
    solve(&a, &b)
}

fn pchip_end(h0: f64, h1: f64, d0: f64, d1: f64) -> f64 {
    let m = ((2.0 * h0 + h1) * d0 - h0 * d1) / (h0 + h1);
    let sign = |v: f64| i8::from(v > 0.0) - i8::from(v < 0.0);
    if sign(m) != sign(d0) {
        0.0
    } else if sign(d0) != sign(d1) && m.abs() > 3.0 * d0.abs() {
        3.0 * d0
    } else {
        m
    }
}

fn pchip_slopes(x: &[f64], y: &[f64]) -> Vec<f64> {
    let n = x.len();
    let h: Vec<f64> = x.windows(2).map(|w| w[1] - w[0]).collect();
    let d: Vec<f64> = (0..n - 1).map(|i| (y[i + 1] - y[i]) / h[i]).collect();
    if n == 2 {
        return vec![d[0], d[0]];
    }
    let mut m = vec![0.0; n];
    for i in 1..n - 1 {
        if d[i - 1] != 0.0 && d[i] != 0.0 && (d[i - 1] > 0.0) == (d[i] > 0.0) {
            let w1 = 2.0 * h[i] + h[i - 1];
            let w2 = h[i] + 2.0 * h[i - 1];
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i]);
        }
    }
    m[0] = pchip_end(h[0], h[1], d[0], d[1]);
    m[n - 1] = pchip_end(h[n - 2], h[n - 3], d[n - 2], d[n - 3]);
    m
}

fn hermite(x: &[f64], y: &[f64], m: &[f64], t: f64) -> (f64, f64) {
    let i = interval(x, t);
    let h = x[i + 1] - x[i];
    let u = (t - x[i]) / h;
    let (u2, u3) = (u * u, u * u * u);
    let s = (2.0 * u3 - 3.0 * u2 + 1.0) * y[i]
        + (u3 - 2.0 * u2 + u) * h * m[i]
        + (-2.0 * u3 + 3.0 * u2) * y[i + 1]
        + (u3 - u2) * h * m[i + 1];
    let ds = (6.0 * u2 - 6.0 * u) / h * (y[i] - y[i + 1])
        + (3.0 * u2 - 4.0 * u + 1.0) * m[i]
        + (3.0 * u2 - 2.0 * u) * m[i + 1];
    (s, ds)
}

fn tension_moments(x: &[f64], y: &[f64], p: f64) -> Result<Vec<f64>> {
    let n = x.len();
    let h: Vec<f64> = x.windows(2).map(|w| w[1] - w[0]).collect();
    let d: Vec<f64> = (0..n - 1).map(|i| (y[i + 1] - y[i]) / h[i]).collect();
    let e: Vec<f64> = h.iter().map(|v| 1.0 / v - p / (p * v).sinh()).collect();
    let c: Vec<f64> = h
        .iter()
        .map(|v| p * (p * v).cosh() / (p * v).sinh() - 1.0 / v)
        .collect();
    let k = n - 2;
    let mut a: Matrix = vec![vec![0.0; k]; k];
    let mut b = vec![0.0; k];
    for r in 0..k {
        let i = r + 1;
        a[r][r] = c[i - 1] + c[i];
        if r > 0 {
            a[r][r - 1] = e[i - 1];
        }
        if r + 1 < k {
            a[r][r + 1] = e[i];
        }
        b[r] = p * p * (d[i] - d[i - 1]);
    }
    let inner = solve(&a, &b)?;
    let mut m = vec![0.0; n];
    m[1..n - 1].copy_from_slice(&inner);
    Ok(m)
}

fn tension_eval(x: &[f64], y: &[f64], m: &[f64], p: f64, t: f64) -> (f64, f64) {
    let i = interval(x, t);
    let h = x[i + 1] - x[i];
    let (l, r) = (x[i + 1] - t, t - x[i]);
    let p2 = p * p;
    let den = p2 * (p * h).sinh();
    let (a, b) = (y[i] - m[i] / p2, y[i + 1] - m[i + 1] / p2);
    let s = (m[i] * (p * l).sinh() + m[i + 1] * (p * r).sinh()) / den + a * l / h + b * r / h;
    let ds = p * (-m[i] * (p * l).cosh() + m[i + 1] * (p * r).cosh()) / den + (b - a) / h;
    (s, ds)
}

pub fn evaluate(method: Method, x: &[f64], y: &[f64], at: &[f64]) -> Result<Evaluated> {
    if x.len() != y.len() || x.len() < method.min_knots() {
        return fail("E_INPUT", "x and y differ in length, or too few knots");
    }
    if !increasing(x) {
        return fail("E_INPUT", "x is not strictly increasing");
    }
    match method {
        Method::LogLinear if y.iter().any(|v| *v <= 0.0) => {
            return fail("E_DOMAIN", "log_linear needs positive y");
        }
        Method::Tension(p) if p < 0.0 => return fail("E_DOMAIN", "tension is negative"),
        Method::Tension(p)
            if p > 0.0
                && x.windows(2).any(|w| {
                    let ph = p * (w[1] - w[0]);
                    ph < 0.01 || ph > 500.0
                }) =>
        {
            return fail("E_DOMAIN", "tension times interval out of range");
        }
        _ => {}
    }
    if at.iter().any(|t| *t < x[0] || *t > x[x.len() - 1]) {
        return fail("E_OUT_OF_RANGE", "query point outside the knots");
    }
    let method = if method == Method::Tension(0.0) {
        Method::CubicNatural
    } else {
        method
    };
    let pairs: Vec<(f64, f64)> = match method {
        Method::Linear | Method::LogLinear => {
            let values = at
                .iter()
                .map(|&t| {
                    let i = interval(x, t);
                    let u = (t - x[i]) / (x[i + 1] - x[i]);
                    if method == Method::Linear {
                        y[i] + u * (y[i + 1] - y[i])
                    } else {
                        ((1.0 - u) * y[i].ln() + u * y[i + 1].ln()).exp()
                    }
                })
                .collect();
            return Ok(Evaluated {
                values,
                derivatives: None,
            });
        }
        Method::Pchip => {
            let m = pchip_slopes(x, y);
            at.iter().map(|&t| hermite(x, y, &m, t)).collect()
        }
        Method::Tension(p) => {
            let m = tension_moments(x, y, p)?;
            at.iter().map(|&t| tension_eval(x, y, &m, p, t)).collect()
        }
        _ => {
            let m = spline_slopes(x, y, method)?;
            at.iter().map(|&t| hermite(x, y, &m, t)).collect()
        }
    };
    Ok(Evaluated {
        values: pairs.iter().map(|p| p.0).collect(),
        derivatives: Some(pairs.iter().map(|p| p.1).collect()),
    })
}

/// `g` at `x`, and its integral from 0 to `x`, on one interval.
fn convex_piece(g0: f64, g1: f64, x: f64) -> (f64, f64) {
    let rise = |eta: f64, x: f64| (eta.powi(3) - (eta - x).powi(3)) / (3.0 * eta * eta);
    let fall = |eta: f64, x: f64| (x - eta).powi(3) / (3.0 * (1.0 - eta).powi(2));
    if g0 == 0.0 && g1 == 0.0 {
        (0.0, 0.0)
    } else if (g0 < 0.0 && -g0 / 2.0 <= g1 && g1 <= -2.0 * g0)
        || (g0 > 0.0 && -g0 / 2.0 >= g1 && g1 >= -2.0 * g0)
    {
        let x2 = x * x;
        let x3 = x2 * x;
        (
            g0 * (1.0 - 4.0 * x + 3.0 * x2) + g1 * (-2.0 * x + 3.0 * x2),
            g0 * (x - 2.0 * x2 + x3) + g1 * (-x2 + x3),
        )
    } else if (g0 < 0.0 && g1 > -2.0 * g0) || (g0 > 0.0 && g1 < -2.0 * g0) {
        let eta = (g1 + 2.0 * g0) / (g1 - g0);
        if x <= eta {
            (g0, g0 * x)
        } else {
            (
                g0 + (g1 - g0) * ((x - eta) / (1.0 - eta)).powi(2),
                g0 * x + (g1 - g0) * fall(eta, x),
            )
        }
    } else if (g0 > 0.0 && -g0 / 2.0 < g1 && g1 < 0.0) || (g0 < 0.0 && 0.0 < g1 && g1 < -g0 / 2.0) {
        let eta = 3.0 * g1 / (g1 - g0);
        if x < eta {
            (
                g1 + (g0 - g1) * ((eta - x) / eta).powi(2),
                g1 * x + (g0 - g1) * rise(eta, x),
            )
        } else {
            (g1, g1 * x + (g0 - g1) * eta / 3.0)
        }
    } else {
        let eta = g1 / (g1 + g0);
        let a = -g0 * g1 / (g0 + g1);
        if x < eta {
            (
                a + (g0 - a) * ((eta - x) / eta).powi(2),
                a * x + (g0 - a) * rise(eta, x),
            )
        } else if eta >= 1.0 {
            // g0 = 0: the second piece is empty, and x = 1 takes the node value by continuity.
            (g1, a * x + (g0 - a) * eta / 3.0)
        } else {
            (
                a + (g1 - a) * ((x - eta) / (1.0 - eta)).powi(2),
                a * x + (g0 - a) * eta / 3.0 + (g1 - a) * fall(eta, x),
            )
        }
    }
}

/// Returns forwards and zero rates at `at`.
pub fn monotone_convex(
    t: &[f64],
    r: &[f64],
    at: &[f64],
    positive: bool,
) -> Result<(Vec<f64>, Vec<f64>)> {
    if t.len() != r.len() || t.len() < 2 {
        return fail("E_INPUT", "t and r differ in length, or too few");
    }
    if !increasing(t) || t[0] <= 0.0 {
        return fail("E_INPUT", "t must be strictly increasing and positive");
    }
    let n = t.len();
    if at.iter().any(|s| *s <= 0.0 || *s > t[n - 1]) {
        return fail("E_OUT_OF_RANGE", "query time out of range");
    }
    // Index 0 is the implied origin.
    let mut tt = vec![0.0];
    tt.extend_from_slice(t);
    let mut rt = vec![0.0];
    rt.extend(t.iter().zip(r).map(|(a, b)| a * b));
    let mut fd = vec![0.0; n + 1];
    for i in 1..=n {
        fd[i] = (rt[i] - rt[i - 1]) / (tt[i] - tt[i - 1]);
    }
    let mut f = vec![0.0; n + 1];
    for i in 1..n {
        let w = tt[i + 1] - tt[i - 1];
        f[i] = (tt[i] - tt[i - 1]) / w * fd[i + 1] + (tt[i + 1] - tt[i]) / w * fd[i];
    }
    f[0] = fd[1] - (f[1] - fd[1]) / 2.0;
    f[n] = fd[n] - (f[n - 1] - fd[n]) / 2.0;
    if positive {
        if fd[1..].iter().any(|v| *v < 0.0) {
            return fail("E_DOMAIN", "a discrete forward is negative");
        }
        f[0] = f[0].clamp(0.0, 2.0 * fd[1]);
        for i in 1..n {
            f[i] = f[i].clamp(0.0, 2.0 * fd[i].min(fd[i + 1]));
        }
        f[n] = f[n].clamp(0.0, 2.0 * fd[n]);
    }
    let mut forwards = Vec::with_capacity(at.len());
    let mut zeros = Vec::with_capacity(at.len());
    for &s in at {
        let i = tt.partition_point(|k| *k < s).clamp(1, n);
        let w = tt[i] - tt[i - 1];
        let x = (s - tt[i - 1]) / w;
        let (g, big_g) = convex_piece(f[i - 1] - fd[i], f[i] - fd[i], x);
        forwards.push(fd[i] + g);
        zeros.push((rt[i - 1] + w * (fd[i] * x + big_g)) / s);
    }
    Ok((forwards, zeros))
}
