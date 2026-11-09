//! Heston, Bates and Merton pricing, and the SLV leverage reference scheme
//! (`05-volatility/heston-family.md`, rulings E-A12 to E-A14).
use crate::arb_surface::{Slice, check_slices, local_variance};
use crate::black::black;
use crate::error::{Result, fail};
use crate::integrate::gauss_legendre_rule;
use std::f64::consts::PI;
use std::ops::{Add, Div, Mul, Neg, Sub};
use std::sync::OnceLock;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct C {
    pub re: f64,
    pub im: f64,
}

const fn c(re: f64, im: f64) -> C {
    C { re, im }
}

const ONE: C = c(1.0, 0.0);
const I: C = c(0.0, 1.0);

impl Add for C {
    type Output = C;
    fn add(self, o: C) -> C {
        c(self.re + o.re, self.im + o.im)
    }
}
impl Sub for C {
    type Output = C;
    fn sub(self, o: C) -> C {
        c(self.re - o.re, self.im - o.im)
    }
}
impl Mul for C {
    type Output = C;
    fn mul(self, o: C) -> C {
        c(
            self.re * o.re - self.im * o.im,
            self.re * o.im + self.im * o.re,
        )
    }
}
impl Mul<f64> for C {
    type Output = C;
    fn mul(self, o: f64) -> C {
        c(self.re * o, self.im * o)
    }
}
impl Div for C {
    type Output = C;
    fn div(self, o: C) -> C {
        let n = o.re * o.re + o.im * o.im;
        c(
            (self.re * o.re + self.im * o.im) / n,
            (self.im * o.re - self.re * o.im) / n,
        )
    }
}
impl Neg for C {
    type Output = C;
    fn neg(self) -> C {
        c(-self.re, -self.im)
    }
}

impl C {
    fn exp(self) -> C {
        let m = self.re.exp();
        c(m * self.im.cos(), m * self.im.sin())
    }
    /// `ln(1 + z)`, accurate for small `z`.
    fn ln_1p(self) -> C {
        let (x, y) = (self.re, self.im);
        c(0.5 * (2.0 * x + x * x + y * y).ln_1p(), y.atan2(1.0 + x))
    }

    /// Principal square root.
    fn sqrt(self) -> C {
        let r = self.re.hypot(self.im);
        let re = ((r + self.re) / 2.0).sqrt();
        let im = ((r - self.re) / 2.0).sqrt();
        c(re, if self.im < 0.0 { -im } else { im })
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Heston {
    pub v0: f64,
    pub kappa: f64,
    pub theta: f64,
    pub xi: f64,
    pub rho: f64,
}

impl Heston {
    pub fn check(&self) -> Result<()> {
        let pos = [self.v0, self.kappa, self.theta, self.xi]
            .iter()
            .all(|v| *v > 0.0);
        if pos && self.rho.abs() < 1.0 {
            Ok(())
        } else {
            fail("E_DOMAIN", "need v0, kappa, theta, xi > 0 and |rho| < 1")
        }
    }

    /// Characteristic function of `ln(S_T/F)` at complex `u`, little-trap form [Alb07].
    pub fn cf(&self, u: C, t: f64) -> C {
        let Heston {
            v0,
            kappa,
            theta,
            xi,
            rho,
        } = *self;
        let iu = I * u;
        let b = c(kappa, 0.0) - iu * (rho * xi);
        let q = iu + u * u;
        let d = (b * b + q * (xi * xi)).sqrt();
        // b - d = (b^2 - d^2)/(b + d), free of cancellation at small xi; divided by xi^2 here.
        let bd = -q / (b + d);
        let g = bd * (xi * xi) / (b + d);
        let e = (-d * t).exp();
        // ln((1 - g e)/(1 - g)) = ln(1 + g (1 - e)/(1 - g)), by log1p for small g.
        let lg = (g * (ONE - e) / (ONE - g)).ln_1p();
        let cc = bd * (kappa * t) - lg * (2.0 * kappa / (xi * xi));
        let dd = bd * ((ONE - e) / (ONE - g * e));
        (cc * theta + dd * v0).exp()
    }
}

/// Log-normal jumps `ln(1+J) ~ N(mu, delta^2)` at rate `lambda`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Jumps {
    pub intensity: f64,
    pub mean_log_jump: f64,
    pub log_jump_vol: f64,
}

impl Jumps {
    pub fn check(&self) -> Result<()> {
        if self.intensity >= 0.0 && self.log_jump_vol >= 0.0 && self.mean_log_jump.is_finite() {
            Ok(())
        } else {
            fail("E_DOMAIN", "need intensity >= 0 and log_jump_vol >= 0")
        }
    }

    fn kbar(&self) -> f64 {
        (self.mean_log_jump + self.log_jump_vol * self.log_jump_vol / 2.0).exp() - 1.0
    }

    /// Compensated jump factor of the characteristic function.
    fn cf(&self, u: C, t: f64) -> C {
        let (mu, d) = (self.mean_log_jump, self.log_jump_vol);
        let iu = I * u;
        let jump = (iu * mu - u * u * (d * d / 2.0)).exp();
        ((jump - ONE - iu * self.kbar()) * (self.intensity * t)).exp()
    }
}

/// Common inputs of every price operation.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Market {
    pub spot: f64,
    pub expiry_years: f64,
    pub rate: f64,
    pub dividend_yield: f64,
    pub call: bool,
}

impl Market {
    fn check(&self, strikes: &[f64]) -> Result<()> {
        if strikes.is_empty() {
            return fail("E_INPUT", "at least 1 strike is required");
        }
        let pos = |v: f64| v > 0.0;
        if !(pos(self.spot) && pos(self.expiry_years) && strikes.iter().all(|&k| pos(k))) {
            return fail("E_DOMAIN", "spot, expiry_years and strikes must be above 0");
        }
        Ok(())
    }

    fn forward(&self) -> f64 {
        self.spot * ((self.rate - self.dividend_yield) * self.expiry_years).exp()
    }
}

fn rule() -> &'static [(f64, f64)] {
    static RULE: OnceLock<Vec<(f64, f64)>> = OnceLock::new();
    RULE.get_or_init(|| gauss_legendre_rule(1024))
}

/// Lewis single-integral prices [Lew01], Gauss-Legendre 1024 nodes on `[0, 200/sqrt(min(T, 1))]`
/// (ruling E-A26).
fn lewis(m: &Market, strikes: &[f64], phi: &dyn Fn(C) -> C) -> Vec<f64> {
    let (f, t) = (m.forward(), m.expiry_years);
    let disc = (-m.rate * t).exp();
    let half = 100.0 / t.min(1.0).sqrt();
    let nodes: Vec<(f64, f64, C)> = rule()
        .iter()
        .map(|&(x, w)| {
            let u = half * (x + 1.0);
            (u, half * w, phi(c(u, -0.5)))
        })
        .collect();
    strikes
        .iter()
        .map(|&k| {
            let lk = (f / k).ln();
            let int: f64 = nodes
                .iter()
                .map(|&(u, w, p)| w * (c(0.0, u * lk).exp() * p).re / (u * u + 0.25))
                .sum();
            let call = disc * (f - (f * k).sqrt() / PI * int);
            if m.call { call } else { call - disc * (f - k) }
        })
        .collect()
}

pub fn heston_price(m: &Market, strikes: &[f64], h: &Heston) -> Result<Vec<f64>> {
    m.check(strikes)?;
    h.check()?;
    Ok(lewis(m, strikes, &|u| h.cf(u, m.expiry_years)))
}

pub fn bates_price(m: &Market, strikes: &[f64], h: &Heston, j: &Jumps) -> Result<Vec<f64>> {
    m.check(strikes)?;
    h.check()?;
    j.check()?;
    let t = m.expiry_years;
    Ok(lewis(m, strikes, &|u| h.cf(u, t) * j.cf(u, t)))
}

/// `(re, im)` of the Heston characteristic function at real `u >= 0`.
pub fn heston_cf(t: f64, h: &Heston, u: &[f64]) -> Result<(Vec<f64>, Vec<f64>)> {
    if u.is_empty() {
        return fail("E_INPUT", "at least 1 u is required");
    }
    if u.iter().any(|v| v.is_nan() || *v < 0.0) || t.is_nan() || t <= 0.0 {
        return fail("E_DOMAIN", "u must be at least 0 and expiry_years above 0");
    }
    h.check()?;
    Ok(u.iter()
        .map(|&x| h.cf(c(x, 0.0), t))
        .map(|z| (z.re, z.im))
        .unzip())
}

/// Merton's Poisson series [Mer76]: weights at `lambda (1 + kbar)`, each term at rate `r_n`.
pub fn merton_price(m: &Market, strikes: &[f64], vol: f64, j: &Jumps) -> Result<Vec<f64>> {
    m.check(strikes)?;
    if vol.is_nan() || vol <= 0.0 {
        return fail("E_DOMAIN", "vol must be above 0");
    }
    j.check()?;
    let (t, s, q) = (m.expiry_years, m.spot, m.dividend_yield);
    let kbar = j.kbar();
    let lt = j.intensity * (1.0 + kbar) * t;
    let mut terms = Vec::new();
    let (mut w, mut total) = ((-lt).exp(), 0.0);
    for n in 0..200 {
        let nf = f64::from(n);
        if n > 0 {
            w *= lt / nf;
        }
        let vn = (vol * vol + nf * j.log_jump_vol * j.log_jump_vol / t).sqrt();
        let rn = m.rate - j.intensity * kbar + nf * kbar.ln_1p() / t;
        terms.push((w, vn, rn));
        total += w;
        if total >= 1.0 - 1e-16 {
            break;
        }
    }
    Ok(strikes
        .iter()
        .map(|&k| {
            terms
                .iter()
                .map(|&(w, vn, rn)| {
                    w * black(m.call, s * ((rn - q) * t).exp(), k, vn, t, (-rn * t).exp())
                })
                .sum()
        })
        .collect())
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Grid {
    pub nx: i64,
    pub nv: i64,
    pub nt: i64,
    pub x_min: f64,
    pub x_max: f64,
    pub v_max: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Leverage {
    pub x: Vec<f64>,
    pub leverage: Vec<f64>,
    pub mass: f64,
}

/// Tridiagonal solve by the Thomas algorithm: `lo[k] p[k-1] + di[k] p[k] + up[k] p[k+1] = rhs[k]`.
pub(crate) fn thomas(lo: &[f64], di: &[f64], up: &[f64], rhs: &mut [f64]) {
    let n = rhs.len();
    let mut c = vec![0.0; n];
    c[0] = up[0] / di[0];
    rhs[0] /= di[0];
    for k in 1..n {
        let m = di[k] - lo[k] * c[k - 1];
        c[k] = up[k] / m;
        rhs[k] = (rhs[k] - lo[k] * rhs[k - 1]) / m;
    }
    for k in (0..n - 1).rev() {
        rhs[k] -= c[k] * rhs[k + 1];
    }
}

/// Rows `(lower, diagonal, upper)` of `I - dt A` on one line (spec "Operator rows").
fn rows(mu: &[f64], s: &[f64], h: f64, dt: f64, no_flux: bool) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let n = mu.len();
    // face k between nodes k-1 and k, k = 0..=n.
    let face: Vec<f64> = (0..=n)
        .map(|k| match k {
            0 if no_flux => 0.0,
            0 => mu[0],
            k if k == n && no_flux => 0.0,
            k if k == n => mu[n - 1],
            k => (mu[k - 1] + mu[k]) / 2.0,
        })
        .collect();
    let (pos, neg) = (|f: f64| f.max(0.0), |f: f64| f.min(0.0));
    let (mut lo, mut di, mut up) = (vec![0.0; n], vec![0.0; n], vec![0.0; n]);
    for k in 0..n {
        let end = no_flux && (k == 0 || k == n - 1);
        let diff = if end {
            dt * s[k] / (2.0 * h * h)
        } else {
            dt * s[k] / (h * h)
        };
        di[k] = 1.0 + diff + dt * (pos(face[k + 1]) - neg(face[k])) / h;
        if k + 1 < n {
            up[k] = -dt * s[k + 1] / (2.0 * h * h) + dt * neg(face[k + 1]) / h;
        }
        if k > 0 {
            lo[k] = -dt * s[k - 1] / (2.0 * h * h) - dt * pos(face[k]) / h;
        }
    }
    (lo, di, up)
}

/// The leverage reference scheme of `heston-family.md` (ruling E-A14).
pub fn slv_leverage(m: &Market, h: &Heston, slices: &[Slice], g: &Grid) -> Result<Leverage> {
    check_slices(slices)?;
    if g.nx < 5 || g.nv < 5 || g.nt < 2 {
        return fail("E_INPUT", "nx and nv must be at least 5 and nt at least 2");
    }
    // Every E_INPUT rule before every E_DOMAIN rule (ruling E-A37).
    let x0 = m.spot.ln();
    if m.spot > 0.0 && !(g.x_min < x0 && x0 < g.x_max) {
        return fail("E_INPUT", "ln(spot) must lie strictly inside the x grid");
    }
    if !(m.spot > 0.0 && m.expiry_years > 0.0) {
        return fail("E_DOMAIN", "spot and expiry_years must be above 0");
    }
    if g.v_max.is_nan() || g.v_max <= 0.0 {
        return fail("E_DOMAIN", "v_max must be above 0");
    }
    h.check()?;
    let (nx, nv, nt) = (
        usize::try_from(g.nx).unwrap_or(0),
        usize::try_from(g.nv).unwrap_or(0),
        g.nt,
    );
    let dx = (g.x_max - g.x_min) / (nx - 1) as f64;
    let dv = g.v_max / (nv + 1) as f64;
    let dt = m.expiry_years / nt as f64;
    let x: Vec<f64> = (0..nx).map(|i| g.x_min + i as f64 * dx).collect();
    let v: Vec<f64> = (0..nv).map(|j| (j + 1) as f64 * dv).collect();
    let (r, q) = (m.rate, m.dividend_yield);
    let ln_f = |t: f64| x0 + (r - q) * t;
    let lv2 = |t: f64, xi: f64| local_variance(slices, t, xi - ln_f(t));

    // Start at t_1 = dt.
    let l0 = lv2(dt, ln_f(dt))? / h.v0;
    let (mx, mv) = (
        x0 + (r - q - l0 * h.v0 / 2.0) * dt,
        h.v0 + h.kappa * (h.theta - h.v0) * dt,
    );
    let sx = (l0 * h.v0 * dt).sqrt().max(2.0 * dx);
    let sv = (h.xi * (h.v0 * dt).sqrt()).max(2.0 * dv);
    let rho = h.rho;
    let mut p: Vec<Vec<f64>> = x
        .iter()
        .map(|&xi| {
            v.iter()
                .map(|&vj| {
                    let (a, b) = ((xi - mx) / sx, (vj - mv) / sv);
                    let z = (a * a - 2.0 * rho * a * b + b * b) / (1.0 - rho * rho);
                    (-z / 2.0).exp() / (2.0 * PI * sx * sv * (1.0 - rho * rho).sqrt())
                })
                .collect()
        })
        .collect();
    let mass = |p: &[Vec<f64>]| p.iter().flatten().sum::<f64>() * dx * dv;
    let m0 = mass(&p);
    p.iter_mut().flatten().for_each(|e| *e /= m0);

    let leverage = |p: &[Vec<f64>], t: f64| -> Result<Vec<f64>> {
        let mi: Vec<f64> = p.iter().map(|row| row.iter().sum()).collect();
        let ei: Vec<f64> = p
            .iter()
            .map(|row| row.iter().zip(&v).map(|(a, b)| a * b).sum())
            .collect();
        let eps = 1e-10 * mi.iter().copied().fold(0.0, f64::max);
        let ebar = ei.iter().sum::<f64>() / mi.iter().sum::<f64>();
        x.iter()
            .enumerate()
            .map(|(i, &xi)| Ok((lv2(t, xi)? / ((ei[i] + eps * ebar) / (mi[i] + eps))).sqrt()))
            .collect()
    };

    for n in 1..nt {
        let l = leverage(&p, n as f64 * dt)?;
        // 1. Mixed term, explicit, interior nodes.
        let f: Vec<Vec<f64>> = (0..nx)
            .map(|i| {
                (0..nv)
                    .map(|j| rho * h.xi * l[i] * v[j] * p[i][j])
                    .collect()
            })
            .collect();
        let mut ps = p.clone();
        for i in 1..nx - 1 {
            for j in 1..nv - 1 {
                ps[i][j] += dt
                    * (f[i + 1][j + 1] - f[i + 1][j - 1] - f[i - 1][j + 1] + f[i - 1][j - 1])
                    / (4.0 * dx * dv);
            }
        }
        // 2. x, implicit for each j, Dirichlet ends.
        for j in 0..nv {
            let mu: Vec<f64> = l.iter().map(|li| r - q - li * li * v[j] / 2.0).collect();
            let s: Vec<f64> = l.iter().map(|li| li * li * v[j]).collect();
            let (mut lo, mut di, mut up) = rows(&mu, &s, dx, dt, false);
            for k in [0, nx - 1] {
                (lo[k], di[k], up[k]) = (0.0, 1.0, 0.0);
            }
            let mut rhs: Vec<f64> = ps.iter().map(|row| row[j]).collect();
            rhs[0] = 0.0;
            rhs[nx - 1] = 0.0;
            thomas(&lo, &di, &up, &mut rhs);
            for (i, val) in rhs.into_iter().enumerate() {
                ps[i][j] = val;
            }
        }
        // 3. v, implicit for each i, no flux.
        let mu: Vec<f64> = v.iter().map(|vj| h.kappa * (h.theta - vj)).collect();
        let s: Vec<f64> = v.iter().map(|vj| h.xi * h.xi * vj).collect();
        let (lo, di, up) = rows(&mu, &s, dv, dt, true);
        for row in &mut ps {
            thomas(&lo, &di, &up, row);
            // 4. Floor.
            for e in row.iter_mut() {
                *e = e.max(0.0);
            }
        }
        p = ps;
    }
    Ok(Leverage {
        leverage: leverage(&p, m.expiry_years)?,
        mass: mass(&p),
        x,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::svi::Svi;

    const H: Heston = Heston {
        v0: 0.04,
        kappa: 1.5,
        theta: 0.04,
        xi: 0.5,
        rho: -0.7,
    };

    fn mkt(call: bool) -> Market {
        Market {
            spot: 100.0,
            expiry_years: 1.0,
            rate: 0.03,
            dividend_yield: 0.01,
            call,
        }
    }

    #[test]
    fn complex_helpers() {
        let z = c(3.0, -4.0);
        let s = z.sqrt();
        assert!(((s * s) - z).re.abs() < 1e-14 && ((s * s) - z).im.abs() < 1e-14);
        let back = (z - ONE).ln_1p().exp();
        assert!((back.re - 3.0).abs() < 1e-14 && (back.im + 4.0).abs() < 1e-14);
        let q = z / z;
        assert!((q.re - 1.0).abs() < 1e-15 && q.im.abs() < 1e-15);
    }

    #[test]
    fn cf_is_one_at_minus_i_and_matches_golden() {
        let z = H.cf(c(0.0, -1.0), 1.0);
        assert!((z.re - 1.0).abs() < 1e-14 && z.im.abs() < 1e-14);
        let (re, im) = heston_cf(1.0, &H, &[0.0, 5.0]).unwrap();
        assert!((re[0] - 1.0).abs() < 1e-15 && im[0].abs() < 1e-15);
        assert!(
            (re[1] - 0.6729975569517288).abs() < 1e-13
                && (im[1] - 0.07269177076832213).abs() < 1e-13
        );
        assert_eq!(heston_cf(1.0, &H, &[]).unwrap_err().code, "E_INPUT");
        assert_eq!(heston_cf(1.0, &H, &[-1.0]).unwrap_err().code, "E_DOMAIN");
    }

    #[test]
    fn heston_prices_and_parity() {
        let k = [70.0, 100.0, 140.0];
        let calls = heston_price(&mkt(true), &k, &H).unwrap();
        assert!((calls[1] - 8.113489032310287).abs() < 1e-8);
        let puts = heston_price(&mkt(false), &k, &H).unwrap();
        let m = mkt(true);
        for i in 0..3 {
            let parity = (-0.03f64).exp() * (m.forward() - k[i]);
            assert!((calls[i] - puts[i] - parity).abs() < 1e-10);
        }
        let small = Heston { xi: 1e-3, ..H };
        let p = heston_price(&m, &[100.0], &small).unwrap()[0];
        let bs = black(true, m.forward(), 100.0, 0.2, 1.0, (-0.03f64).exp());
        assert!((p - bs).abs() < 1e-3);
        for bad in [
            Heston { v0: 0.0, ..H },
            Heston { xi: 0.0, ..H },
            Heston { rho: 1.0, ..H },
        ] {
            assert_eq!(heston_price(&m, &k, &bad).unwrap_err().code, "E_DOMAIN");
        }
        assert_eq!(heston_price(&m, &[], &H).unwrap_err().code, "E_INPUT");
        assert_eq!(heston_price(&m, &[0.0], &H).unwrap_err().code, "E_DOMAIN");
    }

    #[test]
    fn bates_and_merton() {
        let j = Jumps {
            intensity: 0.3,
            mean_log_jump: -0.1,
            log_jump_vol: 0.15,
        };
        let b = bates_price(&mkt(true), &[100.0], &H, &j).unwrap();
        assert!((b[0] - 9.03996849291532).abs() < 1e-8);
        let none = Jumps {
            intensity: 0.0,
            ..j
        };
        let h0 = heston_price(&mkt(true), &[100.0], &H).unwrap();
        assert!((bates_price(&mkt(true), &[100.0], &H, &none).unwrap()[0] - h0[0]).abs() < 1e-12);
        let mj = Jumps {
            intensity: 0.5,
            mean_log_jump: -0.1,
            log_jump_vol: 0.2,
        };
        let mp = merton_price(&mkt(true), &[100.0], 0.2, &mj).unwrap();
        assert!((mp[0] - 10.528655435053093).abs() < 1e-8);
        // Lewis route agrees with the series.
        let phi = |u: C| (-(u * u + I * u) * (0.2 * 0.2 / 2.0)).exp() * mj.cf(u, 1.0);
        assert!((lewis(&mkt(true), &[100.0], &phi)[0] - mp[0]).abs() < 1e-8);
        let m = mkt(true);
        let bs = merton_price(
            &m,
            &[90.0],
            0.2,
            &Jumps {
                intensity: 0.0,
                ..mj
            },
        )
        .unwrap();
        let want = black(true, m.forward(), 90.0, 0.2, 1.0, (-0.03f64).exp());
        assert!((bs[0] - want).abs() < 1e-12);
        assert_eq!(
            merton_price(&m, &[90.0], 0.0, &mj).unwrap_err().code,
            "E_DOMAIN"
        );
        let bad = Jumps {
            intensity: -1.0,
            ..mj
        };
        assert_eq!(
            bates_price(&m, &[90.0], &H, &bad).unwrap_err().code,
            "E_DOMAIN"
        );
        let put = merton_price(&mkt(false), &[90.0], 0.2, &mj).unwrap()[0];
        let call = merton_price(&m, &[90.0], 0.2, &mj).unwrap()[0];
        assert!((call - put - (-0.03f64).exp() * (m.forward() - 90.0)).abs() < 1e-10);
    }

    #[test]
    fn rows_keep_mass_with_no_flux() {
        let mu = [0.3, -0.1, 0.2, -0.4, 0.1];
        let s = [0.2, 0.3, 0.1, 0.4, 0.2];
        let (lo, di, up) = rows(&mu, &s, 0.1, 0.01, true);
        for k in 0..5 {
            let col =
                di[k] + if k > 0 { up[k - 1] } else { 0.0 } + if k < 4 { lo[k + 1] } else { 0.0 };
            assert!((col - 1.0).abs() < 1e-14, "{k}");
        }
        let mut rhs = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let want = rhs.clone();
        thomas(&lo, &di, &up, &mut rhs);
        for k in 0..5 {
            let back = di[k] * rhs[k]
                + if k > 0 { lo[k] * rhs[k - 1] } else { 0.0 }
                + if k < 4 { up[k] * rhs[k + 1] } else { 0.0 };
            assert!((back - want[k]).abs() < 1e-12);
        }
    }

    fn flat() -> Vec<Slice> {
        let s = Svi {
            a: 0.04,
            b: 0.0,
            rho: 0.0,
            m: 0.0,
            sigma: 0.1,
        };
        vec![Slice {
            expiry_years: 1.0,
            svi: s,
        }]
    }

    #[test]
    fn slv_flat_limit_and_checks() {
        let h = Heston {
            v0: 0.04,
            kappa: 2.0,
            theta: 0.04,
            xi: 0.3,
            rho: 0.0,
        };
        let m = Market {
            rate: 0.0,
            dividend_yield: 0.0,
            ..mkt(true)
        };
        let g = Grid {
            nx: 41,
            nv: 30,
            nt: 20,
            x_min: 100f64.ln() - 1.0,
            x_max: 100f64.ln() + 1.0,
            v_max: 0.3,
        };
        let r = slv_leverage(&m, &h, &flat(), &g).unwrap();
        assert!(r.mass > 0.95 && r.mass < 1.01);
        let mid = r.leverage[20];
        assert!((mid - 1.0).abs() < 0.05, "{mid}");
        let code = |g: Grid| slv_leverage(&m, &h, &flat(), &g).unwrap_err().code;
        assert_eq!(code(Grid { nx: 4, ..g }), "E_INPUT");
        assert_eq!(code(Grid { nt: 1, ..g }), "E_INPUT");
        assert_eq!(code(Grid { x_min: 5.0, ..g }), "E_INPUT");
        assert_eq!(code(Grid { v_max: 0.0, ..g }), "E_DOMAIN");
    }
}
