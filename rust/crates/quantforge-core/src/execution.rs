//! Stage H wave 1 (rulings HR-1 to HR-10): execution schedules (`10-execution/schedules.md`),
//! Almgren-Chriss trajectory and frontier (`10-execution/almgren-chriss.md`), square-root and
//! Obizhaeva-Wang impact (`10-execution/impact.md`), implementation-shortfall TCA
//! (`10-execution/tca.md`) and Avellaneda-Stoikov quotes
//! (`09-microstructure/avellaneda-stoikov.md`).
//!
//! Sources, as the specs cite them: [AC00] Almgren and Chriss, J. Risk 3(2), preprint eqs. (5),
//! (8), (16)-(19); [OW13] Obizhaeva and Wang, J. Financial Markets 16(1), eq. (31); [TLD11] Toth
//! et al., Phys. Rev. X 1, 021006, eq. (1); [Per88] Perold (recalled); [AS08] Avellaneda and
//! Stoikov, Quantitative Finance 8(3), eqs. (29)-(30).
use crate::error::{Result, fail};

/// HR-10: the label on outputs that rest on assumed, uncalibrated parameters.
pub const MODEL: &str = "assumed parameters; not calibrated to any venue";

/// A schedule slice: an integer in `UNITS` mode (HR-3), a real in `CONTINUOUS` mode.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Amount {
    Units(i64),
    Real(f64),
}

impl Amount {
    pub fn value(self) -> f64 {
        match self {
            #[allow(clippy::cast_precision_loss)]
            Amount::Units(n) => n as f64,
            Amount::Real(x) => x,
        }
    }
}

/// HR-2, HR-3: the order is positive, and a whole number of units in `UNITS` mode.
fn quantity(x: f64, units: bool) -> Result<()> {
    if x <= 0.0 {
        return fail("E_INPUT", "quantity must be positive");
    }
    if units && x != x.floor() {
        return fail(
            "E_INPUT",
            "quantity must be a whole number of units in UNITS mode",
        );
    }
    Ok(())
}

#[allow(clippy::cast_possible_truncation)]
fn whole(x: f64) -> i64 {
    x as i64
}

/// HR-3: floor every share, then give the missing units to the largest remainders, ties to the
/// earliest slice. If rounding leaves the floors above `x`, units come back from the smallest
/// remainders, ties to the latest, so the slices always sum to `x` exactly.
pub fn largest_remainder(x: f64, exact: &[f64]) -> Vec<i64> {
    let mut floors: Vec<i64> = exact.iter().map(|q| whole(q.floor())).collect();
    let rem: Vec<f64> = exact.iter().map(|q| q - q.floor()).collect();
    let short = whole(x) - floors.iter().sum::<i64>();
    let mut order: Vec<usize> = (0..exact.len()).collect();
    order.sort_by(|&a, &b| rem[b].total_cmp(&rem[a]).then(a.cmp(&b)));
    let up = usize::try_from(short.max(0)).unwrap_or(0);
    let down = usize::try_from((-short).max(0)).unwrap_or(0);
    for &k in order.iter().take(up) {
        floors[k] += 1;
    }
    for &k in order.iter().rev().take(down) {
        floors[k] -= 1;
    }
    floors
}

/// `exec.schedule.twap`: `X / N` per bucket; `UNITS` floors and hands the remainder one unit at a
/// time to the earliest slices (HR-3).
pub fn schedule_twap(x: f64, n: i64, units: bool) -> Result<Vec<Amount>> {
    quantity(x, units)?;
    if n < 1 {
        return fail("E_INPUT", "n_buckets must be at least 1");
    }
    let count = usize::try_from(n).unwrap_or(0);
    if !units {
        #[allow(clippy::cast_precision_loss)]
        let s = x / n as f64;
        return Ok(vec![Amount::Real(s); count]);
    }
    let total = whole(x);
    let (base, extra) = (total / n, total % n);
    Ok((0..n)
        .map(|k| Amount::Units(base + i64::from(k < extra)))
        .collect())
}

/// `exec.schedule.vwap`: slice i = `X w_i / sum w`; `UNITS` by largest remainder (HR-3).
pub fn schedule_vwap(x: f64, profile: &[f64], units: bool) -> Result<Vec<Amount>> {
    quantity(x, units)?;
    if profile.is_empty() {
        return fail("E_INPUT", "profile must not be empty");
    }
    if profile.iter().any(|&w| w < 0.0) {
        return fail("E_DOMAIN", "profile weights must be non-negative");
    }
    let total: f64 = profile.iter().sum();
    if total == 0.0 {
        return fail("E_DOMAIN", "profile is all zero");
    }
    let exact: Vec<f64> = profile.iter().map(|w| x * w / total).collect();
    Ok(if units {
        largest_remainder(x, &exact)
            .into_iter()
            .map(Amount::Units)
            .collect()
    } else {
        exact.into_iter().map(Amount::Real).collect()
    })
}

/// The `exec.schedule.pov` result.
#[derive(Debug, Clone, PartialEq)]
pub struct Pov {
    pub slices: Vec<Amount>,
    pub filled: Amount,
    pub residual: Amount,
}

/// `exec.schedule.pov`: child i = `min(remaining, p v_i / (1 - p))`, p of total volume including
/// own fills (HR-4); floored in `UNITS`. The residual may be positive and is never an error.
pub fn schedule_pov(x: f64, p: f64, volume: &[f64], units: bool) -> Result<Pov> {
    quantity(x, units)?;
    if !(p > 0.0 && p < 1.0) {
        return fail("E_DOMAIN", "participation must lie in (0, 1)");
    }
    if volume.is_empty() {
        return fail("E_INPUT", "market_volume must not be empty");
    }
    if volume.iter().any(|&v| v < 0.0) {
        return fail("E_DOMAIN", "market_volume must be non-negative");
    }
    let ratio = 1.0 - p;
    let (mut remaining, mut filled) = (x, 0.0);
    let mut slices = Vec::with_capacity(volume.len());
    for &v in volume {
        let mut child = remaining.min(p * v / ratio);
        if units {
            // within 1e-12 relative of an integer: snap before flooring
            let near = child.round();
            child = if (child - near).abs() <= 1e-12 * near.abs() {
                near
            } else {
                child.floor()
            };
        }
        remaining -= child;
        filled += child;
        slices.push(if units {
            Amount::Units(whole(child))
        } else {
            Amount::Real(child)
        });
    }
    let residual = remaining; // child <= remaining, so never negative
    let wrap = |v: f64| {
        if units {
            Amount::Units(whole(v))
        } else {
            Amount::Real(v)
        }
    };
    Ok(Pov {
        slices,
        filled: wrap(filled),
        residual: wrap(residual),
    })
}

/// Almgren-Chriss model parameters ([AC00] section 2).
#[derive(Debug, Clone, Copy)]
pub struct AcParams {
    pub quantity: f64,
    pub horizon: f64,
    pub n_steps: i64,
    pub sigma: f64,
    pub epsilon: f64,
    pub eta: f64,
    pub gamma: f64,
}

/// One Almgren-Chriss trajectory with its cost and risk.
#[derive(Debug, Clone, PartialEq)]
pub struct AcPoint {
    pub holdings: Vec<f64>,
    pub trades: Vec<f64>,
    pub kappa: f64,
    pub expected_cost: f64,
    pub variance: f64,
    pub objective: f64,
}

#[allow(clippy::cast_precision_loss)]
fn tau(p: &AcParams) -> f64 {
    p.horizon / p.n_steps as f64
}

/// The checks in the order of `almgren-chriss.md` (`eta_tilde`, sigma, T, then N), then the sign
/// rules of HR-2. Returns `eta_tilde = eta - gamma tau / 2` (HR-5).
fn ac_check(p: &AcParams) -> Result<f64> {
    if p.n_steps >= 1 && p.eta - p.gamma * tau(p) / 2.0 <= 0.0 {
        return fail(
            "E_DOMAIN",
            "eta_tilde = eta - gamma tau / 2 must be positive",
        );
    }
    if p.sigma < 0.0 {
        return fail("E_DOMAIN", "sigma must be non-negative");
    }
    if p.horizon <= 0.0 {
        return fail("E_DOMAIN", "horizon must be positive");
    }
    if p.n_steps < 1 {
        return fail("E_INPUT", "n_steps must be at least 1");
    }
    if p.quantity <= 0.0 {
        return fail("E_INPUT", "quantity must be positive");
    }
    if p.epsilon < 0.0 {
        return fail("E_DOMAIN", "epsilon must be non-negative");
    }
    if p.gamma < 0.0 {
        return fail("E_DOMAIN", "gamma must be non-negative");
    }
    Ok(p.eta - p.gamma * tau(p) / 2.0)
}

/// HR-6: `kappa = acosh(1 + y) / tau`, `y = lambda sigma^2 tau^2 / (2 eta_tilde)`, written
/// `log1p(y + sqrt(y (y + 2)))` so small `y` keeps its digits ([AC00] eq. (16)).
pub fn ac_kappa(lambda: f64, sigma: f64, tau: f64, eta_tilde: f64) -> f64 {
    let y = lambda * sigma * sigma * tau * tau / (2.0 * eta_tilde);
    (y + (y * (y + 2.0)).sqrt()).ln_1p() / tau
}

/// `sinh(a) / sinh(b)` for `0 <= a <= b`, `b > 0`; exponential form when `b > 700` (HR-6).
pub fn sinh_ratio(a: f64, b: f64) -> f64 {
    if b <= 700.0 {
        a.sinh() / b.sinh()
    } else {
        (a - b).exp() * (-(-2.0 * a).exp_m1()) / (-(-2.0 * b).exp_m1())
    }
}

#[allow(clippy::cast_precision_loss)]
fn ac_point(p: &AcParams, lambda: f64, eta_tilde: f64) -> Result<AcPoint> {
    if lambda < 0.0 {
        return fail("E_DOMAIN", "risk_aversion must be non-negative");
    }
    let t = tau(p);
    let n = p.n_steps;
    let x = p.quantity;
    let kappa = if lambda > 0.0 {
        ac_kappa(lambda, p.sigma, t, eta_tilde)
    } else {
        0.0
    };
    let mut holdings = Vec::with_capacity(usize::try_from(n + 1).unwrap_or(0));
    holdings.push(x);
    for j in 1..n {
        holdings.push(if kappa > 0.0 {
            x * sinh_ratio(kappa * (p.horizon - j as f64 * t), kappa * p.horizon)
        } else {
            // HR-5: lambda = 0 (or sigma = 0) is the linear trajectory, exactly
            x * (n - j) as f64 / n as f64
        });
    }
    holdings.push(0.0);
    let trades: Vec<f64> = holdings.windows(2).map(|w| w[0] - w[1]).collect();
    // [AC00] eq. (8): E = 1/2 gamma X^2 + epsilon X + (eta_tilde / tau) sum n_k^2
    let sq: f64 = trades.iter().map(|v| v * v).sum();
    let expected = 0.5 * p.gamma * x * x + p.epsilon * x + eta_tilde / t * sq;
    // [AC00] eq. (5): V = sigma^2 tau sum_{k=1..N} x_k^2
    let hx: f64 = holdings[1..].iter().map(|v| v * v).sum();
    let variance = p.sigma * p.sigma * t * hx;
    Ok(AcPoint {
        holdings,
        trades,
        kappa,
        expected_cost: expected,
        variance,
        objective: expected + lambda * variance,
    })
}

/// `exec.ac.trajectory`: `x_j = X sinh(kappa (T - t_j)) / sinh(kappa T)`, [AC00] eq. (17).
pub fn ac_trajectory(p: &AcParams, lambda: f64) -> Result<AcPoint> {
    let et = ac_check(p)?;
    ac_point(p, lambda, et)
}

/// `exec.ac.frontier`: one (lambda, E, V) per entry, in input order.
pub fn ac_frontier(p: &AcParams, lambdas: &[f64]) -> Result<Vec<AcPoint>> {
    let et = ac_check(p)?;
    if lambdas.is_empty() {
        return fail("E_INPUT", "risk_aversions must not be empty");
    }
    if lambdas.iter().any(|&l| l < 0.0) {
        return fail("E_DOMAIN", "risk_aversions must be non-negative");
    }
    lambdas.iter().map(|&l| ac_point(p, l, et)).collect()
}

/// `exec.impact.sqrt`: `I = Y sigma sqrt(Q / V)` as a fraction of price ([TLD11] eq. (1)); Y is
/// an assumed input (HR-10).
pub fn impact_sqrt(q: f64, daily_volume: f64, daily_vol: f64, coefficient: f64) -> Result<f64> {
    if q < 0.0 {
        return fail("E_DOMAIN", "quantity must be non-negative");
    }
    if daily_volume <= 0.0 {
        return fail("E_DOMAIN", "daily_volume must be positive");
    }
    if daily_vol < 0.0 {
        return fail("E_DOMAIN", "daily_vol must be non-negative");
    }
    if coefficient < 0.0 {
        return fail("E_DOMAIN", "coefficient must be non-negative");
    }
    Ok(coefficient * daily_vol * (q / daily_volume).sqrt())
}

/// `exec.impact.ow_optimal`: blocks `X / (rho T + 2)` at both ends and rate `rho X / (rho T + 2)`
/// in between ([OW13] eq. (31), p. 17). Returns (block, rate).
pub fn impact_ow_optimal(x: f64, horizon: f64, rho: f64) -> Result<(f64, f64)> {
    if x <= 0.0 {
        return fail("E_INPUT", "quantity must be positive");
    }
    if horizon <= 0.0 {
        return fail("E_DOMAIN", "horizon must be positive");
    }
    if rho <= 0.0 {
        return fail("E_DOMAIN", "resilience must be positive");
    }
    let d = rho * horizon + 2.0;
    Ok((x / d, rho * x / d))
}

/// `exec.tca.shortfall` inputs; `buy` is the side (s = +1 BUY, -1 SELL).
#[derive(Debug, Clone)]
pub struct TcaOrder {
    pub buy: bool,
    pub decision_price: f64,
    pub arrival_price: f64,
    pub end_price: f64,
    pub order_quantity: f64,
    pub fills: Vec<(f64, f64)>,
    pub fees: f64,
    pub benchmark_vwap: Option<f64>,
}

/// The shortfall decomposition (HR-8).
#[derive(Debug, Clone, PartialEq)]
pub struct Shortfall {
    pub delay: f64,
    pub execution: f64,
    pub opportunity: f64,
    pub total: f64,
    pub total_bps: f64,
    pub vwap_slippage: Option<f64>,
}

/// `exec.tca.shortfall`: Perold paper-portfolio decomposition (HR-8): delay on the executed
/// quantity, execution against arrival, opportunity on the unexecuted rest, plus fees.
pub fn tca_shortfall(o: &TcaOrder) -> Result<Shortfall> {
    let s = if o.buy { 1.0 } else { -1.0 };
    if o.order_quantity <= 0.0 {
        return fail("E_INPUT", "order_quantity must be positive");
    }
    if o.fills.iter().any(|f| f.0 <= 0.0) {
        return fail("E_INPUT", "fill quantities must be positive");
    }
    let filled: f64 = o.fills.iter().map(|f| f.0).sum();
    if filled > o.order_quantity {
        return fail("E_INPUT", "fills add up to more than the order");
    }
    let bad = [o.decision_price, o.arrival_price, o.end_price]
        .iter()
        .chain(o.fills.iter().map(|f| &f.1))
        .chain(o.benchmark_vwap.iter())
        .any(|&p| p <= 0.0);
    if bad {
        return fail("E_DOMAIN", "prices must be positive");
    }
    let delay = s * filled * (o.arrival_price - o.decision_price);
    let execution = s * o
        .fills
        .iter()
        .map(|(q, p)| q * (p - o.arrival_price))
        .sum::<f64>();
    // + 0.0 turns the -0 of a full SELL into +0
    let opportunity = s * (o.order_quantity - filled) * (o.end_price - o.decision_price) + 0.0;
    let total = delay + execution + opportunity + o.fees;
    // s Q (avg_fill - VWAP) = s (sum q_i p_i - Q VWAP): no division when Q = 0
    let vwap_slippage = o.benchmark_vwap.map(|v| {
        let notional: f64 = o.fills.iter().map(|(q, p)| q * p).sum();
        s * (notional - filled * v)
    });
    Ok(Shortfall {
        delay,
        execution,
        opportunity,
        total,
        total_bps: total / (o.order_quantity * o.decision_price) * 1e4,
        vwap_slippage,
    })
}

/// Avellaneda-Stoikov quotes.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Quotes {
    pub reservation: f64,
    pub spread: f64,
    pub bid: f64,
    pub ask: f64,
}

/// `micro.mm.as_quotes`: `r = s - q gamma sigma^2 (T - t)`, [AS08] eq. (29); spread
/// `gamma sigma^2 (T - t) + (2 / gamma) ln(1 + gamma / k)`, eq. (30); quotes symmetric about r
/// (HR-7).
pub fn as_quotes(
    mid: f64,
    inventory: f64,
    gamma: f64,
    sigma: f64,
    time_left: f64,
    k: f64,
) -> Result<Quotes> {
    if gamma <= 0.0 {
        return fail("E_DOMAIN", "risk_aversion must be positive");
    }
    if k <= 0.0 {
        return fail("E_DOMAIN", "k must be positive");
    }
    if sigma < 0.0 {
        return fail("E_DOMAIN", "sigma must be non-negative");
    }
    if time_left < 0.0 {
        return fail("E_DOMAIN", "time_left must be non-negative");
    }
    let risk = gamma * sigma * sigma * time_left;
    let reservation = mid - inventory * risk;
    let spread = risk + 2.0 / gamma * (gamma / k).ln_1p();
    Ok(Quotes {
        reservation,
        spread,
        bid: reservation - spread / 2.0,
        ask: reservation + spread / 2.0,
    })
}

/// `usecase.execution_tca` inputs beyond the AC parameters (use case 5).
#[derive(Debug, Clone)]
pub struct ExecutionTca {
    pub risk_aversion: f64,
    pub buy: bool,
    pub decision_price: f64,
    pub arrival_price: f64,
    pub end_price: f64,
    pub fill_prices: Vec<f64>,
    pub completed_steps: i64,
    pub fee_per_unit: f64,
}

/// The use case 5 result.
#[derive(Debug, Clone, PartialEq)]
pub struct ExecutionTcaResult {
    pub lots: Vec<i64>,
    pub expected_cost: f64,
    pub variance: f64,
    pub filled: i64,
    pub fees: f64,
    pub shortfall: Shortfall,
}

/// `usecase.execution_tca` (`04-pricing/use-cases.md`, use case 5): AC trades rounded to whole
/// lots by largest remainder (HR-3), the first `completed_steps` filled, then the shortfall
/// (HR-8).
pub fn execution_tca(p: &AcParams, u: &ExecutionTca) -> Result<ExecutionTcaResult> {
    let x = p.quantity;
    if x < 1.0 || x != x.floor() {
        return fail(
            "E_INPUT",
            "quantity must be a whole number of units, at least 1",
        );
    }
    if p.n_steps < 1 {
        return fail("E_INPUT", "n_steps must be at least 1");
    }
    let n = usize::try_from(p.n_steps).unwrap_or(0);
    if u.fill_prices.len() != n {
        return fail("E_INPUT", "fill_prices needs one price per step");
    }
    if u.completed_steps < 0 || u.completed_steps > p.n_steps {
        return fail("E_INPUT", "completed_steps must lie in 0..n_steps");
    }
    if u.fee_per_unit < 0.0 {
        return fail("E_DOMAIN", "fee_per_unit must be non-negative");
    }
    let t = ac_trajectory(p, u.risk_aversion)?;
    #[allow(clippy::cast_precision_loss)]
    let exact = if t.kappa == 0.0 {
        vec![x / p.n_steps as f64; n]
    } else {
        t.trades.clone()
    };
    let lots = largest_remainder(x, &exact);
    let m = usize::try_from(u.completed_steps).unwrap_or(0);
    #[allow(clippy::cast_precision_loss)]
    let fills: Vec<(f64, f64)> = (0..m).map(|k| (lots[k] as f64, u.fill_prices[k])).collect();
    let filled: i64 = lots[..m].iter().sum();
    #[allow(clippy::cast_precision_loss)]
    let fees = u.fee_per_unit * filled as f64;
    let shortfall = tca_shortfall(&TcaOrder {
        buy: u.buy,
        decision_price: u.decision_price,
        arrival_price: u.arrival_price,
        end_price: u.end_price,
        order_quantity: x,
        fills,
        fees,
        benchmark_vwap: None,
    })?;
    Ok(ExecutionTcaResult {
        lots,
        expected_cost: t.expected_cost,
        variance: t.variance,
        filled,
        fees,
        shortfall,
    })
}

#[cfg(test)]
#[path = "execution_tests.rs"]
mod tests;
