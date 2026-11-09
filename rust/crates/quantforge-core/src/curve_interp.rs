//! Stage F interpolations of `ln S` (`curve-framework.md`, "Stage F: pluggable interpolation",
//! rulings F-18 to F-22). Each method precomputes node data once, then gives `ln S(t)` and the
//! instantaneous forward `f(t) = -d ln S/dt` inside `[t_0, t_n]`.
use crate::linalg::solve;

/// Hagan-West node forwards `f_0..f_n` (`n >= 1` sections) from times and `ln S` values.
pub(crate) fn convex_nodes(t: &[f64], l: &[f64]) -> Vec<f64> {
    let n = t.len() - 1;
    let y: Vec<f64> = (1..=n)
        .map(|i| (l[i - 1] - l[i]) / (t[i] - t[i - 1]))
        .collect();
    if n == 1 {
        return vec![y[0], y[0]];
    }
    let mut f = vec![0.0; n + 1];
    for i in 1..n {
        let (dl, dr) = (t[i] - t[i - 1], t[i + 1] - t[i]);
        f[i] = (dr * y[i - 1] + dl * y[i]) / (dl + dr);
    }
    f[0] = 1.5 * y[0] - 0.5 * f[1];
    f[n] = 1.5 * y[n - 1] - 0.5 * f[n - 1];
    f
}

/// Rule (e) with a given `eta`: `(f(x), integral of f from 0 to x)`.
fn rule_e(y: f64, g0: f64, g1: f64, eta: f64, x: f64) -> (f64, f64) {
    let a = -(eta * g0 + (1.0 - eta) * g1) / 2.0;
    if x <= eta && eta > 0.0 {
        let w = (eta - x) / eta;
        let int = (y + a) * x + (g0 - a) * (eta.powi(3) - (eta - x).powi(3)) / (3.0 * eta * eta);
        return (y + a + (g0 - a) * w * w, int);
    }
    if eta == 0.0 && x == 0.0 {
        return (y + g0, 0.0);
    }
    let left = (g0 - a) * eta / 3.0;
    if eta >= 1.0 {
        return (y + g1, (y + a) * x + left);
    }
    let w = (x - eta) / (1.0 - eta);
    let int = (y + a) * x + left + (g1 - a) * (x - eta).powi(3) / (3.0 * (1.0 - eta).powi(2));
    (y + a + (g1 - a) * w * w, int)
}

/// One convex monotone section: `(f(x), integral of f from 0 to x)` for `x` in `[0, 1]`.
pub(crate) fn convex_section(f0: f64, f1: f64, y: f64, x: f64) -> (f64, f64) {
    let (g0, g1) = (f0 - y, f1 - y);
    if g0.abs() < 1e-14 && g1.abs() < 1e-14 {
        return (f0 + (f1 - f0) * x, f0 * x + (f1 - f0) * x * x / 2.0);
    }
    if (g0 > 0.0 && -2.0 * g0 <= g1 && g1 <= -0.5 * g0)
        || (g0 < 0.0 && -0.5 * g0 <= g1 && g1 <= -2.0 * g0)
    {
        let a = 3.0 * f0 + 3.0 * f1 - 6.0 * y;
        let b = -(4.0 * f0 + 2.0 * f1 - 6.0 * y);
        return (
            a * x * x + b * x + f0,
            a * x.powi(3) / 3.0 + b * x * x / 2.0 + f0 * x,
        );
    }
    if (g0 < 0.0 && g1 > -2.0 * g0) || (g0 > 0.0 && g1 < -2.0 * g0) {
        let eta = (g1 + 2.0 * g0) / (g1 - g0);
        if eta >= 1.0 {
            return rule_e(y, g0, g1, 1.0, x);
        }
        if x <= eta {
            return (y + g0, (y + g0) * x);
        }
        let w = (x - eta) / (1.0 - eta);
        let int = (y + g0) * x + (g1 - g0) * (x - eta).powi(3) / (3.0 * (1.0 - eta).powi(2));
        return (y + g0 + (g1 - g0) * w * w, int);
    }
    if (g0 > 0.0 && g1 < 0.0 && g1 > -0.5 * g0) || (g0 < 0.0 && g1 > 0.0 && g1 < -0.5 * g0) {
        let eta = 3.0 * g1 / (g1 - g0);
        if eta <= 0.0 {
            return rule_e(y, g0, g1, 0.0, x);
        }
        if x <= eta {
            let w = (eta - x) / eta;
            let int =
                (y + g1) * x + (g0 - g1) * (eta.powi(3) - (eta - x).powi(3)) / (3.0 * eta * eta);
            return (y + g1 + (g0 - g1) * w * w, int);
        }
        return (y + g1, (y + g1) * x + (g0 - g1) * eta / 3.0);
    }
    let eta = (g1 / (g0 + g1)).clamp(0.0, 1.0);
    rule_e(y, g0, g1, if eta.is_nan() { 0.0 } else { eta }, x)
}

/// Convex monotone `(ln S, f)` at `t` inside `[t_0, t_n]`; `t = t_n` gives the left limit.
pub(crate) fn convex_eval(t: &[f64], l: &[f64], f: &[f64], at: f64) -> (f64, f64) {
    let n = t.len() - 1;
    let i = t.partition_point(|x| *x <= at).clamp(1, n);
    let dx = t[i] - t[i - 1];
    let y = (l[i - 1] - l[i]) / dx;
    let x = ((at - t[i - 1]) / dx).clamp(0.0, 1.0);
    let (fx, int) = convex_section(f[i - 1], f[i], y, x);
    (l[i - 1] - dx * int, fx)
}

/// Hyman-filtered natural cubic slopes `m_i = d ln S/dt` at the nodes.
pub(crate) fn log_cubic_slopes(t: &[f64], l: &[f64]) -> Vec<f64> {
    let n = t.len() - 1;
    let h: Vec<f64> = (0..n).map(|i| t[i + 1] - t[i]).collect();
    let s: Vec<f64> = (0..n).map(|i| (l[i + 1] - l[i]) / h[i]).collect();
    if n == 1 {
        return vec![s[0], s[0]];
    }
    let mut a = vec![vec![0.0; n + 1]; n + 1];
    let mut r = vec![0.0; n + 1];
    a[0][0] = 2.0;
    a[0][1] = 1.0;
    r[0] = 3.0 * s[0];
    for i in 1..n {
        a[i][i - 1] = h[i];
        a[i][i] = 2.0 * (h[i - 1] + h[i]);
        a[i][i + 1] = h[i - 1];
        r[i] = 3.0 * (h[i] * s[i - 1] + h[i - 1] * s[i]);
    }
    a[n][n - 1] = 1.0;
    a[n][n] = 2.0;
    r[n] = 3.0 * s[n - 1];
    let raw = solve(&a, &r).unwrap_or_else(|_| vec![0.0; n + 1]);
    let clip = |m: f64, cap: f64, sign_ref: f64| {
        if m * sign_ref > 0.0 {
            m.signum() * m.abs().min(cap)
        } else {
            0.0
        }
    };
    let mut m = raw.clone();
    m[0] = clip(raw[0], 3.0 * s[0].abs(), s[0]);
    m[n] = clip(raw[n], 3.0 * s[n - 1].abs(), s[n - 1]);
    for i in 1..n {
        let p = (s[i - 1] * h[i] + s[i] * h[i - 1]) / (h[i - 1] + h[i]);
        let mut cap = 3.0 * s[i - 1].abs().min(s[i].abs()).min(p.abs());
        if i > 1 && (s[i - 1] - s[i - 2]) * (s[i] - s[i - 1]) > 0.0 {
            let pd = (s[i - 1] * (2.0 * h[i - 1] + h[i - 2]) - s[i - 2] * h[i - 1])
                / (h[i - 2] + h[i - 1]);
            if p * pd > 0.0 && p * (s[i - 1] - s[i - 2]) > 0.0 {
                cap = cap.max(1.5 * p.abs().min(pd.abs()));
            }
        }
        if i < n - 1 && (s[i] - s[i - 1]) * (s[i + 1] - s[i]) > 0.0 {
            let pu = (s[i] * (2.0 * h[i] + h[i + 1]) - s[i + 1] * h[i]) / (h[i] + h[i + 1]);
            if p * pu > 0.0 && -p * (s[i] - s[i - 1]) > 0.0 {
                cap = cap.max(1.5 * p.abs().min(pu.abs()));
            }
        }
        m[i] = clip(raw[i], cap, p);
    }
    m
}

/// Cubic `(ln S, f)` inside `[t_0, t_n]`, right-hand at nodes except the last.
pub(crate) fn log_cubic_eval(t: &[f64], l: &[f64], m: &[f64], at: f64) -> (f64, f64) {
    let n = t.len() - 1;
    let i = t.partition_point(|x| *x <= at).saturating_sub(1).min(n - 1);
    let h = t[i + 1] - t[i];
    let s = (l[i + 1] - l[i]) / h;
    let b = (3.0 * s - m[i + 1] - 2.0 * m[i]) / h;
    let c = (m[i + 1] + m[i] - 2.0 * s) / (h * h);
    let d = at - t[i];
    (
        l[i] + d * (m[i] + d * (b + d * c)),
        -(m[i] + 2.0 * b * d + 3.0 * c * d * d),
    )
}

/// `1 - e^{-x}` without cancellation.
fn one_minus_exp(x: f64) -> f64 {
    -(-x).exp_m1()
}

/// Tension-spline second derivatives `M_0..M_n` (natural ends).
pub(crate) fn tension_moments(t: &[f64], l: &[f64], sigma: f64) -> Vec<f64> {
    let n = t.len() - 1;
    if n == 1 {
        return vec![0.0, 0.0];
    }
    let h: Vec<f64> = (0..n).map(|i| t[i + 1] - t[i]).collect();
    let s: Vec<f64> = (0..n).map(|i| (l[i + 1] - l[i]) / h[i]).collect();
    let ab = |hi: f64| {
        let z = sigma * hi;
        if z < 1e-3 {
            (
                hi / 6.0 * (1.0 - z * z / 60.0),
                hi / 3.0 * (1.0 - z * z / 15.0),
            )
        } else {
            let q = one_minus_exp(2.0 * z);
            let inv_sinh = 2.0 * (-z).exp() / q;
            let coth = (1.0 + (-2.0 * z).exp()) / q;
            (
                1.0 / (sigma * sigma * hi) - inv_sinh / sigma,
                coth / sigma - 1.0 / (sigma * sigma * hi),
            )
        }
    };
    let k = n - 1;
    let mut a = vec![vec![0.0; k]; k];
    let mut r = vec![0.0; k];
    for row in 0..k {
        let i = row + 1;
        let (al, bl) = ab(h[i - 1]);
        let (ar, br) = ab(h[i]);
        a[row][row] = bl + br;
        if row > 0 {
            a[row][row - 1] = al;
        }
        if row + 1 < k {
            a[row][row + 1] = ar;
        }
        r[row] = s[i] - s[i - 1];
    }
    let inner = solve(&a, &r).unwrap_or_else(|_| vec![0.0; k]);
    let mut m = vec![0.0];
    m.extend(inner);
    m.push(0.0);
    m
}

/// `R(u)` and `R'(u)` of the tension spline on an interval of length `h`.
fn tension_r(u: f64, h: f64, sigma: f64) -> (f64, f64) {
    let z = sigma * h;
    if z < 1e-3 {
        return (
            (u / h) * (u * u - h * h) / 6.0,
            (3.0 * u * u - h * h) / (6.0 * h),
        );
    }
    let q = one_minus_exp(2.0 * z);
    let e = (-sigma * (h - u)).exp();
    let sh = e * one_minus_exp(2.0 * sigma * u) / q;
    let ch = e * (1.0 + (-2.0 * sigma * u).exp()) / q;
    (
        (sh - u / h) / (sigma * sigma),
        (sigma * ch - 1.0 / h) / (sigma * sigma),
    )
}

pub(crate) fn tension_eval(t: &[f64], l: &[f64], m: &[f64], sigma: f64, at: f64) -> (f64, f64) {
    let n = t.len() - 1;
    let i = t.partition_point(|x| *x <= at).saturating_sub(1).min(n - 1);
    let h = t[i + 1] - t[i];
    let (a, b) = (at - t[i], t[i + 1] - at);
    let (rb, drb) = tension_r(b, h, sigma);
    let (ra, dra) = tension_r(a, h, sigma);
    let v = l[i] * b / h + l[i + 1] * a / h + m[i] * rb + m[i + 1] * ra;
    let d = (l[i + 1] - l[i]) / h - m[i] * drb + m[i + 1] * dra;
    (v, -d)
}
