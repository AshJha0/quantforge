//! Numerical integration (`integration.md`).
use crate::error::{Result, fail};

type F<'a> = &'a dyn Fn(f64) -> f64;

fn check_range(a: f64, b: f64) -> Result<()> {
    if a >= b {
        return fail("E_INPUT", "a must be below b");
    }
    Ok(())
}

pub fn trapezoid(f: F, a: f64, b: f64, n: i64) -> Result<f64> {
    check_range(a, b)?;
    if n < 1 {
        return fail("E_INPUT", "n must be at least 1");
    }
    let h = (b - a) / n as f64;
    let mut s = f(a) / 2.0;
    for i in 1..n {
        s += f(a + i as f64 * h);
    }
    s += f(a + n as f64 * h) / 2.0;
    Ok(h * s)
}

pub fn simpson(f: F, a: f64, b: f64, n: i64) -> Result<f64> {
    check_range(a, b)?;
    if n < 2 || n % 2 != 0 {
        return fail("E_INPUT", "n must be even and at least 2");
    }
    let h = (b - a) / n as f64;
    let mut s = f(a);
    for i in 1..n {
        let w = if i % 2 == 1 { 4.0 } else { 2.0 };
        s += w * f(a + i as f64 * h);
    }
    s += f(a + n as f64 * h);
    Ok(h / 3.0 * s)
}

/// Value of P_n and its derivative at `t`.
fn legendre(n: usize, t: f64) -> (f64, f64) {
    let (mut p0, mut p1) = (1.0, t);
    for k in 2..=n {
        let k = k as f64;
        let p2 = ((2.0 * k - 1.0) * t * p1 - (k - 1.0) * p0) / k;
        p0 = p1;
        p1 = p2;
    }
    let nf = n as f64;
    (p1, nf * (t * p1 - p0) / (t * t - 1.0))
}

/// Nodes ascending, with their weights.
pub fn gauss_legendre_rule(n: usize) -> Vec<(f64, f64)> {
    let nf = n as f64;
    let mut rule = Vec::with_capacity(n);
    for i in 1..=n {
        let mut t = (std::f64::consts::PI * (i as f64 - 0.25) / (nf + 0.5)).cos();
        for _ in 0..100 {
            let (p, dp) = legendre(n, t);
            let step = p / dp;
            t -= step;
            if step.abs() < 1e-16 {
                break;
            }
        }
        let (_, dp) = legendre(n, t);
        rule.push((t, 2.0 / ((1.0 - t * t) * dp * dp)));
    }
    rule.reverse();
    rule
}

pub fn gauss_legendre(f: F, a: f64, b: f64, n: i64) -> Result<f64> {
    check_range(a, b)?;
    if n < 1 || n > 64 {
        return fail("E_INPUT", "n must be 1 to 64");
    }
    let (mid, half) = ((a + b) / 2.0, (b - a) / 2.0);
    let mut s = 0.0;
    for (t, w) in gauss_legendre_rule(n as usize) {
        s += w * f(mid + half * t);
    }
    Ok(half * s)
}

fn simpson_panel(l: f64, fl: f64, r: f64, fr: f64, fm: f64) -> f64 {
    (r - l) / 6.0 * (fl + 4.0 * fm + fr)
}

struct Panel {
    l: f64,
    r: f64,
    fl: f64,
    fm: f64,
    fr: f64,
    whole: f64,
}

fn adaptive(f: F, p: Panel, tol: f64, depth: i64, max_depth: i64) -> Result<f64> {
    let m = p.l + (p.r - p.l) / 2.0;
    let flm = f(p.l + (m - p.l) / 2.0);
    let frm = f(m + (p.r - m) / 2.0);
    let s1 = simpson_panel(p.l, p.fl, m, p.fm, flm);
    let s2 = simpson_panel(m, p.fm, p.r, p.fr, frm);
    let delta = s1 + s2 - p.whole;
    if delta.abs() <= 15.0 * tol {
        return Ok(s1 + s2 + delta / 15.0);
    }
    if !delta.is_finite() {
        return fail("E_NON_FINITE", "function value is not finite");
    }
    if depth >= max_depth {
        return fail("E_NO_CONVERGENCE", "max_depth reached");
    }
    let left = Panel {
        l: p.l,
        r: m,
        fl: p.fl,
        fm: flm,
        fr: p.fm,
        whole: s1,
    };
    let right = Panel {
        l: m,
        r: p.r,
        fl: p.fm,
        fm: frm,
        fr: p.fr,
        whole: s2,
    };
    Ok(adaptive(f, left, tol / 2.0, depth + 1, max_depth)?
        + adaptive(f, right, tol / 2.0, depth + 1, max_depth)?)
}

pub fn adaptive_simpson(f: F, a: f64, b: f64, tol: f64, max_depth: i64) -> Result<f64> {
    check_range(a, b)?;
    if tol <= 0.0 || max_depth < 0 {
        return fail("E_INPUT", "tol or max_depth out of range");
    }
    let (fl, fr) = (f(a), f(b));
    let fm = f(a + (b - a) / 2.0);
    let whole = simpson_panel(a, fl, b, fr, fm);
    let p = Panel {
        l: a,
        r: b,
        fl,
        fm,
        fr,
        whole,
    };
    adaptive(f, p, tol, 0, max_depth)
}

const XK: [f64; 8] = [
    0.991455371120812639206854697526329,
    0.949107912342758524526189684047851,
    0.864864423359769072789712788640926,
    0.741531185599394439863864773280788,
    0.586087235467691130294144838258730,
    0.405845151377397166906606412076961,
    0.207784955007898467600689403773244,
    0.0,
];
const WK: [f64; 8] = [
    0.022935322010529224963732008058970,
    0.063092092629978553290700663189204,
    0.104790010322250183839876322541518,
    0.140653259715525918998541745705333,
    0.169004726639267902826583426140209,
    0.190350578064785409913256402421014,
    0.204432940075298892414161999234649,
    0.209482141084727828012999174351914,
];
const WG: [f64; 4] = [
    0.129484966168869693270611432679082,
    0.279705391489276667901467771423780,
    0.381830050505118944950369775488975,
    0.417959183673469387755102040816327,
];

/// Returns `(l, r, K15 value, |K15 - G7|)` on `[l, r]`.
fn kronrod(f: F, l: f64, r: f64) -> (f64, f64, f64, f64) {
    let (mid, half) = ((l + r) / 2.0, (r - l) / 2.0);
    let (mut k, mut g) = (0.0, 0.0);
    for i in 0..8 {
        let pair = if i == 7 {
            f(mid)
        } else {
            f(mid - half * XK[i]) + f(mid + half * XK[i])
        };
        k += WK[i] * pair;
        if i % 2 == 1 {
            g += WG[i / 2] * pair;
        }
    }
    (l, r, half * k, (half * (k - g)).abs())
}

/// Returns the value and the error estimate.
pub fn gauss_kronrod(f: F, a: f64, b: f64, tol: f64, max_intervals: i64) -> Result<(f64, f64)> {
    check_range(a, b)?;
    if tol <= 0.0 || max_intervals < 1 {
        return fail("E_INPUT", "tol or max_intervals out of range");
    }
    let mut list = vec![kronrod(f, a, b)];
    loop {
        let value: f64 = list.iter().map(|p| p.2).sum();
        let error: f64 = list.iter().map(|p| p.3).sum();
        if !value.is_finite() || !error.is_finite() {
            return fail("E_NON_FINITE", "function value is not finite");
        }
        if error <= tol.max(1e-14 * value.abs()) {
            return Ok((value, error));
        }
        if list.len() as i64 >= max_intervals {
            return fail("E_NO_CONVERGENCE", "max_intervals reached");
        }
        let mut worst = 0;
        for i in 1..list.len() {
            if list[i].3 > list[worst].3 {
                worst = i;
            }
        }
        let (l, r, _, _) = list[worst];
        let m = l + (r - l) / 2.0;
        list[worst] = kronrod(f, l, m);
        list.push(kronrod(f, m, r));
    }
}
