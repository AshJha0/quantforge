#pragma once
// Stage H wave 1 (rulings HR-1 to HR-10): execution schedules (10-execution/schedules.md), Almgren-Chriss
// (10-execution/almgren-chriss.md), square-root and Obizhaeva-Wang impact (10-execution/impact.md),
// implementation-shortfall TCA (10-execution/tca.md) and Avellaneda-Stoikov quotes
// (09-microstructure/avellaneda-stoikov.md).
#include <cstddef>
#include <optional>
#include <vector>

namespace quantforge::execution {

using Vec = std::vector<double>;

inline constexpr long long max_steps = 100000;        // HR-9: schedule buckets and AC steps
inline constexpr std::size_t max_fills = 1000000;      // HR-9: TCA fills
inline constexpr const char* assumed = "assumed parameters; not calibrated to any venue";  // HR-10

enum class Mode { Units, Continuous };
enum class Side { Buy, Sell };

double snap_floor(double x);  // floor, treating a value within 1e-12 relative of an integer as that integer
Vec twap(double quantity, long long n_buckets, Mode mode);
Vec vwap(double quantity, const Vec& profile, Mode mode);
struct Pov {
    Vec slices;
    double filled, residual;
};
Pov pov(double quantity, double participation, const Vec& market_volume, Mode mode);

struct AcParams {
    double quantity, horizon;
    long long n_steps;
    double sigma, epsilon, eta, gamma;
};
struct AcTrajectory {
    Vec holdings, trades;
    double kappa, expected_cost, variance, objective;
};
double ac_kappa(double lambda, double sigma, double tau, double eta_tilde);  // HR-6
AcTrajectory ac_trajectory(const AcParams& p, double risk_aversion);
struct AcFrontier {
    Vec risk_aversions, expected_cost, variance;
};
AcFrontier ac_frontier(const AcParams& p, const Vec& risk_aversions);

double impact_sqrt(double quantity, double daily_volume, double daily_vol, double coefficient);
struct OwOptimal {
    double initial_block, rate, final_block;
};
OwOptimal ow_optimal(double quantity, double horizon, double resilience);

struct Fill {
    double quantity, price;
};
struct Shortfall {
    double delay, execution, opportunity, total, total_bps;
    std::optional<double> vwap_slippage;
};
Shortfall shortfall(Side side, double decision, double arrival, double end, double order_quantity,
                    const std::vector<Fill>& fills, double fees, std::optional<double> benchmark_vwap);

struct Quotes {
    double reservation, spread, bid, ask;
};
// usecase.execution_tca (use case 5, 04-pricing/use-cases.md).
struct ExecutionTca {
    Vec lots;
    double expected_cost, variance, filled, fees;
    Shortfall shortfall;
};
ExecutionTca execution_tca(const AcParams& p, double risk_aversion, Side side, double decision, double arrival,
                           double end, const Vec& fill_prices, long long completed_steps, double fee_per_unit);

Quotes as_quotes(double mid, double inventory, double gamma, double sigma, double time_left, double k);

}  // namespace quantforge::execution
