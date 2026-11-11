//! Stage F carry-over risk tools landed in stage G: F3 sensitivities (`f3-sensitivities.md`,
//! G-47) and F4 portfolio-risk tools (`portfolio-risk-tools.md`, G-46).
use crate::error::{Result, fail};
use crate::stats::{normal_cdf, normal_pdf};

/// `risk.sens.inflation01`: `(pv, inflation01, inflation01_bump)` of a receive-inflation
/// zero-coupon swap, `pv = N P ((1 + z)^n - (1 + K)^n)`.
pub fn inflation01(notional: f64, years: i64, k: f64, z: f64, p: f64) -> Result<(f64, f64, f64)> {
    crate::error::finite("inputs", &[notional, k, z, p])?;
    if years < 1 {
        return fail("E_DOMAIN", "years must be at least 1");
    }
    if 1.0 + z <= 0.0 || p <= 0.0 {
        return fail("E_DOMAIN", "need 1 + z > 0 and discount_factor > 0");
    }
    let Ok(n) = i32::try_from(years) else {
        return fail("E_LIMIT", "years too large");
    };
    let pv = |z: f64| notional * p * ((1.0 + z).powi(n) - (1.0 + k).powi(n));
    let v = pv(z);
    let a = notional * p * f64::from(n) * (1.0 + z).powi(n - 1) * 1e-4;
    Ok((v, a, pv(z + 1e-4) - v))
}

/// `risk.sens.dividend_borrow`: `(price, dividend01, borrow01)` under Black-Scholes-Merton with
/// yield `q + b`.
#[allow(clippy::too_many_arguments)]
pub fn dividend_borrow(
    s: f64,
    k: f64,
    t: f64,
    r: f64,
    q: f64,
    b: f64,
    v: f64,
    call: bool,
) -> Result<(f64, f64, f64)> {
    crate::error::finite("inputs", &[s, k, t, r, q, b, v])?;
    if s <= 0.0 || k <= 0.0 || t <= 0.0 || v <= 0.0 {
        return fail(
            "E_DOMAIN",
            "spot, strike, expiry_years and vol must be positive",
        );
    }
    let y = q + b;
    let sd = v * t.sqrt();
    let d1 = ((s / k).ln() + (r - y + v * v / 2.0) * t) / sd;
    let d2 = d1 - sd;
    let (fs, dk) = (s * (-y * t).exp(), k * (-r * t).exp());
    let (price, dvdy) = if call {
        (
            fs * normal_cdf(d1) - dk * normal_cdf(d2),
            -t * fs * normal_cdf(d1),
        )
    } else {
        (
            dk * normal_cdf(-d2) - fs * normal_cdf(-d1),
            t * fs * normal_cdf(-d1),
        )
    };
    Ok((price, dvdy * 1e-4, dvdy * 1e-4))
}

/// `risk.sens.correlation` (Margrabe): `(price, correlation01, spread_vol)`.
#[allow(clippy::too_many_arguments)]
pub fn correlation01(
    s1: f64,
    s2: f64,
    q1: f64,
    q2: f64,
    y1: f64,
    y2: f64,
    v1: f64,
    v2: f64,
    rho: f64,
    t: f64,
) -> Result<(f64, f64, f64)> {
    crate::error::finite("inputs", &[s1, s2, q1, q2, y1, y2, v1, v2, rho, t])?;
    if !(-1.0..=1.0).contains(&rho) {
        return fail("E_DOMAIN", "correlation must be in [-1, 1]");
    }
    if s1 <= 0.0 || s2 <= 0.0 || q1 <= 0.0 || q2 <= 0.0 || t <= 0.0 || v1 < 0.0 || v2 < 0.0 {
        return fail(
            "E_DOMAIN",
            "spots, quantities and expiry must be positive, vols >= 0",
        );
    }
    let var = v1 * v1 + v2 * v2 - 2.0 * rho * v1 * v2;
    if var <= 0.0 {
        return fail("E_DOMAIN", "the spread volatility is zero");
    }
    let sv = var.sqrt();
    let f1 = q1 * s1 * (-y1 * t).exp();
    let f2 = q2 * s2 * (-y2 * t).exp();
    let sd = sv * t.sqrt();
    let d1 = ((f1 / f2).ln() + sd * sd / 2.0) / sd;
    let price = f1 * normal_cdf(d1) - f2 * normal_cdf(d1 - sd);
    let dvds = f1 * normal_pdf(d1) * t.sqrt();
    Ok((price, dvds * (-v1 * v2 / sv) * 0.01, sv))
}

/// `risk.stress.reverse`: `(scale, shocks, pnl)`, the smallest `k > 0` with
/// `b k + a k^2 = -L` along `direction`, by the cancellation-free quadratic.
pub fn reverse_stress(
    d: &[f64],
    delta: &[f64],
    gamma: &[Vec<f64>],
    loss: f64,
) -> Result<(f64, Vec<f64>, f64)> {
    let n = d.len();
    if n == 0 || delta.len() != n || gamma.len() != n || gamma.iter().any(|g| g.len() != n) {
        return fail("E_INPUT", "direction, delta and gamma need matching sizes");
    }
    crate::error::finite("direction", &d)?;
    crate::error::finite("delta", &delta)?;
    crate::error::finite("target_loss", &loss)?;
    for g in gamma {
        crate::error::finite("gamma", &g.as_slice())?;
    }
    if loss <= 0.0 {
        return fail("E_DOMAIN", "target_loss must be positive");
    }
    let b: f64 = (0..n).map(|i| delta[i] * d[i]).sum();
    let mut a = 0.0;
    for i in 0..n {
        for j in 0..n {
            a += d[i] * gamma[i][j] * d[j];
        }
    }
    a /= 2.0;
    // a k^2 + b k + L = 0
    let k = if a == 0.0 {
        (b < 0.0).then(|| -loss / b)
    } else {
        let disc = b * b - 4.0 * a * loss;
        if disc < 0.0 {
            None
        } else {
            let sgn = if b >= 0.0 { 1.0 } else { -1.0 };
            let q = -(b + sgn * disc.sqrt()) / 2.0;
            let roots = [q / a, if q == 0.0 { f64::NAN } else { loss / q }];
            roots
                .iter()
                .copied()
                .filter(|r| *r > 0.0)
                .fold(None, |m: Option<f64>, r| Some(m.map_or(r, |m| m.min(r))))
        }
    };
    let Some(k) = k else {
        return fail("E_DOMAIN", "no positive scale reaches the target loss");
    };
    let shocks: Vec<f64> = d.iter().map(|x| k * x).collect();
    Ok((k, shocks, -loss))
}

/// `risk.limits.check` for one measure: `(utilisation, status)`.
pub fn limit_status(value: f64, soft: f64, hard: f64) -> Result<(f64, &'static str)> {
    crate::error::finite("limit", &[value, soft, hard])?;
    if !(0.0 <= soft && soft <= hard) || hard == 0.0 {
        return fail("E_DOMAIN", "need 0 <= soft <= hard and hard > 0");
    }
    let x = value.abs();
    let st = if x > hard {
        "BREACH"
    } else if x >= soft {
        "WARN"
    } else {
        "OK"
    };
    Ok((x / hard, st))
}

/// `risk.concentration.measures`: `(hhi, effective_number, top_n_share, weights)`.
pub fn concentration(x: &[f64], top_n: i64) -> Result<(f64, f64, f64, Vec<f64>)> {
    crate::error::finite("exposures", &x)?;
    if x.is_empty() {
        return fail("E_INPUT", "exposures needs at least one value");
    }
    let tot: f64 = x.iter().map(|v| v.abs()).sum();
    if tot == 0.0 {
        return fail("E_DOMAIN", "exposures are all zero");
    }
    let n = usize::try_from(top_n).unwrap_or(0);
    if n < 1 || n > x.len() {
        return fail("E_INPUT", "top_n must be 1 to the number of exposures");
    }
    let w: Vec<f64> = x.iter().map(|v| v.abs() / tot).collect();
    let hhi: f64 = w.iter().map(|v| v * v).sum();
    let mut s = w.clone();
    s.sort_by(|a, b| b.total_cmp(a));
    Ok((hhi, 1.0 / hhi, s[..n].iter().sum(), w))
}

/// `risk.var.liquidity_adjusted`: `(liquidity_cost, lvar)`.
pub fn liquidity_adjusted(
    var: f64,
    z: f64,
    p: &[f64],
    mu: &[f64],
    sd: &[f64],
) -> Result<(f64, f64)> {
    if p.len() != mu.len() || p.len() != sd.len() {
        return fail(
            "E_INPUT",
            "position_values, spread_mean and spread_vol need one length",
        );
    }
    crate::error::finite("var", &[var, z])?;
    crate::error::finite("position_values", &p)?;
    crate::error::finite("spread_mean", &mu)?;
    crate::error::finite("spread_vol", &sd)?;
    if var < 0.0 || mu.iter().chain(sd).any(|v| *v < 0.0) {
        return fail("E_DOMAIN", "var and spreads must not be negative");
    }
    let cost = 0.5
        * (0..p.len())
            .map(|i| p[i].abs() * (mu[i] + z * sd[i]))
            .sum::<f64>();
    Ok((cost, var + cost))
}

/// `risk.vol.horizon`: `(vol, sqrt_rule_vol, variance_ratio)` under AR(1) daily returns.
pub fn vol_horizon(sigma: f64, rho: f64, h: i64) -> Result<(f64, f64, f64)> {
    crate::error::finite("inputs", &[sigma, rho])?;
    if sigma <= 0.0 || rho.abs() >= 1.0 || h < 1 {
        return fail(
            "E_DOMAIN",
            "need daily_vol > 0, |ar1| < 1 and horizon_days >= 1",
        );
    }
    #[allow(clippy::cast_precision_loss)]
    let hf = h as f64;
    let mut sum = 0.0;
    let mut p = 1.0;
    for k in 1..h {
        p *= rho;
        #[allow(clippy::cast_precision_loss)]
        let w = (h - k) as f64;
        sum += w * p;
    }
    let ratio = (hf + 2.0 * sum) / hf;
    let sq = sigma * hf.sqrt();
    Ok((sq * ratio.sqrt(), sq, ratio))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn limits_and_closed_forms() {
        let (k, _, pnl) = reverse_stress(&[1.0], &[-1275.0], &[vec![0.0]], 50.0).unwrap();
        assert!((k - 50.0 / 1275.0).abs() < 1e-15 && pnl == -50.0);
        let (_, sq, r) = vol_horizon(0.01, 0.0, 10).unwrap();
        assert!((r - 1.0).abs() < 1e-15 && (sq - 0.01 * 10f64.sqrt()).abs() < 1e-15);
        let (h, e, _, _) = concentration(&[1.0; 4], 2).unwrap();
        assert!((h - 0.25).abs() < 1e-15 && (e - 4.0).abs() < 1e-12);
        let (pv, _, _) = inflation01(1.0, 1, 0.02, 0.02, 0.9).unwrap();
        assert!(pv.abs() < 1e-18);
        assert_eq!(limit_status(5.0, 3.0, 4.0).unwrap().1, "BREACH");
    }
}
