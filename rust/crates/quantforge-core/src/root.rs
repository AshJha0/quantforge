//! Root finders (`root-finders.md`).
use crate::error::{Result, fail};

#[derive(Debug, Clone, Copy)]
pub struct Controls {
    pub x_tol: f64,
    pub f_tol: f64,
    pub max_iter: i64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Root {
    pub root: f64,
    pub iterations: i64,
    pub residual: f64,
    pub termination: &'static str,
}

fn check(c: &Controls) -> Result<()> {
    if c.x_tol <= 0.0 || c.f_tol < 0.0 || c.max_iter < 1 {
        return fail("E_INPUT", "x_tol, f_tol or max_iter out of range");
    }
    Ok(())
}

fn eval(f: &dyn Fn(f64) -> f64, x: f64) -> Result<f64> {
    let y = f(x);
    if y.is_finite() {
        Ok(y)
    } else {
        fail("E_NON_FINITE", "function value is not finite")
    }
}

fn no_convergence<T>() -> Result<T> {
    fail("E_NO_CONVERGENCE", "max_iter reached")
}

fn same_sign(a: f64, b: f64) -> bool {
    (a > 0.0) == (b > 0.0)
}

// Shares the solvers' Result return so every exit path reads the same.
#[allow(clippy::unnecessary_wraps)]
fn done(root: f64, iterations: i64, residual: f64, termination: &'static str) -> Result<Root> {
    Ok(Root {
        root,
        iterations,
        residual,
        termination,
    })
}

/// Shared start of bisection and Brent. The inner `Err` is an end point that is a root.
fn start(
    f: &dyn Fn(f64) -> f64,
    a: f64,
    b: f64,
    c: &Controls,
) -> Result<std::result::Result<(f64, f64), Root>> {
    check(c)?;
    if a >= b {
        return fail("E_INPUT", "a must be below b");
    }
    let fa = eval(f, a)?;
    let fb = eval(f, b)?;
    for (x, y) in [(a, fa), (b, fb)] {
        if y == 0.0 {
            return Ok(Err(done(x, 0, 0.0, "EXACT")?));
        }
    }
    if same_sign(fa, fb) {
        return fail("E_NOT_BRACKETED", "no sign change on the interval");
    }
    Ok(Ok((fa, fb)))
}

pub fn bisection(f: &dyn Fn(f64) -> f64, a: f64, b: f64, c: &Controls) -> Result<Root> {
    let (mut fa, _) = match start(f, a, b, c)? {
        Ok(v) => v,
        Err(r) => return Ok(r),
    };
    let (mut a, mut b) = (a, b);
    for it in 1..=c.max_iter {
        let m = a + (b - a) / 2.0;
        let fm = eval(f, m)?;
        if fm == 0.0 {
            return done(m, it, fm, "EXACT");
        }
        if same_sign(fa, fm) {
            a = m;
            fa = fm;
        } else {
            b = m;
        }
        if (b - a) / 2.0 <= c.x_tol {
            return done(m, it, fm, "X_TOL");
        }
        if fm.abs() <= c.f_tol {
            return done(m, it, fm, "F_TOL");
        }
    }
    no_convergence()
}

pub fn brent(f: &dyn Fn(f64) -> f64, lo: f64, hi: f64, ctl: &Controls) -> Result<Root> {
    let (mut fa, mut fb) = match start(f, lo, hi, ctl)? {
        Ok(v) => v,
        Err(r) => return Ok(r),
    };
    let eps = 2f64.powi(-52);
    let (mut a, mut b) = (lo, hi);
    let (mut c, mut fc) = (a, fa);
    let mut d = b - a;
    let mut e = d;
    for it in 1..=ctl.max_iter {
        if fc.abs() < fb.abs() {
            a = b;
            b = c;
            c = a;
            fa = fb;
            fb = fc;
            fc = fa;
        }
        let tol1 = 2.0 * eps * b.abs() + ctl.x_tol / 2.0;
        let xm = (c - b) / 2.0;
        if xm.abs() <= tol1 {
            return done(b, it - 1, fb, "X_TOL");
        }
        if fb == 0.0 {
            return done(b, it - 1, fb, "EXACT");
        }
        if fb.abs() <= ctl.f_tol {
            return done(b, it - 1, fb, "F_TOL");
        }
        if e.abs() >= tol1 && fa.abs() > fb.abs() {
            let s = fb / fa;
            let (mut p, mut q);
            if a == c {
                p = 2.0 * xm * s;
                q = 1.0 - s;
            } else {
                let qq = fa / fc;
                let r = fb / fc;
                p = s * (2.0 * xm * qq * (qq - r) - (b - a) * (r - 1.0));
                q = (qq - 1.0) * (r - 1.0) * (s - 1.0);
            }
            if p > 0.0 {
                q = -q;
            }
            p = p.abs();
            if 2.0 * p < (3.0 * xm * q - (tol1 * q).abs()).min((e * q).abs()) {
                e = d;
                d = p / q;
            } else {
                d = xm;
                e = d;
            }
        } else {
            d = xm;
            e = d;
        }
        a = b;
        fa = fb;
        b += if d.abs() > tol1 { d } else { tol1.copysign(xm) };
        fb = eval(f, b)?;
        if same_sign(fb, fc) && fb != 0.0 {
            c = a;
            fc = fa;
            d = b - a;
            e = d;
        }
    }
    no_convergence()
}

pub fn newton(
    f: &dyn Fn(f64) -> f64,
    df: &dyn Fn(f64) -> f64,
    x0: f64,
    bracket: Option<(f64, f64)>,
    c: &Controls,
) -> Result<Root> {
    check(c)?;
    let mut br = None;
    if let Some((a, b)) = bracket {
        if a >= b {
            return fail("E_INPUT", "a must be below b");
        }
        let fa = eval(f, a)?;
        let fb = eval(f, b)?;
        if fa != 0.0 && fb != 0.0 && same_sign(fa, fb) {
            return fail("E_NOT_BRACKETED", "no sign change on the interval");
        }
        if x0 < a || x0 > b {
            return fail("E_INPUT", "x0 lies outside the bracket");
        }
        br = Some((a, b, fa, fb));
    }
    let mut x = x0;
    for it in 1..=c.max_iter {
        let fx = eval(f, x)?;
        if fx == 0.0 {
            return done(x, it - 1, fx, "EXACT");
        }
        let dfx = eval(df, x)?;
        if dfx == 0.0 {
            return fail("E_ZERO_DERIVATIVE", "derivative is zero");
        }
        let mut next = x - fx / dfx;
        if let Some((a, b, fa, fb)) = &mut br {
            // An end point may be an exact root, so judge by an end with a sign.
            let left = if *fa == 0.0 {
                !same_sign(*fb, fx)
            } else {
                same_sign(*fa, fx)
            };
            if left {
                *a = x;
                *fa = fx;
            } else {
                *b = x;
                *fb = fx;
            }
            if !(next >= *a && next <= *b) {
                next = *a + (*b - *a) / 2.0;
            }
        }
        let fnext = eval(f, next)?;
        if (next - x).abs() <= c.x_tol * (1.0 + next.abs()) {
            return done(next, it, fnext, "X_TOL");
        }
        if fnext.abs() <= c.f_tol {
            return done(next, it, fnext, "F_TOL");
        }
        x = next;
    }
    no_convergence()
}
