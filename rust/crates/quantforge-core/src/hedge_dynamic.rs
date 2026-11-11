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
    // I-43: relative tests, as rounding leaves a zero hedge leg at about 1e-28 of the item.
    let abs_sum: f64 = x.iter().map(|v| v.abs()).sum();
    if sx.abs() <= 1e-12 * abs_sum || vx <= 1e-20 * vy || vy <= 1e-20 * vx {
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
    /// Wave 4e cost per share traded, `half_spread |dq| + impact dq^2` (I-39); absent is 0.
    pub half_spread: Option<f64>,
    pub impact: Option<f64>,
}

impl BacktestSetup {
    fn trade_cost(&self, dq: f64) -> f64 {
        self.half_spread.unwrap_or(0.0) * dq.abs() + self.impact.unwrap_or(0.0) * dq * dq
    }

    fn costed(&self) -> bool {
        self.half_spread.is_some() || self.impact.is_some()
    }
}

/// Outputs of `hedge.backtest.delta`.
#[derive(Debug, Clone, PartialEq)]
pub struct Backtest {
    pub option_values: Vec<f64>,
    pub shares: Vec<f64>,
    pub portfolio_values: Vec<f64>,
    pub final_pnl: f64,
    pub effectiveness: Effectiveness,
    /// Sum of the costs paid, present only with a cost input (I-40).
    pub trading_cost: Option<f64>,
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
    /// Undiscounted sum of the trading costs paid (0 without cost inputs).
    pub trading_cost: f64,
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
    finite("costs", &[b.half_spread, b.impact])?;
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
    if b.half_spread.is_some_and(|v| v < 0.0) || b.impact.is_some_and(|v| v < 0.0) {
        return fail("E_DOMAIN", "half_spread and impact must be non-negative");
    }
    let marks: Vec<(f64, f64)> = times
        .iter()
        .zip(spots)
        .map(|(t, s)| mark(o, b, *s, o.expiry - t))
        .collect();
    let q = b.quantity;
    let shares: Vec<f64> = marks[..m - 1].iter().map(|(_, d)| -q * d).collect();
    // The initial purchase is a trade (I-39): Pi_0 = -cost(h_0), 0 without costs.
    let mut paid = b.trade_cost(shares[0]);
    let mut cash = -q * marks[0].0 - shares[0] * spots[0] - paid;
    let mut portfolio = vec![0.0; m];
    portfolio[0] = 0.0 - paid;
    for i in 0..m - 1 {
        let dt = times[i + 1] - times[i];
        cash = cash * (b.rate * dt).exp()
            + shares[i] * spots[i] * ((b.dividend_yield * dt).exp() - 1.0);
        portfolio[i + 1] = q * marks[i + 1].0 + shares[i] * spots[i + 1] + cash;
        if i + 2 < m {
            let dq = shares[i + 1] - shares[i];
            let cost = b.trade_cost(dq);
            paid += cost;
            cash -= dq * spots[i + 1] + cost;
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
        trading_cost: paid,
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
        trading_cost: b.costed().then_some(r.trading_cost),
    })
}

/// An order of `hedge.slippage.report`: signed `quantity` (positive buys) and its fills
/// `(quantity, price)`.
#[derive(Debug, Clone, PartialEq)]
pub struct Order {
    pub quantity: f64,
    pub decision_price: f64,
    pub final_price: f64,
    pub half_spread: f64,
    pub impact: f64,
    pub fills: Vec<(f64, f64)>,
}

/// Costs of one order or of all orders (rulings I-36, I-37).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SlippageCosts {
    pub execution_cost: f64,
    pub opportunity_cost: f64,
    pub shortfall: f64,
    pub model_cost: f64,
    pub slippage: f64,
}

/// One order's report: `average_price` is `None` when nothing was filled.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct OrderSlippage {
    pub filled_quantity: f64,
    pub average_price: Option<f64>,
    pub costs: SlippageCosts,
}

/// `hedge.slippage.report`: implementation shortfall of each order against its decision
/// price, and its slippage against the wave 4a cost model; `total` sums the orders.
///
/// # Errors
/// `E_DOMAIN` for a non-finite input; `E_INPUT` (no orders, a zero order, a fill of zero or of
/// the other sign, overfilled); `E_DOMAIN` (a price at or below 0, a negative cost parameter).
pub fn slippage_report(orders: &[Order]) -> Result<(Vec<OrderSlippage>, SlippageCosts)> {
    for o in orders {
        finite(
            "orders",
            &[
                o.quantity,
                o.decision_price,
                o.final_price,
                o.half_spread,
                o.impact,
            ],
        )?;
        finite("fills", &o.fills)?;
    }
    if orders.is_empty()
        || orders.iter().any(|o| {
            let filled: f64 = o.fills.iter().map(|f| f.0).sum();
            o.quantity == 0.0
                || o.fills.iter().any(|f| f.0 * o.quantity <= 0.0)
                || filled.abs() > o.quantity.abs()
        })
    {
        return fail(
            "E_INPUT",
            "orders non-zero, fills of the order's sign and not above it",
        );
    }
    if orders.iter().any(|o| {
        o.decision_price <= 0.0
            || o.final_price <= 0.0
            || o.fills.iter().any(|f| f.1 <= 0.0)
            || o.half_spread < 0.0
            || o.impact < 0.0
    }) {
        return fail("E_DOMAIN", "prices positive, cost parameters non-negative");
    }
    let mut total = SlippageCosts {
        execution_cost: 0.0,
        opportunity_cost: 0.0,
        shortfall: 0.0,
        model_cost: 0.0,
        slippage: 0.0,
    };
    let reports = orders
        .iter()
        .map(|o| {
            let d = o.decision_price;
            let filled: f64 = o.fills.iter().map(|f| f.0).sum();
            let notional: f64 = o.fills.iter().map(|f| f.0 * f.1).sum();
            let execution_cost: f64 = o.fills.iter().map(|f| f.0 * (f.1 - d)).sum();
            let opportunity_cost = (o.quantity - filled) * (o.final_price - d);
            let model_cost = o.half_spread * filled.abs() + o.impact * filled * filled;
            let c = SlippageCosts {
                execution_cost,
                opportunity_cost,
                shortfall: execution_cost + opportunity_cost,
                model_cost,
                slippage: execution_cost - model_cost,
            };
            total.execution_cost += c.execution_cost;
            total.opportunity_cost += c.opportunity_cost;
            total.shortfall += c.shortfall;
            total.model_cost += c.model_cost;
            total.slippage += c.slippage;
            OrderSlippage {
                filled_quantity: filled,
                average_price: (!o.fills.is_empty()).then(|| notional / filled),
                costs: c,
            }
        })
        .collect();
    Ok((reports, total))
}
