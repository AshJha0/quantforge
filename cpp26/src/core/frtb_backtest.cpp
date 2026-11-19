#include "quantforge/core/frtb_backtest.hpp"

#include <algorithm>
#include <cmath>
#include <string_view>

#include "quantforge/core/error.hpp"
#include "quantforge/core/json.hpp"

namespace quantforge::frtb_backtest {
namespace {

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wc23-extensions"
#endif
constexpr unsigned char table_bytes[] = {
#embed "../../../specifications/06-risk/frtb-ima-backtest-tables.json"
};
#if defined(__clang__)
#pragma clang diagnostic pop
#endif

Tables parse_tables() {
    const std::string_view text(reinterpret_cast<const char*>(table_bytes), sizeof table_bytes);
    const auto parsed = json::parse(text);
    const json::Value& d = parsed.value;
    const auto num = [&d](std::string_view k) { return d.find(k)->number; };
    Tables t{};
    t.coverage = num("coverage");
    t.amber_level = num("amber_from_cumulative");
    t.red_level = num("red_from_cumulative");
    t.table_observations = (long long)num("table_observations");
    for (const json::Value& m : d.find("multiplier_250")->items) t.multiplier_250.push_back(m.number);
    t.multiplier_red = num("multiplier_red");
    t.desk_limit_99 = (long long)num("desk_limit_99");
    t.desk_limit_975 = (long long)num("desk_limit_975");
    t.max_observations = (long long)num("max_observations");
    return t;
}

// Compensated running sum of binomial terms in log space, with a running log binomial coefficient, as
// backtest_traffic_light builds its terms.
class Terms {
public:
    Terms(long long n, double p) : n_(n), lp_(std::log(p)), lq_(std::log1p(-p)) {}

    // Adds the next term and returns the partial sum P(X <= k).
    double next() {
        ++k_;
        if (k_ > 0) ln_choose_ += std::log(double(n_ - k_ + 1)) - std::log(double(k_));
        const double term = std::exp(ln_choose_ + double(k_) * lp_ + double(n_ - k_) * lq_);
        const double t = sum_ + term;
        comp_ += std::fabs(sum_) >= std::fabs(term) ? (sum_ - t) + term : (term - t) + sum_;
        sum_ = t;
        return sum_ + comp_;
    }

private:
    long long n_;
    double lp_, lq_;
    double ln_choose_ = 0.0, sum_ = 0.0, comp_ = 0.0;
    long long k_ = -1;
};

void check_observations(long long n) {
    const long long cap = tables().max_observations;
    if (n > cap) throw Error("E_LIMIT", "observations is above its limit of " + std::to_string(cap), "observations");
    if (n < 1) throw Error("E_DOMAIN", "observations must be at least 1", "observations");
}

void check_count(long long n, long long x, const char* field) {
    if (!(0 <= x && x <= n)) throw Error("E_DOMAIN", std::string(field) + " must be in [0, observations]", field);
}

std::vector<long long> days(const std::vector<std::optional<double>>& var,
                            const std::vector<std::optional<double>>& pnl) {
    std::vector<long long> out;
    for (std::size_t t = 0; t < var.size(); ++t)
        if (!var[t] || !pnl[t] || -*pnl[t] > *var[t]) out.push_back((long long)t);
    return out;
}

void finite_series(const char* field, const std::vector<std::optional<double>>& v) {
    for (const auto& x : v)
        if (x && !std::isfinite(*x)) throw Error("E_DOMAIN", std::string(field) + " must be finite", field);
}

}  // namespace

const Tables& tables() {
    static const Tables t = parse_tables();
    return t;
}

double binomial_cdf(long long n, long long x, double p) {
    if (x < 0) return 0.0;
    if (x >= n) return 1.0;
    Terms terms(n, p);
    double s = 0.0;
    for (long long k = 0; k <= x; ++k) s = terms.next();
    return std::min(s, 1.0);
}

long long first_at_least(long long n, double p, double level) {
    Terms terms(n, p);
    for (long long k = 0; k < n; ++k)
        if (terms.next() >= level) return k;
    return n;
}

Zone zone(long long observations, long long actual, long long hypothetical) {
    check_observations(observations);
    check_count(observations, actual, "exceptions_actual");
    check_count(observations, hypothetical, "exceptions_hypothetical");
    const Tables& tb = tables();
    const long long x = std::max(actual, hypothetical);
    const double p = 1.0 - tb.coverage;
    Zone z{};
    z.exceptions = x;
    z.cumulative_probability = binomial_cdf(observations, x, p);
    z.amber_from = first_at_least(observations, p, tb.amber_level);
    z.red_from = first_at_least(observations, p, tb.red_level);
    z.zone = x >= z.red_from ? "RED" : x >= z.amber_from ? "AMBER" : "GREEN";
    if (observations == tb.table_observations)
        z.multiplier = std::size_t(x) < tb.multiplier_250.size() ? tb.multiplier_250[std::size_t(x)] : tb.multiplier_red;
    return z;
}

Desk desk(long long observations, const std::array<long long, 4>& counts) {
    check_observations(observations);
    constexpr const char* fields[] = {"exceptions_99_actual", "exceptions_99_hypothetical", "exceptions_975_actual",
                                      "exceptions_975_hypothetical"};
    for (std::size_t i = 0; i < 4; ++i) check_count(observations, counts[i], fields[i]);
    const Tables& tb = tables();
    Desk out{};
    out.exceptions_99 = std::max(counts[0], counts[1]);
    out.exceptions_975 = std::max(counts[2], counts[3]);
    out.cumulative_probability_99 = binomial_cdf(observations, out.exceptions_99, 0.01);
    out.cumulative_probability_975 = binomial_cdf(observations, out.exceptions_975, 0.025);
    out.breach_99 = out.exceptions_99 > tb.desk_limit_99;
    out.breach_975 = out.exceptions_975 > tb.desk_limit_975;
    out.eligible = !(out.breach_99 || out.breach_975);
    return out;
}

Count count_exceptions(const std::vector<std::optional<double>>& var, const std::vector<std::optional<double>>& actual,
                       const std::vector<std::optional<double>>& hypothetical) {
    finite_series("var", var);
    finite_series("actual", actual);
    finite_series("hypothetical", hypothetical);
    const std::size_t n = var.size();
    if (n == 0) throw Error("E_INPUT", "var is empty", "var");
    if (actual.size() != n) throw Error("E_INPUT", "actual and var differ in length", "actual");
    if (hypothetical.size() != n) throw Error("E_INPUT", "hypothetical and var differ in length", "hypothetical");
    Count c{};
    c.observations = (long long)n;
    c.days_actual = days(var, actual);
    c.days_hypothetical = days(var, hypothetical);
    c.exceptions_actual = (long long)c.days_actual.size();
    c.exceptions_hypothetical = (long long)c.days_hypothetical.size();
    c.exceptions = std::max(c.exceptions_actual, c.exceptions_hypothetical);
    return c;
}

}  // namespace quantforge::frtb_backtest
