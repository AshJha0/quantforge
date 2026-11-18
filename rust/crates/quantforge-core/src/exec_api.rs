//! Typed in-process API for the execution and microstructure layer (stage H item H-5,
//! `specifications/10-execution/library-interfaces.md`; ADR-0011).
//!
//! Closed choices are enums parsed once at the edge (`E_SCHEMA` otherwise); inputs are value
//! types validated when built, so none can exist in an invalid state; every call delegates to the
//! kernel in [`crate::execution`], so the numbers are the kernel's, bit for bit. The kernels stay
//! as they are for the CLI.
//!
//! Thread safety: every function here is pure and holds no state; safe to call from any number of
//! threads.
use crate::error::{QfError, Result};
use crate::execution as k;

pub use crate::execution::Amount;

fn error(code: &'static str, field: &str, why: &str) -> QfError {
    QfError {
        code,
        message: format!("{field}: {why}"),
        field: Some(field.to_string()),
    }
}

fn finite(field: &str, xs: &[f64]) -> Result<()> {
    if xs.iter().all(|x| x.is_finite()) {
        Ok(())
    } else {
        Err(error("E_DOMAIN", field, "must be finite"))
    }
}

/// Order side. Thread safety: immutable; safe to share between threads.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Side {
    Buy,
    Sell,
}

impl Side {
    /// The JSON spelling to the enum, once, at the edge; anything else is `E_SCHEMA`.
    pub fn parse(text: &str) -> Result<Self> {
        match text {
            "BUY" => Ok(Self::Buy),
            "SELL" => Ok(Self::Sell),
            _ => Err(error(
                "E_SCHEMA",
                "side",
                &format!("unknown value {text:?}"),
            )),
        }
    }
    /// The JSON spelling.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Buy => "BUY",
            Self::Sell => "SELL",
        }
    }
}

/// Whole units or continuous quantities. Thread safety: immutable; safe to share between threads.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FillMode {
    Units,
    Continuous,
}

impl FillMode {
    /// The JSON spelling to the enum, once, at the edge; anything else is `E_SCHEMA`.
    pub fn parse(text: &str) -> Result<Self> {
        match text {
            "UNITS" => Ok(Self::Units),
            "CONTINUOUS" => Ok(Self::Continuous),
            _ => Err(error(
                "E_SCHEMA",
                "mode",
                &format!("unknown value {text:?}"),
            )),
        }
    }
    /// The JSON spelling.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Units => "UNITS",
            Self::Continuous => "CONTINUOUS",
        }
    }
    fn units(self) -> bool {
        self == Self::Units
    }
}

/// Almgren-Chriss model inputs (\[AC00\], HR-2, HR-5), checked when built by the kernel's own
/// check, in the order of `almgren-chriss.md`. Thread safety: immutable; safe to share between
/// threads.
#[derive(Debug, Clone, Copy)]
pub struct AcParams(k::AcParams);

impl AcParams {
    pub fn new(
        quantity: f64,
        horizon: f64,
        n_steps: i64,
        sigma: f64,
        epsilon: f64,
        eta: f64,
        gamma: f64,
    ) -> Result<Self> {
        finite(
            "ac_params",
            &[quantity, horizon, sigma, epsilon, eta, gamma],
        )?;
        let p = k::AcParams {
            quantity,
            horizon,
            n_steps,
            sigma,
            epsilon,
            eta,
            gamma,
        };
        k::ac_check(&p)?;
        Ok(Self(p))
    }
    pub fn quantity(&self) -> f64 {
        self.0.quantity
    }
    pub fn horizon(&self) -> f64 {
        self.0.horizon
    }
    pub fn n_steps(&self) -> i64 {
        self.0.n_steps
    }
    pub fn sigma(&self) -> f64 {
        self.0.sigma
    }
    pub fn epsilon(&self) -> f64 {
        self.0.epsilon
    }
    pub fn eta(&self) -> f64 {
        self.0.eta
    }
    pub fn gamma(&self) -> f64 {
        self.0.gamma
    }
    /// The kernel's parameter struct.
    pub fn kernel(&self) -> &k::AcParams {
        &self.0
    }
}

/// One execution. Thread safety: immutable; safe to share between threads.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Fill {
    quantity: f64,
    price: f64,
}

impl Fill {
    pub fn new(quantity: f64, price: f64) -> Result<Self> {
        finite("fills", &[quantity, price])?;
        if quantity <= 0.0 {
            return Err(error(
                "E_INPUT",
                "fills",
                "fill quantities must be positive",
            ));
        }
        if price <= 0.0 {
            return Err(error("E_DOMAIN", "fills", "prices must be positive"));
        }
        Ok(Self { quantity, price })
    }
    pub fn quantity(&self) -> f64 {
        self.quantity
    }
    pub fn price(&self) -> f64 {
        self.price
    }
}

/// Child-order slices; `residual` is zero except for POV. Thread safety: immutable; safe to share
/// between threads.
#[derive(Debug, Clone, PartialEq)]
pub struct Schedule {
    slices: Vec<Amount>,
    filled: Amount,
    residual: Amount,
}

impl Schedule {
    pub fn slices(&self) -> &[Amount] {
        &self.slices
    }
    pub fn filled(&self) -> Amount {
        self.filled
    }
    pub fn residual(&self) -> Amount {
        self.residual
    }
}

fn schedule(slices: Vec<Amount>, mode: FillMode) -> Schedule {
    let (filled, residual) = if mode.units() {
        let n = slices
            .iter()
            .map(|a| match a {
                Amount::Units(n) => *n,
                Amount::Real(x) => *x as i64,
            })
            .sum();
        (Amount::Units(n), Amount::Units(0))
    } else {
        (
            Amount::Real(slices.iter().map(|a| a.value()).sum()),
            Amount::Real(0.0),
        )
    };
    Schedule {
        slices,
        filled,
        residual,
    }
}

/// Holdings `x_0..x_N`, trades `n_1..n_N`, kappa, E, V and E + lambda V. Thread safety: immutable;
/// safe to share between threads.
#[derive(Debug, Clone, PartialEq)]
pub struct AcTrajectory(k::AcPoint);

impl AcTrajectory {
    pub fn holdings(&self) -> &[f64] {
        &self.0.holdings
    }
    pub fn trades(&self) -> &[f64] {
        &self.0.trades
    }
    pub fn kappa(&self) -> f64 {
        self.0.kappa
    }
    pub fn expected_cost(&self) -> f64 {
        self.0.expected_cost
    }
    pub fn variance(&self) -> f64 {
        self.0.variance
    }
    pub fn objective(&self) -> f64 {
        self.0.objective
    }
}

/// One (lambda, E, V) per input, in input order; equal lengths. Thread safety: immutable; safe to
/// share between threads.
#[derive(Debug, Clone, PartialEq)]
pub struct AcFrontier {
    risk_aversions: Vec<f64>,
    expected_costs: Vec<f64>,
    variances: Vec<f64>,
}

impl AcFrontier {
    pub fn risk_aversions(&self) -> &[f64] {
        &self.risk_aversions
    }
    pub fn expected_costs(&self) -> &[f64] {
        &self.expected_costs
    }
    pub fn variances(&self) -> &[f64] {
        &self.variances
    }
}

/// Obizhaeva-Wang optimal blocks and rate. Thread safety: immutable; safe to share between threads.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct OwOptimal {
    initial_block: f64,
    rate: f64,
    final_block: f64,
}

impl OwOptimal {
    pub fn initial_block(&self) -> f64 {
        self.initial_block
    }
    pub fn rate(&self) -> f64 {
        self.rate
    }
    pub fn final_block(&self) -> f64 {
        self.final_block
    }
}

/// Perold decomposition (HR-8); `vwap_slippage` is `None` without a benchmark. Thread safety:
/// immutable; safe to share between threads.
#[derive(Debug, Clone, PartialEq)]
pub struct Shortfall(k::Shortfall);

impl Shortfall {
    pub fn delay(&self) -> f64 {
        self.0.delay
    }
    pub fn execution(&self) -> f64 {
        self.0.execution
    }
    pub fn opportunity(&self) -> f64 {
        self.0.opportunity
    }
    pub fn total(&self) -> f64 {
        self.0.total
    }
    pub fn total_bps(&self) -> f64 {
        self.0.total_bps
    }
    pub fn vwap_slippage(&self) -> Option<f64> {
        self.0.vwap_slippage
    }
}

/// Avellaneda-Stoikov reservation price, spread and quotes; bid <= ask (`E_DOMAIN`). Thread
/// safety: immutable; safe to share between threads.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Quotes(k::Quotes);

impl Quotes {
    pub fn new(reservation: f64, spread: f64, bid: f64, ask: f64) -> Result<Self> {
        if bid <= ask {
            Ok(Self(k::Quotes {
                reservation,
                spread,
                bid,
                ask,
            }))
        } else {
            Err(error("E_DOMAIN", "bid", "bid must not exceed ask"))
        }
    }
    pub fn reservation(&self) -> f64 {
        self.0.reservation
    }
    pub fn spread(&self) -> f64 {
        self.0.spread
    }
    pub fn bid(&self) -> f64 {
        self.0.bid
    }
    pub fn ask(&self) -> f64 {
        self.0.ask
    }
}

/// `exec.schedule.twap`.
pub fn twap(quantity: f64, n_buckets: i64, mode: FillMode) -> Result<Schedule> {
    finite("quantity", &[quantity])?;
    Ok(schedule(
        k::schedule_twap(quantity, n_buckets, mode.units())?,
        mode,
    ))
}

/// `exec.schedule.vwap`.
pub fn vwap(quantity: f64, profile: &[f64], mode: FillMode) -> Result<Schedule> {
    finite("quantity", &[quantity])?;
    finite("profile", profile)?;
    Ok(schedule(
        k::schedule_vwap(quantity, profile, mode.units())?,
        mode,
    ))
}

/// `exec.schedule.pov`.
pub fn pov(
    quantity: f64,
    participation: f64,
    market_volume: &[f64],
    mode: FillMode,
) -> Result<Schedule> {
    finite("quantity", &[quantity])?;
    finite("participation", &[participation])?;
    finite("market_volume", market_volume)?;
    let p = k::schedule_pov(quantity, participation, market_volume, mode.units())?;
    Ok(Schedule {
        slices: p.slices,
        filled: p.filled,
        residual: p.residual,
    })
}

/// `exec.ac.trajectory`.
pub fn ac_trajectory(params: &AcParams, risk_aversion: f64) -> Result<AcTrajectory> {
    finite("risk_aversion", &[risk_aversion])?;
    Ok(AcTrajectory(k::ac_trajectory(&params.0, risk_aversion)?))
}

/// `exec.ac.frontier`.
pub fn ac_frontier(params: &AcParams, risk_aversions: &[f64]) -> Result<AcFrontier> {
    finite("risk_aversions", risk_aversions)?;
    let pts = k::ac_frontier(&params.0, risk_aversions)?;
    Ok(AcFrontier {
        risk_aversions: risk_aversions.to_vec(),
        expected_costs: pts.iter().map(|p| p.expected_cost).collect(),
        variances: pts.iter().map(|p| p.variance).collect(),
    })
}

/// `exec.impact.sqrt`: impact as a fraction of price; assumed coefficient (HR-10).
pub fn impact_sqrt(
    quantity: f64,
    daily_volume: f64,
    daily_vol: f64,
    coefficient: f64,
) -> Result<f64> {
    finite("impact", &[quantity, daily_volume, daily_vol, coefficient])?;
    k::impact_sqrt(quantity, daily_volume, daily_vol, coefficient)
}

/// `exec.impact.ow_optimal`.
pub fn ow_optimal(quantity: f64, horizon: f64, resilience: f64) -> Result<OwOptimal> {
    finite("ow_optimal", &[quantity, horizon, resilience])?;
    let (block, rate) = k::impact_ow_optimal(quantity, horizon, resilience)?;
    Ok(OwOptimal {
        initial_block: block,
        rate,
        final_block: block,
    })
}

/// `exec.tca.shortfall`.
#[allow(clippy::too_many_arguments)]
pub fn shortfall(
    side: Side,
    decision_price: f64,
    arrival_price: f64,
    end_price: f64,
    order_quantity: f64,
    fills: &[Fill],
    fees: f64,
    benchmark_vwap: Option<f64>,
) -> Result<Shortfall> {
    finite(
        "shortfall",
        &[
            decision_price,
            arrival_price,
            end_price,
            order_quantity,
            fees,
        ],
    )?;
    if let Some(v) = benchmark_vwap {
        finite("benchmark_vwap", &[v])?;
    }
    let order = k::TcaOrder {
        buy: side == Side::Buy,
        decision_price,
        arrival_price,
        end_price,
        order_quantity,
        fills: fills.iter().map(|f| (f.quantity, f.price)).collect(),
        fees,
        benchmark_vwap,
    };
    Ok(Shortfall(k::tca_shortfall(&order)?))
}

/// `micro.mm.as_quotes`.
pub fn as_quotes(
    mid: f64,
    inventory: f64,
    risk_aversion: f64,
    sigma: f64,
    time_left: f64,
    k_: f64,
) -> Result<Quotes> {
    finite(
        "as_quotes",
        &[mid, inventory, risk_aversion, sigma, time_left, k_],
    )?;
    let q = k::as_quotes(mid, inventory, risk_aversion, sigma, time_left, k_)?;
    Quotes::new(q.reservation, q.spread, q.bid, q.ask)
}

#[cfg(test)]
#[path = "exec_api_tests.rs"]
mod tests;
