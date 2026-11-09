//! Time series (`statistics-and-time-series.md`).
use crate::dates::Date;
use crate::error::{Result, fail};
use crate::stats::{centered, is_constant, mean, ols};

pub fn returns(prices: &[f64], log: bool) -> Result<Vec<f64>> {
    crate::error::finite("prices", &prices)?;
    if prices.len() < 2 {
        return fail("E_INPUT", "at least 2 prices are needed");
    }
    if prices.iter().any(|p| *p <= 0.0) {
        return fail("E_DOMAIN", "prices must be positive");
    }
    Ok(prices
        .windows(2)
        .map(|w| {
            if log {
                (w[1] / w[0]).ln()
            } else {
                w[1] / w[0] - 1.0
            }
        })
        .collect())
}

pub fn rolling(x: &[f64], window: i64, stdev: bool) -> Result<Vec<Option<f64>>> {
    crate::error::finite("x", &x)?;
    if window < 2 || window > x.len() as i64 {
        return fail("E_INPUT", "window out of range");
    }
    let w = window as usize;
    let mut out = vec![None; w - 1];
    out.extend(x.windows(w).map(|s| {
        Some(if !stdev {
            mean(s)
        } else if is_constant(s) {
            0.0
        } else {
            let d = centered(s).1;
            (d.iter().map(|v| v * v).sum::<f64>() / (w - 1) as f64).sqrt()
        })
    }));
    Ok(out)
}

pub fn ewma_variance(r: &[f64], lambda: f64) -> Result<Vec<f64>> {
    crate::error::finite("r", &r)?;
    crate::error::finite("lambda", &lambda)?;
    if r.is_empty() {
        return fail("E_INPUT", "at least 1 return is needed");
    }
    if lambda <= 0.0 || lambda >= 1.0 {
        return fail("E_DOMAIN", "lambda must lie in (0, 1)");
    }
    let mut out = Vec::with_capacity(r.len());
    let mut v = r[0] * r[0];
    out.push(v);
    for x in &r[1..] {
        v = lambda * v + (1.0 - lambda) * x * x;
        out.push(v);
    }
    Ok(out)
}

pub fn autocorrelation(x: &[f64], max_lag: i64) -> Result<Vec<f64>> {
    crate::error::finite("x", &x)?;
    if max_lag < 1 || max_lag >= x.len() as i64 {
        return fail("E_INPUT", "max_lag out of range");
    }
    if is_constant(x) {
        return fail("E_DOMAIN", "zero variance");
    }
    let d = centered(x).1;
    let den: f64 = d.iter().map(|v| v * v).sum();
    Ok((1..=max_lag as usize)
        .map(|k| (k..d.len()).map(|t| d[t] * d[t - k]).sum::<f64>() / den)
        .collect())
}

pub fn ljung_box(x: &[f64], max_lag: i64) -> Result<f64> {
    crate::error::finite("x", &x)?;
    let acf = autocorrelation(x, max_lag)?;
    let n = x.len() as f64;
    let s: f64 = acf
        .iter()
        .enumerate()
        .map(|(i, a)| a * a / (n - (i + 1) as f64))
        .sum();
    Ok(n * (n + 2.0) * s)
}

/// Returns `(constant, phi, sigma)`.
pub fn ar1(x: &[f64]) -> Result<(f64, f64, f64)> {
    crate::error::finite("x", &x)?;
    if x.len() < 4 {
        return fail("E_INPUT", "at least 4 values are needed");
    }
    let fit = ols(&x[..x.len() - 1], &x[1..])?;
    let sigma = (fit.rss / (x.len() - 3) as f64).sqrt();
    Ok((fit.alpha, fit.beta, sigma))
}

pub fn resample_last(
    dates: &[Date],
    values: &[Option<f64>],
    monthly: bool,
) -> Result<(Vec<Date>, Vec<f64>)> {
    crate::error::finite("values", &values)?;
    if dates.len() != values.len() {
        return fail("E_INPUT", "dates and values differ in length");
    }
    if dates.windows(2).any(|w| w[1] <= w[0]) {
        return fail("E_INPUT", "dates must be strictly increasing");
    }
    let bucket = |d: Date| {
        if monthly {
            i64::from(d.y) * 12 + i64::from(d.m)
        } else {
            (d.serial() + 3).div_euclid(7)
        }
    };
    let (mut od, mut ov): (Vec<Date>, Vec<f64>) = (Vec::new(), Vec::new());
    for (d, v) in dates.iter().zip(values) {
        let Some(v) = v else { continue };
        if od.last().is_some_and(|l| bucket(*l) == bucket(*d)) {
            *od.last_mut().expect("not empty") = *d;
            *ov.last_mut().expect("not empty") = *v;
        } else {
            od.push(*d);
            ov.push(*v);
        }
    }
    Ok((od, ov))
}

pub fn forward_fill(values: &[Option<f64>], limit: i64) -> Result<Vec<Option<f64>>> {
    crate::error::finite("values", &values)?;
    if limit < 1 {
        return fail("E_INPUT", "limit must be at least 1");
    }
    let mut last: Option<(usize, f64)> = None;
    Ok(values
        .iter()
        .enumerate()
        .map(|(i, v)| match (v, last) {
            (Some(x), _) => {
                last = Some((i, *x));
                Some(*x)
            }
            (None, Some((j, x))) if (i - j) as i64 <= limit => Some(x),
            _ => None,
        })
        .collect())
}
