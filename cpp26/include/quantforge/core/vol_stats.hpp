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

// Stage F (R8, garch.md "Stage F additions", rulings F-11 to F-14).
enum class GarchDistribution { Normal, StudentT };

/// Innovation law and mean for the stage F log-likelihood. degrees_of_freedom is required for StudentT
/// (else E_INPUT) and must be above 2 (else E_DOMAIN); it is ignored for Normal. The recursion runs on
/// e_t = r_t - mean, and "SAMPLE" is (1/n) sum e_t^2.
struct GarchLaw {
    GarchDistribution distribution = GarchDistribution::Normal;
    std::optional<double> degrees_of_freedom;
    double mean = 0.0;
};
GarchLoglik garch_loglik(const std::vector<double>& returns, double omega, double alpha, double beta,
                         std::optional<double> initial_variance, const GarchLaw& law);

struct GarchEstimate {
    double omega, alpha, beta;
    std::optional<double> degrees_of_freedom;  // nullopt for Normal
    double mean, loglik, persistence;
    double se_omega, se_alpha, se_beta;
    std::optional<double> se_degrees_of_freedom;
};
/// Maximum likelihood with observed-information standard errors. demean: mu is the sample mean, held fixed.
GarchEstimate garch_estimate(const std::vector<double>& returns, std::optional<double> initial_variance,
                             GarchDistribution distribution, bool demean);

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

/// A quote may be nullopt (stage F, ruling F-15): the series on that side is a null series.
struct VixQuote {
    double strike;
    std::optional<double> call_bid, call_ask, put_bid, put_ask;
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
