//! GARCH(1,1) likelihood, forecast and fit (`05-volatility/garch.md`, rulings E-B1, E-B2).
use crate::error::{Result, fail};
use std::f64::consts::PI;

/// The variance `sigma2_1`: `Sample` is `(1/n) sum r_t^2` with no demeaning (ruling E-B1).
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Start {
    Sample,
    Given(f64),
}

#[derive(Debug, Clone, PartialEq)]
pub struct Likelihood {
    pub loglik: f64,
    pub variances: Vec<f64>,
    pub next_variance: f64,
}

fn start_variance(returns: &[f64], start: Start) -> Result<f64> {
    let v = match start {
        Start::Sample => returns.iter().map(|r| r * r).sum::<f64>() / returns.len() as f64,
        Start::Given(v) => v,
    };
    if v > 0.0 {
        Ok(v)
    } else {
        fail("E_DOMAIN", "initial variance must be positive")
    }
}

fn check_params(omega: f64, alpha: f64, beta: f64) -> Result<()> {
    if omega > 0.0 && alpha >= 0.0 && beta >= 0.0 {
        Ok(())
    } else {
        fail("E_DOMAIN", "need omega > 0, alpha >= 0, beta >= 0")
    }
}

/// The recursion and Gaussian log-likelihood with every term from `t = 1`, `s1` already checked.
fn recurse(returns: &[f64], omega: f64, alpha: f64, beta: f64, s1: f64) -> Likelihood {
    let mut variances = Vec::with_capacity(returns.len());
    let (mut s, mut sum) = (s1, 0.0);
    for r in returns {
        variances.push(s);
        sum += (2.0 * PI).ln() + s.ln() + r * r / s;
        s = omega + alpha * r * r + beta * s;
    }
    Likelihood {
        loglik: -0.5 * sum,
        variances,
        next_variance: s,
    }
}

pub fn loglik(
    returns: &[f64],
    omega: f64,
    alpha: f64,
    beta: f64,
    start: Start,
) -> Result<Likelihood> {
    if returns.len() < 2 {
        return fail("E_INPUT", "at least 2 returns are required");
    }
    check_params(omega, alpha, beta)?;
    let s1 = start_variance(returns, start)?;
    Ok(recurse(returns, omega, alpha, beta, s1))
}

#[derive(Debug, Clone, PartialEq)]
pub struct Forecast {
    pub variances: Vec<f64>,
    pub total_variance: f64,
    pub annualized_vol: f64,
    pub long_run_variance: f64,
}

pub fn forecast(
    omega: f64,
    alpha: f64,
    beta: f64,
    next_variance: f64,
    horizon: i64,
    periods_per_year: f64,
) -> Result<Forecast> {
    if horizon < 1 || periods_per_year.is_nan() || periods_per_year <= 0.0 {
        return fail(
            "E_INPUT",
            "horizon must be at least 1 and periods_per_year positive",
        );
    }
    check_params(omega, alpha, beta)?;
    if next_variance.is_nan() || next_variance <= 0.0 {
        return fail("E_DOMAIN", "next_variance must be positive");
    }
    let p = alpha + beta;
    if p >= 1.0 {
        return fail("E_DOMAIN", "alpha + beta >= 1 has no long-run variance");
    }
    let vl = omega / (1.0 - p);
    let (mut variances, mut pw) = (Vec::new(), 1.0);
    for _ in 0..horizon {
        variances.push(vl + pw * (next_variance - vl));
        pw *= p;
    }
    let total: f64 = variances.iter().sum();
    Ok(Forecast {
        annualized_vol: (total * periods_per_year / horizon as f64).sqrt(),
        total_variance: total,
        variances,
        long_run_variance: vl,
    })
}

fn logistic(x: f64) -> f64 {
    1.0 / (1.0 + (-x).exp())
}

/// Unconstrained `u` to `(omega, alpha, beta)` with `omega > 0`, `alpha, beta >= 0`, sum below 1.
fn params(u: &[f64]) -> (f64, f64, f64) {
    let (s, a) = (logistic(u[1]), logistic(u[2]));
    (u[0].exp(), s * a, s * (1.0 - a))
}

/// Nelder-Mead minimiser of `f` from `x0` with initial steps `step`. Returns point and value.
pub fn nelder_mead<F: Fn(&[f64]) -> f64>(
    f: &F,
    x0: &[f64],
    step: f64,
    iters: usize,
) -> (Vec<f64>, f64) {
    let n = x0.len();
    let mut simplex: Vec<(Vec<f64>, f64)> = (0..=n)
        .map(|i| {
            let mut x = x0.to_vec();
            if i > 0 {
                x[i - 1] += step;
            }
            let v = f(&x);
            (x, v)
        })
        .collect();
    let lerp = |a: &[f64], b: &[f64], t: f64| -> Vec<f64> {
        a.iter().zip(b).map(|(p, q)| p + t * (q - p)).collect()
    };
    for _ in 0..iters {
        simplex.sort_by(|a, b| a.1.total_cmp(&b.1));
        let (best, worst) = (simplex[0].1, simplex[n].1);
        if (worst - best).abs() <= 1e-15 * (1.0 + best.abs()) {
            break;
        }
        let centroid: Vec<f64> = (0..n)
            .map(|j| simplex[..n].iter().map(|s| s.0[j]).sum::<f64>() / n as f64)
            .collect();
        let w = simplex[n].0.clone();
        let reflect = lerp(&centroid, &w, -1.0);
        let fr = f(&reflect);
        if fr < best {
            let expand = lerp(&centroid, &w, -2.0);
            let fe = f(&expand);
            simplex[n] = if fe < fr { (expand, fe) } else { (reflect, fr) };
        } else if fr < simplex[n - 1].1 {
            simplex[n] = (reflect, fr);
        } else {
            let contract = if fr < worst {
                lerp(&centroid, &w, -0.5)
            } else {
                lerp(&centroid, &w, 0.5)
            };
            let fc = f(&contract);
            if fc < fr.min(worst) {
                simplex[n] = (contract, fc);
            } else {
                let b = simplex[0].0.clone();
                for s in simplex.iter_mut().skip(1) {
                    s.0 = lerp(&b, &s.0, 0.5);
                    s.1 = f(&s.0);
                }
            }
        }
    }
    simplex.sort_by(|a, b| a.1.total_cmp(&b.1));
    simplex.swap_remove(0)
}

#[derive(Debug, Clone, PartialEq)]
pub struct Fit {
    pub loglik: f64,
    pub omega: f64,
    pub alpha: f64,
    pub beta: f64,
}

/// Maximum likelihood with the start variance held fixed: multi-start Nelder-Mead in an
/// unconstrained parametrisation, each best point restarted until it stops improving.
pub fn fit(returns: &[f64], start: Start) -> Result<Fit> {
    if returns.len() < 30 {
        return fail("E_INPUT", "at least 30 returns are required");
    }
    let s1 = start_variance(returns, start)?;
    let sample = start_variance(returns, Start::Sample).unwrap_or(s1);
    let neg = |u: &[f64]| {
        let (o, a, b) = params(u);
        let l = recurse(returns, o, a, b, s1).loglik;
        if l.is_finite() { -l } else { f64::INFINITY }
    };
    let mut best: Option<(Vec<f64>, f64)> = None;
    for &persist in &[0.5_f64, 0.9, 0.98] {
        for &share in &[0.05_f64, 0.15, 0.3] {
            let u0 = [
                (sample * (1.0 - persist)).ln(),
                (persist / (1.0 - persist)).ln(),
                (share / (1.0 - share)).ln(),
            ];
            let (mut x, mut v) = nelder_mead(&neg, &u0, 0.5, 4000);
            for _ in 0..20 {
                let (x2, v2) = nelder_mead(&neg, &x, 0.05, 4000);
                let gain = v - v2;
                (x, v) = (x2, v2.min(v));
                if gain <= 1e-12 {
                    break;
                }
            }
            if best.as_ref().is_none_or(|b| v < b.1) {
                best = Some((x, v));
            }
        }
    }
    match best {
        Some((x, v)) if v.is_finite() => {
            let (omega, alpha, beta) = params(&x);
            Ok(Fit {
                loglik: -v,
                omega,
                alpha,
                beta,
            })
        }
        _ => fail("E_NO_CONVERGENCE", "the likelihood could not be maximised"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn worked_example() {
        let l = loglik(&[0.01, -0.02], 1e-5, 0.1, 0.8, Start::Sample).unwrap();
        assert!((l.loglik - 5.410998350356715).abs() < 1e-12);
        assert!((l.variances[1] - 2.2e-4).abs() < 1e-18);
        assert!((l.next_variance - 2.26e-4).abs() < 1e-18);
        let g = loglik(&[0.01, -0.02], 1e-5, 0.1, 0.8, Start::Given(2.5e-4)).unwrap();
        assert_eq!(g, l);
    }

    #[test]
    fn loglik_checks() {
        let r = [0.01, 0.02];
        assert_eq!(
            loglik(&[0.1], 1e-5, 0.1, 0.8, Start::Sample)
                .unwrap_err()
                .code,
            "E_INPUT"
        );
        assert_eq!(
            loglik(&r, 0.0, 0.1, 0.8, Start::Sample).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            loglik(&r, 1e-5, -0.1, 0.8, Start::Sample).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            loglik(&r, 1e-5, 0.1, -0.8, Start::Sample).unwrap_err().code,
            "E_DOMAIN"
        );
        assert_eq!(
            loglik(&r, 1e-5, 0.1, 0.8, Start::Given(0.0))
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        assert_eq!(
            loglik(&[0.0, 0.0], 1e-5, 0.1, 0.8, Start::Sample)
                .unwrap_err()
                .code,
            "E_DOMAIN"
        );
        assert!(loglik(&r, 1e-5, 0.5, 0.6, Start::Sample).is_ok());
    }

    #[test]
    fn forecast_matches_closed_form() {
        let f = forecast(1e-5, 0.1, 0.8, 2.26e-4, 5, 252.0).unwrap();
        assert!((f.long_run_variance - 1e-4).abs() < 1e-18);
        for (h, v) in f.variances.iter().enumerate() {
            let want = 1e-4 + 0.9f64.powi(h as i32) * 1.26e-4;
            assert!((v - want).abs() < 1e-18);
        }
        assert!((f.annualized_vol - (f.total_variance * 252.0 / 5.0).sqrt()).abs() < 1e-15);
        let z = forecast(1e-5, 0.0, 0.0, 2e-4, 2, 252.0).unwrap();
        assert_eq!(z.variances, vec![2e-4, 1e-5]);
    }

    #[test]
    fn forecast_checks() {
        let code = |r: Result<Forecast>| r.unwrap_err().code;
        assert_eq!(code(forecast(1e-5, 0.1, 0.8, 2e-4, 0, 252.0)), "E_INPUT");
        assert_eq!(code(forecast(1e-5, 0.1, 0.8, 2e-4, 1, 0.0)), "E_INPUT");
        assert_eq!(code(forecast(0.0, 0.1, 0.8, 2e-4, 1, 252.0)), "E_DOMAIN");
        assert_eq!(code(forecast(1e-5, 0.1, 0.8, 0.0, 1, 252.0)), "E_DOMAIN");
        assert_eq!(code(forecast(1e-5, 0.3, 0.7, 2e-4, 1, 252.0)), "E_DOMAIN");
    }

    #[test]
    fn fit_recovers_a_maximum() {
        let mut g = crate::rng::Xoshiro::seeded(11, 0);
        let (o, a, b) = (2e-6_f64, 0.08, 0.9);
        let mut s = o / (1.0 - a - b);
        let r: Vec<f64> = (0..400)
            .map(|_| {
                let x = s.sqrt() * g.next_normal();
                s = o + a * x * x + b * s;
                x
            })
            .collect();
        let f = fit(&r, Start::Sample).unwrap();
        assert!(f.alpha + f.beta < 1.0 && f.omega > 0.0);
        let at = loglik(&r, f.omega, f.alpha, f.beta, Start::Sample)
            .unwrap()
            .loglik;
        assert!((at - f.loglik).abs() < 1e-9);
        for (do_, da) in [(1.05, 1.0), (0.95, 1.0), (1.0, 1.05), (1.0, 0.95)] {
            let other = loglik(&r, f.omega * do_, f.alpha * da, f.beta, Start::Sample).unwrap();
            assert!(other.loglik <= f.loglik + 1e-9);
        }
        assert_eq!(fit(&r[..29], Start::Sample).unwrap_err().code, "E_INPUT");
        assert_eq!(fit(&r, Start::Given(-1.0)).unwrap_err().code, "E_DOMAIN");
    }

    #[test]
    fn nelder_mead_finds_a_quadratic_minimum() {
        let f = |x: &[f64]| (x[0] - 1.0).powi(2) + 3.0 * (x[1] + 2.0).powi(2);
        let (x, v) = nelder_mead(&f, &[0.0, 0.0], 1.0, 2000);
        assert!(v < 1e-12 && (x[0] - 1.0).abs() < 1e-5 && (x[1] + 2.0).abs() < 1e-5);
    }
}
