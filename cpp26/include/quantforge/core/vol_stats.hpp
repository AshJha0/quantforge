#pragma once
// Stage E, E7: GARCH(1,1) (05-volatility/garch.md), variance swaps (05-volatility/variance-swaps.md) and the
// VIX-style index (05-volatility/vix-index.md). Rulings E-B1 to E-B7 in stage-e-rulings-b.md.
#include <optional>
#include <vector>

#include "quantforge/core/dates.hpp"

namespace quantforge {

// ---- GARCH(1,1) ----

/// initial_variance: a positive number, or nullopt for "SAMPLE" ((1/n) sum r^2, no demeaning).
struct GarchLoglik {
    double loglik;
    std::vector<double> variances;  // sigma2_1 .. sigma2_n
    double next_variance;           // sigma2_{n+1}
};
GarchLoglik garch_loglik(const std::vector<double>& returns, double omega, double alpha, double beta,
                         std::optional<double> initial_variance);

struct GarchForecast {
    std::vector<double> variances;
    double total_variance, annualized_vol, long_run_variance;
};
GarchForecast garch_forecast(double omega, double alpha, double beta, double next_variance, long long horizon,
                             double periods_per_year);

struct GarchFit {
    double loglik, omega, alpha, beta;
};
GarchFit garch_fit(const std::vector<double>& returns, std::optional<double> initial_variance);

// ---- variance swaps ----

struct StrikeVol {
    double strike, vol;
};
struct VarSwapInputs {
    Date as_of, maturity;
    double spot, rate, dividend_yield;
    std::vector<double> put_strikes, call_strikes;
    std::vector<StrikeVol> vols;
    double extension_step, variance_strike, variance_notional;
};
struct VarSwapFair {
    double fair_variance, fair_vol, pv;
};
VarSwapFair varswap_fair_strike(const VarSwapInputs& in);

struct VarSwapRealized {
    double realized_variance, realized_vol, payoff;
};
VarSwapRealized varswap_realized(const std::vector<double>& prices, double periods_per_year, double variance_strike,
                                 double variance_notional);

// ---- VIX-style index ----

struct VixQuote {
    double strike, call_bid, call_ask, put_bid, put_ask;
};
struct VixTerm {
    long long minutes;
    double rate;
    std::vector<VixQuote> strip;
};
struct VixTermResult {
    double forward, k0, variance, t;
    std::vector<double> strikes_used;
};
VixTermResult vix_term_variance(const VixTerm& term);

struct VixIndex {
    double index, near_variance, next_variance;
};
VixIndex vix_index(const VixTerm& near, const VixTerm& next);

}  // namespace quantforge
