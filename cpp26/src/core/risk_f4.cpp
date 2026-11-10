#include "quantforge/core/risk_f4.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <string_view>
#include <tuple>

#include "quantforge/core/error.hpp"
#include "quantforge/core/finite.hpp"
#include "quantforge/core/rng.hpp"
#include "quantforge/core/stats.hpp"

namespace quantforge {
namespace {

void check_confidence(double c) {
    require_finite(c, "confidence");
    if (!(c >= 0.5 && c < 1.0)) throw Error("E_DOMAIN", "confidence must lie in [0.5, 1)", "confidence");
}

/// n ln q with 0 ln 0 = 0.
double xlogy(double n, double q) { return n == 0.0 ? 0.0 : n * std::log(q); }

/// Ruling F-32: an LR below 1e-12 is exactly 0.
double zeroed(double lr) { return lr < 1e-12 ? 0.0 : lr; }

double lr_uc_of(long long n, long long x, double c) {
    const double p = 1.0 - c;
    const double nd = double(n), xd = double(x);
    const double p_hat = xd / nd;
    const double lr =
        -2.0 * (xlogy(nd - xd, 1.0 - p) + xlogy(xd, p)) + 2.0 * (xlogy(nd - xd, 1.0 - p_hat) + xlogy(xd, p_hat));
    return zeroed(lr);
}

void check_counts(long long observations, long long exceptions) {
    if (observations < 1) throw Error("E_DOMAIN", "observations must be at least 1", "observations");
    if (exceptions < 0 || exceptions > observations)
        throw Error("E_DOMAIN", "exceptions must lie in [0, observations]", "exceptions");
}

}  // namespace

VarResult var_of_losses(std::vector<double> losses, double confidence) {
    std::sort(losses.begin(), losses.end());
    const std::size_t n = losses.size();
    const double nc = double(n) * confidence;
    const std::size_t k = std::clamp<std::size_t>(std::size_t(std::ceil(nc)), 1, n);
    double sum = 0.0;
    for (std::size_t i = k - 1; i < n; ++i) sum += losses[i];
    const std::size_t tail = n - k + 1;
    return {losses[k - 1], sum / double(tail), tail};
}

VarResult var_historical(const std::vector<double>& pnl, double confidence) {
    require_finite(pnl, "pnl");
    check_confidence(confidence);
    if (pnl.empty()) throw Error("E_INPUT", "pnl needs at least one scenario", "pnl");
    std::vector<double> losses;
    losses.reserve(pnl.size());
    for (const double x : pnl) losses.push_back(-x);
    return var_of_losses(std::move(losses), confidence);
}

FhsResult var_filtered_historical(const std::vector<double>& returns, double position_value, double lambda,
                                  double confidence) {
    require_finite(returns, "returns");
    require_finite(position_value, "position_value");
    require_finite(lambda, "lambda");
    check_confidence(confidence);
    if (!(lambda > 0.0 && lambda < 1.0)) throw Error("E_DOMAIN", "lambda must lie in (0, 1)", "lambda");
    if (returns.empty()) throw Error("E_INPUT", "returns needs at least one value", "returns");
    const std::size_t t = returns.size();
    double ms = 0.0;
    for (const double r : returns) ms += r * r;
    ms /= double(t);
    if (!(ms > 0.0)) throw Error("E_DOMAIN", "every return is 0, so the EWMA variance is 0", "returns");
    std::vector<double> var(t + 1);
    var[0] = ms;
    for (std::size_t i = 0; i < t; ++i) var[i + 1] = lambda * var[i] + (1.0 - lambda) * returns[i] * returns[i];
    const double sigma_next = std::sqrt(var[t]);
    std::vector<double> losses(t);
    for (std::size_t i = 0; i < t; ++i) losses[i] = -(position_value * returns[i] * sigma_next / std::sqrt(var[i]));
    return {var_of_losses(std::move(losses), confidence), sigma_next};
}

ParametricVar var_parametric(double mean, double std, double confidence) {
    require_finite(mean, "mean");
    require_finite(std, "std");
    check_confidence(confidence);
    if (!(std > 0.0)) throw Error("E_DOMAIN", "std must be above 0", "std");
    const double z = ppnd16(confidence);
    return {-mean + std * z, -mean + std * normal_pdf(z) / (1.0 - confidence)};
}

VarResult var_monte_carlo(const std::vector<double>& mean, const std::vector<std::vector<double>>& covariance,
                          const std::vector<double>& weights, long long paths, std::uint64_t seed, double confidence) {
    require_finite(mean, "mean");
    for (const auto& row : covariance) require_finite(row, "covariance");
    require_finite(weights, "weights");
    check_confidence(confidence);
    const std::size_t n = mean.size();
    if (n == 0) throw Error("E_INPUT", "mean needs at least one asset", "mean");
    if (weights.size() != n) throw Error("E_INPUT", "weights and mean differ in length", "weights");
    if (covariance.size() != n) throw Error("E_INPUT", "covariance is not N x N", "covariance");
    for (const auto& row : covariance)
        if (row.size() != n) throw Error("E_INPUT", "covariance is not N x N", "covariance");
    if (paths < 1) throw Error("E_DOMAIN", "paths must be at least 1", "paths");
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < i; ++j)
            if (covariance[i][j] != covariance[j][i])
                throw Error("E_DOMAIN", "covariance is not symmetric", "covariance");
    // Cholesky-Banachiewicz, row by row; a pivot at or below 0 is E_DOMAIN (not E_NOT_POSITIVE_DEFINITE).
    std::vector<std::vector<double>> l(n, std::vector<double>(n, 0.0));
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j <= i; ++j) {
            double s = covariance[i][j];
            for (std::size_t k = 0; k < j; ++k) s -= l[i][k] * l[j][k];
            if (i == j) {
                if (!(s > 0.0)) throw Error("E_NOT_POSITIVE_DEFINITE", "covariance is not positive definite", "covariance");  // F-39
                l[i][i] = std::sqrt(s);
            } else {
                l[i][j] = s / l[j][j];
            }
        }
    Xoshiro256 rng(seed, 0);
    std::vector<double> z(n);
    std::vector<double> losses(static_cast<std::size_t>(paths));
    for (auto& loss : losses) {
        for (double& zi : z) zi = rng.next_normal();
        double pnl = 0.0;
        for (std::size_t i = 0; i < n; ++i) {
            double r = mean[i];
            for (std::size_t k = 0; k <= i; ++k) r += l[i][k] * z[k];
            pnl += weights[i] * r;
        }
        loss = -pnl;
    }
    return var_of_losses(std::move(losses), confidence);
}

double chi2_sf_1(double x) { return x <= 0.0 ? 1.0 : std::erfc(std::sqrt(0.5 * x)); }
double chi2_sf_2(double x) { return x <= 0.0 ? 1.0 : std::exp(-0.5 * x); }

Kupiec backtest_kupiec(long long observations, long long exceptions, double confidence) {
    check_confidence(confidence);
    check_counts(observations, exceptions);
    const double lr = lr_uc_of(observations, exceptions, confidence);
    return {lr, chi2_sf_1(lr)};
}

Christoffersen backtest_christoffersen(const std::vector<bool>& exceptions, double confidence) {
    check_confidence(confidence);
    const std::size_t n = exceptions.size();
    if (n < 2) throw Error("E_INPUT", "exceptions needs at least two days", "exceptions");
    long long x = 0;
    for (const bool b : exceptions) x += b ? 1 : 0;
    long long c[2][2] = {{0, 0}, {0, 0}};
    for (std::size_t t = 1; t < n; ++t) ++c[exceptions[t - 1] ? 1 : 0][exceptions[t] ? 1 : 0];
    const double n00 = double(c[0][0]), n01 = double(c[0][1]), n10 = double(c[1][0]), n11 = double(c[1][1]);
    const double pi01 = n00 + n01 > 0 ? n01 / (n00 + n01) : 0.0;
    const double pi11 = n10 + n11 > 0 ? n11 / (n10 + n11) : 0.0;
    const double pi = (n01 + n11) / double(n - 1);
    const double lr_ind = zeroed(-2.0 * (xlogy(n00 + n10, 1.0 - pi) + xlogy(n01 + n11, pi) - xlogy(n00, 1.0 - pi01) -
                                         xlogy(n01, pi01) - xlogy(n10, 1.0 - pi11) - xlogy(n11, pi11)));
    const double lr_uc = lr_uc_of((long long)n, x, confidence);
    const double lr_cc = lr_uc + lr_ind;
    return {lr_uc,   lr_ind,  lr_cc,   chi2_sf_1(lr_uc), chi2_sf_1(lr_ind), chi2_sf_2(lr_cc),
            c[0][0], c[0][1], c[1][0], c[1][1]};
}

TrafficLight backtest_traffic_light(long long observations, long long exceptions, double confidence) {
    check_confidence(confidence);
    check_counts(observations, exceptions);
    const double p = 1.0 - confidence;
    const double nd = double(observations);
    // The pmf by its ratio recursion in logs, so that (1 - p)^n cannot underflow.
    double log_pmf = nd * std::log1p(-p);
    const double log_odds = std::log(p) - std::log1p(-p);
    double cdf = std::exp(log_pmf);
    for (long long k = 0; k < exceptions; ++k) {
        log_pmf += std::log((nd - double(k)) / double(k + 1)) + log_odds;
        cdf += std::exp(log_pmf);
    }
    cdf = std::min(cdf, 1.0);
    const TrafficZone zone = cdf < 0.95 ? TrafficZone::Green : cdf < 0.9999 ? TrafficZone::Yellow : TrafficZone::Red;
    std::optional<double> plus;
    if (observations == 250 && confidence == 0.99) {
        constexpr double table[] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.40, 0.50, 0.65, 0.75, 0.85};
        plus = exceptions >= 10 ? 1.0 : table[exceptions];
    }
    return {cdf, zone, plus};
}

// ---- FRTB GIRR delta ----

namespace {

constexpr double tenor_years[] = {0.25, 0.5, 1, 2, 3, 5, 10, 15, 20, 30};
constexpr double tenor_weight[] = {0.017, 0.017, 0.016, 0.013, 0.012, 0.011, 0.011, 0.011, 0.011, 0.011};
constexpr std::string_view reduced_currencies[] = {"EUR", "USD", "GBP", "AUD", "JPY", "SEK", "CAD"};

bool is_tenor(GirrFactor f) { return f != GirrFactor::Inflation && f != GirrFactor::XccyBasis; }

double risk_weight(GirrFactor f) { return is_tenor(f) ? tenor_weight[std::size_t(f)] : 0.016; }

double rho_medium(const GirrSensitivity& a, const GirrSensitivity& b) {
    if (a.factor == GirrFactor::XccyBasis || b.factor == GirrFactor::XccyBasis) return 0.0;
    const bool same_curve = a.curve == b.curve;
    if (a.factor == GirrFactor::Inflation && b.factor == GirrFactor::Inflation) return same_curve ? 1.0 : 0.999;
    if (a.factor == GirrFactor::Inflation || b.factor == GirrFactor::Inflation) return 0.4;
    const double ta = tenor_years[std::size_t(a.factor)], tb = tenor_years[std::size_t(b.factor)];
    const double r = std::max(std::exp(-0.03 * std::fabs(ta - tb) / std::min(ta, tb)), 0.4);
    return same_curve ? r : r * 0.999;
}

/// MAR21.6: 0 high, 1 medium, 2 low.
double scenario_of(double x, std::size_t s) {
    if (s == 0) return std::min(1.25 * x, 1.0);
    if (s == 1) return x;
    return std::max(2.0 * x - 1.0, 0.75 * x);
}

}  // namespace

GirrResult frtb_girr_delta(const std::vector<GirrSensitivity>& sensitivities, bool specified_currency_reduction,
                           const std::optional<std::string>& reporting_currency) {
    for (const auto& s : sensitivities) require_finite(s.sensitivity, "sensitivity");
    if (sensitivities.empty()) throw Error("E_INPUT", "sensitivities needs at least one entry", "sensitivities");
    std::set<std::tuple<std::string, std::string, GirrFactor>> seen;
    std::map<std::string, std::vector<std::size_t>> buckets;
    for (std::size_t i = 0; i < sensitivities.size(); ++i) {
        const auto& s = sensitivities[i];
        if (!seen.insert({s.currency, s.curve, s.factor}).second)
            throw Error("E_INPUT", "a currency, curve and risk factor appear twice", "sensitivities");
        buckets[s.currency].push_back(i);
    }
    const auto reduced = [&](const std::string& ccy) {
        if (!specified_currency_reduction) return false;
        for (const std::string_view l : reduced_currencies)
            if (ccy == l) return true;
        return reporting_currency && ccy == *reporting_currency;
    };
    std::vector<double> ws(sensitivities.size());
    for (std::size_t i = 0; i < sensitivities.size(); ++i) {
        double rw = risk_weight(sensitivities[i].factor);
        if (reduced(sensitivities[i].currency)) rw /= std::sqrt(2.0);
        ws[i] = rw * sensitivities[i].sensitivity;
    }
    GirrResult out{};
    for (std::size_t sc = 0; sc < 3; ++sc) {
        GirrScenario& g = out.scenarios[sc];
        for (const auto& [ccy, idx] : buckets) {
            double sum = 0.0, s = 0.0;
            for (const std::size_t k : idx) {
                s += ws[k];
                for (const std::size_t l : idx)
                    sum += k == l ? ws[k] * ws[k]
                                  : scenario_of(rho_medium(sensitivities[k], sensitivities[l]), sc) * ws[k] * ws[l];
            }
            g.buckets.push_back({ccy, std::sqrt(std::max(0.0, sum)), s, s});
        }
        const double gamma = scenario_of(0.5, sc);
        const auto total = [&](bool alt) {
            double t = 0.0;
            for (std::size_t b = 0; b < g.buckets.size(); ++b) {
                t += g.buckets[b].k * g.buckets[b].k;
                for (std::size_t c = 0; c < g.buckets.size(); ++c)
                    if (b != c) {
                        const double sb = alt ? g.buckets[b].s_used : g.buckets[b].s;
                        const double sc_ = alt ? g.buckets[c].s_used : g.buckets[c].s;
                        t += gamma * sb * sc_;
                    }
            }
            return t;
        };
        double t = total(false);
        g.alternative_used = false;
        if (t < 0.0) {
            g.alternative_used = true;
            for (auto& b : g.buckets) b.s_used = std::max(std::min(b.s, b.k), -b.k);
            t = total(true);
        }
        g.delta = std::sqrt(std::max(0.0, t));
    }
    out.binding = 0;
    for (std::size_t sc = 1; sc < 3; ++sc)
        if (out.scenarios[sc].delta > out.scenarios[out.binding].delta) out.binding = sc;
    out.capital = out.scenarios[out.binding].delta;
    return out;
}

}  // namespace quantforge
