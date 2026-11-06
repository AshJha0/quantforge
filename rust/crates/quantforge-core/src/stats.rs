//! Distributions and moments (`statistics-and-time-series.md`).
use crate::error::{Result, fail};

pub fn mean(x: &[f64]) -> f64 {
    x.iter().sum::<f64>() / x.len() as f64
}

/// True when all values are equal. Rounding in a mean cannot fake a non-zero variance here.
pub fn is_constant(x: &[f64]) -> bool {
    x.iter().all(|v| *v == x[0])
}

/// The mean and deviations from it, by way of a shift to the first value. The shift is exact for
/// nearby values, so a large offset does not reach the moments through a rounded mean.
pub fn centered(x: &[f64]) -> (f64, Vec<f64>) {
    let y: Vec<f64> = x.iter().map(|v| v - x[0]).collect();
    let my = mean(&y);
    (x[0] + my, y.iter().map(|v| v - my).collect())
}

/// Two-pass sample variance, divisor `n - 1`.
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

pub fn normal_pdf(x: f64) -> f64 {
    (-x * x / 2.0).exp() / (2.0 * std::f64::consts::PI).sqrt()
}

/// `N(x)`. The Gaussian factor is formed from `x` itself, split so that `x^2/2` loses no bits;
/// going through `y = |x|/sqrt 2` would cost about 1e-13 relative at `x = -37`.
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
