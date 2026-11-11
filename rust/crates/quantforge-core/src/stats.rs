//! Distributions and moments (`statistics-and-time-series.md`).

use crate::error::{Result, fail};

/// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
pub fn mean(x: &[f64]) -> f64 {
    x.iter().sum::<f64>() / x.len() as f64
}

/// True when all values are equal. Rounding in a mean cannot fake a non-zero variance here.
/// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
pub fn is_constant(x: &[f64]) -> bool {
    x.iter().all(|v| *v == x[0])
}

/// The mean and deviations from it, by way of a shift to the first value. The shift is exact for
/// nearby values, so a large offset does not reach the moments through a rounded mean.
/// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
pub fn centered(x: &[f64]) -> (f64, Vec<f64>) {
    let y: Vec<f64> = x.iter().map(|v| v - x[0]).collect();
    let my = mean(&y);
    (x[0] + my, y.iter().map(|v| v - my).collect())
}

/// Two-pass sample variance, divisor `n - 1`.
/// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
pub fn variance(x: &[f64]) -> f64 {
    let m = mean(x);
    x.iter().map(|v| (v - m) * (v - m)).sum::<f64>() / (x.len() - 1) as f64
}

// Cody's rational approximations for erf and erfc (Math. Comp. 1969; CALERF).
const A: [f64; 5] = [
    3.16112374387056560e0,
    1.13864154151050156e2,
    3.77485237685302021e2,
    3.20937758913846947e3,
    1.85777706184603070e-1,
];
const B: [f64; 4] = [
    2.36012909523441209e1,
    2.44024637934444173e2,
    1.28261652607737228e3,
    2.84423683343917062e3,
];
const C: [f64; 9] = [
    5.64188496988670089e-1,
    8.88314979438837594e0,
    6.61191906371416295e1,
    2.98635138197400131e2,
    8.81952221241769090e2,
    1.71204761263407058e3,
    2.05107837782607147e3,
    1.23033935479799725e3,
    2.15311535474403846e-8,
];
const D: [f64; 8] = [
    1.57449261107098347e1,
    1.17693950891312499e2,
    5.37181101862009858e2,
    1.62138957456669019e3,
    3.29079923573345963e3,
    4.36261909014324716e3,
    3.43936767414372164e3,
    1.23033935480374942e3,
];
const P: [f64; 6] = [
    3.05326634961232344e-1,
    3.60344899949804439e-1,
    1.25781726111229246e-1,
    1.60837851487422766e-2,
    6.58749161529837803e-4,
    1.63153871373020978e-2,
];
const Q: [f64; 5] = [
    2.56852019228982242e0,
    1.87295284992346725e0,
    5.27905102951428412e-1,
    6.05183413124413191e-2,
    2.33520497626869185e-3,
];

const ERF_SPLIT: f64 = 0.46875;

/// erf for `|x| <= ERF_SPLIT`.
fn erf_small(x: f64) -> f64 {
    let z = x * x;
    let mut num = A[4] * z;
    let mut den = z;
    for i in 0..3 {
        num = (num + A[i]) * z;
        den = (den + B[i]) * z;
    }
    x * (num + A[3]) / (den + B[3])
}

/// `exp(y^2) erfc(y)` for `y > ERF_SPLIT`.
fn erfcx(y: f64) -> f64 {
    if y <= 4.0 {
        let mut num = C[8] * y;
        let mut den = y;
        for i in 0..7 {
            num = (num + C[i]) * y;
            den = (den + D[i]) * y;
        }
        (num + C[7]) / (den + D[7])
    } else {
        let z = 1.0 / (y * y);
        let mut num = P[5] * z;
        let mut den = z;
        for i in 0..4 {
            num = (num + P[i]) * z;
            den = (den + Q[i]) * z;
        }
        let r = z * (num + P[4]) / (den + Q[4]);
        (1.0 / std::f64::consts::PI.sqrt() - r) / y
    }
}

/// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
pub fn normal_pdf(x: f64) -> f64 {
    (-x * x / 2.0).exp() / (2.0 * std::f64::consts::PI).sqrt()
}

/// `N(x)`. The Gaussian factor is formed from `x` itself, split so that `x^2/2` loses no bits;
/// going through `y = |x|/sqrt 2` would cost about 1e-13 relative at `x = -37`.
/// unchecked: caller guarantees finite inputs (F-4). NaN or infinity in gives NaN out.
pub fn normal_cdf(x: f64) -> f64 {
    let ax = x.abs();
    let y = ax / std::f64::consts::SQRT_2;
    if y <= ERF_SPLIT {
        let e = erf_small(y);
        return if x < 0.0 {
            0.5 * (1.0 - e)
        } else {
            0.5 * (1.0 + e)
        };
    }
    let head = (ax * 16.0).trunc() / 16.0;
    let del = (ax - head) * (ax + head);
    let tail = 0.5 * erfcx(y) * (-head * head / 2.0).exp() * (-del / 2.0).exp();
    if x < 0.0 { tail } else { 1.0 - tail }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Summary {
    pub count: i64,
    pub mean: f64,
    pub variance: f64,
    pub stdev: f64,
    pub skewness: Option<f64>,
    pub excess_kurtosis: Option<f64>,
    pub min: f64,
    pub max: f64,
}

pub fn summary(x: &[f64]) -> Result<Summary> {
    crate::error::finite("x", &x)?;
    if x.len() < 2 {
        return fail("E_INPUT", "at least 2 values are needed");
    }
    let n = x.len() as f64;
    let (m, d) = centered(x);
    let central = |k: i32| d.iter().map(|v| v.powi(k)).sum::<f64>() / n;
    let constant = is_constant(x);
    let var = if constant {
        0.0
    } else {
        d.iter().map(|v| v * v).sum::<f64>() / (n - 1.0)
    };
    let (m2, m3, m4) = (central(2), central(3), central(4));
    Ok(Summary {
        count: x.len() as i64,
        mean: m,
        variance: var,
        stdev: var.sqrt(),
        skewness: (!constant).then(|| m3 / m2.powf(1.5)),
        excess_kurtosis: (!constant).then(|| m4 / (m2 * m2) - 3.0),
        min: x.iter().copied().fold(f64::INFINITY, f64::min),
        max: x.iter().copied().fold(f64::NEG_INFINITY, f64::max),
    })
}

pub fn quantile(x: &[f64], p: &[f64]) -> Result<Vec<f64>> {
    crate::error::finite("x", &x)?;
    crate::error::finite("p", &p)?;
    if x.is_empty() {
        return fail("E_INPUT", "at least 1 value is needed");
    }
    if p.iter().any(|v| *v < 0.0 || *v > 1.0) {
        return fail("E_DOMAIN", "p must lie in [0, 1]");
    }
    let mut s = x.to_vec();
    s.sort_by(f64::total_cmp);
    let n = s.len();
    Ok(p.iter()
        .map(|&q| {
            let h = (n - 1) as f64 * q;
            let k = h.floor() as usize;
            if k + 1 >= n {
                s[n - 1]
            } else {
                s[k] + (h - k as f64) * (s[k + 1] - s[k])
            }
        })
        .collect())
}

fn cross(x: &[f64], y: &[f64]) -> f64 {
    let (dx, dy) = (centered(x).1, centered(y).1);
    dx.iter().zip(&dy).map(|(a, b)| a * b).sum::<f64>()
}

pub fn covariance(x: &[f64], y: &[f64]) -> Result<(f64, Option<f64>)> {
    crate::error::finite("x", &x)?;
    crate::error::finite("y", &y)?;
    if x.len() != y.len() || x.len() < 2 {
        return fail("E_INPUT", "equal lengths of at least 2 are needed");
    }
    let cov = cross(x, y) / (x.len() - 1) as f64;
    let corr = (!is_constant(x) && !is_constant(y))
        .then(|| cross(x, y) / (cross(x, x).sqrt() * cross(y, y).sqrt()));
    Ok((cov, corr))
}

#[derive(Debug, Clone, PartialEq)]
pub struct Ols {
    pub alpha: f64,
    pub beta: f64,
    pub r_squared: Option<f64>,
    pub se_alpha: f64,
    pub se_beta: f64,
    pub rss: f64,
}

pub fn ols(x: &[f64], y: &[f64]) -> Result<Ols> {
    crate::error::finite("x", &x)?;
    crate::error::finite("y", &y)?;
    if x.len() != y.len() || x.len() < 3 {
        return fail("E_INPUT", "equal lengths of at least 3 are needed");
    }
    if is_constant(x) {
        return fail("E_SINGULAR", "x has zero variance");
    }
    let n = x.len() as f64;
    let (mx, my) = (centered(x).0, centered(y).0);
    let sxx = cross(x, x);
    let beta = cross(x, y) / sxx;
    let alpha = my - beta * mx;
    let rss: f64 = x
        .iter()
        .zip(y)
        .map(|(a, b)| {
            let e = b - alpha - beta * a;
            e * e
        })
        .sum();
    let s2 = rss / (n - 2.0);
    Ok(Ols {
        alpha,
        beta,
        r_squared: (!is_constant(y)).then(|| 1.0 - rss / cross(y, y)),
        se_alpha: (s2 * (1.0 / n + mx * mx / sxx)).sqrt(),
        se_beta: (s2 / sxx).sqrt(),
        rss,
    })
}

impl crate::error::Finite for Ols {
    fn is_all_finite(&self) -> bool {
        self.alpha.is_all_finite()
            && self.beta.is_all_finite()
            && self.r_squared.is_all_finite()
            && self.se_alpha.is_all_finite()
            && self.se_beta.is_all_finite()
            && self.rss.is_all_finite()
    }
}

impl crate::error::Finite for Summary {
    fn is_all_finite(&self) -> bool {
        self.mean.is_all_finite()
            && self.variance.is_all_finite()
            && self.stdev.is_all_finite()
            && self.skewness.is_all_finite()
            && self.excess_kurtosis.is_all_finite()
            && self.min.is_all_finite()
            && self.max.is_all_finite()
    }
}

/// Regularised lower incomplete gamma `P(s, x)` for `s > 0`, `x >= 0`.
///
/// Series `x^s e^{-x} / Gamma(s+1) * sum x^n / ((s+1)...(s+n))` for `x < s + 1`, otherwise
/// `1 - Q(s, x)` with `Q` by the modified Lentz continued fraction. Both stop at a relative
/// step of `1e-17`; accuracy is limited by the Lanczos `ln Gamma` (about 1e-15 relative in
/// the prefactor). unchecked: caller guarantees finite inputs with `s > 0` (F-4).
pub fn gamma_p(s: f64, x: f64) -> f64 {
    if x <= 0.0 {
        return 0.0;
    }
    let ln_pre = s * x.ln() - x - crate::garch_estimate::lgamma(s);
    if x < s + 1.0 {
        let (mut term, mut sum, mut d) = (1.0 / s, 1.0 / s, s);
        for _ in 0..10_000 {
            d += 1.0;
            term *= x / d;
            sum += term;
            if term.abs() < sum.abs() * 1e-17 {
                break;
            }
        }
        (ln_pre.exp() * sum).min(1.0)
    } else {
        let tiny = 1e-300;
        let mut b = x + 1.0 - s;
        let mut c = 1.0 / tiny;
        let mut d = 1.0 / b;
        let mut h = d;
        for i in 1..10_000 {
            let an = -f64::from(i) * (f64::from(i) - s);
            b += 2.0;
            d = an * d + b;
            if d.abs() < tiny {
                d = tiny;
            }
            c = b + an / c;
            if c.abs() < tiny {
                c = tiny;
            }
            d = 1.0 / d;
            let del = d * c;
            h *= del;
            if (del - 1.0).abs() < 1e-17 {
                break;
            }
        }
        (1.0 - ln_pre.exp() * h).max(0.0)
    }
}

/// Noncentral chi-square CDF `P(X <= x)` with `k > 0` degrees of freedom and noncentrality
/// `lambda >= 0`, as the Poisson-weighted sum `sum_j e^{-lambda/2} (lambda/2)^j / j!
/// P(k/2 + j, x/2)` (Johnson, Kotz and Balakrishnan, *Continuous Univariate Distributions*
/// vol. 2, eq. 29.2).
///
/// The sum starts at the Poisson mode with a log weight and recurs up and down until both the
/// weight and the term fall below `1e-17` of the mode weight and the sum (ruling G-32), so the
/// truncation error is far below the rounding of the terms and nothing underflows. Checked against 50-digit values in the `shortrate_g` CIR option goldens to
/// better than 1e-12 relative. unchecked: caller guarantees finite inputs (F-4).
pub fn noncentral_chi2_cdf(x: f64, k: f64, lambda: f64) -> f64 {
    if x <= 0.0 {
        return 0.0;
    }
    let (h, y, s0) = (lambda / 2.0, x / 2.0, k / 2.0);
    if h == 0.0 {
        return gamma_p(s0, y);
    }
    // G-32: start at the Poisson mode with a log weight (exp(-lambda/2) alone underflows for
    // lambda/2 > 745), then recur the weights up and down.
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    let j0 = h.floor().min(1e9) as u32;
    let jf0 = f64::from(j0);
    let w0 = (-h + jf0 * h.ln() - crate::garch_estimate::lgamma(jf0 + 1.0)).exp();
    let mut sum = w0 * gamma_p(s0 + jf0, y);
    let (mut w, mut j) = (w0, j0);
    loop {
        w *= h / f64::from(j + 1);
        j += 1;
        let term = w * gamma_p(s0 + f64::from(j), y);
        sum += term;
        if (term <= sum * 1e-17 && w <= w0 * 1e-17) || j - j0 > 1_000_000 {
            break;
        }
    }
    let (mut w, mut j) = (w0, j0);
    while j > 0 {
        w *= f64::from(j) / h;
        j -= 1;
        let term = w * gamma_p(s0 + f64::from(j), y);
        sum += term;
        if term <= sum * 1e-17 && w <= w0 * 1e-17 {
            break;
        }
    }
    sum.min(1.0)
}

#[cfg(test)]
mod chi2_tests {
    use super::*;

    #[test]
    fn gamma_p_known_values() {
        // P(1, x) = 1 - e^{-x}
        for x in [0.1, 1.0, 2.5, 10.0] {
            assert!((gamma_p(1.0, x) - (1.0 - f64::exp(-x))).abs() < 1e-14);
        }
        // P(1/2, x) = erf(sqrt x) = 2 N(sqrt(2x)) - 1
        for x in [0.2_f64, 1.7, 6.0] {
            let e = 2.0 * normal_cdf((2.0 * x).sqrt()) - 1.0;
            assert!((gamma_p(0.5, x) - e).abs() < 1e-14);
        }
        assert_eq!(gamma_p(2.0, 0.0), 0.0);
    }

    #[test]
    fn central_limit_and_monotone() {
        // lambda = 0 is the central chi-square: k = 2 gives 1 - e^{-x/2}.
        assert!((noncentral_chi2_cdf(3.0, 2.0, 0.0) - (1.0 - f64::exp(-1.5))).abs() < 1e-14);
        let mut prev = 0.0;
        for i in 1..50 {
            let v = noncentral_chi2_cdf(f64::from(i), 3.0, 7.5);
            assert!(v >= prev && v <= 1.0);
            prev = v;
        }
        assert_eq!(noncentral_chi2_cdf(-1.0, 3.0, 1.0), 0.0);
        // Mean k + lambda: the CDF there is a little above one half.
        let m = noncentral_chi2_cdf(10.0, 4.0, 6.0);
        assert!(m > 0.5 && m < 0.6);
    }

    #[test]
    fn small_lambda_continuity() {
        let a = noncentral_chi2_cdf(5.0, 3.0, 1e-12);
        let b = noncentral_chi2_cdf(5.0, 3.0, 0.0);
        assert!((a - b).abs() < 1e-12);
    }
}
