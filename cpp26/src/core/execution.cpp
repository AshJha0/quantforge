#include "quantforge/core/execution.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <string>
#include <utility>

#include "quantforge/core/error.hpp"

namespace quantforge::execution {
namespace {

[[noreturn]] void input(const std::string& field, const std::string& why) {
    throw Error("E_INPUT", field + ": " + why, field);
}
[[noreturn]] void domain(const std::string& field, const std::string& why) {
    throw Error("E_DOMAIN", field + ": " + why, field);
}

void check_quantity(double x, Mode mode) {
    if (!(x > 0)) input("quantity", "must be positive");
    if (mode == Mode::Units && (x != std::rint(x) || x > 9007199254740992.0))
        input("quantity", "must be a whole number of units in UNITS mode");
}

// sinh(a) / sinh(b) for 0 <= a <= b, b > 0; exponential form when b > 700 (HR-6).
double sinh_ratio(double a, double b) {
    if (b > 700) return std::exp(a - b) * (-std::expm1(-2 * a)) / (-std::expm1(-2 * b));
    return std::sinh(a) / std::sinh(b);
}

// Checks in the order of almgren-chriss.md; returns eta_tilde.
double check_ac(const AcParams& p) {
    if (p.n_steps < 1) input("n_steps", "must be at least 1");
    if (!(p.quantity > 0)) input("quantity", "must be positive");
    if (!(p.horizon > 0)) domain("horizon", "must be positive");
    if (p.sigma < 0) domain("sigma", "must be non-negative");
    if (p.epsilon < 0) domain("epsilon", "must be non-negative");
    if (p.gamma < 0) domain("gamma", "must be non-negative");
    const double tau = p.horizon / (double)p.n_steps;
    const double eta_tilde = p.eta - p.gamma * tau / 2;
    if (!(eta_tilde > 0)) domain("eta", "eta_tilde = eta - gamma tau / 2 must be positive");
    return eta_tilde;
}

void check_lambda(double l) {
    if (l < 0) domain("risk_aversion", "must be non-negative");
}

AcTrajectory trajectory(const AcParams& p, double eta_tilde, double lambda) {
    const auto n = (std::size_t)p.n_steps;
    const double x = p.quantity, t = p.horizon, tau = t / (double)n;
    const double k = lambda == 0 ? 0.0 : ac_kappa(lambda, p.sigma, tau, eta_tilde);
    Vec h(n + 1, 0.0);
    h[0] = x;
    for (std::size_t j = 1; j < n; ++j) {
        if (k == 0) h[j] = x * (double)(n - j) / (double)n;  // HR-5: exactly linear
        else h[j] = x * sinh_ratio(k * (t - (double)j * tau), k * t);
    }
    h[n] = 0;
    Vec trades(n);
    double sum_sq = 0, sum_hold = 0;
    for (std::size_t j = 1; j <= n; ++j) {
        trades[j - 1] = h[j - 1] - h[j];
        sum_sq += trades[j - 1] * trades[j - 1];
        sum_hold += h[j] * h[j];
    }
    const double e = 0.5 * p.gamma * x * x + p.epsilon * x + eta_tilde / tau * sum_sq;  // [AC00] eq. (8)
    const double v = p.sigma * p.sigma * tau * sum_hold;                               // [AC00] eq. (5)
    return {std::move(h), std::move(trades), k, e, v, e + lambda * v};
}

}  // namespace

double snap_floor(double x) {
    const double r = std::rint(x);
    return std::fabs(x - r) <= 1e-12 * std::max(1.0, std::fabs(x)) ? r : std::floor(x);
}

Vec twap(double x, long long n, Mode mode) {
    if (n < 1) input("n_buckets", "must be at least 1");
    check_quantity(x, mode);
    if (mode == Mode::Continuous) return Vec((std::size_t)n, x / (double)n);
    const auto units = (long long)x;
    const long long base = units / n, rem = units % n;
    Vec s((std::size_t)n);
    for (long long i = 0; i < n; ++i) s[(std::size_t)i] = (double)(base + (i < rem ? 1 : 0));
    return s;
}

Vec vwap(double x, const Vec& w, Mode mode) {
    check_quantity(x, mode);
    if (w.empty()) input("profile", "must not be empty");
    double sum = 0;
    for (const double v : w) {
        if (v < 0) domain("profile", "weights must be non-negative");
        sum += v;
    }
    if (!(sum > 0)) domain("profile", "all weights are zero");
    const std::size_t n = w.size();
    Vec s(n);
    for (std::size_t i = 0; i < n; ++i) s[i] = x * w[i] / sum;
    if (mode == Mode::Continuous) return s;
    Vec frac(n);
    double allotted = 0;
    for (std::size_t i = 0; i < n; ++i) {
        const double f = std::floor(s[i]);
        frac[i] = s[i] - f;
        s[i] = f;
        allotted += f;
    }
    const auto rem = (std::size_t)std::max(0.0, x - allotted);
    std::vector<std::size_t> order(n);
    std::iota(order.begin(), order.end(), std::size_t{0});
    // Stable: equal remainders keep index order, so the earliest wins.
    std::ranges::stable_sort(order, [&](std::size_t a, std::size_t b) { return frac[a] > frac[b]; });
    for (std::size_t k = 0; k < rem && k < n; ++k) s[order[k]] += 1;
    return s;
}

Pov pov(double x, double p, const Vec& mv, Mode mode) {
    check_quantity(x, mode);
    if (!(p > 0 && p < 1)) domain("participation", "must lie in (0, 1)");
    for (const double v : mv)
        if (v < 0) domain("market_volume", "must be non-negative");
    const double ratio = p / (1 - p);
    double remaining = x, filled = 0;
    Vec s(mv.size());
    for (std::size_t i = 0; i < mv.size(); ++i) {
        const double raw = ratio * mv[i];
        const double c = std::min(remaining, mode == Mode::Units ? snap_floor(raw) : raw);
        s[i] = c;
        filled += c;
        remaining = x - filled;
    }
    return {std::move(s), filled, x - filled};
}

double ac_kappa(double lambda, double sigma, double tau, double eta_tilde) {
    const double y = lambda * sigma * sigma * tau * tau / (2 * eta_tilde);
    return std::log1p(y + std::sqrt(y * (y + 2))) / tau;
}

AcTrajectory ac_trajectory(const AcParams& p, double lambda) {
    const double eta_tilde = check_ac(p);
    check_lambda(lambda);
    return trajectory(p, eta_tilde, lambda);
}

AcFrontier ac_frontier(const AcParams& p, const Vec& lambdas) {
    const double eta_tilde = check_ac(p);
    if (lambdas.empty()) input("risk_aversions", "must not be empty");
    for (const double l : lambdas) check_lambda(l);
    AcFrontier f{lambdas, Vec(lambdas.size()), Vec(lambdas.size())};
    for (std::size_t i = 0; i < lambdas.size(); ++i) {
        const AcTrajectory r = trajectory(p, eta_tilde, lambdas[i]);
        f.expected_cost[i] = r.expected_cost;
        f.variance[i] = r.variance;
    }
    return f;
}

double impact_sqrt(double q, double v, double sigma, double y) {
    if (q < 0) domain("quantity", "must be non-negative");
    if (!(v > 0)) domain("daily_volume", "must be positive");
    if (sigma < 0) domain("daily_vol", "must be non-negative");
    if (y < 0) domain("coefficient", "must be non-negative");
    return y * sigma * std::sqrt(q / v);  // [TLD11] eq. (1)
}

OwOptimal ow_optimal(double x, double t, double rho) {
    if (!(x > 0)) input("quantity", "must be positive");
    if (!(t > 0)) domain("horizon", "must be positive");
    if (!(rho > 0)) domain("resilience", "must be positive");
    const double d = rho * t + 2, block = x / d;  // [OW13] eq. (31)
    return {block, rho * x / d, block};
}

Shortfall shortfall(Side side, double pd, double p0, double pc, double x, const std::vector<Fill>& fills, double fees,
                    std::optional<double> benchmark) {
    if (!(x > 0)) input("order_quantity", "must be positive");
    double q = 0;
    for (const Fill& f : fills) {
        if (!(f.quantity > 0)) input("fills", "fill quantities must be positive");
        q += f.quantity;
    }
    if (q > x) input("fills", "fills add up to more than the order");
    if (!(pd > 0)) domain("decision_price", "must be positive");
    if (!(p0 > 0)) domain("arrival_price", "must be positive");
    if (!(pc > 0)) domain("end_price", "must be positive");
    for (const Fill& f : fills)
        if (!(f.price > 0)) domain("fills", "fill prices must be positive");
    if (benchmark && !(*benchmark > 0)) domain("benchmark_vwap", "must be positive");
    const double s = side == Side::Buy ? 1.0 : -1.0;
    const double delay = s * q * (p0 - pd);  // HR-8: executed quantity
    double exec = 0, notional = 0;
    for (const Fill& f : fills) {
        exec += f.quantity * (f.price - p0);
        notional += f.quantity * f.price;
    }
    exec *= s;
    const double opp = s * (x - q) * (pc - pd) + 0.0;  // + 0.0: a full sell gives 0, not -0
    const double total = delay + exec + opp + fees;
    std::optional<double> slip;
    if (benchmark) slip = s * (notional - q * *benchmark);  // s Q (avg_fill - VWAP)
    return {delay, exec, opp, total, total / (x * pd) * 1e4, slip};
}

ExecutionTca execution_tca(const AcParams& p, double lambda, Side side, double pd, double p0, double pc,
                           const Vec& fill_prices, long long completed, double fee_per_unit) {
    if (!(p.quantity >= 1) || p.quantity != std::rint(p.quantity) || p.quantity > 9007199254740992.0)
        input("quantity", "must be an Integer >= 1");
    if ((long long)fill_prices.size() != p.n_steps) input("fill_prices", "needs one price per step");
    if (completed < 0 || completed > p.n_steps) input("completed_steps", "must lie in 0 to n_steps");
    if (fee_per_unit < 0) domain("fee_per_unit", "must be non-negative");
    const AcTrajectory ac = ac_trajectory(p, lambda);
    Vec lots = vwap(p.quantity, ac.trades, Mode::Units);
    std::vector<Fill> fills;
    double filled = 0;
    for (std::size_t k = 0; k < (std::size_t)completed; ++k) {
        fills.push_back({lots[k], fill_prices[k]});
        filled += lots[k];
    }
    const double fees = fee_per_unit * filled;
    const Shortfall s = shortfall(side, pd, p0, pc, p.quantity, fills, fees, std::nullopt);
    return {std::move(lots), ac.expected_cost, ac.variance, filled, fees, s};
}

Quotes as_quotes(double mid, double q, double gamma, double sigma, double time_left, double k) {
    if (!(gamma > 0)) domain("risk_aversion", "must be positive");
    if (!(k > 0)) domain("k", "must be positive");
    if (sigma < 0) domain("sigma", "must be non-negative");
    if (time_left < 0) domain("time_left", "must be non-negative");
    const double risk = gamma * sigma * sigma * time_left;
    const double r = mid - q * risk;                                 // [AS08] eq. (29)
    const double spread = risk + 2 / gamma * std::log1p(gamma / k);  // [AS08] eq. (30)
    return {r, spread, r - spread / 2, r + spread / 2};
}

}  // namespace quantforge::execution
