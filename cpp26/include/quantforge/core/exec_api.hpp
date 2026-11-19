#pragma once
// Typed in-process API for the execution and microstructure layer (stage H item H-5,
// specifications/10-execution/library-interfaces.md; ADR-0011).
//
// Closed choices are enums parsed once at the edge (E_SCHEMA otherwise); inputs are value types validated when
// built, so none can exist in an invalid state; every call delegates to the kernel in execution.hpp, so the numbers
// are the kernel's, bit for bit. The kernels stay as they are for the CLI.
//
// Thread safety: every function here is pure and holds no state; safe to call from any number of threads.
#include <cmath>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "quantforge/core/error.hpp"
#include "quantforge/core/execution.hpp"

namespace quantforge::exec_api {

using Vec = std::vector<double>;
namespace kx = ::quantforge::execution;

/// Order side. Thread safety: immutable; safe to share between threads.
using Side = kx::Side;
/// Whole units or continuous quantities (spec 2.2 `FillMode`). Thread safety: immutable; safe to share between
/// threads.
using FillMode = kx::Mode;

namespace detail {
inline void finite(const char* field, double x) {
    if (!std::isfinite(x)) throw Error("E_DOMAIN", std::string(field) + " must be finite", field);
}
inline void finite_all(const char* field, const Vec& xs) {
    for (const double x : xs) finite(field, x);
}
}  // namespace detail

/// The JSON spelling to the enum; anything else is E_SCHEMA.
inline Side parse_side(std::string_view text) {
    if (text == "BUY") return Side::Buy;
    if (text == "SELL") return Side::Sell;
    throw Error("E_SCHEMA", "side: unknown value '" + std::string(text) + "'", "side");
}
inline FillMode parse_fill_mode(std::string_view text) {
    if (text == "UNITS") return FillMode::Units;
    if (text == "CONTINUOUS") return FillMode::Continuous;
    throw Error("E_SCHEMA", "mode: unknown value '" + std::string(text) + "'", "mode");
}
inline const char* to_string(Side s) { return s == Side::Buy ? "BUY" : "SELL"; }
inline const char* to_string(FillMode m) { return m == FillMode::Units ? "UNITS" : "CONTINUOUS"; }

/// Almgren-Chriss model inputs ([AC00], HR-2, HR-5), checked when built in the order of almgren-chriss.md.
/// Thread safety: immutable; safe to share between threads.
class AcParams {
public:
    AcParams(double quantity, double horizon, long long n_steps, double sigma, double epsilon, double eta,
             double gamma)
        : p_{quantity, horizon, n_steps, sigma, epsilon, eta, gamma} {
        detail::finite("quantity", quantity);
        detail::finite("horizon", horizon);
        detail::finite("sigma", sigma);
        detail::finite("epsilon", epsilon);
        detail::finite("eta", eta);
        detail::finite("gamma", gamma);
        check();
    }
    double quantity() const noexcept { return p_.quantity; }
    double horizon() const noexcept { return p_.horizon; }
    long long n_steps() const noexcept { return p_.n_steps; }
    double sigma() const noexcept { return p_.sigma; }
    double epsilon() const noexcept { return p_.epsilon; }
    double eta() const noexcept { return p_.eta; }
    double gamma() const noexcept { return p_.gamma; }
    const kx::AcParams& kernel() const noexcept { return p_; }

private:
    void check() const;
    kx::AcParams p_;
};

/// One execution. Thread safety: immutable; safe to share between threads.
class Fill {
public:
    Fill(double quantity, double price) : f_{quantity, price} {
        detail::finite("fills", quantity);
        detail::finite("fills", price);
        if (!(quantity > 0)) throw Error("E_INPUT", "fill quantities must be positive", "fills");
        if (!(price > 0)) throw Error("E_DOMAIN", "prices must be positive", "fills");
    }
    double quantity() const noexcept { return f_.quantity; }
    double price() const noexcept { return f_.price; }
    const kx::Fill& kernel() const noexcept { return f_; }

private:
    kx::Fill f_;
};

/// Child-order slices; residual is zero except for POV. Thread safety: immutable; safe to share between threads.
class Schedule {
public:
    Schedule(Vec slices, double filled, double residual)
        : slices_(std::move(slices)), filled_(filled), residual_(residual) {}
    const Vec& slices() const noexcept { return slices_; }
    double filled() const noexcept { return filled_; }
    double residual() const noexcept { return residual_; }

private:
    Vec slices_;
    double filled_, residual_;
};

/// Holdings x_0..x_N, trades n_1..n_N, kappa, E, V and E + lambda V. Thread safety: immutable; safe to share
/// between threads.
class AcTrajectory {
public:
    explicit AcTrajectory(kx::AcTrajectory t) : t_(std::move(t)) {}
    const Vec& holdings() const noexcept { return t_.holdings; }
    const Vec& trades() const noexcept { return t_.trades; }
    double kappa() const noexcept { return t_.kappa; }
    double expected_cost() const noexcept { return t_.expected_cost; }
    double variance() const noexcept { return t_.variance; }
    double objective() const noexcept { return t_.objective; }

private:
    kx::AcTrajectory t_;
};

/// One (lambda, E, V) per input, in input order; equal lengths. Thread safety: immutable; safe to share between
/// threads.
class AcFrontier {
public:
    explicit AcFrontier(kx::AcFrontier f) : f_(std::move(f)) {}
    const Vec& risk_aversions() const noexcept { return f_.risk_aversions; }
    const Vec& expected_costs() const noexcept { return f_.expected_cost; }
    const Vec& variances() const noexcept { return f_.variance; }

private:
    kx::AcFrontier f_;
};

/// Obizhaeva-Wang optimal blocks and rate. Thread safety: immutable; safe to share between threads.
class OwOptimal {
public:
    explicit OwOptimal(kx::OwOptimal o) : o_(o) {}
    double initial_block() const noexcept { return o_.initial_block; }
    double rate() const noexcept { return o_.rate; }
    double final_block() const noexcept { return o_.final_block; }

private:
    kx::OwOptimal o_;
};

/// Perold decomposition (HR-8); vwap_slippage is empty without a benchmark. Thread safety: immutable; safe to
/// share between threads.
class Shortfall {
public:
    explicit Shortfall(kx::Shortfall s) : s_(s) {}
    double delay() const noexcept { return s_.delay; }
    double execution() const noexcept { return s_.execution; }
    double opportunity() const noexcept { return s_.opportunity; }
    double total() const noexcept { return s_.total; }
    double total_bps() const noexcept { return s_.total_bps; }
    std::optional<double> vwap_slippage() const noexcept { return s_.vwap_slippage; }

private:
    kx::Shortfall s_;
};

/// Avellaneda-Stoikov reservation price, spread and quotes; bid <= ask (E_DOMAIN). Thread safety: immutable; safe
/// to share between threads.
class Quotes {
public:
    Quotes(double reservation, double spread, double bid, double ask) : q_{reservation, spread, bid, ask} {
        if (!(bid <= ask)) throw Error("E_DOMAIN", "bid must not exceed ask", "bid");
    }
    double reservation() const noexcept { return q_.reservation; }
    double spread() const noexcept { return q_.spread; }
    double bid() const noexcept { return q_.bid; }
    double ask() const noexcept { return q_.ask; }

private:
    kx::Quotes q_;
};

inline void AcParams::check() const {
    // The kernel's own check (E_INPUT / E_DOMAIN, almgren-chriss.md order), run once here so an AcParams is valid.
    (void)kx::ac_trajectory(p_, 0.0);
}

/// exec.schedule.twap
inline Schedule twap(double quantity, long long n_buckets, FillMode mode) {
    detail::finite("quantity", quantity);
    Vec s = kx::twap(quantity, n_buckets, mode);
    double filled = 0;
    for (const double x : s) filled += x;
    return {std::move(s), filled, 0.0};
}

/// exec.schedule.vwap
inline Schedule vwap(double quantity, const Vec& profile, FillMode mode) {
    detail::finite("quantity", quantity);
    detail::finite_all("profile", profile);
    Vec s = kx::vwap(quantity, profile, mode);
    double filled = 0;
    for (const double x : s) filled += x;
    return {std::move(s), filled, 0.0};
}

/// exec.schedule.pov
inline Schedule pov(double quantity, double participation, const Vec& market_volume, FillMode mode) {
    detail::finite("quantity", quantity);
    detail::finite("participation", participation);
    detail::finite_all("market_volume", market_volume);
    kx::Pov p = kx::pov(quantity, participation, market_volume, mode);
    return {std::move(p.slices), p.filled, p.residual};
}

/// exec.ac.trajectory
inline AcTrajectory ac_trajectory(const AcParams& params, double risk_aversion) {
    detail::finite("risk_aversion", risk_aversion);
    return AcTrajectory(kx::ac_trajectory(params.kernel(), risk_aversion));
}

/// exec.ac.frontier
inline AcFrontier ac_frontier(const AcParams& params, const Vec& risk_aversions) {
    detail::finite_all("risk_aversions", risk_aversions);
    return AcFrontier(kx::ac_frontier(params.kernel(), risk_aversions));
}

/// exec.impact.sqrt: impact as a fraction of price; assumed coefficient (HR-10).
inline double impact_sqrt(double quantity, double daily_volume, double daily_vol, double coefficient) {
    detail::finite("impact", quantity);
    detail::finite("impact", daily_volume);
    detail::finite("impact", daily_vol);
    detail::finite("impact", coefficient);
    return kx::impact_sqrt(quantity, daily_volume, daily_vol, coefficient);
}

/// exec.impact.ow_optimal
inline OwOptimal ow_optimal(double quantity, double horizon, double resilience) {
    detail::finite("ow_optimal", quantity);
    detail::finite("ow_optimal", horizon);
    detail::finite("ow_optimal", resilience);
    return OwOptimal(kx::ow_optimal(quantity, horizon, resilience));
}

/// exec.tca.shortfall
inline Shortfall shortfall(Side side, double decision_price, double arrival_price, double end_price,
                           double order_quantity, const std::vector<Fill>& fills, double fees,
                           std::optional<double> benchmark_vwap = std::nullopt) {
    for (const double x : {decision_price, arrival_price, end_price, order_quantity, fees})
        detail::finite("shortfall", x);
    if (benchmark_vwap) detail::finite("benchmark_vwap", *benchmark_vwap);
    std::vector<kx::Fill> k;
    k.reserve(fills.size());
    for (const Fill& f : fills) k.push_back(f.kernel());
    return Shortfall(kx::shortfall(side, decision_price, arrival_price, end_price, order_quantity, k, fees,
                                          benchmark_vwap));
}

/// micro.mm.as_quotes
inline Quotes as_quotes(double mid, double inventory, double risk_aversion, double sigma, double time_left,
                        double k) {
    for (const double x : {mid, inventory, risk_aversion, sigma, time_left, k}) detail::finite("as_quotes", x);
    const kx::Quotes q = kx::as_quotes(mid, inventory, risk_aversion, sigma, time_left, k);
    return {q.reservation, q.spread, q.bid, q.ask};
}

}  // namespace quantforge::exec_api
