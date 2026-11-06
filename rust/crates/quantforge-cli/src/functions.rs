//! The test function registry (`test-functions.md`). Lives in the CLI layer only.
use quantforge_core::stats::{normal_cdf, normal_pdf};

pub type Fun = fn(f64) -> f64;

/// `d1` for `S = K = 100`, `r = 0.01`, `q = 0`, `T = 1`.
fn bs_d1(x: f64) -> f64 {
    (0.01 + x * x / 2.0) / x
}

fn bs_vol_atm(x: f64) -> f64 {
    let d1 = bs_d1(x);
    100.0 * normal_cdf(d1) - 100.0 * (-0.01f64).exp() * normal_cdf(d1 - x) - 10.0
}

fn bs_vega(x: f64) -> f64 {
    100.0 * normal_pdf(bs_d1(x))
}

/// `f` and `df` for root finding.
pub fn root_function(name: &str) -> Option<(Fun, Fun)> {
    Some(match name {
        "cubic_wallis" => (|x| x * x * x - 2.0 * x - 5.0, |x| 3.0 * x * x - 2.0),
        "cos_minus_x" => (|x| x.cos() - x, |x| -x.sin() - 1.0),
        "exp_minus_two" => (|x| x.exp() - 2.0, f64::exp),
        "triple_root" => (|x| (x - 1.0).powi(3), |x| 3.0 * (x - 1.0).powi(2)),
        "square" => (|x| x * x, |x| 2.0 * x),
        "no_real_root" => (|x| x * x + 1.0, |x| 2.0 * x),
        "steep_atan" => (
            |x| (1000.0 * (x - 0.3)).atan(),
            |x| 1000.0 / (1.0 + 1e6 * (x - 0.3) * (x - 0.3)),
        ),
        "bs_vol_atm" => (bs_vol_atm, bs_vega),
        _ => return None,
    })
}

/// `f` for integration and differentiation.
pub fn plain_function(name: &str) -> Option<Fun> {
    Some(match name {
        "exp" => f64::exp,
        "sin" => f64::sin,
        "runge" => |x| 1.0 / (1.0 + 25.0 * x * x),
        "sqrt" => f64::sqrt,
        "inv_sqrt" => |x| 1.0 / x.sqrt(),
        "normal_pdf" => normal_pdf,
        "oscillatory" => |x| (50.0 * x).cos() * (-x).exp(),
        "poly5" => |x| x.powi(5) - 3.0 * x * x + 1.0,
        _ => return None,
    })
}
