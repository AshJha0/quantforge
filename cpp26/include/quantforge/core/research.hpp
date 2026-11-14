#pragma once
// Stage J wave 1 research operations (specifications/11-research/, rulings J-1 to J-19): backtester, purged CV,
// Viterbi regimes, PSR, DSR, power and PBO by CSCV. Callers check E_SCHEMA, E_LIMIT and F-2 first; each function
// raises its page's E_INPUT and E_DOMAIN checks in the page's order.
#include <cstdint>
#include <optional>
#include <vector>

namespace quantforge::research {

inline constexpr double euler_gamma = 0.5772156649015329;

// ---- backtester.md ----
enum class Engine { Event, Vector };

struct BacktestInput {
    std::vector<double> prices, targets;
    long long lag = 1;
    double half_spread_bps = 0, commission_per_unit = 0, fixed_per_trade = 0, multiplier = 1;
};

struct Backtest {
    std::vector<double> positions, trades, pnl_gross, cost, pnl_net, equity;
    double total_gross = 0, total_spread = 0, total_commission = 0, total_fixed = 0, total_net = 0, turnover = 0;
    long long trade_count = 0;
    double max_drawdown = 0;
};

/// The page's E_INPUT then E_DOMAIN checks.
void check_backtest(const BacktestInput& in);
/// Both engines follow the event-loop definition (J-3); runs check_backtest first.
Backtest backtest(const BacktestInput& in, Engine engine);

// ---- purged-cv.md ----
struct Fold {
    std::vector<long long> test, train;
};
struct PurgedKFold {
    std::vector<Fold> folds;
    long long embargo_count = 0;
};
PurgedKFold purged_kfold(const std::vector<double>& t0, const std::vector<double>& t1, long long k, double embargo_pct);

struct CpcvCounts {
    long long n_splits, n_paths;
};
CpcvCounts cpcv_paths(long long n_groups, long long n_test_groups);

// ---- regimes.md ----
struct ViterbiResult {
    std::vector<long long> states;
    double log_probability;
};
/// Non-negative entries, rows summing to 1 within 1e-9 (E_DOMAIN).
void check_model(const std::vector<double>& initial, const std::vector<std::vector<double>>& transition);
/// Logs of a direct T x K emission matrix; negative entries are E_DOMAIN.
std::vector<std::vector<double>> log_emission(const std::vector<std::vector<double>>& e);
/// Gaussian log densities, T x K; sd <= 0 is E_DOMAIN.
std::vector<std::vector<double>> gaussian_log_emission(const std::vector<double>& y, const std::vector<double>& means,
                                                       const std::vector<double>& sds);
/// Viterbi in logs, ties to the smallest index (J-11); every path of zero probability is E_DOMAIN.
ViterbiResult viterbi(const std::vector<double>& initial, const std::vector<std::vector<double>>& transition,
                      const std::vector<std::vector<double>>& log_e);

// ---- research-statistics.md ----
struct Psr {
    double z, psr;
};
Psr psr(double sr, long long n_obs, double skew, double kurtosis, double sr_benchmark);

struct Dsr {
    double sr0, z, dsr;
};
Dsr dsr(double sr, long long n_obs, double skew, double kurtosis, long long n_trials, double sr_variance);

struct Power {
    double z_sum, mds, se_at_zero;
    std::optional<double> years_required, se_at_target;
};
Power power(double years, double alpha, double power, std::optional<double> sr_target);

enum class Metric { Sharpe, Mean };
struct Pbo {
    double pbo;
    std::vector<double> logits;
    long long n_combinations;
};
/// Shape checks of J-15 (E_INPUT).
void check_pbo_shape(const std::vector<std::vector<double>>& perf, long long s);
Pbo pbo(const std::vector<std::vector<double>>& perf, long long s, Metric metric);

}  // namespace quantforge::research
