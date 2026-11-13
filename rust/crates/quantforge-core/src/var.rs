//! Value at risk, expected shortfall and backtests (`06-risk/var-es-and-backtests.md`, rulings F-31 and F-32).
use crate::error::{Result, fail};
use crate::linalg::cholesky;
use crate::rng::{Xoshiro, ppnd16};
use crate::stats::{normal_cdf, normal_pdf};

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct VarEs {
    pub var: f64,
    pub es: f64,
    pub tail_count: i64,
}

fn check_confidence(c: f64) -> Result<()> {
    crate::error::finite("confidence", &c)?;
    if !(0.5..1.0).contains(&c) {
        return fail("E_DOMAIN", "confidence must be in [0.5, 1)");
    }
    Ok(())
}

/// Ruling F-31 on `P&L` scenarios for `VaR`: `k = ceil(n c)`, the `k`-th smallest loss. ES by
/// ruling R6-3.1 (Acerbi-Tasche, fractional tail weight): `w = n - n c`, `m = floor(w)`,
/// `es = (L_1 + ... + L_m + (w - m) L_(m+1)) / w` over losses sorted descending; `w <= 0`
/// gives `L_1`; `tail_count = ceil(w)` (1 when `w <= 0`).
fn order_statistic(pnl: &[f64], c: f64) -> VarEs {
    let mut losses: Vec<f64> = pnl.iter().map(|p| -p).collect();
    losses.sort_by(f64::total_cmp);
    let n = losses.len();
    let k = ((n as f64 * c).ceil() as usize).clamp(1, n);
    let nf = n as f64;
    let w = nf - nf * c;
    let (es, tail_count) = if w <= 0.0 {
        (losses[n - 1], 1)
    } else {
        let m = (w.floor() as usize).min(n);
        let mut sum: f64 = losses[n - m..].iter().rev().sum();
        if m < n {
            sum += (w - m as f64) * losses[n - 1 - m];
        }
        (sum / w, w.ceil() as i64)
    };
    VarEs {
        var: losses[k - 1],
        es,
        tail_count,
    }
}

/// `risk.var.historical`.
pub fn historical(pnl: &[f64], c: f64) -> Result<VarEs> {
    crate::error::finite("pnl", &pnl)?;
    if pnl.is_empty() {
        return fail("E_INPUT", "no scenarios");
    }
    check_confidence(c)?;
    Ok(order_statistic(pnl, c))
}

/// `risk.var.filtered_historical`: `(result, sigma_next)`.
pub fn filtered_historical(
    returns: &[f64],
    position: f64,
    lambda: f64,
    c: f64,
) -> Result<(VarEs, f64)> {
    crate::error::finite("returns", &returns)?;
    crate::error::finite("position_value", &position)?;
    crate::error::finite("lambda", &lambda)?;
    if returns.is_empty() {
        return fail("E_INPUT", "no returns");
    }
    if !(lambda > 0.0 && lambda < 1.0) {
        return fail("E_DOMAIN", "lambda must be in (0, 1)");
    }
    check_confidence(c)?;
    let t = returns.len();
    let mut var = vec![returns.iter().map(|r| r * r).sum::<f64>() / t as f64];
    for r in returns {
        let last = *var.last().expect("seeded");
        var.push(lambda * last + (1.0 - lambda) * r * r);
    }
    let next = var[t].sqrt();
    if var.iter().any(|v| *v <= 0.0) {
        return fail("E_DOMAIN", "a variance is zero");
    }
    let pnl: Vec<f64> = returns
        .iter()
        .zip(&var)
        .map(|(r, v)| position * r * next / v.sqrt())
        .collect();
    Ok((order_statistic(&pnl, c), next))
}

/// `risk.var.parametric`.
pub fn parametric(mean: f64, std: f64, c: f64) -> Result<VarEs> {
    crate::error::finite("mean", &mean)?;
    crate::error::finite("std", &std)?;
    if std.is_nan() || std <= 0.0 {
        return fail("E_DOMAIN", "std must be positive");
    }
    check_confidence(c)?;
    let z = ppnd16(c);
    Ok(VarEs {
        var: -mean + std * z,
        es: -mean + std * normal_pdf(z) / (1.0 - c),
        tail_count: 0,
    })
}

/// `risk.var.monte_carlo`.
pub fn monte_carlo(
    mean: &[f64],
    covariance: &[Vec<f64>],
    weights: &[f64],
    paths: i64,
    seed: u64,
    c: f64,
) -> Result<VarEs> {
    crate::error::finite("mean", &mean)?;
    crate::error::finite("covariance", &covariance)?;
    crate::error::finite("weights", &weights)?;
    let n = mean.len();
    if n == 0
        || weights.len() != n
        || covariance.len() != n
        || covariance.iter().any(|r| r.len() != n)
    {
        return fail("E_INPUT", "mean, covariance and weights must agree in size");
    }
    if paths < 1 {
        return fail("E_DOMAIN", "paths must be at least 1");
    }
    check_confidence(c)?;
    if (0..n).any(|i| (0..i).any(|j| covariance[i][j] != covariance[j][i])) {
        return fail("E_DOMAIN", "covariance must be symmetric");
    }
    // Ruling F-39: a non-positive pivot is `E_NOT_POSITIVE_DEFINITE`.
    let l = cholesky(&covariance.to_vec())?;
    let mut rng = Xoshiro::seeded(seed, 0);
    let mut z = vec![0.0; n];
    let mut pnl = Vec::with_capacity(paths as usize);
    for _ in 0..paths {
        for v in &mut z {
            *v = rng.next_normal();
        }
        let mut p = 0.0;
        for i in 0..n {
            let mut r = mean[i];
            for k in 0..=i {
                r += l[i][k] * z[k];
            }
            p += weights[i] * r;
        }
        pnl.push(p);
    }
    Ok(order_statistic(&pnl, c))
}

/// `x ln y` with `0 ln 0 = 0`.
fn xlny(x: f64, y: f64) -> f64 {
    if x == 0.0 { 0.0 } else { x * y.ln() }
}

/// Ruling F-32.
fn floor_lr(lr: f64) -> f64 {
    if lr < 1e-12 { 0.0 } else { lr }
}

fn chi2_sf(x: f64, df: u8) -> f64 {
    if x <= 0.0 {
        return 1.0;
    }
    match df {
        1 => 2.0 * normal_cdf(-x.sqrt()),
        _ => (-x / 2.0).exp(),
    }
}

fn lr_uc(n: f64, x: f64, p: f64) -> f64 {
    let ph = x / n;
    let lr =
        -2.0 * (xlny(n - x, 1.0 - p) + xlny(x, p)) + 2.0 * (xlny(n - x, 1.0 - ph) + xlny(x, ph));
    floor_lr(lr)
}

/// `risk.backtest.kupiec`: `(lr_uc, p_value)`.
pub fn kupiec(observations: i64, exceptions: i64, c: f64) -> Result<(f64, f64)> {
    check_confidence(c)?;
    if observations < 1 || exceptions < 0 || exceptions > observations {
        return fail(
            "E_DOMAIN",
            "need 0 <= exceptions <= observations and observations >= 1",
        );
    }
    let lr = lr_uc(observations as f64, exceptions as f64, 1.0 - c);
    Ok((lr, chi2_sf(lr, 1)))
}

#[derive(Debug, Clone, PartialEq)]
pub struct Christoffersen {
    pub lr_uc: f64,
    pub lr_ind: f64,
    pub lr_cc: f64,
    pub p_uc: f64,
    pub p_ind: f64,
    pub p_cc: f64,
    /// `n00, n01, n10, n11`.
    pub transitions: [i64; 4],
}

/// `risk.backtest.christoffersen`.
pub fn christoffersen(exceptions: &[bool], c: f64) -> Result<Christoffersen> {
    if exceptions.len() < 2 {
        return fail("E_INPUT", "at least two observations");
    }
    check_confidence(c)?;
    let n = exceptions.len() as f64;
    let x = exceptions.iter().filter(|e| **e).count() as f64;
    let uc = lr_uc(n, x, 1.0 - c);
    let mut t = [0i64; 4];
    for w in exceptions.windows(2) {
        t[usize::from(w[0]) * 2 + usize::from(w[1])] += 1;
    }
    let [n00, n01, n10, n11] = t.map(|v| v as f64);
    let ratio = |a: f64, b: f64| if b == 0.0 { 0.0 } else { a / b };
    let (p01, p11, pi) = (
        ratio(n01, n00 + n01),
        ratio(n11, n10 + n11),
        (n01 + n11) / (n - 1.0),
    );
    let ind = floor_lr(
        -2.0 * (xlny(n00 + n10, 1.0 - pi) + xlny(n01 + n11, pi)
            - xlny(n00, 1.0 - p01)
            - xlny(n01, p01)
            - xlny(n10, 1.0 - p11)
            - xlny(n11, p11)),
    );
    let cc = uc + ind;
    Ok(Christoffersen {
        lr_uc: uc,
        lr_ind: ind,
        lr_cc: cc,
        p_uc: chi2_sf(uc, 1),
        p_ind: chi2_sf(ind, 1),
        p_cc: chi2_sf(cc, 2),
        transitions: t,
    })
}

/// `risk.backtest.traffic_light`: `(cumulative_probability, zone, plus_factor)`.
pub fn traffic_light(
    observations: i64,
    exceptions: i64,
    c: f64,
) -> Result<(f64, &'static str, Option<f64>)> {
    check_confidence(c)?;
    if observations < 1 || exceptions < 0 {
        return fail(
            "E_DOMAIN",
            "observations must be positive and exceptions not negative",
        );
    }
    let (n, p) = (observations, 1.0 - c);
    let x = exceptions;
    // P(X <= x) by summing pmf in log space.
    let (lp, lq) = (p.ln(), (-p).ln_1p());
    let mut lpmf = n as f64 * lq;
    let mut cdf = lpmf.exp();
    for k in 0..x {
        lpmf += ((n - k) as f64).ln() - ((k + 1) as f64).ln() + lp - lq;
        cdf += lpmf.exp();
    }
    let cdf = cdf.min(1.0);
    let zone = if cdf < 0.95 {
        "GREEN"
    } else if cdf < 0.9999 {
        "YELLOW"
    } else {
        "RED"
    };
    let plus = (n == 250 && c == 0.99).then_some(match exceptions {
        0..=4 => 0.0,
        5 => 0.40,
        6 => 0.50,
        7 => 0.65,
        8 => 0.75,
        9 => 0.85,
        _ => 1.0,
    });
    Ok((cdf, zone, plus))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn monte_carlo_shape_errors() {
        let cov = vec![vec![1.0, 0.0], vec![0.0, 1.0]];
        let m = [0.0, 0.0];
        let code = |r: Result<VarEs>| r.unwrap_err().code;
        assert_eq!(
            code(monte_carlo(&m, &cov, &[1.0, 1.0, 1.0], 10, 1, 0.99)),
            "E_INPUT"
        );
        assert_eq!(code(monte_carlo(&m, &cov, &[1.0], 10, 1, 0.99)), "E_INPUT");
        assert_eq!(code(monte_carlo(&[], &[], &[], 10, 1, 0.99)), "E_INPUT");
        assert_eq!(
            code(monte_carlo(&[0.0], &cov, &[1.0], 10, 1, 0.99)),
            "E_INPUT"
        );
        let ragged = vec![vec![1.0, 0.0], vec![0.0]];
        assert_eq!(
            code(monte_carlo(&m, &ragged, &[1.0, 1.0], 10, 1, 0.99)),
            "E_INPUT"
        );
        assert_eq!(
            code(monte_carlo(&m, &cov, &[1.0, 1.0], 0, 1, 0.99)),
            "E_DOMAIN"
        );
        assert_eq!(
            code(monte_carlo(&m, &cov, &[1.0, 1.0], 10, 1, 1.0)),
            "E_DOMAIN"
        );
        assert!(monte_carlo(&m, &cov, &[1.0, 1.0], 10, 1, 0.99).is_ok());
    }

    #[test]
    fn third_largest_of_250_at_99() {
        let pnl: Vec<f64> = (0..250).map(|i| -f64::from(i)).collect();
        let r = historical(&pnl, 0.99).unwrap();
        assert_eq!(r.var, 247.0);
        assert_eq!(r.tail_count, 3);
        // R6-3.1 by hand: w = 2.5, es = (249 + 248 + 0.5 * 247) / 2.5 = 248.2.
        assert!((r.es - 248.2).abs() < 1e-12, "{}", r.es);
        // integer tail: n = 500 at 99%, w = 5, mean of the five largest losses 497 to 499 ... 495.
        let pnl: Vec<f64> = (0..500).map(|i| -f64::from(i)).collect();
        let r = historical(&pnl, 0.99).unwrap();
        assert!((r.es - 497.0).abs() < 1e-9 && r.tail_count == 5, "{r:?}");
    }

    #[test]
    fn kupiec_at_expected_count_is_zero() {
        let (lr, p) = kupiec(1000, 10, 0.99).unwrap();
        assert_eq!(lr, 0.0);
        assert_eq!(p, 1.0);
    }
}
