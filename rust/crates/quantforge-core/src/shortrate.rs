//! One-factor short-rate models: Vasicek, CIR, Hull-White (`04-pricing/short-rate-models.md`).
//! Stage G wave 1, partial: zero-coupon bond prices only.
use crate::error::{Result, fail};

/// Discount curve for Hull-White: log-linear in discount factor through `(0, 1)`,
/// flat forward past the last pillar.
#[derive(Debug, Clone)]
pub struct HwCurve {
    times: Vec<f64>,
    logs: Vec<f64>,
}

impl HwCurve {
    /// Builds the curve from pillar times and discount factors (`(0, 1)` is prepended).
    pub fn new(times: &[f64], dfs: &[f64]) -> Result<HwCurve> {
        crate::error::finite("times", &times)?;
        crate::error::finite("discount_factors", &dfs)?;
        if times.is_empty()
            || times.len() != dfs.len()
            || times[0] <= 0.0
            || times.windows(2).any(|w| w[1] <= w[0])
        {
            return fail(
                "E_INPUT",
                "curve times must be positive and strictly increasing",
            );
        }
        if dfs.iter().any(|d| *d <= 0.0) {
            return fail("E_DOMAIN", "discount factors must be positive");
        }
        let mut t = vec![0.0];
        t.extend_from_slice(times);
        let mut l = vec![0.0];
        l.extend(dfs.iter().map(|d| d.ln()));
        Ok(HwCurve { times: t, logs: l })
    }

    /// Segment holding `t`, right-continuous at pillars; the last segment extends.
    fn seg(&self, t: f64) -> usize {
        let n = self.times.len() - 1;
        self.times
            .partition_point(|x| *x <= t)
            .saturating_sub(1)
            .min(n - 1)
    }

    /// Right-hand instantaneous forward `f(0, t)`.
    pub fn forward(&self, t: f64) -> f64 {
        let i = self.seg(t);
        -(self.logs[i + 1] - self.logs[i]) / (self.times[i + 1] - self.times[i])
    }

    /// `ln P(0, t)`, log-linear between pillars and flat-forward past the last.
    pub fn ln_discount(&self, t: f64) -> f64 {
        let i = self.seg(t);
        self.logs[i] - self.forward(t) * (t - self.times[i])
    }
}

/// A one-factor short-rate model with its parameters.
pub enum Model<'a> {
    Vasicek {
        a: f64,
        b: f64,
        sigma: f64,
    },
    Cir {
        a: f64,
        b: f64,
        sigma: f64,
    },
    HullWhite {
        a: f64,
        sigma: f64,
        curve: &'a HwCurve,
    },
}

/// `B = (1 - e^{-a tau}) / a` and `(B - tau) / a`, the latter by series for small `a tau`.
fn b_terms(a: f64, tau: f64) -> (f64, f64) {
    let b = -(-a * tau).exp_m1() / a;
    let x = a * tau;
    let s = if x.abs() < 1e-2 {
        // (B - tau)/a = sum_{n>=2} (-1)^{n+1} a^{n-2} tau^n / n!
        let (mut s, mut term) = (0.0, -tau * tau / 2.0);
        for n in 2..30 {
            s += term;
            term *= -x / f64::from(n + 1);
        }
        s
    } else {
        (b - tau) / a
    };
    (b, s)
}

/// CIR `(ln A, B)` at time to maturity `tau` [BM 3.25].
fn cir_factors(a: f64, b: f64, sigma: f64, tau: f64) -> (f64, f64) {
    let g = (a * a + 2.0 * sigma * sigma).sqrt();
    let em1 = (g * tau).exp_m1();
    let den = (g + a) * em1 + 2.0 * g;
    let bb = 2.0 * em1 / den;
    let ln_a = 2.0 * a * b / (sigma * sigma) * ((2.0 * g).ln() + (a + g) * tau / 2.0 - den.ln());
    (ln_a, bb)
}

/// `rates.shortrate.zcb`: `(discount_factor, zero_rate)` for `P(t, T)` given `r(t)`.
pub fn zcb(m: &Model, r: f64, t: f64, maturity: f64) -> Result<(f64, f64)> {
    crate::error::finite("short_rate", &r)?;
    crate::error::finite("t_years", &t)?;
    crate::error::finite("maturity_years", &maturity)?;
    let (a, sigma) = match m {
        Model::Vasicek { a, sigma, .. }
        | Model::Cir { a, sigma, .. }
        | Model::HullWhite { a, sigma, .. } => (*a, *sigma),
    };
    crate::error::finite("mean_reversion", &a)?;
    crate::error::finite("sigma", &sigma)?;
    if a <= 0.0 || sigma <= 0.0 {
        return fail("E_DOMAIN", "mean_reversion and sigma must be positive");
    }
    if t < 0.0 || maturity <= t {
        return fail("E_DOMAIN", "need 0 <= t_years < maturity_years");
    }
    let tau = maturity - t;
    let ln_p = match m {
        Model::Vasicek { b, .. } => {
            crate::error::finite("long_term_mean", b)?;
            let (bb, s) = b_terms(a, tau);
            let ln_a =
                s * a * b - s / a * sigma * sigma / 2.0 - sigma * sigma * bb * bb / (4.0 * a);
            ln_a - bb * r
        }
        Model::Cir { b, .. } => {
            crate::error::finite("long_term_mean", b)?;
            if *b <= 0.0 {
                return fail("E_DOMAIN", "CIR long_term_mean must be positive");
            }
            if r < 0.0 {
                return fail("E_DOMAIN", "CIR short_rate must not be negative");
            }
            let (ln_a, bb) = cir_factors(a, *b, sigma, tau);
            ln_a - bb * r
        }
        Model::HullWhite { curve, .. } => {
            let (bb, _) = b_terms(a, tau);
            let ln_a = curve.ln_discount(maturity) - curve.ln_discount(t)
                + bb * curve.forward(t)
                + sigma * sigma / (4.0 * a) * (-2.0 * a * t).exp_m1() * bb * bb;
            ln_a - bb * r
        }
    };
    Ok((ln_p.exp(), -ln_p / tau))
}

/// `rates.shortrate.zcb_option` (Jamshidian for Vasicek and Hull-White, the noncentral
/// chi-square formula [BM 3.26] for CIR):
/// `(price, P(0, T), P(0, S))`. `r` is `r(0)` for Vasicek and CIR, ignored for Hull-White.
pub fn zcb_option(
    m: &Model,
    r: f64,
    call: bool,
    strike: f64,
    expiry: f64,
    maturity: f64,
    notional: f64,
) -> Result<(f64, f64, f64)> {
    crate::error::finite("strike", &strike)?;
    crate::error::finite("expiry_years", &expiry)?;
    crate::error::finite("notional", &notional)?;
    if !(0.0 < expiry && expiry < maturity) || strike <= 0.0 {
        return fail("E_DOMAIN", "need 0 < expiry < maturity and strike > 0");
    }
    let (a, sigma, pt, ps) = match m {
        Model::Vasicek { a, sigma, .. } => (
            *a,
            *sigma,
            zcb(m, r, 0.0, expiry)?.0,
            zcb(m, r, 0.0, maturity)?.0,
        ),
        Model::HullWhite { a, sigma, curve } => {
            zcb(m, 0.0, 0.0, maturity)?;
            (
                *a,
                *sigma,
                curve.ln_discount(expiry).exp(),
                curve.ln_discount(maturity).exp(),
            )
        }
        Model::Cir { a, b, sigma } => {
            let pt = zcb(m, r, 0.0, expiry)?.0;
            let ps = zcb(m, r, 0.0, maturity)?.0;
            let (a, b, sigma) = (*a, *b, *sigma);
            let s2 = sigma * sigma;
            let g = (a * a + 2.0 * s2).sqrt();
            let rho = 2.0 * g / (s2 * (g * expiry).exp_m1());
            let psi = (a + g) / s2;
            let (ln_a, bb) = cir_factors(a, b, sigma, maturity - expiry);
            let rbar = (ln_a - strike.ln()) / bb;
            let k = 4.0 * a * b / s2;
            let num = 2.0 * rho * rho * r * (g * expiry).exp();
            let chi = crate::stats::noncentral_chi2_cdf;
            let c = ps * chi(2.0 * rbar * (rho + psi + bb), k, num / (rho + psi + bb))
                - strike * pt * chi(2.0 * rbar * (rho + psi), k, num / (rho + psi));
            let v = if call { c } else { c - ps + strike * pt };
            return Ok((notional * v, pt, ps));
        }
    };
    let sp = sigma / a
        * -(-a * (maturity - expiry)).exp_m1()
        * (-(-2.0 * a * expiry).exp_m1() / (2.0 * a)).sqrt();
    let h = (ps / (strike * pt)).ln() / sp + sp / 2.0;
    let n = crate::stats::normal_cdf;
    let c = ps * n(h) - strike * pt * n(h - sp);
    let v = if call { c } else { c - ps + strike * pt };
    Ok((notional * v, pt, ps))
}

/// `B(tau)`, minus the sensitivity of `ln P` to the short rate, for the model.
fn b_factor(m: &Model, tau: f64) -> f64 {
    match m {
        Model::Vasicek { a, .. } | Model::HullWhite { a, .. } => b_terms(*a, tau).0,
        Model::Cir { a, b, sigma } => cir_factors(*a, *b, *sigma, tau).1,
    }
}

/// `P(0, t)` under the model: the curve for Hull-White, the bond formula at `r0` otherwise.
pub fn discount0(m: &Model, r0: f64, t: f64) -> Result<f64> {
    match m {
        Model::HullWhite { curve, .. } => Ok(curve.ln_discount(t).exp()),
        _ => Ok(zcb(m, r0, 0.0, t)?.0),
    }
}

/// Checks a swap payment schedule after `start`: non-empty, strictly increasing, first
/// payment after `start`, at most 10,000 entries (G-6).
pub fn check_payments(start: f64, pay: &[f64]) -> Result<()> {
    crate::error::finite("payment_times", &pay)?;
    if pay.len() > 10_000 {
        return fail("E_LIMIT", "at most 10,000 payment times");
    }
    if pay.is_empty() || pay[0] <= start || pay.windows(2).any(|w| w[1] <= w[0]) {
        return fail(
            "E_INPUT",
            "payment_times must be non-empty, strictly increasing and after the start",
        );
    }
    Ok(())
}

/// Output of [`swaption`].
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SwaptionValue {
    /// Present value.
    pub price: f64,
    /// `(P(0,T0) - P(0,Tn)) / sum tau_i P(0,Ti)`.
    pub forward_swap_rate: f64,
    /// `notional sum tau_i P(0,Ti)`.
    pub annuity: f64,
}

/// European swaption by Jamshidian's decomposition (`rates.shortrate.swaption`, G-12, G-13).
///
/// Accruals are time differences starting at `expiry`. The critical rate solves
/// `sum c_i P(T0, Ti; r*) = 1` by Newton from 0 inside a maintained bracket, to 1e-15
/// relative in the sum. `r0` is `r(0)` for Vasicek and CIR and ignored for Hull-White.
pub fn swaption(
    m: &Model,
    r0: f64,
    expiry: f64,
    pay: &[f64],
    fixed_rate: f64,
    payer: bool,
    notional: f64,
) -> Result<SwaptionValue> {
    Ok(swaption_parts(m, r0, expiry, pay, fixed_rate, payer, notional)?.0)
}

/// [`swaption`] plus the critical rate `r*` and the coupons `c_i`.
fn swaption_parts(
    m: &Model,
    r0: f64,
    expiry: f64,
    pay: &[f64],
    fixed_rate: f64,
    payer: bool,
    notional: f64,
) -> Result<(SwaptionValue, f64, Vec<f64>)> {
    crate::error::finite("expiry_years", &expiry)?;
    crate::error::finite("fixed_rate", &fixed_rate)?;
    crate::error::finite("notional", &notional)?;
    discount0(m, r0, 1.0)?; // parameter checks of zcb
    if expiry <= 0.0 {
        return fail("E_DOMAIN", "expiry_years must be positive");
    }
    check_payments(expiry, pay)?;
    let n = pay.len();
    let mut prev = expiry;
    let mut c = Vec::with_capacity(n);
    let mut tau = Vec::with_capacity(n);
    for (i, t) in pay.iter().enumerate() {
        tau.push(t - prev);
        c.push(fixed_rate * (t - prev) + if i + 1 == n { 1.0 } else { 0.0 });
        prev = *t;
    }
    let bs: Vec<f64> = pay.iter().map(|t| b_factor(m, t - expiry)).collect();
    let sum_at = |r: f64| -> Result<(f64, f64, f64)> {
        let (mut f, mut d, mut mag) = (-1.0, 0.0, 1.0);
        for i in 0..n {
            let p = zcb(m, r, expiry, pay[i])?.0;
            f += c[i] * p;
            d -= c[i] * bs[i] * p;
            mag += (c[i] * p).abs();
        }
        Ok((f, d, mag))
    };
    let cir = matches!(m, Model::Cir { .. });
    let (f0, _, _) = sum_at(0.0)?;
    if cir && f0 < 0.0 {
        return fail("E_DOMAIN", "CIR critical rate would be negative");
    }
    // Bracket: lo has f > 0, hi has f < 0.
    let (mut lo, mut hi) = (f64::NEG_INFINITY, f64::INFINITY);
    if cir {
        lo = 0.0;
    }
    let mut r = 0.0;
    let mut found = false;
    for _ in 0..500 {
        let (f, d, mag) = sum_at(r)?;
        // Converged at 1e-15 relative, or at the rounding floor of the sum.
        if f.abs() <= 1e-15_f64.max(2.0 * f64::EPSILON * mag) {
            found = true;
            break;
        }
        if f > 0.0 {
            lo = lo.max(r);
        } else {
            hi = hi.min(r);
        }
        let mut next = r - f / d;
        if !(next > lo && next < hi && next.is_finite()) {
            next = match (lo.is_finite(), hi.is_finite()) {
                (true, true) => 0.5 * (lo + hi),
                (true, false) => lo + 2.0 * (lo.abs() + 0.1),
                (false, true) => hi - 2.0 * (hi.abs() + 0.1),
                (false, false) => r,
            };
        }
        if next == r
            || (lo.is_finite()
                && hi.is_finite()
                && hi - lo <= 4.0 * f64::EPSILON * hi.abs().max(1e-300))
        {
            found = true;
            break;
        }
        r = next;
    }
    if !found {
        return fail("E_NO_CONVERGENCE", "critical rate solve did not converge");
    }
    let mut v = 0.0;
    for i in 0..n {
        let x = zcb(m, r, expiry, pay[i])?.0;
        v += c[i] * zcb_option(m, r0, !payer, x, expiry, pay[i], 1.0)?.0;
    }
    let mut ann = 0.0;
    for i in 0..n {
        ann += tau[i] * discount0(m, r0, pay[i])?;
    }
    let fwd = (discount0(m, r0, expiry)? - discount0(m, r0, pay[n - 1])?) / ann;
    let out = SwaptionValue {
        price: notional * v,
        forward_swap_rate: fwd,
        annuity: notional * ann,
    };
    Ok((out, r, c))
}

/// Hull-White Jamshidian price and its derivative in `sigma`, per unit notional.
///
/// The strikes `X_i` move with `sigma`, but `sum c_i X_i = 1` and every bond option is
/// exercised on the same event `r(T0) > r*`, so their contribution cancels and
/// `d price / d sigma = sum c_i P(0, Ti) n(h_i) sigma_p,i / sigma`.
pub fn hw_swaption_vega(
    curve: &HwCurve,
    a: f64,
    sigma: f64,
    expiry: f64,
    pay: &[f64],
    fixed_rate: f64,
    payer: bool,
) -> Result<(f64, f64)> {
    let m = Model::HullWhite { a, sigma, curve };
    let (v, r, c) = swaption_parts(&m, 0.0, expiry, pay, fixed_rate, payer, 1.0)?;
    let pt = curve.ln_discount(expiry).exp();
    let mut vega = 0.0;
    for (ci, ti) in c.iter().zip(pay) {
        let x = zcb(&m, r, expiry, *ti)?.0;
        let ps = curve.ln_discount(*ti).exp();
        let sp = sigma / a
            * -(-a * (ti - expiry)).exp_m1()
            * (-(-2.0 * a * expiry).exp_m1() / (2.0 * a)).sqrt();
        let h = (ps / (x * pt)).ln() / sp + sp / 2.0;
        vega += ci * ps * crate::stats::normal_pdf(h) * sp / sigma;
    }
    Ok((v.price, vega))
}

/// One swaption in a calibration strip (per unit notional).
#[derive(Debug, Clone)]
pub struct CalibSwaption {
    /// `T0`.
    pub expiry: f64,
    /// `T1 < ... < Tn`.
    pub pay: Vec<f64>,
    /// Fixed rate `K`.
    pub fixed_rate: f64,
    /// Payer (else receiver).
    pub payer: bool,
    /// Target price per unit notional.
    pub target: f64,
}

/// `rates.shortrate.hw_calibrate` (G-17): Hull-White `sigma` minimising the unweighted squared
/// price error on `[1e-4, 1]`, with `a` fixed. Returns `(sigma, fitted prices, rmse)`.
///
/// A log-spaced scan of `F` brackets the minimum; bisection on the sign of the analytic `F'`
/// then runs until the bracket is below 1e-15 relative. A minimum at an end of the interval
/// is `E_NO_CONVERGENCE`.
pub fn hw_calibrate(
    curve: &HwCurve,
    a: f64,
    strip: &[CalibSwaption],
) -> Result<(f64, Vec<f64>, f64)> {
    crate::error::finite("mean_reversion", &a)?;
    if a <= 0.0 {
        return fail("E_DOMAIN", "mean_reversion must be positive");
    }
    if strip.is_empty() {
        return fail("E_INPUT", "swaptions needs at least one entry");
    }
    if strip.len() > 10_000 {
        return fail("E_LIMIT", "at most 10,000 swaptions");
    }
    for q in strip {
        crate::error::finite("swaption", &[q.expiry, q.fixed_rate, q.target])?;
        if q.expiry <= 0.0 {
            return fail("E_DOMAIN", "expiry_years must be positive");
        }
        check_payments(q.expiry, &q.pay)?;
        if q.target < 0.0 {
            return fail("E_DOMAIN", "target_price must not be negative");
        }
    }
    let eval = |s: f64| -> Result<(f64, f64, Vec<f64>)> {
        let (mut f, mut d, mut px) = (0.0, 0.0, Vec::with_capacity(strip.len()));
        for q in strip {
            let (p, v) = hw_swaption_vega(curve, a, s, q.expiry, &q.pay, q.fixed_rate, q.payer)?;
            f += (p - q.target) * (p - q.target);
            d += 2.0 * (p - q.target) * v;
            px.push(p);
        }
        Ok((f, d, px))
    };
    let (lo_s, hi_s) = (1e-4_f64, 1.0_f64);
    let n = 400;
    let grid: Vec<f64> = (0..=n)
        .map(|j| lo_s * (hi_s / lo_s).powf(f64::from(j) / f64::from(n)))
        .collect();
    let mut best = (f64::INFINITY, 0usize);
    for (j, s) in grid.iter().enumerate() {
        // Far from any sensible sigma (sigma near 1 with long expiries) the bond formula
        // leaves binary64 and the critical rate has no root; such points cannot be the
        // minimum, so the scan scores them as +inf.
        let f = eval(*s).map_or(f64::INFINITY, |e| {
            if e.0.is_finite() { e.0 } else { f64::INFINITY }
        });
        if f < best.0 {
            best = (f, j);
        }
    }
    let j = best.1;
    if j == 0 || j == n as usize {
        return fail("E_NO_CONVERGENCE", "the minimum is at an end of [1e-4, 1]");
    }
    let (mut lo, mut hi) = (grid[j - 1], grid[j + 1]);
    for _ in 0..200 {
        let mid = 0.5 * (lo + hi);
        if hi - lo <= 1e-15 * hi || mid <= lo || mid >= hi {
            break;
        }
        if eval(mid)?.1 > 0.0 {
            hi = mid;
        } else {
            lo = mid;
        }
    }
    let sigma = 0.5 * (lo + hi);
    let (f, _, px) = eval(sigma)?;
    #[allow(clippy::cast_precision_loss)]
    let rmse = (f / strip.len() as f64).sqrt();
    Ok((sigma, px, rmse))
}

/// Cap or floor as a portfolio of bond options (`rates.shortrate.capfloor`, G-19):
/// `(price, caplet or floorlet prices)`. A caplet is `(1 + K tau) ZBP(0, t_(i-1), t_i,
/// 1/(1 + K tau))`, a floorlet the same with `ZBC`.
pub fn capfloor(
    m: &Model,
    r0: f64,
    times: &[f64],
    strike: f64,
    cap: bool,
    notional: f64,
) -> Result<(f64, Vec<f64>)> {
    crate::error::finite("period_times", &times)?;
    crate::error::finite("strike", &strike)?;
    crate::error::finite("notional", &notional)?;
    discount0(m, r0, 1.0)?;
    if times.len() > 10_001 {
        return fail("E_LIMIT", "at most 10,000 periods");
    }
    if times.len() < 2 || times.windows(2).any(|w| w[1] <= w[0]) {
        return fail(
            "E_INPUT",
            "period_times needs at least two strictly increasing times",
        );
    }
    if times[0] <= 0.0 {
        return fail("E_DOMAIN", "the first period time must be positive");
    }
    if times
        .windows(2)
        .any(|w| 1.0 + strike * (w[1] - w[0]) <= 0.0)
    {
        return fail("E_DOMAIN", "1 + K tau must be positive");
    }
    let mut lets = Vec::with_capacity(times.len() - 1);
    for w in times.windows(2) {
        let g = 1.0 + strike * (w[1] - w[0]);
        lets.push(notional * g * zcb_option(m, r0, !cap, 1.0 / g, w[0], w[1], 1.0)?.0);
    }
    Ok((lets.iter().sum(), lets))
}

/// G2++ two-factor Gaussian model parameters (`rates.g2pp.*`, ruling G-14).
#[derive(Debug, Clone, Copy)]
pub struct G2pp<'a> {
    /// Mean reversion of `x`.
    pub a: f64,
    /// Volatility of `x`.
    pub sigma: f64,
    /// Mean reversion of `y`.
    pub b: f64,
    /// Volatility of `y`.
    pub eta: f64,
    /// Correlation of the two drivers, strictly inside `(-1, 1)`.
    pub rho: f64,
    /// The fitted discount curve.
    pub curve: &'a HwCurve,
}

/// `(k tau + 2 expm1(-k tau) - expm1(-2 k tau)/2) / k^3`, by series below `k tau = 1`.
fn g2_vterm(k: f64, tau: f64) -> f64 {
    let x = k * tau;
    if x < 1.0 {
        // sum_{n>=3} (-1)^n (2 - 2^{n-1}) x^{n-3} / n!, times tau^3
        let (mut sum, mut fact, mut xp, mut p2) = (0.0_f64, 6.0_f64, 1.0_f64, 4.0_f64);
        for n in 3..60 {
            let sign = if n % 2 == 0 { 1.0 } else { -1.0 };
            let t = sign * (2.0 - p2) * xp / fact;
            sum += t;
            if t.abs() < 1e-18 * sum.abs() {
                break;
            }
            xp *= x;
            p2 *= 2.0;
            fact *= f64::from(n + 1);
        }
        sum * tau * tau * tau
    } else {
        (x + 2.0 * (-x).exp_m1() - (-2.0 * x).exp_m1() / 2.0) / (k * k * k)
    }
}

/// `(tau - B_a - B_b + B_(a+b)) / (a b)`, the integral of `B_a(s) B_b(s)`, by double series
/// when both `a tau` and `b tau` are below 1.
fn g2_cross(a: f64, b: f64, tau: f64) -> f64 {
    if a * tau < 1.0 && b * tau < 1.0 {
        // sum_{m,n>=1} (-1)^{m+n} a^{m-1} b^{n-1} tau^{m+n+1} / (m! n! (m+n+1))
        let mut sum = 0.0;
        let mut am = 1.0; // (a tau)^{m-1} / m!
        for m in 1..40 {
            let mut bn = 1.0; // (b tau)^{n-1} / n!
            for n in 1..40 {
                let sign = if (m + n) % 2 == 0 { 1.0 } else { -1.0 };
                sum += sign * am * bn / f64::from(m + n + 1);
                bn *= b * tau / f64::from(n + 1);
            }
            am *= a * tau / f64::from(m + 1);
        }
        sum * tau * tau * tau
    } else {
        let bk = |k: f64| -(-k * tau).exp_m1() / k;
        (tau - bk(a) - bk(b) + bk(a + b)) / (a * b)
    }
}

impl G2pp<'_> {
    fn check(&self) -> Result<()> {
        crate::error::finite("g2pp", &[self.a, self.sigma, self.b, self.eta, self.rho])?;
        if self.a <= 0.0 || self.sigma <= 0.0 || self.b <= 0.0 || self.eta <= 0.0 {
            return fail("E_DOMAIN", "a, sigma, b and eta must be positive");
        }
        if !(self.rho > -1.0 && self.rho < 1.0) {
            return fail("E_DOMAIN", "rho must be strictly inside (-1, 1)");
        }
        Ok(())
    }

    /// `V(tau)`, the variance of the integrated factors [BM 4.10].
    fn v(&self, tau: f64) -> f64 {
        let (a, b, s, e, r) = (self.a, self.b, self.sigma, self.eta, self.rho);
        s * s * g2_vterm(a, tau) + e * e * g2_vterm(b, tau) + 2.0 * r * s * e * g2_cross(a, b, tau)
    }

    /// `rates.g2pp.zcb`: `(discount_factor, zero_rate)` of `P(t, T)` at states `x`, `y`.
    pub fn zcb(&self, x: f64, y: f64, t: f64, maturity: f64) -> Result<(f64, f64)> {
        crate::error::finite("state", &[x, y, t, maturity])?;
        self.check()?;
        if t < 0.0 || maturity <= t {
            return fail("E_DOMAIN", "need 0 <= t_years < maturity_years");
        }
        let tau = maturity - t;
        let c = self.curve;
        let ln_p = c.ln_discount(maturity) - c.ln_discount(t)
            + 0.5 * (self.v(tau) - self.v(maturity) + self.v(t))
            - b_terms(self.a, tau).0 * x
            - b_terms(self.b, tau).0 * y;
        Ok((ln_p.exp(), -ln_p / tau))
    }

    /// `rates.g2pp.zcb_option`: `(price, P(0, T), P(0, S))` [BM 4.31].
    pub fn zcb_option(
        &self,
        call: bool,
        strike: f64,
        expiry: f64,
        maturity: f64,
        notional: f64,
    ) -> Result<(f64, f64, f64)> {
        crate::error::finite("option", &[strike, expiry, maturity, notional])?;
        self.check()?;
        if !(0.0 < expiry && expiry < maturity) || strike <= 0.0 {
            return fail("E_DOMAIN", "need 0 < expiry < maturity and strike > 0");
        }
        let (a, b, s, e, r) = (self.a, self.b, self.sigma, self.eta, self.rho);
        let u = maturity - expiry;
        let om = |k: f64, t: f64| -(-k * t).exp_m1();
        let ba = b_terms(a, u).0;
        let bb = b_terms(b, u).0;
        // 1 - e^{-2kT} over 2k, written with expm1 so small k loses nothing.
        let var = |k: f64| om(2.0 * k, expiry) / (2.0 * k);
        let cross = om(a + b, expiry) / (a + b);
        let sig2 =
            s * s * ba * ba * var(a) + e * e * bb * bb * var(b) + 2.0 * r * s * e * ba * bb * cross;
        let sp = sig2.sqrt();
        let pt = self.curve.ln_discount(expiry).exp();
        let ps = self.curve.ln_discount(maturity).exp();
        let h = (ps / (strike * pt)).ln() / sp + sp / 2.0;
        let n = crate::stats::normal_cdf;
        let c = ps * n(h) - strike * pt * n(h - sp);
        let v = if call { c } else { c - ps + strike * pt };
        Ok((notional * v, pt, ps))
    }
}

/// Grid of the pinned Hull-White finite-difference scheme (ruling G-18).
#[derive(Debug, Clone, Copy)]
pub struct FdGrid {
    /// Space nodes, odd, 5 to 10,001.
    pub nx: i64,
    /// Time steps per year, 1 to 100,000.
    pub steps_per_year: i64,
    /// Half-width of the space grid in standard deviations of `x(t_m)`.
    pub width: f64,
}

impl FdGrid {
    fn check(&self) -> Result<()> {
        crate::error::finite("width", &self.width)?;
        if self.nx < 5 || self.nx % 2 == 0 {
            return fail("E_INPUT", "grid.nx must be odd and at least 5");
        }
        if self.nx > 10_001 {
            return fail("E_LIMIT", "grid.nx is at most 10,001");
        }
        if self.steps_per_year < 1 {
            return fail("E_INPUT", "grid.steps_per_year must be at least 1");
        }
        if self.steps_per_year > 100_000 {
            return fail("E_LIMIT", "grid.steps_per_year is at most 100,000");
        }
        if self.width <= 0.0 {
            return fail("E_DOMAIN", "grid.width must be positive");
        }
        Ok(())
    }
}

/// `alpha(t) = f(0,t) + sigma^2/(2a^2) (1 - e^{-at})^2`, so that `r = x + alpha`.
fn hw_alpha(curve: &HwCurve, a: f64, sigma: f64, t: f64) -> f64 {
    let e = -(-a * t).exp_m1();
    curve.forward(t) + sigma * sigma / (2.0 * a * a) * e * e
}

/// Terminal values of the FD scheme from `(x nodes, t_m)`.
type Terminal<'a> = dyn Fn(&[f64], f64) -> Result<Vec<f64>> + 'a;
/// Knot update of the FD scheme: `(knot index, V, x nodes, t_k)`.
type AtKnot<'a> = dyn FnMut(usize, &mut [f64], &[f64], f64) -> Result<()> + 'a;

/// The G-18 reference scheme: fully implicit backward induction on `x = r - alpha(t)` over
/// the knots `0 < t_1 < ... < t_m`. `terminal` gives `V` at `t_m` from `(x, t_m)`; `at_knot`
/// is called on arrival at each knot `t_k`, `k < m` (0-based into `knots`, backward order),
/// with `(k, V, x, t_k)`. Returns `V` at the centre node at time 0.
fn hw_fd(
    curve: &HwCurve,
    a: f64,
    sigma: f64,
    knots: &[f64],
    grid: FdGrid,
    terminal: &Terminal,
    at_knot: &mut AtKnot,
) -> Result<f64> {
    let nx = usize::try_from(grid.nx).unwrap_or(5);
    let tm = knots[knots.len() - 1];
    let sx = sigma * (-(-2.0 * a * tm).exp_m1() / (2.0 * a)).sqrt();
    let h = grid.width * sx;
    #[allow(clippy::cast_precision_loss)]
    let dx = 2.0 * h / (nx - 1) as f64;
    #[allow(clippy::cast_precision_loss)]
    let x: Vec<f64> = (0..nx).map(|i| -h + i as f64 * dx).collect();
    let mut v = terminal(&x, tm)?;
    let (mut lo, mut di, mut up, mut cp, mut dp) = (
        vec![0.0; nx],
        vec![0.0; nx],
        vec![0.0; nx],
        vec![0.0; nx],
        vec![0.0; nx],
    );
    let diff = sigma * sigma / (2.0 * dx * dx);
    #[allow(clippy::cast_precision_loss)]
    let spy = grid.steps_per_year as f64;
    let mut all = vec![0.0];
    all.extend_from_slice(knots);
    for k in (1..all.len()).rev() {
        let (ta, tb) = (all[k - 1], all[k]);
        #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
        let n = ((spy * (tb - ta)).ceil() as usize).max(1);
        #[allow(clippy::cast_precision_loss)]
        let dt = (tb - ta) / n as f64;
        for j in 1..=n {
            #[allow(clippy::cast_precision_loss)]
            let t = if j == n { ta } else { tb - j as f64 * dt };
            let al = hw_alpha(curve, a, sigma, t);
            for i in 1..nx - 1 {
                let adv = a * x[i] / (2.0 * dx);
                lo[i] = -dt * (diff + adv);
                di[i] = 1.0 + dt * (2.0 * diff + x[i] + al);
                up[i] = -dt * (diff - adv);
            }
            // V_0 = 2 V_1 - V_2 and V_(nx-1) = 2 V_(nx-2) - V_(nx-3).
            di[1] += 2.0 * lo[1];
            up[1] -= lo[1];
            di[nx - 2] += 2.0 * up[nx - 2];
            lo[nx - 2] -= up[nx - 2];
            // Thomas algorithm on rows 1..nx-2.
            cp[1] = up[1] / di[1];
            dp[1] = v[1] / di[1];
            for i in 2..nx - 1 {
                let m = di[i] - lo[i] * cp[i - 1];
                cp[i] = up[i] / m;
                dp[i] = (v[i] - lo[i] * dp[i - 1]) / m;
            }
            v[nx - 2] = dp[nx - 2];
            for i in (1..nx - 2).rev() {
                v[i] = dp[i] - cp[i] * v[i + 1];
            }
            v[0] = 2.0 * v[1] - v[2];
            v[nx - 1] = 2.0 * v[nx - 2] - v[nx - 3];
        }
        if k >= 2 {
            at_knot(k - 2, &mut v, &x, ta)?;
        }
    }
    Ok(v[(nx - 1) / 2])
}

/// Value of entering at `t` the swap paying from `t` to `Tn` (per unit notional, payer sign
/// `phi`), at short rate `r`: `phi (1 - P(t,Tn) - K sum tau_j P(t,Tj))`, payments after `t`.
fn swap_exercise(m: &Model, r: f64, t: f64, pay: &[f64], k: f64, phi: f64) -> Result<f64> {
    let mut prev = t;
    let mut fixed = 0.0;
    let mut last = 1.0;
    for tj in pay.iter().filter(|tj| **tj > t) {
        let p = zcb(m, r, t, *tj)?.0;
        fixed += (tj - prev) * p;
        prev = *tj;
        last = p;
    }
    Ok(phi * (1.0 - last - k * fixed))
}

/// The underlying swap of a Bermudan swaption.
#[derive(Debug, Clone)]
pub struct SwapLeg<'a> {
    /// `T0`, the start of the swap.
    pub start: f64,
    /// `T1 < ... < Tn`.
    pub pay: &'a [f64],
    /// Fixed rate `K`.
    pub fixed_rate: f64,
    /// Payer (pays fixed) or receiver.
    pub payer: bool,
    /// Notional.
    pub notional: f64,
}

/// `rates.shortrate.bermudan_swaption` on the pinned G-18 scheme. `exercise` must be reset
/// dates `T0, ..., T(n-1)`; exercising at `t` enters the swap paying from `t` to `Tn`.
pub fn bermudan_swaption(
    curve: &HwCurve,
    a: f64,
    sigma: f64,
    swap: &SwapLeg,
    exercise: &[f64],
    grid: FdGrid,
) -> Result<f64> {
    let (start, pay) = (swap.start, swap.pay);
    crate::error::finite("start_years", &start)?;
    crate::error::finite("exercise_times", &exercise)?;
    crate::error::finite("fixed_rate", &swap.fixed_rate)?;
    crate::error::finite("notional", &swap.notional)?;
    let m = Model::HullWhite { a, sigma, curve };
    zcb(&m, 0.0, 0.0, 1.0)?;
    if start <= 0.0 {
        return fail("E_DOMAIN", "start_years must be positive");
    }
    check_payments(start, pay)?;
    let mut resets = vec![start];
    resets.extend_from_slice(&pay[..pay.len() - 1]);
    if exercise.is_empty()
        || exercise.windows(2).any(|w| w[1] <= w[0])
        || exercise.iter().any(|e| !resets.contains(e))
    {
        return fail(
            "E_INPUT",
            "exercise_times must be strictly increasing reset dates before the last payment",
        );
    }
    grid.check()?;
    let phi = if swap.payer { 1.0 } else { -1.0 };
    let ex = |x: &[f64], t: f64| -> Result<Vec<f64>> {
        let al = hw_alpha(curve, a, sigma, t);
        x.iter()
            .map(|xi| swap_exercise(&m, xi + al, t, pay, swap.fixed_rate, phi))
            .collect()
    };
    let terminal = |x: &[f64], t: f64| -> Result<Vec<f64>> {
        Ok(ex(x, t)?.into_iter().map(|e| e.max(0.0)).collect())
    };
    let mut knot = |_k: usize, v: &mut [f64], x: &[f64], t: f64| -> Result<()> {
        for (vi, e) in v.iter_mut().zip(ex(x, t)?) {
            *vi = vi.max(e);
        }
        Ok(())
    };
    Ok(swap.notional * hw_fd(curve, a, sigma, exercise, grid, &terminal, &mut knot)?)
}

/// A fixed-rate bond with an issuer call schedule.
#[derive(Debug, Clone)]
pub struct CallableBond<'a> {
    /// Coupon dates `T1 < ... < Tn`, the last also the maturity.
    pub pay: &'a [f64],
    /// Coupon rate `c`; accruals are time differences from 0.
    pub coupon: f64,
    /// Face amount.
    pub notional: f64,
    /// Call dates: payment times before the last (possibly none).
    pub calls: &'a [f64],
    /// Call price as a fraction of face.
    pub call_price: f64,
}

/// `rates.shortrate.callable_bond` (G-21) on the G-18 scheme. At each coupon date the
/// ex-coupon value is capped by `call_price` (if callable), then the coupon is added.
pub fn callable_bond(
    curve: &HwCurve,
    a: f64,
    sigma: f64,
    bond: &CallableBond,
    grid: FdGrid,
) -> Result<f64> {
    let (pay, calls, coupon) = (bond.pay, bond.calls, bond.coupon);
    crate::error::finite("coupon_rate", &coupon)?;
    crate::error::finite("notional", &bond.notional)?;
    crate::error::finite("call_times", &calls)?;
    crate::error::finite("call_price", &bond.call_price)?;
    let m = Model::HullWhite { a, sigma, curve };
    zcb(&m, 0.0, 0.0, 1.0)?;
    check_payments(0.0, pay)?;
    let before_last = &pay[..pay.len() - 1];
    if calls.windows(2).any(|w| w[1] <= w[0]) || calls.iter().any(|c| !before_last.contains(c)) {
        return fail(
            "E_INPUT",
            "call_times must be strictly increasing payment times before the last",
        );
    }
    if bond.call_price <= 0.0 {
        return fail("E_DOMAIN", "call_price must be positive");
    }
    grid.check()?;
    let n = pay.len();
    let tau = |k: usize| pay[k] - if k == 0 { 0.0 } else { pay[k - 1] };
    let last = 1.0 + coupon * tau(n - 1);
    let terminal = |x: &[f64], _t: f64| -> Result<Vec<f64>> { Ok(vec![last; x.len()]) };
    let mut knot = |k: usize, v: &mut [f64], _x: &[f64], t: f64| -> Result<()> {
        let callable = calls.contains(&t);
        let cpn = coupon * tau(k);
        for vi in v.iter_mut() {
            if callable {
                *vi = vi.min(bond.call_price);
            }
            *vi += cpn;
        }
        Ok(())
    };
    Ok(bond.notional * hw_fd(curve, a, sigma, pay, grid, &terminal, &mut knot)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cir_put_call_parity_and_bounds() {
        let m = Model::Cir {
            a: 0.3,
            b: 0.05,
            sigma: 0.1,
        };
        for (k, te, ts) in [(0.9, 1.0, 3.0), (0.95, 0.5, 2.0), (0.7, 2.0, 10.0)] {
            let (c, pt, ps) = zcb_option(&m, 0.04, true, k, te, ts, 1.0).unwrap();
            let (p, _, _) = zcb_option(&m, 0.04, false, k, te, ts, 1.0).unwrap();
            assert!((c - p - (ps - k * pt)).abs() < 1e-12);
            assert!(c >= 0.0 && c <= ps);
        }
        // r = 0 gives zero noncentrality and must still price.
        assert!(zcb_option(&m, 0.0, true, 0.9, 1.0, 3.0, 1.0).unwrap().0 > 0.0);
    }

    fn curve() -> HwCurve {
        HwCurve::new(
            &[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
            &[0.985, 0.97, 0.94, 0.85, 0.70, 0.33],
        )
        .unwrap()
    }

    #[test]
    fn swaption_payer_minus_receiver_is_forward_swap() {
        let c = curve();
        let models = [
            Model::HullWhite {
                a: 0.05,
                sigma: 0.01,
                curve: &c,
            },
            Model::Vasicek {
                a: 0.15,
                b: 0.045,
                sigma: 0.012,
            },
            Model::Cir {
                a: 0.2,
                b: 0.05,
                sigma: 0.08,
            },
        ];
        let pay = [2.0, 3.0, 4.0, 5.0, 6.0];
        for m in &models {
            for k in [0.02, 0.04, 0.06] {
                let p = swaption(m, 0.04, 1.0, &pay, k, true, 1.0).unwrap();
                let r = swaption(m, 0.04, 1.0, &pay, k, false, 1.0).unwrap();
                let fwd = p.annuity * (p.forward_swap_rate - k);
                assert!((p.price - r.price - fwd).abs() < 1e-8);
            }
        }
    }

    #[test]
    fn capfloor_parity() {
        let c = curve();
        let m = Model::HullWhite {
            a: 0.05,
            sigma: 0.01,
            curve: &c,
        };
        let t = [0.5, 1.0, 1.5, 2.0, 2.5];
        let k = 0.03;
        let cap = capfloor(&m, 0.0, &t, k, true, 1.0).unwrap().0;
        let floor = capfloor(&m, 0.0, &t, k, false, 1.0).unwrap().0;
        let swap: f64 = t
            .windows(2)
            .map(|w| {
                discount0(&m, 0.0, w[0]).unwrap()
                    - (1.0 + k * (w[1] - w[0])) * discount0(&m, 0.0, w[1]).unwrap()
            })
            .sum();
        assert!((cap - floor - swap).abs() < 1e-12);
    }

    #[test]
    fn g2pp_limits() {
        let c = curve();
        let g = G2pp {
            a: 0.1,
            sigma: 0.01,
            b: 0.3,
            eta: 1e-12,
            rho: 0.2,
            curve: &c,
        };
        let hw = Model::HullWhite {
            a: 0.1,
            sigma: 0.01,
            curve: &c,
        };
        let (pg, _, _) = g.zcb_option(true, 0.9, 1.0, 4.0, 1.0).unwrap();
        let (ph, _, _) = zcb_option(&hw, 0.0, true, 0.9, 1.0, 4.0, 1.0).unwrap();
        assert!((pg - ph).abs() < 1e-12);
        let g = G2pp { eta: 0.008, ..g };
        let (p, _) = g.zcb(0.0, 0.0, 0.0, 5.0).unwrap();
        assert!((p - c.ln_discount(5.0).exp()).abs() < 1e-15);
        let (c1, pt, ps) = g.zcb_option(true, 0.9, 1.0, 4.0, 1.0).unwrap();
        let (p1, _, _) = g.zcb_option(false, 0.9, 1.0, 4.0, 1.0).unwrap();
        assert!((c1 - p1 - (ps - 0.9 * pt)).abs() < 1e-12);
        // Series and direct forms of the variance terms agree where they meet.
        for k in [0.999_f64, 1.001] {
            let d = (k + 2.0 * (-k).exp_m1() - (-2.0 * k).exp_m1() / 2.0) / (k * k * k);
            assert!((g2_vterm(k, 1.0) - d).abs() < 1e-12 * d);
        }
        let bk = |k: f64| -(-k).exp_m1() / k;
        let direct = (1.0 - bk(0.9) - bk(0.95) + bk(1.85)) / (0.9 * 0.95);
        assert!((g2_cross(0.9, 0.95, 1.0) - direct).abs() < 1e-11 * direct);
    }

    #[test]
    fn hw_vega_and_exact_calibration() {
        let c = curve();
        let pay = [2.0, 3.0, 4.0, 5.0];
        let (p, v) = hw_swaption_vega(&c, 0.05, 0.01, 1.0, &pay, 0.04, true).unwrap();
        let h = 1e-6;
        let up = hw_swaption_vega(&c, 0.05, 0.01 + h, 1.0, &pay, 0.04, true)
            .unwrap()
            .0;
        let dn = hw_swaption_vega(&c, 0.05, 0.01 - h, 1.0, &pay, 0.04, true)
            .unwrap()
            .0;
        assert!(p > 0.0 && (v - (up - dn) / (2.0 * h)).abs() < 1e-7 * v.abs());
        let strip: Vec<CalibSwaption> = [1.0, 2.0, 3.0]
            .iter()
            .map(|t0| {
                let pay: Vec<f64> = (1..=4).map(|k| t0 + f64::from(k)).collect();
                let target = hw_swaption_vega(&c, 0.05, 0.007, *t0, &pay, 0.04, false)
                    .unwrap()
                    .0;
                CalibSwaption {
                    expiry: *t0,
                    pay,
                    fixed_rate: 0.04,
                    payer: false,
                    target,
                }
            })
            .collect();
        let (sigma, _, rmse) = hw_calibrate(&c, 0.05, &strip).unwrap();
        assert!((sigma - 0.007).abs() < 1e-11 && rmse < 1e-12);
        assert_eq!(hw_calibrate(&c, 0.05, &[]).unwrap_err().code, "E_INPUT");
    }

    #[test]
    fn bermudan_european_limit_and_callable_bound() {
        let c = curve();
        let pay = [2.0, 3.0, 4.0, 5.0, 6.0];
        let grid = FdGrid {
            nx: 201,
            steps_per_year: 100,
            width: 6.0,
        };
        let swap = SwapLeg {
            start: 1.0,
            pay: &pay,
            fixed_rate: 0.04,
            payer: true,
            notional: 1.0,
        };
        let berm1 = bermudan_swaption(&c, 0.05, 0.01, &swap, &[1.0], grid).unwrap();
        let m = Model::HullWhite {
            a: 0.05,
            sigma: 0.01,
            curve: &c,
        };
        let euro = swaption(&m, 0.0, 1.0, &pay, 0.04, true, 1.0).unwrap().price;
        // The pinned scheme is first order in time: about 0.2% below Jamshidian at this grid.
        assert!((berm1 - euro).abs() < 5e-3 * euro, "{berm1} {euro}");
        let berm = bermudan_swaption(&c, 0.05, 0.01, &swap, &[1.0, 2.0, 3.0], grid).unwrap();
        assert!(berm >= berm1);
        let coupons: Vec<f64> = (1..=10).map(f64::from).collect();
        let straight: f64 = coupons
            .iter()
            .map(|t| 0.05 * c.ln_discount(*t).exp())
            .sum::<f64>()
            + c.ln_discount(10.0).exp();
        let bond = |calls: &'static [f64]| CallableBond {
            pay: Box::leak(coupons.clone().into_boxed_slice()),
            coupon: 0.05,
            notional: 1.0,
            calls,
            call_price: 1.0,
        };
        let plain = callable_bond(&c, 0.05, 0.01, &bond(&[]), grid).unwrap();
        let called = callable_bond(&c, 0.05, 0.01, &bond(&[3.0, 4.0, 5.0]), grid).unwrap();
        assert!((plain - straight).abs() < 1e-3 * straight);
        assert!(called < plain);
        let bad = FdGrid { nx: 50, ..grid };
        assert_eq!(
            callable_bond(&c, 0.05, 0.01, &bond(&[]), bad)
                .unwrap_err()
                .code,
            "E_INPUT"
        );
    }
}
