//! Dynamic delta-hedge backtest and hedge effectiveness
//! (`08-hedging/dynamic-hedge-and-effectiveness.md`, stage I wave 4b).

use crate::error::{Result, fail, finite};
use crate::stats::normal_cdf;

/// Outputs of `hedge.effectiveness` (rulings I-30, I-31).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Effectiveness {
    pub dollar_offset: f64,
    pub regression_slope: f64,
    pub regression_r2: f64,
    pub variance_reduction: f64,
}

/// `hedge.effectiveness`: dollar offset and regression measures of hedge changes `y` against
/// hedged-item changes `x`, sample (co)variances over `n - 1`.
///
/// # Errors
/// `E_DOMAIN` for a non-finite input; `E_INPUT` for unequal lengths or fewer than 3 values;
/// `E_DOMAIN` when `sum(x) = 0` or either series has zero sample variance.
#[allow(clippy::cast_precision_loss)]
pub fn effectiveness(x: &[f64], y: &[f64]) -> Result<Effectiveness> {
    finite("item_changes", &x)?;
    finite("hedge_changes", &y)?;
    if x.len() != y.len() || x.len() < 3 {
        return fail("E_INPUT", "need two series of one length, at least 3");
    }
    let n = x.len() as f64;
    let (mx, my) = (x.iter().sum::<f64>() / n, y.iter().sum::<f64>() / n);
    let moment = |f: &dyn Fn(usize) -> f64| (0..x.len()).map(f).sum::<f64>() / (n - 1.0);
    let vx = moment(&|i| (x[i] - mx) * (x[i] - mx));
    let vy = moment(&|i| (y[i] - my) * (y[i] - my));
    let cxy = moment(&|i| (x[i] - mx) * (y[i] - my));
    let sx: f64 = x.iter().sum();
    if sx == 0.0 || vx == 0.0 || vy == 0.0 {
        return fail(
            "E_DOMAIN",
            "the item sums to zero or a series has no variance (I-31)",
        );
    }
    let sm = mx + my;
    let vsum = moment(&|i| (x[i] + y[i] - sm) * (x[i] + y[i] - sm));
    Ok(Effectiveness {
        dollar_offset: -y.iter().sum::<f64>() / sx,
        regression_slope: cxy / vx,
        regression_r2: cxy * cxy / (vx * vy),
        variance_reduction: 1.0 - vsum / vx,
    })
}

/// The option of `hedge.backtest.delta`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BacktestOption {
    pub call: bool,
    pub strike: f64,
    pub expiry: f64,
}

/// Market and hedge settings of `hedge.backtest.delta`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BacktestSetup {
    pub quantity: f64,
    pub rate: f64,
    pub dividend_yield: f64,
    pub hedge_volatility: f64,
}

/// Outputs of `hedge.backtest.delta`.
#[derive(Debug, Clone, PartialEq)]
pub struct Backtest {
    pub option_values: Vec<f64>,
    pub shares: Vec<f64>,
    pub portfolio_values: Vec<f64>,
    pub final_pnl: f64,
    pub effectiveness: Effectiveness,
}

/// `(value, delta)` at spot `s` with `tau` to expiry; at `tau = 0` the payoff and no delta.
fn mark(o: &BacktestOption, b: &BacktestSetup, s: f64, tau: f64) -> (f64, f64) {
    if tau <= 0.0 {
        let payoff = if o.call { s - o.strike } else { o.strike - s };
        return (payoff.max(0.0), 0.0);
    }
    let v = b.hedge_volatility;
    let vs = v * tau.sqrt();
    let d1 = ((s / o.strike).ln() + (b.rate - b.dividend_yield + v * v / 2.0) * tau) / vs;
    let d2 = d1 - vs;
    let (fwd, df) = (s * (-b.dividend_yield * tau).exp(), (-b.rate * tau).exp());
    let carry = (-b.dividend_yield * tau).exp();
    if o.call {
        (
            fwd * normal_cdf(d1) - o.strike * df * normal_cdf(d2),
            carry * normal_cdf(d1),
        )
    } else {
        (
            o.strike * df * normal_cdf(-d2) - fwd * normal_cdf(-d1),
            -carry * normal_cdf(-d1),
        )
    }
}

/// The replay of ruling I-29 without the statistics: the backtest outputs with `item` and
/// `hedge` changes per step in place of the effectiveness measures.
#[derive(Debug, Clone, PartialEq)]
pub struct Replay {
    pub option_values: Vec<f64>,
    pub shares: Vec<f64>,
    pub portfolio_values: Vec<f64>,
    pub item: Vec<f64>,
    pub hedge: Vec<f64>,
}

/// Replays a self-financing delta hedge of an option position along a given path (I-29).
///
/// # Errors
/// `E_DOMAIN` for a non-finite input; `E_INPUT` (path shape, a time after expiry); `E_DOMAIN`
/// (spot, strike, expiry, volatility).
pub fn replay(
    o: &BacktestOption,
    b: &BacktestSetup,
    times: &[f64],
    spots: &[f64],
) -> Result<Replay> {
    finite("option", &[o.strike, o.expiry])?;
    finite(
        "setup",
        &[b.quantity, b.rate, b.dividend_yield, b.hedge_volatility],
    )?;
    finite("times", &times)?;
    finite("spots", &spots)?;
    let m = times.len();
    if spots.len() != m
        || m < 4
        || times[0] != 0.0
        || times.windows(2).any(|w| w[1] <= w[0])
        || times[m - 1] > o.expiry
    {
        return fail(
            "E_INPUT",
            "times from 0, increasing, at least 4, one spot each, not after expiry",
        );
    }
    if spots.iter().any(|s| *s <= 0.0)
        || o.strike <= 0.0
        || o.expiry <= 0.0
        || b.hedge_volatility <= 0.0
    {
        return fail(
            "E_DOMAIN",
            "spots, strike, expiry and hedge volatility must be positive",
        );
    }
    let marks: Vec<(f64, f64)> = times
        .iter()
        .zip(spots)
        .map(|(t, s)| mark(o, b, *s, o.expiry - t))
        .collect();
    let q = b.quantity;
    let shares: Vec<f64> = marks[..m - 1].iter().map(|(_, d)| -q * d).collect();
    let mut cash = -q * marks[0].0 - shares[0] * spots[0];
    // Pi_0 = 0: the hedge starts from zero wealth.
    let mut portfolio = vec![0.0; m];
    for i in 0..m - 1 {
        let dt = times[i + 1] - times[i];
        cash = cash * (b.rate * dt).exp()
            + shares[i] * spots[i] * ((b.dividend_yield * dt).exp() - 1.0);
        portfolio[i + 1] = q * marks[i + 1].0 + shares[i] * spots[i + 1] + cash;
        if i + 2 < m {
            cash -= (shares[i + 1] - shares[i]) * spots[i + 1];
        }
    }
    let item: Vec<f64> = (0..m - 1)
        .map(|i| q * (marks[i + 1].0 - marks[i].0))
        .collect();
    let hedge: Vec<f64> = (0..m - 1)
        .map(|i| (portfolio[i + 1] - portfolio[i]) - item[i])
        .collect();
    Ok(Replay {
        option_values: marks.iter().map(|v| v.0).collect(),
        shares,
        portfolio_values: portfolio,
        item,
        hedge,
    })
}

/// `hedge.backtest.delta`: the replay and the effectiveness of its hedge leg.
///
/// # Errors
/// The `replay` errors, then the `effectiveness` errors on the step changes (`quantity = 0`
/// is `E_DOMAIN` there, I-31).
pub fn backtest_delta(
    o: &BacktestOption,
    b: &BacktestSetup,
    times: &[f64],
    spots: &[f64],
) -> Result<Backtest> {
    let r = replay(o, b, times, spots)?;
    let effectiveness = effectiveness(&r.item, &r.hedge)?;
    Ok(Backtest {
        final_pnl: r.portfolio_values[r.portfolio_values.len() - 1],
        option_values: r.option_values,
        shares: r.shares,
        portfolio_values: r.portfolio_values,
        effectiveness,
    })
}
