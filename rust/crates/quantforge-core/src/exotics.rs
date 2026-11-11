//! Stage E5 exotic options and American exercise (`04-pricing/exotics.md`, rulings E-A19 to
//! E-A23).

use crate::error::{Result, fail};
use crate::stats::normal_cdf as n;

fn phi(call: bool) -> f64 {
    if call { 1.0 } else { -1.0 }
}

/// Common inputs: spot, strike, expiry, rate, dividend yield, vol, option type.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Vanilla {
    pub spot: f64,
    pub strike: f64,
    pub expiry_years: f64,
    pub rate: f64,
    pub dividend_yield: f64,
    pub vol: f64,
    pub call: bool,
}

impl Vanilla {
    pub fn check(&self) -> Result<()> {
        crate::error::finite("self", self)?;
        if [self.spot, self.strike, self.expiry_years, self.vol]
            .iter()
            .all(|v| *v > 0.0)
        {
            Ok(())
        } else {
            fail(
                "E_DOMAIN",
                "spot, strike, expiry_years and vol must be above 0",
            )
        }
    }

    fn carry(&self) -> f64 {
        self.rate - self.dividend_yield
    }

    fn d1_d2(&self) -> (f64, f64) {
        let sd = self.vol * self.expiry_years.sqrt();
        let d1 = ((self.spot / self.strike).ln()
            + (self.carry() + self.vol * self.vol / 2.0) * self.expiry_years)
            / sd;
        (d1, d1 - sd)
    }
}

/// Generalised Black-Scholes.
/// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
pub fn gbs(call: bool, s: f64, k: f64, t: f64, r: f64, b: f64, v: f64) -> f64 {
    let sd = v * t.sqrt();
    let d1 = ((s / k).ln() + (b + v * v / 2.0) * t) / sd;
    let d2 = d1 - sd;
    let p = phi(call);
    p * (s * ((b - r) * t).exp() * n(p * d1) - k * (-r * t).exp() * n(p * d2))
}

pub fn digital(x: &Vanilla, cash_or_nothing: bool, cash: f64) -> Result<f64> {
    crate::error::finite("x", &x)?;
    crate::error::finite("cash", &cash)?;
    x.check()?;
    if cash.is_nan() || cash <= 0.0 {
        return fail("E_DOMAIN", "cash must be above 0");
    }
    let (d1, d2) = x.d1_d2();
    let p = phi(x.call);
    Ok(if cash_or_nothing {
        cash * (-x.rate * x.expiry_years).exp() * n(p * d2)
    } else {
        x.spot * (-x.dividend_yield * x.expiry_years).exp() * n(p * d1)
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BarrierType {
    DownIn,
    DownOut,
    UpIn,
    UpOut,
}

/// Reiner-Rubinstein, continuous monitoring; a touched barrier is `E_DOMAIN` (ruling E-A19).
/// BGK constant for discrete monitoring, pinned to four digits (ruling G-7).
pub const BGK_BETA: f64 = 0.5826;

/// Discretely monitored barrier by the Broadie-Glasserman-Kou continuity correction:
/// the continuous price with the barrier moved away from spot by `exp(beta v sqrt(1/m))`.
/// The domain check uses the unshifted barrier (ruling G-8).
pub fn barrier_discrete(
    x: &Vanilla,
    h: f64,
    rebate: f64,
    kind: BarrierType,
    monitoring_per_year: i64,
) -> Result<f64> {
    if monitoring_per_year < 1 {
        return fail("E_DOMAIN", "monitoring_per_year must be at least 1");
    }
    crate::error::finite("x", &x)?;
    crate::error::finite("h", &h)?;
    x.check()?;
    let down = matches!(kind, BarrierType::DownIn | BarrierType::DownOut);
    if h <= 0.0 || (down && x.spot <= h) || (!down && x.spot >= h) {
        // Delegate so the error text and code match the continuous rule.
        return barrier(x, h, rebate, kind);
    }
    #[allow(clippy::cast_precision_loss)]
    let dt = 1.0 / monitoring_per_year as f64;
    let shift = (BGK_BETA * x.vol * dt.sqrt()).exp();
    let hs = if down { h / shift } else { h * shift };
    barrier(x, hs, rebate, kind)
}

/// Continuously monitored single-barrier option (Reiner-Rubinstein, stage E).
pub fn barrier(x: &Vanilla, h: f64, rebate: f64, kind: BarrierType) -> Result<f64> {
    use BarrierType::{DownIn, DownOut, UpIn, UpOut};
    crate::error::finite("x", &x)?;
    crate::error::finite("h", &h)?;
    crate::error::finite("rebate", &rebate)?;
    x.check()?;
    if h.is_nan() || h <= 0.0 || rebate.is_nan() || rebate < 0.0 {
        return fail("E_DOMAIN", "barrier must be above 0 and rebate at least 0");
    }
    let down = matches!(kind, BarrierType::DownIn | BarrierType::DownOut);
    let s = x.spot;
    if (down && s <= h) || (!down && s >= h) {
        return fail("E_DOMAIN", "spot is on or beyond the barrier");
    }
    let (k, t, r, b, v) = (x.strike, x.expiry_years, x.rate, x.carry(), x.vol);
    let sd = v * t.sqrt();
    let mu = (b - v * v / 2.0) / (v * v);
    let lambda = (mu * mu + 2.0 * r / (v * v)).sqrt();
    let p = phi(x.call);
    let eta = if down { 1.0 } else { -1.0 };
    let x1 = (s / k).ln() / sd + (1.0 + mu) * sd;
    let x2 = (s / h).ln() / sd + (1.0 + mu) * sd;
    let y1 = (h * h / (s * k)).ln() / sd + (1.0 + mu) * sd;
    let y2 = (h / s).ln() / sd + (1.0 + mu) * sd;
    let z = (h / s).ln() / sd + lambda * sd;
    let (gs, gk) = (s * ((b - r) * t).exp(), k * (-r * t).exp());
    let hs = h / s;
    let ab = |xx: f64| p * gs * n(p * xx) - p * gk * n(p * xx - p * sd);
    let cd = |yy: f64| {
        p * gs * hs.powf(2.0 * (mu + 1.0)) * n(eta * yy)
            - p * gk * hs.powf(2.0 * mu) * n(eta * yy - eta * sd)
    };
    let (a, bb, c, d) = (ab(x1), ab(x2), cd(y1), cd(y2));
    let e = rebate
        * (-r * t).exp()
        * (n(eta * x2 - eta * sd) - hs.powf(2.0 * mu) * n(eta * y2 - eta * sd));
    let f = rebate
        * (hs.powf(mu + lambda) * n(eta * z)
            + hs.powf(mu - lambda) * n(eta * z - 2.0 * eta * lambda * sd));
    let above = k > h;
    Ok(match (kind, x.call, above) {
        (DownIn, true, true) | (UpIn, false, false) => c + e,
        (DownIn, true, false) | (UpIn, false, true) => a - bb + d + e,
        (UpIn, true, true) | (DownIn, false, false) => a + e,
        (UpIn, true, false) | (DownIn, false, true) => bb - c + d + e,
        (DownOut, true, true) | (UpOut, false, false) => a - c + f,
        (DownOut, true, false) | (UpOut, false, true) => bb - d + f,
        (UpOut, true, true) | (DownOut, false, false) => f,
        (UpOut, true, false) | (DownOut, false, true) => a - bb + c - d + f,
    })
}

/// Geometric average-price Asian: continuous (Kemna-Vorst) when `fixings` is `None`.
pub fn asian_geometric(x: &Vanilla, fixings: Option<&[f64]>) -> Result<f64> {
    crate::error::finite("x", &x)?;
    crate::error::finite("fixings", &fixings)?;
    let (s, k, t, r, b, v) = (x.spot, x.strike, x.expiry_years, x.rate, x.carry(), x.vol);
    // Input order (ruling E-A38): the common checks come before `fixing_years`.
    x.check()?;
    if let Some(f) = fixings {
        let bad = f.is_empty()
            || f.windows(2).any(|w| w[1] <= w[0])
            || f.iter().any(|&u| !(u > 0.0 && u <= t));
        if bad {
            return fail("E_INPUT", "fixings must increase strictly, each in (0, T]");
        }
    }
    let Some(f) = fixings else {
        return Ok(gbs(
            x.call,
            s,
            k,
            t,
            r,
            (b - v * v / 6.0) / 2.0,
            v / 3f64.sqrt(),
        ));
    };
    let nf = f.len() as f64;
    let m = s.ln() + (b - v * v / 2.0) * f.iter().sum::<f64>() / nf;
    let sum: f64 = f
        .iter()
        .flat_map(|a| f.iter().map(move |c| a.min(*c)))
        .sum();
    let var = v * v * sum / (nf * nf);
    let d1 = (m - k.ln() + var) / var.sqrt();
    let d2 = d1 - var.sqrt();
    let (fwd, disc) = ((m + var / 2.0).exp(), (-r * t).exp());
    Ok(if x.call {
        disc * (fwd * n(d1) - k * n(d2))
    } else {
        disc * (k * n(-d2) - fwd * n(-d1))
    })
}

/// Goldman-Sosin-Gatto floating-strike lookback; `strike` is unused. `b = 0` is `E_DOMAIN`.
pub fn lookback_floating(x: &Vanilla, extreme: f64) -> Result<f64> {
    crate::error::finite("x", &x)?;
    crate::error::finite("extreme", &extreme)?;
    let (s, t, r, b, v) = (x.spot, x.expiry_years, x.rate, x.carry(), x.vol);
    if !(s > 0.0 && t > 0.0 && v > 0.0) {
        return fail("E_DOMAIN", "spot, expiry_years and vol must be above 0");
    }
    if extreme.is_nan() || (x.call && !(extreme > 0.0 && extreme <= s)) || (!x.call && extreme < s)
    {
        return fail(
            "E_DOMAIN",
            "running minimum must be at most spot (call), maximum at least spot (put)",
        );
    }
    if b.abs() <= 1e-8 * v * v {
        // Ruling E-A28: near zero carry the closed form loses all accuracy.
        return fail(
            "E_DOMAIN",
            "carry too close to zero: the closed form divides by b",
        );
    }
    let sq = t.sqrt();
    let e1 = (s / extreme).ln() + (b + v * v / 2.0) * t;
    let a1 = e1 / (v * sq);
    let a2 = a1 - v * sq;
    let (gs, disc) = (s * ((b - r) * t).exp(), (-r * t).exp());
    let k = s * disc * v * v / (2.0 * b);
    let pw = (s / extreme).powf(-2.0 * b / (v * v));
    Ok(if x.call {
        gs * n(a1) - extreme * disc * n(a2)
            + k * (pw * n(-a1 + 2.0 * b * sq / v) - (b * t).exp() * n(-a1))
    } else {
        -gs * n(-a1)
            + extreme * disc * n(-a2)
            + k * (-pw * n(a1 - 2.0 * b * sq / v) + (b * t).exp() * n(a1))
    })
}

pub struct Quanto {
    pub spot: f64,
    pub strike: f64,
    pub expiry_years: f64,
    pub domestic_rate: f64,
    pub foreign_rate: f64,
    pub dividend_yield: f64,
    pub vol: f64,
    pub fx_vol: f64,
    pub correlation: f64,
    pub call: bool,
}

pub fn quanto(x: &Quanto) -> Result<f64> {
    crate::error::finite("x", &x)?;
    let pos = [x.spot, x.strike, x.expiry_years, x.vol, x.fx_vol];
    if !pos.iter().all(|v| *v > 0.0) || !(-1.0..=1.0).contains(&x.correlation) {
        return fail(
            "E_DOMAIN",
            "positive inputs and correlation in [-1, 1] required",
        );
    }
    let b = x.foreign_rate - x.dividend_yield - x.correlation * x.vol * x.fx_vol;
    Ok(gbs(
        x.call,
        x.spot,
        x.strike,
        x.expiry_years,
        x.domestic_rate,
        b,
        x.vol,
    ))
}

/// Rubinstein simple chooser; `call` is unused.
pub fn chooser(x: &Vanilla, choose: f64) -> Result<f64> {
    crate::error::finite("x", &x)?;
    crate::error::finite("choose", &choose)?;
    x.check()?;
    if !(choose > 0.0 && choose <= x.expiry_years) {
        return fail("E_INPUT", "choose_years must lie in (0, expiry_years]");
    }
    let (s, k, t, r, b, v) = (x.spot, x.strike, x.expiry_years, x.rate, x.carry(), x.vol);
    let d = ((s / k).ln() + (b + v * v / 2.0) * t) / (v * t.sqrt());
    let y = ((s / k).ln() + b * t + v * v * choose / 2.0) / (v * choose.sqrt());
    let (gs, gk) = (s * ((b - r) * t).exp(), k * (-r * t).exp());
    Ok(gs * n(d) - gk * n(d - v * t.sqrt()) - gs * n(-y) + gk * n(-y + v * choose.sqrt()))
}

pub struct Spread {
    pub forward_1: f64,
    pub forward_2: f64,
    pub strike: f64,
    pub expiry_years: f64,
    pub rate: f64,
    pub vol_1: f64,
    pub vol_2: f64,
    pub correlation: f64,
}

/// Kirk's call on `F1 - F2 - K`.
pub fn kirk(x: &Spread) -> Result<f64> {
    crate::error::finite("x", &x)?;
    let pos = [x.forward_1, x.forward_2, x.expiry_years, x.vol_1, x.vol_2];
    if !pos.iter().all(|v| *v > 0.0) || !(-1.0..=1.0).contains(&x.correlation) {
        return fail(
            "E_DOMAIN",
            "forwards, expiry and vols above 0, correlation in [-1, 1]",
        );
    }
    let f2k = x.forward_2 + x.strike;
    if f2k.is_nan() || f2k <= 0.0 {
        return fail("E_DOMAIN", "forward_2 + strike must be above 0");
    }
    let f = x.forward_2 / f2k;
    let (v1, v2, t) = (x.vol_1, x.vol_2, x.expiry_years);
    let s = (v1 * v1 - 2.0 * x.correlation * v1 * v2 * f + v2 * v2 * f * f).sqrt();
    let d1 = ((x.forward_1 / f2k).ln() + s * s * t / 2.0) / (s * t.sqrt());
    Ok((-x.rate * t).exp() * (x.forward_1 * n(d1) - f2k * n(d1 - s * t.sqrt())))
}

pub struct Basket<'a> {
    pub forwards: &'a [f64],
    pub weights: &'a [f64],
    pub vols: &'a [f64],
    pub correlation: &'a [Vec<f64>],
    pub strike: f64,
    pub expiry_years: f64,
    pub rate: f64,
    pub call: bool,
}

/// `(price, basket_forward, basket_vol)` by lognormal moment matching.
pub fn basket(x: &Basket) -> Result<(f64, f64, f64)> {
    let k = x.forwards.len();
    let c = x.correlation;
    let shape = k >= 1
        && x.weights.len() == k
        && x.vols.len() == k
        && c.len() == k
        && c.iter().all(|r| r.len() == k);
    let corr_ok = shape
        && (0..k).all(|i| {
            c[i][i] == 1.0 && (0..k).all(|j| c[i][j] == c[j][i] && (-1.0..=1.0).contains(&c[i][j]))
        });
    if !corr_ok {
        return fail(
            "E_INPUT",
            "lengths must match and correlation be a valid correlation matrix",
        );
    }
    if x.weights.iter().any(|w| w.is_nan() || *w < 0.0) || x.weights.iter().all(|w| *w == 0.0) {
        return fail("E_DOMAIN", "weights must be at least 0, not all 0");
    }
    let pos = x
        .forwards
        .iter()
        .chain(x.vols)
        .chain(&[x.strike, x.expiry_years])
        .all(|v| *v > 0.0);
    if !pos {
        return fail(
            "E_DOMAIN",
            "forwards, vols, strike and expiry must be above 0",
        );
    }
    let t = x.expiry_years;
    let m1: f64 = x.weights.iter().zip(x.forwards).map(|(w, f)| w * f).sum();
    let mut m2 = 0.0;
    for i in 0..k {
        for j in 0..k {
            let wf = x.weights[i] * x.weights[j] * x.forwards[i] * x.forwards[j];
            m2 += wf * (c[i][j] * x.vols[i] * x.vols[j] * t).exp();
        }
    }
    let vb = ((m2 / (m1 * m1)).ln() / t).sqrt();
    Ok((gbs(x.call, m1, x.strike, t, x.rate, 0.0, vb), m1, vb))
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Tree {
    pub american: f64,
    pub european: f64,
}

/// CRR with Hull's dividend-yield probability (ruling E-A23).
pub fn crr(x: &Vanilla, steps: i64) -> Result<Tree> {
    crate::error::finite("x", &x)?;
    if !(1..=20_000).contains(&steps) {
        return fail("E_INPUT", "steps must be 1 to 20,000");
    }
    x.check()?;
    let ns = usize::try_from(steps).unwrap_or(1);
    let dt = x.expiry_years / steps as f64;
    let u = (x.vol * dt.sqrt()).exp();
    let d = 1.0 / u;
    let p = ((x.carry() * dt).exp() - d) / (u - d);
    if !(p > 0.0 && p < 1.0) {
        return fail("E_DOMAIN", "up-move probability outside (0, 1)");
    }
    let disc = (-x.rate * dt).exp();
    let pf = phi(x.call);
    let payoff = |i: usize, j: usize| {
        let s = x.spot * u.powi(i32::try_from(i).unwrap_or(0) - 2 * i32::try_from(j).unwrap_or(0));
        (pf * (s - x.strike)).max(0.0)
    };
    let mut am: Vec<f64> = (0..=ns).map(|j| payoff(ns, j)).collect();
    let mut eu = am.clone();
    for i in (0..ns).rev() {
        for j in 0..=i {
            eu[j] = disc * (p * eu[j] + (1.0 - p) * eu[j + 1]);
            am[j] = (disc * (p * am[j] + (1.0 - p) * am[j + 1])).max(payoff(i, j));
        }
    }
    Ok(Tree {
        american: am[0],
        european: eu[0],
    })
}

/// Bisection on `[lo, hi]` with `f(lo)` and `f(hi)` of opposite sign, to the last midpoint.
fn bisect(f: &dyn Fn(f64) -> f64, mut lo: f64, mut hi: f64) -> f64 {
    let low_neg = f(lo) < 0.0;
    for _ in 0..2000 {
        let mid = 0.5 * (lo + hi);
        if mid <= lo || mid >= hi {
            break;
        }
        if (f(mid) < 0.0) == low_neg {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    0.5 * (lo + hi)
}

/// Barone-Adesi-Whaley; `r = 0` is `E_DOMAIN` (ruling E-A22).
pub fn baw(x: &Vanilla) -> Result<f64> {
    crate::error::finite("x", &x)?;
    x.check()?;
    let (s, k, t, r, b, v) = (x.spot, x.strike, x.expiry_years, x.rate, x.carry(), x.vol);
    if r.is_nan() || r <= 0.0 {
        // Ruling E-A30: 1 - e^{-rT} <= 0 and the put critical price has no root.
        return fail("E_DOMAIN", "BAW needs r > 0");
    }
    if x.call && b >= r {
        return Ok(gbs(true, s, k, t, r, b, v));
    }
    let (m, nn, kt) = (2.0 * r / (v * v), 2.0 * b / (v * v), 1.0 - (-r * t).exp());
    let root = ((nn - 1.0) * (nn - 1.0) + 4.0 * m / kt).sqrt();
    let carry = ((b - r) * t).exp();
    let d1 = |sx: f64| ((sx / k).ln() + (b + v * v / 2.0) * t) / (v * t.sqrt());
    if x.call {
        let q2 = (-(nn - 1.0) + root) / 2.0;
        let g =
            |sx: f64| sx - k - gbs(true, sx, k, t, r, b, v) - (1.0 - carry * n(d1(sx))) * sx / q2;
        let mut hi = 2.0 * k;
        while g(hi) < 0.0 {
            hi *= 2.0;
            if hi > 1e12 * k {
                return fail("E_NO_CONVERGENCE", "no critical price found");
            }
        }
        let crit = bisect(&g, k, hi);
        let a2 = crit / q2 * (1.0 - carry * n(d1(crit)));
        Ok(if s < crit {
            gbs(true, s, k, t, r, b, v) + a2 * (s / crit).powf(q2)
        } else {
            s - k
        })
    } else {
        let q1 = (-(nn - 1.0) - root) / 2.0;
        let g =
            |sx: f64| k - sx - gbs(false, sx, k, t, r, b, v) + (1.0 - carry * n(-d1(sx))) * sx / q1;
        let crit = bisect(&g, k * 1e-9, k);
        let a1 = -crit / q1 * (1.0 - carry * n(-d1(crit)));
        Ok(if s > crit {
            gbs(false, s, k, t, r, b, v) + a1 * (s / crit).powf(q1)
        } else {
            k - s
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FdGrid {
    pub nx: i64,
    pub nt: i64,
    pub width: f64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Fd {
    pub price: f64,
    pub delta: f64,
    pub gamma: f64,
}

/// Backward-Euler reference scheme in `ln S` with exercise projection (ruling E-A23).
pub fn american_fd(x: &Vanilla, american: bool, g: &FdGrid) -> Result<Fd> {
    crate::error::finite("x", &x)?;
    crate::error::finite("g", &g)?;
    if g.nx < 5 || g.nx % 2 == 0 || g.nt < 1 {
        return fail("E_INPUT", "nx must be odd and at least 5, nt at least 1");
    }
    x.check()?;
    if g.width.is_nan() || g.width <= 0.0 {
        return fail("E_DOMAIN", "width must be above 0");
    }
    let nx = usize::try_from(g.nx).unwrap_or(5);
    let (s, k, t, r, q, v) = (
        x.spot,
        x.strike,
        x.expiry_years,
        x.rate,
        x.dividend_yield,
        x.vol,
    );
    let h = g.width * v * t.sqrt();
    let dx = 2.0 * h / (nx - 1) as f64;
    let dt = t / g.nt as f64;
    let xs: Vec<f64> = (0..nx).map(|i| s.ln() - h + i as f64 * dx).collect();
    let pf = phi(x.call);
    let payoff: Vec<f64> = xs.iter().map(|xi| (pf * (xi.exp() - k)).max(0.0)).collect();
    let mu = r - q - v * v / 2.0;
    let lo_c = -dt * (v * v / (2.0 * dx * dx) - mu / (2.0 * dx));
    let di_c = 1.0 + dt * (v * v / (dx * dx) + r);
    let up_c = -dt * (v * v / (2.0 * dx * dx) + mu / (2.0 * dx));
    let (mut lo, mut di, mut up) = (vec![lo_c; nx], vec![di_c; nx], vec![up_c; nx]);
    for e in [0, nx - 1] {
        (lo[e], di[e], up[e]) = (0.0, 1.0, 0.0);
    }
    let mut val = payoff.clone();
    for step in 0..g.nt {
        let tau = (step + 1) as f64 * dt;
        let edge = |i: usize| {
            if american {
                payoff[i]
            } else {
                (pf * (xs[i].exp() * (-q * tau).exp() - k * (-r * tau).exp())).max(0.0)
            }
        };
        val[0] = edge(0);
        val[nx - 1] = edge(nx - 1);
        crate::heston::thomas(&lo, &di, &up, &mut val);
        if american {
            for (vi, pi) in val.iter_mut().zip(&payoff) {
                *vi = vi.max(*pi);
            }
        }
    }
    let c = (nx - 1) / 2;
    let (vm, v0, vp) = (val[c - 1], val[c], val[c + 1]);
    Ok(Fd {
        price: v0,
        delta: (vp - vm) / (2.0 * dx * s),
        gamma: ((vp - 2.0 * v0 + vm) / (dx * dx) - (vp - vm) / (2.0 * dx)) / (s * s),
    })
}

impl crate::error::Finite for Fd {
    fn is_all_finite(&self) -> bool {
        self.price.is_all_finite() && self.delta.is_all_finite() && self.gamma.is_all_finite()
    }
}

impl crate::error::Finite for FdGrid {
    fn is_all_finite(&self) -> bool {
        self.width.is_all_finite()
    }
}

impl crate::error::Finite for Quanto {
    fn is_all_finite(&self) -> bool {
        self.spot.is_all_finite()
            && self.strike.is_all_finite()
            && self.expiry_years.is_all_finite()
            && self.domestic_rate.is_all_finite()
            && self.foreign_rate.is_all_finite()
            && self.dividend_yield.is_all_finite()
            && self.vol.is_all_finite()
            && self.fx_vol.is_all_finite()
            && self.correlation.is_all_finite()
    }
}

impl crate::error::Finite for Spread {
    fn is_all_finite(&self) -> bool {
        self.forward_1.is_all_finite()
            && self.forward_2.is_all_finite()
            && self.strike.is_all_finite()
            && self.expiry_years.is_all_finite()
            && self.rate.is_all_finite()
            && self.vol_1.is_all_finite()
            && self.vol_2.is_all_finite()
            && self.correlation.is_all_finite()
    }
}

impl crate::error::Finite for Tree {
    fn is_all_finite(&self) -> bool {
        self.american.is_all_finite() && self.european.is_all_finite()
    }
}

impl crate::error::Finite for Vanilla {
    fn is_all_finite(&self) -> bool {
        self.spot.is_all_finite()
            && self.strike.is_all_finite()
            && self.expiry_years.is_all_finite()
            && self.rate.is_all_finite()
            && self.dividend_yield.is_all_finite()
            && self.vol.is_all_finite()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base(call: bool) -> Vanilla {
        Vanilla {
            spot: 100.0,
            strike: 100.0,
            expiry_years: 1.0,
            rate: 0.05,
            dividend_yield: 0.02,
            vol: 0.25,
            call,
        }
    }

    #[test]
    fn digitals_sum_to_vanilla() {
        let x = Vanilla {
            strike: 105.0,
            ..base(true)
        };
        assert!((digital(&x, true, 10.0).unwrap() - 4.001607857388726).abs() < 1e-12);
        let asset = digital(&x, false, 1.0).unwrap();
        let cash = digital(&x, true, 105.0).unwrap();
        let v = gbs(true, 100.0, 105.0, 1.0, 0.05, 0.03, 0.25);
        assert!((asset - cash - v).abs() < 1e-12);
        let put = digital(&Vanilla { call: false, ..x }, true, 1.0).unwrap();
        assert!((put + cash / 105.0 - (-0.05f64).exp()).abs() < 1e-12);
        assert_eq!(digital(&x, true, 0.0).unwrap_err().code, "E_DOMAIN");
        assert_eq!(
            digital(&Vanilla { vol: 0.0, ..x }, true, 1.0)
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn barrier_in_out_parity_and_golden() {
        use BarrierType::*;
        let di = barrier(&base(true), 90.0, 0.0, DownIn).unwrap();
        assert!((di - 2.9849513804335466).abs() < 1e-12);
        for call in [true, false] {
            for (k, h_down, h_up) in [
                (100.0, 90.0, 110.0),
                (95.0, 97.0, 120.0),
                (115.0, 90.0, 105.0),
            ] {
                let x = Vanilla {
                    strike: k,
                    ..base(call)
                };
                let v = gbs(call, 100.0, k, 1.0, 0.05, 0.03, 0.25);
                let d = barrier(&x, h_down, 0.0, DownIn).unwrap()
                    + barrier(&x, h_down, 0.0, DownOut).unwrap();
                let u =
                    barrier(&x, h_up, 0.0, UpIn).unwrap() + barrier(&x, h_up, 0.0, UpOut).unwrap();
                assert!((d - v).abs() < 1e-10 && (u - v).abs() < 1e-10, "{call} {k}");
            }
        }
        let with = barrier(&base(true), 90.0, 3.0, DownOut).unwrap();
        assert!(with > barrier(&base(true), 90.0, 0.0, DownOut).unwrap());
        assert!(barrier(&base(true), 90.0, 3.0, UpIn).is_err());
        assert_eq!(
            barrier(&base(true), 100.0, 0.0, DownIn).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            barrier(&base(true), 90.0, -1.0, DownIn).unwrap_err().code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn asians() {
        let c = asian_geometric(&base(true), None).unwrap();
        assert!((c - 5.980198553960612).abs() < 1e-12);
        let fine: Vec<f64> = (1..=2000).map(|i| f64::from(i) / 2000.0).collect();
        let d = asian_geometric(&base(true), Some(&fine)).unwrap();
        assert!((d - c).abs() < 0.01);
        let p = asian_geometric(&base(false), Some(&[0.5, 1.0])).unwrap();
        assert!(p > 0.0);
        for bad in [&[0.5, 0.5][..], &[0.5, 1.5][..], &[][..]] {
            assert_eq!(
                asian_geometric(&base(true), Some(bad)).unwrap_err().code,
                "E_INPUT"
            );
        }
    }

    #[test]
    fn lookbacks() {
        assert!((lookback_floating(&base(true), 100.0).unwrap() - 19.29808796226954).abs() < 1e-11);
        assert!(lookback_floating(&base(false), 110.0).unwrap() > 0.0);
        assert_eq!(
            lookback_floating(&base(true), 101.0).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            lookback_floating(&base(false), 99.0).unwrap_err().code,
            "E_DOMAIN"
        );
        let zero = Vanilla {
            dividend_yield: 0.05,
            ..base(true)
        };
        assert_eq!(
            lookback_floating(&zero, 100.0).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            lookback_floating(
                &Vanilla {
                    vol: 0.0,
                    ..base(true)
                },
                100.0
            )
            .unwrap_err()
            .code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn quanto_chooser_kirk() {
        let q = Quanto {
            spot: 100.0,
            strike: 100.0,
            expiry_years: 1.0,
            domestic_rate: 0.05,
            foreign_rate: 0.01,
            dividend_yield: 0.02,
            vol: 0.25,
            fx_vol: 0.1,
            correlation: 0.3,
            call: true,
        };
        assert!((quanto(&q).unwrap() - 8.578183366673422).abs() < 1e-12);
        assert_eq!(
            quanto(&Quanto {
                correlation: 1.5,
                ..q
            })
            .unwrap_err()
            .code,
            "E_DOMAIN"
        );
        let x = base(true);
        let ch = chooser(&x, 0.4986301369863014).unwrap();
        assert!((ch - 16.56529607245119).abs() < 1e-11);
        let at_t = chooser(&x, 1.0).unwrap();
        let straddle = gbs(true, 100.0, 100.0, 1.0, 0.05, 0.03, 0.25)
            + gbs(false, 100.0, 100.0, 1.0, 0.05, 0.03, 0.25);
        assert!((at_t - straddle).abs() < 1e-12);
        assert_eq!(chooser(&x, 1.5).unwrap_err().code, "E_INPUT");
        let s = Spread {
            forward_1: 110.0,
            forward_2: 100.0,
            strike: 5.0,
            expiry_years: 1.0,
            rate: 0.03,
            vol_1: 0.3,
            vol_2: 0.25,
            correlation: 0.7,
        };
        assert!((kirk(&s).unwrap() - 11.60788492945142).abs() < 1e-11);
        assert_eq!(
            kirk(&Spread {
                strike: -100.0,
                ..s
            })
            .unwrap_err()
            .code,
            "E_DOMAIN"
        );
        assert_eq!(
            kirk(&Spread { vol_1: 0.0, ..s }).unwrap_err().code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn baskets() {
        let c = vec![
            vec![1.0, 0.5, 0.5],
            vec![0.5, 1.0, 0.5],
            vec![0.5, 0.5, 1.0],
        ];
        let x = Basket {
            forwards: &[100.0, 50.0, 80.0],
            weights: &[0.3, 0.5, 0.2],
            vols: &[0.2, 0.3, 0.25],
            correlation: &c,
            strike: 71.0,
            expiry_years: 1.0,
            rate: 0.03,
            call: true,
        };
        let (p, m1, vb) = basket(&x).unwrap();
        assert!(
            (p - 5.5778689776598185).abs() < 1e-12
                && m1 == 71.0
                && (vb - 0.20327122737943645).abs() < 1e-14
        );
        let bad = vec![
            vec![1.0, 0.5, 0.4],
            vec![0.5, 1.0, 0.5],
            vec![0.5, 0.5, 1.0],
        ];
        assert_eq!(
            basket(&Basket {
                correlation: &bad,
                ..x
            })
            .unwrap_err()
            .code,
            "E_INPUT"
        );
        assert_eq!(
            basket(&Basket {
                weights: &[0.3, -0.5, 0.2],
                ..x
            })
            .unwrap_err()
            .code,
            "E_DOMAIN"
        );
        assert_eq!(
            basket(&Basket {
                weights: &[0.0; 3],
                ..x
            })
            .unwrap_err()
            .code,
            "E_DOMAIN"
        );
        assert_eq!(
            basket(&Basket {
                vols: &[0.2, 0.0, 0.25],
                ..x
            })
            .unwrap_err()
            .code,
            "E_DOMAIN"
        );
    }

    #[test]
    fn american_methods_agree() {
        let x = base(false);
        let t = crr(&x, 50).unwrap();
        assert!((t.american - 8.539077470526058).abs() < 1e-10);
        assert!((t.european - 8.178595703863163).abs() < 1e-10);
        let b = baw(&x).unwrap();
        assert!((b - 8.580054049689823).abs() < 1e-5);
        let f = american_fd(
            &x,
            true,
            &FdGrid {
                nx: 201,
                nt: 200,
                width: 5.0,
            },
        )
        .unwrap();
        assert!((f.price - 8.549268504869268).abs() < 1e-8);
        let e = american_fd(
            &x,
            false,
            &FdGrid {
                nx: 201,
                nt: 200,
                width: 5.0,
            },
        )
        .unwrap();
        assert!((e.price - gbs(false, 100.0, 100.0, 1.0, 0.05, 0.03, 0.25)).abs() < 0.05);
        let call = baw(&base(true)).unwrap();
        assert!(call >= gbs(true, 100.0, 100.0, 1.0, 0.05, 0.03, 0.25) - 1e-12);
        let carry = Vanilla {
            dividend_yield: -0.01,
            ..base(true)
        };
        assert_eq!(
            baw(&carry).unwrap(),
            gbs(true, 100.0, 100.0, 1.0, 0.05, 0.06, 0.25)
        );
        let deep = Vanilla {
            spot: 40.0,
            ..base(false)
        };
        assert_eq!(baw(&deep).unwrap(), 60.0);
        assert_eq!(
            baw(&Vanilla { rate: 0.0, ..x }).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(crr(&x, 0).unwrap_err().code, "E_INPUT");
        let wild = Vanilla {
            rate: 5.0,
            vol: 0.01,
            ..x
        };
        assert_eq!(crr(&wild, 2).unwrap_err().code, "E_DOMAIN");
        assert_eq!(
            american_fd(
                &x,
                true,
                &FdGrid {
                    nx: 200,
                    nt: 10,
                    width: 5.0
                }
            )
            .unwrap_err()
            .code,
            "E_INPUT"
        );
        assert_eq!(
            american_fd(
                &x,
                true,
                &FdGrid {
                    nx: 21,
                    nt: 10,
                    width: 0.0
                }
            )
            .unwrap_err()
            .code,
            "E_DOMAIN"
        );
    }
}

#[cfg(test)]
mod bgk_acceptance {
    use super::*;

    /// R9 acceptance: daily down-and-out call and put against an exact-date Monte Carlo
    /// (40,000 paths, `core.rng` seed 20261109, stream 0), within 3 standard errors.
    #[test]
    fn daily_down_and_out_matches_exact_date_mc() {
        let (s0, k, h, r, q, v, t, m) = (100.0, 100.0, 90.0, 0.05, 0.02, 0.25, 1.0, 252);
        let paths = 40_000;
        let dt = t / f64::from(m);
        let drift = (r - q - v * v / 2.0) * dt;
        let vol = v * dt.sqrt();
        let mut g = crate::rng::Xoshiro::seeded(20_261_109, 0);
        let (mut sc, mut sc2, mut sp, mut sp2) = (0.0, 0.0, 0.0, 0.0);
        for _ in 0..paths {
            let mut x = s0;
            let mut alive = true;
            for _ in 0..m {
                x *= (drift + vol * g.next_normal()).exp();
                if x <= h {
                    alive = false;
                }
            }
            let df = (-r * t).exp();
            let (c, p) = if alive {
                (df * (x - k).max(0.0), df * (k - x).max(0.0))
            } else {
                (0.0, 0.0)
            };
            sc += c;
            sc2 += c * c;
            sp += p;
            sp2 += p * p;
        }
        let nf = f64::from(paths);
        let stat = |s: f64, s2: f64| {
            let mean = s / nf;
            (mean, ((s2 - nf * mean * mean) / (nf - 1.0) / nf).sqrt())
        };
        for (call, (mean, se)) in [(true, stat(sc, sc2)), (false, stat(sp, sp2))] {
            let x = Vanilla {
                spot: s0,
                strike: k,
                expiry_years: t,
                rate: r,
                dividend_yield: q,
                vol: v,
                call,
            };
            let bgk = barrier_discrete(&x, h, 0.0, BarrierType::DownOut, m.into()).unwrap();
            assert!(
                (bgk - mean).abs() < 3.0 * se,
                "call={call} bgk={bgk} mc={mean} se={se}"
            );
            if call {
                // The continuous price is outside 3 SE of the call: the check discriminates.
                let cont = barrier(&x, h, 0.0, BarrierType::DownOut).unwrap();
                assert!((cont - mean).abs() > 3.0 * se);
            }
        }
    }
}
