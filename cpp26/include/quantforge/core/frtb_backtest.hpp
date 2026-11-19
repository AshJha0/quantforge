#pragma once
// Stage K wave 1b, K-8e: FRTB internal models approach backtesting zones and desk-level exception limits
// (06-risk/frtb-ima-backtest.md, rulings KR-40 to KR-47). A port of python/quantforge_core/frtb_backtest.py. The
// tables come from specifications/06-risk/frtb-ima-backtest-tables.json, embedded at build time (#embed).
#include <array>
#include <optional>
#include <string>
#include <vector>

namespace quantforge::frtb_backtest {

struct Tables {
    double coverage, amber_level, red_level;
    long long table_observations;
    std::vector<double> multiplier_250;
    double multiplier_red;
    long long desk_limit_99, desk_limit_975, max_observations;
};

/// The parsed table file, built once.
const Tables& tables();

/// P(X <= x) for X ~ Binomial(n, p), 0 < p < 1 (compensated sum of log-space terms).
double binomial_cdf(long long n, long long x, double p);
/// The smallest k in 0..n with P(X <= k) >= level.
long long first_at_least(long long n, double p, double level);

struct Zone {
    long long exceptions;
    double cumulative_probability;
    std::string zone;
    long long amber_from, red_from;
    std::optional<double> multiplier;  // 250 observations only (KR-42)
};

/// risk.frtb.backtest.zone (MAR32.5, MAR32.9, MAR99.8, MAR99.17). E_LIMIT on observations first (KR-46).
Zone zone(long long observations, long long actual, long long hypothetical);

struct Desk {
    long long exceptions_99, exceptions_975;
    double cumulative_probability_99, cumulative_probability_975;
    bool breach_99, breach_975, eligible;
};

/// risk.frtb.backtest.desk (MAR32.18, MAR32.19); counts are 99% actual, 99% hypothetical, 97.5% actual, 97.5%
/// hypothetical.
Desk desk(long long observations, const std::array<long long, 4>& counts);

struct Count {
    long long observations, exceptions_actual, exceptions_hypothetical, exceptions;
    std::vector<long long> days_actual, days_hypothetical;
};

/// risk.frtb.backtest.count (MAR32.5(1)-(2)): an exception when -pnl > VaR, or either value is missing.
Count count_exceptions(const std::vector<std::optional<double>>& var, const std::vector<std::optional<double>>& actual,
                       const std::vector<std::optional<double>>& hypothetical);

}  // namespace quantforge::frtb_backtest
