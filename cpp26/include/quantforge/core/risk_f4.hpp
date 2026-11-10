#pragma once
// Stage F, slice F4: VaR, ES, backtests (06-risk/var-es-and-backtests.md) and FRTB-SA GIRR delta
// (06-risk/frtb-sa-girr.md).
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace quantforge {

struct VarResult {
    double var, es;
    std::size_t tail_count;
};

/// Order statistic rule (ruling F-31) on losses; unchecked: caller guarantees finite losses, n >= 1 and c in [0.5, 1).
VarResult var_of_losses(std::vector<double> losses, double confidence);

VarResult var_historical(const std::vector<double>& pnl, double confidence);

struct FhsResult {
    VarResult v;
    double sigma_next;
};
FhsResult var_filtered_historical(const std::vector<double>& returns, double position_value, double lambda,
                                  double confidence);

struct ParametricVar {
    double var, es;
};
ParametricVar var_parametric(double mean, double std, double confidence);

VarResult var_monte_carlo(const std::vector<double>& mean, const std::vector<std::vector<double>>& covariance,
                          const std::vector<double>& weights, long long paths, std::uint64_t seed, double confidence);

/// P(chi^2 > x) for 1 and 2 degrees of freedom; unchecked.
double chi2_sf_1(double x);
double chi2_sf_2(double x);

struct Kupiec {
    double lr_uc, p_value;
};
Kupiec backtest_kupiec(long long observations, long long exceptions, double confidence);

struct Christoffersen {
    double lr_uc, lr_ind, lr_cc, p_uc, p_ind, p_cc;
    long long n00, n01, n10, n11;
};
Christoffersen backtest_christoffersen(const std::vector<bool>& exceptions, double confidence);

enum class TrafficZone { Green, Yellow, Red };
struct TrafficLight {
    double cumulative_probability;
    TrafficZone zone;
    std::optional<double> plus_factor;
};
TrafficLight backtest_traffic_light(long long observations, long long exceptions, double confidence);

// ---- FRTB GIRR delta ----

/// Tenor index 0..9 (0.25Y .. 30Y), 10 = INFLATION, 11 = XCCY_BASIS.
enum class GirrFactor { T0_25, T0_5, T1, T2, T3, T5, T10, T15, T20, T30, Inflation, XccyBasis };

struct GirrSensitivity {
    std::string currency, curve;
    GirrFactor factor;
    double sensitivity;
};

struct GirrBucket {
    std::string currency;
    double k, s, s_used;
};
struct GirrScenario {
    std::vector<GirrBucket> buckets;
    double delta;
    bool alternative_used;
};
struct GirrResult {
    /// high, medium, low.
    std::array<GirrScenario, 3> scenarios;
    double capital;
    std::size_t binding;  // index into scenarios
};
GirrResult frtb_girr_delta(const std::vector<GirrSensitivity>& sensitivities, bool specified_currency_reduction,
                           const std::optional<std::string>& reporting_currency);

}  // namespace quantforge
