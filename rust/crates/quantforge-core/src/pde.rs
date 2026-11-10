//! Finite-difference Black-Scholes solver (`pde.md`).

use crate::error::{Result, fail};
use crate::linalg::thomas;

#[derive(Debug, Clone, Copy)]
pub struct PdeInputs {
    pub call: bool,
    pub spot: f64,
    pub strike: f64,
    pub r: f64,
    pub q: f64,
    pub sigma: f64,
    pub t: f64,
    pub space_steps: i64,
    pub time_steps: i64,
    pub width: f64,
    pub rannacher_steps: i64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PdeResult {
    pub price: f64,
    pub delta: f64,
    pub gamma: f64,
    pub grid_h: f64,
}

struct Grid {
    call: bool,
    strike: f64,
    r: f64,
    q: f64,
    s_low: f64,
    s_high: f64,
    l: f64,
    c: f64,
    u: f64,
}

impl Grid {
    fn boundaries(&self, tau: f64) -> (f64, f64) {
        let (k, r, q) = (self.strike, self.r, self.q);
        if self.call {
            (0.0, self.s_high * (-q * tau).exp() - k * (-r * tau).exp())
        } else {
            (k * (-r * tau).exp() - self.s_low * (-q * tau).exp(), 0.0)
        }
    }

    fn step(&self, v: &mut [f64], tau: f64, s: f64, theta: f64) {
        let n = v.len() - 1;
        let (old_low, old_high) = self.boundaries(tau);
        v[0] = old_low;
        v[n] = old_high;
        let (new_low, new_high) = self.boundaries(tau + s);
        let e = (1.0 - theta) * s;
        let mut rhs: Vec<f64> = (1..n)
            .map(|j| v[j] + e * (self.l * v[j - 1] + self.c * v[j] + self.u * v[j + 1]))
            .collect();
        let i = theta * s;
        rhs[0] += i * self.l * new_low;
        rhs[n - 2] += i * self.u * new_high;
        thomas(-i * self.l, 1.0 - i * self.c, -i * self.u, &mut rhs);
        v[1..n].copy_from_slice(&rhs);
        v[0] = new_low;
        v[n] = new_high;
    }
}

pub fn bs_european(p: &PdeInputs) -> Result<PdeResult> {
    crate::error::finite("p", &p)?;
    if p.spot <= 0.0 || p.strike <= 0.0 || p.sigma <= 0.0 || p.t <= 0.0 || p.width <= 0.0 {
        return fail(
            "E_DOMAIN",
            "spot, strike, sigma, t and width must be positive",
        );
    }
    let (jn, m, rn) = (p.space_steps, p.time_steps, p.rannacher_steps);
    if jn % 2 != 0 || jn < 20 || m < 2 || rn < 0 || rn >= m {
        return fail("E_INPUT", "grid sizes out of range");
    }
    let a = p.sigma * p.sigma / 2.0;
    let b = p.r - p.q - a;
    let h = 2.0 * p.width * p.sigma * p.t.sqrt() / jn as f64;
    let dt = p.t / m as f64;
    let mid = (jn / 2) as usize;
    let x0 = p.spot.ln();
    let x = |j: i64| x0 + (j - jn / 2) as f64 * h;
    let k = p.strike;
    let lk = k.ln();
    let mut v: Vec<f64> = (0..=jn)
        .map(|j| {
            let (lo, up) = (x(j) - h / 2.0, x(j) + h / 2.0);
            if p.call {
                if up <= lk {
                    return 0.0;
                }
                let l = lo.max(lk);
                (up.exp() - l.exp() - k * (up - l)) / h
            } else {
                if lo >= lk {
                    return 0.0;
                }
                let u = up.min(lk);
                (k * (u - lo) - u.exp() + lo.exp()) / h
            }
        })
        .collect();
    let g = Grid {
        call: p.call,
        strike: k,
        r: p.r,
        q: p.q,
        s_low: x(0).exp(),
        s_high: x(jn).exp(),
        l: a / (h * h) - b / (2.0 * h),
        c: -2.0 * a / (h * h) - p.r,
        u: a / (h * h) + b / (2.0 * h),
    };
    for i in 0..m {
        let tau = i as f64 * dt;
        if i < rn {
            g.step(&mut v, tau, dt / 2.0, 1.0);
            g.step(&mut v, tau + dt / 2.0, dt / 2.0, 1.0);
        } else {
            g.step(&mut v, tau, dt, 0.5);
        }
    }
    let vx = (v[mid + 1] - v[mid - 1]) / (2.0 * h);
    let vxx = (v[mid + 1] - 2.0 * v[mid] + v[mid - 1]) / (h * h);
    Ok(PdeResult {
        price: v[mid],
        delta: vx / p.spot,
        gamma: (vxx - vx) / (p.spot * p.spot),
        grid_h: h,
    })
}

impl crate::error::Finite for PdeInputs {
    fn is_all_finite(&self) -> bool {
        self.spot.is_all_finite()
            && self.strike.is_all_finite()
            && self.r.is_all_finite()
            && self.q.is_all_finite()
            && self.sigma.is_all_finite()
            && self.t.is_all_finite()
            && self.width.is_all_finite()
    }
}

impl crate::error::Finite for PdeResult {
    fn is_all_finite(&self) -> bool {
        self.price.is_all_finite()
            && self.delta.is_all_finite()
            && self.gamma.is_all_finite()
            && self.grid_h.is_all_finite()
    }
}
