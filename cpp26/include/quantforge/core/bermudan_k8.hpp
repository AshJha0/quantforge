#pragma once
// K-8 (stage K; rulings KR-8 and KR-18): the `CN_RANNACHER_SMOOTHED` Bermudan scheme
// (specifications/06-risk/bermudan-ladder-k8.md, version 0.2.0), a line-by-line port of the Java build's
// BermudanK8.java, which ports python/quantforge_core/bermudan_k8.py. Same state, grid, knots and exercise value as the
// pinned G-18 scheme, with three changes: the scheme carries U = V exp(-int_0^t alpha), so the operator has no curve
// term and is constant in time; Crank-Nicolson stepping with the first two steps after the maturity payoff and after
// each exercise date each replaced by two implicit half steps; and the exercise max applied as a hat-weighted average
// with an end correction.
//
// The ladder is the exact derivative of this discrete scheme in tangent mode: every quantity is a vector whose entry 0
// is the value and entries 1.. its derivatives with respect to the log discount factors of the curve nodes, the mean
// reversion and the volatility. Inputs are checked by the caller (the CLI, in the order of program/K8_PORT_NOTE.md).
#include <string_view>
#include <vector>

namespace quantforge::bermudan_k8 {

inline constexpr std::string_view method = "CN_RANNACHER_SMOOTHED";
/// Steps replaced by two implicit half steps each after every exercise date (KR-18 c).
inline constexpr long long start_up_steps = 2;

/// A dual number: entry 0 the value, entries 1.. the tangents.
using Dual = std::vector<double>;
using Duals = std::vector<Dual>;

Dual mul(const Dual& u, const Dual& v);
Dual div(const Dual& u, const Dual& v);
Dual add(const Dual& u, const Dual& v);
Dual sub(const Dual& u, const Dual& v);
Dual scale(double k, const Dual& u);

/// `int_0^1 (1 - u) max(p + (q - p) u, 0) du`: half of the hat-weighted average of the positive part.
Dual hat_part(const Dual& p, const Dual& q);
/// `max(V, E)` at an exercise date as a second-order smoothing (KR-18 b, spec step 5).
Duals smoothed_max(const Duals& v, const Duals& e);

/// Price per unit notional (entry 0) and, with `tangents`, its derivatives with respect to the log discount factors
/// of the curve pillars, `a` and `sigma` (entries 1..).
Dual scheme(const std::vector<double>& times, const std::vector<double>& dfs, double a, double sigma,
            const std::vector<double>& payment_times, double k, bool payer, const std::vector<double>& exercise_times,
            long long nx, long long steps_per_year, double width, bool tangents);

/// `rates.shortrate.bermudan_swaption` with `method` `CN_RANNACHER_SMOOTHED`; inputs checked.
double price(const std::vector<double>& times, const std::vector<double>& dfs, double a, double sigma,
             const std::vector<double>& payment_times, double k, bool payer, double notional,
             const std::vector<double>& exercise_times, long long nx, long long steps_per_year, double width);

struct Ladder {
    double price;
    std::vector<double> d_discount_factors;
    double d_mean_reversion, d_sigma;
};
/// `rates.shortrate.bermudan_ladder` with `method` `CN_RANNACHER_SMOOTHED`; inputs checked; scaled by `notional`.
Ladder ladder(const std::vector<double>& times, const std::vector<double>& dfs, double a, double sigma,
              const std::vector<double>& payment_times, double k, bool payer, double notional,
              const std::vector<double>& exercise_times, long long nx, long long steps_per_year, double width);

}  // namespace quantforge::bermudan_k8
