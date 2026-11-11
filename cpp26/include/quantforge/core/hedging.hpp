#pragma once
// Stage I wave 1, hedge solvers (specifications/08-hedging/hedge-solvers.md; rulings I-1 to I-14).
// Every rank or singularity decision compares with 1e-12 times the largest value of the stated matrix (I-3).
#include <array>
#include <optional>
#include <string>
#include <vector>

#include "quantforge/core/credit.hpp"
#include "quantforge/core/linalg.hpp"

namespace quantforge::hedging {

using Vec = std::vector<double>;
using Bound = std::optional<double>;

/// The one relative threshold of ruling I-3.
inline constexpr double singular_threshold = 1e-12;

/// Symmetric eigen-decomposition by cyclic Jacobi. values ascending; vectors[i][k] is entry i of the
/// unit eigenvector of values[k]. unchecked: caller guarantees a finite symmetric square matrix.
struct Eigen {
    Vec values;
    Matrix vectors;
};
Eigen jacobi_eigen(Matrix s);

enum class Singular { Error, MinNorm };

/// hedge.qp.solve: minimise sum_i w_i (A x + b)_i^2 + ridge |x|^2 subject to E x = e and the bounds.
struct QpProblem {
    Matrix a;
    Vec b, weights;
    double ridge = 0.0;
    std::optional<Matrix> eq_matrix;
    std::optional<Vec> eq_rhs;
    std::optional<std::vector<Bound>> lower, upper;
    Singular singular = Singular::Error;
    // Wave 4a (08-hedging/hedge-costs-and-frontier.md, I-24 to I-27): C(x) = sum hs |x| + impact x^2,
    // weighted by cost_weight (default 1), and sum margin_rates |x| <= margin_limit.
    std::optional<Vec> half_spreads, impact, margin_rates;
    std::optional<double> cost_weight, margin_limit;
};
struct QpResult {
    Vec x, residual;
    double objective = 0.0;
    long long rank = 0;
    bool costed = false, margined = false;  // which of the I-27 outputs to write
    double risk = 0.0, cost = 0.0, margin = 0.0;
};
/// Checks in the spec's order: E_INPUT, E_DOMAIN, E_SINGULAR, E_INFEASIBLE.
QpResult solve_qp(const QpProblem& p);
namespace detail {
/// Test oracle for the wave 4a solve (ruling I-48): every closed sign orthant of at most 20 open-sign
/// instruments, one QP each. Not used by the operation.
QpResult solve_qp_by_orthants(const QpProblem& p);
}  // namespace detail

/// hedge.integer.solve: the same objective over x = lot_sizes * n, n integer within optional lot bounds.
struct IntegerProblem {
    Matrix a;
    Vec b, weights;
    double ridge = 0.0;
    Vec lot_sizes;
    std::optional<std::vector<std::optional<long long>>> lower_lots, upper_lots;
};
struct IntegerResult {
    std::vector<long long> lots;
    Vec x, residual;
    double objective = 0.0, continuous_objective = 0.0, rounding_cost = 0.0;
};
IntegerResult solve_integer(const IntegerProblem& p);

/// hedge.minvar.ratio. Index 0 of the covariance is the position, 1..k one unit of each hedge.
struct MinVarResult {
    Vec hedge;
    double variance_before = 0.0, variance_after = 0.0, effectiveness = 0.0;
};
MinVarResult min_variance(const Matrix& covariance);
/// Sample covariance (divisor T - 1) of the exposure and hedge series, index 0 the exposure.
/// E_INPUT for k < 1, unequal lengths or T < k + 2.
Matrix sample_covariance(const Vec& exposure, const Matrix& hedge_series);

enum class Instrument { Call, Put, Underlying };
struct Position {
    Instrument instrument = Instrument::Underlying;
    std::optional<double> strike, expiry_years;
    double quantity = 0.0;
};
struct Market {
    double spot = 0.0, rate = 0.0, dividend_yield = 0.0, volatility = 0.0;
};
struct Greeks {
    double delta = 0.0, gamma = 0.0, vega = 0.0;
};
enum class Greek { Delta, Gamma, Vega };
/// Per-unit Black-Scholes-Merton Greeks; vega per unit of volatility (I-9). unchecked: caller validates.
Greeks unit_greeks(const Market& m, const Position& p);
struct GreekHedge {
    Vec quantities;
    Greeks before, after;
};
GreekHedge neutralise(const Market& m, const std::vector<Position>& book, const std::vector<Position>& hedges,
                      const std::vector<Greek>& targets);

enum class Rounding { Nearest, None };
struct BetaHedge {
    double contracts = 0.0, contracts_held = 0.0, beta_after = 0.0;
};
BetaHedge beta_futures(double value, double beta, double target_beta, double futures_price, double multiplier,
                       Rounding rounding);

struct ResidualReport {
    Vec residual;
    double variance_before = 0.0, variance_after = 0.0, volatility_after = 0.0, effectiveness = 0.0;
    Vec contributions;
};
ResidualReport residual_report(const Matrix& a, const Vec& b, const Vec& x, const Matrix& covariance);

// ---- wave 2: credit and correlation hedges (08-hedging/credit-and-correlation-hedges.md, I-15 to I-19) ----

struct CdsContract {
    Date maturity;
    double coupon = 0.0;
    double notional = 1.0;
    bool buy = true;  // side: BUY_PROTECTION
};
/// One target: CS01, JTD, or BUCKET_k (bucket = k - 1).
struct CreditTarget {
    enum class Kind { Cs01, Jtd, Bucket } kind = Kind::Cs01;
    std::size_t bucket = 0;
    bool operator==(const CreditTarget&) const = default;
};
struct CreditRisk {
    double pv = 0.0, cs01 = 0.0, jtd = 0.0;
    Vec buckets;
};
/// pv, CS01, JTD and bucket CS01s of one unit of bought protection (I-15, I-16).
CreditRisk unit_credit_risk(Date trade_date, const Curve& discount, const HazardCurve& hazard, double recovery,
                            Date maturity, double coupon);
struct CreditHedge {
    Vec notionals;
    CreditRisk book, after;
    double hedge_upfront = 0.0;
};
/// Checks 2 to 4 of hedge.credit.cds; the discount interpolation check (1) is the caller's.
/// targets: CS01, JTD or BUCKET_1 to BUCKET_P; any other name is E_INPUT.
CreditHedge credit_hedge(Date trade_date, const Curve& discount, const HazardCurve& hazard, double recovery,
                         const std::vector<CdsContract>& book, const std::vector<CdsContract>& hedges,
                         const std::vector<std::string>& targets);

enum class TwoAssetKind { Exchange, Call1, Put1, Call2, Put2, Underlying1, Underlying2 };
struct TwoAssetPosition {
    TwoAssetKind kind = TwoAssetKind::Underlying1;
    double quantity1 = 0.0, quantity2 = 0.0, strike = 0.0, expiry_years = 0.0;
    double quantity = 0.0;
};
struct TwoAssetMarket {
    double spot1 = 0.0, spot2 = 0.0, rate = 0.0, yield1 = 0.0, yield2 = 0.0, vol1 = 0.0, vol2 = 0.0, correlation = 0.0;
};
/// delta_1, delta_2, vega_1, vega_2 (per unit volatility), correlation01 (per 0.01; I-18).
using TwoAssetGreeks = std::array<double, 5>;
enum class TwoAssetTarget { Delta1, Delta2, Vega1, Vega2, Correlation };
TwoAssetGreeks unit_two_asset_greeks(const TwoAssetMarket& m, const TwoAssetPosition& p);
struct CorrelationHedge {
    Vec quantities;
    TwoAssetGreeks before{}, after{};
};
/// Checks 2 and 3 of hedge.correlation.neutralise; key sets (check 1) are the caller's.
CorrelationHedge correlation_hedge(const TwoAssetMarket& m, const std::vector<TwoAssetPosition>& book,
                                   const std::vector<TwoAssetPosition>& hedges,
                                   const std::vector<TwoAssetTarget>& targets);

// ---- wave 3: cross-asset hedge, equity and rates (08-hedging/cross-asset-hedge.md, I-20 to I-23) ----

/// Continuously compounded zero rates on ACT/365F pillar times: linear between pillars, flat before the
/// first, undefined after the last (I-20).
struct ZeroCurve {
    Vec times, zero_rates;
};
/// Check 1 of hedge.crossasset.solve: E_INPUT on an empty, ragged or non-increasing curve.
void check_zero_curve(const ZeroCurve& c);

enum class CrossAssetKind { Call, Put, Forward, Zcb, Underlying };
struct CrossAssetPosition {
    CrossAssetKind kind = CrossAssetKind::Underlying;
    double strike = 0.0, expiry_years = 0.0, notional = 0.0, quantity = 0.0;
};
/// Value of one unit, discounting on the curve.
double cross_asset_value(double spot, double dividend_yield, double volatility, const ZeroCurve& c,
                         const CrossAssetPosition& p);
/// EQ01 then KR01_1..KR01_P of one unit, by the half-differences of I-21.
Vec cross_asset_risk(double spot, double dividend_yield, double volatility, const ZeroCurve& c,
                     const CrossAssetPosition& p);
struct CrossAssetHedge {
    Vec positions, book_risk, residual_risk;
    double objective = 0.0;
};
/// Checks 1 and 2 (except key sets, the caller's), then 3 to 5 of hedge.crossasset.solve.
CrossAssetHedge cross_asset_hedge(double spot, double dividend_yield, double volatility, const ZeroCurve& c,
                                  const std::vector<CrossAssetPosition>& book,
                                  const std::vector<CrossAssetPosition>& hedges, const Vec& weights, double ridge);

// ---- wave 4b: dynamic delta-hedge backtest and effectiveness (08-hedging/dynamic-hedge-and-effectiveness.md) ----

struct Effectiveness {
    double dollar_offset = 0.0, regression_slope = 0.0, regression_r2 = 0.0, variance_reduction = 0.0;
};
/// hedge.effectiveness (I-30, I-31): E_INPUT on unequal lengths or fewer than 3 values; E_DOMAIN when the item
/// changes sum to zero or either series has zero sample variance.
Effectiveness effectiveness(const Vec& item_changes, const Vec& hedge_changes);

struct BacktestOption {
    bool call = true;
    double strike = 0.0, expiry_years = 0.0;
};
struct DeltaBacktest {
    Vec option_values, shares, portfolio_values;
    double final_pnl = 0.0;
    Effectiveness stats;
    bool costed = false;  // trading_cost is output only with a cost input (I-40)
    double trading_cost = 0.0;
};
/// Wave 4e (I-39): a trade of dq shares costs half_spread |dq| + impact dq^2.
struct BacktestCosts {
    std::optional<double> half_spread, impact;
};
/// hedge.backtest.delta: the self-financing replay of I-29 on the given path, with the I-39 costs when given.
DeltaBacktest backtest_delta(const BacktestOption& option, double quantity, double rate, double dividend_yield,
                             double hedge_volatility, const Vec& times, const Vec& spots,
                             const BacktestCosts& costs = {});

// ---- wave 4c: instrument selection (08-hedging/instrument-selection.md, I-33 to I-35) ----

struct SelectResult {
    std::vector<long long> selected;  // 0-based, ascending
    Vec x, residual;
    double objective = 0.0;
};
/// hedge.select.solve: the best subset of at most max_instruments columns (I-34). forbidden_keys: eq_matrix,
/// eq_rhs or singular was given (E_INPUT, I-33).
SelectResult select_instruments(const QpProblem& p, long long max_instruments, bool forbidden_keys);

// ---- wave 4d: hedge slippage (08-hedging/hedge-slippage.md, I-36 to I-38) ----

struct Fill {
    double quantity = 0.0, price = 0.0;
};
struct Order {
    double quantity = 0.0, decision_price = 0.0, final_price = 0.0, half_spread = 0.0, impact = 0.0;
    std::vector<Fill> fills;
};
struct Slippage {
    double filled_quantity = 0.0;
    std::optional<double> average_price;  // null with no fills (I-37)
    double execution_cost = 0.0, opportunity_cost = 0.0, shortfall = 0.0, model_cost = 0.0, slippage = 0.0;
};
struct SlippageReport {
    std::vector<Slippage> orders;
    Slippage total;  // sums of the five costs
};
SlippageReport slippage_report(const std::vector<Order>& orders);

}  // namespace quantforge::hedging
