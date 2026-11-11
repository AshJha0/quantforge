//! LIBOR market model: closed-form caps and floors, Rebonato swaptions, and the simulated
//! terminal-measure model (`04-pricing/lmm.md`, rulings G-22, G-25, G-26).
use crate::error::{Result, fail};
use crate::shortrate::HwCurve;
use crate::stats::normal_cdf;

/// The abcd instantaneous volatility `(a + b (T - t)) e^{-c (T - t)} + d` [BM 6.3.2].
#[derive(Debug, Clone, Copy)]
pub struct Abcd {
    /// `a`.
    pub a: f64,
    /// `b`.
    pub b: f64,
    /// `c`, positive.
    pub c: f64,
    /// `d`, non-negative.
    pub d: f64,
}

impl Abcd {
    /// Domain check: `c > 0`, `d >= 0`, `a + d > 0`.
    pub fn check(&self) -> Result<()> {
        crate::error::finite("abcd", &[self.a, self.b, self.c, self.d])?;
        if self.c <= 0.0 || self.d < 0.0 || self.a + self.d <= 0.0 {
            return fail("E_DOMAIN", "abcd needs c > 0, d >= 0 and a + d > 0");
        }
        Ok(())
    }

    /// `sigma_T(t)` for `t <= T`.
    pub fn vol(&self, fix: f64, t: f64) -> f64 {
        let s = fix - t;
        (self.a + self.b * s) * (-self.c * s).exp() + self.d
    }

    /// `C(Ti, Tj; u) = int_0^u sigma_Ti sigma_Tj dt`, composite 24-point Gauss-Legendre on
    /// unit-length pieces (the integrand is a smooth exponential-polynomial; agrees with the
    /// closed form to about 1e-15 relative).
    pub fn cov(&self, ti: f64, tj: f64, u: f64) -> f64 {
        if u <= 0.0 {
            return 0.0;
        }
        let rule = crate::integrate::gauss_legendre_rule(24);
        #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
        let pieces = (u.ceil() as usize).max(1);
        #[allow(clippy::cast_precision_loss)]
        let h = u / pieces as f64;
        let mut sum = 0.0;
        for k in 0..pieces {
            #[allow(clippy::cast_precision_loss)]
            let (lo, hi) = (k as f64 * h, (k + 1) as f64 * h);
            let (m, r) = (0.5 * (lo + hi), 0.5 * (hi - lo));
            for (x, w) in &rule {
                let t = m + r * x;
                sum += w * r * self.vol(ti, t) * self.vol(tj, t);
            }
        }
        sum
    }
}

/// Black-76 call (`call`) or put on a forward, undiscounted.
fn black(call: bool, f: f64, k: f64, v: f64) -> f64 {
    let d1 = ((f / k).ln() + v * v / 2.0) / v;
    let d2 = d1 - v;
    if call {
        f * normal_cdf(d1) - k * normal_cdf(d2)
    } else {
        k * normal_cdf(-d2) - f * normal_cdf(-d1)
    }
}

/// Output of [`capfloor`].
#[derive(Debug, Clone, PartialEq)]
pub struct CapValue {
    /// Sum of the caplets.
    pub price: f64,
    /// Caplet (or floorlet) prices.
    pub caplet_prices: Vec<f64>,
    /// Simple forward of each period.
    pub forward_rates: Vec<f64>,
    /// `v_i / sqrt(t_(i-1))`.
    pub black_vols: Vec<f64>,
}

/// `rates.lmm.capfloor`: Black caplets on the integrated abcd variance to each fixing.
pub fn capfloor(
    curve: &HwCurve,
    v: &Abcd,
    times: &[f64],
    strike: f64,
    cap: bool,
    notional: f64,
) -> Result<CapValue> {
    crate::error::finite("period_times", &times)?;
    crate::error::finite("strike", &strike)?;
    crate::error::finite("notional", &notional)?;
    v.check()?;
    if times.len() > 10_001 {
        return fail("E_LIMIT", "at most 10,000 periods");
    }
    if times.len() < 2 || times.windows(2).any(|w| w[1] <= w[0]) {
        return fail(
            "E_INPUT",
            "period_times needs at least two increasing times",
        );
    }
    if times[0] <= 0.0 {
        return fail("E_DOMAIN", "the first period time must be positive");
    }
    if strike <= 0.0 {
        return fail("E_DOMAIN", "strike must be positive (lognormal LMM)");
    }
    let p = |t: f64| curve.ln_discount(t).exp();
    let fwd: Vec<f64> = times
        .windows(2)
        .map(|w| (p(w[0]) / p(w[1]) - 1.0) / (w[1] - w[0]))
        .collect();
    if fwd.iter().any(|f| *f <= 0.0) {
        return fail("E_DOMAIN", "every forward rate must be positive");
    }
    let mut out = CapValue {
        price: 0.0,
        caplet_prices: Vec::new(),
        forward_rates: fwd.clone(),
        black_vols: Vec::new(),
    };
    for (w, f) in times.windows(2).zip(&fwd) {
        let var = v.cov(w[0], w[0], w[0]);
        let sd = var.sqrt();
        let c = notional * (w[1] - w[0]) * p(w[1]) * black(cap, *f, strike, sd);
        out.caplet_prices.push(c);
        out.black_vols.push(sd / w[0].sqrt());
        out.price += c;
    }
    Ok(out)
}

/// Output of [`swaption_rebonato`].
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SwaptionValue {
    /// Price.
    pub price: f64,
    /// Forward swap rate `S`.
    pub swap_rate: f64,
    /// Annuity `sum tau_i P(T_i)` per unit notional.
    pub annuity: f64,
    /// `v / sqrt(T_0)`.
    pub black_vol: f64,
}

/// `rates.lmm.swaption_rebonato`: Rebonato's frozen-weight swaption volatility with
/// correlation `exp(-beta |T_(i-1) - T_(j-1)|)` [BM 6.13, eq. 6.67].
#[allow(clippy::too_many_arguments)]
pub fn swaption_rebonato(
    curve: &HwCurve,
    v: &Abcd,
    beta: f64,
    expiry: f64,
    pay: &[f64],
    fixed_rate: f64,
    payer: bool,
    notional: f64,
) -> Result<SwaptionValue> {
    crate::error::finite("inputs", &[beta, expiry, fixed_rate, notional])?;
    v.check()?;
    if beta < 0.0 {
        return fail("E_DOMAIN", "correlation_beta must not be negative");
    }
    if expiry <= 0.0 {
        return fail("E_DOMAIN", "expiry_years must be positive");
    }
    crate::shortrate::check_payments(expiry, pay)?;
    if fixed_rate <= 0.0 {
        return fail("E_DOMAIN", "fixed_rate must be positive (lognormal LMM)");
    }
    let p = |t: f64| curve.ln_discount(t).exp();
    let n = pay.len();
    let starts: Vec<f64> = std::iter::once(expiry)
        .chain(pay[..n - 1].iter().copied())
        .collect();
    let tau: Vec<f64> = (0..n).map(|i| pay[i] - starts[i]).collect();
    let fwd: Vec<f64> = (0..n)
        .map(|i| (p(starts[i]) / p(pay[i]) - 1.0) / tau[i])
        .collect();
    if fwd.iter().any(|f| *f <= 0.0) {
        return fail("E_DOMAIN", "every forward rate must be positive");
    }
    let ann: f64 = (0..n).map(|i| tau[i] * p(pay[i])).sum();
    let w: Vec<f64> = (0..n).map(|i| tau[i] * p(pay[i]) / ann).collect();
    let s: f64 = (0..n).map(|i| w[i] * fwd[i]).sum();
    let mut var = 0.0;
    for i in 0..n {
        for j in 0..n {
            let rho = (-beta * (starts[i] - starts[j]).abs()).exp();
            var += w[i] * w[j] * fwd[i] * fwd[j] * rho * v.cov(starts[i], starts[j], expiry);
        }
    }
    let sd = (var / (s * s)).sqrt();
    Ok(SwaptionValue {
        price: notional * ann * black(payer, s, fixed_rate, sd),
        swap_rate: s,
        annuity: ann,
        black_vol: sd / expiry.sqrt(),
    })
}

/// Monte Carlo caplet values and standard errors under the terminal measure (ruling G-26):
/// log-Euler with a predictor-corrector drift, `sigma` at the step midpoint, fixings on step
/// boundaries, Cholesky correlation, `core.rng` stream 0 (one normal per forward per step) `exp(-beta |T_i - T_j|)`. `grid` is `T_0 = 0 < ... < T_N`;
/// caplet `k` (`k = 1..N-1`) is on the forward fixed at `T_k`, paid at `T_(k+1)`.
#[allow(clippy::too_many_arguments, clippy::many_single_char_names)]
pub fn simulate_caplets(
    curve: &HwCurve,
    v: &Abcd,
    beta: f64,
    grid: &[f64],
    strike: f64,
    paths: usize,
    steps_per_year: usize,
    seed: u64,
) -> Result<Vec<(f64, f64)>> {
    v.check()?;
    let nf = grid.len() - 1; // forwards on [T_i, T_(i+1)]
    let p = |t: f64| curve.ln_discount(t).exp();
    let tau: Vec<f64> = (0..nf).map(|i| grid[i + 1] - grid[i]).collect();
    let f0: Vec<f64> = (0..nf)
        .map(|i| (p(grid[i]) / p(grid[i + 1]) - 1.0) / tau[i])
        .collect();
    // Cholesky of rho.
    let mut l = vec![vec![0.0; nf]; nf];
    for i in 0..nf {
        for j in 0..=i {
            let rho = (-beta * (grid[i] - grid[j]).abs()).exp();
            let s: f64 = (0..j).map(|k| l[i][k] * l[j][k]).sum();
            l[i][j] = if i == j {
                (rho - s).sqrt()
            } else {
                (rho - s) / l[j][j]
            };
        }
    }
    let mut times = vec![0.0];
    for i in 1..nf {
        let (a, b) = (grid[i - 1], grid[i]);
        #[allow(
            clippy::cast_possible_truncation,
            clippy::cast_sign_loss,
            clippy::cast_precision_loss
        )]
        let n = ((b - a) * steps_per_year as f64).ceil().max(1.0) as usize;
        for s in 1..=n {
            #[allow(clippy::cast_precision_loss)]
            times.push(if s == n {
                b
            } else {
                a + (b - a) * s as f64 / n as f64
            });
        }
    }
    let mut g = crate::rng::Xoshiro::seeded(seed, 0);
    let mut acc = vec![(0.0_f64, 0.0_f64); nf];
    let pn = p(grid[nf]);
    let mut lf = vec![0.0; nf];
    let mut z = vec![0.0; nf];
    let mut dw = vec![0.0; nf];
    let mut snap = vec![vec![0.0; nf]; nf]; // snap[m][j] = F_j(T_m)
    let drift = |f: &[f64], sig: &[f64], k: usize, alive: usize| -> f64 {
        let mut m = 0.0;
        for j in (k + 1).max(alive)..nf {
            let rho = (-beta * (grid[k] - grid[j]).abs()).exp();
            m += rho * tau[j] * sig[j] * f[j] / (1.0 + tau[j] * f[j]);
        }
        -sig[k] * m
    };
    for _ in 0..paths {
        for i in 0..nf {
            lf[i] = f0[i].ln();
        }
        let mut f: Vec<f64> = f0.clone();
        snap[0].clone_from(&f0);
        let mut alive = 1; // forwards with index >= alive still evolve
        for w in times.windows(2) {
            let (t0, t1) = (w[0], w[1]);
            let dt = t1 - t0;
            let tm = 0.5 * (t0 + t1);
            let sig: Vec<f64> = (0..nf)
                .map(|k| if k >= alive { v.vol(grid[k], tm) } else { 0.0 })
                .collect();
            for zi in &mut z {
                *zi = g.next_normal();
            }
            for i in 0..nf {
                dw[i] = (0..=i).map(|k| l[i][k] * z[k]).sum::<f64>() * dt.sqrt();
            }
            let mu0: Vec<f64> = (0..nf)
                .map(|k| {
                    if k >= alive {
                        drift(&f, &sig, k, alive)
                    } else {
                        0.0
                    }
                })
                .collect();
            let mut pred = f.clone();
            for k in alive..nf {
                pred[k] = (lf[k] + (mu0[k] - sig[k] * sig[k] / 2.0) * dt + sig[k] * dw[k]).exp();
            }
            for k in alive..nf {
                let mu1 = drift(&pred, &sig, k, alive);
                lf[k] += (0.5 * (mu0[k] + mu1) - sig[k] * sig[k] / 2.0) * dt + sig[k] * dw[k];
            }
            for k in alive..nf {
                f[k] = lf[k].exp();
            }
            while alive < nf && grid[alive] <= t1 {
                snap[alive].clone_from(&f);
                alive += 1;
            }
        }
        // Caplet k pays tau_k max(F_k(T_k) - K, 0) at T_(k+1); numeraire P(t, T_N).
        for k in 1..nf {
            let mut prod = 1.0;
            for j in (k + 1)..nf {
                prod *= 1.0 + tau[j] * snap[k + 1][j];
            }
            let x = pn * tau[k] * (snap[k][k] - strike).max(0.0) * prod;
            acc[k].0 += x;
            acc[k].1 += x * x;
        }
    }
    #[allow(clippy::cast_precision_loss)]
    let n = paths as f64;
    Ok((1..nf)
        .map(|k| {
            let m = acc[k].0 / n;
            (m, ((acc[k].1 / n - m * m) * n / (n - 1.0) / n).sqrt())
        })
        .collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn curve() -> HwCurve {
        HwCurve::new(
            &[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
            &[0.985, 0.97, 0.94, 0.85, 0.70, 0.33],
        )
        .unwrap()
    }
    const HUMP: Abcd = Abcd {
        a: -0.06,
        b: 0.17,
        c: 0.54,
        d: 0.17,
    };

    #[test]
    fn flat_vol_and_parities() {
        let c = curve();
        let flat = Abcd {
            a: 0.0,
            b: 0.0,
            c: 0.5,
            d: 0.2,
        };
        let t = [0.5, 1.0, 1.5, 2.0, 3.0];
        let cap = capfloor(&c, &flat, &t, 0.03, true, 1.0).unwrap();
        assert!(cap.black_vols.iter().all(|v| (v - 0.2).abs() < 1e-14));
        let floor = capfloor(&c, &HUMP, &t, 0.03, false, 1.0).unwrap();
        let cap = capfloor(&c, &HUMP, &t, 0.03, true, 1.0).unwrap();
        let p = |x: f64| c.ln_discount(x).exp();
        let swap: f64 = t
            .windows(2)
            .map(|w| p(w[0]) - (1.0 + 0.03 * (w[1] - w[0])) * p(w[1]))
            .sum();
        assert!((cap.price - floor.price - swap).abs() < 1e-14);
        let pay = [2.0, 3.0, 4.0];
        let a = swaption_rebonato(&c, &HUMP, 0.3, 1.0, &pay, 0.03, true, 1.0).unwrap();
        let b = swaption_rebonato(&c, &HUMP, 0.3, 1.0, &pay, 0.03, false, 1.0).unwrap();
        assert!((a.price - b.price - a.annuity * (a.swap_rate - 0.03)).abs() < 1e-14);
        let f = swaption_rebonato(&c, &flat, 0.0, 1.0, &pay, 0.03, true, 1.0).unwrap();
        assert!((f.black_vol - 0.2).abs() < 1e-14);
    }

    /// G-26 acceptance: humped abcd, beta 0.1, annual grid to 7 years, K = 4.5%, 100,000
    /// paths, 20 steps a year; all six caplets within 3 SE of the closed form.
    #[test]
    fn simulated_caplets_match_closed_form() {
        let c = curve();
        let grid: Vec<f64> = (0..=7).map(f64::from).collect();
        let mc = simulate_caplets(&c, &HUMP, 0.1, &grid, 0.045, 100_000, 20, 20_261_111).unwrap();
        let cf = capfloor(&c, &HUMP, &grid[1..], 0.045, true, 1.0).unwrap();
        assert_eq!(mc.len(), 6);
        for (k, (m, se)) in mc.iter().enumerate() {
            let z = (m - cf.caplet_prices[k]) / se;
            assert!(z.abs() < 3.0, "caplet {k}: z = {z}");
        }
    }
}
