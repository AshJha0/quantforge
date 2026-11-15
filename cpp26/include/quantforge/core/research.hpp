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


// ---- stage J wave 2 (rulings J-W2-1 to J-W2-15): optimisation.md, estimation.md, es-backtest.md, baum-welch.md ----
using Matrix2 = std::vector<std::vector<double>>;

struct MeanVariance {
    std::vector<double> weights;
    double expected_return, volatility, objective;
    std::vector<long long> at_bound;
};
/// Empty lower/upper mean the defaults 0 and 1.
MeanVariance mean_variance(const std::vector<double>& mu, const Matrix2& sigma, double gamma,
                           std::vector<double> lower, std::vector<double> upper);

struct RiskParity {
    std::vector<double> weights;
    double volatility;
    std::vector<double> contributions;
};
/// Empty budgets mean 1/N each.
RiskParity risk_parity(const Matrix2& sigma, std::vector<double> budgets);

struct Euler {
    double volatility;
    std::vector<double> marginal, contributions, shares;
};
Euler euler(const std::vector<double>& w, const Matrix2& sigma);

struct LedoitWolf {
    Matrix2 covariance;
    double shrinkage, mu;
};
LedoitWolf ledoit_wolf(const Matrix2& returns);

struct BlackLitterman {
    std::vector<double> posterior_returns;
    Matrix2 posterior_covariance, predictive_covariance;
};
BlackLitterman black_litterman(const Matrix2& sigma, const std::vector<double>& pi, const Matrix2& pick,
                               const std::vector<double>& q, const Matrix2& omega, double tau);

struct EsZ2 {
    double z2;
    long long exceptions;
    double expected_exceptions;
};
EsZ2 es_z2(const std::vector<double>& losses, const std::vector<double>& var, const std::vector<double>& es,
           double alpha);

struct BaumWelch {
    std::vector<double> initial;
    Matrix2 transition;
    std::vector<double> means, sds;
    double log_likelihood;
    long long iterations;
    bool converged;
    std::vector<double> trace;  // log-likelihood L_0 .. L_k (for property tests)
};
BaumWelch baum_welch(const std::vector<double>& y, const std::vector<double>& initial, const Matrix2& transition,
                     const std::vector<double>& means, const std::vector<double>& sds, double tolerance,
                     long long max_iterations);

// ---- stage J wave 3 (rulings J-W3-1 to J-W3-14): scenario-stress.md, interp-backtest.md, drift-detectors.md ----
struct Shock {
    std::vector<double> start_yields, end_yields, shift_bp;
    double level_bp, slope_bp;
};
/// Dates are day numbers (days since 1970-01-01), strictly increasing.
Shock historical_shock(const std::vector<long long>& dates, const std::vector<double>& tenors, const Matrix2& yields,
                       long long start, long long end);

struct Replay {
    std::vector<double> applied_bp, shocked_yields;
    std::optional<double> pnl;
};
/// An empty optional dv01 means no P&L.
Replay replay(const std::vector<double>& base_tenors, const std::vector<double>& base_yields,
              const std::vector<double>& shock_tenors, const std::vector<double>& shock_bp, double scale,
              const std::optional<std::vector<double>>& dv01);

/// method: 0 linear, 1 log_linear, 2 cubic_natural, 3 monotone_pchip.
struct LooBacktest {
    std::vector<double> errors;
    double max_abs_error, rmse;
};
LooBacktest interp_loo(int method, const std::vector<double>& x, const std::vector<double>& y);
struct SurfaceBacktest {
    Matrix2 errors;
    double max_abs_error, rmse;
};
SurfaceBacktest surface_holdout(int method, const std::vector<double>& expiries, const std::vector<double>& strikes,
                                const Matrix2& vols, const std::vector<long long>& holdout);

struct Alarms {
    std::vector<long long> alarms, directions;
    double s_plus = 0, s_minus = 0;
};
Alarms cusum(const std::vector<double>& x, double k, double h, double mu0, double sigma, bool reset);
/// direction: +1 up, -1 down, 0 both.
Alarms page_hinkley(const std::vector<double>& x, double delta, double lambda, int direction, bool reset);
struct Psi {
    double psi;
    std::vector<double> reference_shares, test_shares;
    bool alarm;
};
Psi psi(const std::vector<double>& reference, const std::vector<double>& test, long long bins, double threshold);
struct Ks {
    double statistic, p_value;
    bool reject;
};
Ks ks(const std::vector<double>& a, const std::vector<double>& b, double level);
/// Exposed for the unit tests: the 128-bit lattice count and the binary64 probability walk.
double ks_p_count(long long n, long long m, long long d);
double ks_p_walk(long long n, long long m, long long d);
/// Correctly rounded sum (Python math.fsum) for finite inputs.
double fsum(const std::vector<double>& v);

}  // namespace quantforge::research
